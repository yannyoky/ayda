FROM python:3.13-slim
# pg_dump / pg_restore for the daily backup job (a newer client dumps an older server).
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH"
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY . .
RUN uv sync --locked --no-dev
ARG APP_RELEASE=""
ENV APP_RELEASE=$APP_RELEASE
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn ayda.main:app --host 0.0.0.0 --port 8000"]
