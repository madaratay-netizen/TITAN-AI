"""Voice Studio tests.

Subtitle generation and engine-detection shape are tested deterministically.
TTS / audio tests run only when an engine / ffmpeg is actually present, and
are skipped (not faked) otherwise — matching the 'no fake output' rule.
"""
import pytest

from modules.voice_studio import engines, subtitles, audio, tts, stt
from modules.voice_studio.subtitles import Segment


# -- subtitles (deterministic) ---------------------------------------------- #
def test_srt_format():
    srt = subtitles.to_srt([Segment(0, 1.5, "hello"), Segment(1.5, 3.25, "world")])
    assert "1\n00:00:00,000 --> 00:00:01,500\nhello" in srt
    assert "2\n00:00:01,500 --> 00:00:03,250\nworld" in srt


def test_vtt_format():
    vtt = subtitles.to_vtt([Segment(0, 2, "hi")])
    assert vtt.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:02.000" in vtt


def test_timestamp_hours():
    assert subtitles._fmt_ts(3661.5) == "01:01:01,500"


def test_segments_from_dicts():
    segs = subtitles.segments_from_dicts([{"start": 0, "end": 1, "text": "x"}])
    assert segs[0].end == 1.0 and segs[0].text == "x"


# -- engine detection (shape) ----------------------------------------------- #
def test_detect_shape():
    d = engines.detect().to_dict()
    assert "stt" in d and "tts" in d and "ffmpeg" in d
    assert isinstance(d["stt"]["available"], bool)
    assert isinstance(d["tts"]["available"], bool)


def test_whisper_cpp_names_are_strict():
    # Regression: 'main'/'whisper' must NOT be treated as whisper.cpp.
    assert "main" not in engines.WHISPER_CPP_BINS
    assert "whisper" not in engines.WHISPER_CPP_BINS


# -- STT honesty ------------------------------------------------------------ #
def test_stt_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        stt.transcribe("does_not_exist.wav")


def test_stt_unavailable_is_explicit(tmp_path):
    # When no engine is installed, transcribe raises STTUnavailable (never fakes).
    caps = engines.detect()
    if caps.stt_available:
        pytest.skip("an STT engine is installed on this machine")
    f = tmp_path / "a.wav"
    f.write_bytes(b"RIFF....WAVEfmt ")  # not real audio; engine check precedes read
    with pytest.raises(stt.STTUnavailable):
        stt.transcribe(str(f))


# -- TTS (integration, skipped if no engine) -------------------------------- #
def test_tts_produces_real_audio(tmp_path):
    caps = engines.detect()
    if not caps.tts_available:
        pytest.skip("no TTS engine available")
    out = tmp_path / "out.wav"
    r = tts.synthesize("TITAN voice test.", str(out))
    assert out.exists() and out.stat().st_size > 0
    assert r.duration_s > 0


def test_tts_empty_text_rejected():
    with pytest.raises(ValueError):
        tts.synthesize("   ", "ignored.wav")


# -- audio (integration, skipped if no ffmpeg) ------------------------------ #
def test_audio_duration(tmp_path):
    caps = engines.detect()
    if not (caps.ffmpeg and caps.tts_available):
        pytest.skip("need ffmpeg + a TTS engine")
    wav = tmp_path / "a.wav"
    tts.synthesize("one two three four.", str(wav))
    assert audio.duration(str(wav)) > 0
