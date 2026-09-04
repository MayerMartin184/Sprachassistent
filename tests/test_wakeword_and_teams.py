from sprachassistent.audio.wakeword import FRAME_MS, UtteranceSegmenter, beep_wav
from sprachassistent.tools.teams import parse_vtt

FRAME = b"\x00\x00" * 1280


def _run(probs, **kw):
    seg = UtteranceSegmenter(vad_threshold=0.5, **kw)
    for i, prob in enumerate(probs):
        result = seg.feed(FRAME, prob)
        if result:
            return result, i, seg
    return None, len(probs), seg


def test_segmenter_ends_after_pause():
    speech = [0.9] * 10          # 800 ms Sprache
    silence = [0.1] * 19         # 1520 ms Stille
    result, idx, _ = _run([0] * 3 + speech + silence)
    assert result == "done"
    assert (idx + 1) * FRAME_MS <= 3 * FRAME_MS + 800 + 1520


def test_segmenter_cancels_without_speech():
    result, _, _ = _run([0.1] * 100)
    assert result == "cancel"


def test_segmenter_respects_max_length():
    result, idx, _ = _run([0.9] * 1000, max_ms=4000)
    assert result == "done" and (idx + 1) * FRAME_MS <= 4000


def test_segmenter_discards_leading_frames_and_builds_wav():
    seg = UtteranceSegmenter(vad_threshold=0.5, discard_ms=160)
    for prob in [0.9] * 12 + [0.0] * 19:
        seg.feed(FRAME, prob)
    wavs = seg.wavs()
    # 10 Sprachframes (2 verworfen) + 8 Frames Pause bis zum Schnitt + 4 Frames Nachlauf; restliche Stille entfällt
    assert len(wavs) == 1 and wavs[0][:4] == b"RIFF" and len(wavs[0]) == 44 + 22 * len(FRAME)


def test_segmenter_splits_long_utterance_at_short_pauses():
    # Satz 1 (1 s), Pause 0,7 s, Satz 2 (1 s), Ende 1,6 s
    probs = [0] * 3 + [0.9] * 13 + [0.1] * 9 + [0.9] * 13 + [0.1] * 20
    result, _, seg = _run(probs)
    assert result == "done"
    wavs = seg.wavs()
    assert len(wavs) == 2 and all(w[:4] == b"RIFF" for w in wavs)


def test_beep_is_wav():
    assert beep_wav()[:4] == b"RIFF"


def test_parse_vtt_merges_speakers():
    vtt = """WEBVTT

1
00:00:01.000 --> 00:00:03.000
<v Martin Mayer>Hallo zusammen,</v>

2
00:00:03.000 --> 00:00:05.000
<v Martin Mayer>wir starten mit dem Angebot.</v>

00:00:05.500 --> 00:00:07.000
<v Anna Schmidt>Ich schicke <b>heute</b> die Zahlen.</v>
"""
    assert parse_vtt(vtt) == "Martin Mayer: Hallo zusammen, wir starten mit dem Angebot.\nAnna Schmidt: Ich schicke heute die Zahlen."
