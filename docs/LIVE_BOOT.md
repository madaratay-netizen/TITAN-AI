# TITAN AI — Live Boot Architecture

TITAN AI boots a **portable Live Linux** from the external SSD. It does **not**
install onto the host, does **not** touch the host's internal drives, and does
**not** modify the host's Windows bootloader.

## Model: read-only base + writable overlay + persistent data
```
UEFI firmware
  └─ TITAN_EFI (FAT32, ESP)  → GRUB2  (installed on the SSD only)
       └─ TITAN_BOOT (ext4)  → kernel + initrd + filesystem.squashfs (READ-ONLY base)
            └─ OverlayFS writable layer  (persistence on TITAN_SYSTEM)
                 ├─ /opt/titan        → persistent app/runtime (survives reboot)
                 ├─ /opt/titan/models → TITAN_MODELS
                 └─ /workspace        → TITAN_WORKSPACE (exFAT, user data)
```
- **Base OS is read-only** (SquashFS): reproducible and disposable. A "rebuild
  Live system" replaces `filesystem.squashfs` on `TITAN_BOOT` and nothing else.
- **Writable overlay** (casper `persistent`) holds controlled runtime changes on
  `TITAN_SYSTEM`. Disposable runtime state can be reset without losing user data.
- **User data is a separate partition** (`TITAN_WORKSPACE`) and is **never part
  of the disposable overlay**.

## Base distribution
Ubuntu 24.04 LTS (x86-64), built as a Live image with `casper`. Lightweight
desktop (e.g. XFCE) to keep the footprint appropriate for 128 GB. The image is
built on a **development machine** with reproducible tooling (`live-build` /
Cubic), never against the user's SSD.

## Boot flow
1. User selects the SSD in the firmware boot menu (one-time, per host).
2. GRUB (on `TITAN_EFI`) loads kernel + initrd from `TITAN_BOOT`.
3. `casper` mounts the SquashFS base read-only and layers the OverlayFS
   persistence from `TITAN_SYSTEM`.
4. `TITAN_MODELS` and `TITAN_WORKSPACE` are mounted; the workspace structure is
   verified/created.
5. Auto-login to the TITAN desktop, which launches the backend (loopback) and
   opens the dashboard.

## UEFI / Secure Boot
- **UEFI x86-64** is the primary target; GRUB lives on the SSD's own ESP.
- **Secure Boot:** works only with a signed shim/kernel chain. If the image is
  not signed for the host's key database, the user must either boot a
  signed-shim build or disable Secure Boot in firmware. **This is documented as a
  known limitation, not silently worked around.**
- **Legacy BIOS:** supported only if the chosen GRUB build provides it reliably;
  otherwise UEFI-only is stated plainly.

## Host safety (non-negotiable)
- GRUB is installed **on the SSD ESP only**; the host's EFI entries and Windows
  Boot Manager are untouched.
- No partition of any internal disk is read, mounted-for-write, or modified.
- Booting the SSD changes nothing on the host; unplugging it returns the host to
  normal.

## Updates & recovery (summary; see §11 of the brief)
- **Updates** replace/patch `TITAN_SYSTEM` (and, for a base refresh,
  `TITAN_BOOT`'s squashfs). The updater **verifies the target partition label**
  and **refuses** if it resolves to `TITAN_WORKSPACE`. Config is backed up first;
  update integrity is verified before applying.
- **Recovery / rebuild:** re-flash `filesystem.squashfs` and reinstall GRUB to
  `TITAN_EFI` from the build artifacts. `TITAN_WORKSPACE` is never part of this
  and keeps all user data.
- Because the workspace is exFAT, the user can also copy it off from any
  Windows/Linux machine before a rebuild for extra safety.

## Development vs. deployment
All Live-image building and partitioning is done on a dev box or in
VMs/loopback images. The on-SSD partition/install step is a **separate,
confirmation-gated** operation (see `scripts/identify_disk.sh`, read-only, and
the installation guide) and is never triggered by the application.
