# Enhancement Backlog — REQ-07 Diff-Audience View

Grounded, value/effort-ranked follow-ons for the REQ-07 delivery (`diff.py`, `render_diff.py`,
`navigator diff` + `_load_state`). None auto-execute beyond the P1/P2 fixes already applied inline in
the HTH pass (the `_load_state` structural shape-guard `_validate_node_json` + its negative tests).
Rows are ranked value↓ / effort→. Each cites code.

| # | Enhancement | Value | Effort | Grounding (file:line) | Notes / rung |
|---|-------------|-------|--------|-----------------------|--------------|
| EB-1 | **Apply the same shape-guard to `build`'s `nodes-json` loader** | high | XS | `cli_navigator.py:113-114` — `nodes_from_json(data.get("nodes", data) …)` with NO structural guard, identical to the pre-fix `_load_state` | Yokoten of the P2 fix. `build --source nodes-json` leaks the *same* `AttributeError`/`TypeError` tracebacks on a valid-JSON-wrong-shape file. Extract `_validate_node_json` (already added) + call it in `build`. Out of REQ-07's *diff* surface (it's the `build` command) → backlog, not inline. |
| EB-2 | **Metabolize the field-dataclass dormant class into the reachability probe** | med | S | probe verdict DORMANT 0/0 on `StatusTransition`/`DanglingRef` (both fully wired via field-iteration); prior instance `GovernReport` (REQ-06) | rung-4 poka-yoke. Teach `--reachability` to treat "constructed + assigned to a container dataclass field + that field iterated/serialized" as wired, so HTH stops re-litigating benign field-dataclasses every pass. Owner of the probe is the loop-meta agent (`navigator_spec_delivery_loop.py`) — **route via `/metabolize-finding`, do not edit here** (loop-meta is out of scope). |
| EB-3 | **Fuzzy rename detection (remove+add → renamed)** | med | M | `diff.py:11` NR-4 (v0.1: a renamed key is honestly `1 removed + 1 added`); `_field_deltas` already computes field-level similarity primitives | NR-4 deferred by design. A similarity pass over added×removed pairs (e.g. same `does`/`lives`, key edit-distance) could surface `A → A'` as a rename row. Keep it opt-in (`--detect-renames`) so the honest remove+add stays the default. |
| EB-4 | **Sub-string / word-level `does` diff** | med | M | `render_diff._fmt_field_value` L188 renders `does` before/after as whole strings; NR-5 defers intra-string diff | NR-5 deferred. A word-level highlight (difflib `SequenceMatcher`) inside a changed `does` cell would let a reviewer see *what* in the prose moved, not just before→after. Renderer-only; engine already carries raw before/after. |
| EB-5 | **N-way / changelog timeline across >2 states** | med | L | NR-1/NR-2 (v0.1 is strictly two-state); `diff_nodes(before, after)` is pairwise | Deferred follow-on. Fold a sequence of `NodeDiff`s into a per-key timeline (spec→built→deprecated over N snapshots). Larger — a new renderer + a state-sequence loader; likely its own REQ. |
| EB-6 | **Graph/edge delta (edge added/removed)** | low | L | NR-6 — rides REQ-05 graph topology; REQ-07 diffs the flat keyed node set | Deferred, cross-REQ. The current diff already surfaces `children`/`child_keys` field deltas (a dependency signal); a true edge-delta view belongs with REQ-05, not here. |

**Applied inline this HTH pass (not backlog):**
- **P2-1** — `_load_state` structural shape-guard: `_validate_node_json` recursively validates the
  decoded payload (array-of-objects; objects-only `lives`/`children`) and raises `ValueError` (the
  caught type), converting 5 leaking `AttributeError`/`TypeError` traceback classes into clean exit-1
  errors. `cli_navigator.py` + 10 new negative/robustness tests in `test_cli_diff.py`.

The P1 review found **no un-fixed Critical/High defect** in the diff engine or renderer — the dangling
FS-resolution, order-stability, lens-union, and XSS coverage are all correct + tested as shipped
(see the retro Phase 3). The only real robustness gap (the loader boundary) was fixed inline.
