# Ayda: notes for Claude

- Owner: Alexander (GitHub yannyoky). Chat in Russian; code, commits, PRs and code comments in English.
- Monorepo, see README.md for layout. One task = one small PR linked to an issue, with tests.
- Source of truth: docs/prd.md, docs/roadmap.md, docs/architecture.md, docs/decisions/ (ADR: context, decision, consequences). A new architectural decision = a new ADR.
- Docs are kept in two languages: English in docs/, Russian in the mirrored docs/ru/ tree (same file names). Any change to a doc, including a new ADR, updates both versions in the same PR. Code, commands, paths and API names stay untranslated.
- Design: docs/design/themes.md (tokens for the two themes, Graphite and Plum). Layout: bento widgets, Unbounded + Manrope.
- Decided stack (ADR 0002, 0003): backend is a Python FastAPI modular monolith that includes the AI assistant; PostgreSQL + PostGIS + pgvector; Centrifugo for realtime; Telegram Mini App on React + TypeScript first, then Kotlin Multiplatform with Compose (Android) and SwiftUI (iOS). Modules in backend/src/ayda/modules/ never import each other. LLM providers are pluggable and FREE (no paid APIs). LLM only ranks and phrases candidates selected by code, output validated against a JSON schema.
- Log quest events from day one (append-only `events` table).
- Personal data (location, photos, habits) is minimal and never logged in raw form; 152-FZ applies (Russian users' data stored in Russia).
- Secrets only from environment variables, never in the repo.
- Before pushing run the checks for the component you touched:
  - backend: `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run lint-imports && uv run pytest`
  - miniapp: `npm run lint && npm test`
- Production deploys, data deletion and messages outside the project only after the owner's explicit "yes".
