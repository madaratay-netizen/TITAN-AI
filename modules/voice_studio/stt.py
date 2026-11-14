"""TITAN AI — Voice Studio speech-to-text.

Primary engine: whisper.cpp (binary on PATH).
Alternative:    faster-whisper (CTranslate2, pip-installable, CPU-capable).

transcribe() returns timed segments + full text. It NEVER fabricates a
transcript: if no engine is installed it raises STTUnavailable, and the caller
is expected to surface that honestly.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from modules.voice_studio import engines
from modules.voice_studio.subtitles import Segment


class STTUnavailable(Exception):
    pass


@dataclass
class Transcript:
    text: str
    language: str = ""
    engine: str = ""
    segments: list[Segment] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"text": self.text, "language": self.language, "engine": self.engine,
                "segments": [{"start": s.start, "end": s.end, "text": s.text}
                             for s in self.segments]}


def _transcribe_faster_whisper(audio: Path, model_size: str, language: Optional[str]) -> Transcript:
    from faster_whisper import WhisperModel  # type: ignore
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(audio), language=language, vad_filter=True)
    segs, parts = [], []
    for s in segments:
        segs.append(Segment(round(s.start, 3), round(s.end, 3), s.text.strip()))
        parts.append(s.text.strip())
    return Transcript(text=" ".join(parts).strip(),
                      language=getattr(info, "language", "") or (language or ""),
                      engine=f"faster-whisper:{model_size}", segments=segs)


def _transcribe_whisper_cpp(audio: Path, binary: str, model_path: Optional[str],
                            language: Optional[str]) -> Transcript:
    if not model_path or not Path(model_path).exists():
        raise STTUnavailable(
            "whisper.cpp needs a GGML model (pass model_path, e.g. ggml-base.bin).")
    out_prefix = audio.with_suffix("")
    cmd = [binary, "-m", model_path, "-f", str(audio),
           "-oj", "-of", str(out_prefix)]
    if language:
        cmd += ["-l", language]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    json_path = Path(str(out_prefix) + ".json")
    if proc.returncode != 0 or not json_path.exists():
        raise STTUnavailable(f"whisper.cpp failed: {proc.stderr[:300]}")
    data = json.loads(json_path.read_text(encoding="utf-8"))
    segs, parts = [], []
    for t in data.get("transcription", []):
        off = t.get("offsets", {})
        start = off.get("from", 0) / 1000.0
        end = off.get("to", 0) / 1000.0
        txt = (t.get("text") or "").strip()
        segs.append(Segment(start, end, txt))
        parts.append(txt)
    return Transcript(text=" ".join(parts).strip(),
                      language=language or "", engine="whisper.cpp", segments=segs)


def transcribe(audio_path: str, model_size: str = "base",
               model_path: Optional[str] = None,
               language: Optional[str] = None) -> Transcript:
    audio = Path(audio_path)
    if not audio.is_file():
        raise FileNotFoundError(f"audio not found: {audio_path}")
    caps = engines.detect()
    if caps.whisper_cpp:
        return _transcribe_whisper_cpp(audio, caps.whisper_cpp, model_path, language)
    if caps.faster_whisper:
        return _transcribe_faster_whisper(audio, model_size, language)
    raise STTUnavailable(
        "No speech-to-text engine installed. Install whisper.cpp or "
        "`pip install faster-whisper`.")
