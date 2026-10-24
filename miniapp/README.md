# miniapp

Telegram Mini App, the first Ayda client: React 19, TypeScript, Vite, Tailwind CSS v4, TanStack Query, React Router (memory routing).

## Run

```sh
cd miniapp
npm install
npm run dev        # http://localhost:5173, /api is proxied to the backend at http://localhost:8000
```

Outside Telegram the app runs as a plain web page: the Telegram bridge (`src/telegram/webapp.ts`) turns into no-ops.

### Without a backend

```sh
npm run dev:mock   # the whole API is served in the browser by MSW from src/mocks
```

The mock implements every endpoint of `contracts/openapi.yaml` over an in-memory store (`src/mocks/db.ts`) with the PRD rules (3 taken quests, 5 replacements, scoring, streaks). It starts as a brand-new user (consent, onboarding); open `/?returning` to start as an onboarded user with friends and a streak. Tests use the same handlers through `msw/node`.

## Launch flow

`src/app/Bootstrap.tsx`: sign in with Telegram initData (US-01, token kept in memory only, re-sign-in on 401) → consent to personal data processing (152-FZ) → onboarding (US-02) → the app.

## Checks (same as CI)

```sh
npm run lint       # eslint, tsc, and a check that the generated API client matches the contract
npm test           # vitest + Testing Library
npm run build
```

## End-to-end tests

`e2e/` drives the built app in Chromium (Playwright, phone viewport) against the real backend and database, not the mock: Telegram sign-in → consent → onboarding → check-in → take a quest → complete it → the post in the feed. `e2e/telegram.ts` replaces Telegram's bridge script with a stub carrying initData signed by a test bot token, so the backend's real signature check runs. CI job `e2e` starts the backend without an LLM key, so the pool comes from code.

Locally: PostgreSQL with PostGIS (`docker compose up -d postgres` from the repository root) and the backend on port 8000 with the same test token, then:

```sh
# backend/
createdb -h localhost -U ayda ayda_e2e   # once
export DATABASE_URL=postgresql+asyncpg://ayda:ayda@localhost:5432/ayda_e2e TELEGRAM_BOT_TOKEN=123456:E2E-TOKEN ENVIRONMENT=test
uv run alembic upgrade head && uv run uvicorn ayda.main:app --port 8000

# miniapp/
npx playwright install chromium   # once
npm run e2e                       # builds the app and serves it with vite preview on :4173
```

Each run signs in as a new Telegram user, so the database does not need resetting.

## API client

`src/api/schema.gen.ts` is generated from `contracts/openapi.yaml` (ADR 0004) and never edited by hand:

```sh
npm run generate:api
```

Calls go through `api` from `src/api/client.ts` (openapi-fetch, typed by the contract) and `unwrap`, which throws `ApiError` with the RFC 9457 problem.

## Layout

| Path | What |
| --- | --- |
| `src/app/` | app shell, router, tab bar, theme provider, query client |
| `src/screens/` | one component per screen |
| `src/ui/` | design primitives and icons |
| `src/i18n/` | Russian UI strings and formatters; every user-facing string lives here |
| `src/telegram/` | typed wrapper over `window.Telegram.WebApp` |
| `src/api/` | generated schema, the API client and TanStack Query hooks (`queries.ts`) |
| `src/features/` | feature components shared by screens (onboarding, profile editors, …) |
| `src/mocks/` | MSW handlers and the in-memory mock backend |

Design tokens (Graphite and Plum) are CSS variables in `src/styles.css`, taken from `docs/design/themes.md`; Tailwind utilities like `bg-surface`, `text-muted`, `rounded-card` read them, so `data-theme="plum"` on `<html>` re-themes everything.
