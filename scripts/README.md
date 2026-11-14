# TITAN AI — scripts

| Script | What it does | Writes to disk? |
|---|---|---|
| `titan_report.py` | Full hardware + profile + model-compatibility report (zero deps). | No |
| `offline_test.py` | Offline Verification Test — PASS/FAIL/SKIP per check. | No (reads only) |
| `identify_disk.sh` | Lists **external** block devices to help identify the target SSD (Linux). Refuses the system disk. | **No — read-only** |

## Safety policy for disk operations
- No script in this repo formats or partitions a disk automatically.
- `identify_disk.sh` is strictly read-only and excludes the running system's disk.
- The partition/install step (SSD deployment) is a **separate, confirmation-gated**
  operation: the operator must type the exact device path and `YES`. It is not run
  during development and is never triggered by the backend.

## Usage
```bash
python scripts/titan_report.py          # or --json
python scripts/offline_test.py
bash   scripts/identify_disk.sh         # Linux target only
```
