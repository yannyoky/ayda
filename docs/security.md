# Secrets and leak checks

English · [Русский](ru/security.md)

Secrets live only in environment variables (`.env` on the server, GitHub Actions secrets in CI). They never go into the repo. Three layers catch a mistake.

## 1. gitleaks in CI

The `Secrets` workflow (`.github/workflows/secrets.yml`) runs [gitleaks](https://github.com/gitleaks/gitleaks) on every pull request and every push to `main`. It scans the whole git history, not only the new commits, and fails the check if it finds anything that looks like a key, token or password. Findings are printed redacted.

## 2. Local pre-commit hook

The hook stops a commit before it leaves your machine. Install it once per clone (Windows PowerShell, macOS and Linux alike):

```powershell
uv tool install pre-commit
pre-commit install
```

From then on every `git commit` scans the staged changes. The first run downloads and builds gitleaks, which takes a minute. To scan the whole working tree by hand:

```powershell
pre-commit run gitleaks --all-files
```

If you already have the gitleaks binary (`winget install Gitleaks.Gitleaks`), `gitleaks git .` scans the history the same way CI does.

## 3. GitHub secret scanning and push protection

GitHub checks pushes against the token formats of known providers (Telegram, Cloudflare, Groq, AWS-style S3 keys and many more). For a public repository it is free. To turn it on:

1. Open the repository on GitHub, then **Settings**.
2. In the left menu open **Advanced Security** (on older layouts: **Code security and analysis**).
3. Under **Secret Protection** (or **Secret scanning**) press **Enable**.
4. Right below, enable **Push protection**. GitHub then rejects a `git push` that contains a recognised secret, and tells you the file and line.
5. Optional on the same page: **Private vulnerability reporting**, so that people can report a security issue without opening a public issue.

Alerts appear under **Security → Secret scanning**.

## False positives

A fake value that has to stay in the code (a test fixture, an example from provider docs) gets a `# gitleaks:allow` comment on the same line. A finding in an old commit that cannot be changed goes into `.gitleaksignore` as its fingerprint (`commit:file:rule:line`, gitleaks prints it). Never allow a real secret this way.

## The Telegram bot token

The production bot's token is a master key: whoever knows it can sign Telegram `initData` for any user and sign in to any account. It lives only in `/opt/ayda/.env` on the server and in the protected `production` environment, never in repository-level secrets, which every workflow on `main` can read. The weekly Live checks use a separate test bot (`TELEGRAM_TEST_BOT_TOKEN`; without it the Telegram check is skipped).

If the token may have leaked: in @BotFather send `/revoke` and pick the bot, put the new token into `TELEGRAM_BOT_TOKEN` in `/opt/ayda/.env` (and the `production` environment, if it is there), and run the Deploy workflow. The old token stops working at once, so every `initData` signed with it is rejected. Sessions issued before stay valid; if accounts may have been entered, end them all: put a new `AUTH_TOKEN_SECRET` into `.env` (it signs access tokens) and revoke the refresh tokens:

```sh
docker compose -f docker-compose.prod.yml exec postgres psql -U ayda -d ayda \
  -c "update auth.refresh_tokens set revoked_at = now() where revoked_at is null"
```

Everyone then signs in again.

## If a secret did leak

1. Revoke or rotate the secret at the provider first (BotFather `/revoke`, Cloudflare API tokens, Beget S3 keys, and so on). Once a secret is pushed to a public repo, treat it as known to everyone, even if the commit is removed later.
2. Put the new value into `/opt/ayda/.env` on the server or into the GitHub Actions secret, and restart the affected containers.
3. Remove the value from the code in a normal commit. Rewriting history is optional and does not replace step 1.
