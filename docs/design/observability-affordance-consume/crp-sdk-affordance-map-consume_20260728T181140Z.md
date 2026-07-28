# Convergent Review Prompt

**Generated:** 2026-07-28 18:11:40 UTC
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
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/observability-affordance-consume/PLAN_AFFORDANCE_MAP_GENERATOR_CONSUME.md` | 195 lines · 1190 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/observability-affordance-consume/REQ_AFFORDANCE_MAP_GENERATOR_CONSUME.md` | 326 lines · 3158 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/observability-affordance-consume/.crp-focus.md` | 42 lines · 338 words |

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

# CRP focus — Affordance-Map Generator Consume

**Date:** 2026-07-28  
**Target (least reviewed):** [`REQ_AFFORDANCE_MAP_GENERATOR_CONSUME.md`](REQ_AFFORDANCE_MAP_GENERATOR_CONSUME.md) v0.3.2  
**Secondary:** [`PLAN_AFFORDANCE_MAP_GENERATOR_CONSUME.md`](PLAN_AFFORDANCE_MAP_GENERATOR_CONSUME.md) v0.3.2  
**Parent (settled, do not relitigate):** ContextCore Phase A catalog/Report Card emit + AffordanceMap schema (`REQ_O11Y_AUDIT_CATALOG_REPORT_CARD`)

## Why CRP (Design_Docs #24 calibration)

This feature **writes** artifacts through the **existing** `generate_observability_artifacts` / CLI surface (not additive read-only). CRP is **recommended**.

## Settled / do-not-relitigate

- No `import contextcore` in startd8; consume plain JSON only.
- AffordanceMap is optional; default generate unchanged **except** intentional FR-B5 runbook heading alignment (Hayai).
- When map present: **replace** full `_GENERATORS` loop with planned actions only (not full-then-patch).
- Reuse existing `--dry-run` for plan print; no second dry-run flag.
- Refuse `--check` + `--affordance-map` (NR-G8).
- Known `gen.*` set frozen; unknown ids skipped, not invented.
- Service join: local mirror of CC `catalog_service_id` (FR-B6a); skip unknown after normalize.
- Shrink (`gen.shrink_dashboard_lines`) is net-new; must preserve OBS-200a / RED.
- `rex.*` / `measure.*` out of this REQ.
- Mottainai: reuse `_ensure_red_coverage`, triplet generators, coverage scorer, runbook gen; bias/select only.
- Quality JSON remains SSOT for scores; do not re-derive AffordanceMap inside generator when map provided.
- Keiyaku: typed `ActionPlanEntry` across load→plan→apply.
- Marker presence ≠ operational runbook quality (Obs #32).

## Ask CRP to pressure-test

- FR-B3a branch correctness: does map mode miss required post-gen steps (index write, quality report, portal) that must still run for touched artifacts?
- Shrink heuristics vs contract `max_lines` (EXT-101) and Grafana panel graph integrity after drops.
- Local `normalize_element_id` fidelity vs CC `catalog_service_id` (ENV_FORM + `normalize_service`) without importing CC — drift risk.
- Whether zero-score leg detection for `complete_triplet` has a clear on-disk signal today.
- Interaction of map mode with `--observability-yaml` domain extras / declared-lane generators (should those fire for touched services only, or never in map mode?).
- Exit policy when map is malformed vs when all rows skip.

## Out of scope for this CRP

- Phase A scorecard schema changes.
- SIL-REX remediation consume.
- Renaming affordance ids.
- Relitigating Hayai FR-B5 always-on (architect-resolved; CRP may note residual risk only).

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/observability-affordance-consume/PLAN_AFFORDANCE_MAP_GENERATOR_CONSUME.md`  ·  **Size:** 195 lines · 1190 words

```markdown
# Affordance-Map Consume (startd8 Generator) — Implementation Plan

**Version:** 0.3.2 (aligned with REQ v0.3.2)  
**Date:** 2026-07-28  
**Status:** Architect-hardened; implement after CRP (recommended) or sponsor skip  
**Requirements:** [`REQ_AFFORDANCE_MAP_GENERATOR_CONSUME.md`](REQ_AFFORDANCE_MAP_GENERATOR_CONSUME.md)  
**Parent Phase B:** ContextCore `REQ_O11Y_AUDIT_CATALOG_REPORT_CARD` FR-AFF-3 (`gen.*`)  
**CRP focus:** [`.crp-focus.md`](.crp-focus.md)

---

## 1. Goal

Wire optional AffordanceMap JSON into `generate_observability_artifacts` so listed `gen.*` actions become **targeted repairs**, reusing existing RED / triplet / coverage / runbook synthesizers, plus a new shrink pass — without `import contextcore` or full-tree thrash.

---

## 2. Architecture

```text
scorecard-json / affordance_map.json
        │
        ▼
  load_affordance_map()     # FR-B1 — parse + validate known gen.*
        │
        ▼
  normalize_element_id()    # FR-B6a — local mirror of CC catalog_service_id
        │
        ▼
  plan_affordance_actions() # FR-B2/B2b — list[ActionPlanEntry]
        │
   --dry-run? ──yes──► print plan + exit 0 (no writes)
        │ no
        ▼
  apply_affordance_actions()  # FR-B3/B3a/B4/B5 — replaces full _GENERATORS loop
        │  per ActionPlanEntry → existing generators | shrink
        ▼
  affordance_actions.json     # FR-B7
  (+ existing quality report for touched artifacts)
```

**Module home (new):** `src/startd8/observability/affordance_map_consume.py`  
Keep planner/loader out of the large `artifact_generator.py`; call from generate entry + CLI.

**Mode rule (FR-B3a):**  
- No map → today’s full generate (+ FR-B5 always-on runbook headings).  
- Map present → **do not** run unconditional full-tree `_GENERATORS`; only planned actions.  
- `--check` + map → refuse (NR-G8).

---

## 3. Work packages

### WP-B0 — Loader, planner, CLI, dry-run (FR-B1, B2, B2a, B2b, B6, B6a, B8, AC-G1/2/7/8/9)

| Step | Change |
|------|--------|
| B0.1 | Add `affordance_map_consume.py`: `AffordanceMapEntry`, `ActionPlanEntry`, `load_affordance_map`, `normalize_element_id`, `KNOWN_GEN_AFFORDANCES`, `plan_affordance_actions`, skip reasons |
| B0.2 | Fixture: frozen AffordanceMap from CC scorecard-json shape (+ slim array) under `tests/fixtures/affordance_map/` |
| B0.3 | Wire CLI: `--affordance-map`, reuse `--dry-run`; kwargs on `generate_observability_artifacts`; refuse `--check`+map |
| B0.4 | Unit tests: parse both shapes; unknown id skip; dry-run no writes; no `contextcore` import; normalize join cases |
| B0.5 | Docs: update HOWTO in this folder |

**Exit:** dry-run prints stable plan for fixture; AC-G2/7/8/9 green.

### WP-B1 — Targeted synthesizer bias + runbook headings (FR-B3, B3a, B5, AC-G3/4)

| Step | Change |
|------|--------|
| B1.1 | Hook: when map present, branch to `apply_affordance_actions` instead of full `_GENERATORS` loop |
| B1.2 | `gen.emit_red_panels` → `_ensure_red_coverage` for that service dashboard only |
| B1.3 | `gen.complete_triplet` → regenerate only missing/zero-score legs |
| B1.4 | `gen.improve_metric_coverage` → regen dashboard/alerts favoring uncovered expected metrics (reuse coverage inputs; do not re-derive map) |
| B1.5 | **FR-B5 always-on:** rename/align `generate_runbook` headings to `Overview` / `Risks` / `Procedures` / `Escalation`; update golden tests |
| B1.6 | Integration-style test: single-service RED map touches only that dashboard path |

**Exit:** AC-G3, AC-G4 green.

### WP-B2 — Shrink (FR-B4, AC-G5)

| Step | Change |
|------|--------|
| B2.1 | `shrink_dashboard_lines(dashboard, max_lines, preserve_red=True)` |
| B2.2 | Prefer drop non-RED / duplicate / verbose panels; refuse if OBS-200a would regress |
| B2.3 | Planner already orders shrink last |
| B2.4 | Tests: oversize shrinks under budget; RED-only refuses or preserves RED |

**Exit:** AC-G5 green.

### WP-B3 — Action report + operator wiring (FR-B7, AC-G6)

| Step | Change |
|------|--------|
| B3.1 | Write `{output_dir}/affordance_actions.json` (planned / applied / skipped) |
| B3.2 | Log unknown element_id / affordance; all-skip → exit 0 |
| B3.3 | Finish HOWTO: audit → extract map → generate `--affordance-map` |
| B3.4 | Optional: jq recipe only (no CC CLI required) |

**Exit:** AC-G6 green; operator can run end-to-end on Thanos pilot tree.

---

## 4. File touch list (expected)

| Path | Role |
|------|------|
| `src/startd8/observability/affordance_map_consume.py` | **New** — load/plan/apply/shrink orchestration + typed entries |
| `src/startd8/observability/artifact_generator.py` | Branch: map mode vs full loop |
| `src/startd8/observability/artifact_generator_generators.py` | RED ensure / selective regen; runbook headings (FR-B5) |
| `scripts/generate_observability_artifacts.py` | `--affordance-map`; `--check`+map refuse; dry-run plan print |
| `tests/…/test_affordance_map_consume.py` | Unit + dry-run + join normalize |
| `tests/fixtures/affordance_map/*` | Frozen map + optional dashboard fixtures |
| `docs/design/observability-affordance-consume/*` | REQ/PLAN/HOWTO/CRP focus |

---

## 5. Traceability (REQ → WP)

| REQ | WP |
|-----|-----|
| FR-B0, NR-G* | All (constraints) |
| FR-B1, B6, B6a, B8 | B0 |
| FR-B2, B2a, B2b | B0 |
| FR-B3, B3a | B1 |
| FR-B5 | B1 |
| FR-B4 | B2 |
| FR-B7 | B3 |
| AC-G1–G9 | as listed per WP |

---

## 6. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Shrink deletes RED | OBS-200a gate + refuse; priority after RED emit |
| Selective regen drifts from full-gen paths | Call same helpers as full gen; only narrow *which* services/legs |
| Service id mismatch (CC catalog vs slug) | FR-B6a local normalize; skip unknown; HOWTO join rule |
| Map becomes second quality SSOT | NR-G2; quality report unchanged |
| FR-B5 breaks golden runbooks | Update fixtures in same WP; AC-G1 carves the exception |
| Accidental full+map double write | FR-B3a explicit branch; test AC-G3 |

---

## 7. Out of scope (explicit)

- SIL-REX / remediation `rex.*` and `measure.*` consumers  
- Changing AffordanceMap emit or renaming `gen.*`  
- Mandatory map on every generate  
- LLM-authored repairs  
- Authored-panel merge for shrink  
- Second dry-run CLI flag  

---

## 8. Implementation order

1. WP-B0 (safe, observable, no artifact mutation beyond refuse paths)  
2. WP-B1 (high lever + FR-B5 heading fix)  
3. WP-B2 (shrink — net-new risk)  
4. WP-B3 (operator glue)

Do **not** start code until CRP accepted or sponsor explicitly skips CRP (Design_Docs #24: CRP recommended for write-through-existing surface).

---

*Aligned with REQ v0.3.2. CRP target = REQ; do not relitigate: no import contextcore, map replaces full loop, reuse `--dry-run`, Hayai FR-B5 always-on, shrink preserves RED.*

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/observability-affordance-consume/REQ_AFFORDANCE_MAP_GENERATOR_CONSUME.md`  ·  **Size:** 326 lines · 3158 words

```markdown
# Affordance-Map Consume (startd8 Generator) — Requirements

**Version:** 0.3.2 (Post architect re-validation — lessons base + principle gaps closed)  
**Date:** 2026-07-28  
**Status:** Draft — architect-hardened; CRP recommended (write-through-existing-surface)  
**Owner:** startd8 observability / ContextCore audit consumers  
**Plan:** [`PLAN_AFFORDANCE_MAP_GENERATOR_CONSUME.md`](PLAN_AFFORDANCE_MAP_GENERATOR_CONSUME.md)  
**Parent:** ContextCore [`REQ_O11Y_AUDIT_CATALOG_REPORT_CARD.md`](../../../../ContextCore/docs/design/requirements/REQ_O11Y_AUDIT_CATALOG_REPORT_CARD.md) Phase B (`gen.*` only)  
**Audience:** startd8 `artifact_generator` maintainers, SIL-REX measure operators  
**CRP focus:** [`.crp-focus.md`](.crp-focus.md)

**Related code:**
- startd8: `src/startd8/observability/artifact_generator.py`, `artifact_generator_generators.py`, `observability_artifact_checks.py`, `scripts/generate_observability_artifacts.py`
- ContextCore emit: `src/contextcore/observability/catalog.py` (`AFFORDANCE_BY_GAP`, `affordance_map`, `catalog_service_id`)
- Quality / contracts: `observability-quality.json`, onboarding `expected_output_contracts` (runbook markers: Overview / Risks / Escalation / Procedures)

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between the Phase-B stub in the parent REQ and this grounded draft (planning pass against the generator).

| Pre-plan Assumption | Planning Discovery | Impact |
|---------------------|-------------------|--------|
| Generator needs new synthesizers for each `gen.*` | RED (`_ensure_red_coverage`), triplets (`_GENERATORS`), metric-coverage scoring, runbook generation, EXT-101 **checks** already exist | FR-B = **bias + selective regen + one new shrink pass**; do not fork scorers |
| AffordanceMap might be imported from ContextCore | startd8 observability has **zero** `import contextcore`; dependency direction must stay CC → startd8 | Consume **plain JSON** only; frozen schema in startd8 tests |
| Full regen on map is fine | Thanos multi-service trees + drift/`--check` make full regen destructive | **FR-B3 targeted repair** default; dry-run required |
| `gen.shrink_dashboard_lines` is like the others | EXT-101 is **check-only** (`max_lines`); no shrink writer | FR-B4 is the only net-new generator capability |
| `gen.enrich_runbook` = thicker prose | Generator headings ≠ contract markers (`Overview`/`Risks`/`Procedures`) | Enrich = **marker parity + missing sections**, not LLM prose |
| `gen.complete_triplet` = regenerate all three legs | Triplets already unconditional; incompleteness = missing/zero-score leg | Selective leg regen only |
| Metric coverage needs a new emitter | Coverage = expected ∩ referenced; domain panels already exist | Bias dashboard/alert regen toward uncovered metrics |
| Parent FR-AFF-3 is enough as a REQ | Too thin to implement; needs startd8-owned FRs | This sibling REQ owns Phase B `gen.*` |

**Resolved open questions (planning):**
- **OQ-G1 →** Load AffordanceMap via `--affordance-map PATH` (scorecard-json extract or `affordance_map` array); default off.
- **OQ-G2 →** Targeted per-`(service, affordance)` repair; never full-tree rewrite by default.
- **OQ-G3 →** Shrink must not drop RED below OBS-200a (≥2/3 Rate/Errors/Duration).
- **OQ-G4 →** `rex.*` / `measure.*` out of scope (ContextCore / SIL-REX sibling later).

---

### 0.1 Lessons-Learned Hardening (v0.3 → corrected v0.3.2)

> **v0.3 miss:** claimed “no Lessons_Learned index.” The curated base lives at
> `~/Documents/craft/Lessons_Learned/` (sdk + observability domains). Re-applied
> with concrete lesson IDs:

- **[Design_Docs #12 — Phantom-reference audit]** — Re-grepped HEAD: `_ensure_red_coverage`, OBS-200a / OBS-EXT-100 / OBS-EXT-101, `_write_quality_report`, `compute_metric_coverage`, `generate_runbook`, `_GENERATORS` exist. `shrink_dashboard_lines` / AffordanceMap loader = **to-be-created**. Runbook currently emits `## Service summary` / `## First response` — only `## Escalation` overlaps contract markers `Overview|Risks|Escalation|Procedures` (tests/fixtures). → §7 + FR-B5.
- **[Design_Docs #5 — Single-source vocabulary]** — Affordance ids owned by parent FR-AFF-1; this REQ freezes known `gen.*` as a non-normative snapshot + test assert (FR-AFF-3: no rename). Schema contract owned here as JSON fixtures, not duplicated prose from CC.
- **[Design_Docs #15 — CRP least-reviewed target]** — Target = this REQ; parent Phase A is settled. → `.crp-focus.md`.
- **[Design_Docs #24 — CRP calibration]** — Feature **writes** artifacts through the **existing** generate + CLI surface → CRP is **recommended**, not skippable additive/$0. → Status + Phase 5 offer.
- **[Design_Docs #27 — Substrate HEAD]** — Join rule must match CC `catalog_service_id` behavior at HEAD (ENV_FORM normalize / else lowercase), mirrored locally without `import contextcore`. → FR-B6a.
- **[Observability Leg 9 #32 — markers necessary-not-sufficient]** — AC-G4 clears EXT-100 marker gaps only; does **not** claim runbook quality beyond markers. → AC-G4 wording.
- **[Prune phantom scope]** — LLM runbook rewrite + re-score quality from map remain NR; `rex.*`/`measure.*` out.

---

### 0.2 Design-Principle Hardening (v0.3.1 → v0.3.2)

> Re-checked `docs/design-princples/` index; closed gaps the first pass missed.

- **[Mottainai]** — Map is the worklist; reuse synthesizers; do not re-derive AffordanceMap from quality when map present. → FR-B1/B3, NR-G2.
- **[Warm Up]** — AffordanceMap is the audit→generate handoff artifact; consume it, do not re-audit inside startd8. → FR-B0, NR-G1.
- **[Genchi Genbutsu]** — Bind to real scorecard `affordance_map` / fixture frozen from CC shape; do not invent services. → FR-B1, FR-B6.
- **[Accidental-Complexity]** — One planner module + reuse existing `--dry-run` (no second dry-run verb); refuse `--check`+map combo rather than invent hybrid semantics. → FR-B2a, NR-G8.
- **[Context-Correctness-by-Construction]** — Malformed map → fail; empty → no-op log; unknown ids/element_ids → skip with reason. → FR-B1, FR-B6.
- **[Hitsuzen]** — Action plan derived deterministically; no LLM. → FR-B2, NR-G3.
- **[Keiyaku]** — `ActionPlanEntry` (and load result) are typed dataclasses with skip reasons — not free-form dict soup across load→plan→apply. → FR-B2b.
- **[Hayai vs Sotto on FR-B5]** — Generator already scores runbooks against markers it does not emit → defect. **Hayai wins:** always-on heading alignment is in scope (intentional byte change; update fixtures in same WP). Map-driven `enrich_runbook` then mostly no-ops heading gaps. Documented Sotto exception: correctness defect fix, not a new authored-content layer. → FR-B5.
- **[Anzen]** — Shrink preserves OBS-200a; refuse if RED would regress. → FR-B4.
- **[Mieruka]** — `affordance_actions.json` makes planned/applied/skipped observable. → FR-B7.

---

### 0.3 Architect Validation (v0.3.2)

> Principle solution-architect pass against HEAD generator + CC Phase A emit. Corrections applied:

| Ambiguity / defect | Resolution |
|--------------------|------------|
| Map mode vs full `_GENERATORS` loop | When map present and not dry-run: **replace** the unconditional per-service full loop with planned actions only (FR-B3a). Without map: unchanged. |
| `--affordance-map-dry-run` vs existing `--dry-run` | **Reuse** `--dry-run` when map present (print plan, zero writes). Drop second flag (accidental complexity). |
| `--check` + `--affordance-map` | **Refuse** combination (NR-G8); check remains full-tree drift, map is targeted repair. |
| Service-id join | Local normalize mirroring CC `catalog_service_id` (FR-B6a); skip unknown after normalize. |
| OQ-G5 `--services` ∩ map | Intersect when both passed; empty intersection → no-op + log (exit 0). |
| OQ-G6 sidecar path | `{output_dir}/affordance_actions.json` (settled). |
| FR-B5 always-on vs map-only | Always-on heading alignment (Hayai); see §0.2. |
| CRP | Recommended (Design_Docs #24). |

---

## 1. Problem Statement

ContextCore Observability Audit Phase A emits an **AffordanceMap** (`gen.*` + `rex.*` + `measure.*`) from quality/reconcile/live gaps. Operators still must **manually** decide which generator actions to run. The startd8 generator already implements most `gen.*` behaviors but never reads the map — so gaps like RED-missing, skeletal runbooks, empty metric-coverage, and oversized dashboards persist after regenerate.

| Component | Current state | Gap |
|-----------|---------------|-----|
| CC `affordance_map` | Emitted in scorecard-json | Not consumed downstream |
| `_ensure_red_coverage` | Runs on generate for request-shaped services | No bias from `red_missing` map entries |
| Triplet generators | Unconditional per service | No selective leg repair from `triplet_incomplete` |
| Metric coverage | Scored + gated; domain panels exist | No worklist-driven fill from `metric_coverage_empty` |
| Runbooks | Generated + EXT-100 scored | Heading mismatch → false “skeletal”; no map-driven enrich |
| Dashboard `max_lines` | EXT-101 **check only** | No `gen.shrink_dashboard_lines` writer |
| Generator CLI | `--onboarding-metadata`, coverage mins, … | No `--affordance-map` |

**One-sentence goal:** given an AffordanceMap JSON from a ContextCore audit, the startd8 generator **optionally** performs **targeted** `gen.*` repairs for listed services — reusing existing synthesizers — without importing ContextCore or rewriting the whole tree.

---

## 2. Definitions

| Term | Meaning |
|------|---------|
| **AffordanceMap** | JSON list of `{element_id, gap_code, affordance_ids[], confidence?, provenance?}` as emitted by CC Phase A (or equivalent `gaps[]` with `affordance_ids`). |
| **`gen.*` affordance** | Generator-owned action id from parent FR-AFF-1. |
| **Targeted repair** | Regenerate or patch only the `(service_id, artifact_type)` pairs implied by selected affordances. |
| **Action plan** | Deterministic ordered list of `(service_id, affordance_id, artifact_types[], reason)` derived from the map. |
| **Known gen set** | Frozen: `gen.emit_red_panels`, `gen.complete_triplet`, `gen.improve_metric_coverage`, `gen.enrich_runbook`, `gen.shrink_dashboard_lines`. |

---

## 3. Requirements

### Placement

**FR-B0 — Sibling of Phase A; startd8-owned.**  
This REQ implements parent FR-AFF-3 for **`gen.*` only**. It MUST NOT move AffordanceMap emit into startd8, MUST NOT import `contextcore`, and MUST NOT consume `rex.*` / `measure.*` (defer).

### Load + schema

**FR-B1 — Optional AffordanceMap input.**  
`generate_observability_artifacts` (and `scripts/generate_observability_artifacts.py`) MUST accept optional `--affordance-map PATH` (or kwarg). Accepted shapes:
1. Raw array = `affordance_map` entries, or  
2. Scorecard-json object containing `affordance_map` (and optionally `gaps`).  

Default: **absent → ordinary full generate** (plus intentional FR-B5 runbook heading alignment). Malformed JSON → non-zero exit (or structured error); empty map → no-op with log. Unknown keys ignored. Unknown affordance ids logged and skipped (not invented). Fail-closed / join rules: **FR-B6 / FR-B6a**.

### Planner

**FR-B2 — Deterministic action planner.**  
From the map, produce an ordered **action plan** of repairs. Rules:
- Only `gen.*` ids in the known gen set.
- Index by `element_id` after **FR-B6a** normalization (= service id / catalog service id).
- Deduplicate identical `(service, affordance)` pairs.
- Stable sort: by affordance priority (below) then service name.

**Default priority (tunable constants):**  
`emit_red_panels` → `complete_triplet` → `improve_metric_coverage` → `enrich_runbook` → `shrink_dashboard_lines`  
(RED/triplet before shrink so shrink cannot erase newly added RED panels in the same plan — see FR-B4 ordering.)

**FR-B2a — Dry-run (reuse existing flag).**  
When `--affordance-map` is present and `--dry-run` is set, print the action plan and write **zero** artifact files (including no `affordance_actions.json` mutation of artifacts; a plan-only stdout dump is allowed). Do **not** add a second dry-run CLI verb.

**FR-B2b — Typed plan contract (Keiyaku).**  
`ActionPlanEntry` MUST be a typed dataclass (or Pydantic model) with at least: `service_id`, `affordance_id`, `artifact_types: list[str]`, `reason`, `gap_code?`, `confidence?`. Load/plan/apply boundaries pass these types — not ad-hoc dicts.

### Targeted execute

**FR-B3 — Targeted repair default.**  
When a map is present and dry-run is off, the generator MUST apply only planned actions. It MUST NOT rewrite artifacts for services with no matching `gen.*` entries. Full-tree regenerate remains available via existing entry points **without** a map (unchanged).

**FR-B3a — Map mode replaces full loop.**  
When `--affordance-map` is present, do **not** also run the unconditional per-service `_GENERATORS` / extended full-tree pass for all services. Map mode is a repair path, not “full gen then patch.” Quality report / sidecar still run for what was touched.

| Affordance | Required behavior |
|------------|-------------------|
| `gen.emit_red_panels` | Ensure `_ensure_red_coverage` (or equivalent) for that service’s dashboard; regenerate dashboard only if needed |
| `gen.complete_triplet` | Regenerate **missing or zero-score** legs only (alert / dashboard_spec / SLO) for that service |
| `gen.improve_metric_coverage` | Regenerate dashboard (± alerts) emphasizing uncovered expected metrics for that service |
| `gen.enrich_runbook` | Regenerate/patch runbook so contract `completeness_markers` are present |
| `gen.shrink_dashboard_lines` | Apply FR-B4 shrink to that service’s Grafana JSON |

**FR-B5 — Runbook marker parity (always-on).**  
Align `generate_runbook` headings with the scored contract markers (`Overview`, `Risks`, `Procedures`, `Escalation` — see test fixtures / onboarding contracts). This is an intentional always-on byte change (Hayai; pre-existing EXT-100 defect). Map-driven `enrich_runbook` then primarily fills remaining skeletal gaps beyond headings. Marker presence clears EXT-100; it does **not** by itself assert runbook operational quality (Obs #32).

**FR-B4 — Shrink without RED regression.**  
Implement dashboard line-budget respect using contract `max_lines` / EXT-101:
- Prefer dropping/condensing non-RED panels, duplicates, or verbose options before touching RED panels.
- After shrink, OBS-200a MUST still pass for request-shaped services that had RED completeness before the shrink (or the action is refused with reason).
- Shrink runs **after** RED/triplet/coverage actions in the same plan (FR-B2 priority).
- Dashboards in this path are generator-owned; shrink does not invent an authored-panel preservation layer (NR-G9).

**FR-B6 — Fail closed on ambiguity.**  
If `element_id` (after FR-B6a) does not match a known service in the generation context, skip that entry with an explicit skip reason (do not invent services). Confidence MAY be used as a filter (`--min-affordance-confidence`, default 0.0).

**FR-B6a — Service-id join rule.**  
Normalize map `element_id` with a **local** helper that mirrors ContextCore `catalog_service_id` at HEAD: if the id matches ENV_FORM (`^[A-Z][A-Z0-9_]*(?:_SERVICE)?$`), apply the same slug normalization CC uses; otherwise lowercase. Match against `ServiceHints.service_id` (already lowercased in practice). Document the rule in HOWTO; do not `import contextcore`.

**FR-B7 — Provenance / report.**  
When map-driven repairs run, emit `{output_dir}/affordance_actions.json` listing planned vs applied vs skipped (with reasons). Mottainai: do not re-emit a second quality scorer — existing `_write_quality_report` remains the quality SSOT.

**FR-B8 — Optional `--services` intersect.**  
If the CLI already filters by service list and a map is present, the effective target set is the **intersection**. Empty intersection → no-op with log; exit 0 (unless other errors).

### Non-Requirements

- **NR-G1** — Does NOT `import contextcore` or call the Observability Audit from the generator.
- **NR-G2** — Does NOT re-derive AffordanceMap from `observability-quality.json` when a map file is provided (map is the worklist).
- **NR-G3** — Does NOT use an LLM to choose or author repairs.
- **NR-G4** — Does NOT consume `rex.*` or `measure.*` affordances.
- **NR-G5** — Does NOT change Phase A emit schema or rename `gen.*` ids.
- **NR-G6** — Does NOT make AffordanceMap mandatory for ordinary generate.
- **NR-G7** — Does NOT silently full-regenerate the tree because a map was passed.
- **NR-G8** — Does NOT combine `--check` with `--affordance-map` (refuse with clear error).
- **NR-G9** — Does NOT build an authored-panel merge layer for shrink; generator-owned dashboards only.

---

## 4. Acceptance Criteria

| ID | Criterion |
|----|-----------|
| **AC-G1** | Without `--affordance-map`, generate path is unchanged **except** intentional FR-B5 runbook heading alignment (fixtures updated in same WP). No other new writes. |
| **AC-G2** | `--dry-run` with a fixture AffordanceMap prints the action plan and creates no artifact diffs. |
| **AC-G3** | Map with only `store` + `gen.emit_red_panels` regenerates at most store dashboard (other services untouched); full `_GENERATORS` loop does not run for untouchable services. |
| **AC-G4** | Map with `runbook_skeletal` (or always-on FR-B5) yields runbook containing contract markers; EXT-100 issues for those markers clear on rescore. Does **not** assert runbook operational quality beyond markers. |
| **AC-G5** | Map with `dashboard_oversize` shrinks lines to ≤ `max_lines` **or** refuses with RED-preservation reason; OBS-200a does not regress when shrink applies. |
| **AC-G6** | Unknown affordance id and unknown `element_id` are skipped with logged reasons; exit 0 if remaining actions succeed (all-skip after valid empty/filtered map = exit 0). |
| **AC-G7** | No `contextcore` import in startd8 observability package (grep gate). |
| **AC-G8** | Frozen fixture of CC scorecard-json `affordance_map` parses; known gen set asserted in unit tests. |
| **AC-G9** | `--check` + `--affordance-map` exits non-zero with clear error (NR-G8). |

---

## 5. Open Questions

| ID | Question | Status |
|----|----------|--------|
| **OQ-G5** | `--services` ∩ map? | **Resolved → FR-B8** (intersect when both; empty → no-op). |
| **OQ-G6** | Sidecar path? | **Resolved →** `{output_dir}/affordance_actions.json`. |
| **OQ-G7** | Scorecard-json vs slim array? | **Resolved → FR-B1** (accept both). |

_(No open questions remain for Phase 6.)_

---

## 6. Phasing

| Phase | Scope | Exit |
|-------|-------|------|
| **B0** | Schema loader + planner + `--affordance-map` CLI + `--dry-run` plan print; refuse `--check`+map | AC-G1 (modulo FR-B5), AC-G2, AC-G7, AC-G8, AC-G9 |
| **B1** | Targeted: RED, triplet legs, metric-coverage bias; FR-B5 always-on headings | AC-G3, AC-G4 |
| **B2** | Shrink pass (FR-B4) | AC-G5 |
| **B3** | Action report sidecar; HOWTO wiring | AC-G6 |

SIL-REX `rex.*` consume = separate REQ (not this document).

---

## 7. Reference Audit

| Symbol / check | Exists? | Notes |
|----------------|---------|-------|
| `_ensure_red_coverage` | Yes | `artifact_generator_generators.py` |
| OBS-200a / OBS-EXT-100 / OBS-EXT-101 | Yes | `observability_artifact_checks.py` |
| Unconditional triplet `_GENERATORS` | Yes | `artifact_generator.py` |
| `compute_metric_coverage` / `_write_quality_report` | Yes | quality JSON path |
| `generate_runbook` | Yes | emits `Service summary` / `First response`; contract wants Overview/Risks/Procedures/Escalation |
| `max_lines` contract field | Yes | scored, not enforced at write |
| CLI `--dry-run` / `--check` | Yes | `scripts/generate_observability_artifacts.py` |
| CC `catalog_service_id` / `AFFORDANCE_BY_GAP` | Yes (CC) | mirror join locally; do not import |
| `shrink_dashboard_lines` | **No** | FR-B4 to-be-created |
| AffordanceMap loader / `ActionPlanEntry` | **No** | FR-B1 / FR-B2b to-be-created |
| `import contextcore` in observability | **No** (must stay no) | AC-G7 |

---

## Appendix A: Settled Questions

| ID | Resolution |
|----|------------|
| OQ-G1 | `--affordance-map` optional; default off |
| OQ-G2 | Targeted repair default; map mode replaces full loop (FR-B3a) |
| OQ-G3 | Shrink preserves OBS-200a |
| OQ-G4 | `rex.*`/`measure.*` out of scope |
| OQ-G5 | Intersect with `--services` when both (FR-B8) |
| OQ-G6 | `{output_dir}/affordance_actions.json` |
| OQ-G7 | Accept scorecard-json or slim array (FR-B1) |

## Appendix B: Rejected Suggestions

| Idea | Why rejected |
|------|----------------|
| Import CC catalog module | Reverses dependency direction |
| Full regen when any map entry present | Thanos-scale thrash; NR-G7 |
| LLM enrich runbooks | Violates Hitsuzen; marker parity first |
| Re-derive gaps from quality inside generator when map present | Mottainai; map is worklist |
| Second `--affordance-map-dry-run` flag | Accidental complexity; reuse `--dry-run` |
| Hybrid `--check`+map semantics | Accidental complexity; refuse (NR-G8) |
| Map-only FR-B5 (defer heading fix) | Violates Hayai; generator fails its own contract |

## Appendix C: Incoming Suggestions (Untriaged)

_(empty)_

---

*v0.3.2 — Architect re-validation: consulted real Lessons_Learned base; closed Sotto/Hayai, Keiyaku, Warm Up, dry-run/`--check`/map-mode ambiguities. CRP recommended (write-through-existing surface). Ready for CRP review.*

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
