# ADWIN OS — Live boot & SSD tooling

Reviewed, confirmation-gated templates. **Nothing here runs automatically, and
no script touches the host's internal drives.** Build/test on a dev box or VM;
partition only after explicit, re-verified confirmation.

| Script | What it does | Writes? |
|---|---|---|
| `../../scripts/identify_disk.sh` | List external/USB disks (excludes the system disk). | No (read-only) |
| `build_live.sh` | Build the Ubuntu 24.04 Live image (SquashFS + ADWIN) on a dev box. | Only `./build` |
| `partition_ssd.sh` | Partition the SSD — **dry-run by default**; `--apply` prompts for the device path + `YES` and re-verifies before writing. | Only with `--apply`, after confirmation |
| `mount_workspace.sh` | Mount ADWIN_SYSTEM/MODELS/WORKSPACE by label; create the workspace tree. | Mounts only; no format |

## Safe workflow
1. `bash ../../scripts/identify_disk.sh` — find the SSD (match model + size + USB).
2. Build the image: `bash build_live.sh` (dev box).
3. **Dry-run** the plan: `sudo bash partition_ssd.sh --device /dev/sdX`.
4. Review the plan; it erases the whole SSD. When certain:
   `sudo bash partition_ssd.sh --device /dev/sdX --apply` (type the path + `YES`).
5. Flash the Live image onto `ADWIN_BOOT`, install GRUB to `ADWIN_EFI`
   (SSD only), then `sudo bash mount_workspace.sh`.

## Testing without a real disk (recommended first)
```bash
# Create a 128 GiB sparse loopback image and partition THAT, not a real disk:
truncate -s 128G /tmp/adwin_test.img
sudo losetup -fP /tmp/adwin_test.img      # -> /dev/loopN
# NOTE: partition_ssd.sh refuses non-USB devices by design; use it against a
# real USB SSD only. For loopback tests, exercise core/live_boot/partition_planner
# (pure Python) which computes the same plan with no disk operations.
```

## Guarantees
- Identify by **model + size + bus** (serial is unreliable on some enclosures).
- Refuse the running system disk and non-USB devices.
- Dry-run by default; explicit device + `YES` confirmation; re-verify before write.
- GRUB goes on the SSD's own ESP; the host Windows bootloader is never modified.
- `ADWIN_WORKSPACE` (exFAT) is separate, so user data survives updates/rebuilds.
