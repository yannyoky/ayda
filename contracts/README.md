# contracts

`openapi.yaml` is the hand-written OpenAPI 3.1 contract of the Ayda API and the source of truth for every client (ADR 0004). It covers milestones M1-M3 (US-01..US-19 in `docs/prd.md`). Realtime events sent over Centrifugo are described as `RealtimeEvent` (ADR 0007).

Lint (same as CI):

```sh
cd contracts
npx -y @redocly/cli@2.56.1 lint openapi.yaml
```

Rules: `redocly.yaml` (the `recommended` ruleset). Deliberate exceptions live in `.redocly.lint-ignore.yaml`.

Changing the contract: edit `openapi.yaml` in the same PR as the backend change, keep changes backward compatible while clients are released separately, and regenerate clients (Mini App: `npm run generate:api` once the scaffold lands).
