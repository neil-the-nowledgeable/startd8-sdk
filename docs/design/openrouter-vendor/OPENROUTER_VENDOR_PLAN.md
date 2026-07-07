# OpenRouter Vendor Lane — Implementation Plan

**Version:** 1.0
**Date:** 2026-07-06
**Tracks:** `OPENROUTER_VENDOR_REQUIREMENTS.md` v0.2
**Precedent:** DeepSeek vendor wiring (PR #5) + local-lane pricing — same recipe, mostly a data swap.
**Estimated effort:** ~½ session (provider ~130 lines + catalog/pricing rows + tests); lands & tests
offline, then a $-tiny live smoke once `OPENROUTER_API_KEY` is funded.

---

## Reality map (verified during planning)

| Concern | File:Line | Note |
|---------|-----------|------|
| Recipe to copy | `src/startd8/providers/deepseek.py` | hardcoded base_url + env key → `OpenAICompatibleAgent` |
| Dual registration | `pyproject.toml` providers group + `registry.py:_register_builtin_providers` | mirror deepseek/jetson |
| slug() slash-safe | `model_comparison.py:slug` (verified: `deepseek/deepseek-chat` → `-`) | pass-through canonical ids OK |
| cell_id raw model | `benchmark_matrix/runner.py:cell_id` | identity-only; slash cosmetic; `split(":",1)[0]` recovers hash |
| Pricing table | `costs/pricing.py:DEFAULT_PRICING`, `PROVIDER_PATTERNS`, `resolve_pricing` ($3/$15 fallback) | add per-model rows + `openrouter` pattern |
| Infra-fail markers | `benchmark_matrix/runner.py:_INFRA_ERROR_MARKERS` (now incl. 402/insufficient balance) | missing/unfunded key → infra_fail, not a model 0 |
| No header passthrough | `agents/openai.py` `OpenAI(...)`/`AsyncOpenAI(...)` (no `default_headers`) | NR-OR-1: skip attribution headers in v1 |
| Catalog | `model_catalog.py` (`Models`, `_MODEL_REGISTRY`, `tier_map`) | add openrouter block |

---

## Steps

### Step 1 — `openrouter` provider (FR-OR-1/2/3)
`src/startd8/providers/openrouter.py` from `deepseek.py`:
- `BASE_URL = "https://openrouter.ai/api/v1"`; `MODELS = ["deepseek/deepseek-chat",
  "qwen/qwen-2.5-coder-32b-instruct"]` (+ `deepseek/deepseek-r1` optional).
- `api_key = config.get('api_key') or os.getenv('OPENROUTER_API_KEY')`; error string
  "OpenRouter API key required. Set OPENROUTER_API_KEY…" (infra-fail match).
- `name="openrouter"`, `display_name="OpenRouter"`; **pass model through verbatim** (no alias map);
  unknown id → `logger.warning`, not error (large drifting catalog).
- `get_required_env_vars() -> ["OPENROUTER_API_KEY"]`; `max_tokens` default 8192.

### Step 2 — Dual registration (FR-OR-1)
- `pyproject.toml`: `openrouter = "startd8.providers.openrouter:OpenRouterProvider"`.
- `registry.py:_register_builtin_providers`: guarded `from .openrouter import OpenRouterProvider` block.
- Bump the CLAUDE.md provider count/list.

### Step 3 — Catalog (FR-OR-4)
- `Models.OPENROUTER_DEEPSEEK_CHAT = "openrouter:deepseek/deepseek-chat"`,
  `OPENROUTER_QWEN_CODER_32B = "openrouter:qwen/qwen-2.5-coder-32b-instruct"`.
- `_MODEL_REGISTRY` rows (bare id key, `provider="openrouter"`, tier `balanced`/`fast`, caps
  `{text,code,reasoning}`). NB `get_model_info` strips the first colon → query with the full
  `openrouter:…` spec (the local-lane quirk); the registry key is the slash id after the colon.
- `tier_map["openrouter"]`.

### Step 4 — Pricing (FR-OR-5/6)
- `DEFAULT_PRICING` rows keyed by the bare slash id (`"deepseek/deepseek-chat"`,
  `"qwen/qwen-2.5-coder-32b-instruct"`), `provider="openrouter"`, OpenRouter's **published** per-M
  input/output rate, `estimated=True`, note "OpenRouter published rate; confirm at openrouter.ai/models".
- `PROVIDER_PATTERNS["openrouter"] = ["openrouter"]` (exact-id rows carry `provider` already; the
  pattern is the fallback).

### Step 5 — Secrets (FR-OR-8) — operator
- Fund an OpenRouter account (US/Stripe), create a key, then:
  `read -rs "KEY?OpenRouter key: "; printf '%s' "$KEY" | doppler secrets set OPENROUTER_API_KEY -p startd8 -c dev; unset KEY`.

### Step 6 — Tests (FR-OR-11) — offline
`tests/unit/providers/test_openrouter_provider.py`: registry resolves `openrouter`; missing-key error
is infra-fail-compatible; `create_agent("deepseek/deepseek-chat")` → base_url pinned + model passed
verbatim; pricing non-fallback for each enrolled id + `get_provider_for_model` → `openrouter`; catalog
rows present via `openrouter:…`; FR-OR-2 guard (`openrouter:deepseek/deepseek-chat` splits provider/model,
`slug()` path-safe, `cell_id` hash round-trips).

### Step 7 — Dry-run proof (FR-OR-11)
`python3 scripts/run_behavioral_pilot.py --model openrouter:deepseek/deepseek-chat --dry-run` → finite,
non-fallback, no NO-PRICING warning.

### Step 8 — Live smoke + probe (FR-OR-12) — after funding
1. `doppler run … agenerate` on `openrouter:deepseek/deepseek-chat` returns text (auth+billing).
2. Generate the 3 OB services via OpenRouter deepseek-chat + qwen-coder-32b; run the contamination
   probe vs `/tmp/ob-ref/src` → the hosted differential vs `qwen-coder:7b 0.193`.

### Step 9 — Id-drift guard (OQ-OR-4) — optional, endpoint-gated
A test that `GET https://openrouter.ai/api/v1/models` superset-contains every enrolled id; a missing
id fails loudly naming it (mirrors Jetson FR-J3a).

---

## Sequencing & risk
1. Steps 1–4, 6, 7 land + test **fully offline** (DeepSeek proved the dry-run path). Steps 5, 8 are
   operator/funding-gated.
2. **Branch-first** off `origin/main` (`feat/openrouter-vendor`); do not commit to shared main.
3. Pin `PYTHONPATH=<worktree>/src` for pytest ([[reference_multiworktree_env]]).
4. OpenRouter model-id drift is the main external risk → OQ-OR-4 guard; pin ids, warn-not-error on unknown.

## Traceability
| FR | Step |
|----|------|
| FR-OR-1 | 1, 2 |
| FR-OR-2 | 1, 6 |
| FR-OR-3 | 1, 6 |
| FR-OR-4 | 3 |
| FR-OR-5 / OR-6 | 4, 6 |
| FR-OR-7 | (design — no cost_lane code) |
| FR-OR-8 | 5 |
| FR-OR-9 | 1, 3, 4 |
| FR-OR-10 | 8 (probe) |
| FR-OR-11 | 6, 7 |
| FR-OR-12 | 8 |
| FR-OR-13 | 3, 4 (data-only adds) |
| OQ-OR-4 | 9 |
