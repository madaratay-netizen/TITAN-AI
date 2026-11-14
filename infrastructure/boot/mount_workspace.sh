#!/usr/bin/env bash
# TITAN AI — mount the persistent partitions and verify the workspace (Linux).
# Mounts by LABEL (never by a guessed /dev name). Creates the workspace folder
# structure if missing. Read/verify only — it never formats anything.
set -euo pipefail

ws_dir="/workspace"
sys_dir="/opt/titan"
models_dir="/opt/titan/models"

mount_label() {
  local label="$1" target="$2" opts="${3:-}"
  local dev; dev="$(blkid -L "$label" 2>/dev/null || true)"
  if [ -z "$dev" ]; then
    echo "WARNING: partition labelled $label not found — skipping $target"
    return 0
  fi
  mkdir -p "$target"
  if mountpoint -q "$target"; then
    echo "$label already mounted at $target"
  else
    # shellcheck disable=SC2086
    mount ${opts:+-o $opts} "$dev" "$target" && echo "mounted $label -> $target"
  fi
}

mount_label TITAN_SYSTEM    "$sys_dir"
mount_label TITAN_MODELS    "$models_dir"
# exFAT: no POSIX perms; give everyone rw via mount options.
mount_label TITAN_WORKSPACE "$ws_dir" "uid=1000,gid=1000,umask=000"

if mountpoint -q "$ws_dir"; then
  for d in Images Videos Audio Documents Code Projects AI_Conversations \
           Exports Imports Backups User_Settings; do
    mkdir -p "$ws_dir/$d"
  done
  echo "TITAN_WORKSPACE ready at $ws_dir"
else
  echo "ERROR: TITAN_WORKSPACE is not mounted — outputs cannot be saved." >&2
  exit 1
fi
