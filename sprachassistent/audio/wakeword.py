"""Wake-Word-Erkennung („Hey Jarvis“) mit openWakeWord, danach Aufnahme bis zur Sprechpause.

Ob gesprochen wird, entscheidet eine Sprach-Aktivitätserkennung (Silero-VAD, in openWakeWord enthalten),
nicht die Lautstärke. Lange Aufträge werden an kurzen Pausen in Teilstücke geschnitten, weil die
Azure-Kurzerkennung nur einen Satz am Stück verarbeitet.
"""

from __future__ import annotations

import logging
import math
import threading
from pathlib import Path
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
    """Sammelt Frames nach dem Wake-Word, bis der Nutzer eine längere Pause macht.

    Reine Logik ohne Audio-Geräte, damit sie testbar bleibt.
    feed() erhält pro Frame die Sprachwahrscheinlichkeit (0..1) und liefert
    None (weiter), "done" (Äußerung fertig) oder "cancel" (nichts gesagt).
    """

    def __init__(
        self,
        vad_threshold: float = 0.5,
        end_silence_ms: int = 1500,
        chunk_pause_ms: int = 600,
        max_ms: int = 60000,
        no_speech_ms: int = 6000,
        min_speech_ms: int = 240,
        discard_ms: int = 240,
    ) -> None:
        self.vad_threshold = vad_threshold
        self.end_silence_ms = end_silence_ms
        self.chunk_pause_ms = chunk_pause_ms
        self.max_ms = max_ms
        self.no_speech_ms = no_speech_ms
        self.min_speech_ms = min_speech_ms
        self.discard_ms = discard_ms
        self._frames: list[bytes] = []
        self._cuts: list[int] = []  # Frame-Indizes, an denen ein Teilstück endet
        self._chunk_speech: list[int] = []  # Sprachdauer (ms) je abgeschlossenem Teilstück
        self._elapsed = 0
        self._speech_ms = 0
        self._chunk_speech_ms = 0
        self._silence_run = 0
        self._cut_done = False

    def feed(self, frame: bytes, speech_prob: float) -> str | None:
        self._elapsed += FRAME_MS
        if self._elapsed <= self.discard_ms:
            return None  # Bestätigungston / Nachhall des Wake-Words überspringen
        self._frames.append(frame)
        if speech_prob >= self.vad_threshold:
            self._speech_ms += FRAME_MS
            self._chunk_speech_ms += FRAME_MS
            self._silence_run = 0
            self._cut_done = False
        else:
            self._silence_run += FRAME_MS
            if self._silence_run >= self.chunk_pause_ms and not self._cut_done and self._chunk_speech_ms >= self.min_speech_ms:
                self._cuts.append(len(self._frames))
                self._chunk_speech.append(self._chunk_speech_ms)
                self._chunk_speech_ms = 0
                self._cut_done = True
        if self._speech_ms < self.min_speech_ms:
            return "cancel" if self._elapsed >= self.no_speech_ms else None
        if self._silence_run >= self.end_silence_ms or self._elapsed >= self.max_ms:
            return "done"
        return None

    def wavs(self) -> list[bytes]:
        """Teilstücke als WAV. Stücke ohne Sprache entfallen; die Endpause wird ans letzte Stück angehängt."""
        bounds = [0] + [c for c in self._cuts if c < len(self._frames)] + [len(self._frames)]
        speech = self._chunk_speech[: len(bounds) - 2] + [self._chunk_speech_ms]
        chunks: list[list[bytes]] = []
        for (start, end), ms in zip(zip(bounds, bounds[1:]), speech):
            frames = self._frames[start:end]
            if ms >= self.min_speech_ms:
                chunks.append(frames)
            elif chunks:
                chunks[-1].extend(frames[:4])  # etwas Nachlauf, damit das Wortende nicht abgeschnitten wird
        if not chunks:
            return [pcm_to_wav(b"".join(self._frames), SAMPLE_RATE)]
        return [pcm_to_wav(b"".join(c), SAMPLE_RATE) for c in chunks]


_MODEL_CACHE: dict[str, tuple] = {}


def preload_models(model_name: str = "hey_jarvis") -> None:
    """Lädt Wake-Word- und VAD-Modell einmalig (z. B. vor dem Öffnen des Fensters) und hält sie im Speicher."""
    if model_name in _MODEL_CACHE:
        return
    import openwakeword
    from openwakeword.model import Model
    from openwakeword.vad import VAD

    models_dir = Path(openwakeword.__file__).parent / "resources" / "models"
    needed = ["melspectrogram.onnx", "embedding_model.onnx", "silero_vad.onnx", f"{model_name}_v0.1.onnx"]
    if not all((models_dir / n).exists() for n in needed):
        log.info("Lade Wake-Word-Modelle herunter …")
        openwakeword.utils.download_models(model_names=[model_name])
    _MODEL_CACHE[model_name] = (Model(wakeword_models=[model_name], inference_framework="onnx"), VAD())


class WakeWordListener:
    """Hintergrund-Thread: hört dauerhaft zu, meldet Zustände und liefert fertige Äußerungen als WAV-Teilstücke."""

    def __init__(
        self,
        on_utterance: Callable[[list[bytes]], None],
        on_state: Callable[[str], None],
        model_name: str = "hey_jarvis",
        threshold: float = 0.5,
        device: int | None = None,
        end_silence_ms: int = 1500,
        vad_threshold: float = 0.5,
        attention_ms: int = 20000,
    ) -> None:
        self.on_utterance = on_utterance
        self.on_state = on_state
        self.model_name = model_name
        self.threshold = threshold
        self.device = device
        self.end_silence_ms = end_silence_ms
        self.vad_threshold = vad_threshold
        self.attention_ms = attention_ms  # nach einer Antwort so lange ohne Wake-Word zuhören
        self._attention_left = 0
        self._speech_run = 0
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._thread: threading.Thread | None = None
        self._noise = 200.0
        self.level = 0.0  # 0..1, aktueller Mikrofonpegel für die Visualisierung
        self.score = 0.0  # höchster Wake-Word-Wert der letzten ~2 s (Diagnose/Feinjustierung)
        self.device_name = ""
        self._score_frames = 0

    # --- Steuerung ------------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="wakeword", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def restart(self, device: int | None) -> None:
        """Neues Mikrofon übernehmen (Gerätewechsel im laufenden Betrieb)."""
        self.stop()
        self.device = device
        self.start()

    def pause(self) -> None:
        self._paused.set()

    def resume(self, attentive: bool = False) -> None:
        """Weiter zuhören; mit attentive=True zunächst ohne Wake-Word (Nachfrage-Fenster)."""
        self._attention_left = self.attention_ms if attentive else 0
        self._speech_run = 0
        self._paused.clear()

    @property
    def attentive(self) -> bool:
        return self._attention_left > 0

    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    # --- Schleife -------------------------------------------------------------
    def _load_models(self):  # noqa: ANN202
        preload_models(self.model_name)
        model, vad = _MODEL_CACHE[self.model_name]
        model.reset()
        return model, vad

    def _run(self) -> None:
        import numpy as np
        import sounddevice as sd

        try:
            model, vad = self._load_models()
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
                try:
                    self.device_name = sd.query_devices(stream.device)["name"]
                except Exception:  # noqa: BLE001
                    self.device_name = str(stream.device)
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
                        self.on_state("attentive" if self._attention_left > 0 else "listening")
                    samples = np.frombuffer(frame, dtype=np.int16)
                    level = rms(frame)
                    self.level = max(0.0, min(1.0, (level - self._noise) / max(self._noise * 6.0, 1500.0)))

                    if segment is None and self._attention_left > 0:
                        # Nachfrage-Fenster: Sprache startet die Aufnahme direkt, ohne Wake-Word
                        self._attention_left -= FRAME_MS
                        speech_prob = float(vad.predict(samples, frame_size=640))
                        self.level = max(self.level, speech_prob * 0.6)
                        self._speech_run = self._speech_run + FRAME_MS if speech_prob >= self.vad_threshold else 0
                        if self._speech_run >= 240:
                            self._attention_left = 0
                            self.on_state("wake")
                            segment = UtteranceSegmenter(vad_threshold=self.vad_threshold, end_silence_ms=self.end_silence_ms, discard_ms=0)
                            for _ in range(3):  # die bereits gehörten Sprachframes gehören dazu
                                segment.feed(frame, speech_prob)
                        elif self._attention_left <= 0:
                            model.reset()
                            self.on_state("listening")
                        continue

                    if segment is None:
                        self._noise = 0.97 * self._noise + 0.03 * level
                        score = float(model.predict(samples)[self.model_name])
                        self._score_frames += 1
                        if score >= self.score or self._score_frames >= 25:  # ~2 s Haltezeit
                            self.score, self._score_frames = score, 0
                        if score >= self.threshold:
                            model.reset()
                            self.on_state("wake")
                            segment = UtteranceSegmenter(vad_threshold=self.vad_threshold, end_silence_ms=self.end_silence_ms)
                        continue

                    speech_prob = float(vad.predict(samples, frame_size=640))
                    self.level = max(self.level, speech_prob * 0.6)
                    result = segment.feed(frame, speech_prob)
                    if result == "done":
                        wavs = segment.wavs()
                        segment = None
                        self._paused.set()  # bis die Antwort gesprochen ist, nicht erneut auslösen
                        self.on_state("processing")
                        self.on_utterance(wavs)
                    elif result == "cancel":
                        segment = None
                        self.on_state("cancel")
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
