# Cost-Tracking Precision Requirements

**Version:** 0.2 (Post-review — grounded in a full read of the cost path)
**Date:** 2026-05-28
**Status:** Draft (pre-implementation)
**Prefix:** REQ-CT (Cost Tracking)
**Component:** `src/startd8/costs/` + `src/startd8/agents/{base,claude}.py`, `src/startd8/models.py`

---

## 0. Review Insights (what the code read revealed)

> The cost subsystem is "directionally correct but imprecise." A full read of the path
> (`agents/base.py` → `costs/tracker.py` → `costs/pricing.py`, with `TokenUsage`/`CostRecord`)
> located **six** concrete imprecision sources. The requirements below target each.

| Imprecision | Where | Effect |
|-------------|-------|--------|
| Cache tokens dropped end-to-end | `base.py:339` (bridge omits them), `tracker.py:128` (no params), `CostRecord` (no fields), `pricing.calculate_cost_breakdown` (no cache math) | Cost **under-reported** whenever Anthropic caching is active (0.1× reads + 1.25× write surcharge invisible) |
| `input_tokens` excludes cached input | `claude.py:430` (`input=response.usage.input_tokens`) | Cached prefix contributes $0 to recorded cost |
| Loose model→price prefix match | `pricing.py:328-331` (`startswith(key.rsplit('-',1)[0])`) | `gpt-5.5-pro` silently priced as `gpt-4.1`; any unknown model can match the wrong family |
| No pricing for current flagship defaults | `pricing.py` DEFAULT_PRICING | `claude-opus-4-8/4-7`, `gpt-5.x`, `gemini-3.1-pro-preview` fall to loose-match or `$3/$15` |
| Silent fabricated fallback | `pricing.py:354-356` | Emits a plausible number with no "estimated" signal; analytics can't tell measured from guessed |
| Float accumulation | `tracker.py:274` running totals, `get_summary` sums | Drift across many small costs; no canonical precision policy |

**Resolved questions from the review:**
- **Anthropic cache multipliers** (per platform docs): cache **read** = 0.1× base input; 5-minute cache **write** = 1.25× base input; 1-hour cache **write** = 2.0× base input. The SDK uses the default 5-minute TTL today, so 1.25× applies to `cache_creation_input_tokens`.
- **`response.usage.input_tokens` semantics:** excludes both `cache_creation_input_tokens` and `cache_read_input_tokens`; total input billed = `input·1.0 + cache_creation·write_mult + cache_read·0.1` (× input rate).
- **Scope:** Anthropic caching + the pricing/matching/precision *infrastructure*. OpenAI/Gemini provider-side cached-token capture is acknowledged as a follow-up (their agents don't surface cached-token usage yet).

---

## 1. Problem Statement

Recorded costs diverge from actual Anthropic spend, in two directions: **under-reporting**
when prompt caching is active (the dominant case now that caching is being enabled), and
**mis-pricing** when a model isn't an exact pricing-table key (loose prefix matching, missing
entries for the new defaults, silent fallback). The subsystem cannot currently (a) account for
cache economics, (b) guarantee a model maps to *its own* rate, or (c) signal when a cost is
estimated rather than measured.

---

## 2. Requirements

- **REQ-CT-1 — Cache-aware pricing.** `ModelPricing` MUST express cache economics, and the
  cost calculation MUST consume `cache_creation_input_tokens` and `cache_read_input_tokens`.
  Default multipliers (overridable per model): read `0.1×`, 5-minute write `1.25×`. Cost =
  `input·in_rate + cache_creation·in_rate·write_mult + cache_read·in_rate·read_mult + output·out_rate`.
  - **AC:** for a known model, a call with `input=1000, cache_read=50000, output=500` costs
    `1000·in + 50000·in·0.1 + 500·out` (per million); with `cache_read=0` it equals today's result (no regression).
- **REQ-CT-2 — End-to-end cache-token flow.** Cache tokens MUST survive from the API response
  to the persisted record: `CostTracker.record_cost` accepts `cache_creation_input_tokens` /
  `cache_read_input_tokens`; the `base.py` post-call bridge passes `token_usage.cache_*`;
  `CostRecord` persists them (defaulting to 0/None for non-caching providers).
  - **AC:** a cached Anthropic call yields a `CostRecord` whose cache token fields are non-zero
    and whose `total_cost` includes the cache-read/-write cost.
- **REQ-CT-3 — Safe model→pricing resolution.** Replace the bare-prefix match with resolution
  that never maps a model to a *different family's* rate. Preference order: exact key → an
  explicit alias/normalization (e.g. dated → undated within the same family) → **estimated
  fallback** (REQ-CT-5). A model from family X MUST NOT silently price as family Y.
  - **AC:** `get_pricing("gpt-5.5-pro")` does NOT return the `gpt-4.1` entry; an unknown model
    returns an explicitly-estimated result, not a wrong-family exact rate.
- **REQ-CT-4 — Pricing for current default models.** DEFAULT_PRICING MUST contain entries for
  every model the SDK ships as a *default* (`claude-opus-4-8`, `claude-opus-4-7`, `gpt-5.5-pro`,
  `gpt-5.5`, `gpt-5.4-mini`, `gpt-5.4-nano`, `gemini-3.1-pro-preview`, plus existing). Where the
  official rate is unconfirmed, the entry is marked **estimated** (REQ-CT-5), never omitted.
  - **AC:** `get_pricing(<each shipped default>)` returns a non-fallback entry; estimated ones carry the estimated marker.
- **REQ-CT-5 — Estimated-vs-measured signal.** When pricing is a fallback or a flagged estimate,
  the resulting `CostRecord` MUST carry a machine-readable marker (e.g. `pricing_estimated: bool`
  or a metadata flag) so summaries/analytics can separate measured spend from estimated spend.
  Estimation MUST also log at WARNING with the model id (no silent fabrication).
  - **AC:** a record priced via fallback has the estimated marker set and emits one WARNING; a
    record priced from an exact entry does not.
- **REQ-CT-6 — Deterministic precision.** Define and apply one rounding/precision policy for cost
  values so that aggregations reconcile: a summary's `total_cost` equals the sum of its records'
  `total_cost` under the policy (no float-drift discrepancy beyond the defined epsilon).
  - **AC:** summing N records and comparing to `get_summary().total_cost` differs by ≤ the policy epsilon.

---

## 3. Non-Requirements

- **NR-1** — Does NOT add OpenAI/Gemini provider-side cached-token *capture* in this round (their
  agents don't surface `cached_tokens` yet); the *pricing/record* layer is built cache-ready so
  those can be wired later without schema change.
- **NR-2** — Does NOT invent official prices: unconfirmed rates are flagged estimated (REQ-CT-5), not asserted.
- **NR-3** — Does NOT change caching behavior/defaults (that is a separate decision); this is
  purely about *measuring* cost accurately.
- **NR-4** — Does NOT add 1-hour-TTL write accounting until the SDK actually emits 1h cache
  breakpoints (multiplier hook is present but unused).

---

## 4. Affected Code

| Area | File | Change |
|------|------|--------|
| Pricing model + math | `costs/pricing.py` | cache multipliers on `ModelPricing`; cache-aware `calculate_cost_breakdown`; safe `get_pricing`; default-model entries; estimated signal |
| Tracker | `costs/tracker.py` | `record_cost` cache params → pricing → record; estimated marker passthrough |
| Record schema | `costs/models.py` | `CostRecord` cache token fields + `pricing_estimated` |
| Agent bridge | `agents/base.py` | pass `token_usage.cache_*` into `record_cost` |
| (already done) | `agents/claude.py`, `models.py` | `TokenUsage` cache fields already captured — no change |
| Tests | `tests/costs/` | cache pricing, safe matching, estimated signal, precision reconcile |

---

*v0.2 — grounded in a full cost-path read; 6 requirements targeting the 6 located imprecision
sources. Pairs with `COST_TRACKING_PRECISION_PLAN.md`.*
