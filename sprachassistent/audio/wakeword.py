"""Wake-Word-Erkennung („Hey Jarvis“) mit openWakeWord und anschließende Aufnahme bis zur Sprechpause."""

from __future__ import annotations

import logging
import math
import threading
from typing import Callable

from .io import SAMPLE_RATE, pcm_to_wav

log = logging.getLogger(__name__)

FRAME_SAMPLES = 1280  # 80 ms bei 16 kHz, von openWakeWord erwartet
FRAME_MS = 80


def rms(frame: bytes) -> float:
    import numpy as np

    data = np.frombuffer(frame, dtype=np.int16).astype(np.float32)
    return float(math.sqrt(float(np.mean(data * data)))) if len(data) else 0.0


class UtteranceSegmenter:
    """Sammelt Frames nach dem Wake-Word, bis der Nutzer eine Pause macht.

    Reine Logik ohne Audio-Geräte, damit sie testbar bleibt.
    Rückgabe von feed(): None (weiter), "done" (Äußerung fertig) oder "cancel" (nichts gesagt).
    """

    def __init__(
        self,
        speech_threshold: float,
        silence_ms: int = 1200,
        max_ms: int = 30000,
        no_speech_ms: int = 5000,
        min_speech_ms: int = 240,
        discard_ms: int = 240,
    ) -> None:
        self.speech_threshold = speech_threshold
        self.silence_ms = silence_ms
        self.max_ms = max_ms
        self.no_speech_ms = no_speech_ms
        self.min_speech_ms = min_speech_ms
        self.discard_ms = discard_ms
        self._frames: list[bytes] = []
        self._elapsed = 0
        self._speech_ms = 0
        self._silence_run = 0

    def feed(self, frame: bytes, level: float) -> str | None:
        self._elapsed += FRAME_MS
        if self._elapsed <= self.discard_ms:
            return None  # Bestätigungston / Nachhall des Wake-Words überspringen
        self._frames.append(frame)
        if level >= self.speech_threshold:
            self._speech_ms += FRAME_MS
            self._silence_run = 0
        else:
            self._silence_run += FRAME_MS
        if self._speech_ms < self.min_speech_ms:
            return "cancel" if self._elapsed >= self.no_speech_ms else None
        if self._silence_run >= self.silence_ms or self._elapsed >= self.max_ms:
            return "done"
        return None

    def wav(self) -> bytes:
        return pcm_to_wav(b"".join(self._frames), SAMPLE_RATE)


class WakeWordListener:
    """Hintergrund-Thread: hört dauerhaft zu, meldet Zustände und liefert fertige Äußerungen als WAV."""

    def __init__(
        self,
        on_utterance: Callable[[bytes], None],
        on_state: Callable[[str], None],
        model_name: str = "hey_jarvis",
        threshold: float = 0.5,
        device: int | None = None,
    ) -> None:
        self.on_utterance = on_utterance
        self.on_state = on_state
        self.model_name = model_name
        self.threshold = threshold
        self.device = device
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._thread: threading.Thread | None = None
        self._noise = 200.0
        self.level = 0.0  # 0..1, aktueller Mikrofonpegel für die Visualisierung

    # --- Steuerung ------------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="wakeword", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def pause(self) -> None:
        """Nicht reagieren (z. B. während Sprachausgabe oder Verarbeitung)."""
        self._paused.set()

    def resume(self) -> None:
        self._paused.clear()

    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    # --- Schleife -------------------------------------------------------------
    def _load_model(self):  # noqa: ANN202
        import openwakeword
        from openwakeword.model import Model

        try:
            openwakeword.utils.download_models(model_names=[self.model_name])
        except Exception as exc:  # noqa: BLE001 - offline: vorhandene Modelle weiterverwenden
            log.warning("Wake-Word-Modelle konnten nicht geladen/aktualisiert werden: %s", exc)
        return Model(wakeword_models=[self.model_name], inference_framework="onnx")

    def _run(self) -> None:
        import numpy as np
        import sounddevice as sd

        try:
            model = self._load_model()
        except Exception as exc:  # noqa: BLE001
            log.exception("Wake-Word-Modell nicht ladbar")
            self.on_state(f"error:{exc}")
            return

        segment: UtteranceSegmenter | None = None
        was_paused = False
        try:
            with sd.RawInputStream(
                samplerate=SAMPLE_RATE, blocksize=FRAME_SAMPLES, channels=1, dtype="int16", device=self.device
            ) as stream:
                self.on_state("listening")
                while not self._stop.is_set():
                    data, _overflow = stream.read(FRAME_SAMPLES)
                    frame = bytes(data)
                    if self._paused.is_set():
                        was_paused = True
                        segment = None
                        continue
                    if was_paused:
                        was_paused = False
                        model.reset()
                        self.on_state("listening")
                    level = rms(frame)
                    self.level = max(0.0, min(1.0, (level - self._noise) / max(self._noise * 6.0, 1500.0)))

                    if segment is None:
                        self._noise = 0.97 * self._noise + 0.03 * level
                        score = model.predict(np.frombuffer(frame, dtype=np.int16))[self.model_name]
                        if score >= self.threshold:
                            model.reset()
                            self.on_state("wake")
                            segment = UtteranceSegmenter(speech_threshold=max(self._noise * 3.0, 300.0))
                        continue

                    result = segment.feed(frame, level)
                    if result == "done":
                        wav = segment.wav()
                        segment = None
                        self._paused.set()  # bis die Antwort gesprochen ist, nicht erneut auslösen
                        self.on_state("processing")
                        self.on_utterance(wav)
                    elif result == "cancel":
                        segment = None
                        self.on_state("listening")
        except Exception as exc:  # noqa: BLE001
            log.exception("Wake-Word-Schleife abgebrochen")
            self.on_state(f"error:{exc}")


def beep_wav(freq: float = 880.0, ms: int = 120, volume: float = 0.3) -> bytes:
    """Kurzer Bestätigungston nach dem Wake-Word."""
    import numpy as np

    t = np.arange(int(SAMPLE_RATE * ms / 1000)) / SAMPLE_RATE
    env = np.minimum(1.0, np.minimum(t / 0.01, (t[-1] - t) / 0.03))
    tone = (np.sin(2 * math.pi * freq * t) * env * volume * 32767).astype(np.int16)
    return pcm_to_wav(tone.tobytes(), SAMPLE_RATE)
