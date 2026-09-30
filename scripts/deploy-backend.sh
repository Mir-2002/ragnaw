#!/usr/bin/env sh
# Upload backend/ to the Hugging Face Space.
#
# `hf upload` stores binary files (data/*.sqlite, *.npy) through Xet automatically; a plain
# git push to the Space would reject them.
#
# Usage:  HF_SPACE=<user>/ragnaw scripts/deploy-backend.sh
# Login:  uvx --from huggingface_hub hf auth login   (or set HF_TOKEN)
set -eu

: "${HF_SPACE:?set HF_SPACE=<user>/ragnaw}"

if command -v uvx >/dev/null 2>&1; then
  UVX="uvx"
else
  UVX="python -m uv tool run"
fi

cd "$(dirname "$0")/../backend"

$UVX --from huggingface_hub hf upload "$HF_SPACE" . . --repo-type=space \
  --exclude ".venv/*" \
  --exclude ".env" \
  --exclude "*__pycache__*" \
  --exclude ".pytest_cache/*" \
  --exclude ".ruff_cache/*" \
  --exclude ".cache/*" \
  --exclude "tests/*" \
  --commit-message "Deploy $(git rev-parse --short HEAD 2>/dev/null || echo local)"
