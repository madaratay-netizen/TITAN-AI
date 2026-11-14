"""Deterministic tests for the Adaptive Intelligence Engine.

These use synthetic HardwareReports so they assert real engine behaviour
independent of the machine the tests run on.
"""
from core.hardware_detection.detector import (
    HardwareReport, CPUInfo, MemoryInfo, GPUInfo, Accel,
)
from core.adaptive_engine import engine
from core.adaptive_engine.profiles import F_IMAGE, F_VIDEO_ADV, F_CHAT_LARGE


def make(ram_gb, vram_mb=0, vendor="none"):
    gpus = []
    if vram_mb:
        gpus = [GPUInfo(vendor=vendor, model="Test GPU",
                        vram_total_mb=vram_mb, vram_free_mb=vram_mb,
                        compute_capability="8.6")]
    return HardwareReport(
        os_name="Test", arch="x86_64",
        cpu=CPUInfo(model="Test", physical_cores=4, logical_cores=8),
        memory=MemoryInfo(total_gb=ram_gb, available_gb=ram_gb * 0.7),
        gpus=gpus, accel=Accel(cuda=bool(vram_mb and vendor == "nvidia")),
    )


# -- classification --------------------------------------------------------- #
def test_profile_basic_4gb():
    assert engine.classify(make(4)).key == "P1"


def test_profile_standard_8gb():
    assert engine.classify(make(8)).key == "P2"


def test_profile_advanced_16gb_small_gpu():
    # 16GB + 4GB NVIDIA → Advanced (not Creator: VRAM < 6GB).
    p = engine.classify(make(16, 4096, "nvidia"))
    assert p.key == "P3"
    assert F_CHAT_LARGE in p.enables
    assert F_IMAGE not in p.enables


def test_profile_16gb_reported_as_15_71_still_advanced():
    # Real 16GB stick reports ~15.71 usable — tolerance must keep it at P3.
    assert engine.classify(make(15.71, 4096, "nvidia")).key == "P3"


def test_profile_creator_needs_6gb_vram():
    assert engine.classify(make(16, 8192, "nvidia")).key == "P4"


def test_profile_studio_highend():
    p = engine.classify(make(32, 16384, "nvidia"))
    assert p.key == "P5"
    assert F_VIDEO_ADV in p.enables


def test_amd_gpu_not_counted_for_creator_tier():
    # Creator/Studio currently gate on CUDA; a big AMD card stays Advanced.
    assert engine.classify(make(32, 16384, "amd")).key == "P3"


# -- load decisions --------------------------------------------------------- #
def test_small_llm_fits_on_cpu_only_machine():
    d = engine.fits(make(8), est_ram_gb=4.0, gpu_capable=False, min_ram_gb=6)
    assert d.ok and d.backend == "cpu"


def test_llm_fully_in_vram_uses_cuda():
    rep = make(16, 8192, "nvidia")
    d = engine.fits(rep, est_ram_gb=3.0, gpu_capable=True, min_ram_gb=6)
    assert d.ok and d.backend == "cuda"


def test_oversized_model_rejected():
    d = engine.fits(make(8), est_ram_gb=40.0, gpu_capable=False, min_ram_gb=8)
    assert not d.ok and d.backend == "none"


def test_hard_ram_gate_blocks_big_model():
    # Model demands 32GB system RAM; a 16GB machine must be refused up front.
    d = engine.fits(make(16, 4096, "nvidia"), est_ram_gb=10, est_vram_mb=12288,
                    gpu_capable=True, media=True, min_ram_gb=32)
    assert not d.ok


def test_media_model_cpu_fallback_flagged():
    # VRAM too small but RAM ample → CPU fallback allowed (slow).
    d = engine.fits(make(16, 4096, "nvidia"), est_ram_gb=8, est_vram_mb=6144,
                    gpu_capable=True, media=True, min_ram_gb=16)
    assert d.ok and d.backend == "cpu"


def test_ram_budget_is_fraction_of_total():
    assert engine.ram_budget_gb(make(16)) == 16 * engine.RAM_TOTAL_FACTOR
