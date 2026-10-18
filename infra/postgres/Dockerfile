# PostgreSQL 16 with PostGIS (base image) and pgvector (Debian package from PGDG).
FROM postgis/postgis:16-3.6
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/*
