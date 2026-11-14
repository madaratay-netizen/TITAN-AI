#!/usr/bin/env bash
# ADWIN OS — one-command installer for Ubuntu (run AFTER booting the SSD).
#
# Sets up everything needed to run ADWIN on an Ubuntu Live/installed system:
# system packages, the ADWIN repo, a Python venv, Ollama + a small model, the
# workspace, and a desktop launcher. It does NOT touch disks/partitions.
#
# Usage (inside Ubuntu, with internet for this first-time setup):
#   curl -fsSL https://raw.githubusercontent.com/madaratay-netizen/ADWIN-OS/main/scripts/install_on_ubuntu.sh | bash
# or, safer (download, read, then run):
#   wget https://raw.githubusercontent.com/madaratay-netizen/ADWIN-OS/main/scripts/install_on_ubuntu.sh
#   less install_on_ubuntu.sh   # review it
#   bash install_on_ubuntu.sh
set -euo pipefail

REPO_URL="https://github.com/madaratay-netizen/ADWIN-OS.git"
INSTALL_DIR="${ADWIN_DIR:-$HOME/ADWIN-OS}"
PRIMARY_MODEL="qwen3.5:4b"
FALLBACK_MODEL="qwen2.5:3b"
EMBED_MODEL="nomic-embed-text"

say() { echo -e "\n\033[1;36m==> $*\033[0m"; }
warn() { echo -e "\033[1;33m[!] $*\033[0m"; }

say "ADWIN OS installer for Ubuntu"
command -v apt-get >/dev/null 2>&1 || { echo "This installer is for Ubuntu/Debian."; exit 1; }

say "1/6  Installing system packages (needs sudo)"
sudo apt-get update -y
sudo apt-get install -y git python3 python3-venv python3-pip ffmpeg curl ca-certificates exfatprogs

say "2/6  Getting the ADWIN OS code"
if [ -d "$INSTALL_DIR/.git" ]; then
  git -C "$INSTALL_DIR" pull --ff-only || warn "could not update; using existing copy"
else
  git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"

say "3/6  Creating the Python environment"
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt
# Headless browser for the Code Animation Renderer (engineering explainers).
./.venv/bin/python -m playwright install --with-deps chromium || \
  ./.venv/bin/python -m playwright install chromium || true

say "4/6  Installing Ollama (local AI runtime)"
if ! command -v ollama >/dev/null 2>&1; then
  # Official Ollama installer. Review at https://ollama.com/install.sh if you prefer.
  curl -fsSL https://ollama.com/install.sh | sh
fi
# Start the Ollama service in the background if it isn't running.
if ! curl -fsS http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
  (ollama serve >/tmp/ollama.log 2>&1 &)
  sleep 5
fi

say "5/6  Downloading a small local model (first time only)"
MODEL="$PRIMARY_MODEL"
if ! ollama pull "$PRIMARY_MODEL"; then
  warn "'$PRIMARY_MODEL' not available — falling back to '$FALLBACK_MODEL'"
  ollama pull "$FALLBACK_MODEL"
  MODEL="$FALLBACK_MODEL"
  # Keep the app config in sync with the model we actually installed.
  sed -i "s|^default_model = .*|default_model = \"$MODEL\"|" configs/adwin.toml || true
fi
ollama pull "$EMBED_MODEL" || warn "embedding model pull failed (RAG will use the lexical fallback)"

say "6/6  Preparing the workspace + launcher"
./.venv/bin/python - <<'PY'
from core.storage_manager.manager import WorkspaceManager
from backend.app.config import settings
created = WorkspaceManager(settings.workspace).ensure_structure()
print("workspace folders ready:", ", ".join(created) or "all present")
PY

# Desktop launcher (optional; ignored on a server/live session without a desktop).
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/adwin-os.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=ADWIN OS
Comment=Portable offline AI workstation
Exec=bash -c 'cd "$INSTALL_DIR" && bash scripts/run_adwin.sh'
Terminal=true
Categories=Development;Utility;
EOF

cat <<EOF

============================================================
  ✅ ADWIN OS is installed.   Model: $MODEL

  To start it:
     cd "$INSTALL_DIR" && bash scripts/run_adwin.sh

  Then open:  http://127.0.0.1:8077

  (Or launch "ADWIN OS" from the applications menu.)
============================================================
EOF
