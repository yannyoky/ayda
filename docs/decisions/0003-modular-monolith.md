# 0003. Modular monolith

## Context
One developer, a handful of users at start, and a core loop (check-in, quests, proof, feed, ladder) that touches almost every domain. Microservices would add network calls, distributed transactions and per-service deploys and monitoring without solving a real problem yet.

## Decision
The backend is one deployable application split into domain modules under `backend/src/ayda/modules/`: auth, quests, assistant, events, social, chat, habits, analytics. Each module owns its tables and logic. Modules do not import each other; this is enforced by import-linter in CI. Cross-module work goes through shared application code and domain events (which are also written to the append-only `events` table). The background worker runs the same code with a different entry point. Centrifugo and PostgreSQL are separate infrastructure, not our services.

## Consequences
Simple deploy and transactions across the core loop. A module is extracted into its own service only when its load profile becomes truly different (for example the assistant moving to a GPU host); clear boundaries keep that a move, not a rewrite. The import-linter contract may be relaxed later to allow imports of a module's public API if direct calls prove simpler.
