"""ADWIN OS — Image Studio API routes (real ComfyUI; no placeholder images)."""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.hardware_detection import detector
from modules.image_studio import workflows
from modules.image_studio.studio import (
    ImageStudio, ImageStudioUnavailable, ImageResourceError, preflight)
from core.model_registry.registry import ModelRegistry
from modules.chat import ollama_client
from backend.app.config import REPO_ROOT, settings

router = APIRouter(prefix="/api/image", tags=["image"])

_COMFY_HOST = "http://127.0.0.1:8188"
_OUT = REPO_ROOT / "storage" / "workspace" / "Images"
_OUT.mkdir(parents=True, exist_ok=True)
_SAFE = re.compile(r"^[A-Za-z0-9._-]+$")
_ARABIC = re.compile(r"[؀-ۿ]")


def _to_english(text: str) -> str:
    """Translate an Arabic image prompt to English via the local LLM (image
    models are English-trained). Best-effort; falls back to the original."""
    if not _ARABIC.search(text):
        return text
    try:
        out = ollama_client.chat(
            "Translate this image-generation prompt to concise, vivid English. "
            "Output ONLY the English translation, no quotes:\n" + text,
            model=settings.default_model, host=settings.ollama_host, think=False)
        return out.strip() or text
    except Exception:
        return text


class GenReq(BaseModel):
    prompt: str
    negative: str = "text, watermark, lowres, bad anatomy"
    # Defaults match the 4 GB-VRAM-friendly SD 1.5 checkpoint installed with ADWIN.
    ckpt_name: str = "v1-5-pruned-emaonly.safetensors"
    width: int = 512
    height: int = 512
    steps: int = 20
    cfg: float = 7.0
    sampler: str = "euler"
    scheduler: str = "normal"
    seed: int = 0
    batch_size: int = 1
    allow_slow: bool = False


def _studio() -> ImageStudio:
    return ImageStudio(detector.detect(), comfy_host=_COMFY_HOST, output_dir=_OUT)


@router.get("/status")
def status():
    report = detector.detect()
    st = _studio().status()
    # Hardware image capability from the adaptive profile.
    from core.adaptive_engine import engine
    gpu = report.best_gpu
    return {
        **st,
        "hardware": {
            "vram_mb": gpu.vram_total_mb if gpu else 0,
            "vram_budget_mb": engine.vram_budget_mb(report),
            "note": ("No CUDA GPU — image generation would be CPU-only (very slow)."
                     if not (gpu and gpu.vendor == "nvidia") else None),
        },
    }


@router.get("/checkpoints")
def checkpoints():
    """Checkpoints ComfyUI can load (newest/best first when recognizable)."""
    from modules.image_studio.comfy_client import ComfyUIClient
    cps = ComfyUIClient(_COMFY_HOST).list_checkpoints()
    # Surface a friendlier label; prefer DreamShaper as a nicer default.
    cps_sorted = sorted(cps, key=lambda n: (0 if "dream" in n.lower() else 1, n.lower()))
    return {"checkpoints": cps_sorted,
            "default": cps_sorted[0] if cps_sorted else None}


@router.get("/models")
def models():
    report = detector.detect()
    reg = ModelRegistry()
    reg.evaluate(report)
    imgs = [m.to_dict() for m in reg.all() if m.kind == "image"]
    return {"models": imgs}


@router.post("/preflight")
def check(req: GenReq):
    report = detector.detect()
    pf = preflight(report, req.ckpt_name, req.width, req.height)
    return pf.__dict__


@router.post("/generate")
def generate(req: GenReq):
    prompt_en = _to_english(req.prompt)   # image models are English-trained
    try:
        params = workflows.GenParams(
            prompt=prompt_en, negative=req.negative, ckpt_name=req.ckpt_name,
            width=req.width, height=req.height, steps=req.steps, cfg=req.cfg,
            sampler=req.sampler, scheduler=req.scheduler, seed=req.seed,
            batch_size=req.batch_size)
        params.validate()
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    studio = _studio()
    try:
        result = studio.generate(params, allow_slow=req.allow_slow)
    except ImageStudioUnavailable as exc:
        # Honest 503 — ComfyUI is not running. No placeholder is returned.
        raise HTTPException(503, f"Image generation unavailable: {exc}")
    except ImageResourceError as exc:
        # 409 — would exceed safe VRAM; client may retry with allow_slow=true.
        raise HTTPException(409, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Generation failed: {exc}")

    # Return locally-servable URLs for the downloaded images (so the UI can show them).
    images = []
    for im in result.images:
        name = im.get("filename", "")
        images.append({"filename": name, "url": f"/api/image/file/{name}",
                       "local_path": im.get("local_path")})
    return {"prompt_id": result.prompt_id, "backend": result.backend,
            "prompt_used": prompt_en, "images": images,
            "preflight": result.preflight.__dict__}


@router.get("/file/{name}")
def get_file(name: str):
    if not _SAFE.match(name):
        raise HTTPException(400, "invalid name")
    f = _OUT / name
    if not f.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(str(f), media_type="image/png", filename=name)
