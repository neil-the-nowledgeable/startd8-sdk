# Convergent Review Prompt

**Generated:** 2026-07-03 03:37:20 UTC
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
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/requirements-panel/REQUIREMENTS_PANEL_PLAN.md` | 169 lines · 1560 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/requirements-panel/REQUIREMENTS_PANEL_REQUIREMENTS.md` | 321 lines · 3173 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/requirements-panel/crp-focus-requirements-panel.md` | 45 lines · 438 words |

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

# CRP Focus — Requirements Panel

## Where we need review most (least-reviewed target)

Both docs (`REQUIREMENTS_PANEL_REQUIREMENTS.md` v0.3, `..._PLAN.md` v0.1) are **brand new**. Weight on:

1. **The bucket-4 boundary (P1).** Is "estimate-provenance candidate requirements for human approval"
   a *real* boundary, or does drafting *requirements* inherently cross into authoring product intent
   the SDK shouldn't own? Is the provenance + human-approve-only floor sufficient, or does the mere act
   of a persona proposing an FR constitute bucket-4 authorship?
2. **The project-grounding guard (FR-RP-4).** Planning found the panel's `unsupported_specifics` grounds
   against the *persona's* brief and is *suppressed* for estimates. Is the owned brief+schema variant
   sound — will the money/percent/temporal extractors, tuned for scalar value answers, behave on longer
   requirement prose? Is advisory-then-CRP the right severity, or should any grounding class hard-block?
3. **The synthesis pass (FR-RP-3).** This is the least-deterministic step. Is "dedupe + stable IDs +
   order + conflicts→Open-Questions" enough, or does multi-role→one-doc need more structure? Does the
   R2-S1 "assemble whole, never per-item overwrite" discipline actually hold for a markdown doc?
4. **CRP as the second gate (FR-RP-6, P6).** The loop generates a draft that CRP then reviews — is that
   a clean gate, or a circularity risk (a generator whose only correctness check is the same review it
   feeds)? Should there be a deterministic pre-CRP readiness check (OQ-RP-8)?
5. **Value vs cost.** Is the `$0` persona-less baseline (schema+brief scaffold) worth it, or is all the
   value in the paid role pass? Is the paid elicitation better than a single author + CRP (which already
   exists)?

## Settled — do NOT relitigate

- **P1 scope lock** — estimate-drafts-for-approval, human is the sole promotion gate; NOT an authority
  on product intent. "Accept as-generated" changes edit burden, not the gate.
- **Not fused into the Stakeholder Panel** (NR-RP-1) — separate capability/CLI; the panel stays
  scalar-value-only.
- **No new proposal kind / grammar** (NR-RP-3) — approve is a markdown file-write; CRP is the gate.
  (Requirements have no `manifest`-style apply kind and need none — planning-verified.)
- **Own package + `elicit`** (overloaded-term lesson) — not a third meaning on `recommend`/`suggest`.
- **Reuse persona/routing/roster/`ProposalStore`/`panel.ask`/telemetry; own draft/synthesis/grounding/
  apply** (planning-settled; the grounding guard and apply-kind reuse were both falsified).
- **Three Manifest-Suggester findings already baked in** — do not re-derive: R2-S1 (synthesis, no
  overwrite → FR-RP-3), R3-S1 (heading sanitization → FR-RP-7), R1-S1 (`panel.ask` not bare
  `Persona.ask` → FR-RP-2).

## Dual-doc coverage ask

Confirm every FR-RP-* maps to a plan step (the plan's self-check matrix claims Full on all 9 — verify),
and that §7 Validation (bucket boundary, dual grounding, no-silent-overwrite, sanitization, reuse-not-
fork, panel-isolation) actually proves the requirements. Flag any FR whose acceptance criterion is
untestable as written.

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/requirements-panel/REQUIREMENTS_PANEL_PLAN.md`  ·  **Size:** 169 lines · 1560 words

```markdown
# Requirements Panel — Implementation Plan

**Version:** 0.1
**Date:** 2026-07-02
**Requirements:** `REQUIREMENTS_PANEL_REQUIREMENTS.md` (v0.3)
**Branch:** `feat/requirements-panel-spec` (design-only; code lands on a later `feat/requirements-panel`).

---

## Planning discoveries (fed the reflection pass)

| What v0.1 assumed | What planning (live-code read) revealed | Impact |
|-------------------|-----------------------------------------|--------|
| `grounding_guard.unsupported_specifics` grounds against the project brief | `grounding_guard.py:81-89` — `_brief_corpus` is `goals+constraints+known_positions+display_name` of **the persona's own brief**. It grounds a persona's answer against *that persona's* stated positions, not the project. | **FR-RP-4 owns `ground_requirement`** with a **project corpus** (problem-statement brief + schema entity/field names), reusing only the guard's `extract_money`/`extract_percent` (publicly exported at `grounding_guard.py:68-69`) + a temporal extractor. |
| A drafted requirement, being an estimate, should suppress the specifics check like values do | `recommend.py:130-133` — comment: *"Do NOT carry the reactive unsupported-specifics flags — an estimate is expected to introduce a value the brief never stated."* Only `check_contradiction` runs on value drafts. | **Requirements invert this**: a fabricated `"40% faster"` **is** the failure. FR-RP-4 **runs** the specifics check; the estimate-suppression rationale does not apply to intent prose. |
| Approve reuses the `manifest` proposal kind (Manifest-Suggester template) | No requirements shape in `kickoff_experience/proposals.py:PROPOSAL_KINDS`; requirements are markdown in `docs/design/`, not a `CONVENTION_PATHS`-mapped manifest. | **FR-RP-6 apply = CLI markdown file-write** at human privilege; **CRP is the second gate**. No `PROPOSAL_KINDS` change (NR-RP-3). |
| `input_domains.py` is the "what to draft" layer to reuse | `input_domains.py:79-101,208-248` models **scalar YAML `FieldSlot`s** (dotted keys, composite `{target,why}`); requirements units are prose sections/FR-classes. | **FR-RP-1 owns `RequirementDomain`** — the *structural analogue* of `DomainSpec` (area name, owning role, prompt template, grounding hooks), not a reuse. `resolve_owner`/`route` **are** reusable as-is (they key on a symbol string). |
| Personas draft, then each draft is applied one at a time | The Manifest-Suggester's just-triaged **R2-S1** proved a per-item apply against a shared artifact clobbers prior entries. A requirements doc has the same property. | **FR-RP-3 owns a synthesis pass** that assembles the whole doc once; approve writes the assembled doc, not N incremental splices. |

**Net:** the loop killed the "reuse the guard + reuse an apply kind" shortcuts (both architecturally
wrong on inspection) and sharpened the capability to **owning** a project-grounding guard, a
`RequirementDomain` descriptor, a synthesis pass, and a file-write+CRP apply — while genuinely reusing
persona/routing/roster/store/`panel.ask`/telemetry.

---

## Approach & step map

### Step 1 — The requirements-domain model + `$0` baseline (FR-RP-1)
- New `src/startd8/requirements_panel/` package. `domains.py`:
  - `RequirementDomain{area, owning_role, prompt_template, grounds_on: {brief, schema}}` — the
    section/FR-class → owning-role map (structural analogue of `input_domains.DomainSpec`).
  - A default registry: `problem`, `data` (entity-touching FRs), `ux`, `ops`, `security`, `compliance`.
- `baseline.py`: `scaffold(brief, schema_text) -> RequirementDoc` — deterministic (`$0`) Problem gap
  table + one entity-touching FR **stub** per primary entity (via `languages/prisma_parser`), standard
  `## Non-Requirements` / `## Open Questions` headings, unfilled areas marked `<needs-owner>`. **No LLM.**

### Step 2 — Project-grounding guard (FR-RP-4, owned — NOT the panel's)
- `grounding.py`: `ground_requirement(candidate, project_corpus, schema) -> Ok|Flag(reasons)`.
  - `project_corpus` = brief text + declared entity/field names.
  - Reuse `grounding_guard.extract_money`/`extract_percent`; add `extract_temporal`; flag any
    money/percent/date specific not in the corpus, and any entity/field reference absent from the schema.
  - Advisory (flag + soften), never a hard block (P3); CRP is authoritative.

### Step 3 — Role-informed drafting (FR-RP-2, reuse `panel.ask`/`routing`)
- `elicit.py`: `async elicit_requirements(package_root, panel, brief, schema, *, domains=None, cap=None,
  session_id=None) -> ElicitationRun` — **mirror `recommend_inputs`'s signature/flow**
  (`recommend.py:164`): enumerate domains → `routing.route(briefs, area)` / bounded `resolve_owner`
  → budget-preflight the resolved+capped set → `await panel.ask(owner, drafting_prompt, value_path=area)`
  → skip `UNAVAILABLE`/`DEFERRED` (never fabricate) → run Step 2 grounding → stage `RequirementCandidate`s
  (`estimate` provenance). Prompt carries **brief + literal declared entity names** (Manifest-Suggester
  R2-S3/R2-F3). Under a parent span `requirements.elicit_pass` (reuse `telemetry.span`, mirror
  `stakeholder.recommend_pass`). Paid; the Step-1 `$0` baseline runs without it.

### Step 4 — Sanitization (FR-RP-7, before synthesis)
- `sanitize.py`: `neutralize_headings(text) -> text | Reject` — scan every candidate free-text field for
  `^#{2,4}\s`; reject the candidate (preferred) or demote the line to a blockquote, so no injected
  section reaches the assembled doc or the later CRP appendix. (Manifest-Suggester R3-S1.)

### Step 5 — Synthesis pass (FR-RP-3, owned)
- `synthesis.py`: `synthesize(baseline, candidates) -> RequirementDoc` — dedupe near-identical FRs
  across roles (slug/normalized text), assign stable `FR-<AREA>-<n>` IDs, order by area, lift cross-role
  conflicts into `## Open Questions` (never drop silently). Emits the **whole** doc (R2-S1 discipline).

### Step 6 — draft → review → approve loop + store (FR-RP-8, mirror the panel)
- `store.py` stages the run out-of-band — **mirror `ProposalStore`'s shape** (atomic `mkstemp`+`os.replace`,
  `sort_keys`+`indent=2`, session GC, `_safe_session_component` traversal guard). CLI
  `cli_requirements.py` (`startd8 requirements`): `elicit` (`$0` baseline + optional `--roles`) ·
  `synthesize` (`$0`) · `review` (`$0` render of the **literal** doc bytes that approve would write —
  Manifest-Suggester R3-S2) · `approve`/`reject` → `apply.py` writes the markdown file at human
  privilege + prints the CRP hand-off command (FR-RP-6). Stale-session refuse (no clobber).

### Step 7 — CRP hand-off + reflective-loop discoverability (FR-RP-6/9)
- `approve` emits the ready-to-run `/new-cnvrg-rvw-prmpt --plan … --requirements …` invocation (dual-doc)
  and a one-line pointer from the `reflective-requirements` entry point / Concierge "no reqs doc" gap.

### Step 8 — Tests
- `$0` baseline: brief+schema → a scaffold with an entity-touching FR stub per primary entity, no
  invented intent (all `<needs-owner>`), **no LLM call**.
- Grounding: a candidate asserting `"$2M ARR"` unsupported by the brief is flagged; an FR naming a
  non-existent entity is flagged; a supported specific passes.
- Panel reuse: `elicit_requirements` goes through `panel.ask` (cost/transcript/span recorded), never a
  bare `Persona`; un-owned area → skipped, never a loose match.
- Sanitization: a candidate whose rationale contains `### Non-Requirement:` is rejected/neutralized
  before synthesis; the assembled doc has only intended headings.
- Synthesis: two roles drafting the same FR → one deduped entry; a cross-role conflict → an Open
  Question, never a silent drop; approving assembles the **whole** doc (both roles' FRs present).
- Apply: approve writes the markdown at the target path at human privilege; a pre-existing target →
  stale-refuse, no clobber; the CRP hand-off command is printed.

---

## §7 Validation Strategy
- **Bucket boundary (P1):** a test asserts every drafted candidate + the synthesized doc carry
  `estimate`/`$0`-baseline provenance and that approve requires an explicit human action (no
  auto-approve path exists).
- **Dual grounding (P3):** brief-only and schema-only fixtures each catch their class of fabrication;
  a doubly-supported specific passes both.
- **No-silent-overwrite (R2-S1):** synthesizing/approving N role contributions yields all N in the
  final doc, never just the last.
- **Sanitization (R3-S1):** injected `##`/`####` lines never survive into the assembled doc or the CRP
  appendix scaffold.
- **Reuse-not-fork:** `elicit_requirements` imports `panel`/`routing`/`ProposalStore` but adds no value
  domain and no proposal kind; `PROPOSAL_KINDS` unchanged.
- **Panel-isolation (NR-RP-1):** the stakeholder-panel value pass is untouched.

## Risks
- **R1 — Grounding false-positives/negatives on prose.** The specifics extractors were tuned for scalar
  value answers; requirement prose is longer. Mitigation: advisory-only (P3) + CRP as authoritative
  gate; tune the temporal extractor conservatively (the guard already drops bare month words for this
  reason — `grounding_guard.py:39-46`).
- **R2 — Synthesis quality (the hard LLM step).** Merging multi-role drafts into a coherent doc is the
  least-deterministic step. Mitigation: keep synthesis mechanical where possible (dedupe/ID/order are
  `$0`); only conflict-framing needs judgment, and unresolved conflicts degrade to Open Questions, not
  silent choices.
- **R3 — Scope creep past bucket-4.** The capability could drift toward "writing the real requirements."
  Mitigation: P1 scope lock + provenance on every unit + human-approve-only + CRP second gate.
- **R4 — Roster coupling.** Mitigation: reuse `persona`/`routing`/`roster` only (generic); ship a
  default requirements roster (OQ-RP-7) keyed on FR-area `answers_for`, no new roster grammar.

---

## Requirements Coverage (self-check, pre-CRP)

| Requirement | Plan Step(s) | Coverage |
|-------------|-------------|----------|
| FR-RP-1 (`$0` baseline) | Step 1 | Full |
| FR-RP-2 (role drafting via `panel.ask`) | Step 3 | Full |
| FR-RP-3 (synthesis, no overwrite) | Step 5 | Full |
| FR-RP-4 (project-grounding guard) | Step 2 | Full |
| FR-RP-5 (provenance) | Steps 3, 5 | Full |
| FR-RP-6 (file-write apply + CRP gate) | Steps 6, 7 | Full |
| FR-RP-7 (heading sanitization) | Step 4 | Full |
| FR-RP-8 (elicit→synthesize→review→approve loop) | Step 6 | Full |
| FR-RP-9 (discoverable from reflective loop) | Step 7 | Full |

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to
Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or
Appendix B (rejected with rationale). **Do not delete A/B** — cross-model memory.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items
  already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest
  existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: list agreements in an **Endorsements** section.
- **When validating (orchestrator)**: append a row to Appendix A (applied) or Appendix B (rejected).
- **If rejecting**: record **why** (specific rationale).

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

*(No review rounds yet.)*
```

---

## Document Under Review: Requirements

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/requirements-panel/REQUIREMENTS_PANEL_REQUIREMENTS.md`  ·  **Size:** 321 lines · 3173 words

```markdown
# Requirements Panel — Requirements

**Version:** 0.3 (Post lessons-learned hardening)
**Date:** 2026-07-02
**Status:** Draft
**Owner:** neil-the-nowledgeable
**Plan:** `REQUIREMENTS_PANEL_PLAN.md`
**Extends / reuses (cite, don't duplicate):** the **Stakeholder Panel** persona machinery
(`stakeholder_panel/` — `persona.Persona`, `panel.StakeholderPanel.ask`, `routing.route`,
`roster.py`, `proposals.ProposalStore`, `telemetry.span`, the recommend→review→approve *pattern*),
the **Manifest Suggester** design (`../kickoff/MANIFEST_SUGGESTER_{REQUIREMENTS,PLAN}.md` — the
"role-based agents draft a prose artifact for approval" sibling), the **CRP** workflow
(`convergent-review` → `architectural-review-log`, `workflows/builtin/`), `languages/prisma_parser`
(schema grounding), the **`reflective-requirements`** skill (the loop this capability automates), the
**four-bucket separation** in `CLAUDE.md`.

> **What this is.** A **persona-driven requirements *drafting* capability** that simulates a
> stakeholder elicitation session: role-based agents (end-user, PM, ops, security, compliance,
> sponsor) each draft candidate requirements from their vantage, a synthesis assembles a coherent
> **draft requirements document**, and a human stakeholder **approves** it. It is the **third sibling**
> in the pattern — after the Stakeholder Panel (drafts scalar *value-inputs*) and the Manifest
> Suggester (drafts *screens*), this one drafts *requirements prose*. It answers "**what should we
> even be building, and what did each stakeholder forget to say?**" — the elicitation the
> `reflective-requirements` loop does by hand today.

> **What this is NOT.** It does not *decide* what the product must do. Its output is
> **estimate-provenance candidate requirements** the human owns and accepts, edits, or discards. See
> **P1 (scope lock)** — this is the load-bearing boundary.

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass (reading the live `stakeholder_panel/` code) falsified **four** first-draft
> assumptions — the two grounding ones and the "there's an apply kind" one are load-bearing. This is
> the loop working: >30% of the naive reuse plan changed at document cost, not refactor cost.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| Reuse `grounding_guard.unsupported_specifics` as the brief/schema grounding gate | `grounding_guard.py:81-89` grounds specifics against the **persona's own brief corpus** (`goals`/`constraints`/`known_positions`/`display_name`) — **not** a project brief or schema. | **FR-RP-4 owns a project-grounding variant** (`ground_requirement`) that grounds against the **problem-statement brief + parsed schema**, reusing the guard's money/percent/temporal **extractors** (`extract_money`/`extract_percent`, publicly exported) but its **own corpus**. |
| A drafted requirement is an estimate, so treat it like `recommend.py` does | `recommend.py:130-133` **deliberately suppresses** `unsupported_specifics` for value estimates (only `check_contradiction` fires) because a scalar estimate is *expected* to introduce a value the brief never stated. | **Requirements are the inverse:** a fabricated specific (`"40% faster"`, `"$2M ARR"`) with no brief/schema support **is** the failure mode. FR-RP-4 must **run** the specifics check (not suppress it) and flag/soften unsupported specifics. |
| Reuse the `manifest` proposal kind for apply (like the Manifest Suggester) | There is **no "requirements" proposal kind** anywhere (`kickoff_experience/proposals.py` `PROPOSAL_KINDS` has no requirements-doc shape); requirements are a free markdown doc in `docs/design/`, not a grammar-gated manifest. | **FR-RP-6 apply = a plain markdown file-write at human privilege** (no new proposal kind); the **second gate is CRP** (`convergent-review`), not an extractor round-trip. |
| `input_domains.py` models the "what to draft" layer directly | It models **scalar YAML field-slots** (dotted keys, composite `{target,why}` rows); requirements units are **prose sections / FR-classes**, not YAML keys. | **FR-RP-1 owns a `RequirementDomain` descriptor** (the section/FR-class → owning-role map) — the *structural analogue* of `DomainSpec`/`FieldSlot`, not a reuse of it. |

**Resolved open questions:** OQ-1 → the drafting unit is a **requirement section / FR-class**
(Problem, per-area FR blocks, NRs, OQs), routed by an `answers_for`-named area symbol (`security`/
`ops`/`data`/…). OQ-2 → **synthesis is an explicit owned step** (personas draft per-area units → a
synthesis pass assembles one coherent doc → human approves the whole), never a silent per-item
overwrite (mirrors Manifest-Suggester R2-S1). OQ-3 → **reuse** persona/routing/roster/`ProposalStore`/
`panel.ask`/telemetry; **own** the requirements-shaped draft/synthesis/grounding/apply. OQ-4 → the
**second gate is CRP**; the loop *generates* a draft that CRP then *reviews* and the orchestrator
*triages* — closing a generate→review→triage loop that dogfoods `reflective-requirements` itself.
OQ-5 → the `$0` baseline is a **deterministic template + schema scaffold** (problem table, entity-
touching FR stubs, standard NR/OQ headings), the persona-less alternative. OQ-6 → dedupe/merge is the
synthesis pass's job (§ FR-RP-3).

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied the SDK design-docs lessons + the *shipped* Manifest-Suggester CRP findings (its R1–R3,
> just triaged) before CRP. Each changed the draft:

- **[Phantom-reference audit]** — every cited symbol grepped in `stakeholder_panel/` and verified (see
  §Reference-Audit); new symbols marked *to-be-created*. Caught the two grounding-guard corrections
  (§0) — the guard does **not** do what a name-level read implied.
- **[Prune phantom scope]** — the "reuse the `manifest` apply kind" line was architecturally wrong
  (no such kind for requirements) → moved to §0 and NR-RP-3; apply is a file-write + CRP gate.
- **[Overloaded-term co-location]** — the Stakeholder Panel **owns `recommend`** (value scalars) and
  the Manifest Suggester owns `suggest` (screens). This capability lives in its **own package
  `requirements_panel/`** and names its pass **`elicit`** (`startd8 requirements elicit`) — it does
  **not** stack a third meaning onto `recommend`/`suggest`.
- **[Single-source vocabulary ownership]** — persona/roster/routing/provenance vocabulary is **owned
  by `stakeholder_panel`** (cited, non-normative snapshot here); the requirements-doc grammar
  (`## Problem`/`### FR-*`/`## Non-Requirements`/`## Open Questions`) is the **`reflective-requirements`
  skill's** convention (cited). This doc **owns only** its new vocabulary — *requirements panel*,
  *requirement candidate*, *elicitation session*, *synthesis pass*, *requirement domain*.
- **[Carry the Manifest-Suggester CRP findings forward]** — three of its just-accepted findings
  transfer directly and are pre-baked here so CRP need not re-derive them: **the whole-doc
  accumulation gap** (its R2-S1 → our FR-RP-3 synthesis, no per-item overwrite), **heading-injection
  sanitization** (its R3-S1 → our FR-RP-7, since persona free-text becomes a markdown doc CRP later
  parses by `##`/`####` headings), and **`panel.ask` not bare `Persona.ask`** (its R1-S1 → our
  FR-RP-2, for cost/telemetry/transcript).
- **[CRP steering]** — brand-new doc (least-reviewed) → CRP target. Settled (focus file): P1 scope
  lock (estimate-drafts-for-approval, not authority), CRP-as-second-gate, panel-isolation (NR-RP-1),
  own-package/`elicit` naming.

### Reference-Audit

| Symbol | Owning module (verified present) |
|--------|----------------------------------|
| `Persona` / `Persona.ask(question, *, value_path="")` | `stakeholder_panel/persona.py` |
| `StakeholderPanel.ask(role_id, question, *, value_path="")` / `.ask_all` / `.preflight_budget` / `.briefs` / `span`/`_record_cost`/transcript | `stakeholder_panel/panel.py` |
| `route(briefs, value_path, claim="")` / `persona_matches` | `stakeholder_panel/routing.py` |
| `parse_roster` / `load_roster` / `validate_roster` (`domain: stakeholders`) | `stakeholder_panel/roster.py` |
| `PersonaBrief` (`role_id`,`goals`,`constraints`,`known_positions`,`out_of_scope`,`answers_for`) / `Recommendation` / `Grounding` | `stakeholder_panel/models.py` |
| `ProposalStore(project_root, session_id)` (atomic write, `sort_keys`+`indent=2`, `latest_session`/`session_ids`/`gc_stale_proposals`, `_safe_session_component`) | `stakeholder_panel/proposals.py` |
| `unsupported_specifics` / `extract_money` / `extract_percent` (extractors reusable; **corpus is persona-brief-scoped**) | `stakeholder_panel/grounding_guard.py` |
| `check_contradiction` | `stakeholder_panel/contradiction_guard.py` |
| `span` / `_stamp_span` (`stakeholder.recommend_pass` precedent) | `stakeholder_panel/telemetry.py`, `recommend.py` |
| `convergent-review` / `architectural-review-log` workflows (the second gate) | `workflows/builtin/{convergent_review,architectural_review_log}_workflow.py` |
| schema parse (entities/relations) | `languages/prisma_parser.py` |

*New (to-be-created): `requirements_panel/` (`domains.py`, `elicit.py`, `synthesis.py`,
`grounding.py`, `sanitize.py`, `baseline.py`, `store.py`, `apply.py`), `RequirementDomain`,
`RequirementCandidate`, `startd8 requirements` CLI.*

---

## 1. Problem Statement

The `reflective-requirements` loop (draft → plan → reflect → harden → CRP) is high-value but **entirely
hand-driven**: a single author writes v0.1 alone, and the "stakeholder perspectives" (security, ops,
compliance, the end-user) are simulated only implicitly, in one head. There is no capability that
**elicits** a first draft the way a real requirements workshop would — many roles contributing in
parallel, then synthesized.

| Component | Current state | Gap for a requirements elicitor |
|-----------|--------------|---------------------------------|
| **`reflective-requirements` skill** | A human author writes v0.1, plans, reflects, hardens; CRP reviews. | No **generative** first-draft step. v0.1 is a blank page; missing-perspective gaps surface only later, in CRP. |
| **Stakeholder Panel** (`recommend_inputs`) | Personas draft **scalar value-inputs** into 3 fixed domains (`estimate` provenance, approve-gated). | Drafts *values*, not *requirements prose*. No section/FR-class drafting, no synthesis into a doc. |
| **Manifest Suggester** (design-only) | Personas draft **screens** (pages/views prose), grounded in schema, applied via the `manifest` kind. | Drafts *structure*, not *intent*. Blessed template but a different artifact + apply seam. |
| **CRP** (`convergent-review`) | Multi-round **review** of an *existing* requirements+plan doc; appends to Appendix C; orchestrator triages. | **Review-only** — critiques a doc that must already exist. Nothing generates the doc it reviews. |
| **Schema** (`prisma/schema.prisma`) | The entities the app stores. | A deterministic grounding source for data-touching FRs — unused for drafting requirements. |

**What should exist:** a **persona-driven elicitation capability** that (a) deterministically (`$0`)
scaffolds a requirements **baseline** from the brief + schema, (b) lets **stakeholder roles** each
draft **candidate requirements** in the areas they own (security → security FRs, ops → ops/validation
FRs, end-user → UX FRs, …), (c) **synthesizes** the contributions into one coherent draft, grounded in
the brief + schema, and (d) runs a **draft → review → approve** loop whose output is a markdown
requirements doc the human confirms — then hands straight to **CRP** as the external second gate.
It never authors the *real* product intent (bucket-4); it produces a **starting draft**.

---

## 2. Guiding Principles

- **P1 — Scope lock: draft-for-approval, never authority (bucket boundary).** Requirements express
  *what the company wants built* — near bucket-4. This capability produces **estimate-provenance
  candidate requirements** the human **owns and approves**; it is an **elicitation simulator / starting
  draft generator**, never the source of truth for what the product must do. "High enough quality to
  accept as-generated" changes the **edit burden**, never whether the human approval gate exists. Every
  candidate carries a provenance marker; no requirement is silently promoted.
- **P2 — Mirror the panel *pattern*, own the engine.** Same role-based *draft → synthesize → review →
  approve* loop and provenance discipline, but a **separate** capability/CLI and a **different artifact**
  (a requirements markdown doc, grounded by brief+schema, gated by **CRP** — not a scalar splice, not an
  extractor round-trip).
- **P3 — Dual grounding (brief + schema).** Every drafted requirement is grounded **twice**: intent
  against the **problem-statement brief**, and any data-touching specific against the **parsed schema**.
  A requirement asserting an unsupported money/percent/date specific, or naming a non-existent entity,
  is **flagged/softened** before synthesis (P3 is advisory-then-CRP, not a hard block — CRP is the
  authoritative gate).
- **P4 — Propose, then human-apply (inherited floor).** The loop drafts and synthesizes; the human
  approves; the durable write is a plain markdown file at human privilege. The loop never writes a
  final doc unprompted; MCP read/preview-only (CLI is the sole writer, per the Concierge precedent).
- **P5 — Reuse, don't reimplement.** persona/routing/roster/`ProposalStore`/`panel.ask`/telemetry all
  exist and are CRP-hardened — this adds *sequencing, a requirements-domain descriptor, synthesis,
  project-grounding, and CRP hand-off*, not new persona/panel engines.
- **P6 — Dogfood the loop.** The capability *generates* a draft that `reflective-requirements`'s own
  CRP step then *reviews* and the orchestrator *triages* — the same generate→review→triage loop it
  automates, run on its own output.

---

## 3. Requirements

### A. Elicit candidate requirements

- **FR-RP-1 — `$0` deterministic baseline (persona-less, schema+brief grounded).** From the brief +
  on-disk schema, deterministically scaffold a **requirements baseline**: a Problem-Statement gap table,
  an **entity-touching FR stub per primary entity** (grounded in `prisma_parser`), and the standard
  `## Non-Requirements` / `## Open Questions` headings. This is the **"manifest suggester without a
  designated persona"** alternative the sponsor raised — always cheap, always safe, lower value; it runs
  with **no LLM**. It never invents intent — stubs are marked `<needs-owner>` placeholders.
- **FR-RP-2 — Role-informed drafting (paid, opt-in), via `StakeholderPanel.ask`.** For each requirement
  **domain** (§FR-RP-1's areas + roster-owned areas), route to the owning persona via `routing.route`
  and draft candidate requirements through **`StakeholderPanel.ask(role_id, prompt, value_path=area)`**
  — **not** a bare `Persona.ask` (which bypasses cost tracking, transcript, budget preflight, and OTel
  spans; verified `panel.py` vs `persona.py`). Routing is **bounded** like the panel: the owning role
  for the area if present, else a high-confidence `answers_for` match, else **skip the area** — never a
  loose assignment. The drafting prompt carries the **brief + the literal declared entity names** (so a
  data-touching FR references real entities verbatim).
- **FR-RP-3 — Synthesis pass (assemble one coherent doc; no silent overwrite).** A dedicated
  **synthesis** step merges every approved-for-synthesis candidate into **one** requirements document:
  dedupe near-identical FRs across roles, assign stable `FR-<AREA>-<n>` IDs, order by area, and resolve
  cross-role conflicts into an **Open Question** (never by dropping one silently). This is the analogue
  of the Manifest-Suggester's accepted **R2-S1 accumulation finding** — the artifact is assembled whole,
  not clobbered one candidate at a time.

### B. Grounding & safety

- **FR-RP-4 — Project-grounding guard (brief + schema; owned, not the panel's).** A **`ground_requirement`**
  check grounds each candidate against **the project brief corpus + the parsed schema** (not the
  persona's own brief). It **reuses** `grounding_guard.extract_money`/`extract_percent` (+ a temporal
  extractor) but with a **project corpus**, and — unlike `recommend.py` — it **runs** the
  unsupported-specifics check (a fabricated `"40% faster"`/`"$2M ARR"` with no brief/schema support is
  flagged). A data-touching FR naming an entity/field absent from the schema is flagged. Effects are
  **advisory** (flag + soften), with CRP as the authoritative gate (P3).
- **FR-RP-5 — Provenance, never silently promoted.** Every candidate and the synthesized doc carry a
  **provenance** marker (`$0`-baseline vs `estimate`-role-drafted, with role_id + model + session), so an
  AI/role-drafted requirement is never indistinguishable from a human-authored one; human approval is the
  sole promotion gate (P1/P4). Reuse the panel's `ESTIMATE_PROVENANCE`/`panel_origin` stamping shape.
- **FR-RP-6 — Approve = markdown file-write at human privilege + CRP hand-off (no new proposal kind).**
  An approved synthesized draft is written to `docs/design/<feature>/<FEATURE>_REQUIREMENTS.md` (v0.1)
  by the **CLI** (sole writer), then the loop **offers CRP** (`/new-cnvrg-rvw-prmpt` dual-doc) as the
  external second gate. There is **no** requirements proposal/grammar kind (unlike the Manifest
  Suggester); the durable write is a plain file, the gate is CRP.
- **FR-RP-7 — Heading-injection sanitization (before synthesis and write).** Every persona free-text
  field is scanned for a line matching `^#{2,4}\s` (a markdown heading) before it enters the synthesized
  document; such lines are **rejected or neutralized** so a persona cannot smuggle an unreviewed
  `## Non-Requirement` / `#### Review Round` / `## Appendix` section into the doc (which would corrupt
  both the requirements structure and the **CRP appendix scaffold** the doc is later handed to). This is
  the Manifest-Suggester's accepted **R3-S1** finding applied to this project's markdown surface.

### C. The loop & surface

- **FR-RP-8 — draft → synthesize → review → approve (mirror the panel *pattern*, own the engine).** A
  **separate** CLI surface (`startd8 requirements`): `elicit` (`$0` baseline + optional `--roles` paid
  pass), `synthesize` (`$0` assemble), `review` (`$0` render of the **literal** doc that would be
  written), `approve`/`reject` (→ file-write + CRP offer). Staged out-of-band in `store.py` (mirror
  `ProposalStore`'s shape). A stale session (the target doc was created meanwhile) is detected and the
  approve refuses rather than clobbering.
- **FR-RP-9 — Discoverable from the `reflective-requirements` entry point.** When a user invokes the
  reflective loop (or the Concierge surfaces a "no requirements doc yet" gap), point at
  `startd8 requirements elicit` as the guided way to produce v0.1 — so the capability is discoverable at
  the moment of need. Presentation-only.

---

## 4. Non-Requirements

- **NR-RP-1 — Not fused into the Stakeholder Panel's value pass.** Separate capability, separate CLI;
  the panel stays scalar-value-only (its clean abstraction is preserved).
- **NR-RP-2 — Not the source of product truth (bucket-4).** It drafts *candidate* requirements for human
  approval; the *real* intent is the user/company's (P1). It is not an autonomous product manager.
- **NR-RP-3 — No new proposal kind / grammar / write engine.** Approve is a plain markdown file-write;
  no `PROPOSAL_KINDS` addition, no extractor. (Contrast the Manifest Suggester, which rides the
  `manifest` kind — requirements have no such kind and need none.)
- **NR-RP-4 — Does not replace CRP.** It *generates* the draft CRP reviews; CRP remains the external
  second gate and is not reimplemented here.
- **NR-RP-5 — Not a planning/implementation generator.** It drafts *requirements*, not the plan
  (`implementation_engine`) or code (Prime/Micro-Prime). The plan is the reflective loop's Phase 2.
- **NR-RP-6 — Not autonomous.** The loop never writes a final doc unprompted; every doc is a
  human-approved, provenance-marked draft.
- **NR-RP-7 — Not polyglot-specific.** Grounds against the Python-path `prisma` schema; the drafted
  requirements are language-neutral prose.

---

## 5. Open Questions

*The 6 v0.1 OQs were resolved by the planning pass — see §0. Remaining for CRP:*

- **OQ-RP-1 — RESOLVED** → drafting unit = requirement **section / FR-class**, routed by an
  `answers_for`-named area symbol.
- **OQ-RP-2 — RESOLVED** → synthesis is an **owned step**; the doc is assembled whole (no per-item
  overwrite).
- **OQ-RP-3 — RESOLVED** → reuse persona/routing/roster/store/`panel.ask`/telemetry; own
  draft/synthesis/grounding/apply.
- **OQ-RP-4 — RESOLVED** → the second gate is **CRP**; the loop generates → CRP reviews → triage.
- **OQ-RP-5 — RESOLVED** → `$0` baseline = deterministic template + schema scaffold (persona-less).
- **OQ-RP-6 — RESOLVED** → dedupe/merge is the synthesis pass's responsibility.
- **OQ-RP-7 — OPEN (for CRP)** → the **roster for elicitation**: reuse the shipped reviewer-roles
  roster fixture shape, or ship a curated `requirements-stakeholders.yaml` (end-user/PM/ops/security/
  compliance/sponsor) as a default? (Leaning: ship a default, `answers_for`-keyed on FR areas.)
- **OQ-RP-8 — OPEN (for CRP)** → **acceptance quality signal**: is "accept as-generated" purely human
  judgment, or does the loop attach a *readiness score* (e.g. coverage of the 7 CRP areas + grounding
  flag count) to inform the human — without ever auto-approving? (Leaning: advisory readiness score,
  never a gate.)

---

*v0.1 — Draft (pre-planning): assumed broad panel reuse incl. the grounding guard and an apply kind.*

*v0.2 — Post-planning self-reflective update. Planning (live-code read) falsified 4 assumptions: the
grounding guard is persona-brief-scoped (own a project variant), `recommend.py` suppresses the
specifics check (requirements must run it), there is no requirements apply kind (file-write + CRP gate),
and requirement "domains" are prose sections not YAML slots (own a `RequirementDomain`). All 6 v0.1 OQs
resolved; 2 new OQs opened for CRP.*

*v0.3 — Post lessons-learned hardening. Applied phantom-reference-audit (§Reference-Audit; caught the
grounding-guard corrections), prune-phantom-scope (dropped the apply-kind → NR-RP-3), overloaded-term
(own package + `elicit`, not `recommend`/`suggest`), single-source vocabulary ownership, and carried
three just-accepted Manifest-Suggester CRP findings forward (R2-S1 synthesis, R3-S1 sanitization, R1-S1
`panel.ask`). CRP steering → focus file. Ready for CRP.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to
Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or
Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that
stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items
  already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest
  existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it
  in an **Endorsements** section instead of restating it.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or
  Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same
  idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

*(No review rounds yet.)*
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
