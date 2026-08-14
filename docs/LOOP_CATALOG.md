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
