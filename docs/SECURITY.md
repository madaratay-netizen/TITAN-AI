# TITAN AI — Security

## Principles
- **Local-first, loopback-only** by default; no telemetry; no hidden network.
- **Least privilege** for every tool; destructive actions are gated.
- **Honest capability reporting** — never claim a protection that isn't verified.

## Network / offline
- Backend binds `127.0.0.1`; CORS limited to localhost (`backend/app/main.py`).
- Chat and RAG refuse non-loopback AI endpoints when offline mode is on.
- Linux target ships firewall rules (`infrastructure/firewall/`): default-deny
  outbound in offline mode, with an explicit allowlist for download mode.

## Code execution (Developer Lab)
- Generated code is **never auto-executed**. Flow: `propose → display → explicit
  approve`. Execution is workspace-confined, timed, output-capped.
- Destructive command patterns (`rm -rf`, `shutdown`, pipe-to-shell, fork bombs,
  raw-disk writes) are blocked unless explicitly overridden.

## IT & Cyber Lab (defensive only)
- Read-only diagnostics + an **authorization-gated** TCP connect check: loopback
  is free; private/public targets require explicit `authorized=true`.
- **No** exploitation, stealth, credential theft, persistence, or destructive
  offensive features.

## Secrets
- API keys / passwords are never logged and never stored in plaintext on the
  Windows-visible `TITAN_WORKSPACE`. App secrets live on `TITAN_SYSTEM`.

## Disk operations
- Never automatic. Enumerate → identify by **model + size + bus** (serial is
  unreliable on the reference enclosure) → show the plan → explain what is erased
  → explicit confirm → re-verify immediately before execution.
- Host internal drives and the Windows bootloader are **out of scope**.

## Updates
- Target `TITAN_SYSTEM`/`TITAN_BOOT` only; refuse any op resolving to
  `TITAN_WORKSPACE`; back up config first; verify integrity before applying.

## Input handling
- Workspace filenames sanitized for exFAT/Windows; atomic writes prevent
  partial files; untrusted document parsing is sandboxed to the workspace.
