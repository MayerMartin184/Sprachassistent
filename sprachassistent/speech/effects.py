"""Lokale Audio-Effekte für Charakterstimmen (16 kHz, mono, int16).

Eine Effektkette ist eine Liste von Tupeln (Name, Parameter...). Alles läuft mit numpy, ohne Zusatzpakete.
"""

from __future__ import annotations

import io
import wave

import numpy as np

SR = 16000


def _ola_time_stretch(x: np.ndarray, factor: float, grain: int = 1024) -> np.ndarray:
    """Zeit dehnen/stauchen ohne Tonhöhenänderung (einfaches Overlap-Add). factor > 1 = länger."""
    if abs(factor - 1.0) < 1e-3 or len(x) < grain * 2:
        return x
    hop_out = grain // 2
    hop_in = int(hop_out / factor)
    window = np.hanning(grain).astype(np.float32)
    out_len = int(len(x) * factor) + grain
    out = np.zeros(out_len, dtype=np.float32)
    norm = np.zeros(out_len, dtype=np.float32)
    pos_in, pos_out = 0, 0
    while pos_in + grain <= len(x) and pos_out + grain <= out_len:
        out[pos_out : pos_out + grain] += x[pos_in : pos_in + grain] * window
        norm[pos_out : pos_out + grain] += window
        pos_in += hop_in
        pos_out += hop_out
    norm[norm < 1e-3] = 1.0
    return (out / norm)[: int(len(x) * factor)]


def pitch_shift(x: np.ndarray, semitones: float) -> np.ndarray:
    """Tonhöhe verschieben, Dauer beibehalten (Resampling + Zeitkorrektur)."""
    ratio = 2 ** (semitones / 12)
    idx = np.arange(0, len(x), ratio)
    resampled = np.interp(idx, np.arange(len(x)), x).astype(np.float32)  # kürzer bei ratio>1
    stretched = _ola_time_stretch(resampled, ratio)
    if len(stretched) < len(x):
        stretched = np.pad(stretched, (0, len(x) - len(stretched)))
    return stretched[: len(x)]


def distortion(x: np.ndarray, drive: float) -> np.ndarray:
    return np.tanh(x * drive) / np.tanh(drive)


def lowpass(x: np.ndarray, cutoff_hz: float) -> np.ndarray:
    alpha = float(np.exp(-2 * np.pi * cutoff_hz / SR))
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):  # einpolig, ausreichend schnell für Sprachlängen
        acc = alpha * acc + (1 - alpha) * v
        y[i] = acc
    return y


def highpass(x: np.ndarray, cutoff_hz: float) -> np.ndarray:
    return x - lowpass(x, cutoff_hz)


def reverb(x: np.ndarray, decay_s: float, mix: float) -> np.ndarray:
    n = int(decay_s * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(7)
    ir = rng.standard_normal(n).astype(np.float32) * np.exp(-3 * t / decay_s)
    ir[0] = 1.0
    ir /= np.sqrt(np.sum(ir**2))
    size = 1 << int(np.ceil(np.log2(len(x) + n)))
    wet = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size))[: len(x)]
    return (1 - mix) * x + mix * wet.astype(np.float32)


def ring_mod(x: np.ndarray, freq_hz: float, depth: float = 1.0) -> np.ndarray:
    t = np.arange(len(x)) / SR
    carrier = (1 - depth) + depth * np.sin(2 * np.pi * freq_hz * t)
    return x * carrier.astype(np.float32)


def tremolo(x: np.ndarray, rate_hz: float, depth: float = 0.5) -> np.ndarray:
    t = np.arange(len(x)) / SR
    return x * (1 - depth / 2 + depth / 2 * np.sin(2 * np.pi * rate_hz * t)).astype(np.float32)


def flanger(x: np.ndarray, rate_hz: float = 0.6, depth_ms: float = 3.0, mix: float = 0.5) -> np.ndarray:
    t = np.arange(len(x)) / SR
    delay = (depth_ms / 1000 * SR) * (1 + np.sin(2 * np.pi * rate_hz * t)) / 2 + 1
    idx = np.arange(len(x)) - delay
    delayed = np.interp(np.clip(idx, 0, len(x) - 1), np.arange(len(x)), x)
    return (1 - mix) * x + mix * delayed.astype(np.float32)


def bitcrush(x: np.ndarray, bits: int, downsample: int = 1) -> np.ndarray:
    steps = 2 ** (bits - 1)
    y = np.round(x * steps) / steps
    if downsample > 1:
        y = np.repeat(y[::downsample], downsample)[: len(x)]
    return y.astype(np.float32)


def noise(x: np.ndarray, level: float) -> np.ndarray:
    rng = np.random.default_rng(3)
    return x + rng.standard_normal(len(x)).astype(np.float32) * level


def bandpass(x: np.ndarray, low_hz: float, high_hz: float) -> np.ndarray:
    return highpass(lowpass(x, high_hz), low_hz)


def compress(x: np.ndarray, threshold: float = 0.25, ratio: float = 4.0, makeup: float = 1.6) -> np.ndarray:
    """Einfacher Kompressor: laute Stellen zusammendrücken, Gesamtpegel anheben (gepresster, druckvoller Klang)."""
    env = lowpass(np.abs(x), 25.0)
    gain = np.where(env > threshold, (threshold + (env - threshold) / ratio) / np.maximum(env, 1e-6), 1.0)
    return (x * gain * makeup).astype(np.float32)


def _breath_cycle(seconds_in: float = 0.9, seconds_out: float = 1.1, level: float = 0.28) -> np.ndarray:
    """Ein Atemzug: gefiltertes Rauschen mit Ein- und Ausatem-Hüllkurve (Maskenatmung)."""
    rng = np.random.default_rng(11)
    n_in, n_out, gap = int(seconds_in * SR), int(seconds_out * SR), int(0.12 * SR)
    noise_in = bandpass(rng.standard_normal(n_in).astype(np.float32), 350, 1400)
    noise_out = bandpass(rng.standard_normal(n_out).astype(np.float32), 250, 1000)
    env_in = np.sin(np.linspace(0, np.pi, n_in)) ** 1.4
    env_out = np.sin(np.linspace(0, np.pi, n_out)) ** 1.1
    breath = np.concatenate([noise_in * env_in * 0.9, np.zeros(gap, dtype=np.float32), noise_out * env_out])
    breath /= max(float(np.max(np.abs(breath))), 1e-6)
    return (breath * level).astype(np.float32)


def breath(x: np.ndarray, before: bool = True, after: bool = True) -> np.ndarray:
    """Hängt Maskenatmung vor und/oder nach die Sprache (Vader-Stil)."""
    parts = []
    pause = np.zeros(int(0.35 * SR), dtype=np.float32)
    if before:
        parts += [_breath_cycle(), pause]
    parts.append(x)
    if after:
        parts += [pause, _breath_cycle()]
    return np.concatenate(parts)


def layer(x: np.ndarray, semitones: float, gain: float) -> np.ndarray:
    """Eine tonhöhenverschobene Kopie dazumischen (Sub-Oktave, Dämonen-Chor)."""
    return x + pitch_shift(x, semitones) * gain


EFFECTS = {
    "pitch": pitch_shift, "distortion": distortion, "lowpass": lowpass, "highpass": highpass, "reverb": reverb,
    "ring_mod": ring_mod, "tremolo": tremolo, "flanger": flanger, "bitcrush": bitcrush, "noise": noise, "layer": layer,
    "bandpass": bandpass, "compress": compress, "breath": breath,
}


def apply_chain(x: np.ndarray, chain: list[tuple]) -> np.ndarray:
    y = x.astype(np.float32)
    for name, *params in chain:
        y = EFFECTS[name](y, *params)
    peak = float(np.max(np.abs(y))) or 1.0
    if peak > 0.98:
        y = y / peak * 0.98
    return y


def process_wav(wav_bytes: bytes, chain: list[tuple]) -> bytes:
    """Wendet die Effektkette auf eine WAV-Datei (16 kHz mono int16) an und gibt WAV zurück."""
    if not chain:
        return wav_bytes
    with wave.open(io.BytesIO(wav_bytes)) as wf:
        rate, channels = wf.getframerate(), wf.getnchannels()
        pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
    if channels != 1 or rate != SR:
        return wav_bytes  # unerwartetes Format: unverändert lassen
    y = apply_chain(pcm.astype(np.float32) / 32768.0, chain)
    out = (np.clip(y, -1, 1) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(out.tobytes())
    return buf.getvalue()
