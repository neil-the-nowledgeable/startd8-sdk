# Convergent Review Prompt

**Generated:** 2026-06-15 16:31:24 UTC
**Mode:** Dual-Document (Plan + Requirements)

> **For the human / orchestrator who generated this file (not instructions to the reviewing agent):**
>
> - This prompt asks the reviewing **agent** to **persist suggestions directly into the source documents** by appending a new **Review Round** under the document's **Appendix C (Incoming)**. The A/B/C scaffold is **pre-initialized by this generator script** (per `CONVERGENT_REVIEW_AGENT_GUIDE.md`), so the reviewer only appends. The chat reply is a short write-confirmation only — **no** in-chat numbered list.
> - **Triage is yours and MUST be persisted, not stripped:** for each suggestion record a disposition — **Accepted → Appendix A** (note where it was merged) or **Rejected → Appendix B** (with rationale) — and update the **Areas Substantially Addressed** tracker (3 accepted per area). Appendices A/B are the **cross-model memory**: later reviewers (you embed the guide telling them so) read them to avoid re-proposing settled or rejected ideas. Do **not** delete A/B after merging.
> - **Suggested separate review passes (orchestrator workflow):** 2 — e.g. run the prompt once for breadth, again for adversarial pass, then triage yourself.
> - **Triage threshold (reference):** 3 accepted suggestions per review area when you triage.
> - **Max suggestions to request from the model:** 10 (soft cap in reviewer instructions below).
> - **Reviewer must have file-write tools (Write/Edit/equivalent) and filesystem access to the source documents.** Chat-only LLMs will fail this contract.

### Source documents

| Role | Path | Size |
|------|------|------|
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-import/docs/design/python-contract-codegen/GENERATED_IMPORT_PATH_PLAN.md` | 142 lines · 1360 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-import/docs/design/python-contract-codegen/GENERATED_IMPORT_PATH_REQUIREMENTS.md` | 352 lines · 3996 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/private/tmp/import-path-crp-focus.md` | 29 lines · 309 words |

Treat the embedded documents below as **read-only ground truth** for this review. If something conflicts between plan and requirements, call it out explicitly in suggestions and in the coverage mapping.

---

## Your Task

You are a **senior architectural reviewer** with **file-edit tools** (Write/Edit/equivalent) and filesystem access to the source documents listed above. Your job is to produce **improvement suggestions** (structured, anchored, actionable) and **persist them directly into the source documents** by appending a new **Review Round** under each reviewed document's **Appendix C (Incoming)** — see **Prior Review State** below.

**First, read the existing review state** (Appendix A/B/C) in each source doc and **avoid re-proposing** what is already settled (A) or rejected (B), and **avoid near-duplicates** of untriaged items in C (dedup rules below). Every in-scope doc already contains a `## Appendix: Iterative Review Log` with an empty A/B/C scaffold (the generator created it) — **append your round to Appendix C**; do **not** create a second scaffold.

**Do not** triage (no ACCEPT/REJECT disposition for your own or others' suggestions — that is orchestrator-side and lands in Appendix A/B), **do not** modify or rewrite existing prose, **do not** alter Appendix A/B or **prior rounds** in Appendix C, and **do not** emit a numbered suggestion list in chat — the orchestrator reads them from the files.

Optimize for **actionable, mergeable feedback** written into the right file.

### Prior Review State — read this BEFORE writing suggestions

Each source document **is** the persistent review state. Before proposing anything, parse its `## Appendix: Iterative Review Log` (if present):

- **Appendix A (Applied / Accepted)** — settled improvements. **Do not re-propose** anything here.
- **Appendix B (Rejected)** — read each **rationale**. Do **not** re-propose a rejected idea unless you explicitly cite its ID and argue why the rationale no longer holds.
- **Appendix C (Incoming)** — prior rounds, some untriaged. **Do not duplicate** a near-identical suggestion; if you agree with an untriaged item, **endorse** it (see Deliverables) instead of restating it.

**Your round number** is `R{n}` where **n = (highest existing `#### Review Round R{n}` in Appendix C) + 1**, or **1** if none exist. Put it in every suggestion ID: **R{n}-S{k}** (plan) / **R{n}-F{k}** (requirements).

**Go deeper, not wider:** prior reviewers caught the obvious issues — look for what they missed (second-order effects, cross-cutting concerns, interactions between already-accepted suggestions), and spend effort on areas with **few accepted** suggestions rather than those already **substantially addressed** (3+ accepted).

### Mode: Dual-Document Review

You have been given **two documents**: a project plan and a feature requirements document. Use **dual-document** perspective (plan ↔ requirements consistency) to inform your **suggestions only**—do not run full CRP phase/triage automation in this chat.

- Generate **S-prefix** suggestions targeting the **plan** (gaps, sequencing, risks, interfaces, validation strategy).
- Generate **F-prefix** suggestions targeting the **requirements** (ambiguity, missing acceptance criteria, inconsistencies, untestable statements).
- Optionally include a **Requirements coverage** table (each major requirement ID or section → plan section/task → **Covered / Partial / Gap**) as *observations* to inform the orchestrator—still **suggestions / analysis**, not triage.
- Use suggestion IDs so the orchestrator can map items to plan vs requirements later.

**Dual-document quality bar:** At least **three** F-prefix suggestions must cite a **specific sentence or table row** in the requirements; at least **three** S-prefix suggestions must cite a **specific section or task ID** in the plan. **Deprioritize** generic suggestions without anchors.


### Configuration (for structuring your suggestions)

| Parameter | Value |
|-----------|-------|
| Max suggestions (soft cap) | 10 |
| Review areas to consider | Architecture, Interfaces, Data, Risks, Validation, Ops, Security |

### Sponsor / author — review focus (from --focus-file)

Prioritize the following when scoring severity and ordering work. Do not treat this file as normative over the requirements or plan; use it to **weight** attention.

# Where we need review input most

1. **FR-IMP-2 — the identity-key CONSOLIDATION (highest stakes).** `ai_layer.py` already ships TWO
   dedup keys (`source_binding` = source-scope; `dedup_by` = single field, F-11). The plan unifies
   them into one declared `IdentityKey` (id | field | composite | source | name | none) in a shared
   helper consumed by BOTH the AI-persist path and the new `from_json` path. Is the unified vocabulary
   complete and unambiguous? Is the **byte-identity back-compat gate** (existing passes emit identical
   generated code) a sufficient regression guard, or are there cases it misses (e.g. a pass that sets
   both keys today)? Is the shared-seam (one helper, two call sites) the right boundary, or does the
   AI path's `confirmed`-aware source-scope clear diverge enough from `from_json`'s user-row upsert
   that one abstraction will leak?

2. **Coordination with the parallel team that owns `ai_layer.py`.** Phase 0 front-loads a proposal,
   but is the plan resilient if the owner rejects the consolidation or ships a third key first? Should
   FR-IMP-2 be decoupled so FR-IMP-1/3/6 can proceed without it?

3. **FR-IMP-1 `from_json` gate discipline.** It borrows the FR-PE-6 fail-loud model (errors /
   unrenderable / `--allow-lossy`). For an IMPORT (vs emit), what failure modes are unique — partial
   transactions, FK ordering across entities, a row whose identity collides with a confirmed row,
   malformed JSON? Does the structured `ImportResult` + `--strict`/`--allow-lossy` cover them?

4. **FR-IMP-3 `imports.yaml` grammar.** It clones the FR-PE manifest pattern. Are the grammar columns
   (Entity | Format | Identity | Provenance | Extract via | Surface) the right closed vocabulary? Any
   cross-manifest coupling risk (it references `human_inputs.yaml` provenance + `ai_passes.yaml`
   extractor by name — what if those drift)?

5. **OQ-IMP-D — the unnamed consumer (load-bearing).** The acceptance (FR-IMP-1/6 target entities,
   formats) depends on naming the first consumer. Is it safe to build P1/P2 before that's resolved, or
   does the unnamed consumer poison the whole plan's acceptance criteria?

**If the focus file above contains numbered asks** (e.g. `A1`/`A2`/`Ask 1`/`Ask 2` or similar), address each ask **at the top of your appended appendix**, before standard S/F-prefix suggestions, using this template per ask (orchestrator triages later — **no** ACCEPT/REJECT tables here, and **no** chat-only response):

```
- **Summary answer:** one sentence (e.g. yes / no / partial / depends on X)
- **Rationale:** 2–4 sentences with citations to FR-IDs, plan sections, or headings
- **Assumptions / conditions:** what must hold for your answer; or "none"
- **Suggested improvements:** concrete doc or plan deltas (bullet list OK)
```

Standard CRP S/F-prefix suggestions are **secondary** when explicit asks are present; do not let area-coverage steering distort effort allocation.

---

### Reviewer contract — suggestion quality and anti-slop rules

Every **suggestion you list** should be written so the orchestrator could **merge it as-is** if they agree (their adopt/decline step is **not** your task here). Aim for:

1. **Actionable** — A human could turn it into an edit, a new task, or a test without further clarification meetings.
2. **Anchored** — Include a **verbatim fragment** (short quote) or **heading path** from the document under review so the author can find the locus quickly.
3. **Scoped** — One primary issue per suggestion; use multiple suggestions instead of bundling unrelated concerns.
4. **Testable when relevant** — For requirements changes, state **how** acceptance could be verified (criterion, automated check, or explicit manual step).

**Reviewer attribution:** use your model identifier exactly as you would self-identify (e.g., `claude-opus-4-7-1m`, `claude-sonnet-4-6`, `claude-haiku-4-5`, `gpt-5`). Do not invent.

**Length budget:** target roughly **500–1500 words** total across the appended appendix sections (adjust up slightly if the focus file has many numbered asks). Quality over volume.

**Self-filter (do not label as triage):** Omit vague praise (“looks good”), duplicate issues, and purely stylistic nits unless they block comprehension. **Also omit near-duplicates of suggestions already in Appendix A/B/C** — endorse or extend the existing ID instead (see Deliverables). If something **contradicts stated project constraints**, frame it as a **scope trade-off** suggestion rather than as a mandate.

**Deliverables (mandatory — persist to source files, not chat):**

1. **Append a `#### Review Round R{n} — <your-model-id> — <UTC date>`** block under **Appendix C (Incoming)** of each source document you reviewed (plan suggestions → plan file; requirements suggestions → requirements file). The `## Appendix: Iterative Review Log` scaffold already exists (generator-created) — append to its Appendix C. Use Write/Edit; do **not** modify existing prose, Appendix A/B, or prior rounds.
2. **Inside your round block**, include:
   - **Executive summary** — at most **10 bullets**: top risks, opportunities, blocking gaps (no triage tables).
   - **Numbered suggestions** — full list with **R{n}-S{k}** / **R{n}-F{k}** IDs. Optional "first pass" / "adversarial pass" subsections — **no** ACCEPT/REJECT columns.
3. **Endorsements & Disagreements (do this if you have tokens remaining):** after your suggestions, react to **untriaged** prior items (in Appendix C, not yet in A/B):
   - `**Endorsements**` — prior IDs you agree with, one-line reason each.
   - `**Disagreements**` — untriaged prior IDs you would reject, one-line reason (so triage can weigh it).
   This builds the cross-model consensus signal the orchestrator uses during triage.
4. **(Dual mode only)** Append a `## Requirements Coverage Matrix — R{n}` section at the **end of the plan file** mapping each major requirement ID/section → plan section/task → **Covered / Partial / Gap**. Analysis only.
5. **Chat reply** — a **short write-confirmation** (1-3 lines) with your round number, file paths, and counts (e.g. `Round R2: 6 S-suggestions → plan.md, 4 F → requirements.md, 3 endorsements`). **Do not** repeat suggestion content in chat.

**Suggestion ID reminder (dual mode):** Plan → **R{n}-S{k}**; Requirements → **R{n}-F{k}** (n = your round, computed from Appendix C; the orchestrator triages your items into Appendix A/B afterward).

### Optional second-pass suggestions (inside the appended appendix, still no triage)

If you still have budget under the max-suggestions cap after your first list, you may add a `### Stress-test / adversarial pass` subheading **inside your round block**, with **additional** numbered suggestions (continue **R{n}-S\*** / **R{n}-F\*** numbering within the same round — do not fabricate a separate round). Try to break your own prior conclusions where it genuinely helps; skip if redundant. **Still no in-chat list** — keep the chat reply to the short write-confirmation.


---

### Pre-flight (before drafting suggestions)

1. **Optionally expand** the protocol guide `<details>` block below and skim **quality norms** (anchoring, scope, security). You are **not** executing full CRP phase/triage automation—use the guide as reference only.
2. Read the **Document Under Review** section(s) once for structure; read again while drafting suggestions.
3. Note **explicit out-of-scope** lines — do not file suggestions that only restate excluded work unless you flag a **dependency risk** (why exclusion threatens delivery).

---

### Protocol guide — optional reference (norms for good suggestions)

**Important:** Some chat clients or models collapse `<details>` by default. Expand if you need **deeper** CRP vocabulary; this prompt does **not** require you to run guide phases 5–7 (triage, appendix merge, final document emit).

If anything in the guide seems to conflict with **this prompt’s “suggestions only” scope**, **this prompt wins** for what you must deliver in-chat; the orchestrator reconciles with the guide afterward.


### Scope lock (normative — overrides conflicting text in the guide below)

The long **Protocol guide** block below (wrapped in an HTML **details** element) embeds the **full** CRP guide, including instructions for **triage**, **appendix edits**, and **document rewrites**. For **this** assignment:

**You MUST:**

- First **read** each source doc's Appendix A/B/C and **avoid re-proposing** settled (A) or rejected (B) items; **dedup** against untriaged C.
- Use file-edit tools to **append a `#### Review Round R{n}` block** under **Appendix C** of each reviewed doc, computing **n** = highest existing round + 1 (or 1). The `## Appendix: Iterative Review Log` scaffold is **pre-initialized by the generator** — append to it; do not recreate it.
- In dual mode, also append a `## Requirements Coverage Matrix — R{n}` section to the end of the plan file.
- If tokens remain, add an **Endorsements & Disagreements** block on untriaged prior suggestions.

**You MUST NOT:**

- Triage (no ACCEPT/REJECT disposition for your own or others' suggestions) — that is orchestrator-side and lands in Appendix A/B.
- Modify, rewrite, reorder, or delete existing prose, **populated** Appendix A/B, or **prior rounds** in Appendix C. (The A/B/C scaffold is generator-created — do **not** add a second one.)
- Execute **Phase 5–7** (triage/merge) from the guide, or output a **rewritten** document body.
- Reproduce the full numbered suggestion list in chat — chat output is a **short write-confirmation** only.

Treat the guide as **optional reference** for vocabulary, risk lenses, and quality norms only — not as a second execution checklist.

## Convergent Review Protocol — Agent Execution Guide

<details>
<summary><strong>Expand: full CRP protocol guide</strong> (you append your round to Appendix C; triage into Appendix A/B is orchestrator-side)</summary>

# Convergent Review Protocol (CRP) — Agent Execution Guide

**Purpose:** Step-by-step instructions for any AI agent to run the Convergent Review Protocol on a document. Covers first-encounter initialization, document formatting, review rounds, triage, and convergence tracking.

**Protocol source:** `ARCHITECTURAL_REVIEW_REQUIREMENTS.md` (76 requirements, RV-100 through RV-807)

---

## How This Process Works: Multi-Agent Iterative Review

**You are not the only reviewer.** This document undergoes multiple sequential review rounds, each performed by a different agent (or the same agent in a later pass). The CRP is designed so that each reviewer builds on the cumulative work of all prior reviewers — not by re-reading their raw suggestions, but by reading the **triaged outcomes** persisted in the document itself.

### What You Inherit From Prior Reviewers

When you receive a document that has already been through CRP rounds, the appendix structure contains the full review history:

- **Appendix A (Applied)** — Suggestions that prior reviewers proposed and that were accepted during triage. These are the "settled" improvements. **Do not re-propose anything that already appears here.**
- **Appendix B (Rejected)** — Suggestions that were explicitly rejected with rationale. **Read the rejection rationale carefully.** If you believe a rejected idea should be reconsidered, you must explicitly reference its ID and argue why the original rationale no longer applies. Do not silently re-propose rejected ideas.
- **Appendix C (Incoming)** — Raw suggestion tables from each prior round, plus any endorsement blocks. Contains both triaged and untriaged suggestions. Your job is to add a new round here, not modify existing rounds.
- **Areas Substantially Addressed / Areas Needing Further Review** — Coverage tracking sections that tell you which areas have enough accepted suggestions and which still need attention.

### Your Role as Reviewer R{n}

Each review pass should be **sharper than the last**. You are not starting from scratch — you are working from the foundation laid by R1 through R{n-1}. Your job is to:

1. **Go deeper, not wider** — Prior reviewers handled the obvious issues. Look for what they missed: second-order effects, unstated assumptions, cross-cutting concerns, and interactions between already-accepted suggestions.
2. **Challenge, don't repeat** — If prior rounds covered an area well, do not generate more suggestions in that area unless you find a genuine gap. Redundant suggestions waste triage effort.
3. **Endorse good untriaged work** — If a prior reviewer proposed something valuable that hasn't been triaged yet, endorse it rather than proposing a duplicate. Endorsements build consensus signal.
4. **Respect rejections** — Rejected suggestions were dismissed for a reason. Read the rationale. Only revisit if circumstances have changed or the rationale was flawed.

### The Document Is the State

There is no external database or API tracking review state. The document's appendix structure **is** the persistent state. Round numbers, applied/rejected decisions, coverage counts, and endorsement signals are all derived by parsing the document. This means:

- If the document is passed to you with Appendices A/B/C populated, prior rounds happened.
- If Appendix A is empty and Appendix C has no rounds, you are the first reviewer.
- If coverage sections show 5 of 7 areas addressed, the review is in its middle-to-late phase.
- Your output is appended to the document and becomes part of the state for the next reviewer.

---

## Quick Reference

| Concept | Value |
|---------|-------|
| Review areas | Architecture, Interfaces, Data, Risks, Validation, Ops, Security |
| Severities | critical, high, medium, low |
| Suggestion ID format | `R{round}-S{n}` (plan), `R{round}-F{n}` (feature requirements) |
| Table columns (7) | ID, Area, Severity, Suggestion, Rationale, Proposed Placement, Validation Approach |
| Substantially addressed threshold | 3 accepted suggestions per area (configurable) |
| Appendix A | Applied suggestions (accepted and integrated) |
| Appendix B | Rejected suggestions (with rationale) |
| Appendix C | Incoming suggestions (untriaged, append-only) |

---

## Phase 0: First-Encounter Initialization

When you receive a document for review **for the first time** (no appendix structure exists), you must prepare it before generating any review suggestions.

### Step 0a: Detect Whether Initialization Is Needed

Search the document for this heading:

```
## Appendix: Iterative Review Log (Applied / Rejected Suggestions)
```

- **If found:** The document has been through CRP before. Skip to Phase 1.
- **If not found:** This is a first encounter. Continue with Step 0b.

### Step 0b: Append the Appendix Structure

Append the following template **verbatim** to the end of the document, separated from the body by a horizontal rule (`---`):

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

Write the document back with the appendix appended. **Do not modify the document body.** The initialization is purely additive.

---

## Phase 1: Pre-Review Analysis

Before generating suggestions, analyze the current state of the document.

### Step 1a: Parse Existing State

1. **Scan Appendix A** — collect all applied suggestion IDs and their areas.
2. **Scan Appendix B** — collect all rejected suggestion IDs. Read rejection rationale to understand what has already been considered and dismissed.
3. **Scan Appendix C** — find the highest existing round number by searching for `#### Review Round R{n}` headings. Your round number is `max(existing) + 1`, or `1` if no rounds exist.
4. **Collect untriaged suggestions** — any suggestions in Appendix C whose IDs do not appear in Appendix A or B.

### Step 1b: Compute Area Coverage

For each of the 7 review areas, count how many suggestions have been **accepted** (appear in Appendix A):

| Area | Accepted Count | Addressed? (>= 3) | Gap |
|------|---------------|-------------------|-----|
| Architecture | ? | ? | ? |
| Interfaces | ? | ? | ? |
| Data | ? | ? | ? |
| Risks | ? | ? | ? |
| Validation | ? | ? | ? |
| Ops | ? | ? | ? |
| Security | ? | ? | ? |

An area is **substantially addressed** when it has >= 3 accepted suggestions (the default threshold; configurable per run).

#### Understanding "Substantially Addressed"

This threshold is a **steering mechanism**, not a quality certification. An area with 3 accepted suggestions is not "done" — it means the review process has invested enough attention there that additional suggestions in that area should only come from genuine insight, not routine scanning. The threshold exists to prevent late-round reviewers from piling more suggestions into areas that are already well-covered while neglecting areas with zero coverage.

**How it affects your behavior:**

| Coverage State | Your Priority | What to Do |
|----------------|--------------|------------|
| 0 accepted in an area | Highest | This area has been completely overlooked. Allocate suggestion slots here first. |
| 1–2 accepted in an area | High | Below threshold. Prioritize but check what's already accepted to avoid overlap. |
| 3+ accepted in an area | Low | Substantially addressed. Only propose if you find something the prior 3+ suggestions genuinely missed. |
| All 7 areas at 3+ | Shift focus | Enter gap-hunting mode. Stop thinking in terms of individual areas and look for cross-cutting concerns, low-hanging opportunities, and design principle alignment. |

**Key insight:** The coverage table in Step 1b is your primary decision tool for allocating review effort. Do not distribute suggestions evenly across areas — concentrate on the gaps.

### Step 1c: Determine Review Mode

Based on coverage analysis:

- **Some areas below threshold** — Enter **two-tier priority mode** (Phase 2a). Focus your suggestion slots on uncovered areas.
- **All areas at or above threshold** — Enter **gap-hunting and opportunity mode** (Phase 2b). Shift from area coverage to deeper analysis, cross-cutting concerns, and high-value opportunities.
- **Most areas addressed (5–6 of 7)** — Use two-tier mode but recognize you are in a late-phase review. For the 1–2 remaining gaps, be precise. For addressed areas, consider whether the plan/requirements create natural opportunities for low-effort, high-value improvements (see Phase 2b, Lens 1).

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
- Consider whether accepted suggestions in addressed areas **enable low-effort extensions** — if so, these belong in your Tier 2 slots (see Phase 2b, Lens 1)

### Transitional State (5–6 of 7 areas addressed)

When only 1–2 areas remain below threshold, you are in a **transitional state** between two-tier and gap-hunting modes. Handle this by:

1. Allocating 2–3 suggestion slots to the remaining uncovered areas (Tier 1)
2. Using the rest of your slots for gap-hunting and opportunity suggestions across the already-addressed areas (Tier 2, using the Phase 2b lenses)
3. Paying special attention to interactions between the uncovered area(s) and the well-covered areas — these cross-cutting blind spots are the most common late-phase misses

### Generate Your Suggestions

Produce a review round following the output format in Phase 3.

---

## Phase 2b: Gap-Hunting and Opportunity Mode

When all 7 areas are substantially addressed (or nearly so — 5–6 of 7 with the remainder close), shift from area coverage to deeper analysis and value discovery.

**Mindset shift:** In early rounds, reviewers are scanning for problems — missing sections, unaddressed risks, gaps in coverage. By the time all areas are substantially addressed, the obvious problems have been found. Your job now is different: find what the plan/requirements **make possible but don't yet exploit**, and surface cross-cutting issues that only become visible after the foundational suggestions are in place.

### Gap-Hunting and Opportunity Lenses

Evaluate the document through these lenses, in order of priority:

**1. Low-hanging fruit: high-value improvements enabled by the plan**

The most valuable late-round suggestions are often not about what's *wrong* but what's *almost there*. Read the plan and requirements together and ask: given what is already committed to, what low-effort additions would deliver outsized value?

- **Capabilities that are 80% built** — The plan describes infrastructure (an event bus, a validation layer, an API gateway) that could serve additional use cases with minimal extension. Call these out specifically: "Since you are already building X, adding Y is ~N lines of additional work and enables Z."
- **Data already flowing that isn't being captured** — The plan may route data through a pipeline without persisting intermediate results that would be valuable for debugging, analytics, or audit. If the data is already in hand, storing it is low effort.
- **Configuration that could be externalized** — Hard-coded values, thresholds, or feature flags mentioned in the plan that could be made configurable with minimal overhead, enabling runtime tuning without redeployment.
- **Reusable building blocks** — A component built for one task that could serve 2–3 other tasks if its interface were slightly generalized. The plan already pays the cost of building it — generalizing it captures compound value.
- **Test infrastructure synergies** — Test fixtures, mock services, or validation harnesses described for one feature that could be shared across features with minor refactoring.

**Framing:** These suggestions should emphasize the **effort-to-value ratio**. "Since the plan already does A, extending it to also do B requires [specific low effort] and yields [specific high value]." Avoid vague "it would be nice" suggestions — quantify the lift and the payoff where possible.

**2. Gaps and cross-cutting concerns**
- Contradictions between areas (e.g., an ops process that conflicts with an architecture decision)
- Assumptions that were never validated
- Second-order effects of accepted suggestions — do any of the previously accepted changes create new risks or interactions?
- Edge cases or failure modes not yet addressed
- Interactions between accepted suggestions from different rounds that were reviewed independently

**3. Missed opportunities to leverage platform capabilities**
- Data or artifacts already available from upstream pipeline stages that the design ignores
- Deterministic computations being deferred to stochastic LLM inference
- Existing infrastructure (OTel, ContextCore contracts, capability index) that could replace hand-rolled solutions
- Reusable components or shared utilities that would reduce duplication

**4. Design principle violations**

Evaluate against these three principles:

- **Mottainai** (waste aversion) — Are artifacts from earlier pipeline stages being discarded or regenerated instead of forwarded? Is deterministic data being re-derived via LLM? Does the design inventory what exists before generating?

- **Context Correctness by Construction** (declare-and-verify) — Does the design declare what context must flow between phases and verify it at boundaries? Are there silent degradation paths where missing context falls through to defaults without signaling? Are contracts prescriptive (declare and verify) rather than descriptive (collect and hope)?

- **Context Contracts** (boundary validation) — Do phase boundaries validate required fields with appropriate severity (BLOCKING/WARNING/ADVISORY)? Is provenance tracked so data can be traced to its source? Can the design degrade gracefully when upstream data is missing rather than failing silently?

### Prioritizing Late-Round Suggestions

When you are in gap-hunting and opportunity mode, prioritize your suggestion slots in this order:

1. **Low-effort, high-value opportunities** (Lens 1) — These are the most actionable and most likely to be accepted during triage because they build on decisions already made.
2. **Cross-cutting gaps** (Lens 2) — Issues that span multiple areas are the ones most likely to have been missed by area-focused early rounds.
3. **Platform leverage** (Lens 3) — Concrete opportunities to replace custom work with existing infrastructure.
4. **Principle violations** (Lens 4) — Important but more abstract; triage may defer these if the other suggestions are more immediately actionable.

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
| R{n}-S1 | {area} | {severity} | {suggestion text} | {why this matters} | {where in the doc} | {how to verify} |
| R{n}-S2 | ... | ... | ... | ... | ... | ... |
```

### Output Rules

1. **Round heading** — Must be `#### Review Round R{n}` with the correct round number.
2. **Metadata block** — Must include Reviewer, Date (UTC), and Scope.
3. **Table columns** — Must use exactly these 7 headers: `ID`, `Area`, `Severity`, `Suggestion`, `Rationale`, `Proposed Placement`, `Validation Approach`. Plain text headers only (no bold, no italic).
4. **Suggestion IDs** — Must follow `R{round}-S{n}` format, numbered sequentially starting at 1.
5. **Area values** — Must be one of: `Architecture`, `Interfaces`, `Data`, `Risks`, `Validation`, `Ops`, `Security`. Use title case.
6. **Severity values** — Must be one of: `critical`, `high`, `medium`, `low`. Use lowercase.
7. **Suggestion count** — At least 1, at most 10 (configurable; default 10).
8. **Pipe escaping** — If suggestion text contains `|`, escape it as `\|` to preserve table structure.
9. **No appendix modification** — Output must NOT contain `### Appendix A` or `### Appendix B` headings.
10. **No document rewriting** — Output the snippet only, not the entire document.

### Endorsements (optional)

If you agree with untriaged suggestions from prior rounds (in Appendix C but NOT in Appendix A or B), append an endorsement block after your table:

```markdown
**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R{prior_round}-S{n}: {one-sentence reason you agree}
- R{prior_round}-S{m}: {one-sentence reason you agree}
```

Only endorse suggestions you genuinely believe should be implemented. Do not endorse your own suggestions from the current round.

---

## Phase 4: Append the Review Round

Append your generated snippet to the end of the document, after all existing content in Appendix C. Do not insert it anywhere else.

---

## Phase 5: Triage

After all review rounds for this session are complete, triage all untriaged suggestions.

### Step 5a: Collect Untriaged Suggestions

Parse Appendix C for all suggestion rows whose IDs do **not** appear in Appendix A or Appendix B.

### Step 5b: Classify Each Suggestion

For each untriaged suggestion, decide:

- **ACCEPT** — The suggestion is valuable and should be integrated into the document. Move a row into Appendix A.
- **REJECT** — The suggestion is not worth implementing. Move a row into Appendix B **with a specific rationale** explaining why.

Consider endorsement counts: suggestions endorsed by multiple reviewers across rounds carry stronger consensus signal.

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

### Step 5d: Partial Triage Is Acceptable

You do not need to triage every suggestion in a single pass. Suggestions not covered remain untriaged in Appendix C for the next triage pass.

---

## Phase 6: Update Coverage Sections

After triage, update (or insert) two coverage tracking sections in the document. These go **inside** the appendix, before Appendix A.

### Step 6a: Areas Substantially Addressed

Insert or update this section:

```markdown
### Areas Substantially Addressed

- **Architecture**: {count} suggestions applied ({id1}, {id2}, ...)
- **Interfaces**: {count} suggestions applied ({id1}, {id2}, ...)
- ...
```

Only list areas that have reached the threshold (>= 3 accepted).

### Step 6b: Areas Needing Further Review

Insert or update this section (after "Areas Substantially Addressed"):

```markdown
### Areas Needing Further Review

- **Data**: {count}/{threshold} suggestions accepted (need {gap} more)
- **Security**: {count}/{threshold} suggestions accepted (need {gap} more)
- ...
```

Only list areas below the threshold.

---

## Phase 7: Verify Protocol Invariants

Before finishing, verify these invariants hold:

1. **Append-only** — Appendix C content from prior rounds was not modified. Only new rounds were appended.
2. **Monotonic rounds** — Your round number is strictly greater than all existing round numbers.
3. **No body modification** — The document body (everything before the appendix `---` separator) was not changed by the review process (only by explicit triage-driven integration, if applicable).
4. **Domain exhaustiveness** — All 7 review areas were considered during your review. None were skipped.
5. **ID uniqueness** — Your suggestion IDs do not collide with any existing IDs in the document.

---

## Dual-Document Mode: Plan + Requirements Combo Evaluation

When you are given both a **plan document** and a **feature requirements document**, you operate in dual-document mode. This mode adds requirements traceability, a second suggestion stream, and cross-document routing on top of the standard CRP phases.

### When to Enter Dual-Document Mode

Enter dual-document mode when **both** of these are true:

1. You have a plan/design document (the primary review target)
2. You have a separate feature requirements document that the plan is supposed to implement

If you only have a plan with no separate requirements doc, use standard single-document mode (Phases 0–7 above).

### Quick Reference (Dual-Document Additions)

| Concept | Value |
|---------|-------|
| Plan suggestion IDs | `R{n}-S1`, `R{n}-S2`, ... (S-prefix) |
| Requirements suggestion IDs | `R{n}-F1`, `R{n}-F2`, ... (F-prefix) |
| Extra output section | `#### Feature Requirements Suggestions` table |
| Extra output section | `#### Requirements Coverage` mapping table |
| Routing | S-prefix → plan doc appendices; F-prefix → requirements doc appendices |

---

### Phase 0-DD: Initialize Both Documents

Both documents must have the three-appendix structure. Run Phase 0 (Steps 0a–0c) independently on **each** document:

1. **Plan document** — check for `## Appendix: Iterative Review Log` heading. If missing, append the full appendix template (Phase 0b).
2. **Requirements document** — check for the same heading. If missing, append the same appendix template.

Both documents are now ready for CRP review rounds.

---

### Phase 1-DD: Pre-Review Analysis (Both Documents)

Extend Phase 1 to cover both documents:

1. **Parse plan document state** — Appendix A/B/C, round number, coverage (same as Phase 1a–1c).
2. **Parse requirements document state** — Appendix A/B/C of the requirements doc. Track accepted/rejected F-prefix IDs separately.
3. **Read the requirements document body** — identify each requirement section/heading. You will need these for the coverage mapping.

### Phase 2-DD: Review With Traceability

Your review must cover three concerns simultaneously:

1. **Plan quality** — the same 7-area architectural review (Phases 2a/2b apply as normal). These produce S-prefix suggestions targeting the plan document.
2. **Requirements quality** — are the requirements themselves ambiguous, conflicting, incomplete, or missing acceptance criteria? These produce F-prefix suggestions targeting the requirements document.
3. **Plan-to-requirements traceability** — does the plan adequately address every requirement? This produces the Requirements Coverage table.

---

### Phase 3-DD: Generate the Review Round (Dual-Document Output)

Your output must contain **three sections** in this order:

#### Section 1: Plan Suggestions (S-prefix)

The standard 7-column table, identical to single-document mode:

```markdown
#### Review Round R{n}

- **Reviewer**: {your name or model identifier}
- **Date**: {YYYY-MM-DD HH:MM:SS UTC}
- **Scope**: {brief description of review focus}

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R{n}-S1 | {area} | {severity} | {plan suggestion} | {why} | {where in plan} | {how to verify} |
| R{n}-S2 | ... | ... | ... | ... | ... | ... |
```

**Rules:** Same as Phase 3 output rules (7 columns, area/severity enums, max 10 S-prefix suggestions per round).

#### Section 2: Feature Requirements Suggestions (F-prefix)

A **separate** table under its own heading for issues found in the requirements document itself:

```markdown
#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R{n}-F1 | {area} | {severity} | {requirements issue} | {why} | {where in requirements doc} | {how to verify} |
| R{n}-F2 | ... | ... | ... | ... | ... | ... |
```

**When to generate F-prefix suggestions:**

- A requirement is **ambiguous** — could be interpreted multiple ways by an implementer
- A requirement is **conflicting** — contradicts another requirement or a plan decision
- A requirement is **incomplete** — missing acceptance criteria, boundary conditions, or error cases
- A requirement is **missing** — the plan reveals a need that no requirement covers
- A requirement is **untestable** — no clear way to verify it was implemented correctly

**If the requirements are clean**, you may omit this section entirely (or include it with zero rows). Do not invent issues.

#### Section 3: Requirements Coverage Mapping

A traceability table mapping each requirement section to plan coverage:

```markdown
#### Requirements Coverage

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| {requirement heading or ID} | {plan section(s) that address it} | Full | — |
| {requirement heading or ID} | {plan section(s) that address it} | Partial | {what's missing from the plan} |
| {requirement heading or ID} | (none) | Missing | {the plan does not address this requirement} |
```

**Coverage values:**

| Value | Meaning |
|-------|---------|
| `Full` | The plan fully addresses this requirement with clear implementation steps |
| `Partial` | The plan mentions it but is missing detail, edge cases, or implementation specifics |
| `Missing` | The plan does not address this requirement at all |

**Rules:**

- Every requirement section in the requirements document must appear in this table. Do not skip any.
- When Coverage is `Partial` or `Missing`, the Gaps column must explain specifically what is lacking.
- `Partial` coverage with gaps should generate a corresponding S-prefix suggestion in Section 1 (proposing the plan addition).
- `Missing` coverage should generate a corresponding S-prefix suggestion in Section 1 (proposing plan coverage for the requirement).

---

### Phase 4-DD: Append and Route

After generating your output:

1. **Plan suggestions (S-prefix)** — Append the full round snippet (Section 1 + Section 3) to the **plan document's** Appendix C.
2. **Feature suggestions (F-prefix)** — If Section 2 is non-empty, wrap it in a round heading with metadata and append it to the **requirements document's** Appendix C:

```markdown
#### Review Round R{n}

- **Reviewer**: {your name or model identifier}
- **Date**: {YYYY-MM-DD HH:MM:SS UTC}
- **Scope**: {scope} (Feature Requirements)

#### Feature Requirements Suggestions
{the F-prefix table from Section 2}
```

**Do not mix S-prefix and F-prefix suggestions in the same document's appendix.**

---

### Phase 5-DD: Triage (Both Documents)

Triage handles both prefixes:

1. **Collect all untriaged suggestions** — S-prefix from the plan doc's Appendix C, F-prefix from the requirements doc's Appendix C.
2. **Classify each suggestion** — ACCEPT or REJECT, same as Phase 5.
3. **Route decisions by prefix:**
   - S-prefix ACCEPT → plan document Appendix A
   - S-prefix REJECT → plan document Appendix B
   - F-prefix ACCEPT → requirements document Appendix A
   - F-prefix REJECT → requirements document Appendix B

---

### Phase 6-DD: Update Coverage (Both Documents)

Update the "Areas Substantially Addressed" and "Areas Needing Further Review" sections in **both** documents independently, based on each document's own Appendix A counts.

---

### Phase 7-DD: Verify Invariants (Both Documents)

Verify all Phase 7 invariants on **both** documents:

- Append-only, monotonic rounds, no body modification, domain exhaustiveness, ID uniqueness
- **Additional invariant:** No S-prefix IDs in the requirements document's appendix; no F-prefix IDs in the plan document's appendix

---

### Worked Example: First Dual-Document Review

**Scenario:** You receive `IMPLEMENTATION_PLAN.md` and `FEATURE_REQUIREMENTS.md`, neither has appendix structure.

#### 1. Initialize Both

Append the appendix template to both documents (Phase 0-DD).

#### 2. Analyze

- Plan: empty appendices, Round 1, all areas at 0/3
- Requirements: empty appendices
- Requirements doc body has 5 sections: Authentication, Rate Limiting, Data Export, Audit Logging, Error Handling

#### 3. Generate Round R1

**Section 1 (Plan suggestions):**

```markdown
#### Review Round R1

- **Reviewer**: Claude Opus 4.6 (claude-opus-4-6)
- **Date**: 2026-02-28 20:00:00 UTC
- **Scope**: Full architectural review with requirements traceability

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | Add rate limiting middleware layer | Plan has no rate limiting implementation despite REQ-RL-001 | Section 3: API Design | Load test with rate limit thresholds |
| R1-S2 | Security | critical | Add JWT token rotation strategy | Authentication section lacks token lifecycle management | Section 2: Authentication | Security audit of token flow |
| R1-S3 | Data | medium | Define data export pagination | Export endpoint will timeout on large datasets | Section 4: Data Export | Test export with 100k+ records |
| R1-S4 | Ops | high | Add structured audit log format | Audit logging requirement has no log schema in plan | Section 5: Audit Logging | Verify log entries match schema |
```

**Section 2 (Requirements suggestions):**

```markdown
#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Validation | medium | Add rate limit thresholds to REQ-RL-001 | Requirement says "rate limiting" but specifies no limits (requests/sec, burst) | Rate Limiting section | Verify numeric thresholds are specified |
| R1-F2 | Interfaces | medium | Add error response format to Error Handling | Requirement specifies "graceful error handling" but no response schema | Error Handling section | Verify JSON error schema is defined |
```

**Section 3 (Coverage mapping):**

```markdown
#### Requirements Coverage

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| Authentication | Section 2: Authentication | Partial | Missing token rotation and session management |
| Rate Limiting | (none) | Missing | No rate limiting section in the plan |
| Data Export | Section 4: Data Export | Partial | No pagination or timeout strategy |
| Audit Logging | Section 5: Observability | Partial | Mentioned but no structured log format |
| Error Handling | Section 6: Error Handling | Full | — |
```

#### 4. Route

- Append the full snippet (Sections 1 + 3) to `IMPLEMENTATION_PLAN.md` Appendix C
- Wrap Section 2 in a round heading and append to `FEATURE_REQUIREMENTS.md` Appendix C

#### 5. Triage

- Accept R1-S1, R1-S2, R1-S4 → plan Appendix A
- Reject R1-S3 (pagination is handled by framework) → plan Appendix B
- Accept R1-F1 → requirements Appendix A
- Accept R1-F2 → requirements Appendix A

#### 6. Update Coverage

Plan: Architecture=1, Security=1, Ops=1 — all below threshold. Requirements: track F-prefix accepted counts separately.

---

## Area Aliases

LLMs sometimes use synonyms for area names. Normalize them:

| Synonym | Canonical Area |
|---------|---------------|
| design, structure, modularity, scalability, maintainability, extensibility, clarity, readability, documentation | Architecture |
| api, apis, contracts, integration | Interfaces |
| data model, data models, storage, database, persistence | Data |
| risk, reliability, resilience, fault tolerance, error handling | Risks |
| testing, testability, test, quality, completeness | Validation |
| operations, deployment, observability, monitoring, performance, infrastructure | Ops |
| auth, authentication, authorization | Security |

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
| Placement, Location, File, File Path, Where | Proposed Placement |
| Validation, Test, Testing, How to Validate, Verification | Validation Approach |

---

## Worked Example: First Review of a New Document

**Scenario:** You receive `IMPLEMENTATION_PLAN.md` with no appendix structure.

### 1. Initialize

Detect: no `## Appendix: Iterative Review Log` heading found. Append the full appendix template (Phase 0b).

### 2. Analyze

- Appendix A: empty (no applied suggestions)
- Appendix B: empty (no rejected suggestions)
- Appendix C: empty (no prior rounds)
- Round number: 1 (no existing rounds)
- Coverage: all areas at 0/3, all below threshold

### 3. Review (Two-Tier Priority)

All 7 areas are uncovered, so all are Tier 1 priority. Generate up to 10 suggestions spread across the areas with the largest gaps.

### 4. Output

```markdown
#### Review Round R1

- **Reviewer**: Claude Opus 4.6 (claude-opus-4-6)
- **Date**: 2026-02-28 18:00:00 UTC
- **Scope**: Full architectural review — initial pass across all 7 areas

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | Add dependency injection for service layer | Improves testability and decouples components | Section 3: Architecture | Unit test coverage of isolated services |
| R1-S2 | Security | critical | Add input validation at API boundary | Prevents injection attacks (OWASP A03) | Section 5: API Design | OWASP ZAP scan + fuzz testing |
| R1-S3 | Data | medium | Define schema migration strategy | Avoids breaking changes on deployment | Section 4: Data Model | Dry-run migration against staging DB |
| R1-S4 | Risks | high | Add circuit breaker for external API calls | Prevents cascade failures under load | Section 6: Integration | Load test with upstream service unavailable |
| R1-S5 | Validation | medium | Add contract tests for API consumers | Catches breaking changes before deployment | Section 5: API Design | Run contract test suite in CI |
| R1-S6 | Ops | high | Define health check endpoints | Required for orchestrator liveness probes | Section 7: Deployment | Verify probe responses under load |
| R1-S7 | Interfaces | medium | Version the REST API from day one | Avoids breaking consumers on iteration | Section 5: API Design | Integration test with versioned routes |
```

### 5. Append

Append the snippet after `### Appendix C: Incoming Suggestions (Untriaged, append-only)`.

### 6. Triage

Evaluate each suggestion. For this example, accept R1-S1 through R1-S4 and reject none:

Insert into Appendix A:
```markdown
| R1-S1 | Add dependency injection for service layer | Claude Opus 4.6 | Restructured service layer with DI container | 2026-02-28 |
| R1-S2 | Add input validation at API boundary | Claude Opus 4.6 | Added Pydantic validators on all endpoints | 2026-02-28 |
| R1-S3 | Define schema migration strategy | Claude Opus 4.6 | Added Alembic migration section to data model | 2026-02-28 |
| R1-S4 | Add circuit breaker for external API calls | Claude Opus 4.6 | Added resilience section with circuit breaker pattern | 2026-02-28 |
```

### 7. Update Coverage

After triage, compute new coverage and insert sections:

```markdown
### Areas Substantially Addressed

(No areas have reached the threshold of 3 accepted suggestions yet.)

### Areas Needing Further Review

- **Architecture**: 1/3 suggestions accepted (need 2 more)
- **Interfaces**: 0/3 suggestions accepted (need 3 more)
- **Data**: 1/3 suggestions accepted (need 2 more)
- **Risks**: 1/3 suggestions accepted (need 2 more)
- **Validation**: 0/3 suggestions accepted (need 3 more)
- **Ops**: 0/3 suggestions accepted (need 3 more)
- **Security**: 1/3 suggestions accepted (need 2 more)
```

### 8. Next Round

The next reviewer (Round R2) will see the applied IDs (R1-S1 through R1-S4), the untriaged suggestions (R1-S5 through R1-S7), and the coverage gaps. They will prioritize areas with the largest gaps (Interfaces, Validation, Ops) and may endorse untriaged suggestions from Round 1.

---

## Convergence Criteria

The review process converges naturally as areas cross the substantially addressed threshold. Each phase has a distinct character:

### Phase Progression

| Phase | Typical Rounds | Coverage State | Reviewer Focus | Suggestion Character |
|-------|---------------|----------------|----------------|---------------------|
| **Early** | R1–R2 | 0–2 areas addressed | Broad scanning across all 7 areas | Foundational: missing sections, unaddressed risks, structural gaps |
| **Middle** | R2–R3 | 3–5 areas addressed | Two-tier priority steering toward remaining gaps | Targeted: filling specific coverage gaps, building on prior accepted work |
| **Late** | R3–R5 | 6–7 areas addressed | Gap-hunting + opportunity discovery | Refined: cross-cutting concerns, low-hanging fruit, high-value extensions |
| **Converged** | R5+ | All areas addressed, diminishing returns | Consider stopping | If fewer than 2–3 novel suggestions emerge, the document has likely converged |

### How to Tell Where You Are

When you receive a document for review, the coverage state tells you which phase the review is in:

- **Empty Appendix A + no prior rounds** — You are the first reviewer (early phase). Cast a wide net.
- **Some applied IDs, some areas still at 0** — Middle phase. Prior reviewers started the work but significant gaps remain. Be targeted.
- **Most or all areas at threshold, with untriaged suggestions pending** — Late phase. Prior reviewers covered the breadth. Your value-add is depth: cross-cutting issues, interactions between accepted suggestions, and opportunities that only become visible once the foundation is laid.
- **All areas addressed, few untriaged suggestions, and prior gap-hunting rounds exist** — The document may be converged. Only generate a round if you find genuinely novel insights. It is acceptable to produce a round with fewer than the maximum suggestion count, or to note that the document appears well-converged.

### Convergence Signals

The review is likely converged when:

1. All 7 areas are substantially addressed (3+ accepted suggestions each)
2. Gap-hunting rounds produce fewer than 2–3 novel suggestions
3. New suggestions are increasingly low-severity (medium/low) rather than high/critical
4. Endorsements outnumber new suggestions (reviewers agree with existing untriaged work rather than finding new issues)
5. The Requirements Coverage table (in dual-document mode) shows Full coverage across all requirement sections

### When Not to Stop

Even if coverage looks complete, continue if:

- Accepted suggestions from different rounds have **interactions that haven't been examined** (e.g., a caching strategy from R1 and a consistency requirement from R3 that may conflict)
- The plan describes infrastructure that **enables valuable extensions** not yet proposed (Lens 1 — low-hanging fruit)
- Rejection rationale in Appendix B reveals **recurring themes** suggesting a deeper architectural issue that individual suggestions have been working around rather than addressing directly

There is no fixed number of rounds required. A typical run uses 2–5 review rounds, but complex documents with many requirements may warrant more.

</details>

---

## Document Under Review: Project Plan

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-import/docs/design/python-contract-codegen/GENERATED_IMPORT_PATH_PLAN.md`  ·  **Size:** 142 lines · 1360 words

```markdown
# Generated Import Path — Implementation Plan

**Version:** 1.0
**Date:** 2026-06-15
**Pairs with:** `GENERATED_IMPORT_PATH_REQUIREMENTS.md` v0.3 (FR-IMP-1/2/3/6 + the §0b refresh)
**Base:** `origin/main` (FR-IMP-4/5 + source-scope FR-IMP-2 already shipped)

## Overview

Build the remaining import-path capabilities in dependency order: the **identity-key consolidation
(FR-IMP-2)** and the **`imports.yaml` grammar (FR-IMP-3)** are the two foundations and can run in
parallel; the **`from_json` owned-kind (FR-IMP-1)** consumes both; the **import surface (FR-IMP-6)**
consumes the manifest. The discipline throughout is the FR-PE emitter's: **declare → generate →
fail-loud gate → human-gated write**. The AI-layer surface (`ai_layer.py`) is actively owned by a
parallel team, so Phase 0 front-loads coordination and every phase re-checks `origin/main`.

## Phase 0 — Coordinate + name the consumer *(blocks nothing technical; gates the rest)*

| Step | Action |
|------|--------|
| 0.1 | `git fetch origin main`; branch `feat/import-path` off **current** `origin/main` in a fresh worktree (pin `PYTHONPATH=<wt>/src` for tests — `reference_multiworktree_env`). |
| 0.2 | **Resolve OQ-IMP-D — name the first consumer** (strtd8 content-import FR-13/15 / navig8 / startd8-generator). Fixes the formats + acceptance entities. |
| 0.3 | Post the **FR-IMP-2 unification proposal** (Phase 1 design below) to the AI-layer owner; agree the seam before touching `ai_layer.py`. |

## Phase 1 — FR-IMP-2: unify the dedup keys into ONE identity key *(foundational; coordinated)*

> Today `AiPass` has `source_binding` (source-scope) **and** `dedup_by` (single-field), each with its
> own persist helper. Collapse to one declared **identity key**, defined once, consumed by the AI
> persist path *and* (Phase 3) the `from_json` path. **Back-compat is the hard constraint.**

| Feature | Target files | Est. LOC | Notes |
|---------|-------------|----------|-------|
| F-101 `IdentityKey` model + resolver | **new** `manifest_extraction/identity.py` (or `backend_codegen/identity.py`) | ~90 | `IdentityKey(kind: id\|field\|composite\|source\|name\|none, fields: tuple, provenance: str\|None)`; `resolve_identity(...)` from manifest + schema. One source of truth. |
| F-102 map `source_binding`/`dedup_by` → `IdentityKey` (back-compat) | `ai_layer.py` (`AiPass`, `parse_ai_passes`) | ~40 | `source_binding` → `source:<field>`; `dedup_by` → `field:<name>`; neither → `name` (today's default). Keys stay accepted; deprecation note only. |
| F-103 single parameterized persist helper | `ai_layer.py` (replace `_persist`/`_persist_source`/`_persist_dedup` shared strings) | ~80 | One emitted `_persist(session, model, edge, *, identity)` dispatching on `IdentityKey.kind`. **Verify byte-identity** of generated harnesses for existing `source_binding`/`dedup_by` passes (the regression gate). |
| F-104 (optional) `identity:` first-class manifest key | `ai_passes.yaml` parse + `imports.yaml` (Phase 2) | ~30 | Lets a pass/import declare `identity:` directly; the legacy keys map onto it. |

**Verify:** existing `source_binding`/`dedup_by` manifests emit **byte-identical** generated code
(diff vs pre-change); new `identity: id|[a,b]|source:f|none` each behave per FR-IMP-2; the
`ai-tests-pass` generated suite stays green. **Dependency:** blocks Phase 3.

## Phase 2 — FR-IMP-3: `imports.yaml` grammar *(paved road; parallel with Phase 1)*

> Clone the FR-PE manifest pattern end-to-end. Lowest-risk phase.

| Feature | Target files | Est. LOC | Notes |
|---------|-------------|----------|-------|
| F-201 `## Imports` extractor | `manifest_extraction/extractors.py` (model on `extract_views`) | ~70 | Table → `imports.yaml`; per-row `not_extracted(reason)`; unknown entity/field fails loud. |
| F-202 `parse_imports` strict parser | `import_codegen.py` (new) | ~60 | The round-trip oracle (like `parse_views`). |
| F-203 wire into the round-trip gate | `manifest_extraction/extract.py` (`extract_manifests` round_trips map) | ~15 | `imports.yaml` round-trips through `parse_imports` before return (`RoundTripError` on failure). |
| F-204 authoring-contract doc | `docs/design/kickoff/KICKOFF_AUTHORING_CONTRACT.md` §2.8 | docs | The `## Imports` grammar table (Entity\|Format\|Identity\|Provenance\|Extract via\|Surface). |

**Verify:** a conforming `## Imports` block → valid `imports.yaml` that round-trips; unknown
entity/field → loud; non-conforming row → one `not_extracted` row. **No dependency** (parallel P1).

## Phase 3 — FR-IMP-1: `from_json` owned-kind *(gated importer; needs P1 + P2)*

| Feature | Target files | Est. LOC | Notes |
|---------|-------------|----------|-------|
| F-301 `render_import` → `app/import.py` | `import_codegen.py` | ~150 | The inverse of `derived.render_export`: `from_json(text) -> ImportResult`, per-entity loader honouring the Phase-1 `IdentityKey`. |
| F-302 import gate (FR-PE-6 model) | `import_codegen.py` | ~60 | Structured `ImportResult(ok, errors, unrenderable, counts)`; a row violating identity / referencing an undeclared field is **reported, not dropped**; `--strict`/`--allow-lossy`. |
| F-303 drift registration | `backend_codegen/drift.py` (`_renderers`) + headers | ~20 | Register `python-import` owned-kind so `generate backend --check` covers `app/import.py`. |
| F-304 generated contract tests | `backend_codegen/test_emitter.py` | ~40 | `from_json(to_json(payload))` round-trips; idempotent re-load under the identity key. |

**Verify:** round-trip fidelity + idempotency; undeclared-field row reported; `--check` drift clean.
**Dependency:** P1 (identity key) + P2 (manifest).

## Phase 4 — FR-IMP-6: import surface *(needs P2)*

| Feature | Target files | Est. LOC | Notes |
|---------|-------------|----------|-------|
| F-401 import route + template | `backend_codegen/htmx_generator.py` (model on `render_ui` form path) | ~90 | When `imports.yaml` declares `surface: true`: a paste textarea + text-file upload → creates the target row; storage independent of extraction. |
| F-402 nav + generated route test | `htmx_generator` + `test_route_smoke_emitter` | ~30 | Route smoke; byte-for-byte stored text round-trip. |

**Verify:** posting pasted text creates one target row whose stored text round-trips; nothing
extracted by the act of importing. **Dependency:** P2.

## Phase 5 — End-to-end on the named consumer

| Step | Action |
|------|--------|
| 5.1 | Author the consumer's `## Imports` block; run `generate backend` (+ the new import owned-kind); `--check` clean. |
| 5.2 | Boot-smoke: import a doc via the surface (P4), restore via `from_json` (P3), and (existing) source-bound extract (FR-IMP-4) — the full FR-13/14/15 loop. |
| 5.3 | Drift `--check` + the generated test suite green; promote per the consumer's flow. |

## Dependencies

```
P0 (coordinate + consumer) ─┬─> P1 (identity consolidation) ─┐
                            └─> P2 (imports.yaml grammar) ────┼─> P3 (from_json gated) ─┐
                                                  P2 ─────────┴─> P4 (import surface) ──┴─> P5 (e2e)
```
P1 ∥ P2 (parallel). P3 needs P1+P2. P4 needs P2.

## Risks & coordination

- **R1 — AI-layer collision (high).** `ai_layer.py` is the parallel team's hot surface; Phase 1
  rewrites its persist helpers. *Mitigation:* Phase 0 proposal + agreement; byte-identity regression
  gate (F-103); land via coordinated PR onto current `origin/main`, not a stale branch.
- **R2 — back-compat regression.** Collapsing two keys risks changing generated output for existing
  passes. *Mitigation:* F-103 byte-identity diff is a hard gate; keep both legacy keys accepted.
- **R3 — consumer drift.** Building FR-IMP-1/6 acceptance without a named consumer risks the wrong
  formats. *Mitigation:* OQ-IMP-D resolved in Phase 0; the grammar (P2) is consumer-agnostic so it can
  proceed regardless.
- **R4 — branch drift / test contamination.** *Mitigation:* fresh worktree off `origin/main`, pin
  `PYTHONPATH`, re-fetch before each phase (`reference_multiworktree_env`).

## Acceptance (whole plan)
1. Existing `source_binding`/`dedup_by` passes: **byte-identical** generated code post-Phase-1.
2. `## Imports` → `imports.yaml` round-trips; loud on unknown entity/field.
3. `from_json(to_json(x))` round-trips + idempotent under the identity key; undeclared-field rows
   reported (not dropped); `--check` drift clean.
4. Import surface stores a pasted doc, round-trips byte-for-byte, extraction-independent.
5. The named consumer's full import→extract→restore loop works end-to-end, $0 generated.

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)
```

---

## Document Under Review: Requirements

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-import/docs/design/python-contract-codegen/GENERATED_IMPORT_PATH_REQUIREMENTS.md`  ·  **Size:** 352 lines · 3996 words

```markdown
# Generated Import Path & Import Templates — Requirements

**Version:** 0.3 (Refresh — un-deferred 2026-06-15; consolidation-aware)
**Date:** 2026-06-07 (v0.2) · 2026-06-15 (v0.3 refresh)
**Status:** ▶ **ACTIVE — scheduled for build.** FR-IMP-4/5 + the source-scope member of FR-IMP-2
already SHIPPED (source-bound extraction, on `origin/main`). The remaining generalization (FR-IMP-1
`from_json` owned-kind, FR-IMP-2 **identity-key consolidation**, FR-IMP-3 `imports.yaml` grammar,
FR-IMP-6 import surface) is un-deferred — real consumer need confirmed (2026-06-15) and the
rule-of-three cost concern collapsed (the FR-PE Prisma emitter paved the grammar→manifest→generate→
gate→promote road). Plan: `GENERATED_IMPORT_PATH_PLAN.md`. See §0b for the refresh insights.
**Format:** SDK-internal requirements (REQ/FR), grounded against shipped `backend_codegen/`
**Companion:** `PYTHON_CONTRACT_CODEGEN_REQUIREMENTS.md` (the path this extends),
`../kickoff/KICKOFF_AUTHORING_CONTRACT.md` (the manifest grammar an import template joins),
`docs/design/IDEAL_TARGET_ARCHITECTURE.md` (canonical target arch)
**First consumer:** strtd8 `docs/kickoff/CONTENT_IMPORT_REQUIREMENTS_v0.2-draft.md` (FR-13/14/15)

> **Objective.** Give the SDK a **generated IMPORT path symmetric to the shipped EXPORT path**
> (`backend_codegen/derived.render_export`), so that **applications built by the framework can
> leverage the deterministic generation framework directly** to build entity-import utilities —
> not hand-author them. Import behavior is **declared, not coded**: an `imports.yaml` manifest
> authored in the **same authoring-contract grammar** that already drives `pages.yaml` /
> `views.yaml` / `ai_passes.yaml` / `human_inputs.yaml`, extracted and round-trip-validated by the
> same `manifest_extraction` machinery, and projected into a generated owned-kind for $0. The one
> in-scope LLM touch (extraction from imported text) **reuses the existing AI-pass harness**, now
> made source-bindable. This sits in **bucket 1 (application) + bucket 3 (integration)** of the
> CLAUDE.md scope separation — it builds the utility that *holds/produces* content, never the real
> content itself.

> **Scope discipline (CLAUDE.md).** Deterministic-first. The **storage + round-trip + library +
> idempotency** half is $0-LLM owned capability (FR-IMP-1/2/3/6) and lands first. The **one**
> non-deterministic item — source-bound extraction (FR-IMP-4/5) — reuses an existing pass and is
> built second. No new content-authoring scope is introduced.

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass read the shipped generators (`backend_codegen/derived.py`,
> `backend_codegen/ai_layer.py`, `manifest_extraction/{grammar,extractors,extract}.py`) and the
> first consumer's draft (strtd8 CONTENT_IMPORT v0.2) to stress-test the naive "just add an import
> generator mirroring export" framing. Five corrections:

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| "Add an import generator symmetric to export" is the whole job. | Export is `render_export` → `to_json` (lossless, sorted) + `to_markdown` only (`derived.py:38–71`); there is no `from_json`. But the *easy* half is the de-serializer. The hard half is the **write policy** (identity/dedup + provenance), which lives in a **different module** — `_persist` (`ai_layer.py:384–404`), hardwired to AI output. | **Split the work.** FR-IMP-1 (round-trip de-serializer, next to export, easy) is decoupled from FR-IMP-2/4/5 (write-policy generalization in the persist/AI layer — the real work). Symmetry with export is necessary but not sufficient. |
| Provenance just needs the field marked human/server-managed in `human_inputs.yaml`. | Omission keeps the AI from *authoring* it, but **nothing STAMPS it**. `_persist` strips every server-managed field (`{"id","ownerId","source","confirmed","createdAt","updatedAt"}`, `ai_layer.py:390`) and never sets a source id. A bare omitted provenance field lands **null**, not provenance-bearing. | **FR-IMP-5 added.** Omission and deterministic *stamping* are **two** requirements, not one. The strtd8 finding ("`_persist` never stamps non-edge fields") is structural, not a config gap. |
| Source-scoped dedup is a one-line `_persist` tweak. | `_persist` dedups **by `name` only** (`ai_layer.py:392–395`) and the text-mode harness signature is `def <pass>(<request_field>: str, session: Session)` (`ai_layer.py:452`) — **no source parameter exists to scope by.** Dedup AND the harness signature must both change, together. | **FR-IMP-2 + FR-IMP-4 are coupled.** Neither alone delivers FR-14-class "idempotent by source"; the value to dedup on doesn't reach the harness today. |
| Import templates are a new bespoke config format. | The SDK already extracts **6 manifests** from controlled grammar with mandatory round-trip validation against each generator's own parser (`manifest_extraction/extract.py:105–132`, fail-loud `RoundTripError`). An import template is just a **7th manifest in the same idiom** — one extractor + one parser + the existing round-trip gate. | **FR-IMP-3 reuses `manifest_extraction` wholesale.** "Import template" = a new authoring-contract §-section (`## Imports`) + `imports.yaml`, **not** a new config subsystem. Zero new parsing machinery. |
| The generated app needs a foreign-format parser. | strtd8 OQ-2 (closed from code): **no** pdf/docx/text-extraction dependency exists or is importable. v1 source formats are **JSON round-trip** + **text (paste / `.txt` / `.md`)** only. | **Format vocabulary bounded** to `{json, text}` for v1. Binary formats (PDF/DOCX) and OCR are deferred to a named future increment **with their dependency cost called out** — never silently assumed. |

**Resolved / updated open questions:**
- **OQ-IMP-A → resolved.** The import owned-kind lives in a **new `import_codegen.py`** module
  (symmetric to `ai_layer.py`), not bolted onto `derived.py` — the write-policy half pulls in the
  persist/edge machinery and would overload the "three small pure emitters" docstring of `derived`.
- **OQ-IMP-B → resolved.** `imports.yaml` is a **standalone manifest** that *cross-references*
  `human_inputs.yaml` (the stamped field) and `ai_passes.yaml` (the bound extractor) by
  entity/field name — it does not absorb them. One concern per manifest (the §5 vocabulary rule).
- **OQ-IMP-C → still open (correctly deferred):** whether `from_json` import should *replace* an
  app's bespoke FR-10-style restore or *complement* it. No SDK code bearing; consumer choice.

## 0b. Refresh Planning Insights (v0.3 — 2026-06-15, the un-deferral pass)

> Between v0.2 (deferred north-star) and v0.3, the world moved: the FR-PE Prisma emitter shipped a
> full grammar→generate→gate→promote loop, a second dedup mechanism (`dedup_by`/F-11) landed next to
> `source_binding`, and real consumer need was confirmed. Six refresh corrections:

| v0.2 Assumption | v0.3 Discovery (current `origin/main`) | Impact |
|-----------------|----------------------------------------|--------|
| FR-IMP-2 is greenfield — replace `_persist`'s name-dedup with one declared key. | **Two** dedup keys now coexist on `AiPass` (`ai_layer.py`): `source_binding` (source-scope, mine) **and** `dedup_by` (single-field, the parallel team's F-11), plus an unrelated `trigger`. | **FR-IMP-2 is a CONSOLIDATION/refactor, not greenfield** — unify both under one declared identity key, **back-compat preserved**, and **coordinate with the AI-layer owner** (the highest-collision surface). |
| FR-IMP-3 (the grammar) is the risky, expensive part. | The Prisma emitter shipped the entire **authoring-contract §-section → `extract_*` extractor → `parse_*` round-trip gate → generate owned-kind → FR-PE-6/7 gate+promote** pattern, plus a generalized `build_entity_graph` and the fail-loud gate discipline (errors/unrenderable/round-trip oracle, `--allow-lossy`). | **FR-IMP-3 cost collapsed — it's a paved road.** `imports.yaml` is a 7th manifest cloning `extract_views`/`parse_views`; the keystone is now the *cheapest* phase, not the riskiest. |
| `from_json` is the easy de-serializer; just write it. | The emitter proved a **safety-gate discipline** is essential for a write path: a round-trip import that drops rows or violates the declared identity should **fail loud**, not silently. | **FR-IMP-1 gains a gate** (idempotency + completeness oracle) mirroring FR-PE-6; symmetric to export is necessary but a *gated* importer is the bar. |
| The identity key is an AI-pass concern (`_persist`). | `from_json` restore (FR-IMP-1) writes **user** rows; the AI pass writes **ai** rows — both need the **same** declared identity key, at **two** call sites. | **FR-IMP-2's identity key is the shared seam** between the AI `_persist*` path and the new `from_json` path — define it once, consume it in both (under-specified in v0.2). |
| Rule-of-three: hold for a 2nd consumer. | Real need confirmed 2026-06-15 (consumer to be named — strtd8 content-import FR-13/15, navig8, or startd8-generator). | **Un-deferred.** Consumer identity is now the load-bearing open question (it fixes formats/entities) → **OQ-IMP-D**. |
| Build it on a branch like any feature. | The repo runs many concurrent worktrees + a parallel team **actively in `ai_layer.py`/`generate contract`** (see memory `reference_multiworktree_env`). | **Coordination is a first-class plan step.** `git fetch` + check `origin/main` before each phase; the FR-IMP-2 phase opens with a heads-up to the AI-layer owner, not a surprise PR. |

**Refresh open-question updates:**
- **OQ-IMP-A → revised.** Module split stands (`import_codegen.py`), but the **identity-key logic** is
  shared with `ai_layer.py` — extract it to a small `identity.py` (or `ai_layer` helper) consumed by
  both, so there is one source of truth (resolves the FR-IMP-2 two-call-site seam).
- **OQ-IMP-D → NEW (load-bearing):** **name the first un-deferred consumer.** strtd8 content-import
  (FR-13/15) drives `{json, text}` + a snippet library; navig8/the generator may need different
  formats/entities. The grammar (FR-IMP-3) is consumer-agnostic, but the *acceptance* (FR-IMP-6
  surface, FR-IMP-1 round-trip target) needs a named consumer. Resolve before Phase 3.

---

## 1. Problem Statement

The deterministic framework projects one `.prisma` contract into ~12 owned kinds, **including a
generated EXPORT** (`derived.render_export` → `app/export.py`: `to_json` round-trip + `to_markdown`).
**It generates no IMPORT.** An application built by the framework that wants to *bring data back in*
— restore its own export, ingest a foreign document as a durable record, or extract structured rows
from imported text — must **hand-author every line of that glue**, outside the deterministic /
drift-tracked / $0 model. The framework can *produce* an entity's data but cannot *take it back*.

Three concrete shipped gaps block the first consumer (strtd8 content-import) and any other:

| Capability | Current State | Gap this doc addresses |
|------------|---------------|------------------------|
| Round-trip restore of the app's own export | `to_json` writes it; **no `from_json` reads it** | **FR-IMP-1** — generated inverse de-serializer |
| Idempotent re-ingest (no duplicate explosion) | `_persist` dedups **by `name` only** (`ai_layer.py:392`); entities without a `name` column never dedup → re-ingest **appends duplicates** | **FR-IMP-2** — declarable identity/idempotency key |
| Declaring *how* an entity is imported | No surface for it; import is whatever an app hand-writes | **FR-IMP-3** — `imports.yaml`, authored in the manifest grammar |
| Extract from a *stored* record with provenance | Text harness is `def <pass>(text, session)` — **no source binding** (`ai_layer.py:452`); can't scope or stamp | **FR-IMP-4** — source-bound AI pass |
| Provenance fields that survive | `_persist` strips all server-managed fields and **never stamps** a source id; edge-schema would otherwise **hand the field to the AI to hallucinate** | **FR-IMP-5** — server-stamped, never-AI-filled provenance |
| An import affordance (paste / upload) in the UI | Only generic CRUD create exists; no paste/text-file intake | **FR-IMP-6** — generated import surface (optional, declared) |

**The core unmet need (project-agnostic):** *let the application reach into its own deterministic
contract to import entities — restore, ingest, and (where declared) extract — with declared
identity and declared provenance, generated for $0 from the same contract the entity was defined by.*

---

## 2. Requirements

> FR-IMP-1…6. Behaviors only; the `imports.yaml` shape is in §5. Each has a `Verify:` line a test
> can assert, per the house format. The deterministic split (CLAUDE.md): **FR-IMP-1/2/3/6 are $0
> owned generation; FR-IMP-4/5 reuse one existing AI pass.**

- **FR-IMP-1 — Generated round-trip import (the inverse of export).** The SDK emits a deterministic
  owned-kind (`app/import.py`, kind `python-import`, drift-tracked, $0) projected from the contract:
  a `from_json(text) -> payload` / loader that ingests the app's own `to_json` export format into
  entity rows, the structural inverse of `render_export`. It honours the entity's declared identity
  key (FR-IMP-2). Touches: `import_codegen.render_import`, `app/import.py`. **It is GATED** (v0.3,
  mirroring the FR-PE-6 emitter discipline): the importer reports a structured result and **fails
  loud** rather than silently — a row that violates the declared identity, a field the contract can't
  accept, or a count that doesn't reconcile is surfaced (not dropped); a `--strict`/`--allow-lossy`
  switch governs partial imports. Verify: for any contract, `from_json(to_json(payload))` reconstructs
  every entity row with field fidelity (sorted-key stable); re-running the load is idempotent under
  the declared identity key (no duplicate rows); a row referencing an undeclared field is reported,
  not silently dropped; the emitted file carries the standard provenance header and passes `--check`
  drift.

- **FR-IMP-2 — Unify the dedup mechanisms into ONE declared identity key (CONSOLIDATION).** *(v0.3:
  no longer greenfield.)* `AiPass` carries **two** overlapping dedup keys today — `source_binding`
  (source-scope) and `dedup_by` (single field, F-11). Consolidate them into **one** declared identity
  key with the full vocabulary: `id` (upsert / restore), a single named field, a composite of named
  fields, a **source scope** (an FR-IMP-5 provenance field), or `none` (append-only). The key is the
  **shared seam** between the AI persist path *and* the FR-IMP-1 `from_json` path — defined once
  (a small `identity` helper), consumed at both call sites. **Back-compat is mandatory:** existing
  `source_binding`/`dedup_by` manifests keep working (mapped onto the unified key), and an entity
  with no declaration still dedups by `name` exactly as before. Touches: `ai_layer` (the persist
  helpers + `AiPass`), `import_codegen`, `imports.yaml`. **Coordination (the highest-collision
  surface):** this lands via a proposal to the AI-layer owner, not a surprise branch (see §0b).
  Verify: `source_binding`/`dedup_by` manifests emit byte-identical generated code post-unification;
  `identity: id` upserts on re-import; `identity: [a, b]` composites; `identity: source:<field>`
  replaces only that source's unconfirmed rows; `identity: none` appends; no-declaration still
  name-dedups.

- **FR-IMP-3 — Import templates declared in the authoring-contract grammar → `imports.yaml`.** A new
  authoring-contract section (`## Imports`, §5) and a `manifest_extraction` extractor emit
  `imports.yaml`, **round-trip-validated against its own `parse_imports` parser** like every other
  manifest (`extract.py:105–132`), with per-value extraction-report rows (`extracted(source:…)` /
  `not_extracted(reason)` / `defaulted(source)`). An import template binds: target entity, source
  format, identity key (FR-IMP-2), provenance source value, and an optional source/extractor binding
  (FR-IMP-4). **(v0.3 — paved road):** this clones the exact pattern the FR-PE Prisma emitter shipped
  — a `## Imports` extractor modeled on `extract_views` (`extractors.py`), a `parse_imports` strict
  parser, and wiring into the `extract_manifests` round-trip gate (`extract.py`) — so it is the
  **cheapest, lowest-risk phase**, not the riskiest. Touches: `KICKOFF_AUTHORING_CONTRACT §2.8`,
  `manifest_extraction/extractors.py` + `extract.py`, `import_codegen.parse_imports`. Verify: a
  conforming `## Imports` block extracts to an `imports.yaml` that round-trips through `parse_imports`;
  an unknown target entity / field reference fails **loudly** (never a silent flag); a non-conforming
  row emits exactly one `not_extracted(reason)` report row.

- **FR-IMP-4 — Source-bound AI pass (context binding) — generalize the text-mode harness.** Extend
  `ai_passes.yaml` + the text-mode harness (`ai_layer._render_pass_text`) so a pass may be **bound
  to a source record**: emit `def <pass>(text, session, source_id=…)` when a binding is declared
  (the current `def <pass>(text, session)` remains the unbound case). The bound harness stamps the
  declared provenance field (FR-IMP-5) and scopes dedup to that source (FR-IMP-2 `source` identity).
  Touches: `ai_layer._render_pass_text`, `ai_passes.yaml` (binding field), `imports.yaml`. Verify:
  a source-bound pass writes ≥1 row whose declared provenance field equals the passed `source_id`
  and `source="ai", confirmed=false`; re-running with the same `source_id` leaves the count of that
  source's **unconfirmed** rows stable and never modifies a **confirmed** row; an unbound pass
  generates byte-identical code to today.

- **FR-IMP-5 — Server-stamped provenance fields (never AI-filled).** A field declared as a
  provenance/source-binding target is (a) **omitted** from the AI edge schema — already supported
  via `human_inputs.yaml` omission (`ai_layer.render_edge_schemas`) — **and** (b) **deterministically
  stamped** by the harness from the binding context, closing the gap that omission alone leaves the
  field null. Provenance fields are server-managed; the AI can neither author nor see them. Touches:
  `ai_layer._persist` (stamp step), `human_inputs.yaml` (omission), `imports.yaml` (binding). Verify:
  the target entity's edge schema omits the provenance field (existing `test_edge_privacy`
  assertion); after a source-bound pass the field is **non-null** and equals the source id; a
  generated test asserts the field is absent from the edge model AND present-and-stamped on the row.

- **FR-IMP-6 — Generated import surface (optional, declared).** When an import template declares a
  surface, the generator emits an import route/screen (paste textarea + file upload for text
  formats) that creates the target entity record(s), reusing the HTMX generator idiom; storage is
  **independent of any extraction step** (importing stores; extracting is a separate user action).
  Touches: `import_codegen`, `htmx_generator`, `imports.yaml` (surface flag). Verify: posting pasted
  text to the generated import route creates one target row whose stored text round-trips
  byte-for-byte and whose label/kind render back unchanged; nothing is extracted by the act of
  importing.

## 3. Non-Requirements (explicit scope fence)

- **Not a generic ETL / CSV column-mapping engine.** v1 source formats are **JSON round-trip** and
  **text (paste / `.txt` / `.md`)** only. CSV / arbitrary-schema mapping is a future format entry,
  not v1.
- **No binary parsing.** No PDF / DOCX / OCR / scanned images — no such dependency exists in the
  target runtime (strtd8 OQ-2). Deferred to a named increment **with its dependency cost stated**.
- **Does not change export.** `render_export` / `to_json` / `to_markdown` stay exactly as-is; import
  is the inverse, added alongside.
- **No content-quality grading or fuzzy/similarity dedup.** Identity keys are **exact-match** only;
  the framework stores and surfaces, the user judges.
- **No auto-confirm of AI-authored rows.** Source-bound extraction output stays `source="ai",
  confirmed=false`; the import path never silently writes to the confirmed value model.
- **Not a foreign-key resolver beyond the declared identity key.** Loose `text` references with no FK
  (the consumer's `subjectId` pattern) are honoured; cross-entity reference *resolution* is out.
- **No new content-authoring scope (bucket 4).** This builds the import *utility*; the imported
  content is the user's / company's, never SDK-generated.

## 4. Open Questions

- **OQ-IMP-1 — Composite identity-key normalization.** For `identity: [a, b]`, are values
  case-normalized / trimmed before comparison, or compared verbatim? (Lean: verbatim in v1; document
  it; a normalization policy is a later refinement.)
- **OQ-IMP-2 — Binding cardinality.** Is FR-IMP-4 source-binding a single `source_id` → single
  declared provenance field, or a general `{context-key → stamped-field}` map? (Lean: single in v1;
  covers the consumer; generalize only on a second consumer's need.)
- **OQ-IMP-3 — `from_json` vs app-level restore (= OQ-IMP-C).** Should the generated `from_json`
  *replace* a project's bespoke FR-10-style round-trip restore, or *complement* it? No SDK code
  bearing; consumer choice. **Open.**
- **OQ-IMP-4 — Surface kind vocabulary.** Does FR-IMP-6's surface reuse a `views.yaml` archetype
  (closed vocabulary) or get its own minimal `import-form` kind? (Lean: minimal own kind — the
  archetype set is deliberately closed; an import form is a distinct shape.)
- **OQ-IMP-5 — Identity `source` scope without a provenance field.** Can an entity declare
  `identity: source` without also declaring an FR-IMP-5 provenance field? (Lean: **no** — fail
  loudly at extraction; `source` identity *requires* the field it scopes by.)

## 5. The `imports.yaml` manifest *(planning-confirmed shape)*

> A 7th manifest, authored as a new authoring-contract section and extracted like the other six.
> It **cross-references** `human_inputs.yaml` (the stamped field) and `ai_passes.yaml` (the bound
> extractor) by name — it does not absorb them (§ vocabulary-ownership rule). Round-trip-validated
> against `parse_imports`; any non-round-tripping emission is a bug, never a flag.

### Authoring grammar — `## Imports` *(new authoring-contract §2.8)*

A table, one row per import template, in the controlled idiom of the sibling sections:

```markdown
## Imports
| Entity | Format | Identity | Provenance | Extract via |
|--------|--------|----------|------------|-------------|
| ImportedDocument | text   | id            |               |              |
| ContentSnippet   | text   | id            | sourceDocumentId |           |
| ProofPoint       | text   | source: sourceDocumentId | sourceDocumentId | extract |
```

- **Entity** — must match a declared contract model (else `not_extracted(unknown-entity)` → loud).
- **Format** — `json` (round-trip) | `text` (paste / `.txt` / `.md`). Closed vocabulary; binary
  flagged `not_extracted(generator-gap: format-deferred)`.
- **Identity** — `id` | `<field>` | `[<f1>, <f2>]` | `source: <field>` | `none`. Drives FR-IMP-2.
- **Provenance** — a field name to **server-stamp** with the source id (FR-IMP-5); must also appear
  in `## Owned fields` (cross-ref to `human_inputs.yaml` for AI-omission). Blank = none.
- **Extract via** — the `ai_passes.yaml` pass name to source-bind (FR-IMP-4). Blank = store only
  (FR-IMP-6), no extraction.

### Emitted `imports.yaml`

```yaml
imports:
  - entity: ImportedDocument
    format: text
    identity: id
    surface: true            # FR-IMP-6, when a surface is declared
  - entity: ProofPoint
    format: text
    identity: { source: sourceDocumentId }
    provenance: sourceDocumentId   # FR-IMP-5 server-stamp; AI-omitted via human_inputs
    extract_via: extract           # FR-IMP-4 source-bind the existing 'extract' pass
```

**Three accompanying manifest cross-edits (planning-confirmed, mirroring the consumer's §5):**
1. `human_inputs.yaml` — every `provenance:` field marked human/server-managed (AI edge omission).
2. `ai_passes.yaml` — the `extract_via` pass gains a source-binding marker (FR-IMP-4).
3. `completeness.yaml` — import-only / library entities the project excludes stay the project's call
   (the SDK does not auto-exclude; it surfaces the field for the author).

## 6. First consumer — StartDate (the requirements-to-SDK map)

> How strtd8 `CONTENT_IMPORT_REQUIREMENTS v0.2` FR-13/14/15 land on these project-agnostic
> capabilities. This is the "see how a project would like these to work" mapping.

| strtd8 need | SDK capability | Notes |
|-------------|----------------|-------|
| FR-13 — import a prior document as a durable record; paste + `.txt`/`.md` | **FR-IMP-6** (surface) + existing CRUD create | $0 cascade today *except* the paste/upload affordance, which FR-IMP-6 generates |
| FR-13 — round-trip stored raw text byte-for-byte | **FR-IMP-1** | round-trip fidelity is the same property as restore |
| FR-14 — extract ProofPoints from a stored doc, stamped with `sourceDocumentId` | **FR-IMP-4 + FR-IMP-5** | the exact "`extract(text, session, source_id=…)` + server-stamp" the consumer asked for |
| FR-14 — re-running is idempotent by source; never touches confirmed rows | **FR-IMP-2** (`identity: source: sourceDocumentId`) | replaces the false "dedup-by-name" path the consumer found broken |
| FR-14 — AI never authors `sourceDocumentId` | **FR-IMP-5** (omit + stamp) | closes the "AI-hallucinated id" gap |
| FR-15 — reusable snippet library (tagged, listed, copyable) | existing $0 CRUD/UI + **FR-IMP-1/6** | library is plain generated CRUD; import path lets snippets be saved *from* a document |

**The deterministic split this produces (CLAUDE.md-aligned):** FR-IMP-1/2/3/6 = **$0 owned
generation**, build first (delivers strtd8 FR-13 + FR-15 + the idempotency the consumer needs);
FR-IMP-4/5 = **one source-bound reuse of an existing AI pass**, build second (delivers strtd8 FR-14).
Exactly the consumer's own Stage-1/Stage-2 sequencing, generalized into SDK capability.

## 7. Implementation sequence *(v0.3 — see `GENERATED_IMPORT_PATH_PLAN.md` for the detailed plan)*

**Already shipped (`origin/main`):** FR-IMP-4 (source-bound pass) + FR-IMP-5 (server-stamp) + the
source-scope member of FR-IMP-2 — the source-bound-extraction work.

**Remaining, phased (foundational first):**
- **Phase 0 — Coordinate** (the AI-layer surface is hot): `git fetch`, confirm `origin/main`, post
  the FR-IMP-2 unification proposal to the AI-layer owner. Name the consumer (OQ-IMP-D).
- **Phase 1 — FR-IMP-2 identity-key consolidation** (foundational): unify `source_binding` + `dedup_by`
  into one declared key in a shared `identity` helper; back-compat byte-identical. Blocks FR-IMP-1.
- **Phase 2 — FR-IMP-3 `imports.yaml` grammar** (paved road, parallelizable with Phase 1): `## Imports`
  extractor + `parse_imports` + round-trip gate, cloning `extract_views`.
- **Phase 3 — FR-IMP-1 `from_json` owned-kind** (gated importer): consumes the Phase-1 key + Phase-2
  manifest; the FR-PE-6-style import gate.
- **Phase 4 — FR-IMP-6 import surface**: `htmx_generator` paste/upload screen when `imports.yaml`
  declares one.
- **Phase 5 — End-to-end** on the named consumer + drift `--check` + boot-smoke.

---

*v0.3 — Refresh / un-deferral (2026-06-15). Un-deferred on confirmed consumer need; the rule-of-three
cost concern collapsed because the FR-PE Prisma emitter paved the grammar→generate→gate→promote road
(FR-IMP-3 is now the cheapest phase). FR-IMP-2 reframed from greenfield to a **consolidation** of two
shipped dedup keys (`source_binding` + `dedup_by`) into one identity key shared by the AI-persist and
`from_json` paths — back-compat mandatory, coordinated with the AI-layer owner. FR-IMP-1 gained a
fail-loud import gate (FR-PE-6 model). New OQ-IMP-D (name the consumer). See §0b + the plan doc.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)
```

---

## Begin

Produce your **suggestions** now and **append them to the source files** via Write/Edit (see **Your Task**, **Deliverables**, and **Scope lock** above). Source file paths are in the **Source documents** table at the top of this prompt.

Checklist before your **final** chat reply:

- [ ] Read each source file's Appendix A/B/C; did not re-propose settled (A) or rejected (B) items, nor near-duplicate untriaged (C).
- [ ] Appended a `#### Review Round R{n}` block under **Appendix C** of each source file in scope (the A/B/C scaffold is generator-created — appended to it, did not recreate it).
- [ ] Round block contains: executive summary (≤10 bullets) + numbered suggestions (**R{n}-S\*** / **R{n}-F\***); optional adversarial subsection; optional Endorsements & Disagreements block.
- [ ] Did not modify existing prose, populated Appendix A/B, or prior rounds in C.
- [ ] Appended `## Requirements Coverage Matrix — R{n}` section to the end of the **plan** file (after your round block).
- [ ] Chat reply is a **short** (1–3 line) write-confirmation listing file paths and suggestion counts — **not** the suggestion content.

**Stop after persisting** — do not triage, do not emit merged documents in chat or in the files, do not modify existing prose, populated Appendix A/B, or prior rounds in Appendix C (the A/B/C scaffold is generator-created — do not add another).
