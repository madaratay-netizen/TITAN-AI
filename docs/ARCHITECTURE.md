# ADWIN OS — Architecture

**ADWIN OS** is a portable, offline-first AI workstation designed to live on an
external SSD, boot on an x86-64 PC, and run local AI (chat, documents, and —
where hardware permits — image/audio/video) with **no cloud, no API keys, and
no mandatory internet**.

This document reflects the **as-built** state plus the planned module map. See
[PHASE_REPORT.md](PHASE_REPORT.md) for exactly what is implemented vs. planned.

---

## 1. Design principles

1. **Offline-first** — local-only service binding; no outbound AI calls in offline mode.
2. **Hardware-adaptive** — never assume a GPU or RAM size; measure, then decide.
3. **Modular** — a missing model or absent GPU disables one feature, never the whole system.
4. **Honest** — no faked AI output, no "passed" tests that didn't run, no silent fallbacks.
5. **Free/open** — FOSS components; licenses reviewed before any redistribution.
6. **Portable & persistent** — state lives on the SSD, separate from the host PC.

## 2. Service map

```
                    ┌───────────────────────────────────────────┐
  Browser (local)   │              ADWIN Dashboard                │  frontend/  (static, API-driven)
  127.0.0.1:8077 ───▶  Dashboard · Chat · Models · (Studios…)      │
                    └───────────────┬─────────────────────────────┘
                                    │ HTTP (loopback only)
                    ┌───────────────▼─────────────────────────────┐
                    │           ADWIN Backend API (FastAPI)        │  backend/
                    │  /hardware /profile /models /chat /offline…  │
                    └───┬───────────┬───────────┬───────────┬──────┘
                        │           │           │           │
        ┌───────────────▼┐ ┌────────▼───────┐ ┌─▼─────────┐ ┌▼─────────────┐
        │ Adaptive Engine│ │ Model Registry │ │ Offline   │ │ Module layer │
        │ (core/)        │ │ (core/)        │ │ Manager   │ │ (modules/)   │
        │ detect→profile │ │ compat + state │ │ net state │ │ chat, image, │
        │ →load decision │ │ (SQLite)       │ │           │ │ video, voice,│
        └───────┬────────┘ └───────┬────────┘ └───────────┘ │ knowledge,   │
                │                  │                         │ dev, cyber   │
                │                  │                         └──────┬───────┘
         reads real HW      informs downloads                       │
                                                        ┌───────────▼────────────┐
                                                        │ Local inference engines │
                                                        │ Ollama · llama.cpp       │
                                                        │ ComfyUI · Whisper · Piper│
                                                        │ FFmpeg                   │
                                                        └──────────────────────────┘
```

## 3. Core: the Adaptive Intelligence Engine (`core/`)

The engine is the product's spine and is **fully implemented and tested**.

### 3.1 `hardware_detection/detector.py`
Measures the real machine: OS/arch, CPU (model, cores/threads, clock), RAM
(total/available), every GPU (vendor, model, VRAM total/free, driver, CUDA
compute capability via `nvidia-smi`), disks (mount, FS, total/free, removable),
and acceleration backends (CUDA/Vulkan/ROCm/Metal/CPU). Works on Windows (dev)
and Linux (target); uses `psutil` when present, falls back to `/proc`, WMI, and
`ctypes` otherwise, so it runs with **zero third-party dependencies**.

### 3.2 `adaptive_engine/`
- `profiles.py` — five **policy** profiles P1–P5 (Basic→Studio), each a set of
  minimum RAM/VRAM and the feature flags it enables.
- `engine.py` — `classify()` picks the highest profile the machine satisfies
  (with a 0.5 GB tolerance so a 16 GB stick reporting ~15.7 GB still qualifies).
  `fits()` makes a **per-model safe-load decision**:
  - LLMs may load into VRAM (CUDA), RAM (CPU), or split (hybrid).
  - Media (image/video) models effectively need VRAM; CPU is allowed but flagged slow.
  - A **hard gate** rejects any model whose minimum *system* RAM exceeds the machine.
  - RAM budget is a fraction of **total** RAM (deterministic), VRAM budget is **free** VRAM.

### 3.3 `model_registry/`
A registry (`seed_models.json` + SQLite install-state) carrying the full spec'd
schema per model: size, quantization, min/rec RAM & VRAM, backends, license,
source, install status, and a live **compatibility status** computed from the
engine (`ok` / `cpu_only` / `incompatible`). **No model is ever downloaded here.**

### 3.4 `offline_manager/`
Reports network state and distinguishes the three required levels:
`no_internet_requirement`, `no_network_connectivity`, `fully_isolated`. It never
claims full isolation unless the offline test harness has verified it.

## 4. Backend API (`backend/app/`)
FastAPI app, **loopback-bound by default**, CORS limited to localhost. Endpoints:
`/api/health`, `/api/hardware`, `/api/profile`, `/api/models`,
`/api/ollama/status`, `/api/offline`, `/api/storage`, and `POST /api/chat`
(guards against any non-local AI endpoint, then calls local Ollama). Logs to
`storage/adwin.log`.

## 5. Module layer (`modules/`)
| Module | Status | Engine(s) |
|---|---|---|
| `chat` | **Implemented** (Ollama client, streaming + direct) | Ollama / llama.cpp |
| `image_studio` | **Implemented** (Phase 6) — real ComfyUI API + VRAM gate | ComfyUI + SDXL/FLUX |
| `video_studio` | **Implemented** (Phase 7) — scene-based FFmpeg assembly; AI gen gated | FFmpeg + local LLM + TTS (ComfyUI video optional) |
| `voice_studio` | **Implemented** (Phase 8) — TTS live, STT engine-gated | Piper/pyttsx3 (TTS), whisper.cpp/faster-whisper (STT), ffmpeg |
| `knowledge_center` | **Implemented** (Phase 9) — RAG with citations | local embeddings + SQLite vector store |
| `developer_lab` | **Implemented** (Phase 10) — assistant + approval-gated exec | coding LLM, confined sandbox |
| `cyber_lab` | **Implemented** (Phase 13) — defensive diagnostics + authorized port check | psutil, sockets, DNS/ping |

## 6. Technology choices
Python + FastAPI (backend), static JS dashboard now → React+TS later, SQLite
(metadata), local filesystem (documents/models), Ollama + llama.cpp (LLMs),
ComfyUI (images), FFmpeg (media assembly), Whisper.cpp + Piper (voice). Docker
is **optional** (dev / ComfyUI isolation); the SSD target runs native services.

## 7. Portability & deployment
Development happens on any OS (this repo was built and tested on Windows 11).
The deployment target is **Ubuntu on the external SSD** as a Live + persistent
system with a Windows-readable **exFAT** output partition. See
[INSTALLATION_GUIDE.md](../INSTALLATION_GUIDE.md). Installation onto the SSD is
**never automated** and never touches internal drives without explicit, validated
confirmation.
