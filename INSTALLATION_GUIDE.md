# TITAN AI — Installation & Deployment Guide

Two tracks:

- **A. Development / run the engine now** — works today on Windows, macOS, or Linux.
- **B. SSD deployment** — the portable Live-Linux target (documented; never automated).

> ⚠️ **Safety first.** TITAN never formats a disk automatically and never writes to
> your computer's internal drives. Every destructive step requires you to confirm
> the exact target device. Read [scripts/README.md](scripts/README.md) before running
> any disk script.

---

## A. Development quickstart (runs the real engine + chat)

**Prerequisites:** Python 3.11+, and (for chat) [Ollama](https://ollama.com) with a model.

```bash
# 1. Zero-dependency system report — runs with just Python:
python scripts/titan_report.py

# 2. Install backend deps into a virtual environment:
python -m venv .venv
.venv/Scripts/activate            # Windows
# source .venv/bin/activate       # Linux/macOS
pip install -r requirements.txt

# 3. (chat) Ensure Ollama is running and a model is present:
ollama serve &                    # if not already running
ollama pull qwen3.5:4b            # ~3.3 GB (skip if already installed)

# 4. Start the TITAN backend + dashboard (loopback only):
uvicorn backend.app.main:app --host 127.0.0.1 --port 8077

# 5. Open the dashboard:
#    http://127.0.0.1:8077
```

Run the tests:
```bash
pip install pytest
pytest -q
```

---

## B. Portable SSD deployment (final approved design)

**Target:** a 128 GB external USB SSD (≈119 GB usable). Design: **Live Linux +
persistent workspace + Windows-accessible shared storage**.

### B.1 Approved 128 GB partition plan

| Label | Purpose | Filesystem | Size |
|---|---|---|---|
| **LIVE** | Base system + TITAN apps (boot/EFI + root) | ext4 (+ FAT32 EFI) | ~28 GB |
| **AI** | Local AI models | ext4 | ~35 GB |
| **SHARED** | Your outputs (images, video, audio, docs) | **exFAT** | ~45 GB |
| **EXTRA** | Reserve, cache, updates | (free / ext4) | ~20 GB |

- **exFAT** on SHARED is deliberate: it is read/write on **both Linux and Windows**
  and handles large video files — so your renders are accessible from either OS.
- Large **video** models are **not** installed by default; they belong on an
  optional second external drive. The storage manager warns before any download
  that would breach free-space reserves.
- These are **planning targets**. The installer presents the computed plan from
  the SSD's *actual* usable capacity and asks for approval before writing anything.

### B.2 Recommended base
Ubuntu 24.04 LTS Desktop (x86-64), installed to the SSD as a persistent system
with its **own** EFI partition and GRUB **on the SSD** (never the internal disk),
UEFI-compatible, with Secure Boot compatibility tested separately.

### B.3 Procedure (high level — scripts validate each step)
1. **Identify the SSD** — `scripts/identify_disk.sh` lists candidate *external*
   devices with model, size, and bus, and refuses fixed internal disks.
2. **Confirm the target** — you type the exact device path; the script re-reads
   and shows you what will be erased and requires an explicit `YES`.
3. **Partition** per the plan above (or the capacity-adjusted plan).
4. **Install** the base OS to LIVE, mount AI/SHARED/EXTRA, and deploy TITAN.
5. **First-run wizard** detects hardware, classifies the profile, proposes a
   storage plan, and offers to pull the primary LLM (`qwen3.5:4b`) on demand.
6. **Offline hardening** — local-only binding + firewall rules; then run the
   offline verification test before flipping `isolation_verified = true`.

> The partition/install scripts are provided as **reviewed, confirmation-gated
> templates**. They do not run as part of development and must be executed
> deliberately by an operator who has verified the target device.

### B.4 Backup & recovery
The SHARED (exFAT) partition is portable and can be copied from any Windows/Linux
machine. `scripts/backup.sh` (planned) snapshots configs + the model manifest
(not the weights) so a machine can be re-provisioned and models re-pulled on demand.

---

## Known limitations (be honest)
- SSD install scripts are **templates**, not yet run end-to-end on hardware.
- Image/Video/Voice/Knowledge/Dev/Cyber modules are **planned** — see the
  [phase report](docs/PHASE_REPORT.md). Chat + the adaptive engine are live.
- On a 4 GB-VRAM GPU, a 4B LLM partially offloads to CPU; expect a few seconds of
  cold-load before the first answer.
