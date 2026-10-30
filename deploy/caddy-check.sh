#!/usr/bin/env bash
# Starts the production Caddyfile over plain HTTP in Docker and checks a few responses.
# CI runs it on every change under deploy/ (job `caddy`). Locally: bash deploy/caddy-check.sh
set -euo pipefail

IMAGE="${CADDY_IMAGE:-caddy:2-alpine}"
PORT=18080
NAME="ayda-caddy-check-$$"
here="$(cd "$(dirname "$0")" && pwd)"

docker run -d --name "$NAME" -p "$PORT:$PORT" \
  -e AYDA_DOMAIN="http://localhost:$PORT" \
  -e ERRORS_DOMAIN="http://errors.localhost:$PORT" \
  -e ACME_EMAIL=ci@example.invalid \
  -e TELEGRAM_BOT_USERNAME=ayda_test_bot \
  -e ANDROID_CERT_SHA256=00:11 \
  -v "$here/Caddyfile:/etc/caddy/Caddyfile:ro" \
  "$IMAGE" >/dev/null
trap 'docker rm -f "$NAME" >/dev/null' EXIT

for _ in $(seq 1 30); do
  curl -s -o /dev/null "http://localhost:$PORT/.well-known/assetlinks.json" && break
  sleep 1
done

fail() { echo "FAIL: $*"; docker logs "$NAME" | tail -20; exit 1; }

# K1: the /app/* page must not reflect the (decoded) request path.
body="$(curl -s "http://localhost:$PORT/app/x%22%3E%3Cb%3Einjected")"
grep -q 'Открыть Ayda' <<<"$body" || fail "/app/* page not served"
grep -q '<b>' <<<"$body" && fail "/app/* reflects the request path"
grep -q 'injected' <<<"$body" && fail "/app/* reflects the request path"
grep -q 'intent://localhost/app/signed-in#Intent' <<<"$body" || fail "/app/* intent link changed"

# Audit M4: security headers on every response.
headers="$(curl -s -D - -o /dev/null "http://localhost:$PORT/app/signed-in")"
grep -qi "^content-security-policy: script-src 'self' https://telegram.org;" <<<"$headers" \
  || fail "no Content-Security-Policy"
grep -qi "frame-ancestors 'self' https://web.telegram.org" <<<"$headers" || fail "no frame-ancestors"
grep -qi "^strict-transport-security: max-age=31536000; includeSubDomains" <<<"$headers" \
  || fail "no HSTS includeSubDomains"

echo "Caddyfile checks passed"
