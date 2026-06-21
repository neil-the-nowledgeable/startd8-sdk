# Convergent Review Prompt

**Generated:** 2026-06-20 22:32:15 UTC
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
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/cloud-native-deploy/CLOUD_NATIVE_DEPLOY_PLAN.md` | 185 lines · 3074 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/cloud-native-deploy/CLOUD_NATIVE_DEPLOY_REQUIREMENTS.md` | 244 lines · 3582 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/cloud-native-deploy/CRP_FOCUS_R1.md` | 38 lines · 325 words |

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

# CRP Focus — Cloud-Native Deployment Artifacts (R1)

Where we most need independent review. Weight suggestions toward these:

1. **Security — secrets path.** Doppler-as-default-backend behind the vendor-neutral ESO
   `ExternalSecret` seam (FR-CND-5). Is the `eso-doppler` default sound? Is the Doppler
   service-token bootstrap (chicken-and-egg, FR-CND-11) handled safely? Any leak path where an
   operator-bound secret/value gets baked into a deterministic artifact (violating FR-CND-9)?

2. **Security — identity behind the gateway.** The Bearer/JWT decode-only seam (FR-CND-6,
   auth-seam-jwt) trusts agentgateway to have verified the token. Is "no app change between direct
   and behind-gateway" safe? What happens if the app is exposed WITHOUT a gateway in front (direct
   internet) — is there a fail-closed story, or a footgun?

3. **Vendor-neutrality boundary.** Core = standard Kubernetes + Gateway API (`v1` HTTPRoute) + ESO;
   vendor-specific (Gloo CRDs, Doppler-operator CRD, agentgateway/kagent) is opt-in (FR-CND-3/7,
   `deploy.secrets.backend`). Is the line clean? Any place a vendor CRD leaks into the neutral core?

4. **Bucket-1/bucket-4 line (Mottainai).** SDK emits app-layer manifests + infra-needs contract
   (bucket 1); Terraform/StackGen provision (bucket 4); Kestra/Argo orchestrate. Is the infra-needs
   contract (FR-CND-11) a sufficient, well-specified seam? Is render-only `startd8 deploy k8s`
   (no kubectl/build/push) the right boundary, or does it leave a gap the operator can't close?

5. **Determinism / drift.** All artifacts owned/$0/drift-checked via the ScaffoldFileProvider
   pattern; `deployed`-only emission must stay byte-identical-when-absent (SOTTO). Risk: manifest
   layer drifts from app reality (port, `/health` path, env names) — is the cross-check (plan §4)
   adequate?

6. **Ops prerequisites.** Cluster prereqs (Gateway-API CRDs, ESO/Doppler operator, OTLP collector,
   IdP issuer, SecretStore). Are they all enumerated in the infra-needs contract? Anything an
   operator would hit at deploy time that the contract doesn't surface?

7. **StartDate (strtd8) pilot acceptance (FR-PILOT-1).** Is the graded boot ladder (local harness
   extended to a cluster-smoke rung, operator-run) a sufficient acceptance gate for "deploy to
   AWS/GCP soon"? What's the minimum proof that the pilot actually validates the capability?

8. **OQ-9 (open).** Should v1 render a Terraform variables stub, or stay tool-neutral YAML only?
   Recommendation welcome.

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/cloud-native-deploy/CLOUD_NATIVE_DEPLOY_PLAN.md`  ·  **Size:** 185 lines · 3074 words

```markdown
# Cloud-Native Deployment Artifacts — Implementation Plan

**Version:** 1.0
**Date:** 2026-06-20
**Tracks:** `CLOUD_NATIVE_DEPLOY_REQUIREMENTS.md` (v0.2)

---

## 1. Planning Discoveries (fed back into requirements §0)

| Requirements assumed (v0.1) | Code reality | Impact |
|---|---|---|
| FR-CND-2: a `/health`+liveness endpoint must be ADDED | **Already emitted** — `health_renderer.py` → `app/health.py` (kind `fastapi-health`): `GET /health` (readiness, `SELECT 1` via get_session) + `GET /health/live` (liveness); mounted in `crud_generator.py:385`. The deploy harness already probes the bare `/health`. | **FR-CND-2 narrows to "wire K8s probes to the existing paths"** — zero app-code change. |
| FR-CND-4: new OTel bootstrap code needed | **Already emitted** — `telemetry_renderer.py` → `app/telemetry.py` when `telemetry.enabled`; `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`, and `ENV`→`deployment.environment` are all **env-overridable at runtime**. | **FR-CND-4 narrows to "enable telemetry in app.yaml + set deploy-time env to the cluster collector"** — code exists. |
| New `app.yaml` block shape unknown (OQ-1) | `AppManifest` (`manifest.py`) is strict-keyed with sibling blocks `app/persistence/logging/migrations/container/deployment/telemetry/messaging`; unknown keys hard-error (no LLM fallback). | **Add a new strict `deploy:` block** (k8s settings) parallel to `container:`/`deployment:`. Don't overload `container:`. |
| Home module unknown (OQ-2) | `scaffold_codegen` already owns app.yaml-derived plumbing (pyproject/logging/alembic/**Dockerfile**) via `ScaffoldFileProvider` + `SCAFFOLD_RENDERERS` + `#`-comment GENERATED headers + drift. | **Emit the K8s/Gateway/ESO manifests as new scaffold output kinds** (optionally a `scaffold_codegen/k8s/` submodule) reusing the provider/drift/header. No new provider plumbing. |
| Much of "cloud-native" is unbuilt | health ✓, OTel env-config ✓, container/0.0.0.0 bind ✓ (FR-NET), auth seam ✓ (auth-seam-jwt), settings ✓ (FR-CFG-7), tenancy ✓ (M3). | **The capability is mostly a MANIFEST LAYER that wires together things the app already exposes** — far smaller than v0.1 implied. ~40% of FRs narrowed from "build app code" to "emit manifests pointing at existing surfaces." |
| EKS vs GKE may need separate code paths (OQ-7) | Structural manifests (Deployment/Service/HTTPRoute/ExternalSecret) are identical; only operator bindings differ (ECR vs Artifact Registry; AWS Secrets Mgr vs GCP Secret Mgr SecretStore; gateway class). | **One artifact set; cloud-specifics are operator bindings** (ConfigMap/env/SecretStore ref) — FR-CND-10 confirmed feasible, no fork. |
| SDK could run the deploy (OQ-8) | The SDK never provisions/touches operator cloud creds; `secrets/` hydrates env, deploy harness stays in a local sandbox. `kubectl apply`/image build+push touch the operator's cluster + registry. | **`startd8 deploy k8s` is RENDER-ONLY ($0):** emit manifests; `kubectl apply`/build/push are operator-run (documented runbook). Mirrors "SDK emits, operator deploys." |
| App-exposed MCP is in scope (FR-CND-8) | No generated-app-CRUD→MCP bridge exists; `MCPGateway` fronts skills/workflows, not generated app routes. Building it is a separate, large capability. | **Defer FR-CND-8** to a later increment (tracked stretch). v1 = the app is gateway-/HTTP-ready, not MCP-exposing. |

> ~50% of v0.1 FRs revised (2 narrowed to wiring-only, 1 deferred, render-only reframe, no-fork confirmation).
> Past the 30% bar — the substrate was richer than assumed; the real work is the manifest layer + a render command.

## 2. Approach (milestones)

**M0 — Manifest model + `deploy:` block.** Add a strict `deploy:` block to `AppManifest`
(`scaffold_codegen/manifest.py`): replicas, resource requests/limits, gateway listener ref,
secret-store ref name, image placeholder. Strict-keyed, mode-aware (deploy artifacts emit only in
`deployed` mode, like `settings.py`/`auth.py`).

**M1 — Vendor-neutral manifest renderers** (`scaffold_codegen/k8s/`, new output kinds; reuse
`ScaffoldFileProvider`/drift/header):
- `k8s-deployment` → `deploy/deployment.yaml` — container from the existing Dockerfile image
  (`image:` is an operator-bound placeholder), env from ConfigMap+Secret, **liveness probe
  `/health/live` + readiness probe `/health`** (FR-CND-2 wired, not built), resource limits.
- `k8s-service` → `deploy/service.yaml`.
- `k8s-configmap` → `deploy/configmap.yaml` — non-secret env incl. `OTEL_EXPORTER_OTLP_ENDPOINT`
  (cluster collector), `OTEL_SERVICE_NAME`, `ENV` (FR-CND-4 wired).
- `k8s-httproute` → `deploy/httproute.yaml` — Gateway API `HTTPRoute` referencing an operator-owned
  `Gateway`/listener (FR-CND-3). Standard `gateway.networking.k8s.io`, never Gloo CRDs.
- `k8s-externalsecret` → `deploy/externalsecret.yaml` — ESO `ExternalSecret` referencing an
  operator-owned `SecretStore` (name is a `deploy:` binding), keys = provider API keys + `DATABASE_URL`
  (FR-CND-5). **Default backend = Doppler** (ESO Doppler provider) — consistent with the SDK's existing
  `secrets/doppler.py` + env-hydration model, so secrets flow identically dev (`doppler run`) →
  in-cluster (Doppler→K8s Secret→pod env), zero app change. `deploy.secrets.backend` selects
  `eso-doppler` (default) / `doppler-operator` (opt-in `DopplerSecret` CRD) / `eso-aws|eso-gcp`. SDK
  emits the reference, never the store/values; the Doppler service token is an operator bootstrap
  (infra-contract prerequisite).
- `deploy-infra-contract` → `deploy/infra-contract.yaml` — the **IaC/orchestration seam** (FR-CND-11):
  machine-readable list of what the app needs the cluster/cloud to provide (cluster+namespace,
  registry, SecretStore + expected keys, Gateway/listener, OTLP collector, min CRD versions). The
  three-layer boundary in one artifact: **SDK emits this → Terraform/StackGen provision from it →
  Kestra/Argo/CI orchestrate apply.** Optional Terraform variables stub (inputs only, not resources).
  Per Mottainai/NR: the SDK does NOT generate the Terraform resources or the pipeline itself.

**M2 — `startd8 deploy k8s --render` (RENDER-ONLY, $0).** CLI that emits the `deploy/` tree from
`app.yaml`; `--check` drift like `generate backend`. No `kubectl`, no build/push. Wireframe surfaces
the deploy artifacts + operator-bound placeholders.

**M3 — Coherence + bucket guard.** Extend `scaffold_codegen/coherence.py`: ERROR if `deploy:` present
without `deployment.mode: deployed`; WARN if `ExternalSecret` keys reference secrets with no
SecretStore binding; surface "operator must bind: image, host, SecretStore, gateway" advisory.

**M4 — Optional agent integration (FR-CND-7, opt-in, separated).** Behind a `deploy.agentgateway: true`
flag: emit a reference agentgateway target / kagent workload reference. Clearly vendor-specific,
outside the vendor-neutral core. (FR-CND-8 app-exposed MCP stays deferred.)

**M5 — StartDate pilot (FR-PILOT-1).** Generate StartDate's app + `deploy/` tree; produce a runbook:
build→push to ECR/Artifact Registry → `kubectl apply` → rollout → probe via agentgateway → smoke.
Extend the local-deploy-harness graded ladder conceptually to a cluster-smoke rung (operator-run).

## 3. Validation

```bash
PYTHONPATH=$PWD/src .venv/bin/pytest tests/unit/scaffold_codegen/ -v        # manifest + renderers + drift
# every emitted YAML must parse + pass `kubectl --dry-run=client` (gated, operator env) and a vendor-neutral schema check
PYTHONPATH=$PWD/src .venv/bin/python -c "import yaml,glob;[yaml.safe_load(open(f)) for f in glob.glob('deploy/*.yaml')]"
```
- All manifests `yaml.safe_load` clean; drift `--check` in_sync; installed mode emits NO `deploy/` (byte-identical-when-absent, SOTTO).
- Gateway API objects validate against `gateway.networking.k8s.io`; ExternalSecret against `external-secrets.io`.
- StartDate: `deploy/` renders, operator runbook applies cleanly to a test EKS/GKE namespace.

## 4. Risks

| Risk | Mitigation |
|---|---|
| Operator-bound values get baked (bucket-4 leak) | Placeholders via ConfigMap/`deploy:` bindings + M3 guard; never bake registry/host/account/secret |
| Gateway API version skew | Pin `v1` `HTTPRoute`; document min Gateway-API version; keep listener ref operator-owned |
| ESO not installed in cluster | M3 WARN + runbook prerequisite list (ESO, Gateway-API CRDs, collector, IdP) |
| Manifest layer drifts from app reality (port/health path) | Renderers read the SAME constants as health/main/settings; drift test cross-checks port + `/health` path |
| Scope creep into a deploy orchestrator | Render-only CLI; apply/build/push stay operator-run (documented) |

## 5. Out of scope (deferred / operator)
- App-exposed MCP surface (FR-CND-8) — later increment.
- Helm/kustomize templating (v1 = plain manifests; overlays = v2, OQ-5).
- Cluster provisioning, IdP/SecretStore/gateway install — operator.
- Mesh/mTLS (Ambient/ztunnel) — optional operator layer, not emitted.

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

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-20

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-20 (UTC)
- **Scope**: Plan quality (S-prefix) — weighted to sponsor focus (secrets bootstrap, JWT-behind-gateway footgun, vendor-neutrality boundary, bucket-1/4 line, determinism/drift, ops prereqs, pilot acceptance, OQ-9). Companion F-suggestions + focus-ask answers (incl. OQ-9 recommendation) are in the requirements file's Appendix C. Requirements coverage matrix is appended at the end of this plan.

##### Executive summary (top risks / gaps)

- **Highest risk: M1 `k8s-httproute` + decode-only JWT seam (FR-CND-6) has no fail-closed plan** — if the rendered Service/route is ever reachable without a gateway terminating auth, the app trusts any token. The plan needs a NetworkPolicy / internal-only Service rung. (R1-S1)
- **Doppler service-token bootstrap (M1/M5) is named but has no concrete operator runbook step** — the chicken-and-egg break is hand-waved; M5 runbook must seed it before `kubectl apply`. (R1-S2)
- **M3 coherence guard is too weak** — it WARNs on missing SecretStore binding; it should ERROR on secret keys with no store, and should assert the vendor-neutrality allowlist on the default tree. (R1-S3)
- **The §4 "manifest drifts from app reality" cross-check is asserted but not specified** — no concrete shared-constant source or test is named for port/`/health` path/env names. (R1-S4)
- **M5 pilot lacks a defined PASS predicate** — "smoke" is unscoped; the cluster-smoke rung needs a single documented acceptance gate. (R1-S5)
- **OQ-9 unresolved in the plan** — no milestone owns the tfvars-stub decision; recommend tool-neutral YAML default + opt-in stub (see requirements R1-F5). (R1-S6)
- **ConfigMap/Secret classification is implicit** — M1 `k8s-configmap` vs `k8s-externalsecret` split needs a declared secret-key list to avoid a credential landing in the ConfigMap. (R1-S7)

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Security | critical | Add a fail-closed network rung to M1: emit an internal-only Service (ClusterIP) plus a NetworkPolicy that denies ingress except from the gateway namespace/selector, OR require a `deploy.trust_gateway` ack that M3 ERRORs without. Document that no internet-facing Service is emitted by default. | The decode-only JWT seam (FR-CND-6) is an auth bypass if the app is reachable without the gateway in front; the plan currently emits Deployment/Service/HTTPRoute with no guard against direct exposure. | M1 (new `k8s-networkpolicy` kind) + M3 guard | Apply default tree without a Gateway; confirm pod is not reachable from outside the gateway selector; M3 ERRORs if `trust_gateway` unacknowledged. |
| R1-S2 | Ops | high | M5 runbook must include the Doppler service-token bootstrap as an explicit ordered step BEFORE `kubectl apply` (seed via Terraform/cloud-secret-manager/sealed-secret), and the infra-contract consumer must verify the token exists. Today M1's `deploy-infra-contract` lists it only as a "prerequisite." | The chicken-and-egg (ESO needs the Doppler token to fetch secrets, but the token itself must arrive out-of-band) is the named focus risk; without a runbook step the first apply fails opaquely. | M5 runbook list + M1 `deploy-infra-contract` | Runbook step ordering test / dry-run; contract marks the token `operator-provided` and absence is detectable pre-apply. |
| R1-S3 | Security | high | Strengthen M3: change "WARN if ExternalSecret keys reference secrets with no SecretStore binding" to ERROR, and add a vendor-neutrality allowlist check — the default (non-opt-in) `deploy/` tree must contain only allowlisted `apiVersion`s; any vendor CRD (Doppler-operator `DopplerSecret`, Gloo, kagent/agentgateway) only under its opt-in flag. | A dangling ExternalSecret with no store is a deploy-time failure, not a warning; and the vendor-neutrality "clean line" (focus area 3) is only enforceable via an allowlist assertion, which M3 is the natural home for. | M3 (coherence + bucket guard) | Unit test: dangling-store app.yaml → coherence exit nonzero; default tree apiVersions ∈ allowlist; opt-in flags introduce CRDs only when set. |
| R1-S4 | Validation | high | Specify the §4 drift cross-check concretely: name the single source of truth the renderers read for port, `/health` + `/health/live` paths, and env-var names (e.g. the same constants `health_renderer.py`/`telemetry_renderer.py`/`settings` emit), and add a test that fails if a manifest probe path or container port diverges from that source. | §4 risk row asserts "renderers read the SAME constants" but neither the constant module nor the cross-check test is named; this is the determinism/drift focus area and the most likely silent breakage (probe points at a path the app no longer serves). | §3 Validation + §4 Risks row | Test mutates the app's health path constant and asserts the manifest renderer + drift `--check` catch the mismatch. |
| R1-S5 | Validation | medium | Define M5's cluster-smoke PASS predicate explicitly: which graded-ladder rungs are required (boot→health→smoke) and the single pass gate (e.g. readiness probe green AND one authenticated request through agentgateway returns 2xx). | "rollout → probe via agentgateway → smoke" is unscoped; FR-PILOT-1 acceptance needs a documented predicate or the pilot can be declared passing on any subset. | M5 + §3 Validation | Pilot record lists each required rung's result; PASS is one boolean predicate. |
| R1-S6 | Architecture | medium | Assign OQ-9 to a milestone: default M1/M2 output is tool-neutral YAML contract only; add optional `startd8 deploy k8s --emit-tfvars-stub` (inputs-only, byte-identical-when-absent per SOTTO); M5 documents the StackGen/Terraform hand-off rather than integrating it. | OQ-9 is the only open question and currently owned by no milestone; deferring the decision blocks the bucket-1/4 boundary from being implementable. Recommendation matches requirements R1-F5. | M1/M2 (flag) + M5 (hand-off doc) + resolve OQ-9 | Default render has no `.tf*`; with the flag, only variable declarations emitted; absence byte-identical. |
| R1-S7 | Data | medium | M1 must declare the secret-vs-non-secret env classification as a single explicit list so `k8s-configmap` and `k8s-externalsecret` partition deterministically; known-secret keys (provider API keys, `DATABASE_URL`) must never appear in the ConfigMap. | The split is implied across two renderers; a misclassification silently bakes a credential into a $0 ConfigMap (FR-CND-9 / FR-CND-5 leak). | M1 `k8s-configmap` / `k8s-externalsecret` | Test: secret-key allowlist never appears in `configmap.yaml`; classification is one shared list consumed by both renderers. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S8 | Risks | medium | Add a risk row + mitigation for the `image:` placeholder: M1 says the image is "an operator-bound placeholder," but a placeholder that is a syntactically valid image ref (e.g. `REPLACE_ME:latest`) can be `kubectl apply`-ed and silently pull-fail or pull a squatted image. Use an obviously-invalid sentinel and have M3 ERROR if it survives to a non-render context. | An apply-able-but-wrong image placeholder is a classic deploy footgun and undermines "operator binds at deploy time"; the §4 risk table omits it. | §4 Risks + M3 guard | Test: rendered `image:` is a non-pullable sentinel; M3 flags an unbound image; runbook requires binding before apply. |
| R1-S9 | Interfaces | low | Clarify the M1 `k8s-httproute` ↔ operator `Gateway` contract: the plan emits an `HTTPRoute` referencing an operator-owned Gateway/listener, but does not state how the listener name/namespace/sectionName is supplied (a `deploy:` binding) vs hardcoded. | An HTTPRoute with a hardcoded `parentRef` is an operator-bound value baked in (FR-CND-9); the binding seam needs to be explicit at the interface level. | M1 `k8s-httproute` + `deploy:` block (M0) | Two app.yamls differing only in gateway listener ref produce HTTPRoutes differing only in `parentRef`; nothing else baked. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — R1 is the first round; Appendix C had no prior suggestions.

---

## Requirements Coverage Matrix — R1

Analysis only (informs orchestrator triage). Maps each requirement to the plan milestone(s) that address it. Coverage: **Covered** / **Partial** / **Gap**.

| Requirement | Plan milestone(s) | Coverage | Gap / note |
| ---- | ---- | ---- | ---- |
| FR-CND-1 (K8s Deployment+Service, ConfigMap/Secret) | M0 (`deploy:` block), M1 (`k8s-deployment`, `k8s-service`, `k8s-configmap`, `k8s-externalsecret`) | Partial | Secret-vs-non-secret env classification rule is implicit — see R1-S7 / R1-F8. |
| FR-CND-2 (health probes wired to existing paths) | M1 (`k8s-deployment` liveness `/health/live` + readiness `/health`) | Covered | Drift cross-check against the app's actual path is asserted but unspecified — see R1-S4. |
| FR-CND-3 (Gateway API HTTPRoute, vendor-neutral) | M1 (`k8s-httproute`, `gateway.networking.k8s.io/v1`) | Partial | Operator `Gateway`/listener `parentRef` binding seam not specified — see R1-S9; vendor-neutrality allowlist not enforced — see R1-S3 / R1-F7. |
| FR-CND-4 (OTel → cluster collector, config-only) | M1 (`k8s-configmap` OTLP env) | Partial | Contract surfaces only "endpoint," not protocol/port — see R1-F6. |
| FR-CND-5 (Secrets via ESO, Doppler default) | M1 (`k8s-externalsecret`, `deploy.secrets.backend`) | Partial | Doppler project/config could leak into the emitted artifact (FR-CND-9) — see R1-F2; service-token bootstrap under-specified — see R1-S2 / R1-F1. |
| FR-CND-6 (gateway-ready decode-only identity) | M1 (route/config assumes upstream verify) | Gap | No fail-closed posture for direct (non-gateway) exposure — the critical finding, see R1-S1 / R1-F3. |
| FR-CND-7 (optional agentgateway/kagent, opt-in) | M4 (`deploy.agentgateway` flag) | Covered | Ensure CRDs gated behind the flag are caught by the allowlist check — see R1-S3 / R1-F7. |
| FR-CND-8 (app-exposed MCP) | (deferred — §5 out of scope) | Covered | Explicitly deferred; no plan obligation in v1. |
| FR-CND-9 (determinism + bucket line, no baked operator values) | M3 (bucket guard), §4 risks | Partial | `image:` placeholder footgun (R1-S8); project/config leak (R1-F2); enforcement is prose, not an allowlist test (R1-S3). |
| FR-CND-10 (EKS/GKE no-fork) | §1 discovery, M1 (one artifact set) | Covered | Confirmed structural; differences are operator bindings. |
| FR-CND-11 (infra-needs contract / IaC seam) | M1 (`deploy-infra-contract`) | Partial | Prereq fields not exhaustive/machine-checkable (R1-F6); OQ-9 tfvars-stub decision unassigned (R1-S6 / R1-F5). |
| FR-PILOT-1 (StartDate pilot acceptance) | M5 (runbook + cluster-smoke rung) | Partial | No defined required rungs / PASS predicate — see R1-S5 / R1-F4. |
| OQ-9 (open: tfvars stub vs YAML-only) | (unassigned) | Gap | Recommend tool-neutral YAML default + opt-in `--emit-tfvars-stub`; document hand-off, don't validate against StackGen in pilot — see R1-S6 / R1-F5. |
```

---

## Document Under Review: Requirements

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/cloud-native-deploy/CLOUD_NATIVE_DEPLOY_REQUIREMENTS.md`  ·  **Size:** 244 lines · 3582 words

```markdown
# Cloud-Native Deployment Artifacts (Generated Apps → EKS/GKE behind agentgateway/kagent) — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-20
**Status:** Ready for CRP / implementation
**Owner:** StartD8 SDK / scaffold_codegen + backend_codegen (bucket-1 $0 deterministic; bucket-4 boundary held)
**Builds on:** `docs/design/deployment-mode/` (the `deployed` tier) + `docs/design/auth-seam-jwt/` (Bearer/JWT seam) + `docs/design/local-deploy-harness/`
**Pilot:** StartDate (`strtd8`) — deploy the SDK-generated StartDate app to AWS (EKS) or GCP (GKE)

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2 after planning against the real code
> (`health_renderer.py`, `telemetry_renderer.py`, `scaffold_codegen/manifest.py`+`provider.py`,
> deployment-mode FR-NET/FR-OBS). See `CLOUD_NATIVE_DEPLOY_PLAN.md` §1. Central correction: **most
> of the "cloud-native" substrate already exists in the generated app** — this capability is mostly
> a vendor-neutral MANIFEST LAYER wiring together surfaces the app already exposes, plus a
> render-only command. The build is far smaller than v0.1 implied.

| v0.1 assumption | Planning discovery | Impact |
|-----------------|--------------------|--------|
| FR-CND-2: must ADD a `/health`+liveness endpoint | Already emitted — `app/health.py` serves `GET /health` (readiness, `SELECT 1`) + `GET /health/live` (liveness); deploy harness already probes `/health`. | FR-CND-2 narrows to **wiring K8s probes to existing paths** (no app change). |
| FR-CND-4: new OTel bootstrap code needed | Already emitted — `app/telemetry.py` with `OTEL_EXPORTER_OTLP_ENDPOINT`/`OTEL_SERVICE_NAME`/`ENV` all env-overridable. | FR-CND-4 narrows to **enable telemetry + set deploy-time env** to the cluster collector. |
| New manifest home + app.yaml shape unknown | `scaffold_codegen` already owns app.yaml-derived plumbing (incl. `Dockerfile`) via `ScaffoldFileProvider`+drift+header; `AppManifest` is strict-keyed. | Emit K8s/Gateway/ESO as **new scaffold output kinds**; add a strict **`deploy:` block**. No new provider plumbing. |
| EKS vs GKE need separate paths (OQ-7) | Structural manifests identical; only operator bindings differ (registry, SecretStore backend, gateway class). | FR-CND-10 confirmed — **one artifact set, no fork**. |
| SDK could run the deploy (OQ-8) | SDK never touches operator cloud creds; `kubectl`/build/push are operator territory. | **`startd8 deploy k8s` is render-only ($0)**; apply/build/push are an operator runbook. |
| FR-CND-8 (app-exposed MCP) in scope | No generated-app-CRUD→MCP bridge exists; `MCPGateway` fronts skills/workflows, not app routes — a separate large capability. | **FR-CND-8 deferred** to a later increment (tracked stretch). |

**Resolved open questions:**
- **OQ-1 → New `deploy:` block** in `AppManifest` (strict-keyed, parallel to `container:`/`deployment:`).
- **OQ-2 → New output kinds in `scaffold_codegen`** (optional `k8s/` submodule), reusing the provider/drift/header.
- **OQ-3 → YES, `/health` + `/health/live` already exist.** FR-CND-2 = wiring only.
- **OQ-4 → YES, OTLP endpoint is env-configurable.** FR-CND-4 = env + enable only.
- **OQ-5 → Plain manifests in v1**; kustomize base+overlay (and any IaC layer — see OQ-9) deferred.
- **OQ-6 → FR-CND-8 deferred** (app-exposed MCP) to a later increment.
- **OQ-7 → No fork** — EKS/GKE differences are operator bindings, not SDK code.
- **OQ-8 → Render-only CLI** + operator runbook; pilot ladder = local harness + a cluster-smoke rung (operator-run).
- **OQ-9 (new, for CRP).** Should the infra-needs contract (FR-CND-11) render an optional Terraform
  **variables stub** in v1, or stay tool-neutral YAML only? And: do we validate the contract against
  StackGen/Terraform consumption in the pilot, or document the hand-off and defer integration?

---

## 1. Problem Statement

The `deployed` tier (DEPLOYMENT_MODE) gives a generated app a container (`Dockerfile`, `0.0.0.0` bind),
a centralized-OTel posture, an auth seam, settings, and (declared) tenancy. **It stops at the
container.** To actually run that app on EKS/GKE — behind the agentgateway/kagent stack discussed for
the SDK's own MCP — an operator still hand-writes every Kubernetes manifest, the gateway route, the
secret wiring, and the probe/telemetry plumbing. That is structural deployment skeleton (the same
"who routes to it / where do secrets come from / how does the cluster health-check it" that the
determinism thesis says should be *generated*, bucket 1), not company content (bucket 4).

The goal: a generated app should **emit the cloud-native artifacts needed to deploy to a private
cloud (EKS/GKE) behind agentgateway/kagent** — deterministically, `$0`, drift-checked, and
**vendor-neutral** (standard Kubernetes + Gateway API + External Secrets, never Gloo-/cloud-specific
CRDs), with operator-owned values (image registry, domain, cluster policy, IdP, SecretStore) **bound
at deploy time, not baked**. StartDate is the pilot and the acceptance surface.

### Gap table (what the `deployed` tier already gives vs what K8s-behind-gateway needs)

| Concern | `deployed` tier today | Gap for EKS/GKE + agentgateway |
|---------|----------------------|--------------------------------|
| Container | `Dockerfile`, `0.0.0.0:8000` (scaffold) | No K8s Deployment/Service wrapping it |
| Health | (assumed none — to verify) | K8s liveness/readiness probes |
| Routing | none | Gateway API `HTTPRoute` to the gateway listener |
| Telemetry | OTel posture declared (assumed code TBD) | OTLP → in-cluster collector wiring |
| Secrets | SDK `secrets/` backend (doppler/local) | K8s `ExternalSecret`/`ConfigMap` from cloud secret mgr |
| Identity | Bearer/JWT seam (auth-seam-jwt) | HTTPRoute/gateway terminates auth, forwards identity |
| Agent surface | none | (optional) agentgateway/kagent integration; app-exposed MCP |
| Cloud neutrality | n/a | One artifact set for EKS *and* GKE; cloud-specifics operator-bound |

---

## 2. Requirements

- **FR-CND-1 (K8s workload manifests).** A `deployed` app SHALL emit standard Kubernetes
  `Deployment` + `Service` manifests wrapping the existing container, with resource requests/limits
  and env sourced from a generated `ConfigMap` (non-secret) and `Secret`/`ExternalSecret` (secret).
- **FR-CND-2 (Health probes — narrowed v0.2).** The manifests SHALL wire Kubernetes readiness
  (`GET /health`) + liveness (`GET /health/live`) probes to the app's **already-emitted** endpoints
  (`app/health.py`). No app-code change — manifest wiring only.
- **FR-CND-3 (Gateway API routing).** A `deployed` app SHALL emit a **vendor-neutral** Gateway API
  `HTTPRoute` (and a referenceable `Gateway`/listener stub) so kgateway / agentgateway / Gloo /
  any Gateway-API implementation can route to it without app changes.
- **FR-CND-4 (OTel → cluster collector — narrowed v0.2).** The emitted ConfigMap SHALL set the
  app's **existing** env knobs (`OTEL_EXPORTER_OTLP_ENDPOINT`→cluster collector, `OTEL_SERVICE_NAME`,
  `ENV`→`deployment.environment`); `telemetry.enabled` in `app.yaml` activates `app/telemetry.py`.
  No new telemetry code — config wiring only.
- **FR-CND-5 (Secrets via ESO — Doppler as default backend, v0.2).** The app SHALL source provider
  API keys + DB credentials at runtime from `os.environ`, populated in-cluster via a **vendor-neutral**
  `ExternalSecret` (External Secrets Operator) referencing an **operator-owned `SecretStore`** — the
  SDK emits the reference, never the store or the values. **The default `SecretStore` backend SHALL
  be Doppler** (ESO has a first-class Doppler provider), since Doppler is already the org's secrets
  manager and the SDK already ships a Doppler backend (`src/startd8/secrets/doppler.py`,
  `docs/design/doppler-secrets/`). This is end-to-end consistent: the SDK + generated app already use
  an **env-hydration** model (`os.getenv`, never a central getter), so secrets flow identically in dev
  (`doppler run`) and in-cluster (Doppler → K8s Secret → pod env) **with zero app-code change**.
  A `deploy.secrets.backend` binding SHALL select: `eso-doppler` (default), `doppler-operator`
  (opt-in, emits the Doppler K8s Operator `DopplerSecret` CRD — vendor-specific, like FR-CND-7), or
  `eso-aws`/`eso-gcp` (cloud-native secret manager) for shops not standardizing on Doppler.
- **FR-CND-6 (Gateway-ready identity).** The Bearer/JWT seam (auth-seam-jwt) SHALL be the contract
  agentgateway terminates and forwards; the emitted route/config SHALL assume upstream identity
  verification (decode-only seam), with no app change between "direct" and "behind-gateway."
- **FR-CND-7 (Optional agent integration).** The capability SHALL OPTIONALLY emit reference
  agentgateway/kagent integration (e.g., a kagent-managed workload reference or an agentgateway
  target) — opt-in, vendor-specific, and clearly separated from the vendor-neutral core.
- **FR-CND-8 (App-exposed MCP — DEFERRED v0.2).** A generated app MAY later expose its own MCP
  surface (CRUD/actions as agent-accessible tools) so the app itself can sit behind agentgateway as
  an MCP server, mirroring the SDK's `MCPGateway`. **Deferred to a later increment** — no
  generated-app-CRUD→MCP bridge exists today; it is a separate large capability, not v1 scope.
- **FR-CND-9 (Determinism + bucket line).** All emitted artifacts SHALL be owned/`$0`/drift-checked
  (DeterministicFileProvider pattern), carry the GENERATED header, and be **vendor-neutral reference
  scaffolds**: operator-owned values (image registry/tag, domain/host, replica count, SecretStore,
  IdP issuer, cluster policy) are bound at deploy time (env/ConfigMap/overlay), never baked.
- **FR-CND-10 (Cloud-target neutrality).** The same artifact set SHALL deploy to EKS and GKE; the
  only differences SHALL be operator bindings (registry, secret store backend, ingress/gateway
  class), not separate SDK code paths.
- **FR-CND-11 (Infra-needs contract — the IaC/orchestration seam, added v0.2).** The capability
  SHALL emit a machine-readable **infra-needs contract** (`deploy/infra-contract.yaml`) enumerating
  what the app requires the cluster/cloud to provide — cluster + namespace, container registry, a
  `SecretStore` and the secret keys it expects, a Gateway-API `Gateway`/listener, an OTLP collector
  endpoint, the **Doppler project/config** (default SecretStore backend, FR-CND-5) and — flagged as a
  one-time operator prerequisite — the **Doppler service-token bootstrap** (the single secret seeded
  into the cluster via Terraform/cloud-secret-manager/sealed-secret to break the chicken-and-egg),
  and min CRD/versions (Gateway-API, ESO/Doppler-operator). This is the **seam to provisioning IaC and
  pipeline orchestration**, NOT the provisioning itself: per Mottainai/bucket-4, the SDK does not
  reimplement Terraform/StackGen (infra provisioning) or Kestra/Argo/CI (deploy orchestration) — it
  emits the contract those mature tools consume. The contract MAY render an optional Terraform
  **variables stub** (the inputs, not the resources) to ease hand-off.
- **FR-PILOT-1 (StartDate pilot).** The acceptance surface is the SDK-generated **StartDate** app:
  generate → emit cloud-native artifacts → deploy to EKS or GKE behind agentgateway → graded boot
  ladder (the local-deploy-harness ladder, extended to a cluster) passes.

## 3. Non-Requirements

- NOT a cluster provisioner — operator owns EKS/GKE, the gateway install, the IdP, the SecretStore.
- NOT Gloo-/cloud-vendor CRDs in the core — vendor-neutral Gateway API + ESO only (vendor extras are FR-CND-7, opt-in).
- NOT baking secrets, cloud account IDs, registries, or domains.
- NOT a Helm/kustomize templating engine in v1 (plain manifests; templating deferred — see OQ-5).
- NOT the SDK's own MCP deployment (that was the prior architecture discussion; this is *generated-app* deployment).
- NOT runtime hot-switching of topology (inherits DEPLOYMENT_MODE NR-3).
- **NOT an IaC engine or a deploy orchestrator (Mottainai).** The SDK does NOT reimplement
  Terraform/StackGen (cluster/VPC/IAM/registry/SecretStore/gateway provisioning — bucket-4 operator)
  or Kestra/Argo/CI (build→push→apply→smoke orchestration). It emits the app-layer manifests + the
  infra-needs contract (FR-CND-11) those tools consume. Leverage the mature layer; don't recreate it.

## 4. Open Questions

> OQ-1..OQ-8 were **resolved by the planning pass — see §0** for resolutions. Retained here for
> traceability. OQ-9 (below) is open for CRP. Secrets-backend choice is resolved in FR-CND-5
> (default `eso-doppler`).

- **OQ-1.** New `app.yaml` block (`deploy:` / `k8s:`) or extend the existing `container:` block?
- **OQ-2.** New `k8s_codegen` module + its own DeterministicFileProvider, or new output kinds inside `scaffold_codegen`?
- **OQ-3.** Does a generated app already expose `/health` (+ liveness) for probes, or must it be added (FR-CND-2)?
- **OQ-4.** Is the generated app's OTLP endpoint already env-configurable, or is new telemetry code needed (FR-CND-4)?
- **OQ-5.** v1 output: plain manifests, or kustomize base+overlays (to make operator bindings cleaner)?
- **OQ-6.** App-exposed MCP (FR-CND-8): in v1 or deferred to a later increment?
- **OQ-7.** How much EKS-vs-GKE divergence is genuinely structural vs operator-bound (FR-CND-10)?
- **OQ-8.** Pilot ladder: extend the local-deploy-harness graded ladder to a real cluster, or a separate cluster-smoke?

---

*v0.2 — Post-planning self-reflective update. 2 requirements narrowed to wiring-only (FR-CND-2/4),
1 deferred (FR-CND-8 app-MCP), 1 added (FR-CND-11 infra-needs contract / IaC seam), render-only
reframe, EKS/GKE no-fork confirmed, 8 open questions resolved, 1 new (OQ-9) for CRP. Three-layer
boundary set: SDK = app-layer manifests + infra contract (bucket 1); Terraform/StackGen = provisioning
(bucket 4); Kestra/Argo/CI = orchestration. Mottainai: leverage mature layers, don't recreate them.*

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

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-20

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-20 (UTC)
- **Scope**: Requirements quality (F-prefix) — weighted to the sponsor focus areas (secrets/ESO/Doppler bootstrap, JWT-behind-gateway footgun, vendor-neutrality boundary, bucket-1/4 Mottainai line, determinism/drift, ops prereqs, pilot acceptance, OQ-9). Dual-document review; this round is requirements-only. Plan S-suggestions + coverage matrix live in the plan file's Appendix C / coverage matrix.

##### Sponsor focus asks (answered first)

**Ask 1 — Is `eso-doppler` default sound, and is the FR-CND-11 Doppler service-token bootstrap handled safely? Any leak path violating FR-CND-9?**
- **Summary answer:** Default is sound; the bootstrap seam is *named* but **under-specified**, and there is a latent FR-CND-9 leak risk via the Doppler *project/config* identifiers.
- **Rationale:** FR-CND-5 correctly keeps the SDK emitting only the `ExternalSecret` reference, never the store or values, which matches the env-hydration model. But FR-CND-11 lists "the **Doppler project/config**" as contract content — these are operator-owned bindings, and if the renderer writes them *into the emitted `ExternalSecret`/`SecretStore` ref* rather than the contract-only, that is an operator-bound value baked into a deterministic artifact (FR-CND-9 violation). The service-token bootstrap is mentioned as a one-time prerequisite but never given an acceptance criterion (who seeds it, where it must NOT appear, how absence is detected).
- **Assumptions / conditions:** Doppler project/config names are treated as operator bindings, not constants.
- **Suggested improvements:** see R1-F1 (bootstrap acceptance criteria) and R1-F2 (project/config must be a `deploy:` binding, not baked). 

**Ask 2 — Is "no app change direct vs behind-gateway" (FR-CND-6) safe? Footgun if exposed direct-to-internet without a gateway?**
- **Summary answer:** **No — this is a fail-OPEN footgun as written.** A decode-only JWT seam that trusts an upstream verifier becomes an auth bypass the moment the app is reachable without that verifier in front.
- **Rationale:** FR-CND-6 says the route "SHALL assume upstream identity verification (decode-only seam), with no app change between 'direct' and 'behind-gateway.'" If the same artifact set is applied without a Gateway/agentgateway terminating auth (or with a Service of type LoadBalancer / a misconfigured route), the app decodes but does not *verify* the JWT — any attacker-minted token is trusted. There is no requirement that the deployment fail closed in this state.
- **Assumptions / conditions:** none — this is the defining risk of a decode-only seam.
- **Suggested improvements:** see R1-F3 (fail-closed requirement + a `deploy:` assertion that traffic is gateway-fronted, e.g. require an internal-only Service / NetworkPolicy denying non-gateway ingress, or an explicit `deploy.trust_gateway: true` acknowledgement that surfaces a coherence WARN/ERROR).

**Ask — OQ-9 (Terraform variables stub in v1, or tool-neutral YAML only?).**
- **Summary answer:** **Tool-neutral YAML only in v1; render the Terraform variables stub behind an explicit opt-in flag, and do NOT validate against StackGen/Terraform consumption in the pilot — document the hand-off.**
- **Rationale:** The infra-needs contract (FR-CND-11) is the bucket-1/bucket-4 seam; a `.tfvars`-shaped stub starts pulling Terraform-specific schema assumptions into the neutral core, which erodes the "leverage the mature layer, don't recreate it" Mottainai line (NR, §3). A single canonical YAML contract with a documented, optional `--emit-tfvars-stub` (inputs only, byte-identical-when-absent per SOTTO) preserves neutrality while easing hand-off for Terraform shops. Validating against live StackGen/Terraform in the pilot couples acceptance to an external tool the SDK explicitly does not own (bucket 4) and would inflate FR-PILOT-1 scope.
- **Assumptions / conditions:** the stub is derived purely from the YAML contract (no new inputs), and its absence changes no other byte.
- **Suggested improvements:** see R1-F5 (make OQ-9 a stated FR with the opt-in default) — and the plan-side S-suggestion R1-S6.

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Security | high | Add explicit acceptance criteria for the Doppler service-token bootstrap in FR-CND-11: name the seeding mechanism (Terraform/cloud-secret-manager/sealed-secret), state that the token MUST NOT appear in any SDK-emitted artifact, and define how the contract signals the token as an UNMET operator prerequisite (vs a satisfied one). | FR-CND-11 currently calls the bootstrap "a one-time operator prerequisite" with no testable boundary — "handled safely" is asserted, not verifiable. | FR-CND-11, after "...to break the chicken-and-egg" | Grep all emitted artifacts for any token-shaped value; contract lists the bootstrap secret with `status: operator-provided` and absence is detectable. |
| R1-F2 | Security | high | Require the Doppler project/config (and any SecretStore identifiers) to be `deploy:`-block bindings surfaced in the infra-contract, NOT written into the emitted `ExternalSecret`/`SecretStore` reference body. | FR-CND-11 lists "Doppler project/config" as contract content while FR-CND-9 forbids baking operator-owned values; without this, the project/config name leaks into a deterministic artifact. | FR-CND-5 (binding) + FR-CND-9 (explicit "Doppler project/config" added to the operator-bound list) | Drift test: two app.yamls differing only in Doppler project produce byte-identical `externalsecret.yaml`; project name appears only in the contract/ConfigMap. |
| R1-F3 | Security | critical | FR-CND-6 must state a fail-CLOSED posture when no gateway terminates auth: the deterministic artifacts SHALL make direct (non-gateway) exposure either impossible-by-default (internal-only Service + NetworkPolicy denying non-gateway ingress) or loudly flagged (a required `deploy.trust_gateway` acknowledgement that coherence ERRORs without). | As written, "no app change direct vs behind-gateway" + decode-only = silent auth bypass if the app is ever reachable without the verifier. This is the highest-severity gap in the doc. | FR-CND-6, replace "with no app change between 'direct' and 'behind-gateway'" with the fail-closed clause | Apply manifests without a Gateway in front in a test ns; confirm the app is NOT internet-reachable OR coherence/check fails; attacker-minted token is rejected at the network layer. |
| R1-F4 | Validation | high | FR-PILOT-1 must define the minimum acceptance evidence: which rungs of the local-harness graded ladder (discover→install→boot→health→smoke) are REQUIRED at the cluster-smoke rung, and what counts as PASS (e.g. readiness probe green + one authenticated smoke request through agentgateway returns 2xx). | "graded boot ladder ... passes" is untestable without naming the required rungs and the pass bar; an operator could declare any rung sufficient. | FR-PILOT-1, after "extended to a cluster" | Pilot run record shows each required rung result; PASS gate is a single documented predicate. |
| R1-F5 | Architecture | medium | Promote OQ-9 to a stated requirement: v1 emits tool-neutral YAML contract by default; an optional `--emit-tfvars-stub` renders inputs-only (no resources), byte-identical-when-absent; pilot documents the StackGen/Terraform hand-off rather than integrating/validating it. | OQ-9 is the only open question; leaving it open blocks the bucket-1/4 boundary from being testable and risks the stub leaking Terraform schema into the neutral core. | New FR-CND-12 (or fold into FR-CND-11) + resolve OQ-9 in §0/§4 | Default render contains no `.tf`/`.tfvars`; with the flag, stub holds only variable declarations; absence is byte-identical. |
| R1-F6 | Ops | medium | FR-CND-11's prerequisite enumeration should be made exhaustive and machine-checkable: add the IdP issuer/JWKS URL (needed by the gateway for FR-CND-6), the OTLP collector's protocol/port (not just "endpoint"), and the Gateway listener's hostname/TLS expectation — each tagged operator-provided with a min-version where a CRD is involved. | The focus file asks whether ops prereqs are exhaustive; today FR-CND-11 names categories but not the fields an operator actually needs to satisfy (issuer URL, collector protocol, listener TLS), so the contract under-surfaces deploy-time blockers. | FR-CND-11 prerequisite list | Contract schema lists each prereq with `{name, kind, min_version?, status}`; a stub cluster missing any one is reported by the contract consumer. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F7 | Risks | medium | State a vendor-neutrality conformance criterion: the core (non-opt-in) artifact set SHALL contain ONLY `apiVersion`s in an allowlist (`apps/v1`, `v1`, `gateway.networking.k8s.io/v1`, `external-secrets.io/*`); any vendor CRD (`gloo`, `getambassador`, Doppler-operator `DopplerSecret`, kagent/agentgateway) appears ONLY under an explicit opt-in flag. | FR-CND-3/7 describe the intent prose-only; "is the line clean?" (focus area 3) is unverifiable without an enumerable allowlist that a drift/lint test can assert against. | FR-CND-9 or a new FR (vendor-neutrality conformance) | Lint the default `deploy/` tree: every `apiVersion` ∈ allowlist; flip `deploy.secrets.backend: doppler-operator` and confirm the CRD appears only then. |
| R1-F8 | Data | low | FR-CND-1's `ConfigMap` vs `Secret`/`ExternalSecret` split needs an explicit classification rule (which env keys are non-secret vs secret), so the split is deterministic rather than per-renderer judgement. | "non-secret" vs "secret" is asserted but the partitioning rule is implicit; a misclassification (e.g. `DATABASE_URL` landing in the ConfigMap) is a silent credential leak into a $0 artifact. | FR-CND-1 | Test: known-secret keys (provider API keys, `DATABASE_URL`) never appear in `configmap.yaml`; classification is a single declared list. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — R1 is the first round; Appendix C had no prior suggestions.
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
