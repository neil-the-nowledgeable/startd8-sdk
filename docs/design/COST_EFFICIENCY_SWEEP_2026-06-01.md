# Cost-Efficiency Sweep — 2026-06-01

**Task:** Single representative moderate code-gen prompt (`TokenBucketRateLimiter` class +
3 pytest tests) sent live to the cheap/mid/flagship tier of each of the 3 key-configured
providers (Anthropic, OpenAI, Gemini). One run per agent, parallel.

Driver: `scripts/spikes/cost_efficiency_sweep.py`. Costs via SDK `PricingService`
(`startd8.costs.pricing`). Benchmark ID `benchmark-5e454c0f100d` (current gpt-5.x run).

## Ranked by total run cost (cheapest first)

| # | agent | tier | in | out | cost $ | $/1k out | ms |
|---|-------|------|----|----|--------|----------|----|
| 1 | openai:gpt-5.4-nano | cheap | 158 | 647 | 0.000275 | 0.000424 | 4891 |
| 2 | gemini:gemini-2.5-flash-lite | cheap | 167 | 1238 | 0.000384 | 0.000310 | 4618 |
| 3 | openai:gpt-5.4-mini | mid | 158 | 548 | 0.000940 | 0.001715 | 3312 |
| 4 | gemini:gemini-2.5-flash | mid | 167 | 1879 | 0.001152 | 0.000613 | 20165 |
| 5 | gemini:gemini-2.5-pro | flagship | 167 | 1047 | 0.005444 | 0.005199 | 28862 |
| 6 | anthropic:claude-haiku-4-5 | cheap | 184 | 1230 | 0.006334 | 0.005150 | 7766 |
| 7 | openai:gpt-5.5 | flagship | 158 | 1205 | 0.012445 | 0.010328 | 21173 |
| 8 | anthropic:claude-sonnet-4-6 | mid | 184 | 1125 | 0.017427 | 0.015491 | 15689 |
| 9 | anthropic:claude-opus-4-8 | flagship | 240 | 1210 | 0.031450 | 0.025992 | 14637 |

## Ranked by efficiency — $/1k output tokens (verbosity-normalized; the fairer metric)

1. gemini-2.5-flash-lite — $0.000310  **(best)**
2. gpt-5.4-nano — $0.000424
3. gemini-2.5-flash — $0.000613
4. gpt-5.4-mini — $0.001715
5. claude-haiku-4-5 — $0.005150
6. gemini-2.5-pro — $0.005199
7. gpt-5.5 — $0.010328
8. claude-sonnet-4-6 — $0.015491
9. claude-opus-4-8 — $0.025992

## Verdict

- **Most efficient & fastest cheap tier:** `gemini-2.5-flash-lite` (best $/1k out, 4.6 s);
  `gpt-5.4-nano` is the cheapest *total* run and a close #2 on efficiency.
- **Best flagship value:** `gemini-2.5-pro` — ~2× cheaper per output token than `gpt-5.5`
  and ~5× cheaper than `claude-opus-4-8`.
- **By provider:** Gemini owns the efficiency frontier; OpenAI's gpt-5.x cheap/mid tiers are
  very competitive (nano/mini); Anthropic occupies the premium band.

## SDK fix made during this sweep

The gpt-5 family and o-series (o1/o3/o4) reject `max_tokens` (require
`max_completion_tokens`) and only accept the default `temperature` (1). The OpenAI agent
always sent `max_tokens` + a custom temperature, so **every gpt-5.x / o-series model 400'd
and was mislabeled "model not found or not available."**

- Added `requires_max_completion_tokens()` in `agents/base.py`.
- `agents/openai.py` `_make_api_call` (both `GPT4Agent` and `OpenAICompatibleAgent`) now
  switches to `max_completion_tokens` and drops the temperature override for those models.
- Regression tests in `tests/unit/test_agents.py::TestOpenAINextGenParams`.

## Caveats

- **Output length not normalized** — total-cost ranking is skewed by verbosity. Use the
  **$/1k output** ranking for apples-to-apples model economics.
- **Cost only, not quality** — measures price, not correctness. A cheap model that needs a
  repair pass can cost more end-to-end. Pair with a scored eval before routing decisions.
- **Single run per agent** — no variance/repeat sampling.
- **Catalog vs. access:** all gpt-5.x names in `model_catalog.py`/`pricing.py` ARE reachable
  on this key (verified against the live models endpoint); the earlier failure was the
  parameter bug above, not access.
