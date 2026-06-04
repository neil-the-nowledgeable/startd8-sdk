# Convergent Review Prompt

**Generated:** 2026-06-03 23:40:09 UTC
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
| **Plan** | `/Users/neilyashinsky/.claude/plans/zazzy-roaming-cupcake.md` | 259 lines · 2486 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/CONTENT_PAGES_CAPABILITY_HANDOFF.md` | 207 lines · 1860 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/content-pages-authoring-focus.md` | 36 lines · 355 words |

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

# CRP Focus — Content-Pages UI Authoring (default-on / multi-user gate)

The page-authoring capability (`--pages-authoring`) is **built and gated OFF by default**, sound for
its stated bound: **NFR-UI-1 — local-first, single-user, no auth**. This review is the gate before any
decision to (a) enable it by default in every generated app, or (b) expose authoring beyond local
single-user. Weight findings toward what *changes when that bound is removed*.

## Where we need input most

1. **Raw-HTML self-XSS in prose → stored XSS at multi-user.** python-markdown passes raw HTML through;
   the generated app renders prose at generate time and serves it. Harmless self-XSS locally. What is the
   right control before multi-user/default-on — sanitize at generate time (bleach/allowlist), escape, a
   CSP, or a documented "trusted-authors-only" boundary? Where should it live (SDK generate-time vs app)?

2. **Concurrent-POST race on `pages.yaml`/`.md`.** Read-modify-write with no lock; lost updates under
   concurrency. Acceptable single-user. What's the minimal correct mechanism if authoring is shared
   (file lock, optimistic version check on the manifest, single-writer queue)?

3. **Broader manifest shapes.** The owned safe-append supports only block-style, consistently-indented
   `pages:`; flow-style / odd-indent fail loud without corruption (write gated on a clean reparse). Is
   "fail-loud + document the supported shape" acceptable, or should the append normalize/round-trip
   arbitrary valid YAML (e.g. a comment-preserving round-tripper)? Trade-off vs. the no-SDK-import,
   minimal-runtime-deps constraint.

4. **The generated-owned validator drifting from the SDK `parse_pages`.** `app/pages_io.py` re-emits the
   strict-parse rules as owned code (the app must not import the SDK). How do we keep the two in sync over
   time — a shared contract test, codegen from one source, or a versioned rule-set? What breaks if they
   diverge (UI accepts a manifest the next `generate backend` rejects)?

5. **Disk-write endpoint as an attack surface.** Even gated/local, the app exposes POST routes that write
   into the project source tree. Beyond slugify + `parent == app/pages/` containment, what else matters at
   exposure (auth hook, path/size limits, rate limiting, refusing symlinked targets, write-scope allowlist)?

6. **Atomicity / rollback completeness.** Create validates-then-writes-prose-then-commits-manifest with
   prose rollback on manifest failure. Are there partial-failure windows left (e.g. manifest write
   succeeds, process dies before response; orphan `.md` overwrite/rollback-delete of a pre-existing file)?

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

**Path:** `/Users/neilyashinsky/.claude/plans/zazzy-roaming-cupcake.md`  ·  **Size:** 259 lines · 2486 words

```markdown
# Content Pages: Generator + UI-Driven Page Authoring (Reflective Requirements + Plan)

## Context

The StartDate app (consumer of `startd8-sdk`) is getting a **content-pages capability**: generate
owned, non-entity pages (home `/`, how-it-works) + a site nav from a `pages.yaml` manifest + authored
`app/pages/*.md` prose, the same owned/$0/no-LLM/drift-tracked model the AI layer already uses. That
base generator is **planned but not yet built** (Capabilities 1 + 2 below).

On top of it, the user wants an **iterative, UI-driven page-authoring** experience so a page can be
created/edited through a simple UI instead of hand-editing files. Confirmed scope (via clarifying Q):
- **Author & timing:** *design-time author + regenerate* — the UI writes the generator **inputs**
  (`pages.yaml` entry + `.md`); the page goes live on the next `generate backend`. Pages stay owned,
  $0, drift-tracked. No runtime page invention.
- **Surface:** a **web UI served by the app** (e.g. `/ui/pages`).
- **Ships as:** **SDK-generated into the app** — the backend generator emits the authoring UI from
  the contract, so every generated app gets it.

This document runs the reflective loop: v0.1 assumptions → planning discoveries (§0) → v0.2
requirements → phased plan → verification.

---

## Foundation (prerequisite — Capabilities 1 & 2, already designed)

The UI work depends on these landing first. Summary (full design retained from the prior plan):

**Cap 1 — Content-pages generation.** New `backend_codegen/pages_generator.py`: strict `parse_pages`
(mirrors `parse_ai_passes` in `ai_layer.py:99`); `--pages PATH` flag on `cli_generate.py:backend`;
emits `app/pages.py` (`pages_router`, one GET route per slug), per-page **owned shell templates**
`app/templates/pages/<name>.html`, and **untracked body fragments** `app/templates/pages/_<name>.body.html`
(generate-time markdown render — keeps the app runtime markdown-free); injects a `<nav>` into
`base.html` (`htmx_generator.py:101`). Drift: 2-hash header (schema + pages) via a new
`header_pages` in `_headers.py`; `_PAGES_KINDS` routed through `check_drift` like `_AI_KINDS`.
**Prose lives only in the untracked fragment**, so editing a `.md` never flags drift while
`pages.yaml` edits do.

**Cap 2 — Form system-field omission.** `htmx_generator.py` gains `_writable_fields()` = scalars
minus `f.is_id` and `_PROVENANCE_OMIT` (imported from `ai_layer.py:42`); used in
`render_form_template` + `_entity_routes` so forms expose only human-authored fields (list/detail
still display `createdAt` etc.).

---

## Requirements v0.1 (pre-planning assumptions — for the record)

- A1: A small web form in the app appends an entry to `pages.yaml`. *(Phase 1)*
- A2: A markdown editor in the app defines the page body, "matching the `.md` formatting we support". *(Phase 2)*
- A3: One flow wires the yaml entry + `.md` together for end-to-end page creation. *(Phase 3)*
- A4: The UI can later edit existing `.md` files. *(Phase 4)*
- A5 (implicit): the running app can read/validate/write `pages.yaml` directly.
- A6 (implicit): editing prose via the UI behaves like any prose edit (outside the drift hash).

## 0. Planning Insights (Self-Reflective Update: v0.1 → v0.2)

| v0.1 assumption | Planning discovery | Impact |
|---|---|---|
| A5: app can validate `pages.yaml` like the SDK does | The generated app **must not import the SDK**, and ships **no `pyyaml`/`markdown`** (`derived.py:_RUNTIME_REQUIREMENTS` = fastapi/sqlmodel/jinja2/multipart/uvicorn) | **NEW NFR-UI-3/4**: validation is **generated-owned** (a minimal in-app validator mirroring `parse_pages` rules), and `pyyaml` is added to the app's runtime deps **only when authoring is enabled** |
| A1: "append an entry" is a simple write | `pages.yaml` is strict-parsed (loud-fail) and carries **comments + an explicit `nav:`** | **FR-UI-1 tightened**: structured append that preserves the file, then **re-validate the whole result** before commit; reject dup/invalid slugs with friendly errors |
| A2: a markdown editor implies a live preview | A live preview re-introduces a **runtime `markdown` dep** — the very thing Cap 1 avoided | **NEW non-requirement**: no live preview in v1 (regen to see the rendered page); textarea only |
| A1/A3: user supplies the `content` path | Path can be **derived from the slug** (`/how-it-works` → `pages/how_it_works.md`); hand-typed paths are an error surface | **FR-UI-1/3**: content path auto-derived + **path-sanitized** (confined to `app/pages/`) |
| (unstated) "live" after save | design-time+regen means the page is **not served until `generate backend` re-runs** | **FR-UI-3**: the UI must surface a clear **"regenerate to publish"** step (+ the exact command); **no auto-regen** in v1 |
| (unstated) where the authoring UI's drift comes from | The authoring form/validator are **generic** — they don't vary with `pages.yaml` content or the entity schema | **FR-UI-5**: authoring artifacts are **schema-hashed (1-hash)**, simpler than the 2-hash page artifacts; emitted only when authoring is enabled |
| A6: UI prose edits are drift-safe | True, and it composes: the `.md`/fragment split from Cap 1 already keeps prose outside the hash | **FR-UI-4 confirmed feasible** with no new drift machinery |

**Resolved open questions**
- **OQ-A → in-app validator, generated-owned.** Mirror `parse_pages` rules in emitted code; never import the SDK.
- **OQ-B → structured append + full re-validate.** Preserve `pages.yaml` (comments/nav); validate the result before writing.
- **OQ-C → derive + sanitize the content path** from the slug.
- **OQ-D → explicit "regenerate to publish"**; no auto-regeneration in v1.
- **OQ-E → `pyyaml` added to runtime deps only when authoring is on**; `markdown` stays out (no live preview).

---

## 2. Requirements v0.2

### A. Authoring capability (SDK-generated into the app; design-time author + regen)
- **FR-UI-1 (Phase 1) — Safe "add page" form.** Generated screen at `GET /ui/pages` with a form
  (`slug` req, `title` req, `nav_label` opt). On `POST /ui/pages` it **appends one entry to
  `pages.yaml`**: derive `content: pages/<name>.md` from the slug; validate (required keys, slug
  format `^/`, uniqueness) via the **generated-owned** validator; **re-parse the full file** to
  confirm it stays valid; preserve existing content/comments/`nav:`. Friendly inline errors on
  failure; nothing written on any error.
- **FR-UI-2 (Phase 2) — Markdown body editor.** The form includes a `<textarea>` for the page body.
  On submit, write `app/pages/<name>.md` (raw markdown — no rendering at write time). Body formatting
  is whatever the Cap 1 generator renders (`extensions=["extra","sane_lists"]`); a short hint lists
  supported syntax. **No live preview** (v1).
- **FR-UI-3 (Phase 3) — End-to-end create (atomic).** One submit creates **both** the `pages.yaml`
  entry **and** the `.md` file, all-or-nothing (no half-created page on failure). On success, show a
  confirmation that names the page and states: *"Saved. Run `startd8 generate backend --pages …` to
  publish."* (with the concrete command).
- **FR-UI-4 (Phase 4) — Edit existing prose.** `GET /ui/pages` lists authored pages; selecting one
  (`GET /ui/pages/<name>/edit`) loads the **raw `.md`** into the editor; `POST /ui/pages/<name>`
  writes it back. Editing prose **does not flag drift** (Cap 1 model). Title/nav edits to
  `pages.yaml` may follow but are **out of scope for v1 Phase 4** (prose-only edit first).
- **FR-UI-5 — Owned + drift-tracked + gated.** The authoring route(s), template, and the in-app IO
  helper are **generated, owned, schema-hashed**, and join `--check`. Emitted when authoring is
  enabled — **gate on a `--pages-authoring` flag** on `generate backend` (default off; requires
  `--pages`). Mounted on the existing `pages_router`.
- **FR-UI-6 — Pipe/CLI consumable.** `generate backend` (and the cap-dev-pipe `--lang python` flow)
  accept the gate flag with no change to the owned-spine protection model.

### B. Non-functional
- **NFR-UI-1 — Local-first, single-user, no auth** (matches existing content-pages non-reqs). The
  disk-write endpoint is acceptable **only** in that context; documented as such.
- **NFR-UI-2 — Path safety.** Slug → filename via a strict slugifier; all writes confined to
  `app/pages/`; reject any path traversal. `pages.yaml` path resolved by convention from the `app/`
  package location (project root = parent of `app/`).
- **NFR-UI-3 — No SDK import at runtime.** Validation is emitted-owned code, not an SDK dependency.
- **NFR-UI-4 — Minimal new runtime deps.** Add `pyyaml` to the generated `requirements.txt` **only
  when `--pages-authoring`**; do **not** add `markdown`.

### 3. Non-Requirements (v1)
- No live markdown preview (regen to render). · No auto-regeneration / "publish" button that shells
  to the SDK. · No delete/reorder pages via UI. · No editing of owned templates/`base.html`/nav via
  UI. · No WYSIWYG. · No multi-user/auth/remote. · Phase 4 edits prose only (not title/nav metadata).

---

## Implementation Plan (phased; builds on Foundation)

> **Sequencing:** Foundation (Cap 1 + Cap 2) → Phase 1 → 2 → 3 → 4. Each phase is independently
> shippable and round-trip-verifiable against `strtd8/`.

### New SDK artifacts (in `backend_codegen/`, gated by `--pages-authoring`)
1. **`pages_authoring.py`** — renderers for the authoring layer:
   - `render_pages_io()` → **`app/pages_io.py`** (owned, schema-hashed, kind `pages-io`): in-app
     helpers — `project_root()` (from `__file__`), `slugify(slug)`, `validate_entry(...)` (mirrors
     `parse_pages` rules: required keys, `^/` slug, dup check), `append_page(slug,title,nav_label)`
     (structured append to `pages.yaml` + full re-parse), `write_prose(name, md)`, `read_prose(name)`,
     `list_pages()`. Uses `pyyaml` (`safe_load`) for read/dup-check; append preserves the file body.
   - `render_pages_authoring_routes()` → appended into **`app/pages.py`** (kind stays `pages-router`,
     or a sibling `app/pages_admin.py` kind `pages-authoring`): `GET /ui/pages`, `POST /ui/pages`,
     `GET /ui/pages/<name>/edit`, `POST /ui/pages/<name>` — all via `Jinja2Templates`, request-first.
   - `render_pages_authoring_template()` → **`app/templates/pages/_authoring.html`** (owned, kind
     `pages-authoring`, extends `base.html`): the add form + textarea + the authored-pages list +
     the "regenerate to publish" notice.
2. **`derived.py`** — `render_requirements` gains an `authoring: bool` param to append `pyyaml`.
3. **`assembler.py`** — `render_backend(..., pages_text, authoring: bool)`: when `authoring`, extend
   with the authoring artifacts and pass `authoring=True` to `render_requirements`.
4. **`drift.py`** — register the authoring kinds (`pages-io`, `pages-authoring`) in `_renderers()`
   (schema-only, 1-hash — generic). No new multi-hash path needed.
5. **`cli_generate.py`** — add `--pages-authoring` flag (requires `--pages`); thread `authoring` into
   `render_backend` and `--check`.
6. **`backend_codegen/__init__.py`** — export new renderers; extend `__all__`.

### Per-phase mapping
- **Phase 1 (FR-UI-1, FR-UI-5):** `pages_io.py` (`validate_entry` + `append_page`) + `GET/POST /ui/pages`
  (form only, no textarea) + template. Round-trip: add a page via the form → `pages.yaml` gains a
  valid entry → `--check` still in_sync (inputs aren't owned) → `generate backend --pages` makes it live.
- **Phase 2 (FR-UI-2):** add the `<textarea>` + `write_prose` + the supported-syntax hint.
- **Phase 3 (FR-UI-3):** make `POST /ui/pages` atomic over (entry + `.md`); add the confirmation +
  concrete regen command; rollback on partial failure.
- **Phase 4 (FR-UI-4):** `list_pages` + `GET /ui/pages/<name>/edit` + `POST /ui/pages/<name>` +
  `read_prose`; assert a UI prose edit leaves `--check` in_sync.

### Tests (`tests/unit/backend_codegen/`)
- `test_pages_authoring.py`: validator rejects (dup slug, bad slug, missing required); `append_page`
  preserves comments + `nav:` and the result re-parses; `slugify` + path-sanitization blocks
  traversal; `write/read/list_prose` round-trip; `requirements.txt` includes `pyyaml` only with
  `--pages-authoring`; authoring artifacts drift-check as schema-hashed; route shapes + request-first.
- Extend `test_cli_backend.py`: `--pages-authoring` requires `--pages`; `--check` in_sync after a
  clean generate.

### Docs to update on execution (not in plan mode)
- SDK `docs/design/CONTENT_PAGES_CAPABILITY_HANDOFF.md` → add **Capability 3 — authoring UI**.
- Consumer `strtd8/docs/USER_FACING_CONTENT_REQUIREMENTS.md` → fold in v0.2 §0 + FR-UI-* (or a sibling
  doc), keeping the tekizai-tekisho boundary (consumer owns UX contract; SDK owns the generator).

## Verification (end-to-end against `strtd8/`)
```
.venv/bin/startd8 generate backend --schema prisma/schema.prisma \
  --ai-passes prisma/ai_passes.yaml --human-inputs prisma/human_inputs.yaml \
  --pages prisma/pages.yaml --pages-authoring --out . --boot-smoke
```
Confirm, per phase:
- `GET /ui/pages` serves the authoring form (with nav).
- Submitting slug/title appends a **valid** entry to `prisma/pages.yaml` (comments + `nav:` intact);
  a bad/dup slug shows an inline error and writes nothing.
- (P2/P3) Submitting with a body writes `app/pages/<name>.md`; the confirmation names the page and
  prints the exact regen command; re-running `generate backend --pages` serves the new page at its slug.
- (P4) Editing an existing page's prose via the UI then `--check` → **in_sync** (prose outside the hash).
- The app boots with only `pyyaml` added (no `markdown`); boot-smoke passes.
- `pytest tests/unit/backend_codegen/ -q` green.

## Phase 5 — Convergent Review (offered)
After this v0.2 + plan, I can run `/new-cnvrg-rvw-prmpt` (dual-doc: requirements + plan) for an
independent architectural pass before any code — recommended given this introduces a runtime
disk-write surface in the generated app.

---

## Implementation Status (2026-06-03) — BUILT + VERIFIED

All three capabilities implemented, tested (140 unit tests + live round-trips against the `strtd8`
golden reference), in the SDK working tree:
- **Cap 1** `backend_codegen/pages_generator.py` (+ `_headers.header_pages`, htmx nav, `drift._PAGES_KINDS`,
  `crud_generator.render_main` tolerant mount); `--pages`. Verified: `/`+`/how-it-works` render w/ nav;
  nav on entity pages; **`.md` edit ≠ drift**, `pages.yaml` edit = drift; **no runtime `markdown`**.
- **Cap 2** `htmx_generator._writable_fields` (reuses `ai_layer._PROVENANCE_OMIT`). Verified: forms omit
  the 6 system fields; list/detail still show them.
- **Authoring (P1–4)** `backend_codegen/pages_authoring.py` → `app/pages_io.py` + `app/pages_admin.py`
  + `_authoring.html`; `--pages-authoring` (requires `--pages`; adds `pyyaml`). Verified via TestClient:
  create (atomic, comment-preserving, dup-safe), edit prose; create → drift-until-regen, prose-edit → in_sync.
- `markdown>=3.0.0` added to `pyproject.toml` core deps (build-time only).

## Focused write-surface review (2026-06-03) — adversarial probe of the disk-write code

Probed the *generated* `pages_io.py`/`pages_admin.py` against hostile/edge manifests (flow-style,
zero-indent, non-mapping root, garbage entries, comment placement, orphan files, special-char titles).

**Fixed (2 graceful-failure gaps):**
- **F-A (Med):** an odd-indent existing manifest made `append_page`'s reparse throw a raw `yaml.YAMLError`
  that bypassed the route's `except PageError` → HTTP 500. (File was never corrupted — write is gated on a
  clean reparse.) → wrapped into a friendly `PageError`; regression test `test_io_odd_indent_manifest_fails_friendly_without_corrupting`.
- **F-B (Low-Med):** `list_pages()` raised on a hand-corrupted manifest → 500 on `GET /ui/pages`/edit;
  non-mapping entries rendered garbage. → `_safe_pages()`/`_find()` make all views tolerant (200 + banner,
  skip non-dicts); verified live.

**Confirmed safe / fixed earlier:** path traversal (slugify + `parent == _PAGES_DIR` check, defense-in-depth);
special-char titles round-trip (safe_dump quoting); `safe_load`/`safe_dump` only (no RCE); destructive-dup
fixed mid-build (validate-before-write).

**Documented, not fixed (fail-safe / out of NFR-UI-1 threat model):** append supports only block-style,
consistently-indented `pages:` (others fail loud, no corruption); orphan `.md` overwrite/rollback-delete;
comment between last page and `nav:` migrates on append (cosmetic); concurrent-POST race (single-user OK);
**raw HTML in prose → self-XSS only (local-only) — GATE ITEM: sanitize before any multi-user/default-on exposure.**

**Verdict:** sound for the gated, local-first, single-user bound. The residual items (raw-HTML, concurrency,
broader manifest shapes) are what a **full CRP should own at the default-on gate**; they don't block the
gated prototype.

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/CONTENT_PAGES_CAPABILITY_HANDOFF.md`  ·  **Size:** 207 lines · 1860 words

```markdown
# SDK Capability Request — Content Pages Generation + Form System-Field Omission

**Date:** 2026-06-03 · **Origin:** `startd8` consumer repo (the StartDate app) · **Status:** ✅ IMPLEMENTED in SDK-home (2026-06-03)
**Consumer source of truth:** `strtd8/docs/USER_FACING_CONTENT_REQUIREMENTS.md` (v0.2, reflective-loop)
**Golden reference (working POC):** `strtd8/prisma/pages.yaml`, `strtd8/app/pages/*.md`, `strtd8/app/poc_pages.py`

> **Implementation status (SDK-home).** All citations below were verified at home (accurate; line
> numbers drift a few lines). Capabilities 1 & 2 are built + verified end-to-end against the golden
> reference; a third capability (UI-driven page authoring) was added on consumer request. Once
> regenerated against the live SDK, the consumer can delete `app/poc_pages.py` + `app/poc_server.py`.
>
> | Capability | Module(s) | CLI | Verified |
> |---|---|---|---|
> | **1 — Content pages** | `backend_codegen/pages_generator.py` (+ `_headers.header_pages`, `htmx_generator.render_base_template` nav, `drift._PAGES_KINDS`, `crud_generator.render_main` tolerant mount) | `generate backend --pages pages.yaml` | `/` + `/how-it-works` render w/ nav; nav on entity pages; `--check` in_sync; **`.md` edit ≠ drift**, `pages.yaml` edit = drift; **app runtime needs no `markdown`** |
> | **2 — Form omission** | `htmx_generator._writable_fields` (reuses `ai_layer._PROVENANCE_OMIT` + `is_id`) | (always) | `profile/form.html` shows only human fields; list/detail still display system fields |
> | **3 — Authoring UI** | `backend_codegen/pages_authoring.py` (`app/pages_io.py` + `app/pages_admin.py` + `_authoring.html`) | `generate backend --pages --pages-authoring` | `/ui/pages` create (atomic entry+`.md`, comment-preserving, dup-safe) + edit prose; `pyyaml` added only when authoring; design-time author + regenerate-to-publish |
>
> **Design key (Cap 1 drift vs prose):** the owned page **shell** template carries the 2-hash
> (schema + pages) header and contains no prose; the rendered markdown lives in an **untracked body
> fragment** `app/templates/pages/_<name>.body.html` (no header → outside `--check`). That is what
> lets "render at generate time" and "a `.md` edit never flags drift" both hold — the exact analogue
> of the AI layer, where the owned harness embeds only the prompt *path*.
>
> **Cap 3 model:** *design-time author + regenerate*. The `/ui/pages` UI writes the generator
> **inputs** (`pages.yaml` entry + `app/pages/*.md`); pages go live on the next `generate backend`
> (so a UI **create** correctly drifts `--check` until regen; a UI **prose edit** stays in_sync). The
> app never imports the SDK — the strict validator is **re-emitted as owned code** in `app/pages_io.py`,
> and `pyyaml` is added to the app's runtime deps **only** with `--pages-authoring`.
>
> **Write-surface review (2026-06-03, adversarial probe of the generated `pages_io.py`/`pages_admin.py`).**
> Two graceful-failure gaps fixed: **(F-A)** an odd-indent existing manifest made the safe-append reparse
> throw a raw `yaml.YAMLError` that bypassed the route handler → 500 (file was never corrupted; write is
> gated on a clean reparse) — now a friendly `PageError`; **(F-B)** `list_pages()` raised on a
> hand-corrupted manifest → 500 on the UI — views now degrade to a banner. Confirmed safe: path traversal
> (slugify + `parent == app/pages/` check), `safe_load`/`safe_dump` only, special-char titles round-trip,
> validate-before-write (a dup slug can't delete existing prose). **Accepted under NFR-UI-1 (local-first,
> single-user, no auth):** block-style/consistent-indent `pages:` only (others fail loud, no corruption),
> orphan-`.md` overwrite, concurrent-POST race, and **raw HTML in prose → self-XSS only.** The last three
> are the **default-on / multi-user gate items** for a full CRP — not blockers for the gated prototype.

> **Boundary (tekizai-tekisho).** The consumer owns the *content/UX contract*, the *manifest shape*, and
> the *operational evidence* below — those are first-hand and authoritative. The *generator capability*
> is SDK-home work: **implement it your way.** The SDK code citations here are **consumer-observed →
> verify-at-home**; they're a starting map, not a prescription. Where this doc and the SDK source
> disagree, the source wins.

---

## BLUF — two independent capabilities requested

1. **Content-pages generation.** Let `generate backend` emit owned, non-entity content pages (a home
   page at `/`, a "how it works" page, etc.) + a site nav, from a new `pages.yaml` manifest +
   markdown prose — analogous to how `ai_passes.yaml` drives the AI layer. Today `/` is 404 and
   `base.html` has no nav.
2. **Form system-field omission (small, independent).** The HTMX form generator emits *every* column
   as required — including `id`/`ownerId`/`source`/`confirmed`/`createdAt`/`updatedAt` — so users are
   asked to hand-type a CUID and timestamps. The SDK **already computes** the omission set for the AI
   edge schema; reuse it in the form generator.

These are decoupled — ship either independently.

---

## Why this is owned-generation, not LLM-authored

Content pages are mechanical (routes + templates + nav from a manifest); only the prose is authored.
This is the same boundary as the AI layer (prompts authored, glue generated) and matches
`IDEAL_TARGET_ARCHITECTURE` ("everything mechanical is generated for $0; UI templated from the
contract"). The prose is the *only* hand-authored surface, exactly like AI-pass prompts.

---

## Capability 1 — Content pages

### The contract (consumer-owned; validated by the POC)

A new `pages.yaml`, parsed with the **same strictness as `parse_ai_passes`** (`ai_layer.py:99` +
`_PASS_KEYS` at `:72` + unknown-key loud-fail at `:108`). Validated instance (golden reference):

```yaml
pages:
  - slug: "/"
    title: "StartDate — Land your next start date"
    nav_label: "Home"            # omit to exclude from nav
    content: pages/home.md       # markdown under app/pages/ (authored prose)
  - slug: "/how-it-works"
    title: "How StartDate works"
    nav_label: "How it works"
    content: pages/how_it_works.md
nav:                             # optional; else derive from nav_label + curated entities
  - { label: "Home",         href: "/" }
  - { label: "Profile",      href: "/ui/profile" }
  - { label: "Proof Points", href: "/ui/proofpoint" }
  - { label: "How it works", href: "/how-it-works" }
```

Allowed per-page keys: `slug` (req), `title` (req), `nav_label` (opt), `content` (req). Loud-fail on
unknown keys.

### Expected generated artifacts (the POC `poc_pages.py` is the executable reference)

| Artifact | Shape |
|---|---|
| `app/pages.py` | A `pages_router = APIRouter()` (mirror `web_router` at `htmx_generator.py:282`) with one GET route per `slug` rendering the page; mounted in `main.py` alongside `all_routers`/`web_router` (`crud_generator.py:128–150`) |
| Owned page template(s) | A content template extending `base.html`; carries the standard provenance header (`_headers.py:15`) |
| `base.html` nav | Inject a `<nav>` built from the manifest nav (today `render_base_template` at `htmx_generator.py:101` is a fixed string literal — needs a generator change; no new templating engine required) |

### Three operational findings from the POC (decide these, don't re-derive)

1. **Render markdown→HTML at GENERATE time, not request time.** The POC rendered at request time and
   had to add a `markdown` *runtime* dependency. Generate-time rendering into the owned template keeps
   the app runtime dependency-free and matches the static owned-generation model. (Tradeoff: a prose
   edit then needs a regen — acceptable, same as any owned artifact. Recommend keeping one drift model.)
2. **Nav must live in `base.html`.** A consumer can't add nav from outside (it would drift) — it's
   structurally an SDK change. The POC nav only appears on the content pages; the entity pages stay
   nav-less until `base.html` carries it.
3. **Nav/CTA links target `/ui/<entity>`, NOT `/<entity>/`.** The bare `/<entity>/` route returns
   **JSON** (the CRUD API); the human HTML pages are `/ui/profile`, `/ui/proofpoint`, … If nav is
   auto-derived from entities, derive it against the `/ui/` prefix.

### Drift / anchoring (mirror the AI layer)

- Generated page routes/templates + the modified `base.html` carry a provenance header and join
  `--check`. Use a three-input header like `header_ai_layer` (`_headers.py:26`): `schema + pages`
  (+ human-inputs if relevant).
- Prose (`app/pages/*.md`) is **outside** the hash — editing prose must not flag drift, same rule as
  AI-pass prompts.
- New `--pages PATH` flag on `backend()` (`cli_generate.py:109`, beside `--ai-passes` at `:132`);
  cap-dev-pipe `--lang python` passes it through. Inputs (`pages.yaml`, `app/pages/*.md`) get anchored.

### Acceptance
- `GET /` returns the rendered home page (HTML); `GET /how-it-works` renders; both carry the nav.
- Nav appears on **every** page (entity + content) and links resolve to `/ui/<entity>` + content slugs.
- `--check` reports `in_sync` after a clean generate; editing a `.md` does **not** flag drift; editing
  `pages.yaml` **does**.
- App runtime needs no markdown dependency.

---

## Capability 2 — Form system-field omission (FR-PG-5)

**Problem:** `app/templates/<entity>/form.html` lists every column as a labeled, `required` input —
including `id`, `ownerId`, `source`, `confirmed`, `createdAt`, `updatedAt`. Users are asked to type a
CUID and ISO timestamps. (Observed on the generated `profile/form.html`.)

**The fix is reuse, not new policy.** The SDK already defines the exact omission set for the AI edge
schema: `_PROVENANCE_OMIT = {"source", "confirmed", "ownerId", "createdAt", "updatedAt"}`
(`ai_layer.py:42`), applied at `:290–293` (also dropping PKs). The HTMX **form** generator
(`htmx_generator.py`) does not apply it. Apply the same omission (+ PK/`id`) in the form generator so
forms expose only human-authored fields, with human-readable labels.

**Acceptance:** `profile/form.html` shows only `name/title/company/industry/summary/...` — never
`id`/`ownerId`/`source`/`confirmed`/`createdAt`/`updatedAt`. System/provenance fields are auto-managed
(as they already are on create: `ownerId="local"`, `source="user"`, timestamps server-set).

---

## How to consume the golden reference

The POC is a hand-built stand-in for exactly what Capability 1 should generate. In `strtd8/`:
- `prisma/pages.yaml` — the manifest instance (the input contract).
- `app/pages/home.md`, `app/pages/how_it_works.md` — the authored prose (the only hand-authored surface).
- `app/poc_pages.py` — a throwaway router that reads the manifest, renders the markdown, serves the
  slugs, and emits the nav. **This is the reference behavior to generate** (it renders at request time;
  the SDK should do the equivalent at generate time per finding #1).
- Run it: `uvicorn app.poc_server:app --port 8766` → `/` and `/how-it-works` render with nav.

The durable artifacts (`pages.yaml`, the `.md` files) are intended to become real generator inputs
once Capability 1 lands; `poc_pages.py`/`poc_server.py` are throwaway and will be deleted.

---

## Citations (consumer-observed; verify-at-home)
- Strict manifest parse pattern: `ai_layer.py:99` (`parse_ai_passes`), `:72` (`_PASS_KEYS`), `:108` (unknown-key fail).
- Omission set to reuse: `ai_layer.py:42` (`_PROVENANCE_OMIT`), `:290–293`.
- Base template (string literal, no nav seam): `htmx_generator.py:101` (`render_base_template`).
- Web router pattern to mirror: `htmx_generator.py:282` (`web_router`); mount in `crud_generator.py:128–150` (`render_main`/`all_routers`).
- Provenance headers (1-input vs 3-input): `_headers.py:15` (`header_standard`), `:26` (`header_ai_layer`).
- CLI entry + flag precedent: `cli_generate.py:109` (`backend`), `:132` (`--ai-passes`).

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
