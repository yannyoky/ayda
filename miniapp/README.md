# miniapp

Telegram Mini App, the first Ayda client: React 19, TypeScript, Vite, Tailwind CSS v4, TanStack Query, React Router (memory routing).

## Run

```sh
cd miniapp
npm install
npm run dev        # http://localhost:5173, /api is proxied to the backend at http://localhost:8000
```

Outside Telegram the app runs as a plain web page: the Telegram bridge (`src/telegram/webapp.ts`) turns into no-ops.

## Checks (same as CI)

```sh
npm run lint       # eslint, tsc, and a check that the generated API client matches the contract
npm test           # vitest + Testing Library
npm run build
```

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
| `src/api/` | generated schema and the API client |

Design tokens (Graphite and Plum) are CSS variables in `src/styles.css`, taken from `docs/design/themes.md`; Tailwind utilities like `bg-surface`, `text-muted`, `rounded-card` read them, so `data-theme="plum"` on `<html>` re-themes everything.
