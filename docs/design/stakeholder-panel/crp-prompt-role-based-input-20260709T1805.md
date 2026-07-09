# Convergent Review Prompt

**Generated:** 2026-07-09 18:05:23 UTC
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
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-rolebased-input/docs/design/stakeholder-panel/ROLE_BASED_INPUT_INGESTION_PLAN.md` | 124 lines · 1124 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-rolebased-input/docs/design/stakeholder-panel/ROLE_BASED_INPUT_INGESTION_REQUIREMENTS.md` | 236 lines · 2371 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/Users/neilyashinsky/Documents/dev/startd8-rolebased-input/docs/design/stakeholder-panel/crp-focus-role-based-input.md` | 27 lines · 269 words |

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

# CRP Focus — Role-Based Input Ingestion (reqs v0.4 + plan v1.0)

## Least-reviewed / highest-risk surfaces (spend review budget here)
- **FR-14 — the guarded backlog append** (new WRITE into a project's `ENHANCEMENTS_BACKLOG.md`).
  Pressure-test: idempotency by `<!-- startd8-panel-backlog: <sid> -->` marker (concurrent runs, malformed
  existing marker, marker injected by hostile synthesis text), atomic write (temp+rename, partial-write,
  symlink target), "append-only / never-rewrite" (insertion point when the footer is absent/duplicated),
  preview-default vs `--yes`, fail-closed on missing/unwritable file.
- **FR-12 — the opt-in LLM `input_kind` refinement** (new paid boundary). Pressure-test: bounding/caps,
  enum-validation + out-of-enum discard, fail-open to the deterministic kind, never mutating `lane`/`raw_text`,
  index-alignment of the `{index: kind}` mapping (off-by-one / dropped items), cost-ceiling + missing-key.
- **FR-3/FR-5 — the residual pass + "nothing dropped" coverage invariant.** Is the union-covers-every-line
  invariant well-defined (what counts as "boilerplate"? banner/disclaimer lines, blank lines, sub-bullets)?
  Can residual double-count a line the structured pass already claimed?
- `synthesis_bridge/extract.py` — never CRP'd; the new dual-pass (structured + residual) refactor.

## Settled — do NOT relitigate
- The stakeholder-panel **prototype posture** (shipped #172–174) and its prompts/synthesis structure.
- The **two existing lanes'** meaning (FIELD_LEVEL / NON_DECIDABLE); adding UNSTRUCTURED is decided.
- **$0 deterministic default** as the core; LLM strictly refine-only/opt-in (OQ-3 resolved).
- The **10-kind taxonomy** and `input_kind` naming (OQ-1/OQ-2 resolved) — challenge assignment logic, not the enum.
- Bucket separation: **no content generation** (NR-1) — challenge whether any FR violates it, not the rule.

## Cross-repo / integration notes
- `KickoffTranscript` (Pydantic, `kickoff_view/models.py`) gains `posture` (FR-8) — check downstream loaders.
- The `TriageReport` schema grows (`UNSTRUCTURED` lane, `input_kind`, kind counts) — additive; flag any strict
  external consumer.

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-rolebased-input/docs/design/stakeholder-panel/ROLE_BASED_INPUT_INGESTION_PLAN.md`  ·  **Size:** 124 lines · 1124 words

```markdown
# Role-Based Input Ingestion — Implementation Plan

**Version:** 1.0 (paired with REQUIREMENTS v0.3)
**Date:** 2026-07-09
**Target:** `src/startd8/stakeholder_panel/synthesis_bridge/` + `kickoff_view/models.py` + `cli_panel.py`

> Deterministic, `$0`. Increments are independently landable; each ends green + ruff-clean.

## Sequencing (dependency order)

```
M1 models         (Lane.UNSTRUCTURED, InputKind[10], Candidate.input_kind)   ← foundation
M2 extract        (FR-1 vocab, FR-2 format, FR-3 residual pass)
M3 classify       (FR-4 input_kind assignment; residual + decision/constraint heuristics)
M4 report         (FR-11 residual+kind sections/counts)
M5 posture        (FR-8 KickoffTranscript.posture, FR-9 health note, FR-10)
M6 backlog        (FR-6 render_backlog_section, FR-7 CLI + FR-14 guarded append)
M7 LLM Tier-2     (FR-12 opt-in --llm-kind refine — IN SCOPE per OQ-3)
M8 guards         (FR-13 coverage/regression/golden/mapping + append-idempotency + LLM-refine tests)
```

## Per-milestone

### M1 — models (`synthesis_bridge/models.py`)
- `Lane`: add `UNSTRUCTURED = "UNSTRUCTURED"`. `counts()` auto-includes it (iterates `Lane`).
- New `class InputKind(str, Enum)` (10): recommendation/suggestion/question/risk/tension/feedback/content/**decision**/**constraint**/uncategorized.
- `Candidate`: add `input_kind: InputKind = InputKind.uncategorized`; thread into `to_dict()`.
- `TriageReport.counts()` add a `by_kind` sub-count (or a sibling `kind_counts()`).
- **Risk:** `to_dict()["kind"]` already = report-type label → the per-candidate field MUST be `input_kind` (not `kind`). Guard: grep no `["kind"]` collision.

### M2 — extract (`extract.py`)
- FR-1: extend `_SECTION_PREFIXES` with `"prioritized ux"/"ux improvement" → "UX Improvements"`,
  `"quick win" → "Quick Wins"`, `"bigger bet" → "Bigger Bets"`.
- FR-2: add a `_BOLD_LEAD_RE = ^\s*\*\*(.+?)\*\*` capture inside a known section (dedupe vs numbered/bullet);
  strip the trailing `**`.
- FR-3 residual pass: track claimed line-indices during the structured pass; a second sweep emits an
  `UNSTRUCTURED` Candidate (source_section = the heading it fell under, or `"(unsectioned)"`) for each
  unclaimed non-boilerplate line/para (skip: blank, `## `-only headings already consumed, table separators,
  the banner/disclaimer lines, <8 chars). Set `lane=UNSTRUCTURED` at construction; classify refines kind.
- **Design:** refactor the single-pass loop into `extract_structured()` + `extract_residual(text, claimed)`;
  `extract_candidates` = union. Keeps the structured path byte-identical for existing fixtures.

### M3 — classify (`classify.py`)
- FR-4: `_KIND_BY_SECTION` map (Recommendations→recommendation, Open Questions→question, Risk Register→risk,
  Tensions→tension, UX Improvements/Quick Wins/Bigger Bets→suggestion). Apply to every candidate.
- Residual heuristic `_infer_kind(text)` (ordered): trailing `?`→question; `must|never|cannot|only|limit|required`→constraint; `decided|will|chosen|ratified|agreed`→decision; `suggest|recommend|should|could|consider`→suggestion; else content. Never returns None (→ uncategorized).
- Preserve existing lane logic; UNSTRUCTURED items stay UNSTRUCTURED (never promoted to FIELD_LEVEL — NR-2),
  but still get a `reason`/`suggested_owner` (`"unstructured — preserved for a human"`, owner `human / requirements`).

### M4 — report (`models.py::to_markdown`/`to_dict`)
- Add `## UNSTRUCTURED (preserved — received but not previously accounted for)` section listing verbatim items + input_kind.
- Add per-`input_kind` count line to the Counts header. `to_dict` gains `kind_counts` + `input_kind` per candidate.

### M5 — posture (`kickoff_view/models.py`, `route.py`, `classify.py`)
- FR-8: `KickoffTranscript`: add `posture: str = "scrutiny"` (Pydantic maps the JSON key; default covers old transcripts).
- FR-9: `build_triage` passes `posture` into `health_check`; add the prototype backlog-bound note.
- FR-10: scrutiny path unchanged (default posture → no new health note; residual/kind additive only).

### M6 — backlog + guarded append (`synthesis_bridge/backlog.py` new, `cli_panel.py`)
- FR-6: `render_backlog_section(report, *, title, project) -> str` — pure, consumes the `TriageReport`; groups by
  section/kind; SYNTHETIC & UNRATIFIED banner; open tensions/questions as decisions. Byte-stable output.
- FR-7: `kickoff panel backlog <session> [--project] [--json] [--out FILE] [--append FILE] [--yes]`.
- FR-14 guarded append (`_append_backlog_section(path, section, session_id)`):
  - **idempotent** — wrap the rendered section in `<!-- startd8-panel-backlog: <sid> --> … <!-- /startd8-panel-backlog: <sid> -->`; on re-run, replace ONLY the bytes between the matching markers (regex on the sid); absent → insert.
  - **append-only / never-rewrite** — insert before the doc's closing `*italic footer*` if present, else EOF; never touch other bytes (diff must be a single contiguous insertion/replacement).
  - **preview-default** — without `--yes`, print the unified diff and exit 0 (no write); `--append … --yes` writes atomically (temp+rename).
  - **fail-closed** — target must be an existing writable file; else error (never create the canonical doc).

### M7 — LLM Tier-2 (`synthesis_bridge/kind_llm.py` new; `extract_llm.py` precedent)
- FR-12: opt-in `--llm-kind [--model …]`. Batches UNSTRUCTURED (+ `content`/`uncategorized`) candidates into one
  bounded prompt → returns `{index: input_kind}`; validate each against the 10-enum, discard out-of-enum (keep
  deterministic). Never touches `lane`/`raw_text`. Fail-open: any error → deterministic result + a health note.
  Budget-guarded (cheap model default; cap N items/call).

### M8 — guards (`tests/unit/stakeholder_panel/`)
- `test_synthesis_bridge_residual.py`: FR-5 coverage invariant (union of lanes' verbatim text ⊇ non-boilerplate
  lines) on **prototype** + **scrutiny** fixtures; the "7 Open Questions only" regression now surfaces
  UX/Quick Wins/Bigger Bets + typed tensions; the 10-kind mapping table (section + heuristic incl.
  decision/constraint); scrutiny golden additive-only.
- `test_backlog_append.py`: preview-default (no write) → diff; `--yes` writes; **re-run is idempotent** (byte-equal,
  no dup block); append-only (surrounding bytes unchanged); fail-closed on missing file.
- `test_kind_llm.py`: `$0` stub agent refines a residual item's kind; out-of-enum discarded; missing-key/error →
  deterministic fallback + health note; lane/raw_text never mutated.
- Update existing triage tests for the new `counts()` keys / report sections.

## Backward-compat / risk register
- **Transcript schema:** `Candidate.to_dict` + `TriageReport.to_dict` gain keys → update any exact-shape tests;
  additive for external consumers.
- **`counts()` keys** grow by `UNSTRUCTURED` → update assertions.
- **Extraction of previously-dropped content in scrutiny** is a (desired) behavior change → golden re-baseline
  with an explicit note; guard that structured (numbered/bullet) items are byte-identical.
- **`input_kind` naming** must not collide with the report `["kind"]`.

## Definition of done
- All FRs mapped; FR-13 guards green; ruff clean; scrutiny golden additive-only; the household prototype
  synthesis fixture triages with 0 dropped lines and non-empty UX/Quick Wins/Bigger Bets/Tensions.

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-rolebased-input/docs/design/stakeholder-panel/ROLE_BASED_INPUT_INGESTION_REQUIREMENTS.md`  ·  **Size:** 236 lines · 2371 words

```markdown
# Role-Based Project Input — Complete, Honest Ingestion (incl. a Residual Capture Lane)

**Version:** 0.4 (User decisions folded — pre-CRP)
**Date:** 2026-07-09
**Status:** Draft (reflective loop complete; CRP pending)
**Author:** Neil Yashinsky (with Claude)

> ### 0.2 Decisions (v0.4) — the five OQs resolved by the user
> - **OQ-1 → 3rd lane + tag.** `Lane.UNSTRUCTURED` *and* an `input_kind` on every candidate (FR-3/FR-4).
> - **OQ-2 → 10-kind taxonomy.** Added `decision` + `constraint` to the 8 (FR-4).
> - **OQ-3 → build the LLM Tier-2 now.** The opt-in `input_kind` refinement ships this increment (FR-12).
> - **OQ-4 → in-report only** (default kept; no sidecar).
> - **OQ-5 → guarded append.** The backlog renderer also appends into an existing `ENHANCEMENTS_BACKLOG.md`
>   under write-guards — this **lifts NR-4** and adds a write surface (FR-7 + FR-14 write-safety).

> **Strategic frame.** The SDK's ability to generate *useful, role-based input on a project* — via the
> stakeholder panel — is a **differentiator**. For that to hold, panel output must be **fully
> captured, typed, and routed**; it must never be silently dropped just because it did not fit a
> predefined structure. This spec closes the ingestion gaps (A–D) and adds the differentiating piece:
> a **residual/unstructured capture lane** (E) that preserves *and types* everything the structured
> extractor doesn't claim.

---

## 0. Planning Insights (Self-Reflective Update)

> Planning this against the real `synthesis_bridge` + `kickoff_view` code (v0.1 → v0.2) surfaced 5
> corrections; two were structural.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| `build_triage` can read `transcript.posture` for B/D | **`KickoffTranscript` (Pydantic, `kickoff_view/models.py`) exposes `objective`/`synthesis`/`status` but NOT `posture`** — the field exists in the session JSON (#174) but is unmapped by the model | **Added FR-8:** declare `posture` on `KickoffTranscript` (maps the JSON key) before any posture-aware routing. A phantom reference if unaddressed. |
| Residual could be "just a `kind` tag" on NON_DECIDABLE | `TriageReport.to_markdown` has a **fixed two-section layout** (FIELD_LEVEL + NON_DECIDABLE) and `counts()` enumerates `Lane`; dropped content has no home | **Lane and kind are ORTHOGONAL** (FR-3/FR-4): a 3rd `Lane.UNSTRUCTURED` gives residual its own section+count; an `input_kind` tag types EVERY candidate. Do both. |
| Fixing extraction might yield field-level candidates | `classify._detect_value_path` marks FIELD_LEVEL only on a verbatim allow-listed `Entity.field` token; UX recs never contain one | Confirmed: A/E restore **completeness**, not field-level yield. The apply pipeline still correctly gets ~0 for prototype (recorded as NR-2, not a gap). |
| Backlog render (C) is a fresh parse of the synthesis | `build_triage` already produces a structured `TriageReport`; a 2nd parse would drift | **C consumes the `TriageReport`** (one extraction, two renderers) — FR-6. DRY. |
| Only prototype synthes drop content | The bold-lead item-format miss (`**T1 — … OPEN**` not matching the numbered/bullet regex) affects the **`Tensions` section in BOTH postures** | A's format-robustness + E's residual pass are **posture-independent**; only D's health note and the section *vocabulary emphasis* are posture-flavored. |

**Resolved open questions (from v0.1):**
- **OQ (persistence path) → the `TriageReport` IS the artifact.** Residual lives in the report (`to_dict`/`to_markdown`), persisted wherever the caller writes the report. A separate sidecar file is optional (kept as OQ-4).
- **OQ (LLM typing) → deterministic default, LLM is an opt-in Tier-2** mirroring the `extract_llm.py` precedent. Residual is ALWAYS captured deterministically; an LLM only *refines* `input_kind`.

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied the SDK lessons before CRP. Each changed the draft:

- **Phantom-reference audit (Leg 13/16)** — grepped every named symbol. Found `transcript.posture` unmapped
  on `KickoffTranscript` → **FR-8** (declare it). All other symbols (`Lane`, `Candidate`, `TriageReport`,
  `extract_candidates`, `classify`, `health_check`, `build_triage`, `PanelSynthesis.text`) verified present.
  See §Reference Audit.
- **Overloaded-term co-location (Leg 12/16)** — `kind` is heavily overloaded in this SDK (`backend_codegen`
  "kinds", deterministic-provider "kinds", `TriageReport.to_dict()["kind"]` = the report type). → name the new
  candidate field **`input_kind`** (never bare `kind`), and keep it on `Candidate`, not a new co-located concept.
- **Single-source "nothing silently dropped" contract (Leg 16)** — the invariant is stated in
  `kickoff-panel triage --help` and `TriageReport` docstring (existing FR-5). This spec makes it TRUE; it cites
  that contract as the owner, and does not restate it as a new rule free to drift.
- **Under-generation is a false-pass (Leg 16 #—)** — a residual lane could be gamed by emitting empty/near-empty
  fragments. → FR-3 sets a **minimum-content floor** + a completeness invariant test (FR-13) that asserts the
  union of all lanes' verbatim text covers every non-boilerplate synthesis line.
- **CRP steering** — least-reviewed artifact = this doc (brand new) + `synthesis_bridge/extract.py` (never
  CRP'd). Settled / do-not-relitigate: the prototype posture itself (#172–174), the 2 existing lanes' meaning,
  the "$0 deterministic default" stance.

---

## 1. Problem Statement

The stakeholder panel produces role-based project input (a facilitated **synthesis**). The
`synthesis_bridge` triages that synthesis into actionable lanes. Today it **under-reads** any synthesis
whose shape differs from the original scrutiny structure — silently dropping the majority of a
`prototype` synthesis — which both violates the stated "nothing dropped" contract and wastes the very
role-based input that is the differentiator.

| Component | Current State | Gap |
|-----------|--------------|-----|
| `extract.py` section vocab | `{recommendation, open question, risk register, tension}` | prototype headers `Prioritized UX Improvements / Quick Wins / Bigger Bets` unrecognized → **dropped** (A) |
| `extract.py` item format | captures only numbered/bullet lines | bold-lead items (`**T1 — … OPEN**`) → **dropped**, both postures (A) |
| unrecognized/orphan content | not captured at all | any content outside a known section+format is **silently lost** — no residual bucket (E) |
| `build_triage` posture awareness | reads `objective`/`synthesis` only | can't tailor routing/health to `posture` (B/D) — and `posture` isn't even on the model (FR-8) |
| input typing | items carry only `source_section` | no **type-of-input** classification (suggestion/feedback/…) across items (E) |
| backlog handoff | none (done by hand — household §7) | no tool to fold a synthesis into a backlog doc (C) |

---

## 2. Requirements

### A — Structured extraction completeness
- **FR-1 (section vocabulary).** `extract_candidates` recognizes the prototype section headers
  (`Prioritized UX Improvements`, `Quick Wins`, `Bigger Bets`) in addition to the existing four, via the
  same prefix-match mechanism. Header→label additions are the single source; `classify` routes them.
- **FR-2 (item-format robustness).** Within a recognized section, capture **bold-lead** items
  (`**Label — …**`) and definition-style lines, not only `1.`/`-` lines — so `Tensions` (both postures)
  and bold UX items are captured. Preserve the ≥8-char noise floor.

### E — Residual / unstructured capture (the centerpiece)
- **FR-3 (residual lane).** Add `Lane.UNSTRUCTURED`. After the structured pass, a **residual pass**
  emits an `UNSTRUCTURED` candidate for every non-boilerplate synthesis line/paragraph the structured
  pass did **not** already claim (content under unknown headings; recognized-section lines that matched
  no item pattern). Each preserves **verbatim** `raw_text` (Mottainai). A minimum-content floor
  (≥ N chars / not a bare heading or separator) prevents empty-fragment gaming.
- **FR-4 (`input_kind` typing — orthogonal to lane).** Every `Candidate` (all lanes) carries an
  `input_kind: InputKind` — the *type of input received*. **Taxonomy (10, closed enum):**
  `recommendation, suggestion, question, risk, tension, feedback, content, decision, constraint,
  uncategorized`. Deterministic assignment: from `source_section` where known (Recommendations→
  `recommendation`, Open Questions→`question`, Risk Register→`risk`, Tensions→`tension`,
  UX Improvements/Quick Wins/Bigger Bets→`suggestion`); for residual, a keyword heuristic —
  trailing `?`→`question`; `must|never|cannot|only|limit|required`→`constraint`;
  `decided|will|chosen|ratified|agreed`→`decision`; `suggest|recommend|should|could|consider`→
  `suggestion`; else `content`. Unmappable → `uncategorized` (never dropped). The heuristic is the
  deterministic floor; the LLM Tier-2 (FR-12) may only *refine* it.
- **FR-5 (nothing-dropped, now true).** The union of all candidates' verbatim text covers every
  non-boilerplate line of the synthesis. This upgrades the existing FR-5 contract from *claimed* to
  *verified* (see FR-13). Applies to **both** postures.
- **FR-11 (report surfaces residual + kind).** `TriageReport.to_markdown`/`to_dict` gain an
  `## UNSTRUCTURED (preserved — received but not previously accounted for)` section and expose
  `input_kind` per candidate and a per-kind count summary.

### B / D — Posture-aware routing + honest framing
- **FR-8 (map posture onto the transcript).** Declare `posture: str = "scrutiny"` on `KickoffTranscript`
  so the session-JSON key (#174) is available to consumers. *(Blocks B/D.)*
- **FR-9 (posture-aware framing/health).** `build_triage` reads `transcript.posture`. For `prototype`,
  `health_check` adds a non-blocking note: *"prototype/UX synthesis — items are design recommendations,
  not `entity.field` values; route to the requirements backlog, not the VIPP apply pipeline."* Field-level
  detection still runs (harmless; a prototype synthesis MAY name a field) but is not expected to fire.
- **FR-10 (scrutiny unchanged).** For `posture="scrutiny"` (default / absent), routing and the report
  are behavior-compatible except for the additive residual/kind surfaces (guarded by FR-13).

### C — Backlog renderer
- **FR-6 (render a backlog section from the report).** A pure function
  `render_backlog_section(report, *, title, project) -> str` consumes a `TriageReport` and emits a
  markdown backlog section (grouped by `source_section`/`input_kind`; SYNTHETIC & UNRATIFIED banner;
  preserves open tensions + open questions as decisions) — the shape produced by hand for
  household `ENHANCEMENTS_BACKLOG.md §7`.
- **FR-7 (CLI surface + guarded append).** `startd8 kickoff panel backlog <session> [--project] [--json]
  [--out FILE] [--append FILE]` — default prints the section to stdout (`$0`, read-only); `--out` writes a
  new file; `--append` performs a **guarded append** into an existing `ENHANCEMENTS_BACKLOG.md` per FR-14.
- **FR-14 (write-safety for the guarded append).** The append is: **preview-by-default** (prints the
  diff/would-write unless `--append --yes`); **append-only** (never rewrites or reorders existing content —
  inserts a new section before the doc's closing footer, or at EOF); **idempotent** (each session's block
  carries a `<!-- startd8-panel-backlog: <session_id> -->` marker; re-running replaces only that marked
  block, never duplicates); **fail-closed** if the target isn't a writable existing file. Carries the
  SYNTHETIC & UNRATIFIED banner.

### Cross-cutting
- **FR-12 (deterministic $0 default; LLM opt-in Tier-2 — IN SCOPE).** All of A–E run deterministically at
  `$0` and always produce a complete, typed triage. A **flag-gated, bounded** LLM pass
  (`--llm-kind [--model …]`) may only **refine `input_kind`** on `UNSTRUCTURED` (and unconfidently-typed)
  items — it **never** generates/rewrites content (NR-1), **never** changes `lane` or `raw_text`, and is
  bounded (batched, capped, cheap-model default). Output is validated against the closed 10-kind enum; an
  out-of-enum answer is discarded (keeps the deterministic kind). Off by default; degrades to the
  deterministic result on any error (missing key / cost ceiling / parse fail), with a health note.
- **FR-13 (completeness + backward-compat guards).** Tests: (a) coverage invariant (FR-5) on both a
  prototype and a scrutiny synthesis fixture; (b) the real household prototype synthesis now surfaces
  UX Improvements/Quick Wins/Bigger Bets + typed Tensions (regression vs the "7 Open Questions only"
  bug); (c) scrutiny golden unchanged except additive residual/kind; (d) `input_kind` mapping table.

---

## 3. Non-Requirements

- **NR-1 (no content generation).** Residual capture **preserves and types** existing panel output; it
  never authors content (bucket 4). No summarization/rewriting of the residual text.
- **NR-2 (residual/UX is never FIELD_LEVEL).** UNSTRUCTURED and UX-suggestion items are never auto-mapped
  to `entity.field`; they never enter the VIPP apply pipeline. 0 field-level candidates for a prototype
  synthesis is CORRECT, not a defect.
- **NR-3 (no synthesis re-structuring).** This does not build the latent structured-synthesis arrays
  (`kickoff_view` FR-UX-15/16). It parses the prose `synthesis.text` as today.
- ~~**NR-4 (no auto-write into project docs).**~~ **LIFTED in v0.4 (OQ-5).** The renderer MAY append into an
  existing `ENHANCEMENTS_BACKLOG.md`, but ONLY under the FR-14 write-guards (preview-default, append-only,
  idempotent-by-session-marker, fail-closed). It still never *creates* the project's canonical docs from
  scratch and never rewrites existing content.
- **NR-5 (no new posture).** Uses the existing `scrutiny`/`prototype` postures only.

---

## 4. Open Questions — RESOLVED (v0.4)

- **OQ-1 → 3rd lane + `input_kind` tag.** `Lane.UNSTRUCTURED` + `input_kind` on every candidate (FR-3/FR-4).
- **OQ-2 → 10-kind taxonomy** (added `decision` + `constraint`) (FR-4).
- **OQ-3 → build the LLM Tier-2 now** — opt-in, bounded, refine-only (FR-12).
- **OQ-4 → in-report only** (no sidecar).
- **OQ-5 → guarded append** into `ENHANCEMENTS_BACKLOG.md` (FR-7 + FR-14; lifts NR-4).

*(No open questions remain. Residual forks for CRP: the write-safety of the guarded append (FR-14) and the
bounded LLM refinement (FR-12) are the least-settled surfaces.)*

---

## Reference Audit (phantom-reference check)

| Symbol | Where | Exists? |
|--------|-------|---------|
| `Lane` (FIELD_LEVEL, NON_DECIDABLE) | `synthesis_bridge/models.py:19` | ✅ (add UNSTRUCTURED) |
| `Candidate` (title/source_section/raw_text/lane/reason/…) | `models.py:26` | ✅ (add `input_kind`) |
| `TriageReport` (counts/to_dict/to_markdown) | `models.py:50` | ✅ (add residual section) |
| `extract_candidates` / `_SECTION_PREFIXES` / regexes | `extract.py:66/25/32` | ✅ |
| `classify` / `_detect_value_path` / `_SECTION_ROUTING` | `classify.py:49/35/24` | ✅ |
| `health_check` | `classify.py:76` | ✅ |
| `build_triage` (reads session_id/objective/synthesis) | `route.py:25` | ✅ |
| `PanelSynthesis.text` | `kickoff_view/models.py:100` | ✅ |
| `KickoffTranscript.posture` | `kickoff_view/models.py:111` | ❌ **absent → FR-8** |
| `startd8 kickoff panel …` CLI group | `cli_panel.py` | ✅ (add `backlog`) |

---

*v0.4 — Post-planning (5 corrections, 2 structural) + lessons-hardening (5 lessons) + 5 user decisions
folded (10-kind taxonomy, LLM Tier-2 in scope, guarded backlog append). Centerpiece = the
residual/unstructured capture lane (E). Deterministic `$0` core + opt-in LLM refine; scrutiny
backward-compatible. Ready for CRP.*

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
