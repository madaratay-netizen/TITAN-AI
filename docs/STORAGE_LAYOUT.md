# ADWIN OS — Storage Layout

Target device (measured 2026-11-14): **Realtek RTL9210B-CG USB SSD —
128.03 GB nominal / 119.24 GiB usable**. The enclosure reports an **all-zero
serial**, so device identification must use **model + size + bus**, never serial.

> **Protecting `ADWIN_WORKSPACE` is a top-level requirement.** User outputs live
> on their **own exFAT partition**, never inside the Live system or its overlay,
> so they survive system updates, recovery, and Live rebuilds.

## Partition table (planning target — installer recomputes & asks approval)

| # | Label | FS | Size (GiB) | Mount (Linux) | Windows | Purpose |
|---|---|---|---:|---|:--:|---|
| 1 | `ADWIN_EFI` | FAT32 | 1 | `/boot/efi` | shown* | UEFI boot (ESP), GRUB on the SSD only |
| 2 | `ADWIN_BOOT` | ext4 | 21 | `/run/live/medium` | no | Kernel/initrd + read-only SquashFS base |
| 3 | `ADWIN_SYSTEM` | ext4 | 14 | `/opt/adwin` (+ overlay) | no | Persistent app, Python env, deps, config, logs, app SQLite |
| 4 | `ADWIN_MODELS` | ext4 | 23 | `/opt/adwin/models` | no | Optional model weights (ext4: keeps perms/symlinks) |
| 5 | `ADWIN_WORKSPACE` | **exFAT** | 52 | `/workspace` | **yes (drive letter)** | **User outputs; cross-OS; protected** |
| — | free | — | ~8.2 | — | — | Recovery buffer + SSD over-provisioning |

\* The ESP is visible to Windows but normally has no drive letter. Only
`ADWIN_WORKSPACE` is meant for day-to-day Windows access.

**Why these filesystems**
- **FAT32** ESP — required by UEFI.
- **ext4** for BOOT/SYSTEM/MODELS — journaling, POSIX permissions, symlinks
  (model runtimes and Python envs need these; exFAT cannot provide them).
- **exFAT** for WORKSPACE — the only filesystem both Windows and Linux read/write
  natively that also handles large (>4 GB) video files.

## Capacity math (why ~8 GiB stays free)
`1 + 21 + 14 + 23 + 52 = 111 GiB` allocated of 119.24 GiB usable → **~8.2 GiB
unallocated**. That headroom covers filesystem overhead, SSD wear-levelling
over-provisioning, and a safety margin so the system never runs a partition to
0 bytes. The storage manager refuses writes that would breach the reserve.

## ADWIN_WORKSPACE directory structure
Created on first boot (and re-created if missing) by the storage manager:

```
ADWIN_WORKSPACE/
├── Images/            # Image Studio outputs
├── Videos/            # Video Studio renders & imports
├── Audio/             # Voice Studio TTS/STT outputs
├── Documents/         # Knowledge Center source docs & exports
├── Code/              # Developer Lab files
├── Projects/          # multi-file user projects
├── AI_Conversations/  # exported chats
├── Exports/           # general exports
├── Imports/           # user-provided inputs
├── Backups/           # config/settings backups (no plaintext secrets)
└── User_Settings/     # per-user preferences (non-secret)
```

Every module writes user outputs here by default; a custom output directory is
allowed. The home dashboard shows free space before large writes and warns when
low.

## exFAT handling rules (enforced by the storage manager)
- **No POSIX ownership/permissions/symlinks/journaling** — never rely on them
  for workspace files. App state that needs permissions lives on `ADWIN_SYSTEM`.
- **Atomic writes:** write to a temp file on the same partition, `fsync`, then
  rename into place, so a crash never leaves a half-written output.
- **Safe filenames:** strip characters exFAT/Windows reject (`<>:"/\|?*`,
  control chars, trailing dot/space); avoid reserved names (`CON`, `NUL`, …).
- **No plaintext secrets** on the shared partition (keys/passwords stay on
  `ADWIN_SYSTEM`, out of the Windows-visible area).
- **Unavailable / read-only detection:** if the workspace is missing, not
  mounted, or read-only, the app reports it clearly and blocks large writes
  rather than silently writing to the system partition.
- **Unsafe removal:** exFAT has no journal; always eject safely. Recovery steps
  in [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Separation guarantees
- User content (`ADWIN_WORKSPACE`) ⟂ system (`ADWIN_BOOT`/`ADWIN_SYSTEM`) ⟂
  models (`ADWIN_MODELS`).
- Updates target `ADWIN_SYSTEM`/`ADWIN_BOOT` only; the installer/updater refuses
  any operation whose target resolves to the workspace partition.
- The host computer's internal drives are **out of scope** for every disk
  operation (see [INSTALLATION_GUIDE.md](../INSTALLATION_GUIDE.md) §B and the
  safety rules).
