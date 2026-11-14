"""ADWIN OS — Image Studio orchestrator.

Ties the ComfyUI client + workflow builders to the Adaptive Engine's VRAM
budget. Key honesty rules:
  - Real generation only: if ComfyUI is not running, raise ImageStudioUnavailable.
    Never return a placeholder image.
  - Resource safety: estimate VRAM for the requested resolution/model and refuse
    (unless explicitly allowed) when it exceeds the safe VRAM budget — mirroring
    the engine's "never load beyond safe resources" rule. CPU is allowed but slow.
"""
from __future__ import annotations

import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from core.hardware_detection.detector import HardwareReport
from core.adaptive_engine import engine
from modules.image_studio.comfy_client import ComfyUIClient, ImageRef
from modules.image_studio import workflows


class ImageStudioUnavailable(Exception):
    pass


class ImageResourceError(Exception):
    pass


# Approximate VRAM (MB) a model needs at 1024x1024; scales with pixel count.
MODEL_VRAM_BASE = {
    "sdxl": 6000,
    "sd_xl": 6000,
    "flux": 12000,
    "sd15": 3000,
}


def _model_base_mb(ckpt_name: str) -> int:
    low = ckpt_name.lower()
    for key, mb in MODEL_VRAM_BASE.items():
        if key in low:
            return mb
    return 4000  # conservative default


@dataclass
class Preflight:
    ok: bool
    backend: str            # cuda | cpu | none
    est_vram_mb: int
    vram_budget_mb: int
    needs_allow: bool
    message: str


def preflight(report: HardwareReport, ckpt_name: str,
              width: int, height: int) -> Preflight:
    base = _model_base_mb(ckpt_name)
    est = int(base * (width * height) / (1024 * 1024))
    # Budget is based on TOTAL VRAM, not momentary free: ComfyUI is the loader
    # and manages its own memory (--lowvram swaps), so once it is resident the
    # "free" figure is misleading. Total VRAM is the right "can the GPU run it"
    # measure for the ComfyUI backend.
    gpu = report.best_gpu
    total_vram = gpu.vram_total_mb if (gpu and gpu.vendor == "nvidia") else 0
    budget = int(total_vram * 0.9)
    if budget >= est:
        return Preflight(True, "cuda", est, budget, False,
                         f"fits VRAM ({est} MB <= {budget} MB budget)")
    # Too big for VRAM — CPU is possible but slow; require explicit allow.
    return Preflight(
        False, "cpu", est, budget, True,
        f"needs ~{est} MB VRAM but only {budget} MB is safely available. "
        f"Generation would fall back to CPU (very slow) — pass allow_slow=true "
        f"to proceed, or reduce resolution / use a smaller model.")


@dataclass
class GenerationResult:
    prompt_id: str
    images: list[dict]       # {filename, url, local_path}
    backend: str
    preflight: Preflight


class ImageStudio:
    def __init__(self, report: HardwareReport, comfy_host: str = "http://127.0.0.1:8188",
                 output_dir: str | Path = "storage/workspace/images"):
        self.report = report
        self.client = ComfyUIClient(comfy_host)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def status(self) -> dict:
        st = self.client.status()
        return {"comfyui": st.__dict__,
                "note": None if st.running else
                "ComfyUI is not running. Start it (python main.py in ComfyUI) "
                "and ensure a model checkpoint is installed."}

    def _download(self, ref: ImageRef) -> Optional[str]:
        url = self.client.image_path(ref)
        dest = self.output_dir / ref.filename
        try:
            urllib.request.urlretrieve(url, dest)
            return str(dest)
        except Exception:
            return None

    def generate(self, params: workflows.GenParams, allow_slow: bool = False,
                 wait: bool = True, timeout: float = 600.0) -> GenerationResult:
        # 1. ComfyUI must actually be running — no placeholders.
        st = self.client.status()
        if not st.running:
            raise ImageStudioUnavailable(st.error or "ComfyUI not running")

        # 2. Resource gate.
        pf = preflight(self.report, params.ckpt_name, params.width, params.height)
        if not pf.ok and not allow_slow:
            raise ImageResourceError(pf.message)

        # 3. Build + submit the real workflow.
        graph = workflows.text_to_image(params)
        prompt_id = self.client.submit(graph)

        images: list[dict] = []
        if wait:
            refs = self.client.wait(prompt_id, timeout=timeout)
            for ref in refs:
                local = self._download(ref)
                images.append({"filename": ref.filename,
                               "url": ref.view_path(),
                               "local_path": local})
        return GenerationResult(prompt_id=prompt_id, images=images,
                                backend=("cuda" if pf.ok else "cpu"), preflight=pf)
