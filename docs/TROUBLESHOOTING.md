# ADWIN OS — Troubleshooting

## Boot
- **SSD not in the boot menu:** enable USB boot in firmware; try the other USB
  port; confirm the image was written to the SSD, not a file on it.
- **Secure Boot blocks boot:** use a signed-shim build or disable Secure Boot in
  firmware (see [LIVE_BOOT.md](LIVE_BOOT.md)).
- **Boots to host Windows instead:** pick the SSD explicitly in the one-time
  firmware boot menu; ADWIN never changes the host boot order.

## Workspace (exFAT)
- **Workspace not visible in Windows:** ensure `ADWIN_WORKSPACE` is exFAT and the
  SSD is fully seated; assign a drive letter if Windows didn't.
- **Read-only / unavailable workspace:** ADWIN reports this and blocks large
  writes. Re-mount the partition; check it isn't mounted elsewhere.
- **Corruption after unsafe removal:** always eject safely (exFAT has no
  journal). Repair: `chkdsk /f` (Windows) or `fsck.exfat` (Linux). Keep a copy in
  `Backups/`.
- **"Filename rejected":** ADWIN sanitizes names, but manually created files with
  `<>:"/\|?*` or trailing dot/space won't work on exFAT/Windows.

## AI runtime
- **Chat says Ollama not running:** start `ollama serve`; confirm a model is
  installed (`ollama list`).
- **Model won't load / out of memory:** the adaptive engine refused it as unsafe
  — pick a smaller/quantized model or free RAM/VRAM.
- **Image generation unavailable:** ComfyUI isn't running — start it; on a
  4 GB-VRAM GPU, SDXL is CPU-only (slow) and large models are refused by design.
- **STT unavailable:** install whisper.cpp or `pip install faster-whisper`
  (ADWIN won't fake a transcript).

## Storage
- **Low-space warning / download refused:** free space or move models to
  `ADWIN_MODELS` / another drive; the reserve is enforced on purpose.

## Network / offline
- **A feature needs the internet:** switch to the explicit online/download mode
  for models/updates, then back to offline. ADWIN never silently uses a cloud API.

## Logs
- Backend logs: `storage/adwin.log`. Secrets are never written there.

## Recovery
- Rebuild the Live base (re-flash `filesystem.squashfs`, reinstall GRUB to
  `ADWIN_EFI`); `ADWIN_WORKSPACE` is untouched. Back it up from Windows/Linux
  first for extra safety.
