"""TITAN AI — Image Studio ComfyUI client.

A real client for the ComfyUI HTTP API (the engine TITAN uses for image
generation). It submits actual workflow graphs and retrieves the real images
ComfyUI produces. It NEVER fabricates or substitutes placeholder images: if
ComfyUI is not running, callers get an honest "unavailable" result.

ComfyUI API endpoints used:
  GET  /system_stats        -> server + device/VRAM info (liveness)
  POST /prompt              -> queue a workflow, returns {prompt_id}
  GET  /history/{prompt_id} -> execution result incl. output image refs
  GET  /queue               -> running/pending (progress)
  GET  /view?filename=...   -> the generated image bytes
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Optional

DEFAULT_HOST = "http://127.0.0.1:8188"


@dataclass
class ComfyStatus:
    running: bool
    host: str
    version: str = ""
    devices: list[dict] = field(default_factory=list)
    error: str = ""


@dataclass
class ImageRef:
    filename: str
    subfolder: str
    type: str          # output | temp | input

    def view_path(self) -> str:
        q = urllib.parse.urlencode(
            {"filename": self.filename, "subfolder": self.subfolder, "type": self.type})
        return f"/view?{q}"


class ComfyUIClient:
    def __init__(self, host: str = DEFAULT_HOST, client_id: Optional[str] = None):
        self.host = host.rstrip("/")
        self.client_id = client_id or uuid.uuid4().hex

    # -- liveness --------------------------------------------------------- #
    def status(self, timeout: float = 3.0) -> ComfyStatus:
        try:
            req = urllib.request.Request(self.host + "/system_stats", method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return ComfyStatus(running=False, host=self.host,
                               error=f"ComfyUI not reachable at {self.host}: {exc}")
        system = data.get("system", {})
        return ComfyStatus(
            running=True, host=self.host,
            version=str(system.get("comfyui_version", system.get("python_version", ""))),
            devices=data.get("devices", []))

    # -- submit / poll ---------------------------------------------------- #
    def submit(self, workflow: dict, timeout: float = 10.0) -> str:
        """Queue a workflow graph. Returns the prompt_id."""
        payload = json.dumps({"prompt": workflow, "client_id": self.client_id}).encode()
        req = urllib.request.Request(self.host + "/prompt", data=payload,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        pid = data.get("prompt_id")
        if not pid:
            raise RuntimeError(f"ComfyUI rejected workflow: {data}")
        return pid

    def history(self, prompt_id: str, timeout: float = 5.0) -> Optional[dict]:
        try:
            req = urllib.request.Request(self.host + f"/history/{prompt_id}", method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError):
            return None
        return data.get(prompt_id)

    @staticmethod
    def extract_images(history_entry: dict) -> list[ImageRef]:
        """Pull output image references from a /history entry."""
        images: list[ImageRef] = []
        outputs = (history_entry or {}).get("outputs", {})
        for node_out in outputs.values():
            for img in node_out.get("images", []):
                images.append(ImageRef(
                    filename=img.get("filename", ""),
                    subfolder=img.get("subfolder", ""),
                    type=img.get("type", "output")))
        return images

    def wait(self, prompt_id: str, poll: float = 1.0, timeout: float = 600.0) -> list[ImageRef]:
        """Poll until the workflow finishes, then return its images."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            entry = self.history(prompt_id)
            if entry and entry.get("outputs"):
                return self.extract_images(entry)
            time.sleep(poll)
        raise TimeoutError(f"ComfyUI job {prompt_id} did not finish in {timeout}s")

    def image_path(self, ref: ImageRef) -> str:
        """Full URL to fetch a generated image."""
        return self.host + ref.view_path()

    def queue_depth(self, timeout: float = 3.0) -> Optional[int]:
        try:
            req = urllib.request.Request(self.host + "/queue", method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError):
            return None
        return len(data.get("queue_running", [])) + len(data.get("queue_pending", []))
