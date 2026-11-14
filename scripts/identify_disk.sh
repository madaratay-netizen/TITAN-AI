#!/usr/bin/env bash
# ADWIN OS — external SSD identification (READ-ONLY, Linux).
#
# Lists candidate EXTERNAL/USB block devices so an operator can identify the
# target SSD before any partitioning. This script NEVER writes to any disk.
# It explicitly refuses to treat the running system's disk as a candidate.
set -euo pipefail

echo "ADWIN OS — disk identification (read-only)"
echo "=========================================="

if ! command -v lsblk >/dev/null 2>&1; then
  echo "ERROR: lsblk not found (this script is for Linux targets)." >&2
  exit 1
fi

# Disk that currently hosts root '/', which we must never offer as a target.
root_src="$(findmnt -no SOURCE / 2>/dev/null || true)"
root_disk="$(lsblk -no PKNAME "$root_src" 2>/dev/null || true)"
[ -z "$root_disk" ] && root_disk="$(basename "${root_src%[0-9]*}" 2>/dev/null || true)"

echo "System root is on: ${root_disk:-unknown} (will be EXCLUDED)"
echo
printf '%-10s %-8s %-8s %-28s %s\n' NAME SIZE BUS MODEL NOTE

while read -r name size tran rota type model; do
  [ "$type" = "disk" ] || continue
  if [ "$name" = "$root_disk" ]; then
    note="INTERNAL/SYSTEM — excluded"
  elif [ "$tran" = "usb" ]; then
    note="candidate (USB external)"
  else
    note="NOT usb — review carefully"
  fi
  printf '%-10s %-8s %-8s %-28s %s\n' "$name" "$size" "${tran:-?}" "${model:-?}" "$note"
done < <(lsblk -dno NAME,SIZE,TRAN,ROTA,TYPE,MODEL)

cat <<'EOF'

Next steps (manual, deliberate):
  1. Confirm the candidate is really your external SSD (match SIZE + MODEL).
  2. Back up anything on it — partitioning ERASES it.
  3. Only then run the (separate, confirmation-gated) partition step and type the
     exact device path plus 'YES' when prompted.

This script wrote nothing. No disk was modified.
EOF
