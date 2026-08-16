# Prompt: pattern analysis + data modeling over a spec corpus (dogfood the navigator)

**For:** an analysis/data-modeling agent · **Author:** emeritus/direction session · **Date:** 2026-08-16
**Use as-is** on the requirements-visualization corpus, or **retarget** the `CORPUS` pointer to another
corpus (legal · benchmark · dev-os) to test whether the patterns generalize.

## The premise

A spec corpus is a **dataset**, and this one is *structured* (det-req fields) and *self-describing* (it was
built to model exactly this kind of thing). Your job is **pattern analysis + data modeling over the corpus,
rendered through the navigator it grew** — the analysis dogfoods the tool. **Ground every claim in the data
or the code; never assert a pattern you did not measure.** (The corpus's own near-universal move is
"grounded, not declared" — honor it.)

## The dataset + tools

- **CORPUS:** `docs/design/requirements-visualization/REQ-*.md` (21 integer REQs + `REQ-seat-*`), plus the
  ADR / RESEARCH / HANDOFF / REVIEW / VISUALIZATION_VARIANTS_ANALYSIS docs.
- **Structure:** each FR is one physical line with `Name:`/`Touches:`/`Lives:`/`Approve?:`/`Verify:`/`Serves:`.
  Parse with `startd8.navigator.det_req.parse_fr_lines`. Header carries DIDL identity + `Pairs with:`/`Inherits`.
- **The modeling tool (use it):** the navigator — `startd8.navigator` (`models.Node`, `render_tree`,
  `render_graph`, `derive_status`, the derivation edge + `regime` slot). Model the corpus AS a Node graph and
  **render it through the navigator** (as `scripts/viz_mutation_graph.py` already does for the viz lineage).
- **Prior art:** `scripts/viz_mutation_graph.py` (the variant mutation graph), `VISUALIZATION_VARIANTS_ANALYSIS.md`
  (the SOURCE × TOPOLOGY × PRESENTATION × AUDIENCE factoring), `THE_CRAFT_GRAMMAR_reflective_abstraction.md`.

## Seed findings (already measured — start here, don't re-derive)

- **A generative grammar exists.** Near-universal syntax: **byte-identical 20/21 · additive 17/21**. Idiom
  tier: honest-grounding 13 · mirror/self-similar 12 · seam 11 · Kagami/no-fork 7. Specialized tail
  (confidence-degrade · reserve-a-slot · firewall) clusters in REQ-16→21.
- **The corpus is a node graph:** 21 nodes, 66 directed dependency edges. Foundations (in-degree): REQ-01 (9),
  REQ-02/06 (7), REQ-03/04 (6). Most-composed (out-degree): REQ-08 (7), REQ-07 (6), REQ-20 (5).
- **Move-density rises over time** (REQ-18 = 10 moves; early REQs 2–3) — the corpus compounds its patterns.
- **Structural regularity:** ~3 objectives/REQ, 7.2 FR/REQ (REQ-01 an outlier at 19).

## The directed analyses (ranked; pick per scope, ground each)

1. **Model the corpus as a Node graph + render it.** REQs = nodes; `Pairs with`/`Inherits`/build-blocked =
   derivation edges; status/axis = facets. Render through `render_graph`/`render_tree`. Report: the
   foundations (high in-degree), the composed frontier (high out-degree), any **cycle** (a dependency cycle
   is a defect — flag it), and the critical build path. *(Highest leverage — it dogfoods the tool and yields
   a reusable artifact.)*
2. **The axis-coverage matrix.** Re-run the `VISUALIZATION_VARIANTS_ANALYSIS` factoring (SOURCE × TOPOLOGY ×
   PRESENTATION × AUDIENCE) over the *current* corpus. Which cells are full, which **empty**? An empty cell is
   a next-opportunity (the empty TOPOLOGY cell is what shook out REQ-05). Ground each cell in a real REQ/file.
3. **Formalize the design-move grammar → a govern check.** Turn the near-universal moves into a `govern`
   (REQ-06) rule: a REQ that claims to touch shipped surface but does **not** assert byte-identity/additive is
   flagged. Measure precision before shipping (a heuristic that cries wolf is worse than none).
4. **FR → Objective → REQ traceability graph.** Use `Serves:` to link FRs → objectives → REQs. Report thin
   objectives (few FRs), orphan FRs (serve nothing), and objective/FR coverage per REQ.
5. **Cross-corpus generalization (the big one).** Retarget the mining to another corpus (legal · benchmark ·
   dev-os). Does the same grammar hold? A move that is universal *across corpora* is a **principle**; one
   local to this corpus is a **convention**. This is the empirical test of the Craft-Grammar claim.
6. **Temporal/maturity trend.** Model move-density and dependency-fan-in over REQ number. Is the corpus
   converging (reusing a stable move-set) or sprawling (new one-off moves each REQ)?

## Output form + discipline

- **Render, don't just tabulate** — the primary artifact is a **Node graph rendered through the navigator**
  (plus a short grounded pattern report). Seeing the graph is the point (Mieruka).
- **Ground everything** — cite the REQ/file/line for each pattern; a count with no decision attached is
  bare-data (cruft). State what a reader should *do* with each finding.
- **If you build anything** (a script, a govern rule): additive + byte-identical on existing renders; no new
  Node field unless a schema decision authorizes it; DIDL-name the artifact (semantic name + handle + ref);
  and mind the **det-req single-line trap** — never put literal `Verify:`/`Approve?:` tokens (with colons) in
  FR prose.
- **Name the caps you drop** — if you sample/top-N/skip, say so; silent truncation reads as "covered
  everything."

## The one-paragraph brief

Treat this spec corpus as a structured, self-describing dataset; **model it as a Node graph and render it
through the navigator it grew**; mine it for its generative grammar (start from the seed findings — don't
re-derive them), its dependency structure, its empty axis-cells, and its traceability gaps; and — the real
prize — **retarget the mining to a second corpus to separate the corpus-local conventions from the
cross-corpus principles.** Ground every pattern in the bytes; render what you find; propose the govern rule
or the next REQ the gaps imply.
