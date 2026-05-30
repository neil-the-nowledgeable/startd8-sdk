# Cost-Tracking Precision — Implementation Plan

**Version:** 0.1
**Date:** 2026-05-28
**Pairs with:** `COST_TRACKING_PRECISION_REQUIREMENTS.md` (v0.2)

Maps REQ-CT-1…6 onto the cost path. Ordered so each step is independently testable and the
risky bits (model matching) are isolated.

---

## 1. Design decisions

- **Cache multipliers live on `ModelPricing`** as fields with defaults
  (`cache_read_multiplier=0.1`, `cache_write_multiplier=1.25`) rather than hard-coded constants,
  so a provider with different cache economics can override per model. Anthropic uses the defaults.
- **`calculate_cost_breakdown` stays backward compatible**: new `cache_creation_input_tokens` /
  `cache_read_input_tokens` params default to `0`, so existing callers are unaffected and the
  no-cache result is byte-identical to today (REQ-CT-1 AC).
- **Model resolution becomes family-safe** (REQ-CT-3): exact key → dated/undated normalization
  *within the same provider+family* → estimated fallback. The current
  `startswith(key.rsplit('-',1)[0])` collapse to bare `gpt`/`claude` is removed. Family is keyed
  off the leading tokens (`provider` + first two id segments), never a 1-char prefix.
- **Estimated signal** (REQ-CT-5): `get_pricing` returns `(ModelPricing, estimated: bool)` via a
  new `resolve_pricing()` that the tracker uses; `get_pricing()` keeps its old signature for
  compatibility (delegates to `resolve_pricing()[0]`).
- **Precision policy** (REQ-CT-6): round each record's `input_cost`/`output_cost`/`total_cost` to
  **1e-9 USD** (nano-dollar) at record creation; aggregations sum the already-rounded values.
  Epsilon for reconciliation = 1e-6.

## 2. Surface changes

```
# costs/pricing.py
ModelPricing: + cache_read_multiplier: float = 0.1
              + cache_write_multiplier: float = 1.25
              + estimated: bool = False
resolve_pricing(model) -> tuple[ModelPricing, bool]   # (pricing, is_estimated) — family-safe
get_pricing(model) -> ModelPricing | None             # unchanged signature; delegates
calculate_cost_breakdown(model, input_tokens, output_tokens,
                         cache_creation_input_tokens=0, cache_read_input_tokens=0)
                         -> tuple[float, float]        # input_cost now folds cache costs

# costs/tracker.py
record_cost(..., cache_creation_input_tokens: int|None = None,
                 cache_read_input_tokens: int|None = None)   # threads to pricing + record

# costs/models.py
CostRecord: + cache_creation_input_tokens: int = 0
            + cache_read_input_tokens: int = 0
            + pricing_estimated: bool = False

# agents/base.py
record_cost(..., cache_creation_input_tokens=token_usage.cache_creation_input_tokens,
                 cache_read_input_tokens=token_usage.cache_read_input_tokens)
```

## 3. Task decomposition

| Step | Deliverable | REQ |
|------|-------------|-----|
| CT-1 | `ModelPricing` cache fields + `estimated`; default-model entries (opus-4-8/4-7, gpt-5.x, gemini-3.1) flagged estimated where unconfirmed | REQ-CT-1, 4 |
| CT-2 | `resolve_pricing()` family-safe matcher; remove bare-prefix collapse; `get_pricing` delegates | REQ-CT-3, 5 |
| CT-3 | cache-aware `calculate_cost_breakdown` (+ `calculate_total_cost`) | REQ-CT-1 |
| CT-4 | `CostRecord` cache + `pricing_estimated` fields; `record_cost` accepts/threads cache tokens + estimated marker; nano-dollar rounding | REQ-CT-2, 5, 6 |
| CT-5 | `base.py` bridge passes `token_usage.cache_*` | REQ-CT-2 |
| CT-6 | Unit tests: cache pricing math, no-cache regression, family-safe matching (`gpt-5.5-pro` ≠ gpt-4.1), each default resolves, estimated marker+WARNING, summary reconcile within epsilon | all |

> Sequencing: CT-1→CT-3 are pricing-internal (no caller impact until CT-4 threads tokens).
> CT-2 (matching) is isolated so its risk (wrong-family regressions) is caught by CT-6 before
> CT-4 wires it into recording. CT-5 is the one-line agent change, last.

## 4. Risks

- **Changing `get_pricing` matching can shift existing recorded costs** for models that *relied*
  on the loose match. Mitigation: family-safe match still resolves dated→undated within a family;
  a test pins that previously-correct loose matches (e.g. `claude-3-5-sonnet-20241022`) still
  resolve, while wrong-family matches now go to flagged-estimated instead of a wrong rate.
- **Backward-compat of `calculate_cost_breakdown`**: new params default 0 → identical output for
  all existing callers; pinned by a no-cache regression test.
- **Estimated rates for new defaults** could be wrong; mitigated by the `estimated` flag +
  WARNING so they're never mistaken for measured, and are trivially updatable via `update_pricing`.

## 5. Out of scope (mirrors Non-Requirements)

OpenAI/Gemini cached-token capture (NR-1), caching default changes (NR-3), 1h-TTL write
accounting (NR-4).
