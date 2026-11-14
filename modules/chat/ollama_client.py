"""ADWIN OS — Local LLM client (Ollama).

Thin, dependency-light client for a locally running Ollama server. Uses only
the standard library (urllib) so it works without extra installs. All traffic
is to the local host only; this module never contacts a remote endpoint.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Iterator, Optional

DEFAULT_HOST = "http://127.0.0.1:11434"


@dataclass
class OllamaStatus:
    running: bool
    host: str
    models: list[str]
    version: str = ""
    error: str = ""


def _get(host: str, path: str, timeout: float = 3.0) -> Optional[dict]:
    try:
        req = urllib.request.Request(host + path, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def status(host: str = DEFAULT_HOST) -> OllamaStatus:
    tags = _get(host, "/api/tags")
    if tags is None:
        return OllamaStatus(running=False, host=host, models=[],
                            error="Ollama server not reachable on local host.")
    models = [m.get("name", "") for m in tags.get("models", [])]
    ver = _get(host, "/api/version") or {}
    return OllamaStatus(running=True, host=host, models=models,
                        version=ver.get("version", ""))


def list_models_cli() -> list[str]:
    """Fallback: read installed models via the ollama CLI if the API is down."""
    exe = shutil.which("ollama")
    if not exe:
        return []
    try:
        out = subprocess.run([exe, "list"], capture_output=True, text=True,
                             timeout=8, check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    names = []
    for line in out.stdout.splitlines()[1:]:  # skip header
        parts = line.split()
        if parts:
            names.append(parts[0])
    return names


def chat(prompt: str, model: str, host: str = DEFAULT_HOST,
         system: Optional[str] = None, timeout: float = 300.0,
         options: Optional[dict] = None, keep_alive: str = "10m",
         think: Optional[bool] = None) -> str:
    """Single-shot, non-streaming local chat. Returns the assistant text."""
    return chat_full(prompt, model, host, system, timeout, options,
                     keep_alive, think)["content"]


def chat_full(prompt: str, model: str, host: str = DEFAULT_HOST,
              system: Optional[str] = None, timeout: float = 300.0,
              options: Optional[dict] = None, keep_alive: str = "10m",
              think: Optional[bool] = None) -> dict:
    """Local chat returning {"content", "thinking", "model"}.

    `options` passes Ollama generation options (e.g. {"num_predict": 256}).
    `think`: for reasoning models, False requests a direct answer (faster);
    None leaves the model default. `keep_alive` keeps the model resident.
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    body = {"model": model, "messages": messages, "stream": False,
            "keep_alive": keep_alive}
    if options:
        body["options"] = options
    if think is not None:
        body["think"] = think
    payload = json.dumps(body).encode()
    req = urllib.request.Request(host + "/api/chat", data=payload,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    msg = data.get("message", {})
    return {"content": msg.get("content", ""),
            "thinking": msg.get("thinking", ""),
            "model": model}


def chat_stream(prompt: str, model: str, host: str = DEFAULT_HOST,
                system: Optional[str] = None, timeout: float = 300.0) -> Iterator[str]:
    """Streaming local chat. Yields content chunks as they arrive."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = json.dumps({"model": model, "messages": messages, "stream": True}).encode()
    req = urllib.request.Request(host + "/api/chat", data=payload,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            line = raw.decode("utf-8").strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            chunk = obj.get("message", {}).get("content", "")
            if chunk:
                yield chunk
            if obj.get("done"):
                break
