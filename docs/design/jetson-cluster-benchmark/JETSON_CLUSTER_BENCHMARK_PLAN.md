# Jetson Cluster Benchmark Enrollment — Implementation Plan

**Version:** 1.0
**Date:** 2026-06-16
**Tracks:** `JETSON_CLUSTER_BENCHMARK_REQUIREMENTS.md` v0.2
**Precedent:** DeepSeek vendor wiring (PR #5) — same recipe, this plan reuses it.
**Estimated effort:** SDK side ~1 focused session; gated on operator (endpoint up) + one server check.

---

## Reality map (verified during planning)

| Concern | File:Line | Note |
|---------|-----------|------|
| Provider recipe to copy | `src/startd8/providers/deepseek.py` (this PR) | hardcoded base_url + sentinel key + alias map |
| No-auth only localhost | `agents/openai.py:484` | `192.168.x.x` NOT covered → FR-J11 sentinel key |
| Agent stores base_url | `agents/openai.py:62` (`self.base_url`) | test assertion target |
| Spec → command | `model_comparison.py:build_command:149`; `slug():55` | `--lead/--drafter` = spec; paths slug-safe |
| cell_id embeds raw model | `benchmark_matrix/runner.py:cell_id` | argues for slash-free aliases (FR-J3a) |
| Pricing fallback $3/$15 | `costs/pricing.py` `_FALLBACK_INPUT/OUTPUT_PER_M` | FR-J9b: explicit entries mandatory |
| Infra-fail covers unreachable | `runner.py:_INFRA_ERROR_MARKERS` (connection error) | FR-J1 needs no new code |
| Benchmark sends own system | `prime_contractor.py:2646` + `agents/openai.py:111` | FR-J6 is server-side only |
| Registration (dual) | `pyproject.toml` providers group + `registry.py:_register_builtin_providers` | mirror DeepSeek |

---

## Steps

### Step 1 — `jetson` provider (FR-J3, FR-J3a, FR-J11)
Create `src/startd8/providers/jetson.py` from `deepseek.py`, changing:
- `BASE_URL = "http://192.168.7.57:8000/v1"`
- `ALIASES = {"mistral-7b-base": "mistralai/Mistral-7B-v0.3", "iter-002": "iter_002", ...}`;
  `MODELS = list(ALIASES)`.
- `create_agent`: translate alias → real id (`served = self.ALIASES.get(model, model)`), pass `served`
  as the agent `model`; `api_key = config.get('api_key') or os.getenv('LOCAL_FASTAPI_API_KEY', 'local-no-auth')`.
- `name="jetson"`, `display_name="Jetson Edge Cluster"`.
- Each alias's `MODEL_INFO` carries a `contamination` label: `"clean"` (mistral-7b-base) vs
  `"in-domain-finetune"` (iter-002).

### Step 2 — Dual registration (mirror DeepSeek)
- `pyproject.toml`: `jetson = "startd8.providers.jetson:JetsonProvider"`.
- `registry.py:_register_builtin_providers`: add the guarded `from .jetson import JetsonProvider` block.

### Step 3 — Catalog (FR-J8/J9)
- `model_catalog.py`: `Models.JETSON_MISTRAL_BASE = "jetson:mistral-7b-base"` (+ iter alias);
  `_MODEL_REGISTRY` rows (`provider="jetson"`, tier `fast`, capabilities `{"text","code"}`);
  `tier_map["jetson"]`.

### Step 4 — Pricing (FR-J9b)
- `costs/pricing.py` `DEFAULT_PRICING`: entries for `mistralai/Mistral-7B-v0.3` and `iter_002`
  (the REAL served ids the cost layer sees), `provider="jetson"`, rate per OQ-J3 (start ≈$0 marginal
  with an amortized note), `estimated=True`. Add `"jetson": ["jetson"]` to `PROVIDER_PATTERNS`.
  > Note: pricing is keyed by the served model id, not the alias — confirm which id the cost tracker
  > receives (the agent's `model` = the translated served id). Test both.

### Step 5 — Contamination labels & provenance (FR-J5, FR-J7)
- Surface the per-alias `contamination` label in the matrix report / cells.json (small addition to the
  report builder), so in-domain cells are visibly fenced off from the general leaderboard.

### Step 6 — Server-side neutral-prompt verification (FR-J6) — edge-brains, not SDK
- Inspect `edge-brains/scripts/fastapi_serve.py`: confirm a request `messages[0].role=="system"`
  overrides the env `SYSTEM_PROMPT` (don't force-prepend). Fix if it force-prepends. **Gate any fair
  run on this.** (Out of this repo; tracked here as a checklist item.)

### Step 7 — Tests (mirror DeepSeek test file)
`tests/unit/providers/test_jetson_provider.py`: registry resolves `jetson`; alias→served-id
translation; sentinel key applied when no env; `base_url` pinned; pricing real (non-fallback) for the
served ids; `get_provider_for_model` → `"jetson"`; clean vs in-domain label present.

### Step 8 — End-to-end smoke (FR-J10) — operator-gated
1. Operator: `bash edge-brains/scripts/start_fastapi_on_rosie.sh`; confirm `curl …:8000/v1/models`.
2. `python3 scripts/run_behavioral_pilot.py --model jetson:mistral-7b-base --dry-run` → finite,
   non-fallback cost estimate.
3. One live `--run` cell; confirm scored output + provenance label; verify the request carried the
   neutral system prompt (FR-J6).

---

## Sequencing & risk
1. Steps 1–4 + 7 are pure SDK and can land + be tested **without the cluster online** (DeepSeek proved
   the dry-run path is offline). Steps 6 & 8 are operator/cluster-gated.
2. **Branch-first** off `origin/main` (`feat/jetson-vendor`); do not merge into shared main locally
   ([[reference_multiworktree_env]] contended-main hazard).
3. Pin `PYTHONPATH=<worktree>/src` for pytest.
4. **Do not enroll iter-002 on the general leaderboard** — FR-J5/J7 labels + FR-J6 server check are
   prerequisites; the clean `mistral-7b-base` is the v1 deliverable.

## Traceability
| FR | Step |
|----|------|
| FR-J1 | (none — already covered) / 8 optional |
| FR-J2 | 3 (opt-in; not in DEFAULT_MODELS) |
| FR-J3 / J3a / J11 | 1 |
| FR-J4 | 1 |
| FR-J5 / J7 | 1, 5 |
| FR-J6 | 6 (server-side) |
| FR-J8 / J9 | 3 |
| FR-J9b | 4 |
| FR-J10 | 8 |
