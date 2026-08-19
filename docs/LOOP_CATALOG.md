# Loop Catalog

A registry of the **repeatable improvement/verification loops** built in this project, so they can
be found and reused instead of reinvented. A "loop" here = a defined, re-runnable cycle that measures
a subject, names the single highest-value gap, applies the smallest fix, and re-measures — driven by
a script and/or runbook.

> How to add an entry: copy the template at the bottom, fill it in, keep the one-line "does" crisp.
> Cross-link the runbook and the driver. Prefer a measurable "moving number" per loop.

---

## Active loops (built here)

### 1. Pilot Improvement Loop  *(navigator dogfood)*

- **What it does:** improves a NODE-SCHEMA navigator consumer **one node at a time, measurably** —
  `baseline → diagnose → [apply smallest fix] → verify → record` — rolling each node's
  glance-approvability up to a single `pilot_score ∈ [0,1]` and naming the one **TOP GAP** to fix next.
- **Driver:** `scripts/navigator_pilot_loop.py`  ·  **Runbook:** `docs/design/requirements-visualization/PILOT_IMPROVEMENT_LOOP.md`
- **Moving number:** `pilot_score` (status grounded/built · confidence ≥0.9 · all Lives resolve ·
  health not a dishonest done-claim · has APPROVE? prompt).
- **Reusable across consumers (source-aware):**
  - `--source requirements` (default) — REQ-01's own FRs. Confirmed trio FR-6→FR-4→FR-8, all at **1.0**.
  - `--source capability-index` — the 68-node SDK capability manifest. Pilots discovered via `--survey`.
  - Extend to a new consumer by adding a loader + profile to `PILOTS_BY_SOURCE` / `_nodes_for`.
- **Run it:**
  ```bash
  python3 scripts/navigator_pilot_loop.py --status                          # requirements pilots
  python3 scripts/navigator_pilot_loop.py FR-6 --verify                     # one iteration
  python3 scripts/navigator_pilot_loop.py --source capability-index --survey # discover pilots (68 nodes)
  python3 scripts/navigator_pilot_loop.py startd8.codegen.import_path --source capability-index
  ```
- **State:** per-source ledger in `docs/design/requirements-visualization/_pilot/ledger*.{json,md}`.
- **Provenance:** what it caught while dogfooding — a lying status (FR-8 spec→grounded), a
  mis-calibrated scoring signal (health), a parser bug (decimal truncation), a stale manifest Lives
  ref (`import_path`). The loop's value is surfacing gaps no unit test was looking for.
- **Status:** ACTIVE. Requirements consumer complete (trio at 1.0); capability consumer surveyed +
  baselined (systemic finding: manifest carries **no** approve prompts → all nodes cap at 0.85).

### 2. Node Content Improvement Loop  *(child of the Pilot loop)*

- **What it does:** improves a navigator node's **authored content** (orthogonal to the Pilot loop's
  *grounding*) — the deterministic **Name:** and its derived handle/canonical ref, behavior prose,
  acceptance test, objective link, surface, and non-goals — one node at a time via the same
  `baseline → diagnose → author → verify → record` cycle.
- **Driver:** `scripts/navigator_content_loop.py`  ·  **Convention:** `docs/NAMING_CONVENTION.md`
- **Moving number:** `content_score` (name 0.30 · real behavior 0.15 · verify 0.15 · serves 0.15 ·
  touches 0.15 · wont 0.10). The Name signal is the headline — a node identified by its integer key
  alone is the anti-pattern this loop closes; handle + canonical ref derive from the name.
- **Relationship to the Pilot loop:** *sibling, orthogonal.* Both read one shared node→metrics pass
  (`_metrics_of_node`), so grounding and content never re-derive each other. The **Pilot loop calls
  this loop** for its content read and **hands off** when a node is grounding-complete
  (`pilot_score=1.0`) but content-incomplete — e.g. FR-6 is fully grounded yet content_score 0.6
  (no `Name:`).
- **Run it:**
  ```bash
  python3 scripts/navigator_content_loop.py --survey            # rank nodes by content_score
  python3 scripts/navigator_content_loop.py FR-2                # baseline (top gap: NAME)
  python3 scripts/navigator_content_loop.py FR-2 --verify       # after authoring Name: → delta
  ```
- **State:** `docs/design/requirements-visualization/_pilot/ledger-content*.{json,md}`.
- **Status:** ACTIVE. Requirements: FR-1 authored (content 0.9), FR-2…FR-10 need `Name:` (0.6).

### 3. Chrome Origin Audit  *(audit sub-loop)*

- **What it does:** traces every **apex/chrome** element of a navigator view (eyebrow · headline ·
  summary meta · why · do · status band · shape band · legend · sections · node keys) to its
  **origin** — a RenderProfile field, a computed aggregate, or the node data — and flags any
  **orphan** (chrome with no source value). Answers "where does this text come from?" and enforces
  Kagami: the mirror must not show sourceless hand-drawn chrome.
- **Driver:** `scripts/navigator_origin_audit.py`  ·  **Core:** `src/startd8/navigator/provenance.py`
- **Moving number:** `chrome_score` = fraction of chrome elements that trace to a present source
  (1.0 = no orphans). Exit 1 on any orphan.
- **Companion view feature (FR-11 structure-only):** with **Structure only** on, each remaining
  element also shows its **available metadata** inline (`type · default · provenance · ← origin`),
  so the skeleton carries its provenance — the audit made visible on the page.
- **Run it:**
  ```bash
  python3 scripts/navigator_origin_audit.py --source node-schema   # trace + score the chrome
  python3 scripts/navigator_origin_audit.py --source requirements --record
  ```
- **State:** `docs/design/requirements-visualization/_pilot/ledger-origin*.json`.
- **Status:** ACTIVE. All three sources score 1.0 (no orphan chrome).

### 4. Cruft Sentinel  *(triggers /audit-then-metabolize)*

- **What it does:** enforces the stance **all content is cruft until proven otherwise** on the
  rendered navigator views. Every chrome element is presumed guilty; proof = a traceable origin
  (Chrome Origin Audit). What can't prove its origin (an **orphan**) is cruft. When cruft is found the
  loop does not patch it inline — it **triggers `/audit-then-metabolize`** on the offending corpus
  (prints the exact invocation + writes a findings artifact), so cruft is diagnosed→cured as a class,
  not swept under the render.
- **Driver:** `scripts/navigator_cruft_loop.py`  ·  **Signals:** chrome orphans (deterministic) +
  `cruft_lint` gaps (advisory; JS-template FPs flagged).
- **Moving number:** cruft count (0 = clean, exit 0; >0 = exit 1 + the ATM trigger directive).
- **Run it:**
  ```bash
  python3 scripts/navigator_cruft_loop.py --all           # sweep every view
  # cruft found → "TRIGGER → /audit-then-metabolize (corpus: navigator views [...])"
  ```
- **State:** `docs/design/requirements-visualization/_pilot/ledger-cruft.json`.
- **Live counterpart:** the debug panel's provenance readout (FR-13) shows the same score/cruft
  in-view (green = clean, ochre = cruft).
- **Status:** ACTIVE. All views clean (provenance 1.0) — armed, not currently triggering.

### 5. Inspect Loop  *(the constructive inverse of the Cruft Sentinel)*

- **What it does:** on the non-node-driven chrome that **survived** the cruft pass (masthead · summary
  band · legend), it presumes a **legacy value** (not guilt) and hunts for the **derivative value or
  updated context** that makes each element useful in the current sense. Output is a repurpose /
  enhancement worklist, not a purge. Where the Cruft Sentinel asks "prove your origin or be purged,"
  the inspect loop asks "you were built for a reason — what derivative value could you carry now?"
- **Driver:** `scripts/navigator_inspect_loop.py`  ·  **Core:** `src/startd8/navigator/inspect.py`
- **Moving number:** `inspect_score` = realized / total. Verdicts: **realized** (derivative value
  already serving) · **candidate** (latent value to wire) · **uninspected** (chrome with no inspection).
- **Trigger (opposite polarity to the Cruft Sentinel):** when **candidates** remain, it recommends
  **/enhancement-backlog** (wire the derivative value / expose the plumbing that already exists) —
  the generative counterpart to cruft → /audit-then-metabolize.
- **Run it:**
  ```bash
  python3 scripts/navigator_inspect_loop.py --source requirements
  # e.g. status_band ◆ CANDIDATE → grounding composition as an interactive filter
  ```
- **State:** `docs/design/requirements-visualization/_pilot/ledger-inspect.json`.
- **Status:** ACTIVE. requirements: 7/9 realized; **candidates: status_band, shape_band** (their
  count roll-ups have latent derivative value as debugging filters).

---

### 6. Spec Delivery Loop  *(the forward loop — spec → merged implementation)*

- **What it does:** turns a build-ready det-req SPEC into a landed IMPLEMENTATION under engineering
  discipline, semi-autonomously. Seven stages: **0 GATE** (deterministic build-readiness) → **1 PREP**
  (out-of-cast readiness + decisions) → **2 BUILD** (agent in an isolated worktree) → **3 GATE-2**
  (full suite + byte-identity UNEDITED + no-forbidden-import + ruff) → **4 REVIEW** (human reads the
  diff) → **5 LAND** (git cadence, own files only) → **6 RECORD** (ledger) → **7 HARVEST**
  (`/harden-then-harvest` on the shipped surface — now an official closing stage, not just a complement).
  The human stays in the loop at stages 1, 4, and HTH's between-phase offers in 7 — that is what makes
  it *semi*-autonomous. Proven on REQ-03/04 before naming.
- **Driver (gate):** `scripts/navigator_spec_delivery_loop.py`  ·  **Runbook:**
  `docs/design/requirements-visualization/SPEC_DELIVERY_LOOP.md`
- **Moving number:** specs delivered (build-ready → merged) with byte-identity preserved. Stage-0
  readiness is the guard: name block · single-line FRs that parse · every FR has Name/Verify/Serves.
- **Reuse (Kagami/Mottainai):** the gate calls the SDK's own `det_req.parse_fr_lines` — the same parser
  the corpus is governed by, not a second one. Stage 0 **is REQ-06 corpus governance in embryo**
  (scoped to the one precondition that guards a build); when REQ-06 lands, stage 0 should call it.
- **Run it:**
  ```bash
  python3 scripts/navigator_spec_delivery_loop.py --status     # readiness of every REQ-*.md
  python3 scripts/navigator_spec_delivery_loop.py REQ-05       # gate one (exit 1 if blocked)
  python3 scripts/navigator_spec_delivery_loop.py --checklist  # the 7-stage runbook
  ```
- **Stage 7 (HARVEST) — Check→Act back-half:** **`/harden-then-harvest`** is now an official closing
  stage (not just a complement) — run it on the surface this loop ships. Delivery's Plan→Do arc ends at
  RECORD, which hands off to HARVEST (code-review §1.5 value-path → python-code-refactor →
  reflective-retrospective §2.5 dormant inventory → cumulative-enhancement → bus/Yokoten). It catches
  built-but-unwired defects a green GATE-2 misses and harvests the standard + a ranked backlog; runs on
  a substantial delivery (scale down / skip a trivial one). See the runbook's "Stage 7 — HARVEST" section.
- **State:** the gate is stateless (reads the spec live); outcomes recorded in `SESSION_LEDGER`.
- **Status:** ACTIVE. Build-ready: REQ-02/03/04/05/06/07/08; blocked: REQ-01 (`frs-named`), seat-req.

### 7. Corpus Governance Loop  *(the corpus-wide governor — the discipline REQ-06 formalizes)*

- **What it does:** governs a whole DIRECTORY of `REQ-*.md` docs against the corpus contract, then
  routes recurring drift to the metabolize skills. The corpus-wide generalization of loop #6's
  stage-0 gate: where #6's `gate_spec` guards ONE spec's build-readiness, this runs a fixed 5-check
  battery — **name-block presence · single-line-FR · dangling cross-ref · coverage · index-freshness**
  — over the whole corpus and emits a pass/fail governance report (0=clean / 1=drift / 2=error).
  Read-only (NR-2): a fix is a human edit or a downstream-skill hand-off, never an inline rewrite.
- **Driver:** `startd8 navigator govern --dir <corpus> [--format text|json] [--out …]`
  (`src/startd8/navigator/govern.py` · CLI in `cli_navigator.py`)  ·  **Spec:**
  `docs/design/requirements-visualization/REQ-06-corpus-governance.md`
- **Moving number:** `govern_score` = clean checks / total checks (5). 1.0 = the corpus obeys its
  discipline; each fail-severity finding names the exact doc + FR + fix.
- **Reuse (Kagami/Mottainai — FR-9):** every check reads through the ONE shared parser + health model
  (`det_req.parse_fr_lines`, `render_a11y.ReqView`, `render_index._req_summary`, `naming.name_forms`).
  `govern.py` owns no second parser, FR parser, or health model. The stage-0 `gate_spec` was **lifted**
  from the loop-#6 driver into `govern.py` (one home) and re-exported there, so #6's gate and #7's
  governor read a spec identically.
- **Precision (FR-8):** a hard acceptance test — the current corpus (REQ-01..09) governs with **zero
  fail-severity** findings; a check that can't reach zero false positives degrades to **advisory**
  (reported, never fails the exit code) so the pass never cries wolf. Charter-bounded (NR-6): a new
  check needs a demonstrated real drift + a rationale here.
- **Run it:**
  ```bash
  startd8 navigator govern --dir docs/design/requirements-visualization           # text, exit 0/1/2
  startd8 navigator govern --dir docs/design/requirements-visualization --format json
  ```
- **Drift routing:** cruft → `/audit-then-metabolize`; a finding-class recurring across ≥2 docs →
  `/metabolize-finding` (make the class structurally impossible), surfaced by the CLI. Ledger under
  `docs/design/requirements-visualization/_pilot/` when run as a loop.
- **Status:** ACTIVE. REQ-01..09 clean (govern_score 1.0); seat-req is a legitimate real finding
  (stage-0-blocked), not a false positive.

### 8. Review-Theme Metabolizer  *(cross-kit — the CRP review-wisdom shift-left)*

- **What it does:** turns the CRP corpus's **re-derived** review concerns into **fired grammar rules**, so a
  settled concern surfaces once (at draft time + in the review prompt) instead of being re-sought review
  after review. Cycle: **census** (rank the 7,299 accepted suggestions by theme) → **promote** (a recurring
  theme → a PATTERN-CATALOG entry) → **metabolize** (`/metabolize-finding`: theme → a concrete grammar rule)
  → **lint** (the rule fires as an advisory fact-rung at draft time + as a "settled themes — do not re-derive"
  block in the review prompt) → **re-census** (the theme's re-seek rate drops). The KAIZEN "don't re-derive
  lessons" move applied to the review corpus.
- **Driver (cross-kit):** census `~/Documents/dev/dev-os/scripts/render_crp_index.py` (`REVIEW_THEME_RULES`)
  · catalog `dev-os/PATTERN-CATALOG.md` + `contextcore learning pattern_catalog recall` · metabolizer
  `/metabolize-finding` · lint host `dev-os/det-req-kit/extract.py::collect_findings` · review-prompt
  generator `~/.claude/skills/new-cnvrg-rvw-prmpt/SKILL.md`.  ·  **Spec:**
  `docs/design/requirements-visualization/REQ-32-draft-time-firing-wire.md`
- **Moving number:** **re-seek rate** for a metabolized theme — how often a *settled* concern is re-derived
  in a fresh review (goal → 0). A wired theme's re-seek rate collapses once its lint fires; a rising re-seek
  rate = a theme that slipped back to dormant.
- **Scope (FR-5):** **cross-kit family capability**, not det-req-kit-only — the census / catalog / metabolizer
  serve every det-doc-kit member (det-req / plan / handoff / howto / crp), and the firing seam fuels both the
  authoring surface and the review surface.
- **Run it (once the firing seam lands):**
  ```bash
  python3 ~/Documents/dev/dev-os/scripts/render_crp_index.py       # census: theme counts
  contextcore learning pattern_catalog recall <theme>              # is the theme promoted + queryable?
  # draft-time: det-req-kit extract.py fires the fact-rung lint (advisory, exit-unchanged)
  ```
- **State:** `dev-os/CRP-INDEX.md` (census) + `dev-os/PATTERN-CATALOG.md` (promoted themes, PC-16..18+).
- **Status:** **REGISTERED — firing seam pending REQ-32.** The metabolization pipeline is built end-to-end;
  only the draft-time firing wire is missing (REQ-32, spec `e3560ca3`). Cross-repo build handed off in
  `HANDOFF_devos-req32-draft-time-firing-wire.md` (5/6 FRs land in dev-os/skills; **this catalog entry is
  REQ-32's SDK-local slice, FR-5**).

---

## Related established loops in the repo (cross-reference)

These predate this catalog; listed so the registry is a complete map. See CLAUDE.md for detail.

| Loop | What it does | Where |
|------|--------------|-------|
| **Kaizen quality loop** (Phases A–E) | cross-**run** quality measurement → suggestions injected into next run's prompts | `contractors/prime_postmortem.py`, `docs/design/kaizen/` |
| **Repair pipeline** | post-generation syntax/lint/import/semantic repair, routed per failure class | `repair/orchestrator.py` |
| **Mottainai persist-then-rescore** | generate servers once, re-score for **$0** as the harness improves | `scripts/rescore_behavioral.py` |
| **Reflective requirements** (skill) | draft reqs → plan → fold planning insight back before coding | `/reflective-requirements` |
| **Convergent Review Protocol** (CRP, skill) | multi-model review rounds persisted into a doc's appendices | `/new-cnvrg-rvw-prmpt` |
| **Cruft-Expunge Loop** (dev-os) | rung-4 `cruft_lint` mechanical bleed/cruft detector on rendered artifacts | `~/Documents/dev/dev-os/scripts/cruft_lint.py` |

---

## Entry template

```
### N. <Loop Name>
- **What it does:** <one line — subject, cycle, outcome>
- **Driver:** <script>  ·  **Runbook:** <doc>
- **Moving number:** <the metric it improves>
- **Run it:** <commands>
- **State:** <where the ledger/artifacts live>
- **Status:** ACTIVE | PARKED | RETIRED
```
