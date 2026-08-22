# REQ — Dash0 backend metric-name profile for Perses dashboards (G3-SDK-2)

**Status:** Draft · **Date:** 2026-08-22 · **Owner:** startd8-sdk dashboard-vendor-neutrality
**Source:** `docs/G3_DASH0_PERSES_IMPORT_RESULTS_2026-08-21.md` finding **G3-SDK-2** (the load-bearing one) ·
**Ledger:** `CLOSURE-LEDGER.md` **CL-8** (L4→L5 residual) · **Depends on:** merged Perses lowering (#490/#492/#493)

## Context & the gap (grounded)

G3 proved the SDK's bare Perses artifact **imports** into Dash0 with zero edits. But it only renders **live**
data if the queries use **Dash0's stored metric names**, which differ from Prometheus-native. Today the emitter
passes the query expression through **verbatim** — `perses/emitter.py::_query` emits `query.expression` unchanged
(no name/label/unit/macro rewriting). So a dashboard authored against Prometheus-native names shows **"No data"**
in Dash0 on every panel.

The pilot works around this **consumer-side** (`scripts/import_dashboards_dash0.py::retarget` +
`tools/METRIC_SCHEMA_MAP.md`). This REQ makes it a **first-class, in-SDK backend profile** so
"generate → import → renders live" is one command, not a retarget-and-hand-edit.

### The observed name deltas (Prometheus-native → Dash0-stored)

| Prometheus-native (won't render in Dash0) | Dash0 needs | Transform class |
|---|---|---|
| `traces_span_metrics_calls_total` | `traces_span_metrics_calls` | metric-suffix drop (`_total`) |
| `business_criticality` (label) | `service_criticality` | label rename |
| `http_server_{request,response}_body_size_bucket` | `…_body_size_bytes_bucket` | UCUM unit-suffix insert (`_bytes`) |
| `$__rate_interval` | concrete window (e.g. `5m`) | macro resolution |

## Design principle (keep the neutrality thesis intact)

The neutral model stays **backend-agnostic** — it must NOT carry Dash0 names. The transform is a **target-backend
profile** applied *during/after the Perses lowering*, exactly mirroring the "neutral IR → per-target lowering"
shape the whole subsystem is built on. Dash0 is the **first** backend profile; the seam is general
(`BackendProfile`), so a future Mimir/Thanos/other profile is a new instance, not a rewrite.

```
neutral Dashboard ──emit_perses_dashboard(backend_profile=DASH0)──▶ Perses JSON with Dash0-stored names
                     (default backend_profile=None → today's byte-identical output)
```

## Functional requirements

- **FR-D0-1 — Optional, additive, byte-identical-when-absent.** `emit_perses_dashboard(..., backend_profile=None)`
  is **unchanged** (SOTTO). The profile only engages when explicitly requested (`--backend dash0` / API arg).
- **FR-D0-2 — Declared name map, not heuristics.** Metric-name rewrites come from a **reviewed, declared map**
  (the in-SDK analogue of `tools/METRIC_SCHEMA_MAP.md`), not fuzzy matching. Unmapped names pass through unchanged
  (a rename is opt-in per entry), and the profile can be asked to **fail loud** on a name it was told to expect but
  can't map (guarded mode) vs pass-through (lenient) — default lenient with a logged report of what it rewrote.
- **FR-D0-3 — Four transform classes** (from the table): (a) metric-suffix drop (`_total`), (b) label rename,
  (c) UCUM unit-suffix insert (`_bytes`), (d) `$__rate_interval` (and `$__interval`) → a configurable concrete
  window (default `5m`). Each applies to the PromQL **expression string** in `Query.expression`.
- **FR-D0-4 — Macro resolution is explicit + reported.** Replacing `$__rate_interval` with a fixed window is a
  **semantic change** (adaptive → fixed); it must be logged, the window must be configurable, and it only fires
  under the Dash0 profile.
- **FR-D0-5 — CLI surface.** `startd8 dashboard create <obs.yaml> --target perses --backend dash0` (default
  `--backend none`). `--check` validates the profiled output against the CUE oracle too.
- **FR-D0-6 — Still CUE-valid.** Profiled output MUST still pass `validate_perses_dashboard` (the transform is
  name-level; it must not break Perses schema conformance).
- **FR-D0-7 — Label-name single-source cross-check.** `business_criticality`→`service_criticality` is the SAME
  label the collector-enrichment path emits. The dashboard query name and the enrichment OTTL output must agree —
  reference the enrichment convention, do not fork a second spelling. (Cross-repo: ties to the
  `CONTEXTCORE_GENERATOR_CONVERGENCE_FINDINGS_DASH0` finding.)

## Implementation plan (reflective pass)

1. **`perses/backend_profile.py`** — `BackendProfile` protocol + `DASH0_PROFILE`: a declared `metric_renames`
   map, `label_renames` map, `unit_suffix` rules, `macro_windows`. Pure string transform over a PromQL expression.
2. **Thread through `emit_perses_dashboard`** — new `backend_profile: Optional[BackendProfile] = None`; applied to
   each `Query.expression` inside `_query` before emit. Absent → current code path untouched (guard test).
3. **CLI** — add `--backend {none,dash0}` to `dashboard create` (only meaningful with `--target perses`).
4. **Golden tests** — one neutral fixture → {none (byte-identical to today), dash0 (retargeted names)} both CUE-valid;
   a parity test proving `backend=none` is byte-identical to the pre-change golden.
5. **Port the map** — seed `DASH0_PROFILE` from the demo's `tools/METRIC_SCHEMA_MAP.md` (ground each entry).

## Reflection — what the planning pass surfaced (fold back before coding)

- **PromQL string-rewrite is fragile.** Rewriting inside a raw PromQL string risks partial matches (e.g. a metric
  name that is a substring of another). Mitigation: token-boundary-aware replacement, and the declared-map approach
  bounds the blast radius. **Open question:** is a light PromQL tokenizer worth it, or is boundary-regex enough for
  the generated (not hand-authored) query shapes? Lean regex-with-word-boundaries first; revisit if a collision appears.
- **`$__rate_interval` fixed window is lossy.** A fixed `5m` loses Grafana's adaptive interval. Acceptable for
  *generated* dashboards, but must be **configurable + logged** (FR-D0-4), never silent.
- **Is this Dash0-specific or general?** The four transform classes are generic; only the *map contents* are Dash0's.
  Ship the general `BackendProfile` seam + the Dash0 instance (avoids a Dash0-only dialect; matches the ADR's
  "adopt a standard, don't fork" posture).
- **FR-D0-7 is the real single-source risk.** If the dashboard renames `business_criticality`→`service_criticality`
  but the enrichment OTTL emits a different spelling, panels still show no data. The rename must be sourced from the
  **same** convention both sides read — otherwise we've just moved the drift. Flag for a cross-repo grounding check
  against `collector_enrichment` before coding.

## Non-goals

- Not baking Dash0 names into the **neutral model** (stays backend-agnostic).
- Not a general PromQL rewriter/optimizer — only the four declared transform classes.
- Not vendor-neutral *viewing*; this is about one backend (Dash0) rendering the generated output.
- Not G3-SDK-3/4 (empty-grid / Grafana-ism cleanup) — tracked separately, though same profile PR may touch them.

## Acceptance

- `startd8 dashboard create <obs.yaml> --target perses --backend dash0` emits a CUE-valid Perses dashboard whose
  queries use Dash0-stored names; imported into Dash0 it **renders live data with no consumer-side retarget**.
- `--backend none` output is **byte-identical** to today's (golden parity guard).
- The rewrite report lists every transform applied; `$__rate_interval` resolution is logged with the window used.
