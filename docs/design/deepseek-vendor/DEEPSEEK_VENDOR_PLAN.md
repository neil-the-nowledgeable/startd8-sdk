# DeepSeek Vendor Wiring — Implementation Plan

**Version:** 1.0
**Date:** 2026-06-16
**Tracks:** `DEEPSEEK_VENDOR_REQUIREMENTS.md` v0.2
**Estimated effort:** ~1 focused session (provider is ~150 lines, rest is registration + tables + tests)

---

## Reality map (verified during planning)

| Concern | File:Line | Note |
|---------|-----------|------|
| Provider pattern to copy | `src/startd8/providers/mistral.py:1-154` | Hardcoded base_url + env key + `OpenAICompatibleAgent` |
| Entry-point declaration | `pyproject.toml` `[project.entry-points."startd8.providers"]` (~L114-120) | `nim`/`openai-compatible` already there |
| Builtin fallback registration | `src/startd8/providers/registry.py:209-238` | `_register_if_missing(name, factory, display)` |
| Catalog consts + registry | `src/startd8/model_catalog.py:120-131` (Mistral block), `_MODEL_REGISTRY:176+`, `mistral` rows `329-343` | Add a DeepSeek block mirroring Mistral |
| Pricing table | `src/startd8/costs/pricing.py:70 DEFAULT_PRICING`; `get_pricing:438`; `get_provider_for_model:497` | Keyed by bare model_id; add rows |
| Benchmark roster | `scripts/run_behavioral_pilot.py:39 DEFAULT_MODELS`; `--model` append:74 | Pass `deepseek:deepseek-chat` |
| Spec→command threading | `model_comparison.py:build_command:149-192` | `--lead-agent`/`--drafter-agent` = model spec; **no base_url** |
| Infra-fail exclusion | `benchmark_matrix/runner.py:35 _INFRA_ERROR_MARKERS`, `is_infra_error:51` | Matches "api key required"/"failed to resolve agents" |
| edge-brains reuse pattern | `edge-brains/.../run_multi_agent_benchmark.py` | `provider: openai-compatible` + `base_url` (self-hosted) — FR-13 only |

---

## Steps

### Step 1 — Provider (FR-1, FR-3, FR-5)
Create `src/startd8/providers/deepseek.py` by copying `mistral.py` and changing:
- `MODELS = ["deepseek-chat"]` (+ `"deepseek-reasoner"` iff OQ-1 says yes)
- `MODEL_INFO` with context window + rates (from FR-4 numbers)
- `name`→`"deepseek"`, `display_name`→`"DeepSeek"`
- `base_url='https://api.deepseek.com/v1'`
- env var `DEEPSEEK_API_KEY`; error string **"DeepSeek API key required. Set DEEPSEEK_API_KEY environment variable or pass api_key in config."** (must contain "api key required" → infra-fail match, FR-3)
- `get_required_env_vars()` → `['DEEPSEEK_API_KEY']`
- `max_tokens` default per OQ-2 (start 8192)

### Step 2 — Dual registration (FR-2)
- `pyproject.toml`: add `deepseek = "startd8.providers.deepseek:DeepSeekProvider"` to the providers entry-point group.
- `registry.py:_register_builtin_providers` (~after the mistral block): add
  ```python
  try:
      from .deepseek import DeepSeekProvider
      _register_if_missing("deepseek", DeepSeekProvider, "DeepSeek")
  except ImportError:
      pass
  ```
- Update the CLAUDE.md "6 registered providers" note → 7 (and entry-points list).

### Step 3 — Catalog (FR-7, FR-8)
- `model_catalog.py`: add a `# DeepSeek` block in `Models` with `DEEPSEEK_CHAT = "deepseek:deepseek-chat"`.
- Add `_MODEL_REGISTRY["deepseek-chat"] = ModelInfo(provider="deepseek", model_id="deepseek-chat", tier="balanced", capabilities={"text","code","reasoning"})`.
- Confirm `get_latest_model("deepseek", …)` path / tier map includes deepseek (mirror the `"mistral": {...}` tier dict at ~`model_catalog.py:470`).

### Step 4 — Pricing (FR-4)
- `costs/pricing.py` `DEFAULT_PRICING`: add
  ```python
  "deepseek-chat": ModelPricing(
      model="deepseek-chat", provider="deepseek",
      input_cost_per_million=<confirmed>, output_cost_per_million=<confirmed>,
      estimated=<True if unconfirmed>, notes="DeepSeek list price; confirm at https://api-docs.deepseek.com/quick_start/pricing",
  ),
  ```
- Verify `get_provider_for_model("deepseek-chat")` returns `"deepseek"` (it reads the `.provider` field — should be automatic; add a test).

### Step 5 — Secrets (FR-9)
- `doppler secrets set DEEPSEEK_API_KEY=… -p startd8 -c dev` (operator step; document in the requirements + a one-liner in the benchmark run notes).
- No repo change beyond documentation. Local fallback: plain `DEEPSEEK_API_KEY` env var.

### Step 6 — Tests (FR-12)
Add `tests/unit/providers/test_deepseek_provider.py`:
- registry resolves `deepseek` via builtin path (call `ProviderRegistry.discover()` then `get_provider("deepseek")`).
- `validate_config({})` with no env raises `ConfigurationError` whose message satisfies `is_infra_error(...)`.
- `create_agent("deepseek-chat", api_key="x")` returns an `OpenAICompatibleAgent` with `base_url` == `https://api.deepseek.com/v1`.
- pricing: `PricingService().get_pricing("deepseek-chat")` is not None and (if confirmed) `estimated is False`.
- `get_provider_for_model("deepseek-chat") == "deepseek"`.

### Step 7 — Dry-run proof (FR-11)
```bash
doppler run -p startd8 -c dev -- python3 scripts/run_behavioral_pilot.py \
  --model deepseek:deepseek-chat --dry-run
```
Expect: finite cost estimate, no fallback-estimate warning. (Then a single live `--run` cell before adding to `DEFAULT_MODELS`, OQ-4.)

### Step 8 — Extension docs (FR-13, FR-14)
Append an "Extending to other vendors" section to the requirements (or a short `EXTENSION.md`):
- hosted OpenAI-compatible (xAI/Grok, Groq, OpenRouter): copy `deepseek.py`, swap base_url/env/pricing.
- self-hosted/local-quantized (edge-brains pattern + quantization serving): use `openai-compatible` + base_url; note the `provider:model`-can't-carry-base_url gap and the two future fixes.

---

## Sequencing & risk

1. Steps 1→4 are independent edits; do them together, then Step 6 tests, then Step 2 wiring verified by tests.
2. **Branch-first** ([[feedback_branch_first_workflow]]): `feat/deepseek-vendor` off `origin/main`; do not commit to main.
3. **Multiworktree** ([[reference_multiworktree_env]]): run tests with `PYTHONPATH=<this-worktree>/src` so pytest imports the right `startd8`; check `git branch` before any git op.
4. Live spend is gated behind explicit `--run` (default `--dry-run`); confirm Doppler key present before any live cell.

---

## Traceability

| FR | Step(s) |
|----|---------|
| FR-1 | 1 |
| FR-2 | 2 |
| FR-3 | 1, 6 |
| FR-4 | 4, 6 |
| FR-5 | 1 (OQ-1) |
| FR-6 | (design constraint — verified by 7, no code) |
| FR-7 | 3 |
| FR-8 | 4, 6 |
| FR-9 | 5 |
| FR-10 | 7 |
| FR-11 | 7 |
| FR-12 | 6 |
| FR-13 | 8 |
| FR-14 | 8 |
