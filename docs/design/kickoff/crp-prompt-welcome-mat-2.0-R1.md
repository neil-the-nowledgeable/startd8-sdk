# Convergent Review Prompt

**Generated:** 2026-06-26 19:27:48 UTC
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
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/kickoff/WELCOME_MAT_2.0_PLAN.md` | 143 lines · 1413 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/kickoff/WELCOME_MAT_2.0_REQUIREMENTS.md` | 263 lines · 2876 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/kickoff/crp-focus-welcome-mat-2.0.md` | 54 lines · 503 words |

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

# CRP Focus — Welcome Mat 2.0 (R1)

Welcome Mat 2.0 adds three pillars to the **served** Welcome Mat web app
(`src/startd8/kickoff_experience/web.py`): (1) read-only template **download**, (2) a home-page
**agentic chat** with **propose-only** writes, (3) authoring the one missing template
(`conventions.md`). Weight the review toward the highest-risk surface — the **chat**. The
template-download and template-authoring pillars are lower risk; spend proportionally less there.

## Settled boundaries — do NOT re-propose

Inherited from `WELCOME_MAT_CONCIERGE_MODE_REQUIREMENTS.md` v0.4 and treated as fixed:
- MCP Concierge stays **preview/read-only**; no new MCP surface.
- **Writes only at human privilege** (web same-origin POST + CSRF + loopback Host + rate-limit, or
  CLI, or explicit TUI confirm). The agentic **loop never applies** a write.
- The agentic floor is `allow_effect_classes=("read",)` with a two-layer dispatch reject.

Do not suggest changes that re-litigate these — assume them.

## Where reviewer input matters most

### A. Agentic chat security & lifecycle (HIGHEST priority)
- **Propose-only write bridge** (FR-WM2-7 / plan S8): the chat may *prefill* a friction/instantiate
  form that the human submits to the **existing** `/concierge/*` endpoints. Can a chat-supplied
  "prefill" smuggle a value past the existing **preview-then-apply / one-time-intent / CSRF**
  gates? Is "the loop never posts" actually guaranteed by the design, or only by convention?
- **Server-side session state** `_ChatStore` (FR-WM2-5 / plan S5): session-fixation, cross-session
  bleed, unbounded growth, eviction correctness, idle expiry. Is keying it "like the CSRF store"
  sufficient, or does chat history need a distinct, harder-to-guess id?
- **Async `POST /chat`** (plan S6) alongside sync routes: does mixing async/sync handlers in the same
  FastAPI app interact badly with the loopback Host / rate-limit machinery? Is the chat endpoint
  rate-limited at all (it's the one **paid** surface)?
- **Cost/turn caps** (FR-WM2-9 / OQ-7): is a per-session turn cap enough, or is a per-session/-server
  spend ceiling needed? What happens at the cap — typed refusal, not a 500?
- **Graceful degradation** (FR-WM2-8): `agent=None` ⇒ disabled panel. Are there partial-failure modes
  (key valid but provider 401/timeout mid-conversation) that must also degrade rather than 500 `/`?
- **Error containment**: must a chat agent exception **never** propagate into the home-page render or
  leak provider error text / keys into the response?

### B. Download key-closure & parity (MEDIUM)
- **Path-traversal closure** (FR-WM2-2 / NR-3): is manifest-**key** lookup genuinely sufficient, or
  are there encoding/normalization escapes? Confirm no `..`/absolute path can ever be requested.
- **Download↔instantiate posture parity** (FR-WM2-4): downloaded `conventions.yaml` must be
  byte-identical to the instantiate plan's content at the same posture. Is the verify criterion right?
- **One-inventory no-drift** (FR-WM2-4/11/12): the manifest derives from `_KICKOFF_FILES` +
  `_AUTHORING_FILES`. Is the "adding a template without a manifest row fails a test" guard real?

### C. Open questions needing a call
- **OQ-4** — zip in-memory build: size ceiling needed?
- **OQ-5** — should `templates/authoring/*.md` (incl. new `conventions.md`) be downloadable? They are
  not packaged in `concierge_templates/` today (additive packaging decision).

## Out of scope for this review
- The assembly/manifest-grammar templates (data-model contract, app/pages/views) — explicitly NR-6.
- Re-designing the Concierge-mode milestone (v0.4) — only 2.0's additions.

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/kickoff/WELCOME_MAT_2.0_PLAN.md`  ·  **Size:** 143 lines · 1413 words

```markdown
# Welcome Mat 2.0 — Implementation Plan

**Version:** 0.1 (Draft — pairs with `WELCOME_MAT_2.0_REQUIREMENTS.md` v0.1)
**Date:** 2026-06-26
**Status:** Draft

> This plan maps each FR to concrete files/seams and records what the codebase reveals. Discoveries
> that change the requirements are collected in §6 and fed back into requirements §0 (v0.2).

---

## 1. Architecture at a glance

Everything new attaches to `kickoff_experience/web.py:build_kickoff_app` (the FastAPI factory) and
reuses three existing subsystems verbatim:

| Pillar | Reuses | New surface |
|--------|--------|-------------|
| Download (FR-WM2-1..4, 11, 12) | `concierge/writes.py` `_KICKOFF_FILES`/`_AUTHORING_FILES` + `_load_template`/`_render_input` | a public manifest accessor + 3 GET routes + an in-memory zip |
| Chat (FR-WM2-5..9) | `chat.py` `build_kickoff_registry` + `new_kickoff_chat` + `KickoffChat` + `utils/agent_resolution.resolve_agent_spec` | an agent threaded into the app + a chat-session store + 1 async POST route + overview render |
| Templates (FR-WM2-10..12) | `templates/authoring/*` structure | author `conventions.md` + a manifest/index doc + a completeness test |

---

## 2. Pillar 1 — Template download

**S1. Public manifest accessor (FR-WM2-4, 11).** In `concierge/writes.py`, add
`kickoff_template_manifest() -> list[TemplateEntry]` deriving from the existing
`_KICKOFF_FILES + _AUTHORING_FILES` (the lists stay the single source of truth). Each entry:
`{key, template_rel, dest, group, label}` where `key` is a stable slug (e.g. `package/kickoff-intro`,
`authoring/requirements-template`). This is the closed key space FR-WM2-2/NR-3 depend on.

**S2. Download routes in `web.py` (FR-WM2-1..3).**
- `GET /templates` → HTML list rendered from the manifest (label, dest, group, bytes via
  `len(content.encode())`). Linked from `_render_overview`. Read-only; no CSRF; available in every mode.
- `GET /templates/file/{key}` → look up the manifest entry by `key`; 404 (typed) on miss; return
  `Response(_render_input(rel, posture) or _load_template(rel), media_type=…, headers={Content-Disposition: attachment; filename="<dest basename>"})`. **Key-only lookup ⇒ no path param ⇒ no traversal** (NR-3 satisfied structurally).
- `GET /templates/bundle.zip` → build a `zipfile.ZipFile` in a `BytesIO` with each entry at its
  `dest` path; stream as `application/zip`. Posture defaults to `prototype` (a `?posture=` query may
  select, validated against `VALID_POSTURES`).
- Emit `template_downloaded` / `template_bundle_downloaded` (FR-WM2-14).

**S3. Tests.** Manifest↔instantiate parity (same rel set); key 404; Content-Disposition present;
no path param accepted; zip contains exactly the manifest dests; bytes match `_load_template`.

## 3. Pillar 2 — Home-page agentic chat

**S4. Thread an agent into the app (OQ-3 → resolved).** `build_kickoff_app(..., agent: BaseAgent | None = None)`.
`serve_kickoff` + the `start` CLI gain an optional `--agent` (default `Models.CLAUDE_SONNET_LATEST`),
resolved with `resolve_agent_spec` inside a try/except that mirrors `cli_kickoff.py:chat_cmd` — on
failure, `agent=None` (chat disabled, server still serves). One agent per server process.

**S5. Chat-session store (OQ-1 → resolved).** `_SessionStore` holds CSRF tokens, **not** chat history
— so add a small `_ChatStore` modeled on it: `session_id -> (KickoffChat, last_used, turns)`, idle
expiry (`_IDLE_S`), a per-session turn cap (FR-WM2-9 cost guard, OQ-7), bounded entry count (evict
oldest, like `concierge_view._survey_cache`). `KickoffChat` is built lazily per session via
`new_kickoff_chat(agent, root)`.

**S6. Async chat endpoint (OQ-2 → resolved: use `async def`).** `POST /chat` (`async def`) takes
`message` + a chat-session cookie; calls `await chat.ask(message)` directly (no `asyncio.run` —
uvicorn owns the loop); returns `{text, cost: {turns, tokens, usd}}`. Read-only by construction (the
registry is `allow_effect_classes=("read",)`; `handle_kickoff_read` is the floor). 500-safe: any
agent error returns a typed `chat_error` JSON, never crashes the page.

**S7. Overview render (FR-WM2-5, OQ-6).** Decision: **inline panel on `/`** (single home page), posting
to `/chat`. `_render_overview` gains a chat panel + the posture banner when `agent is not None`; when
`None`, a disabled panel with the degradation message (FR-WM2-8). Emit `chat_turn` / `chat_unavailable`.

**S8. Propose-only bridge (FR-WM2-7).** No new endpoint and **no new tool**. The chat reply may include
a suggested friction draft / instantiate posture (assistant text the user copies, or — thin
enhancement — a "prefill" button that populates the existing `/concierge` friction/instantiate form
client-side). Submission goes through the **unchanged** `/concierge/friction` / `/concierge/instantiate`
(CSRF + loopback + one-time-intent + preview-then-apply all intact). The loop never posts.

**S9. Tests.** Read-floor preserved (no write tool reachable); `agent=None` ⇒ disabled panel + 200
home; async endpoint returns text+cost; turn cap enforced; chat error ⇒ typed JSON not 500; events
exclude message text.

## 4. Pillar 3 — Complete the template set

**S10. Author `docs/design/kickoff/templates/authoring/conventions.md` (FR-WM2-10).** Match
`observability.md`/`business-targets.md` structure; cover `conventions.yaml` (stack, module paths,
naming, `data_model:` cross-cutting choices, field authorship) + the production(architect-authored)
vs prototype(templated) rule from `KICKOFF_INPUT_PACKAGE_GUIDE.md` §5.

**S11. Index doc + manifest assertion (FR-WM2-11, 12).** A short `templates/README` row set (or extend
`templates/authoring/README.md`) naming the complete set; the FR-WM2-4 accessor is the machine-readable
manifest. Completeness test: every manifest entry resolves via `_load_template`; package + quintet all
present; no orphan rows.

**S12. (Pending OQ-5)** If authoring `*.md` guidance should also be downloadable, they must be added to
the packaged `concierge_templates/` tree first (they live only under `docs/` today). Deferred to the
reflect pass / CRP.

## 5. Sequencing

1. S1 manifest accessor → S2 download routes → S3 tests (self-contained, `$0`, lowest risk — ship first).
2. S10 `conventions.md` + S11 index/manifest + S12 decision (docs-only, parallelizable).
3. S4 agent threading → S5 chat store → S6 endpoint → S7 overview → S8 bridge → S9 tests (largest surface; do last).

## 6. Planning discoveries (feed back to requirements §0)

| Requirements assumed (v0.1) | Planning revealed | Impact on requirements |
|-----------------------------|-------------------|------------------------|
| P-A "reuse, don't re-implement" applies uniformly | Download + templates are pure reuse, but **chat needs genuinely new plumbing**: an agent threaded through `build_kickoff_app`/`serve_kickoff`/`start`, AND a new chat-session store (the `_SessionStore` holds CSRF, not history). | Soften P-A for the chat: reuse the *loop/registry/cost*; acknowledge new *agent-threading + session-store* plumbing. (OQ-1, OQ-3) |
| Chat endpoint shape open (OQ-2) | Routes are sync `def`; `AgenticSession.ask` is async; uvicorn owns the loop ⇒ `POST /chat` must be `async def` calling `await` directly (the CLI's `asyncio.run` is a CLI-only bridge). | Resolve OQ-2: async endpoint. |
| Agent source open (OQ-3) | `serve_kickoff` has no agent; the CLI resolves via `resolve_agent_spec(spec or Models.CLAUDE_SONNET_LATEST)` with a try/except degradation already written. | Resolve OQ-3: one agent per server, `--agent` flag, reuse the CLI's degradation pattern → directly satisfies FR-WM2-8. |
| "Author the missing templates" (P3) sounds large | The 11 packaged templates **all exist**; the *only* genuinely missing file is `conventions.md` authoring guidance. P3 is narrow. | Narrow FR-WM2-10 to `conventions.md` + manifest/index; mark P3 "thinner than feared." |
| Download is the trivial pillar | True, but the real risk is **path traversal / arbitrary-file disclosure** — mitigated structurally by manifest-**key** lookup (no path param). | Elevate the key-closure invariant (already NR-3/FR-WM2-2) as the download acceptance criterion. |
| Posture substitution only matters at instantiate | `conventions.yaml` carries a posture-resolved provenance placeholder; a downloaded copy must resolve it too, else the download differs from instantiate output. | FR-WM2-4 must state download applies the same `_render_input` posture substitution. |
| Chat is "just another panel" | It is the **only non-`$0`, only-stateful, only-async, only-needs-a-key** surface in the whole Welcome Mat. | Make graceful degradation + cost visibility first-class (FR-WM2-8/9), not afterthoughts. |

---

*Plan v0.1 — drafted against the live code. Feeds 7 discoveries into requirements §0 for v0.2.*

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/kickoff/WELCOME_MAT_2.0_REQUIREMENTS.md`  ·  **Size:** 263 lines · 2876 words

```markdown
# Welcome Mat 2.0 — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-26
**Status:** Draft
**Owner:** neil-the-nowledgeable
**Plan:** `WELCOME_MAT_2.0_PLAN.md` (v0.1)
**Related (settled boundaries inherited, do not re-litigate):**
`WELCOME_MAT_CONCIERGE_MODE_REQUIREMENTS.md` (v0.4, the Concierge-mode milestone),
`INTERACTIVE_KICKOFF_EXPERIENCE_REQUIREMENTS.md` (v0.5, "Welcome Mat"),
`KICKOFF_INPUT_PACKAGE_GUIDE.md` (v0.1, the canonical template set), `CONCIERGE_MCP_REQUIREMENTS.md`

> **What "2.0" is.** The Welcome Mat shipped as a $0, read-mostly onboarding surface (readiness
> meter + per-field badges + a Concierge mode that surveys / instantiates / logs friction). 2.0 adds
> three *outward-facing* affordances on top of that settled base — **without** widening any of the
> safety boundaries the Concierge-mode milestone established. Everything new is either read-only/`$0`
> or rides the **existing** human-privilege write seam.

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2. The planning pass read the live
> `kickoff_experience/web.py`, `chat.py`, `concierge/writes.py`, and `cli_kickoff.py` and found the
> three pillars are **unequal**: two are pure reuse, but the chat is the only stateful / async /
> paid / key-needing surface in the whole Welcome Mat — and the "missing templates" work is far
> thinner than the phrasing implied.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| **P-A "reuse, don't re-implement"** applies uniformly across all three pillars | Download + templates are pure reuse; **chat needs genuinely new plumbing** — an agent threaded through `build_kickoff_app`/`serve_kickoff`/`start` (none takes an agent today, `serve.py:239`) **and** a new chat-session store (`_SessionStore` holds CSRF tokens, not conversation history, `web.py:69`). | **P-A softened for chat** (reuse the loop/registry/cost; new agent-threading + session-store plumbing is expected, not a smell). Resolves OQ-1, OQ-3. |
| **OQ-2 — chat endpoint shape unknown** | Existing routes are sync `def`; `AgenticSession.ask` is **async**; uvicorn owns the loop. The CLI's `asyncio.run` (`cli_kickoff.py:chat`) is a CLI-only bridge. | **OQ-2 resolved → `POST /chat` is `async def`** calling `await chat.ask(...)` directly. Pinned in FR-WM2-5. |
| **OQ-3 — where the chat agent comes from** | `serve_kickoff` has no agent; the CLI resolves `resolve_agent_spec(spec or Models.CLAUDE_SONNET_LATEST)` inside a **try/except degradation already written** (`cli_kickoff.py:233`). | **OQ-3 resolved → one agent per server**, `--agent` flag, reuse the CLI degradation pattern — which directly *implements* FR-WM2-8. |
| **P3 "author the missing templates"** sounds like a multi-file authoring effort | The 11 packaged templates **all exist** (`concierge_templates/`). The *only* genuinely missing file is per-domain authoring guidance for `conventions.yaml` — every other input domain has a `templates/authoring/*.md`, `conventions.md` does not. | **FR-WM2-10 narrowed to `conventions.md` + a manifest/index.** P3 is "thinner than feared." |
| **Download is the trivial pillar** (no risk) | Trivial to build, but the real risk is **path traversal / arbitrary-file disclosure**. Mitigated *structurally* by manifest-**key** lookup (no path parameter ever accepted). | Elevated the **key-closure invariant** to the download acceptance criterion (FR-WM2-2 / NR-3). |
| **Posture substitution only matters at instantiate** | `conventions.yaml` ships a posture-resolved provenance placeholder (`writes.py:_render_input`); a *downloaded* copy must resolve it the same way or download output diverges from instantiate output. | **FR-WM2-4 extended** — download applies the same `_render_input` posture substitution. |
| **Chat is "just another home-page panel"** | It is the **only** non-`$0`, **only** stateful, **only** async, **only** key-needing surface in the Welcome Mat. | **Graceful degradation (FR-WM2-8) + cost visibility (FR-WM2-9) are first-class**, not afterthoughts; per-session turn cap added (OQ-7). |

**Resolved open questions:**
- **OQ-1 → new `_ChatStore`** modeled on `_SessionStore` (session-id → `KickoffChat` + last-used +
  turn count; idle expiry + bounded entries). The CSRF store can't hold chat history.
- **OQ-2 → `async def /chat`** calling `await chat.ask(...)` (uvicorn owns the loop).
- **OQ-3 → one agent per server**, `--agent` on `serve`/`start`, default `Models.CLAUDE_SONNET_LATEST`.
- **OQ-6 → inline chat panel on `/`** (one home page), not a separate `/chat` page.
- **OQ-7 → per-session turn cap** in `_ChatStore` (the cost guard the paid surface needs).
- **OQ-4 → STILL OPEN** (zip vs tar; in-memory build — bounded set, almost certainly safe; confirm at build).
- **OQ-5 → STILL OPEN** (whether `templates/authoring/*.md` join the downloadable set; they aren't
  packaged in `concierge_templates/` today, so it's an additive packaging decision — defer to CRP).

---

## 1. Problem Statement

The served Welcome Mat helps a user *understand* their kickoff state but gives them no way to **take
the templates with them**, and its only conversational help (the agentic kickoff chat) is **invisible
on the web** — it lives behind a CLI command. Three concrete gaps:

| # | Capability | Current state | Gap |
|---|-----------|--------------|-----|
| **P1** | **Download the template files** | Templates reach a project *only* by `instantiate` **writing** them to disk (`concierge/writes.py:_load_template`). `web.py` has **no** download route (no `FileResponse` / `Content-Disposition` anywhere). | A user who wants to read/keep the kickoff-input + authoring templates — without scaffolding them into a project — has no path. There is no "download the templates" affordance. |
| **P2** | **Agentic chat on the home page** | The read-only agentic kickoff chat (`chat.py`: `survey` / `assess` / `field_states`, `allow_effect_classes=("read",)`) is **CLI-only** (`startd8 kickoff chat`, `cli_kickoff.py:219`). The web home page (`web.py:344 overview` → `_render_overview`) shows a readiness meter and a *link* to `/concierge`, but **no chat**. | A web user can't converse with the assistant at all; and the assistant — even where reachable — can only talk, never help the human *act* (draft a friction entry, prefill an instantiate). |
| **P3** | **A complete, downloadable template set** | The canonical set (`KICKOFF_INPUT_PACKAGE_GUIDE.md` §1) is 6 package files + a 5-file authoring quintet = the 11 packaged files in `src/startd8/concierge_templates/`. Per-domain **authoring guidance** lives in `docs/design/kickoff/templates/authoring/` — but `conventions.yaml` (the "run-028 guard", the Architect's centerpiece) has **no** `conventions.md`, unlike every other input domain. | The template surface the Welcome Mat would offer for download is **incomplete**: the highest-stakes input has no authoring guidance, and there is no single manifest that says "this is the complete set." |

**What should exist (2.0):**
1. A **read-only download surface** in the served web app that offers the kickoff-package + authoring
   templates — individually and as a single bundle — sourced from the *same* inventory `instantiate`
   uses (so the two can never drift), keyed so no arbitrary file can be requested.
2. A **home-page agentic chat** that surfaces the existing read-only kickoff loop on the web, and can
   **propose** (draft / prefill) a friction entry or an instantiate — which a **human still applies**
   through the existing same-origin + CSRF write seam. The loop itself never writes.
3. The **missing template element(s)** authored so the downloadable set is complete and coherent —
   concretely, `conventions.md` authoring guidance, plus a manifest/index that names the full set.

---

## 2. Guiding Principles (inherited from the Concierge-mode milestone)

- **P-A — Reuse, don't re-implement (with one honest exception).** Download rides `_load_template` +
  the `_KICKOFF_FILES`/`_AUTHORING_FILES` inventory. Chat rides `build_kickoff_registry` +
  `AgenticSession` + `KickoffChat` + `resolve_agent_spec`. Propose-only writes ride the **existing**
  `/concierge/friction` + `/concierge/instantiate` seam — no new write engine, no new template loader,
  no new readiness computation. *Exception surfaced by planning:* the chat does need **new plumbing** —
  an agent threaded into the app and a chat-session store — because nothing existing carries an agent
  or holds conversation history (the `_SessionStore` holds only CSRF tokens). That plumbing is
  expected, not a reuse failure.
- **P-B — `$0` and offline except the chat.** Download and template authoring are deterministic and
  `$0`. The agentic chat is the **one** surface that calls an LLM (cost + an API key); it must
  **degrade gracefully** (the rest of the Welcome Mat keeps working with no key / no agent).
- **P-C — Writes only at human privilege; never MCP, never the loop.** The chat is read-only by
  construction (`allow_effect_classes=("read",)`). "Propose-only" means the assistant *suggests
  values*; the **human** applies them through the unchanged write seam (web same-origin POST with
  session/CSRF + loopback Host + rate-limit). The loop never reaches `apply_write_plan`.
- **P-D — No new disclosure / traversal surface.** Download serves only the allow-listed packaged
  templates by **manifest key**, never by a caller-supplied path. Chat exposes only the three
  existing read tools; it never reads consumer file *content* beyond what those tools already return.
- **P-E — One inventory, two consumers.** The downloadable set and the instantiate set are the *same*
  list. A template added to one is added to both, by construction.

---

## 3. Requirements

### A. Template download (P1)

- **FR-WM2-1 — A download surface.** The served web app exposes a read-only download area listing the
  kickoff-package + authoring templates with, per entry, a human label, destination-when-instantiated,
  group (`package` | `authoring`), and byte size. Reachable from the home page. Read-only, `$0`,
  available in **all** feature modes (incl. `inspect`/`preview`) — it never writes.
- **FR-WM2-2 — Individual file download.** A route serves one template's bytes with
  `Content-Disposition: attachment; filename="<canonical>"` and a text/markdown or text/yaml content
  type. The file is selected by a **manifest key**, not a path; an unknown key returns a typed 404.
  No `..`/absolute path can ever be requested (the key space is closed).
- **FR-WM2-3 — Bundle download.** A route serves the whole set as a single archive (zip) with the
  package + authoring trees laid out as they would be on disk (`docs/kickoff/…`), built in-memory
  from `_load_template`. `$0`, read-only.
- **FR-WM2-4 — One inventory (no drift).** The download manifest is **derived from** the same
  `_KICKOFF_FILES` + `_AUTHORING_FILES` lists `build_instantiate_plan` consumes (exposed via a small
  public accessor). A template added to instantiate appears in download with no extra edit. **Posture
  substitution must match instantiate:** a downloaded `conventions.yaml` resolves the provenance
  placeholder via the same `_render_input` path `instantiate` uses (default posture `prototype`), so
  downloaded bytes equal instantiated bytes. *Verify:* download of `conventions.yaml` at posture P is
  byte-identical to the `instantiate` plan's content for that file at posture P.

### B. Home-page agentic chat (P2)

- **FR-WM2-5 — Chat on the home page.** The home page (`/`, inline panel — OQ-6) surfaces the
  read-only agentic kickoff chat (`build_kickoff_registry` — `survey` / `assess` / `field_states`) as a
  conversational panel. An **`async def POST /chat`** endpoint accepts a user message and returns the
  assistant's turn by `await chat.ask(...)` (uvicorn owns the loop; the CLI's `asyncio.run` is not
  reused). Multi-turn history is held in a server-side **`_ChatStore`** (session-id → `KickoffChat` +
  last-used + turn count; idle expiry + bounded entries), modeled on `_SessionStore` — which holds
  CSRF tokens, *not* history.
- **FR-WM2-6 — Read-only floor preserved.** The web chat uses the **same** registry and dispatch floor
  as the CLI (`handle_kickoff_read` hard-rejects any non-read action). No write tool is ever
  registered. The posture banner (`chat.py:POSTURE_BANNER`) is shown.
- **FR-WM2-7 — Propose-only writes (bridge, not a new write path).** The assistant may *draft* a
  friction entry or *prefill* an instantiate posture; the UI renders those as a **prefilled form** that
  posts to the existing `/concierge/friction` / `/concierge/instantiate` endpoints. The human reviews
  and submits; the existing preview-then-apply + CSRF + loopback + one-time-intent gates are unchanged.
  The loop never calls those endpoints itself.
- **FR-WM2-8 — Graceful degradation (no key / no agent).** If no agent can be resolved (missing API
  key, no provider), the chat panel renders a disabled state with an explanatory message and the rest
  of the home page is unaffected. Chat failures never 500 the home page.
- **FR-WM2-9 — Cost visibility.** Each assistant turn surfaces the per-turn cost line
  (`KickoffChat.cost_line`: turns / tokens / `cost≈$`), so the one non-`$0` surface is honest about
  spend.

### C. Complete the template set (P3)

- **FR-WM2-10 — Author the missing authoring guidance** *(narrowed by planning: the 11 packaged
  templates all exist; this is the **only** genuinely missing file)*. Author
  `templates/authoring/conventions.md` (the one input domain missing per-domain guidance), matching the
  structure/voice of the existing `business-targets.md` / `observability.md` / `build-preferences.md`,
  and covering the `conventions.yaml` fields (stack, module paths, naming, `data_model:` cross-cutting
  choices, field authorship) and the production-vs-prototype authorship rule (`KICKOFF_INPUT_PACKAGE_GUIDE.md`
  §5).
- **FR-WM2-11 — A named, complete manifest.** A single manifest (the FR-WM2-4 accessor, plus a short
  human index doc) enumerates the complete downloadable set and is the assertion target for "the set
  is complete." Adding a template without adding its manifest row fails a test.
- **FR-WM2-12 — Verify completeness.** A test asserts every manifest entry resolves to a readable
  packaged template and that the package + authoring quintet are all present (no missing file, no
  orphan manifest row).

### D. Boundaries & cross-cutting

- **FR-WM2-13 — MCP unchanged.** No new MCP surface. Download and chat are web/CLI only; the MCP
  Concierge stays read/preview-only (inherited NR).
- **FR-WM2-14 — Observability.** New funnel events: `template_downloaded` (key, group),
  `template_bundle_downloaded`, `chat_turn` (turns, tokens, cost — **no** message text),
  `chat_unavailable` (degraded reason). Event attributes exclude user message text and raw paths
  (inherited privacy contract).
- **FR-WM2-15 — Parity where it applies.** Download is web-only (no TUI download); chat already has a
  CLI surface (`kickoff chat`) — 2.0 adds the *web* surface over the *same* registry, so behavior is
  equivalent by shared construction, not re-implemented.

---

## 4. Non-Requirements

- **NR-1 — No write tools in the chat.** The agentic loop never gains `instantiate-kickoff` /
  `log-friction` / `derive-contract` tools. Propose-only is a UI bridge to the human-applied seam.
- **NR-2 — No MCP download/chat.** Neither new surface is exposed over MCP.
- **NR-3 — No arbitrary-file download.** Only the closed manifest key space; never a path parameter.
- **NR-4 — Not an operator.** Nothing here runs the cascade, records a gate, or deploys.
- **NR-5 — No re-implementation.** No second template loader, readiness computation, or write engine.
- **NR-6 — Assembly/manifest-grammar templates out of scope.** The data-model contract, assembly
  manifests, and content prose (the "deliberately NOT in the package" set, `KICKOFF_INPUT_PACKAGE_GUIDE.md`
  §1) are **not** part of 2.0's downloadable set. 2.0 ships the kickoff-package + authoring quintet only.

---

## 5. Open Questions

*5 of 7 resolved by the planning pass — see §0 for rationale + citations. Retained for the record.*

- **OQ-1 — RESOLVED → new `_ChatStore`** (session-id → `KickoffChat` + last-used + turn count; idle
  expiry + bounded entries), modeled on `_SessionStore`. The CSRF store cannot hold chat history.
- **OQ-2 — RESOLVED → `async def POST /chat`** calling `await chat.ask(...)` (uvicorn owns the loop;
  the CLI `asyncio.run` bridge is not reused).
- **OQ-3 — RESOLVED → one agent per server**, `--agent` on `serve`/`start`, default
  `Models.CLAUDE_SONNET_LATEST`, resolved with the CLI's existing `resolve_agent_spec` degradation.
- **OQ-6 — RESOLVED → inline chat panel on `/`** (single home page), not a separate `/chat` page.
- **OQ-7 — RESOLVED → per-session turn cap** in `_ChatStore` (the cost guard the paid surface needs),
  distinct from the capture rate-limit.
- **OQ-4 — STILL OPEN.** Bundle as zip (stdlib `zipfile`, in-memory `BytesIO`); the set is small and
  bounded so an in-memory build is almost certainly safe — confirm a size ceiling at build.
- **OQ-5 — STILL OPEN.** Whether the per-domain authoring guidance (`templates/authoring/*.md`,
  including the new `conventions.md`) should also be downloadable. They aren't packaged in
  `concierge_templates/` today, so it's an additive packaging decision — defer to CRP / implementation.

---

*v0.2 — Post-planning self-reflective update. The planning pass falsified 3 assumptions and confirmed
2: chat **does** need new plumbing (agent threading + `_ChatStore`) — P-A softened; "author the missing
templates" **is** thin — only `conventions.md` (FR-WM2-10 narrowed); download **is** trivial but its
real risk is path-traversal, mitigated by manifest-key closure (FR-WM2-2/NR-3). 1 requirement softened
(P-A), 1 narrowed (FR-WM2-10), 2 extended (FR-WM2-4 posture parity, FR-WM2-5 async/store), 5 of 7 open
questions resolved. Ready for CRP review before implementation.*

---

## Appendix A — Accepted (with where merged)

<!-- F-<n> / S-<n> — <suggestion> → ACCEPTED; merged into <section>. -->
*(none yet — populated after CRP review.)*

## Appendix B — Rejected (with rationale)

<!-- F-<n> / S-<n> — <suggestion> → REJECTED; <why>. -->
*(none yet.)*

## Appendix C — Incoming review rounds

<!-- #### Review Round R{n} — <model-id> — <UTC date> -->
*(none yet.)*

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
