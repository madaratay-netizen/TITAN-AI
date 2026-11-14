"""TITAN AI — Video Studio API routes (scene-based FFmpeg production)."""
from __future__ import annotations

import re
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.hardware_detection import detector
from modules.video_studio.project import VideoProject
from modules.video_studio import storyboard
from modules.video_studio.assembler import Assembler, AssemblerError, ffmpeg
from modules.video_studio import generation
from modules.voice_studio import tts
from modules.chat import ollama_client
from backend.app.config import settings, REPO_ROOT

router = APIRouter(prefix="/api/video", tags=["video"])

_WS = REPO_ROOT / "storage" / "workspace"
_PROJECTS = _WS / "Projects"
_VIDEOS = _WS / "Videos"
_AUDIO = _WS / "Audio"
for d in (_PROJECTS, _VIDEOS, _AUDIO):
    d.mkdir(parents=True, exist_ok=True)
_SAFE = re.compile(r"^[A-Za-z0-9._-]+$")


class StoryboardReq(BaseModel):
    idea: str
    name: str = "Untitled"
    scene_count: int = 5
    model: str | None = None


class RenderReq(BaseModel):
    project_id: str
    resolution: str = "720p"
    burn_subtitles: bool = False
    narrate: bool = False


@router.get("/status")
def status():
    report = detector.detect()
    has_ffmpeg = shutil.which("ffmpeg") is not None
    cap = generation.capability(report)
    return {"ffmpeg": has_ffmpeg,
            "assembly_available": has_ffmpeg,
            "ai_generation": cap.to_dict(),
            "note": None if has_ffmpeg else "FFmpeg not found — install it to render video."}


@router.post("/storyboard")
def make_storyboard(req: StoryboardReq):
    st = ollama_client.status(settings.ollama_host)
    if not st.running:
        raise HTTPException(503, "Local Ollama is not running (needed for storyboard).")
    model = req.model or settings.default_model
    try:
        scenes = storyboard.generate_storyboard(req.idea, model=model,
                                                scene_count=req.scene_count,
                                                host=settings.ollama_host)
    except Exception as exc:
        raise HTTPException(500, f"Storyboard generation failed: {exc}")
    proj = storyboard.project_from_storyboard(req.name, scenes)
    proj.save(_PROJECTS / f"{proj.id}.json")
    return proj.to_dict()


@router.get("/project/{pid}")
def get_project(pid: str):
    f = _PROJECTS / f"{pid}.json"
    if not f.is_file():
        raise HTTPException(404, "project not found")
    return VideoProject.load(f).to_dict()


@router.post("/render")
def render(req: RenderReq):
    if not shutil.which("ffmpeg"):
        raise HTTPException(503, "FFmpeg not found — cannot render.")
    f = _PROJECTS / f"{req.project_id}.json"
    if not f.is_file():
        raise HTTPException(404, "project not found")
    proj = VideoProject.load(f)

    # Optional: synthesize narration per scene via the local TTS engine.
    if req.narrate:
        try:
            for i, s in enumerate(proj.scenes):
                if s.narration.strip():
                    wav = _AUDIO / f"{proj.id}_{i:03d}.wav"
                    res = tts.synthesize(s.narration, str(wav))
                    s.narration_audio = res.path
                    s.duration = max(s.duration, round(res.duration_s + 0.4, 2))
            proj.save(f)
        except tts.TTSUnavailable:
            pass  # render without narration rather than fail

    out = _VIDEOS / f"{proj.id}_{int(time.time())}.mp4"
    try:
        result = Assembler().render(proj, str(out), resolution=req.resolution,
                                    burn_subtitles=req.burn_subtitles)
    except AssemblerError as exc:
        raise HTTPException(500, f"Render failed: {exc}")
    return {"url": f"/api/video/file/{out.name}", "duration_s": result.duration,
            "resolution": f"{result.width}x{result.height}", "scenes": result.scenes,
            "size_mb": round(result.size_bytes / (1024 * 1024), 2)}


@router.get("/file/{name}")
def get_file(name: str):
    if not _SAFE.match(name):
        raise HTTPException(400, "invalid name")
    f = _VIDEOS / name
    if not f.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(str(f), media_type="video/mp4", filename=name)
