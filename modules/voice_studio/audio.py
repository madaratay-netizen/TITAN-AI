"""TITAN AI — Voice Studio audio helpers (ffmpeg).

Thin wrappers over ffmpeg/ffprobe for duration, format conversion, and
concatenation. ffmpeg is detected at call time; if absent, a clear error is
raised rather than silently doing nothing.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


class AudioError(Exception):
    pass


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise AudioError("ffmpeg not found on PATH")
    return exe


def _ffprobe() -> str | None:
    return shutil.which("ffprobe")


def duration(path: str) -> float:
    """Return media duration in seconds (ffprobe, else ffmpeg stderr parse)."""
    p = Path(path)
    if not p.is_file():
        raise AudioError(f"file not found: {path}")
    probe = _ffprobe()
    if probe:
        out = subprocess.run(
            [probe, "-v", "quiet", "-print_format", "json", "-show_format", str(p)],
            capture_output=True, text=True, timeout=30)
        try:
            return float(json.loads(out.stdout)["format"]["duration"])
        except (ValueError, KeyError):
            pass
    # Fallback: parse ffmpeg -i stderr.
    out = subprocess.run([_ffmpeg(), "-i", str(p)], capture_output=True, text=True)
    import re
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", out.stderr)
    if m:
        h, mi, s = m.groups()
        return int(h) * 3600 + int(mi) * 60 + float(s)
    raise AudioError("could not determine duration")


def convert(src: str, dst: str, bitrate: str = "192k") -> str:
    """Convert audio to the format implied by dst's extension (e.g. .mp3)."""
    s, d = Path(src), Path(dst)
    if not s.is_file():
        raise AudioError(f"source not found: {src}")
    d.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [_ffmpeg(), "-y", "-i", str(s), "-b:a", bitrate, str(d)],
        capture_output=True, text=True, timeout=300)
    if proc.returncode != 0 or not d.exists():
        raise AudioError(f"conversion failed: {proc.stderr[-300:]}")
    return str(d)


def concat(inputs: list[str], dst: str) -> str:
    """Concatenate same-codec audio files via the ffmpeg concat demuxer."""
    if not inputs:
        raise AudioError("no inputs")
    for i in inputs:
        if not Path(i).is_file():
            raise AudioError(f"input not found: {i}")
    d = Path(dst)
    d.parent.mkdir(parents=True, exist_ok=True)
    listfile = d.with_suffix(".concat.txt")
    listfile.write_text(
        "\n".join(f"file '{Path(i).resolve().as_posix()}'" for i in inputs),
        encoding="utf-8")
    try:
        proc = subprocess.run(
            [_ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
             "-c", "copy", str(d)],
            capture_output=True, text=True, timeout=300)
    finally:
        try:
            listfile.unlink()
        except OSError:
            pass
    if proc.returncode != 0 or not d.exists():
        raise AudioError(f"concat failed: {proc.stderr[-300:]}")
    return str(d)
