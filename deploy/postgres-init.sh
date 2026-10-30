#!/bin/sh
# Runs once, when the data volume is created: a separate database and role for GlitchTip.
set -eu
# The password goes in as a psql variable, quoted by psql itself, so any character is safe.
psql -v ON_ERROR_STOP=1 -v pw="$GLITCHTIP_DB_PASSWORD" \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
CREATE ROLE glitchtip LOGIN PASSWORD :'pw';
CREATE DATABASE glitchtip OWNER glitchtip;
SQL
