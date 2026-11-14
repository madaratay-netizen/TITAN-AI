"""TITAN AI — Model Registry.

A compatibility registry backed by SQLite (metadata) + a JSON seed. It records
each model's footprint and, given a live HardwareReport, reports:
  - compatibility_status: can this machine run it safely?
  - load decision (backend + reason) via the adaptive engine
  - installation_status: is it present locally (Ollama / files)?

No model is ever downloaded here. This module only informs decisions.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core.hardware_detection.detector import HardwareReport
from core.adaptive_engine import engine

SEED_PATH = Path(__file__).with_name("seed_models.json")


@dataclass
class ModelEntry:
    name: str
    family: str
    kind: str                 # llm / code_llm / embedding / image / video
    version: str
    download_gb: float
    quantization: str
    min_ram_gb: float
    rec_ram_gb: float
    min_vram_mb: int
    rec_vram_mb: int
    backends: list[str]
    license: str
    source: str
    default: bool = False
    notes: str = ""
    installed: bool = False
    compatibility_status: str = "unknown"   # ok / cpu_only / incompatible
    load_reason: str = ""

    @classmethod
    def from_seed(cls, d: dict) -> "ModelEntry":
        return cls(
            name=d["name"], family=d.get("family", ""), kind=d["kind"],
            version=d.get("version", ""), download_gb=float(d.get("download_gb", 0)),
            quantization=d.get("quantization", ""),
            min_ram_gb=float(d.get("min_ram_gb", 0)),
            rec_ram_gb=float(d.get("rec_ram_gb", 0)),
            min_vram_mb=int(d.get("min_vram_mb", 0)),
            rec_vram_mb=int(d.get("rec_vram_mb", 0)),
            backends=list(d.get("backends", [])),
            license=d.get("license", "unknown"),
            source=d.get("source", ""),
            default=bool(d.get("default", False)),
            notes=d.get("notes", ""),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name, "family": self.family, "kind": self.kind,
            "version": self.version, "download_gb": self.download_gb,
            "quantization": self.quantization, "min_ram_gb": self.min_ram_gb,
            "rec_ram_gb": self.rec_ram_gb, "min_vram_mb": self.min_vram_mb,
            "rec_vram_mb": self.rec_vram_mb, "backends": self.backends,
            "license": self.license, "source": self.source,
            "default": self.default, "notes": self.notes,
            "installed": self.installed,
            "compatibility_status": self.compatibility_status,
            "load_reason": self.load_reason,
        }


class ModelRegistry:
    def __init__(self, db_path: Optional[Path] = None,
                 seed_path: Path = SEED_PATH):
        self.db_path = Path(db_path) if db_path else None
        self.seed_path = seed_path
        self._entries: dict[str, ModelEntry] = {}
        self._load_seed()
        if self.db_path:
            self._init_db()
            self._sync_installed_from_db()

    # -- seed ------------------------------------------------------------- #
    def _load_seed(self) -> None:
        data = json.loads(self.seed_path.read_text(encoding="utf-8"))
        for d in data.get("models", []):
            entry = ModelEntry.from_seed(d)
            self._entries[entry.name] = entry

    # -- sqlite (installation state) ------------------------------------- #
    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS installed_models ("
                "name TEXT PRIMARY KEY, source TEXT, installed_at TEXT DEFAULT CURRENT_TIMESTAMP)"
            )

    def _sync_installed_from_db(self) -> None:
        with sqlite3.connect(self.db_path) as con:
            rows = con.execute("SELECT name FROM installed_models").fetchall()
        for (name,) in rows:
            if name in self._entries:
                self._entries[name].installed = True

    def mark_installed(self, name: str, installed: bool = True) -> None:
        if name in self._entries:
            self._entries[name].installed = installed
        if not self.db_path:
            return
        with sqlite3.connect(self.db_path) as con:
            if installed:
                con.execute(
                    "INSERT OR REPLACE INTO installed_models(name, source) VALUES (?, ?)",
                    (name, self._entries.get(name, ModelEntry(
                        name, "", "", "", 0, "", 0, 0, 0, 0, [], "", "")).source),
                )
            else:
                con.execute("DELETE FROM installed_models WHERE name=?", (name,))

    # -- queries ---------------------------------------------------------- #
    def all(self) -> list[ModelEntry]:
        return list(self._entries.values())

    def get(self, name: str) -> Optional[ModelEntry]:
        return self._entries.get(name)

    def reconcile_with_ollama(self, installed_names: list[str]) -> None:
        """Mark registry entries installed if Ollama reports them present."""
        present = set(installed_names)
        for entry in self._entries.values():
            if entry.name in present:
                entry.installed = True

    def evaluate(self, report: HardwareReport) -> list[ModelEntry]:
        """Annotate every model with compatibility + load decision for this machine."""
        results = []
        for entry in self._entries.values():
            model_gpu_capable = "cuda" in entry.backends or "comfyui" in entry.backends
            is_media = entry.kind in ("image", "video")
            # Footprint estimate = model file size * 1.2 + fixed runtime overhead.
            est_ram = entry.download_gb * 1.2 + engine.RUNTIME_OVERHEAD_GB
            decision = engine.fits(
                report,
                est_ram_gb=est_ram,
                est_vram_mb=entry.min_vram_mb,
                gpu_capable=model_gpu_capable,
                media=is_media,
                min_ram_gb=entry.min_ram_gb,
            )
            entry.load_reason = decision.reason
            if not decision.ok:
                entry.compatibility_status = "incompatible"
            elif is_media and decision.backend == "cpu":
                entry.compatibility_status = "cpu_only"   # allowed but slow
            else:
                entry.compatibility_status = "ok"
            results.append(entry)
        return results

    def recommended_for(self, report: HardwareReport) -> list[ModelEntry]:
        """Default-installable models this machine can run safely."""
        self.evaluate(report)
        return [e for e in self._entries.values()
                if e.default and e.compatibility_status in ("ok", "cpu_only")]
