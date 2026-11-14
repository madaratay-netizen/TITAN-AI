#!/usr/bin/env bash
# ADWIN OS — optional ComfyUI + SD 1.5 setup (Linux), for AI image generation
# and AI scene images in the Video Studio. Run AFTER install_on_ubuntu.sh.
# Needs a CUDA-capable GPU for reasonable speed (works on ~4 GB VRAM with
# --lowvram). ~7 GB of downloads (PyTorch + model). No disk operations.
set -euo pipefail

COMFY_DIR="${COMFY_DIR:-$HOME/ComfyUI}"
MODEL_URL="https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5/resolve/main/v1-5-pruned-emaonly.safetensors"

say() { echo -e "\n\033[1;36m==> $*\033[0m"; }

say "1/4  Getting ComfyUI"
if [ ! -d "$COMFY_DIR/.git" ]; then
  git clone https://github.com/comfyanonymous/ComfyUI.git "$COMFY_DIR"
fi
cd "$COMFY_DIR"

say "2/4  Python env + PyTorch (CUDA) + requirements  (big download)"
python3 -m venv venv
./venv/bin/python -m pip install --upgrade pip
# Recent torch so the latest ComfyUI (comfy_kitchen) works; cu124 wheels.
./venv/bin/pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
./venv/bin/pip install -r requirements.txt

say "3/4  Downloading SD 1.5 checkpoint (~4 GB, resumable)"
mkdir -p models/checkpoints
curl -L -C - --retry 10 --retry-delay 5 --retry-all-errors \
  -o models/checkpoints/v1-5-pruned-emaonly.safetensors "$MODEL_URL"

say "4/4  Done"
cat <<EOF

ComfyUI is installed.  Start it (keep it running) with:
   cd "$COMFY_DIR" && ./venv/bin/python main.py --lowvram --port 8188

Then in ADWIN: Image Studio works, and Video Studio "AI scene images"
generates a picture per scene. On a 4 GB GPU use 512x512.
EOF
