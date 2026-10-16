# Ayda

Social quest app: every morning an AI assistant turns your day into a few quests (a walk, a workout, an hour on your own project, a local event), and in the evening you show friends what you did. Friends ladder, streaks, proofs feed, co-op quests at a distance.

## Repository layout

| Path | What | Stack |
| --- | --- | --- |
| `backend/` | API, realtime, auth via Telegram | C# ASP.NET Core, SignalR, EF Core, PostgreSQL |
| `ai/` | quest generation and ranking | Python, FastAPI, pluggable free LLM providers |
| `miniapp/` | Telegram Mini App (first client) | TypeScript, Vite |
| `android/` | native Android client | Kotlin, Jetpack Compose |
| `ios/` | native iOS client | Swift, SwiftUI |
| `contracts/` | OpenAPI spec shared by all clients | OpenAPI 3.1 |
| `docs/` | PRD, roadmap, architecture, ADRs, design | Markdown |

Each component gets its own README when its code lands.
