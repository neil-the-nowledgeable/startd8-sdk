# ContextCore Objective `serves` Edge (Value-Lineage Rollup, EB-4) — Requirements

> ⚠️ **CROSS-REPO PROPOSAL — authored from the navig8r (startd8-sdk) side, owned by ContextCore.**
> This is a **proposal to hand to the ContextCore owner**, not an SDK build item. It proposes a
> change to *their* `ContextManifest` model. **Validate every file:line citation against the live
> ContextCore tree before building** — the citations below are grounded as of 2026-08-17 but this
> doc is a *belief artifact* about another repo (see [[feedback_cross_repo_handoff_grounding]]).
> **Owner: ContextCore.** Home for the build: `~/Documents/dev/ContextCore/`.

**Project:** ContextCore (proposed by startd8-sdk / navig8r)   **Criticality:** medium
**Version:** 0.1   **Date:** 2026-08-17
**Format:** det-req/0.1
**Backend:** python-data-store
**Pairs with:** `PM_FINDINGS_contextcore-o11y-value-lineage.md` (the grounded survey this specs)
**Inherits standards:** det-req-kit · NODE-SCHEMA (Category facet §1a; derivation edge) · ContextCore `ContextManifest` correct-by-construction validation conventions
**Audience:** operator
**Trust boundary:** ContextCore manifest models only (Pydantic); no network; no new evaluator engine
**Data classification:** internal

> **Readable handle:** `feature/contextcore-objective-serves-edge`
> **Semantic name:** *ContextCore Objective gains an optional `serves` derivation edge so a feature/delivery objective can declare which business objective it serves, turning the flat category list into a validated, cycle-free value lineage (business ← feature ← agent) read by a rollup over the existing business engine — the reference shape is the navig8r Node's `serves`/`child_keys`/DerivationEdge, and the shipped business/delivery/agent boards are untouched.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-contextcore-objective-serves-edge`

---

## 0. Planning Insights (grounded, file:line)

> Grounded against the **live ContextCore tree** (`~/Documents/dev/ContextCore/`) and the navig8r
> reference model (`~/Documents/dev/startd8-sdk/src/startd8/navigator/models.py`) on 2026-08-17.
> The full survey is `PM_FINDINGS_contextcore-o11y-value-lineage.md`; the load-bearing facts:

| # | Grounded fact (file:line) | Impact on this spec |
|---|---------------------------|---------------------|
| 1 | `Objective` = `{ id, description, category, metric?, target?, key_results[] }` — **no** `parent`/`serves`/`rollup`/`children` field (`ContextCore/src/contextcore/models/manifest.py:455-489`) | FR-1 = **add one optional field** to this exact model; additive, default `None` |
| 2 | `KeyResult` (`:343-400`) has **no** link/parent field either | FR-2 (optional) may add the finer-grained KR-level edge; default is the Objective-level edge (FR-1) |
| 3 | `objectives_by_category()` is a **flat filter** over `self.objectives` by the `category` string (`:929-942`) | The rollup read (FR-5) composes *over* this flat selector; it does **not** replace it |
| 4 | `category` is documented as *"Node taxonomy Category facet (dev-os/NODE-SCHEMA §1a)"* (`:461-472`, constant `:53`); values `business_observability` (`:61`) / `delivery_observability` (`:69`) | The `serves` edge is the **derivation edge** the Node schema pairs with the Category facet; adding it closes the NODE-SCHEMA gap the PM found |
| 5 | `Objective.id` is validated against `OBJECTIVE_ID_PATTERN = ^OBJ-[A-Z0-9-]+$` (`:43`, `:491-500`) | FR-3 validates the `serves` target against the **same** `OBJECTIVE_ID_PATTERN` shape before existence |
| 6 | Manifest-level cross-reference existence checks live in `ContextManifest.validate_cross_references()` (`:856-897`) — it already builds `objective_ids = {obj.id for obj in self.objectives}` and raises on unknown refs | FR-3 = **extend this existing validator**, reusing its `objective_ids` set; the correct-by-construction home already exists |
| 7 | The pace/rollup engine is `business/evaluator.py:evaluate_objective_pace` / `evaluate_keyresult_pace` returning `PaceKeyResultStatus` rows (`ContextCore/src/contextcore/business/evaluator.py`), rendered by `business/board.py` | FR-5 rollup **reuses** these; NO new evaluator — the read walks the edge and calls the existing evaluator per objective |
| 8 | feature o11y is spec'd as a *"delivery-facet **sibling** of Business Observability on the same engine"* and the rollup is deferred to **EB-4** (`ContextCore/docs/design/requirements/REQ_FEATURE_OBSERVABILITY.md:9,16,36`) | This spec **is** EB-4 — the one missing edge that turns the sibling into a descendant |
| 9 | The proven edge shape: navig8r `Node` carries `child_keys: Tuple[str,...]` (DEPENDS-ON) + a typed `DerivationEdge` (`from_key`/`relation`/`regime`) with `EdgeRelation.DERIVED_FROM` (`startd8-sdk/src/startd8/navigator/models.py:87-114,118-145`); `serves` rides the open `attributes` bag today (`:135,215`) | FR-1 **adopts this shape** — a typed, directional, cycle-free derivation edge — rather than inventing a new one |

**Resolved framing (from the PM survey):**
- **The gap is structural, not a mislabel.** Feature o11y's parent is *absent*, not mis-set; adding the edge is the whole fix (PM §3).
- **`serves` is a derivation edge, the coin's other side.** It traces "this agent-produced, deterministically-grounded feature → serves this business outcome" (PM §4.3). It is the exact edge the Node model already defines.
- **No engine change.** The rollup is a *read* over the existing `business/` evaluator; the flat boards keep working (NR-1).

**Open questions (for the ContextCore owner to resolve before build):**
- **OQ-1 — Objective-level vs KeyResult-level edge.** Default here is an **Objective-level** `serves` (FR-1); a finer KR→KR edge (FR-2) is optional/deferred. Confirm the coarser edge suffices for the value chain.
- **OQ-2 — relation vocabulary.** This spec uses a single relation value `serves`. Confirm ContextCore wants only `serves` (vs a small enum like the navig8r `EdgeRelation`); if an enum, name it once (do not fork per call site).
- **OQ-3 — is EB-4 still open + is the model unchanged?** Re-confirm against the live tree; if `Objective` already grew a link field, this spec is superseded.

## Objectives

- O-1: A ContextCore manifest author can declare that one `Objective` **serves** another (parent) `Objective`, so a feature/delivery goal names the business goal it rolls up to — target: an additive optional field on `Objective` that defaults `None` and leaves existing manifests byte-identical.
- O-2: The edge is **correct-by-construction** — the `serves` target must be a real objective id and the graph must be acyclic — target: loading a manifest with a dangling or cyclic `serves` raises a named `ValueError` at validation time.
- O-3: An operator can **read the value lineage** (business ← feature ← agent) as a rollup that reuses the existing business pace engine — target: a rollup read walks the `serves` edges and returns per-objective pace status with **no** new evaluator.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | Cross-repo drift: the cited `manifest.py` lines move or the model already changed | Re-ground every FR against the live ContextCore tree before build (OQ-3); this doc is a belief artifact | high |
| quality | A `serves` cycle silently creates an infinite rollup walk | FR-4: cycle detection in `validate_cross_references` raises before any read; the rollup never runs on an invalid manifest | high |
| quality | Adding a field drifts existing manifests / breaks round-trip | FR-6: field is optional, default `None`, `exclude_none` on dump; a golden asserts existing manifests serialize byte-identical | high |
| scope-creep | Rebuilding a rollup engine instead of reading over the business one | FR-5 reuses `evaluate_objective_pace`; NR-4 forbids a new evaluator | medium |
| scope-creep | Changing the shipped business/delivery/agent boards | NR-1: this spec only *adds* the edge + a rollup read; the flat boards are untouched | medium |

## Profile

Declared profile: **internal**

## Functional requirements

- **FR-1 — Optional `serves` edge on Objective.** `Objective` gains an optional `serves: Optional[str]` field (alias `serves`) naming the id of the parent objective this one rolls up to, defaulting `None` so it is additive and every existing objective is unchanged. Name: ContextCore Objective carries an optional serves field naming the parent business objective it rolls up to, adopting the navig8r Node derivation-edge shape. Touches: `store`, `table`, `repository`. Verify: an `Objective` constructed with `serves="OBJ-REVENUE"` exposes `.serves == "OBJ-REVENUE"`, and one constructed without it exposes `.serves is None`. Serves: O-1
- **FR-2 — Optional KeyResult-level serves (deferred default).** The finer-grained edge — a `KeyResult` naming the parent `KeyResult` it serves — is spec'd as an OPTIONAL follow-on (`KeyResult.serves: Optional[str]`, default `None`); the shipped default lineage is the Objective-level edge (FR-1), so KR-level is off unless OQ-1 selects it. Name: ContextCore KeyResult optionally carries a serves field for a finer key-result-level lineage, deferred behind the objective-level edge as the default. Touches: `store`, `table`. Verify: with OQ-1 unresolved, `KeyResult` has no required `serves`; when the follow-on lands, `KeyResult(serves="...")` round-trips and absent leaves `.serves is None`. Serves: O-1
- **FR-3 — Target-existence validation (correct-by-construction).** `ContextManifest.validate_cross_references()` is extended so that for every objective carrying a non-null `serves`, the referenced id must be present in the manifest's `objective_ids` set and must match `OBJECTIVE_ID_PATTERN`; an unknown or malformed target raises the existing named `ValueError`. Name: ContextManifest validate_cross_references rejects an objective whose serves target is not a real objective id, reusing the existing objective-id set and pattern. Touches: `store`, `repository`. Verify: a manifest with an objective `serves="OBJ-GHOST"` (no such objective) raises `ValueError` naming the unknown reference; a manifest whose `serves` points at a present objective loads cleanly. Serves: O-2
- **FR-4 — Acyclicity validation (no cycles in the lineage).** The same validator detects any cycle among the `serves` edges (an objective reachable from itself by following `serves`) and raises a named `ValueError`; a self-`serves` (an objective naming its own id) is the degenerate cycle and is likewise rejected. Name: ContextManifest validation rejects any cycle in the serves lineage so the value chain is a finite acyclic rollup. Touches: `store`, `repository`. Verify: a manifest where `OBJ-A` serves `OBJ-B` and `OBJ-B` serves `OBJ-A` raises `ValueError` naming the cycle; a self-serving objective (`OBJ-A` serves `OBJ-A`) also raises. Serves: O-2
- **FR-5 — Value-lineage rollup read (reuse the business engine).** A read helper walks the `serves` edges upward from a leaf objective to its business root and returns per-objective pace status by calling the EXISTING `business/evaluator.py:evaluate_objective_pace` for each objective on the path — no new evaluator, no change to `PaceKeyResultStatus`. Name: ContextCore exposes a serves-lineage rollup read that walks the parent chain and reuses evaluate_objective_pace per objective without a new engine. Touches: `query`, `repository`. Verify: given `agent-obj serves feature-obj serves business-obj`, the rollup returns three pace statuses (one per objective) each produced by an existing `evaluate_objective_pace` call, in leaf→root order. Serves: O-3
- **FR-6 — Additive byte-identity for existing manifests.** The field is optional with `None` default and excluded on serialization when unset (`exclude_none`), so a manifest authored before this change serializes byte-identically and re-parses unchanged. Name: existing ContextCore manifests round-trip byte-identically because the serves field is optional and omitted when unset. Touches: `store`, `migration`. Verify: a fixture manifest with no `serves` on any objective dumps to the same bytes before and after the schema change (`model_dump(by_alias=True, exclude_none=True)` unchanged); no new keys appear. Serves: O-1
- **FR-7 — Flat category selectors unchanged.** `objectives_by_category()`, `business_objectives()`, and `delivery_objectives()` keep returning the flat filtered lists they return today; the rollup (FR-5) is a separate read that composes over them and does not alter their signatures or output. Name: the existing flat category selectors return identical results after the serves edge is added, with the rollup layered separately on top. Touches: `query`, `repository`. Verify: `objectives_by_category("delivery_observability")` returns the same objective list before and after the change for a fixture manifest; its signature is unchanged. Serves: O-3

## Non-goals

- NR-1: Changing the shipped business, delivery, or agent boards — this spec only adds the optional edge + a rollup *read*; every existing board keeps rendering unchanged.
- NR-2: A new `category` value or a `deterministic_observability` category — the PM survey found deterministic o11y is a substrate quality, not a pillar; no new category is introduced.
- NR-3: A second renderer, a navig8r-side model, or a graph HTML view — rendering ContextCore objectives through the navig8r graph is a *separate* cross-repo adopter task (PM §6 rec 2), not this spec.
- NR-4: A new rollup/evaluator engine — the rollup reuses `business/evaluator.py`; introducing a parallel evaluator is explicitly out of scope.
- NR-5: Binding flat goals to nested work spans (Project→Epic→Story→Task) — the second gap in PM §5 is a distinct future iteration.
- NR-6: Any SDK-side build — the SDK's role ends at authoring this proposal; the SDK does not implement ContextCore model changes.

## Owned fields

Only humans enter: the `serves` target id on an `Objective` (which parent business/feature objective it
rolls up to) in the source manifest. Everything else — existence validation, cycle detection, the rollup
walk, pace status — is **derived**, never authored. `serves` defaults `None` (a leaf/root objective has
no parent) and is optional at every layer.

## Contract projection

- **Backend:** python-data-store
- **Vocabulary home (cite):** `~/Documents/dev/dev-os/det-req-kit/SCHEMA.md` §`python-data-store` entry kinds (`store` · `table` · `migration` · `query` · `repository`) · living homes `~/Documents/dev/ContextCore/src/contextcore/models/manifest.py` (the `Objective`/`KeyResult`/`ContextManifest` model store) · grammar cite `~/Documents/dev/dev-os/NODE-SCHEMA.md` (Category facet §1a + derivation edge) · reference edge shape `~/Documents/dev/startd8-sdk/src/startd8/navigator/models.py:87-145`

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| manifest-model | store | structure | `ContextManifest` — the persisted objective/KR structure (`manifest.py`) |
| objective | table | structure | `Objective` gains optional `serves` (FR-1) |
| key-result | table | structure | `KeyResult` optional `serves` (FR-2, deferred) |
| serves-edge | repository | structure | the derivation edge + its validators (FR-3/FR-4) |
| serves-validation | migration | structure | additive-optional field; existing manifests unchanged (FR-6) |
| lineage-rollup | query | structure | the read that walks `serves` and reuses `evaluate_objective_pace` (FR-5) |
| category-selectors | query | structure | `objectives_by_category` and friends, unchanged (FR-7) |

Library seams (cite as Touches file paths, in ContextCore): `~/Documents/dev/ContextCore/src/contextcore/models/manifest.py`
(the `Objective`/`KeyResult`/`ContextManifest` models + `validate_cross_references`);
`~/Documents/dev/ContextCore/src/contextcore/business/evaluator.py` (reused rollup engine, unchanged).
Reference (read-only, navig8r): `~/Documents/dev/startd8-sdk/src/startd8/navigator/models.py`
(`DerivationEdge` / `EdgeRelation` / `Node.child_keys` — the proven edge shape).

## Iterations (acyclic)

The build DAG for the ContextCore owner (each iteration depends only on earlier ones — acyclic):

1. **IT-1 — Add the field (FR-1, FR-2-deferred).** Add optional `serves` to `Objective` (default `None`, alias). No behaviour change. Depends on: nothing.
2. **IT-2 — Validate the edge (FR-3, FR-4).** Extend `ContextManifest.validate_cross_references()` for target-existence (reusing `objective_ids`) and acyclicity. Depends on: IT-1.
3. **IT-3 — Byte-identity + selectors (FR-6, FR-7).** Prove existing manifests round-trip unchanged and the flat selectors are untouched. Depends on: IT-1.
4. **IT-4 — Rollup read (FR-5).** Add the lineage walk reusing `evaluate_objective_pace`. Depends on: IT-2 (a valid, acyclic edge set) and IT-3.

## Appendix A — grounding index (cross-repo, file:line)

| Claim | Evidence |
|-------|----------|
| `Objective` = id/description/category/key_results, **no edge** | `ContextCore/src/contextcore/models/manifest.py:455-489` |
| `KeyResult` has no link/parent field | `ContextCore/src/contextcore/models/manifest.py:343-400` |
| `objectives_by_category` is a flat filter | `ContextCore/src/contextcore/models/manifest.py:929-942` |
| `category` = "Node taxonomy Category facet, NODE-SCHEMA §1a" | `ContextCore/src/contextcore/models/manifest.py:53,461-472` |
| category constants `business_observability` / `delivery_observability` | `ContextCore/src/contextcore/models/manifest.py:61,69` |
| `OBJECTIVE_ID_PATTERN` (`^OBJ-...`) + `Objective.validate_id_format` | `ContextCore/src/contextcore/models/manifest.py:43,491-500` |
| `ContextManifest.validate_cross_references()` builds `objective_ids` + raises on unknown refs | `ContextCore/src/contextcore/models/manifest.py:856-897` |
| rollup engine `evaluate_objective_pace` / `PaceKeyResultStatus` | `ContextCore/src/contextcore/business/evaluator.py:76-148` |
| feature o11y = "delivery-facet **sibling**"; rollup deferred to **EB-4** | `ContextCore/docs/design/requirements/REQ_FEATURE_OBSERVABILITY.md:9,16,36` |
| reference edge shape: `DerivationEdge` / `EdgeRelation` / `Node.child_keys` / `serves` in attributes | `startd8-sdk/src/startd8/navigator/models.py:87-114,118-145,215` |
| the full grounded survey this specs | `startd8-sdk/docs/design/requirements-visualization/PM_FINDINGS_contextcore-o11y-value-lineage.md` |

## Appendix B — why the navig8r Node is the reference model

The value lineage the PM survey wants (business ← feature ← agent) is exactly a **derivation edge on a
Node** — and the navig8r `Node` already carries it. `Node.child_keys` is the generic DEPENDS-ON reference
edge; `DerivationEdge(from_key, relation, regime)` is the typed derivation edge with `EdgeRelation.DERIVED_FROM`
as the forward compilation relation; and `serves` already rides `Node.attributes` (the open extension bag,
documented at `models.py:215` as "name/handle/serves/…"). This spec proposes ContextCore adopt the **same
directional, typed, cycle-free** shape at the `Objective` level: one optional field, validated for existence
and acyclicity, walked by a rollup read. Adopting the proven shape (rather than inventing a new edge) is the
Mottainai move the PM survey recommends — *"give objectives the edge the Node model already defines"* (PM §4.1).

## Appendix C — Incoming review rounds

*This appendix is append-only. Reviewers add `#### Review Round R{n}` blocks here; the orchestrator
records dispositions in Appendix A (applied) / B (rejected). Do not delete triaged rows.*

*v0.1 — CROSS-REPO PROPOSAL, authored from the navig8r side. Hand to the ContextCore owner; re-ground
against the live tree (OQ-3) before build.*
