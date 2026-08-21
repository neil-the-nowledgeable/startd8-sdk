# PM Findings — ContextCore's observability value lineage is a missing `serves` edge

**Date:** 2026-08-17 · **Method:** iterative top-down PM survey (2 iterations), grounded in ContextCore
source. **Subject:** ContextCore observability pillars. **Lens:** the navig8r NODE-SCHEMA / two-sided-coin
frame ([[project_navigator_cross_repo_renderer]], [[project_navig8r_two_sided_validation]]).
**Status:** grounded finding (file:line evidence in Appendix) — **a cross-repo belief to validate with the
ContextCore owner before acting** (the recommendation is a change to *their* model).

---

## TL;DR

The question "what is the right *parent* for **feature observability**, up to the top pillars?" converged
on a structural answer: **there is no parent.** ContextCore's observability goals are a **flat list of
`Objective`s distinguished only by a `category` string** — no `parent`/`serves`/`rollup` edge exists.
Feature o11y is a **sibling** of business o11y, not a descendant, and the rollup that would connect them is
an **unbuilt backlog item (EB-4)**. The value lineage the PM view wants (`business ← feature ← agent ←
deterministic`) is therefore a **missing structural relationship**, not a mislabeled level. The fix is one
edge — an `Objective`→`Objective` **`serves`** relation — which is exactly the derivation edge the navig8r's
`Node` model already carries.

---

## 1. The pillars, corrected against the code

| Pillar (as named) | ContextCore reality (grounded) | State |
|---|---|---|
| **business o11y** | `business_observability` category (`manifest.py:61`) | shipped |
| **Project / AI-Agent o11y** | `ai_agent_observability` = **Phase 1 of `delivery_observability`** (`manifest.py:530`) | shipped (the hero) |
| **feature o11y** | **Phase 2 of `delivery_observability`** (`REQ_FEATURE_OBSERVABILITY.md`) | **planned, not built** |
| **deterministic o11y** | **not a category** — a cross-cutting *principle* ("derive from artifacts, don't guess") | quality, not a pillar |
| other o11y | `issue_`, `incident_`, `pilot_queue_`, `project_management_`, `derive_observability` (the engine) | mixed |

Two mental-model corrections:
1. **"Project/AI-Agent" and "feature" are the two phases of one `delivery_observability` umbrella** — the
   *producer* (agent-productivity, Phase 1, shipped) and the *product* (feature-delivery, Phase 2, planned)
   — not free-floating peers.
2. **"Deterministic o11y" is not a pillar; it is the trust *substrate*** under all pillars — literally
   [[project_verify_liveness_value_prop]] ("verification that cannot silently die") applied to observability.

## 2. The core finding — the model is flat, not hierarchical

`Objective` (`manifest.py:455-489`) = `{ id, description, category, key_results }`. **No** `parent`, `serves`,
`rollup`, `contributes`, or `children`. `KeyResult` (`:343-400`) has no link field either.
`objectives_by_category()` (`:929-942`) simply *filters a flat list* by the `category` string.

```
TODAY (flat siblings, no edges — Manifest.objectives is a flat list):
   ┌───────────────────┐        ┌───────────────────────────────┐
   │ Objective         │        │ Objective                     │
   │ category=business │   ??   │ category=delivery             │
   │ (the number)      │◀──────▶│  KR: agent-productivity (P1)  │
   └───────────────────┘  no    │  KR: feature-milestone  (P2)  │
                          edge   └───────────────────────────────┘
```

The feature-obs spec says so in its own words: feature o11y is *"a **delivery-facet sibling** of Business
Observability on the same `Objective`/`KeyResult` engine"* (`REQ_FEATURE_OBSERVABILITY.md:9,16`), and the
rollup is deferred: *"the boards **share the rollup (EB-4)**"* (`:36`) — **EB-4 is an unbuilt enhancement
item.** So the ancestry-to-the-top exists only in prose, not in data.

## 3. The answer to "the right level of parent for feature observability"

- **Today: none.** Feature o11y is a peer category. Its parent is not mis-set — it is *absent*.
- **Target: one missing edge.** Add an `Objective`/`KeyResult` **`serves`** relation and the flat list
  becomes the value chain:

```
TARGET (add the `serves` edge = EB-4):
   business KR (the number)                       ← the TOP
      ▲ serves
   feature KR (milestone pace)   ← feature o11y's real parent = the business KR it serves   [the HINGE]
      ▲ serves
   agent-productivity KR (P1)    ← the producer, serving the feature
      ▲ grounded by
   deterministic derivation      ← the substrate quality (not a node; a guarantee on every signal)
```

## 4. Why this matters — three payoffs

1. **It's a NODE-SCHEMA gap.** ContextCore's Objectives *are* Nodes — the `category` field is documented as
   *"Node taxonomy facet, dev-os/NODE-SCHEMA §1a"* (`manifest.py:53`) — but they carry **no derivation edge**
   (`serves`/`child_keys`). The exact edge the value lineage needs is the one the **navig8r `Node` model
   already has** and the graph renderer already *draws*. **EB-4 ≈ "give objectives the edge the Node model
   already defines."**
2. **The navig8r makes the gap visible.** Project ContextCore's objectives as NODE-SCHEMA-JSON and render
   them in the graph renderer → you see **disconnected nodes** (the flat model, drawn). That is both the
   cross-repo-renderer dogfood (adopter #2) and a live diagnostic of the missing lineage.
3. **It is the two-sided coin, literally.** The `serves` edge is what traces *"this agent-produced,
   deterministically-grounded feature (technical side) → serves this business outcome (value side)."*
   **Feature o11y is the hinge; the missing edge is what would join the two validation sides.** Without it,
   technical and business o11y are disconnected data; with it, feature o11y connects producer → deliverable →
   outcome.

## 5. A second, confirmed gap — goals and work are unjoined (Iteration 3, grounded)

The observed **work** has a hierarchy the **goals** lack: work-item types nest `Epic → Story → Task → Subtask`
(`contracts/types.py:155-165`) via span parentage (`SpanState.parent_span_id`, `task.parent_id` attribute
`contracts/attributes.py:35`). But a feature-as-goal (`delivery` Objective/KeyResult) is flat — **and the two
are joined only implicitly.** A `KeyResult` reaches its work through `data_source` (`manifest.py:371-375`) — a
**PromQL/sentinel string** like `"promql:epic:EPIC-001"`, resolved by string-id match in
`delivery/milestones.py:28-44` — **not a declared field.** There is **no `objective_id`/`goal_id` on work
spans and no `work_span_id`/`epic_id` field on KeyResults** (the only explicit goal cross-ref in the manifest
is `Strategy → objective_refs`, `manifest.py:584-589`). Coverage checks "does the metric exist and is it live"
(`business/coverage.py:101-138`), never "which work item tracks this goal."

**So the flatness compounds: no edge *between* objectives (§2) AND no explicit edge *from goals to the work*
that realizes them.** Both are implicit — query-string parsing, not declared relations. Giving feature o11y a
real lineage needs *both* the objective `serves` edge (§3 / EB-4) and a declared goal→work binding
(`KeyResult.realized_by` / a `goal_id` on the Epic span) so the value chain is data, not string convention.

## 6. Recommendations

1. **Add the objective `serves`/rollup edge (EB-4)** — spec it via reflective-requirements, using the
   navig8r `Node.serves` / `child_keys` as the reference model. This hands ContextCore its value hierarchy
   with one field. *(Owner: ContextCore; validate this findings note against their tree first.)*
2. **Render ContextCore objectives through the navig8r graph** (cross-repo adopter #2) — to *see* the flat
   gap and to prove the navig8r as the pillar-lineage viewer.
3. **Elevate feature o11y out of the "delivery" umbrella** in the product narrative — it is the *hinge*
   between the technical (agent/deterministic) and business (outcome) sides, not a Phase-2 footnote of
   "delivery." Model producer (agent) and product (feature) as distinct pillars linked by `serves`.

---

## Appendix — grounding index (ContextCore, file:line)

| Claim | Evidence |
|-------|----------|
| Objective = id/description/category/key_results, **no edge** | `src/contextcore/models/manifest.py:455-489` |
| KeyResult has no link/parent field | `src/contextcore/models/manifest.py:343-400` |
| Categories are a flat filter, not a hierarchy | `objectives_by_category` `manifest.py:929-942` |
| `business_observability` / `delivery_observability` category constants | `manifest.py:61,69` |
| Phase 1 rides `ai_agent_observability` | `manifest.py:530` |
| `category` = "Node taxonomy facet, dev-os/NODE-SCHEMA §1a" | `manifest.py:53` |
| feature o11y = "delivery-facet **sibling** of Business Observability" | `docs/design/requirements/REQ_FEATURE_OBSERVABILITY.md:9,16` |
| rollup deferred to **EB-4** | `REQ_FEATURE_OBSERVABILITY.md:36` |
| no `deterministic_observability` category exists | grep of `*_observability` across `src`+`docs` — absent |

*Findings produced 2026-08-17 via a 2-iteration top-down survey; grounded against the cited files. Treat as a
cross-repo belief until the ContextCore owner confirms EB-4 is still open and the model unchanged.*
