# Ready-to-apply patch — dev-os `NODE-SCHEMA.md` §1 → 0.4.0

**Date:** 2026-08-16 · **Target:** `~/Documents/dev/dev-os/NODE-SCHEMA.md` · **Owner-authorized** (schema
owner said go) · **Status: APPLIED 2026-08-19** on `chore/det-req-kit-learn-sdk-fields` (0.3.9 WIP
kept as Prior prose, then §1 bumped to 0.4.0). Also listed `verify_gate` (REQ-22) so §1 matches
current `node_field_names()` (**20** stored fields, not the 19 named when this handoff was drafted).

## Why

The startd8 navigator Node + the ContextCore mirror are now at **0.4.0** (REQ-16/17): 4 new fields
`{verify, approve, was, derivation}`. The dev-os doc is the cited SSOT and must follow. Separately, §1's
YAML block is **already stale** — it omits `child_keys`, `status_facets`, `attributes` that the code has
carried for a while (the 3 axes `category/orientation/route_state` are fine — they live in §1a). REQ-16's
parity gate flags this drift by design until the doc catches up.

**Parity target:** after this patch, §1 (+ §1a for the 3 axes) documents all **startd8 `Node` fields**
(`node_field_names()`), plus `maturity` as the documented derivation *input* (not a stored field).
As of apply day that is **20** stored fields (includes `verify_gate`).

## Edit 1 — version line (context-anchored on the stable prefix)

Replace the substring:

```
**Version:** 0.3.9 (Draft — 
```

with:

```
**Version:** 0.4.0 (Draft — 2026-08-16: **+4 fields** `verify`/`approve`/`was` + the typed `derivation` edge (`regime` reserved/unset) — field-parity with the startd8 navigator Node 0.4.0 (REQ-16/17) + the ContextCore mirror (PR contextcore#491); §1 de-stale: `child_keys`/`status_facets`/`attributes` now listed. Prior 0.3.9 — 
```

(This prepends the 0.4.0 note and demotes the existing 0.3.9 prose to "Prior 0.3.9 —", preserving it verbatim. If the 0.3.9 WIP reworded line 3, keep the same shape: bump the number, prepend the 0.4.0 clause, demote the rest to `Prior 0.3.9 —`.)

**Applied note:** the live version line also names `verify_gate` and dates the bump 2026-08-19.

## Edit 2 — §1 YAML block: append the missing + new fields after `children:`

Replace:

```yaml
  children:    # → the next zoom level (the drill-down edge)
```
```

with:

```yaml
  children:    # → the next zoom level (the drill-down edge)
  child_keys:  # cross-references to dependency nodes (DEPENDS-ON) — edges preserved while the
               #   `children` tree stays acyclic. Reference edge, NOT containment.
  derivation:  # 0.4.0 — typed DERIVATION edges[]: {from_key, relation=derived-from, regime?}. the
               #   upstream keys this node was compiled/derived FROM — distinct from `children`
               #   (containment) and from `child_keys` (generic reference). `regime`
               #   (deterministic|llm|human) is RESERVED/UNSET here; the realization REQ populates it
               #   and derives a node's realization from its incoming edges (min-rolls-up, like status).
  verify:      # 0.4.0 — the acceptance ORACLE: the requirement's raw Verify clause (the compiler's
               #   type-checker). CARRIED, not reconstructed. Kind (command|assertion|manual) is a
               #   consumer's classification, not stored here.
  approve:     # 0.4.0 — the human-approval GATE: the Approve? prompt(s) — the reliability pivot.
  was:         # 0.4.0 — change-history alias(es): prior presentation names (key is identity; §5 inv. 1).
  status_facets: # the status VECTOR (inv. 5): instance health facets[] {name,value,glyph?,color?},
               #   orthogonal to the scalar `status` maturity (discussed in §1a).
  attributes:  # open extension bag {str:str} — free-form axis values a source carries through.
  # category / orientation / route_state — the three orthogonal axes; see §1a.
```
```

(The trailing fence is the YAML fence — keep it. The `children:` line is the stable
anchor; the additions go between it and the fence.)

**Applied note:** `verify_gate` was also listed (REQ-22 / CL-55) so §1 matches `node_field_names()`.

## After applying

1. Confirm §1 (+ §1a) now names all startd8 `Node` fields — cross-check against
   `startd8-sdk` `python3 -c "from startd8.navigator.models import node_field_names as f; print(f())"`.
2. The startd8 parity gate's cross-repo drift flag for §1 is now satisfiable (it's advisory /
   existence-guarded, so no startd8 code change is required — REQ-16 FR-2 parity is SDK-internal).
3. The realization REQ (startd8 REQ-18, in flight) will later document `regime`'s populated semantics —
   this patch only reserves/notes it as unset, matching the code.

## Provenance of this patch

Composed against the dev-os working-tree **0.3.9** text (read-only) on 2026-08-16, as the final step of
the coordinated 0.4.0 cross-repo bump: startd8 REQ-16/17 (shipped) + EB-1 (shipped) + ContextCore
PR #491 (open) + **this** (the dev-os doc). **Applied 2026-08-19** after seat-req Definer closeout.
