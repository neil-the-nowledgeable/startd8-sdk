# Kaizen Convergent Review Protocol — Agent Execution Guide

**Purpose:** Step-by-step instructions for any AI agent to run the Convergent Review Protocol (CRP) on the Kaizen for Prime Contractor design documents. This is a domain-customized version of the [generic CRP Agent Guide](../arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md), tailored to the Kaizen requirements and implementation plan.

**Target documents:**
- **Requirements:** `KAIZEN_PRIME_REQUIREMENTS.md` (22 requirements across 6 layers)
- **Plan:** `KAIZEN_IMPLEMENTATION_PLAN.md` (6 layers, ~18 implementation steps)

**Protocol source:** [CONVERGENT_REVIEW_AGENT_GUIDE.md](../arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md) — the generic CRP protocol. This document specializes it for the Kaizen domain.

---

## How This Process Works

This review operates in **dual-document mode**: the implementation plan is the primary review target, and the requirements document is the secondary target. Both documents already have the CRP appendix structure initialized.

You are not the only reviewer. Prior rounds exist. Read the appendix state in both documents before generating suggestions. See the generic guide's "Multi-Agent Iterative Review" section for full orientation.

---

## Quick Reference

| Concept | Value |
|---------|-------|
| Review areas | Architecture, Interfaces, Data, Risks, Validation, Ops, Security |
| Severities | critical, high, medium, low |
| Plan suggestion IDs | `R{round}-S{n}` |
| Requirements suggestion IDs | `R{round}-F{n}` |
| Table columns (7) | ID, Area, Severity, Suggestion, Rationale, Proposed Placement, Validation Approach |
| Substantially addressed threshold | 3 accepted suggestions per area |
| Documents | Plan (S-prefix) + Requirements (F-prefix) |

---

## Domain Context: What You Are Reviewing

### The Kaizen System

Kaizen ("change for the better") is a continuous improvement system for the PrimeContractorWorkflow. It closes 5 gaps (K-1 through K-5) identified in the prompt audit:

| Gap | Description | Closed By |
|-----|-------------|-----------|
| K-1 | No prompt capture during real runs | Layer 2 (REQ-KZ-200–204) |
| K-2 | No cross-run metric aggregation | Layer 4 (REQ-KZ-400–402) |
| K-3 | No feedback loop from analysis to configuration | Layer 5 (REQ-KZ-500–504) |
| K-4 | No prompt-quality correlation | Layer 6 (REQ-KZ-600–601) |
| K-5a | No prime post-mortem (artisan has parity) | Layer 1 (REQ-KZ-100–102) |
| K-5b | No archive index for efficient querying | Layer 3 (REQ-KZ-300–302) |

### The 6 Requirement Layers

| Layer | Requirements | Scope |
|-------|-------------|-------|
| 1: Prime Post-Mortem Parity | KZ-100–102 | Wire existing `run_prime_postmortem.py` into `run-prime-contractor.sh` |
| 2: Prompt-Response Pairing | KZ-200–204 | Capture prompts + responses during real runs, with redaction |
| 3: Run Metrics & Archive Index | KZ-300–302 | Standardized metrics JSON, project-level index, retention policy |
| 4: Cross-Run Aggregation | KZ-400–402 | Trend analysis across runs, failure pattern persistence, cost outliers |
| 5: Feedback Loop | KZ-500–504 | Suggestion generation, manual config curation, config injection, improvement verification |
| 6: Prompt Quality Correlation | KZ-600–601 | Correlate prompt characteristics with output quality |

### Two Implementation Homes

Changes span **two repositories**:
- **cap-dev-pipe** — Shell scripts (`run-prime-contractor.sh`, `run-atomic.sh`, new trend/correlation scripts)
- **startd8-sdk** — Python modules (`prime_contractor.py`, `run_prime_postmortem.py`, `protocols.py`, `postmortem.py`)

This dual-repo boundary is a key review concern: changes must be coordinated across repos, and interface contracts between shell scripts and Python code are particularly fragile.

### Key Source Artifacts

When verifying claims in the plan, these are the ground-truth sources:

| Artifact | Location | Key Fields/Lines |
|----------|----------|-----------------|
| `PrimePostMortemReport` | `prime_postmortem.py:300-319` | `report_id`, `total_features`, `successful_features`, `failed_features`, `aggregate_score`, `aggregate_verdict`, `features`, `pipeline_attribution`, `micro_prime_analysis`, `cross_feature_patterns`, `lessons`, `cost_summary` |
| `CrossFeaturePattern` | `prime_postmortem.py:255-262` | `.pattern_type`, `.description`, `.frequency`, `.affected_features`, `.severity` |
| `PipelineStageAttribution` | `prime_postmortem.py:266-272` | `.stage`, `.failure_count`, `.root_causes` (Dict[str, int]) |
| `GenerationResult` | `protocols.py:20-30` | NamedTuple: `success`, `generated_files`, `error`, `input_tokens`, `output_tokens`, `cost_usd`, `iterations`, `model`, `metadata` — NO `text` or `raw_response` field |
| `_persist_walkthrough_prompts` | `prime_contractor.py:1779-1823` | Prompt persistence logic (45 lines, not 140) |
| `develop_feature` | `prime_contractor.py:~1920` | The walkthrough/real-run branch |
| `run-prime-contractor.sh` | cap-dev-pipe | `$SDK_ROOT` (line 31), `$OUTPUT_DIR` (line 130), venv (152-155), exit (line 340) |
| `run-atomic.sh` | cap-dev-pipe | Phase 5 (510-517), `$ROUTE` (50/70), `$RUN_ID` (49/128), `$NAME` (54/74/97), `$PROCESS_HOME` (42) |

**Warning:** Prior review rounds discovered multiple field name and line number inaccuracies in the plan. Verify any specific field name, line number, or variable reference against the source before accepting a plan claim at face value.

---

## Phase 0: Initialization

Both documents already have the CRP appendix structure. Skip to Phase 1.

If either document is missing the appendix, follow Phase 0 from the [generic guide](../arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md).

---

## Phase 1: Pre-Review Analysis

### Step 1a: Parse Existing State

**Plan document (`KAIZEN_IMPLEMENTATION_PLAN.md`):**
1. Scan Appendix A for applied suggestion IDs and areas
2. Scan Appendix B for rejected suggestion IDs and rationale
3. Scan Appendix C for the highest round number — your round is `max + 1`
4. Collect untriaged suggestions (in C but not in A or B)
5. Also scan the "Convergent Review — Round R1 (Triaged)" section above the appendix — this pre-appendix section contains R1 findings that were triaged inline before the CRP structure was added

**Requirements document (`KAIZEN_PRIME_REQUIREMENTS.md`):**
1. Same scan of Appendix A/B/C
2. Note that F-prefix suggestions target requirements, S-prefix target the plan
3. Read the requirements body to identify each REQ-KZ-NNN section

### Step 1b: Compute Area Coverage

Count accepted suggestions in each document's Appendix A:

**Plan coverage:**

| Area | Threshold | Notes |
|------|-----------|-------|
| Architecture | 3 | |
| Interfaces | 3 | |
| Data | 3 | |
| Risks | 3 | |
| Validation | 3 | |
| Ops | 3 | |
| Security | 3 | |

**Requirements coverage:** Same table, tracked independently.

### Step 1c: Determine Review Mode

Use the coverage tables to determine which mode applies:
- **Some areas below threshold** — Two-tier priority mode (Phase 2a)
- **All areas at or above threshold** — Gap-hunting and opportunity mode (Phase 2b)
- **5-6 of 7 addressed** — Transitional mode

---

## Phase 2: Review Focus Areas (Kaizen-Specific)

The standard 7 CRP review areas apply, but each has Kaizen-specific concerns. Use these domain lenses when evaluating.

### Architecture

- **Layer dependency ordering** — Layers must ship in dependency order (1→3→4, 2→6, 5 depends on 1+3). Are these dependencies correctly documented and enforced?
- **Dual-repo coordination** — Shell scripts in cap-dev-pipe call Python scripts in startd8-sdk. Are the interface contracts (CLI flags, file paths, env vars) explicit enough for independent implementation?
- **Inline Python in shell scripts** — Steps 3.3, 3.4, 5.3 embed Python in bash heredocs. Are shell variables safely passed (env vars, not f-string interpolation)?
- **`_CAUSE_TO_SUGGESTION` completeness** — The mapping covers 3 of 16 `RootCause` enum values. Is the gap documented, handled, or ignored?
- **Kaizen code locality in `prime_contractor.py`** — Is kaizen logic (capture, redaction, config injection) structurally isolated or scattered across the 2000+ line file?

### Interfaces

- **CLI flag contracts** — New flags (`--kaizen`, `--kaizen-config`, `--emit-metrics`, `--emit-suggestions`, `--run-metadata`, `--kaizen-enabled`, `--kaizen-source-run`, `--no-kaizen`, `--kaizen-keep`). Are these stable? What happens with version mismatch between cap-dev-pipe and SDK?
- **File format schemas** — `kaizen-metrics.json`, `kaizen-index.json`, `kaizen-suggestions.json`, `kaizen-config.json`, `kaizen-patterns.json`, `kaizen-trends.json`. Are schemas explicitly versioned? What happens on schema evolution?
- **Prompt directory layout** — The layout shared between `_write_prompt_files()`, `_persist_walkthrough_prompts()`, and `extract_prompt_characteristics()` is an implicit contract. Is it formalized?
- **`_build_phase_prompts` return type** — Is the return type documented?
- **`metadata.json` schema** — Is the content defined, or inferred from existing code?

### Data

- **Metrics JSON completeness** — Does `kaizen-metrics.json` capture all fields needed for Layer 4 trend analysis and Layer 6 correlation?
- **Partial report handling** — What happens when `pipeline_attribution` is `None` or `micro_prime_analysis` is missing?
- **Pattern accumulation** — Cross-run pattern tracking uses `cross_feature_patterns` from postmortem reports. Is the accumulation logic correct for patterns that appear in some runs but not others?
- **Index idempotency** — The dedup filter prevents duplicate entries. Is it correct? What about entries with the same `run_id` but different metrics (re-run scenario)?

### Risks

- **Secret leakage** — Prompt/response files may contain API keys, tokens, or sensitive data. Is the redaction system (REQ-KZ-204) fully implemented in the plan?
- **Fail-closed vs fail-open** — Redaction is fail-closed (invalid config disables persistence). Config injection is fail-open (invalid config proceeds without kaizen). Is this asymmetry intentional and correct?
- **Retention and protected runs** — Can pruning delete a run that `kaizen-config.json` references as `source_run`?
- **Exit code preservation** — Post-mortem and kaizen steps must not alter the contractor's exit code. Is this guaranteed?
- **Response size** — 2 MB guard exists. What about binary or non-UTF-8 responses?

### Validation

- **Verification steps** — Each layer has a verify section. Do they cover failure cases (negative tests), not just happy paths?
- **E2E loop test** — Is there a single test that exercises the full Kaizen cycle (run → post-mortem → suggestions → config → improved run → trend)?
- **Acceptance criteria** — Are REQ-KZ-504 thresholds (±0.05, min 2 runs) implemented correctly?
- **Structural verification** — REQ-KZ-203's "no duplication of prompt serialization logic" — is this testable as stated?
- **Line count estimates** — Are scope guards defined for implementation growth beyond estimates?

### Ops

- **Retention policy** — Default 20, configurable via `--kaizen-keep`. Bounds? What about `KAIZEN_KEEP=0`?
- **Index growth** — Is there a maximum size bound for `kaizen-index.json`?
- **`latest` symlink handling** — Pruning must update the symlink if its target is pruned. Is this implemented?
- **Script naming and discoverability** — New scripts (`run-kaizen-trends.sh`, `run-kaizen-correlation.sh`). Do they follow cap-dev-pipe conventions?
- **Insertion order in `run-atomic.sh`** — Multiple Phase 5 blocks are added. Is the execution order specified?
- **Variable naming consistency** — `$NAME` vs `{project}` — are these the same?

### Security

- **Redaction semantics** — Single-line vs multi-line regex. `re.MULTILINE` vs `re.DOTALL`. Applied before or after JSON serialization?
- **Shell variable injection** — Inline Python receiving shell variables via f-string interpolation into source code. Is this safe against special characters in project names?
- **Config validation** — `kaizen-config.json` is loaded and injected into prompt context. Is it validated beyond schema version check?
- **Feature ID sanitization** — Path traversal via malicious `feature_id` values. Is `_sanitize_feature_id()` sufficient?
- **File permissions** — Are kaizen artifact files written with restricted permissions (like the generation manifest's `0o600`)?

---

## Phase 2b: Kaizen-Specific Gap-Hunting Lenses

When all or most areas are substantially addressed, apply these domain-specific lenses in addition to the generic CRP lenses.

### Lens K1: Feedback Loop Completeness

The central claim of Kaizen is that "run N's analysis improves run N+1." Trace this loop end-to-end:

1. Run N produces `prime-postmortem-report.json` (Layer 1)
2. Postmortem produces `kaizen-metrics.json` (Layer 3) and `kaizen-suggestions.json` (Layer 5)
3. Operator reviews suggestions, edits `kaizen-config.json` (Layer 5, manual)
4. Run N+1 reads `kaizen-config.json`, injects hints into prompts (Layer 5)
5. Run N+1's post-mortem produces new metrics (Layer 3)
6. Trend script compares before/after (Layer 4/5)

**Look for:** Broken links in this chain. Silent failures that prevent hints from reaching the LLM. Metrics that don't capture enough signal to detect improvement. Manual steps that aren't documented clearly enough for an operator to follow.

### Lens K2: Mottainai Alignment

Kaizen extends Mottainai ("don't waste across runs"). Check:

- Are any artifacts computed but not consumed? (Wasted computation)
- Are any artifacts consumed but not archived? (Lost data)
- Is any data being re-derived by LLM that could be deterministically extracted?
- Does the plan inventory existing capabilities before building new ones?

### Lens K3: Cross-Layer Contract Consistency

Each layer produces outputs consumed by later layers. Verify that:

- Layer 1 outputs (`prime-postmortem-report.json`) are consumed correctly by Layer 3 (`_emit_kaizen_metrics`) and Layer 4 (trend analysis)
- Layer 2 outputs (prompt/response files) are consumed correctly by Layer 6 (`extract_prompt_characteristics`)
- Layer 3 outputs (`kaizen-index.json`, `kaizen-metrics.json`) are consumed correctly by Layer 4 (trend script)
- Layer 5 outputs (`kaizen-suggestions.json`) are consumed correctly by the manual config workflow and Layer 5's config injection

**Look for:** Schema mismatches, field name inconsistencies, assumptions about file existence that aren't validated.

### Lens K4: Operational Ergonomics

The Kaizen system adds new operational touchpoints. Check:

- Is the operator's manual workflow clear? (Review suggestions → edit config → run pipeline → check trends)
- Are error messages actionable? (Not just "failed" but "missing X, expected at Y")
- Can the operator disable kaizen cleanly? (`--no-kaizen` flag coverage)
- Is the system observable from outside? (Can an operator tell at a glance whether kaizen is active, what config is being used, and whether it's helping?)

---

## Phase 3: Generate the Review Round

### Output Format (strict)

Your output must contain up to **three sections** in this order:

#### Section 1: Plan Suggestions (S-prefix)

```markdown
#### Review Round R{n}

- **Reviewer**: {your name or model identifier}
- **Date**: {YYYY-MM-DD HH:MM:SS UTC}
- **Scope**: {brief description of review focus}

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R{n}-S1 | {area} | {severity} | {suggestion} | {rationale} | {where in plan} | {how to verify} |
```

#### Section 2: Feature Requirements Suggestions (F-prefix)

```markdown
#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R{n}-F1 | {area} | {severity} | {requirements issue} | {rationale} | {where in reqs doc} | {how to verify} |
```

Only include Section 2 if you find genuine issues in the requirements document. Do not invent problems.

#### Section 3: Requirements Coverage Mapping

```markdown
#### Requirements Coverage

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| REQ-KZ-100 | Step 1.1 | Full | -- |
| REQ-KZ-200 | Step 2.2 | Partial | {what's missing} |
```

Coverage values: `Full`, `Partial`, `Missing`. Every REQ-KZ-NNN must appear. When coverage is `Partial` or `Missing`, generate a corresponding S-prefix suggestion in Section 1.

### Output Rules

1. Round heading: `#### Review Round R{n}` with correct round number
2. Metadata: Reviewer, Date (UTC), Scope
3. Table columns: exactly 7 headers (ID, Area, Severity, Suggestion, Rationale, Proposed Placement, Validation Approach)
4. Plan IDs: `R{n}-S{n}`, Requirements IDs: `R{n}-F{n}`
5. Area values: `Architecture`, `Interfaces`, `Data`, `Risks`, `Validation`, `Ops`, `Security`
6. Severity values: `critical`, `high`, `medium`, `low`
7. Max 10 S-prefix suggestions, max 5 F-prefix suggestions per round
8. Pipe escaping: `|` in text becomes `\|`
9. Do not modify Appendix A or Appendix B
10. Output the snippet only, not the entire document

### Endorsements (optional)

If you agree with untriaged suggestions from prior rounds:

```markdown
**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R{prior}-S{n}: {one-sentence reason}
```

---

## Phase 4: Append and Route

1. **Plan suggestions (S-prefix + Requirements Coverage)** — Append to `KAIZEN_IMPLEMENTATION_PLAN.md` Appendix C
2. **Requirements suggestions (F-prefix)** — If non-empty, wrap in round heading and append to `KAIZEN_PRIME_REQUIREMENTS.md` Appendix C

Do not mix S-prefix and F-prefix in the same document's appendix.

---

## Phase 5: Triage

### Step 5a: Collect Untriaged Suggestions

Parse both documents' Appendix C for suggestion IDs not in Appendix A or B.

### Step 5b: Classify Each Suggestion

For each untriaged suggestion: **ACCEPT** or **REJECT**.

**Kaizen-specific triage guidance:**

- Suggestions that improve the feedback loop completeness (Lens K1) should be weighted heavily — the loop is the system's reason for existing
- Suggestions about field name accuracy or line number correctness should be verified against source code before accepting
- Suggestions that add complexity without closing a documented gap (K-1 through K-5) should be scrutinized — Kaizen is already a large design
- "Nice to have" suggestions for later maturity levels should be deferred, not rejected — document as DEFERRED in the notes column

### Step 5c: Route by Prefix

- S-prefix ACCEPT → plan Appendix A
- S-prefix REJECT → plan Appendix B (with rationale)
- F-prefix ACCEPT → requirements Appendix A
- F-prefix REJECT → requirements Appendix B (with rationale)

---

## Phase 6: Update Coverage Sections

After triage, update both documents' "Areas Substantially Addressed" and "Areas Needing Further Review" sections based on each document's own Appendix A counts.

---

## Phase 7: Verify Invariants

1. **Append-only** — Prior Appendix C content unchanged
2. **Monotonic rounds** — Your round number > all existing rounds
3. **No body modification** — Document body unchanged by review process
4. **Domain exhaustiveness** — All 7 areas considered
5. **ID uniqueness** — No collisions with existing IDs
6. **Prefix routing** — No S-prefix IDs in requirements appendix; no F-prefix IDs in plan appendix

---

## Area Aliases

Normalize synonyms to canonical area names:

| Synonym | Canonical Area |
|---------|---------------|
| design, structure, modularity, layers, pipeline, decomposition | Architecture |
| api, cli, flags, contracts, integration, schema, format | Interfaces |
| data model, metrics, json, storage, persistence, index | Data |
| risk, reliability, fault tolerance, error handling, failure modes | Risks |
| testing, testability, test, verification, acceptance criteria | Validation |
| operations, deployment, retention, pruning, scripts, symlinks | Ops |
| auth, redaction, secrets, sanitization, injection, permissions | Security |

---

## Requirements Coverage Reference

Use this complete list when building the Requirements Coverage table in Section 3:

| Requirement | Layer | Brief Description |
|-------------|-------|-------------------|
| REQ-KZ-100 | 1 | Post-mortem invocation in run-prime-contractor.sh |
| REQ-KZ-101 | 1 | Post-mortem report in run directory |
| REQ-KZ-102 | 1 | Console display of post-mortem summary |
| REQ-KZ-200 | 2 | Prompt persistence during real runs |
| REQ-KZ-201 | 2 | Response capture (with size guard) |
| REQ-KZ-202 | 2 | Archive prompt directory per run |
| REQ-KZ-203 | 2 | No duplication of serialization logic |
| REQ-KZ-204 | 2 | Redaction and opt-out |
| REQ-KZ-300 | 3 | Standardized kaizen-metrics.json |
| REQ-KZ-301 | 3 | Project-level kaizen-index.json |
| REQ-KZ-302 | 3 | Retention policy with pruning |
| REQ-KZ-400 | 4 | Cross-run trend report |
| REQ-KZ-401 | 4 | Failure pattern persistence |
| REQ-KZ-402 | 4 | Cost outlier detection |
| REQ-KZ-500 | 5 | Kaizen config schema |
| REQ-KZ-501 | 5 | Suggestion generation from post-mortem |
| REQ-KZ-502 | 5 | Config injection into workflow |
| REQ-KZ-503 | 5 | Opt-out flag (--no-kaizen) |
| REQ-KZ-504 | 5 | Improvement verification |
| REQ-KZ-600 | 6 | Prompt characteristic extraction |
| REQ-KZ-601 | 6 | Prompt-quality correlation analysis |

---

## Convergence Criteria

### Phase Progression (Kaizen-specific)

| Phase | Coverage State | Focus |
|-------|---------------|-------|
| **Early** (R1-R2) | 0-2 areas addressed | Broad: field accuracy, missing implementation details, cross-layer contract gaps |
| **Middle** (R2-R3) | 3-5 areas addressed | Targeted: filling coverage gaps, failure case verification, interface formalization |
| **Late** (R3-R5) | 6-7 areas addressed | Refined: feedback loop completeness (K1), operational ergonomics (K4), cross-layer contract consistency (K3) |
| **Converged** (R5+) | All areas addressed | If fewer than 2-3 novel suggestions emerge, the documents have likely converged |

### When to Stop

The review is likely converged when:

1. All 7 areas are substantially addressed in both documents
2. Gap-hunting rounds produce fewer than 2-3 novel suggestions
3. The Requirements Coverage table shows Full coverage for all 22 requirements
4. The feedback loop (Lens K1) has been traced end-to-end without gaps
5. Cross-layer contract consistency (Lens K3) has been verified for all layer boundaries

### When Not to Stop

Continue if:

- Accepted suggestions from different rounds create **interactions** not yet examined (e.g., redaction interacting with prompt characteristic extraction)
- The **manual workflow** (operator reviews suggestions, edits config) has not been examined for usability
- **Negative test cases** are absent from verification steps
- Any requirement shows only **Partial** coverage in the traceability mapping
