# LLM provider eval

Compares free LLM providers on the two assistant tasks of the MVP (issue #23, `docs/prd.md` "AI assistant"):

1. **parse_checkin**: Russian free-text check-in to tasks, busy windows and flags.
2. **rank_pool**: candidates picked by code plus an anonymized profile to 5-7 ids with a "why you" line.

Inputs are fake: 24 profiles in `data/profiles.json` (busy day, tired, rain, frost, empty text, typos, slang, mixed English, prompt injection, illness) and a 40-quest sample catalog in `data/catalog.json`. Each answer is validated by the same kind of Pydantic schema the backend will use, with one retry.

Run from `backend/` (keys in the environment, see `providers.toml`):

```sh
uv run python evals/llm/run_eval.py --providers groq-llama70b,zai-glm47flash --out evals/llm/results
```

Output: `results/rows.jsonl` (every answer and check) and `results/summary.md`.

Metrics per provider: valid JSON on parse and rank, first-try validity, task recall against expected tasks, free-evening detection, valid candidate ids, a rest quest when tired, goal match in the top 3, Russian "why" lines, no long outdoor quests in bad weather, safety (injection ignored, no banned topics), latency p50/p95. Russian phrasing quality is also read by hand on a sample.

Not run in CI: it needs network and keys and costs free-tier quota.
