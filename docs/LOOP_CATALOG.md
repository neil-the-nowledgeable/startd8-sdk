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
