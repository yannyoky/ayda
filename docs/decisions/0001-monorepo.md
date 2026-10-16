# 0001. Monorepo

## Context
Ayda has a backend, an AI service, a Telegram Mini App and two native clients that share one API contract. One person builds it with Claude.

## Decision
Keep every component in one repository with top-level folders per component and a shared `contracts/` OpenAPI spec.

## Consequences
One history and one CI for all parts; CI jobs are filtered by path so unrelated parts are not rebuilt. Repository-level Claude settings (`.claude/settings.json`) apply to every thread.
