# Convergent Review Prompt

**Generated:** 2026-07-22 14:20:03 UTC
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
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-obs226/docs/design/observability-requirement-shaped/PLAN.md` | 91 lines · 891 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-obs226/docs/design/observability-requirement-shaped/REQUIREMENTS.md` | 187 lines · 2994 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/Users/neilyashinsky/Documents/dev/startd8-obs226/docs/design/observability-requirement-shaped/crp-focus-R1.md` | 22 lines · 353 words |

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

# CRP Focus — #226 de-overfit observability spec (Round 1)

## Least-reviewed target (concentrate here)
The **v0.4 generalization** content is brand-new and unreviewed:
- §0.3 (De-Overfit Generalization) + the overfit catalog table
- **FR-12** — contract-first SLI-kind determination (resolved SLI-kind set; convention fallback only for the request-serving family; non-request+undeclared ⇒ ∅ + coverage gap)
- **FR-13** — delete the unconditional RED synthesis in `_ensure_red_coverage`
- Generalized **FR-5** (signal_kind primary axis), **FR-6** (kind→profile table), **FR-7** (per-signal_kind thresholds), **FR-9** (∅-service coverage)
- **CR-3** — 7-kind enum + no-listen-port inference

## Settled — DO NOT relitigate
- (a) FR-1/2/3 are **cross-repo** (ContextCore/cap-dev-pipe own the manifest + onboarding-metadata schemas; the SDK is consume-only). Settled by exploration.
- (b) OQ-1..OQ-6 were resolved by the reflective loop (§0). Do not reopen.
- (c) Back-compat mechanism is fixed: byte-identical absent-input parity (**FR-11**) gated by a golden test (**FR-0**).
- (d) Seam is fixed: extend `MetricDescriptor._PROFILES`, not a parallel kind-dispatcher.

## High-value review axes (weight these)
1. **Parity soundness** — does FR-12's "resolved SLI-kind set, convention-fallback-only-for-request-serving-family" *provably* reproduce today's byte-identical output for an existing http_server service (same descriptor, same 3 SLOs, same panels)? Any path where the resolver yields a different set for a plain http service is a defect.
2. **FR-13 safety** — is deleting the unconditional RED synthesis safe for **every** existing http fixture, or does some current http output depend on the synthesis firing even when convention metrics are present? Name the failure mode if any.
3. **Enum completeness/orthogonality** — is `signal_kind` ∈ {availability, latency, throughput, queue_depth, retry_rate, freshness, run_success, saturation, lag, custom} complete and non-overlapping? (e.g. is `retry_rate` a special case of an error-budget on `run_success`? is `lag` vs `freshness` a real distinction?)
4. **Kind taxonomy gaps** — does the kind→profile table {http_server, grpc_server, async_worker, batch, cron, stream, ml_inference, unknown} leave a real gap? Specifically **hybrid services** that both serve HTTP *and* run background workers — which profile, and does one service need multiple SLI-kind sets?
5. **Non-blocking scoping** — are OQ-5 (pilot evidence absent → worker metric names/thresholds ungrounded) and OQ-7 (who authors signal_kind/target) correctly scoped as non-blocking, or does either actually gate the SDK-side seam?

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-obs226/docs/design/observability-requirement-shaped/PLAN.md`  ·  **Size:** 91 lines · 891 words

```markdown
# Implementation Plan — Requirement-Shaped, Service-Kind-Aware Observability (#226)

**Version:** 1.1 (matches REQUIREMENTS v0.4)
**Date:** 2026-07-22
**Companion:** `REQUIREMENTS.md`

> Seam decision: **invert the core triplet from "always RED, patch exceptions" to
> "derive per resolved SLI-kind set; RED is just the request-serving fallback."**
> Promote the existing contract-driven `_EXTENDED_PER_SERVICE_GENERATORS` gate
> (`artifact_generator.py:200/556`) to govern the triplet, and **delete** the
> unconditional synthesis in `_ensure_red_coverage`. Everything else is a table
> lookup (kind→profile, signal_kind→series, signal_kind→thresholds) — one general
> rule, not per-kind `if` branches. The single justified branch is the SLI-kind
> gate inside `_ensure_signal_coverage`.

---

## Phase 0 — Lock back-compat (SDK, DO FIRST) — FR-0, FR-11

- Add `tests/unit/observability/test_http_golden.py`: generate alert + SLO + dashboard_spec for one representative `http_server` service from a fixed onboarding-metadata + `.contextcore.yaml` fixture; assert full-YAML equality against a committed golden.
- This is the regression gate for every later phase. No generator code changes yet.

## Phase 1 — Cross-repo prerequisites (ContextCore / cap-dev-pipe) — CR-1, CR-2, CR-3

*Lands in the producer repo, not here. Sequenced first because §3 consumes it, but the SDK degrades gracefully (FR-11) so Phases 2–3 can proceed against fixtures before Phase 1 ships.*
- CR-1/CR-2: add `spec.requirements.functional[]` + `traceability[]` to the manifest schema; populate `traceability[]` by forwarding `ingestion-traceability.json` `requirement_mappings[]` (`plan_ingestion_workflow.py:2207`). Author `signal_kind`/`target` (see OQ-7).
- CR-3: add `instrumentation_hints[svc].kind` to the Stage-4 EXPORT producer.
- Deliverable back to SDK: updated sample fixtures (onboarding-metadata.json with `kind`; `.contextcore.yaml` with `functional[]`).

## Phase 2 — SDK consumption + determination — FR-4, FR-5, FR-6, FR-7, FR-12, FR-13

- **Models** (`artifact_generator_models.py`): add `kind: str = ""` to `ServiceHints`; add a `FunctionalRequirement` dataclass and `functional_requirements: List[FunctionalRequirement]` to `BusinessContext`.
- **Context** (`artifact_generator_context.py`): read `hint.get("kind")` in `extract_service_hints` (~:327); read `requirements.get("functional")`/`traceability` in `load_business_context` (~:390). Absent ⇒ empty ⇒ today's path (FR-11).
- **FR-12 — SLI-kind resolver.** Add `resolve_sli_kinds(kind, functional[], transport) → Set[SignalKind]`, computed once per service beside the descriptor (`artifact_generator.py:519`). Request-serving + no declaration ⇒ `{latency,availability,throughput}` (byte-identical today); non-request + no declaration ⇒ `∅`.
- **FR-12 — gate the triplet.** Make each alert/SLO block emit iff its SLI kind ∈ the resolved set (mirrors the extended-generator gate at `:556`). The `latency`/`availability` template rows *are* today's code, extracted not rewritten.
- **FR-6 — kind→profile table** (`metric_descriptor.py`): add `async_worker`, `batch`, `cron`, `stream` rows to `_PROFILES` (per-kind series/selectors) + a `kind→profile` map beside `_TRANSPORT_DEFAULTS` + a `kind` tier in `resolve_descriptor` (kind wins; HTTP fallback kept for the request family only).
- **FR-7 — per-signal_kind thresholds** (`artifact_generator_generators.py:40`): `_DEFAULT_THRESHOLDS` keyed by `signal_kind`; selected in `_resolve_threshold` (~:127).
- **FR-13 — delete unconditional RED** (`artifact_generator_generators.py:795`): rewrite `_ensure_red_coverage` → `_ensure_signal_coverage(panels, sli_kinds, …)`; backfill only what the set implies; no-op otherwise. Remove the always-on synthesis.
- **FR-5 — signal-kind derivation rows**: `queue_depth`/`retry_rate`/`freshness`/`run_success`/`lag`/`saturation` templates, additive; a kind may suppress a default SLI (worker suppresses latency).

## Phase 3 — Traceability + coverage — FR-8, FR-9

- **FR-8**: at FR-driven emit sites, attach a `DerivationTrace` carrying the source FR id (or add `source_fr` to `ArtifactResult`); it flows into `observability-manifest.yaml` `derivation_rules` (`artifact_generator.py:1150`) with no extra plumbing.
- **FR-9**: add an `fr_coverage` block to the `_write_index` summary (`artifact_generator.py:1077`) — FRs with zero produced artifacts listed explicitly, mirroring `_record_unimplemented_artifact_types` (:870).

## Phase 4 — Doc supersession — FR-10

- Update `docs/design/UNIFIED_OBSERVABILITY_MANIFEST_REQUIREMENTS.md` (or add `docs/design/observability-requirement-shaped/ADR-001-per-fr-derivation.md`) reversing the "new manifest schema" / "per-FR derivation" non-goals, citing this requirements doc.

---

## Cross-repo vs SDK-only

| FR | Owner |
|----|-------|
| CR-1, CR-2, CR-3 (schema + export + `signal_kind`/`kind` authoring) | **Cross-repo** (ContextCore / cap-dev-pipe) |
| FR-0, FR-4 (consume), FR-5, FR-6, FR-7, FR-8, FR-9, FR-10, FR-11 | **SDK** (this repo) |

## Validation

- Phase 0 golden test stays green through Phases 2–3 (FR-11 parity).
- New unit tests: `async_worker` descriptor resolution; worker gets no `http_server_duration` SLO; `signal_kind`-keyed derivation emits queue/retry/freshness artifacts; `fr_coverage` lists a 0-artifact FR.
- End-to-end (OQ-5): once CR-3 emits `kind`, run a minimal worker+FR pilot; confirm the 6-of-7-missing gap closes.

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-obs226/docs/design/observability-requirement-shaped/REQUIREMENTS.md`  ·  **Size:** 187 lines · 2994 words

```markdown
# Requirement-Shaped, Service-Kind-Aware Observability Generation — Requirements

**Version:** 0.4 (Post de-overfit generalization research — ready for CRP)
**Date:** 2026-07-22
**Status:** Ready for review
**Issue:** #226
**Supersedes (in part):** `docs/design/UNIFIED_OBSERVABILITY_MANIFEST_REQUIREMENTS.md` non-goals "New manifest schema" and per-FR derivation (user decision, 2026-07-22: reverse those — see FR-10).

---

## 0. Planning Insights (Self-Reflective Update)

> Documents what changed between v0.1 (pre-planning) and v0.2. The planning pass
> (mapping every FR to real code) produced **8 material corrections** — well over the
> 30% threshold, i.e. the draft was premature and the loop paid for itself.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| FR-1/2/3 add fields "to the manifest / onboarding-metadata" as if the SDK owns those schemas | The SDK **only consumes** `onboarding-metadata.json` (`load_onboarding_metadata`) and `.contextcore.yaml` (`load_business_context`, `artifact_generator_context.py:349`). The producer is ContextCore / cap-dev-pipe Stage-4 EXPORT. | FR-1/2/3 are **cross-repo prerequisites**, not SDK deliverables. Reclassified as CR-* (§2). SDK work = *consumption only*. |
| FR-4 "forward FRs from plan-ingestion" — feasibility unknown (OQ-2) | Plan-ingestion **already emits** `ingestion-traceability.json` via `_build_traceability_artifact` (`plan_ingestion_workflow.py:2207`), with `requirement_mappings[]` carrying `requirement_id`, `feature_ids`, `task_ids`, `acceptance_obligations`, `source_references`. But it has **no `signal_kind`, no numeric target, no service binding**. | FR-4 is **partial-forward**: FR ids + traceability are forwardable cheaply; `signal_kind`/`target`/`service` must be *authored* (they don't exist upstream yet). Split accordingly. |
| FR-6 "branch metric template on service kind" implies scattered if-kind logic | `MetricDescriptor` + named `_PROFILES` (`metric_descriptor.py:127`) **is already the per-shape strategy seam** — resolved once per service (`resolve_descriptor`, `artifact_generator.py:519`) and threaded into every descriptor-aware generator. | FR-6/FR-7 **collapse into** adding an `async_worker` profile + a kind→profile map. Far smaller and more maintainable than a new branch mechanism. |
| FR-7 "replace the single `_DEFAULT_THRESHOLDS`" | `_DEFAULT_THRESHOLDS` (`artifact_generator_generators.py:40`) is **already overridable** per-run via `business.default_thresholds` (`_resolve_threshold`, `:127`). | FR-7 becomes "make `default_thresholds` **kind-keyed**" — plumbing exists; only the shape (flat→per-kind) + lookup change. |
| "Workers get `http_server_duration` SLOs they can't satisfy" is a main-loop bug | The alert/SLO loops gate strictly on `type=="histogram" and "duration" in name` (`generators.py:218/934`). A worker carrying no duration metric already emits nothing there. The spurious RED most likely comes from `_ensure_red_coverage` (`generators.py:795`), which **unconditionally synthesizes** request-rate/availability panels, or from the worker being *fed* http convention metrics upstream. | FR-6's real SDK fix = make **`_ensure_red_coverage` kind-aware** (the one legitimate `if kind` branch). Root cause re-scoped. |
| NR-4 back-compat is protected by golden tests | `test_parity.py` checks metric-name export parity, not full output. **No full-YAML golden/snapshot test of http_server artifacts exists.** | Added **FR-0**: land a golden test locking today's http output *before* touching generators. Back-compat holds structurally (absent kind ⇒ transport default ⇒ identical descriptor) but needs a regression gate. |
| FR-8/FR-9 need new plumbing | `DerivationTrace` + `ArtifactResult.derivations` (surfaced as `derivation_rules` in the manifest) and `GenerationReport` coverage summaries + `_record_unimplemented_artifact_types` (`:870`) are existing patterns. | FR-8/FR-9 attach to existing channels — low churn, no new subsystem. |
| FR-3 "kind could be inferred SDK-side like `detected_databases`" (OQ-3) | `detected_databases` is **not** inferred SDK-side — it arrives pre-computed in the onboarding hint (`artifact_generator_context.py:332`). No SDK-side queue/worker detection exists to reuse. | Kind is **producer-supplied** (cross-repo). SDK may only add a deterministic *fallback* (`transport=http ⇒ http_server`). |

**Resolved open questions:**
- **OQ-1 → onboarding-metadata.json is produced by ContextCore / cap-dev-pipe Stage-4 EXPORT, not the SDK.** SDK consumes it. FR-3/FR-4 forwarding is producer-side.
- **OQ-2 → YES, a structured FR/traceability artifact already exists** (`ingestion-traceability.json`), but lacks `signal_kind`/`target`/`service`. Forward is partial (see FR-4).
- **OQ-3 → kind is producer-supplied** (like `detected_databases`); SDK adds only a transport→kind fallback.
- **OQ-4 → worker metric names live in the new `async_worker` MetricDescriptor profile**; custom signals are declared per-FR via `signal_kind`+`target`.
- **OQ-5 → pilot artifact still not located.** Root-cause hypothesis refined to `_ensure_red_coverage`. Recommend a fresh minimal worker+FR pilot to ground thresholds once the producer emits `kind` (tracked as a validation task, not a blocker for the SDK-side spec).
- **OQ-6 → additive by default.** FR-driven signals are additive to the convention triplet; a kind may *suppress* the default availability/latency SLO (workers suppress latency).

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied the SDK **Design-Docs** lessons (Leg 6) before CRP. Each changed the draft:

- **[Phantom-requirement pruning]** — FR-1/2/3 describe schema fields owned by *other repos*; presenting them as SDK FRs would over-claim scope → moved to **§2 Cross-Repo Prerequisites (CR-1..CR-3)**, leaving §3 as the SDK-owned deliverables only.
- **[Phantom-reference audit]** — every code symbol this spec names was grep-verified to exist → added **§5 Reference Audit** (all PRESENT: `_PROFILES`, `resolve_descriptor`, `_ensure_red_coverage`, `_DEFAULT_THRESHOLDS`, `_resolve_threshold`, `_build_traceability_artifact`, `DerivationTrace`, `_record_unimplemented_artifact_types`).
- **[Extend-vs-build-separate (abstraction invariants)]** — the draft's "branch metric template" risked a parallel mechanism beside the existing profile seam → FR-6/FR-7 rewritten to **extend `MetricDescriptor._PROFILES`**, not build a new kind-dispatcher.
- **[Vocabulary-drift single-source ownership]** — the `signal_kind` enum (availability|latency|queue_depth|retry_rate|freshness|throughput|custom) could drift across the manifest schema and the generator → **this doc is its normative owner** (§3, FR-5); CR-1 and the generator cite it, not restate it.

### 0.2 Design-Principle Hardening (v0.3.1)

> Checked against `docs/design-princples/`. Each changed the draft:

- **[Mottainai]** — don't re-author what an earlier stage produced → FR-4 mandates *forwarding* `ingestion-traceability.json`'s `requirement_mappings[]` rather than re-parsing requirements; only the genuinely-absent `signal_kind`/`target` are authored.
- **[Genchi Genbutsu]** — bind to the real authoritative artifact and respect the boundary → FRs bind to the plan's *actual* FR ids (not a template), and the SDK **stays consume-only** on upstream schemas (CR-* own the writes). No SDK injection into producer artifacts.
- **[Accidental-Complexity anti-principle]** — prefer one general rule to an enumerated special-case list → the profile-extension seam (one rule: kind→descriptor) replaces per-generator `if kind==...` branches; the *sole* justified branch is `_ensure_red_coverage` (RED is a server semantic, not a metric-name swap).
- **[Context-Correctness-by-Construction]** — required context must be declared+validated+degradable, never a silent `None` → **FR-11**: every new field (`kind`, `functional[]`) is optional and its absence yields *byte-identical* pre-#226 output (the NR-4 guarantee, made constructive and test-gated by FR-0).
- **[Hitsuzen]** — derive the determinable deterministically → kind fallback (`transport→kind`) and `signal_kind→metric series` mapping are deterministic table lookups, not LLM calls.

### 0.3 De-Overfit Generalization (v0.4)

> After v0.3.1, two research agents audited the generator for assumptions **overfit to
> HTTP request-serving microservices / the Online Boutique demo** (the first use case).
> The finding reframes #226: v0.3.1 patched *one* off-template case (async workers); the
> real defect is that the **core RED triplet is emitted unconditionally**, i.e. the
> determination model itself assumes every service is a request-server. This pass
> upgrades the spec from "add async_worker" to a general **contract-first determination**
> rule. (The reflective-loop caution: generalize the rule, don't accrete `batch_worker`,
> `cron_worker`, … as siblings.)

**The overfit, in one line:** convention answers *"what does a request-server emit"*; it must **not** be used to answer *"is this a request-server, and if not, what is it"* — yet today's unconditional triplet + `_ensure_red_coverage` synthesis (`artifact_generator_generators.py:795`) does exactly that.

**What the audit found (representative; full catalog in the research report):**

| Decision point | file:line | Overfit class | Breaks for |
|----------------|-----------|---------------|------------|
| `_GENERATORS` triplet emitted unconditionally | `artifact_generator.py:509` | request-serving-only | cron/batch (no availability%/p99), workers |
| `_ensure_red_coverage` **synthesizes** rate/error/availability panels for every service | `artifact_generator_generators.py:795` | request-serving-only (ROOT) | worker/batch/stream/cron get fabricated "Request Rate" panels |
| Duration-histogram gate (`type==histogram and "duration" in name`) is the *only* SLI path | `generators.py:218/934` | request-serving-only | any service whose primary SLI is a counter/gauge/age ⇒ **zero** alerts/SLOs (the pilot's 6-of-7) |
| `_DEFAULT_THRESHOLDS` = availability 99 / latency 500ms / throughput 100rps | `generators.py:40` | request-serving-only | worker/batch/cron (category-error units) |
| `_PROFILES` = only http/grpc/span-metrics | `metric_descriptor.py:127` | request-serving-only | no queue-depth/last-success/lag surface |
| Transport is a **required** field; no-transport services dropped | `artifact_generator_context.py:298` | request-serving-only | workers/cron/batch have no listen transport ⇒ never generated |

**The general principle (now FR-12):** artifacts are derived from a **resolved SLI-kind set** per service — declared (`kind` + `functional[].signal_kind`) with **convention as fallback only within the request-serving family**. Every alert/SLO/panel is a per-SLI-kind template row. The codebase already has this pattern in miniature: `_EXTENDED_PER_SERVICE_GENERATORS` is contract-driven (emitted iff declared, `artifact_generator.py:200/556`). This pass **promotes that pattern to govern the core triplet** and **deletes** the unconditional RED synthesis (FR-13). A plain request-server with no declaration resolves to `{latency, availability, throughput}` ⇒ **byte-identical** to today (FR-0/FR-11 preserved).

**Precedent in-repo:** `stakeholder_panel/facilitation.py:1156` already fixed this exact anti-pattern ("the old fixed Online-Boutique class silently mis-forecast every non-OB project" → now derived from the project's objective). Same inversion, different subsystem.

**Cross-generator scope (honest bound):** the smell is concentrated in `observability/`. The app-skeleton generators (`backend_/frontend_/scaffold_codegen`, `presentation_polish`) are well-hardened (contract-derived, graceful fallbacks). The one sibling instance is **#77** (`view_codegen` `workspace` archetype overfit to the *polymorphic* shape) — same root pattern, tracked separately (its crash is already fixed on main; the non-polymorphic renderer is the open half).

---

## 1. Problem Statement

The observability artifact generator derives a **generic per-service HTTP template** and ignores (a) the plan's functional requirements + traceability and (b) each service's *kind*. Surfaced by the Mastodon status-fanout pilot.

**Behavior today (source-grounded):** iterates `service.convention_metrics`; emits only availability + latency-p99 SLOs on `http_server_duration`; hardcoded defaults `availability="99"`/`latency_p99="500ms"` (`artifact_generator_generators.py:40`); branches only on `transport` (http/grpc), never on service kind.

**Consequences (pilot; re-verify per OQ-5):** every service gets the same two SLOs; an async Sidekiq worker (`mastodonsidekiq`, no HTTP) got `http_server_duration` SLOs; FR-specific signals (queue depth, retry rate, fan-out freshness) produced **zero** artifacts — 6 of 7 FRs yielded nothing.

---

## 2. Cross-Repo Prerequisites (owned by ContextCore / cap-dev-pipe — NOT this repo)

> These unblock the SDK work but land in the producer. Tracked here as dependencies with acceptance criteria; the SDK consumes them (§3) and degrades gracefully until they arrive (FR-11).

- **CR-1 — Manifest carries functional requirements.** `.contextcore.yaml` `spec.requirements.functional[]`, each: `id`, `description`, `signal_kind` (enum owned by §3/FR-5), optional `target`/threshold, optional `service` binding.
- **CR-2 — Manifest carries traceability.** `spec.requirements.traceability[]` mapping FR id → service(s); SHOULD be populated by forwarding `ingestion-traceability.json` `requirement_mappings[]` (Mottainai).
- **CR-3 — Onboarding metadata carries service kind.** `instrumentation_hints[svc].kind ∈ {http_server, grpc_server, async_worker, batch, cron, stream, ml_inference, unknown}` *(generalized v0.4)*, producer-supplied (inferred where possible: queue/worker-library import ⇒ worker/stream; **no listen port ⇒ worker/cron/batch** — the same detection mechanism that supplies `detected_databases`). The producer SHOULD also relax the transport-required drop so a service that declares a `kind` is not excluded for lacking a listen transport (`artifact_generator_context.py:298`).

## 3. Requirements (SDK — this repo)

### Back-compat gate
- **FR-0 — Golden regression test first.** Before any generator change, add a full-YAML golden/snapshot test for a representative `http_server` service (alert + SLO + dashboard_spec) under `tests/unit/observability/`. Every later FR runs against it. (None exists today.)

### Determination model (the general rule — the core of v0.4)
- **FR-12 — Contract-first, SLI-kind determination.** Each service SHALL resolve to a **set of SLI kinds** it is observed by, via one deterministic resolver `resolve_sli_kinds(kind, functional[], transport)`: the union of declared `functional[].signal_kind` and `kind`-implied defaults, falling back to `{latency, availability, throughput}` **only when nothing is declared AND the transport is request-serving**. Empty-and-non-request ⇒ `∅` + a visible coverage gap (FR-9), **never** a silent HTTP triplet. Every alert/SLO/dashboard-panel is derived **per SLI kind** from a per-kind template row. Convention answers "what does a request-server emit"; it does not answer "is this a request-server."
- **FR-13 — Delete unconditional RED synthesis.** `_ensure_red_coverage` (`artifact_generator_generators.py:795`) SHALL become `_ensure_signal_coverage(panels, sli_kinds, …)` — it backfills only the panels the resolved SLI-kind set implies, and is a **no-op** when the set implies none. The always-on request-rate/availability synthesis is **removed**, not merely skipped for one kind. This is the single load-bearing deletion; it is the root cause of the wrong output for *every* non-request class, not just workers.

### Consume + derive
- **FR-4 — Partial-forward, don't re-author.** Consume forwarded FR ids + traceability (CR-2). Only the genuinely-absent `signal_kind`/`target`/`service` are authored/declared; the ids, feature/task mappings, and source references come from `ingestion-traceability.json` unchanged.
- **FR-5 — Signal-kind is the primary derivation axis.** The core triplet's emission is itself `signal_kind`-gated (FR-12), not unconditional. Read `spec.requirements.functional[]`; derive artifacts per `signal_kind`. **Normative `signal_kind` enum (owned here):** `availability`, `latency`, `throughput`, `queue_depth`, `retry_rate`, `freshness`, `run_success`, `saturation`, `lag`, `custom`. At minimum the non-request kinds (`queue_depth`, `retry_rate`, `freshness`, `run_success`, `lag`, `saturation`) gain derivation paths beyond today's availability+latency. Additive by default (OQ-6); a kind MAY suppress a default SLI (workers suppress latency).
- **FR-6 — Kind→profile table (general, not one row).** Extend `MetricDescriptor._PROFILES` with a **table** of workload profiles — ship `http_server`, `grpc_server`, `async_worker`, **`batch`, `cron`, `stream`** (+ their SLI series/selectors) — plus one `kind→profile` map beside `_TRANSPORT_DEFAULTS`; thread `kind` into `resolve_descriptor` so kind wins over transport. `profile_for_transport`'s HTTP fallback survives **for the request-serving family only**. The requirement is the *table + resolution tier*; each row is ~4 additive lines. No service shall receive an SLI on series it does not emit (e.g. a worker on `http_server_duration`).
- **FR-7 — Per-SLI-kind default thresholds.** Make `_DEFAULT_THRESHOLDS` a **per-`signal_kind`** table (not just per-service-kind), selected in `_resolve_threshold` — so a `freshness` FR on *any* service gets a freshness default, decoupled from the service's kind. `business.default_thresholds` override plumbing already exists.

### Traceability + visibility
- **FR-8 — Stamp originating FR id on outputs.** Each FR-derived SLO/alert records its source FR id via a `DerivationTrace` (or a `source_fr` field on `ArtifactResult`), surfaced in `observability-manifest.yaml`.
- **FR-9 — FR + SLI-kind coverage report.** The generation report SHALL list which FRs/`signal_kind`s produced artifacts and which produced **none**, **and** which services resolved to `∅` (the non-request-server-got-nothing symptom), mirroring `_record_unimplemented_artifact_types`. Makes both "6 of 7 FRs missing" and "this ML/stream/cron service got nothing" visible without a manual grep — the gap surfaces in the report instead of being masked by fabricated RED panels.

### Invariants + docs
- **FR-11 — Absent-input parity (constructive).** With no `functional[]` and no `kind`, output is **byte-identical** to pre-#226 for every service (gated by FR-0). New fields are optional; absence degrades to today's convention path.
- **FR-10 — Supersede the design doc.** Update `UNIFIED_OBSERVABILITY_MANIFEST_REQUIREMENTS.md` (or add an ADR) recording that per-FR derivation + the manifest-schema extension are now in-scope, reversing the prior non-goals.

---

## 4. Non-Requirements

- **NR-1 — No target-project code introspection.** Derive from declared FRs + convention metrics only (the prior doc's rejection stands).
- **NR-2 — No new telemetry runtime.** Changes *what artifacts are derived*, not how the target app is instrumented.
- **NR-3 — Ship the general kind→profile table; defer per-kind authoring guidance, not the mechanism.** *(Revised v0.4 — the prior "defer batch/cron/stream" was itself the overfit.)* Ship the `http_server`/`grpc_server`/`async_worker`/`batch`/`cron`/`stream`/`unknown` rows now (each is cheap + additive). What is deferred is polished per-kind *authoring guidance / runbook prose*, not the determination mechanism. Truly exotic archetypes (ml_inference specifics like GPU saturation series) may land as later rows without spec change.
- **NR-4 — No breaking change to today's HTTP output** (now the constructive FR-11 + FR-0 gate).
- **NR-5 — SDK does not write upstream schemas.** CR-1..CR-3 land in the producer; the SDK only consumes (Genchi Genbutsu boundary).

## 5. Reference Audit

All symbols this spec names were grep-verified PRESENT:

| Symbol | File | Used by |
|--------|------|---------|
| `_PROFILES`, `resolve_descriptor`, `_TRANSPORT_DEFAULTS` | `metric_descriptor.py` | FR-6 |
| `_DEFAULT_THRESHOLDS`, `_resolve_threshold`, `_ensure_red_coverage` | `artifact_generator_generators.py` | FR-6, FR-7 |
| `extract_service_hints`, `load_business_context` | `artifact_generator_context.py` | FR-4, FR-6 (consumption) |
| `ServiceHints`, `BusinessContext`, `DerivationTrace`, `ArtifactResult`, `GenerationReport` | `artifact_generator_models.py` | FR-5, FR-8, FR-9 |
| `_record_unimplemented_artifact_types`, `_write_index` | `artifact_generator.py` | FR-9 |
| `_build_traceability_artifact`, `ingestion-traceability.json`, `requirement_mappings[]` | `plan_ingestion_workflow.py:2207` | FR-4 (forward source) |

## 6. Remaining Open Questions

- **OQ-5 (validation)** — locate/read the Mastodon `coverage-gap-analysis.md`, or run a fresh minimal worker+FR pilot to ground `async_worker` metric names + thresholds once CR-3 emits `kind`. Non-blocking for the SDK spec.
- **OQ-7 (new)** — who authors `signal_kind`/`target` for each FR (CR-1): the plan author by hand, a plan-ingestion enrichment pass, or an LLM classifier over `requirements_hints[]`? Determines whether CR-1 is pure schema or schema + an authoring step.

---

*v0.4 — Post de-overfit generalization research (§0.3). Reframed from "add async_worker" to a general contract-first SLI-kind determination model: added FR-12 (SLI-kind determination), FR-13 (delete unconditional RED synthesis); generalized FR-5 (signal_kind primary axis), FR-6 (kind→profile table, not one row), FR-7 (per-signal_kind thresholds), FR-9 (∅-service coverage), NR-3 (ship the table), CR-3 (7-kind enum + no-listen-port inference). Sibling instance #77 (view_codegen) noted; smell bound to observability/. Precedent: stakeholder_panel already fixed this inversion. Ready for CRP.*
*v0.3.1 — Post design-principle hardening. 8 planning corrections; 3 FRs reclassified cross-repo (CR-1..3); FR-6/7 collapsed to profile extension; FR-0 (golden gate) and FR-11 (constructive parity) added; 5 OQs resolved. Applied lessons: phantom-requirement-pruning, phantom-reference-audit, extend-vs-build-separate, vocabulary-single-source. Applied principles: Mottainai, Genchi Genbutsu, Accidental-Complexity, Context-Correctness-by-Construction, Hitsuzen.*

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
