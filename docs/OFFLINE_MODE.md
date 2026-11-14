# ADWIN OS — Offline Mode & Privacy

Normal operation is **offline-first**. Internet is used only in an explicit
**online/download mode** for obtaining software and models.

## Guarantees in normal operation
- No mandatory external APIs, cloud accounts, or logins.
- No telemetry, no automatic uploads, no background calls to external servers.
- No automatic model downloads.
- No hidden network activity.
- AI inference is local only (Ollama/llama.cpp/ComfyUI on loopback).

## Three distinct states (reported honestly, never conflated)
- **`no_internet_requirement`** — ADWIN works without internet (by design).
- **`no_network_connectivity`** — this host currently has no link.
- **`fully_isolated`** — verified no outbound traffic. **Claimed only after an
  external packet-capture test**, never asserted by the app alone.

Implemented in `core/offline_manager`; surfaced at `/api/offline` and on the
dashboard.

## Offline mode ON (default)
- Backend binds to **127.0.0.1 only**; CORS limited to localhost.
- Optional outbound access is disabled; the chat endpoint refuses any non-local
  AI host.
- Any component that cannot function offline is reported clearly; the system
  **never silently falls back to a cloud API**.

## Online / download mode (explicit, opt-in)
Used to pull OS packages and models. Scoped to known sources (the model
registry's `source` field, OS repos). Turned off again for normal use. On the
Linux target this is backed by firewall rules (see `infrastructure/firewall/`
and [SECURITY.md](SECURITY.md)).

## Secrets & logs
- API keys / passwords are **never written to logs**.
- No plaintext secrets on the Windows-visible workspace; app secrets live on
  `ADWIN_SYSTEM`.

## Offline verification test
`scripts/offline_test.py` checks, and reports PASS/FAIL/SKIP honestly:
hardware detection, adaptive engine, local model server reachable, a **real
local inference**, and a coherent offline state. It explicitly notes that it
verifies offline *operation*, not network *isolation*.
