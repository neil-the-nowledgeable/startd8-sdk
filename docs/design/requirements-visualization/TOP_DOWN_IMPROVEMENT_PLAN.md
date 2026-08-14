# Requirements Visualization — Top-Down Improvement Plan

**Date:** 2026-08-14 · **Status:** synthesis locked; Phase 1 REQ/PLAN at **v0.4** (CRP R1 triaged — ready to implement)  
**Scope:** make the latest Node / navigator capabilities available **first and foremost in the
startd8 SDK**, then extend up (authoring / Definer seat) and down (evidence leaves).

> Companion standards (cite, don't restate):  
> [`dev-os/NODE-SCHEMA.md`](../../../../dev-os/NODE-SCHEMA.md) (v0.3.9) ·  
> [`dev-os/HOWTO-VISUALIZE-A-REQUIREMENT.md`](../../../../dev-os/HOWTO-VISUALIZE-A-REQUIREMENT.md) ·  
> [`dev-os/visual-editor/VISUAL-REQUIREMENTS-DEFINER-ROADMAP.md`](../../../../dev-os/visual-editor/VISUAL-REQUIREMENTS-DEFINER-ROADMAP.md) ·  
> Architect stack: [`../kickoff/kits/architect/validation-visualization.md`](../kickoff/kits/architect/validation-visualization.md)

---

## 0. Verdict (why this plan)

“Requirements Navigator” is a **shared grammar** (the Node), not one SDK class. Today the SDK owns
the hard render pieces (`wireframe_view`, `RenderProfile`, summary-first, signoff, min-rolls-up) while
**ContextCore owns the Node model + requirements/capability sources** and reuses the SDK renderer.
Hand-maintained fsn navigators are byte-identical across repos but **evidence-rotten** (counts and
`file:line` refs). The improvement lever is: **make the SDK a first-class Node home**, then grow
from that single substrate — no second renderer, grammar, or requirements store (Definer guards).

---

## 1. What exists (layers)

```
contract  →  wireframe  →  descriptive layer  →  node navigator
(data)       (shape)       (WHAT/WHY/DO/NEXT)     (glance / drill)
```

| Layer | Home | Role |
|-------|------|------|
| Grammar SSOT | `dev-os/NODE-SCHEMA.md` v0.3.9 | DOES / WON'T / LIVES / SHIPS-WHEN + axes |
| Static fsn navigators | `docs/design/{kickoff,wireframe}/README.md`, `docs/capability-index/README.md` | Hand cards; **not** the interactive product |
| App-shape preview | `startd8 wireframe` (+ `--html`, `--describe`) | `$0` planned-app landscape |
| Requirements drafting | `startd8 requirements …` | Writes reqs; does not visualize Nodes |
| Live HTML over Nodes | `contextcore navigator build --source requirements\|capability-index` | Node → wireframe HTML (or a11y) |
| Authoring seat (up) | Loop Studio Definer It-1…It-6 **compose complete** | Graph ↔ det-req ↔ navigator round-trip |
| Recipe | HOWTO §6 | author → evidence gate → render → cruft → audit → score → corpus |

---

## 2. Forks (two senses)

### 2a. Product / renderer forks

```
NODE-SCHEMA
  ├─ Static markdown navigators (hand-maintained)
  ├─ startd8 wireframe HTML (+ descriptive layer)     ← SDK embryo of unified HTML backend
  ├─ ContextCore navigr8 HTML (reuses wireframe + RenderProfile)
  ├─ ContextCore a11y HTML (must not import wireframe)
  ├─ loops-view HTML + Loop Studio HTML
  └─ harbor-tour.html (marketing ≠ NODE-SCHEMA)
```

Authoring-format forks (overlapping intent, different parsers): reflective/CRP · kickoff format ·
det-req · Requirements Panel candidates · capability-index YAML.

### 2b. Worktree forks

Many `ContextCore-*` trees carry `navigator/`. Pin **ContextCore `origin/main`** as the merge target
for cockpit Tier-2/3; local editable installs may lag (HOWTO §1 propagation note — bidirectional).

---

## 3. Grounding refresh applied 2026-08-14

| Artifact | Change |
|----------|--------|
| `dev-os/NODE-SCHEMA.md` | **v0.3.9** — SV-1 footer clause DISCHARGED (FR-SV-12); 66→68 caps; navigr8 MERGED; Requirement `confidence` ADOPTED; SDK named canonical navigator home |
| `docs/capability-index/README.md` | CL-13 `wont` rollout marked SHIPPED; counts/maturity mix refreshed; session_tracking LIVES + APPROVE? re-derived (**ATM survivorship LIE-1 fixed 2026-08-14** — prior stamp had not landed) |


Hand-navigator review ([Review fsn navigators](bd5c5338-e215-46f1-b74f-458c29204826)): **zero copy drift**
sdk↔ctxseed; 8/15 kickoff counts drifted; 3/4 wireframe soft line refs rotted; capability README
premise was a month stale until fixed above.

---

## 4. SDK gap ranking (primary home)

Already in SDK: `worst()` / severity · authored WON'T (descriptive) · SV-10 gap floor · summary-first ·
audience/fluency · signoff lifecycle · `RenderProfile` · `view_model_json`.

| # | Gap | Why first |
|---|-----|-----------|
| 1 | Typed `lives` / evidence on nodes | Grounding backbone; `git:<sha>:<path>` has no carrier |
| 2 | Derived status (evidence × maturity) | Stop hand-stored glyphs |
| 3 | `ships_when` + honest-skip `route_state` in gap denominator | Inv. 7 — parked ≠ defect |
| 4 | Confidence per node (+ 0.9/0.6/0.4 heuristic) | Wireframe navigator operationalized it |
| 5 | First-class **Node source in the SDK** | Invert CC-only ingestion; SDK renders its own navigators |
| 6 | Automated `$0` grounding pass | Kills the staleness class |
| 7–10 | WAS/alias · APPROVE?→signoff · evidence-count column · facet/search | After 1–6 |

---

## 5. Phased ladder

### Phase 1 — SDK is a Node home (this REQ/PLAN pair)

Typed grounding fields · derived status · Node model + projection + sources **in the SDK** ·
CLI to build · automated grounding. See:

- [`REQ-01-sdk-node-home.md`](./REQ-01-sdk-node-home.md)
- [`PLAN-01-sdk-node-home.md`](./PLAN-01-sdk-node-home.md)

### Phase 2 — Down (evidence leaves)

EVIDENCE-1 strong refs in SDK leaves · honest-skip exclusion in `GAP_STATUSES` / `need_items` ·
wire kickoff APPROVE? questions into `signoff.py`.

**Shipped (minimal seam — one store, omit-when-empty):**
- `Approve?:` in det-req → `Node.attributes["approve_prompts"]` → `WireframeItem.approve_prompts`
  → compose (item + rolled-up section) → HTML sign row + export → `load_signoff` /
  `format_signoff` (prompts listed; section ok/flag/unreviewed unchanged).
- Soft `Lives:` → `prefer_git_ref` when path is in HEAD; Lives extracted only before `Verify:`
  (dogfood: Verify prose must not invent evidence).

**Residual (explorer backlog — not required for Phase 2 close):**
- Per-item APPROVE? checkboxes in HTML + answers in the existing `wf-signoff` localStorage map
  (today: prompts display/export only; verdict still section-level).
- Gate unanswered/flagged *question* rows via `open_flags` / exit `1` (optional schema bump).
- Seed kickoff/capability README cards from the same typed prompts (still prose examples today).

### Phase 3 — Up (authoring seat)

Requirements Panel emits det-req/0.1 with `Lives:` · flows into Definer `roundtrip.sh --no-serve` ·
HOWTO §6 becomes the per-iteration improvement loop.

### Explicitly deferred

Interactive/3D fsn navigator · auto-gen navigator READMEs (descriptive OQ-5) · converging all HTML
backends in one PR · FR-KIT Role Kit CLI.

---

## 5.5 ATM — Audit-Then-Metabolize (2026-08-14)

Corpus: `docs/design/requirements-visualization/` + `navigator/` + dogfood `/tmp/req-01-nav.html`.
Phase 1 fan-out (parallel): survivorship · generality · lacuna · cruft (extra).

| Member | Denominator / headline |
|--------|------------------------|
| Survivorship | 5 greens · **4 hold · 1 LIE** (README CL-13 stamp; **fixed**) · dominant shape authored≠propagated (navigator untracked) |
| Generality | Item omit-when-empty **earned**; summary/shape band **app-bound** (P1/P2/P3 confirmed) |
| Lacuna | L1 LIVES glanceable (metabolize) · L2 WAS wired · L3 `DET_REQ_KIT` opt-in wired (fail-loud); Phase 2 residuals / F-CC-1 / Phase 3 **correctly absent** |

| Cruft | Apex still speaks Entities/CRUD zeros; NODE fields flattened; fix at `plan.shape` + profile footer/`renderItem` |

### Phase 1.5 convergence

**Class found: `app-bound wireframe summary/chrome on non-app Node consumers`**
(independently: generality + cruft + lacuna L1). Guard-shaped (not method-shaped).

Representative instances: zeroed `entities/crud_routes/…` in `nodes_to_wireframe_plan` →
`footer_lines` / `_plain_shape`; `renderItem` ignores typed `lives`; capability HTML `profile=None`
→ “Your app”.

**Phase 2 metabolize — DONE 2026-08-14 (user: metabolize).** Class climbed to rung-4:

| Guard | What it does |
|-------|----------------|
| `wireframe/shape_dialect.reject_app_bound_node_shape` | Fail-loud if `nodes>0` and app cascade keys present |
| `nodes_to_wireframe_plan` | Emits `{nodes, sections}` only (calls reject) |
| `footer_lines` / `_plain_shape` / `_plain_status` | Dialect-aware (Nodes/grounded — not Entities/planned zeros) |
| `_template.renderItem` | Paints typed `Lives` when present |
| `tests/unit/navigator/test_metabolize_app_shape.py` | Bite: bad raises · good passes · REQ compose no Entities bleed |

`cruft_lint` on dogfood HTML: bleed gaps **0** (was 8); residual = JS-template redundancy FPs.
Phase 3 record: this §5.5 block. Bus: **no bus peer** (SDK-local class).

---

## 6. Operating recipe (every iteration)

Follow HOWTO §6: normalize to det-req → evidence gate → render → `cruft_lint` → `/cruft-audit` →
score SV-1…10 + Panel Laws → corpus index. Prefer **wireframe + RenderProfile** over a new HTML
backend. Cite NODE-SCHEMA; don't re-spec.

---

## 7. Acceptance test (architect)

Can an architect **glance-approve or reject** the planned / required shape? If the view still reads
as a raw wall, the visualization layer has failed — regardless of grammar elegance.
