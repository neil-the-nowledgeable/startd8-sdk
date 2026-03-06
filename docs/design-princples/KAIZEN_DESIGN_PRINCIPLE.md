# Kaizen Design Principle

Purpose: establish a cross-cutting design principle for the startd8-sdk pipeline — systematic, continuous improvement of pipeline effectiveness through disciplined analysis of every run's outputs, successful and unsuccessful alike.

This document is intentionally living guidance. Update it as new improvement cycles are identified.

---

## The Principle

**Kaizen** (改善) — "change for the better." In manufacturing and business, Kaizen is the philosophy of continuous improvement through small, incremental changes driven by observation and measurement. Every worker on the line is empowered to identify waste, suggest improvements, and verify results.

Applied to the pipeline: **every run — successful or failed — produces observable outcomes that, when systematically analyzed, reveal concrete opportunities to improve the next run. No run's output should be discarded unexamined. The pipeline should get measurably better over time.**

---

## Relationship to Mottainai

Kaizen is a significant manifestation of the [Mottainai Design Principle](./MOTTAINAI_DESIGN_PRINCIPLE.md). Where Mottainai focuses on **forwarding existing artifacts** to avoid wasteful regeneration within a single run, Kaizen focuses on **learning across runs** to avoid repeating the same mistakes and to amplify what works.

| Dimension | Mottainai | Kaizen |
|-----------|-----------|--------|
| **Scope** | Single pipeline run | Across runs over time |
| **Focus** | Don't discard artifacts | Don't discard lessons |
| **Waste eliminated** | Redundant LLM regeneration | Repeated failures, missed optimizations |
| **Mechanism** | Artifact forwarding | Observation → Analysis → Action → Verification |
| **Question** | "Has this already been computed?" | "Have we seen this problem before, and what worked?" |

Together they form a complete anti-waste strategy: Mottainai prevents waste within a run; Kaizen prevents waste across runs.

---

## Why This Matters

The Prime Contractor workflow (and Artisan pipeline) already produces rich diagnostic output after every run:

1. **Post-mortem reports** — root-cause classification (16 failure types across 9 pipeline stages), cross-feature pattern detection, cost outlier flagging, and actionable lessons extraction
2. **Walkthrough prompts** — complete prompt capture (system + user for spec/draft/review phases) enabling pre-run quality analysis without LLM cost
3. **Generation manifests** — per-feature success/failure, cost, token counts, source checksums
4. **Micro Prime metadata** — tier classifications, escalation reasons, repair steps applied, per-element timing

This output represents invested diagnostic computation. Today it is examined ad-hoc by human operators. Under Kaizen, it is **systematically consumed** by the pipeline itself to improve subsequent runs.

---

## The Kaizen Cycle (PDCA)

The Kaizen cycle follows the classic Plan-Do-Check-Act (PDCA / Deming cycle), adapted for LLM pipeline operations:

### Plan — Identify improvement targets from prior run data

Analyze post-mortem reports, walkthrough evaluations, and generation metadata to identify:
- Recurring failure root causes (e.g., `DUPLICATE_IMPORT` appearing in 40% of runs)
- Prompt patterns correlated with high/low quality scores
- Cost outliers by feature type, model tier, or element complexity
- Escalation hotspots (elements frequently bumped from SIMPLE→MODERATE→COMPLEX)

### Do — Apply targeted improvements to the next run

Translate observations into concrete pipeline adjustments:
- Prompt template refinements based on prompt-response correlation
- Complexity classifier threshold tuning based on escalation frequency
- Template registry expansion for recurring element patterns
- Repair pipeline rule additions for recurring failure signatures

### Check — Measure improvement against baseline

Compare the improved run's metrics against prior runs:
- Success rate delta (overall and per-tier)
- Cost delta (total and per-feature)
- Escalation rate delta
- New failure types introduced vs. existing failures resolved

### Act — Standardize successful improvements, investigate regressions

- Improvements that hold: codify into defaults (threshold values, template entries, prompt patterns)
- Regressions: root-cause analyze and revert or adjust
- Update this document with new improvement cycles

---

## Application Rules

### Rule 1: Preserve All Run Outputs

Every pipeline run must persist its full diagnostic output regardless of success or failure. No run artifact should be cleaned up before analysis is possible.

**Applies to:**
- Post-mortem report JSON + summary markdown
- Walkthrough prompt directories
- Generation manifests
- Queue state snapshots
- Integration history entries with generation metadata

**Anti-pattern:** Deleting `.startd8/` output between runs, or only preserving successful run artifacts.

### Rule 2: Prompt-Response Pairing

The most valuable unit of analysis is a paired prompt and its corresponding LLM response. The pipeline must be able to correlate what was asked with what was produced.

**Current gap (from PRIME_CONTRACTOR_PROMPT_AUDIT_FINDINGS.md):**
- Walkthrough mode captures prompts but skips execution (no responses)
- Post-mortem captures results but not prompts
- Neither provides paired prompt-response audit trails during real runs

**Kaizen requirement:** Close this gap so that every LLM call's prompt is recoverable alongside its output.

### Rule 3: Measure Before and After

Every improvement must be measurable. Before applying a change, establish a baseline from prior run data. After applying the change, compare against that baseline using the same metrics.

**Key metrics:**
- Feature success rate (pass/partial/fail distribution)
- Per-tier success rate (TRIVIAL/SIMPLE/MODERATE/COMPLEX)
- Cost per successful feature
- Escalation rate (tier bumps / total elements)
- Repair step frequency (which repairs fire most often)
- Prompt quality score (requirement/constraint coverage from walkthrough evaluator)

### Rule 4: Small, Attributable Changes

Each improvement cycle should change one variable at a time so that metric deltas can be attributed to specific changes. Batch improvements obscure causation.

**Anti-pattern:** Simultaneously changing prompt templates, complexity thresholds, and repair rules, then observing aggregate metrics.

### Rule 5: Feed Forward, Not Just Back

Kaizen insights should flow forward into the next run's configuration, not just backward into documentation. The pipeline should support configuration injection from prior analysis.

**Examples:**
- Post-mortem identifies `PHANTOM_IMPORT` as top failure cause → next run's prompt includes explicit import constraint
- Walkthrough evaluator scores requirement coverage at 60% → next run's prompt template adds missing requirement sections
- Cost outlier detected for MODERATE-tier elements → complexity router threshold adjusted

### Rule 6: Automate the Cycle

Manual analysis is the starting point; automation is the goal. Each Kaizen cycle should progress from manual observation to scripted analysis to automated feedback.

**Maturity levels:**
1. **Manual** — Human reads post-mortem, identifies issue, manually adjusts config
2. **Scripted** — Script aggregates metrics across runs, human decides on action
3. **Semi-automated** — Pipeline suggests improvements based on pattern detection, human approves
4. **Automated** — Pipeline applies low-risk improvements automatically (e.g., template additions for recurring patterns)

---

## Existing Capabilities Inventory

Before building new capabilities, Kaizen leverages what already exists across the **Capability Delivery Pipeline** (`cap-dev-pipe`) and the **startd8 SDK**:

### Pipeline Orchestration Layer (cap-dev-pipe)

| Capability | Source | Kaizen Use |
|-----------|--------|------------|
| Run isolation | `run-atomic.sh` | Timestamped run directories (`pipeline-output/{project}/run-NNN/`) with `latest` symlink — this IS the archive infrastructure |
| State archiving | `run-atomic.sh` Phase 5 | Archives `.prime_contractor_state.json` and `.startd8/state/` into run directory on completion |
| Run metadata | `run-atomic.sh` | `run-metadata.json` with run_id, timestamp, route, plan, requirements, project_root |
| Provenance chain | `resolve-provenance.py` | Input fingerprints (checksums, file paths) linked across stages via `run-provenance.json` |
| Artisan post-mortem | `run-artisan.sh:364-388` | Reads and displays post-mortem verdict/score/lessons after artisan runs |
| Dual-route comparison | `run-compare.sh` | Side-by-side cost/duration/success metrics for prime vs. artisan on same seed |
| Target cleanup | `run-clean-target.sh` | Pre-run artifact cleanup with interactive confirmation |
| Project wrapper | `{project}-cap-dlv-pipe.sh` (template) | Project-specific entry point with default language injection |
| Pipeline requirements | `design/pipeline-requirements.md` | Always injected as additional requirements alongside plan-specific requirements |

### SDK Analysis Layer (startd8-sdk)

| Capability | Source | Kaizen Use |
|-----------|--------|------------|
| Post-mortem evaluation | `prime_postmortem.py`, `scripts/run_prime_postmortem.py` | Root-cause classification (16 types, 9 stages), pattern detection, lessons extraction |
| Walkthrough mode | `prime_contractor.py:_persist_walkthrough_prompts()` | Prompt quality analysis without LLM cost |
| Super walkthrough | `scripts/run_super_walkthrough.py` | Cross-contractor prompt comparison, overlap analysis, diffs |
| WalkthroughPromptEvaluator | `contractors/postmortem.py` | Requirement/constraint coverage scoring |
| Generation manifest | Pipeline mode output | Per-feature success/cost/token tracking |
| Micro Prime metadata | `prime_adapter.py` | Tier classification, escalation, repair step tracking |
| Retrospective system | `artisan_phases/retrospective.py` | Anti-pattern detection, lesson categorization |
| AntiPatternDetector | `artisan_phases/retrospective.py` | Structural anti-pattern identification |
| Resume cache | `.startd8/state/` | 3-layer validation (schema version → source checksum → file hash) |

### Key Insight: Pipeline Orchestration Is the Implementation Home

The cap-dev-pipe already solves K-5 (run artifacts overwritten) via `run-atomic.sh`'s timestamped run directories. The remaining Kaizen gaps (K-1 through K-4) should be implemented as **extensions to the cap-dev-pipe orchestration scripts**, not as SDK-internal changes, because:

1. The pipeline scripts control when stages run and where outputs go
2. Post-mortem integration for artisan already lives in `run-artisan.sh` — prime needs parity
3. Cross-run analysis is naturally a pipeline-level concern (comparing runs in `pipeline-output/`)
4. Feedback injection (kaizen config) belongs at the pipeline invocation layer

---

## Current Gaps (Baseline)

### Gap K-1: No Prompt Capture During Real Runs

Post-mortem captures results but not prompts. Walkthrough captures prompts but skips execution. There is no mechanism to persist prompts alongside their outputs during actual LLM-calling runs.

**Impact:** Cannot correlate prompt quality with output quality. Cannot identify which prompt patterns produce better code.

### Gap K-2: No Cross-Run Metric Aggregation

Each run produces its own post-mortem report, but there is no mechanism to aggregate metrics across runs to detect trends (improving/degrading success rates, cost trajectories, recurring failure patterns).

**Impact:** Improvement is invisible. Cannot answer "is the pipeline getting better?" without manual spreadsheet work.

### Gap K-3: No Feedback Loop from Analysis to Configuration

Post-mortem insights remain in report files. There is no mechanism to translate a post-mortem finding into a configuration adjustment for the next run.

**Impact:** Every run starts from the same baseline regardless of what was learned from prior runs.

### Gap K-4: No Prompt-Response Quality Correlation

Even where prompts and responses are separately available, there is no analysis that correlates prompt characteristics (length, constraint density, context completeness) with output quality (success rate, repair frequency, review scores).

**Impact:** Prompt improvements are based on intuition rather than data.

### Gap K-5: Run Archive Organization — PARTIALLY CLOSED

`run-atomic.sh` already creates timestamped run directories under `pipeline-output/{project}/run-NNN-YYYYMMDDTHHMM/` with `latest` symlink, and archives contractor state into the run directory. However, the archive does not yet include:
- Post-mortem reports for prime route (artisan has parity via `run-artisan.sh`)
- Prompt-response pairs from real runs
- Standardized metrics extraction for cross-run comparison
- An index file for efficient archive querying

**Impact:** Run data is preserved but not yet fully analyzable without manual inspection.

---

## Design Interactions

### With Mottainai
Kaizen extends Mottainai from "don't waste within a run" to "don't waste across runs." A Kaizen insight that a particular artifact is consistently regenerated unnecessarily becomes a Mottainai violation to fix.

### With Context Correctness by Construction
Kaizen analysis may reveal that context propagation failures (gaps in the contract chain) cause systematic quality issues. These findings feed back into Context Correctness by Construction requirements.

### With Context Correctness by Design
Kaizen cross-run analysis of shared-file conflicts feeds into design-time compatibility requirements.

---

## Success Criteria

1. Every Prime Contractor run produces a complete, self-contained diagnostic archive that can be analyzed independently
2. Cross-run trend analysis is possible via scripting against the archive
3. At least one feedback loop exists: analysis output from run N influences configuration of run N+1
4. Prompt-response pairing enables data-driven prompt quality improvement
5. The pipeline's success rate, cost efficiency, and escalation rate are measurably tracked over time
