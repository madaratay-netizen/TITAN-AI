"""Model registry tests against synthetic hardware."""
from core.hardware_detection.detector import (
    HardwareReport, CPUInfo, MemoryInfo, GPUInfo, Accel,
)
from core.model_registry.registry import ModelRegistry


def machine(ram_gb, vram_mb=0, vendor="none"):
    gpus = [GPUInfo(vendor=vendor, model="GPU", vram_total_mb=vram_mb,
                    vram_free_mb=vram_mb)] if vram_mb else []
    return HardwareReport(
        memory=MemoryInfo(total_gb=ram_gb, available_gb=ram_gb * 0.7),
        cpu=CPUInfo(logical_cores=8, physical_cores=4),
        gpus=gpus, accel=Accel())


def test_seed_loads_models():
    reg = ModelRegistry()
    names = {m.name for m in reg.all()}
    assert "qwen3.5:4b" in names
    assert "nomic-embed-text" in names


def test_small_llm_ok_on_16gb():
    reg = ModelRegistry()
    reg.evaluate(machine(16, 4096, "nvidia"))
    assert reg.get("qwen3.5:4b").compatibility_status == "ok"


def test_32gb_video_model_incompatible_on_16gb():
    reg = ModelRegistry()
    reg.evaluate(machine(16, 4096, "nvidia"))
    assert reg.get("ltx-video-0.9").compatibility_status == "incompatible"


def test_flux_incompatible_on_16gb():
    reg = ModelRegistry()
    reg.evaluate(machine(16, 4096, "nvidia"))
    assert reg.get("flux.1-schnell").compatibility_status == "incompatible"


def test_recommended_are_defaults_and_compatible():
    reg = ModelRegistry()
    rec = reg.recommended_for(machine(16, 4096, "nvidia"))
    names = {m.name for m in rec}
    # Default, compatible models for a 16GB machine.
    assert "qwen3.5:4b" in names
    assert "nomic-embed-text" in names
    # No large non-default model sneaks into the recommended set.
    assert "flux.1-schnell" not in names


def test_reconcile_marks_installed():
    reg = ModelRegistry()
    reg.reconcile_with_ollama(["qwen3.5:4b"])
    assert reg.get("qwen3.5:4b").installed is True
    assert reg.get("gemma3:4b").installed is False


def test_every_model_has_a_license():
    reg = ModelRegistry()
    for m in reg.all():
        assert m.license and m.license != "unknown", m.name
