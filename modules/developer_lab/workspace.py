"""TITAN AI — Developer Lab workspace.

Safe, read-oriented access to a confined project directory. Every path is
resolved and checked to stay inside the workspace root, so the Developer Lab
cannot read or list files elsewhere on the machine. Writes go through an
explicit, size-limited save that is also confined.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class WorkspaceError(Exception):
    pass


MAX_READ_BYTES = 512 * 1024          # 512 KB per file read
MAX_WRITE_BYTES = 2 * 1024 * 1024    # 2 MB per write
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", ".idea", ".mypy_cache"}


@dataclass
class Entry:
    name: str
    path: str          # relative to workspace root
    is_dir: bool
    size: int = 0


class Workspace:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, rel: str) -> Path:
        """Resolve a relative path and confine it to the workspace root."""
        rel = (rel or "").strip().lstrip("/\\")
        target = (self.root / rel).resolve()
        # Confinement check — reject traversal outside the root.
        if target != self.root and self.root not in target.parents:
            raise WorkspaceError(f"path escapes workspace: {rel!r}")
        return target

    def list_dir(self, rel: str = "") -> list[Entry]:
        base = self._resolve(rel)
        if not base.exists():
            raise WorkspaceError(f"not found: {rel}")
        if not base.is_dir():
            raise WorkspaceError(f"not a directory: {rel}")
        entries = []
        for p in sorted(base.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if p.name in SKIP_DIRS:
                continue
            try:
                size = p.stat().st_size if p.is_file() else 0
            except OSError:
                size = 0
            entries.append(Entry(
                name=p.name,
                path=str(p.relative_to(self.root)).replace("\\", "/"),
                is_dir=p.is_dir(), size=size))
        return entries

    def read_file(self, rel: str) -> str:
        target = self._resolve(rel)
        if not target.is_file():
            raise WorkspaceError(f"not a file: {rel}")
        if target.stat().st_size > MAX_READ_BYTES:
            raise WorkspaceError(f"file too large (> {MAX_READ_BYTES} bytes)")
        return target.read_text(encoding="utf-8", errors="replace")

    def write_file(self, rel: str, content: str) -> int:
        """Write a file inside the workspace. Returns bytes written."""
        data = content.encode("utf-8")
        if len(data) > MAX_WRITE_BYTES:
            raise WorkspaceError(f"content too large (> {MAX_WRITE_BYTES} bytes)")
        target = self._resolve(rel)
        if target.is_dir():
            raise WorkspaceError(f"is a directory: {rel}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return len(data)

    def search(self, query: str, max_results: int = 50) -> list[dict]:
        """Case-insensitive substring search across text files in the workspace."""
        if not query:
            return []
        q = query.lower()
        results: list[dict] = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                fp = Path(dirpath) / fn
                try:
                    if fp.stat().st_size > MAX_READ_BYTES:
                        continue
                    text = fp.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                for i, line in enumerate(text.splitlines(), 1):
                    if q in line.lower():
                        results.append({
                            "path": str(fp.relative_to(self.root)).replace("\\", "/"),
                            "line": i, "text": line.strip()[:200]})
                        if len(results) >= max_results:
                            return results
        return results
