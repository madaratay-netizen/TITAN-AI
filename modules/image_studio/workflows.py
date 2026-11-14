"""TITAN AI — Image Studio ComfyUI workflow builders.

Produces real ComfyUI API-format graphs (node-id -> {class_type, inputs}) that
ComfyUI's /prompt endpoint executes. These are the standard SD/SDXL graphs, not
mock data.

Supported:
  text_to_image  — CheckpointLoader -> 2x CLIPTextEncode -> EmptyLatentImage
                   -> KSampler -> VAEDecode -> SaveImage
  image_to_image — LoadImage -> VAEEncode -> KSampler(denoise<1) -> VAEDecode -> SaveImage
  upscale_latent — latent upscale pass over an existing generation
"""
from __future__ import annotations

from dataclasses import dataclass, field

SAMPLERS = {"euler", "euler_ancestral", "dpmpp_2m", "dpmpp_2m_sde",
            "dpmpp_sde", "ddim", "uni_pc", "lcm"}
SCHEDULERS = {"normal", "karras", "exponential", "simple", "sgm_uniform"}


@dataclass
class GenParams:
    prompt: str
    negative: str = "text, watermark, lowres, bad anatomy"
    ckpt_name: str = "sd_xl_base_1.0.safetensors"
    width: int = 1024
    height: int = 1024
    steps: int = 25
    cfg: float = 7.0
    sampler: str = "euler"
    scheduler: str = "normal"
    seed: int = 0
    batch_size: int = 1
    filename_prefix: str = "TITAN"

    def validate(self) -> None:
        if not self.prompt.strip():
            raise ValueError("prompt is required")
        for dim, v in (("width", self.width), ("height", self.height)):
            if not (64 <= v <= 4096) or v % 8 != 0:
                raise ValueError(f"{dim} must be a multiple of 8 in [64, 4096]")
        if not (1 <= self.steps <= 150):
            raise ValueError("steps must be in [1, 150]")
        if not (1.0 <= self.cfg <= 30.0):
            raise ValueError("cfg must be in [1, 30]")
        if self.sampler not in SAMPLERS:
            raise ValueError(f"sampler must be one of {sorted(SAMPLERS)}")
        if self.scheduler not in SCHEDULERS:
            raise ValueError(f"scheduler must be one of {sorted(SCHEDULERS)}")
        if not (1 <= self.batch_size <= 16):
            raise ValueError("batch_size must be in [1, 16]")


def _ksampler(seed, steps, cfg, sampler, scheduler, denoise,
              model, positive, negative, latent) -> dict:
    return {"class_type": "KSampler", "inputs": {
        "seed": int(seed), "steps": int(steps), "cfg": float(cfg),
        "sampler_name": sampler, "scheduler": scheduler, "denoise": float(denoise),
        "model": model, "positive": positive, "negative": negative,
        "latent_image": latent}}


def text_to_image(p: GenParams) -> dict:
    p.validate()
    return {
        "4": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": p.ckpt_name}},
        "6": {"class_type": "CLIPTextEncode",
              "inputs": {"text": p.prompt, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode",
              "inputs": {"text": p.negative, "clip": ["4", 1]}},
        "5": {"class_type": "EmptyLatentImage",
              "inputs": {"width": p.width, "height": p.height,
                         "batch_size": p.batch_size}},
        "3": _ksampler(p.seed, p.steps, p.cfg, p.sampler, p.scheduler, 1.0,
                       ["4", 0], ["6", 0], ["7", 0], ["5", 0]),
        "8": {"class_type": "VAEDecode",
              "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage",
              "inputs": {"filename_prefix": p.filename_prefix, "images": ["8", 0]}},
    }


def image_to_image(p: GenParams, source_image: str, denoise: float = 0.6) -> dict:
    p.validate()
    if not (0.0 < denoise <= 1.0):
        raise ValueError("denoise must be in (0, 1]")
    return {
        "4": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": p.ckpt_name}},
        "10": {"class_type": "LoadImage", "inputs": {"image": source_image}},
        "11": {"class_type": "VAEEncode",
               "inputs": {"pixels": ["10", 0], "vae": ["4", 2]}},
        "6": {"class_type": "CLIPTextEncode",
              "inputs": {"text": p.prompt, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode",
              "inputs": {"text": p.negative, "clip": ["4", 1]}},
        "3": _ksampler(p.seed, p.steps, p.cfg, p.sampler, p.scheduler, denoise,
                       ["4", 0], ["6", 0], ["7", 0], ["11", 0]),
        "8": {"class_type": "VAEDecode",
              "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage",
              "inputs": {"filename_prefix": p.filename_prefix + "_img2img",
                         "images": ["8", 0]}},
    }


def upscale_latent(p: GenParams, scale: float = 1.5, denoise: float = 0.4) -> dict:
    """Generate then latent-upscale for a higher-resolution result."""
    p.validate()
    g = text_to_image(p)
    tw, th = int(p.width * scale), int(p.height * scale)
    tw -= tw % 8
    th -= th % 8
    g["20"] = {"class_type": "LatentUpscale",
               "inputs": {"samples": ["3", 0], "upscale_method": "nearest-exact",
                          "width": tw, "height": th, "crop": "disabled"}}
    g["21"] = _ksampler(p.seed, max(10, p.steps // 2), p.cfg, p.sampler,
                        p.scheduler, denoise, ["4", 0], ["6", 0], ["7", 0], ["20", 0])
    g["8"]["inputs"]["samples"] = ["21", 0]
    g["9"]["inputs"]["filename_prefix"] = p.filename_prefix + "_upscaled"
    return g
