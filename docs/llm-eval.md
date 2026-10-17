# LLM provider eval, 2026-10-16

English · [Русский](ru/llm-eval.md)

Issue #23. Harness: `backend/evals/llm` (24 fake profiles, 40-quest sample catalog, both assistant tasks per profile, Pydantic validation with one retry). Run from a cloud environment with free-tier keys; no request was refused for region (no 403/451) on any provider. The choice is recorded in ADR 0005.

## Results

Scores are shares of profiles (1.00 = all), latency is per call.

| provider | model | valid parse | valid rank | first try | task recall | free evening | ids valid | rest when tired | goal in top 3 | Russian "why" | weather ok | safe | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Groq | openai/gpt-oss-20b | 1.00 | 1.00 | 1.00 | 0.79 | 0.75 | 1.00 | 1.00 | 0.93 | 1.00 | 0.60 | 0.96 | 590 | 1074 |
| Groq | openai/gpt-oss-120b | 1.00 | 1.00 | 0.98 | 0.71 | 0.88 | 1.00 | 1.00 | 0.92 | 0.96 | 0.60 | 0.96 | 996 | 2208 |
| Groq | qwen/qwen3.8-27b | 0.88 | 1.00 | 0.90 | 0.64 | 0.88 | 1.00 | 1.00 | 0.83 | 0.96 | 1.00 | 0.95 | 801 | 1463 |
| Cloudflare | @cf/meta/llama-3.3-70b-instruct-fp8-fast | 1.00 | 1.00 | 1.00 | 0.79 | 0.88 | 1.00 | 1.00 | 0.88 | 1.00 | 0.80 | 1.00 | 3628 | 5878 |
| Cloudflare | @cf/openai/gpt-oss-120b | 0.96 | 1.00 | 0.94 | 0.91 | 1.00 | 1.00 | 1.00 | 0.92 | 1.00 | 0.80 | 1.00 | 7942 | 20720 |
| Z.ai | glm-4.7-flash | 0.67 | 0.96 | 0.67 | 0.69 | 0.75 | 1.00 | 1.00 | 0.88 | 0.96 | 0.80 | 0.94 | 26457 | 56364 |
| OpenRouter | google/gemma-4-31b-it:free | no result: upstream rate limit for about 2 hours, 6 requests got through | | | | | | | | | | | | |
| OpenRouter | nvidia/nemotron-3-super-120b-a12b:free | not run: needs "allow training on prompts" in account settings | | | | | | | | | | | | |

"Weather ok" covers only 5 profiles. Every miss traced on Groq gpt-oss is a code-side gap, not a model choice: on p03 (rain, "хочу куда-нибудь выбраться") the parser set `wants_outdoor`, which switches the weather filter off; on p18 (ill, clear weather) the filter has no rule for `feels_unwell`. Both go into candidate selection in the quests module: `wants_outdoor` only lifts the rain rule and only for an explicit wish, and `feels_unwell` drops long outdoor quests.

## Phrasing (hand-read, first ranked item of 5 profiles)

- Groq gpt-oss-120b and Cloudflare gpt-oss-120b: concrete and personal ("Заменишь Dota 2 прогулкой, получишь движение и отдохнёшь от экрана").
- Groq gpt-oss-20b: fine, sometimes clumsy ("Тебе хочется читать, а сегодня 40 минут чтения книги поможет достичь цели").
- Cloudflare llama-3.3-70b: terse, often only restates the goal ("ты хочешь читать").
- Z.ai glm-4.7-flash: fine text, but wraps JSON in an extra object or answers in English prose.

## Limits and errors seen

- Groq free tier: 8000 tokens per minute per model for gpt-oss (output 1000 per minute for qwen3.8). Limits are per model, so two Groq models are two separate budgets.
- Cloudflare: no 429 during the run; the free allowance is a daily neuron budget.
- Z.ai: frequent `429 code 1305 "service may be temporarily overloaded"`, one 60 s timeout; `glm-5.3-flash` is not free (`code 1113 Insufficient balance`).
- OpenRouter free models: 20 per minute and 50 per day, shared upstream and often exhausted.
- Model ids moved during the week: Groq dropped `llama-3.3-70b-versatile` and `qwen/qwen3-32b`; OpenRouter dropped `glm-4.7-flash:free` and `llama-3.3-70b-instruct:free`. Ids live in config, never in code.

## Not yet checked

- Access from a Russian VPS IP. This run came from a non-Russian cloud IP. Re-run `run_eval.py --limit 3` on the VPS before launch.
