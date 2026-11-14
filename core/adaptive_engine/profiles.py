"""TITAN AI — Capability profiles.

These are *policy* profiles (initial defaults), NOT guaranteed hardware
requirements. The engine always re-checks actual free resources before it
clears a model to load (see engine.fits()).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    key: str
    name: str
    min_ram_gb: float
    min_vram_mb: int          # 0 == no GPU required
    enables: tuple[str, ...]  # feature flags this profile turns on
    summary: str


# Feature flags used across TITAN modules.
F_CHAT_LIGHT = "chat_light"
F_CHAT_STD = "chat_standard"
F_CHAT_LARGE = "chat_large"
F_DOCS = "documents"
F_RAG = "rag"
F_CODE = "coding"
F_IMAGE = "image_generation"
F_IMAGE_ADV = "image_advanced"
F_VIDEO_SHORT = "video_short"
F_VIDEO_ADV = "video_advanced"
F_AUDIO = "audio_generation"

PROFILES: tuple[Profile, ...] = (
    Profile(
        "P1", "BASIC", min_ram_gb=4, min_vram_mb=0,
        enables=(F_CHAT_LIGHT, F_DOCS),
        summary="Lightweight quantized LLM on CPU, basic text + document help.",
    ),
    Profile(
        "P2", "STANDARD", min_ram_gb=8, min_vram_mb=0,
        enables=(F_CHAT_LIGHT, F_CHAT_STD, F_DOCS, F_RAG, F_CODE),
        summary="Small/medium quantized LLMs, document analysis, basic coding.",
    ),
    Profile(
        "P3", "ADVANCED", min_ram_gb=16, min_vram_mb=0,
        enables=(F_CHAT_LIGHT, F_CHAT_STD, F_CHAT_LARGE, F_DOCS, F_RAG, F_CODE),
        summary="Larger quantized LLMs, extensive RAG, advanced coding. "
                "Image gen only if VRAM permits.",
    ),
    Profile(
        "P4", "CREATOR", min_ram_gb=16, min_vram_mb=6144,
        enables=(F_CHAT_LIGHT, F_CHAT_STD, F_CHAT_LARGE, F_DOCS, F_RAG, F_CODE,
                 F_IMAGE, F_VIDEO_SHORT, F_AUDIO),
        summary="Compatible GPU: image gen/editing, short video, audio.",
    ),
    Profile(
        "P5", "STUDIO", min_ram_gb=32, min_vram_mb=12288,
        enables=(F_CHAT_LIGHT, F_CHAT_STD, F_CHAT_LARGE, F_DOCS, F_RAG, F_CODE,
                 F_IMAGE, F_IMAGE_ADV, F_VIDEO_SHORT, F_VIDEO_ADV, F_AUDIO),
        summary="High-performance GPU: advanced video, larger image models, "
                "higher resolutions.",
    ),
)

PROFILE_BY_KEY = {p.key: p for p in PROFILES}
