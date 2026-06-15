# Convergent Review Prompt

**Generated:** 2026-06-12 03:40:24 UTC
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
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-concierge/docs/design/kickoff/CONCIERGE_MCP_WRITE_PATH_PLAN.md` | 180 lines · 1378 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-concierge/docs/design/kickoff/CONCIERGE_MCP_REQUIREMENTS.md` | 271 lines · 2912 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/Users/neilyashinsky/Documents/dev/startd8-concierge/docs/design/kickoff/crp-focus-concierge-write-path.md` | 29 lines · 271 words |

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

# CRP Focus — Concierge Write-Path Increment

Weight the review on the **write-path security surface**. The read-only core (`survey`/`assess`)
already shipped and is not under review; focus on `instantiate-kickoff` + `log-friction`, the
safe-writer, and the OQ-7 boundary.

## Where we need input most

1. **Safe-writer confinement is airtight (Plan Step 2; PQ-3).** The single chokepoint claims
   path confinement via `resolve()` + `is_relative_to(project_root)`, reject `..`/symlink escape,
   no-clobber, atomic `os.replace`. Is this sufficient against: a `project_root` that is itself a
   symlink into a sensitive tree; TOCTOU between resolve and write; case-insensitive/UNC FS edge
   cases; a planned target whose parent dir is a symlink? What guard is missing?

2. **OQ-7 boundary leak-check (Plan Step 3/4).** The claim: the MCP tool has *no* `apply`
   parameter and calls builders only, so it physically cannot write; the CLI is the sole writer
   at human privilege. Is that boundary actually leak-proof as designed, or does any path
   (preview content containing secrets, a builder with a side effect, the shared WritePlan) let
   an MCP-invoked call cause a write or disclose something it shouldn't?

3. **Idempotency / partial-existing semantics (PQ-2).** navig8 already has *some* kickoff files.
   Plan says per-file `new`/`exists`, skip-existing unless `--force`, never merge YAML. Is
   skip-existing the right default, or does it silently leave a half-instantiated package that
   reads as "done"? Should re-run report drift the way `generate backend --check` does?

4. **Friction-log durability (PQ-1).** `log-friction` is the first writer of the friction log.
   Markdown-table append (human-canonical, brittle id-parse) vs JSON sidecar + rendered markdown
   (two files, against F-10's "one durable home"). Which survives F-10 (uncommitted-artifact
   loss) and stays machine-appendable? Is there a single-file option that is both?

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-concierge/docs/design/kickoff/CONCIERGE_MCP_WRITE_PATH_PLAN.md`  ·  **Size:** 180 lines · 1378 words

```markdown
# Concierge Write-Path Increment — Implementation Plan

**Version:** 0.1 (Draft — pre-CRP)
**Date:** 2026-06-11
**Status:** Draft — for Convergent Review before implementation
**Parent requirements:** [`CONCIERGE_MCP_REQUIREMENTS.md`](CONCIERGE_MCP_REQUIREMENTS.md) v0.3
(FR-C2/C3/C7/C9/C13/C14; OQ-7 resolution)
**Builds on:** the shipped read-only core (`src/startd8/concierge/`, commit `d44c9c4c`) and CLI
parity (`src/startd8/cli_concierge.py`, commit `3834570d`), branch `feat/concierge-mcp`.

> **The increment:** add the two *write* actions — `instantiate-kickoff` and `log-friction` —
> under the OQ-7 resolution: **MCP returns previews only; the CLI is the sole writer**, running
> at the human's own filesystem privilege. The security surface (path confinement, no-clobber,
> idempotency) is the reason this increment gets a CRP pass before code.

---

## 1. Scope & Non-Scope

**In:** `instantiate-kickoff` (project the kickoff package into a consuming project) and
`log-friction` (append a structured friction item to the project's Concierge friction log).
The shared **safe-writer** chokepoint. Template packaging (FR-C7 prerequisite). CLI write
surface + MCP preview surface. Security + idempotency tests.

**Out:** `derive-contract` (separate deferred follow-on — net-new AST). Real-content generation.
Any MCP-side disk write (forbidden by OQ-7). Gate/approval recording (FR-C2).

---

## 2. Design

### Step 0 — Template packaging (FR-C7 prerequisite)

The kickoff templates live in `docs/design/kickoff/templates/` which is **not shipped in the
wheel**. Mirror the `help_content/*.yaml` precedent:

- New package dir `src/startd8/concierge_templates/` holding the kickoff package templates
  (`KICKOFF_INTRO_TEMPLATE.md`, `KICKOFF_INPUTS_EXPLAINED_TEMPLATE.md`,
  `inputs/{business-targets,observability,conventions,build-preferences}.yaml`) and the optional
  authoring trio (`REQUIREMENTS_TEMPLATE.md`, `PLAN_TEMPLATE.md`, `TEST_USERS_TEMPLATE.md`,
  `HOW_TO_AUTHOR_REQUIREMENTS_AND_PLANS.md`, `REQUIREMENTS_AND_PLAN_FORMAT.md`).
- Register in `pyproject.toml` `[tool.setuptools.package-data]` (`concierge_templates/**`) and
  `setup.py` `package_data` (both are kept in sync today).
- Loader reads via `importlib.resources.files("startd8.concierge_templates")` — works from a
  wheel, not just a source checkout.
- **Anti-fork:** `docs/design/kickoff/templates/` stays canonical for humans; the packaged copy
  is the shipped artifact. A test asserts the two trees are byte-identical (the FR-W14 pattern),
  so they can't silently diverge.

### Step 1 — SDK preview builders (pure; what MCP returns; FR-C3)

In `src/startd8/concierge/writes.py` (new), two pure functions that compute *planned writes*
without touching disk:

- `build_instantiate_plan(project_root, posture) -> WritePlan` — resolves each kickoff-package
  file's destination + rendered content (provenance pre-filled per posture), plus per-file
  status (`new` / `exists` / `would-overwrite`). Posture ∈ {`prototype`, `production`}.
- `build_friction_entry(project_root, *, friction, what_happened, implication) -> WritePlan` —
  computes the next friction id, the entry markdown, the target log path, and whether the log
  needs scaffolding (absent) vs appending (present).

`WritePlan` = `{ "writes": [{path, action: new|append|overwrite, content|append_text, bytes}],
"warnings": [...], "schema_version": N }`. This is exactly what `handle_concierge_tool` returns
over MCP (preview), and exactly what the CLI feeds the safe-writer.

### Step 2 — The safe-writer chokepoint (security core; FR-C2/C3)

`src/startd8/concierge/safe_write.py`: `apply_write_plan(project_root, plan, *, force=False)`.
**The single place any Concierge byte reaches disk.** Invariants, each its own guard + test:

1. **Confinement:** every target resolves (`Path.resolve()`) to a path **inside** the realpath
   of `project_root`. Reject `..` traversal and symlink escape (resolve then `is_relative_to`).
2. **No clobber:** `action: new` refuses if the file exists; `overwrite` requires `force=True`.
   `append` only appends (never truncates).
3. **Atomic:** write to a temp file in the same dir + `os.replace` (no partial files on crash).
4. **No directory creation outside the plan:** only `mkdir(parents=True)` for dirs under the
   confined root.
5. Returns a structured result (`written`, `skipped`, `errors`) — never raises past a contained
   per-file error unless confinement itself is violated (that is a hard stop).

### Step 3 — MCP wrapper: preview-only (OQ-7)

`startd8_concierge` gains `instantiate-kickoff` / `log-friction` to its action enum. Over MCP
they call the **builders only** and return the `WritePlan` JSON. **No `apply` parameter exists
on the MCP tool** — it cannot write, by construction (the cleanest expression of OQ-7). The tool
annotation stays `readOnlyHint: True` because the MCP surface genuinely never writes.

### Step 4 — CLI: the sole writer (FR-C13)

`cli_concierge.py` gains:
- `startd8 concierge instantiate-kickoff [ROOT] [--posture prototype|production] [--with-authoring]
  [--apply] [--force]` — default (no `--apply`) prints the preview (files + statuses); `--apply`
  runs `apply_write_plan` at the human's privilege. `--force` needed to overwrite.
- `startd8 concierge log-friction [ROOT] --friction TEXT --what-happened TEXT --implication TEXT
  [--apply]` — default previews the entry; `--apply` appends.
- Exit semantics: advisory exit 0; exit 2 unreadable input; **exit 3** when `--apply` is given
  but a confinement/clobber guard blocked the write (so CI can detect a refused write).

### Step 5 — Tests

- Security (the load-bearing set): traversal (`../../etc/x`), absolute path outside root,
  symlink-escape, clobber-without-force, append-not-truncate, atomicity-on-failure.
- Behavior: instantiate into an empty dir (all `new`); re-run idempotency (all `exists`, no
  change without `--force`); posture provenance (prototype vs production); owners block never
  fabricated (ships flagged). log-friction: scaffold-when-absent, append id increment.
- Anti-fork: packaged templates == `docs/.../templates/` tree.
- CLI: preview exit 0; `--apply` writes; refused write exit 3.

---

## 3. Step → Requirement trace

| Step | Requirements |
|------|--------------|
| 0 Packaging | FR-C7 (prerequisite) |
| 1 Builders | FR-C3 (preview), FR-C7, FR-C9, FR-C11 (schema-versioned) |
| 2 Safe-writer | FR-C2 (confinement), FR-C3 (no silent/over-write), OQ-7 |
| 3 MCP preview | FR-C1, FR-C3, FR-C12 (readOnly stays honest) |
| 4 CLI writer | FR-C13, OQ-7 (sole writer at human privilege) |
| 5 Tests | all of the above |

---

## 4. Open Questions (seeds for CRP)

- **PQ-1 — Friction-log structure.** Append a row to the markdown table (human-canonical but
  brittle to parse for id-increment) vs a structured JSON sidecar (`concierge-friction.json`)
  rendered to the markdown? The read-only `survey`/`assess` don't read it today; `log-friction`
  is the first writer. Lean: JSON sidecar is source-of-truth, markdown is rendered — but that is
  two files where F-10 wanted one durable home.
- **PQ-2 — instantiate-kickoff partial-existing semantics.** A project may already have *some*
  kickoff files (navig8 does). Per-file `new`/`exists` is planned; is a 3-way merge ever wanted,
  or is "skip existing unless --force" sufficient? Lean: skip-existing; never merge YAML values.
- **PQ-3 — Confinement on symlinked/again case-insensitive roots.** `is_relative_to` after
  `resolve()` handles symlinks; do we also need to reject a `project_root` that is *itself* a
  symlink into a sensitive area, or is realpath-confinement enough? (Security — wants the CRP
  security lens.)
- **PQ-4 — `owners` block (tier U).** instantiate ships it deliberately fictional + flagged
  (`.test`); should `--apply` refuse production posture until owners are real, or just warn?
  Lean: warn (advisory posture), never block.
- **PQ-5 — MCP preview payload size.** A full kickoff package is ~6 files of content; returning
  all bytes in the WritePlan is fine here, but is there a cap beyond which preview returns a
  digest + paths only? Lean: cap per-file bytes in the preview, full content via CLI.
- **PQ-6 — Posture default.** Should `instantiate-kickoff` default to `prototype` (zero required
  human input, matches navig8) or refuse without an explicit `--posture`? Lean: default
  prototype, since the whole point is zero-friction start.

---

*Draft 0.1 — pre-CRP. Grounded in the shipped read-only core, the `help_content` packaging
precedent, and the OQ-7 resolution. The security invariants (Step 2) and PQ-1/3/4 are the
intended focus of the Convergent Review.*

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-concierge/docs/design/kickoff/CONCIERGE_MCP_REQUIREMENTS.md`  ·  **Size:** 271 lines · 2912 words

```markdown
# Concierge MCP Command(s) — Requirements

**Version:** 0.3 (Design decisions on OQ-3/OQ-7; CRP deferred to the write-action increment)
**Date:** 2026-06-11
**Status:** Draft — read-only core (`survey`/`assess`) cleared to spike
**Parent role spec:** [`CONCIERGE_FRICTION_LOG_NAVIG8.md`](CONCIERGE_FRICTION_LOG_NAVIG8.md)
(the observed-activity source), [`HITM_ROLE_MODEL_REQUIREMENTS.md`](../HITM_ROLE_MODEL_REQUIREMENTS.md)
(role map; candidate role 3.11)
**Sibling precedents:** [`ROLE_KIT_CLI_REQUIREMENTS.md`](ROLE_KIT_CLI_REQUIREMENTS.md)
(deferred `startd8 kit <role>` advisory CLI — $0/read-only/advisory pattern),
`docs/design/wireframe/WIREFRAME_REQUIREMENTS.md` (the $0/read-only/advisory CLI this mirrors)
**MCP surface basis:** `src/startd8/mcp/gateway.py` — the single-tool-with-actions bridge
(`startd8_workflow` → `get_workflow_tool_schema()` / `handle_workflow_tool()`)

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2, after a thorough planning pass against the
> actual MCP surface, the wireframe machinery, the manifest-extraction code, and the CLI/packaging
> conventions. The pass corrected ~6 of 13 requirements (>30% — the v0.1 was premature against an
> unfamiliar surface, exactly the case this loop is for). The largest correction would otherwise
> have surfaced mid-implementation, when it is 10× more expensive.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| MCP surface = the gateway single-tool-with-actions **bridge** (`get_workflow_tool_schema`/`handle_workflow_tool`) | The **real client-facing server is a SEPARATE repo** — `mcp/startd8-mcp-builder/startd8_mcp.py` (`FastMCP("startd8_mcp")`) — with **discrete `@mcp.tool()` functions** (list_skills, use_skill, help, status, tasks_*), each = Pydantic input + `@mcp.tool(annotations=…)` + async handler importing `startd8.*`. The gateway bridge is library-internal and **not** what the server uses. | **FR-C1 reframed:** `startd8_concierge` is **one `@mcp.tool()`** in the FastMCP server whose Pydantic input carries an `action` field. "Single tool, action-dispatched" survives as a *within-tool* design; registration is `@mcp.tool()`, not the gateway bridge. |
| The tool lives in the SDK (gateway.py) | Logic and registration are in **two packages of the same repo**: `src/startd8/` ships the callable library; the self-contained subproject `mcp/startd8-mcp-builder/` (own `pyproject`=`startd8-mcp`, CLAUDE.md, CI/CODEOWNERS — **tracked in the SDK repo, not a separate repo**) holds the `@mcp.tool()` wrapper alongside its existing 17 `startd8_*` tools. | **New FR-C14 (cross-package split).** Simpler than a cross-repo split; both halves are committed in one repo (also satisfies F-10 durability). |
| `derive-contract` is "a deterministic AST transform, not generation" (implied lightweight) | Pydantic→Prisma introspection is **net-new AST work**; only the *emit* half is reusable (`manifest_extraction/entities.py` `EntityGraph` → `prisma_emitter.render_prisma_schema()`). The introspection front-half does not exist. | **FR-C8 is the heaviest action by far → DEFERRED out of v1** to its own follow-on (resolves OQ-1 granularity). When built, it reuses `prisma_emitter` for the back half only. |
| `assess` wraps a wireframe that "exists" (hoped) | **CONFIRMED:** `build_wireframe_plan()` → `WireframePlan` carries the exact provisioning states; `cli_wireframe.py` is the rendering precedent. | **FR-C6/FR-C10 strengthened** — `assess` is cheap (wrap + summarize); wireframe is the model for the whole JSON/CLI shape. `validate` folds into `assess` (no separate action). |
| `instantiate-kickoff` just copies templates | Templates in `docs/design/kickoff/templates/` are **NOT packaged** (docs tree isn't shipped). Must become package data — `src/startd8/help_content/` is the shipped-data precedent. | **FR-C7 gains a prerequisite:** package the templates (`src/startd8/concierge_templates/`) before the action can read them at a consumer site. |
| annotations "MUST carry readOnlyHint…" at the gateway level | Annotations are a **FastMCP-server** convention (`@mcp.tool(annotations={readOnlyHint, destructiveHint, idempotentHint, openWorldHint})`), absent from `mcp/types.py`. | **FR-C12 retargeted** to the wrapper layer; SDK gateway types unaffected. |

**Resolved open questions:**
- **OQ-1 → Resolved.** v1 = `survey` · `assess` (absorbs `validate`) · `instantiate-kickoff` · `log-friction`. `derive-contract` **deferred** to its own action/follow-on (it is net-new AST work).
- **OQ-2 → Resolved.** Logic in a new `src/startd8/concierge/` package (stable API); registration as a `@mcp.tool()` in the FastMCP-builder repo. Not the gateway, not the SkillRegistry.
- **OQ-4 → Resolved (and deferred).** Pydantic-only front-half is net-new; reuse `prisma_emitter` back-half. Lands with the deferred `derive-contract`.
- **OQ-5 → Resolved.** Package templates as `concierge_templates/` package-data (`help_content/` precedent); read via `importlib.resources`.
- **OQ-6 → Resolved.** `assess` wraps `build_wireframe_plan()`; never recomputes provisioning state.
- **OQ-7 → Open (sharpened).** A FastMCP tool writing into a consumer project path still crosses a trust boundary; `apply:true` + path-confinement (FR-C2) are the controls. Kept for CRP.
- **OQ-3 → Partially resolved.** Mechanism known (own `typer.Typer` app, `cli_queue.py` pattern); the assist/kit/concierge family relationship stays a design choice.

---

## 1. Problem Statement

The **Concierge** is the project-side SDK-onboarding role, defined empirically from the navig8
instantiation (friction log, 10 items). Today every Concierge activity is performed by a human
+ Claude reading docs and running ad-hoc shell/greps; nothing is exposed as a callable surface
an *external AI agent* (the consuming project's own assistant, or a remote orchestrator) can
invoke through the SDK's MCP gateway.

The operating posture is fixed (operator decision 2026-06-07): the Concierge **assists** — it
surveys, derives starters, validates, and advises; it does **not** operate or orchestrate
(it never runs the cascade, never records a gate sign-off, never mutates the consuming repo
without the team driving). MCP commands must encode that posture in their *capabilities*, not
just their docs.

### Gap table

| Concierge activity (observed) | Today | Gap |
|-------------------------------|-------|-----|
| Brownfield asset survey / triage | ad-hoc `find`/`grep`/`Explore` agent | No structured, repeatable survey an agent can call |
| Kickoff package instantiation | hand-copy templates, hand-fill | Not callable; provenance discipline applied by memory |
| Contract derivation from existing models | hand-written by Claude (F-5) | No models→prisma surface; risk of contract↔models drift |
| Inputs/contract validation | `startd8 wireframe` (exists, $0/advisory) | Wireframe covers the cascade view, not the *onboarding-readiness* view |
| Friction capture back to SDK | hand-edited markdown, **lost when uncommitted (F-10)** | No durable, structured capture path |
| Readiness assessment / "what's next" | Claude reads state, narrates | No machine-readable onboarding-state report |

### Why MCP (not just a CLI)

The Role Kit CLI sibling is a *terminal* command for the human operator. The Concierge surface
is for the **consuming project's agent** to self-serve onboarding through the gateway the SDK
already ships — the same way `startd8_workflow` lets an external agent discover/run workflows.
A CLI (`startd8 concierge …`) MAY back the same logic (FR-C9), but the MCP tool is the primary
deliverable here.

---

## 2. Requirements

### Command surface & shape

- **FR-C1 — Single tool, action-dispatched, registered as a FastMCP `@mcp.tool()`.** Expose
  **one** MCP tool, `startd8_concierge`, registered in the FastMCP server
  (`mcp/startd8-mcp-builder/startd8_mcp.py`) the same way `startd8_use_skill` /
  `startd8_status` are: a Pydantic input model carrying an `action` field (enum) +
  `@mcp.tool(annotations=…)` + an async handler that calls the SDK library. (The action-dispatch
  *within* the tool echoes the gateway's `startd8_workflow` shape, but registration is the
  FastMCP discrete-tool pattern, **not** the gateway bridge — see §0.) **v1 actions:**
  `survey` · `assess` · `instantiate-kickoff` · `log-friction`. (`validate` folded into
  `assess`; `derive-contract` deferred — FR-C8.)
- **FR-C2 — Assist-only capability envelope (load-bearing).** No action may: run a generation
  cascade or pipeline pass; record a validation/gate sign-off; promote any artifact out of a
  candidate/estimate provenance state; or write outside the **consuming project** directory.
  The tool *prepares and advises*; the team *decides and runs*. This is a capability boundary,
  not a doc convention.
- **FR-C3 — MCP never writes; the CLI writes (OQ-7 resolution, 2026-06-11).** Over MCP, **all
  actions are read/preview-only**: `survey`/`assess` are pure reads; `instantiate-kickoff`/
  `log-friction` **return the planned content + target path but do not touch disk**. The only
  writer is the CLI (FR-C13), which runs at the human's own filesystem privilege — so **no new
  write trust boundary** is crossed by an LLM-invoked MCP call. Rationale: `apply:true` is a
  *safety* control (no silent writes), not an *authorization* control (an LLM can set it);
  read/preview-only MCP sidesteps the authorization question entirely for v1. If MCP writes are
  later needed, they gate behind a server-side allowlist (`STARTD8_CONCIERGE_ALLOWED_ROOTS`) +
  hard path-confinement, **not** merely `apply:true`. The CLI writer enforces path-confinement
  (realpath within the named project root; reject `..`/symlink escape; no clobber without
  `--force`).
- **FR-C4 — `$0` by default; LLM only where the activity is irreducibly generative.** `survey`,
  `assess`, `validate`, `instantiate-kickoff` (template copy + provenance fill), and
  `derive-contract` (models→prisma is a *deterministic* AST transform, not generation) are all
  $0. Any action that would need an LLM (e.g. a future "draft requirements from PRD") MUST be a
  distinct action that declares its cost and is off by default.

### Per-action behavior

- **FR-C5 — `survey`.** Given a project root, return a structured brownfield triage: detected
  product boundary candidates, existing requirement/PRD docs (+ whether they match the
  extraction format), existing models/entities, test-fixture candidates, path couplings that a
  carve would break (the F-3 grep), and any PII/personal-material risk flags (F-2). Read-only.
- **FR-C6 — `assess`.** Return a machine-readable **onboarding-readiness report**: per kickoff
  input domain (business-targets / observability / conventions / build-preferences) and per
  assembly input (schema / app.yaml / manifests), the provisioning state
  (`authored|estimate|config-default|placeholder|absent`) and what's blocking the next step.
  This is the "what's next" report the team's `NEXT_STEPS.md` is the prose form of. Composes
  with `startd8 wireframe` rather than duplicating it (FR-C10).
- **FR-C7 — `instantiate-kickoff`.** Project the kickoff templates into the consuming project
  with provenance pre-filled per posture (production vs prototype/solo), every value carrying
  honest `provenance`. **Over MCP: returns the planned files + provenance, never writes** (FR-C3);
  the CLI applies them. Never fabricates the `owners`/contacts block
  (tier U — no LLM starter; ships flagged). **Prerequisite (planning):** the templates currently
  live under `docs/design/kickoff/templates/`, which is **not shipped in the wheel**; this action
  depends on first packaging them as package-data (`src/startd8/concierge_templates/`, following
  the `help_content/` precedent) and reading via `importlib.resources`. The packaging task is a
  named dependency of this FR, not an afterthought.
- **FR-C8 — `derive-contract` (DEFERRED — own follow-on, not v1).** Deterministically derive a
  `schema.prisma` candidate from the project's existing Pydantic models, carrying the navig8
  derivation rules as transform logic: semantic-id→`nodeKey`+`@@unique`, `Dict`/`List`→`Json`,
  cross-list trace→join model, hyphenated enum value normalization, builtin-name renames,
  computed fields stay computed. Emits the contract **plus a derivation report** naming every
  deviation and exclusion (so the Architect can ratify — the gate stays theirs, FR-C2).
  Preview-by-default. **Deferred because** planning showed the Pydantic→IR introspection
  front-half is net-new AST work (only the emit half reuses
  `manifest_extraction/prisma_emitter.render_prisma_schema()`); it is heavier than the other
  four actions combined and earns its own reflective pass. v1 ships without it; navig8's contract
  was derived by hand and stands.
- **FR-C9 — `log-friction`.** Produce a structured friction item for the project's Concierge
  friction log. **Over MCP: returns the entry + target path** (FR-C3); the CLI appends it. The
  log lives **in the consuming project, which the team owns and commits** (the F-10 lesson) —
  never the only copy untracked in the SDK tree.

### Output, integration, durability

- **FR-C10 — Compose, don't duplicate.** Where the SDK already ships the capability
  (`startd8 wireframe` for cascade view; `generate backend --check` for drift), the Concierge
  action *calls and summarizes* it, never reimplements. `assess` wraps wireframe;
  `derive-contract`'s output is validated by re-running wireframe.
- **FR-C11 — Structured, schema-versioned results.** Every action returns a stable,
  schema-versioned JSON object (the gateway/`handle_workflow_tool` convention). Human-readable
  rendering is a separate concern (the CLI/Rich layer, FR-C13).
- **FR-C12 — Tool annotations honest about the posture.** The MCP tool/action schema MUST carry
  correct annotations: `readOnlyHint` true for survey/assess/validate; `destructiveHint` false
  for all (Concierge never destroys); writes gated behind `apply`. These annotations are how a
  calling agent *knows* the assist-only envelope without reading prose.
- **FR-C13 — CLI parity. [DONE — read-only actions]** `startd8 concierge survey|assess` backs
  the same `handle_concierge_tool` code path as the MCP tool (one logic, two front doors —
  FR-W16). Rich by default, `--json` for the schema-versioned payload, advisory exit 0 / exit 2
  on unreadable input (FR-W9). Implemented in `src/startd8/cli_concierge.py`, registered in
  `cli.py` beside `assist`. Write actions will land here as the CLI is the sole writer (OQ-7).
- **FR-C14 — Cross-package split (SDK logic / MCP-builder wrapper), one repo.** The callable
  logic and its stable public API (`build_concierge_*` / `handle_concierge_tool(action,
  project_root, …)`) live in the SDK package (`src/startd8/concierge/`). The thin `@mcp.tool()`
  registration — Pydantic input model, annotations, async handler delegating to the SDK — is
  added to the existing FastMCP server in the **`mcp/startd8-mcp-builder/`** subproject
  (`startd8_mcp.py`), beside the 17 `startd8_*` tools already there. Both packages live in the
  startd8-sdk repo (the subproject has its own `pyproject`/CI but is **not** a separate git repo).
  The wrapper imports the SDK as a library and declares the minimum SDK version exposing the API,
  and MUST stay thin (no business logic) so the CLI (FR-C13) and the MCP tool render from the one
  SDK code path. **Registration target (resolved):** add the `@mcp.tool()` to the root monolith
  **`startd8_mcp.py`** — it is the documented "Primary Server," the module all 14 test files
  import, the CLAUDE.md launch target (`python3 startd8_mcp.py`), and the public entrypoint the
  `startd8_mcp_server/` package itself defers to "for backward compatibility." Caveat for the
  implementer: the 20 existing tools are **duplicated** in `startd8_mcp_server/server.py` (a
  parked monolith→package refactor with the identical tool surface); a tool added to the monolith
  must be mirrored there too, or the refactor's go-forward status confirmed first — pre-existing
  drift, flagged not inherited.

---

## 3. Non-Requirements

- **No orchestration.** Never runs the cascade, a pipeline pass, or a workflow. (That's
  `startd8_workflow`'s job; Concierge may *point at* it but not invoke it.)
- **No gate recording / approvals.** Never records attorney/architect/PO sign-off; gates stay
  with their owning role (FR-C2). No SLA/assignment/notification machinery (HITM §5 stands).
- **No real-content generation.** Bucket-4 content is the company's; the Concierge prepares
  buckets 1–2 inputs only.
- **No multi-project orchestration.** One consuming project per call. No fleet/portfolio view.
- **Not a replacement for the human+Claude Concierge.** v1 exposes the *mechanizable* subset of
  the observed activities; judgment-heavy assists (PRD→requirements translation) stay manual or
  become explicitly-LLM actions later.
- **Not a new MCP server.** Adds one `@mcp.tool()` to the existing FastMCP server
  (`mcp/startd8-mcp-builder/startd8_mcp.py`, tool #18); no new transport/server.

## 4. Open Questions

> OQ-1/2/4/5/6 resolved by the planning pass (§0). OQ-3/OQ-7 resolved by design decision
> 2026-06-11 (below). OQ-8 remains a small implementation-pass call.

- **OQ-3 — RESOLVED (2026-06-11): three sibling commands, `concierge` composes with `kit`.**
  `assist` / `kit` / `concierge` are three phases of one project lifecycle — **triage** /
  **deliver** / **onboard** — not competitors, and not one umbrella noun (that would force churn
  on shipped `assist` and conflate the phases). Each is its own `typer.Typer` app. Where they
  touch: `concierge assess` and `kit` both report readiness, at different grains (project-inputs
  vs role-kit completeness) — so `assess` **calls** `kit` for the kit-completeness line rather
  than reimplementing it (FR-C10). Since `kit` is deferred, that is a forward-compatible seam,
  not a v1 dependency. Folding `kit` *into* `concierge` is rejected (a category error — `kit` is
  delivery-time and role-scoped; `concierge` is onboarding). `concierge` reuses `assist`'s
  conventions (idempotent, exit-0-always, `--no-emit`/`--no-write`) but stays a separate command.
- **OQ-7 — RESOLVED (2026-06-11): MCP is read/preview-only in v1; the CLI is the only writer.**
  See FR-C3. `apply:true` is a safety control, not authorization; making MCP non-writing removes
  the trust boundary for v1 entirely (the human-run CLI writes at its own privilege). A
  server-side allowlist + path-confinement is the design *if/when* MCP writes are added — at
  which point that increment warrants the CRP security lens. Not v1.
- **OQ-8 — `survey` PII detection depth (F-2).** Open (small). How far does the
  personal/PII-material flag go — filename/extension heuristics only, or content sniffing?
  Content sniffing in a read action has its own privacy implications. Lean: path/extension
  heuristics + a conservative "review these" list, **never reading flagged file contents**.

---

*v0.2 — Post-planning self-reflective update. 6 of 13 requirements corrected (FR-C1 reframed to
FastMCP registration, FR-C7 gained a packaging prerequisite, FR-C8 deferred, FR-C12 retargeted),
1 added (FR-C14 cross-package split), 1 action merged (`validate`→`assess`), 5 open questions
resolved. The one expensive error caught: the MCP surface is a separate FastMCP subproject with
discrete tools, not the gateway bridge the draft was built on.*

*v0.3 — OQ-3 and OQ-7 resolved as design decisions (not unknowns), so CRP is not warranted yet:
MCP is read/preview-only in v1 (CLI is the sole writer — removes the write trust boundary), and
`concierge` ships as a sibling of `assist`/`kit`, composing with `kit`. Next move is a thin spike
of the read-only core (`survey`+`assess`) — which, being read-only, needs neither OQ-7 nor the
template-packaging prerequisite — on branch `feat/concierge-mcp`. CRP is reserved for the
write-action increment, where the security lens earns its keep.*

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
