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

# Backend tests need PostgreSQL with PostGIS; the cloud image ships PostgreSQL 16 without it.
if [ -f backend/pyproject.toml ] && command -v pg_ctlcluster >/dev/null 2>&1; then
  if [ ! -f /usr/share/postgresql/16/extension/postgis.control ]; then
    apt-get update -qq >/dev/null
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
      postgresql-16-postgis-3 postgresql-16-pgvector >/dev/null
  fi
  pg_ctlcluster 16 main start 2>/dev/null || true
  su postgres -c "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='ayda'\"" | grep -q 1 \
    || su postgres -c "psql -qc \"CREATE ROLE ayda LOGIN SUPERUSER PASSWORD 'ayda'\""
  for db in ayda ayda_test; do
    su postgres -c "psql -tAc \"SELECT 1 FROM pg_database WHERE datname='$db'\"" | grep -q 1 \
      || su postgres -c "createdb -O ayda $db"
  done
fi

if [ -f miniapp/package.json ]; then
  (cd miniapp && npm install --no-audit --no-fund)
fi
