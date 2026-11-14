#!/usr/bin/env bash
# TITAN AI — partition the external SSD (CONFIRMATION-GATED, Linux).
#
# SAFETY (brief §12): this script is DRY-RUN by default. It never partitions a
# disk automatically, refuses the running system disk and any non-USB device,
# identifies the target by MODEL + SIZE + BUS (never serial), shows the plan and
# exactly what will be erased, requires you to type the device path and YES, and
# re-verifies the device immediately before writing. It NEVER touches internal
# drives. Test with a loopback image before using a real disk.
#
# Usage:
#   sudo bash partition_ssd.sh --device /dev/sdX            # dry-run (default)
#   sudo bash partition_ssd.sh --device /dev/sdX --apply    # actually write (prompts)
set -euo pipefail

DEV=""
APPLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --device) DEV="$2"; shift 2 ;;
    --apply)  APPLY=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

die() { echo "REFUSED: $*" >&2; exit 1; }
[ -n "$DEV" ] || die "no --device given"
[ -b "$DEV" ] || die "$DEV is not a block device"

for tool in lsblk sgdisk mkfs.vfat mkfs.ext4 mkfs.exfat findmnt; do
  command -v "$tool" >/dev/null 2>&1 || die "required tool missing: $tool"
done

NAME="$(basename "$DEV")"
MODEL="$(lsblk -dno MODEL "$DEV" | xargs)"
SIZE_BYTES="$(blockdev --getsize64 "$DEV")"
SIZE_GIB=$(( SIZE_BYTES / 1024 / 1024 / 1024 ))
BUS="$(lsblk -dno TRAN "$DEV" | xargs)"

# Refuse the running system disk.
ROOT_SRC="$(findmnt -no SOURCE / || true)"
ROOT_DISK="$(lsblk -no PKNAME "$ROOT_SRC" 2>/dev/null | head -n1 || true)"
[ "$NAME" = "${ROOT_DISK:-__none__}" ] && die "$DEV hosts the running system (/)"

# Refuse non-USB (the TITAN SSD is external USB).
[ "$BUS" = "usb" ] || die "$DEV bus is '${BUS:-unknown}', not usb"

# Size sanity (warn, don't hard-fail — operator confirms).
if [ "$SIZE_GIB" -lt 100 ] || [ "$SIZE_GIB" -gt 140 ]; then
  echo "WARNING: $DEV is ${SIZE_GIB} GiB, outside the expected 128 GB window."
fi

# Plan (GiB): fixed EFI/BOOT/SYSTEM/MODELS; WORKSPACE = rest - reserve.
ESP=1; BOOT=21; SYSTEM=14; MODELS=23
RESERVE=$(( SIZE_GIB / 20 )); [ "$RESERVE" -lt 2 ] && RESERVE=2
WORKSPACE=$(( SIZE_GIB - ESP - BOOT - SYSTEM - MODELS - RESERVE ))
[ "$WORKSPACE" -lt 10 ] && die "disk too small for a safe TITAN layout"

cat <<EOF

TITAN AI — proposed partition plan for: $DEV
  Model : ${MODEL:-unknown}
  Size  : ${SIZE_GIB} GiB   Bus: ${BUS}   (serial NOT trusted)

  #  LABEL            FS      SIZE
  1  TITAN_EFI        FAT32   ${ESP} GiB
  2  TITAN_BOOT       ext4    ${BOOT} GiB
  3  TITAN_SYSTEM     ext4    ${SYSTEM} GiB
  4  TITAN_MODELS     ext4    ${MODELS} GiB
  5  TITAN_WORKSPACE  exFAT   ${WORKSPACE} GiB   (Windows-visible)
     (reserve/free)           ${RESERVE} GiB

  *** ALL EXISTING DATA ON $DEV WILL BE ERASED ***
EOF

print_commands() {
  cat <<EOF
  # (commands that would run)
  sgdisk --zap-all "$DEV"
  sgdisk -n1:0:+${ESP}GiB     -t1:EF00 -c1:TITAN_EFI "$DEV"
  sgdisk -n2:0:+${BOOT}GiB    -t2:8300 -c2:TITAN_BOOT "$DEV"
  sgdisk -n3:0:+${SYSTEM}GiB  -t3:8300 -c3:TITAN_SYSTEM "$DEV"
  sgdisk -n4:0:+${MODELS}GiB  -t4:8300 -c4:TITAN_MODELS "$DEV"
  sgdisk -n5:0:+${WORKSPACE}GiB -t5:0700 -c5:TITAN_WORKSPACE "$DEV"
  mkfs.vfat  -F32 -n TITAN_EFI       ${DEV}1
  mkfs.ext4  -L TITAN_BOOT           ${DEV}2
  mkfs.ext4  -L TITAN_SYSTEM         ${DEV}3
  mkfs.ext4  -L TITAN_MODELS         ${DEV}4
  mkfs.exfat -n TITAN_WORKSPACE      ${DEV}5
EOF
}

if [ "$APPLY" -ne 1 ]; then
  echo
  echo "DRY-RUN (no changes made). Re-run with --apply to write."
  print_commands
  exit 0
fi

echo
echo "To proceed, type the device path again:"
read -r CONFIRM_DEV
[ "$CONFIRM_DEV" = "$DEV" ] || die "device confirmation did not match"
echo "Type YES (uppercase) to ERASE $DEV and partition it:"
read -r CONFIRM_YES
[ "$CONFIRM_YES" = "YES" ] || die "not confirmed"

# Re-verify immediately before writing (device could have changed).
NOW_MODEL="$(lsblk -dno MODEL "$DEV" | xargs)"
NOW_BUS="$(lsblk -dno TRAN "$DEV" | xargs)"
[ "$NOW_MODEL" = "$MODEL" ] && [ "$NOW_BUS" = "usb" ] || die "device changed since the plan was shown — aborting"
[ "$NAME" = "${ROOT_DISK:-__none__}" ] && die "device now resolves to the system disk — aborting"

echo "Partitioning $DEV ..."
sgdisk --zap-all "$DEV"
sgdisk -n1:0:+${ESP}GiB     -t1:EF00 -c1:TITAN_EFI "$DEV"
sgdisk -n2:0:+${BOOT}GiB    -t2:8300 -c2:TITAN_BOOT "$DEV"
sgdisk -n3:0:+${SYSTEM}GiB  -t3:8300 -c3:TITAN_SYSTEM "$DEV"
sgdisk -n4:0:+${MODELS}GiB  -t4:8300 -c4:TITAN_MODELS "$DEV"
sgdisk -n5:0:+${WORKSPACE}GiB -t5:0700 -c5:TITAN_WORKSPACE "$DEV"
partprobe "$DEV" || true
mkfs.vfat  -F32 -n TITAN_EFI       "${DEV}1"
mkfs.ext4  -F -L TITAN_BOOT        "${DEV}2"
mkfs.ext4  -F -L TITAN_SYSTEM      "${DEV}3"
mkfs.ext4  -F -L TITAN_MODELS      "${DEV}4"
mkfs.exfat -n TITAN_WORKSPACE      "${DEV}5"
echo "Done. TITAN_WORKSPACE (exFAT) is readable from Windows and Linux."
