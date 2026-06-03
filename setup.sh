#!/usr/bin/env bash
# sci_paper_llm — Samuel Adone (GitHub: RebornX10) — MIT
set -euo pipefail

cd "$(dirname "$0")"

echo "==> Checking pipenv"
if ! command -v pipenv >/dev/null 2>&1; then
  echo "Installing pipenv"
  python3 -m pip install --user pipenv
fi

echo "==> Installing dependencies"
pipenv install --dev

echo "==> Checking Ollama"
if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama is not installed. Install it from https://ollama.com, then re-run."
else
  if ! curl -s --max-time 3 http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "Ollama is installed but not running. Start it with: ollama serve"
  fi
  if ! ollama list 2>/dev/null | grep -q .; then
    echo "No model found. Pulling llama3.2"
    ollama pull llama3.2
  fi
fi

echo
echo "Setup complete. Edit config.yaml as needed, then run:"
echo "  pipenv run start"
