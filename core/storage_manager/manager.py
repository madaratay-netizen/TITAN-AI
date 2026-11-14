"""TITAN AI — Storage / Workspace Manager.

Creates and guards the persistent TITAN_WORKSPACE, reports capacity & health,
enforces a free-space reserve, and writes files safely on exFAT (atomic writes,
sanitized filenames). Protecting the workspace is a top-level requirement, so
this module:

- never deletes user files,
- refuses writes that would breach the free-space reserve,
- detects an unavailable / read-only workspace and says so clearly,
- keeps app secrets OUT of the shared workspace.

It works today against any directory (dev: storage/workspace) and, on the Live
SSD, against the exFAT TITAN_WORKSPACE mount.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

GB = 1024 ** 3

# Standard workspace layout (see docs/STORAGE_LAYOUT.md).
STANDARD_DIRS = [
    "Images", "Videos", "Audio", "Documents", "Code", "Projects",
    "AI_Conversations", "Exports", "Imports", "Backups", "User_Settings",
]

# Free-space reserve: never write below this. max(2 GiB, 5% of capacity).
RESERVE_MIN_GB = 2.0
RESERVE_FRACTION = 0.05
LOW_SPACE_WARN_GB = 5.0

# exFAT / Windows invalid filename characters and reserved names.
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL",
             *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}
MAX_NAME_LEN = 200


class StorageError(Exception):
    pass


class WorkspaceUnavailable(StorageError):
    pass


class InsufficientSpace(StorageError):
    pass


def safe_filename(name: str, default: str = "untitled") -> str:
    """Make a filename safe for exFAT/Windows and Linux."""
    name = (name or "").strip().replace("/", "_").replace("\\", "_")
    name = _INVALID_CHARS.sub("_", name)
    name = name.rstrip(" .")                      # no trailing dot/space (Windows)
    if not name:
        return default
    stem, dot, ext = name.partition(".")
    if stem.upper() in _RESERVED:
        stem = "_" + stem
    name = stem + dot + ext
    if len(name) > MAX_NAME_LEN:
        keep_ext = ("." + ext)[:16] if ext else ""
        name = name[: MAX_NAME_LEN - len(keep_ext)] + keep_ext
    return name


@dataclass
class SubdirInfo:
    name: str
    exists: bool
    files: int = 0
    size_mb: float = 0.0


@dataclass
class WorkspaceHealth:
    root: str
    exists: bool
    available: bool
    writable: bool
    filesystem: str
    total_gb: float
    free_gb: float
    used_percent: float
    reserve_gb: float
    below_reserve: bool
    low_space: bool
    status: str                       # ok | low_space | critical | unavailable | read_only
    subdirs: list[SubdirInfo] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["subdirs"] = [s.__dict__ for s in self.subdirs]
        return d


class WorkspaceManager:
    def __init__(self, root: str | os.PathLike):
        self.root = Path(root)

    # -- filesystem helpers ---------------------------------------------- #
    def _filesystem(self) -> str:
        try:
            import psutil  # type: ignore
            best = ""
            rp = str(self.root.resolve())
            for part in psutil.disk_partitions(all=False):
                mp = part.mountpoint
                if rp.lower().startswith(mp.lower()) and len(mp) > len(best):
                    best = mp
                    fs = part.fstype
            if best:
                return fs
        except Exception:
            pass
        return ""

    def reserve_gb(self) -> float:
        try:
            total = shutil.disk_usage(self._usable_root()).total / GB
        except OSError:
            return RESERVE_MIN_GB
        return max(RESERVE_MIN_GB, total * RESERVE_FRACTION)

    def _usable_root(self) -> str:
        """A path that exists for disk_usage (root or nearest existing parent)."""
        p = self.root
        while not p.exists() and p != p.parent:
            p = p.parent
        return str(p)

    # -- availability ----------------------------------------------------- #
    def is_available(self) -> bool:
        return self.root.exists() and self.root.is_dir()

    def is_writable(self) -> bool:
        if not self.is_available():
            return False
        probe = self.root / f".titan_write_test_{os.getpid()}"
        try:
            probe.write_bytes(b"ok")
            probe.unlink()
            return True
        except OSError:
            return False

    # -- structure -------------------------------------------------------- #
    def ensure_structure(self) -> list[str]:
        """Create the workspace + standard subdirs. Returns dirs created."""
        created = []
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise WorkspaceUnavailable(f"cannot create workspace at {self.root}: {exc}")
        for d in STANDARD_DIRS:
            p = self.root / d
            if not p.exists():
                try:
                    p.mkdir(parents=True, exist_ok=True)
                    created.append(d)
                except OSError:
                    pass
        return created

    # -- health ----------------------------------------------------------- #
    def health(self) -> WorkspaceHealth:
        exists = self.is_available()
        fs = self._filesystem()
        reserve = self.reserve_gb()
        try:
            u = shutil.disk_usage(self._usable_root())
            total_gb, free_gb = u.total / GB, u.free / GB
            used_pct = round((u.total - u.free) / u.total * 100, 1) if u.total else 0.0
        except OSError:
            total_gb = free_gb = used_pct = 0.0

        writable = self.is_writable() if exists else False
        below = free_gb < reserve
        low = free_gb < LOW_SPACE_WARN_GB

        if not exists:
            status, note = "unavailable", "Workspace path does not exist or is not mounted."
        elif not writable:
            status, note = "read_only", "Workspace is read-only — cannot save outputs here."
        elif below:
            status, note = "critical", f"Free space below the {reserve:.1f} GB reserve."
        elif low:
            status, note = "low_space", "Free space is low."
        else:
            status, note = "ok", ""

        subdirs = []
        if exists:
            for d in STANDARD_DIRS:
                p = self.root / d
                if p.is_dir():
                    files = 0
                    size = 0
                    for f in p.rglob("*"):
                        if f.is_file():
                            files += 1
                            try:
                                size += f.stat().st_size
                            except OSError:
                                pass
                    subdirs.append(SubdirInfo(d, True, files, round(size / (1024 * 1024), 2)))
                else:
                    subdirs.append(SubdirInfo(d, False))

        return WorkspaceHealth(
            root=str(self.root), exists=exists, available=exists, writable=writable,
            filesystem=fs or "unknown", total_gb=round(total_gb, 2),
            free_gb=round(free_gb, 2), used_percent=used_pct,
            reserve_gb=round(reserve, 2), below_reserve=below, low_space=low,
            status=status, subdirs=subdirs, note=note)

    # -- space checks ----------------------------------------------------- #
    def check_space(self, needed_bytes: int) -> dict:
        reserve = self.reserve_gb()
        try:
            free = shutil.disk_usage(self._usable_root()).free
        except OSError:
            return {"ok": False, "reason": "cannot read disk usage"}
        after = free - needed_bytes
        ok = after >= reserve * GB
        return {"ok": ok, "free_gb": round(free / GB, 2),
                "needed_gb": round(needed_bytes / GB, 3),
                "reserve_gb": round(reserve, 2),
                "after_gb": round(after / GB, 2),
                "reason": "" if ok else "would breach the free-space reserve"}

    # -- safe write (atomic, reserve-checked) ----------------------------- #
    def safe_write(self, category: str, filename: str, data: bytes) -> str:
        """Atomically write `data` into <workspace>/<category>/<safe filename>.

        Refuses if the workspace is unavailable/read-only or the write would
        breach the reserve. Never overwrites by deleting first — uses rename.
        """
        if not self.is_available():
            raise WorkspaceUnavailable("workspace is not available")
        if not self.is_writable():
            raise WorkspaceUnavailable("workspace is read-only")
        space = self.check_space(len(data))
        if not space["ok"]:
            raise InsufficientSpace(space["reason"] + f" ({space})")

        subdir = self.root / (category if category in STANDARD_DIRS else "Exports")
        subdir.mkdir(parents=True, exist_ok=True)
        dest = subdir / safe_filename(filename)

        # Atomic: write temp in same dir, flush+fsync, then replace.
        fd, tmp = tempfile.mkstemp(dir=str(subdir), prefix=".titan_tmp_")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, dest)
        except OSError as exc:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise StorageError(f"write failed: {exc}")
        return str(dest)

    # -- backup / restore ------------------------------------------------- #
    def backup_settings(self, extra_paths: Optional[list[Path]] = None) -> str:
        """Zip User_Settings (+ extra config paths) into Backups/. No secrets."""
        self.ensure_structure()
        backups = self.root / "Backups"
        name = f"titan_settings_{time.strftime('%Y%m%d_%H%M%S')}.zip"
        out = backups / name
        settings_dir = self.root / "User_Settings"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            if settings_dir.is_dir():
                for f in settings_dir.rglob("*"):
                    if f.is_file():
                        z.write(f, f.relative_to(self.root))
            for p in (extra_paths or []):
                p = Path(p)
                if p.is_file():
                    z.write(p, "extra/" + p.name)
        return str(out)

    def restore_settings(self, backup_zip: str) -> list[str]:
        z = Path(backup_zip)
        if not z.is_file():
            raise StorageError(f"backup not found: {backup_zip}")
        restored = []
        with zipfile.ZipFile(z, "r") as zf:
            for member in zf.namelist():
                # Confinement: never allow path traversal out of the workspace.
                target = (self.root / member).resolve()
                if self.root.resolve() not in target.parents and target != self.root.resolve():
                    continue
                zf.extract(member, self.root)
                restored.append(member)
        return restored
