# Convergent Review Prompt

**Generated:** 2026-06-16 01:08:38 UTC
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
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-derive-contract/docs/design/kickoff/CONCIERGE_DERIVE_CONTRACT_PLAN.md` | 153 lines · 1288 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-derive-contract/docs/design/kickoff/CONCIERGE_DERIVE_CONTRACT_REQUIREMENTS.md` | 205 lines · 1952 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/Users/neilyashinsky/Documents/dev/startd8-derive-contract/docs/design/kickoff/crp-focus-derive-contract.md` | 33 lines · 318 words |

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

# CRP Focus — Concierge `derive-contract`

Weight the review on the four questions the planning pass surfaced (requirements §4 / plan §4).
The deterministic derivation rules and the EntityGraph-reuse decision are already verified against
navig8 — don't re-litigate those; focus on the unresolved design risks.

## Where we need input most

1. **Import safety (OQ-DC-3 / FR-DC-10) — the security question.** Derivation introspects models
   at **runtime**, which *executes the target package's module code* (imports run top-level code,
   and the project's deps must be importable). What's the right containment: subprocess/sandbox
   isolation, an import allowlist, or "only point it at code you trust" documented as the posture
   (it is the team's own models)? Is runtime import even acceptable, or should v1 fall back to a
   constrained static path despite its limits? This is the analogue of the write-path's OQ-7 — get
   the threat model explicit.

2. **Marker shape (OQ-DC-2 / FR-DC-12).** The two non-deterministic derivations (M2M joins,
   pipeline-artifact exclusion) need an opt-in author marker. Options: `Field(json_schema_extra=…)`,
   a `model_config` key, a sidecar YAML, a decorator. Which keeps domain models free of DB concerns,
   survives refactors, and stays discoverable? Is a sidecar (contract-side, not model-side) cleaner
   than annotating the models at all?

3. **Golden-test fidelity / acceptance bar (OQ-DC-1 / FR-DC-12, plan Step 7).** A re-derivation
   won't byte-match the hand-written navig8 contract (flagged M2M, the SequenceConfig Json bag,
   house-field ordering). Is "matches modulo flagged items" a sound acceptance bar, or does it hide
   real divergence? How should the golden test distinguish "correctly flagged ambiguity" from "got
   it wrong"?

4. **Assist-posture integrity under a richer output.** derive-contract emits a *contract* — the
   most load-bearing artifact in the SDK — plus a report for the Architect to ratify. Does anything
   in the design risk the contract being treated as authoritative before ratification (e.g. an
   `--apply` that writes a `schema.prisma` the cascade will immediately consume)? Is the
   ratification gate actually enforceable, or just advisory prose?

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-derive-contract/docs/design/kickoff/CONCIERGE_DERIVE_CONTRACT_PLAN.md`  ·  **Size:** 153 lines · 1288 words

```markdown
# Concierge `derive-contract` — Implementation Plan

**Version:** 0.1 (Draft — post-exploration, pre-CRP)
**Date:** 2026-06-15
**Status:** Draft — for review before implementation
**Requirements:** [`CONCIERGE_DERIVE_CONTRACT_REQUIREMENTS.md`](CONCIERGE_DERIVE_CONTRACT_REQUIREMENTS.md) v0.2

> The planning pass read the emitter/IR (`manifest_extraction/`), the navig8 source models
> (`startd8_work.legal`), and the hand-derived `navig8/prisma/schema.prisma`. Verdict: **most of
> the derivation is deterministic and the emit half + drift primitives are reused as-is**; the
> only net-new code is a Pydantic introspector + the IR mapping, and the only *ambiguous* rules
> (M2M joins, pipeline-artifact exclusion) are resolved by an explicit marker + flag-for-human.

---

## 1. Architecture: three layers, two reused

```
[1 NET-NEW]  PydanticModelIntrospector   models → normalized field/enum/relation facts
[2 NET-NEW]  EntityGraph mapper          facts → manifest_extraction.EntityGraph
[3 REUSE  ]  render_prisma_schema(graph) → schema.prisma            (prisma_emitter, unchanged)
[4 REUSE  ]  parity_against_live(graph, live) → drift               (--check, unchanged)
[  SAFE   ]  apply_write_plan / CLI                                 (Concierge safe-writer, OQ-7)
```

The contract direction is reversed from `generate backend`, but the **back half is identical** —
derive-contract feeds the same `EntityGraph` the markdown path feeds, into the same emitter.

## 2. Steps

### Step 1 — `PydanticModelIntrospector` (net-new, ~200 LOC)
Runtime introspection (OQ-2 resolved: AST alone is insufficient — Pydantic needs `model_fields`
for `is_required`/defaults). Per `BaseModel`:
- `model_fields` → name, annotation, required, default;
- unwrap `Optional[T]`/`List[T]`/`Dict[K,V]` via `typing.get_args`/`get_origin`;
- classify each field: scalar / enum (`issubclass(ann, Enum)`) / nested `BaseModel` / `List[BaseModel]`
  / `List[scalar]` / `Dict` / marked-join;
- detect & **drop** `@computed_field`/`@property` (not stored);
- collect `Enum` classes (values, with hyphen→underscore normalization + a note).
**Constraint (new, FR-DC-10):** importing the models executes module code and needs the project's
deps importable — derive-contract runs in an env where the target package imports cleanly; the
report records the import set. Side-effect risk is documented.

### Step 2 — EntityGraph mapper (net-new, ~300 LOC)
Map introspected facts → `EntityGraph` (entities/fields/enums/fk_parents/joins/uniques). The
deterministic rules (verified against navig8):

| Model-side signal | Contract result | Determinism |
|---|---|---|
| explicit `id: str` field present | `<entity>Key` + `@@unique([parentFk, key])` + synth cuid PK | **deterministic** |
| no `id` field | cuid PK only (root/value object: DecisionTree, Citation) | **deterministic** |
| parent has `List[ChildModel]` | child gets `<parent>Id` FK + parent reverse list (1:N) | **deterministic** |
| field is nested `BaseModel` / `Optional[BaseModel]` | `<model>Id` FK (optional mirrors Optional) | **deterministic** |
| `List[scalar]` / `Dict[...]` / nested dict | `Json?` | **deterministic** |
| `@computed_field` / `@property` | excluded (not a column) | **deterministic** |
| Python `Enum` | Prisma `enum`; hyphenated values → underscore + note | **deterministic** |
| `List[str]` of foreign ids (e.g. `screens`) ↔ reciprocal list | **M2M join model** (navig8 `ScreeningLink`) | **NOT deterministic → marker (Step 4) or flag** |
| house meta-fields absent | add `id/ownerId/source/confirmed/createdAt/updatedAt` per SDK convention | deterministic |

### Step 3 — Emit (reuse, ~0 LOC)
`render_prisma_schema(graph)` unchanged. The contract + the derivation report (every rule applied,
every exclusion, every flagged ambiguity — FR-DC-7/8) are the output.

### Step 4 — Ambiguity resolution: explicit markers + flag-for-human
The two NEEDS-ADAPTER cases (OQ-3 M2M, OQ-5 artifact exclusion) get an **opt-in marker** the model
author can set, with **flag-for-human** as the safe default when unmarked:
- M2M join: a `List[str]`-of-ids field is ambiguous (loose refs vs Json vs join) — unmarked ⇒
  emit `Json?` **and flag** "could be an M2M join — mark to confirm"; a marker (e.g. a
  `model_config`/`Field(json_schema_extra=...)` hint, TBD shape — OQ-DC-2) makes it a join.
- exclusion: which models are storage-bearing is the human's call (IntakePacket isn't even in the
  model set) — derive-contract emits **only the model set the user points it at** (Step 6) and
  auto-excludes computed fields; pipeline-artifact name heuristics (`*Verification`, `*Challenge`,
  `*Sceptic`, `*Arbiter`) are **flagged, not auto-dropped**.

### Step 5 — Drift mode `--check` (reuse, ~50 LOC)
Reuse `parity_against_live(graph, live_text)` + the round-trip gate (production primitives in
`prisma_emitter`). `derive-contract --check`: introspect → map → diff against the live
`schema.prisma`, non-zero exit on drift. **This is the durable value of mechanizing F-5** (catch
model↔contract drift over time), so it is a v1 requirement, not an extra.

### Step 6 — Surfaces (reuse the Concierge pattern)
- `handle_concierge_tool("derive-contract", project_root, models=..., ...)` → preview (the
  proposed contract + report), **never writes** (FR-C3/C3a). Add to the action enum in both MCP
  server files (parity).
- CLI `startd8 concierge derive-contract [ROOT] --models <pkg/paths> [--apply] [--force] [--check]`
  — sole writer (OQ-7), preview-by-default, safe-writer enforces no-clobber/confinement.

### Step 7 — Tests
- Introspector unit tests against the navig8 models (`tree_models`/`register_models`/`models`).
- **Golden test: re-derive navig8's contract** and assert it matches the hand-derived
  `schema.prisma` modulo the flagged-ambiguity items (M2M join + the SequenceConfig Json bag).
- Drift test: mutate a model, assert `--check` reports it.
- Disclosure/no-write: the MCP path writes nothing (FR-C3a conformance, as for the other actions).

## 3. Step → Requirement trace

| Step | Requirements |
|------|--------------|
| 1 Introspector | FR-DC-3, FR-DC-2 ($0), FR-DC-10 (importable-env, new) |
| 2 Mapper | FR-DC-4, FR-DC-5 |
| 3 Emit | FR-DC-4, FR-DC-7 |
| 4 Markers/flag | FR-DC-6, FR-DC-8 |
| 5 Drift | FR-DC-11 (--check, promoted from OQ-7) |
| 6 Surfaces | FR-DC-1, FR-C3/C3a/C14, OQ-7 |
| 7 Tests | all |

## 4. Open Questions (for CRP)

- **OQ-DC-1 — Golden-test fidelity.** How close can a re-derivation get to the hand-written navig8
  contract? The flagged items (M2M `ScreeningLink`, the `SequenceConfig` Json bag, house-field
  ordering) won't match byte-for-byte. Is "matches modulo flagged items" the acceptance bar?
- **OQ-DC-2 — Marker shape.** How does a model author mark an M2M join / an excludable artifact —
  a `Field(json_schema_extra={"prisma": ...})`, a `model_config` key, a sidecar YAML, or a
  decorator? (Wants to avoid polluting domain models with contract concerns.)
- **OQ-DC-3 — Import safety.** Runtime import executes the target's module code. Sandbox? subprocess
  isolation? Or document "only point it at code you trust" (consistent with it being the team's own
  models)? Security-relevant — flag for CRP.
- **OQ-DC-4 — Model-set selection ergonomics.** `--models app.models` (package), a glob, or scan
  for `BaseModel` subclasses under a root? Inheritance/imported-model handling.

---

*Plan 0.1 — post-exploration. Net-new surface is bounded (~550 LOC introspector+mapper); emit +
drift + safe-writer are reused. The only non-deterministic derivations (M2M joins, artifact
exclusion) are handled by opt-in markers + flag-for-human, never silent guesses.*

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-derive-contract/docs/design/kickoff/CONCIERGE_DERIVE_CONTRACT_REQUIREMENTS.md`  ·  **Size:** 205 lines · 1952 words

```markdown
# Concierge `derive-contract` — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-15
**Status:** Draft
**Plan:** [`CONCIERGE_DERIVE_CONTRACT_PLAN.md`](CONCIERGE_DERIVE_CONTRACT_PLAN.md)
**Parent:** [`CONCIERGE_MCP_REQUIREMENTS.md`](CONCIERGE_MCP_REQUIREMENTS.md) v0.4 (FR-C8, the deferred
action this expands); [`CONCIERGE_FRICTION_LOG_NAVIG8.md`](CONCIERGE_FRICTION_LOG_NAVIG8.md) (F-5,
the motivating friction)
**Worked example:** `~/Documents/dev/navig8/prisma/schema.prisma` — derived **by hand** from
`startd8_work.legal` Pydantic models this session; the rules below are reverse-engineered from
that hand-pass.
**Reuse target:** `manifest_extraction/prisma_emitter.render_prisma_schema(graph)` — the emit half.

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass read the emitter/IR, the navig8 source models, and the hand-derived contract.
> It resolved all 8 open questions and corrected ~4 requirements (>30% — the loop working). The
> biggest result is positive: the load-bearing OQ-1 is FEASIBLE, so no new IR is needed.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| Unclear whether `EntityGraph` (built for the markdown path) can represent Pydantic models (OQ-1) | **FEASIBLE — no adapter.** Every field the emitter *reads* has a Pydantic source; doc-specific fields (`heading_path`/`row_index`/`notes`/`human_only`) are simply ignored. | FR-DC-4 firmed: reuse `EntityGraph` + `render_prisma_schema` as-is; no new IR. |
| Introspection mechanism open (OQ-2) | **Runtime import, not static AST** — Pydantic needs `model_fields` for `is_required`/defaults/computed-field detection; AST alone is insufficient. | New **FR-DC-10**: the action imports the target models, so the project's deps must be importable; module-import side effects are documented. |
| "cross-entity trace → join model" listed as a deterministic rule (FR-DC-5) | **NOT deterministic.** A `List[str]` of ids is ambiguous (loose refs vs Json vs M2M join); navig8's `ScreeningLink` needed hand judgment. | FR-DC-5 corrected: M2M joins are **marker-driven + flagged**, not auto-derived. New **FR-DC-12** (marker mechanism). |
| Exclusions framed as "rules" (FR-DC-6) | **Mostly model-selection + auto computed-field filter.** Which entities are storage-bearing is the human's pick (IntakePacket isn't even in the model set); only `@computed_field` is auto-excluded. Pipeline-artifact names are *flagged*, not dropped. | FR-DC-6 reframed; new **FR-DC-13** (model-set selection). |
| `--check` drift mode floated as OQ-7 | **FEASIBLE, reuse `parity_against_live`/`semantic_diff` as-is** (~50 LOC). It is the *durable* value of mechanizing F-5. | Promoted to **FR-DC-11** (a requirement, not an option). |
| id-detection / 1:N / nested-ref / Dict→Json / enum rules (OQ-3/4/5) | **Deterministic**, verified against navig8: explicit `id:str`→`<entity>Key`+`@@unique`; no-id→cuid; parent `List[Child]`→child FK; nested `BaseModel`→FK; `List[scalar]`/`Dict`→`Json`; `Enum`→prisma enum + hyphen-normalize. | FR-DC-5 kept for these; confidence raised. |

**Resolved open questions:**
- **OQ-1 → reuse EntityGraph** (feasible, no adapter). **OQ-2 → runtime import** (FR-DC-10).
  **OQ-3 → deterministic for 1:N/nested-ref; M2M needs a marker** (FR-DC-12). **OQ-4 → deterministic**
  (explicit `id:str` present → key; absent → cuid). **OQ-5 → model-selection + computed-field
  auto-exclude; artifacts flagged** (FR-DC-13). **OQ-6 → model-set selection becomes FR-DC-13.**
  **OQ-7 → promoted to FR-DC-11.** **OQ-8 → v1 is a fuller slice than feared** — deterministic rules
  cover most of navig8; only M2M + artifact-exclusion need markers/flags.
- **New open questions for CRP:** golden-test fidelity (OQ-DC-1), marker shape (OQ-DC-2), import
  safety/sandboxing (OQ-DC-3), model-set selection ergonomics (OQ-DC-4) — see the plan §4.

---

## 1. Problem Statement

The Concierge ships four actions (`survey`/`assess`/`instantiate-kickoff`/`log-friction`).
`derive-contract` is the fifth, deferred (FR-C8) because it is net-new AST work. It exists to
close friction **F-5**: kickoff assumes the `schema.prisma` contract is *authored fresh* as the
front DATA-MODEL bookend, but **brownfield** projects already have stable, validated domain
models (navig8 had attorney-pipeline-validated Pydantic models). For those, the contract must be
*derived from code* — the reverse of `generate backend` (contract → code). Today that derivation
is done by hand (I did navig8's), which is slow and risks the hand-written contract silently
**drifting** from the proven models.

### Gap table

| Component | Current state | Gap |
|-----------|--------------|-----|
| Contract authoring | `generate backend` consumes a `schema.prisma`; assumes it exists | No path *to* a contract from existing models |
| Models→contract | Hand-derived (navig8); rules live only in a human's head + commit msg | Not mechanized; drift risk; not repeatable |
| Emit half | `prisma_emitter.render_prisma_schema(EntityGraph)` exists ($0) | Consumes the *markdown-doc* IR; no Pydantic front-end produces that IR |
| Architect ratification | The contract is the human DATA-MODEL bookend | No artifact enumerating what a derivation *changed/excluded* for review |

---

## 2. Requirements

### Surface & posture

- **FR-DC-1 — Fifth Concierge action, same envelope.** `derive-contract` joins the
  `startd8_concierge` action enum and the `startd8 concierge` CLI. **MCP preview-only** (returns
  the proposed contract + report, never writes — FR-C3/C3a); **CLI is the sole writer** (OQ-7),
  preview-by-default, `--apply`/`--force` via the safe-writer. Assist posture (FR-C2): it
  *proposes*; the **Architect ratifies** — derive-contract never marks the contract authoritative.
- **FR-DC-2 — $0, deterministic, no LLM.** Derivation is AST/introspection + a deterministic
  transform, not generation. No model calls. Same inputs → byte-identical output.

### Input & introspection

- **FR-DC-3 — Input is the project's Pydantic models.** The action takes a target (a module, a
  package, or a declared list of model classes) and introspects the `BaseModel` subclasses into an
  intermediate representation (IR). *(Assumption: Pydantic v2; SQLModel/dataclasses out of v1.)*
- **FR-DC-4 — Produce the emit-half IR.** Introspection yields an `EntityGraph` (the
  `manifest_extraction` IR: entities, fields, enums, fk_parents, joins, uniques) so the existing
  `render_prisma_schema` emits the `.prisma`. *(Assumption to verify: that IR — built for the
  markdown path — can faithfully represent Pydantic-derived models; see OQ-1.)*

### Derivation rules (reverse-engineered from the navig8 hand-pass)

- **FR-DC-5 — The transform rules.** Apply deterministically, each recorded in the report:
  - semantic string id field → `<entity>Key` + `@@unique([parent, key])`, with a synthesized cuid row PK;
  - `Dict`/`List[...]`/nested-object fields with no relation → `Json`;
  - a list/set that encodes a cross-entity trace → an M2M **join model** (navig8 `ScreeningLink`)
    — **but this is not deterministic** (a `List[str]` of ids is ambiguous); it is marker-driven
    (FR-DC-12) and flagged when unmarked (FR-DC-8), never auto-guessed;
  - Python `Enum` → Prisma `enum`; **hyphenated enum *values* → underscore** + a loader-normalization note (hyphens are illegal Prisma identifiers);
  - builtin/reserved-name fields renamed (navig8 `type` → `nodeType`);
  - `@computed_field`/`@property` → **not** stored columns (stay computed);
  - house meta-fields (`id`/`createdAt`/`updatedAt`/…) added per the SDK convention if absent.
- **FR-DC-6 — Exclusions are explicit, not silent.** Entities/fields excluded from the contract
  (no-storage entities, verification/pipeline artifacts, computed fields) are **listed in the
  report with a reason**, never dropped invisibly. *(navig8 excluded `IntakePacket` + the
  verification artifacts by hand.)*

### Output, ratification, integrity

- **FR-DC-7 — Emit contract + derivation report.** Output is (a) the candidate `schema.prisma`
  and (b) a **derivation report** naming every transform applied, every exclusion, and every
  **ambiguity flagged** (FR-DC-8). The report is the Architect's review surface (FR-DC-1).
- **FR-DC-8 — Flag ambiguity, never guess silently.** Where introspection cannot decide
  (is `List[str]` a `Json` column or a relation? which field is the semantic id? is this entity
  storage-bearing?), the action **flags it for the human** with its best guess + the alternatives,
  rather than committing a silent choice.
- **FR-DC-9 — No clobber; validate the result.** Never overwrites an existing `schema.prisma`
  without `--force` (safe-writer). The emitted contract is validated by re-running
  `startd8 wireframe` against it (compose, FR-C10) so a malformed derivation is caught.

### Added by the planning pass

- **FR-DC-10 — Runtime introspection; importable env (OQ-2).** Derivation introspects the models
  **at runtime** (`model_fields` — static AST can't see `is_required`/defaults/computed fields), so
  the action **imports the target package** and requires the project's dependencies importable.
  The report records the imported model set. Module-import side effects are a documented constraint
  (see OQ-DC-3 for the import-safety question).
- **FR-DC-11 — `--check` drift mode (promoted from OQ-7).** Re-derive the IR from the models and
  diff against the live `schema.prisma` via the existing `parity_against_live`/`semantic_diff`
  primitives; non-zero exit on drift. This is the durable value of mechanizing F-5 (catch
  model↔contract drift over time), so it ships in v1.
- **FR-DC-12 — Explicit markers for the non-deterministic derivations.** The two ambiguous cases —
  M2M joins (FR-DC-5) and pipeline-artifact exclusion (FR-DC-6) — are resolved by an **opt-in
  marker** the model author sets (shape TBD — OQ-DC-2), with **flag-for-human** (FR-DC-8) as the
  safe default when unmarked. Markers MUST NOT require polluting domain models with DB concerns
  beyond a minimal hint.
- **FR-DC-13 — Model-set selection (OQ-6).** The user points the action at the entities to include
  (a package/module path or declared list). Exclusion is primarily *non-selection* + automatic
  computed-field filtering (FR-DC-6); the action never silently pulls in or drops entities.

---

## 3. Non-Requirements

- **Not a general ORM/migration tool.** Pydantic v2 in; not SQLAlchemy/Django/SQLModel/dataclasses
  in v1.
- **Not multi-language.** Python only.
- **Not semantic authorship.** It mechanizes the *structural* derivation; the human DATA-MODEL
  bookend (what the contract should *mean*, which entities matter) stays human — derive-contract
  proposes, the Architect decides.
- **Not relation invention.** It only derives relations the models actually express; it does not
  infer foreign keys the models don't encode.
- **Not a `generate backend` replacement.** It produces the *input* to that cascade, once.

## 4. Open Questions

> OQ-1…OQ-8 were **resolved** by the planning pass — see §0. The remaining questions are new ones
> the planning pass surfaced, carried for the CRP / implementation pass:

- **OQ-DC-1 — Golden-test fidelity.** A re-derivation won't byte-match the hand-written navig8
  contract (the flagged M2M `ScreeningLink`, the `SequenceConfig` Json bag, house-field ordering).
  Is "matches modulo flagged-ambiguity items" the right acceptance bar (FR-DC-12)?
- **OQ-DC-2 — Marker shape (FR-DC-12).** How does a model author mark an M2M join / an excludable
  artifact — `Field(json_schema_extra={"prisma": …})`, a `model_config` key, a sidecar YAML, or a
  decorator? Constraint: keep domain models free of DB concerns beyond a minimal hint.
- **OQ-DC-3 — Import safety (FR-DC-10).** Runtime introspection executes the target's module code.
  Subprocess isolation / sandbox, or document "only point it at code you trust" (it is the team's
  own models)? Security-relevant — flag for CRP.
- **OQ-DC-4 — Model-set selection ergonomics (FR-DC-13).** `--models app.models` (package) vs a
  glob vs scan-for-`BaseModel`-subclasses-under-a-root; inheritance/imported-model handling.

---

*v0.2 — Post-planning self-reflective update. OQ-1 resolved FEASIBLE (reuse `EntityGraph` +
`render_prisma_schema`, no new IR — the load-bearing win); 1 rule corrected (M2M joins are
marker-driven, not deterministic — FR-DC-5/FR-DC-12); 3 requirements added (FR-DC-10 runtime
import, FR-DC-11 `--check` drift, FR-DC-13 model-selection); exclusions reframed (FR-DC-6). All 8
original OQs resolved; 4 new implementation-pass OQs seeded. Net-new code bounded (~550 LOC
introspector+mapper); emit + drift + safe-writer reused. The reflective loop earned its keep by
falsifying the "trace → join" determinism claim before any code was written.*

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
