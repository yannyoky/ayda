# Ayda: notes for Claude

- Owner: Alexander (GitHub yannyoky). Chat in Russian; code, commits, PRs and code comments in English.
- Monorepo, see README.md for layout. One task = one small PR linked to an issue, with tests.
- Source of truth: docs/prd.md, docs/roadmap.md, docs/architecture.md, docs/decisions/ (ADR: context, decision, consequences). A new architectural decision = a new ADR.
- Design: docs/design/themes.md (tokens for the two themes, Graphite and Plum). Layout: bento widgets, Unbounded + Manrope.
- Decided stack: Telegram Mini App first, then native Kotlin + Swift; backend C# ASP.NET + SignalR + PostgreSQL; AI service in Python with pluggable FREE LLM providers (no paid APIs). LLM only ranks and phrases candidates selected by code, output validated against a JSON schema.
- Log quest events from day one (append-only `events` table).
- Personal data (location, photos, habits) is minimal and never logged in raw form; 152-FZ applies (Russian users' data stored in Russia).
- Secrets only from environment variables, never in the repo.
- Before pushing run the checks for the component you touched:
  - backend: `dotnet format --verify-no-changes && dotnet test`
  - ai: `ruff check . && pytest`
  - miniapp: `npm run lint && npm test`
- Production deploys, data deletion and messages outside the project only after the owner's explicit "yes".
