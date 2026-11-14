"""TITAN AI — Backend API (FastAPI).

Exposes the Adaptive Intelligence Engine, model registry, local LLM chat,
offline status and storage planning over a local-only HTTP API, and serves
the dashboard. Every AI call is routed to the local Ollama server; when
offline mode is on, no outbound network AI call is ever made.

Run:  uvicorn backend.app.main:app --host 127.0.0.1 --port 8077
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.hardware_detection import detector
from core.adaptive_engine import engine
from core.model_registry.registry import ModelRegistry
from core.offline_manager import offline
from modules.chat import ollama_client
from backend.app.config import settings, REPO_ROOT
from backend.app.routers import knowledge, dev, cyber, voice, image, storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(REPO_ROOT / "storage" / "titan.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("titan.api")

app = FastAPI(title="TITAN AI", version="0.1.0",
              description="Portable Offline Intelligence & Creative Studio")

# Local dashboard only — do not open CORS to the internet.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[f"http://127.0.0.1:{settings.port}", f"http://localhost:{settings.port}"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_registry = ModelRegistry(db_path=Path(settings.db_path))

app.include_router(knowledge.router)
app.include_router(dev.router)
app.include_router(cyber.router)
app.include_router(voice.router)
app.include_router(image.router)
app.include_router(storage.router)

# Planning budget for a 128GB external SSD (final approved design).
STORAGE_PLAN_128 = {
    "LIVE  (system + apps)": 28,
    "AI    (models)": 35,
    "SHARED (outputs, exFAT)": 45,
    "EXTRA (reserve + cache)": 20,
}


class ChatRequest(BaseModel):
    prompt: str
    model: str | None = None
    system: str | None = None
    think: bool | None = False   # reasoning models: direct answer by default


# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health():
    return {"status": "ok", "service": "titan", "version": app.version,
            "offline_mode": settings.offline_mode}


@app.get("/api/hardware")
def api_hardware():
    return detector.detect().to_dict()


@app.get("/api/profile")
def api_profile():
    report = detector.detect()
    result = engine.evaluate(report)
    return {
        "hardware_summary": {
            "cpu": report.cpu.model,
            "ram_gb": report.memory.total_gb,
            "best_gpu": report.best_gpu.model if report.best_gpu else None,
            "vram_mb": report.best_gpu.vram_total_mb if report.best_gpu else 0,
        },
        **result.to_dict(),
    }


@app.get("/api/models")
def api_models():
    report = detector.detect()
    st = ollama_client.status(settings.ollama_host)
    if st.running:
        _registry.reconcile_with_ollama(st.models)
    evaluated = _registry.evaluate(report)
    return {"models": [m.to_dict() for m in evaluated],
            "recommended": [m.name for m in _registry.recommended_for(report)]}


@app.get("/api/ollama/status")
def api_ollama_status():
    st = ollama_client.status(settings.ollama_host)
    return st.__dict__


@app.get("/api/offline")
def api_offline():
    st = offline.check(settings.offline_mode, settings.isolation_verified)
    return st.__dict__


@app.get("/api/storage")
def api_storage():
    report = detector.detect()
    disks = [d.__dict__ if hasattr(d, "__dict__") else d for d in report.disks]
    return {"disks": report.to_dict()["disks"], "plan_gb_128": STORAGE_PLAN_128}


@app.post("/api/chat")
def api_chat(req: ChatRequest):
    # Offline guard: chat only talks to the LOCAL ollama host. We assert the
    # configured host is a loopback address before proceeding.
    host = settings.ollama_host
    if not (host.startswith("http://127.0.0.1") or host.startswith("http://localhost")):
        raise HTTPException(400, "Refusing non-local AI endpoint in offline mode.")
    st = ollama_client.status(host)
    if not st.running:
        raise HTTPException(503, "Local Ollama server is not running. Start it with `ollama serve`.")
    model = req.model or settings.default_model
    if st.models and model not in st.models:
        raise HTTPException(404, f"Model '{model}' not installed. Available: {st.models}")
    try:
        result = ollama_client.chat_full(req.prompt, model=model, host=host,
                                          system=req.system, think=req.think)
    except Exception as exc:
        log.exception("chat failed")
        raise HTTPException(500, f"Local inference failed: {exc}")
    return {"model": model, "response": result["content"],
            "thinking": result["thinking"]}


# --------------------------------------------------------------------------- #
# Serve the dashboard (static) at /
_frontend = REPO_ROOT / "frontend"
if _frontend.exists():
    app.mount("/static", StaticFiles(directory=str(_frontend)), name="static")

    @app.get("/")
    def index():
        idx = _frontend / "index.html"
        if idx.exists():
            return FileResponse(str(idx))
        return {"service": "titan", "note": "frontend not built"}
