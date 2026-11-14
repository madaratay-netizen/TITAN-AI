"""TITAN AI — Adaptive Intelligence Engine.

Turns a HardwareReport into:
  1. a capability profile (P1..P5), and
  2. per-model safe/unsafe load decisions based on *actual* free resources.

Core safety rule: never clear a model to load if its estimated memory
consumption exceeds safe available resources. CPU fallback is offered
whenever technically possible.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.hardware_detection.detector import HardwareReport
from core.adaptive_engine.profiles import PROFILES, Profile

# Safety head-room: we never let a model consume the last slice of RAM/VRAM,
# or the OS + services get starved. These are deliberately conservative.
#
# RAM budget is computed from *total* physical RAM (what the machine can
# dedicate), not the momentary "available" figure — that number fluctuates
# with OS cache and other apps and would make load decisions non-deterministic
# and unfairly pessimistic. VRAM budget uses *free* VRAM (GPUs aren't paged).
RAM_TOTAL_FACTOR = 0.65    # a model may use up to this fraction of total RAM
VRAM_HEADROOM_MB = 512
VRAM_SAFETY_FACTOR = 0.90
# A 16 GB stick reports ~15.7 GB usable; tolerate that when gating profiles.
RAM_TOLERANCE_GB = 0.5
# Fixed runtime overhead added on top of the model file footprint estimate.
RUNTIME_OVERHEAD_GB = 0.5


@dataclass
class LoadDecision:
    ok: bool
    backend: str                 # "cuda" | "cpu" | "none"
    reason: str
    est_ram_gb: float = 0.0
    est_vram_mb: int = 0
    ram_budget_gb: float = 0.0
    vram_budget_mb: int = 0


def classify(report: HardwareReport) -> Profile:
    """Pick the highest profile whose min requirements the machine meets."""
    ram = report.memory.total_gb
    best_gpu = report.best_gpu
    vram = best_gpu.vram_total_mb if best_gpu else 0
    nvidia = bool(best_gpu and best_gpu.vendor == "nvidia")

    chosen = PROFILES[0]
    for p in PROFILES:
        ram_ok = ram >= (p.min_ram_gb - RAM_TOLERANCE_GB)
        # VRAM gate only applies to profiles that require a GPU, and we only
        # count a *compatible* (CUDA) GPU toward creator/studio tiers.
        if p.min_vram_mb > 0:
            vram_ok = nvidia and vram >= p.min_vram_mb
        else:
            vram_ok = True
        if ram_ok and vram_ok:
            chosen = p
    return chosen


def ram_budget_gb(report: HardwareReport) -> float:
    """Safe RAM a model may use, derived from TOTAL physical RAM."""
    return max(0.0, report.memory.total_gb * RAM_TOTAL_FACTOR)


def vram_budget_mb(report: HardwareReport) -> int:
    gpu = report.best_gpu
    if not gpu or gpu.vendor != "nvidia" or gpu.vram_total_mb <= 0:
        return 0
    free = gpu.vram_free_mb or gpu.vram_total_mb
    return max(0, int(free * VRAM_SAFETY_FACTOR) - VRAM_HEADROOM_MB)


def fits(report: HardwareReport, est_ram_gb: float, est_vram_mb: int = 0,
         gpu_capable: bool = False, media: bool = False,
         min_ram_gb: float = 0.0) -> LoadDecision:
    """Decide whether a model can be loaded safely on this machine.

    Models fall into two memory behaviours:

    * LLMs (media=False): weights load into VRAM, RAM, or split across both
      (Ollama/llama.cpp partial offload). Fit = footprint <= VRAM budget
      (full GPU), else <= RAM budget (CPU), else <= combined (hybrid).
    * Media models (media=True): image/video weights must effectively live in
      VRAM to be usable. CPU fallback is *technically* possible but slow, so we
      allow it only when RAM is ample and flag it upstream as cpu_only.

    A hard gate also rejects any model whose recommended minimum *system* RAM
    exceeds this machine's total RAM, regardless of footprint arithmetic.
    """
    rb = ram_budget_gb(report)
    vb = vram_budget_mb(report)
    vb_gb = vb / 1024.0

    def _dec(ok, backend, reason):
        return LoadDecision(ok=ok, backend=backend, reason=reason,
                            est_ram_gb=round(est_ram_gb, 2), est_vram_mb=est_vram_mb,
                            ram_budget_gb=round(rb, 2), vram_budget_mb=vb)

    # Hard gate: not enough total system RAM for this class of model.
    if min_ram_gb and report.memory.total_gb < (min_ram_gb - RAM_TOLERANCE_GB):
        return _dec(False, "none",
                    f"needs >= {min_ram_gb:.0f} GB system RAM, "
                    f"machine has {report.memory.total_gb:.1f} GB")

    if media:
        if gpu_capable and est_vram_mb > 0 and vb > 0 and est_vram_mb <= vb:
            return _dec(True, "cuda",
                        f"fits VRAM ({est_vram_mb} MB <= {vb} MB safe budget)")
        if est_ram_gb <= rb:
            return _dec(True, "cpu",
                        f"VRAM {vb} MB < {est_vram_mb} MB needed — CPU fallback "
                        f"(slow); fits RAM ({est_ram_gb:.1f} <= {rb:.1f} GB)")
        return _dec(False, "none",
                    f"needs {est_vram_mb} MB VRAM (budget {vb} MB) and "
                    f"{est_ram_gb:.1f} GB RAM (budget {rb:.1f} GB)")

    # LLM path.
    if gpu_capable and vb_gb > 0 and est_ram_gb <= vb_gb:
        return _dec(True, "cuda",
                    f"fits fully in VRAM ({est_ram_gb:.1f} GB <= {vb_gb:.1f} GB)")
    if est_ram_gb <= rb:
        return _dec(True, "cpu",
                    f"fits RAM ({est_ram_gb:.1f} GB <= {rb:.1f} GB safe budget)")
    if gpu_capable and est_ram_gb <= (rb + vb_gb):
        return _dec(True, "hybrid",
                    f"split GPU+CPU ({est_ram_gb:.1f} GB <= {rb:.1f}+{vb_gb:.1f} GB)")
    return _dec(False, "none",
                f"needs ~{est_ram_gb:.1f} GB (RAM budget {rb:.1f} GB"
                + (f", VRAM {vb_gb:.1f} GB" if gpu_capable else "") + ")")


@dataclass
class EngineResult:
    profile: Profile
    ram_budget_gb: float
    vram_budget_mb: int
    enabled_features: list[str]

    def to_dict(self) -> dict:
        return {
            "profile": {
                "key": self.profile.key,
                "name": self.profile.name,
                "summary": self.profile.summary,
            },
            "ram_budget_gb": self.ram_budget_gb,
            "vram_budget_mb": self.vram_budget_mb,
            "enabled_features": self.enabled_features,
        }


def evaluate(report: HardwareReport) -> EngineResult:
    profile = classify(report)
    return EngineResult(
        profile=profile,
        ram_budget_gb=round(ram_budget_gb(report), 2),
        vram_budget_mb=vram_budget_mb(report),
        enabled_features=list(profile.enables),
    )
