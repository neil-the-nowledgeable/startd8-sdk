# Requirements Visualization — Variants Analysis (a reflective-abstraction)

**Date:** 2026-08-14 · **Method:** catalog the variants, then read them through three reflective
lenses (adoption · retrospective · **abstraction**). **Grounded** in the built corpus (file:line).
**Companion artifact:** `scripts/viz_mutation_graph.py` renders the mutation node-graph through the
tree renderer it grew (`/tmp/viz-mutations-tree.html`) — the capability visualizing its own evolution.

> The prompt that produced this: *"it shows quite a bit more, via multiple lenses… I sense a new
> reflective look at the abstraction implied by the variants… catalog the visualization capabilities
> and their REQ/PLAN pairs… a node graph of the mutations and a categorical analysis of the audience,
> how the visualization relates to the information and its presentation."*

---

## 1. Catalog — the visualization capabilities + REQ/PLAN pairs

| Capability | Kind | Axis | REQ / PLAN | Status | Home |
|-----------|------|------|-----------|--------|------|
| hand fsn-markdown navigators | renderer (ur-form) | presentation | — | retired | `docs/**/README.md` |
| wireframe renderer | renderer | presentation | (pre-REQ) | built | `wireframe_view/view.py` |
| RenderProfile (domain vocab/chrome seam) | abstraction | abstraction | REQ-01 / PLAN-01 | built | `wireframe/profile.py` |
| requirements source | source | source | REQ-01 | built | `navigator/sources_requirements.py` |
| capability-index source | source | source | REQ-01 | built | `navigator/sources_capability.py` |
| node-schema source (self) | source | self-reference | REQ-01 | built | `navigator/sources_node_schema.py` |
| typed grounding (lives/confidence/status) | data | evidence | REQ-01 | built | `navigator/models.py` |
| debug layer (structure/combined/scaffold/hide/provenance) | lens | self-reference | REQ-01 FR-11..15 | built | `wireframe_view/_template.py` |
| status-filter chips | lens | audience | REQ-01 PF-1 | built | `wireframe_view/_template.py` |
| **tree renderer (N-level)** | renderer | topology | **REQ-02** | **built** | `navigator/render_tree.py` |
| `--source nodes-json` (adopter seam) | source | source | REQ-02 FR-2 | built | `navigator/project.py` |
| **a11y ReqView renderer** | renderer | audience | **REQ-03** | **spec** | (`navigator/render_a11y.py`) |
| **corpus index (drill-to-leaf)** | renderer | topology | **REQ-03** | **spec** | (`navigator/render_index.py`) |
| the five loops (pilot/content/origin/cruft/inspect) | governance | governance | (LOOP_CATALOG) | built | `scripts/navigator_*.py` |

REQ/PLAN pairs: **REQ-01 ↔ PLAN-01** (paired); **REQ-02**, **REQ-03** (REQ-only — no PLAN yet; a
gap the retrospective flags). Cross-repo consumer view: `NAVIG8_A11Y_RENDERER_TRACK…`,
`VISUALIZATION_CAPABILITY_ANALYSIS_FROM_DEV-OS…`.

---

## 2. The abstraction the variants imply — a four-axis product space

The variants are **not ad-hoc**; they factor. Every concrete visualization is a point:

```
visualization  =  SOURCE  ×  TOPOLOGY  ×  PRESENTATION  ×  AUDIENCE-LENS
```

| Axis | What it varies | Members (built · spec · empty) |
|------|----------------|-------------------------------|
| **SOURCE** (`Domainᵢ → Node`) | what information is projected in | requirements · capability-index · node-schema · nodes-json · *(live/stream — empty)* |
| **TOPOLOGY** | the shape of the node relation | flat · 2-level (section→item) · **N-level tree** · corpus-index *(spec)* · **graph/network — empty** |
| **PRESENTATION** (`Node → View`) | the shell / renderer | wireframe (editorial) · tree (drill) · a11y *(spec)* · json · grounding-counts |
| **AUDIENCE-LENS** (transform on the view-model) | for whom / which facet | audience(end_user·architect·10 kits) × fluency(beg·int·adv) × debug(content·structure·combined·scaffold) × a11y |

**The invariant is the Node.** `contract → wireframe → descriptive → node-navigator` — the **Node
graph is the waist of the hourglass**: SOURCES are functors *into* it (`Fᵢ : Domainᵢ → Node`),
RENDERERS are functors *out* of it (`Gⱼ : Node → View`), and the LENSES are natural transformations
on the view-model. A visualization is `Gⱼ ∘ (lens) ∘ Fᵢ`. **This is the reflective-abstraction: the
set of variants reveals that the Node is the natural-transformation point, and everything else is one
of two fibered families around it.** Add a source = one new `Fᵢ`; add a renderer = one new `Gⱼ`; and
— *if the Node contract and the lens layer are honored* — you get the cross-product for free.

---

## 3. Same / different across the variants

**Same (the invariant core — do not fork these):**
- the **NODE-SCHEMA-JSON contract** (`key/does/status/status_facets/lives/children/…`);
- the **glance-approve acceptance test** (can an architect approve/reject at a glance?);
- **offline, self-contained** HTML (inlined CSS+JS, no CDN);
- **byte-identity discipline** (a new surface must not perturb the app-scaffold path);
- **evidence-binding** (a node is grounded by typed `lives`, or honestly flagged).

**Different (the axes that vary):** the shell, the topology, the audience, **whether the lenses
apply**, and evidence-strictness. The load-bearing difference is the last-but-one:

> **Factorization failure (FF-1):** the audience × fluency × debug **lenses are entangled with the
> wireframe renderer** (`_template.py`) — the tree renderer (REQ-02 NR-2) and the a11y renderer
> (REQ-03 NR-2) each carry their **own** shell and therefore *cannot inherit the lenses*. The
> "crown jewel" (the lenses) is welded to one `Gⱼ` instead of living on the Node view-model. The
> abstraction (§2) says the lenses should be a **transform between source and renderer**, shared by
> all `Gⱼ`. This is the single most important thing the variant set reveals.

---

## 4. The mutation node-graph (phylogeny)

Rendered live at `/tmp/viz-mutations-tree.html` (`scripts/viz_mutation_graph.py`). Each mutation moved
along one axis:

| # | Mutation | Axis moved | Delta |
|---|----------|-----------|-------|
| M1 | fsn-markdown → wireframe renderer | presentation | automate the render; $0 deterministic |
| M2 | + RenderProfile | **abstraction** | decouple domain vocab/chrome from the engine (unlocked reuse) |
| M3 | + navigator sources | source | invert ingestion — the SDK renders its own |
| M4 | + typed grounding | evidence | lives/confidence/status derived, survive compose |
| M5 | + node-schema source | self-reference | the model renders itself (Kagami) |
| M6 | + debug layer | self-reference | meta-view: structure/combined/scaffold |
| M7 | + the five loops | governance | prove-or-purge / salvage the render |
| M8 | + tree renderer | topology | 2-level → N-level (REQ-02) |
| M9 | + a11y + corpus index | audience · topology | screen-reader; doc → corpus (REQ-03) |

**Direction of drift:** toward (a) more **sources**, (b) deeper **topology**, (c) more **audiences**,
(d) more **self-reference & governance**. Notice M2 (abstraction) is the pivot that made every later
mutation cheap — and FF-1 is the *un-repeated* M2: the lenses still await their "RenderProfile moment."

---

## 5. Categorical analysis — audience × the information↔presentation relation

**Audience spectrum** (the variants have been climbing toward the meta end):

| Audience | Wants | Served by |
|----------|-------|-----------|
| consumer / owner (`end_user`) | "is my thing right?" — benefit-first | wireframe + end_user lens |
| producer / builder (`architect`) | "is the shape/grounding right?" — approve the contract | wireframe + architect lens; status-filter |
| integrator / adopter (legal · benchmark · dev-os) | "does my node-tree render?" — the contract | tree renderer + nodes-json |
| accessibility user | semantic navigation | a11y ReqView *(spec)* |
| **maintainer / debugger** | "how does the template work?" | scaffold mode |
| **auditor** | "is this proven / does it earn its place?" | provenance readout + cruft/inspect loops |

**How presentation relates to information — a trichotomy:**
1. **Transparent** — presentation *serves* information (tree, a11y, wireframe: show the nodes).
2. **Self-referential** — presentation *is* information (scaffold mode: the render's own anatomy is
   the subject; node-schema source: the model is the data).
3. **Evaluative** — presentation *judges* information (provenance readout, cruft/inspect loops: the
   render scores/prosecutes the nodes).

The capability began transparent and has grown **self-referential** and **evaluative** — the
debugging-layer arc. That is itself a predictor: the next audiences are meta (a "diff" auditor, an
"exec" summarizer), and the next relation is likely **generative** (presentation *proposes* changes to
the information — the inspect loop's `/enhancement-backlog` hand-off is the embryo).

---

## 6. The three reflective lenses (and the new one)

| Lens | Direction | Question | Applied here |
|------|-----------|----------|--------------|
| `/reflective-requirements` | forward | spec before build | each REQ-0x |
| `/reflective-retrospective` | backward | what standard did my ACTUALS prove? | the loop family, prove-or-purge, byte-identity-by-construction, the naming convention, the git cadence — all extracted from doing |
| `/reflective-adoption` | outward | generalize → pilot into a *different* consumer → fold friction back | navigator generalized → requirements-viz first pilot; friction (app-scaffold bleed) hardened the RenderProfile seam; legal/benchmark/dev-os are the next pilots |
| **`/reflective-abstraction`** (NEW) | **upward** | what higher-order STRUCTURE do the VARIANTS imply? | §2 (the four-axis product space, Node as fixed point) + FF-1 (the factorization the variants demand) |

**`/reflective-abstraction` — proposed new reflective twin.** Piaget's *réfléchissement*: build a
higher-order structure by reflecting on the **coordination of one's own operations**, not on any
single object. Here the "operations" are the renderers/sources/lenses; the reflective abstraction is
the **algebra they form** (§2) and the **refactoring it demands** (FF-1). It is distinct:
- from **adoption** (which pilots into a *new consumer*),
- from **retrospective** (which extracts *process* from what you did),
- from **requirements** (which specs *before* building).

It is the constructive counterpart to `/generality-survivorship-audit` (which finds *false* generality)
and `/complexity-distiller` (which finds *accidental* complexity): reflective-abstraction finds the
**true generality** latent in a set of variants and names it — then predicts the empty cells and the
entanglements to un-weld. **Trigger:** you have ≥3 sibling variants that grew incrementally and you
sense they "want" a common structure. (Worth formalizing via `/skill-creator`.)

---

## 7. Emergent capabilities / requirements (what the analysis shakes out)

The empty cells (§2) and the factorization failure (§3) name the next requirements:

| Candidate | Kind | Why (from the analysis) |
|-----------|------|-------------------------|
| **REQ-04 — lift the lenses to a Node-view-model transform** | factor-out | FF-1: un-weld audience/fluency/debug from `_template.py` so tree + a11y inherit them; the un-repeated M2. **Highest leverage.** |
| **REQ-05 — graph/network topology renderer** | new topology | the empty TOPOLOGY cell: `child_keys` are edges; a network view (vs tree) is unbuilt |
| **REQ-06 — corpus governance** | cross-cell | corpus-index × the provenance/cruft/inspect loops (govern a whole doc corpus, not one view) |
| REQ-07 — a "diff" audience/renderer | new audience | show what CHANGED between two node graphs (the generative/meta end of §5) |
| a **visualization taxonomy** standard | reference | promote §2–§5 to a cited standard so future variants declare their (source,topology,presentation,audience) coordinates |

**Future direction (what the drift predicts):** converge on a **unified renderer architecture** — one
Node view-model, **pluggable presentation shells**, and a **shared lens layer** — so the axes are
truly orthogonal. Concretely: **do REQ-04 before adding a fourth renderer**, or every new shell
re-forks the crown jewel. The mutation graph's own lesson (M2 made everything after it cheap) says the
next high-value mutation is the *second* abstraction pivot, not another feature.

---

*Grounded 2026-08-14. The mutation graph is regenerable (`viz_mutation_graph.py`); this doc is its
narrative. Next: `/skill-creator` for `/reflective-abstraction`, then REQ-04 (the factor-out).*
