#!/usr/bin/env bash
# sci_paper_llm — Samuel Adone (GitHub: RebornX10) — MIT
set -euo pipefail

cd "$(dirname "$0")"

VENV=".venv"
PY="$VENV/bin/python"

if [ ! -x "$PY" ]; then
  echo "==> Creating virtualenv in $VENV"
  python3 -m venv "$VENV"
fi

if ! "$PY" -c "import django, requests, fitz, pandas, yaml, pyarrow" >/dev/null 2>&1; then
  echo "==> Installing dependencies"
  "$PY" -m pip install --quiet --upgrade pip
  "$PY" -m pip install --quiet django requests pymupdf pandas pyarrow pyyaml anthropic
fi

exec "$PY" main.py "$@"
