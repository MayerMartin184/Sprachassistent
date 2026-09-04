from sprachassistent.audio.wakeword import FRAME_MS, UtteranceSegmenter, beep_wav
from sprachassistent.tools.teams import parse_vtt

FRAME = b"\x00\x00" * 1280


def _run(levels, **kw):
    seg = UtteranceSegmenter(speech_threshold=500, **kw)
    for i, level in enumerate(levels):
        result = seg.feed(FRAME, level)
        if result:
            return result, i
    return None, len(levels)


def test_segmenter_ends_after_pause():
    speech = [1000] * 10          # 800 ms Sprache
    silence = [100] * 15          # 1200 ms Stille
    result, idx = _run([0] * 3 + speech + silence)
    assert result == "done"
    assert (idx + 1) * FRAME_MS <= 3 * FRAME_MS + 800 + 1200


def test_segmenter_cancels_without_speech():
    result, _ = _run([100] * 80)
    assert result == "cancel"


def test_segmenter_respects_max_length():
    result, idx = _run([1000] * 1000, max_ms=4000)
    assert result == "done" and (idx + 1) * FRAME_MS <= 4000


def test_segmenter_discards_leading_frames_and_builds_wav():
    seg = UtteranceSegmenter(speech_threshold=500, discard_ms=160)
    for level in [1000] * 12 + [0] * 15:
        seg.feed(FRAME, level)
    wav = seg.wav()
    assert wav[:4] == b"RIFF" and len(wav) == 44 + (27 - 2) * len(FRAME)


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
