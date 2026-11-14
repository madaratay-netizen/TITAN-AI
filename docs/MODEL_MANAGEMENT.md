# ADWIN OS — Model Management

Models are **never downloaded automatically** and **never large by default**.
The model registry (`core/model_registry/`) records, per model: name, family,
kind, size, quantization, min/recommended RAM & VRAM, backends, **license**,
source, install status, and a live **compatibility status** computed from the
adaptive engine.

## What the user can do
- See installed models, sizes, and estimated RAM/VRAM needs.
- See whether a model is **compatible with the current hardware**
  (`ok` / `cpu_only` / `incompatible`).
- Download a model manually (with a free-space check first).
- Remove a model; select a default; store models on `ADWIN_MODELS` or another
  external drive.

## Default footprint (lightweight for 128 GB)
- **LLM:** `qwen3.5:4b` (Apache-2.0, ~3.3 GB) — primary.
- **Embeddings:** `nomic-embed-text` (Apache-2.0, ~0.3 GB) — RAG.
- Everything else (SDXL, FLUX, video models, larger LLMs, Piper voices) is
  **optional** and installed only on explicit approval after storage/hardware
  checks.

## Compatibility gating
The adaptive engine refuses to load a model whose estimated footprint exceeds
safe resources (hard RAM gate + VRAM budget), offering CPU fallback where
practical. Example on the reference machine (16 GB / RTX 2050 4 GB): LLMs `ok`,
SDXL `cpu_only`, FLUX & video models `incompatible`.

## Licensing
Each model keeps its own license; the registry records it and it is reviewed
**before** bundling or recommending. Gemma-family terms, CreativeML-OpenRAIL
(SDXL), and per-model video licenses are flagged for review; nothing with an
unclear redistribution status is bundled by default.

## Storage safety
Before any download the storage manager checks free space against the reserve;
a download that would breach the reserve is refused with a clear message.
