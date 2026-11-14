#!/usr/bin/env bash
# TITAN AI — build the Live image (reviewed template, run on a DEV BOX only).
#
# Produces a reproducible Ubuntu 24.04 Live image (read-only SquashFS base +
# TITAN baked in) that boots from the SSD. This runs on a development machine or
# VM and writes ONLY to ./build — it never touches the user's SSD or any disk.
# After building, flash the image artifacts onto TITAN_BOOT and install GRUB to
# TITAN_EFI with the (separate) confirmation-gated installer.
set -euo pipefail

BUILD_DIR="${1:-./build}"
DIST="noble"            # Ubuntu 24.04 LTS
ARCH="amd64"

for tool in lb debootstrap mksquashfs; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "Missing '$tool'. Install with: sudo apt-get install live-build debootstrap squashfs-tools"
    exit 1; }
done

mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

# 1. Configure a minimal live image (UEFI, systemd-boot/GRUB, XFCE desktop).
lb config \
  --distribution "$DIST" \
  --architecture "$ARCH" \
  --binary-images iso-hybrid \
  --debian-installer none \
  --bootappend-live "boot=live components quiet splash persistence persistence-label=TITAN_SYSTEM"

# 2. Package selection kept lightweight for a 128 GB SSD.
mkdir -p config/package-lists
cat > config/package-lists/titan.list.chroot <<'PKGS'
xfce4 xfce4-terminal network-manager
python3 python3-venv python3-pip
ffmpeg exfatprogs
PKGS

# 3. Bake TITAN into the image under /opt/titan (copied at build time).
mkdir -p config/includes.chroot/opt/titan
echo "# TITAN AI app is copied here during the image build."     \
     > config/includes.chroot/opt/titan/README.txt

# 4. Autostart the backend + dashboard on login (systemd user service).
mkdir -p config/includes.chroot/etc/systemd/system
cat > config/includes.chroot/etc/systemd/system/titan.service <<'UNIT'
[Unit]
Description=TITAN AI backend (loopback only)
After=network.target
[Service]
ExecStart=/opt/titan/.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8077
WorkingDirectory=/opt/titan
Restart=on-failure
[Install]
WantedBy=multi-user.target
UNIT

# 5. Build. Output: live-image-amd64.hybrid.iso + filesystem.squashfs in ./
echo "Building Live image (this takes a while)..."
sudo lb build

echo "Done. Artifacts are in $BUILD_DIR (ISO + SquashFS)."
echo "Next: flash onto TITAN_BOOT and install GRUB to TITAN_EFI with the"
echo "confirmation-gated installer. Never write to an internal disk."
