"""ADWIN OS — Voice Studio API routes (local STT/TTS, offline)."""
from __future__ import annotations

import re
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from modules.voice_studio import engines, tts, stt, subtitles, audio
from backend.app.config import REPO_ROOT

router = APIRouter(prefix="/api/voice", tags=["voice"])

_VOICE_DIR = REPO_ROOT / "storage" / "workspace" / "voice"
_VOICE_DIR.mkdir(parents=True, exist_ok=True)
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


class TTSReq(BaseModel):
    text: str
    voice: str | None = None
    rate: int | None = None
    format: str = "wav"       # wav | mp3


class STTReq(BaseModel):
    path: str
    language: str | None = None


class SubReq(BaseModel):
    segments: list[dict]
    format: str = "srt"       # srt | vtt


@router.get("/status")
def status():
    return engines.detect().to_dict()


@router.post("/tts")
def synth(req: TTSReq):
    if not req.text.strip():
        raise HTTPException(400, "text is required")
    name = f"tts_{int(time.time()*1000)}.wav"
    out = _VOICE_DIR / name
    try:
        res = tts.synthesize(req.text, str(out), voice=req.voice, rate=req.rate)
    except tts.TTSUnavailable as exc:
        raise HTTPException(503, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"TTS failed: {exc}")
    url_name = name
    if req.format == "mp3":
        try:
            mp3 = out.with_suffix(".mp3")
            audio.convert(str(out), str(mp3))
            url_name = mp3.name
        except audio.AudioError as exc:
            raise HTTPException(503, f"mp3 export needs ffmpeg: {exc}")
    return {"url": f"/api/voice/file/{url_name}", "engine": res.engine,
            "voice": res.voice, "duration_s": res.duration_s,
            "sample_rate": res.sample_rate}


@router.post("/stt")
def transcribe(req: STTReq):
    p = Path(req.path)
    if not p.is_absolute():
        p = _VOICE_DIR / req.path.lstrip("/\\")
    if not p.is_file():
        raise HTTPException(404, f"audio not found: {req.path}")
    try:
        t = stt.transcribe(str(p), language=req.language)
    except stt.STTUnavailable as exc:
        # Honest 503 — no fabricated transcript.
        raise HTTPException(503, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"STT failed: {exc}")
    return t.to_dict()


@router.post("/subtitles")
def make_subtitles(req: SubReq):
    segs = subtitles.segments_from_dicts(req.segments)
    text = subtitles.to_vtt(segs) if req.format == "vtt" else subtitles.to_srt(segs)
    return {"format": req.format, "content": text}


@router.get("/file/{name}")
def get_file(name: str):
    if not _SAFE_NAME.match(name):
        raise HTTPException(400, "invalid name")
    f = _VOICE_DIR / name
    if not f.is_file():
        raise HTTPException(404, "not found")
    media = "audio/mpeg" if f.suffix == ".mp3" else "audio/wav"
    return FileResponse(str(f), media_type=media, filename=name)
