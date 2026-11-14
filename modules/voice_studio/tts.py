"""TITAN AI — Voice Studio text-to-speech.

Primary engine: Piper (high-quality neural TTS, Linux SSD target).
Fallback engine: pyttsx3 over the OS speech engine (SAPI5 on Windows, eSpeak on
Linux, NSSpeech on macOS) — works offline with no model download.

synthesize() writes a real WAV file and returns its path + duration. It never
fabricates audio: if no engine is available it raises TTSUnavailable.
"""
from __future__ import annotations

import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from modules.voice_studio import engines


class TTSUnavailable(Exception):
    pass


@dataclass
class TTSResult:
    path: str
    engine: str
    voice: str
    duration_s: float
    sample_rate: int


def _wav_duration(path: Path) -> tuple[float, int]:
    try:
        with wave.open(str(path), "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate()
            return (frames / rate if rate else 0.0), rate
    except Exception:
        return 0.0, 0


def _synth_pyttsx3(text: str, out: Path, voice_id: Optional[str], rate: Optional[int]) -> TTSResult:
    import pyttsx3  # type: ignore
    eng = pyttsx3.init()
    chosen = ""
    if voice_id:
        for v in eng.getProperty("voices"):
            if v.id == voice_id or voice_id.lower() in (v.name or "").lower():
                eng.setProperty("voice", v.id)
                chosen = v.name or v.id
                break
    if rate:
        eng.setProperty("rate", rate)
    eng.save_to_file(text, str(out))
    eng.runAndWait()
    try:
        eng.stop()
    except Exception:
        pass
    if not out.exists() or out.stat().st_size == 0:
        raise TTSUnavailable("pyttsx3 produced no audio (no system voice?)")
    dur, sr = _wav_duration(out)
    return TTSResult(str(out), "pyttsx3", chosen or "system-default", round(dur, 2), sr)


def _synth_piper(text: str, out: Path, model_path: str) -> TTSResult:
    caps = engines.detect()
    if not caps.piper:
        raise TTSUnavailable("Piper binary not found")
    if not Path(model_path).exists():
        raise TTSUnavailable(f"Piper voice model not found: {model_path}")
    proc = subprocess.run(
        [caps.piper, "--model", model_path, "--output_file", str(out)],
        input=text, text=True, capture_output=True, timeout=120)
    if proc.returncode != 0 or not out.exists():
        raise TTSUnavailable(f"Piper failed: {proc.stderr[:300]}")
    dur, sr = _wav_duration(out)
    return TTSResult(str(out), "piper", Path(model_path).stem, round(dur, 2), sr)


def synthesize(text: str, out_path: str, voice: Optional[str] = None,
               rate: Optional[int] = None, piper_model: Optional[str] = None) -> TTSResult:
    """Synthesize `text` to `out_path` (WAV). Prefers Piper if a model is given."""
    if not text.strip():
        raise ValueError("empty text")
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    caps = engines.detect()
    if piper_model and caps.piper:
        return _synth_piper(text, out, piper_model)
    if caps.pyttsx3:
        return _synth_pyttsx3(text, out, voice, rate)
    if caps.piper and piper_model:
        return _synth_piper(text, out, piper_model)
    raise TTSUnavailable(
        "No TTS engine available. Install Piper (+ a voice model) or pyttsx3.")
