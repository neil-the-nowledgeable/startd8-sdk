# Convergent Review Prompt

**Generated:** 2026-06-21 19:23:57 UTC
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
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/cicd/CICD_PLAN.md` | 126 lines · 1345 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/cicd/CICD_REQUIREMENTS.md` | 334 lines · 3301 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/cicd/CRP_FOCUS_R1.md` | 47 lines · 454 words |

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

# CRP Focus — CI/CD Capability R1

Where reviewer input is needed most. Weight these over generic completeness checks.

## 1. Layer B credentialed provisioning (highest risk)
The `ci_provision` layer performs side effects against a real vendor (GitHub in v1): repo creation,
`git` push, secret registration, branch-protection rules. Pressure-test:
- **Auth-scope minimization** — what is the *minimum* token scope per operation? Is a single broad PAT
  assumed where fine-grained/OIDC would do?
- **Blast radius** — what is the worst outcome of a misfired provision (wrong repo, overwritten
  protection rules, leaked secret name collision)?
- **Partial-failure recovery** — repo created but secret-register fails midway: what state is the user
  left in, and is re-run safe (FR-PROV-3 idempotency claims this — does the plan actually deliver it)?
- **Token handling** — FR-PROV-4 says tokens never logged/disked/hydrated. Is that enforceable given
  the `secrets.get_secret` path, or just asserted?
- **Dry-run integrity** — is `--dry-run` (FR-PROV-2, the default) genuinely side-effect-free, or could
  a "preview" call mutate (e.g. an auth probe that creates state)?

## 2. Supply-chain posture of GENERATED pipelines
The emitted YAML is itself an attack surface. Validate:
- **SHA-pinning (FR-SUP-1)** — is pinning by commit SHA actually achievable for all referenced
  actions, and how are pins kept current without re-introducing floating tags?
- **OIDC vs stored creds (FR-SUP-2)** — is keyless auth viable across the registry choices, or does the
  fallback to long-lived creds undermine the posture?
- **SBOM/scan (FR-SUP-3, optional)** — is "optional, default off" the right call, or should a minimum
  scan be on-by-default for `deployed`?

## 3. Layer-A / Layer-B trust-boundary integrity
The invariant: Layer B consumes Layer A output and never authors pipeline content; it refuses on drift
(FR-PROV-5). Challenge:
- Is the drift-gate actually enforceable before side effects, or can provisioning race ahead of a stale
  generate?
- Is there any code path where Layer B could synthesize/patch YAML directly, breaking the boundary?

## 4. Secret-name handling after backend-enumeration was ruled out (D4)
FR-SEC-1 now derives names from the `cicd.secrets` manifest + the `.env.example` convention, deny-list
filtered. Validate this is complete and safe:
- Does the convention set cover the real secret surface, or will operators silently miss a required
  secret (pipeline references a name nothing provides)?
- Is the deny-list filter the right gate, or does it risk dropping a legitimately-needed name?

## 5. Per-vendor renderer/drift robustness (OQ-3)
The drift check re-renders and byte-compares emitted YAML. Stress:
- Vendor-side normalization/reformatting of committed YAML (or a UI edit) would flip drift to "1" —
  is owning files operators shouldn't hand-edit a sufficient mitigation, or does this generate false drift?
- Does flattening the vendor into the artifact-kind string (FR-GEN-4, D2) hold across all 5 vendors, or
  do CircleCI/Azure force a structural concession?

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/cicd/CICD_PLAN.md`  ·  **Size:** 126 lines · 1345 words

```markdown
# CI/CD Capability — Implementation Plan

**Version:** 1.0 (Post-planning pass)
**Date:** 2026-06-21
**Status:** Draft
**Tracks:** `CICD_REQUIREMENTS.md` v0.2

---

## 1. Planning Discoveries (D1–D10)

The planning pass traced every requirement to real source. The two-layer architecture, the
provider/drift/renderer clone, CLI gate invocation, and manifest extensibility all hold. **Five
requirements were misframed or infeasible as written** — captured here and folded into requirements §0.

| # | v0.1 assumption | Code reality (file:line) | Impact |
|---|---|---|---|
| **D1** | `ci_codegen` clones `ScaffoldFileProvider` 1:1 | Cloneable (`provider.py:18-52`), but the ownership marker `_MARKER="# GENERATED from app.yaml"` + `_KIND_RE`/`_MSHA_RE` are scaffold-private (`drift.py:16-18`). Reusing `is_owned_scaffold_file` would make scaffold claim CI files. | Need a **separate** `ci_codegen/drift.py` with marker `# GENERATED from app.yaml (cicd)`. Hashing (`schema_sha256`) is shareable. FR-GEN-2/3. |
| **D2** | Renderer map keyed by `(vendor, kind)` tuple | Drift re-render only threads `manifest_text` (`drift.py:51`); it dispatches by **kind**. Vendor must be **baked into the kind string** (e.g. `cicd-github-validate`) so drift can recover the renderer. | FR-GEN-4 **reframed**: emit-time map may be a tuple, but the on-disk artifact-kind must flatten vendor in. |
| **D3** | CI/CD coherence rows add without restructuring | `evaluate_coherence(manifest, *, has_auth_seam, has_tenant)` (`coherence.py:47-95`) takes only `AppManifest`+2 bools. CI facts (`registry`, `build.enabled`, secrets backend) aren't on `AppManifest`. | FR-COH-1 needs a **signature extension** (new `cicd` kwarg) + new `AppManifest` fields. Wiring point exists (`cli_generate.py:346-376`). |
| **D4** | `secrets/` backend enumerates key **names** for Layer A | **No name-only API.** Protocol exposes `get_all_secrets()→{name:value}` and `get_secret(key)→value` (`protocol.py:63-77`); `local` returns `{}` (`local.py:24-26`). Harvesting names would return empty (local) or **fetch real values into memory** (Doppler) — violating FR-SEC-4. Deny-list `is_dangerous_key()` IS importable (`__init__.py:46`). | **FR-SEC-1 INFEASIBLE as written.** Names must come from the `cicd.secrets` manifest block + the `.env.example` convention (`ANTHROPIC_API_KEY`/`DATABASE_URL`/`DOPPLER_TOKEN`, `renderers.py:264-283`), deny-list-filtered. |
| **D5** | CD smoke boots the deployed artifact via the harness | Harness **boots installed-mode only**: `mode != installed` ⇒ `Stage.BOOT = SKIPPED` `skipped:deployed-needs-db` (`deploy.py:133-141`). No Postgres/`DATABASE_URL` boot path. | **FR-CD-1/2 BLOCKED for deployed apps.** M3 smoke scoped to **installed** apps; deployed smoke = documented skip + harness-prerequisite tracked separately. |
| **D6** | `cicd.registry` reuses `container.*`; Dockerfile is mode-aware | `container.*` = only `dockerfile: bool` (`manifest.py:177`). **No registry concept anywhere** (zero grep hits). Dockerfile **always binds `0.0.0.0`** (`renderers.py:119`); only the comment + `run.sh` are mode-derived. | FR-BLD-1/2 **reframed**: `cicd.registry` is **net-new** (no reuse); "mode-aware Dockerfile" → "optionally-emitted Dockerfile gated by `container.dockerfile`." |
| **D7** | CI runs `pip install startd8 && startd8 …`; coherence is a step | `startd8` IS a console_script (`pyproject.toml:113-114`, v0.4.0, py≥3.9). Gates are real subcommands. **Coherence has NO standalone CLI** — it runs inside `generate backend` (`cli_generate.py:349`). | FR-CI-1 confirmed; **coherence must ride inside `generate cicd`**, no `startd8 coherence` exists. Resolves OQ-1. |
| **D8** | New `generate cicd` / `cicd provision` follow existing registration | Confirmed. `app.add_typer(generate_app, name=…)` (`cli.py:992`); `generate cicd` = `@generate_app.command` sibling of `scaffold` (`cli_generate.py:537`); `cicd provision` = new `cicd_app` Typer + callback (`cli.py:1009` pattern). | FR-GEN-5/FR-PROV-1 confirmed, mechanical. |
| **D9** | A deployment-mode wireframe section exists to mirror | No standalone section; mode is folded into `_scaffold_section` (`plan.py:354-402`). Sections are a fixed tuple (`plan.py:1029-1034`). | FR-COH-3 feasible: add `_cicd_section` + append to tuple + `_ITERATION_BY_SECTION` (`render.py:189`). |
| **D10** | Adding top-level `cicd:` to `app.yaml` is trivial | Parser is **strict/fail-loud**: `_TOP_KEYS` closed set, unknown key ⇒ `raise ValueError` (`manifest.py:16-19,77-79`). An unregistered `cicd:` **breaks every existing `generate` run**. | FR-GEN-1 ordering-critical: add `"cicd"` to `_TOP_KEYS` + strict sub-parse in **M0**, before any manifest carries it. |

---

## 2. Milestones

> Decision: extend the existing `scaffold_codegen` `AppManifest`/parser (not a separate parser),
> because coherence and renderers all consume `AppManifest`. New module `src/startd8/ci_codegen/`.

### M0 — manifest + provider skeleton + VCS hygiene (FR-GEN-1..3, FR-VCS-*)
- **Modify** `scaffold_codegen/manifest.py`: add `"cicd"` to `_TOP_KEYS`; strict `cicd` sub-parse (mirror `deployment` `:98-101`) → `cicd_vendors`, `cicd_registry`, `cicd_environments`, `cicd_build_enabled`, `cicd_secrets`, `cicd_codeowners` on `AppManifest`.
- **Create** `ci_codegen/drift.py`: own `_MARKER="# GENERATED from app.yaml (cicd)"`, `is_owned_cicd_file()`, `cicd_in_sync()`; reuse `schema_sha256`; dispatch `CICD_RENDERERS` by flat vendor-embedded kind (D2).
- **Create** `ci_codegen/provider.py`: `CiCdFileProvider` (`name="cicd"`).
- **Create** `ci_codegen/renderers.py`: `render_gitignore`, `render_gitattributes`, `render_codeowners`, `render_pr_template`; `CICD_RENDERERS`.
- **Create** `ci_codegen/__init__.py`.
- **Modify** `pyproject.toml`: register `cicd = "startd8.ci_codegen.provider:CiCdFileProvider"` under `startd8.contractors.deterministic_providers`.
- **Modify** `cli_generate.py`: `@generate_app.command("cicd")` with `--check` (clone scaffold `:537-602`).

### M1 — GitHub validate job + coherence (FR-CI-*, FR-COH-1/2)
- **Modify** `ci_codegen/renderers.py`: `render_github_validate` → `.github/workflows/validate.yml` running `startd8 generate backend --check`, `generate cicd --check`, `pytest`, `ruff`, `mypy`, `polish check`; `m.python_version`; push+PR triggers.
- **Modify** `scaffold_codegen/coherence.py`: extend `evaluate_coherence` with a `cicd` kwarg; rows — push+`installed`⇒ERROR, `deployed`+build+no-Dockerfile⇒ERROR, `deployed`+push+local-secrets⇒ERROR, CI+no-migrations+`deployed`⇒WARN.
- **Modify** `cli_generate.py`: `generate cicd` calls coherence + fails on ERROR (mirror `:346-376`).

### M2 — build/push + named secrets + supply-chain (FR-BLD-*, FR-SEC-*, FR-SUP-1/2)
- **Modify** `ci_codegen/renderers.py`: `render_github_build` (gated on `m.dockerfile`); SHA-pinned actions; OIDC; **secret refs by name only**, names from `m.cicd_secrets` + `.env.example` convention, filtered via `secrets.is_dangerous_key` (D4). Net-new `cicd.registry` handling (D6).
- **Modify** `scaffold_codegen/coherence.py`: registry/secrets-backend rows.

### M3 — CD smoke (FR-CD-*) — GATED (D5)
- **Modify** `ci_codegen/renderers.py`: `render_github_smoke` → `startd8 deploy local --json`, gate on `LadderResult`.
- **Scope**: smoke for **installed** apps only; `deployed` ⇒ documented skip (harness can't boot Postgres). Deployed smoke = **prerequisite** (new harness deployed-boot in `deploy_harness/deploy.py:133-141`), tracked outside this feature.

### M4 — remaining vendors (FR-GEN-4/6)
- **Modify** `ci_codegen/renderers.py`: gitlab/circleci/azure/bitbucket renderers under vendor-embedded kinds in `CICD_RENDERERS`. No core change (validates D2).

### M5 — Layer B provisioning (FR-PROV-*) — GitHub first
- **Create** `cli_cicd.py`: `cicd_app` Typer + callback; `provision` command, **`--dry-run` default**, idempotent; tokens via `secrets.get_secret`; **refuses on `generate cicd --check` drift** (FR-PROV-5).
- **Create** `ci_provision/github.py`: REST + GHCR side effects (repo create, push, secret register, branch protection).
- **Modify** `cli.py`: `app.add_typer(cicd_app, name="cicd")`.

### Cross-cutting — wireframe (FR-COH-3, after M1)
- **Modify** `wireframe/plan.py`: `_cicd_section(state)` (clone `_scaffold_section`) appended to the section tuple (`:1029-1034`).
- **Modify** `wireframe/render.py`: add `"cicd"` to `_ITERATION_BY_SECTION` (`:189`).

---

## 3. Traceability (FR → milestone)

| Milestone | Requirements |
|---|---|
| M0 | FR-GEN-1, FR-GEN-2, FR-GEN-3, FR-GEN-5, FR-VCS-1..4 |
| M1 | FR-GEN-6, FR-CI-1..4, FR-COH-1, FR-COH-2 |
| M2 | FR-BLD-1..4, FR-SEC-1..4, FR-SUP-1, FR-SUP-2 |
| M3 | FR-CD-1..3 (installed-scoped) |
| M4 | FR-GEN-4, remaining FR-GEN-6 vendors |
| M5 | FR-PROV-1..6 |
| Cross | FR-COH-3, FR-SUP-3/4 (optional) |

---

## 4. Critical Files
- `src/startd8/scaffold_codegen/manifest.py` — `_TOP_KEYS` strict gate + `AppManifest` fields (M0, D10)
- `src/startd8/scaffold_codegen/coherence.py` — matrix + signature extension (M1, D3)
- `src/startd8/scaffold_codegen/drift.py` — template for `ci_codegen/drift.py` (D1)
- `src/startd8/cli_generate.py` — `generate cicd` registration + coherence wiring (M0/M1, D7/D8)
- `src/startd8/deploy_harness/deploy.py:133-141` — installed-only boot (M3 blocker, D5)
- `src/startd8/secrets/{protocol.py,manager.py,__init__.py}` — no name-enum; deny-list (D4)
- `src/startd8/wireframe/plan.py`, `render.py` — wireframe section (D9)
- `pyproject.toml` — entry-point + console_script (D7)

---

*Plan v1.0 — paired with requirements v0.2.*

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/cicd/CICD_REQUIREMENTS.md`  ·  **Size:** 334 lines · 3301 words

```markdown
# CI/CD as a Deployment Configuration Option — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-21
**Status:** Draft
**Owner:** StartD8 SDK — new `ci_codegen` (bucket-1, $0 deterministic) + `ci_provision` (operational tooling)
**Pilot surface:** Apps generated by `startd8 generate backend` / `scaffold`, already carrying a `deployment.mode`
**Extends:** `docs/design/deployment-mode/` (installed vs deployed), `docs/design/local-deploy-harness/`
**Plan:** `CICD_PLAN.md` v1.0 (discoveries D1–D10)

---

## 0. Planning Insights (Self-Reflective Update)

> This section records what changed between v0.1 (pre-planning) and v0.2. The planning pass
> (`CICD_PLAN.md` §1, discoveries D1–D10) mapped every requirement to real files and reclassified
> five of them. The central lesson: **the generation skeleton clones cleanly, but three "just read
> existing infra" assumptions were false** — the secrets backend can't enumerate names, the deploy
> harness can't boot deployed apps, and there is no registry concept anywhere in the SDK.

| v0.1 assumption | Planning discovery | Impact |
|---|---|---|
| Layer A maps secret **names** by reading the `secrets/` backend (FR-SEC-1, OQ-6) | **No name-only API.** Backend exposes name→**value** only; `local` returns `{}`; harvesting names would fetch real values into memory (Doppler) — violating FR-SEC-4. (D4) | **FR-SEC-1 reframed**: names come from the `cicd.secrets` manifest block + the `.env.example` convention, deny-list-filtered via `is_dangerous_key()`. Never from backend enumeration. |
| CD smoke boots the **deployed** artifact via the harness (FR-CD-1/2, OQ-8) | Harness **boots installed-mode only**; `deployed` ⇒ `BOOT=SKIPPED` (`deploy.py:133-141`). No Postgres path. (D5) | **FR-CD scoped to installed apps.** Deployed smoke deferred behind a harness-prerequisite (new deployed-boot), tracked outside this feature. |
| `cicd.registry` reuses `container.*`; the Dockerfile is mode-aware (FR-BLD, OQ-4) | `container.*` = only `dockerfile: bool`; **no registry concept exists**; Dockerfile always binds `0.0.0.0` (only comment + `run.sh` are mode-derived). (D6) | **FR-BLD reframed**: `cicd.registry` is net-new; "mode-aware Dockerfile" → "optionally-emitted Dockerfile gated by `container.dockerfile`." |
| Renderer map keyed by `(vendor, kind)` tuple (FR-GEN-4) | Drift re-render threads only `manifest_text`, dispatches by **kind** (`drift.py:51`). (D2) | **FR-GEN-4 reframed**: the on-disk artifact-kind must **flatten the vendor in** (e.g. `cicd-github-validate`) so drift can recover the renderer. |
| Coherence has a standalone step; CI just calls SDK gates (FR-CI-1, OQ-1) | `startd8` IS a console_script (pip-installable), but **coherence has no standalone CLI** — it runs inside `generate backend`. (D7) | **FR-CI-1 reframed**: coherence rides inside `generate cicd`; CI does `pip install startd8 && startd8 generate … --check`. |

**Resolved open questions:**
- **OQ-1 → Installed `startd8` console_script.** CI runs `pip install startd8==0.4.0 && startd8 generate backend --check` etc. Gates are real Typer subcommands; coherence rides inside `generate cicd` (no standalone `startd8 coherence`). (D7)
- **OQ-4 → `cicd.registry` is net-new.** No `container.*` registry concept to reuse; the container block is `dockerfile: bool` only. (D6)
- **OQ-6 → Names from manifest + convention, not the backend.** The `secrets/` backend cannot enumerate names without fetching values; Layer A derives the named-reference set from `cicd.secrets` + the `.env.example` convention, deny-list-filtered. (D4)
- **OQ-8 → Harness is installed-only.** Deployed-mode CD smoke is blocked on a harness prerequisite; v1 CD smoke targets installed apps. (D5)
- **OQ-9 → Layer B stays a separate module.** Provisioning is in-scope (user decision) but lives in `ci_provision/` + `cli_cicd.py`, structurally apart from the deterministic `ci_codegen/` core, preserving the $0 generation surface.

- **OQ-7 → Mode-derived default.** `cicd.environments` defaults to a single env for `installed`,
  `[dev,staging,prod]` for `deployed` (FR-SEC-2). Avoids over-provisioning installed apps.

**v1 scope decisions (locked):** CD smoke is **installed-scoped** (deployed smoke deferred behind the
harness prerequisite, FR-CD-4); Layer B **provisions GitHub only**, other 4 vendors generate-only
(FR-PROV-6).

**Still open (carried):** OQ-2 (cross-vendor shareability — resolves at M4), OQ-3 (drift robustness vs vendor YAML normalization), OQ-5 (min credential scope / OIDC per vendor — M5).

---

## 1. Problem Statement

A StartD8-generated app today can declare a **deployment mode** (installed vs deployed) and be run
locally through the **deploy harness** (`startd8 deploy local/batch` → discover→install→boot→health→smoke).
What it *cannot* do is describe or stand up the **path from a source repository to a verified build**:
there is no source-control hygiene, no CI pipeline definition, no container build/push, no
named-secret/environment wiring, and no supply-chain posture in anything the SDK emits. An operator
who wants a deployed app must hand-write `.github/workflows/*.yml` (or the equivalent for whatever
vendor they use), re-deriving — by hand and inconsistently — the exact quality gates the SDK already
owns deterministically (`generate backend --check` drift, `coherence.py`, the generated pytest suite,
`ruff`/`mypy`, `polish check`).

That hand-wiring defeats the determinism thesis twice over: (a) the CI definition is **structural
plumbing derived from the app manifest** — it is bucket-1 generable, not human content; and (b) the
gates it runs **already exist in the SDK** and should be wrapped, not re-implemented in YAML by each
operator. The goal is **turn-key**: declaring CI/CD in `app.yaml` should emit a working, vendor-native
pipeline that runs the SDK's own gates, builds the already-emitted Dockerfile, and smoke-tests via the
existing deploy harness — and, optionally, **provision** the repo and pipeline against a real vendor.

This capability is explicitly framed as **a deployment configuration option**: it is the
repo→build→verify complement to the deployment-mode work, gated by the same `deployment.mode` and
governed by an extension of the same coherence matrix.

### Current-state gap table

| Concern | What exists today | Gap |
|---|---|---|
| **Source-control hygiene** | none emitted (no `.gitignore`, `.gitattributes`, CODEOWNERS) | App ships with no VCS scaffolding |
| **CI definition** | none | No pipeline file for any vendor |
| **Reuse of SDK gates** | gates exist (`--check` drift, coherence, pytest, ruff/mypy, polish) but only runnable by hand | No CI job wraps them |
| **Container build/push** | mode-aware `Dockerfile` is emitted by `scaffold_codegen` | Nothing builds or pushes it |
| **CD verify** | `deploy_harness` boot→health→smoke runs locally | Not invoked as a pipeline stage |
| **Secrets in CI** | `secrets/` backend (local + Doppler, deny-list) | No mapping to vendor secret stores; no named-ref convention |
| **Environments** | `deployment.mode` (installed/deployed) | No dev/staging/prod environment model |
| **Supply chain** | none | No SHA-pinned actions, OIDC, SBOM, or dependency scanning posture |
| **Repo/pipeline provisioning** | none | No way to actually create the repo, push, or register secrets/pipeline |

---

## 2. Goals & Non-Goals

**Goal:** Make CI/CD a declared, deterministic-where-it-can-be property of a generated app: a new
`cicd:` block in `app.yaml` drives (Layer A) **$0 deterministic generation** of vendor-native
source-control + pipeline artifacts that wrap the SDK's existing gates, and (Layer B) an **opt-in,
credentialed provisioning** path that stands those artifacts up against a real vendor.

**Non-goals (v1):**
- **No deploy-to-target.** CD stops at build + push + smoke. No emission of Fly/Render/Cloud Run/ECS/K8s
  deploy steps or infra-as-code. (Deferred; see §6.)
- **No universal CI IR.** We emit native per-vendor YAML via a renderer map, not an abstract pipeline
  language that compiles to all vendors.
- **No secret values, ever.** Emitted pipelines reference vendor secret stores **by name only**.
- **No authoring of pipeline *policy* content** (which approvers, which environments gate prod, branch
  rules) beyond safe defaults — that is operator content (bucket 4). The SDK generates the mechanism.
- **No provisioning of all 5 vendors at once.** Generation covers all 5; provisioning lands
  vendor-by-vendor, GitHub first.

---

## 3. Architecture — Two Layers (the load-bearing distinction)

> The single most important design constraint. Generation is deterministic and side-effect-free;
> provisioning is credentialed and partially irreversible. They must not be the same code path.

| | **Layer A — `ci_codegen` (generate)** | **Layer B — `ci_provision` (execute/provision)** |
|---|---|---|
| Cost | $0, no LLM (bucket 1) | n/a (operational tooling) |
| Effect | pure file emission | side-effecting: `git init`+push, repo create, secret register |
| Trust | none required | credentialed; explicit confirmation + `--dry-run` first |
| Determinism | byte-identical, drift-checked, skip-hook-owned | idempotent (safe re-run), not byte-deterministic |
| Registration | `startd8.contractors.deterministic_providers` entry point (like `scaffold`) | a CLI subcommand family, not a codegen provider |
| Source of truth | `cicd:` block in `app.yaml` + `deployment.mode` | Layer A's **emitted files** (consumes, never bypasses) |
| Vendors | all 5 (renderer map) | GitHub first, then others incrementally |

**Invariant:** Layer B never synthesizes pipeline content itself — it reads what Layer A wrote and acts
on it. A provision run against artifacts that fail Layer A's drift check must refuse (or re-generate
first).

---

## 4. Requirements

### 4.1 Generation core (Layer A) — FR-GEN-*

- **FR-GEN-1** — A new `cicd:` block in `app.yaml` declares the CI/CD surface. Absent block ⇒ nothing
  emitted (byte-identical-when-absent, per the SOTTO principle).
- **FR-GEN-2** — A new `ci_codegen` module registers a `DeterministicFileProvider` (e.g. `cicd`) under
  the `startd8.contractors.deterministic_providers` entry-point group, following the `ScaffoldFileProvider`
  pattern (header marker + `manifest-sha256`, `owns()` cheap check, `is_in_sync()` full re-render).
- **FR-GEN-3** — Emitted CI/CD files self-describe their source and hash (e.g. `# GENERATED from
  app.yaml (cicd)` + `manifest-sha256:`), so the skip-hook recognizes them as $0-owned and `--check`
  detects drift.
- **FR-GEN-4** — A renderer map (`CICD_RENDERERS`, analogous to `SCAFFOLD_RENDERERS`) maps
  artifact-kind → renderer function. **The vendor is flattened into the artifact-kind string** (e.g.
  `cicd-github-validate`) so the drift re-render path — which threads only `manifest_text` and
  dispatches by kind — can recover the correct renderer (D2). Adding a vendor = adding renderers, no
  core change.
- **FR-GEN-5** — A CLI surface emits the artifacts: `startd8 generate cicd` (+ `--check` drift mode,
  exit 0=in-sync / 1=drift / 2=error), consistent with `generate backend --check` and `polish check`.
- **FR-GEN-6** — Generation is vendor-parameterized: `cicd.vendors: [github, gitlab, circleci, azure,
  bitbucket]` selects which native pipeline files to emit. Default = `[github]`.

### 4.2 Source-control hygiene — FR-VCS-*

- **FR-VCS-1** — Emit a `.gitignore` appropriate to the generated all-Python app (venv, `.startd8/`,
  `__pycache__`, local `*.db`, `.env`, build artifacts).
- **FR-VCS-2** — Emit `.gitattributes` (normalize line endings, mark generated files where useful).
- **FR-VCS-3** — Emit `CODEOWNERS` from a declared `cicd.codeowners` list (default: empty/commented stub).
- **FR-VCS-4** — Emit branch/PR convention docs or config (e.g. PR template) where the vendor supports
  it as a file. Branch-protection *rules* that are API-only belong to Layer B (FR-PROV-*).

### 4.3 CI validate job — FR-CI-*

- **FR-CI-1** — Emit a CI pipeline whose validate job runs the SDK's existing gates via the
  pip-installable `startd8` console_script (D7): `generate backend --check` (drift), the generated
  pytest suite, `ruff`, `mypy`, `polish check`. **Coherence has no standalone CLI** — it is invoked by
  running `generate cicd --check` (which evaluates the extended coherence matrix), not a separate step.
- **FR-CI-2** — The validate job triggers on push and pull-request to the default branch by default;
  triggers are overridable via `cicd.triggers`.
- **FR-CI-3** — The validate job uses the app's declared Python version (`app.python_version`) and
  installs from the emitted dependency files (`requirements*.txt` / `pyproject.toml`).
- **FR-CI-4** — A drift failure (`--check` exit 1) fails CI — hand-edits to $0-owned files are caught
  at PR time.

### 4.4 Container build & push — FR-BLD-*

- **FR-BLD-1** — When `container.dockerfile` is enabled (scaffold optionally emits the Dockerfile;
  note its bind is always `0.0.0.0`, not mode-derived — D6), emit a build job that builds that exact
  Dockerfile.
- **FR-BLD-2** — Emit a push job to a declared registry. **`cicd.registry` is a net-new manifest field**
  (no `container.*` registry concept exists to reuse — D6); supports GHCR / GitLab registry / generic
  OCI. Registry credentials are referenced by name only (FR-SEC-*).
- **FR-BLD-3** — Image build/push runs only when coherence permits (e.g. push-to-prod-registry requires
  `mode: deployed`; see FR-COH-*).
- **FR-BLD-4** — Build/push is opt-in via `cicd.build.enabled`; default off when no Dockerfile exists.

### 4.5 CD verify (smoke) — FR-CD-*

- **FR-CD-1** — Emit a CD verify stage that runs the existing deploy harness boot→health→smoke ladder
  (`startd8 deploy local --json`) against the app. **Scoped to `installed`-mode apps**: the harness
  boots installed-only and reports `BOOT=SKIPPED` for `deployed` (no Postgres path — D5).
- **FR-CD-2** — The verify stage consumes the harness's graded `LadderResult` and fails the pipeline on
  a failed required stage (boot/health), with smoke as gated-but-graded.
- **FR-CD-3** — v1 CD ends at verify. No deploy-to-target job is emitted.
- **FR-CD-4** — For `deployed`-mode apps, emit a **documented skip** (not a smoke job). Deployed-mode CD
  smoke is a **prerequisite** on new harness deployed-boot support (`deploy_harness/deploy.py`),
  tracked outside this feature.

### 4.6 Secrets & environments — FR-SEC-*

- **FR-SEC-1** — Emitted pipelines reference secrets **by name only**, never inline values. **The
  name set is derived from the `cicd.secrets` manifest block + the `.env.example` convention**
  (`ANTHROPIC_API_KEY`, `DATABASE_URL`, `DOPPLER_TOKEN`, …), filtered through the importable
  `secrets.is_dangerous_key()` deny-list. **It is NOT enumerated from the `secrets/` backend** — that
  backend exposes name→value only and has no name-only API; harvesting names would fetch real values
  into memory and violate FR-SEC-4 (D4).
- **FR-SEC-2** — A declared `cicd.environments` maps to the vendor's environment/variable model where
  one exists. **Default is mode-derived** (OQ-7 resolved): `installed` ⇒ a single environment;
  `deployed` ⇒ `[dev, staging, prod]`. Operator-overridable. Avoids over-provisioning environments for
  single-user installed apps.
- **FR-SEC-3** — Mode-aware defaults: `deployed` defaults the secrets backend to a non-local store
  (Doppler), consistent with deployment-mode's `.env.example` defaults.
- **FR-SEC-4** — No secret value is ever written to an emitted file, a log, or a drift report (extends
  the redaction posture already required of the benchmark/Loki path).

### 4.7 Supply-chain hygiene — FR-SUP-*

- **FR-SUP-1** — Generated GitHub Actions (and equivalents) pin third-party actions/images by **commit
  SHA**, not floating tags.
- **FR-SUP-2** — Prefer **OIDC keyless auth** for registry/cloud where the vendor supports it; avoid
  long-lived stored credentials by default.
- **FR-SUP-3** — Optionally emit an SBOM step and a dependency/vulnerability scan step
  (`cicd.supply_chain.sbom` / `.scan`, default off in v1).
- **FR-SUP-4** — Optionally emit a dependency-update config (Dependabot/Renovate) when requested.

### 4.8 Coherence — FR-COH-*

- **FR-COH-1** — Extend the `scaffold_codegen/coherence.py` ERROR/WARN/OK matrix with CI/CD rows. E.g.:
  push-to-prod-registry + `mode: installed` ⇒ ERROR; `deployed` + build enabled + no Dockerfile ⇒ ERROR;
  `deployed` + push enabled + local secrets backend ⇒ ERROR; CI without migrations on `deployed` ⇒ WARN.
- **FR-COH-2** — Coherence is evaluated at `generate cicd` time and as part of `generate backend`'s
  existing coherence pass; ERROR fails the build.
- **FR-COH-3** — The `wireframe` pre-generation summary gains a "CI/CD" section describing what the
  cascade will emit (advisory, $0), mirroring the deployment-mode wireframe section.

### 4.9 Provisioning (Layer B) — FR-PROV-*

- **FR-PROV-1** — A `startd8 cicd provision` CLI family executes side effects against a vendor:
  `git init`/commit/push, repo creation, secret registration, branch-protection rules.
- **FR-PROV-2** — Provisioning **defaults to `--dry-run`**: it prints the exact side effects (API calls,
  pushes) without performing them. Real execution requires an explicit confirmation flag.
- **FR-PROV-3** — Provisioning is **idempotent**: re-running against an already-provisioned target is
  safe (detect-and-skip / update, never duplicate or destroy).
- **FR-PROV-4** — Provisioning sources credentials from the `secrets/` backend; tokens are never logged,
  never written to disk, never hydrated into emitted files.
- **FR-PROV-5** — Provisioning **consumes Layer A output**: it refuses to run if `generate cicd --check`
  reports drift (or offers to regenerate first). It never authors pipeline content itself.
- **FR-PROV-6** — **v1 provisions GitHub only** (REST + GHCR). GitLab, CircleCI, Azure DevOps, and
  Bitbucket are **generate-only** in v1 (their pipeline files are emitted by Layer A, but Layer B does
  not stand them up). A provision request against a generate-only vendor returns a clear "generate-only"
  message, not a failure. Later increments add provisioners vendor-by-vendor.

---

## 5. Non-Requirements (explicit)

- Deploy-to-target / infra-as-code (Terraform, Helm, K8s manifests) — deferred.
- A universal/abstract CI pipeline language — rejected in favor of native per-vendor renderers.
- LLM-authored pipeline content — this is bucket 1 (Layer A) / operational tooling (Layer B), never bucket 3/4.
- Multi-repo/monorepo matrix orchestration beyond single-app-per-repo — deferred.
- Authoring real environment-promotion *policy* (approvers, prod gates) beyond safe defaults.
- Provisioning all 5 vendors in v1 (generation yes; provisioning GitHub-first).

---

## 6. Milestones (see `CICD_PLAN.md` §2 for file-level detail)

- **M0** — Add `"cicd"` to the strict `_TOP_KEYS` (load-bearing — an unregistered block breaks every
  existing `generate` run, D10) + `ci_codegen` provider/drift with its **own** marker (D1) +
  `.gitignore`/`.gitattributes`/CODEOWNERS (FR-GEN-1..3/5, FR-VCS-*).
- **M1** — GitHub Actions validate job wrapping existing gates + drift `--check` + coherence rows
  (signature-extended, D3) (FR-CI-*, FR-COH-1/2).
- **M2** — Container build/push + manifest-derived named-secret model (D4) + net-new `cicd.registry`
  (D6) + supply-chain pins/OIDC (FR-BLD-*, FR-SEC-*, FR-SUP-1/2).
- **M3** — CD smoke via deploy harness, **installed-scoped** (D5) (FR-CD-*).
- **M4** — Remaining 4 vendor renderers (GitLab, CircleCI, Azure, Bitbucket); validates the flat
  vendor-in-kind map (D2) (FR-GEN-4/6).
- **M5** — Layer B provisioning, GitHub-first, dry-run-default, idempotent, drift-gated (FR-PROV-*).

---

## 7. Open Questions

- **OQ-1** — Does the validate job run SDK gates via an **installed `startd8`** (pip install the SDK in
  CI) or via a thin vendored runner? The former couples generated apps to SDK availability in CI.
- **OQ-2** — How much of a pipeline is genuinely **shareable** across the 5 vendors vs vendor-specific?
  Does a thin neutral `cicd:` manifest + per-vendor renderers hold, or do CircleCI/Azure force
  manifest-level concessions?
- **OQ-3** — Is the **drift check** of vendor YAML robust to vendor-side normalization (e.g. a vendor
  reformatting the file)? Or do we only own files the operator shouldn't hand-edit?
- **OQ-4** — Where does **registry choice** live — `cicd.registry` vs reuse of `container.*`? And does
  GHCR-by-default conflict with non-GitHub vendors?
- **OQ-5** — For Layer B, what is the **minimum credential scope** per vendor, and can we always use
  OIDC to avoid storing long-lived tokens?
- **OQ-6** — Does the existing `secrets/` backend expose the **key-name enumeration** Layer A needs to
  emit named references, or does that require a new read API?
- **OQ-7** — Should `cicd.environments` default to `[dev, staging, prod]` or to a single environment
  matching `deployment.mode`? (Over-provisioning environments may be wrong for installed apps.)
- **OQ-8** — Does CD smoke in CI need the **deployed** path (Postgres + `DATABASE_URL`), which the deploy
  harness currently defers (installed-only boot)? If so, M3 depends on harness deployed-boot support.
- **OQ-9** — *Resolved (see §0):* provisioning is in-scope but lives in a separate `ci_provision/` +
  `cli_cicd.py`, structurally apart from the deterministic `ci_codegen/` core.

> Open questions OQ-1/4/6/7/8/9 are resolved in §0. OQ-2/3/5 are carried into implementation.

---

*v0.2 — Post-planning self-reflective update. 5 requirements reframed (FR-SEC-1, FR-CI-1, FR-BLD-1/2,
FR-GEN-4, FR-CD-1), 1 added (FR-CD-4), 6 open questions resolved (OQ-1/4/6/7/8/9), 2 v1 scope decisions
locked (installed-scoped smoke; GitHub-only provisioning). Paired with `CICD_PLAN.md` v1.0.*

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
