# ADWIN OS — Testing

## Automated tests (run with `pytest`)
Current status: **91 passing** across the engine and every implemented module.
Run:
```bash
.venv/Scripts/python -m pytest -q      # Windows
# .venv/bin/python -m pytest -q        # Linux
```
Coverage by area:
- **Adaptive engine / registry** — profile classification, safe-load gating,
  compatibility, licensing presence.
- **API** — health/hardware/profile/models/offline + the chat offline guard.
- **Knowledge/RAG** — chunking, deterministic lexical embeddings, vector-store
  retrieval, parsers, confinement.
- **Developer Lab** — workspace confinement, the execution approval gate,
  destructive-pattern blocking.
- **Cyber Lab** — authorization gate, real open-port detection on a bound
  socket, log-signature grouping.
- **Voice Studio** — subtitle formatting, engine-detection shape, TTS/audio
  integration (skipped, not faked, when no engine is present).
- **Image Studio** — real ComfyUI workflow construction, validation, the VRAM
  gate, `/history` parsing, and the honest-unavailable path.

Integration tests that need an external engine **skip** rather than fake when it
is absent (matching the "no fake passes" rule).

## Manual / live verification performed
- Local LLM chat via Ollama (`qwen3.5:4b`) — real answers, offline.
- RAG end-to-end with semantic embeddings (`nomic-embed-text`) — cited answers.
- Developer Lab approval gate — refuses without confirm, blocks `rm -rf /`.
- Cyber Lab — gated public scan, loopback port detection.
- Voice Studio — real WAV/MP3 voiceover played in the UI.
- Image Studio — honest 503 when ComfyUI is absent (no placeholder).

## System tests still to run (Phase 7, on hardware/VMs)
- Boot the Live SSD on UEFI hardware; CPU-only operation.
- GPU detection on machines with real GPUs.
- **Offline isolation** via external packet capture (before claiming
  `fully_isolated`).
- Missing-model / missing-dependency behaviour.
- Low-storage behaviour and reserve enforcement.
- **Workspace persistence across reboots**; exFAT read/write on both Linux and
  Windows.
- **System update does not overwrite `ADWIN_WORKSPACE`.**
- **Host internal drives remain untouched** (verify on a disposable test host /
  VM with virtual disks — never a user's real disk).

## Rules
- A test is reported passed only if it actually ran.
- Disk-operation logic is exercised against **loopback/virtual disks**, never a
  real user disk.
