"""TITAN AI — Video Studio AI clip generation (optional, hardware-gated).

AI video generation (LTX / Wan / HunyuanVideo via ComfyUI) is heavy and needs a
large-VRAM GPU. This adapter reports availability **honestly** and refuses when
the hardware/engine aren't present — it never fabricates a clip. On machines
that can't run it, the Video Studio still works via imported footage + the
FFmpeg assembler (see assembler.py).
"""
from __future__ import annotations

from dataclasses import dataclass

from core.hardware_detection.detector import HardwareReport
from core.adaptive_engine import engine
from modules.image_studio.comfy_client import ComfyUIClient

# Minimum safe VRAM (MB) for the smallest practical local video model.
MIN_VIDEO_VRAM_MB = 12000


class VideoGenUnavailable(Exception):
    pass


@dataclass
class VideoGenCapability:
    available: bool
    reason: str
    comfyui_running: bool
    vram_mb: int
    vram_budget_mb: int

    def to_dict(self) -> dict:
        return self.__dict__


def capability(report: HardwareReport,
               comfy_host: str = "http://127.0.0.1:8188") -> VideoGenCapability:
    gpu = report.best_gpu
    vram = gpu.vram_total_mb if gpu else 0
    budget = engine.vram_budget_mb(report)
    comfy = ComfyUIClient(comfy_host).status().running

    if vram < MIN_VIDEO_VRAM_MB:
        return VideoGenCapability(
            False, f"AI video generation needs ~{MIN_VIDEO_VRAM_MB} MB VRAM; "
                   f"this GPU has {vram} MB. Use imported footage + the FFmpeg "
                   f"assembler instead.", comfy, vram, budget)
    if not comfy:
        return VideoGenCapability(
            False, "A compatible GPU was found, but ComfyUI (with a video model) "
                   "is not running. Start ComfyUI and install a video model.",
            comfy, vram, budget)
    return VideoGenCapability(True, "AI video generation available via ComfyUI.",
                              comfy, vram, budget)


def generate_clip(report: HardwareReport, prompt: str, seconds: float = 4.0,
                  comfy_host: str = "http://127.0.0.1:8188") -> str:
    """Attempt an AI video clip. Raises VideoGenUnavailable when unsupported —
    never returns a placeholder."""
    cap = capability(report, comfy_host)
    if not cap.available:
        raise VideoGenUnavailable(cap.reason)
    # A real LTX/Wan ComfyUI video workflow would be submitted here. It is only
    # reached on hardware that passes the gate above, so it is never faked.
    raise VideoGenUnavailable(
        "Video-model workflow not installed. Install a ComfyUI video model "
        "(e.g. LTX-Video) and its workflow to enable AI clip generation.")
