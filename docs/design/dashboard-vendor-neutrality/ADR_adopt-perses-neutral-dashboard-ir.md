# ADR: Adopt Perses as the vendor-neutral dashboard IR; decouple `dashboard_creator` from Grafana

**Status:** Proposed · **Date:** 2026-08-19 · **Deciders:** startd8-sdk + ContextCore
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

1. **Adopt Perses' dashboard spec AS the vendor-neutral dashboard IR** (the narrow waist). Do **not** invent a
   home-grown neutral IR — adopt the existing CNCF standard.
2. **Decouple `dashboard_creator/v2`'s model from `dashboard.grafana.app/v2`.** Extract the neutral construct
   core — panel = *viz-kind + query + position*; variable; datasource-ref; section — from Grafana-specific
   naming (`viz_config` kind names, `AutoGridLayout`). The neutral model becomes the **source of truth**.
3. **Emit per-target from the neutral model.** `to_perses()` is the **primary** emitter (validated against
   Perses' CUE schema); `to_v2()` (Grafana) is retained as a **secondary** lowering for Grafana-UI viewing.
   *(Emit-both — Grafana does not import Perses; see boundaries.)*
4. **ContextCore emits Perses Dashboard CRDs** from `DerivationRule` — a CRD→CRD projection native to its worldview.
5. **Use Perses' CUE schema as the dashboard validation oracle** — validate the emitted dashboard at generation
   time (the "verify that can't silently die" for the BI waist; Grafana v2 gives no equivalent gate).

## Consequences

**Positive**
- Vendor-neutrality becomes **structural** (one model, N back-ends), not a swap of one lock-in for another.
- The dashboard model goes target-agnostic — the same "define once, project deterministically" pattern as the codegen path.
- A real **validation oracle** (CUE) raises the determinism/verifiability of dashboard generation.
- ContextCore's CRD/GitOps worldview and the Perses Dashboard CRD align natively.
- Fills the BI/dashboard narrow-waist gap named in §3.6.

**Negative / costs**
- Real effort: decouple the model + build the Perses lowering + CUE validation. Not a rewrite (the model is
  already typed constructs) but not trivial.
- **Vendor-neutral *generation* ≠ vendor-neutral *viewing*** — to keep Grafana's UI you emit **both** targets
  (two lowerings to maintain).
- The neutral IR covers the **portable subset** (standard panels/queries) — exotic Grafana plugins are out of
  scope (acceptable for *generated* dashboards, which don't use them).
- Perses' rendering/UI ecosystem is younger/smaller than Grafana's.

**Neutral**
- The Grafana v2 emit path is retained as a secondary lowering — nothing is lost for Grafana consumers.

## Alternatives considered

| Alternative | Verdict |
|---|---|
| Stay Grafana-coupled | **Rejected** — contradicts the vendor-neutrality priority; the coupling is a strategic liability. |
| Swap Grafana → Perses without decoupling | **Rejected** — replaces one vendor lock-in with another; not neutrality. |
| Home-grown neutral dashboard IR | **Rejected** — reinvents a standard that exists (Perses); a framework-for-single-use (accidental complexity). |

## Boundaries / non-goals

- Not achieving vendor-neutral **viewing** (that's emit-both, or the Perses UI).
- Not supporting arbitrary Grafana-plugin panels in the neutral IR (portable subset only).
- Not deprecating Grafana output — it's a retained secondary lowering.

## Migration approach (the decoupling, behavior-preserving)

1. **Freeze the neutral construct vocabulary** (the portable subset) as the model's core.
2. **Reframe `to_v2()` as a Grafana *lowering*** off that core — existing Grafana output stays **byte-identical**
   (a golden test guards it).
3. **Add `to_perses()` + CUE validation.**
4. **ContextCore:** add Perses Dashboard CRD as a `DerivationRule` output-kind.
5. **Golden-test both lowerings** from shared fixtures (one neutral model → {Grafana v2, Perses} both valid).

## Open question to resolve first (de-risk before decoupling)

Does Perses' CUE schema **cover the construct vocabulary `dashboard_creator/v2` actually emits**? Map the model's
panel/query/variable/layout kinds against the Perses schema and confirm the portable subset is complete for our
*generated* dashboards. If a gap exists, it bounds the decision; if not (likely, since we emit standard panels),
the decoupling is safe. *(This is the cheap first step in the next-steps plan.)*
