# TITAN AI — Portable Offline Intelligence & Creative Studio

A portable, **offline-first** AI workstation that runs local models (chat today;
image/voice/video/knowledge as hardware and later phases allow) with **no cloud,
no API keys, no mandatory internet**. Built to live on an external SSD and boot on
any compatible x86-64 PC without touching the host's internal drives.

> **Status: early, honest, and real.** The Adaptive Intelligence Engine and local
> LLM chat are implemented and tested on real hardware. The creative studios are
> scaffolded and planned. Nothing here fakes AI output. See
> [docs/PHASE_REPORT.md](docs/PHASE_REPORT.md).

## What works right now
- **Hardware detection** — real CPU/RAM/GPU/VRAM/disk/accel probing (Win + Linux).
- **Adaptive engine** — classifies the machine into profiles P1–P5 and makes
  **safe per-model load decisions** (never loads a model that won't fit).
- **Model registry** — compatibility + licensing metadata; download-on-demand only.
- **Local chat** — talks to a local Ollama model, fully offline. Direct answers
  or reasoning traces for thinking models.
- **Knowledge Center (RAG)** — ingest PDF/DOCX/XLSX/TXT/MD/CSV into per-project
  libraries; ask questions and get **cited** answers from your own documents,
  fully offline. Semantic embeddings via a local model, with a zero-download
  lexical fallback so it works on any machine.
- **Developer Lab** — local coding assistant (generate/explain/review/debug) plus a
  **safe execution gate**: generated code is never auto-run — it's displayed and
  must be explicitly approved, then runs confined to a workspace, timed, with
  destructive commands blocked.
- **IT & Cyber Lab** — defensive diagnostics only: system/disk/network health,
  DNS/ping, log analysis, and an **authorization-gated** TCP port check (loopback
  free; other targets require explicit authorization). No exploitation/stealth tools.
- **Voice Studio** — local text-to-speech (offline, with real audio export to
  WAV/MP3), SRT/VTT subtitle generation, and speech-to-text wired to
  whisper.cpp/faster-whisper. Engines are detected and reported honestly; no
  capability is claimed that isn't installed.
- **Dashboard** — live hardware, profile, models, and a working chat, loopback-only.
- **Offline manager** — honest network-state reporting with three isolation levels.
- **Tests** — deterministic engine tests (`pytest`).

## Quickstart
```bash
python scripts/titan_report.py          # zero-dependency system report
pip install -r requirements.txt
uvicorn backend.app.main:app --host 127.0.0.1 --port 8077
# open http://127.0.0.1:8077
```
Full guide: [INSTALLATION_GUIDE.md](INSTALLATION_GUIDE.md) ·
Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Repository layout
```
TITAN-AI/
├── core/            # Adaptive Intelligence Engine (detection, profiles, registry, offline)
├── backend/         # FastAPI API + config
├── frontend/        # Dashboard (static, API-driven)
├── modules/         # chat (live) · image/video/voice/knowledge/dev/cyber (planned)
├── infrastructure/  # linux / docker / firewall / boot
├── scripts/         # titan_report, disk identification (confirmation-gated), offline test
├── tests/           # pytest
├── docs/            # architecture, phase report
├── configs/         # titan.toml (offline + loopback by default)
├── models/ storage/ # local weights (gitignored) + persistent state
└── docker-compose.yml  requirements.txt  README.md  INSTALLATION_GUIDE.md
```

## Principles
Offline-first · hardware-adaptive · modular (a missing GPU/model disables one
feature, not the system) · honest (no fake output, no untested "passes") · FOSS
with license review · portable & persistent.

## License & models
TITAN's own code: see `LICENSE` (to be added). Each AI model keeps its own license —
the registry records it; review before redistribution. Model weights are never
committed to this repo.
