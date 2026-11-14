"""TITAN AI — Image Studio API routes (real ComfyUI; no placeholder images)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.hardware_detection import detector
from modules.image_studio import workflows
from modules.image_studio.studio import (
    ImageStudio, ImageStudioUnavailable, ImageResourceError, preflight)
from core.model_registry.registry import ModelRegistry
from backend.app.config import REPO_ROOT

router = APIRouter(prefix="/api/image", tags=["image"])

_COMFY_HOST = "http://127.0.0.1:8188"
_OUT = REPO_ROOT / "storage" / "workspace" / "images"


class GenReq(BaseModel):
    prompt: str
    negative: str = "text, watermark, lowres, bad anatomy"
    # Defaults match the 4 GB-VRAM-friendly SD 1.5 checkpoint installed with TITAN.
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
    try:
        params = workflows.GenParams(
            prompt=req.prompt, negative=req.negative, ckpt_name=req.ckpt_name,
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
    return {"prompt_id": result.prompt_id, "backend": result.backend,
            "images": result.images, "preflight": result.preflight.__dict__}
