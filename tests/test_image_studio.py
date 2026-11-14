"""Image Studio tests — real ComfyUI workflow construction, the VRAM gate, and
honest handling when ComfyUI is not running. No image generation is faked.
"""
import pytest

from core.hardware_detection.detector import (
    HardwareReport, CPUInfo, MemoryInfo, GPUInfo, Accel)
from modules.image_studio import workflows
from modules.image_studio.workflows import GenParams
from modules.image_studio.comfy_client import ComfyUIClient, ImageRef
from modules.image_studio.studio import (
    ImageStudio, ImageStudioUnavailable, preflight)


def machine(ram_gb, vram_mb=0, vendor="none"):
    gpus = [GPUInfo(vendor=vendor, model="GPU", vram_total_mb=vram_mb,
                    vram_free_mb=vram_mb)] if vram_mb else []
    return HardwareReport(memory=MemoryInfo(ram_gb, ram_gb * 0.7),
                          cpu=CPUInfo(logical_cores=8), gpus=gpus, accel=Accel())


# -- workflow construction (real ComfyUI graph) ----------------------------- #
def test_t2i_graph_structure():
    g = workflows.text_to_image(GenParams(prompt="a cat", seed=42, steps=20))
    classes = {n["class_type"] for n in g.values()}
    assert {"CheckpointLoaderSimple", "CLIPTextEncode", "EmptyLatentImage",
            "KSampler", "VAEDecode", "SaveImage"} <= classes
    # KSampler wiring + params propagate.
    ks = g["3"]["inputs"]
    assert ks["seed"] == 42 and ks["steps"] == 20
    assert ks["model"] == ["4", 0] and ks["latent_image"] == ["5", 0]
    # Two text encoders: positive (prompt) and negative.
    texts = [g[n]["inputs"]["text"] for n in g if g[n]["class_type"] == "CLIPTextEncode"]
    assert "a cat" in texts


def test_resolution_propagates():
    g = workflows.text_to_image(GenParams(prompt="x", width=768, height=512))
    assert g["5"]["inputs"]["width"] == 768
    assert g["5"]["inputs"]["height"] == 512


def test_validate_rejects_bad_params():
    with pytest.raises(ValueError):
        GenParams(prompt="").validate()
    with pytest.raises(ValueError):
        GenParams(prompt="x", width=1001).validate()   # not a multiple of 8
    with pytest.raises(ValueError):
        GenParams(prompt="x", steps=999).validate()
    with pytest.raises(ValueError):
        GenParams(prompt="x", sampler="nope").validate()


def test_img2img_has_load_and_encode():
    g = workflows.image_to_image(GenParams(prompt="x"), "src.png", denoise=0.5)
    classes = {n["class_type"] for n in g.values()}
    assert "LoadImage" in classes and "VAEEncode" in classes
    # KSampler reads the encoded latent and uses the given denoise.
    assert g["3"]["inputs"]["denoise"] == 0.5
    assert g["3"]["inputs"]["latent_image"] == ["11", 0]


def test_upscale_adds_node_and_bigger_res():
    g = workflows.upscale_latent(GenParams(prompt="x", width=512, height=512), scale=1.5)
    assert any(n["class_type"] == "LatentUpscale" for n in g.values())
    up = g["20"]["inputs"]
    assert up["width"] == 768 and up["height"] == 768


# -- client parsing --------------------------------------------------------- #
def test_extract_images_from_history():
    entry = {"outputs": {"9": {"images": [
        {"filename": "ADWIN_0001.png", "subfolder": "", "type": "output"}]}}}
    refs = ComfyUIClient.extract_images(entry)
    assert len(refs) == 1 and refs[0].filename == "ADWIN_0001.png"


def test_imageref_view_path():
    ref = ImageRef("a b.png", "sub", "output")
    p = ref.view_path()
    assert p.startswith("/view?") and "filename=a+b.png" in p and "type=output" in p


def test_status_unreachable_is_not_running():
    # Nothing listens here → honest 'not running', never a crash.
    st = ComfyUIClient("http://127.0.0.1:1").status(timeout=1.0)
    assert st.running is False and st.error


# -- VRAM gate -------------------------------------------------------------- #
def test_preflight_blocks_sdxl_on_small_gpu():
    pf = preflight(machine(16, 4096, "nvidia"), "sd_xl_base_1.0.safetensors", 1024, 1024)
    assert pf.ok is False and pf.needs_allow is True
    assert pf.est_vram_mb > pf.vram_budget_mb


def test_preflight_ok_on_big_gpu():
    pf = preflight(machine(32, 16384, "nvidia"), "sd_xl_base_1.0.safetensors", 1024, 1024)
    assert pf.ok is True and pf.backend == "cuda"


def test_preflight_scales_with_resolution():
    big = preflight(machine(16, 4096, "nvidia"), "sdxl.safetensors", 2048, 2048)
    small = preflight(machine(16, 4096, "nvidia"), "sdxl.safetensors", 512, 512)
    assert big.est_vram_mb > small.est_vram_mb


# -- honest unavailability (no placeholder) --------------------------------- #
def test_generate_raises_when_comfy_down(tmp_path):
    studio = ImageStudio(machine(16, 4096, "nvidia"),
                         comfy_host="http://127.0.0.1:1", output_dir=tmp_path)
    with pytest.raises(ImageStudioUnavailable):
        studio.generate(GenParams(prompt="a cat", width=512, height=512),
                        allow_slow=True)
