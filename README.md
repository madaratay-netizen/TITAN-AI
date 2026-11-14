# TITAN AI — Portable Offline Intelligence & Creative Studio

A portable, **offline-first** AI workstation that runs local models (chat today;
image/voice/video/knowledge as hardware and later phases allow) with **no cloud,
no API keys, no mandatory internet**. Built to live on an external SSD and boot on
any compatible x86-64 PC without touching the host's internal drives.

> **Status: early, honest, and real.** The Adaptive Intelligence Engine and local
> LLM chat are implemented and tested on real hardware. The creative studios are
> scaffolded and planned. Nothing here fakes AI output. See
> [docs/PHASE_REPORT.md](docs/PHASE_REPORT.md).

> 🌍 **جديد على المشروع؟ ابدأ من هنا (بالعربي، للمبتدئين):**
> **[TITAN AI — الحكاية كاملة ببساطة](docs/BEGINNERS_GUIDE_AR.md)**

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
- **Image Studio** — a real ComfyUI integration (SDXL text-to-image / img2img /
  upscale workflows) with a VRAM gate. If ComfyUI isn't running it says so
  honestly and refuses — it never shows a placeholder image.
- **Video Studio** — scene-based production: a local-LLM storyboard, then a real
  **FFmpeg** render (title/clip/image scenes, TTS narration, subtitles, music) to
  MP4. Works offline on modest hardware; AI clip generation is optional and
  hardware-gated (never faked).
- **Storage Manager** — creates & guards the exFAT `TITAN_WORKSPACE`: capacity/
  health, a free-space reserve, exFAT-safe atomic writes, backup/restore.
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
## Documentation
- [docs/FIRST_DELIVERABLE.md](docs/FIRST_DELIVERABLE.md) — design brief (architecture, partitions, Live tech, runtimes, roadmap, risks)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/STORAGE_LAYOUT.md](docs/STORAGE_LAYOUT.md) · [docs/LIVE_BOOT.md](docs/LIVE_BOOT.md)
- [docs/OFFLINE_MODE.md](docs/OFFLINE_MODE.md) · [docs/MODEL_MANAGEMENT.md](docs/MODEL_MANAGEMENT.md) · [docs/SECURITY.md](docs/SECURITY.md)
- [docs/TESTING.md](docs/TESTING.md) · [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) · [docs/PHASE_REPORT.md](docs/PHASE_REPORT.md)
- [INSTALLATION_GUIDE.md](INSTALLATION_GUIDE.md) — dev quickstart + SSD deployment

Target SSD: **128 GB (119.24 GiB usable)**; user outputs live on a separate
exFAT **`TITAN_WORKSPACE`** partition, readable from Windows and Linux.

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
TITAN's own code is **MIT-licensed** — see [LICENSE](LICENSE). Third-party
components and AI model weights keep their own licenses — see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md); the model registry records each
model's license. Review before redistribution. Model weights are never committed.
