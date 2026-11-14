"""ADWIN OS — Voice Studio subtitle generation.

Converts timed transcription segments into SRT and WebVTT. Pure standard
library and fully deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Segment:
    start: float   # seconds
    end: float
    text: str


def _fmt_ts(seconds: float, sep: str = ",") -> str:
    if seconds < 0:
        seconds = 0.0
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def to_srt(segments: list[Segment]) -> str:
    lines = []
    for i, seg in enumerate(segments, 1):
        lines.append(str(i))
        lines.append(f"{_fmt_ts(seg.start)} --> {_fmt_ts(seg.end)}")
        lines.append(seg.text.strip())
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def to_vtt(segments: list[Segment]) -> str:
    lines = ["WEBVTT", ""]
    for seg in segments:
        lines.append(f"{_fmt_ts(seg.start, '.')} --> {_fmt_ts(seg.end, '.')}")
        lines.append(seg.text.strip())
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def segments_from_dicts(items: list[dict]) -> list[Segment]:
    return [Segment(float(d["start"]), float(d["end"]), str(d.get("text", "")))
            for d in items]
