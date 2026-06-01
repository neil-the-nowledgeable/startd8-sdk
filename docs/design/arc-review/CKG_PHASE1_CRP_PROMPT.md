# Convergent Review Prompt

**Generated:** 2026-06-01 18:36:15 UTC
**Mode:** Dual-Document (Plan + Requirements)

> **For the human / orchestrator who generated this file (not instructions to the reviewing agent):**
>
> - This prompt asks the reviewing **agent** to **persist suggestions directly into the source documents** by appending a new **Review Round** under the document's **Appendix C (Incoming)** — initializing the Appendix A/B/C scaffold if the doc has none yet (per `CONVERGENT_REVIEW_AGENT_GUIDE.md`). The chat reply is a short write-confirmation only — **no** in-chat numbered list.
> - **Triage is yours and MUST be persisted, not stripped:** for each suggestion record a disposition — **Accepted → Appendix A** (note where it was merged) or **Rejected → Appendix B** (with rationale) — and update the **Areas Substantially Addressed** tracker (3 accepted per area). Appendices A/B are the **cross-model memory**: later reviewers (you embed the guide telling them so) read them to avoid re-proposing settled or rejected ideas. Do **not** delete A/B after merging.
> - **Suggested separate review passes (orchestrator workflow):** 2 — e.g. run the prompt once for breadth, again for adversarial pass, then triage yourself.
> - **Triage threshold (reference):** 3 accepted suggestions per review area when you triage.
> - **Max suggestions to request from the model:** 10 (soft cap in reviewer instructions below).
> - **Reviewer must have file-write tools (Write/Edit/equivalent) and filesystem access to the source documents.** Chat-only LLMs will fail this contract.

### Source documents

| Role | Path | Size |
|------|------|------|
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/CODE_KNOWLEDGE_GRAPH_PHASE1_PLAN.md` | 134 lines · 1095 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/CODE_KNOWLEDGE_GRAPH_PHASE1_REQUIREMENTS.md` | 198 lines · 1807 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/ckg_phase1_focus.md` | 45 lines · 443 words |

Treat the embedded documents below as **read-only ground truth** for this review. If something conflicts between plan and requirements, call it out explicitly in suggestions and in the coverage mapping.

---

## Your Task

You are a **senior architectural reviewer** with **file-edit tools** (Write/Edit/equivalent) and filesystem access to the source documents listed above. Your job is to produce **improvement suggestions** (structured, anchored, actionable) and **persist them directly into the source documents** by appending a new **Review Round** under each reviewed document's **Appendix C (Incoming)** — see **Prior Review State** below.

**First, read the existing review state** (Appendix A/B/C) in each source doc and **avoid re-proposing** what is already settled (A) or rejected (B), and **avoid near-duplicates** of untriaged items in C (dedup rules below). If a doc has **no** review-log appendix yet, **initialize the A/B/C scaffold** at the end of that doc (additive only) before appending your round.

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

# CKG Phase 1 — Where Reviewer Input Is Most Needed

This review is **not** a blanket pass. The requirements (v2.1) and plan (v1.1) were already
hardened by a spike (run against the real target `strtd8/`, see `SG_FINDINGS.md`) and a
self-reflective planning loop. Spend your suggestions on the six high-uncertainty decisions below;
deprioritize generic completeness/style notes on settled material.

**Read for context before reviewing:** `CODE_KNOWLEDGE_GRAPH_DESIGN.md` (the architecture + §0
research reconciliation), `CROSS_FILE_CONTRACT_RESOLUTION.md` (the 16 RUN_009 failures this exists
to kill), `scripts/spikes/ckg/SG_FINDINGS.md` (what the spike proved already-built vs the gap).

## Focus asks (answer each: Summary / Rationale / Assumptions / Suggested improvements)

1. **Is the reframe sound — is Phase 1 UNDER-scoped?** The plan asserts SG-1 (`prisma_parser`) and
   SG-3 (`prisma_zod_symmetry`) plus the "5 of 6 shipped Approach-B signatures" already cover most
   of the 16 failures, so Phase 1 builds only 3 new checks. Pressure-test the *coverage holes within
   the existing 5*: does `prisma_zod_symmetry` handle nested Zod objects, `z.union`/discriminated
   unions, `.extend()`/`.merge()`, and api-shape mismatches **beyond flat field-presence**? If those
   gaps let RUN_009-class drift through, Phase 1 is under-scoped — name the missing checks.

2. **REQ-CKG-620 route-shape feasibility (OQ-2).** Can SCIP-resolved Next.js (app-router) handler
   signatures actually yield usable request/response *shapes* (Response generics, inferred returns,
   `NextResponse.json(...)` body types)? Is the spike-gate + narrowed-fallback the right call, or is
   route-shape fundamentally a tsc-gate concern that shouldn't be in Phase 1 at all?

3. **Signature (f) strategy (a) sufficiency (REQ-CKG-610).** Does validating only *referenced*
   external members against the resolved SCIP occurrence set (not enumerating a package's exports)
   reliably catch #4/#11 **without false-positives** on real code — re-exports, namespace imports,
   type-only imports, `import type`, conditional exports, subpath exports? When must we fall back to
   indexing the `.d.ts` directly (strategy b)?

4. **Integration / surface risk (REQ-CKG-600, 690a).** Is extending the shipped, wired
   `_evaluate_cross_file_integrity` the right move, or should the 3 new checks be a *separate* pass
   to avoid coupling? Is "land the 690a regression-lock before any surface edit" an adequate
   behavior-preservation guarantee, or is more isolation needed?

5. **Per-batch SCIP integration point (OQ-3, REQ-CKG-230).** At what point in a prime-contractor run
   is the target project actually installed/buildable so `scip-typescript` can index it? If batches
   run before `npm install` / against partially-generated code, does the advisory-degrade path leave
   the very failures we care about (#4/#11/#15) *uncaught* in practice? Specify the trigger point.

6. **Deferral correctness.** Is it safe for Phase 1 to defer the SQLite CKG store, the OTel
   projection, taint, and tree-sitter draft mode — and to drop failures #10 (unused params) and #16
   (framework rendering-mode) to a tsc-gate track? Call out any deferral that will force expensive
   rework or that hides a failure category the pipeline silently mis-scores.

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

1. **Append a `#### Review Round R{n} — <your-model-id> — <UTC date>`** block under **Appendix C (Incoming)** of each source document you reviewed (plan suggestions → plan file; requirements suggestions → requirements file). If a doc has no `## Appendix: Iterative Review Log`, **initialize the A/B/C scaffold** at its end first (additive only). Use Write/Edit; do **not** modify existing prose, Appendix A/B, or prior rounds.
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
- Use file-edit tools to **append a `#### Review Round R{n}` block** under **Appendix C** of each reviewed doc, computing **n** = highest existing round + 1 (or 1). If no `## Appendix: Iterative Review Log` exists, **initialize the empty A/B/C scaffold** (additive) first.
- In dual mode, also append a `## Requirements Coverage Matrix — R{n}` section to the end of the plan file.
- If tokens remain, add an **Endorsements & Disagreements** block on untriaged prior suggestions.

**You MUST NOT:**

- Triage (no ACCEPT/REJECT disposition for your own or others' suggestions) — that is orchestrator-side and lands in Appendix A/B.
- Modify, rewrite, reorder, or delete existing prose, **populated** Appendix A/B, or **prior rounds** in Appendix C. (Creating the empty scaffold when none exists is allowed.)
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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/CODE_KNOWLEDGE_GRAPH_PHASE1_PLAN.md`  ·  **Size:** 134 lines · 1095 words

```markdown
# Code Knowledge Graph — Phase 1 Implementation Plan

> **Version:** 1.1 (2026-06-01 — aligned with reqs v2.1 reflective update)
> **Status:** Draft plan (post-reflection)
> **Requirements:** [CODE_KNOWLEDGE_GRAPH_PHASE1_REQUIREMENTS.md](./CODE_KNOWLEDGE_GRAPH_PHASE1_REQUIREMENTS.md) v2.0
> **Spike:** `scripts/spikes/ckg/SG_FINDINGS.md`
> **Principle:** ship the Verifier (Approach B) for the run-009 stack; reuse the 5 shipped
> signatures; add only the 3 genuinely-missing checks behind scip-typescript.

---

## 1. Approach

Extend the **existing** Verifier surface — `contractors/prime_postmortem.py:_evaluate_cross_file_integrity`
(~lines 1660–1759) — with three new checks backed by a thin scip-typescript layer. No new
substrate, no store. The new checks **degrade to advisory** when the Node toolchain / installed
project is unavailable, so the 5 toolchain-free signatures always run. Build the 16-failure
regression corpus alongside, since it is both the acceptance gate and the dev harness.

### Module layout (new)
```
src/startd8/code_observability/
  scip_runner.py     # REQ-CKG-200: subprocess `scip-typescript index` → index path
  scip_reader.py     # REQ-CKG-210/220: parse SCIP via vendored scip_pb2; exposes typed accessors
                     #   external_member_refs() / cross_file_edges() / routes() — no separate facts model
  scip_pb2.py        # vendored generated bindings (from scip.proto, pinned proto version)
src/startd8/validators/
  external_type_presence.py   # REQ-CKG-610: signature (f)
  route_shape.py              # REQ-CKG-620: route request/response shape
  # tsconfig alias check (REQ-CKG-630): extend cross_file_imports.py (already reads aliases)
```
Wiring point: `prime_postmortem.py:_evaluate_cross_file_integrity` gains the 3 checks behind a
`scip_facts` object (None when unavailable → new checks skipped + logged).

---

## 2. Work breakdown (increments)

Ordered by value × (1 − uncertainty). Inc-0 → Inc-1 first (highest value, lowest risk).

### Inc-0 — SCIP plumbing (REQ-CKG-200/210/220)  · ~1.5d
- Vendor `scip_pb2.py` (pin the proto version; record source commit) — avoids a protoc build dep.
- `scip_runner.run_index(project_root) -> Path|None`: subprocess `scip-typescript index --output …`;
  returns None + warning if tool missing or project not indexable (REQ-CKG-230).
- `scip_reader`: load index; expose typed accessors `external_member_refs()` (occurrence symbols
  with package + member descriptor, e.g. `npm zod 3.x …/ZodObject#extend().`), `cross_file_edges()`,
  `routes()`. **Read from `Document.occurrences`, NOT `Index.external_symbols`** (empty in 0.4.0 —
  verified). *(reqs v2.1: REQ-CKG-220 collapsed in here — no separate `ScipFacts` model.)*
- **Tests:** golden test against a committed small `.scip` (or generate in CI if the Node tool is present); assert external member descriptors parse.
- **Exit:** `ScipFacts` available for `strtd8/` in CI-or-local; graceful None path tested.

### Inc-1 — Signature (f): external-type-presence (REQ-CKG-610)  · ~1.5d  ★ highest value
- `external_type_presence.scan(sources, scip_facts) -> [Violation]`: for each external-package
  member reference in generated code, assert it resolves to a real symbol; unresolved → violation
  (`drafter / cross-file contract / external_type_presence`).
- Decide enumeration strategy (OQ-1): (a) validate only *referenced* members against the resolved
  occurrence set, vs (b) index the dependency's `.d.ts` directly to enumerate valid exports. Start
  with (a) — sufficient for #4/#11; spike (b) only if (a) yields false-positives.
- Wire into `_evaluate_cross_file_integrity` behind `scip_facts`.
- **Tests:** invented `Anthropic.ContentBlockParam` flagged; real `Anthropic.TextBlockParam` passes;
  `import { defineConfig } from 'next'` flagged (#4).
- **Exit:** #4 + #11 detected, zero false-positive on a coherent file.

### Inc-2 — tsconfig path-alias existence (REQ-CKG-630)  · ~0.5d  (small, do before Inc-3)
- Extend `cross_file_imports.py` (already parses alias bases): assert each `tsconfig` path-alias
  target directory/file exists on disk.
- **Tests:** `@/* → ./src/*` with no `src/` flagged (#5); valid alias passes.

### Inc-3 — Route request/response-shape (REQ-CKG-620)  · ~2–3d  ⚠ highest uncertainty (OQ-2)
- **Sub-spike first (0.5d):** confirm SCIP exposes Next.js handler request/response types usefully
  (Response generics, inferred return). If fidelity is poor, narrow REQ-CKG-620 to what's reliably
  extractable (e.g. response field-set vs consumer expectation) and record the limitation.
- `route_shape.scan(sources, scip_facts)`: bind UI consumer expected shape ↔ route actual response
  type; diff. Reuse the field-diff style from `prisma_zod_symmetry`.
- **Tests:** UI consuming a `body` field absent from the route response flagged (#15).
- **Exit:** #15 detected; documented fidelity bound.

### Inc-4 — Unify + regression corpus (REQ-CKG-600/690)  · ~1.5d (parallel w/ Inc-1..3)
- Build `tests/.../fixtures/run009_corpus/` encoding all 16 failures (reuse existing run008
  fixtures + spike fixtures; recover real files if locatable).
- **690a (precondition, land FIRST):** encode the 5-existing-signature categories and lock current
  behavior *before* touching `_evaluate_cross_file_integrity` (the safety net for the surface edit).
- **690b (end):** extend to all 16; 3 new checks catch #4/#11/#5 (and #15 iff 620 confirmed) →
  zero false-PASS across the full set.
- Add `[code-observability]` extra / document the `scip-typescript` Node prerequisite; assert core
  suite green with the tool absent (REQ-CKG-230/NFR-1).

---

## 3. Sequencing & dependencies

```
Inc-0 (SCIP plumbing) ──► Inc-1 (signature f) ──► Inc-2 (tsconfig) ──► Inc-3 (route-shape, sub-spike gated)
        └───────────────► Inc-4 (corpus + unify) runs alongside, finalizes last
```
Inc-1 depends on Inc-0. Inc-2 is independent (no SCIP) — could land first as a quick win. Inc-3 is
gated on its sub-spike. Inc-4 accumulates throughout; the regression half (5 existing signatures)
can be encoded immediately, before any new code.

## 4. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Route-shape extraction from SCIP is low-fidelity (OQ-2) | Sub-spike gates Inc-3; narrow acceptance if needed; #15 is the only failure depending on it |
| scip-typescript needs a cleanly-installed project; mid-batch code isn't built | Run per-batch against installed disk state; new checks advisory when unindexable (REQ-CKG-230) |
| Enumerating valid exports without a reference (OQ-1) | Start with referenced-member validation (a); `.d.ts` indexing (b) only if needed |
| Vendored `scip_pb2` drifts from tool's SCIP version | Pin proto version; CI note; reader tolerant of unknown fields (protobuf default) |
| Duplicating/!regressing the 5 shipped signatures | Inc-4 regression half locks current behavior before touching the surface |
| Node 26 / tool-version churn | Pin `@sourcegraph/scip-typescript` version; record in extra |

## 5. Test plan

- **Unit:** each new check in isolation (Inc-1/2/3) + `scip_reader` golden parse (Inc-0).
- **Regression:** the 5 existing signatures over the corpus (no behavior change).
- **Acceptance (REQ-CKG-690):** 16/16 detected, zero false-PASS, on the run-009 corpus.
- **Degrade:** corpus run with `scip-typescript` absent → 5 signatures still fire; 3 new advisory.

## 6. Rollout

- Behind the existing postmortem path (no separate flag needed — the Verifier already runs);
  new checks self-gate on `scip_facts is not None`.
- Land Inc-2 + Inc-1 first (close #4/#11/#5), then Inc-3 (#15). Ship the corpus test with Inc-1.

## 7. Effort summary

| Inc | REQ | Effort | Risk |
|-----|-----|--------|------|
| 0 SCIP plumbing | 200/210/220 | ~1.5d | Low |
| 1 signature (f) | 610 | ~1.5d | Low |
| 2 tsconfig alias | 630 | ~0.5d | Low |
| 3 route-shape | 620 | ~2–3d | **Med-High (OQ-2)** |
| 4 corpus + unify | 600/690 | ~1.5d | Low |

**Total ≈ 7–8 days**, front-loaded on the low-risk high-value slices; the only real uncertainty is Inc-3.
```

---

## Document Under Review: Requirements

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/CODE_KNOWLEDGE_GRAPH_PHASE1_REQUIREMENTS.md`  ·  **Size:** 198 lines · 1807 words

```markdown
# Code Knowledge Graph — Phase 1 Requirements (Post-Spike, Reframed)

> **Version:** 2.1 (2026-06-01 — reflective update after writing the implementation plan)
> **Status:** Draft for review
> **Supersedes:** v1.0 of this file (which proposed building DMMF + a CONFORMS_TO binder + a new
> SQLite substrate — the spike proved most of that is already shipped). Also supersedes
> `CODE_OBSERVABILITY_PHASE1_REQUIREMENTS.md` (REQ-MIE-*).
> **Design:** [CODE_KNOWLEDGE_GRAPH_DESIGN.md](./CODE_KNOWLEDGE_GRAPH_DESIGN.md)
> **Spike evidence:** `scripts/spikes/ckg/SG_FINDINGS.md` (run against the real target `strtd8/`)
> **Forcing context:** [CROSS_FILE_CONTRACT_RESOLUTION.md](./CROSS_FILE_CONTRACT_RESOLUTION.md)

---

## 0. Thesis (what the spike changed)

The SG-1/2/3 spike, run against the real run-009 stack (`/Users/neilyashinsky/Documents/dev/strtd8/strtd8/`),
found that **most of the proposed Phase 1 is already shipped**:

- **Prisma fact extraction** — `languages/prisma_parser.py` already parses all 12 real models. *(was SG-1)*
- **Zod⇄Prisma CONFORMS_TO** — `validators/prisma_zod_symmetry.py` already binds + diffs, and caught the real #13 drift with zero false-positives. *(was SG-3)*
- **5 of the 6 Approach-B cross-file signatures** are implemented and wired into
  `contractors/prime_postmortem.py:_evaluate_cross_file_integrity`.

So Phase 1 is **not** "build a substrate." It is the **two genuinely-missing checks** plus
**wiring scip-typescript** (which the spike proved works: full app-source index in ~7s, real
cross-file + external `.d.ts` resolution). The SQLite store, OTel projection, taint, and the
Go/Python/Java/C# backends from the design are **all deferred** — Phase 1 needs none of them.

---

## 0.1 Planning Insights (v2.0 → v2.1, reflective update)

> Writing the implementation plan ([CODE_KNOWLEDGE_GRAPH_PHASE1_PLAN.md](./CODE_KNOWLEDGE_GRAPH_PHASE1_PLAN.md))
> stress-tested v2.0. Six corrections — the requirements still carried premature specifics.

| v2.0 assumption | Planning discovery | Impact |
|---|---|---|
| Need a separate fact normalizer (REQ-CKG-220) | The 3 checks consume the SCIP reader's accessors directly; a separate `ScipFacts` model is an unneeded layer in Phase 1 | **220 collapsed into 210** (reader exposes typed accessors) |
| Route-shape (620) is a firm deliverable | SCIP route/response-type fidelity is unverified (OQ-2); it's the only med-high-risk item | **620 made spike-gated** with a narrowed fallback acceptance |
| Signature-(f) enumeration strategy open (OQ-1) | Validating *referenced* members against resolved occurrences (strategy a) suffices for #4/#11 | **OQ-1 resolved → strategy (a) for Phase 1** |
| Corpus (690) is an end-of-phase gate | The regression half must land *first* to lock the 5 shipped signatures before editing the shared Verifier | **690 split: 690a regression-lock (precondition) / 690b acceptance** |
| Extending `_evaluate_cross_file_integrity` is safe | Modifying a shipped, wired surface risks regressing the existing 5 checks | **600 strengthened: behavior-preserving, enforced by 690a** |
| Need a `[code-observability]` pip extra + scip_pb2 generation | `protobuf` already present; vendor a pinned `scip_pb2.py` → no protoc/grpcio-tools runtime dep; only the Node tool is new | **Dependencies simplified** (no new pip extra required) |

**Resolved open questions:** OQ-1 → strategy (a). OQ-3 → run per-batch SCIP against the installed
disk state; treat in-flight generated files as the batch under test.

---

## 1. The 16 RUN_009 failures — coverage after the spike

This is the scope, evidence-based. "Existing" = already shipped & verified; "**NEW**" = Phase 1 work.

| # / category | Status | Owner |
|---|---|---|
| 1,2 module-path | ✅ existing | `cross_file_imports.scan_unresolvable_imports` |
| 3 dependency-availability | ✅ existing | `cross_file_imports.scan_missing_dependencies` |
| 6,8,12 canonical-schema (fields/compound-key) | ✅ existing | `prisma_usage.scan_prisma_usage` + `prisma_parser` |
| 13 + 9 Zod/api field drift | ✅ existing | `prisma_zod_symmetry.evaluate_cross_file_integrity` |
| 7 type-class mismatch | ✅ existing | `prisma_zod_symmetry` |
| **4, 11 external-library-API** (`Anthropic.ContentBlockParam`, `next` `defineConfig`) | ❌ **NEW** | **REQ-CKG-610 signature (f)** |
| **15 api-response-shape** (UI `body` field not on model) | ❌ **NEW** | **REQ-CKG-620 route-shape** |
| **5 project-config** (tsconfig alias → nonexistent `src/`) | ⚠ **NEW (small)** | **REQ-CKG-630** |
| 10 unused params; 16 framework-rendering-mode | ⏸ deferred | tsc-gate / framework-config (out of Phase 1) |

**Phase 1 closes #4, #11, #15, and #5.** Everything else is already caught — Phase 1 must keep it caught (regression).

---

## 2. Reuse, do not rebuild (promote existing code to CKG fact sources)

| Existing | Role in Phase 1 |
|---|---|
| `languages/prisma_parser.py` | Prisma facts (no DMMF — demoted to optional fidelity) |
| `validators/cross_file_imports.py` | signatures (a) unresolvable-import, (b) missing-dep |
| `validators/prisma_usage.py` | signatures (c) field-site, (e) compound-key |
| `validators/prisma_zod_symmetry.py` | signature (d) Zod⇄Prisma CONFORMS_TO + field diff |
| `contractors/prime_postmortem.py:_evaluate_cross_file_integrity` | the Verifier surface to **extend**, not replace |
| `contractors/upstream_interface.py:render_prisma_field_sets` | generation-time Prisma field inheritance (already live) |

---

## 3. Requirements (new work only)

### 3.1 scip-typescript authoritative TS index (REQ-CKG-2xx)

**REQ-CKG-200 — scip-typescript runner.** Wrap `scip-typescript index` as a subprocess producing
a per-batch SCIP index for the target project. Authoritative mode: requires `node_modules`
installed; runs once per batch (the spike measured ~7s; **not** the inner loop). Output to a
transient path under `.startd8/state/` (no persistent store required in Phase 1).

**REQ-CKG-210 — SCIP reader.** Read the index via generated `scip_pb2` (vendor `scip_pb2.py`
or generate from `scip.proto` at build). **Read external symbols from `Document.occurrences`,
not `Index.external_symbols`** (empty in scip-typescript 0.4.0 — verified). Expose: per-document
occurrences (symbol string, roles, range), cross-file def→ref edges, and external-package member
symbols (e.g. `… npm zod 3.x …/ZodObject#extend().`).

**REQ-CKG-220 — (collapsed into 210 per Planning Insights).** No separate fact-normalizer model
in Phase 1. The reader (REQ-CKG-210) exposes the typed accessors the three checks need —
`external_member_refs()`, `cross_file_edges()`, `routes()` — and that *is* the fact surface. A
general-purpose CKG schema/store is deferred (§5). Revisit only if a second consumer needs facts
in a shape the reader doesn't already provide.

**REQ-CKG-230 — Fallback.** If the target doesn't install/index cleanly, skip the SCIP-backed
checks (signature f, route-shape) with a logged warning and downgrade them to advisory — never
raise. The 5 existing toolchain-free signatures continue to run.

### 3.2 The two new checks + unification (REQ-CKG-6xx)

**REQ-CKG-610 — Signature (f): external-type-presence.** For each reference to an external
package member in generated code (e.g. `Anthropic.ContentBlockParam`, `import { defineConfig }
from 'next'`), assert it resolves to a real symbol. **Mechanism (OQ-1 resolved → strategy a):**
validate the *referenced* member against the resolved occurrence set from the SCIP index; a
referenced member that resolves to nothing / `local` is a violation. Strategy (b) — indexing the
package's `.d.ts` directly to enumerate valid exports — is a fallback used **only if (a) produces
false-positives** (not Phase 1 default). **Acceptance:** flags a deliberately-invented
`Anthropic.ContentBlockParam` and passes the real `Anthropic.TextBlockParam` (RUN_009 #11, #4).

**REQ-CKG-620 — Route request/response-shape check. ⚠ SPIKE-GATED (OQ-2).** *Before committing
this requirement,* a 0.5d sub-spike must confirm SCIP exposes Next.js handler request/response
types with enough fidelity (Response generics, inferred returns). **If confirmed:** extract `Route`
request/response types and assert a UI consumer's expected response shape matches the producing
route's actual shape — **acceptance:** flags RUN_009 #15 (UI consumes a `body` field absent from
the route's response). **If fidelity is poor:** narrow to the reliably-extractable subset (e.g.
response field-set vs consumer expectation) and record the limitation; #15 may move to the
tsc-gate track. This is the only RUN_009 failure depending on 620.

**REQ-CKG-630 — tsconfig path-alias target existence (small).** Assert every `tsconfig` path
alias resolves to a directory/file that exists on disk. **Acceptance:** flags #5 (`@/*` →
`./src/*` with no `src/`).

**REQ-CKG-600 — Unify under one Verifier (behavior-preserving).** Extend
`_evaluate_cross_file_integrity` to run the 5 existing + 3 new checks behind one surface, each
emitting the existing attribution (`drafter / cross-file contract / <check>`) + Kaizen suggestion.
New checks gated on SCIP availability (REQ-CKG-230). **The extension MUST be behavior-preserving
for the 5 existing checks** — verified by landing the REQ-CKG-690a regression lock *before* any
modification to this surface.

**REQ-CKG-690a — Regression lock (precondition).** Encode the categories the 5 shipped signatures
already catch (#1–3, 6–9, 12, 13) as fixtures and assert current behavior **before** modifying
`_evaluate_cross_file_integrity`. This is the safety net for REQ-CKG-600 and must land first.

**REQ-CKG-690b — New-check acceptance (end of phase).** Extend the corpus to all 16 failures;
assert the 3 new checks catch #4/#11/#5 (and #15 iff 620 is confirmed) with **zero false-PASS**
across the full set. This is the operational definition of "the score-vs-reality inversion is
closed for this stack."

---

## 4. Non-functional requirements

- **NFR-1 — Toolchain-free baseline preserved.** The 5 existing signatures must keep running with
  no Node toolchain; only the 3 SCIP-backed checks require it (and degrade gracefully, REQ-CKG-230).
- **NFR-2 — Per-batch, not inner-loop.** SCIP indexing runs once per batch against installed code
  (~7s verified). Per-feature checks are queries against the already-built index.
- **NFR-3 — Clean-room.** scip-typescript (Apache-2.0), protobuf, existing SDK validators — no
  CodeQL artifacts. Record tool versions/licenses.
- **NFR-4 — Anti-deferral.** The new external-API + route-shape checks ship in Phase 1; they are
  the only RUN_009 categories still uncaught.

## 5. Non-requirements (explicitly deferred — the spike removed these from Phase 1)

- **DMMF Prisma probe** — `prisma_parser` suffices; DMMF is an optional fidelity upgrade later.
- **New CONFORMS_TO binder** — already exists (`prisma_zod_symmetry`).
- **SQLite CKG store + OTel projection + Grafana** — Phase 1 uses the transient SCIP index; persist
  only if incremental needs force it.
- **Go / Python / Java / C# authoritative backends** — later phases.
- **Taint / injection (Pysa, IFDS-lite)** — Phase 3.
- **tree-sitter draft mode** — only needed once we want inner-loop partial extraction; not Phase 1.
- **Failures #10 (unused params), #16 (rendering-mode)** — tsc-gate / framework-config track.

## 6. Dependencies

- **Node tools (subprocess):** `@sourcegraph/scip-typescript` (verified v0.4.0). Documented as a
  prerequisite for the SCIP-backed checks, not a Python import.
- **Python:** `protobuf` is **already present** in the env; **vendor a pinned `scip_pb2.py`**
  (record the source proto version) so there is **no protoc/grpcio-tools runtime dependency** and
  **no new pip extra is required** for Phase 1. The only new prerequisite is the Node
  `scip-typescript` tool (subprocess). Core suite must run with the Node tool absent (REQ-CKG-230).

## 7. Verification strategy

1. **Regression** — the RUN_009 corpus: 5 existing signatures still catch #1–3,6–9,12,13 (no behavior change).
2. **New checks** — signature (f) catches #4/#11 (invented external member); route-shape catches #15; tsconfig check catches #5.
3. **Ops** — SCIP index builds on the real `strtd8/` in seconds; reader extracts external member symbols from occurrences.
4. **Graceful degrade** — with `node_modules` absent / project not indexable, SCIP-backed checks downgrade to advisory; toolchain-free 5 still run.
5. **Total** — 16/16 detected, zero false-PASS (REQ-CKG-690).

## 8. Open questions

- **OQ-1 → RESOLVED (strategy a).** Validate *referenced* external members against the resolved
  occurrence set; index a package's `.d.ts` directly only as a fallback if (a) false-positives.
- **OQ-2 — OPEN, gates REQ-CKG-620.** Route-shape extraction fidelity from SCIP handler signatures
  (Next.js `Response` generics) — the Inc-3 sub-spike resolves this before 620 is committed.
- **OQ-3 → RESOLVED.** Per-batch SCIP runs against the installed disk state; in-flight generated
  files are treated as the batch under test.
- **OQ-4 — OPEN (lean check-only).** Should the unified Verifier emit CKG facts for a future store,
  or stay check-only until a store is justified? Phase 1 stays check-only.
```

---

## Begin

Produce your **suggestions** now and **append them to the source files** via Write/Edit (see **Your Task**, **Deliverables**, and **Scope lock** above). Source file paths are in the **Source documents** table at the top of this prompt.

Checklist before your **final** chat reply:

- [ ] Read each source file's Appendix A/B/C; did not re-propose settled (A) or rejected (B) items, nor near-duplicate untriaged (C).
- [ ] Appended a `#### Review Round R{n}` block under **Appendix C** of each source file in scope (initialized the A/B/C scaffold if it was absent).
- [ ] Round block contains: executive summary (≤10 bullets) + numbered suggestions (**R{n}-S\*** / **R{n}-F\***); optional adversarial subsection; optional Endorsements & Disagreements block.
- [ ] Did not modify existing prose, populated Appendix A/B, or prior rounds in C.
- [ ] Appended `## Requirements Coverage Matrix — R{n}` section to the end of the **plan** file (after your round block).
- [ ] Chat reply is a **short** (1–3 line) write-confirmation listing file paths and suggestion counts — **not** the suggestion content.

**Stop after persisting** — do not triage, do not emit merged documents in chat or in the files, do not modify existing prose, populated Appendix A/B, or prior rounds in Appendix C (initializing an absent A/B/C scaffold is fine).
