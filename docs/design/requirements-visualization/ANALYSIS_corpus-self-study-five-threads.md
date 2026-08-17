# Analysis: five self-study threads over the requirements-visualization corpus

**Date:** 2026-08-17 · **Type:** parallel corpus analysis (5 agents, consolidated) · **Status:** grounded/measured
**Method:** five independent agents mined the corpus (REQ-01..25, 180 FRs) + the shipped navigator code + git/ledger,
each grounding in the parser/AST/git — not assertion. Rendered artifacts in `/tmp` (noted per thread).

## Thread 1 (the standout) — dogfood the liveness column on our OWN corpus

**The corpus authored the cure while being ~96% afflicted by the disease.** Running verify-liveness (the value prop's
own concept, via `verify_oracle.classify`) back over the corpus that authored it:

| Check | live/runnable | present-but-dead (prose) | dead rate |
|---|---|---|---|
| **verify-liveness** (180 FRs) | 8 `command` | 172 `assertion`/`manual` | **95.6%** |
| **`verify.gate` adoption** (the field REQ-22 specced) | **0** real (1 false-positive) | 180 absent | **~100% absent** |
| **target-unmeasured** (83 objectives) | 4 | 79 prose | **95.2%** |

Only **6 of 25** docs contain *any* runnable verify; **REQ-09→25 (17 docs, including REQ-22/23/25 themselves) have
zero**. Every FR in REQ-22 — the doc that authored *"a requirement can't read verified while its check attests
nothing"* — is 8/8 prose. **Verdict: the corpus does NOT pass its own test — and that IS the finding.** It proves the
value prop is real and applies to us: our requirements read "verified" (non-empty `Verify:` prose, pass every presence
check) while attesting nothing runnable. REQ-22's own `verify.gate` remedy has **0/180 adoption** in the corpus that
specified it. *(Actionable: dogfood the fix, not just the check — adopt `verify.gate` on our own high-value FRs.)*

## Thread 2 — the corpus rendered as a Node graph (dogfood the renderer)

25 nodes, **89 build-on edges**, single connected component, rendered through `render_navigator_graph_html` →
`/tmp/req-corpus-graph.html` (builder `/tmp/req_corpus_graph.py`).
- **Foundations (in-degree):** REQ-06 Corpus Governance (**11**), REQ-01 Node Home (**9**) — the twin bedrock; REQ-01 is
  the only pure root (out-degree 0).
- **Composed frontier (out-degree):** REQ-08, REQ-22, REQ-25 (**7** each) — the liveness/realization/feedback tip.
- **Cycle verdict: ACYCLIC** (clean DAG, full 3-colour DFS — no defect).
- **Critical path (15 edges):** `REQ-25→23→22→20→19→18→17→16→08→07→06→05→04→03→02→01` — the corpus spine; REQ-08 is the
  hinge joining the provenance half to the renderer/lens half. Leaf frontier: REQ-09/13/15/24/25.

## Thread 3 — FR → Objective traceability

**Clean on traceability, thin on fan-in.** 180 FRs, 83 objectives; **0 orphan FRs, 0 dangling serves** (100% of FRs map
to a declared objective). But **23% of objectives (19/83) are backed by ≤1 FR.**
- **The one hard gap:** **REQ-04 O-5 has 0 FRs** — a declared objective with no implementing FR (fix candidate).
- **Thinnest REQ:** **REQ-15** (only 1 of 4 objectives reaches ≥2 FRs).
- *(Calibration note: the objective-label extractor needed to tolerate 3 spellings — `**O-N:**`/`**O-N :**`/plain
  `O-N:` — a naive regex drops 21/25 REQs. A latent inconsistency in our own authoring.)*

## Thread 4 — the axis-coverage matrix refreshed (Mendeleev census)

Since the original (2026-08-14): **FF-1 is CLOSED** (lenses lifted, REQ-04/09), the **graph topology cell is FILLED**
(REQ-05), and **SOURCE nearly doubled** (7: +pipeline/retrospective/frame). **The empty cells migrated UP the stack** —
from missing renderers to missing **lens×topology compositions**. Ranked next-opportunities:
1. **a11y as a cross-topology lens** (a11y-of-tree/graph/diff) — **the exact FF-1 analogue**: a11y is welded to the flat
   topology the way lenses were once welded to wireframe. One fill lights 3 cells. → the *fourth RenderProfile moment*.
2. topological/edge diff + corpus diff index (reuses `diff.py`+`graph_projection.py`).
3. corpus-as-graph with the governance lens (wire `govern.py` into a renderer).
4. render the retrospective/lesson subgraph through the shared renderers (the feedback loop, made visible).
5. a **live/stream** SOURCE functor (telemetry→Node — the one pure empty SOURCE cell).
6. lift the **realization/determinism** lens off wireframe (a fourth micro-FF, same shape as FF-1).

## Thread 5 — delivery velocity + maturity

18 numbered deliveries in ~44.5h, **median gap 0.7h** (mean 2.6h). **Spec Delivery Loop = 83% (15/18)**; switched to
**reflective-requirements at delivery #16** (REQ-24 — a loop that *revises the spec from build-time discovery*).
- **Cadence accelerated** — from overnight gaps early to **7 deliveries in ~3.8h** in the final realization→retrospective
  arc — *under a held `test_no_profile_is_byte_identical` invariant* (the convergence signature).
- **Move density: bimodal, not linearly rising.** +50% intensity late-half (r=+0.31) but a mechanical-cascade *valley*
  (REQ-09..17) → a conceptual-arc *spike* (REQ-18..24, 66-75 moves each). **Breadth is flat (~5 distinct moves/spec)** —
  the grammar stabilized early; later specs go *deeper on fewer moves*, not broader. **Verdict: converging, not sprawling.**
- **The one recurring debt:** *spec-ahead-of-live-wiring* seams (the density spikes all carry "specced-but-unfueled seam"
  harvest notes) — disciplined (tracked + circled back), but the standing tension. Ledger drifted from code twice
  (REQ-15/REQ-19-fuel misfiled open) — hence the standing "verify by FR-tag commits + tests, not the list."

## Emergent actionable items (across threads)

1. **Dogfood the fix (Thread 1):** adopt `verify.gate` on the corpus's high-value FRs — 0/180 today; our own value prop
   indicts us. The most on-theme follow-on.
2. **REQ-26 — a11y-as-cross-topology-lens (Thread 4):** the highest-leverage empty cell, the FF-1 analogue.
3. **Fix REQ-04 O-5 (Thread 3):** the one 0-FR objective; thin REQ-15.
4. **Watch the spec-ahead-of-wiring seam (Thread 5):** the recurring, well-tracked debt.

*(All five agents returned findings only — nothing was committed by them; this consolidation is the single-writer persist.)*
