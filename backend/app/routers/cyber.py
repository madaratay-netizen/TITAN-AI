"""TITAN AI — IT & Cyber Lab API routes (defensive diagnostics only).

Read-only diagnostics plus an authorization-gated TCP port check. No
exploitation, stealth, credential-testing, or persistence functionality.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from modules.cyber_lab import diagnostics, scanner, logs
from backend.app.config import REPO_ROOT

router = APIRouter(prefix="/api/cyber", tags=["cyber"])

_LOG_ROOT = REPO_ROOT / "storage"


class PingReq(BaseModel):
    host: str
    count: int = 4


class ScanReq(BaseModel):
    host: str
    ports: list[int] | None = None
    authorized: bool = False


class LogTextReq(BaseModel):
    text: str


class LogFileReq(BaseModel):
    path: str


@router.get("/system")
def system():
    return diagnostics.system_health()


@router.get("/disks")
def disks():
    return diagnostics.disk_health()


@router.get("/interfaces")
def interfaces():
    return diagnostics.net_interfaces()


@router.get("/dns")
def dns(host: str):
    try:
        return diagnostics.dns_lookup(host)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/ping")
def ping(req: PingReq):
    try:
        return diagnostics.ping(req.host, req.count)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/scan")
def scan(req: ScanReq):
    """Authorization-gated TCP-connect port check (defensive).

    Returns an authorization_required response (not an error) for non-loopback
    targets until the caller confirms authorization with authorized=true.
    """
    try:
        return scanner.scan(req.host, req.ports, req.authorized)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/logs/text")
def logs_text(req: LogTextReq):
    return logs.analyze_text(req.text)


@router.post("/logs/file")
def logs_file(req: LogFileReq):
    try:
        return logs.analyze_file(req.path, allowed_root=_LOG_ROOT)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))
