# Convergent Review Prompt

**Generated:** 2026-07-04 17:55:34 UTC
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
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-ctxseed/docs/design/context-seed-refactor/PLAN.md` | 173 lines · 1298 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-ctxseed/docs/design/context-seed-refactor/REQUIREMENTS.md` | 219 lines · 2048 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/Users/neilyashinsky/Documents/dev/startd8-ctxseed/docs/design/context-seed-refactor/crp-focus.md` | 46 lines · 442 words |

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

## Focus: pressure-test the Essential vs Accidental complexity boundary

This refactor pivoted at v0.4 from *relocating* accidental complexity to *eliminating* it. Weight
your review on whether the v0.4/v2.0 shape is truly the minimal essential-complexity form — and
whether it quietly introduces new accidental complexity of its own.

**Primary asks (please answer each with Summary / Rationale / Assumptions / Suggested improvements):**

1. **Is the dependency-inversion diagnosis correct and complete?** §0.2 of REQUIREMENTS claims the
   root accidental complexity is that `core.py` conflates (a) shared-helper library, (b) aggregator,
   (c) handler home, forcing phases to import back from `core` and forcing the `__getattr__` shim.
   Is that the real root, or a symptom? Is there a *simpler* essential shape than the proposed
   `handler_support.py` (leaf) ← `phases/*` ← `core` (aggregator)?

2. **`handler_support.py` vs folding into `shared.py`.** The plan creates a *new* leaf module rather
   than dumping the 15 helpers into the existing `shared.py`, arguing single-responsibility (shared =
   seed-task parsing; handler_support = phase plumbing). Is a new module the right call, or does it
   add a module without earning its keep? Would 2 modules (e.g. `telemetry_support` + `config_types`)
   be clearer, or is that over-splitting?

3. **Shim deletion / import-order risk.** Step 6 deletes `core.__getattr__` + the `TYPE_CHECKING`
   guard + `__init__.__getattr__`, making `core.py` import all handlers eagerly. Does eager import at
   module load risk a *different* cycle or import-order fragility (e.g. a handler that transitively
   imports something that imports `core`)? What must be proven before deleting the shim?

4. **Wrapper-repoint blast radius.** FR-9 repoints `context_seed_handlers.py` import lines (44 test
   files + 5 active src consumers + 4 on-hold Artisan consumers depend on it) while keeping `__all__`
   fixed. Is asserting `__all__` equality sufficient, or can a repoint change *identity/binding*
   semantics that a consumer or a `mock.patch` relies on?

5. **Patch-Migration Protocol adequacy.** The plan flags that some current
   `context_seed_handlers._ensure_context_loaded` patches (11×) may already be vacuous. Is the
   "prove the mock binds (assert called)" gate enough to catch a silently-broken test, or is a
   stronger check needed (e.g. a temporary sentinel that raises if the real function is hit)?

6. **Un-removed accidental complexity.** Does the plan *preserve* any accidental complexity it could
   opportunistically remove within the behavior-preserving boundary (duplicated per-handler boilerplate
   — `_log_task_boundary_*`, provenance, span capture — that an `AbstractPhaseHandler` template method
   could absorb; dead `__all__` entries; unused re-exports)?

**Do NOT relitigate (settled):**
- Behavior-preserving boundary: no algorithm / prompt / scoring / control-flow changes. This is a pure
  structural refactor.
- `IntegrationEngine.integrate` (~947 LOC) is out of scope (NR-6) — different file/class.
- The compat wrapper is kept working, not retired (NR-7) — retirement is a separate Tier-2 migration.
- The five handlers are mutually independent (grep-verified) — don't re-derive.

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-ctxseed/docs/design/context-seed-refactor/PLAN.md`  ·  **Size:** 173 lines · 1298 words

```markdown
# Context Seed Extraction & Decomposition — Implementation Plan

**Version:** 2.0 (dependency-inversion elimination — supersedes v1.0's pure-move)
**Date:** 2026-07-04
**Tracks:** REQUIREMENTS.md v0.4
**Branch:** `refactor/context-seed-phases-extraction`

---

## Why v2.0 replaces v1.0

v1.0 mirrored the `design.py` "core-dependent phase" flavor — phases importing shared symbols
*back from* `core`, surfaced through a lazy `__getattr__` shim. That flavor **is** the accidental
complexity (a dependency inversion), so v1.0 relocated the mess and grew the shim. v2.0 eliminates it.

## Target architecture (acyclic, one-way dependency arrows)

```
handler_support.py  (leaf: config, listeners, telemetry/hash/provenance helpers)
shared.py           (leaf: seed-task parsing — already clean, imports no core)
        ▲
        │  import
phases/{plan,scaffold,design,implement,integrate,test_phase,review,finalize}.py
        ▲
        │  import (eager, no shim)
core.py  →  pure aggregator: class ContextSeedHandlers  (~200 LOC)
        ▲
        │  re-export (public __all__ unchanged)
context_seed_handlers.py (compat wrapper, kept working — NR-7)
```

No arrow points *back* into `core`. The `__getattr__` shim and `TYPE_CHECKING` design guard are
**deleted** because nothing needs them once phases depend on leaves instead of the aggregator.

## Step 0 — Extract the stranded substrate (enables everything else)

Move the ~15 leaf helpers/classes (FR-6 list) from `core.py` → new `handler_support.py`.
Verified leaf: their bodies reference no `*PhaseHandler`/aggregator (the only such refs in that
region are in `__all__` and the shim, which are being deleted anyway). `handler_support.py` imports
only external deps + `shared` + `tracing`. Repoint `phases/design.py`'s `from core import (…)` →
`from handler_support import (…)` in the same step and confirm the design tests stay green — this
proves the leaf module works before we pile the other four handlers onto it.

## Per-handler extraction recipe (mechanical, repeatable)

For handler `H` → `phases/<mod>.py` (after Step 0 lands `handler_support.py`):

1. **Create `phases/<mod>.py`.** Copy `design.py`'s header import block; keep only what `H` uses.
2. **Import shared symbols from `handler_support`/`shared`** — NOT `core` — exactly the symbols `H`
   consumes (per-handler list below; same symbol sets, new home).
3. **Cut `H`'s class body verbatim** from `core.py` into the new module.
4. **Aggregator:** add `H` to `core.py`'s eager top-level phase imports (acyclic now — no local
   import, no shim entry).
5. **`phases/__init__.py.__all__`:** add `"<mod>"`.
6. **Migrate that handler's mock-patch targets** (see Patch-Migration Protocol) — patch at
   `phases.<mod>.<symbol>`, the point of lookup.
7. **Run the handler's dedicated test file(s)** with `PYTHONPATH=src` — green before commit.

Once all five are out, **delete** `core.__getattr__`, the `TYPE_CHECKING` design guard, and the
`__init__.py` design `__getattr__`. Repoint the compat wrapper's import lines (handlers from
`phases`/aggregator, helpers from `handler_support`/`shared`); assert its `__all__` is unchanged.

### Shared-symbol import contract (same sets, sourced from `handler_support`/`shared`)

| Handler → module | Imports (from `handler_support` unless noted) |
|---|---|
| `implement.py` | `EditModeClassification, HandlerConfig, PerFileMode, SeedTaskUnit, _coerce_optional_float, _compute_design_results_hash, _dict_to_gen_result, _log_task_boundary_complete, _log_task_boundary_start` |
| `integrate.py` | `HandlerConfig, SeedTaskUnit, ArtisanIntegrationListener, OTelIntegrationListener, _build_provenance_links, _capture_task_span_context, _log_task_boundary_complete, _log_task_boundary_start`; `_ensure_context_loaded` from `shared` |
| `test_phase.py` | `HandlerConfig, _build_provenance_links, _capture_task_span_context, _compute_design_results_hash, _compute_gen_file_hash, _format_review_prompt, _log_task_boundary_complete, _log_task_boundary_start, _log_task_timing` |
| `review.py` | `HandlerConfig, _build_provenance_links, _capture_task_span_context, _coerce_optional_float, _compute_design_results_hash, _compute_gen_file_hash, _format_review_prompt, _get_review_template, _log_task_boundary_complete, _log_task_boundary_start, _log_task_timing` |
| `finalize.py` | `HandlerConfig` |

## Patch-Migration Protocol (the highest-risk step — FR-15)

Planning found **20 mock-patch sites** against `context_seed_handlers.*` / `context_seed.core.*`.
Two patterns matter:

- **Correct model (already in tree):** `patch("…context_seed.phases.plan._load_enriched_seed")`
  — patches the symbol *in the phase module that looks it up*. This is the target shape after a move.
- **At-risk sites:** e.g. `test_integrate_phase.py` patches `context_seed_handlers._ensure_context_loaded`
  (11×), and `test_implement_auto_commit.py` patches `context_seed_handlers.subprocess` (5×). These
  patch the *wrapper's* re-exported binding, not the binding the handler actually calls. Today the
  handler is in `core.py`; after the move it's in `phases/<mod>.py`. **The lookup namespace changes.**

**Protocol per handler:**
1. Before moving, run the handler's test file and confirm each relevant patch actually takes effect
   (the mock is asserted-called, not vacuously green). Any patch that is *already* a no-op is flagged.
2. After moving, repoint each patch to `…context_seed.phases.<mod>.<symbol>`.
3. Re-run; confirm the mock is exercised (add an `assert mock.called` if none exists, to prove the
   patch binds — prevents preserving a pre-existing vacuous patch).

## Ordering (each step = one commit)

0. **`handler_support.py`** — extract the stranded substrate; repoint `phases/design.py` to it;
   green design tests. *This is the keystone: it proves the leaf module before any handler moves.*
1. **`finalize.py`** — needs only `HandlerConfig`; ~840 LOC; validates the handler recipe. Tests:
   `test_finalize_partial_manifest.py`, `test_finalize_status_rollup.py`, `test_context_seed_review_finalize.py`.
2. **`integrate.py`** — ~380 LOC; listener/`SeedTaskUnit` imports **and** the `_ensure_context_loaded`
   patch cluster (11 sites, repointed to `phases.integrate`). Tests: `test_integrate_*` (5 files).
3. **`test_phase.py`** — ~850 LOC; review-template shared helpers.
4. **`review.py`** — ~2,180 LOC; large but self-contained. Tests: `test_review_*` (4 files).
5. **`implement.py`** — ~4,650 LOC flagship, last, recipe fully de-risked. Tests: `test_implement_*` (7 files).
6. **Delete the shims** — remove `core.__getattr__`, the `TYPE_CHECKING` design guard, and the
   `__init__.py` design `__getattr__`; repoint the compat wrapper's import lines; assert `__all__`
   unchanged on wrapper + package `__init__`. `core.py` is now the pure aggregator.

## Part B — Method decomposition (per handler, after it lands)

Once handler `H` is in its own file, decompose its >200-line methods into named private steps.
Behavior-preserving: pure extraction, no control-flow change. Confirmed targets:
- `implement.py`: `execute` (~1,137), `_execute_with_inner_loop` (~706), `_tasks_to_chunks` (~733).
- `review.py`: largest methods (~384 `execute` + others).
Decompose only after the handler's test file is green post-move (so a decomposition regression is
isolated from a move regression).

## Part C — `IntegrationEngine.integrate` (resolves OQ-1: it is NOT a context_seed handler)

The ~947-line `integrate` lives in `IntegrationEngine` in `integration_engine.py` — a **different
class in a different file**, unrelated to `IntegratePhaseHandler`. It should be a **separate,
independently-sequenced refactor** (its own branch/PR), not conflated with the phase extraction.
The helpers it needs already exist (`_attempt_repair`, `_run_anzen_gate`, `_run_semantic_checks`),
so decomposition is an orchestration-extraction. Deferred out of this plan's Parts A/B.

## Verification (every step)

```bash
PYTHONPATH=src python3 -c "from startd8.contractors.context_seed_handlers import (
  ImplementPhaseHandler, IntegratePhaseHandler, TestPhaseHandler,
  ReviewPhaseHandler, FinalizePhaseHandler, ContextSeedHandlers); print('OK')"
PYTHONPATH=src pytest tests/unit/contractors/<handler-test-files> -q   # per-step
PYTHONPATH=src pytest tests/unit/contractors -q                        # full package before merge
```

## Definition of done

- `core.py` reduced to the pure aggregator (~200 LOC); `handler_support.py` + 5 `phases/*.py` added.
- **No `__getattr__` shim** anywhere in `context_seed` (grep proves 0 hits); no phase imports `core`.
- Compat wrapper + `context_seed/__init__.py` public `__all__` **unchanged** (assert via `__all__` equality test).
- Every migrated patch proven to bind (mock asserted-called); 0 patches target `context_seed.core.*`
  or `context_seed_handlers.*` for a symbol a handler *calls* (grep proves).
- Full `tests/unit/contractors` green with `PYTHONPATH=src`.

---

*Plan v2.0 — dependency-inversion elimination. Supersedes v1.0 (pure move). Tracks REQUIREMENTS v0.4.*

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-ctxseed/docs/design/context-seed-refactor/REQUIREMENTS.md`  ·  **Size:** 219 lines · 2048 words

```markdown
# Context Seed Phase-Handler Extraction & Method Decomposition — Requirements

**Version:** 0.4 (Essential/accidental-complexity hardening — ready for CRP)
**Date:** 2026-07-04
**Status:** Ready for review
**Owner:** SDK maintainers
**Type:** Structural refactor (behavior-preserving)

---

## 0. Planning Insights (Self-Reflective Update)

> Changes between v0.1 (pre-planning) and v0.2 (post-planning). The planning pass revealed
> 6 corrections, all confirmed by grepping the actual tree.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| Compat wrapper / `__init__.py` may need edits | `core.__getattr__` (L404) already serves `DesignPhaseHandler` lazily; extending its table serves all five with **zero** wrapper/`__init__` edits | FR-9/FR-10 strengthened to "unchanged, assert via diff" |
| Patch-target risk is small ("2 tests patch core.*") | **20 patch sites**; 11 patch `context_seed_handlers._ensure_context_loaded`, 5 patch `…_handlers.subprocess` — these bind the *wrapper's* re-export, not the handler's call path | FR-15 upgraded to a first-class **Patch-Migration Protocol** with a bind-proof gate |
| `integrate` (~947 LOC) is an `IntegratePhaseHandler` method | It is `IntegrationEngine.integrate` in `integration_engine.py` — **different class, different file** | OQ-1 resolved → moved to Non-Requirement NR-6 / Plan Part C (separate refactor) |
| Handlers may be coupled to each other | No handler references another; only the aggregator instantiates them | Each handler extracts **independently** (parallel-safe, per-commit) |
| Aggregator import style unknown | Must be a **local** import inside `create_handlers` (module-top import would recreate the core↔handler cycle) | FR-8 specifies local import, mirroring L163 precedent |
| Correct post-move patch shape unknown | Tree already demonstrates it: `patch("…phases.plan._load_enriched_seed")` (8×) | Protocol has a concrete model to copy |

**Resolved open questions:**
- **OQ-1 → Resolved.** `integrate` is `IntegrationEngine.integrate` (different file); descoped to NR-6 / Plan Part C.
- **OQ-2 → Interleave.** Extract handler, prove green, then decompose *that* handler's methods — isolates move-regressions from decomposition-regressions.
- **OQ-3 → No.** Wrapper-re-exported helpers (`_format_review_prompt`, `_get_review_template`) are col-0 module-level in `core`, not handler-internal; they stay in `core`.
- **OQ-4 → Lazy/local.** Aggregator local-imports handlers to avoid the load-time cycle.
- **OQ-5 → 20 sites.** Enumerated; the `_ensure_context_loaded` (11) and `subprocess` (5) clusters are the exposure. Some may already be vacuous — the Protocol proves each binds.

### 0.1 Lessons-Learned Hardening (v0.3)

> Consulted `Lessons_Learned/sdk/Design_Docs_LESSONS_LEARNED.md`. Applied:

- **[Leg 4 §5 — Import-Path-Driven Feature Duplication]** — module-per-thing splits invite
  duplicate/ambiguous import paths → mandated the single `core.__getattr__` table as the *sole*
  lazy-resolution point (no per-site re-imports), and the `test_phase.py` naming guard (FR-3).
- **[Phantom-reference audit]** — every symbol named in FRs (handlers, helpers, line ranges,
  test files) was grep-verified against the tree; added §5 Reference Audit.
- **[CRP steering memory]** — least-reviewed artifact is this brand-new PLAN; settled/do-not-relitigate:
  the `design.py` precedent (proven) and the "behavior-preserving, no algorithm change" boundary.

### 0.2 Essential vs. Accidental Complexity Ledger (v0.4 — the pivot)

> External-lens review (2026-07-04) rejected the v0.3 direction as *relocating* accidental
> complexity rather than eliminating it. v0.3 proposed **extending** `core.__getattr__` with 5 new
> entries and mandating the wrapper stay byte-identical — both of which **lock in** the accidental
> complexity. v0.4 reverses this: distill to essential complexity.

**Root accidental complexity: a dependency inversion.** `core.py` conflates three roles — (a) the
shared-helper library, (b) the composition root (`ContextSeedHandlers` aggregator), and (c) the
handler home. Because the shared helpers live in the *same file* as the aggregator, extracted phases
must import *back* from `core`, but `core` (as aggregator) must import the phases → a cycle, papered
over with a lazy `__getattr__` shim and `TYPE_CHECKING` guards. The `design.py` "core-dependent phase"
flavor I proposed to mirror **is itself the accidental-complexity artifact**, not a precedent to copy.

| Complexity | Essential or Accidental? | Verdict |
|---|---|---|
| Multi-phase orchestration, retry, telemetry, checkpointing logic | **Essential** | Preserve verbatim |
| Phases importing shared symbols *back from* `core` | **Accidental** (dependency inversion) | **Eliminate** — phases import from a leaf |
| `core.__getattr__` lazy shim + `TYPE_CHECKING` design guard | **Accidental** (exists only to break the self-inflicted cycle) | **Delete** |
| `_ensure_context_loaded` traveling shared→core→wrapper→patched (3 hops) | **Accidental** (stranded re-export) | **Collapse** — patch at the leaf/phase |
| `HandlerConfig` + 15 helpers/listeners stranded in the aggregator file | **Accidental** (wrong home) | **Move** to a leaf support module |
| Compat wrapper existing at all | **Accidental**, but load-bearing (5 active + 4 on-hold src consumers, 44 test files) | **Keep working**, do NOT byte-freeze; retirement is NR-7 |

**Verified enablers (grep, 2026-07-04):** `shared.py` imports nothing from `core` (clean leaf);
`_ensure_context_loaded` is *already* in `shared.py`; the stranded helpers + both listeners are leaf
(no `*PhaseHandler`/aggregator refs in their bodies); only `prime_review.py` imports `core` directly.
∴ moving the stranded helpers to a leaf module breaks the cycle with **no** new cycle introduced.

---

## 1. Problem Statement

`src/startd8/contractors/context_seed/core.py` is **9,952 lines** — the single largest
file in the SDK and the dominant "god file" surfaced by the 2026-07-04 structural review.
It holds five implementation-half phase handlers plus their monster methods. A sibling
`context_seed/phases/` subpackage already exists and holds the design-half handlers
(`plan.py`, `scaffold.py`, `design.py`), proving the module split was **started but not
finished**.

The file already carries a special maintenance burden documented in CLAUDE.md: a
`context_seed_handlers.py` compat wrapper, a mock-patch-target rule, and a "re-export new
symbols" rule — all workarounds that exist *because* the file is oversized.

| Component | Current State | Gap |
|-----------|--------------|-----|
| `core.py` | 9,952 lines, 13 classes, 5 phase handlers | Should be ~1,050 lines (shared substrate + aggregator) |
| `phases/` subpackage | Holds plan/scaffold/design only | Missing implement/integrate/test/review/finalize |
| `ImplementPhaseHandler.execute` | ~1,137-line single method | Should decompose into named sub-steps |
| `integration_engine.py::integrate` | ~947-line method | Should orchestrate named stages |
| `_execute_with_inner_loop`, `_tasks_to_chunks` | ~706 / ~733 lines | Should decompose |

## 2. Requirements

### Part A — Handler Extraction

- **FR-1.** Move `ImplementPhaseHandler` (core.py L654–5307) to `phases/implement.py`.
- **FR-2.** Move `IntegratePhaseHandler` (core.py L5475–5856) to `phases/integrate.py`.
- **FR-3.** Move `TestPhaseHandler` (core.py L5856–6709) to `phases/test_phase.py`
  (NOT `test.py` — pytest would collect it).
- **FR-4.** Move `ReviewPhaseHandler` (core.py L6748–8929) to `phases/review.py`.
- **FR-5.** Move `FinalizePhaseHandler` (core.py L8929–9769) to `phases/finalize.py`.
- **FR-6.** Create a leaf support module `context_seed/handler_support.py` holding the ~15 shared
  helpers/classes currently stranded in `core.py` (`HandlerConfig`, `PerFileMode`,
  `EditModeClassification`, `SeedTaskUnit`, `ArtisanIntegrationListener`, `OTelIntegrationListener`,
  `_dict_to_gen_result`, `_capture_task_span_context`, `_build_provenance_links`, `_log_task_timing`,
  `_log_task_boundary_start`, `_log_task_boundary_complete`, `_coerce_optional_float`,
  `_compute_gen_file_hash`, `_compute_design_results_hash`, `_format_review_prompt`,
  `_get_review_template`). It imports only external deps + `shared.py` + `tracing.py` — never `core`.
  It is a distinct concern from `shared.py` (which owns seed-task parsing), so it is its own module.
- **FR-7.** Each extracted phase module imports its shared symbols from `handler_support`/`shared` —
  **never from `core`**. This severs the cycle. `phases/design.py`'s existing
  `from …context_seed.core import (…)` is **repointed** to `handler_support` in the same pass
  (opportunistic elimination of the pre-existing inversion).
- **FR-8.** With phases no longer importing `core`, `core.py` becomes a **pure aggregator**
  (the `ContextSeedHandlers` class) that imports all handlers **eagerly at module top** — no local
  imports, no lazy resolution. `core.py.__getattr__` shim and the `TYPE_CHECKING` design-handler
  guard are **deleted** (they existed only to break the self-inflicted cycle).
- **FR-9.** `context_seed_handlers.py` compat wrapper keeps its public `__all__` **unchanged**, but
  its *import lines* are repointed to the symbols' real homes (handlers from `phases`, helpers from
  `handler_support`/`shared`). Assert public surface via an `__all__` equality test, not a byte diff.
- **FR-10.** `context_seed/__init__.py` keeps its public `__all__` unchanged; its `__getattr__`
  design-handler shim is deleted (handlers now import eagerly with no cycle).
- **FR-11.** `phases/__init__.py.__all__` gains the five new module names.

### Part B — Method Decomposition

- **FR-12.** After each handler lands in its own file, decompose its methods exceeding
  ~200 lines into named private sub-steps. The orchestrating method should read as a
  sequence of named calls.
- **FR-13.** Decomposition is behavior-preserving: extracted sub-steps are pure moves of
  existing logic; no control-flow or side-effect changes.

### Cross-cutting

- **FR-14.** No public behavior change. Full `pytest` suite passes with `PYTHONPATH=src` pin.
- **FR-15.** Migrate every `mock.patch` target referencing a symbol a moved handler *calls*
  to the handler's new module path (patch where looked up, not where re-exported), per the
  **Patch-Migration Protocol** (PLAN.md). Each migrated patch must be proven to bind (mock
  asserted-called), because some current wrapper-targeted patches may already be vacuous and a
  naive path-swap would silently preserve the vacuity. 20 sites enumerated; the exposure is the
  `_ensure_context_loaded` (11) and `subprocess` (5) clusters.

## 3. Non-Requirements

- **NR-1.** ~~Does NOT extract shared helpers into a separate module.~~ **REVERSED in v0.4** —
  extracting the stranded helpers to `handler_support.py` (FR-6) is now the *central* move; it is
  what makes the cycle-elimination possible. Kept here as a visible record of the v0.3→v0.4 pivot.
- **NR-2.** Does NOT touch the ON-HOLD Artisan handlers (`artisan_phases/`), except to repoint their
  *import lines* if a symbol they consume moves home (mechanical, no logic change).
- **NR-3.** Does NOT change any handler's algorithm, prompts, or scoring.
- **NR-4.** Does NOT rename `core.py` or the compat wrapper.
- **NR-5.** Does NOT decompose methods in files other than the five extracted handlers.
- **NR-6.** Does NOT refactor `IntegrationEngine.integrate` (~947 LOC) — it is a different class
  in a different file (`integration_engine.py`), unrelated to `IntegratePhaseHandler`. Tracked
  separately as PLAN.md Part C (its own branch/PR). *(Was OQ-1; resolved during planning.)*
- **NR-7.** Does NOT retire the `context_seed_handlers.py` compat wrapper. Its ~5 active src
  consumers, 4 on-hold Artisan consumers, and 44 test files make deletion a separate migration
  (Tier 2). This refactor keeps the wrapper working with its public surface intact; only its
  internal import lines are repointed (FR-9).

## 4. Open Questions

*All v0.1 open questions were resolved during the planning pass — see §0. No open questions remain.*

## 5. Reference Audit (phantom-reference discipline)

Every code symbol named in this document was verified against the tree on 2026-07-04:

| Symbol / claim | Verified |
|---|---|
| 5 handler classes + line ranges in `core.py` | ✓ grep of col-0 `class` defs |
| `core.__getattr__` at L404 serving `DesignPhaseHandler` | ✓ read L404–408 |
| Aggregator `ContextSeedHandlers.create_handlers` local-imports design at L163 | ✓ read L9769–9952 |
| Per-handler shared-symbol import contract | ✓ per-handler body grep |
| `phases/` holds plan/scaffold/design | ✓ directory listing |
| Dedicated per-handler test files exist (implement×7, integrate×5, review×4, finalize×3) | ✓ `ls tests/unit/contractors` |
| 20 mock-patch sites; `_ensure_context_loaded`×11, `subprocess`×5 | ✓ grep of `patch(` in tests |
| `IntegrationEngine.integrate` is in `integration_engine.py`, not a phase handler | ✓ grep class/def |
| Correct patch precedent `patch("…phases.plan._load_enriched_seed")` | ✓ grep of tests |

---

*v0.4 — Essential/accidental-complexity hardening (external-lens pivot). Reversed the v0.3
"extend the shim / byte-freeze the wrapper" direction, which relocated accidental complexity;
v0.4 eliminates it: extract stranded helpers to a leaf `handler_support.py` (FR-6), phases import
from the leaf not `core` (FR-7), delete the `__getattr__` shim (FR-8/FR-10). Net: `core.py`
9,952 → ~200 LOC, and 3 accidental-complexity mechanisms deleted rather than grown.
Prior: v0.3 lessons hardening (3 lessons); v0.1→v0.2: 6 corrections, 5 OQs resolved. Ready for CRP.*

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
