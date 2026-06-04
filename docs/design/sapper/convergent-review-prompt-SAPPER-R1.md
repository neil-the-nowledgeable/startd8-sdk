# Convergent Review Prompt

**Generated:** 2026-06-04 19:03:57 UTC
**Mode:** Single-Document (Requirements)

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
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/nemawashi/NEMAWASHI_PREEXECUTION_VALIDATION_REQUIREMENTS.md` | 369 lines · 4342 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/nemawashi/.crp-focus.md` | 39 lines · 403 words |

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

### Mode: Single-Document Review (Requirements)

You have been given a **requirements document**. Produce **suggestions only** (no self-triage, no merged appendix output).

Focus your review on:
- **Unambiguity** — Could an implementer or QA misinterpret the text?
- **Completeness** — Acceptance criteria, boundaries, error cases, out-of-scope statements?
- **Consistency** — Contradictions between sections?
- **Testability** — Objective verification per requirement?
- **Traceability** — Links to design tasks, interfaces, or risks where expected?

Use **F-prefix** suggestion IDs in the form **R{n}-F{k}** (n = your round, computed from Appendix C; e.g. for round 2: R2-F1, R2-F2).


### Configuration (for structuring your suggestions)

| Parameter | Value |
|-----------|-------|
| Max suggestions (soft cap) | 10 |
| Review areas to consider | Architecture, Interfaces, Data, Risks, Validation, Ops, Security |

### Sponsor / author — review focus (from --focus-file)

Prioritize the following when scoring severity and ordering work. Do not treat this file as normative over the requirements or plan; use it to **weight** attention.

# Where this review needs input most

**Do NOT re-litigate feasibility or locked scope.** Both mechanism routes are already empirically
spike-validated against the real RUN-028 fixture — the existence/typecheck bore (§0.6) and the
declaration-surface conformance route (§0.7). Scope is locked by decision: near-side role only (FDE is a
*query interface*, NR-1), advisory-first v1 (FR-NEM-8), deterministic skeleton "pilot bore" as the lead
mechanism (FR-NEM-4). Suggestions that propose blocking-by-default, building the FDE agent now, or doubting
that the skeleton-compile works will be rejected as out-of-scope — spend budget elsewhere.

Concentrate the review on the **design unknowns the spikes could not resolve**:

1. **Friction-report schema (FR-NEM-1/2/3).** Is the `Assumption` → `AssumptionVerdict {VALIDATED/REFUTED/
   UNRESOLVED}` → `FrictionFinding` model complete and unambiguous? Stress the **avoidable-cost ranking**
   (`repair < integration < boot < cross-feature-cascade`): how is the cost stage assigned per finding, is the
   ordering stable/defensible, and what happens on ties or unknown stage? Is `UNRESOLVED` distinguishable in the
   schema from "validator not run / degraded"? What is the artifact contract for `nemawashi-friction-report.json`
   (schema versioning, consumer stability)?

2. **FDE escalation/query contract (FR-NEM-7).** `answer(question) → {VALIDATED | REFUTED | OMIT}` — is this
   contract specified enough to build the *consumer* against? What is the question/evidence payload shape? How
   are timeouts, OMIT, and human-in-the-loop latency handled when the near-side gate is otherwise synchronous and
   $0? Is there a risk the FDE path silently becomes the dumping ground for everything hard (all `UNRESOLVED`)?

3. **Overlay ops/security (FR-NEM-4).** The bore **copies the real project into a throwaway dir and runs a
   toolchain (mypy/compileall) over it.** Surface the risks: copy cost/size on large repos, secrets/.env in the
   copy, running a subprocess over project code, temp-dir cleanup/leakage, concurrent runs colliding, symlink
   escape, and the `STARTD8_PY_TYPECHECK` + `--ignore-missing-imports` + file-scoping config interactions
   (OQ-7). Is "throwaway copy" even the right isolation primitive vs. an overlay/MYPYPATH approach?

4. **Advisory→gating graduation (FR-NEM-8).** The hard-block path is "specified but gated off" behind an env
   flag. Is the *precision bar* for flipping it defined and measurable? What evidence/metrics gate the
   graduation, and how is a false-positive `REFUTED` prevented from blocking a valid run once gating is on?

5. **Host-stage integration (FR-NEM-9).** Hosting on `domain-preflight` and loading the upstream EMIT
   `ForwardManifest` + `skeleton_sources`: is the coupling sound? What if EMIT artifacts are absent/stale, or the
   skeletons lack the declaration-surface fidelity (decorators) FR-NEM-10 depends on (OQ-8)? Checkpoint/EventBus
   failure modes?

Anchor every suggestion to a specific FR/NR/OQ id. Prefer fewer, sharper, testable suggestions over breadth.

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

## Document Under Review: Requirements

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/nemawashi/NEMAWASHI_PREEXECUTION_VALIDATION_REQUIREMENTS.md`  ·  **Size:** 369 lines · 4342 words

```markdown
# Nemawashi — Pre-Execution Plan Validation (Tunnel-Alignment Survey) — Requirements

**Version:** 0.4 (Post-spike×2 — both mechanism routes validated at plan time, coverage model sharpened)
**Date:** 2026-06-04
**Status:** Draft — no production code yet. v0.1 (pre-planning) corrected against the actual `domain-preflight`,
`preflight_rules`, `python_toolchain`, `forward_manifest`, `project_knowledge`, and `element_fillability`
code (**7 corrections**, §0); then the **two mechanism routes were run as feasibility spikes against the real
RUN-028 fixture** — the existence bore (FR-NEM-4, §0.6) and the conformance/convention route (`repair/convention.py`
at plan time, §0.7). Both work; together they corrected the coverage model to a **declaration-surface vs.
body-internal** axis. Mechanism feasibility is now evidence-backed end-to-end.

**Role name (proposed, not decided):** *Nemawashi* (根回し — "going around the roots": validating a decision
with everyone who holds ground truth *before* the formal commit, so execution is friction-free). The near-side
tunnel-survey crew. Pairs with the **Forward Deployed Engineer (FDE)** — the far-side / project-side ground-truth
crew (defined here as a *query interface*, built thin/later — see §3 NR-1).

**Locked scope decisions (this doc):**
1. **Near-side role only.** The FDE is a defined collaborating *query interface* (FR-NEM-7), not built here.
2. **Advisory-first** (FR-NEM-8). v1 emits a ranked friction report + escalations and **never blocks**;
   the graduation path to a Hayai hard-block on `REFUTED`-high is specified but gated off.
3. **Deterministic skeleton-compile "pilot bore" is the lead mechanism** (FR-NEM-4). LLM/FDE only for
   assumptions code cannot answer.

**Serves:** `docs/design-princples/HAYAI_DESIGN_PRINCIPLE.md` (don't defer enforcement — pull it to the
earliest stage: the pseudo-code/decomposition layer, before any body is generated).

**Aligns with / depends on:**
- `../repair-pipeline/CONVENTION_AWARE_REPAIR_REQUIREMENTS.md` (FR-CAR-0 Python convention authority; FR-CAR-5
  micro-prime injection) and `../micro-prime/MICRO_PRIME_FIDELITY_REQUIREMENTS.md` (FR-MPF-1). Nemawashi is the
  **pre-execution sibling** of those *post-generation* levers, and consumes the same authority when it lands.

**Motivating evidence:** `strtd8/docs/P2_RUN_028_POSTMORTEM.md` and the convention-repair doc's RUN-032
baseline — micro-prime emitted Flask-not-FastAPI / `session.query` / `app.models`-not-`app.tables`, and **one
un-prevented micro-prime file cascaded to a boot failure that zeroed three features sharing `app/jobs.py`**.
Every one of those was a *false assumption about the other side of the tunnel*, already latent in the plan,
discovered only at integration/boot time. Nemawashi is the gate that interrogates those assumptions at
**document cost, not refactoring cost.**

---

## 0. Planning Insights (Self-Reflective Update: v0.1 → v0.2)

> The planning pass (codebase exploration of the reuse targets) tested v0.1's assumptions against the actual
> pre-generation machinery. It revealed **7 corrections**.

| v0.1 Assumption | Planning Discovery | Impact |
|---|---|---|
| The pilot bore "compiles the skeleton" via `python_toolchain` directly. | `run_project_check()` (`validators/python_toolchain.py:152`) operates over a **project *directory*** (compileall → mypy → pytest), not an in-memory stub. Its power to catch *cross-module* misalignment (the actual tunnel test) comes from **mypy**, which is **off by default** (`STARTD8_PY_TYPECHECK`, line 284) and may be **absent**. `compileall` alone only verifies the stub's own syntax — it cannot detect that a stub calls a function the real codebase doesn't expose. | **FR-NEM-4 reshaped:** the bore must (a) *materialize* signature/import/type-stub skeletons into a **throwaway overlay of the real project** and run `run_project_check(run_pytest=False)`, and (b) adopt the module's **loud-degradation** contract — mypy-absent ⇒ reduced fidelity (syntax+import only), **never a silent `VALIDATED`**. mypy availability becomes a stated soft-dependency + open question (OQ-2). |
| The empty `startd8.preflight_rules` seam hosts the gate and emits the friction report. | The rule system is **per-(file, domain)**: `PreflightRule.evaluate(ctx)` → `RuleContribution{checks, constraints, validators, validator_fns}` (`preflight_rules/_base.py`), aggregated per file by `evaluate_all`. `RuleContribution` carries **enrichment** (prompt constraints + post-gen validator specs), *not* a ranked cross-task finding with severity / who-validates / resolution. | **FR-NEM-6 narrowed + FR-NEM-1/2/3 are new:** reuse the seam for **per-element deterministic checks**, but the **unified whole-decomposition gate**, the `VALIDATED/REFUTED/UNRESOLVED` trichotomy, cost-ranking, and FDE routing are **new orchestration + new models** layered on top, not rules alone. |
| `ProjectKnowledge` can answer the Python framework/ORM/module-source assumptions (it's the FDE's brain). | The producer reads **`.ts/.tsx/.js` + `schema.prisma` + `@/` aliases — TS/Prisma-ONLY** and encodes **no framework/ORM idiom** (per the convention-repair doc's own §0). For a Python target it yields little today. Its **`omissions` list is first-class**, though. | **FR-NEM-7 reframed:** the FDE is a *capability contract* `answer → {VALIDATED \| REFUTED \| OMIT}`; for Python, the backing authority is currently thin, so many assumptions correctly land **`UNRESOLVED`** (escalated) rather than `VALIDATED`. Early value concentrates in the **deterministic pilot bore + cross-contract consistency**; FDE escalation is the explicit "we don't know yet" channel. Aligns Nemawashi with the in-flight FR-CAR-0 / FR-MPF-1 authority work. |
| `VALIDATED/REFUTED/UNRESOLVED` maps onto the existing `CheckStatus`. | `CheckStatus` is `pass/warn/fail/skip` (`domain_preflight_models.py:36`) — there is **no `UNRESOLVED` equivalent** (an assumption needing a *ruling*). | **FR-NEM-2 is a new trichotomy.** `UNRESOLVED` is the load-bearing novel state — the escalation surface that *pairs with the FDE*. `REFUTED`≈cited contradiction; `VALIDATED`≈evidence-backed; `UNRESOLVED`≈question routed out-of-band. |
| Forward Manifest already cross-checks contracts before generation. | Contracts are **injected** pre-gen (as `[BINDING]` constraints) but **validation runs post-gen only** (`validate_forward_manifest`); there is **no cross-contract or contract-vs-codebase consistency check at plan time**. | **FR-NEM-5 is new:** a plan-time deterministic validator over `InterfaceContract`s — contradictory contracts for one id, and contracts that conflict with an existing codebase symbol — distinct from the post-gen validator, reusing the same data model. |
| Nemawashi is a new standalone workflow. | `domain-preflight` (`workflows/builtin/domain_preflight_workflow.py`, 825 LOC) is **already** the deterministic, zero-LLM pre-gen stage (`load→scan→classify→check→enrich`) with `PreflightState` checkpointing, `EventBus` `QUALITY_GATE_RESULT` emission, and a `TaskEnrichment` output. | **FR-NEM-9 reuses it as host:** Nemawashi is a **new phase** consuming the same seed + `AvailableDeps` + manifest, reusing checkpoint/EventBus/loud-degradation conventions — not a parallel pipeline. |
| `element_fillability` is unrelated. | `is_fillable_spec` / `is_empty_fillable_spec` (`element_fillability.py`) is **already a pre-gen "is this buildable" predicate** (catches `class value-model {}`-style non-implementable types). | **FR-NEM-6 composes it:** a non-fillable empty type is a `REFUTED` "this element cannot be built" finding — reuse, don't duplicate. |

**Resolved open questions** (from v0.1):
- **OQ-A (host) → reuse `domain-preflight` as a new phase** (FR-NEM-9). Not a standalone pipeline.
- **OQ-B (verdict model) → new trichotomy** `VALIDATED/REFUTED/UNRESOLVED` (FR-NEM-2); does not fit `CheckStatus`.
- **OQ-C (FDE backing) → ProjectKnowledge + human escalation, with OMIT⇒UNRESOLVED** (FR-NEM-7); thin for Python today, by design.
- **OQ-D (cross-contract) → new plan-time validator** (FR-NEM-5); post-gen `validate_forward_manifest` is the wrong stage.

Remaining open questions are carried to §4.

---

## 0.6 Spike: FR-NEM-4 feasibility (v0.2 → v0.3)

> Before committing to a plan, the lead mechanism was run for real: the RUN-028 `app/jobs.py` (surviving as
> `strtd8/app/jobs.py.backup`) was reduced to a **skeleton** (imports + signatures, bodies → `...`), overlaid
> onto the real `strtd8` `app/` package (ground truth: `tables.py`, `models.py`), and checked with the actual
> toolchain (`mypy`, the engine inside `python_toolchain.run_project_check`). Spike tree: `/tmp/nemawashi_spike`.

**Result: FR-NEM-4 is feasible and precise on its true axis — but that axis is *existence*, not *convention*.**

| Assumption in the RUN-028 skeleton | Ground truth | Bore verdict | Correct? |
|---|---|---|---|
| `from app.tables import Match` | `Match` **not defined** in schema | `REFUTED` — `Module "app.tables" has no attribute "Match" [attr-defined]` | ✅ true positive |
| `from app.tables import JobDescription` | **exists** (`tables.py:665`) | silent (`VALIDATED`) | ✅ true negative |
| `from app.models import JobDescriptionSchema` | **exists** (`models.py:193`) | silent (`VALIDATED`) | ✅ true negative |
| `from app.models import JobDescription` (wrong module-source) | name is in `tables`, not `models` | `REFUTED` — *"has no attribute 'JobDescription'; maybe 'JobDescriptionSchema'?"* | ✅ true positive (+ suggested the fix) |
| `from flask import Blueprint` (wrong framework) | Flask is a real, importable package | **silent — MISSED** | ❌ blind spot |
| `from sqlalchemy.orm import Session` (wrong ORM idiom) | `sqlalchemy.orm.Session` is real | **silent — MISSED** | ❌ blind spot |

**Three corrections this forces into the requirements:**

1. **The coverage axis is existence vs. conformance, NOT import-line vs. body (corrects the v0.2 §0 prediction).**
   The bore deterministically catches references to things that **don't exist** in ground truth (invented entity
   `Match`; a name imported from the wrong-but-real module when that module lacks the name). It is **structurally
   blind to "exists but is the wrong choice"** — `flask`/`sqlalchemy.orm` are real, so the typechecker has no
   opinion. → **FR-NEM-1 routing reframed** (existence → bore; conformance → authority/FDE), **FR-NEM-4 scope
   narrowed**, **FR-NEM-10 reinforced** (convention is the authority's job, not the bore's — the bore is the
   existence backstop, FR-CAR is the conformance lever).
2. **Diagnostics MUST be scoped to the skeleton-under-test file(s).** With `sqlmodel` absent, mypy emitted **15
   false `table=True` errors in the ground-truth `tables.py`** — noise from a *ground-truth* module, not the
   skeleton. Filtering diagnostics to those whose path is a skeleton file made the signal exact (one diagnostic).
   `run_project_check` collects *all* diagnostics, so **FR-NEM-4 must add file-scoping** (and OQ-7 covers whether
   to instead require the project venv so framework stubs resolve).
3. **The bore's precision depends on ground-truth modules being parseable, not the framework being installed.**
   `mypy` resolved `app.tables` attribute membership correctly **even with `sqlmodel` uninstalled** (class names
   exist at module scope regardless of base-class resolution). So the existence check is cheap and venv-light;
   only conformance/type-accuracy would need the real deps. This *strengthens* the $0-LLM, low-setup thesis.

**Net:** the lead mechanism works and earns its place — it caught the genuine RUN-028 domain miss (`Match`) at
skeleton stage with no false positives — but v0.2 over-claimed its reach. Convention misalignment
(Flask/SQLAlchemy) is **out of scope for the bore by construction** and belongs to FR-NEM-7 (FDE) / the FR-CAR
authority. Carried as OQ-7.

---

## 0.7 Spike 2: conformance route at plan time (v0.3 → v0.4)

> Spike 1 made the conformance route *load-bearing* (the bore is blind to wrong-but-valid imports). Spike 2 tests
> whether the **already-landed** FR-CAR convention detector (`repair/convention.py` `detect_conventions` /
> `PythonConventionAuthority`, from `24893fcc`) can run at **plan time** over a skeleton and cover that blind
> spot. Same RUN-028 fixture; ran the real detector on (A) the full pre-repair file and (B) its body-stripped
> skeleton.

**Result: the route IS plan-time-capable — `detect_conventions(code: str, …)` takes raw source — and on the
skeleton it caught the *headline* RUN-028 failures: `from flask import` (framework) and `from app.models import
JobDescription` (module_source). But it caught only what lives on the *declaration surface*; the body-internal
idioms vanished with the bodies.**

| RUN-028 violation | kind | lives in | full file (A) | skeleton (B) |
|---|---|---|:---:|:---:|
| `from flask import Blueprint` | framework | import | ✅ | **✅ caught** |
| `from app.models import JobDescription` | module_source | import | ✅ | **✅ caught** |
| `@app.route(...)` | framework | decorator | ✅ | ⚠️ only if skeleton keeps decorators |
| `session.query(...).get(...)` / `.query(...)` | orm_idiom | body call | ✅ | ❌ gone (no body) |
| `render_template(...)` | template_idiom | body call | ✅ | ❌ gone (no body) |
| `from sqlalchemy.orm import Session` | — | import | ❌ | ❌ no rule exists for it |

**This sharpens the coverage model into a 2×2** (superseding v0.3's single existence-vs-conformance axis):

|  | **Existence** (symbol absent from ground truth) | **Conformance** (symbol valid but wrong choice) |
|---|---|---|
| **Declaration surface** (import / signature / decorator) — *in the skeleton* | bore / typecheck (FR-NEM-4) — e.g. invented `Match` | convention authority (FR-NEM-10) — e.g. `flask`, `app.models`-source |
| **Body-internal** (call / statement) — *not in the skeleton* | — | **out of scope → post-gen FR-CAR** — e.g. `session.query`, `render_template` |

**Nemawashi owns the whole declaration-surface column** — *both* existence and conformance — at plan time, $0
LLM. **Body-internal idioms are out of scope by construction** (no bodies to read) and remain FR-CAR's post-gen
job. The two are **complementary, not redundant**: together they cover the full RUN-028 class; neither alone does.

**Two actionable findings:**
1. **Authority gap (concrete, cheap):** `_IDIOM_RULES` has **no import-level rule for `from sqlalchemy.orm import
   Session`** — SQLAlchemy is caught only via the `.query(` *body* call. A skeleton that imports SQLAlchemy
   before bodies exist slips through. **Adding a declaration-surface SQLAlchemy import rule** completes
   conformance coverage for the RUN-028 class at plan time → OQ-6 (now a plan task, not just a question).
2. **Skeleton fidelity = coverage:** whether `@app.route` is caught depends on the manifest-rendered skeleton
   **retaining decorators**. FR-NEM-4 must specify that skeletons preserve the full declaration surface (imports
   + signature + **decorators**) — that surface *is* Nemawashi's detection field → OQ-8.

**Net:** the load-bearing dependency is real and works; OQ-6 resolves to "yes — reuse `detect_conventions` at
plan time, plus one new import rule." Both empirical hinges are retired — mechanism feasibility (existence *and*
conformance routes) is evidence-backed. **CRP is now the right next step.**

---

## 1. Problem Statement

The SDK's quality machinery is **bimodal**: rich *design-time capture* (forward contracts injected into prompts)
and rich *post-generation* enforcement (forward-manifest validation, semantic checks, convention-aware repair,
disk-quality scoring, post-mortem/Kaizen). The **earliest gate — interrogating the plan itself before any body
is generated — is thin**: `domain-preflight` checks domain/deps/environment readiness, and `element_fillability`
checks buildability, but nothing reconciles the plan's **assumptions about the existing codebase** against
ground truth. So a plan that assumes Flask (codebase is FastAPI), `app.models` (it's `app.tables`),
`session.query` (it's SQLModel `session.exec`), or a writable field the domain forbids, is generated, integrated,
and **discovered wrong at boot/integration time** — the most expensive, most avoidable failure class.

The tunnel analogy: two crews bore toward each other. The **plan/design crew** holds the `ForwardManifest` /
`ForwardElementSpec` / skeletons ("here's what I intend to build"); the **implementation-reality crew** holds
the real conventions, interfaces, domain rules, runtime ("here's the ground I'm boring into"). When their
assumptions about each other are wrong, the crews miss at the middle — that miss *is* the implementation-time bug.
Nemawashi runs the **alignment survey** at the pseudo-code stage so the miss is caught at document cost.

| Component | Current State | Gap |
|---|---|---|
| Pre-gen environment readiness | `domain-preflight` (deps, domain, env checks) | Doesn't reconcile **plan assumptions vs codebase ground truth** |
| Buildability predicate | `element_fillability.is_fillable_spec` | Single-element only; no whole-plan friction report |
| Forward contracts | Injected pre-gen; validated **post-gen** | **No plan-time** cross-contract / contract-vs-codebase consistency |
| Skeleton emission | Skeletons emitted before generation (`forward_manifest`) | **Never compiled/typechecked** against the real codebase |
| Ground-truth authority | `ProjectKnowledge` (TS/Prisma) + omissions list | No **queryable FDE role**; Python framework/ORM idiom not encoded |
| Convention enforcement | Post-gen (FR-CAR-*) detect+escalate+repair | **No pre-gen** plan-level convention catch (and micro-prime bypasses injection — RUN-028) |

---

## 2. Requirements

### Model (foundational)

- **FR-NEM-1 — Assumption extraction.** Define an `Assumption`: a claim the plan makes about "the other side of
  the tunnel," extracted deterministically from the decomposition artifacts (`ForwardManifest`,
  `InterfaceContract`, `ForwardElementSpec`, emitted skeletons). Each carries: `id`, `kind` ∈
  {`interface_signature`, `import_availability`, `module_source`, `framework_idiom`, `orm_idiom`,
  `field_authority`, `domain_rule`, `identity_collision`, `decomposition_integrity`, `reachability`}, the claim
  text, a ref to the source artifact, and a `validator_class` ∈ {`deterministic`, `pilot_bore`, `fde_query`}.
  **Routing is by the existence/conformance axis the spike established (§0.6):** *existence* assumptions
  (`import_availability`, `interface_signature`, `field_authority`, `identity_collision`,
  `decomposition_integrity`, and the existence half of `module_source` — a name absent from its named module) →
  `pilot_bore`/`deterministic`; *conformance* assumptions (`framework_idiom`, `orm_idiom`, and the residual of
  `module_source` where the name exists in **both** the named and the correct module) → `fde_query` (the bore is
  structurally blind to these — the referenced symbol exists, it is merely the wrong choice).
- **FR-NEM-2 — Verdict trichotomy.** `AssumptionVerdict` ∈ {`VALIDATED`, `REFUTED`, `UNRESOLVED`} (a **new**
  model — `CheckStatus` has no `UNRESOLVED`). `VALIDATED` cites the confirming ground-truth; `REFUTED` cites the
  contradiction (`expected` vs `found`); `UNRESOLVED` carries the question + *why code cannot answer it* and is
  the routing payload to the FDE (FR-NEM-7). No assumption is silently dropped.
- **FR-NEM-3 — FrictionFinding ranked by avoidable cost.** Each non-`VALIDATED` assumption → a `FrictionFinding`
  with `severity` and an **avoidable-cost** estimate = the downstream stage at which it would *otherwise* surface
  (`repair` < `integration` < `boot` < `cross-feature-cascade`, seeded from the RUN-028/032 cascade evidence).
  The report is ranked by avoidable cost **descending** — surfacing the costliest, most avoidable misses first
  (the stated objective).

### Mechanism

- **FR-NEM-4 — Deterministic skeleton "pilot bore" (lead mechanism, $0-LLM).** **Reuse the skeletons
  plan-ingestion EMIT already renders** (`plan_ingestion_emitter.py` `_run_mottainai_pre_assembly` →
  `DeterministicFileAssembler.render_specs(forward_manifest)` → `skeleton_sources`); the bore does **not**
  re-render them. Overlay those signature+import+type-stub skeletons (no bodies) into a **throwaway copy of the
  real project**, then run `python_toolchain.run_project_check(run_pytest=False)`. Map `mypy`/`compileall`
  diagnostics → `REFUTED` findings **on the existence axis only** (spike-validated, §0.6): a stub that references
  a symbol the real codebase **does not define** fails the typecheck (`attr-defined`/`name-defined`) — the
  cheapest possible alignment test. **Scope diagnostics to the skeleton-under-test file(s)** (`PyDiagnostic.file`
  ∈ skeletons) — the spike showed a ground-truth module with absent framework stubs emits false positives that
  would otherwise pollute the report; file-scoping made the signal exact. **Out of scope by construction:**
  conformance errors (a *valid* import that is the wrong framework/ORM — `flask`, `sqlalchemy.orm`) typecheck
  clean and route to `fde_query` (FR-NEM-1), not the bore. **Loud degradation (load-bearing):** when `mypy` is
  unavailable, the bore runs at syntax+import-resolution fidelity only and the report **states the reduced
  fidelity** — an unverifiable assumption is `UNRESOLVED`, never a silent `VALIDATED`. Mirrors `python_toolchain`'s
  `checked/unavailable` contract. (Spike confirmed existence checks resolve correctly even with the framework
  uninstalled — venv-light; OQ-7 covers when full deps are warranted.)
- **FR-NEM-5 — Plan-time cross-contract / contract-vs-codebase consistency.** A new deterministic validator over
  the `ForwardManifest`'s `InterfaceContract`s: detect (a) **contradictory contracts** — two contracts
  prescribing incompatible signatures/schemas for the same `contract_id`; and (b) **contract-vs-codebase
  conflicts** — a prescribed `function_name`/`class_name`/`import_path` that collides with or contradicts an
  existing definition. Reuses `InterfaceContract`; distinct from post-gen `validate_forward_manifest`.
- **FR-NEM-6 — Deterministic per-element checks via the `preflight_rules` seam.** Register Nemawashi rules on the
  **empty `startd8.preflight_rules` entry point**, *composing* existing predicates: `element_fillability`
  (non-buildable empty type ⇒ `REFUTED` `decomposition_integrity`), **identity/reserved-name collision** (the
  `metadata`-class crash ⇒ `REFUTED` `identity_collision`), and import availability against `AvailableDeps`
  (⇒ `REFUTED` `import_availability`). Per-element findings feed the FR-NEM-3 report.
- **FR-NEM-7 — FDE query interface (defined, not built — NR-1).** Define the FDE as a capability contract:
  `answer(question) → {VALIDATED(evidence) | REFUTED(evidence) | OMIT}`. v1 backs it with `ProjectKnowledge`
  (including its first-class `omissions` list) + a human-escalation channel; `OMIT`/omission ⇒ `UNRESOLVED`.
  Assumptions that are neither deterministically checkable nor pilot-borable (framework/orm idiom on Python,
  domain rules like "AI never writes `Metric.value`") route here. The near-side role only **consumes** this
  contract.

### Enforcement & integration

- **FR-NEM-8 — Advisory-first posture.** v1 emits a ranked friction report artifact
  (`nemawashi-friction-report.json` + `.md`) and `EventBus` event; it **never blocks generation**. The
  graduation path — hard-block on `REFUTED`-high-severity (full Hayai) — is **specified but gated off** behind an
  env flag (mirroring `STARTD8_CONVENTION_GATING`), to be flipped once precision is proven (same trust-earning
  path as the Semantic Compliance Reviewer v1).
- **FR-NEM-9 — Hosted on the `domain-preflight` stage.** Runs after `classify`/`check`, before generation;
  consumes the same seed + `AvailableDeps` (from preflight) **plus the `ForwardManifest` + `skeleton_sources`
  already produced upstream by plan-ingestion EMIT** — both inputs are available at this stage (OQ-4 resolved),
  so no new pipeline position is required; domain-preflight is extended to load the upstream EMIT artifacts.
  Reuses `PreflightState` checkpointing, `EventBus` emission, and the loud-degradation convention. The deterministic half (FR-NEM-4/5/6) is **zero-LLM**; LLM
  enters only inside the FR-NEM-7 FDE-query path.
- **FR-NEM-10 — Declaration-surface conformance via the FR-CAR authority (spike-validated, §0.7).** Run
  `repair/convention.py` `detect_conventions(skeleton_code, build_python_convention_authority())` over each
  skeleton at plan time. The spike confirmed this catches the **declaration-surface** conformance violations —
  `from flask import` (framework) and `from app.models import <Table>` (module_source), i.e. the *headline*
  RUN-028 failures — as deterministic `REFUTED` findings, $0 LLM. Findings already carry the shared
  `convention_kind`/`expected` vocabulary, so they compose with post-gen FR-CAR. **Scope boundary (load-bearing,
  not a hedge):** body-internal idioms (`session.query`, `render_template`) are absent from a skeleton and remain
  FR-CAR's *post-gen* job — Nemawashi and FR-CAR are complementary halves of one convention story (the 2×2 in
  §0.7), not competitors. **Extend the authority:** add a declaration-surface `from sqlalchemy.orm import …` rule
  to `_IDIOM_RULES` (OQ-6) so SQLAlchemy is caught at plan time, not only via its `.query(` body call.
- **FR-NEM-11 — RUN-028 structural safety net (the *why* this matters).** Because Nemawashi validates the
  **plan**, FR-NEM-4/10 catch declaration-surface violations destined for the **micro-prime tier regardless of
  whether adherence injection reached that tier's prompt** — closing the bypass the convention-repair doc
  documents (micro-prime has zero `project_knowledge` refs). The advisory report is the backstop the injection
  path structurally cannot be.

---

## 3. Non-Requirements

- **NR-1 — Does NOT build the FDE agent.** Interface/contract only (FR-NEM-7). The project-side ground-truth
  agent is a separate, later effort.
- **NR-2 — Does NOT block generation in v1.** Advisory only (FR-NEM-8). The block path is specified-but-gated.
- **NR-3 — Does NOT generate bodies or call the LLM for the deterministic half.** Not a generation step; the
  pilot bore emits *stubs*, not implementations.
- **NR-4 — Does NOT replace post-generation validation.** `forward_manifest_validator`, semantic checks, and
  convention-aware repair remain; Nemawashi is the *earliest* gate, not the only one.
- **NR-5 — Does NOT build the Python convention authority.** Depends on / aligns with FR-CAR-0 / FR-MPF-1. Where
  no authority exists yet, framework/orm-idiom assumptions route to `UNRESOLVED` (escalate, don't invent a verdict).
- **NR-6 — Not Service-Assistant work.** SA is *post-run* triage of completed runs; Nemawashi is *pre-run* plan
  validation. Distinct lifecycle position — which is exactly why it warrants a separate role.
- **NR-7 — v1 is Python-first.** The pilot bore rides `python_toolchain`. Polyglot bores (Go/Java/C#/Node
  toolchains) are deferred; for non-Python targets v1 runs FR-NEM-5/6 only and labels the bore `unavailable`.

---

## 4. Open Questions (remaining after the planning pass)

- **OQ-1 — Skeleton overlay strategy.** Full throwaway project copy vs. in-place temp-file overlay vs. mypy
  against a synthetic stub package. Correctness/cost tradeoff. *Lean:* temp overlay dir; measure on the RUN-028
  `jobs.py` fixture.
- **OQ-2 — mypy-absent fidelity floor.** Is `compileall` + import-resolution alone worth running, or should the
  bore mark itself `unavailable` and route everything to `UNRESOLVED`? *Lean:* run it, label reduced fidelity
  (some import/syntax misalignment is still caught cheaply).
- **OQ-3 — Avoidable-cost calibration.** Static heuristic (`kind → stage`) vs. learned from Kaizen history.
  *Lean:* static seed table from the RUN-028/032 cascade, refined via Kaizen feedback later.
- **OQ-4 — Input availability / sequencing → RESOLVED.** Planning-pass code check found the `ForwardManifest`
  **and rendered skeletons are produced *upstream* during plan-ingestion EMIT** (`plan_ingestion_emitter.py`
  `_extract_forward_manifest` + `_run_mottainai_pre_assembly` → `skeleton_sources`), which runs **before**
  `domain-preflight` (`scripts/run_artisan_workflow.py:858`). Both inputs (seed/deps *and* manifest/skeletons)
  are therefore available at the host stage — **FR-NEM-9 holds**: extend `domain-preflight` to load the EMIT
  artifacts; no new pipeline slot needed. Bonus: FR-NEM-4 reuses EMIT's skeletons rather than re-rendering.
- **OQ-5 — FDE escalation mechanics for v1.** Synchronous human prompt vs. async escalation artifact resolved
  out-of-band. *Lean:* async artifact + `EventBus`, consistent with advisory-first.
- **OQ-6 — Shared convention authority → RESOLVED + scoped to a plan task (§0.7).** Confirmed: Nemawashi reuses
  `repair/convention.py` `detect_conventions` at plan time over skeletons — it caught Flask + module_source on
  the RUN-028 skeleton. **Remaining work (now a plan task, not an open question):** add one declaration-surface
  `from sqlalchemy.orm import …` rule to `_IDIOM_RULES` so SQLAlchemy import is caught at plan time (today only
  its `.query(` body is). No architectural unknown remains here.
- **OQ-8 — Skeleton declaration-surface fidelity (from §0.7).** Nemawashi's entire detection field is the
  declaration surface the manifest-rendered skeleton emits. Confirm `DeterministicFileAssembler.render_specs`
  preserves **imports + signatures + decorators** (the `@app.route` catch depends on decorators surviving into
  the skeleton). If decorators are dropped, FR-NEM-10 loses decorator-level framework detection. *Lean:* require
  full declaration-surface fidelity in the skeleton contract; verify against `ForwardElementSpec.decorators`.
- **OQ-7 — Bore mypy config / deps (from the spike).** Two sub-decisions surfaced by §0.6: (a) **diagnostic
  scoping** — filter to skeleton-file diagnostics (chosen) vs. require the project venv so framework stubs resolve
  and the ground-truth-module noise disappears at the source; and (b) **`--ignore-missing-imports`** — keep it
  (existence checks against intra-project modules still fire; only genuinely-missing third-party is silenced) vs.
  provision deps for higher-fidelity type accuracy. *Lean:* scope-by-file + `--ignore-missing-imports` for the
  v1 existence bore (venv-light, $0); revisit deps only if FR-NEM-5 needs signature-level type matching.

---

*v0.4 — Post-spike×2. v0.2 corrected 7 assumptions against the code (>30% revision) + resolved OQ-4 sequencing;
v0.3 ran the **existence bore** for real (§0.6 — caught the `Match` domain miss, zero false positives); v0.4 ran
the **conformance route** for real (§0.7 — `detect_conventions` on the skeleton caught the headline Flask +
module_source failures). Together they corrected the coverage model from one axis to the **declaration-surface ×
existence/conformance 2×2**: Nemawashi owns the declaration-surface column at plan time / $0 LLM; body-internal
idioms stay with post-gen FR-CAR. Both empirical hinges retired — mechanism feasibility is evidence-backed
end-to-end. 11 FRs, 7 NRs, 6 OQs (OQ-4/6 resolved; OQ-6/8 now plan tasks). Pairs with a forthcoming
`NEMAWASHI_PREEXECUTION_VALIDATION_PLAN.md`. **Next: CRP review (Phase 5) — no feasibility unknowns remain;
remaining unknowns are design (report schema, FDE escalation contract, overlay ops/security), which is CRP's job.***

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
- [ ] Chat reply is a **short** (1–3 line) write-confirmation listing file paths and suggestion counts — **not** the suggestion content.

**Stop after persisting** — do not triage, do not emit merged documents in chat or in the files, do not modify existing prose, populated Appendix A/B, or prior rounds in Appendix C (the A/B/C scaffold is generator-created — do not add another).
