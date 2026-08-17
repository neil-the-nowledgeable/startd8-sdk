# Handoff — Take the feature→capability composition + ground-up rollup through the loop

**For:** the loop operator (a separate implementation session), cold. **Written:** 2026-08-17.
**Goal:** build the reusable **feature→capability composition edge + a ground-up (bottom-up) capability
rollup view** via the Spec Delivery Loop. Self-contained.

---

## 0. What you're building (one paragraph)

A feature (FR) declares the **capability it builds up to**, so the navig8r can render capabilities
**ground-up from their constituent features**. It is **mostly reuse**: the `serves` semantic edge is
already drawn generic-on-target-id (`graph_projection.py:181-182`); the FR `serves` attribute already
flows from the parse (`sources_requirements.py:303`); capability nodes already exist
(`sources_capability.py`). The **one gate** is the det-req parser `_SERVES` (`det_req.py:31-32`), which
only accepts `O-\d+` today. Extend it to accept a capability target, join FR + capability nodes into one
graph, reuse the `serves` edge, and add a bottom-up rank layout. The **same** extended edge is
ContextCore's missing EB-4 (objective→objective) — this is the SDK **dogfood** of that rollup.

- **Spec:** `docs/design/requirements-visualization/REQ-feature-capability-composition-rollup.md` (6 FRs, BUILD-READY).
- **The parallel:** `PM_FINDINGS_contextcore-o11y-value-lineage.md` + `REQ-contextcore-objective-serves-edge.md` (the same primitive, ContextCore side).

## 1. Preconditions

```bash
python3 scripts/navigator_spec_delivery_loop.py \
  $(pwd)/docs/design/requirements-visualization/REQ-feature-capability-composition-rollup.md
# expect: BUILD-READY ✓ (6 FRs)
```

## 2. The reuse cascade (build order = the spec's iterations)

1. **Parser** — extend `_SERVES` (`det_req.py:31-32`) to accept a capability ref (`CAP-*` / capability_id)
   alongside `O-\d+`, **backward-compatible** (109× `Serves: O-1` etc. must still parse — that's the guard).
2. **Join** — FR nodes + capability nodes (`sources_capability.py`) into ONE graph so both endpoints of a
   feature→capability edge exist (`add_semantic` needs both — `graph_projection.py:172`).
3. **Edge** — reuse the existing `serves` semantic edge (`graph_projection.py:181`) — **no new edge kind**.
4. **View** — a ground-up rank direction (features at the base, capabilities above) over an existing
   renderer (graph or an inverted tree) — **no third renderer**.
5. **Corpus-agnostic** — the primitive is at the Node/det-req grammar level; confirm it also expresses
   ContextCore's objective→objective (the EB-4 dogfood).
6. **Guard** — `Serves: O-N` and existing renders unchanged; the capability edge is additive; app-path
   byte-identity held.

## 3. Relationship to the rest of the backlog

Orthogonal to **Move 3 / search** (those are card-browse *filters*; this is a cross-source *graph +
composition*). It sits with **Move 1** (the hub / cross-source graph). Sequence independently; no
dependency on the visibility-predicate work.

## 4. Git cadence — the hot-main discipline

`main` is a hot, contended ref (advanced many times this session); the primary worktree holds other
agents' uncommitted files (never disturb them); `origin/main` is diverged (do not push there). Work in a
worktree off local `main`, pin `PYTHONPATH=<wt>/src`, land with **`--ff-only`** (rebase onto current main,
re-check tip, ff; if it moved, re-rebase). Resolve rebase conflicts by **combining**. Add a
`docs(viz): ledger —` entry on delivery.

## 5. Done-when

6/6 FRs verified (grounded) · `Serves: O-N` still parses (backward-compat test) · a feature→capability
`serves` edge renders in the joined graph · the ground-up view puts features at the base · app-path
byte-identity held unedited · ruff clean · landed on local `main` via ff + a ledger entry.
