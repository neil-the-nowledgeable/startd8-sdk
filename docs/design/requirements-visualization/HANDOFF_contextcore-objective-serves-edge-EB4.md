# Handoff → ContextCore team: build the Objective `serves` edge (EB-4 value-lineage rollup)

> **Owner: ContextCore.** Home for the build: `~/Documents/dev/ContextCore/`.
> **From: startd8-sdk / navig8r.** The SDK side of this composition primitive is now **shipped and
> live** — this handoff hands you the twin to build on your `ContextManifest` models.
> **Status of your portion:** spec is **BUILD-READY**; no ContextCore code has been written yet.

---

## 1. TL;DR — what to do

1. Read the spec: **`REQ-contextcore-objective-serves-edge.md`** (same directory as this file). It is
   det-req/0.1, 7 FRs, an acyclic IT-1→IT-4 build DAG, and a full file:line grounding index (Appendix A).
2. **Resolve the 3 open questions first** (OQ-1/2/3 — see §4 below). OQ-3 is a hard gate: re-ground the
   cited `manifest.py` lines against your live tree before writing anything.
3. Build IT-1 → IT-4 in order (§5). It is **additive** — one optional field + two validators + one read
   helper. **No engine change, no board change.**
4. Ship it as the ContextCore realization of **EB-4** (the rollup deferred in `REQ_FEATURE_OBSERVABILITY.md`).

This is a **small** task deliberately: the SDK just proved the exact shape end-to-end, so you are copying
a validated pattern, not designing one.

---

## 2. Why now: the SDK twin is live (copy the proven shape)

The SDK and ContextCore share **one composition primitive** — a directional, typed, cycle-free derivation
edge that rolls a leaf up to a root. The SDK side shipped it on **2026-08-18** (`726405b3` on `startd8-sdk`
`main`):

| Concern | SDK (navig8r) — **shipped** | ContextCore — **your portion** |
|---------|------------------------------|--------------------------------|
| The edge | FR **`Serves:`/`Composes:`** → capability, parsed in `det_req.py` | `Objective.serves` → parent objective (FR-1) |
| The join | `--source requirements+capabilities` joins both node sets (`cli_navigator.py`) | rollup read walks `serves` across `self.objectives` (FR-5) |
| The rollup direction | `--rank-direction ground-up` puts leaves at the base (`render_graph.py`) | leaf→root pace walk, reusing `evaluate_objective_pace` (FR-5) |
| Correct-by-construction | edge only draws when both endpoints exist (generic `serves` in `graph_projection.py`) | `validate_cross_references` rejects dangling/cyclic targets (FR-3/FR-4) |
| Additive byte-identity | default layout byte-identical; `Serves: O-N` back-compat held | optional field, `exclude_none`, existing manifests unchanged (FR-6) |

**Reference shape to read (read-only, do not import across repos):**
`startd8-sdk/src/startd8/navigator/models.py:87-145` — `DerivationEdge` / `EdgeRelation` / `Node.child_keys`,
plus `serves` riding `Node.attributes` (`:215`). The SDK's 9 FR-keyed regression pins are in
`startd8-sdk/tests/unit/navigator/test_composition_rollup.py` — a worked model for your own FR pins.

**Key convergence fact:** the SDK's own FRs did **not** roll up to capabilities either until this shipped
(they Served only local `O-N`). Your `Objective`s have the identical gap — a flat category list with no
parent edge. The fix is the same one edge, on both corpora.

---

## 3. Scope guard (what this is NOT — from the spec's Non-goals)

- **NR-1** — no change to the shipped business / delivery / agent boards. Additive edge + a rollup *read* only.
- **NR-2** — no new `category` value (no `deterministic_observability`). Deterministic o11y is a substrate
  quality, not a pillar.
- **NR-3** — rendering ContextCore objectives *through the navig8r graph* is a **separate** cross-repo
  adopter task (PM §6 rec 2), not this build.
- **NR-4** — **no new evaluator engine.** The rollup is a read over the existing `business/evaluator.py`.
- **NR-5** — binding flat goals to nested work spans (Project→Epic→Story→Task) is a distinct future iteration.

If a step tempts you toward a new engine, a board change, or a renderer, stop — it is out of scope by NR.

---

## 4. Resolve these before building (the 3 OQs)

| OQ | Question | Default in the spec | What you owe |
|----|----------|---------------------|--------------|
| **OQ-1** | Objective-level vs KeyResult-level edge? | Objective-level `serves` (FR-1); KR-level (FR-2) deferred | Confirm the coarser edge suffices for the value chain; only turn on FR-2 if you need KR→KR granularity. |
| **OQ-2** | Relation vocabulary — single `serves` string vs a small enum? | single `serves` value | If you want an enum (like navig8r `EdgeRelation`), **name it once** — do not fork a relation constant per call site. |
| **OQ-3** | **Is EB-4 still open + is the model unchanged?** | assumed open, `Objective` has no edge field | **Hard gate.** Re-`grep` `Objective` in `src/contextcore/models/manifest.py` on your live tree. If it already grew a link field, this spec is **superseded** — reconcile before building. |

> This handoff is a **belief artifact about your repo.** Every `manifest.py:NNN` line in the spec's Appendix
> A was grounded on 2026-08-17 from the SDK side and *will* drift. Re-ground each FR's Touches against the
> live tree before you write it (this is the [[feedback_cross_repo_handoff_grounding]] rule — the prose
> drifts from the code in both directions).

---

## 5. Build order (the spec's acyclic DAG)

Each iteration depends only on earlier ones. Land each behind its own FR-keyed test pin (mirror the SDK's
`test_composition_rollup.py`).

1. **IT-1 — Add the field (FR-1; FR-2 deferred per OQ-1).**
   Add `serves: Optional[str] = None` (aliased) to `Objective` in `models/manifest.py`. No behaviour change.
   *Verify:* `Objective(serves="OBJ-REVENUE").serves == "OBJ-REVENUE"`; absent → `.serves is None`.
   *Depends on:* nothing.

2. **IT-2 — Validate the edge (FR-3, FR-4).**
   Extend `ContextManifest.validate_cross_references()` — reuse its existing `objective_ids` set for
   target-existence (against `OBJECTIVE_ID_PATTERN`), and add cycle detection (self-`serves` is the
   degenerate cycle). Both raise the existing named `ValueError`.
   *Verify:* `serves="OBJ-GHOST"` raises naming the unknown ref; `A→B→A` and `A→A` raise naming the cycle.
   *Depends on:* IT-1.

3. **IT-3 — Byte-identity + selectors unchanged (FR-6, FR-7).**
   Prove an existing fixture manifest dumps byte-identically (`model_dump(by_alias=True, exclude_none=True)`)
   and `objectives_by_category()` / `business_objectives()` / `delivery_objectives()` return identical lists.
   *Depends on:* IT-1. (Can run parallel to IT-2.)

4. **IT-4 — Rollup read (FR-5).**
   Add a lineage-walk read helper: from a leaf objective, follow `serves` to the business root, calling the
   **existing** `evaluate_objective_pace` per objective; return leaf→root pace statuses. No new evaluator,
   no change to `PaceKeyResultStatus`.
   *Verify:* `agent-obj serves feature-obj serves business-obj` → 3 pace statuses in leaf→root order, each
   from an existing `evaluate_objective_pace` call.
   *Depends on:* IT-2 (a valid, acyclic edge set) and IT-3.

---

## 6. Done-when (your portion)

- [ ] OQ-1/2/3 resolved and recorded in the spec's §0 (OQ-3 re-grounded against the live tree).
- [ ] IT-1→IT-4 landed, each with an FR-keyed test pin (7 FRs → pins mirroring the SDK's 9).
- [ ] A byte-identity golden proves pre-existing manifests round-trip unchanged (FR-6).
- [ ] Dangling-target **and** cycle negative tests are load-bearing and green (FR-3/FR-4).
- [ ] The rollup calls the existing evaluator only — `grep` confirms no new evaluator symbol (NR-4).
- [ ] Shipped as EB-4; `REQ_FEATURE_OBSERVABILITY.md`'s deferred-rollup note updated to point at it.

---

## 7. Pointers

- **Spec (build from this):** `REQ-contextcore-objective-serves-edge.md`
- **Grounded survey it specs:** `PM_FINDINGS_contextcore-o11y-value-lineage.md`
- **SDK twin (shipped, read for the proven shape + test model):**
  `startd8-sdk` `main` `726405b3` — `src/startd8/navigator/{det_req,cli_navigator,render_graph}.py`,
  `tests/unit/navigator/test_composition_rollup.py`
- **Reference edge model:** `startd8-sdk/src/startd8/navigator/models.py:87-145,215`
- **Your model store:** `ContextCore/src/contextcore/models/manifest.py`
  (`Objective` / `KeyResult` / `ContextManifest` + `validate_cross_references`)
- **Your reused rollup engine (unchanged):** `ContextCore/src/contextcore/business/evaluator.py`

*Cross-repo handoff authored from the navig8r side, 2026-08-18. Re-ground against the live ContextCore tree
(OQ-3) before build. The SDK does not implement ContextCore model changes (NR-6) — this is your portion.*
