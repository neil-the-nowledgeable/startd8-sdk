# G3 closed — SDK Perses imported into Dash0 (results + gaps to inform the SDK)

**From:** ContextCore Dash0 pilot (`roles/commerical-solutions-architect/dash0/demo`)
**To:** startd8-sdk / dashboard-vendor-neutrality owners
**Date:** 2026-08-21
**Refs:** `docs/design/dashboard-vendor-neutrality/` (T0 matrix, ADR, TODO), `CLOSURE-LEDGER.md` **CL-8**,
demo's `G3-DASH0-IMPORT-CHECKLIST.md` + `demo-notes/PERSES_DASHBOARD_ORACLE.md`.

## TL;DR — G3 is closed; the SDK's Perses profile works at its first real consumer
The SDK's **bare Perses output imports into Dash0 with zero manual edits and renders live data.** All **14/14**
generated dashboards (13 per-service × 8 panels + business-criticality overview) imported and rendered in the
`dev` dataset. **CL-8 L3 → L4/L5** — vendor-neutral dashboard generation proven at a real backend.

## ✅ What worked (positive, keep as-is)
- **Bare `kind: Dashboard` (Perses v0.54) is import-ready.** Dash0's Dashboards → Create → *Edit as JSON → upload*
  accepts the SDK's exact bare artifact — **no envelope wrap, no edits.**
- **Do NOT emit the CRD envelope.** Round-trip: we uploaded bare `kind: Dashboard`; Dash0 **stored** it as
  `apiVersion: perses.dev/v1alpha1`, `kind: PersesDashboard`, adding `metadata.annotations["dash0.com/folder-path"]`
  itself. So the **bare portable IR is correct** — the consumer supplies its own envelope. Emitting the wrapper
  SDK-side would be wrong.
- **`spec.*` matched the Dash0-stored shape key-for-key** (`display, duration, layouts, panels, variables`);
  `TimeSeriesChart`/`GaugeChart` plugins, `$ref`'d panels, `PrometheusTimeSeriesQuery` — all accepted.

## 🔎 Gaps / improvements to inform the SDK

- **G3-SDK-1 — `--target perses` not in the installed CLI.** `startd8 dashboard create --help` (this env) exposes
  **Grafana only** (`--check`, `--dry-run`, `--provision`, …) — **no `--target perses`** — though
  `startd8.dashboard_creator.perses.emitter` (`emit_perses_dashboard`, `perses_json`) *is* importable. The pilot had
  to call the emitter/golden directly. **Fix direction:** wire `--target {grafana|perses}` into
  `dashboard create` (or confirm #492 does and this env is pre-#492). Without it, the CLI can't emit the artifact G3 needs.

  > **RESOLVED / STALE (verified 2026-08-22, startd8-sdk owner).** `--target perses` **is already on `origin/main`**
  > — `cli_dashboard.py` defines `DashboardTarget.PERSES` and the `--target` option (PR **#492**, merged). The pilot
  > env was **pre-#492**. No SDK work outstanding for G3-SDK-1; the fix is to update the pilot's checkout. Not an open gap.

- **G3-SDK-2 — metric-name convention for Dash0 rendering (the load-bearing one).** To render **live** in Dash0 the
  queries must use Dash0's stored names, which differ from Prometheus-native:
  | Prometheus-native (won't render in Dash0) | Dash0 needs |
  |---|---|
  | `traces_span_metrics_calls_total` | **`traces_span_metrics_calls`** (no `_total`) |
  | `business_criticality` (label) | **`service_criticality`** (Dash0's rendering of `business.criticality`) |
  | `http_server_{request,response}_body_size_bucket` | **…_body_size_`bytes`_bucket** (UCUM `_bytes`) |
  | `$__rate_interval` | a concrete window (e.g. `5m`) — Perses import won't resolve the macro |
  If the SDK emits Prometheus-native names, every panel shows **"No data"** in Dash0. Today the demo applies these as a
  post-gen retarget (`scripts/import_dashboards_dash0.py::retarget`, `tools/METRIC_SCHEMA_MAP.md`). **Fix direction:**
  make this a first-class **Dash0/backend profile** in the SDK (same name-binding class as the earlier
  `CONTEXTCORE_GENERATOR_CONVERGENCE_FINDINGS_DASH0` finding), not a consumer-side hack.

- **G3-SDK-3 — drop conversion artifacts from the native emit.** The oracle exports (Grafana→Perses UI conversion)
  carry **empty `Errors` and `Availability` grids** on the per-service dashboards — visible again on import. These are
  lossy-conversion residue. The **native** Perses profile should emit a clean layout (no empty grids); confirm it does
  and isn't reproducing them.

- **G3-SDK-4 — confirm the Grafana-ism removals are intrinsic to the native profile.** `${datasource}` omitted (Dash0
  supplies it), `histogram` panel → `TimeSeriesChart` (Perses has no histogram viz), unit mapping
  (`ms→milliseconds`, `bytes`, `percentunit→percent-decimal`, req/s→`counts/sec`). PR #490's profile should bake these
  so no consumer retarget is needed; the oracle (`PERSES_DASHBOARD_ORACLE.md §"Grafana → Perses mapping"`) is the checklist.

## Evidence
14/14 imported (Playwright-MCP against `app.dash0.com`, dataset `dev`): screenshots
`Ops/pilot/g3-after-bare-upload.png` (bare golden renders), `Ops/pilot/g3-databearing.png` (live 4-tier criticality),
`Ops/pilot/g3-perservice-shipping.png` (per-service live latency/size/rate). Round-trip re-export confirmed the
`PersesDashboard`/v1alpha1 envelope Dash0 adds on save. Credential-safe path = the authenticated browser session (UI
upload); the app-host has no dashboard-write API — the write API is on `api.<region>.aws.dash0.com` (separate token).

## Net
The SDK's neutral→Perses lowering is **correct and consumer-ready** (bare emit, faithful spec). The remaining SDK work
is **ergonomics + Dash0-fidelity**: expose `--target perses` (G3-SDK-1), bake the Dash0 metric-name profile (G3-SDK-2,
the one that gates *live* rendering), and ensure the native emit is artifact-free (G3-SDK-3/4). None block G3 — they
make "generate → import → renders live" a one-command path instead of a retarget-and-hand-upload.
