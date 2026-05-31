# Known Limitation: domain-alert TODO stubs double-stamp the service prefix

**Date:** 2026-05-31
**Status:** COSMETIC — DEFERRED (commented-out text only; not worth the churn)
**Component:** `src/startd8/observability/artifact_generator.py` → `_domain_alert_todo_block`
**Introduced by:** Closure 1 / Gap 1 (commit `5c1578fc`)

---

## Problem

The commented-out domain-metric alert stubs emitted for `manifest_declared`
metrics produce alert names that repeat the product/service token, e.g.:

```yaml
#  - alert: Strtd8Startd8ContextUsageRatioHigh
#    expr: startd8_context_usage_ratio{service="strtd8"} > <THRESHOLD>
```

`Strtd8Startd8…` double-stamps because:

- `_alert_name(service_id, suffix)` PascalCases the **service id** (`strtd8` →
  `Strtd8`) and prepends it, and
- the `manifest_declared` metric name already begins with the **product prefix**
  (`startd8_context_usage_ratio` → `Startd8ContextUsageRatio`).

So the two prefixes stack.

## Why it is low-impact

These names appear **only inside the commented-out `# TODO: domain-metric alerts`
block** of `alerts/{service}-alerts.yaml`. They are stubs an operator uncomments
and edits after setting a threshold (the TODO-when-absent policy) — they are
never emitted as active Prometheus rules, never loaded by Alertmanager, and never
referenced by dashboards or SLOs. The cost is purely aesthetic, in a block that
already requires manual editing before use.

## Resolution path (if/when pursued)

In `_domain_alert_todo_block`, drop the redundant leading token when the metric
name already carries the service/product prefix. Options:

1. Pass a flag to `_alert_name` to skip the service prefix for declared-metric
   stubs (the metric name is already globally unique).
2. Strip a leading `_pascal(service_id)` / known product prefix from
   `_pascal(metric.name)` before concatenation.

Keep it scoped to the TODO-stub path; the active-rule alert names
(`{Service}LatencyP99High`, etc.) are correct and must not change.

## Evidence

| Item | Reference |
|------|-----------|
| Stub name construction | `artifact_generator.py:933` (`_alert_name(service.service_id, _pascal(metric.name) + "High")`) |
| `_pascal` helper | `artifact_generator.py:903` |
| Stub block (commented) | `_domain_alert_todo_block`, `artifact_generator.py:909` |
| Appears only in | the `# TODO: domain-metric alerts` comment block of `alerts/{service}-alerts.yaml` |
| Active rules unaffected | `generate_alert_rules` (latency/error/availability names are single-prefixed) |
| Commit | `5c1578fc` (Closure 1 / Gap 1) |
