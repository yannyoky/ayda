# Ayda

Social quest app: every morning an AI assistant turns your day into a few quests (a walk, a workout, an hour on your own project, a local event), and in the evening you show friends what you did. Friends ladder, streaks, proofs feed, co-op quests at a distance.

## Repository layout

| Path | What | Stack |
| --- | --- | --- |
| `backend/` | modular monolith: API, AI assistant, Telegram bot, background jobs | Python, FastAPI, PostgreSQL (PostGIS, pgvector), Centrifugo, free LLM providers |
| `miniapp/` | Telegram Mini App (first client) | React, TypeScript, Vite |
| `android/` | native Android client | Kotlin Multiplatform shared code, Jetpack Compose |
| `ios/` | native iOS client | Kotlin Multiplatform shared code, SwiftUI |
| `contracts/` | OpenAPI spec shared by all clients | OpenAPI 3.1 |
| `docs/` | PRD, roadmap, architecture, ADRs, design | Markdown |

Stack and architecture: `docs/decisions/0002-tech-stack.md`, `docs/decisions/0003-modular-monolith.md`.

Each component gets its own README when its code lands.
