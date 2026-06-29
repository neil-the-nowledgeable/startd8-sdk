# Convergent Review Prompt

**Generated:** 2026-06-29 20:19:47 UTC
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
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/kickoff/RED_CARPET_TREATMENT_PLAN.md` | 140 lines · 1399 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/kickoff/RED_CARPET_TREATMENT_REQUIREMENTS.md` | 297 lines · 2982 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/kickoff/crp-focus-red-carpet-treatment.md` | 70 lines · 662 words |

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

# CRP Focus — Red Carpet Treatment (R1)

The **Red Carpet Treatment (RCT)** is a new, large milestone: a white-glove **agentic,
build-from-scratch** experience (web + CLI) that orchestrates EXISTING startd8 pieces to populate the
**complete kickoff input surface** (data-model `schema.prisma` contract + assembly manifests + 4 value
inputs + placeholder content) so the deterministic `$0` cascade can run at full capability. It is an
**orchestration layer above** Welcome Mat 2.0 + Concierge. Weight the review toward the highest-risk
architecture below; RCT is "mostly reuse" but the new pieces touch the security boundary.

## Settled boundaries — do NOT re-propose (assume them)

Inherited from Welcome Mat 2.0 / Concierge mode, treated as fixed:
- The agentic **loop never writes** — it proposes; a foreground **human applies at human privilege**
  (web same-origin POST + CSRF + loopback Host + one-time-intent; or CLI/TUI explicit confirm).
- **MCP stays preview/read-only.**
- The deterministic cascade is **bucket-1, `$0`, Python-only**; RCT produces inputs (buckets 1–3),
  never the user's real bucket-4 content.
- **Reuse, don't re-implement** (`concierge/derive`, `manifest_extraction` extractors, the `$0`
  cascade, the `ProposedAction`/`apply_proposal` proposal model, `capture.py`, readiness).

## Where reviewer input matters most

### A. The write-model extension (HIGHEST — this is the security crux)
- **Per-kind apply paths (FR-RCT-9).** RCT adds proposal kinds `schema` / `manifest` / `value-input`
  to the existing `ProposedAction`/`apply_proposal` model (today `friction`/`instantiate`), each routed
  to a different write seam: `schema` → `generate contract --promote`; `manifest` → the new N1
  project-tree writer; `value-input` → `capture.py` per-key merge. **Does adding kinds widen the
  loop's reach?** Can an agent-drafted proposal of a new kind smuggle a write the human didn't intend
  (e.g. a `manifest` proposal whose `dest` escapes `docs/kickoff/inputs/`, or a `schema` proposal that
  promotes without ratification)? How must each kind **re-validate on apply** (grammar/round-trip/
  confinement) so the loop's draft is never trusted blindly?
- **The "loop never writes" invariant under a richer vocabulary.** With many more propose-able kinds,
  what keeps the read-effect floor intact? Should there be a single enumerated allow-list of
  human-apply kinds + a test that the agent registry exposes only read/propose, never apply?

### B. N1 — the project-tree manifest writer (HIGH — the biggest new piece)
- `extract_manifests` is pure/in-memory and round-trip-gated; **no command writes prose→
  `docs/kickoff/inputs/*.yaml` in the project tree today** (only a workflow → run-dir). RCT adds that
  writer over the existing `apply_write_plan` confinement seam. **Path-confinement / overwrite
  semantics:** does it clobber an existing hand-edited manifest? no-clobber vs overwrite-on-confirm?
  zip-slip-style `dest` validation? atomicity across the multi-file write?

### C. The data-model bookend (HIGH)
- **N2 interview → requirements prose brief → `generate contract --promote`.** Is the prose-brief an
  intermediate artifact the human reviews, or ephemeral? Does `--promote` need its own confirm gate
  distinct from the prose-brief confirm (two-step ratification)? What happens on schema *revision* after
  manifests already derive from v1 (drift/regeneration)?

### D. Orchestration & state (MEDIUM)
- **N3 stage-state.** A `.startd8/` cursor over `build_assess`. Resumability, concurrency (two RCT
  sessions / the multi-worktree reality), staleness if the user hand-edits between stages.
- **Cascade-readiness threshold (OQ-7).** What gates the "run the cascade" offer — full surface vs a
  minimal viable subset? Make it testable.
- **Web surface shape (OQ-4).** New `/red-carpet` route vs a stage-rail extension of the existing
  `/concierge/chat` panel + `_ChatStore`. Reviewer's call on the lower-risk reuse.

### E. Cost / observability (MEDIUM)
- The agentic interview is the **one paid surface**; a from-scratch build is many turns. Does the
  inherited budget envelope (FR-WM2-9a: per-session turn/token/cost caps) suffice, or does RCT need a
  whole-build spend ceiling + resumable checkpoints so a long build can't blow budget in one session?

## Build-environment note (real, already in §0)
RCT must branch from **`origin/main`** — the proposal model + web chat live there, not on the primary
worktree. The repo runs concurrent multi-vendor agents; flag any plan step that risks parallel-work
collision.

## Out of scope for this review
- Re-litigating the inherited boundaries above.
- The polyglot LLM-driven path (NR-4) and the Prime/Artisan pipeline (NR-5).
- Authoring real bucket-4 content (NR-1).

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/kickoff/RED_CARPET_TREATMENT_PLAN.md`  ·  **Size:** 140 lines · 1399 words

```markdown
# Red Carpet Treatment — Implementation Plan

**Version:** 0.1 (Draft — pairs with `RED_CARPET_TREATMENT_REQUIREMENTS.md` v0.1)
**Date:** 2026-06-29
**Status:** Draft

> Planned against **`origin/main`** (not the primary worktree — see §0 build-env discovery). Maps each
> FR to real seams; discoveries that change the requirements are in §6 → fed to requirements §0 (v0.2).

---

## 0. Build-environment discovery (read first)

The planning Explore pass read the **primary worktree** (`feat/welcome-mat-2-download`), which is
**behind `origin/main`** — it has the download pillar but **not** PR #62's chat panel nor the 7
chat-hardening commits. It therefore mis-reported the **proposal model and the web chat as absent**.
Verified against `origin/main`: `kickoff_experience/proposals.py` (`ProposedAction`, `apply_proposal`),
the `propose_action` read-effect tool (`chat.py`), `/concierge/chat` + `_ChatStore` +
`new_agentic_kickoff_chat` (`web.py`/`cli_kickoff.py`) **all exist**. **RCT must be branched from
`origin/main`** — the primary worktree lacks the substrate RCT rides.

## 1. Architecture at a glance

RCT is a **conductor** over five existing subsystems, plus **three genuinely-new pieces**:

| RCT concern | Reuses (origin/main) | New |
|-------------|----------------------|-----|
| Agentic interview + propose-confirm | `AgenticSession` + `build_kickoff_registry` + `propose_action`→`ProposedAction`→`apply_proposal`; `/concierge/chat` panel + `_ChatStore` (web), `kickoff chat` (CLI) | a RCT **system prompt** + **stage driver**; extend proposal **kinds** |
| Data-model contract | `generate contract` (prose→prisma, `--promote`); `concierge/derive` (Pydantic→prisma) | **interview → requirements/PRD prose brief** step |
| Manifests + value inputs | `manifest_extraction` extractors + `extract_manifests`; `build_instantiate_plan` + templates; `capture.py` (per-key inputs merge) | **project-tree manifest writer** (the key gap) |
| Readiness → run | `build_assess`/`build_readiness`/`build_concierge_view`; `wireframe`; `generate backend/scaffold/views/frontend` | RCT **stage-state** + stage rail |
| Retrospective | the friction path | a reflection prompt per increment |

## 2. The genuinely-new pieces (where the real work is)

**N1 — Project-tree manifest writer (FR-RCT-6, the biggest gap).** `extract_manifests(docs)` returns
the manifests **in memory**, round-trip-gated; the only on-disk writer targets a *run-dir*
(`plan_ingestion_emitter`), **not** the project's `docs/kickoff/inputs/`. RCT needs an orchestration
that maps each `result.manifests[filename]` → its project destination and writes through the
**existing** `apply_write_plan` confinement seam (mirroring `build_instantiate_plan`). Pure plumbing
over existing extraction — but net-new.

**N2 — Interview → requirements/PRD prose brief (FR-RCT-4).** Neither producer does a *conversational*
interview→schema: `generate contract` consumes a **prose requirements doc**; `derive` reverse-derives
from **live Pydantic models**. So RCT's from-scratch path is: agent interviews → **drafts a requirements
prose brief** (a proposal) → human confirms → `generate contract` (prose→prisma) → `--promote`. (The
`derive` path is a *side door* for users who already have models.)

**N3 — RCT stage-state + stage rail (FR-RCT-2).** No persisted kickoff/RCT session state exists today
(readiness is recomputed from the filesystem each call). RCT's "current stage / next gap / resume"
needs a small `.startd8/` state record — though the **stage map itself is derived from `build_assess`**
(which already reports per-stage cascade readiness AND the 4 value domains), so state is a thin cursor,
not a second source of truth.

## 3. Reuse map (origin/main seams — verified)

- **Proposal/confirm:** `ProposedAction(kind, payload, id)` + `ProposalBuffer.pending()/pop()` +
  `apply_proposal(root, action, config)` (dispatches by `kind`; today `friction`/`instantiate`). The
  `propose_action` read-effect tool records proposals; the loop never writes; `/concierge/chat/confirm`
  applies at human privilege (`_concierge_write_gate`: mode+host+CSRF). **RCT extends the `kind`
  vocabulary** with `schema`/`manifest`/`value-input` + their apply paths (→ `generate contract
  --promote`, → N1 writer, → `capture.py` merge). *Medium.*
- **Schema producers:** `startd8 generate contract` (`cli_generate.py`), `concierge/derive`. *Small.*
- **Extractors:** `manifest_extraction/{extract,extractors}.py` — pure prose→dict, round-trip-gated. *None.*
- **Cascade + wireframe:** `startd8 generate backend/scaffold/views/frontend`, `startd8 wireframe` — all
  `$0`/no-LLM. *None.*
- **Readiness:** `build_assess` (cascade sections + 4 value domains), `build_readiness` (score),
  `build_concierge_view` (web/TUI payload + next_action). *None* (RCT consumes, never recomputes).
- **Value-input capture:** `capture.py` single-key merge-splice into `inputs/*.yaml` (allow-list gated)
  — `value-input` proposals must use THIS, not a whole-file write. *None.*
- **Web chat:** `/concierge/chat` + `_ChatStore` + `chat_factory` (web.py) + the chat hardening (cookie,
  budget, mode-gate, etc.). RCT's web surface = a **staged experience reusing the chat engine** + a
  stage rail, not a new chat. *Medium* (stage rail + a richer write-proposal registry, not a new chat).
- **CLI:** add `@kickoff_app.command("red-carpet")` mirroring `chat_cmd`'s agent resolution. *Trivial.*

## 4. Per-stage flow (the conductor)

For each stage in `build_assess`-derived order — **DATA MODEL → pages → views → forms → flows →
imports → app/scaffold → value inputs → placeholder content → readiness/run**:
1. RCT reads the gap (`build_assess`), picks the next unmet stage.
2. The agent interviews + **drafts a proposal** (`propose_action`, the right `kind`).
3. The human **confirms** (web CSRF/loopback/intent, or CLI confirm) → apply path runs (N1 / `generate
   contract --promote` / `capture`).
4. **Re-assess** (`build_assess`), show updated readiness, run the **per-increment reflection**
   (FR-RCT-12).
5. When the surface is complete → `wireframe` checkpoint → offer the `$0` cascade.

## 5. Sequencing

1. **N1 project-tree manifest writer** + extend proposal `kind`s (`manifest`, `value-input`) — unblocks every input stage.
2. **N2 interview→prose-brief→`generate contract`** + `schema` kind — the DATA MODEL bookend.
3. **N3 stage-state + the `build_assess`-driven stage driver** (the conductor) — CLI first (`kickoff red-carpet`).
4. Web stage rail over `/concierge/chat`; reflection step; telemetry; cascade handoff + `wireframe` checkpoint.

## 6. Planning discoveries (feed to requirements §0)

| Requirements assumed (v0.1) | Planning revealed (origin/main) | Impact |
|-----------------------------|----------------------------------|--------|
| The proposal model + web chat are reusable substrate | True on `origin/main`; the Explore pass on the primary worktree wrongly reported them absent → **RCT must branch from `origin/main`** | Add §0 build-env note; pin the base branch |
| `concierge/derive` does interview→schema (OQ-5) | `derive` is **Pydantic-models→prisma**; `generate contract` is **prose→prisma**. Neither is conversational. | **FR-RCT-4 reframed**: interview → requirements **prose brief** → `generate contract --promote`; `derive` is a side door (OQ-5 resolved) |
| Extractors + an existing writer materialize manifests into the project | Extractors are pure/in-memory; **no command writes prose→`docs/kickoff/inputs/*.yaml`** in the project tree (only a workflow → run-dir) | **New requirement/step N1** — the project-tree manifest writer is RCT's biggest genuinely-new piece |
| Proposal kinds extend cleanly (OQ-1) | Model EXISTS (`ProposedAction`/`apply_proposal`, kinds friction/instantiate) but kinds are **bespoke per-kind apply**, no registry | OQ-1 = **medium** extension (builders + dispatch branch per kind); still the riskiest |
| Readiness may only cover the 4 value inputs (FR-RCT-2 risk) | `build_assess` reports **both** per-stage cascade readiness AND the 4 domains | FR-RCT-2 confirmed feasible; **stage-state is a thin cursor** over `build_assess`, not a second readiness |
| RCT is "mostly orchestration" (P1) | Confirmed — 3 new pieces (N1 writer, N2 interview→brief, N3 stage-state); everything else is reuse | P1 holds; name the 3 new pieces explicitly |
| `value-input` writes ride the instantiate write | They must ride **`capture.py`** (per-key merge into `inputs/*.yaml`, allow-list gated), not a whole-file write | FR-RCT-9 must distinguish per-kind apply paths |

---

*Plan v0.1 — drafted against origin/main. 7 discoveries feed requirements §0 (v0.2). Headline: RCT is
genuinely an orchestration layer, but it must branch from `origin/main` and build three new pieces — the
project-tree manifest writer (N1), the interview→prose-brief→contract step (N2), and the
`build_assess`-driven stage driver/state (N3).*

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/kickoff/RED_CARPET_TREATMENT_REQUIREMENTS.md`  ·  **Size:** 297 lines · 2982 words

```markdown
# Red Carpet Treatment — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-29
**Status:** Draft
**Owner:** neil-the-nowledgeable
**Plan:** `RED_CARPET_TREATMENT_PLAN.md` (v0.1)
**Related (reuse, inherit boundaries — do not re-litigate):**
`WELCOME_MAT_2.0_REQUIREMENTS.md` (v0.4), `WELCOME_MAT_CONCIERGE_MODE_REQUIREMENTS.md` (v0.4),
`INTERACTIVE_KICKOFF_EXPERIENCE_REQUIREMENTS.md`, `KICKOFF_INPUT_PACKAGE_GUIDE.md`,
`KICKOFF_AUTHORING_CONTRACT.md`, `CONCIERGE_DERIVE_CONTRACT_REQUIREMENTS.md`; the **four-bucket
separation** + **two-generation-paths** framing in `CLAUDE.md`.

> **What the Red Carpet Treatment is.** The white-glove, **agentic, build-your-app-from-scratch**
> experience. An agent walks a greenfield user from *nothing* to a **complete kickoff input surface**,
> co-authoring every input the deterministic `$0` cascade needs, so `startd8 generate
> backend/scaffold/views/frontend` can run at **full capability**. RCT is an **orchestration layer
> above** Welcome Mat 2.0 + Concierge — it sequences the agent and the human through producing inputs;
> it does not re-implement the pieces beneath it, and it never authors the user's real content.

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2. The planning pass confronted the draft with the
> real code and surfaced one **build-environment** correction and several **scope** corrections. The
> headline holds — RCT is genuinely an orchestration layer — but it must **branch from `origin/main`**
> and build exactly **three** new pieces.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| The proposal model + web chat are reusable substrate | **True on `origin/main`** — `ProposedAction`/`apply_proposal`/`propose_action`, `/concierge/chat`+`_ChatStore`+`new_agentic_kickoff_chat` all exist. The planning Explore pass read the **primary worktree** (`feat/welcome-mat-2-download`), which is *behind* `origin/main` and lacks them, and wrongly reported them absent. | **RCT must branch from `origin/main`** (the primary worktree lacks the substrate). Recorded as a build-env prerequisite. |
| `concierge/derive` does interview→schema (OQ-5) | `derive` is **Pydantic-models → prisma**; `generate contract` is **prose (requirements doc) → prisma** (`--promote` = the human write). **Neither is conversational.** | **FR-RCT-4 reframed:** agent interviews → drafts a **requirements prose brief** → human confirms → `generate contract --promote`. `derive` is a side door for users with existing models. (OQ-5 resolved.) |
| Extractors + an existing writer materialize manifests into the project | `extract_manifests` is pure/in-memory + round-trip-gated; the **only** on-disk writer targets a *run-dir*. **No command writes prose→`docs/kickoff/inputs/*.yaml` in the project tree.** | **New piece N1** (FR-RCT-6 acceptance): a project-tree manifest writer over the existing `apply_write_plan` seam — RCT's biggest genuinely-new piece. |
| Proposal kinds extend cleanly (OQ-1) | Model exists but kinds are **bespoke per-kind apply** (no registry); today `friction`/`instantiate`. | OQ-1 = **medium** extension (a builder + dispatch branch + apply path per new kind); still the riskiest. `value-input` must ride `capture.py` (per-key merge), not a whole-file write. |
| Readiness might cover only the 4 value inputs (FR-RCT-2 risk) | `build_assess` reports **both** per-stage cascade readiness AND the 4 value domains. | FR-RCT-2 confirmed feasible; **RCT stage-state is a thin cursor** over `build_assess` (piece N3), not a second readiness computation. |
| `derive` writes the schema | `derive` **returns a candidate** (`unratified` header); the CLI is the sole writer. The `.prisma` human-privilege write is `generate contract --promote`. | FR-RCT-4/OQ-2 resolved: `.prisma` writes via `generate contract --promote`, distinct from the `inputs/` capture seam. |

**Resolved open questions:**
- **OQ-1 → the proposal model exists & is reusable** (origin/main); extending it to `schema`/`manifest`/
  `value-input` kinds is a **medium** per-kind addition (builders + dispatch + apply path). Still riskiest.
- **OQ-2 → two write seams:** `.prisma` via `generate contract --promote`; `inputs/*.yaml` via the
  `capture.py` per-key merge; both confined/atomic via the safe-writer.
- **OQ-5 → neither `derive` nor `generate contract` is conversational.** From-scratch path = interview →
  requirements prose brief → `generate contract --promote` (piece **N2**).
- **OQ-6 → stage-state is net-new but thin** — a `.startd8/` cursor over the `build_assess` stage map (N3).
- **OQ-3 → prose-authoring is the default front door** (round-trips via the authoring contract); direct-
  manifest only where an extractor doesn't exist. *(Still partly open per manifest — see §5.)*
- **OQ-4, OQ-7, OQ-8 → STILL OPEN** (web stage-rail shape; cascade-readiness threshold; interview spend).

---

## 1. Problem Statement

The deterministic cascade is the SDK's crown jewel — one `schema.prisma` + a handful of manifests
projects into a working all-Python app for `$0`. But **getting to a complete, correct input surface
from a blank start is the hard part**, and today it's a disconnected, expert-only assembly job:

| Capability | Today | Gap |
|-----------|-------|-----|
| **Data-model contract** (`schema.prisma`) | Hand-authored, or derived from a PRD via `concierge/derive` (a discrete action) | No guided, conversational path that *interviews* a non-expert and co-authors the schema from scratch |
| **Assembly manifests** (app/pages/views/forms/flows/imports) | Authored as prose sources that deterministically extract (`manifest_extraction`, authoring-contract §2.2–2.7) or hand-written YAML | No orchestration that walks a user through authoring *each* manifest in dependency order |
| **Value inputs** (conventions/build-prefs/business-targets/observability) | Instantiated as templates by Concierge `instantiate`; filled by hand or pre-filled (`estimate`/`config-default`) | Welcome Mat surfaces readiness + downloads + a chat that can *propose* friction/instantiate — but nothing drives the user to *fill the whole surface* |
| **Readiness → run** | `build_assess`/`build_readiness` report gaps; `startd8 wireframe` previews; the cascade runs when inputs exist | No experience that closes the loop: gap → co-author → confirm → re-assess → … → run |
| **Agentic assist** | `/concierge/chat` (Welcome Mat 2.0) proposes friction/instantiate via the read-effect `propose_action` → human-confirm model | The proposal model isn't yet a *build-the-whole-app* driver; `derive-contract` is explicitly **out of scope** there (WM2 NR-1) |

There is **no single experience that takes a user from "I have an idea" to "the cascade can build my
app."** The pieces exist (derive, extractors, the cascade, the propose-confirm seam, readiness,
download); nothing **sequences** them with an agent in the lead and the human in control.

**What should exist:** a staged, resumable, **agentic Red Carpet Treatment** — web (Welcome
Mat-hosted) and CLI, one engine — that (a) interviews the user and **co-authors the data-model
contract**, then (b) walks the **dependency-ordered** surface (manifests → value inputs → placeholder
content), the agent **drafting each input as a proposal** the human **confirms at human privilege**,
(c) continuously **re-assesses readiness** and (d) when the surface is complete, hands off to the **`$0`
cascade** — bracketed by the two human bookends (DATA MODEL up front, RETROSPECTIVE after each
increment).

---

## 2. Guiding Principles

- **P1 — Orchestrate, don't re-implement.** RCT is a *conductor*. The schema co-authoring rides
  `concierge/derive`; manifests ride the authoring-contract extractors (`manifest_extraction`); value
  inputs ride `build_instantiate_plan` + the input templates; writes ride the `propose_action` →
  `apply_proposal` proposal/confirm seam; readiness rides `build_assess`/`build_readiness`; the build
  rides the `$0` cascade. RCT adds **sequencing, interview prompts, and stage state** — no new
  extractor, generator, write engine, or readiness computation.
- **P2 — The loop proposes; the human applies (inherited, non-negotiable).** Every RCT write is a
  proposal the agent drafts and a foreground human confirms at human privilege (web same-origin POST +
  CSRF + loopback + one-time-intent; or CLI explicit confirm). The agentic loop **never** writes,
  never runs the cascade autonomously, and is never reachable as a write over MCP.
- **P3 — Honor the two human bookends.** The **DATA MODEL** is the front bookend — the contract
  everything derives from — so RCT *starts* there with deliberate human confirmation, never auto-deriving
  past it. The **RETROSPECTIVE** is the back bookend — after each increment RCT reflects and feeds
  lessons back (to the data model / requirements / the next stage).
- **P4 — Respect the four buckets.** RCT produces buckets **1–3** inputs (the application skeleton's
  contract + manifests = bucket 1's *inputs*; placeholder copy + static test data = bucket 2; the
  integration glue = bucket 3). It **never authors bucket 4** — the user's/company's real content. The
  cascade itself is bucket-1, `$0`, **Python-only** (the deterministic path); RCT targets that path.
- **P5 — Readiness-driven, resumable.** RCT is not a fixed wizard; it's a **gap-closing loop** keyed to
  the live readiness/assess state. It can be left and resumed; it always drives to the next real gap.

---

## 3. Requirements

### A. The experience & orchestration

- **FR-RCT-1 — A named, staged Red Carpet flow.** A single agentic experience that sequences a
  greenfield user through the **complete input surface** to cascade-readiness, present in **both** web
  (Welcome Mat-hosted) and CLI, over **one** shared agentic engine + the propose-confirm seam.
- **FR-RCT-2 — Readiness-driven stage map.** RCT derives its current stage and "next gap" from the
  existing `build_assess`/`build_readiness`/wireframe state (never a second readiness computation), so
  it is **resumable** and always advances the largest real gap. Stages (dependency-ordered): **DATA
  MODEL → manifests (pages/views/forms/flows/imports) → value inputs → placeholder content →
  readiness/run**.
- **FR-RCT-3 — Discoverable entry.** Web: a prominent "Build my app" entry (a `/red-carpet` route
  and/or a home-page CTA). CLI: `startd8 kickoff red-carpet`. Both bootstrap a from-scratch project
  (scaffold the kickoff package via `instantiate` if absent).

### B. Data model — the front human bookend

- **FR-RCT-4 — Interview-and-draft the data-model contract** *(reframed by planning)*. The agent
  conducts a **domain interview** and drafts a **requirements/PRD prose brief** (entities, fields, plain
  types, relationships in the authoring-contract §2.1 grammar) as a **proposal**; the human confirms;
  then `startd8 generate contract` (prose→prisma) produces `schema.prisma` and the human ratifies it
  with **`--promote`** (the sole `.prisma` write). *(Planning: neither `generate contract` nor
  `concierge/derive` is conversational — `derive` reverse-derives from existing Pydantic models, a
  **side door** for users who already have them.)* The agent originates the draft; the human owns the
  ratification. This is piece **N2**.
- **FR-RCT-5 — Data model gates the rest.** The schema is the **first** stage and a **gate**: manifests
  derive from it, so RCT will not drive manifest stages until a confirmed `schema.prisma` exists. This
  enforces "data model = the front bookend" rather than letting generation invent a contract.

### C. Manifests & value inputs — derive from the contract

- **FR-RCT-6 — Co-author each input via the authoring contract.** For every manifest
  (`pages`/`views`/`forms`/`flows`/`imports`, `app`/scaffold) and value input
  (`conventions`/`build-preferences`/`business-targets`/`observability`), the agent **drafts the
  authoring-contract prose source** as a proposal; the human confirms; the **existing extractor**
  (`manifest_extraction`) turns prose → manifest. RCT supplies the interview + the draft, not a new
  extractor.
  - **Acceptance (planning N1 — the project-tree manifest writer):** `extract_manifests` returns
    manifests **in memory** (round-trip-gated) and **no command writes them into the project's
    `docs/kickoff/inputs/*.yaml`** today (only a workflow → run-dir). RCT must add an orchestration that
    maps each extracted manifest → its project destination and writes it through the **existing**
    `apply_write_plan` confinement/atomic seam (mirroring `build_instantiate_plan`). This is RCT's
    biggest genuinely-new piece — pure plumbing over existing extraction, no new extractor.
- **FR-RCT-7 — Placeholder content only (bucket boundary).** RCT generates **placeholder/bucket-2**
  content prose and static test data sufficient to prove the app works, and then **explicitly hands
  off** real (bucket-4) content to the user/company. RCT never authors real value content.

### D. The write model — propose, then human-apply

- **FR-RCT-8 — Every write is propose-then-human-apply.** RCT reuses the `propose_action` (read-effect)
  → `apply_proposal` (human-privilege) proposal/confirm model: the agent drafts a proposal for each
  input; the human applies it (web same-origin+CSRF+loopback+one-time-intent, or CLI confirm). The loop
  never applies; MCP never writes.
- **FR-RCT-9 — Proposal kinds span the surface (per-kind apply paths).** Extend the existing
  `ProposedAction`/`apply_proposal` model (today `friction`/`instantiate`) with the RCT kinds, each
  routed to its **correct existing write seam** (planning: the kinds are bespoke per-kind apply, not a
  registry — so each is a builder + dispatch branch + apply path):
  - `schema` → `generate contract --promote` (the `.prisma` write),
  - `manifest` → the **N1 project-tree manifest writer** (FR-RCT-6),
  - `value-input` → **`capture.py`** (per-key merge-splice into `inputs/*.yaml`, allow-list gated) —
    **not** a whole-file write.
  Each proposal **re-validates on apply** (extractor/grammar/round-trip conformance), never trusting the
  loop's draft blindly; the human applies at human privilege.

### E. Readiness → cascade handoff

- **FR-RCT-10 — Live readiness + run handoff.** RCT surfaces the live readiness/wireframe throughout
  and, when the surface is complete, **offers to run the `$0` cascade** (`generate
  backend`/`scaffold`/`views`/`frontend`). RCT **orchestrates the inputs**; the cascade is the separate
  deterministic `$0` step. RCT never claims to *generate content* (bucket-4) and never makes the build a
  loop-autonomous action.
- **FR-RCT-11 — Wireframe checkpoint.** Before offering the cascade, RCT shows the `startd8 wireframe`
  `$0` pre-generation summary ("here's the app we'll build") as the human go/no-go checkpoint.

### F. Retrospective — the back human bookend

- **FR-RCT-12 — Per-increment reflection.** After each confirmed stage/increment, RCT runs a short
  **reflection** — what was decided, what's still ambiguous, what should feed back to the data model or
  earlier inputs — and offers to log friction (reusing the existing friction path). This operationalizes
  the RETROSPECTIVE bookend; it is advisory, never a gate.

### G. Boundaries & cross-cutting

- **FR-RCT-13 — Cost posture.** The agentic interview is the **one paid surface** (LLM); extraction, the
  cascade, readiness, and wireframe are `$0`. RCT inherits the chat hardening from Welcome Mat 2.0
  (per-session budget caps, turn cap, message cap, graceful degradation, mode gate) — a `preview`/
  `inspect` serve disables the paid interview.
- **FR-RCT-14 — Observability.** RCT emits stage-funnel events (`red_carpet_started`, `stage_entered`,
  `input_proposed`, `input_confirmed`, `stage_completed`, `cascade_offered`) with bounded attributes
  (stage/kind/code, **no** interview text, no raw paths) — registered in the kickoff telemetry module.
- **FR-RCT-15 — Parity by shared construction.** Web and CLI run the **same** RCT engine, stage map, and
  propose-confirm seam; surface differences are limited to the authorization gate (web CSRF/loopback vs
  CLI confirm), as in Welcome Mat 2.0.

---

## 4. Non-Requirements

- **NR-1 — No real (bucket-4) content authoring.** RCT produces placeholder content + static test data
  only; the user's/company's real value content is theirs.
- **NR-2 — No re-implementation.** RCT does not re-implement `concierge/derive`, the
  `manifest_extraction` extractors, the `$0` cascade, the proposal/confirm write engine, readiness, or
  the template instantiate — it sequences them.
- **NR-3 — No autonomous / loop writes; no MCP writes.** The agentic loop never applies a write or runs
  the cascade; MCP stays preview/read-only.
- **NR-4 — Not polyglot.** RCT targets the **deterministic, Python-only** generation path. The
  LLM-driven polyglot path (Prime/MicroPrime microservice fleets) is out of scope.
- **NR-5 — Not a benchmark / not Prime.** RCT is an onboarding/build experience, not the Prime/Artisan
  construction pipeline or the model benchmark.

---

## 5. Open Questions

*5 of 8 resolved by the planning pass — see §0 for rationale. Retained for the record.*

- **OQ-1 — RESOLVED → the proposal model exists & is reusable** (`origin/main`); extending to
  `schema`/`manifest`/`value-input` kinds is a **medium** per-kind addition (builder + dispatch + apply
  path). Still the riskiest piece.
- **OQ-2 — RESOLVED → two confined write seams:** `.prisma` via `generate contract --promote`;
  `inputs/*.yaml` via the `capture.py` per-key merge. Both atomic/confined through the safe-writer.
- **OQ-5 — RESOLVED → neither producer is conversational.** From-scratch path = interview →
  requirements prose brief → `generate contract --promote` (piece N2); `derive` (Pydantic→prisma) is a
  side door.
- **OQ-6 — RESOLVED → stage-state is net-new but thin** — a `.startd8/` cursor over the `build_assess`
  stage map (piece N3), not a second readiness computation.
- **OQ-3 — PARTLY RESOLVED → prose-authoring is the default** front door (round-trips via the authoring
  contract); direct-manifest only where no extractor exists. Per-manifest specifics still open.
- **OQ-4 — STILL OPEN.** Web surface: a new `/red-carpet` staged route vs a stage-rail extension of the
  existing `/concierge/chat` panel + `_ChatStore`. (The chat engine is reusable either way.)
- **OQ-7 — STILL OPEN.** Cascade-readiness threshold for the run offer — full surface vs a minimal
  viable subset (schema + app + ≥1 page/view).
- **OQ-8 — STILL OPEN.** Interview turn/spend scale for a realistic from-scratch build, and whether the
  inherited budget envelope (FR-WM2-9a) needs RCT-specific tuning.

---

*v0.2 — Post-planning self-reflective update. P1 ("orchestrate, don't re-implement") **confirmed** —
RCT builds exactly **three** new pieces (N1 project-tree manifest writer, N2 interview→prose-brief→
`generate contract`, N3 `build_assess`-driven stage-state/driver); everything else rides existing
seams. Corrections: FR-RCT-4 reframed (no conversational schema producer exists → interview→prose-brief
path); FR-RCT-6 gained the N1 writer (the real gap); FR-RCT-9 split into per-kind apply paths
(schema→`generate contract --promote`, manifest→N1, value-input→`capture.py`). 1 build-env prerequisite
surfaced (**RCT must branch from `origin/main`**, which the planning Explore pass — reading the stale
primary worktree — initially missed). 5 of 8 open questions resolved. Ready for CRP review before
implementation.*

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
