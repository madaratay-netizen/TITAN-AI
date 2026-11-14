"""ADWIN OS — Video Studio scene visuals (AI image per scene).

Generates a real image for each scene from its description using the local
ComfyUI image backend, then attaches it to the scene so the FFmpeg assembler
renders actual visuals instead of a title card. If ComfyUI isn't running, the
scene keeps its title card — nothing is faked.
"""
from __future__ import annotations

from pathlib import Path

from core.hardware_detection.detector import HardwareReport
from modules.image_studio.comfy_client import ComfyUIClient
from modules.image_studio.studio import ImageStudio
from modules.image_studio import workflows
from modules.video_studio.project import VideoProject

# Small, 4 GB-VRAM-friendly checkpoint (downloaded into ComfyUI/models/checkpoints).
SD15_CKPT = "v1-5-pruned-emaonly.safetensors"
DEFAULT_SIZE = 512
DEFAULT_STEPS = 20
STYLE_SUFFIX = ", cinematic, high detail, professional photography"


def comfy_available(host: str = "http://127.0.0.1:8188") -> bool:
    return ComfyUIClient(host).status().running


def best_checkpoint(host: str = "http://127.0.0.1:8188", fallback: str = SD15_CKPT) -> str:
    """Pick the nicest installed checkpoint (prefer DreamShaper), else fallback."""
    cps = ComfyUIClient(host).list_checkpoints()
    if not cps:
        return fallback
    for want in ("dream", "sd_xl", "sdxl"):
        for c in cps:
            if want in c.lower():
                return c
    return cps[0]


def generate_scene_images(project: VideoProject, report: HardwareReport,
                          out_dir: str | Path, host: str = "http://127.0.0.1:8188",
                          ckpt: str | None = None, size: int = DEFAULT_SIZE,
                          steps: int = DEFAULT_STEPS, timeout: float = 300.0) -> dict:
    """For each scene without a source, generate an image and attach it.

    Returns a summary {generated, failed, scenes}. Scenes that fail keep their
    title card (honest fallback).
    """
    if ckpt is None:
        ckpt = best_checkpoint(host)
    studio = ImageStudio(report, comfy_host=host, output_dir=out_dir)
    generated, failed = 0, 0
    for i, scene in enumerate(project.scenes):
        if scene.source:            # already has footage/image
            continue
        prompt = (scene.description or scene.title or "a cinematic scene").strip()
        params = workflows.GenParams(
            prompt=prompt + STYLE_SUFFIX,
            ckpt_name=ckpt, width=size, height=size,
            steps=steps, cfg=7.0, seed=(i + 1) * 1000)
        try:
            result = studio.generate(params, allow_slow=True, wait=True, timeout=timeout)
            local = result.images[0]["local_path"] if result.images else None
            if local and Path(local).is_file():
                scene.source = local
                scene.type = "image"
                generated += 1
            else:
                failed += 1
        except Exception:
            failed += 1   # keep the title card for this scene
    return {"generated": generated, "failed": failed, "scenes": len(project.scenes)}
