"""TITAN AI — Storage / Workspace Manager API routes."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.hardware_detection import detector
from core.storage_manager.manager import (
    WorkspaceManager, WorkspaceUnavailable, InsufficientSpace, StorageError,
    STANDARD_DIRS, safe_filename)
from core.live_boot import partition_planner
from backend.app.config import settings, REPO_ROOT

router = APIRouter(prefix="/api/storage", tags=["storage"])

_wm = WorkspaceManager(settings.workspace)

# Approved 128 GB (119.24 GiB) partition plan (see docs/STORAGE_LAYOUT.md).
PARTITION_PLAN = [
    {"label": "TITAN_EFI", "fs": "FAT32", "gib": 1, "windows": True, "purpose": "UEFI boot (ESP)"},
    {"label": "TITAN_BOOT", "fs": "ext4", "gib": 21, "windows": False, "purpose": "Live base (read-only) + boot files"},
    {"label": "TITAN_SYSTEM", "fs": "ext4", "gib": 14, "windows": False, "purpose": "Persistent app/runtime, config, logs"},
    {"label": "TITAN_MODELS", "fs": "ext4", "gib": 23, "windows": False, "purpose": "Optional AI model weights"},
    {"label": "TITAN_WORKSPACE", "fs": "exFAT", "gib": 52, "windows": True, "purpose": "User outputs — cross-OS, protected"},
    {"label": "(free)", "fs": "-", "gib": 8.2, "windows": False, "purpose": "Recovery buffer + over-provisioning"},
]


class BackupReq(BaseModel):
    pass


@router.get("/plan")
def plan(device_gb: float = 128.03):
    """Computed partition plan for a device of `device_gb` (default: the
    measured 128 GB SSD). Pure planning — no disk operations."""
    computed = partition_planner.compute_plan(int(device_gb * 1_000_000_000))
    return {"device_gb": device_gb, "computed": computed.to_dict(),
            "standard_dirs": STANDARD_DIRS}


@router.get("/disks")
def disks():
    return {"disks": detector.detect().to_dict()["disks"]}


@router.get("/workspace")
def workspace():
    return _wm.health().to_dict()


@router.post("/workspace/ensure")
def ensure():
    try:
        created = _wm.ensure_structure()
    except WorkspaceUnavailable as exc:
        raise HTTPException(503, str(exc))
    return {"root": str(_wm.root), "created": created,
            "health": _wm.health().to_dict()}


@router.post("/workspace/backup")
def backup():
    cfg = REPO_ROOT / "configs" / "titan.toml"
    try:
        path = _wm.backup_settings(extra_paths=[cfg] if cfg.exists() else None)
    except StorageError as exc:
        raise HTTPException(500, str(exc))
    return {"backup": path}


class SpaceReq(BaseModel):
    needed_mb: float


@router.post("/check-space")
def check_space(req: SpaceReq):
    return _wm.check_space(int(req.needed_mb * 1024 * 1024))
