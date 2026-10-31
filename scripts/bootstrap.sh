#!/usr/bin/env bash
# Create the virtualenv, install dependencies and build the indexes.
# Usage: scripts/bootstrap.sh            (from the project root)
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3.11}"
command -v "$PYTHON" >/dev/null || { echo "Python 3.11 not found (set PYTHON=...)"; exit 1; }

[ -d .venv ] || "$PYTHON" -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements-dev.txt

[ -f .env ] || { cp .env.example .env; echo "Created .env from .env.example - fill in API_KEYS and an LLM key."; }

# Parses, chunks, embeds (downloads the models on first run) and writes data/.
.venv/bin/python -m app.retrieval.index --rebuild
echo "Bootstrap complete."
