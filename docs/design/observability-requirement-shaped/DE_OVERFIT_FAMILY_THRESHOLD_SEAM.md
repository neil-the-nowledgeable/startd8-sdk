# Coordination note — the de-overfit family shares one threshold seam (now 3-axis)

**Date:** 2026-07-22
**From:** ContextCore side (importance-scaled-SLO effort)
**For:** SDK team working the #226 de-overfit family (#229–#233)
**Status:** informational — landed in PR #251; no action required, one thing to know before you add signal_kind cells

---

## BLUF

The `#226` de-overfit family (#230 batch, #231 ML-inference, #233 cron, plus #229) and the
ContextCore importance-scaled-SLO effort **write to the same seam**: one table
(`src/startd8/observability/config/importance_thresholds.yaml`) resolved by one function
(`_resolve_threshold`, generic over `field_name`). They converged there by collision, not by plan
(see the #226 RETROSPECTIVE, "compose onto the collision, don't rebuild"). This note makes the
shared shape explicit so the deferred FR-7 `signal_kind` values land at the right nesting level.

**The one thing to know: the table is now 3-axis.** When FR-7/§0.4 were written it was
`<criticality>.<field>`. PR #247 (importance-scaled SLOs) populated the `installed` / `deployed`
**deployment_mode** rows, so the live structure is:

```
<criticality>.<deployment_mode>.<field>
```

So the deferred FR-7 signal_kind fields (`run_success`, `freshness`, `saturation`, `lag`,
`queue_depth`, `retry_rate`) slot in as `field_name`s **under each `<criticality>.<deployment_mode>`
cell** — not directly under `<criticality>`. Net table = **criticality × deployment_mode × signal_kind**.

## Who owns which axis

| Axis | Meaning | Owner | Doc |
|------|---------|-------|-----|
| `criticality × deployment_mode` | SLO **tightness** (how strict) | importance-scaled-SLO (ContextCore-driven) | `docs/design/importance-scaled-slo/REQUIREMENTS.md` |
| `signal_kind` | **which SLIs even apply** (latency vs run-success vs saturation…) | #226 de-overfit family | `docs/design/observability-requirement-shaped/REQUIREMENTS.md` |

Orthogonal, not rival — composed by explicit decision (#226 §0.4). One table, one resolver.
A signal_kind is a `field_name` that sits alongside `availability`/`latency_p99` inside each cell.

## What already landed (PR #251 — the fixes this note makes visible)

- **`observability-requirement-shaped/REQUIREMENTS.md` FR-7** — corrected "add signal_kind cells
  under each **criticality**" → "under each **`<criticality>.<mode>`**" (3-level), with a note that
  #247 populated the mode rows.
- **`importance-scaled-slo/REQUIREMENTS.md`** — gained a reciprocal "Composes with #226" callout so
  the two designs reference each other in both directions.
- **Issue #229** — carries the same 3-axis coordination comment.

## Connection to ContextCore ADR-005 (same root cause, other side of the boundary)

The de-overfit family is the SDK-side face of a pattern ContextCore names
**[ADR-005: First-pilot fossilization](../../../../ContextCore/docs/adr/005-first-pilot-fossilization.md)**
(generalizing [ADR-004](../../../../ContextCore/docs/adr/004-no-fabricated-slo-placeholders.md)):

> A project's **first real subject** gets its concrete shape and values **hardcoded into the
> pipeline** instead of abstracted. #226's own framing — "determination overfit to the Online
> Boutique / HTTP request-serving first use case" — *is* first-pilot fossilization: the HTTP
> request-serving shape of the first pilot fossilized into `_ensure_red_coverage` /
> `_DEFAULT_THRESHOLDS`, so batch/ML/cron services get fabricated RED panels and a 500ms p99 that
> was never authored for them.

The two efforts are the two halves of the same fix:

- **SDK / #226 side** — stop fossilizing *which SLIs apply* to the HTTP shape → the `signal_kind` axis
  and per-kind profile rows (#230/#231/#233).
- **ContextCore / ADR-004+005 side** — stop the manifest template fabricating flat placeholder
  thresholds that mask the importance-scaled derivation → the `criticality × deployment_mode` axis.

Neither fix is complete without the other landing in the **same** cell of the **same** table. That is
why this is a coordination note and not two independent tickets.

## For the SDK team, concretely

When you implement FR-6/FR-7 for #230/#231/#233, add the signal_kind `field_name`s under each
existing `<criticality>.<deployment_mode>` cell in `importance_thresholds.yaml` (installed rows can be
extremely forgiving, matching the mode semantics #247 established), and seed a criticality-agnostic
baseline for each in the flat `_DEFAULT_THRESHOLDS`. No new resolution code — the existing
manifest → importance → flat tiers in `_resolve_threshold` apply unchanged.
