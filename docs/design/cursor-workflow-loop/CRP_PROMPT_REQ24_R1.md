# Convergent Review Prompt

**Generated:** 2026-08-08 00:24:14 UTC
**Mode:** Dual-Document (Plan + Requirements)

> **For the human / orchestrator who generated this file (not instructions to the reviewing agent):**
>
> - This prompt asks the reviewing **agent** to **persist suggestions directly into the source documents** by appending a new **Review Round** under the document's **Appendix C (Incoming)**. The A/B/C scaffold is **pre-initialized by this generator script** (per \`CONVERGENT_REVIEW_AGENT_GUIDE.md\`), so the reviewer only appends. The chat reply is a short write-confirmation only — **no** in-chat numbered list.
> - **Triage is yours and MUST be persisted, not stripped:** for each suggestion record a disposition — **Accepted → Appendix A** (note where it was merged) or **Rejected → Appendix B** (with rationale) — and update the **Areas Substantially Addressed** tracker (3 accepted per area). Appendices A/B are the **cross-model memory**: later reviewers (you embed the guide telling them so) read them to avoid re-proposing settled or rejected ideas. Do **not** delete A/B after merging.
> - **Suggested separate review passes (orchestrator workflow):** 2 — e.g. run the prompt once for breadth, again for adversarial pass, then triage yourself.
> - **Triage threshold (reference):** 3 accepted suggestions per review area when you triage.
> - **Max suggestions to request from the model:** 10 (soft cap in reviewer instructions below).
> - **Reviewer must have file-write tools (Write/Edit/equivalent) and filesystem access to the source documents.** Chat-only LLMs will fail this contract.

### Source documents

| Role | Path | Size |
|------|------|------|
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/cursor-workflow-loop/PLAN-24-WLQ-Atomic-Claim-Lease.md` | 101 lines · 880 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/cursor-workflow-loop/REQ-24-WLQ-Atomic-Claim-Lease.md` | 241 lines · 2283 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/cursor-workflow-loop/CRP_FOCUS_REQ24_R1.md` | 41 lines · 443 words |

Treat the embedded documents below as the **authoritative review surface** for this
round: do **not** rewrite plan/requirements body prose (Appendix C append only —
that is what "read-only" means here). If something conflicts between plan and
requirements, call it out explicitly in suggestions and in the coverage mapping.

When the docs extend or modify an **existing** system (not greenfield), you **MAY
and SHOULD** open **named** files/symbols the docs cite (or that the plan's file
list implies) to check real APIs, reuse opportunities, and accidental-complexity
risks (parallel machinery, reinvented helpers, wrong layer). Do **not** run
open-ended repo-wide exploration unrelated to validating a concrete suggestion —
persist Appendix C first; targeted code reads are in service of better suggestions,
not a substitute for writing them.

---

## Your Task

You are a **senior architectural reviewer** with **file-edit tools** (Write/Edit/equivalent) and filesystem access to the source documents listed above (and, when needed for non-greenfield grounding, **read** access to named implementation files those docs cite). Your job is to produce **improvement suggestions** (structured, anchored, actionable) and **persist them directly into the source documents** by appending a new **Review Round** under each reviewed document's **Appendix C (Incoming)** — see **Prior Review State** below.

**First, read the existing review state** (Appendix A/B/C) in each source doc and **avoid re-proposing** what is already settled (A) or rejected (B), and **avoid near-duplicates** of untriaged items in C (dedup rules below). Every in-scope doc already contains a \`## Appendix: Iterative Review Log\` with an empty A/B/C scaffold (the generator created it) — **append your round to Appendix C**; do **not** create a second scaffold.

**Do not** triage (no ACCEPT/REJECT disposition for your own or others' suggestions — that is orchestrator-side and lands in Appendix A/B), **do not** modify or rewrite existing prose, **do not** alter Appendix A/B or **prior rounds** in Appendix C, and **do not** emit a numbered suggestion list in chat — the orchestrator reads them from the files.

Optimize for **actionable, mergeable feedback** written into the right file.

### Prior Review State — read this BEFORE writing suggestions

Each source document **is** the persistent review state. Before proposing anything, parse its \`## Appendix: Iterative Review Log\` (if present):

- **Appendix A (Applied / Accepted)** — settled improvements. **Do not re-propose** anything here.
- **Appendix B (Rejected)** — read each **rationale**. Do **not** re-propose a rejected idea unless you explicitly cite its ID and argue why the rationale no longer holds.
- **Appendix C (Incoming)** — prior rounds, some untriaged. **Do not duplicate** a near-identical suggestion; if you agree with an untriaged item, **endorse** it (see Deliverables) instead of restating it.

**Your round number** is \`R{n}\` where **n = (highest existing \`#### Review Round R{n}\` in Appendix C) + 1**, or **1** if none exist. Put it in every suggestion ID: **R{n}-S{k}** (plan) / **R{n}-F{k}** (requirements).

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

# CRP Focus — REQ-24 / PLAN-24 WLQ Atomic Claim Lease (Round 1)

## Least-reviewed target
Both REQ-24 (v0.3.1) and PLAN-24 are **brand-new, never CRP'd** — this is Round 1. Weight the review
toward the concurrency semantics below; the surrounding det-req scaffolding has already passed the
reflective loop + lessons + principle hardening.

## Settled — do NOT relitigate (already decided with rationale)
1. **Scope is option 2 / minimal.** `renew`/heartbeat, the `CLAIM{won|lost}` fleet event, and
   `blind_rotate`/`depends_on` acquire-guards are **deliberately deferred to full A1** (see Non-goals).
   Do not propose adding them.
2. **`O_EXCL` sentinel over fcntl `FileLock`** — chosen because fcntl advisory locks release on holder
   death, which would defeat TTL takeover; the sentinel persists so `reclaim_expired_leases` can steal
   it. Rationale recorded in Appendix B. Do not re-propose fcntl.
3. **Local-filesystem assumption is intentional.** NFS / network-FS `O_EXCL` correctness is out of
   scope (NR + OQ-B). Do not propose an NFS-safe redesign.
4. **Reuse-not-rebuild (Mottainai) is a hard constraint.** No new lock server, daemon, or second
   ledger. Suggestions must extend the existing lease/queue, not introduce a new engine.

## Where input is most valuable (weight these)
1. **Sentinel lifecycle correctness.** Is there any window where the `CLAIM.lock` sentinel and the
   job-state lease (`lease_expires_at`/`lease_owner`) can diverge? Consider: acquire that stamps the
   lease but crashes before/after writing the sentinel; the `save_job` temp+rename not being atomic
   *with* the `O_EXCL` create (two separate operations). Is FR-1's ordering (sentinel-first, then
   stamp) the safe one, or should it be reversed?
2. **`run_next` internal-CAS integration (FR-6).** `run_next` calls `reclaim_expired_leases()` then
   `_try_claim`. Is there a TOCTOU *between* the reclaim and the acquire? Does routing the internal
   transition through the sentinel change any existing `run_next` behavior (sdk-workflow vs one-shot
   drain paths, `complete_drain` re-entry on an already-PROCESSING job at queue.py:319)?
3. **Reclaim/release cleanup completeness.** FR-4 claims sentinel-unlink at *every*
   `lease_expires_at = None` site (queue.py:248, 262, 1285, 1515, complete_drain, cancel, requeue).
   Is that enumeration complete and correct? Is there a site that nulls the lease *without* going
   through `_transition`? Is unlink idempotent (missing_ok) so double-release/reclaim races don't error?
4. **Cross-process contention test design (It-2).** Is `multiprocessing.Process` racing on a shared
   temp queue root a faithful reproduction of the TOCTOU? Does it need a synchronization barrier so
   both processes reach the acquire simultaneously (else the race never actually fires and the test is
   a false green)? What's the assertion that proves *exactly one* winner without flakiness?
5. **Owner-authority edge cases (FR-4).** After a TTL takeover, surface A's lease was stolen by
   surface B; can surface A's late `release` (still believing it owns the job) now unlink surface B's
   live sentinel? How does release distinguish "I own the current lease" from "I owned a since-expired
   one"?

**If the focus file above contains numbered asks** (e.g. `A1`/`A2`/`Ask 1`/`Ask 2` or similar), address each ask **at the top of your appended round**, before standard S/F-prefix suggestions, using this template per ask (orchestrator triages later — **no** ACCEPT/REJECT tables here, and **no** chat-only response):

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

If you still have budget under the max-suggestions cap after your first list, you may add a \`### Stress-test / adversarial pass\` subheading **inside your round block**, with **additional** numbered suggestions (continue **R{n}-S\*** / **R{n}-F\*** numbering within the same round — do not fabricate a separate round). Try to break your own prior conclusions where it genuinely helps; skip if redundant. **Still no in-chat list** — keep the chat reply to the short write-confirmation.

---

### Pre-flight (before drafting suggestions)

1. **Optionally expand** the protocol guide \`<details>\` block below and skim **quality norms** (anchoring, scope, security). You are **not** executing full CRP phase/triage automation—use the guide as reference only.
2. Read the **Document Under Review** section(s) once for structure; read again while drafting suggestions.
3. Note **explicit out-of-scope** lines — do not file suggestions that only restate excluded work unless you flag a **dependency risk** (why exclusion threatens delivery).

---

### Protocol guide — optional reference (norms for good suggestions)

**Important:** Some chat clients or models collapse \`<details>\` by default. Expand if you need **deeper** CRP vocabulary; this prompt does **not** require you to run guide phases 5–7 (triage, appendix merge, final document emit).

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/cursor-workflow-loop/PLAN-24-WLQ-Atomic-Claim-Lease.md`  ·  **Size:** 101 lines · 880 words

```markdown
# PLAN-24 — WLQ Atomic Claim Lease (option 2 / minimal)

**Pairs with:** `REQ-24-WLQ-Atomic-Claim-Lease.md` (v0.2)
**Date:** 2026-08-07   **Status:** planned, not started

> Iterations are dependency-ordered and acyclic. It-1 builds the primitive; It-2 proves it closes the
> TOCTOU; It-3 adopts it in the adapters. Each iteration ends green (tests pass) before the next.

## It-1 — The CAS primitive + model field + CLI verbs  →  FR-1, FR-2, FR-5, FR-6

1. **Model (FR-5).** Add `lease_owner: Optional[str] = None` to `WorkflowLoopJob`
   (`models.py:346`, beside `lease_expires_at`). No migration — additive optional field; existing job
   files deserialize with `lease_owner=None`.
2. **Sentinel helper (FR-1).** Add `claim_lock_path(job_id) -> Path` to `LoopQueueStorage`
   (`storage.py`, beside `handoff_path`/`result_path`) → `artifact_dir(job_id)/CLAIM.lock`. Add
   `try_acquire_sentinel(job_id, owner) -> bool` (os.open `O_CREAT|O_EXCL|O_WRONLY`, write
   `{owner, ts}`, close; `FileExistsError` → `False`) and `release_sentinel(job_id)` (unlink,
   `missing_ok=True`). Ensure `artifact_dir` exists before the `O_EXCL` open.
3. **Internal acquire (FR-1, FR-6).** Introduce `_try_claim(job, owner) -> bool` in `queue.py`: after
   the existing `PENDING` check, call `try_acquire_sentinel`; on success `_transition(job, PROCESSING, …)`
   (which already stamps `lease_expires_at`) and set `job.lease_owner = owner`, `save_job`; on failure
   return `False` (no state change). Route **`run_next`'s** pending→processing transition
   (`queue.py:332 → 442`) through `_try_claim` so the direct path is race-safe (FR-6). Keep the leading
   `reclaim_expired_leases()` call (`:317`) — reclaim now clears stale sentinels (It-1 step 5).
4. **CLI verbs (FR-1, FR-2).** Add `@wloop_app.command("claim")` (`--job-id`, `--surface`) and
   `release` (`--job-id`) to `cli_wloop.py`. `claim`: `_try_claim` True → print `won`, exit 0; False →
   if lease live `raise typer.Exit(3)`, else surface the error. `release`: FR-4 (It-1 step 6).
5. **Reclaim cleanup (FR-3).** In `reclaim_expired_leases` (`queue.py:1274`), before/after nulling
   `lease_expires_at`, call `release_sentinel(job.job_id)` and clear `lease_owner`, so an expired
   lease's sentinel is removed and the next claim can win.
6. **Release + authority (FR-4).** `release(job_id, owner=None)`: reject if `job.lease_owner` set and
   `owner != job.lease_owner` and lease not expired; else `release_sentinel` + clear `lease_owner` +
   transition off PROCESSING as applicable. Wire `release_sentinel` + `lease_owner=None` into every
   existing `lease_expires_at = None` site: `complete_drain`, `cancel` (`:230`), `requeue` (`:238/:248`),
   `_transition`'s non-PROCESSING branch (`:1515`).

## It-2 — Contention test (the acceptance that proves the TOCTOU is closed)  →  FR-1, FR-2, FR-3, FR-6

- **Cross-process race (FR-1/FR-6).** `tests/unit/workflows/loop_queue/test_atomic_claim.py`: enqueue
  one PENDING job in a temp queue root; spawn **two `multiprocessing.Process`** workers that both call
  `claim` (and a second test: both call `run_next`); assert **exactly one** wins, one gets exit-3 /
  raises, and exactly one `CLAIM.lock` exists. Use processes not threads — the primitive is cross-process.
- **Single-holder (FR-2).** Second `claim` on a held job exits 3.
- **Stale reclaim (FR-3).** Set `lease_ttl_seconds` small (or backdate `lease_expires_at`); assert
  reclaim removes the sentinel and a subsequent `claim` wins.
- **Mixed-surface temp-queue contention** (acceptance): two distinct `--surface` ids racing one job →
  exactly one `won`.

## It-3 — Adapter adoption + board deprecation  →  FR-4 (authority)

- `drain-claude` / codex adapters call `wloop claim --job-id --surface` **before** drain, replacing the
  per-surface single-flight lock as the *cross-surface* primitive; `release` (or `run-next` consume) on
  completion.
- Deprecate any `CLAIMED_BY.*` / `CLAIM.lock.claude` per-root convention in the board §2 (it is
  per-surface-per-root and does not serialize across surfaces — superseded by the per-job sentinel).
- Update `codex-loop/REQ-01` note: "until an upstream atomic claim contract is available" → **A1
  option 2 IS that contract** (this REQ).

## Acceptance (whole)

Two surfaces racing one job → exactly one `won`; stale lease reclaimed **and its sentinel removed**
after expiry; a mixed-surface temp-queue contention test passes; `run-next` direct path is race-safe.

## Traceability

| FR | Iteration(s) |
|----|--------------|
| FR-1 Atomic acquire (CAS) | It-1 (2,3,4), It-2 |
| FR-2 Single holder | It-1 (4), It-2 |
| FR-3 Stale reclaim + sentinel cleanup | It-1 (5), It-2 |
| FR-4 Release + owner authority | It-1 (6), It-3 |
| FR-5 Owner-stamped lease field | It-1 (1) |
| FR-6 `run_next` closes TOCTOU | It-1 (3), It-2 |

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/cursor-workflow-loop/REQ-24-WLQ-Atomic-Claim-Lease.md`  ·  **Size:** 241 lines · 2283 words

```markdown
# WLQ Atomic Claim Lease (option 2 / minimal) — Requirements

**Project:** startd8-sdk   **Criticality:** medium
**Version:** 0.3.1 (Post-planning + lessons + design-principle hardening — ready for CRP)
**Date:** 2026-08-07
**Format:** det-req/0.1
**Backend:** spike-component
**Pairs with:** `PLAN-24-WLQ-Atomic-Claim-Lease.md`
**Inherits standards:** det-req-kit
**Precedes / grounds in:** `A1-WLQ-ATOMIC-CLAIM-NEXT-STEPS.md` (the build handoff); extends
`CURSOR_WORKFLOW_LOOP_REQUIREMENTS.md` **FR-3** (durable status + lease reclaim) + **OQ-5** (lease
TTL, resolved). Upstream ask: `OSS/Istio/analysis/CODE_ASKS_fleet_and_loop_REQ_PLAN_2026-08-04.md`
§A1 (option 2 = the FR-1/2/5 subset of the full A1). Pattern (rule 1):
`dev-os/multi-vendor-loop/docs/SURFACE_FLEET.md`.

## 0. Planning Insights (Self-Reflective Update)

> The v0.1 framing is the A1 handoff's §3/§4 ("extend the existing lease, atomicize it with
> `O_EXCL` over the lease field"). A code-grounding planning pass against the real WLQ surface
> (`queue.py`, `storage.py`, `models.py`, `file_operations.py`) falsified or sharpened **6**
> assumptions. The rate (>30%) confirms the handoff framing was a correct *direction* but premature
> as a spec — exactly what this loop is for.

| v0.1 Assumption (A1 handoff) | Planning Discovery (file / fact) | Impact |
|------------------------------|----------------------------------|--------|
| `O_CREAT\|O_EXCL` writes "over the existing lease field" | The lease lives *inside* the job envelope; `storage.job_path` **already exists** after `enqueue`, and `save_job` → `atomic_write_json` is **temp+rename, last-writer-wins** (`file_operations.py:174`) — not a CAS. You cannot `O_EXCL` a file that exists. | The CAS must be a **separate per-job sentinel file**; its `O_EXCL` *creation* is the compare-and-set. The lease field is only the *record* of who won. → **FR-1, FR-5** |
| "Extend the existing lease" is sufficient | The lease is **owner-less**: `lease_expires_at` (`models.py:346`) is a bare timestamp; there is **no** `surface_id`/owner anywhere on `WorkflowLoopJob`. | "Single holder" (FR-2) and "release by owner" (FR-4) are unenforceable without an owner. Add `lease_owner`. → **FR-5** |
| Reuse `reclaim_expired_leases` unchanged for stale takeover | `reclaim_expired_leases` (`queue.py:1274`) only nulls `lease_expires_at` + transitions to PENDING (`:1285`). It knows nothing of a sentinel. | With a sentinel CAS, an expired lease would be "reclaimed" in job state **while the sentinel still blocks every future claim** → permanent wedge. Reclaim **must also unlink the sentinel**. Same for every other `lease_expires_at = None` site (`:248` requeue, `:262`, `:1515` `_transition`). → **FR-3, FR-4** |
| A new `wloop claim` CLI verb closes the race | `run_next` already calls `reclaim_expired_leases()` then a **bare** `_transition(job, PROCESSING)` (`queue.py:317 → 332 → 442`). A CLI-only sentinel leaves the **direct `run-next` path's TOCTOU wide open**. | The CAS must be **internal to the acquire path `run_next` uses**; the `claim` verb is just an explicit entry to the same primitive. → **FR-6** |
| Use `O_EXCL` (vs the existing lock) — unmotivated | A fcntl `FileLock` already exists (`file_operations.py:183`). | Lock the rationale in: **fcntl advisory locks release on holder death**, which would defeat TTL takeover; an **`O_EXCL` sentinel persists** past a dead holder, so `reclaim_expired_leases` can steal it after `lease_ttl_seconds`. Choose sentinel, reject fcntl. → **FR-1 note, NR** |
| `exit 3, retryable` is a given | `cli_wloop.py` is Typer; exit codes are `typer.Exit(code=…)`, not implicit. | FR-2 must specify `typer.Exit(code=3)` and document 0=won / 3=held-retryable / non-3-nonzero=error so drainers can branch. → **FR-2** |

**Resolved open questions (from planning):**
- **OQ-A → Sentinel home = `storage.artifact_dir(job_id)/CLAIM.lock`.** The per-job artifact dir
  already exists (`storage.py:55`); the sentinel rides beside `drain-handoff.json` / `drain-result.json`,
  so cleanup and discovery are trivial and per-job-scoped (not per-root like the old `CLAIM.lock.claude`).
- **OQ-B → Local-filesystem assumption is explicit.** `O_EXCL` atomicity is guaranteed on local FS;
  NFS/`O_EXCL` is out of scope (NR). The queue root is a local `.startd8/` dir today.

### 0.1 Lessons-Learned Hardening (v0.3)

> Keyed Pattern-Catalog recall (`concurrency-primitive × file-lock`, `cli-verb × queue-op`,
> `model-field × lease`) returned empty → domain browse of `craft/Lessons_Learned/sdk/`. Two lessons
> changed the draft:

- **[Phantom-reference audit]** — grepped every symbol the spec names. Caught: the A1 handoff's
  `is_expired` does **not** exist — the model method is `lease_expired(now=…)` (`models.py:424`).
  Corrected here; all other refs verified live (see Reference-Audit below). This is why FR-3 cites
  `reclaim_expired_leases`/the TTL, not a method name.
- **[Single-source vocabulary ownership]** — WLQ **job state remains the one source of truth**; the
  `CLAIM.lock` sentinel and `lease_owner` are **derived records**, not a second authority. Reinforced
  in FR-4 by unlinking the sentinel + clearing `lease_owner` at *every* `lease_expires_at = None` site,
  so the sentinel can never drift out of sync with job state.
- **[Propagation gate]** *(build-time, carried to PLAN It-3, not a spec change)* — "PR merged ≠ tip on
  `main`"; verify the adapter adoption + board-deprecation actually reach `origin/main`.

**Reference-Audit** (every code symbol the spec names, grounded):

| Symbol / anchor | Status |
|-----------------|--------|
| `WorkflowLoopJob.lease_expires_at` `models.py:346` | ✅ exists |
| `lease_expired(now=…)` `models.py:424` | ✅ exists (**A1's `is_expired` was phantom**) |
| `LoopQueueConfig.lease_ttl_seconds` `models.py:443` | ✅ exists |
| `reclaim_expired_leases` `queue.py:1274` | ✅ exists |
| `run_next` acquire `queue.py:317/332/442` | ✅ exists (TOCTOU confirmed) |
| `cancel` `queue.py:230` · `requeue` `queue.py:238` · `_transition` `queue.py:1500/1515` | ✅ exist |
| `LoopQueueStorage.artifact_dir` `storage.py:55` · `save_job`→`atomic_write_json` `storage.py:92` | ✅ exist |
| `atomic_write_json` (temp+rename) `file_operations.py:174` · fcntl `FileLock` `:183` | ✅ exist |
| `wloop_app` Typer verbs `cli_wloop.py:38` | ✅ exists; `claim`/`release` **to-be-created** |
| `WorkflowLoopJob.lease_owner` | ⛔ **to-be-created** (FR-5) |
| `CLAIM.lock` sentinel + `claim_lock_path`/`try_acquire_sentinel` | ⛔ **to-be-created** (FR-1) |

### 0.2 Design-Principle Hardening (v0.3.1)

> Keyed lookup against `dev-os/PRINCIPLE-INDEX.md` §2 on this draft's decision-classes
> (`code × fail-loud/validation-gate`, `× single-source/no-drift`, `code × idempotency/reuse`). Four
> principles bore on the draft:

- **[Hayai — don't defer enforcement]** — mutual exclusion binds at the **earliest resolvable point**
  (the `O_EXCL` acquire), never a later scan/review. *Enforcer named:* the `O_EXCL` open itself + the
  cross-process contention test (PLAN It-2) — surfacing is not the gate, the failing-then-passing race
  test is.
- **[Mottainai — don't regenerate what exists]** — reuse `lease_expires_at`, `lease_ttl_seconds`,
  `reclaim_expired_leases`, `_transition`'s stamp, and `artifact_dir`; **no new engine, no lock
  server**. The whole premise of option 2. → Non-goals, FR-3/FR-5.
- **[Single-source / no-drift]** *(enforceable)* — job state is authoritative; the sentinel is derived.
  *Enforcer named:* the unified sentinel-cleanup wired into every `lease_expires_at = None` site
  (FR-4) — one code path keeps the two representations from ever diverging.
- **[Context-Correctness-by-Construction]** — `lease_owner` must **arrive**, not silently be `None`
  (else FR-2 single-holder and FR-4 owner-authority degrade to no-ops). → **sharpened FR-2/FR-5:
  `--surface` is required on `claim`; an acquire with no owner is rejected, not defaulted.**
- **[Accidental-Complexity]** — checked: the sentinel + one owner field is the single general rule;
  the fcntl alternative and a per-root allowlist were both rejected (Appendix B). No compensating
  layer added.

## Overview

`run_next`'s pending→processing claim is a TOCTOU: two drainers (e.g. two vendor surfaces) can both
read `PENDING`, both pass the check, and both write `processing` → double-drain. This adds one
**atomic claim primitive** — a per-job `O_EXCL` sentinel that is the compare-and-set — reusing the
SDK's existing lease state (`lease_expires_at`, `lease_ttl_seconds`, `reclaim_expired_leases`) and
adding only an owner field plus two CLI verbs. It is the multi-vendor fleet's **rule 1**. It is
**fleet-readiness, not a live-bug fix**: the race is dormant today (single-surface use + WIP=1), so
build it deliberately as the enabler of the intra-project vendor fleet, not a firefight.

## Objectives

- O-1: Exactly one drainer can hold a given job at a time — the pending→processing acquire is atomic
  across processes and across surfaces.
- O-2: An abandoned claim is recoverable without operator intervention — reused TTL reclaim, sentinel included.
- O-3: Zero new engines — extend the existing lease + queue; no lock server, no fleet-event, no renew.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | Orphaned sentinel wedges the queue (holder dies mid-claim) | FR-3: TTL reclaim unlinks the sentinel; local-FS `O_EXCL` + TTL bounds the wedge window | high |
| quality | CLI-only CAS leaves `run_next`'s internal path racy | FR-6: acquire is internal to the path `run_next` uses, not a bolt-on | high |
| safety | Non-owner releases someone else's live claim | FR-4: release checks recorded `lease_owner`; only owner or TTL-expired takeover may release | medium |
| availability | `O_EXCL` semantics on NFS/network FS | NR + OQ-B: local-filesystem assumption stated; NFS out of scope | low |

## Profile

Declared profile: **internal**

## Functional requirements

- **FR-1 — Atomic acquire (CAS via sentinel).** Acquiring a `PENDING` job creates
  `storage.artifact_dir(job_id)/CLAIM.lock` via `O_CREAT|O_EXCL` (a separate sentinel, **never** the
  job envelope); on success it stamps `lease_owner=<surface_id>` + `lease_expires_at` (reusing
  `_transition`'s existing stamp) — never read-then-write. Note: sentinel chosen over the existing
  fcntl `FileLock` because the sentinel survives holder death (required by FR-3). Touches:
  `src/startd8/workflows/loop_queue/queue.py` (claim path), `src/startd8/workflows/loop_queue/storage.py`
  (sentinel path helper). Verify: two processes race one `PENDING` job → exactly one `CLAIM.lock`
  created, one `won`, one non-zero.
- **FR-2 — Single holder.** A second `claim` on a job whose sentinel exists and whose lease is not
  expired returns `typer.Exit(code=3)` (retryable); exit codes: `0`=won, `3`=held-retryable,
  other-nonzero=error. `--surface <sid>` is **required** (no default) — an acquire with no owner is
  rejected, so `lease_owner` can never be `None` on a held job (CCbC). Touches:
  `src/startd8/cli_wloop.py` (`claim` verb), `src/startd8/workflows/loop_queue/queue.py`. Verify: a
  held job's second `claim` exits `3`; a `claim` with no `--surface` exits non-zero (never acquires).
- **FR-3 — Stale reclaim + sentinel cleanup (extends existing).** A lease past `lease_ttl_seconds` is
  reclaimable via the existing `reclaim_expired_leases`, **and that reclaim now also unlinks the
  orphaned `CLAIM.lock`** so the next `claim` can win; `0` disables (unchanged). Touches:
  `src/startd8/workflows/loop_queue/queue.py:1274`. Verify: given an expired lease, reclaim removes
  the sentinel and the next `claim` wins.
- **FR-4 — Release + owner authority.** `startd8 wloop release --job-id <id>` (auto on `run-next`
  consume / `complete_drain`) unlinks the sentinel and clears `lease_owner`; only the recorded
  `lease_owner` (or a TTL-expired takeover) may release; WLQ job state is the single source of truth.
  Every `lease_expires_at = None` site (`queue.py:248` requeue, `:262`, `:1515`, `complete_drain`,
  `cancel`) also unlinks the sentinel. Touches: `src/startd8/cli_wloop.py` (`release` verb),
  `src/startd8/workflows/loop_queue/queue.py`. Verify: consume releases + removes sentinel; a
  non-owner `release` is rejected; direct status writes are not the claim path.
- **FR-5 — Owner-stamped lease field.** Add `lease_owner: Optional[str] = None` to `WorkflowLoopJob`;
  stamped on acquire, cleared on release/reclaim. Touches:
  `src/startd8/workflows/loop_queue/models.py:346`. Verify: an acquired job serializes
  `lease_owner=<surface_id>`; a released/reclaimed job serializes `lease_owner=None`.
- **FR-6 — `run_next` closes the TOCTOU.** `run_next`'s internal pending→processing acquire
  (`queue.py:332 → 442`) goes through the **same** CAS primitive as FR-1, not the bare
  check-then-`_transition`, so direct `run-next` callers are race-safe too. Touches:
  `src/startd8/workflows/loop_queue/queue.py:296-442`. Verify: two concurrent `run-next` on one
  `PENDING` job → exactly one drains; the other raises/exits non-zero (does not double-drain).

## Non-goals

- `renew` / heartbeat lease extension (full A1).
- The `CLAIM{won|lost}` **Fleet Event** (`contextcore fleet emit` — A3).
- `blind_rotate` / `depends_on` **acquire guards** (FR-4 of the code-asks — full A1).
- A new lock server or daemon; a second ledger; any fcntl-based lock (rejected — see FR-1).
- NFS / network-filesystem `O_EXCL` correctness (local-FS queue root only — OQ-B).

## Owned fields

Only humans enter: none. `lease_owner` is **machine-stamped** from the caller's `--surface <sid>`;
never hand-authored into a job file.

## Contract projection

- **Backend:** spike-component
- **Vocabulary home (cite):** `src/startd8/workflows/loop_queue/models.py` (`WorkflowLoopJob`,
  `LoopQueueConfig`, `LoopJobStatus`); `src/startd8/cli_wloop.py` (`wloop_app` Typer verbs).

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| `WorkflowLoopJob.lease_owner` | field | structure | new `Optional[str]`; drift-hashed |
| `CLAIM.lock` sentinel | file path | structure | `storage.artifact_dir(job_id)/CLAIM.lock`; `O_EXCL` = CAS |
| `wloop claim` | cli-verb | structure | `--job-id`, `--surface`; exit 0/3/other |
| `wloop release` | cli-verb | structure | `--job-id`; owner-checked |
| `reclaim_expired_leases` (extended) | queue-op | structure | now also unlinks sentinel |

---

## Appendix A — Accepted (with where merged)

_(none yet — pre-CRP)_

## Appendix B — Rejected (with rationale)

- **fcntl `FileLock` for the CAS** — rejected: advisory locks release on holder death, defeating TTL
  takeover (FR-3). The `O_EXCL` sentinel persists past death so reclaim can steal it. (planning, v0.2)

## Appendix C — Incoming review rounds

_(awaiting CRP round 1)_

---

*v0.2 — Post-planning self-reflective update. 6 assumptions corrected (1 CAS-target, 1 owner-field,
1 reclaim-cleanup, 1 run_next-internal, 1 fcntl-rationale, 1 exit-code), 2 open questions resolved,
1 requirement added (FR-6). — v0.3 — Applied 2 lessons (phantom-reference audit → caught A1's
`is_expired`; single-source vocabulary), reference-audit table added. — v0.3.1 — Applied 4 principles
(Hayai, Mottainai, single-source/no-drift, CCbC → `--surface` required; Accidental-Complexity checked).
Ready for CRP review.*

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
- [ ] Appended a \`#### Review Round R{n}\` block under **Appendix C** of each source file in scope (the A/B/C scaffold is generator-created — appended to it, did not recreate it).
- [ ] Round block contains: executive summary (≤10 bullets) + numbered suggestions (**R{n}-S\*** / **R{n}-F\***); optional adversarial subsection; optional Endorsements & Disagreements block.
- [ ] Did not modify existing prose, populated Appendix A/B, or prior rounds in C.
- [ ] Appended `## Requirements Coverage Matrix — R{n}` section to the end of the **plan** file (after your round block).
- [ ] Chat reply is a **short** (1–3 line) write-confirmation listing file paths and suggestion counts — **not** the suggestion content.

**Stop after persisting** — do not triage, do not emit merged documents in chat or in the files, do not modify existing prose, populated Appendix A/B, or prior rounds in Appendix C (the A/B/C scaffold is generator-created — do not add another).
