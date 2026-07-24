# Per-signal_kind grounded threshold defaults (#229 residual / #226 FR-7 completion) — Requirements

**Version:** 0.3.1 (post planning + lessons + design-principle hardening; ready for CRP)
**Date:** 2026-07-23
**Status:** Draft — spec only, no code
**Owner:** observability artifact generator (`src/startd8/observability/`)
**GitHub:** #229 (the residual values-grounding task) · completes #226 FR-7 (compose the `signal_kind`
axis onto the #234 criticality × deployment_mode table)
**Refs:** `config/importance_thresholds.yaml`, `_select_importance_default`/`_resolve_threshold`
(`artifact_generator_generators.py`), the #300-D2/#308 threshold-deferral discipline

---

## 0. Planning Insights (Self-Reflective Update)

> Ground: read `importance_thresholds.yaml`, `_resolve_threshold`, `_FUNCTIONAL_SLI_TEMPLATES`, and the
> generate_functional_slos target-requirement. The naïve draft ("fill in per-kind threshold values") hit
> the OQ-5 honesty wall and split into a *mechanism* deliverable + a *grounded-values* subset.

| v0.1 Assumption | Planning Discovery | Impact |
|---|---|---|
| Fill all per-signal_kind cells (freshness/queue_depth/lag/retry_rate/saturation/run_success) with values. | `_FUNCTIONAL_SLI_TEMPLATES` shows the **units** (`saturation`=percentunit, `freshness`=s, `queue_depth`/`lag`=count, `run_success`=ratio). Only **saturation** (SRE-canonical ~0.8) and **run_success** (availability-analog ~0.99) can be grounded WITHOUT a live run; freshness/queue_depth/lag/retry_rate magnitudes are **app-specific** and would be **invention** (OQ-5 forbids). | **Split (FR-2/FR-3):** fill the SRE-groundable cells now; ship the app-specific cells as **grounding-pending** (resolution DEFERS — never a fabricated magnitude). This is exactly OQ-5's "ship the table shape, don't invent values." |
| The table already scales by deployment_mode, so per-kind cells inherit it. | The table is `<criticality>.<deployment_mode>.{availability, latency_p99}` — **only two fields**; `_select_importance_default(business, field_name)` keys by `field_name`, so a `signal_kind` is just a new field name that composes for free. | **FR-1 is additive**: add `signal_kind` keys as new fields under each `<crit>.<mode>` cell; `_select_importance_default` needs **no structural change** — pass the signal_kind as `field_name`. |
| Functional SLOs already resolve a default. | `generate_functional_slos` **requires `fr.target`** (`:1840`); no target ⇒ `unfulfilled` (`:1848`). No per-signal_kind default is ever resolved today. | **FR-4:** insert a resolution step (author target > grounded config cell > defer) before `unfulfilled`; same for the declared-functional (#300 D2) and probe (#308) threshold-deferral. |
| A config default contradicts #300-D2/#308 NR-1 "no invented threshold." | NR-1 forbids **per-call invention**; the criticality/latency defaults are already resolved from a **single-sourced, overridable, grounded table** — that is NOT invention. | **The config table IS the grounding seam.** NR-1 is refined to "no per-call invention; the grounded table is the single source." A config cell resolves; an absent/grounding-pending cell still defers. |
| "Grounded" means measured from a live Mastodon run. | The live magnitudes need P2-live (external). What IS grounded here: the **declared kickoff inputs** — `criticality` (`artifact_generator_context.py:535`) and `deployment_mode` (`spec.deployment.mode`, `:538`) — plus each kind's **unit**. | Ground the values in **declared context + unit + SRE standard**, and provenance-tag them honestly; NEVER claim a live-measured magnitude. Live-pilot magnitudes = the follow-up when P2-live runs. |

**Resolved OQ:** #229 OQ-5 → *ship the shape + the SRE-groundable cells; app-specific cells are grounding-pending (defer, not invent).*

### 0.1 Lessons-Learned Hardening (v0.3)
- **Phantom-reference audit** — verified: `importance_thresholds.yaml` structure, `_select_importance_default`
  (`:57`), `_resolve_threshold` (`:146`, returns `(value, tier)`), `_FUNCTIONAL_SLI_TEMPLATES` (`:1042`),
  the `generate_functional_slos` target gate (`:1840`), `business.{criticality, deployment_mode,
  importance_thresholds}`. Added §9.
- **[preserve-declared-intent]** — an author `fr.target` always wins over a config default (no producer-side
  override of declared intent).
- **Single-source vocabulary ownership** — the VALUES live only in `importance_thresholds.yaml`; the binder
  cites `_resolve_threshold`, never restates a magnitude. The units are owned by `_FUNCTIONAL_SLI_TEMPLATES`.

### 0.2 Design-Principle Hardening (v0.3.1)
- **Genchi Genbutsu / not-fabrication** — values are grounded in *declared* context (criticality/mode) + unit
  + SRE standard; app-specific magnitudes are left **grounding-pending**, not invented. Provenance is tagged.
- **Hitsuzen (derive the determinable)** — the criticality×mode *scaling* is deterministic; only the app-
  specific *anchor* is undetermined, so it defers. Nothing is LLM-generated.
- **Accidental-Complexity anti-principle** — no new resolution engine; reuse `_select_importance_default`'s
  field-name keying. The signal_kind axis is *data* in the YAML, not code.
- **Monotonicity (the table's existing invariant, FR-2a)** — the new cells preserve it: raising criticality
  and/or moving installed→deployed never loosens a bound (saturation non-increasing, run_success non-
  decreasing, etc.).

---

## 1. Problem Statement

`_DEFAULT_THRESHOLDS` (`availability=99 / latency_p99=500ms / throughput=100rps`) is the flat fallback for
**every** signal kind. For a worker/batch/ML/cron service these are category errors (#229): a Sidekiq
worker's saturation SLO falls back to `100rps`; a freshness SLO to `500ms`. The criticality × deployment_mode
table (#234) fixed availability/latency but **only those two fields** — the functional signal kinds
(saturation/freshness/queue_depth/retry_rate/lag/run_success) have no grounded default and either take an
explicit `fr.target` or become `unfulfilled`. #226 FR-7 promised the composed `criticality × signal_kind`
table; this completes it, honestly (OQ-5).

## 2. Requirements

**FR-1 — Add a `signal_kind` axis to the threshold table (additive).** Extend
`importance_thresholds.yaml`: under each `<criticality>.<deployment_mode>` cell, add the functional
signal_kind keys as new fields (unit-correct). `_select_importance_default(business, signal_kind)` resolves
them with **no structural change** (the signal_kind is a field name). Non-request kinds only; `throughput`
stays flat (a capacity fact, per the existing FR-2b decision).

**FR-2 — Fill the SRE-groundable cells now (grounded, not invented).**
- **`saturation`** (percentunit): the SRE-canonical utilization bound — e.g. `deployed high` ≈ `0.8`,
  loosening for lower criticality / `installed` (per the monotonic scale). Grounded in SRE standard.
- **`run_success`** (ratio): an availability-analog — e.g. `deployed high` ≈ `0.99`, scaling like
  availability. Grounded in the same logic as the availability column.
Each carries a `# grounded: SRE-standard | availability-analog` provenance comment.

**FR-3 — App-specific cells are grounding-pending (defer, never invent).** `freshness` (s),
`queue_depth`/`lag` (count), `retry_rate` (rate) have **app-specific magnitudes** that this repo cannot
ground without a live run. Ship these keys **present but null/omitted** (a `grounding_pending` marker), so
`_select_importance_default` returns `None` and the caller **defers** (as today) — no fabricated value. The
table shape is ready; a grounded pilot or an author override fills them.

**FR-4 — Resolve the per-signal_kind default in the binders (author > grounded cell > defer).** In
`generate_functional_slos` (before `unfulfilled`), and in the declared-functional (#300 D2) and probe (#308)
threshold-deferral, resolve `_resolve_threshold(signal_kind, business, …)`: an author `fr.target`/series
`target` wins; else a grounded config cell binds a graded SLO; else defer/threshold-defer exactly as today.
The resolution tier (`manifest` / `default:importance` / `default` / `deferred`) is recorded (traceability).

**FR-5 — Deployment-mode scaling applies to the new cells.** `installed` (a local single-user tool) gets a
forgiving band; `deployed` the criticality scale — the same pattern the availability/latency cells already
use, so a freshness/saturation SLO for a locally-installed app isn't held to production magnitudes. *(The
user's "leveraging deployed mode".)*

**FR-6 — Honesty / provenance.** No per-call invention; a resolved value's tier is surfaced (as
`_resolve_threshold` already returns). The YAML header documents that saturation/run_success are grounded
(SRE/availability-analog) and freshness/queue_depth/lag/retry_rate are **grounding-pending** — live-pilot
magnitudes are the follow-up (P2-live). A CHANGELOG/comment names the provenance of every filled cell.

## 3. Non-Requirements

**NR-1 — No invented app-specific magnitudes.** freshness/queue_depth/lag/retry_rate stay grounding-pending
until a live pilot or an author fills them. (Genchi Genbutsu / OQ-5.)
**NR-2 — `throughput` stays flat** (capacity fact; existing FR-2b decision, not touched).
**NR-3 — Author target always wins** — no config default overrides a declared `fr.target`/series `target`.
**NR-4 — Byte-identical when no functional kinds** — a request-only service (RED-only) resolves exactly as
today; the new YAML keys don't touch availability/latency/throughput resolution.
**NR-5 — No new resolution engine / no project-scoped AI kinds** — `llm_cost_per_request`/`token_throughput`/
`context_saturation` are project-scoped (out of scope; separate thresholds).

## 4. Open Questions

- **OQ-1 — saturation/run_success exact scale cells.** The anchor (deployed-high 0.8 / 0.99) is SRE-standard,
  but the per-criticality/mode ladder (does `low installed` saturation go to 0.95? 0.9?) needs a monotonic
  fill — confirm the ladder in CRP against the existing availability/latency ladders.
- **OQ-2 — the `grounding_pending` marker shape.** A YAML `null`, an explicit `grounding_pending: true`, or
  simply omit the key (so `.get()` returns None)? Lean: omit → `None` → defer (simplest, no parser change).
- **OQ-3 — should FR-4 bind functional SLOs from a config default change #300-D2/#308 shipped behavior?**
  Yes for saturation/run_success (they now have a grounded cell → bind instead of defer); freshness etc.
  still defer (no cell). Confirm this is the intended, welcome behavior change (more SLOs bind, all grounded).

## 9. Reference Audit

| Symbol / fact | Location | Exists? |
|---|---|---|
| `importance_thresholds.yaml` (`<crit>.<mode>.{availability,latency_p99}`) | `observability/config/` | ✅ (extend) |
| `_select_importance_default(business, field_name)` (keys by field) | `artifact_generator_generators.py:57` | ✅ (reuse) |
| `_resolve_threshold` → `(value, tier)` | `:146` | ✅ |
| `_FUNCTIONAL_SLI_TEMPLATES` (units per kind) | `:1042` | ✅ |
| `generate_functional_slos` target gate → `unfulfilled` | `:1840/:1848` | ✅ (change locus) |
| `business.criticality` / `deployment_mode` (kickoff inputs) | `artifact_generator_context.py:535/538` | ✅ |
| declared-functional / probe threshold-deferral | `generate_declared_functional_slos` / `generate_declared_probe_slos` | ✅ (FR-4 sites) |

---

*v0.3.1 — Post planning + lessons + design-principle hardening. 6 assumptions corrected; the honest split
(SRE-grounded now vs app-specific grounding-pending) resolves OQ-5. 6 FRs / 5 NRs / 3 OQs. Ready for CRP.*
