import io
import wave

import numpy as np

from sprachassistent.speech import effects
from sprachassistent.speech.azure import VOICE_PRESETS, preset


def _tone(seconds=1.0, freq=180.0):
    t = np.arange(int(effects.SR * seconds)) / effects.SR
    return (0.4 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_pitch_shift_keeps_length_and_changes_pitch():
    x = _tone()
    y = effects.pitch_shift(x, -12)
    assert len(y) == len(x)
    fx, fy = np.abs(np.fft.rfft(x)), np.abs(np.fft.rfft(y))
    assert np.argmax(fy) < np.argmax(fx)  # tiefer


def test_every_preset_chain_runs_and_stays_in_range():
    x = _tone(0.5)
    for key, *_ in VOICE_PRESETS:
        voice, pitch, rate, style, fx = preset(key)
        y = effects.apply_chain(x, fx)
        has_breath = any(step[0] == "breath" for step in fx)
        assert (len(y) > len(x) if has_breath else len(y) == len(x)) and np.isfinite(y).all() and np.max(np.abs(y)) <= 0.99, key


def test_process_wav_roundtrip():
    pcm = (_tone(0.3) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(effects.SR); wf.writeframes(pcm.tobytes())
    out = effects.process_wav(buf.getvalue(), [("distortion", 2.0), ("reverb", 0.3, 0.3)])
    with wave.open(io.BytesIO(out)) as wf:
        assert wf.getframerate() == effects.SR and wf.getnframes() == len(pcm)
    assert effects.process_wav(buf.getvalue(), []) == buf.getvalue()


def test_vader_breath_adds_audio_before_and_after():
    x = _tone(0.5)
    y = effects.breath(x)
    assert len(y) > len(x) + effects.SR * 3  # zwei Atemzüge plus Pausen
    head = y[: int(0.5 * effects.SR)]
    assert np.max(np.abs(head)) > 0.02  # vorne ist Atmen hörbar
