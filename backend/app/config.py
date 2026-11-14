"""ADWIN OS — runtime configuration.

Loads settings from configs/adwin.toml if present, else sane defaults.
Local-only binding (127.0.0.1) is the default, per the offline-security spec.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib  # py311+
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "configs" / "adwin.toml"


@dataclass
class Settings:
    host: str = "127.0.0.1"          # local-only by default
    port: int = 8077
    offline_mode: bool = True        # strict offline by default
    isolation_verified: bool = False
    ollama_host: str = "http://127.0.0.1:11434"
    default_model: str = "qwen3.5:4b"
    db_path: str = str(REPO_ROOT / "storage" / "adwin.db")
    workspace: str = str(REPO_ROOT / "storage" / "workspace")


def load_settings() -> Settings:
    s = Settings()
    if tomllib and CONFIG_PATH.exists():
        try:
            data = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            srv = data.get("server", {})
            s.host = srv.get("host", s.host)
            s.port = int(srv.get("port", s.port))
            net = data.get("network", {})
            s.offline_mode = bool(net.get("offline_mode", s.offline_mode))
            s.isolation_verified = bool(net.get("isolation_verified", s.isolation_verified))
            ai = data.get("ai", {})
            s.ollama_host = ai.get("ollama_host", s.ollama_host)
            s.default_model = ai.get("default_model", s.default_model)
        except Exception:
            pass
    # Environment overrides (e.g. ADWIN_OFFLINE=0 for maintenance).
    if "ADWIN_OFFLINE" in os.environ:
        s.offline_mode = os.environ["ADWIN_OFFLINE"] not in ("0", "false", "False")
    return s


settings = load_settings()
