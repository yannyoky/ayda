#!/bin/sh
# Runs once, when the data volume is created: a separate database and role for GlitchTip.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE ROLE glitchtip LOGIN PASSWORD '${GLITCHTIP_DB_PASSWORD}';
CREATE DATABASE glitchtip OWNER glitchtip;
SQL
