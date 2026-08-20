# ADR: Adopt Perses as the vendor-neutral dashboard IR; decouple `dashboard_creator` from Grafana

**Status:** Accepted — bounded adoption · **Date:** 2026-08-19 · **Accepted:** 2026-08-20 by authorized decider proxy
· **Deciders:** startd8-sdk + ContextCore
**Trigger:** vendor-neutrality of observability output declared a first-class priority.

---

## Context

- **Vendor-neutrality is a stated strategic priority** for the observability output.
- **Dashboard generation today is Grafana-coupled.** `dashboard_creator/v2/models.py` builds a *typed construct
  tree* but emits `dashboard.grafana.app/v2` via `to_v2()` (`constructs.py:13`
  `V2_API_VERSION = "dashboard.grafana.app/v2"`; `emitter.py` "assembles the `dashboard.grafana.app/v2`
  envelope"). The model mirrors Grafana's schema. ContextCore's `DerivationRule` treats `dashboard` as a
  derived artifact-kind (`EXPORT_ENRICHMENT_PLAN.md:40`), also Grafana-oriented.
- **Grafana v2 is cleaner than legacy JSON but still vendor-specific.** `dashboard.grafana.app/v2` is Grafana
  Labs' own typed CRD-style schema — a good model, but a Grafana one.
- **The BI/dashboard domain lacked a neutral narrow waist** in our system (per
  `docs/design/requirements-visualization/RESEARCH_implicature-audit-and-the-missing-half-irs.md §3.6`).
  **Perses** — CNCF, multi-vendor governance (Chronosphere · Red Hat · Amadeus), a formal **CUE schema**,
  k8s-CRD + GitOps — is the canonical vendor-neutral dashboard standard.
- **ContextCore is k8s-CRD-native** (`ProjectContext`) and GitOps-oriented — structurally aligned with Perses'
  Dashboard CRD in a way Grafana never was.

## Decision

1. **Adopt Perses' dashboard spec as the canonical portable interchange target** (the narrow waist).
   The in-process source model is a small typed vocabulary, not a separately serialized home-grown standard.
   T0 found that Perses cannot losslessly express every Grafana behavior already emitted; therefore the source
   model distinguishes the portable subset from explicit target capabilities and the Perses lowering fails loud
   on unsupported constructs. See
   [T0_perses-coverage-matrix.md](T0_perses-coverage-matrix.md).
2. **Decouple `dashboard_creator/v2`'s model from `dashboard.grafana.app/v2`.** Extract the neutral construct
   core — portable panel = *viz-kind + typed query + datasource-ref*; explicit position; section;
   dashboard-level static-list variable — from Grafana-specific naming (`viz_config`, `QueryGroup`,
   `AutoGridLayout`). The neutral model becomes the source of truth for portable dashboards. Nested
   tab/section composition, conditional rendering, auto-grid, section-scoped variables, dashboard-list, and
   arbitrary plugin payloads remain explicit Grafana capabilities until a pinned Perses schema provides an
   equivalent. Perses already supports flat tab-to-grid layouts; that capability can be added to the portable
   vocabulary when a pilot needs it.
3. **Emit per-target from the neutral model.** `to_perses()` is the **primary** emitter (validated against
   Perses' CUE schema); `to_v2()` (Grafana) is retained as a **secondary** lowering for Grafana-UI viewing.
   *(Emit-both — Grafana does not import Perses; see boundaries.)*
4. **ContextCore emits Perses Dashboard CRDs** from `DerivationRule` — a CRD→CRD projection native to its worldview.
5. **Use Perses' CUE schema as the dashboard validation oracle** — validate the emitted dashboard at generation
   time (the "verify that can't silently die" for the BI waist; Grafana v2 gives no equivalent gate).
6. **Close useful standard gaps upstream-first.** Track the non-portable capability gaps against Perses and
   contribute generally useful schemas/behaviors where the project is receptive. Upstream contribution is a
   strategic follow-on, not a reason to weaken fail-loud behavior or block the bounded Dash0 pilot. Do not carry
   a private startd8-only Perses fork or compatibility dialect without a separate decision.

## Consequences

**Positive**
- Vendor-neutrality becomes **structural** (one model, N back-ends), not a swap of one lock-in for another.
- The dashboard model goes target-agnostic — the same "define once, project deterministically" pattern as the codegen path.
- A real **validation oracle** (CUE) raises the determinism/verifiability of dashboard generation.
- ContextCore's CRD/GitOps worldview and the Perses Dashboard CRD align natively.
- Fills the BI/dashboard narrow-waist gap named in §3.6.
- Contributing broadly useful missing capabilities can shrink the portability boundary for startd8 and the
  wider Perses ecosystem without creating a private extension standard.

**Negative / costs**
- Real effort: decouple the model + build the Perses lowering + CUE validation. Not a rewrite (the model is
  already typed constructs) but not trivial.
- **Vendor-neutral *generation* ≠ vendor-neutral *viewing*** — to keep Grafana's UI you emit **both** targets
  (two lowerings to maintain).
- The neutral core covers a deliberately bounded **portable subset**. T0 found that generated dashboards do
  use non-portable Grafana capabilities (nested tab/section composition, conditional rendering, auto-grid,
  section-scoped variables, and dashboard-list); they remain supported by the Grafana lowering but are
  rejected by the Perses lowering.
- Perses' rendering/UI ecosystem is younger/smaller than Grafana's.
- Upstream proposals have independent review, design, and release timelines; startd8 delivery cannot assume
  that a contribution will be accepted or available in the pinned release.

**Neutral**
- The Grafana v2 emit path is retained as a secondary lowering — nothing is lost for Grafana consumers.

## Alternatives considered

| Alternative | Verdict |
|---|---|
| Stay Grafana-coupled | **Rejected** — contradicts the vendor-neutrality priority; the coupling is a strategic liability. |
| Swap Grafana → Perses without decoupling | **Rejected** — replaces one vendor lock-in with another; not neutrality. |
| Home-grown serialized neutral dashboard standard | **Rejected** — reinvents Perses. A small typed in-process source model is still required to preserve intent and make unsupported target capabilities explicit. |

## Boundaries / non-goals

- Not achieving vendor-neutral **viewing** (that's emit-both, or the Perses UI).
- Not supporting arbitrary Grafana-plugin panels in the neutral core (portable subset only).
- Not deprecating Grafana output — it's a retained secondary lowering.
- Not silently flattening nested tab/section layouts, materializing auto-grid, promoting section variables,
  dropping conditions, or replacing dashboard-list. Those require an explicit product-level fallback decision.
- Not maintaining a private Perses fork, startd8-only schema dialect, or downstream patch queue as part of this
  decision. Any exception requires its own ownership, compatibility, and exit-plan decision.

## Migration approach (the decoupling, behavior-preserving)

1. **Freeze the neutral construct vocabulary** (the portable subset) as the model's core.
2. **Reframe `to_v2()` as a Grafana *lowering*** off that core — existing Grafana output stays **byte-identical**
   (a golden test guards it).
3. **Add `to_perses()` + CUE validation.**
4. **ContextCore:** add Perses Dashboard CRD as a `DerivationRule` output-kind.
5. **Golden-test both lowerings** from shared fixtures (one neutral model → {Grafana v2, Perses} both valid).
6. **Upstream contribution lane:** inventory existing Perses issues/RFCs for each gap, submit minimal generic
   proposals where appropriate, and adopt accepted capabilities only after they ship in a pinned release and
   pass the same CUE + Dash0 verification gates.

## Open question to resolve first (de-risk before decoupling)

**Resolved by T0 and accepted on 2026-08-20:** only the bounded portable subset is covered. The complete matrix
and go/no-go criteria are in [T0_perses-coverage-matrix.md](T0_perses-coverage-matrix.md). Implementation may
proceed through the bounded core, Perses lowering, and Dash0 pilot. A Perses emitter must reject unsupported
capabilities rather than silently change them; useful gaps should be pursued with Perses upstream in parallel.
