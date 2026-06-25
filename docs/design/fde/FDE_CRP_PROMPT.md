# Convergent Review Prompt

**Generated:** 2026-06-04 17:04:24 UTC
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
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/fde/FORWARD_DEPLOYED_ENGINEER_PLAN.md` | 159 lines · 1125 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/fde/FORWARD_DEPLOYED_ENGINEER_REQUIREMENTS.md` | 424 lines · 4400 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/fde/fde-crp-focus.md` | 43 lines · 398 words |

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

# CRP Focus — Forward Deployed Engineer (FDE)

These docs already passed a reflective-requirements loop (planning pass + open-question
resolution verified against the codebase). The internal loop's blind spot is *external*
architecture/interface/risk. Weight the review toward the following; for each, give a
Summary answer / Rationale / Assumptions / Suggested improvements.

1. **SA↔FDE coupling & dependency direction (FR-17).** FR-17 adds an `fde_explanation` ref to
   the Service Assistant's `TriageReport` and claims one-directional coupling (FDE→SA, no import
   cycle), modeled on SA's local `SemanticReviewRef`. Stress-test: does the FDE reading
   `TriageReport` as a *typed import* (vs reading the JSON artifact) reintroduce a cycle or a
   version-lockstep between the two packages? Is artifact-level coupling the safer Tekizai-Tekisho
   boundary? Who owns the `FdeRef` schema and where does it live?

2. **Keiyaku-contract-shaped, transport-agnostic protocol (FR-12).** There is no A2A transport
   in the SDK today. The protocol is a frozen-dataclass contract whose `.md` files are the
   serialized view. Stress-test: is the markdown↔contract round-trip lossless and versionable?
   How is protocol/schema versioning handled as the contract evolves (the SDK-version stamp vs a
   protocol-version field)? Does "transport-agnostic" hold if EventBus (fire-and-forget, no
   resident consumer) is the only near-term transport?

3. **Deterministic-first vs LLM boundary (FR-15).** Mechanism *facts* are deterministic reads;
   LLM is confined to (a) prose-assumption detection and (b) narrative composition. Stress-test:
   is the boundary actually clean, or does narrative composition (b) risk re-introducing
   unlabeled mechanism claims that violate FR-6? How is the zero-LLM explain path validated/tested?

4. **Two-track preflight ordering (FR-8 / OQ-9).** Track 1 (prose, raw markdown, no signals) vs
   Track 2 (post-`plan-ingestion`, signals → `classify_tier()`). Stress-test: does running
   `plan-ingestion` inside the FDE preflight duplicate or conflict with the operator's own later
   ingestion run? Is Track 2's tier *prediction* sound given signals extracted from freshly-parsed
   (not-yet-real) features? Cost/latency of invoking a full workflow for preflight?

5. **Tekizai-Tekisho source-labeling guarantee (FR-6).** Every load-bearing claim tagged
   OBSERVED(project) vs MECHANISM(sdk). Stress-test: is the guarantee *enforceable* (a test/lint
   that fails on an unlabeled claim), or merely aspirational prose? What stops the LLM narrative
   step from emitting an unlabeled synthesis? How are *preflight predictions* labeled distinctly
   from *explain observations* (FR-16)?

6. **Security & ops (cross-boundary reads).** The FDE reads cross-artifact data
   (`prime-result*.json`, SA triage, project context, `.contextcore.yaml`) and may run LLM calls.
   Stress-test: trust boundary on artifacts the FDE did not produce; surprise-spend controls
   (FR-14 defers auto-launch — is that sufficient?); idempotency key correctness (request
   checksum + SDK version) across SDK upgrades.

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/fde/FORWARD_DEPLOYED_ENGINEER_PLAN.md`  ·  **Size:** 159 lines · 1125 words

```markdown
# Forward Deployed Engineer (FDE) — Implementation Plan

**Version:** 0.2 (Post-reflection — traces v0.2 requirements)
**Date:** 2026-06-04
**Status:** Draft
**Companion:** [`FORWARD_DEPLOYED_ENGINEER_REQUIREMENTS.md`](FORWARD_DEPLOYED_ENGINEER_REQUIREMENTS.md)

> This plan is the output of the reflective loop's planning pass, re-aligned to the corrected
> v0.2 requirements. Every step traces to an FR; every FR traces to a step. Open questions
> that block a step are called out inline.

---

## Architecture at a glance

```
PROJECT (consumer repo, where the FDE is "posted")          SDK (the FDE's home / brain)
┌───────────────────────────────────┐        ┌─────────────────────────────────────────┐
│ .startd8/fde/                      │        │ src/startd8/fde/                          │
│   fde-request.md      (inbound)    │◀──────▶│   models.py     Keiyaku-shaped contracts  │
│   fde-explanation.md  (outbound)   │  .md   │   explain.py    explain mode (FROM ARTIFACT)│
│   fde-preflight.md    (outbound)   │ proto- │   preflight.py  preflight mode (LIVE)     │
│   fde-context.json    (posting)    │  col   │   sources.py    §6 source-of-truth reads  │
│   fde-cursor.json     (idempotency)│        │   compose.py    source-labeled narrative  │
└───────────────────────────────────┘        │   assistant_bridge.py  SA handshake       │
        ▲                                     └─────────────────────────────────────────┘
        │ reads service-assistant-triage.json (EVIDENCE half)   cli_fde.py / scripts/run_fde.py
        │ writes fde_explanation ref back into TriageReport (FR-17)
   Service Assistant (existing) ── deterministic/actionable flags trigger FDE (FR-14)
```

The **brain** is deterministic-first (FR-15): `sources.py` does pure reads/calls; LLM is only
invoked by `preflight.py` (assumption detection) and `compose.py` (narrative).

---

## Step-by-step (FR-traced)

### Phase 1 — Package skeleton + contracts
1. **Create `src/startd8/fde/`** package (FR-1, OQ-1). Mirror `service_assistant/` layout.
2. **`models.py`** — define the Keiyaku-shaped contract pair (FR-12): `FdeRequest`,
   `FdeExplanation`, `FdePreflightReport`, each a frozen dataclass with `.to_dict()` /
   `.from_json()` / `.to_markdown()`. Reuse `RootCause`/`PipelineStage` (NR-6). The `.md`
   serializers (FR-11) are methods here.
3. **`cli_fde.py`** — `fde_app = typer.Typer(name="fde", …)`; commands `explain`, `preflight`,
   `init`. Register with `app.add_typer(fde_app, name="fde")` in `cli.py` (mirror `cli_assist.py`
   at `cli.py:774`). (FR-1)
4. **`scripts/run_fde.py`** — thin shim, `sys.path` inject + always `exit(0)` (mirror
   `scripts/run_service_assistant.py`). (FR-1/FR-13)

### Phase 2 — Source-of-truth reads (deterministic core)
5. **`sources.py`** — one function per §6 row (FR-3/FR-5/FR-15). **OQ-2'/OQ-10 now resolved:**
   - `read_element_data(...)` → **prefer `prime-postmortem-report.json`** (`ElementPostMortem`
     already flattens tier / repair_steps / ast-validity); **fall back** to `prime-result*.json`
     raw nesting `history[].generation_metadata.micro_prime_file_results[].element_results[]`.
   - `classify_live(signals)` → `classify_tier()` (`complexity/classifier.py:58`).
   - `resolve_model_by_tier(provider, tier)` → `get_latest_model` / `Models.*` (`model_catalog.py`);
     `resolve_model_by_role(role)` → `get_models_by_role()` / `ModelCatalogEntry.agent_spec`
     (`contractors/protocols.py:432`).
   - `language_capability(lang_id)` → `LanguageRegistry.get(...)`.
   - Every return carries a `source` tag (`OBSERVED`/`MECHANISM`) for FR-6 labeling.

### Phase 3 — Explain mode (compose with Service Assistant)
6. **`explain.py`** (FR-4/5/6/7/16-explain):
   - Load `service-assistant-triage.json` → `TriageReport` (EVIDENCE half, FR-4).
   - For each `FailureTriage`, read mechanism from `sources.py` (MECHANISM half, FR-5).
   - Detect SA mechanism-misattributions (FR-7) — e.g. `deterministic == True` but SA's
     `re_run_strategy` implies "regenerate"; flag the correction with home-authority.
   - `compose.py` renders `fde-explanation.md` with every claim tagged `OBSERVED (project)` /
     `MECHANISM (sdk)` (FR-6). **Zero-LLM path** when no assumption-detection is needed (FR-15).
7. **`assistant_bridge.py`** (FR-14/FR-17): add optional `fde_explanation` ref to SA's
   `TriageReport` (path + checksum), mirroring `semantic_review: SemanticReviewRef`. Trigger =
   `FailureTriage.deterministic` / mechanism-dependent recommendation. **No auto-launch** (v1).

### Phase 4 — Preflight mode (landmine review)
8. **`preflight.py`** — two tracks (FR-8/9/10/16-preflight; OQ-9 resolved):
   - **Track 1 (pre-ingestion, no signals):** LLM reads raw plan/requirements markdown and flags
     prose assertions about SDK behavior; cross-check each against `language_capability()` /
     known mechanism facts. No `classify_tier()` needed. Cheap, runs first.
   - **Track 2 (post-ingestion, signals required):** `WorkflowRegistry.run_workflow(
     "plan-ingestion", …)` → features → `extract_signals_from_feature()` → `classify_live()`;
     flag divergence between the plan's stated expectation and the predicted tier/route. Reuse
     `run_semantic_compliance(...)` / `convergent-review` for generic quality alongside.
   - Each landmine names its track + the §6 source that adjudicates it; tier claims labeled
     *prediction*, not observation (FR-16). Render `fde-preflight.md` into `.startd8/fde/`.

### Phase 5 — Posting + idempotency
9. **`fde-context.json` + optional `init`** (FR-2, OQ-6 resolved): **auto-create** `.startd8/fde/`
   on first invocation (no mandatory init); provide optional `startd8 fde init` for explicit
   setup/re-stamp. Stamp project id + SDK version (`startd8.__version__`), refresh each run.
   **Placement:** project-scoped files (`fde-context.json`, `fde-cursor.json`, `fde-request.md`,
   `fde-preflight.md`) under `.startd8/fde/`; run-scoped `fde-explanation.md` into the run output
   dir beside `service-assistant-triage.json`.
10. **`fde-cursor.json`** (FR-13): idempotency keyed by (request-artifact checksum + SDK
    version), mirroring SA's `service-assistant-cursor.json` (`detector.py:206-249`).

### Phase 6 — Tests
11. Unit tests per FR; a coverage test that every §6 mechanism question has a `sources.py`
    reader (analogue of SA's `CAUSE_TO_OPERATIONAL_ACTION` coverage test). Logger-policy
    allowlist update for new files (CLAUDE.md "Must Avoid").

---

## Reuse map (FR-9, confirmed library surfaces)

| Need | Call | Returns |
|------|------|---------|
| Parse prose plan → features | `WorkflowRegistry.run_workflow("plan-ingestion", cfg)` | `WorkflowResult` (features, context-seed) |
| Requirements+plan review | `WorkflowRegistry.run_workflow("convergent-review", cfg)` | `WorkflowResult` |
| Semantic compliance | `run_semantic_compliance(output_dir, …)` | `SemanticComplianceReport` |
| Post-ingestion domain checks | `WorkflowRegistry.run_workflow("domain-preflight", cfg)` | `WorkflowResult` (needs context-seed) |

## Blocking open questions (resolve before the dependent step)
- ~~**OQ-2'** → Step 5~~ **RESOLVED.** Source = `prime-result*.json`
  (`scripts/run_prime_workflow.py:838`), preferred flattened surface = `prime-postmortem-report.json`.
- ~~**OQ-10** → Step 5~~ **RESOLVED.** Two complementary catalogs (tier: `model_catalog.py`;
  role: `contractors/protocols.py:432`); no discrepancy.
- ~~SA↔FDE coupling~~ **RESOLVED.** One-directional (FDE→SA), no import cycle; SA owns a local
  `FdeRef` (FR-17).
- ~~**OQ-9** → Step 8~~ **RESOLVED.** Two-track preflight: Track 1 (prose, raw markdown, no
  signals) + Track 2 (post-`plan-ingestion`, signals → `classify_tier()`).
- ~~**OQ-6** → Step 9~~ **RESOLVED.** Auto-create (optional `fde init`); scope-split footprint
  (`.startd8/fde/` project-scoped; `fde-explanation.md` run-scoped beside the SA triage).

**All open questions resolved.** Ready for Convergent Review, then implementation.

---

*v0.2 — traces requirements v0.2. Steps are ordered by dependency; the deterministic core
(Phase 2) is the spine, explain (Phase 3) ships before preflight (Phase 4) since it has fewer
open questions.*

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/fde/FORWARD_DEPLOYED_ENGINEER_REQUIREMENTS.md`  ·  **Size:** 424 lines · 4400 words

```markdown
# Forward Deployed Engineer (FDE) Requirements

**Version:** 0.2.2 (All open questions resolved — pre-CRP)
**Date:** 2026-06-04
**Status:** Draft
**Owner:** neil-the-nowledgeable

---

## Locked design decisions (pre-draft)

These were decided before drafting and frame every requirement below:

1. **Form — Hybrid.** The FDE's *brain* (mechanism-authority logic) is a first-class SDK
   component (a class + `startd8 fde` CLI surface). Its *posting* (project-local context
   bundle + the `fde-*.md` communication protocol) lives in the project under
   `.startd8/fde/`. The SDK side is versioned/testable/home-authoritative; the project side
   is the deployed footprint the Service Assistant writes to and the FDE answers in.
2. **Authority role — SDK mechanism authority.** Per
   [Tekizai-Tekisho](../../design-princples/TEKIZAI_TEKISHO_DESIGN_PRINCIPLE.md), the FDE
   supplies the **MECHANISM** half of a cross-boundary composition (how the SDK actually
   decides). The **Service Assistant** supplies the project **EVIDENCE** half (what happened
   on disk). FDE output is a *composed* report, never a solo cross-boundary verdict.
3. **Preflight — reuse + SDK-mechanism lens.** Landmine-spotting in plans/requirements builds
   on existing review machinery (`domain-preflight` workflow, plan-ingestion, the semantic
   compliance reviewer, CRP). The FDE adds only its unique lens: *"does this plan/requirement
   assume SDK behavior that isn't how the SDK actually decides?"*
4. **Sync roadmap — A2A typed contract (Keiyaku).** v1 communication is `fde-*.md` files. The
   eventual synchronous channel is an A2A typed contract. The `.md` protocol is designed as
   the serialized form of whatever the A2A contract will later carry.

---

## 0. Planning Insights (Self-Reflective Update)

> This section documents what changed between v0.1 (pre-planning) and v0.2 (post-planning).
> The planning pass mapped each requirement to real SDK seams (three parallel codebase
> sweeps) and revealed **6 material corrections** — enough to confirm the v0.1 draft carried
> the usual share of wrong assumptions, which is the loop working as intended. The single
> most important discovery is itself a Tekizai-Tekisho lesson: **the draft named the wrong
> source-of-truth artifact for "did micro-prime run," and verifying the real one is a
> home-authority step the requirements must not skip.**

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| FR-5: the FDE reads `prime-result*.json` as the authoritative source for micro-prime/tier/repair mechanism. | **No file in `src/` writes `prime-result*.json`** — only Service Assistant (`detector.py`/`triage.py`) and `cli_assist.py` *read* it; it's produced upstream (workflow runner / out-of-repo wrapper). The fields the FDE actually needs (`generation_strategy`, `tier`, `repair_steps_applied`, `repair_attribution`) live on the serialized **`ElementResult`** inside `FileResult.element_results[]` (`micro_prime/models.py:214-440`), consumed by `prime_postmortem.py:1776`. | **FR-5 rewritten.** The authoritative fields are `ElementResult.*`, not a loosely-named JSON. *Which on-disk file* serializes them is **not confirmable from `src/` alone** → new residual **OQ-2'** (a home-verification step — exactly the move the principle prescribes, refusing to assert a "reachable" artifact as truth). |
| OQ-3: unclear whether the FDE computes mechanism live or reads it from an artifact. | **It's both, split by function.** Tier decisions are **never persisted** (only OTel metrics + logs; `classify_tier()` → `ClassificationResult`, `complexity/classifier.py:58`) → must be recomputed live, *or* read back as `ElementResult.tier` if the element already ran. Micro-prime strategy + repair steps **are fully recorded** on `ElementResult`. | **New FR-16.** Two explicit read modes: **explain** (FROM ARTIFACT — `ElementResult` of a completed run) vs **preflight** (LIVE — `classify_tier`/`LanguageRegistry`/`model_catalog` over hypothetical tasks). OQ-3 resolved. |
| OQ-8 / FR-3: the FDE's mechanism reasoning is implicitly LLM-backed. | Almost every mechanism fact is a **deterministic read or call** (`ElementResult` fields, `classify_tier`, `LanguageRegistry.get()`, `get_latest_model`). LLM is only needed to (a) detect assumptions in prose plans and (b) compose readable narrative. | **New FR-15 (deterministic-first).** Mechanism *facts* are deterministic; LLM is confined to prose parsing + narrative. Controls surprise-spend (cf. semantic-compliance reviewer's deferred auto-launch). OQ-8 resolved. |
| FR-9: the FDE layers on `domain-preflight` for raw plan/requirements review. | `domain-preflight` is **deterministic and consumes a post-ingestion `artisan-context-seed.json`**, not a raw plan/requirements `.md` (`workflows/builtin/domain_preflight_workflow.py`). The front-door for raw markdown is **`plan-ingestion`** (parses prose → features) and **`convergent-review`** (an *in-SDK* `ConvergentReviewWorkflow`, distinct from the external `/new-cnvrg-rvw-prmpt` skill). All are callable as a **library** via `WorkflowRegistry.run_workflow(...)` and `run_semantic_compliance(...)`. | **FR-9 corrected + sharpened.** Reuse is **function-call composition**, not CLI orchestration. Front-door = `plan-ingestion` + `convergent-review`; `domain-preflight` is reusable only *after* ingestion yields a context-seed. |
| FR-12 / sync-target: advance the protocol toward an **A2A typed contract**. | **There is no A2A transport in the SDK** — `docs/design/a2a/` is empty; the only A2A references are lazy imports to an external `contextcore.contracts.a2a` with `Any` fallbacks. The established in-SDK pattern for typed boundaries is **Keiyaku contracts** (K-6…K-10): frozen dataclasses with `.to_dict()`/`.from_json()`/`.to_prompt_section()` (`micro_prime/models.py`, `complexity/models.py`). | **FR-12 reframed.** "A2A-ready" → "**Keiyaku-contract-shaped and transport-agnostic**": define the FDE request/response as a frozen-dataclass contract pair now; the `.md` is its serialized view; it rides a synchronous transport (EventBus, or a contextcore A2A layer) **if/when one exists**. A2A is a roadmap *dependency the SDK does not yet have*, not a wiring target. |
| FR-14: the SA "hands off" to the FDE via an `fde-request.md`. | SA's `TriageReport` already carries an **optional folded-report reference** (`semantic_review: SemanticReviewRef`, `service_assistant/models.py`) — a proven precedent for referencing another component's report. SA's per-failure `FailureTriage.deterministic` / `.actionable` flags are the exact trigger signal for "this needs mechanism authority." | **FR-14 made concrete + new FR-17.** SA references the FDE report via a new optional `fde_explanation` ref field on `TriageReport` (mirroring `semantic_review`); the trigger is `FailureTriage.deterministic == True` or a recommendation that rests on a mechanism assumption. Auto-launch stays **deferred** (surprise-spend), matching the semantic-compliance reviewer. |

**Resolved open questions:**
- **OQ-1 → Separate package `src/startd8/fde/`** mirroring `service_assistant/`, with a `cli_fde.py` Typer sub-app registered via `app.add_typer(fde_app, name="fde")` (`cli.py:774` shows the `assist` pattern) and a thin `scripts/run_fde.py` shim that always exits 0. Different authority role ⇒ different home ⇒ separate package.
- **OQ-2 → Mechanism-source map pinned** to concrete symbols (see FR-5 / the new §6 source-of-truth table): tier=`classify_tier`/`ElementResult.tier`, strategy=`ElementResult.generation_strategy`, repair=`ElementResult.repair_steps_applied`+`repair_attribution`, model=`get_latest_model`/`Models`, language caps=`LanguageRegistry.get()`. **OQ-2' (residual):** confirm *which on-disk file* serializes `FileResult.element_results[]` — a home-verification step, deliberately left unasserted.
- **OQ-3 → Both, split by function** (FR-16): explain reads artifacts, preflight computes live.
- **OQ-4 → Library composition** via `WorkflowRegistry.run_workflow(...)` / `run_semantic_compliance(...)`; not CLI orchestration (FR-9).
- **OQ-5 → No A2A transport exists.** Follow the Keiyaku contract pattern; transport is a roadmap dependency (FR-12).
- **OQ-7 → Both operator and SA can invoke**, but SA **auto-launch is deferred** (FR-14/FR-17); v1 ships the file handoff + the trigger condition, not unconditional auto-spend.
- **OQ-8 → Deterministic-first** (FR-15); LLM confined to prose-plan parsing + narrative composition.

---

## 1. Problem Statement

A project built **with** the startd8 SDK is a consumer that sits *on top of* SDK mechanism
it cannot see. When something goes wrong — a Prime Contractor run fails, a generated file is
truncated, a tier route surprises the operator — the project's own agent is forced to infer
*why* from the artifacts in its own reach. As [Tekizai-Tekisho](../../design-princples/TEKIZAI_TEKISHO_DESIGN_PRINCIPLE.md)
documents (the 2026-06-03 micro-prime incident), this produces **plausible-but-wrong causal
stories**: real project evidence stitched to a misunderstood SDK mechanism, read as
authoritative, and propagated.

The **Service Assistant** (`src/startd8/service_assistant/`) already closes half of this gap:
it detects completed cap-dev-pipe runs and post-mortems from the project filesystem and
writes a triage artifact recommending an operator action. But the Service Assistant is
deliberately **Rabbit-weight** — it relays project *evidence* and maps causes to operational
actions; it does **not** carry SDK-mechanism authority. Its recommendations are sourced from
on-disk proxies in the project's reach, which is exactly the side of the composition the
principle warns is unreliable when it tries to narrate framework internals.

There is **no component whose authoritative home is the SDK that is deployed into the project
to answer "why, per the SDK's real mechanism?"** — and no component that reviews the project's
plans/requirements for assumptions about SDK behavior *before* a run burns cost reproducing a
predictable failure.

The **Forward Deployed Engineer** is that component. It is the SDK's insider, posted to the
project: it reads the SDK's own source-of-truth artifacts and mechanism, composes that with
the Service Assistant's project evidence, and (a) explains failures with home-authority and
(b) flags SDK-mechanism landmines in plans/requirements before implementation.

### Gap table

| Concern | Current State | Gap the FDE fills |
|---------|--------------|-------------------|
| Failure *evidence* (what happened on disk) | Service Assistant detects + triages | Covered (SA) — FDE consumes it as the EVIDENCE half |
| Failure *mechanism* (why, per SDK control flow) | Inferred by the project agent from reachable proxies | No SDK-home authority deployed downstream → FDE supplies MECHANISM half |
| Pre-run plan/requirements review | `domain-preflight`, plan-ingestion, semantic-compliance, CRP | None checks *SDK-mechanism assumptions* in the plan |
| Source-of-truth artifact knowledge | Only the SDK home knows which artifact is authoritative (`prime-result*.json` vs `generation_cache`) | FDE encodes that knowledge as code, not prose |
| Composed, source-labeled reporting | SA report is project-sourced only | FDE tags each claim OBSERVED(project) vs MECHANISM(sdk) |
| Project↔SDK communication | SA writes triage `.json`/`.md`; EventBus fire-and-forget | FDE establishes a durable `fde-*.md` protocol, A2A-ready |

---

## 2. Goals & Non-Goals (summary)

**Goal.** A hybrid FDE that is *deployed to a project* and, drawing its mechanism authority
from the SDK, (a) **explains failures** by composing Service Assistant project-evidence with
SDK-mechanism truth into a source-labeled report, and (b) **spots SDK-mechanism landmines** in
the project's plans and requirements *before* implementation — communicating via a durable
`fde-*.md` protocol designed to graduate to an A2A typed contract.

**Not a goal (v1).** Auto-remediation or executing fixes; replacing the Service Assistant's
detection/triage; a long-running daemon; a synchronous transport (v1 is `.md` files);
re-implementing existing review machinery.

---

## 3. Requirements

### A. Deployment & identity (hybrid form)

- **FR-1 — SDK-resident brain.** The FDE's mechanism logic SHALL live in the SDK as a
  first-class component (a class plus a `startd8 fde` CLI sub-app, mirroring `startd8 assist`),
  versioned and tested with the SDK. *Assumption: the CLI uses the same Typer `add_typer`
  pattern as `assist`/`manifest`.*

- **FR-2 — Project-deployed posting (scope-split footprint).** The FDE SHALL maintain a
  project-local footprint, established **automatically on first invocation** (optional
  `startd8 fde init` for explicit setup), split by scope (per OQ-6): **project-scoped** under
  **`.startd8/fde/`** — the context bundle `fde-context.json` (project id, contract/plan ref,
  SDK version from `startd8.__version__`), the idempotency `fde-cursor.json`, the inbound
  `fde-request.md`, and `fde-preflight.md`; **run-scoped** — `fde-explanation.md` written into
  the *run output dir* alongside `service-assistant-triage.json` (so FR-17's ref is a local
  sibling). "Deployed" means this footprint is established in the project, and the FDE operates
  with the project as its working context.

- **FR-3 — Mechanism authority is code, not prose.** Every MECHANISM claim the FDE makes SHALL
  be derived from reading an SDK source-of-truth artifact or calling SDK code at invocation
  time (the complexity classifier, the model catalog, the serialized `ElementResult`, the
  language registry — see the §6 source-of-truth table), NOT from a static knowledge-bundle
  string that can drift. *This is the direct answer to the principle's "trust the home's
  source-of-truth artifact" — the FDE encodes which symbol/artifact is authoritative for each
  question.* *(Resolved: two complementary catalogs — `get_latest_model(provider,
  tier)`/`Models.*` (`model_catalog.py`) for tier defaults, and `ModelCatalogEntry.agent_spec`/
  `get_models_by_role()` (`contractors/protocols.py:432`) for contractor roles. See OQ-10.)*

### B. Failure explanation (compose with Service Assistant)

- **FR-4 — Consume Service Assistant evidence.** The FDE SHALL read the Service Assistant's
  triage artifact (`service-assistant-triage.json`) as the **EVIDENCE half** of the
  composition — detection results, observed verdict, the project's on-disk reality. It SHALL
  NOT re-derive that evidence.

- **FR-5 — Supply SDK-mechanism authority (concrete sources).** For each failure in the SA
  triage, the FDE SHALL answer the *mechanism* question — *why did the SDK behave this way?* —
  by reading the SDK's authoritative symbols/artifacts, **not** a loosely-named JSON. Per the
  planning sweep the concrete sources are: **which tier ran and why** → `ElementResult.tier`
  (recorded) with the rationale recomputable via `classify_tier()` → `ClassificationResult.
  reason` (`complexity/classifier.py:58`); **whether micro-prime ran / which path** →
  `ElementResult.generation_strategy` (`micro_prime/models.py:246`); **which repair steps
  fired** → `ElementResult.repair_steps_applied` + `repair_attribution`; **the default model**
  → `get_latest_model(provider, tier)` / `Models.*`. This is the **MECHANISM half**. *(Resolved
  (OQ-2'): the element data is serialized in `prime-result*.json` under
  `history[].generation_metadata.micro_prime_file_results[].element_results[]`, and
  already-flattened/classified in `prime-postmortem-report.json` as `ElementPostMortem` — the
  FDE prefers the post-mortem surface for *explain* mode, falling back to the raw nesting.)*

- **FR-6 — Composed, source-labeled report.** The FDE SHALL emit `fde-explanation.md` that
  presents a composed causal story, with **every load-bearing claim tagged** `OBSERVED
  (project)` or `MECHANISM (sdk)`, per the principle's labeling rule. It SHALL NOT present a
  solo cross-boundary verdict (no unlabeled "why" claims).

- **FR-7 — Correct, not just relay.** Where the Service Assistant's operational recommendation
  rests on a mechanism assumption that is wrong (the SA is project-sourced and may misattribute
  mechanism), the FDE SHALL flag the correction with its home-authority — e.g. SA says
  "regenerate next pass" but the FDE knows the failure was on the `$0` deterministic path
  (cf. SA FR-14) so a plain re-run is idempotent-futile.

### C. Plan / requirements landmine review (pre-implementation)

- **FR-8 — SDK-mechanism-assumption lens (two tracks).** Given a project plan and/or
  requirements doc, the FDE SHALL review it for **assumptions about SDK behavior that contradict
  how the SDK actually decides**, across two tracks (per OQ-9):
  - **Track 1 — prose-assumption landmines (pre-ingestion, no signals):** detect assertions in
    the raw text about SDK behavior — "assumes micro-prime is off," "assumes a repair step exists
    for language X," "assumes tier T uses an LLM." LLM-driven (FR-15(a)); runs on raw markdown.
  - **Track 2 — mechanism-prediction landmines (post-ingestion, signals required):** after
    reusing `plan-ingestion` to produce features, extract `TaskComplexitySignals` and call
    `classify_tier()` live, flagging where the plan's stated expectation diverges from the
    predicted tier/route. Requires ingestion (prose cannot supply blast_radius/mro_depth/etc.).

  Output: `fde-preflight.md` listing each landmine with severity, its track, and the
  authoritative mechanism (§6 source) it contradicts.

- **FR-9 — Reuse existing review machinery (library composition).** The FDE SHALL build on,
  not replace, existing review components, layering on only the SDK-mechanism lens (FR-8);
  generic plan/requirements quality stays with those components. **Confirmed surfaces
  (planning):** all are callable as a *library*, not just CLI —
  `WorkflowRegistry.run_workflow("plan-ingestion", …)` (parses raw prose → features),
  `WorkflowRegistry.run_workflow("convergent-review", …)` (the *in-SDK* `ConvergentReviewWorkflow`
  over a requirements+plan pair — distinct from the external `/new-cnvrg-rvw-prmpt` skill), and
  `run_semantic_compliance(output_dir, …)`. **Correction:** the `domain-preflight` workflow
  consumes a *post-ingestion* `artisan-context-seed.json`, **not** a raw plan/requirements
  `.md` — so for raw-markdown landmine review the front-door is `plan-ingestion` +
  `convergent-review`, and `domain-preflight` is reusable only *downstream* of ingestion. The
  FDE SHALL compose via function calls, not CLI orchestration.

- **FR-10 — Landmine taxonomy is mechanism-grounded.** Each landmine class SHALL name the SDK
  source-of-truth that adjudicates it (router source, catalog entry, language profile
  capability table), so a flagged landmine carries home-authority, not FDE opinion.

### D. Communication protocol

- **FR-11 — `.md` file protocol (v1).** Project↔FDE communication SHALL be via a defined set of
  markdown artifacts in `.startd8/fde/`: an inbound request (`fde-request.md` — "explain this
  failure" / "review this plan") and outbound responses (`fde-explanation.md`,
  `fde-preflight.md`). The protocol SHALL define the required sections of each.

- **FR-12 — Keiyaku-contract-shaped, transport-agnostic protocol.** The FDE request/response
  SHALL be defined as a **Keiyaku-style typed contract** — a frozen dataclass pair with
  `.to_dict()` / `.from_json()` (and optionally `.to_prompt_section()`), matching the K-6…K-10
  pattern in `micro_prime/models.py` / `complexity/models.py`. The `fde-*.md` files (FR-11) are
  the **serialized view** of that contract. **Correction (planning):** there is **no A2A
  transport in the SDK today** (`docs/design/a2a/` is empty; A2A refs are lazy imports to an
  external `contextcore.contracts.a2a` with `Any` fallbacks). Therefore the synchronous channel
  is a **roadmap dependency, not a v1 wiring target**: when a transport materializes (EventBus,
  or a contextcore A2A layer), the *same* typed contract rides it unchanged. The contract is the
  durable interface; the transport is swappable.

- **FR-13 — Idempotent, one-shot.** Like the Service Assistant, the FDE SHALL be a one-shot
  invocation (no daemon) that is idempotent per (request artifact + SDK version), so
  re-invocation on an unchanged request does not redo work.

### E. Service Assistant handshake

- **FR-14 — SA triggers FDE on mechanism-relevant failures (concrete handshake).** When the
  Service Assistant produces a triage whose per-failure `FailureTriage.deterministic == True`
  (or whose recommendation rests on a mechanism assumption), the FDE SHALL be invocable to
  deepen that triage with home-authority. **Trigger signal (confirmed):** SA's existing
  `FailureTriage.deterministic` / `.actionable` flags (`service_assistant/models.py:80-93`).
  **v1:** SA emits an `fde-request.md` (file handoff); the FDE answers with `fde-explanation.md`.
  **Auto-launch is DEFERRED** — like the semantic-compliance reviewer, SA does not auto-spend
  on the FDE in v1; v1 ships the handoff artifact + the trigger condition, and operator/agent
  pulls the trigger. *v-next: the Keiyaku contract (FR-12) rides a synchronous transport.*

### F. Execution model (added in planning)

- **FR-15 — Deterministic-first mechanism core.** The FDE's mechanism *facts* SHALL come from
  deterministic reads/calls (the §6 sources), NOT an LLM. LLM use SHALL be confined to two
  bounded jobs: (a) detecting SDK-behavior *assumptions* in prose plans/requirements (FR-8),
  and (b) composing the human-readable narrative of the source-labeled report (FR-6). A failure
  explanation that requires *no* assumption-detection SHALL be producible with **zero LLM
  calls**. *This keeps mechanism authority deterministic-and-verifiable and caps surprise-spend.*

- **FR-16 — Two read modes (artifact vs live).** The FDE SHALL operate in two explicit modes:
  - **explain** (post-failure): read mechanism **FROM ARTIFACT** — the serialized `ElementResult`
    fields of a *completed* run (strategy, repair steps, recorded tier). No recomputation.
  - **preflight** (pre-implementation): compute mechanism **LIVE** — `classify_tier()` over
    extracted signals, `LanguageRegistry.get()` for capability, `get_latest_model()` for the
    model that *would* run — because the task has not run and nothing is recorded yet.

  The mode determines the source; a tier claim in *explain* cites `ElementResult.tier`, the same
  claim in *preflight* cites a live `classify_tier()` result (and is labeled a *prediction*,
  not an observation).

- **FR-17 — FDE report referenced from the SA triage (decoupled, no import cycle).** Mirroring
  SA's existing `semantic_review: SemanticReviewRef` folded-report pattern
  (`service_assistant/models.py:126,159`), the SA `TriageReport` SHALL gain an optional
  `fde_explanation` reference field pointing at the FDE's `fde-explanation.md` (path + checksum).
  **Coupling direction (verified):** `SemanticReviewRef` is an **SA-local, lightweight dataclass**
  — `service_assistant/models.py` imports **no** producer package. The FDE ref SHALL follow the
  same rule: SA owns a local `FdeRef` (path + checksum only) and does **not** import the `fde`
  package; the FDE depends on SA (reads `service-assistant-triage.json` as an artifact, or
  imports `TriageReport` for a typed read) but SA never depends on the FDE. **One-directional,
  no import cycle.** The FDE writes the report; SA (or the operator) attaches the ref.

---

## 4. Non-Requirements

- **NR-1.** No auto-remediation or fix execution — the FDE explains and flags; it does not act.
- **NR-2.** No daemon / inotify watcher — one-shot invocation like the Service Assistant.
- **NR-3.** Does not replace the Service Assistant's detection or triage — it composes on top.
- **NR-4.** Does not re-implement `domain-preflight` / plan-ingestion / semantic-compliance /
  CRP — only adds the SDK-mechanism lens.
- **NR-5.** No synchronous transport in v1 — `.md` files only; A2A is the roadmap, not v1.
- **NR-6.** No new failure-classification taxonomy — reuse `RootCause`/`PipelineStage` (as SA
  does). The FDE adds *mechanism authority*, not a new taxonomy.
- **NR-7.** Not a decision-maker — it supplies the MECHANISM half for a human/agent to act on.

---

## 5. Open Questions

> OQ-1, 3, 4, 5, 7, 8 were resolved by the planning pass (see §0). Retained in condensed form
> for traceability; OQ-2 narrowed to a residual home-verification step; OQ-6 still open.

- **OQ-1 → RESOLVED.** Separate package `src/startd8/fde/` + `cli_fde.py` Typer sub-app + thin
  `scripts/run_fde.py` shim. Different authority role ⇒ different home.
- **OQ-2 → RESOLVED (incl. the OQ-2' residual).** The per-question mechanism sources are pinned
  (§6 table). The residual — *which on-disk file serializes the element data* — is now confirmed:
  **`prime-result.json` / `prime-result-<task-id>.json`**, written by
  `scripts/run_prime_workflow.py:838` (in-repo, in `scripts/`). The earlier sweep's "nothing in
  `src/` writes it" was a `src/`-only blind spot — the producer is the workflow *runner* script,
  not a library module. Field path: `result_dict["history"][i]["generation_metadata"]
  ["micro_prime_file_results"][j]["element_results"][k]` → `.tier` / `.generation_strategy` /
  `.repair_steps_applied` / `.repair_attribution` (serialized at `prime_adapter.py:1257` via
  `_serialize_file_result`, attached to history at `prime_contractor.py:3919`). **Cleaner
  alternative for the FDE:** read `prime-postmortem-report.json`, whose `ElementPostMortem`
  records already-*flattened and classified* the same fields (`prime_postmortem.py:1773-1815`) —
  preferred for *explain* mode; fall back to the raw `prime-result*.json` nesting if the
  post-mortem is absent. *(Meta-note: v0.1 named `prime-result.json` and was right; the
  planning sweep's correction was itself wrong — caught only by checking the home, which is the
  Tekizai-Tekisho lesson in miniature.)*
- **OQ-3 → RESOLVED** (FR-16). Both — *explain* reads `ElementResult`; *preflight* calls
  `classify_tier()` live. Tier is never persisted as a standalone artifact (OTel metrics + logs
  only); the recorded form is `ElementResult.tier`.
- **OQ-4 → RESOLVED** (FR-9). All reusable components are library-callable via
  `WorkflowRegistry.run_workflow(...)` / `run_semantic_compliance(...)`. Function-call
  composition, not CLI. `domain-preflight` is downstream of ingestion (consumes a context-seed).
- **OQ-5 → RESOLVED** (FR-12). No A2A transport exists in the SDK; follow the Keiyaku
  frozen-dataclass contract pattern; the transport is a roadmap dependency.
- **OQ-6 → RESOLVED.** **Auto-create on first invocation** (no *mandatory* init — matches the
  Service Assistant's no-init precedent); an **optional `startd8 fde init`** is provided for
  explicit setup / version re-stamp. **Footprint split by scope:** project-scoped posting
  (`fde-context.json`, `fde-cursor.json`, inbound `fde-request.md`, and `fde-preflight.md` which
  is not tied to a run) lives in **`.startd8/fde/`** (the `.startd8/` storage convention);
  run-scoped **`fde-explanation.md` is written into the run output dir** next to
  `service-assistant-triage.json`, so FR-17's `fde_explanation` ref is a local sibling and the
  explanation co-locates with the run evidence it composes. SDK version stamped from
  `startd8.__version__` into `fde-context.json` on create and refreshed each invocation (feeds
  the FR-13 staleness key).
- **OQ-7 → RESOLVED** (FR-14). Both operator and SA can invoke; SA **auto-launch deferred** to
  avoid surprise LLM spend; v1 ships the file handoff + trigger condition only.
- **OQ-8 → RESOLVED** (FR-15). Deterministic-first; LLM confined to prose-plan assumption
  detection + narrative composition. Zero-LLM path exists for pure artifact explanation.

### New open questions surfaced during planning

- **OQ-9 → RESOLVED (two-track preflight).** Full `TaskComplexitySignals` (blast_radius,
  mro_depth, cross-file edges, …) **cannot** be extracted from prose — they need real code/AST —
  so tier *prediction* requires ingestion. Resolution splits preflight into two tracks
  (formalized in **FR-8**): **Track 1 — prose-assumption landmines** (no signals): the LLM reads
  the raw plan/requirements and flags assertions about SDK behavior ("assumes micro-prime is
  off," "assumes a Go repair step exists") — runs **pre-ingestion, on raw markdown**.
  **Track 2 — mechanism-prediction landmines** (signals required): the FDE first runs
  `plan-ingestion` (FR-9 reuse) to produce features, then `extract_signals_from_feature()` →
  live `classify_tier()`, flagging where the plan's stated expectation diverges from the
  predicted tier/route — runs **after ingestion**. Track 1 preserves "works on raw markdown" for
  the high-value prose lens; Track 2 is honest that tier prediction needs ingestion.
- **OQ-10 → RESOLVED (no discrepancy).** Both catalogs exist and are complementary, not
  conflicting: `ModelCatalogEntry` with `.agent_spec` lives at **`contractors/protocols.py:432`**
  (role-based — `DRAFT`/`VALIDATE`/`REVIEW`, via `get_models_by_role`); `Models.*` /
  `get_latest_model(provider, tier)` live in **`model_catalog.py`** (tier-based defaults). The
  sweep only checked `model_catalog.py` and missed the former. FR-5 uses `get_latest_model` for
  the tier-default question and `ModelCatalogEntry`/`get_models_by_role` for the contractor-role
  question.

---

## 6. Mechanism Source-of-Truth Table (pinned in planning)

> The home-authority map. Every FDE MECHANISM claim cites one of these. "Read mode" is per
> FR-16. This is the FDE's analogue of SA's `CAUSE_TO_OPERATIONAL_ACTION` mapping.

| Mechanism question | Authoritative source (symbol / file:line) | Read mode | Notes |
|--------------------|--------------------------------------------|-----------|-------|
| Which tier ran? | `ElementResult.tier` (`micro_prime/models.py:214+`) | explain: ARTIFACT | Recorded per element. |
| Why that tier? | `classify_tier()` → `ClassificationResult.reason` (`complexity/classifier.py:58`) | preflight: LIVE | Decision **not persisted** standalone (OTel + logs only). |
| Did micro-prime run / which path? | `ElementResult.generation_strategy` (`micro_prime/models.py:246`) | explain: ARTIFACT | Values: `template`, `llm_simple`, `escalation`, `cache:*`, … |
| Which repair steps fired? | `ElementResult.repair_steps_applied` + `repair_attribution` | explain: ARTIFACT | AST-valid-before/after recorded too. |
| What model would run (by tier)? | `get_latest_model(provider, tier)` / `Models.*` (`model_catalog.py`) | preflight: LIVE | Tier-based defaults. |
| What model would run (by contractor role)? | `ModelCatalogEntry.agent_spec` / `get_models_by_role()` (`contractors/protocols.py:432`) | preflight: LIVE | Role-based (DRAFT/VALIDATE/REVIEW). |
| Does the SDK support X for language Y? | `LanguageRegistry.get(lang_id)` props (`languages/registry.py`, `protocol.py`) | preflight: LIVE | `repair_enabled`, `syntax_check_command`, MicroPrime support, etc. |
| **Where is the element data serialized?** | **`prime-result*.json`** (`scripts/run_prime_workflow.py:838`); flattened in **`prime-postmortem-report.json`** | explain: ARTIFACT | Path: `history[].generation_metadata.micro_prime_file_results[].element_results[]`. Prefer the post-mortem's flattened `ElementPostMortem`; fall back to raw nesting. |

---

*v0.2 — Post-planning self-reflective update. 6 requirements revised (FR-3/5/9/12/14 sharpened
or corrected, FR-12 reframed), 3 added (FR-15 deterministic-first, FR-16 two read modes, FR-17
SA reference field). A §6 source-of-truth table pins the mechanism map.*

*v0.2.1 — Open-question resolution pass (home-verified against the codebase). **OQ-2' resolved:**
the element data lives in `prime-result*.json` (`scripts/run_prime_workflow.py:838`) /
flattened in `prime-postmortem-report.json` — and notably the planning sweep's own "nothing
writes it" correction was itself wrong (a `src/`-only blind spot), caught only by checking the
home. **OQ-10 resolved:** no discrepancy — `ModelCatalogEntry.agent_spec` exists at
`contractors/protocols.py:432` (role-based) alongside `get_latest_model` (tier-based).
**SA↔FDE coupling resolved:** one-directional, no import cycle (FR-17).*

*v0.2.2 — Final two open questions resolved. **OQ-6:** auto-create footprint (optional
`fde init`), scope-split placement — project-scoped under `.startd8/fde/`, run-scoped
`fde-explanation.md` beside the SA triage (FR-2). **OQ-9:** two-track preflight — Track 1
prose-assumption landmines on raw markdown (no signals), Track 2 mechanism-prediction landmines
after `plan-ingestion` (FR-8). **All open questions now resolved.** Ready for Convergent Review.*

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
