# Repair Capability Capture — Requirements

**Version:** 0.1 (Draft — pre-planning)
**Date:** 2026-06-16
**Status:** Draft
**Owner area:** `src/startd8/benchmark_matrix/` (consumer of persisted run artifacts)
**Related:** `REPAIR_LAYER_FINDINGS_ROUND3.md` (the analysis this generalizes),
`docs/design/kaizen/SEMANTIC_REPAIR_REQUIREMENTS.md`,
`docs/design/repair-pipeline/POST_GENERATION_REPAIR_PIPELINE_REQUIREMENTS.md`

---

## 1. Problem Statement

The SDK has a rich, multi-layer **repair capability** — syntax/import/lint file-repair, four
deterministic **semantic** repair categories (`method_resolution`, `import_resolution`,
`discarded_return`, `duplicate_main_guard`), and a 10-layer **disk-compliance** validator with DC-3
pre/post-repair dual scoring. Every benchmark run (under `--repair-mode shadow`) **persists what
repair would do** per cell — but nothing aggregates it. That signal is a **by-product** of the
benchmark, yet it is **first-class evidence of an SDK capability**: it shows, on real generated code,
exactly what the SDK's repair pipeline can detect and fix.

**This is explicitly NOT a scoring concern.** Repair activity must never enter the scoreboard,
composite, pass-rate, ranking, or any leaderboard artifact (the benchmark measures *model* skill;
repair is *SDK* leverage, deliberately held OFF for scoring). The capture exists to:
1. **Improve the SDK** — surface where repair fires, where it's idle, and where raw output already
   passes, to guide where repair investment pays off.
2. **Narrate the SDK** — feed a fuller "what the SDK does" write-up (capability descriptions:
   "the SDK performs deterministic semantic repair of …"), backed by observed activity.

### Grounding evidence (this is real, persisted, $0 today)

| Signal | round3 | round2 |
|--------|--------|--------|
| file-repair would-fire | 52/297 (17.5%) | 16/81 (19.8%) |
| …all Python, all `Import Check` | yes | yes |
| disk_quality_score mean | 0.959 | 0.953 |
| semantic_error_count > 0 | 4/403 | 3/81 |
| semantic_repairs_applied | 0 | 0 |
| DC-3 pre/post deltas captured | 0 | 0 |

The data exists in `repair-shadow/*.json` + `prime-postmortem-report.json`; only aggregation is missing.

## 2. Requirements

**FR-1 — File-repair capture.** Aggregate `repair-shadow/*.json` per run: would-fire vs would-not,
broken out by failed-check type, language, and provider, plus the concrete files + checks that would
drive repair.

**FR-2 — Semantic / disk-compliance capture.** Aggregate the postmortem fields: `disk_quality_score`
distribution, `disk_compliance` layer detail, `semantic_error_count` by category, and — when present
— the DC-3 `pre_semantic_repair_score` → `disk_quality_score` **uplift delta** and
`semantic_repairs_applied`/`semantic_repair_categories`.

**FR-3 — Capability catalogue (narration, not just counts).** The report pairs *observed activity*
with a *capability description* per layer: what file-repair fixes, what each of the 4 semantic
categories fixes, what the 10 disk-compliance layers check — sourced from the requirements/code so the
write-up can state "the SDK can repair X" alongside "in this run it would have repaired Y."

**FR-4 — Honest idle reporting (the load-bearing nuance).** When a layer has **no activity** (e.g.
semantic repair on frontier raw output), the report MUST distinguish **"capability present but not
exercised"** from "capability absent." Idle ≠ missing. A reader must not conclude the SDK lacks
semantic repair because a frontier run didn't trigger it.

**FR-5 — Config context.** Stamp each capture with the run config (`repair-mode`, deterministic/
micro-prime on/off, model tier) — repair activity is **config-dependent** (frontier raw saturates;
cheap-tier/micro-prime exercises more). The report states the regime so activity is read correctly.

**FR-6 — Cross-run view.** Aggregate across runs (round1→2→3) to show repair-activity trends
(e.g. "OpenAI Python import-completeness: 6 would-fire in round2 → 0 in round3").

**FR-7 — Separate artifact, never scoring.** Emit a standalone **Repair Capability Report**
(`repair-capability.md` + `.json`) in the run dir. It MUST NOT touch `cells.json`, `aggregate.json`,
`leaderboard.md`, `SCORECARD.*`, or any composite/ranking. It MAY be referenced by the fuller SDK
write-up. (Structurally: a sidecar, like the phase-trajectory pattern.)

**FR-8 — $0, persisted-only, advisory.** No regeneration, no LLM, no re-running repair. Pure
aggregation of already-persisted artifacts. A standalone CLI mirroring `rescore_ob_benchmark.py`.

## 3. Non-Requirements

- **Not** a scoring input — no leaderboard/composite/ranking effect (FR-7). This is the hard line.
- **Not** applying or re-running repair — observe/aggregate only (shadow data as-is).
- **Not** a new detector — consumes existing persisted signals; adds no detection logic.
- **Not** exercising semantic repair to manufacture activity — if a run idles the layer, report it
  idle (FR-4); don't switch the run to apply-mode just to populate the report.

## 4. Open Questions

- **OQ-1** — Where does the fuller "what the SDK does" write-up live, and how does it consume the
  report (embed `.md`? read `.json`?)? Decides the report's format contract.
- **OQ-2** — To *showcase* semantic repair (which idles on frontier raw), is a separate **cheap-tier
  or apply-mode demonstration run** worth doing? That would actually populate DC-3 deltas — but it's
  a demonstration, not the benchmark (keep them distinct).
- **OQ-3** — Should the capability catalogue (FR-3) be hand-authored once or derived from the
  requirements docs / routing table at report time? Derived stays in sync but is more work.
- **OQ-4** — Cross-run identity: runs differ in matrix shape (round1/2 = 81 cells, round3 = 405).
  Normalize rates, or report raw + rate? (Likely both, like the scorecard.)

---

*Draft 0.1 — will be updated after a planning pass. Captures the SDK's repair capability as a $0
by-product artifact, strictly outside scoring (FR-7), with honest idle-vs-absent reporting (FR-4) and
config-context labeling (FR-5) so frontier saturation isn't misread as missing capability.*
