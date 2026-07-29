# WLQ CRP Drain Reliability — Enhancement Backlog (CEP Round 1)

**Subject:** startd8 Workflow Loop Queue CRP multi-round drain (Cursor Tasks + auto-consume) after the 2026-07-29 Thanos design-unit footguns  
**Spec / surface:** `docs/design/cursor-workflow-loop/` (VASI, HOWTO_BUILD, HOWTO_AGENT_ENQUEUE) · `src/startd8/workflows/loop_queue/` · `dev-os/cursor-loops/templates/auto-consume.sh`  
**Shipped surface graded against:** working tree 2026-07-29 (doc_highest gates + auto-consume S/F preflight already landed)  
**Produced by:** CEP — 3 seeders (A hung → orchestrator fill from greps; B ops UX; C robustness) + 1 cumulate round + lineage triage  
**Status:** proposed. Human picks S/M/L. Phase-4 may auto-exec XS/clearly-mechanical-S to a PR only.

> **Honesty note.** Seeders read specs + code. Every `fix` row carries a grep confirming it is still open. Re-open cited lines before building.

---

## Provenance

### Prior-art manifest (FR-9 — greps actually run)

```bash
# Dedicated WLQ ENHANCEMENT_BACKLOG?
rg -l 'ENHANCEMENT_BACKLOG' docs/design/cursor-workflow-loop/
  → HOWTO_AGENT_ENQUEUE.md (references other subjects' backlogs only)
  → NO WLQ_CRP_DRAIN_ENHANCEMENT_BACKLOG.md  ← this file creates it (no duplicate)

# Sibling remediation CEP (explicitly out-of-scopes WLQ)?
rg -n 'WLQ|V-1|out of scope' \
  ~/Documents/dev/ContextCore/docs/design/REMEDIATION_LOOP_ENHANCEMENT_BACKLOG.md
  → marks WLQ V-1/V-2/V-3 "live in startd8, cross-repo, out of scope"

# Tonight already shipped (VOID as open defects)?
rg -n '_doc_highest_round|doc_highest' src/startd8/workflows/loop_queue/queue.py
  → present (drain gate + triage + finish_review_phase)
rg -n 'not severity labels|S/F' src/startd8/workflows/loop_queue/models.py \
  ~/Documents/dev/dev-os/cursor-loops/templates/auto-consume.sh
  → present (DrainResult + auto-consume preflight)
rg -n 'test_doc_saturated_rounds_finish_without_phantom_r4' \
  tests/unit/workflows/loop_queue/test_agent_surface_crp.py
  → present

# Gaps still open?
rg -n 'timeout=' src/startd8/workflows/loop_queue/renderer.py
  → subprocess.run(...) at :218 with NO timeout=  ← OPEN
rg -n 'flock|auto-consume.pid' ~/Documents/dev/dev-os/cursor-loops/templates/auto-consume.sh
  → none  ← OPEN
rg -n 'finish.from|finish_from_docs' src/startd8/cli_wloop.py
  → none  ← OPEN
```

**Hansei / fix archive fed to seeders (dedup):**  
`ContextCore/docs/design/remediation/thanos/_HANSEI_2026-07-29_wlq-crp-design-unit.md` ·  
`craft/Lessons_Learned/skills/python-code-refactor/archive/2026-07-29-wlq-loop-code-review-fix.md`

### CEP run shape & kill-metric (R-4)

- **Seeders:** A core-plumbing (orchestrator fill after agent hang) · B ops/UX (`254f4281`) · C robustness (`bb6bda1d`) → ~18 ideas  
- **Cumulate:** 1 round on the union → 3 CROSS + 4 VARY + 2 NEW kept after triage  
- **Triage-surviving off-seed (forwarded):** CROSS render-timeout+handoff-arm · CROSS finish-from-docs+stale-drain runbook · CROSS flock+pidfile watcher · VARY skill S/F example · VARY `wloop watch` from status · NEW HOWTO drift CI · NEW OTel meters  
- **Off-seed yield ≫ 0 → CEP earned keep this run.**

### Write-target
Repo `startd8-sdk`, path `docs/design/cursor-workflow-loop/WLQ_CRP_DRAIN_ENHANCEMENT_BACKLOG.md` on the working branch (docs-only persist). Phase-4 applies on an isolated branch off `origin/main` if/when executed.

---

## Ranked backlog (defect-first, best-of-lineage)

### EC-WLQ-01 — Renderer subprocess timeout (fail-loud) ⭐
**Type:** fix · **Effort:** XS · **Value:** HIGH (unblocks silent ~90s+ `run-next` stalls)  
**Lineage:** C1 · A-fill (same gap)  
`renderer.py:218` `subprocess.run(cmd, capture_output=True, text=True)` has **no** `timeout=`. Hang in `new-cnvrg-rvw-prmpt` stalls the drain lease with no error.  
*Grep (open):* `rg -n 'subprocess.run' renderer.py` → `:218` without timeout.  
**Verify:** unit test mocks hang → `TimeoutExpired` → `LoopQueueBlockedError` with stderr snippet.  
**Phase-4 eligible:** YES (mechanical).
**Phase-4 status:** applied on `cep/wlq-drain-xs` (→ [PR #368](https://github.com/neil-the-nowledgeable/startd8-sdk/pull/368)) — renderer timeout + unit test.

### EC-WLQ-02 — `finish-from-docs` CLI escape hatch
**Type:** wire-existing · **Effort:** S · **Value:** HIGH (operator recovery after failed drain-result)  
**Lineage:** CROSS(C4 + B5) — CLI wraps existing `_finish_review_phase` / doc_highest gate; runbook names when to use it  
Expose `startd8 wloop finish-from-docs --job-id …` that refuses unless `doc_highest >= max_rounds` (or `--i-confirm` with reason). Prevents phantom requeue after Appendix C is already R1..Rmax.  
*Grep (open):* no `finish_from` in `cli_wloop.py`.  
**Verify:** fixture with R1..R3 in docs + 2 recorded rounds → command completes + auto_accept; without saturation → exit 2.

### EC-WLQ-03 — auto-consume single-flight lock (+ optional pidfile)
**Type:** fix · **Effort:** XS–S · **Value:** HIGH (duplicate consume races seen live)  
**Lineage:** CROSS(C2 + C3 VARY) — flock is XS; pidfile is the S half for visibility  
`flock -n` on `$JOB_DIR/auto-consume.lock`; write `auto-consume.pid`; refuse second watcher.  
*Grep (open):* no `flock` / `.pid` in template.  
**Verify:** two overlapping `--once` invocations → second exits 1 with clear message; first still consumes.  
**Phase-4 eligible:** flock half YES; pidfile optional same PR.
**Phase-4 status:** applied in `dev-os` (`cursor-loops/templates/auto-consume.sh`) via portable `mkdir` lock + pidfile (macOS has no `flock`). **No PR:** `dev-os` has no git remote and `cursor-loops/templates/` is untracked — change is in the working tree only.

### EC-WLQ-04 — Handoff card emits copy-paste auto-consume arm line
**Type:** wire-existing · **Effort:** S · **Value:** MED-HIGH  
**Lineage:** B2 · CROSS with C6 (template path discoverability)  
Markdown handoff already exists; append:
`STARTD8_WLOOP_ROOT=… ./auto-consume.sh --job-id … --watch-rounds N`  
**Verify:** snapshot test on rendered handoff.md contains the job_id and `--watch-rounds`.

### EC-WLQ-05 — Skill / Task-prompt DrainResult exemplar (S/F only)
**Type:** fix · **Effort:** XS · **Value:** MED (prevents recurrence of severity-key FAILED)  
**Lineage:** B1 VARY — skill mentions `suggestion_counts` but not the severity anti-pattern  
Add a minimal JSON exemplar + “NOT blocking/major/minor/nit” to `.cursor/skills/workflow-loop-queue/SKILL.md` and any packaged CRP Task brief.  
*Grep:* skill lists fields but no severity ban string.  
**Verify:** `rg -n 'severity|blocking/major' SKILL.md` finds the ban.  
**Phase-4 eligible:** YES (docs-only).
**Phase-4 status:** applied on `cep/wlq-drain-xs` (→ [PR #368](https://github.com/neil-the-nowledgeable/startd8-sdk/pull/368)) — S/F exemplar + severity ban in SKILL.md.

### EC-WLQ-06 — `startd8 wloop watch` (status stream)
**Type:** wire-existing · **Effort:** S · **Value:** MED  
**Lineage:** B3 — reuses existing status + `drain_result_exists` already in pilot status rows (`queue.py:203`)  
Poll compact row: status, round, lease, drain-result present, handoff age.  
**Verify:** `--once` prints one JSON row; `--interval` exits on terminal status.

### EC-WLQ-07 — Stale-drain recovery runbook (HOWTO)
**Type:** fix · **Effort:** S · **Value:** MED  
**Lineage:** B5 · absorbs C6 “sync HOWTO” as a section, not a new CLI init engine  
Decision tree: expired lease · stale drain-result · FAILED after Appendix C write · awaiting_triage · when to `finish-from-docs` vs requeue.  
**Verify:** link from SKILL + HOWTO_BUILD; checklist items are copy-paste commands.

### EC-WLQ-08 — Refuse new handoff while live drain-result has wrong round (fail-closed)
**Type:** fix · **Effort:** S · **Value:** MED  
**Lineage:** A-fill NEW — storage already archives on success; live file can still poison next round  
Before writing a new handoff in `processing`, if `drain-result.json` exists and `round_number != expected`, fail closed with archive instructions.  
**Verify:** plant stale R1 JSON while opening R2 → validation error naming both rounds.

---

## Wildcard section (orthogonal, single-seeder, no descendants)

### WC-WLQ-01 — HOWTO/skill drift CI check
**Type:** new-capability · **Effort:** M · **Origin:** B6 alone  
Parse documented `startd8 wloop` subcommands vs `--help` / recipe registry in CI.  
**Why wildcard:** no VARY/CROSS parents; catches class of lag beyond tonight’s S/F prose.

### WC-WLQ-02 — WLQ OTel meters (`wlq.job.*`)
**Type:** new-capability · **Effort:** M · **Origin:** C5 alone  
Counters/histograms for drain/complete/fail durations. Useful once watch/runbook exist; not required to stop tonight’s footguns.

---

## Absorbed / demoted (Appendix-B style)

| Idea | Fate | Why |
|------|------|-----|
| Re-propose doc_highest / S/F preflight / phantom-R4 test | VOID | Already shipped (Phase-0 greps) |
| Auto-backfill RoundRecords from Appendix C without drain-result | DECLINED | Provenance theater (Hansei + prior code-review declined) |
| `startd8 wloop init-watcher` copy engine | Demoted into EC-WLQ-07 | Accidental complexity; path cite on handoff (EC-WLQ-04) is enough |
| Nominal CROSS that was only a VARY of C1 | Demoted | Goodhart guard |

---

## Phase 4 plan (trivial tier)

| ID | Action |
|----|--------|
| EC-WLQ-01 | Auto-apply: `timeout=` + TimeoutExpired → BlockedError + unit test |
| EC-WLQ-03 | Auto-apply: `flock -n` (+ pidfile write) in auto-consume.sh |
| EC-WLQ-05 | Auto-apply: SKILL.md exemplar + severity ban |
| EC-WLQ-02,04,06,07,08 + wildcards | Left for human (judgment / larger) |
