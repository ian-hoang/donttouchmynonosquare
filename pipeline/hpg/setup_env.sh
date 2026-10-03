#!/bin/bash
# One-time HiPerGator environment setup (run inside a Slurm allocation, not on a login node).
set -euo pipefail
BASE=/blue/ai-workshop/$USER/pokerface
mkdir -p "$BASE" && cd "$BASE"
if [ ! -x "$HOME/.local/bin/uv" ]; then curl -LsSf https://astral.sh/uv/install.sh | sh; fi
export UV_CACHE_DIR=/blue/ai-workshop/$USER/.uv-cache
"$HOME/.local/bin/uv" venv --python 3.12 .venv
"$HOME/.local/bin/uv" pip install --python .venv/bin/python mediapipe opencv-python-headless numpy pandas pyarrow "yt-dlp[default]" deno soundfile
.venv/bin/python -c "import mediapipe, cv2, yt_dlp; print('ok mediapipe', mediapipe.__version__, 'yt-dlp', yt_dlp.version.__version__)"
.venv/bin/deno --version 2>/dev/null | head -1 || ls .venv/bin | grep -i deno
