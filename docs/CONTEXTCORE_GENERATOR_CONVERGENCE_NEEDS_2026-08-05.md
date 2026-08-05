# What ContextCore needs from startd8 to converge its legacy observability generators

**From:** ContextCore (consumer of `startd8.observability`)
**To:** startd8-sdk / SDK team
**Date:** 2026-08-05
**TL;DR:** **We need essentially nothing new from you to be unblocked.** The generation entry points we
need already exist and are proven (see §2). This note documents the convergence, confirms the seam, and
lists one small *nice-to-have* — so you can say "yes, that's the intended path" (or correct us) before we
build the ContextCore-side mapper/adapter.

---

## 0. Context (why this is happening now)

- **ADR-003** (ContextCore, Accepted) names `startd8.observability.artifact_generator` the **canonical**
  observability generator; the ContextCore **operator** (`operator.py`) and **CLI** (`cli/_generators.py`)
  generators are LEGACY and emit a **divergent metric shape** (`http_requests_total{status=~"5.."}`,
  Prometheus-client) vs the canonical OTel `http_server_*`. Convergence was **deferred** pending a
  cross-repo dependency-direction decision.
- **That decision is now made** (ContextCore, 2026-08-05): ContextCore imports startd8 as an **optional**
  dependency — the same pattern already used for the taxonomy `Category` (`_known_categories()`), and now
  used for generation in Feature/Delivery Observability **G13**. `CROSS_CAPABILITY_REUSE_DECISIONS.md` D4
  ("do NOT share startd8 generation") was **reversed** — the `DashboardSpec→Grafana` render tail is shared.
- So ContextCore now wants to **retire the legacy generators' divergent shape by delegating to your
  canonical generation.** This note is the pre-build check-in.

## 1. What we're converging (ContextCore-side)

`contextcore.operator.generate_prometheus_rules / generate_grafana_dashboard` (#2, kopf runtime) and
`contextcore.cli._generators.generate_prometheus_rule / generate_dashboard / generate_service_monitor`
(#3, `contextcore create --apply`). Both currently hardcode/parameterize the Prometheus-client RED shape
(`http_requests_total`, `status=~"5.."`). They produce **RED error-ratio** alerts and per-service
dashboards from a `ProjectContext` (availability/latency SLOs).

## 2. What you ALREADY provide (grounded in your tree, 2026-08-05) — this is the "unblock"

| Need | Your API | Status |
|------|----------|--------|
| Domain threshold → alert rules (Prometheus rule groups YAML) | `observability.alert_renderer.render_domain_alert_rules(spec, project_id)` | ✅ used by ContextCore **G13** |
| Domain spec → dashboard spec YAML | `observability.dashboard_renderer.render_domain_dashboard(spec, project_id)` | ✅ used by G13 |
| observability.yaml mapping → `ObservabilitySpec` | `observability.spec.from_observability_yaml(dict)` | ✅ used by G13 |
| **Service-RED** artifacts (the error-ratio / duration RED families the legacy generators emit) | `observability.artifact_generator.generate_observability_artifacts(...)` | ✅ exists |
| DashboardSpec → Grafana JSON (the final render the CLI's `generate_dashboard` returns) | `dashboard_creator/` (the `/dbrd-cr8r` pipeline front-ends it) | ✅ exists |
| Canonical HTTP metric family | `observability_fidelity_static.py` (`"http": "http_server_duration"`), `red_taxonomy.py` | ✅ present (see §4 nice-to-have) |

**Conclusion: the convergence is ContextCore-side work.** We map `ProjectContext` → your input, call your
generator, adapt the output to the K8s artifact shapes our operator/CLI callers expect, and delete our
hardcodes. No new capability required from you.

## 3. What we'd like CONFIRMED (a pointer, not a build)

One paragraph from you would save us reverse-engineering the intended entry point:

> **For "a service's declared SLOs (availability, latency-p99) → RED alert rules + a per-service
> dashboard," which entry point is intended?** `generate_observability_artifacts(...)` with a
> `MetricDescriptor`/service context, or `render_domain_*` for the simple-threshold case, or the
> `dashboard_creator` workflow for the dashboard? And what is the minimal input each needs?

The render tail's `metric_thresholds` gives simple `<metric> <op> <value>` alerts — **not** the RED
`error/total` ratio our legacy generators emit — so we suspect the right path for faithful RED parity is
`generate_observability_artifacts` with a descriptor. A confirm/correct is all we need.

## 4. One nice-to-have (optional, non-blocking)

Expose a **stable, importable canonical-metric-convention** — the RED family names (or a helper that
builds the canonical error-ratio / p99 exprs). Today the convention lives across `red_taxonomy.py` +
`observability_fidelity_static.py` with no single import, so a consumer that wants "the canonical HTTP
error-ratio expr" must mirror it. A one-symbol export (e.g. `observability.convention.RED_HTTP` or a
`canonical_red_exprs(service)` helper) would let ContextCore's mapper `import` it instead of duplicating —
closing the drift at the source. **Not required to unblock us; a courtesy that prevents the next
divergence.**

## 5. What we are NOT asking

- Not asking you to build a `ProjectContext` adapter (that mapping is ours).
- Not asking for a new generator, a plugin seam, or a K8s-artifact output mode (we adapt your output).
- Not asking you to change the RED input model.

## 6. Provenance

ContextCore ADR-003 (`docs/adr/003-canonical-observability-generator.md`),
`docs/design/CROSS_CAPABILITY_REUSE_DECISIONS.md` (D4, reversed 2026-08-05), and the Feature/Delivery
Observability G13 generation (`src/contextcore/delivery/generate.py`) which already consumes your render
tail. Tracked ContextCore-side as the "legacy generator convergence" follow-up (ADR-003 pt 3 / the
standing P2 risk in `.contextcore.yaml`).

---

## SDK RESPONSE — 2026-08-05 (startd8-sdk)

**§3 confirmed — your suspicion is right.** For "a service's declared SLOs (availability, latency-p99)
→ faithful **RED** (error/total ratio + duration) alert rules + per-service dashboard," the intended
entry point is **`generate_observability_artifacts(...)` with a resolved `MetricDescriptor`** (via
`observability.metric_descriptor.resolve_descriptor` / `profile_for(...)`), **not** the
`render_domain_*` tail. `render_domain_*` (`metric_thresholds`) is the simple `<metric> <op> <value>`
threshold-alert path (correct for domain gauges); it does **not** emit the RED error-ratio your legacy
generators need. Minimal input to the RED path: a `ServiceHints` (service_id + transport, or an explicit
profile for name-scoped surfaces like Harbor) → `resolve_descriptor` → the generator builds the RED
families. For the final Grafana JSON, the `dashboard_creator` / `/dbrd-cr8r` tail is correct.

**§4 delivered (this note's companion PR).** The canonical RED convention is now a **single import**:
```python
from startd8.observability.convention import canonical_red_exprs, red_http
canonical_red_exprs(descriptor, service_id)   # -> {RedRole.RATE|ERROR|DURATION: <canonical PromQL>}
red_http("my-service")                        # the semconv-HTTP RED, instead of hardcoding http_requests_total{status=~"5.."}
```
`canonical_red_exprs` builds the **same** rate/error/duration shape the artifact generator emits (the
generator now single-sources from it, so they cannot drift), and is FR-4a null-safe (omits a leg the
descriptor can't provide — e.g. no ERROR for Harbor jobservice's no-error-dimension counter, no DURATION
for Harbor core's summary latency). Import it in your mapper instead of mirroring the shape — this closes
the drift at the source, as you asked.
