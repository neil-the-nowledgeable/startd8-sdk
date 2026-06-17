# Repair Layer — What Would (and Wouldn't) Be Repaired, round3

**Date:** 2026-06-16
**Status:** Findings (shadow-repair + disk-compliance/semantic, round3 N=5)
**Data:** `results/round3/` persisted `repair-shadow/*.json` + `prime-postmortem-report.json`
**Context:** benchmark runs **`--repair-mode shadow`** (observe-only) + deterministic/micro-prime **OFF**

---

## 1. Question

The benchmark ran repair in **shadow** mode — repair observed but did not alter output. What *would*
it have repaired, across both repair layers (file-level and semantic/disk-compliance)? And are the
requirements/implementation for the semantic layer actually in place?

## 2. File-repair layer (syntax / import / lint)

297 cells with a shadow report:

| | count | share |
|---|---|---|
| would **NOT** repair (`no_repairable_failed_checks`) | 245 | 82.5% |
| would **repair** | **52** | 17.5% |

**The 52 are entirely Python, entirely `Import Check`, never OpenAI:**

- by language: python 52 / go 0 / nodejs 0 / csharp 0 / java 0
- by provider: **anthropic 29, gemini 23, openai 0**
- files: only the two Python services — `recommendationservice/recommendation_server.py`,
  `emailservice/email_server.py`

So *syntax/lint* repair never fires (raw output is syntactically clean); the only file-repair work is
**import-completion on Python**, and OpenAI's Python never tripped it.

## 3. Semantic / disk-compliance layer

**Requirements & implementation: BUILT.**
- `docs/design/kaizen/SEMANTIC_REPAIR_REQUIREMENTS.md` — 2,150 lines, Layers 1–4 complete
  (capability → architecture → per-category specs → impl plan). Covers `method_resolution`,
  `import_resolution`, `discarded_return`, `duplicate_main_guard`; **DC-3 dual scoring** (pre/post
  repair) and **Kaizen separation** (assembly delta on the *pre*-repair score).
- Implemented: 5 steps in `src/startd8/repair/steps/semantic_*` + `prime_postmortem.py` carries
  `disk_quality_score`, `disk_compliance`, `semantic_error_count`, `pre_semantic_repair_score`,
  `semantic_repairs_applied`, `semantic_repair_categories`.

**But in this benchmark the layer is nearly idle** (403 feature entries):

| field | populated |
|---|---|
| `disk_quality_score` | 245/403 (ok cells) — **mean 0.959**, range 0.70–1.00 |
| `semantic_error_count > 0` | **4/403** (6 errors total) |
| `semantic_repairs_applied > 0` | **0/403** |
| `pre_semantic_repair_score` (DC-3) | **0/403** |

Frontier-model raw output is already disk-compliant: disk-quality saturates near 0.96, semantic
issues appear in 4 of 403 features, and **nothing triggers a semantic repair**. The DC-3 dual-scoring
machinery, though implemented, recorded **no** pre/post deltas because no repair fired.

## 4. Synthesis — repair value is config-dependent, and this config suppresses it

Across every layer we've now measured on frontier-model raw output, the signal **saturates**:

| Layer | Saturation on raw frontier output |
|---|---|
| compile gate | 98–100% first drafts compile (`TIER_A_PILOT_FINDINGS.md`) |
| structural / disk-quality | mean 0.959 |
| semantic issues | 4/403 features |
| semantic repairs that would apply | 0 |
| file-repair (import) | the *one* place work exists — 52 Python cells |

**This refines the prior "repair carries real value (disk-quality 0.85 → ~1.0)" note.** That figure
came from a **cheaper-tier / different** configuration; on this benchmark (frontier models,
deterministic + micro-prime OFF) the raw output is already clean, so repair's only real work is
Python import-completion. The semantic/disk-compliance repair layer — fully spec'd and implemented —
has essentially nothing to fix here.

## 5. Implication

- To actually **measure semantic repair's uplift** (the DC-3 pre/post delta), you need a config where
  semantic issues are present: **cheaper models (Ollama/local), micro-prime ON, or apply-mode** — the
  benchmark deliberately turns these off to isolate model skill, which is exactly why the layer is idle.
- For the benchmark itself, repair is **correctly a no-op signal** — reporting "what would be repaired"
  (52 Python imports) is the honest extent of it; there is no hidden semantic uplift being masked.
- A future **shadow *semantic*-repair** pass (the un-built v0.2) would, on this data, report ~0 — so
  it is **not worth building for the frontier benchmark**; its value is in the cheap-tier regime.

*Findings complete. Requirements + implementation for the semantic/disk-compliance repair layer are
in place (SEMANTIC_REPAIR_REQUIREMENTS.md, 5 steps, DC-3 fields), but on frontier-model raw output the
layer is idle (disk-quality 0.959, 4/403 semantic errors, 0 repairs). Repair's only real work in this
config is Python import-completion (52 cells); the "0.85→1.0" uplift is a cheaper-tier phenomenon.*
