# Implementation Plan Review Protocol — Agent Execution Guide

**Purpose:** Step-by-step instructions for any AI agent to run the Convergent Review Protocol (CRP) on the Simple → Trivial Decomposer Implementation Plan, evaluating it against the Feasibility Analysis for implementation readiness.

**Target documents:**
- **Plan:** `SIMPLE_TO_TRIVIAL_DECOMPOSER_IMPLEMENTATION_PLAN.md`
- **Feasibility:** `SIMPLE_TO_TRIVIAL_DECOMPOSER_FEASIBILITY.md`

**Protocol source:** Adapted from `CONVERGENT_REVIEW_AGENT_GUIDE.md` (arc-review CRP)

---

## How This Process Works: Multi-Agent Iterative Review

**You are not the only reviewer.** This plan undergoes multiple sequential review rounds, each performed by a different agent (or the same agent in a later pass). The CRP is designed so that each reviewer builds on the cumulative work of all prior reviewers — not by re-reading their raw suggestions, but by reading the **triaged outcomes** persisted in the plan document itself.

### What You Inherit From Prior Reviewers

When you receive a plan that has already been through CRP rounds, the appendix structure contains the full review history:

- **Appendix A (Applied)** — Suggestions that prior reviewers proposed and that were accepted during triage. These are the "settled" improvements. **Do not re-propose anything that already appears here.**
- **Appendix B (Rejected)** — Suggestions that were explicitly rejected with rationale. **Read the rejection rationale carefully.** If you believe a rejected idea should be reconsidered, you must explicitly reference its ID and argue why the original rationale no longer applies. Do not silently re-propose rejected ideas.
- **Appendix C (Incoming)** — Raw suggestion tables from each prior round, plus any endorsement blocks. Contains both triaged and untriaged suggestions. Your job is to add a new round here, not modify existing rounds.
- **Areas Substantially Addressed / Areas Needing Further Review** — Coverage tracking sections that tell you which areas have enough accepted suggestions and which still need attention.

### Your Role as Reviewer R{n}

Each review pass should be **sharper than the last**. You are not starting from scratch — you are working from the foundation laid by R1 through R{n-1}. Your job is to:

1. **Go deeper, not wider** — Prior reviewers handled the obvious issues. Look for what they missed: unstated prerequisites, ordering dependencies between phases, gaps between the feasibility analysis's accepted suggestions and the plan's coverage.
2. **Challenge, don't repeat** — If prior rounds covered an area well, do not generate more suggestions in that area unless you find a genuine gap. Redundant suggestions waste triage effort.
3. **Endorse good untriaged work** — If a prior reviewer proposed something valuable that hasn't been triaged yet, endorse it rather than proposing a duplicate. Endorsements build consensus signal.
4. **Respect rejections** — Rejected suggestions were dismissed for a reason. Read the rationale. Only revisit if circumstances have changed or the rationale was flawed.

### The Document Is the State

There is no external database or API tracking review state. The plan document's appendix structure **is** the persistent state. Round numbers, applied/rejected decisions, coverage counts, and endorsement signals are all derived by parsing the document. This means:

- If the document is passed to you with Appendices A/B/C populated, prior rounds happened.
- If Appendix A is empty and Appendix C has no rounds, you are the first reviewer.
- If coverage sections show 5 of 7 areas addressed, the review is in its middle-to-late phase.
- Your output is appended to the document and becomes part of the state for the next reviewer.

---

## Review Focus: Implementation Readiness

Unlike a general architectural review, this review evaluates whether the plan is **specific enough for a developer (human or agent) to implement** the feasibility document's accepted design. Every suggestion should make the plan more concrete, more correct, or more safely implementable.

### What Makes a Good Implementation Plan Suggestion

| Good Suggestion | Bad Suggestion |
|----------------|----------------|
| "Phase 0 Step 3 doesn't specify which `GenerationResult` fields to populate for file-copy tasks — add `files_generated`, `cost_usd=0.0`, `strategy='file_copy'`" | "Consider adding more detail to Phase 0" |
| "The `detect_copy_task` function needs to handle the case where `depends_on` contains multiple predecessors but only one is the copy source" | "Copy detection could have edge cases" |
| "Phase 1 says 'reuse `ClassDecomposeStrategy.assemble()`' but that method expects `SubElement.content` which won't be populated for template-rendered sub-elements — specify how template output maps to `SubElement.content`" | "Assembly might not work" |

**Principle:** Every suggestion should either (a) identify a specific gap that would block or confuse an implementer, or (b) add a specific detail that reduces implementation ambiguity.

---

## Quick Reference

| Concept | Value |
|---------|-------|
| Review areas | Specificity, Dependencies, Data Contracts, Risk Mitigation, Testability, Observability, Feasibility Traceability |
| Severities | critical, high, medium, low |
| Suggestion ID format | `R{round}-S{n}` (plan), `R{round}-F{n}` (feasibility gaps) |
| Table columns (7) | ID, Area, Severity, Suggestion, Rationale, Proposed Placement, Validation Approach |
| Substantially addressed threshold | 3 accepted suggestions per area (configurable) |
| Appendix A | Applied suggestions (accepted and integrated) |
| Appendix B | Rejected suggestions (with rationale) |
| Appendix C | Incoming suggestions (untriaged, append-only) |

### Review Area Definitions

| Area | What to Evaluate |
|------|-----------------|
| **Specificity** | Are implementation steps concrete enough to code from? Do they name exact classes, methods, fields, files, and parameters? Are return types, error conditions, and edge cases specified? |
| **Dependencies** | Are phase/step ordering constraints explicit? Are cross-phase data dependencies identified? Would a developer know what must exist before starting each step? |
| **Data Contracts** | Are data structures (new fields, enums, dataclasses) fully specified with types, defaults, and validation rules? Are schema changes backward-compatible? |
| **Risk Mitigation** | Are failure modes identified with specific fallback behavior? Are safety gates (signature mismatch, decorator guard, path traversal) concrete enough to implement? |
| **Testability** | Are test cases specified with inputs, expected outputs, and assertions? Are negative tests (rejection paths, edge cases) defined? Can each phase be tested in isolation? |
| **Observability** | Are metrics, counters, and span attributes named with exact string values? Are log messages specified? Is the reporting format (JSON schema) defined? |
| **Feasibility Traceability** | Does every accepted suggestion from the feasibility doc (Appendix A, R1–R6) have a clear, specific implementation step in the plan? Are any accepted feasibility suggestions missing or underspecified? |

---

## Phase 0: First-Encounter Initialization

When you receive the plan for review **for the first time** (no appendix structure exists), you must prepare it before generating any review suggestions.

### Step 0a: Detect Whether Initialization Is Needed

Search the plan document for this heading:

```
## Appendix: Iterative Review Log (Applied / Rejected Suggestions)
```

- **If found:** The plan has been through CRP before. Skip to Phase 1.
- **If not found:** This is a first encounter. Continue with Step 0b.

### Step 0b: Append the Appendix Structure

Append the following template **verbatim** to the end of the plan document, separated from the body by a horizontal rule (`---`):

```markdown
---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Areas Substantially Addressed

(No areas have reached the threshold of 3 accepted suggestions yet.)

### Areas Needing Further Review

- **Specificity**: 0/3 suggestions accepted (need 3 more)
- **Dependencies**: 0/3 suggestions accepted (need 3 more)
- **Data Contracts**: 0/3 suggestions accepted (need 3 more)
- **Risk Mitigation**: 0/3 suggestions accepted (need 3 more)
- **Testability**: 0/3 suggestions accepted (need 3 more)
- **Observability**: 0/3 suggestions accepted (need 3 more)
- **Feasibility Traceability**: 0/3 suggestions accepted (need 3 more)

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)
```

### Step 0c: Save the Initialized Document

Write the plan document back with the appendix appended. **Do not modify the document body.** The initialization is purely additive.

---

## Phase 1: Pre-Review Analysis

Before generating suggestions, analyze the current state of both documents.

### Step 1a: Parse Existing State

1. **Scan plan Appendix A** — collect all applied suggestion IDs and their areas.
2. **Scan plan Appendix B** — collect all rejected suggestion IDs. Read rejection rationale to understand what has already been considered and dismissed.
3. **Scan plan Appendix C** — find the highest existing round number by searching for `#### Review Round R{n}` headings. Your round number is `max(existing) + 1`, or `1` if no rounds exist.
4. **Collect untriaged suggestions** — any suggestions in Appendix C whose IDs do not appear in Appendix A or B.

### Step 1b: Read the Feasibility Document

Read `SIMPLE_TO_TRIVIAL_DECOMPOSER_FEASIBILITY.md` thoroughly. Pay special attention to:

1. **Appendix A (Applied suggestions)** — These are the accepted design decisions (R1–R6). Every one of these must map to a specific, implementable step in the plan.
2. **Appendix B (Rejected suggestions)** — These were explicitly excluded. The plan should NOT contain steps that implement rejected feasibility suggestions.
3. **Section 6 (Recommended Implementation Path)** — The phasing the plan should follow.
4. **Section 4 (Feasibility Assessment)** — Challenges and mitigations the plan must address.
5. **Section 5 (Integration with DFA)** — Data flow requirements the plan must specify.

### Step 1c: Compute Area Coverage

For each of the 7 review areas, count how many suggestions have been **accepted** (appear in plan Appendix A):

| Area | Accepted Count | Addressed? (>= 3) | Gap |
|------|---------------|-------------------|-----|
| Specificity | ? | ? | ? |
| Dependencies | ? | ? | ? |
| Data Contracts | ? | ? | ? |
| Risk Mitigation | ? | ? | ? |
| Testability | ? | ? | ? |
| Observability | ? | ? | ? |
| Feasibility Traceability | ? | ? | ? |

### Step 1d: Determine Review Mode

Based on coverage analysis:

- **Some areas below threshold** — Enter **two-tier priority mode** (Phase 2a). Focus your suggestion slots on uncovered areas.
- **All areas at or above threshold** — Enter **gap-hunting and implementation depth mode** (Phase 2b).
- **Most areas addressed (5–6 of 7)** — Use two-tier mode but recognize you are in a late-phase review.

---

## Phase 2a: Two-Tier Priority Review

When uncovered areas exist, structure your review to prioritize them.

### Tier 1: Priority Areas (uncovered)

List each area below the substantially addressed threshold. For each:
- Note how many accepted suggestions it has
- Note the gap (threshold minus count)
- Allocate **at least `max_suggestions - 1`** of your suggestion slots to these areas

### Tier 2: Addressed Areas (secondary)

For areas already substantially addressed:
- Only propose suggestions if you find a **genuine gap** that the existing accepted suggestions missed
- Do not rehash topics already well-covered

### Generate Your Suggestions

Produce a review round following the output format in Phase 3.

---

## Phase 2b: Gap-Hunting and Implementation Depth Mode

When all 7 areas are substantially addressed (or nearly so), shift from area coverage to deeper analysis.

### Implementation Readiness Lenses

Evaluate the plan through these lenses, in order of priority:

**1. Code-level specificity audit**

For each plan step, ask: "Could I write a PR from this description alone, without reading any other document?"

- **Method signatures** — Are parameters, return types, and exceptions specified? Does the plan say `detect_copy_task(feature) -> Optional[CopySource]` or just "add a detection function"?
- **Field definitions** — Are new dataclass/model fields specified with exact names, types, defaults, and validators?
- **Integration points** — Does the plan specify *where* in existing code each change goes (file, class, method, line-range)?
- **Error paths** — For each operation that can fail, is the failure behavior specified (raise, log+continue, fallback)?

**2. Feasibility suggestion coverage audit**

Cross-reference the plan's traceability table against the feasibility document's Appendix A. For each accepted feasibility suggestion:

- Is there a concrete plan step that implements it?
- Is the plan step specific enough, or does it just restate the suggestion without adding implementation detail?
- Are there accepted feasibility suggestions whose implementation interacts with other suggestions in ways the plan doesn't address?

**3. Phase boundary contracts**

For each phase transition (0→1, 1→2, 2→3):

- What artifacts does the preceding phase produce?
- What artifacts does the next phase consume?
- Are the schemas of these artifacts specified?
- Could a developer implement Phase N without knowledge of Phase N+1's internals?

**4. Existing code compatibility**

Does the plan account for the actual current state of the codebase?

- Are the classes, methods, and modules referenced in the plan real and current? (Check against the codebase.)
- Do proposed changes to existing classes (e.g., adding fields to `ForwardElementSpec`) account for existing callers?
- Are import paths and module locations correct?

**5. Design principle alignment**

Evaluate against these principles from the Micro Prime requirements:

- **Deterministic before probabilistic** — Does the plan try templates/copy before LLM at every decision point?
- **Manifest as specification** — Does the plan use the Forward Manifest as structural ground truth for validation?
- **Escalate, don't retry blindly** — Do fallback paths escalate to the next tier rather than retrying the same approach?
- **Mottainai** — Does the plan preserve and reuse work from earlier phases rather than discarding it?

### Prioritizing Late-Round Suggestions

1. **Code-level specificity gaps** (Lens 1) — Most actionable; directly unblocks implementation.
2. **Feasibility coverage gaps** (Lens 2) — Prevents accepted design decisions from being silently dropped.
3. **Phase boundary contracts** (Lens 3) — Prevents integration failures between independently-developed phases.
4. **Codebase compatibility** (Lens 4) — Prevents plan steps that reference nonexistent code.
5. **Principle alignment** (Lens 5) — Important but more abstract.

---

## Phase 3: Generate the Review Round

### Output Format (strict)

Your output must be **only** an appendable markdown snippet. Do not rewrite the document. Do not modify Appendix A or Appendix B.

```markdown
#### Review Round R{n}

- **Reviewer**: {your name or model identifier}
- **Date**: {YYYY-MM-DD HH:MM:SS UTC}
- **Scope**: {brief description of review focus}

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R{n}-S1 | {area} | {severity} | {suggestion text} | {why this matters} | {where in the plan} | {how to verify} |
| R{n}-S2 | ... | ... | ... | ... | ... | ... |
```

### Output Rules

1. **Round heading** — Must be `#### Review Round R{n}` with the correct round number.
2. **Metadata block** — Must include Reviewer, Date (UTC), and Scope.
3. **Table columns** — Must use exactly these 7 headers: `ID`, `Area`, `Severity`, `Suggestion`, `Rationale`, `Proposed Placement`, `Validation Approach`. Plain text headers only (no bold, no italic).
4. **Suggestion IDs** — Must follow `R{round}-S{n}` format, numbered sequentially starting at 1.
5. **Area values** — Must be one of: `Specificity`, `Dependencies`, `Data Contracts`, `Risk Mitigation`, `Testability`, `Observability`, `Feasibility Traceability`. Use title case.
6. **Severity values** — Must be one of: `critical`, `high`, `medium`, `low`. Use lowercase.
7. **Suggestion count** — At least 1, at most 10 (configurable; default 10).
8. **Pipe escaping** — If suggestion text contains `|`, escape it as `\|` to preserve table structure.
9. **No appendix modification** — Output must NOT contain `### Appendix A` or `### Appendix B` headings.
10. **No document rewriting** — Output the snippet only, not the entire document.
11. **Specificity requirement** — Every suggestion must name the exact plan section, phase, and step it targets. "Phase 0 Step 3" not "the copy detection section."

### Feasibility Gap Suggestions (F-prefix, optional)

If you find gaps in the feasibility document itself (ambiguous accepted suggestions, missing edge cases that affect implementation), add a separate table:

```markdown
#### Feasibility Document Gaps

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R{n}-F1 | {area} | {severity} | {feasibility issue} | {why} | {where in feasibility doc} | {how to verify} |
```

**When to generate F-prefix suggestions:**

- An accepted feasibility suggestion (Appendix A) is **ambiguous** enough that the plan can't implement it without interpretation
- A feasibility decision **conflicts** with another accepted suggestion when both are implemented
- A feasibility decision's **edge case** (from Section 4.3) would block implementation but isn't addressed
- The feasibility document **assumes** codebase state that has changed since it was written

### Feasibility Coverage Mapping

On your **first round only** (R1), include a traceability table:

```markdown
#### Feasibility Suggestion Coverage

| Feasibility ID | Suggestion Summary | Plan Phase/Step | Coverage | Gaps |
| ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Decision order/exclusivity | Phase 1, Step 2 (strategy enum) | Full | -- |
| R3-S1 | Identical-copy file duplication | Phase 0, Steps 1-6 | Full | -- |
| R6-S7 | Path traversal guard | Phase 0, Step 2 | Partial | Guard specified but no test defined |
```

**Coverage values:** `Full` (plan has concrete implementation steps), `Partial` (mentioned but underspecified), `Missing` (not addressed in plan).

On subsequent rounds, only include this table if you find new coverage gaps.

### Endorsements (optional)

If you agree with untriaged suggestions from prior rounds (in Appendix C but NOT in Appendix A or B), append an endorsement block after your table:

```markdown
**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R{prior_round}-S{n}: {one-sentence reason you agree}
```

---

## Phase 4: Append the Review Round

Append your generated snippet to the end of the plan document, after all existing content in Appendix C. Do not insert it anywhere else.

If you generated F-prefix suggestions, wrap them in a round heading and append to the **feasibility document's** Appendix C (it already has the appendix structure).

---

## Phase 5: Triage

After all review rounds for this session are complete, triage all untriaged suggestions.

### Step 5a: Collect Untriaged Suggestions

Parse Appendix C for all suggestion rows whose IDs do **not** appear in Appendix A or Appendix B.

### Step 5b: Classify Each Suggestion

For each untriaged suggestion, decide:

- **ACCEPT** — The suggestion adds specific, actionable detail that would improve implementation readiness. Move a row into Appendix A.
- **REJECT** — The suggestion is too vague, duplicates existing content, or is out of scope. Move a row into Appendix B **with a specific rationale**.

**Triage criteria specific to implementation plans:**

| Accept When | Reject When |
|------------|-------------|
| Suggestion names exact classes, methods, fields, or parameters | Suggestion says "add more detail" without specifying what |
| Suggestion identifies a concrete failure mode with specific fallback | Suggestion raises a theoretical concern without a specific scenario |
| Suggestion identifies a missing test case with inputs and expected outputs | Suggestion says "add tests" without specifying what to test |
| Suggestion identifies a real dependency between plan steps | Suggestion reorganizes steps without functional difference |
| Suggestion traces a specific feasibility suggestion to a missing plan step | Suggestion restates a feasibility suggestion without adding implementation detail |

### Step 5c: Route Decisions to Appendices

**For ACCEPT decisions**, insert a row into Appendix A:

```markdown
| R{n}-S{m} | {suggestion summary} | {source reviewer} | {implementation/validation notes} | {YYYY-MM-DD} |
```

**For REJECT decisions**, insert a row into Appendix B:

```markdown
| R{n}-S{m} | {suggestion summary} | {source reviewer} | {specific rejection rationale} | {YYYY-MM-DD} |
```

Replace the `(none yet)` placeholder rows when inserting the first real entry.

---

## Phase 6: Update Coverage Sections

After triage, update the coverage tracking sections in the plan document.

### Step 6a: Areas Substantially Addressed

```markdown
### Areas Substantially Addressed

- **Specificity**: {count} suggestions applied ({id1}, {id2}, ...)
- **Dependencies**: {count} suggestions applied ({id1}, {id2}, ...)
- ...
```

Only list areas that have reached the threshold (>= 3 accepted).

### Step 6b: Areas Needing Further Review

```markdown
### Areas Needing Further Review

- **Data Contracts**: {count}/{threshold} suggestions accepted (need {gap} more)
- **Observability**: {count}/{threshold} suggestions accepted (need {gap} more)
- ...
```

Only list areas below the threshold.

---

## Phase 7: Verify Protocol Invariants

Before finishing, verify these invariants hold:

1. **Append-only** — Appendix C content from prior rounds was not modified. Only new rounds were appended.
2. **Monotonic rounds** — Your round number is strictly greater than all existing round numbers.
3. **No body modification** — The plan body (everything before the appendix `---` separator) was not changed by the review process.
4. **Domain exhaustiveness** — All 7 review areas were considered during your review. None were skipped.
5. **ID uniqueness** — Your suggestion IDs do not collide with any existing IDs in the document.
6. **Feasibility alignment** — No plan suggestion contradicts a feasibility document Appendix A (accepted) decision. No plan suggestion implements a feasibility Appendix B (rejected) decision.

---

## Area Aliases

LLMs sometimes use synonyms for area names. Normalize them:

| Synonym | Canonical Area |
|---------|---------------|
| detail, concreteness, precision, completeness, implementation detail | Specificity |
| ordering, sequencing, prerequisites, phase order, workflow | Dependencies |
| schema, types, models, fields, data structures, contracts | Data Contracts |
| risks, safety, fallback, error handling, failure modes, guards, gates | Risk Mitigation |
| testing, tests, test cases, assertions, verification, validation | Testability |
| metrics, telemetry, logging, monitoring, reporting, OTel | Observability |
| traceability, coverage, feasibility mapping, requirement coverage | Feasibility Traceability |

---

## Column Aliases

LLMs sometimes use different column headers. Normalize them:

| Synonym | Canonical Column |
|---------|-----------------|
| #, No, No., Number, Item, Ref, Suggestion ID | ID |
| Category, Domain, Focus Area, Topic | Area |
| Level, Priority, Impact, Sev | Severity |
| Recommendation, Finding, Issue, Description, Detail, Details | Suggestion |
| Reasoning, Justification, Reason, Explanation, Why | Rationale |
| Placement, Location, Section, Phase, Where | Proposed Placement |
| Validation, Test, Testing, How to Validate, Verification | Validation Approach |

---

## Convergence Criteria

### Phase Progression

| Phase | Typical Rounds | Coverage State | Reviewer Focus | Suggestion Character |
|-------|---------------|----------------|----------------|---------------------|
| **Early** | R1–R2 | 0–2 areas addressed | Broad scan for specificity gaps, missing data contracts, untested paths | Foundational: "this step can't be implemented as written because X is missing" |
| **Middle** | R2–R3 | 3–5 areas addressed | Targeted gap-filling, feasibility traceability audit | Targeted: "feasibility R3-S4 maps to Phase 1 but the plan doesn't specify the validation gate's exact checks" |
| **Late** | R3–R5 | 6–7 areas addressed | Cross-phase interactions, codebase compatibility, implementation shortcuts | Refined: "Phase 0's `CopySource` dataclass and Phase 1's `AssemblyStrategy` enum should share a base or be co-located because both are consumed by the router" |
| **Converged** | R5+ | All areas addressed | Consider stopping | If fewer than 2–3 novel suggestions emerge, the plan is implementation-ready |

### Convergence Signals

The review is likely converged when:

1. All 7 areas are substantially addressed (3+ accepted suggestions each)
2. Every accepted feasibility suggestion (R1–R6 Appendix A) maps to a `Full` coverage plan step
3. Gap-hunting rounds produce fewer than 2–3 novel suggestions
4. New suggestions are increasingly low-severity (medium/low)
5. A developer could write a PR for any plan phase using only the plan document and the codebase

### When Not to Stop

Even if coverage looks complete, continue if:

- Plan steps reference classes or methods that **don't exist in the current codebase** (stale references)
- Two plan phases produce or consume the **same data structure** but describe it with different field names or types
- A feasibility Appendix A suggestion's implementation in the plan would **conflict** with another accepted suggestion's implementation
- The plan describes **fallback behavior** (e.g., "fall back to `_handle_simple`") without specifying how the fallback is triggered or what state is cleaned up before fallback
