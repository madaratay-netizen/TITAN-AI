"""ADWIN OS — Knowledge Center API routes (local RAG)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from modules.knowledge_center.parsers import ParserError, supported_extensions
from modules.knowledge_center.rag import KnowledgeCenter
from modules.chat import ollama_client
from backend.app.config import settings, REPO_ROOT

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

_kc = KnowledgeCenter(
    db_path=str(REPO_ROOT / "storage" / "knowledge.db"),
    ollama_host=settings.ollama_host,
)


class LibraryReq(BaseModel):
    name: str


class IngestTextReq(BaseModel):
    library: str
    name: str
    text: str


class IngestFileReq(BaseModel):
    library: str
    path: str


class AskReq(BaseModel):
    library: str
    question: str
    model: str | None = None
    top_k: int = 4


@router.get("/info")
def info():
    return {"supported_extensions": supported_extensions(),
            "embed_model": settings.default_model and _kc.embed_model}


@router.get("/libraries")
def libraries():
    return {"libraries": _kc.list_libraries()}


@router.post("/libraries")
def create_library(req: LibraryReq):
    if not req.name.strip():
        raise HTTPException(400, "library name required")
    _kc.create_library(req.name.strip())
    return {"ok": True, "library": req.name.strip()}


@router.get("/{library}/documents")
def documents(library: str):
    return {"library": library, "documents": _kc.list_documents(library)}


@router.post("/ingest-text")
def ingest_text(req: IngestTextReq):
    try:
        res = _kc.ingest_text(req.library, req.name, req.text)
    except ParserError as exc:
        raise HTTPException(400, str(exc))
    return res.__dict__


@router.post("/ingest-file")
def ingest_file(req: IngestFileReq):
    p = Path(req.path)
    if not p.exists():
        raise HTTPException(404, f"file not found: {req.path}")
    try:
        res = _kc.ingest_file(req.library, str(p))
    except ParserError as exc:
        raise HTTPException(400, str(exc))
    return res.__dict__


@router.post("/ask")
def ask(req: AskReq):
    model = req.model or settings.default_model
    st = ollama_client.status(settings.ollama_host)
    if not st.running:
        raise HTTPException(503, "Local Ollama server is not running.")
    if st.models and model not in st.models:
        raise HTTPException(404, f"Model '{model}' not installed. Available: {st.models}")
    try:
        ans = _kc.ask(req.library, req.question, model=model, top_k=req.top_k)
    except Exception as exc:
        raise HTTPException(500, f"RAG failed: {exc}")
    return {"answer": ans.answer, "sources": ans.sources,
            "embedder": ans.embedder, "model": ans.model,
            "used_context": ans.used_context}
