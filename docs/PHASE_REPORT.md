# ADWIN OS — Phase Report

Honest record of what is **built and verified** vs. **planned**. No feature is
listed as working unless it was actually run.

_Dev/build machine (measured):_ Windows 11, Intel i7-12650H (10C/16T), 15.71 GB
RAM, NVIDIA RTX 2050 4 GB (CUDA cc 8.6) + Intel UHD, external 128 GB SSD at `E:`.
_Classified:_ **PROFILE 3 (Advanced)**.

---

## Phase 1 — Environment inspection ✅ done
Detected OS/CPU/RAM/GPU/storage and tool availability (Ollama 0.40.16 +
`qwen3.5:4b`, ffmpeg, nvidia-smi, node, git present; Docker/WSL-distro absent).

## Phase 2 — Project structure + architecture ✅ done
Repo scaffolded (`git init`, branch `main`), full directory tree, architecture
and installation docs, `docker-compose.yml`, pinned `requirements.txt`.

## Phase 3 — Adaptive Intelligence Engine ✅ done & tested
- `core/hardware_detection/detector.py` — real multi-platform probing, zero-dep fallbacks.
- `core/adaptive_engine/` — P1–P5 classification + safe per-model load decisions
  (VRAM/CPU/hybrid, hard RAM gate). Two logic bugs found during testing were
  fixed (profile tolerance; budgeting on total RAM + GPU offload).
- `core/model_registry/` — full schema registry, SQLite install-state,
  live compatibility status, license tracking.
- `core/offline_manager/` — three-level isolation reporting (never over-claims).

## Phase 4 — Backend API + Dashboard ✅ done & verified live
- FastAPI app, loopback-only, logging to `storage/adwin.log`. Endpoints:
  health, hardware, profile, models, ollama/status, offline, storage, chat.
- Dashboard (`frontend/index.html`) rendered live with real hardware, profile,
  models and storage; served at `http://127.0.0.1:8077`.

## Phase 5 — Local LLM integration ✅ done & verified
- `modules/chat/ollama_client.py` — stdlib Ollama client (status, list, chat,
  streaming, reasoning-model `think` toggle). **Real answer returned from
  `qwen3.5:4b` via the API, fully local.** Cold load ~6 s, warm response <1 s.

## Phase 9 — Knowledge Center (RAG) ✅ done & verified live
- `modules/knowledge_center/` — real pipeline: parsers (pdf/docx/xlsx/txt/md/csv),
  overlapping chunking, local embeddings, SQLite vector store (pure-Python cosine),
  and a RAG orchestrator that answers from retrieved context with `[n]` citations.
- **Embeddings:** `OllamaEmbedder` (nomic-embed-text, semantic) with a zero-download
  **lexical fallback** so RAG works on any machine offline. A per-process `hash()`
  bug (would break retrieval across restarts) was found and fixed (deterministic crc32).
- **Verified:** ingested text, asked via API and UI; the local LLM returned grounded,
  cited answers (e.g. "7 bar", "peristaltic dosing pump 50 L/h [1]") — fully offline.
- **Semantic embeddings active:** `nomic-embed-text` pulled (274 MB) and in use; a
  paraphrased query with no keyword overlap retrieved the right passage (score 0.60
  vs ~0.33 lexical), proving semantic retrieval over the lexical fallback.
- Per-project libraries; documents never leave the machine; `/api/knowledge/*` routes +
  a working Knowledge Center dashboard view.

## Phase 10 — Developer Lab ✅ done & verified live (Cyber Lab pending)
- `modules/developer_lab/` — three parts:
  - `assistant.py` — code generate / explain / review / debug via the local LLM
    (prefers an installed coding model, else the default). Text only; never runs code.
  - `workspace.py` — project file list/read/write/search **confined** to a workspace
    root (path-traversal attempts rejected).
  - `executor.py` — **security-critical approval gate**: `propose → display → approve`.
    Code never auto-runs; approval needs explicit `confirm=True`; execution is
    cwd-confined, timed, output-capped; destructive patterns (`rm -rf`, `shutdown`,
    pipe-to-shell, …) are blocked unless explicitly overridden.
- **Verified (API + UI):** generated a Fibonacci fn; proposed a command (didn't run);
  approve-without-confirm → **403 refused**; approve-with-confirm → ran confined
  (exit 0, stdout `4950`); `rm -rf /` → flagged and **403 blocked**.
- Routes `/api/dev/*` + a working Developer Lab dashboard view.

## Phase 13 (IT & Cyber Lab) ✅ done & verified live — defensive only
- `modules/cyber_lab/` — read-only diagnostics + an authorization-gated check:
  - `diagnostics.py` — system health (CPU/RAM/uptime/procs), disk health (usage +
    SMART/WMI status), network interfaces, DNS lookup, ping (arg-list, no shell).
  - `scanner.py` — TCP-**connect** port check (no stealth/raw sockets). Loopback is
    allowed; private/public targets require explicit `authorized=true`. Single host,
    port count capped.
  - `logs.py` — severity counts, recent errors, and normalized error-signature grouping;
    file analysis confined to an allowed directory.
- **Verified live:** system metrics returned; loopback check found 445/8077/11434;
  **scanning 8.8.8.8 without authorization was gated** (authorization_required); logs
  grouped two `disk <path> failed` lines into one signature.
- No exploitation, stealth, credential-testing, or persistence features — by design.
- Routes `/api/cyber/*` + a working IT & Cyber Lab dashboard view.

## Phase 8 — Voice Studio ✅ done & verified live (STT needs an engine install)
- `modules/voice_studio/` — pluggable local voice:
  - `engines.py` — honest detection of whisper.cpp / faster-whisper (STT), Piper /
    pyttsx3 (TTS), ffmpeg, and the system voices (flags Arabic availability).
  - `tts.py` — Piper (neural) with a **pyttsx3/SAPI fallback that works offline now**;
    writes a real WAV + duration. Never fabricates audio.
  - `stt.py` — whisper.cpp + faster-whisper integration; raises STTUnavailable
    (honest) rather than faking a transcript when no engine is present.
  - `subtitles.py` — deterministic SRT/VTT from timed segments.
  - `audio.py` — ffmpeg duration / convert / concat.
- **Found & fixed a false-positive bug:** whisper.cpp detection matched `main`
  (→ Windows `main.CPL`) and `whisper` (→ an unrelated project's CLI), wrongly
  reporting "STT available". Tightened to `whisper-cli`/`whisper-cpp` only.
- **Verified live:** generated a real offline voiceover (WAV + MP3, played in the UI,
  3.3–3.5 s @ 22050 Hz via SAPI); ffmpeg duration matched; SRT/VTT correct; STT with
  a real audio file returned an honest 503 ("install whisper.cpp / faster-whisper").
- **Arabic:** no Arabic system voice on this machine — reported honestly (needs a
  Piper ar_* model or a Windows Arabic language pack), per the spec's verify-first rule.
- Routes `/api/voice/*` + a working Voice Studio dashboard view with audio playback.

## Phase 6 — Image Studio ✅ done & verified (real ComfyUI; no placeholders)
- `modules/image_studio/` — a genuine ComfyUI integration:
  - `comfy_client.py` — real ComfyUI HTTP API client (system_stats liveness,
    /prompt submit, /history poll, /view fetch, /queue depth).
  - `workflows.py` — builds real ComfyUI API-format graphs (SDXL text-to-image,
    image-to-image, latent upscale), with parameter validation.
  - `studio.py` — orchestrator with a **VRAM gate** (reuses the adaptive engine):
    estimates VRAM for the resolution/model and refuses (unless allow_slow) when
    it exceeds the safe budget. **If ComfyUI is not running, raises
    ImageStudioUnavailable — it never returns a placeholder image** (spec rule).
- **Verified live (this machine has no ComfyUI):** status reports not-running
  honestly; preflight for SDXL 1024² returns est 6000 MB > 3053 MB budget
  (needs_allow); /generate returns an honest **503** (no fake image); the VRAM
  gate is unit-tested for the 409 path. Dashboard shows the honest banner + preflight.
- **Honest hardware note:** on the RTX 2050 (4 GB) SDXL exceeds the safe VRAM
  budget, but **SD 1.5 at 512×512 runs well** — verified: ComfyUI v0.7.0 + SD 1.5
  generated a real image in **~14 s on the RTX 2050** (CUDA, `--lowvram`).
- Routes `/api/image/*` + an Image Studio dashboard view. Defaults tuned to SD 1.5.
- **Video Studio integration:** `modules/video_studio/visuals.py` generates an AI
  image per scene via ComfyUI (the "AI scene images" option), so a rendered video
  shows real generated visuals instead of title cards — verified end-to-end
  (3-scene narrated 720p video from generated images). Falls back to title cards
  honestly when ComfyUI isn't running. Setup: `scripts/install_comfyui.sh`.

## Storage / Workspace Manager ✅ done & verified live (Phase 3 / brief §4)
- `core/storage_manager/` — creates & guards `ADWIN_WORKSPACE`:
  - `ensure_structure()` — builds the 11 standard folders (Images/Videos/Audio/…).
  - `health()` — filesystem, capacity, used %, **free-space reserve**
    (max 2 GiB / 5%), low-space & below-reserve flags, per-folder file counts/sizes,
    and **unavailable / read-only detection**.
  - `safe_write()` — **atomic** (temp + fsync + rename) with reserve enforcement;
    **exFAT-safe filenames** (invalid chars, reserved names, trailing dot/space, length).
  - `backup_settings()` / `restore_settings()` — zip User_Settings + config, with
    path-traversal-safe restore. **Never deletes user files.**
- **Verified live:** health on the dev workspace (NTFS, reserve 5.67 GB); ensure
  created all folders; a 1 PB request was refused ("would breach reserve"); backup
  zip written; the partition plan (ADWIN_EFI/BOOT/SYSTEM/MODELS/WORKSPACE) served.
- Routes `/api/storage/*` + a Storage Manager dashboard view (health cards, folder
  table, plan, ensure/backup actions).

## Phase 7 — Video Studio ✅ done & verified live (FFmpeg assembly)
- `modules/video_studio/` — a real **scene-based** production pipeline:
  - `project.py` — multi-scene project model (JSON-persisted; add/remove/reorder/
    duration edits; resume after interruption). A 3-minute video = many scenes.
  - `storyboard.py` — **local-LLM** idea → scene breakdown (title/description/
    narration/duration). Produces a plan, never claims to be rendered video.
  - `assembler.py` — **real FFmpeg render**: title/color cards, still images, and
    imported clips → normalized → concat → MP4; optional per-scene narration audio,
    burned subtitles, background music; 480p/720p/1080p/4k.
  - `generation.py` — optional AI clip generation, **hardware-gated and honest**:
    on <12 GB VRAM it refuses and points to the import+assemble path (never fakes).
- **Verified live:** `qwen3.5:4b` produced a 3-scene storyboard; a **narrated MP4**
  was rendered (854×480, 13.6 s, local TTS voiceover) and played back — fully
  offline. AI clip-gen correctly reported unavailable on the RTX 2050 (4 GB).
- On low-resource machines, editing/assembly from imported footage works without
  any AI video model (per the brief). Routes `/api/video/*` + a Video Studio view.

## Phase 11 — Offline hardening ✅ done & verified live
- `core/security_manager/` — the offline security posture made real:
  - `firewall.py` — generates **nftables** (Linux) + **Windows** firewall rules for
    `offline` (default-drop outbound, loopback only) and `download` (+ DNS/HTTP/S)
    modes. Templates written to `infrastructure/firewall/`. **ADWIN never applies
    them automatically** (that would change system security settings).
  - `egress.py` — egress self-test: bare TCP connects to public DNS IPs (no data
    sent) → `egress_blocked` / `egress_open`, so isolation is reported truthfully.
  - `audit.py` — config audit: loopback bind, offline mode, local AI endpoint, no
    telemetry, no auto-download, honest isolation claim → posture
    (hardened / needs_attention / not_offline_safe).
- **Verified live:** audit = **hardened (6/6 pass)**; egress test correctly reported
  `egress_open` on this internet-connected dev box ("apply the offline firewall to
  block egress") — the honest offline-mode vs fully-isolated distinction; offline
  nftables ruleset generated.
- Routes `/api/security/*` + a Security dashboard view (audit, egress, firewall).

## Live-boot & SSD tooling ✅ done & verified (Phase 6/12 — no real disk touched)
- `core/live_boot/partition_planner.py` — computes the partition plan from a
  disk's **actual** capacity (fixed EFI/BOOT/SYSTEM/MODELS; WORKSPACE = rest −
  reserve; scales down on small disks; refuses tiny disks) and **classifies a
  target** as safe/unsafe (refuses the system disk and non-USB devices; identifies
  by model+size+bus, never serial). Pure logic — **no disk operations**.
- `infrastructure/boot/` — reviewed, confirmation-gated shell templates
  (`bash -n` clean): `partition_ssd.sh` (**dry-run by default**; `--apply` prompts
  for the device path + `YES` and re-verifies before writing; refuses system/
  non-USB), `mount_workspace.sh` (mount by label + build the workspace tree),
  `build_live.sh` (Ubuntu 24.04 Live image build on a dev box only). Plus the
  read-only `scripts/identify_disk.sh`.
- **Verified:** the planner produced the real plan for the measured device
  (119.24 GiB → 118.64 usable, 53.7 GiB exFAT workspace); `/api/storage/plan`
  returns it live; all scripts pass syntax checks. **No disk was partitioned.**
- Remaining for a physical deployment (hardware/VM, operator-driven): run the
  Live build, apply the gated partitioning on the real SSD, install GRUB to
  ADWIN_EFI, and run the Phase-7 system tests (boot, persistence, exFAT on both
  OSes, update-safety). These require the SSD + a test host and are out of scope
  for this dev environment by design.

## Phase 12 — Install/deploy/recovery/test scripts 🟡 partial
- `scripts/adwin_report.py` ✅, `scripts/offline_test.py` ✅ (5/5 pass),
  `scripts/identify_disk.sh` ✅ (read-only, refuses system disk).
- Partition/Ubuntu-to-SSD install: **documented template only, not executed** —
  deliberately confirmation-gated and never automated.

---

## Tests actually run
| Suite | Result |
|---|---|
| `pytest` (engine, registry, API, RAG, dev, cyber, voice, image, storage, video, security, live-boot) | **132 passed** |
| `scripts/offline_test.py` | **5 passed, 0 failed, 0 skipped** |
| Live API + chat (`qwen3.5:4b`) | **verified** |
| Dashboard render (browser) | **verified** |

## Commands executed (key ones)
`python scripts/adwin_report.py` · `python -m venv .venv` ·
`pip install -r requirements.txt` · `pytest -q` · `python scripts/offline_test.py` ·
`uvicorn backend.app.main:app --host 127.0.0.1 --port 8077`

## Known limitations
- Image/Video/Voice/Knowledge/Dev/Cyber modules are **not yet implemented**.
- Creator/Studio tiers currently gate on **CUDA**; AMD/Intel acceleration for
  media is not yet wired (Vulkan is detected but not used for inference).
- SSD partition/install scripts are **unexecuted templates**.
- Frontend is a single static page; the React+TS build is a later step.
- "Full network isolation" is **not** claimed — only offline operation is tested.

## Next steps (recommended order)
1. Phase 6: ComfyUI integration + Image Studio (real text-to-image; SDXL `cpu_only`
   here, needs a ≥6 GB-VRAM machine for GPU).
2. Phase 9: Knowledge Center RAG using `nomic-embed-text` (fits this machine).
3. Phase 10: Developer Lab with `qwen2.5-coder:3b` and sandboxed, approval-gated exec.
4. Phase 11: firewall rules + offline hardening, then re-run the offline test.
5. Storage manager with pre-download free-space guards for the 128 GB plan.
