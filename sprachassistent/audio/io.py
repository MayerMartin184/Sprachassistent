"""Mikrofonaufnahme und Wiedergabe (sounddevice, 16 kHz mono int16)."""

from __future__ import annotations

import io
import wave

SAMPLE_RATE = 16000


class Recorder:
    def __init__(self, samplerate: int = SAMPLE_RATE) -> None:
        self.samplerate = samplerate
        self._frames: list[bytes] = []
        self._stream = None

    @property
    def recording(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        import sounddevice as sd

        if self._stream is not None:
            return
        self._frames = []

        def callback(indata, _frames, _time, status) -> None:  # noqa: ANN001
            self._frames.append(bytes(indata))

        self._stream = sd.RawInputStream(samplerate=self.samplerate, channels=1, dtype="int16", callback=callback)
        self._stream.start()

    def stop(self) -> bytes:
        if self._stream is None:
            return b""
        self._stream.stop()
        self._stream.close()
        self._stream = None
        return pcm_to_wav(b"".join(self._frames), self.samplerate)

    def duration_seconds(self, wav_bytes: bytes) -> float:
        with wave.open(io.BytesIO(wav_bytes)) as wf:
            return wf.getnframes() / wf.getframerate()


def pcm_to_wav(pcm: bytes, samplerate: int = SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(pcm)
    return buf.getvalue()


def play_wav(wav_bytes: bytes, device: int | None = None) -> None:
    import numpy as np
    import sounddevice as sd

    with wave.open(io.BytesIO(wav_bytes)) as wf:
        rate = wf.getframerate()
        data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
    sd.play(data, rate, device=device)
    sd.wait()


def list_devices(kind: str = "input") -> list[tuple[int, str, bool]]:
    """(Index, Name, ist Standard) aller Ein- ("input") oder Ausgabegeräte ("output")."""
    import sounddevice as sd

    pos = 0 if kind == "input" else 1
    default = sd.default.device[pos] if isinstance(sd.default.device, (list, tuple)) else sd.default.device
    key = "max_input_channels" if kind == "input" else "max_output_channels"
    devices = []
    for idx, dev in enumerate(sd.query_devices()):
        if dev.get(key, 0) > 0:
            devices.append((idx, dev["name"], idx == default))
    return devices


def list_input_devices() -> list[tuple[int, str, bool]]:
    return list_devices("input")


def resolve_device(selector: str | None, kind: str = "input") -> int | None:
    """Wandelt Name (Teilstring, Groß-/Kleinschreibung egal) oder Nummer in einen Geräteindex um."""
    if not selector:
        return None
    devices = list_devices(kind)
    if selector.strip().isdigit():
        idx = int(selector)
        if any(d[0] == idx for d in devices):
            return idx
        raise ValueError(f"Kein {'Eingabe' if kind == 'input' else 'Ausgabe'}gerät mit Nummer {idx}")
    needle = selector.strip().lower()
    for idx, name, _ in devices:
        if needle in name.lower():
            return idx
    raise ValueError(f"Kein {'Mikrofon' if kind == 'input' else 'Lautsprecher'} mit '{selector}' im Namen gefunden")


def resolve_input_device(selector: str | None) -> int | None:
    return resolve_device(selector, "input")
