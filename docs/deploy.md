# Production

English · [Русский](ru/deploy.md)

One VPS in Russia runs everything with Docker Compose (ADR 0002): Caddy (TLS, the Mini App's static files, reverse proxy), the API, the worker, the bot, PostgreSQL with PostGIS and pgvector, Centrifugo, and GlitchTip for errors. Photos and database backups go to a Russian S3-compatible provider. Files: `deploy/`.

```
Telegram ──▶ Caddy :443 ─┬─ /            Mini App (static, baked into ayda-web)
                         ├─ /api/*       api:8000
                         ├─ /telegram/webhook   bot:8081
                         └─ /connection/*       centrifugo (M2)
             errors.<domain> ──▶ glitchtip:8000
api / worker / bot ──▶ postgres     worker ──▶ S3 (photos, daily pg_dump)
```

## How a release goes out

1. Every push to `main` builds three images and pushes them to GHCR, tagged with the commit sha: `ayda-backend`, `ayda-web` (Mini App + Caddy) and `ayda-postgres`.
2. Production changes only when someone runs **Actions → Deploy → Run workflow**. The `deploy` job waits for a reviewer of the protected `production` environment to approve it, then copies the Compose file to the VPS, pulls the images of that commit and restarts what changed. Migrations run first (`migrate` service); the API starts only after they succeed. The job ends with a health check of `https://<domain>/api/v1/health`.
3. Rollback: run the workflow again with `tag` set to an earlier commit sha of `main`. Migrations are forward-only: roll back freely between commits with the same migrations; across a migration, the older code must still work with the newer schema, or restore a backup taken before it.

Pull requests touching `deploy/` or `infra/` validate the Compose file and build the web image.

## One-time setup (owner)

1. **VPS in Russia**: Ubuntu 26.04 LTS, 2 vCPU, 4 GB RAM, 60 GB SSD and one static public IPv4 is enough for the MVP. Install Docker Engine with the Compose plugin, create a `deploy` user in the `docker` group with an SSH key, open ports 22, 80 and 443 only. `sudo mkdir /opt/ayda && sudo chown deploy /opt/ayda`.
2. **Domain**: an A record for the app (`AYDA_DOMAIN`, e.g. `app.example.ru`) and one for errors (`ERRORS_DOMAIN`, e.g. `errors.example.ru`) pointing to the VPS's IPv4. Do not add AAAA records unless IPv6 is set up on the VPS and in Docker. Caddy gets the certificates itself.
3. **S3 in Russia**: two private buckets (`ayda-media`, `ayda-backups`) and one access key. On the media bucket allow CORS `PUT` and `GET` from `https://<AYDA_DOMAIN>` (the Mini App uploads photos straight to S3 with presigned URLs).
4. **Secrets on the VPS**: copy `deploy/env.prod.example` to `/opt/ayda/.env`, fill it in, `chmod 600`. Random values: `openssl rand -base64 32`. `SENTRY_DSN` is filled after step 7.
5. **GitHub**: Settings → Environments → `production`: required reviewer (the owner), deployment branch `main`. Environment secrets `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY` (private key of the deploy user), `DEPLOY_KNOWN_HOSTS` (`ssh-keyscan <host>`), environment variable `AYDA_DOMAIN`.
6. **First deploy**: run the Deploy workflow and approve it.
7. **GlitchTip**: `docker compose -f docker-compose.prod.yml exec glitchtip ./manage.py createsuperuser`, sign in at `https://<ERRORS_DOMAIN>`, create the organization and the `ayda` project, put its DSN into `SENTRY_DSN` in `.env`, run the Deploy workflow again. User registration is off; events are kept 30 days.
8. **@BotFather**: Bot Settings → Configure Mini App → Main Mini App URL `https://<AYDA_DOMAIN>/`; Menu Button → the same URL. The bot sets its webhook to `https://<AYDA_DOMAIN>/telegram/webhook` with `TELEGRAM_WEBHOOK_SECRET` on start.
9. **LLM providers**: from the VPS, run the eval smoke check (`docs/llm-eval.md`, `--limit 3`) to confirm Groq and Cloudflare answer from a Russian IP. If Groq is blocked, put `cloudflare-llama70b` first in `LLM_PROVIDERS`.
10. **Local events** (M3, ADR 0008): nothing to set up; Timepad and KudaGo need no keys (`TIMEPAD_TOKEN` is optional). The worker loads events once a day after 04:00 Moscow time, and right after the first deploy if that time has passed; `docker compose -f docker-compose.prod.yml logs worker | grep events:` shows the counts per source.
   Venues for meetups (M5, ADR 0011) come from public OpenStreetMap instances and need no key either; `docker compose -f docker-compose.prod.yml logs worker | grep venues:` shows how many cities were loaded. Check that the Russian VPS reaches `overpass-api.de`; if not, list another public instance in `VENUES_OVERPASS_URLS`.
11. **Invite links and the Android app** (optional until the app is released): put the SHA-256 fingerprint of the app's signing certificate into `ANDROID_CERT_SHA256` in `.env` (`AA:BB:...`; Caddy serves it at `/.well-known/assetlinks.json`) and run the Deploy workflow. Invites are then `https://<AYDA_DOMAIN>/i/<code>`: they open the app when it is installed and the verified link is trusted by Android, and send everyone else to the bot (`t.me/<bot>?startapp=<code>`). Old `t.me` links keep working.

## Backups

The worker uploads a `pg_dump` to `BACKUP_BUCKET` every day after 03:30 Moscow time and keeps 14 days (`docs/architecture.md`, "Backups and error tracking"). A failed backup is retried; when it gives up, the error shows up in GlitchTip.

By hand, on the VPS in `/opt/ayda`:

```sh
alias ayda='docker compose -f docker-compose.prod.yml run --rm migrate'
ayda python -m ayda.core.backup list
ayda python -m ayda.core.backup create
```

### Monthly restore check

Restore the latest dump into a scratch database and compare a few counts with production, then drop it:

```sh
docker compose -f docker-compose.prod.yml exec postgres createdb -U ayda ayda_restore_check
ayda python -m ayda.core.backup restore <key> \
  --target-url "postgresql://ayda:<POSTGRES_PASSWORD from .env>@postgres:5432/ayda_restore_check"
docker compose -f docker-compose.prod.yml exec postgres psql -U ayda -d ayda_restore_check \
  -c "select count(*) from auth.users" -c "select max(occurred_at) from analytics.events"
docker compose -f docker-compose.prod.yml exec postgres dropdb -U ayda ayda_restore_check
```

### Disaster recovery

New VPS (steps 1, 4, 6 above), stop `api`, `worker` and `bot`, restore the latest dump into the empty `ayda` database with the same command (`--target-url` pointing to `ayda`), start everything, then re-run account erasure for accounts deleted after the dump was taken (152-FZ: a restore must not bring erased data back).

## Logs

`docker compose -f docker-compose.prod.yml logs -f api worker bot`. Logs stay on the VPS (rotated, 5 × 20 MB per container), Caddy writes no access log, and application logs pass through the redaction filter (`ayda.core.logging`).
