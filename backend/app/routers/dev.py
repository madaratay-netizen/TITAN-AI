"""TITAN AI — Developer Lab API routes.

Security model: the assistant only PRODUCES text/code. Execution is gated —
/propose creates a pending proposal (nothing runs), the exact command/code is
returned for display, and /approve runs it only on explicit confirmation.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from modules.developer_lab.assistant import CodingAssistant
from modules.developer_lab.workspace import Workspace, WorkspaceError
from modules.developer_lab.executor import ExecutionManager
from modules.chat import ollama_client
from backend.app.config import settings, REPO_ROOT

router = APIRouter(prefix="/api/dev", tags=["developer"])

_WS_ROOT = REPO_ROOT / "storage" / "dev_workspace"
_assistant = CodingAssistant(host=settings.ollama_host, default_model=settings.default_model)
_workspace = Workspace(_WS_ROOT)
_executor = ExecutionManager(_WS_ROOT)


class GenReq(BaseModel):
    task: str
    language: str = "python"
    model: str | None = None


class CodeReq(BaseModel):
    code: str
    model: str | None = None


class DebugReq(BaseModel):
    code: str
    error: str
    model: str | None = None


class ProposeReq(BaseModel):
    kind: str            # "shell" | "python"
    content: str
    cwd: str | None = None


class ApproveReq(BaseModel):
    id: str
    confirm: bool = False
    allow_dangerous: bool = False


class WriteReq(BaseModel):
    path: str
    content: str


def _require_model(model: str | None) -> str:
    st = ollama_client.status(settings.ollama_host)
    if not st.running:
        raise HTTPException(503, "Local Ollama server is not running.")
    m = model or _assistant._model()
    if st.models and m not in st.models:
        raise HTTPException(404, f"Model '{m}' not installed. Available: {st.models}")
    return m


# -- assistant (text only) -------------------------------------------------- #
@router.post("/generate")
def generate(req: GenReq):
    _require_model(req.model)
    return _assistant.generate(req.task, req.language, req.model)


@router.post("/explain")
def explain(req: CodeReq):
    _require_model(req.model)
    return _assistant.explain(req.code, req.model)


@router.post("/review")
def review(req: CodeReq):
    _require_model(req.model)
    return _assistant.review(req.code, req.model)


@router.post("/debug")
def debug(req: DebugReq):
    _require_model(req.model)
    return _assistant.debug(req.code, req.error, req.model)


# -- workspace (confined) --------------------------------------------------- #
@router.get("/files")
def files(path: str = ""):
    try:
        return {"path": path, "entries": [e.__dict__ for e in _workspace.list_dir(path)]}
    except WorkspaceError as exc:
        raise HTTPException(400, str(exc))


@router.get("/file")
def read_file(path: str):
    try:
        return {"path": path, "content": _workspace.read_file(path)}
    except WorkspaceError as exc:
        raise HTTPException(400, str(exc))


@router.post("/file")
def write_file(req: WriteReq):
    try:
        n = _workspace.write_file(req.path, req.content)
    except WorkspaceError as exc:
        raise HTTPException(400, str(exc))
    return {"path": req.path, "bytes": n}


@router.get("/search")
def search(q: str):
    return {"query": q, "results": _workspace.search(q)}


# -- execution (approval-gated) --------------------------------------------- #
@router.post("/propose")
def propose(req: ProposeReq):
    try:
        p = _executor.propose(req.kind, req.content, req.cwd)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    # Returned, NOT executed. The UI must display content + dangerous flags.
    return p.to_dict()


@router.get("/proposals")
def proposals():
    return {"pending": [p.to_dict() for p in _executor.list_pending()]}


@router.post("/approve")
def approve(req: ApproveReq):
    try:
        p = _executor.approve(req.id, confirm=req.confirm,
                              allow_dangerous=req.allow_dangerous)
    except KeyError:
        raise HTTPException(404, "no such proposal")
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return p.to_dict()


@router.post("/reject")
def reject(req: ApproveReq):
    ok = _executor.reject(req.id)
    if not ok:
        raise HTTPException(404, "no pending proposal with that id")
    return {"ok": True, "id": req.id}
