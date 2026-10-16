# backend

Ayda backend: a FastAPI modular monolith (ADR 0002, 0003). Domain modules live in `src/ayda/modules/` and never import each other.

```sh
uv sync
uv run uvicorn ayda.main:app --reload
```

Checks (same as CI):

```sh
uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run lint-imports && uv run pytest
```
