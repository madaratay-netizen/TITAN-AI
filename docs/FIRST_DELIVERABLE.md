# TITAN AI — First Deliverable (Design Brief)

This document answers the eight items the brief requires **before** further
implementation (§15). It reflects the **actual** target device measured on
2026-11-14 and the software already built in this repository.

> Status check: the seven application modules (Chat, Knowledge/RAG, Image,
> Voice, Developer, Cyber + the adaptive engine & model registry) are
> **implemented and tested** (91 passing tests). What remains is largely the
> **Live-boot + storage/workspace layer** this brief emphasises. See
> [PHASE_REPORT.md](PHASE_REPORT.md) for exactly what runs today.

---

## 1. Architecture proposal

Layered, modular, runtime-agnostic (full detail in
[ARCHITECTURE.md](ARCHITECTURE.md)):

```
Dashboard (React/TS planned; working static dashboard today)
      │  loopback HTTP only
Backend API (FastAPI)  ── Storage Manager ── Hardware Detection ── Model Manager
      │                      │ (NEW)              │                   │
AI runtime adapters ────────┴────────────────────┴───────────────────┘
  Ollama / llama.cpp · ComfyUI · Whisper.cpp/Piper · FFmpeg
Security manager (offline guard, authz gate) · Logging & diagnostics
```

Separation of concerns is enforced by folder: `core/` (detection, adaptive
engine, model registry, offline manager), `backend/` (API), `modules/` (one
package per app), `infrastructure/` (linux/docker/firewall/boot). Configuration
(`configs/`, app SQLite DBs in `storage/`) is kept **separate from
user-generated content** (the exFAT workspace).

The system depends on **no single model or runtime**: the model registry +
adaptive engine choose at runtime, and every adapter degrades honestly.

## 2. Partition & storage plan for the real 128 GB SSD

Measured device: **Realtek RTL9210B-CG, 128.03 GB (119.24 GiB usable), USB,
serial unreliable (all-zeros)**. Full detail + mount table in
[STORAGE_LAYOUT.md](STORAGE_LAYOUT.md). Concrete plan (GiB):

| # | Label | FS | Size | Windows-visible | Purpose |
|---|---|---|---:|:--:|---|
| 1 | `TITAN_EFI` | FAT32 | 1 | yes* | UEFI boot (ESP) |
| 2 | `TITAN_BOOT` | ext4 | 21 | no | Live base (squashfs, read-only) + boot files |
| 3 | `TITAN_SYSTEM` | ext4 | 14 | no | Persistent app runtime, deps, config, logs, app DBs + writable overlay |
| 4 | `TITAN_MODELS` | ext4 | 23 | no | Optional AI model weights |
| 5 | `TITAN_WORKSPACE` | **exFAT** | 52 | **yes** | **User outputs — survives updates/rebuilds** |
| — | (free) | — | ~8.2 | — | Recovery buffer + SSD over-provisioning |

Totals to 111 GiB allocated, ~8.2 GiB left free for safety. These are planning
targets; the installer recomputes from real capacity and **requires approval**.

## 3. Linux Live technologies (selected)

- **Base:** Ubuntu 24.04 LTS (x86-64), built as a **Live ISO/image** (casper),
  not a host installation.
- **Read-only base + overlay:** SquashFS base + OverlayFS writable layer
  (casper `persistent`), so the OS layer is reproducible/disposable while a
  controlled persistence store survives reboots.
- **Bootloader:** GRUB2 (UEFI) installed **on the SSD's own ESP**; the host
  Windows bootloader is never touched. Legacy BIOS only if GRUB provides it
  reliably on the chosen image.
- **Build tooling:** `live-build`/`cubic`-style reproducible image build (run on
  a dev box, never against the user's disk).
- **Secure Boot:** documented with limitations (see [LIVE_BOOT.md](LIVE_BOOT.md)).

## 4. AI runtimes & model options

- **LLM runtime:** **Ollama** (primary; already integrated and verified) with
  **llama.cpp** as the lower-level fallback. Runtime-agnostic adapter.
- **Images:** **ComfyUI** (real API integration built; optional, GPU-gated).
- **Voice:** **Whisper.cpp** (STT) + **Piper** (TTS), with a pyttsx3/SAPI
  fallback (works offline today).
- **Media:** **FFmpeg** (present and used).
- **Default model:** one small quantized LLM — `qwen3.5:4b` (Apache-2.0), plus
  `nomic-embed-text` for RAG. **No large models by default.** License + size +
  hardware fit recorded per model in the registry; see
  [MODEL_MANAGEMENT.md](MODEL_MANAGEMENT.md).

## 5. Hardware-compatibility strategy

Measure first, promise nothing. `core/hardware_detection` probes CPU/RAM/GPU/
VRAM/disk/accel; `core/adaptive_engine` maps to performance profiles and makes
**per-model safe-load decisions** (hard RAM gate, VRAM budget, CPU fallback).
Profiles: **Low Resource · Balanced · High Performance · GPU Accelerated** (the
existing P1–P5 ladder maps onto these). CUDA is never assumed; AMD/Intel are
detected and unsupported combinations are reported rather than hidden. Heavy
image/video is explicitly gated and refused (not faked) when VRAM is insufficient.

## 6. Development roadmap

| Phase | Scope | State |
|---|---|---|
| 1 Environment inspection | real HW/tooling audit | ✅ done |
| 2 Architecture | structure, interfaces, storage, security | ✅ done |
| 3 Core app | FastAPI, dashboard, config, logging, **storage mgr** | ⏳ storage mgr next |
| 4 AI integration | inference, model mgmt, chat, RAG | ✅ done |
| 5 Creative tools | image ✅, voice ✅, **video** ⬜ | partial |
| 6 Live system | Live build, boot, overlay, workspace mount, recovery | ⬜ next major |
| 7 Testing | VM/CPU/offline/missing-deps/low-storage/persistence/exFAT | ⏳ unit done; system tests pending |
| 8 Documentation | the doc set below | ⏳ in progress (this deliverable) |

## 7. Risk assessment

| Risk | Severity | Mitigation |
|---|---|---|
| **Wrong disk partitioned** (host Windows wiped) | Critical | Read-only enumeration, model+size+bus match (serial unreliable here), explicit confirm, re-verify immediately pre-write; never auto-run |
| exFAT has no perms/symlinks/journaling | Med | Workspace holds user data only; atomic writes; no secrets in plaintext; models/app on ext4 |
| 4 GB-VRAM GPU can't run SDXL/FLUX/video | Med | VRAM gate refuses honestly; CPU fallback flagged slow; import-and-edit path for video |
| Workspace lost on update/rebuild | High | Workspace is a **separate partition**, never in the Live overlay; updates target system partition only |
| Model downloads fill the SSD | Med | Pre-download free-space checks; download-on-demand; no large models by default |
| Secure Boot blocks custom kernel | Low/Med | Document; signed shim path or user disables SB in firmware |
| exFAT corruption on unsafe removal | Med | Safe-eject guidance; atomic writes; fsck guidance in [TROUBLESHOOTING.md](TROUBLESHOOTING.md) |

## 8. Optional (not installed by default)

Installed only on explicit approval + storage/hardware checks: image models
(SDXL/FLUX) and ComfyUI, **all video generation models (LTX/Wan/Hunyuan)**,
larger LLMs, `faster-whisper`/whisper.cpp models, Piper Arabic voices, GPU
driver stacks (CUDA/ROCm). Default install stays lightweight for the 128 GB SSD;
large models may live on `TITAN_MODELS` or an additional external drive.

---

**Next implementation step (per §15, after this plan):** the **Storage /
Workspace Manager** — create & guard `TITAN_WORKSPACE`, capacity/health
reporting, low-space warnings, exFAT-safe atomic writes — because *protecting
TITAN_WORKSPACE is a top-level requirement*. Then the Live-boot build + the
confirmation-gated partition tooling.
