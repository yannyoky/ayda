# 0005. Free LLM providers for the assistant

## Context
The assistant makes two calls per morning pool: parse the check-in and rank 5-7 of about 20 code-selected candidates with a "why you" line (PRD, "AI assistant"). Only free providers are allowed, the pool must be ready in 10 s or less, and an LLM outage must not break the loop. ADR 0002 set an in-house adapter over the OpenAI-compatible API with providers switched by config. The eval in `docs/llm-eval.md` compared Groq, Cloudflare Workers AI, Z.ai and OpenRouter free models on 24 fake profiles.

## Decision
Provider chain, tried in order for each call:

1. Groq `openai/gpt-oss-20b` (reasoning effort low): valid JSON on every profile, best or tied on most checks, p95 about 1 s.
2. Groq `openai/gpt-oss-120b` (reasoning effort low): same quality, better phrasing, and a separate per-model rate-limit budget.
3. Cloudflare Workers AI `@cf/meta/llama-3.3-70b-instruct-fp8-fast`: valid JSON on every profile and a different vendor; terser "why" lines, p95 about 6 s.
4. Code only: tasks taken line by line, ranking by goal weights, template "why" lines.

A provider is skipped after a 429, a 5xx, a timeout (4 s for Groq, 8 s for Cloudflare) or a second invalid answer. Model ids, timeouts and extra request fields live in config. Ollama `qwen3:8b` is the development default. Z.ai (slow, overloaded, 0.67 valid parse) and OpenRouter free models (shared daily cap, and the usable one needs training on prompts enabled) are not used.

## Consequences
Two US providers process the check-in text. Only that text and an anonymized profile are sent (no name, Telegram id or city), consent says so plainly, and `assistant.llm_calls` stores metadata only; the cross-border transfer still needs a line in the privacy notice under 152-FZ. Groq's free limit (8000 tokens per minute per model) fits about 5 users with backoff; growth beyond that means more fallback traffic to Cloudflare or a review of this ADR. Access from the Russian VPS is unverified and is checked with the eval harness before launch; if Groq refuses Russian IPs, Cloudflare moves to the top of the chain. Model ids change often, so the eval is re-run when a model is replaced.
