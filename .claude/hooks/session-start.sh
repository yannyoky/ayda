#!/bin/bash
# Install backend and Mini App dependencies so cloud sessions can run lint and tests.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"

if ! command -v uv >/dev/null 2>&1; then
  python3 -m pip install --quiet uv
fi

if [ -f backend/pyproject.toml ]; then
  (cd backend && uv sync --locked)
  # pyright fetches its Node package on first run; warm it up so the cache is saved
  (cd backend && uv run pyright --version >/dev/null)
fi

if [ -f miniapp/package.json ]; then
  (cd miniapp && npm install --no-audit --no-fund)
fi
