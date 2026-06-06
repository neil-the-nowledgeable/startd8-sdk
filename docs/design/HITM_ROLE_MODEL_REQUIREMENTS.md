# Human-in-the-Middle Role Model — Requirements

**Version:** 0.4 (operator decision walkthrough — all remaining OQs resolved/closed; tier-E
starter-value default mode confirmed)
**Date:** 2026-06-05
**Status:** Draft

> **v0.3 CRP triage summary.** Two rounds (R1 opus: 12, R2 sonnet w/ adversarial pass: 9 + 6
> endorsements), all accepted. Headline fixes: tier classification rules + a machine-evidence
> class (M); the **hash-bound lazy gate rule** (approval binds to artifact version, evaluated at
> consumption — resolves OQ-4); unattended gates record `unattended-override`, never synthesized
> approvals; the lifted approval validator requires BOTH `approved_at` AND `approved_by` on
> APPROVED (the source ChunkState validator is one-directional — verified); FR-J7 gains a
> defined "production path" (generated-app render gate + export exclusion), the sidecar status
> form, and a `draft-rejected` terminal state; two new roles (Customer/Product Owner — the
> missing U-tier holder — and Security); FitCheckRecord schema; ledger changes block pending PM
> approval. Dispositions in Appendix A.
**Related:**
- [`KICKOFF_REQUIREMENTS.md`](KICKOFF_REQUIREMENTS.md) v0.2 + the `kickoff/` slices — the input
  classes (F/G/H/I/A–E), provisioning states, and FR-X machinery this doc adds the **human
  dimension** to
- `docs/design-princples/DATA_MODEL_AND_RETROSPECTIVE.md` — the two human bookends (this doc
  generalizes them into a full role map)
- CLAUDE.md "Generation Scope & Priority" — the bucket separation (tier D refines the bucket-4
  boundary)

---

## 0. Planning Insights (Self-Reflective Update)

> v0.1 was drafted assumption-first, then grounded against the SDK/demo-repo prior art (two
> read-only sweeps: roles/approval mechanisms; exemplar ladder + artifact-form coverage). Key
> corrections:

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| `roles.yaml` is reusable role infrastructure | It's a ContextCore **PersonaManifest** (`contextcore-demo-retail/personas/roles.yaml`): 12 *operating personas* with narratives, pain points, `business_kpis`, `contextcore_persona` mapping — and **no generator consumes it** | FR-J1 distinguishes **delivery roles** (this doc — who builds) from **operating personas** (roles.yaml — who runs/uses); the registry adopts the manifest *format family*, not the file |
| No approval schema exists anywhere in the SDK | **`ChunkState`** (`contractors/artisan_models.py:234–263`) already models `DRAFT → IN_REVIEW → APPROVED/REJECTED` with `author`, `reviewer`, `approved_at` and a validator enforcing approved_at ⇒ APPROVED (**one-directional only** — CRP R1 verified `APPROVED` with `approved_at=None` passes today) — but it lives in the **ON-HOLD artisan tree** and has no `approved_by` identity | **FR-J3 narrowed**: lift the ChunkState shape out of artisan + add an `approved_by` ActorReference; don't invent a new state machine. Doc-side disposition prior art: the CRP Appendix A/B pattern and `architectural_review_log_workflow.py` triage decisions (ACCEPT/REJECT + rationale, no identity) |
| Exemplar maturity ladder ≈ tier-R approval semantics | The ladder is **3 persisted levels** (VALIDATED → CONFIRMED → INVARIANT) + TEMPLATE meta-level (`exemplars/registry.py:95–139`, `template_promoter.py:176–265`) and promotion is **fully automatic** (run-count + fingerprint; zero human steps). The registry IS generic enough for non-code artifacts (fingerprint + tuple) | **FR-J5 reframed**: maturity (automatic, evidence-based) and approval (human, recorded) are **orthogonal axes**. Tier R = high maturity **AND** recorded approval — the approval bit is the new thing this doc adds; the ladder is reused as-is |
| Reviewable-form coverage unknown (OQ-6) | Measured: **8/24 artifacts have .md companions** (postmortem summary, batch summary, semantic-compliance, SA triage, FDE explanation/preflight, runbooks), 9 YAML-readable, **7 JSON-only** (kaizen-metrics, kaizen-suggestions, lessons, run-provenance, onboarding-metadata, observability-quality, artifacts index). Onboarding portal = Grafana JSON only (HTML never implemented) | **FR-J2 becomes a concrete backlog** (the 7 JSON-only artifacts + the portal gap), not an abstraction. OQ-6 resolved |
| Human gates don't exist in the pipeline | Two **TTY boolean confirmations** exist (seed-quality gate `pipeline/seed_quality.py:77–114`; run confirmation, REQ-CDP-INT-010) — boolean only, no audit | FR-J3 gains concrete wiring points: the existing confirmations are the first gates to convert to recorded approvals |
| Agent roles (lead/drafter) might offer a role abstraction to mirror | They're **ad-hoc strings** per workflow (`prime_contractor.py:2614–2626`) — no registry | The FR-J1 registry is the *first* role abstraction; note it may later serve agent roles too |

**Resolved open questions:**
- **OQ-1 → PARTIALLY RESOLVED.** The recording *schema* is the lifted ChunkState shape +
  `approved_by: ActorReference{id, role, email?, timestamp}`; identity *resolution* anchors on
  `metadata.owners` (team mode) with git identity as the solo-mode default. Remaining: signature
  strength (plain field vs signed).
- **OQ-6 → RESOLVED.** Coverage measured (see table above); FR-J2 lists the JSON-only backlog.

---

## 1. Problem Statement & Thesis

### 1.1 The thesis

Software delivery contains two fundamentally different kinds of work:

1. **Translation work** — turning business language into technical inputs (requirements →
   architecture → design docs → schemas → tests). This is **well-suited to LLM generation as
   input and thoughtful deterministic projection as output**, with humans validating and
   enhancing the result.
2. **Uniquely human work** — judgment that draws on understanding of *humans and the world*:
   what the business actually needs, what users will accept, what matters more when goals
   conflict, what "good" looks like to a customer. This **cannot be synthesized** by LLMs or
   deterministic logic. It enters the process in exactly two forms: as **key inputs** (the
   things only a human can supply) and as **validation/enhancement points** (the things only a
   human can approve).

The **Human-in-the-Middle (HITM) operating model** organizes the build process around this
split: generation does the translation; named human roles supply the uniquely human inputs and
hold the validation points; **every artifact exists in a human-reviewable form**.

### 1.2 What exists today / gap

| Component | Current state | Gap |
|-----------|---------------|-----|
| Input classes + provisioning states | Kickoff doc set (F/G/H/I/A–E, `authored\|placeholder\|absent`, FR-X machinery) | No mapping from inputs to the **human roles** that author/validate them |
| Human bookends | DATA MODEL (front) + RETROSPECTIVE (back) principle | Only two points; the middle roles (BA→QA) are undocumented |
| Generation pipeline | plan ingestion → prime contractor → repair → postmortem; $0 deterministic cascade | Validation is LLM-review (convergent review, review phase) — **no named human validation gates**, no approval recording |
| Reuse | ExemplarRegistry maturity ladder (candidate→…→template) for code exemplars | No equivalent **approved-for-reuse** concept for requirements/architecture/test artifacts (tier R) |
| Business targets | Group E `businessTargets` collected intent-first | No "estimate vs human decision" distinction (tier E) |
| Content boundary | FR-G3: SDK never authors bucket-4 content | Too absolute for UAT: business-critical content **should** be LLM-draftable *for validation only* (tier D) |
| Artifact forms | Mixed: some artifacts have .md summaries (postmortem, kaizen trends), many are JSON-only | No requirement that every artifact carries a human-reviewable form |

### 1.3 Goal

Produce, for each classic software role, **the key assets that role needs to perform its job**
in a HITM operation — and organize all project inputs so later phases can **expand the
automation boundary** (more deterministic generation, more LLM-drafted business logic) while
humans remain the source of uniquely human inputs and the holders of validation points.

---

## 2. The Authorship-Tier Taxonomy

Every project input/artifact is classed by **who can author it and what role machines play**.
Ordered by human involvement (most → least):

| Tier | Name | Rule | Example |
|------|------|------|---------|
| **U** | Uniquely human | Cannot be synthesized; supplied only by a human. These are the HITM *inputs* and *validation acts* themselves | Customer's actual goals; acceptance ("this is what I meant"); priority calls between conflicting goals; the RETROSPECTIVE judgment |
| **E** | Estimable, human-authoritative | Machines MAY estimate as a **pre-fill**, clearly flagged `estimate`; the human decision is authoritative and recorded; an estimate is never silently promoted | Business KPIs / targets (Group E); cost budgets; SLO targets |
| **D** | Draft-for-validation only | Business-critical content MAY be LLM-drafted **solely** for end-user acceptance validation and fine-tuning; **never production** without explicit human approval after acceptance | Real value summaries/pitches, customer-facing copy (bucket 4) |
| **G** | Generate-and-validate | The default translation mode: LLM generates from business language and/or deterministic logic projects from contracts; a named human role validates/enhances | Requirements drafts, architecture options, design docs, schemas, tests |
| **R** | Reuse-approved | Previously reviewed, validated, and **approved-for-reuse** artifacts; deterministically instantiated; reuse skips re-validation (a recorded fit-check + provenance suffice) | Common requirement patterns, standard architecture stacks, CRUD scaffolds, standard test suites |

**Classification rules (CRP R1):**
- Tier is **single-valued per FR-X5 inventory entry at a point in time**. It is a **current
  state**, not a permanent label: the FR-X5 row holds the current value; prior values and the
  evidence for any change are preserved in the FR-J8 ledger (FR-J4).
- **Composite artifacts** take the tier of their *authoritative* content; mixed-judgment
  artifacts (e.g. `plan.md` = U sequencing judgment + G skeleton) are classed by their
  human-decision core.
- **E/D discriminator:** E covers decision **values** (numbers/targets) that machines may
  pre-fill; D covers business-critical **content/prose**. An LLM-drafted KPI *rationale* is D
  prose attached to an E value — recorded as two inventory entries.
- **Class M — machine evidence (CRP R1).** Telemetry, postmortem, and provenance artifacts
  (`kaizen-metrics.json`, `run-provenance.json`, postmortem reports, …) are machine-authored,
  human-consumed, and validated **in aggregate** at the QA sign-off gate — never per-artifact.
  They are class M, outside the U–R ladder; FR-J1's registry maps them to the QA aggregate gate,
  not to individual validators (no fake per-artifact ceremony).

The **automation boundary** is the current tier assignment per asset. The expansion direction is
always **toward R** — toward *less* human effort (G→R as patterns prove out; U→E as estimation
improves) but **never** past the floor: U-tier acts and D-tier approval stay human permanently.
*(Directional note, CRP R2: the table is ordered most-human at top; "expansion" always means
moving toward the bottom of the table — toward R — never toward U.)*

---

## 3. The Role Map

For each role: mission, key assets (what they need / what they produce), the generation split,
and the human validation point. Kickoff input classes in parentheses.

### 3.0 Customer / Product Owner (CRP R1 — the U-tier holder)

- **Mission:** the source of the uniquely human inputs the whole model exists to capture —
  actual business goals, **acceptance** ("this is what I meant"), priority calls between
  conflicting goals, and the end-user acceptance FR-J7's tier-D promotion requires.
- **Consumes:** the running application, UAT/draft content, the BA's requirements drafts.
- **Key assets:** the goal description (the BA's raw input); acceptance sign-offs; priority
  decisions; tier-E final decisions (KPI targets are *theirs*, estimated or not).
- **Generation split:** none — this role is pure tier U. Machines may *present* (UAT
  environments, draft content, estimate pre-fills); they never substitute.
- **Validation point:** acceptance sign-off on UAT/draft-for-validation content (the FR-J7
  promotion gate) and on requirement priority. Without this role named, the model's most-human
  tier had no holder.

### 3.1 Business Analyst (BA)

- **Mission:** turn the customer's description of business goals into the **requirements
  document** — the primary initial input of the whole pipeline.
- **Consumes:** customer conversations, business goals, domain knowledge (U).
- **Key assets:** `requirements.md` (the Stage-2 INIT source); business-goal → requirement
  traceability; Group E target candidates.
- **Generation split:** LLM drafts requirements from a transcribed/structured goal description
  (G); POLISH structure checks are the deterministic aid; the *understanding of what the
  customer actually means* is U.
- **Validation point:** BA approves the requirements doc before it enters the pipeline; BA owns
  reconciling LLM-drafted requirements against customer intent.

### 3.2 Project Manager (PM)

- **Mission:** the **high-level implementation plan** (`plan.md`), sequencing, increments.
- **Consumes:** requirements doc; team/capacity/timeline realities (U).
- **Key assets:** `plan.md` (Stage-2 INIT source); batch/increment decomposition; cost budget
  (I); risk register (`spec.risks[]`).
- **Generation split:** plan skeleton + decomposition draftable from requirements (G); the
  feasibility, sequencing-by-business-priority, and stakeholder management are U.
- **Validation point (two distinct acts — CRP R2):** (a) **pre-first-run gate** — PM approves
  `plan.md` + initial budget before the first run; hash-bound (FR-J3), so it re-triggers only
  when the plan/budget content changes, never on every run; (b) **ongoing ledger stewardship**
  — PM reviews and approves boundary-expansion ledger entries (FR-J8) as evidence accumulates,
  per-entry-proposal cadence, independent of the plan gate.

### 3.3 Architect

- **Mission:** requirements → **technical architecture**: persistence + display frameworks,
  front-end/back-end languages, the contract.
- **Consumes:** requirements; non-functional constraints; organizational standards (R candidates).
- **Key assets:** the convention manifest (H — framework/ORM/module paths/naming); the data-model
  contract `schema.prisma` (F — the front bookend); language/stack declaration (I);
  architecture decision records.
- **Generation split:** architecture *options* with trade-offs are LLM-draftable (G); standard
  stacks are tier R (the all-Python FastAPI+SQLModel+HTMX stack is an approved-for-reuse
  architecture); the *choice* for this business, and the contract design, are U/E.
- **Validation point:** Architect approves the convention manifest + contract before the first
  cascade run — this **is** the DATA MODEL bookend, generalized.

### 3.4 Backend Developer

- **Mission:** requirements + architecture → **technical design docs/specs** → implementation
  (models/controllers/services — the "MVC etc.").
- **Key assets:** design docs / specs (the spec-builder's spec is the machine analog); the
  generated backend (bucket 1 — `generate backend`, $0); integration glue (bucket 3).
- **Generation split:** bucket 1 is deterministic from the contract (R-like); specs and bucket-3
  glue are G (lead/drafter); judging whether the design *serves the requirement* is U.
- **Validation point:** reviews generated specs + integration diffs in human-reviewable form;
  approves escalations the repair pipeline can't close.

### 3.5 Frontend Developer

- **Mission:** requirements → design docs → **display logic**.
- **Key assets:** `views.yaml` + `pages.yaml` (F/G classes); view archetype selections; the
  generated views (bucket 1); display/UX judgment (U).
- **Generation split:** composite views/forms/lists deterministic from contract (R/G); *whether
  the display serves the user* — flow, emphasis, comprehension — is U.
- **Validation point:** approves two **named artifacts** (CRP R1 — judgments need artifact
  forms): the view manifests (`views.yaml`/`pages.yaml` diff) and a **rendered-page snapshot
  set** generated per run — not an unanchored "rendered output against user expectations."

### 3.6 DBA

- **Mission:** design docs → **schema scripts**: tables, indexes, triggers, migrations.
- **Key assets:** the contract (`schema.prisma`) as the single source; generated
  tables/migrations ($0); index/performance tuning inputs; data-lifecycle policies.
- **Generation split:** schema/table/CRUD generation is deterministic (R); index strategy and
  growth/performance judgment from production knowledge is U/E.
- **Validation point:** approves the contract's persistence projection + migration scripts
  before they run against a real database.

### 3.7 Network Admin / Ops

- **Mission:** requirements + deployment inputs → **environments + deployment**.
- **Consumes:** deployment targets from business requirements / project plan (where this runs);
  org infra standards (R).
- **Key assets:** `app.yaml` scaffold manifest (container/env/WAL — F); `.env.example`;
  `pipeline.env` (I); observability provisioning inputs (A–E: receivers, runbook base,
  dashboards); environment definitions.
- **Generation split:** scaffold + observability artifacts are deterministic/G; *where and how
  this should actually run* (compliance, cost, org reality) is U/E.
- **Validation point:** approves environment definitions + receiver targets before deploy;
  owns the credential-presence checklist (FR-I6).

### 3.8 Testing Engineer

- **Mission:** **tests from business requirements** (not from the implementation).
- **Key assets:** acceptance criteria per requirement; generated contract/completeness tests
  (deterministic — `test_emitter`); requirement-driven test specs (G); a **requirement→test
  traceability matrix** (requirement ID → test IDs — a generated artifact, CRP R1; part of the
  FR-J9 kit); the *which-failures-matter-to-the-business* judgment (U).
- **Validation point:** approves the **traceability matrix** — the named artifact form of "the
  test set actually covers the business requirements," the judgment a coverage number can't
  make.

### 3.9 QA

- **Mission:** **test scripts, execution, captured results**.
- **Key assets:** runnable test scripts (G/R); execution runs (deterministic); result capture
  (postmortem/kaizen reports — already machine-produced); the *accept/reject* call and
  regression triage (U).
- **Validation point:** QA's sign-off on a run's results is the last gate before the
  RETROSPECTIVE bookend; QA validates that captured results match observed reality. QA's
  aggregate sign-off is also where **class-M machine evidence** (§2) is validated — telemetry
  and postmortem artifacts are reviewed in aggregate here, never per-artifact.

### 3.10 Security (CRP R1)

- **Mission:** uniquely human security judgment — risk acceptance, override decisions,
  compliance interpretation.
- **Consumes:** threat/compliance context (U); the SDK's automated security verdicts.
- **Key assets:** Security Prime gate verdicts (`GateVerdictReport` — already machine-produced);
  credential-policy inputs (FR-I6 presence checklist shares ownership with Ops); security
  contract derivations (`security_prime/contract.py`).
- **Generation split:** detection/scoring is automated (Security Prime, `verify_file()`); the
  *override and residual-risk acceptance* is U — risk appetite is a judgment about the world.
- **Validation point:** approves security-gate overrides and accepts residual risk. The SDK
  ships this gate in code today with no named human holder — an FR-J3 wiring point hiding in
  plain sight; unowned overrides become impossible once wired.

---

## 4. Requirements (Group J — HITM role model)

- **FR-J1 — Role–artifact registry.** Every pipeline-relevant artifact and kickoff input MUST
  map to (a) a producing role analog (which role's work the generation replaces/assists) and
  (b) a **validating human role**. The §3 role map is the registry's seed; the registry extends
  the FR-X5 per-project inventory with `role` and `validated_by` columns. **Scope note (from
  planning):** this registry covers *delivery roles* (who builds); ContextCore's PersonaManifest
  (`roles.yaml`) covers *operating personas* (who runs/uses the result) — adopt its format
  family for compatibility, do not merge the two. The registry is the SDK's first role
  abstraction; agent roles (lead/drafter — today ad-hoc strings) MAY later register in it.
  **Scope (CRP R1):** "every pipeline-relevant artifact" means inputs + human-validated outputs;
  class-M machine evidence (§2) maps to the QA aggregate gate, never to per-artifact validators.
  **Column-extension note (CRP R2):** `role`/`validated_by` extend the kickoff master's settled
  FR-X5 column set — extensions are append-only with defaults for existing rows, cite the
  master's schema, and are decided with kickoff OQ-1/OQ-2 (the same schema-governance question).
- **FR-J2 — Human-reviewable form, always.** Every generated artifact MUST exist in a form a
  human in the validating role can review without tooling (markdown, rendered report, diagram
  — not raw JSON). Where the machine form is canonical (JSON/YAML), a derived review form is
  generated alongside it. **Measured starting point (planning):** 8/24 artifacts already have
  .md companions; the **JSON-only backlog** is: `kaizen-metrics.json`,
  `kaizen-suggestions.json`, `prime-postmortem-lessons.json`, `run-provenance.json`,
  `onboarding-metadata.json`, `observability-quality.json`, the observability artifacts index —
  plus the onboarding portal (Grafana-JSON-only; the declared HTML form was never implemented).
  YAML artifacts (alerts/SLOs/monitors/policies) count as reviewable as-is.
- **FR-J3 — Named validation points with recorded approval.** Each §3 validation point is a
  defined gate: what is approved, by which role, in which artifact form. Approvals are
  **recorded** (who/when/what-hash) with the same provenance machinery as FR-X4; an unapproved
  gate is visible state, not an error (graceful degradation per FR-X3 unless the criticality
  matrix says otherwise). **Schema (from planning — reuse, don't invent):** lift the
  `ChunkState` approval shape out of the ON-HOLD artisan tree
  (`artisan_models.py:234–263`: `DRAFT → IN_REVIEW → APPROVED|REJECTED`, `approved_at` enforced
  by validator) and add **`approved_by: ActorReference{id, role, email?, timestamp}`** — the
  identity field it lacks. **Validator correction (CRP R1/R2 — verified):** the source validator
  is one-directional (`approved_at` ⇒ APPROVED; an APPROVED record with `approved_at=None` is
  valid today). The lifted model MUST add the reverse implication for **both** fields: status
  `APPROVED` requires non-null `approved_at` **AND** non-null `approved_by` — a who-less or
  when-less "approval" fails validation. Identity resolution anchors on `metadata.owners` (team
  mode) with git identity as the solo-mode default; **solo-mode self-approval** (approver ==
  author) is valid but logged distinctly (`solo_mode: true`) so audit consumers can tell
  self-approval from second-party review (CRP R2 adversarial).
  **The binding gate rule (CRP R1 — resolves OQ-4):** an approval binds to an **artifact
  version** (the recorded what-hash) and persists until the hash changes; gates are evaluated
  **lazily at consumption** — when a downstream phase reads the gated artifact — where the
  FR-X3 matrix decides block-vs-warn. Unchanged approved artifacts never re-prompt; a content
  change re-opens exactly that gate. Cadence is therefore **per-change**, not per-run or
  per-increment — neither stop-the-world nor decorative. (Inherits FR-X3's co-deployment
  dependency on the FR-E1 matrix — kickoff master OQ-4.)
  **Unattended path (CRP R1):** when a gate passes non-interactively (`config.yes`,
  `CDP_PROCEED_ON_LOW_QUALITY` — both exist in `handle_seed_quality_gate`,
  `pipeline/seed_quality.py:77+`), the record is a **non-approval `unattended-override`** naming
  the authorizing flag/env var — never a synthesized ActorReference. Pre-seeded approvals (the
  `question-answers.yaml` analog) MAY carry a real ActorReference.
  **First wiring points:** the two existing TTY boolean confirmations (seed-quality gate, run
  confirmation — REQ-CDP-INT-010) convert from unaudited booleans to recorded approvals; third:
  **Security Prime gate overrides** (§3.10) — the automated gate that exists in code today with
  no named human holder.
- **FR-J4 — Tier classification is part of the inventory.** Every input/artifact carries its
  §2 tier (U/E/D/G/R, or class M) in the FR-X5 inventory; the FR-X1 pre-flight report shows
  tier alongside provisioning status. The tier value is the **current state** (mutable; §2
  classification rules); tier changes (boundary expansion) are explicit, recorded events —
  never silent — with prior values preserved in the FR-J8 ledger. The `tier` column follows the
  same FR-X5 column-extension note as FR-J1 (CRP R2).
- **FR-J5 — Tier R reuse library.** Approved-for-reuse artifacts are held in a registry reusing
  the ExemplarRegistry pattern — fingerprint lookup + the **actual** maturity ladder
  (VALIDATED → CONFIRMED → INVARIANT, + TEMPLATE meta-level; promotion automatic on cross-run
  evidence, `registry.py:95–139`). **Two orthogonal axes (the planning correction):** *maturity*
  is automatic and evidence-based (the ladder, unchanged); *approval* is human and recorded
  (FR-J3) — **tier R requires both** (maturity ≥ CONFIRMED **and** a recorded approval). The
  approval bit is the new addition; today's ladder has zero human steps, so high maturity alone
  never confers tier R. The registry's fingerprint+tuple structure is generic — requirements/
  architecture/test artifacts ride the same mechanism as code exemplars.
  **Reuse-path boundary (CRP R1/R2 — verified):** `ExemplarRegistry.lookup()` today reuses at
  maturity ≥ 1 with zero approvals (`registry.py:65–83`). Decision: **code exemplars are
  grandfathered** — the existing lookup is bucket-1/3 *internal* generation reuse, not
  HITM-governed, and is unchanged. **All other artifact classes riding the registry
  (requirements/architecture/test — anything HITM-governed) require the full tier-R gate**
  (maturity ≥ CONFIRMED + recorded approval) — explicitly including non-code classes, so the
  "generic mechanism" sentence can never be read as extending the maturity-≥1 threshold to
  them. Name↔level pin: 1 = VALIDATED, 2 = CONFIRMED, 3 = INVARIANT (the code has numeric
  levels only).
  **Fit-check (CRP R2 — defined, not just promised):** reusing an R artifact skips
  re-validation but MUST emit a `FitCheckRecord{artifact_id, reuse_target_id, score, passed,
  checked_at, checked_by?}` persisted alongside the approval provenance. The check is
  machine-executed by default; a **failing** fit-check routes to re-validation — never silent
  fallback to a lower-maturity/unapproved artifact. Reuse is the high-frequency path; its audit
  trail matters more than the full-approval path's.
- **FR-J6 — Tier E estimates are pre-fills — and the expected default mode** *(strengthened per
  the 2026-06-05 operator decision, Q7)*. Machine-estimated values (KPIs, budgets, targets, rule
  parameters) carry provenance `estimate`; the FR-X1 report and the role's review form show them
  as estimates; promotion to `authored` happens only by recorded human decision. **LLM-drafted
  sample/starter values are the intended default**, not an optional nicety: tier-E inputs ship
  to humans pre-filled with reasonable starters for the human to approve/adjust — never as blank
  fields. An estimate is never silently used where the criticality matrix requires an authored
  value.
  **Kickoff-enum integration (CRP R1 — extends the settled FR-X4 mapping, R1-F-master-3):**
  `estimate` joins the FR-X4 provenance enum with status mapping → **`placeholder (estimate)`**
  — never `authored`; estimates do **not** count toward the `input_provisioning_score`
  numerator until promoted by a recorded decision (only `authored` counts — explicit, so the
  score the enum exists to keep honest can't be inflated by pre-fills).
- **FR-J7 — Tier D draft-for-validation (refines FR-G3).** Business-critical content MAY be
  LLM-drafted with status **`draft-for-validation`** — usable ONLY in acceptance-validation and
  fine-tuning contexts (UAT environments, review sessions), structurally blocked from
  production paths. Promotion to `authored` requires explicit human approval recorded per
  FR-J3 after end-user acceptance (the §3.0 Customer/PO gate). FR-G3's "MUST NOT generate real
  company content" is hereby scoped to *production use*: drafting for validation is allowed;
  unapproved production use remains prohibited.
  **"Production path" defined (CRP R1 — the SDK never sees deployment, so enforcement lives
  where the SDK reaches):** (a) **runtime** — the generated app's render/serve layer refuses
  (or watermarks) `draft-for-validation` content unless an explicit UAT-mode flag is set
  (default-deny, deterministic, $0); (b) **pipeline** — VALIDATE/export excludes draft-status
  content from export packages. Deployment-environment detection is explicitly out of SDK
  reach — that is *why* enforcement must live in the generated app.
  **Status carrier (CRP R1 — closes the render-strip loophole):** because FR-G1 makes
  front-matter render-strip normative, draft status MUST use the **sidecar form** (the
  `pages.yaml` entry status field) — stripped front-matter leaves the runtime gate nothing to
  check.
  **Group-G interaction (CRP R1):** in FR-G2 scoring, drafts count as non-authored (distinct
  from `placeholder` in the FR-X1 report); FR-G3's write-block keys on `authored`, so drafts
  remain machine-writable **by design** — promotion to `authored` flips the write-block on.
  **Rejected terminal state (CRP R2):** end-user rejection (a recorded human act per FR-J3,
  the `REJECTED` analog of the lifted ChunkState) transitions content to **`draft-rejected`**
  — terminal: never re-served, never exported, excluded from FR-G2 scores. The rejected draft
  MAY be discarded or replaced by a new draft, which restarts the validation cycle. Without
  this, user-rejected content sits in `draft-for-validation` indefinitely, eligible to be
  re-served.
- **FR-J8 — Boundary-expansion ledger.** The current automation boundary (tier per asset) and
  its planned movements are recorded in a reviewable ledger owned by the PM role. Each movement
  names: the asset, from-tier → to-tier, the evidence (e.g. N successful validated runs), and
  the approving role. Movements only travel toward less human effort when evidence supports it;
  U-tier acts and D-tier approval never move.
  **Pending entries block (CRP R2 — "recorded" is not enough):** a ledger entry without a PM
  approval record (FR-J3) does NOT take effect — the first pipeline stage that would *consume*
  the new tier classification checks for an approved entry (the same lazy-consumption model as
  FR-J3's gate rule) and reports `gate-pending` rather than silently using the new tier. The PM
  gate on boundary expansion is the model's safeguard against autonomous automation creep; it
  must actually block.
- **FR-J9 — Role asset kits.** For each §3 role, the SDK/pipeline provides the role's **kit**:
  the templates, generated drafts, review forms, and validation checklists that role needs to
  perform its job (e.g. BA: requirements template + POLISH report; Architect: convention
  manifest template + contract scaffold + ADR template; Testing Engineer: the requirement→test
  traceability matrix; QA: run report + sign-off form). Kits are tier-R candidates themselves.
  **Kit completeness (CRP R2 — acceptance criteria):** a kit is complete only when it contains
  at minimum (a) a generated-draft template, (b) a review checklist, and (c) the named
  validation artifact for that role's §3 gate; the FR-X1 pre-flight report carries a
  kit-completeness field per role. OQ-5 narrows to the *format* decision only (docs vs CLI vs
  per-project generated), which must be resolved before kit implementation begins.

---

## 5. Non-Requirements

- **Not an org chart.** Roles are *functions*, not headcount — one human may hold many roles
  (solo-founder mode collapses all roles onto one person without changing the gates).
- **No autonomous approval.** Nothing in this doc lets generation approve its own output; LLM
  review (convergent review, review phases) is quality assistance, never a substitute for a
  named human validation point.
- **Does not change the bucket separation or the $0 deterministic model** — it adds the human
  dimension on top.
- **Does not build workflow/HR tooling** (assignment, notifications, SLAs) — only the artifact
  and recording requirements.
- **Does not mandate ceremony.** Gates are visible state, not stop-the-world meetings; the
  criticality matrix (FR-X3) decides what hard-gates.

---

## 6. Open Questions

1. ~~**OQ-1 — Approval signature strength.**~~ **CLOSED as moot (2026-06-05 operator decision,
   Q6):** follows from OQ-2's de-scope — plain fields wherever approvals happen to be recorded;
   git history is the tamper-evidence; revisit only if a multi-party/compliance context
   materializes. Considered, not missed.
2. ~~**OQ-2 — Where approval records live.**~~ **CLOSED (2026-06-05 operator decision, Q2):
   operator-coordinated** — durable approval-store machinery was CRP-induced
   over-formalization; the operator coordinates record-keeping and ensures delivery when a real
   need arises. The FR-J3 schema remains available to gates that want it; nothing ships
   proactively.
3. ~~**OQ-3 — Tier D scope.**~~ **RESOLVED (2026-06-05 operator decision, Q7): content-only,
   with LLM-drafted starter VALUES as tier E's default mode.** Tier D governs business-critical
   content/prose. Business-critical *values* (KPI targets, thresholds, rule parameters) are tier
   E where **LLM-drafted sample/starter values are the expected default** — LLM drafts, human
   approves (FR-J6). Business-critical *logic* is not tier-D-eligible: it decomposes into
   tier-E values + deterministic computation; residual bucket-3 glue keeps its review+test
   gates.
4. ~~**OQ-4 — Validation cadence.**~~ **RESOLVED (CRP R1):** cadence is **per-change** — the
   hash-bound lazy gate rule in FR-J3 (approval binds to artifact version, evaluated at
   consumption; unchanged artifacts never re-prompt). Neither per-run ceremony nor decorative.
5. ~~**OQ-5 — Role kit format.**~~ **RESOLVED (2026-06-05 operator decision, Q8): docs-first.**
   Kits are markdown templates/checklists in `docs/` plus the components that already exist
   (POLISH report for BA, FDE preflight/explanation .md for ops, SA triage .md, the industry
   defaults doc + team request list for the business side). A `startd8 kit <role>` CLI is the
   natural v2 once kits stabilize (the `startd8 wireframe` advisory-CLI precedent) — not built
   now. **Deferred-phase requirements drafted:**
   [`kickoff/ROLE_KIT_CLI_REQUIREMENTS.md`](kickoff/ROLE_KIT_CLI_REQUIREMENTS.md) (v0.1 —
   FR-KIT-1…9, activation criteria + the planning-pass checklist the implementing project runs).
6. ~~**OQ-6 — Existing artifact review-form coverage.**~~ **RESOLVED (planning):** measured —
   8/24 .md-paired, 9 YAML-readable, 7 JSON-only; the backlog is enumerated in FR-J2.

---

*v0.3 — Post-CRP triage: 21 suggestions applied (Appendix A), 0 rejected. 11 roles mapped
(Customer/PO + Security added), 5 authorship tiers + class M, 9 Group-J requirements
(substantially hardened), OQ-4 resolved (per-change cadence), OQ-5 narrowed.*

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
| R1-F1 | Tier classification rules (single-valued, composite rule, E/D discriminator) | R1 (opus); endorsed R2 | §2 classification-rules block; KPI rationale = D prose + E value, two entries | 2026-06-05 |
| R1-F2 | Machine-evidence class for telemetry artifacts | R1 (opus) | §2 class M (aggregate validation at QA gate); FR-J1 scope sentence; §3.9 QA note | 2026-06-05 |
| R1-F3 | Hash-bound lazy gate rule (binding rule; resolves OQ-4) | R1 (opus); endorsed R2 | FR-J3 binding-gate-rule paragraph; OQ-4 marked resolved; FR-E1 dependency noted | 2026-06-05 |
| R1-F4 | Unattended path = `unattended-override`, never synthesized approval | R1 (opus); endorsed R2 | FR-J3 unattended-path paragraph (config.yes / CDP_PROCEED_ON_LOW_QUALITY named) | 2026-06-05 |
| R1-F5 | Reverse implication in lifted validator; correct §0 "⇔" overstatement | R1 (opus); endorsed R2 | FR-J3 validator-correction (with R2-F7); §0 table corrected to "⇒ one-directional" | 2026-06-05 |
| R1-F6 | Define "production path" + two enforcement points | R1 (opus) | FR-J7: generated-app render/serve gate (default-deny, UAT flag) + VALIDATE/export exclusion; deployment out of SDK reach stated | 2026-06-05 |
| R1-F7 | `draft-for-validation` × FR-G1/G2/G3 interaction; sidecar form mandatory | R1 (opus) | FR-J7 status-carrier + Group-G-interaction paragraphs | 2026-06-05 |
| R1-F8 | `estimate` integration with the settled FR-X4 enum/mapping/score | R1 (opus) | FR-J6: status mapping `placeholder (estimate)`; numerator = `authored` only | 2026-06-05 |
| R1-F9 | Add Customer/Product Owner role (the U-tier holder) | R1 (opus); endorsed R2 | New §3.0; FR-J7 promotion gate now names it | 2026-06-05 |
| R1-F10 | Add Security role (Security Prime override gate) | R1 (opus) | New §3.10; third FR-J3 wiring point | 2026-06-05 |
| R1-F11 | Artifact forms for §3.5/§3.8 (snapshot set; traceability matrix) | R1 (opus) | §3.5 + §3.8 named artifacts; matrix added to §3.8 key assets + FR-J9 kit | 2026-06-05 |
| R1-F12 | Reconcile FR-J5 with registry's maturity-≥1 lookup; pin level names | R1 (opus); endorsed R2 | FR-J5 reuse-path boundary: code exemplars grandfathered; HITM-governed classes need full gate; 1=VALIDATED/2=CONFIRMED/3=INVARIANT pinned | 2026-06-05 |
| R2-F1 | Tier = current state, not static ordinal | R2 (sonnet) | §2 classification rule (b) + FR-J4 "current state" wording | 2026-06-05 |
| R2-F2 | FitCheckRecord schema + failure mode + performer | R2 (sonnet) | FR-J5 fit-check paragraph (machine-executed default; failure → re-validation, never silent fallback) | 2026-06-05 |
| R2-F3 | `draft-rejected` terminal state for tier D | R2 (sonnet) | FR-J7 rejected-terminal-state paragraph (never re-served/exported/scored) | 2026-06-05 |
| R2-F4 | FR-X5 column-extension protocol | R2 (sonnet) | FR-J1 + FR-J4 extension notes (append-only, cite master schema, decided with kickoff OQ-1/OQ-2) | 2026-06-05 |
| R2-F5 | Split PM validation point (pre-first-run gate vs ledger stewardship) | R2 (sonnet) | §3.2 validation point split into two cadence-distinct acts | 2026-06-05 |
| R2-F6 | FR-J9 acceptance criteria (kit completeness minimums) | R2 (sonnet) | FR-J9 completeness criteria + FR-X1 kit-completeness field; OQ-5 narrowed to format | 2026-06-05 |
| R2-F7 | `approved_by` also non-null on APPROVED | R2 (sonnet, adversarial) | Merged into FR-J3 validator correction with R1-F5 (both fields required) | 2026-06-05 |
| R2-F8 | Pending ledger entries block downstream effect | R2 (sonnet, adversarial) | FR-J8 blocking paragraph (`gate-pending` at consumption) | 2026-06-05 |
| R2-F9 | Fix directional metaphor (downward vs toward-R) | R2 (sonnet, adversarial) | §2 boundary paragraph: "toward R" + directional note | 2026-06-05 |
| R2-adv-5 | Solo-mode self-approval logged distinctly | R2 (sonnet, adversarial prose item 5) | FR-J3: `solo_mode: true` flag on self-approval records | 2026-06-05 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-05

- **Reviewer**: claude-opus-4-8-1m (Claude Opus 4.8, 1M context)
- **Date**: 2026-06-05 (UTC)
- **Scope**: First CRP round on the HITM role model; the five focus asks answered first; code anchors spot-verified read-only (`artisan_models.py`, `exemplars/registry.py`, `cap-dev-pipe/pipeline/seed_quality.py`, `prime_contractor.py`); kickoff master + Group-G slice (post-triage v0.2) read for composition checks.

##### Focus-file asks

**Ask 1 — Tier taxonomy soundness (U/E/D/G/R)**
- **Summary answer:** Partial — the five tiers are jointly sufficient for *human-consumed* inputs/artifacts but not mutually exclusive without two missing rules, and machine-authored evidence artifacts class into none of them.
- **Rationale:** The tiers mix classification dimensions: U/E/D classify by content authority, G by process mode, R by lifecycle state — so one artifact legitimately holds G now and R later (§2's own expansion direction), and composite artifacts (`plan.md` = U sequencing judgment + G skeleton) hold several at once. The focus example (LLM-drafted KPI rationale) is genuinely ambiguous: the KPI *value* is E, the rationale *prose* is bucket-4-adjacent content → D; no rule in §2 says which dimension wins. Telemetry/evidence artifacts (`kaizen-metrics.json`, `run-provenance.json`, postmortem reports) are machine-authored with no per-run human validation — they are not U/E/D/G/R, yet FR-J1 demands a validating role for "every pipeline-relevant artifact".
- **Assumptions / conditions:** tier is meant to be single-valued per FR-X5 inventory entry (the doc implies but never states this).
- **Suggested improvements:** R1-F1 (discriminator + composite rule + E/D boundary), R1-F2 (evidence-artifact class or FR-J1 scope cut).

**Ask 2 — Gate/ceremony tension (FR-J3 vs §5 vs OQ-4)**
- **Summary answer:** Yes, implementable without stop-the-world or decorative gates — if approval is bound to **artifact versions checked at consumption**, which the doc has all the pieces for but never states as the binding rule.
- **Rationale:** FR-J3 already records `what-hash`; FR-X3 already decides block-vs-warn. The missing rule: an approval attaches to an artifact *version* (hash) and persists until the artifact changes; gates are evaluated **lazily where a downstream phase consumes the gated artifact**, not on a calendar or per-run schedule. Nine roles × every run then collapses to "only what changed since its last approval re-gates" — per-increment cadence emerges naturally (OQ-4 resolves). Decorativeness is avoided because the criticality matrix makes specific consumptions blocking; friction is avoided because unchanged artifacts never re-prompt.
- **Assumptions / conditions:** artifact hashing is available at every gate (true for the cascade manifests via drift headers; needs defining for docs like `requirements.md`).
- **Suggested improvements:** R1-F3 (the binding rule), R1-F4 (the unattended path — verified: `handle_seed_quality_gate` has two non-TTY proceed paths, `config.yes` + `CDP_PROCEED_ON_LOW_QUALITY`, with no human present), R1-F5 (the lifted ChunkState validator is one-directional — verified `artisan_models.py:256–262`: APPROVED with `approved_at=None` passes today).

**Ask 3 — Tier D production-blocking enforceability**
- **Summary answer:** Not enforceable as specified — "production path" is undefined and the SDK cannot see deployment; and yes, the FR-G1 render-strip rule creates a real loophole.
- **Rationale:** The SDK's reach ends at emitted code/content; whether the app serves UAT or production traffic is the user's deployment fact, invisible to the pipeline. "Structurally blocked" is only implementable if the *generated app itself* enforces it (deterministic render/serve gate keyed on status, default-deny without an explicit UAT-mode flag) plus a VALIDATE/export-side exclusion. The loophole: FR-G1 (post-triage) makes front-matter render-strip normative — if `draft-for-validation` lives only in front-matter, it is stripped at generate time and the runtime has nothing left to check; the sidecar form (`pages.yaml` status) is the only carrier that survives to where enforcement must happen.
- **Assumptions / conditions:** "production path" ⊇ default-mode rendering/serving + export packages (proposed definition, R1-F6).
- **Suggested improvements:** R1-F6 (define production path + the two enforcement points), R1-F7 (the FR-G1/G2/G3 three-way status interaction).

**Ask 4 — Kickoff integration (FR-X5/FR-X4/FR-G1 extensions)**
- **Summary answer:** Mostly clean — the FR-X5 column extension composes; but FR-J6 silently extends a **closed, already-triaged enum**, and FR-J7's third status value lands in FR-G1/G2 machinery that was just pinned to two values.
- **Rationale:** Kickoff FR-X4 (post-R1/R2 triage) defines a closed provenance enum (`authored | supplemental:pre-seeded | supplemental:interactive | config-default | templated`/inferred) **and** a normative provenance↔status mapping (applied as R1-F-master-3). FR-J6's `estimate` is a new enum member with no defined status mapping and no `input_provisioning_score` treatment — an estimate that maps to `authored` would inflate the score FR-X4 exists to keep honest. Likewise FR-G1's enum is `placeholder | authored` with a defined FR-G2 denominator; `draft-for-validation` is a third value with undefined score treatment, and FR-G3's accepted write-block (R2-F-cnt-3) keys on `authored` — drafts stay machine-writable, which is correct but currently only by accident. FR-J3's "unless the criticality matrix says otherwise" also inherits FR-X3's co-deployment dependency on FR-E1 (matrix rows are still kickoff master OQ-4) — worth one dependency note.
- **Assumptions / conditions:** the kickoff doc set v0.2 Appendix-A decisions are settled and FR-J must conform to them, not vice versa.
- **Suggested improvements:** R1-F8 (estimate enum + mapping + score rule), R1-F7 (draft-for-validation × FR-G1/G2/G3), and the dependency note inside R1-F3's placement.

**Ask 5 — Role map completeness/realism**
- **Summary answer:** Two roles missing — the **Customer/Product Owner** (the holder of the U-tier acceptance acts) and **Security** — and two §3 validation points are unverifiable as written.
- **Rationale:** §2 tier U is defined by "customer's actual goals; acceptance ('this is what I meant')" and FR-J7 requires "end-user acceptance", yet no §3 role holds those acts: the BA *reconciles against* customer intent but is not its source, so FR-J1 cannot map the acceptance gate to a validating role — the doc's most-human tier has no named holder. Security: the SDK already ships a security gate (Security Prime `GateVerdictReport`/Anzen) with no named human validation point for overrides/risk acceptance — uniquely human judgment by this doc's own definition. Unverifiable points: §3.5 "approves … rendered output against user expectations" and §3.8 "approves that the test set actually covers the business requirements" name no artifact form, so FR-J3's "what is approved, in which artifact form" cannot be instantiated for them (§3.8 needs a requirement→test traceability artifact no FR currently requires).
- **Assumptions / conditions:** "role" = function not headcount (§5), so adding roles costs nothing in solo mode.
- **Suggested improvements:** R1-F9 (Customer/PO role), R1-F10 (Security role), R1-F11 (artifact forms for §3.5/§3.8).

##### Executive summary

- The taxonomy is one discriminator short of sound: E-vs-D and the composite-artifact rule are undefined, and machine-authored evidence artifacts fit no tier while FR-J1 demands they map to a validator.
- The gate model is salvageable from its own pieces: bind approval to artifact-hash versions, evaluate at consumption — OQ-4 resolves to per-change cadence, neither ceremony nor decoration.
- FR-J3's lifted schema has a verified defect inherited from source: the ChunkState validator never requires `approved_at`/`approved_by` when status is APPROVED — an "approved" gate with zero audit record is schema-valid.
- The two named first wiring points both have unattended bypass paths (`config.yes`, `CDP_PROCEED_ON_LOW_QUALITY`); FR-J3 doesn't say what is recorded when no human is present — the largest hole in "recorded approval".
- FR-J7 is unimplementable until "production path" is defined; the only SDK-reachable enforcement point is the generated app's own render/serve gate plus export exclusion, and the FR-G1 render-strip rule forces the sidecar status form.
- Two enum extensions (FR-J6 `estimate`, FR-J7 `draft-for-validation`) land in already-triaged closed kickoff enums without mapping/score rules — the most likely silent-integration breakage.
- The U tier has no role holder: Customer/Product Owner is missing from §3; Security is missing despite an existing in-SDK security gate.
- FR-J5 sets a tier-R bar (≥ CONFIRMED + approval) that the existing registry lookup contradicts (reuses at maturity ≥ 1, zero approvals — verified); the doc must say whether code exemplars are exempt or the lookup changes.

##### Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Data | medium | Add classification rules to §2: (a) tier is **single-valued per FR-X5 inventory entry at a point in time**; (b) composite artifacts take the tier of their *authoritative* content, with mixed-judgment artifacts (plan.md) classed by their human-decision core; (c) the E/D discriminator: E covers decision **values** (numbers/targets) machine-pre-fillable; D covers bucket-4 **content/prose** — an LLM-drafted KPI rationale is D prose attached to an E value, recorded as two inventory entries | "Every project input/artifact is classed by who can author it" gives no rule when authority dimensions conflict; the focus file's KPI-rationale case is undecidable from §2 as written | §2, after the tier table, before the automation-boundary paragraph | A worked-example table of ~10 artifacts (incl. KPI rationale, plan.md, pricing rule) classes identically when assigned independently by two readers |
| R1-F2 | Architecture | high | Resolve the evidence-artifact gap: either add an explicit machine-evidence class (telemetry/postmortem/provenance artifacts — machine-authored, human-consumed, validated **in aggregate** at the QA sign-off gate, never per-artifact) or scope FR-J1's "every pipeline-relevant artifact" to inputs + human-validated outputs | `kaizen-metrics.json`, `run-provenance.json`, postmortem reports fit no U/E/D/G/R tier (G requires a named human validator per artifact); FR-J1 as written forces fake per-artifact gates onto telemetry — the exact ceremony §5 forbids | §2 (new class or carve-out note) + FR-J1 scope sentence | The FR-X5 inventory for a strtd8 run assigns every artifact a tier with zero unclassifiable rows and zero per-run human gates on telemetry files |
| R1-F3 | Architecture | high | State the binding gate rule in FR-J3: an approval binds to an **artifact version** (the recorded what-hash) and persists until the hash changes; gates are evaluated **at consumption** (when a downstream phase reads the gated artifact), where the FR-X3 matrix decides block-vs-warn; re-approval is triggered only by content change. Note the FR-E1 co-deployment dependency (matrix rows = kickoff master OQ-4). This resolves OQ-4: cadence is per-change, not per-run or per-increment | FR-J3 + §5 + OQ-4 currently leave gate timing undefined — the focus file's exact tension; hash-bound lazy evaluation is the only model that is neither stop-the-world (unchanged artifacts never re-gate) nor decorative (matrix-marked consumptions block) | §4 FR-J3 + §6 OQ-4 (mark resolved-by-FR-J3) | Two consecutive runs with an unchanged approved contract: run 1 records the approval, run 2 re-prompts nothing; mutating the contract re-opens exactly that gate |
| R1-F4 | Ops | high | Define the unattended path for converted gates: when a gate is passed non-interactively (`config.yes`, `CDP_PROCEED_ON_LOW_QUALITY` — both exist in `handle_seed_quality_gate`, `pipeline/seed_quality.py:77+`), the record is a **non-approval override** (`unattended-override` + which env/flag authorized it), never a synthesized ActorReference; optionally allow pre-seeded approvals (the `question-answers.yaml` analog) carrying a real ActorReference | FR-J3 names the seed-quality gate as a first wiring point but its non-TTY branches have no human; recording an env-var bypass as an "approval" would forge the audit trail the FR exists to create | §4 FR-J3, after the "First wiring points" sentence | An unattended run past the seed-quality gate produces a record with `override`, the authorizing env var, and **no** `approved_by`; an attended run produces an ActorReference |
| R1-F5 | Interfaces | high | When lifting the ChunkState shape, add the **reverse implication** the source validator lacks: status `APPROVED` MUST require non-null `approved_at` AND `approved_by`. Verified: `artisan_models.py:256–262` enforces only "approved_at ⇒ APPROVED"; a chunk with `status=APPROVED, approved_at=None` is valid today — §0's "approved_at ⇔ APPROVED" overstates the prior art | The lifted schema is the foundation of every FR-J3 gate; without the reverse direction an "approved" gate with zero who/when is schema-valid, silently defeating recorded approval | §4 FR-J3 schema sentence (and correct the §0 table's "⇔" claim) | Pydantic model test: constructing the lifted state with `status=APPROVED` and missing `approved_by` or `approved_at` raises a validation error |
| R1-F6 | Architecture | high | Define "production path" in FR-J7 and name the two enforcement points: (a) **runtime** — the generated app's render/serve layer refuses (or watermarks) `draft-for-validation` content unless an explicit UAT-mode flag is set (default-deny, deterministic, $0); (b) **pipeline** — VALIDATE/export excludes draft-status content from export packages. State explicitly that deployment-environment detection is out of SDK reach, which is why enforcement must live in the generated app | "Structurally blocked from production paths" has no referent: the SDK emits code/content and never sees where it is deployed; without naming the enforcement point the FR is untestable and each implementer will invent one | §4 FR-J7 | Generated-app test: a page with draft status returns the block/watermark in default mode and renders under the UAT flag; export package contains no draft-status content |
| R1-F7 | Data | high | Specify the `draft-for-validation` × Group-G interaction: (a) FR-G2 scoring — drafts count as **non-authored** (distinct from `placeholder` in the FR-X1 report); (b) FR-G3's write-block keys on `authored`, so drafts remain machine-writable — state this as intended, and that **promotion flips the write-block on**; (c) because FR-G1 makes render-strip normative, draft status MUST use the **sidecar form** (`pages.yaml` status field), not front-matter alone — stripped front-matter leaves the runtime gate (R1-F6) nothing to check | FR-J7 says it refines FR-G3/FR-G1 but the post-triage Group-G slice pinned a two-value enum, a denominator, and a write-block that all behave undefinedly (or accidentally) with a third status value | §4 FR-J7 (+ ripple notes to kickoff slice G FR-G1/G2/G3) | Fixture with authored/placeholder/draft pages: FR-G2 score and FR-X1 report distinguish all three; regeneration rewrites the draft, refuses the authored page |
| R1-F8 | Data | medium | Integrate FR-J6's `estimate` with the closed FR-X4 machinery: add `estimate` to the provenance enum, define its status mapping (`placeholder (estimate)` — never `authored`), and its score rule (estimates do **not** count toward the `input_provisioning_score` numerator until promoted by recorded decision). Cite kickoff FR-X4's applied mapping (R1-F-master-3) as the table being extended | FR-X4's enum and provenance↔status mapping are settled kickoff decisions; FR-J6 introduces `estimate` with neither, so an implementer could map estimates to `authored` and inflate the provisioning score that exists to keep estimate-vs-authored honest | §4 FR-J6 | A run with a machine-estimated KPI target reports `placeholder (estimate)` in FR-X1 and an unchanged numerator; recording the human decision flips it to `authored` and moves the score |
| R1-F9 | Architecture | high | Add the **Customer / Product Owner** role to §3 (or explicitly assign customer-proxy authority to the BA): the holder of the U-tier acts — actual goals, acceptance ("this is what I meant"), priority calls between conflicting goals, and FR-J7's end-user acceptance. Its validation point: acceptance sign-off on UAT/draft content and on requirement priority | §2 defines tier U by acts no §3 role holds; FR-J1 requires every artifact to map to a validating role, but the acceptance gate FR-J7 depends on has no nameable role today — the model's most-human tier is the one role the role map omits | §3 (new §3.0 or §3.10) + FR-J1 seed note | Every U-tier example in §2 and the FR-J7 acceptance gate maps to a named §3 role in the FR-J1 registry with no unassigned U acts |
| R1-F10 | Security | medium | Add a **Security** role (or explicitly fold its duties into Architect + Ops): consumes threat/compliance context (U); key assets: security gate verdicts (Security Prime `GateVerdictReport` — already machine-produced), credential-policy inputs; validation point: approves security-gate overrides and accepts residual risk — uniquely human risk acceptance | The SDK already ships an automated security gate with no named human validation point for failures/overrides; §3 covers nine delivery roles but the one gate that exists in code today has no role holder — an FR-J3 wiring point hiding in plain sight | §3 (new role) + a third "first wiring point" in FR-J3 | A Security-Prime gate failure override produces an FR-J3 approval record naming the security role; unowned overrides are impossible |
| R1-F11 | Validation | medium | Give §3.5 and §3.8 verifiable artifact forms: §3.5 Frontend approves a **named artifact** (rendered-page snapshot set or the view manifest + generated-view diff), not "rendered output against user expectations"; §3.8 Testing Engineer approves a **requirement→test traceability artifact** (matrix: requirement ID → test IDs), which no FR currently requires anyone to produce — add it to the §3.8 key assets and the FR-J9 kit | FR-J3 requires each gate to define "what is approved … in which artifact form"; these two validation points name judgments with no artifact, so their gates cannot be instantiated — the focus file's "unverifiable as written" case | §3.5 + §3.8 (+ FR-J9 kit list) | Each §3 validation point names ≥ 1 concrete artifact; the §3.8 traceability matrix exists as a generated artifact a human can mark approved |
| R1-F12 | Interfaces | medium | Reconcile FR-J5's tier-R bar with the registry's actual behavior: `ExemplarRegistry.lookup()` reuses at **maturity ≥ 1** (VALIDATED) with zero approvals (`registry.py:65–83`, verified). State whether (a) code exemplars are exempt from tier R (grandfathered — the existing path is bucket-1/3 internal reuse, not HITM-governed), or (b) the lookup gains the tier-R gate. Also pin the name↔level mapping (1=VALIDATED, 2=CONFIRMED, 3=INVARIANT) — the code has numeric levels only, no named constants | FR-J5 says the ladder is "reused as-is" and tier R = maturity ≥ CONFIRMED + approval, but as-is the registry already reuses below that bar with no approval — an implementer cannot satisfy both sentences without knowing which reuse path FR-J5 governs | §4 FR-J5 | If (a): code-exemplar reuse unchanged, non-code artifacts require the gate; if (b): a maturity-1 or unapproved exemplar is never returned for tier-R instantiation — one registry test each |

**Endorsements / Disagreements:** none possible — R1, Appendix C has no prior rounds.

#### Review Round R2 — claude-sonnet-4-6 — 2026-06-05

- **Reviewer**: claude-sonnet-4-6
- **Date**: 2026-06-05 00:00:00 UTC
- **Scope**: Second CRP pass on the HITM role model. R1 answered all five focus asks comprehensively; R2 goes deeper on second-order effects, adversarial failure modes, and gaps R1 did not reach. Code spot-verified read-only (`artisan_models.py`, `exemplars/registry.py`). Kickoff master v0.2 and Group-G slice (post-triage) read for composition checks.

##### Focus-file asks — R2 positions

**Ask 1 — Tier taxonomy soundness**
- **Summary answer:** Concur with R1 (partial) — the discriminator and composite-artifact rule are missing; adding a second-order gap: the taxonomy table implies tier is assigned once at authoring time, but FR-J4 says tier changes via boundary-expansion ledger, yet the table's ordering ("most → least human") implies a permanent ordinal. The tier therefore means two different things depending on whether you read §2 as a static classification or a dynamic assignment.
- **Rationale:** §2's table header is "ordered by human involvement (most → least)" — a static axis. FR-J4's boundary expansion makes tier a *current state* (G→R as patterns prove out). These two framings are incompatible: a static ordering cannot model an artifact that is tier-G today and tier-R next sprint. The classification rules R1-F1 proposes would fix the static/dynamic ambiguity only if they also state that the tier value in the FR-X5 row is mutable, with the previous value preserved in the FR-J8 ledger.
- **Assumptions / conditions:** tier is single-valued in the FR-X5 inventory row at any point in time (consistent with R1-F1).
- **Suggested improvements:** R2-F1 (tier-as-current-state annotation in §2 + the static/dynamic dual reading).

**Ask 2 — Gate/ceremony tension**
- **Summary answer:** Concur with R1's hash-bound lazy evaluation model as the binding rule. Second-order gap R1 did not raise: the fit-check for tier-R reuse (FR-J5) is a new micro-gate with no defined gate record schema — it is the "approval-lite" path but FR-J3's schema only covers full approvals. If fit-checks silently pass without a record, R artifacts can be reused without any audit trail, defeating the provenance goal.
- **Rationale:** FR-J5 says reuse "records a fit-check + provenance to the approving record" but does not define the fit-check's schema, who performs it, or whether it can fail. A fit-check that always passes is decoration; a fit-check with no defined failure mode cannot trigger a re-validation. This is the tier-R analog of the unattended-bypass problem R1-F4 identified for the two TTY gates.
- **Assumptions / conditions:** fit-checks are machine-executed unless stated otherwise.
- **Suggested improvements:** R2-F2 (fit-check schema + failure mode + human vs machine performer).

**Ask 3 — Tier D production-blocking**
- **Summary answer:** Concur with R1. Additional gap: FR-J7 says "promotion to `authored` requires explicit human approval recorded per FR-J3 after end-user acceptance" — but it does not say what happens if the D-tier content is rejected by end-users rather than accepted. Rejection of draft content is not covered; without a `rejected` terminal state for D-tier, the content sits in `draft-for-validation` indefinitely and a future run can re-serve it.
- **Rationale:** The tier-D lifecycle has only two documented outcomes: (a) approved → `authored`, (b) never approved → blocked. There is no `rejected` state and no path for "the end-user said this is wrong — discard it." In practice this means the SDK pipeline accumulates stale draft content that was explicitly found wrong by users but is still `draft-for-validation` and still blockable-but-not-discarded.
- **Assumptions / conditions:** the approval record per FR-J3 covers only the APPROVED state; `REJECTED` in the ChunkState enum exists but is not mentioned in FR-J7's lifecycle.
- **Suggested improvements:** R2-F3 (tier-D `rejected` terminal state and discard-or-replace rule).

**Ask 4 — Kickoff integration**
- **Summary answer:** Concur with R1 on the two enum-extension gaps (FR-J6 `estimate`, FR-J7 `draft-for-validation`). Additional gap R1 did not raise: FR-J4 requires tier to appear in the FR-X5 inventory row, but the kickoff master's FR-X5 column definition (v0.2 Appendix A) was settled before Group J existed — the `role` and `validated_by` columns FR-J1 adds, and the `tier` column FR-J4 adds, are extensions to a closed, already-triaged schema with no defined forward-compatibility rule.
- **Rationale:** FR-X5 Appendix A in the kickoff master records the accepted column set. FR-J1 and FR-J4 each add columns; if a second Group-J requirement (e.g. a future FR-J10) adds a third column, there is no defined process for amending the canonical FR-X5 schema — each CRP round touches a different doc and the master stays stale. The kickoff master needs a versioned column extension protocol, or FR-J1/J4 need to cite the master's OQ for schema evolution.
- **Assumptions / conditions:** FR-X5 column set is settled and tracked in the kickoff master's Appendix A.
- **Suggested improvements:** R2-F4 (FR-X5 extension protocol or forward-reference to kickoff OQ-1/OQ-2).

**Ask 5 — Role map completeness/realism**
- **Summary answer:** Concur with R1 on the missing Customer/PO and Security roles, and on the two unverifiable validation points (§3.5, §3.8). One additional unrealism: the PM role's validation point says "approves plan + budget before runs" and "owns the boundary-expansion ledger entries" — but the ledger (FR-J8) is an ongoing artifact spanning many runs, while the gate is described as a pre-run act. These are two different cadences (one-time pre-run vs. ongoing across-runs), conflated into a single validation point with no distinction.
- **Rationale:** A pre-run plan-approval gate and ongoing ledger maintenance are operationally different: the gate blocks the first run; the ledger is updated after evidence accumulates across runs. Conflating them means either (a) the PM must re-approve the plan on every boundary change (stop-the-world) or (b) the gate is never re-triggered after the first run (decorative after run 1). Neither is the intent.
- **Assumptions / conditions:** §5 "does not mandate ceremony" means the gate model must not require pre-run sign-off on every run.
- **Suggested improvements:** R2-F5 (split PM validation point into pre-first-run gate vs. ongoing ledger stewardship).

##### Executive summary

- R1 comprehensively addressed all five focus asks; R2 focuses on second-order and adversarial gaps.
- §2's tier table conflates static ordinal ranking with dynamic current-state assignment — FR-J4's mutability is incompatible with the table's framing without an explicit "tier is the current value; changes are ledgered" note.
- The tier-R fit-check (FR-J5) is an unspecified micro-gate with no defined schema, failure mode, or performer — the audit-trail gap for reuse is potentially larger than the full-approval gap because reuse is the high-frequency path.
- Tier D has no `rejected` terminal state — draft content that end-users explicitly reject sits indefinitely in `draft-for-validation`, eligible to be re-served.
- FR-J1/J4 extend FR-X5 with new columns against a closed, already-triaged schema in the kickoff master with no defined extension protocol.
- PM's validation point conflates a one-time pre-run gate with ongoing cross-run ledger stewardship — these need separate cadence definitions.
- ChunkState's `REJECTED` enum value is unused in the HITM model despite being the natural terminal state for rejected-at-review artifacts.
- The fit-check + the rejected terminal state together define the "reuse declined" and "draft discarded" paths — both are missing from the requirements.

##### Suggestions

| ID | Area | Severity | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- |

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Architecture | medium | Annotate §2 to distinguish tier as a **current state** (not a static ordinal): add a sentence after the tier table: "The tier value in the FR-X5 inventory row is the *current* classification; prior tier values and the evidence for any boundary change are preserved in the FR-J8 ledger. The table order (most→least human involvement) reflects the expansion direction, not a fixed label." This resolves the static-vs-dynamic reading ambiguity that FR-J4 creates. | §2 presents tiers as a static ordered classification; FR-J4 makes them mutable; an implementer who reads §2 as a stable label will not preserve history when a tier changes, violating FR-J4's "recorded event" requirement without technically breaking §2. | §2, sentence after the tier table | Two independent implementers reading §2 + FR-J4 produce the same data model: a mutable `tier` field with a ledger for prior values, not an immutable enum column. |
| R2-F2 | Interfaces | high | Define the **fit-check** in FR-J5: state (a) the check is machine-executed by default; (b) it produces a `FitCheckRecord{artifact_id, reuse_target_id, score, passed, checked_at, checked_by?}`; (c) a fit-check **failure** (score below threshold) routes to re-validation, not silent fallback to the next-best exemplar; (d) the record is persisted alongside the approval provenance. Without this, tier-R reuse has no audit trail for the highest-frequency approval path. | FR-J5 says "records a fit-check + provenance to the approving record" but neither defines the fit-check's schema nor its failure behavior. As written, a machine can silently skip a failing fit-check and fall back to a lower-maturity exemplar — the audit trail is only promised, never enforced. Spot-verified: `registry.py:65–83` returns the best match silently with no fit-check record emitted. | §4 FR-J5, after the "reusing an R artifact skips re-validation" sentence | A reuse event with a failing fit-check produces a `FitCheckRecord` with `passed=False` and triggers re-validation, not silent fallback; a passing fit-check produces a record with `passed=True`; `exemplar-registry.json` contains both types. |
| R2-F3 | Risks | high | Add the **rejected terminal state** for tier-D content to FR-J7: alongside "promotion to `authored`", specify that end-user rejection (expressed as a recorded human act per FR-J3, using the `REJECTED` ChunkState analog) transitions the content to **`draft-rejected`** — a terminal state where the SDK pipeline will not re-serve, re-include in export packages, or re-count in FR-G2 scores. The prior draft MAY be discarded or replaced by a new draft. | FR-J7 documents only the approval path (draft → authored); the rejection path is absent. Draft content that end-users explicitly reject sits indefinitely in `draft-for-validation` — blockable but not terminal. The ChunkState enum already has `REJECTED`; not using it for D-tier rejection wastes the prior art. | §4 FR-J7, alongside the promotion sentence | A D-tier artifact with a recorded rejection produces `draft-rejected` status; subsequent pipeline runs do not include it in FR-G2 scores or export packages; a new draft can be generated and restarts the validation cycle. |
| R2-F4 | Architecture | medium | Add a **column extension protocol** to FR-J1 and FR-J4 (or note the dependency on kickoff OQ-1/OQ-2): when a Group-J requirement adds columns to FR-X5, it MUST cite the kickoff master's schema version and follow the agreed extension mechanism (append-only columns with default values for existing rows). Without this, each FR-J column addition silently diverges the Group-J view of FR-X5 from the kickoff master's settled definition. | FR-J1 adds `role` + `validated_by`; FR-J4 adds `tier` — both against a kickoff master FR-X5 whose column set was accepted in Appendix A before Group J existed. There is no defined protocol for extending a settled schema across doc boundaries; the next Group-J requirement will hit the same gap. | §4 FR-J1 (note) + FR-J4 (note), pointing to kickoff master OQ-1/OQ-2 (where approval record home is decided — the same schema governance question) | The kickoff master's FR-X5 definition and the Group-J description of FR-X5 produce identical column sets when read in parallel; no column is defined in one doc but absent from the other. |
| R2-F5 | Ops | medium | Split the PM validation point in §3.2 into two distinct acts: (a) **pre-first-run gate** — PM approves `plan.md` + initial budget before the first pipeline run (hash-bound per R1-F3; re-triggers only if plan/budget hash changes); (b) **ongoing ledger stewardship** — PM reviews and approves boundary-expansion ledger entries as evidence accumulates across runs (cadence: per-ledger-entry-proposal, not per-run). The conflation in §3.2 is the root cause of the stop-the-world vs. decorative-gate tension for the PM role specifically. | §3.2 says "PM approves the plan + budget before runs; PM owns the boundary-expansion ledger entries" — one sentence, two different cadences. The first is a one-time gate; the second is continuous stewardship. Conflating them forces either re-approval on every run or no re-approval ever. | §3.2 PM validation point; cross-reference to FR-J3 (gate schema) + FR-J8 (ledger) | Two pipeline runs with an unchanged plan.md + budget produce one approval record (first run) and no re-prompt (second run); a boundary-expansion ledger entry proposed after run 3 triggers a PM approval prompt without re-gating the plan itself. |
| R2-F6 | Validation | medium | FR-J9 is the only requirement in §4 with **no acceptance criteria** — every other FR names at least one observable outcome, but FR-J9 ("the SDK/pipeline provides the role's kit") does not specify what constitutes a complete kit, how completeness is measured, or what the minimum viable kit contains per role. Add: at minimum, a kit MUST contain (a) a generated-draft template, (b) a review checklist, and (c) a validation artifact name per §3 validation point; OQ-5's format decision (docs vs CLI vs per-project) must be resolved before implementation begins. | Without acceptance criteria, FR-J9 is unfalsifiable — any doc folder can claim to be a "kit." The existing kit components called out in OQ-5 (POLISH report for BA, FDE preflight/explanation for ops, SA triage .md) satisfy some criteria for some roles; an implementer cannot tell if the kit is "done" without a completeness definition. | §4 FR-J9 + §6 OQ-5 (narrow remaining decision to format only) | Each §3 role has a kit entry in the registry; each kit entry contains ≥ 1 draft template, ≥ 1 review checklist, and ≥ 1 validation artifact reference; the FR-X1 pre-flight report includes a "kit completeness" field per role. |

### Stress-test / adversarial pass

**Edge cases in the tier taxonomy:**

The tier table is ordered U→E→D→G→R (most→least human involvement). This ordering implies that promotion is always "rightward" (toward R), but §2 says the automation boundary moves "downward in human effort" — the direction metaphors conflict. An implementer who reads "downward" as the natural direction will be confused when the table's ordering goes top-to-bottom with most-human at top. Low severity but worth fixing for implementer clarity.

**Ways an implementer satisfies the letter while violating intent:**

1. **FR-J3 / ChunkState validator gap (confirmed by R1-F5):** An implementer lifts the ChunkState shape verbatim, adds `approved_by`, and writes a Pydantic model where `approved_at` is required when `status=APPROVED` (the existing direction R1-F5 proposed) — but `approved_by` has `Optional[ActorReference]`. The schema is formally compliant with FR-J3's "add `approved_by`" instruction, but a gate can have `approved_at` set with `approved_by=None`, producing a who-less audit record. The fix requires BOTH fields to be non-null on APPROVED status.

2. **FR-J8 ledger with no blocking trigger:** FR-J8 says tier movements are "explicit, recorded events — never silent" but does not say who is notified or what blocks on an unreviewed movement. An implementer can satisfy FR-J8 by writing the ledger entry without ever prompting the PM — the entry exists, it is not silent, but no human ever reviewed it. The requirement needs "the PM role is notified and MUST record approval (per FR-J3) before the boundary change takes effect downstream."

3. **FR-J5 tier-R lookups bypass approval:** The registry lookup at `registry.py:65–83` returns any exemplar with `maturity >= 1` — R1-F12 identified this as the exemption ambiguity. An adversarial implementer reads FR-J5's "the registry's fingerprint+tuple structure is generic — requirements/architecture/test artifacts ride the same mechanism as code exemplars" and applies the SAME maturity->=1 threshold to non-code artifacts (no approval required for non-code tier-R lookups). The doc must explicitly state that the approval gate applies to ALL artifact classes using the registry, not just code exemplars.

4. **FR-J6 `estimate` in the score numerator:** The kickoff master FR-X4 (per R1-F8) defines a provisioning score with a settled numerator/denominator. FR-J6 adds `estimate` provenance but if the implementer maps `estimate` to `placeholder (estimate)` in the status column AND the score formula only excludes `absent` from the numerator (not `placeholder`), then estimates count as authored — inflating the score. The fix is to make the score rule explicit: only `authored` counts toward the numerator; `placeholder` (with or without `estimate` tag) does not.

5. **Solo mode collapsing all roles:** §5 says "one human may hold many roles (solo-founder mode collapses all roles onto one person without changing the gates)." An adversarial implementer reads this and auto-assigns all FR-J1 `validated_by` fields to the same single ActorReference, making every gate a self-approval. The doc should state that self-approval (approver == author == same identity for a gate) is valid in solo mode but MUST be logged distinctly (e.g. `solo_mode: true` in the gate record) so audit consumers can distinguish solo self-approval from an actual second-party review.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F7 | Security | high | Require that BOTH `approved_at` AND `approved_by` are non-null when `status=APPROVED` in the lifted ChunkState shape. R1-F5 proposed the reverse implication (`approved_at` ⇒ non-null); this suggestion adds the parallel constraint for `approved_by`: status=APPROVED with `approved_by=None` MUST fail validation. Without this, an approval record with a timestamp but no identity satisfies FR-J3's "who/when/what-hash" claim on the timestamp dimension only. | A Pydantic model that adds `approved_by: Optional[ActorReference]` without making it required on APPROVED status silently satisfies the FR-J3 letter while producing who-less audit records — the most likely implementation mistake when lifting ChunkState. | §4 FR-J3 schema sentence (alongside R1-F5's reverse implication) | Pydantic model test: `status=APPROVED, approved_by=None` raises validation error; `status=APPROVED, approved_by=ActorReference(...)` passes; `status=DRAFT, approved_by=None` passes. |
| R2-F8 | Architecture | high | State in FR-J8 that a **pending ledger entry blocks the boundary change from taking effect downstream** until the PM records approval per FR-J3. "Explicit, recorded event" is not enough: without a blocking condition, an implementer writes the ledger entry and the boundary change silently propagates. The trigger for the PM gate should be the same lazy-consumption model R1-F3 proposed for other gates: the first pipeline stage that would *use* the new tier classification checks for an approved ledger entry and blocks if absent. | FR-J8 says movements are "never silent" but does not say the change is blocked pending approval; an implementer can satisfy the letter by writing a log entry while the tier change takes effect immediately. The PM gate on boundary expansion is the HITM model's safeguard against autonomous automation creep — it must actually block. | §4 FR-J8, after the "approving role" sentence | A tier-G→tier-R boundary change entered in the ledger without a PM approval record causes the next pipeline stage that reads the artifact's tier to report a `gate-pending` state, not to use the new tier silently. |
| R2-F9 | Architecture | medium | Add a sentence to §2 clarifying that the tier table's top-to-bottom order (U→R) represents the expansion direction from most to least human involvement, and that "downward in human effort" (used in the paragraph below the table) means moving toward R (not toward U). Resolve the directional metaphor conflict before an implementer encodes it. | §2 uses both "downward" and the table's top-to-bottom ordering; a reader who maps "downward" to "toward R" gets the right behavior, but a reader who maps "downward" to "lower in the table" (toward U) gets the opposite. The expansion direction is the fundamental safety guarantee of the HITM model; a metaphor ambiguity here is a docility risk. | §2, the automation-boundary paragraph after the tier table | Two independent readers of §2 independently label the automation-boundary expansion direction identically (toward R / toward less human involvement). |

**Endorsements** (prior untriaged suggestions from R1 this reviewer agrees with):
- R1-F1: Endorse — the discriminator rule is foundational; without it the five focus asks in this doc's own focus file are undecidable.
- R1-F3: Endorse — hash-bound lazy evaluation at consumption is the binding gate rule; the doc has all the pieces; this suggestion provides the assembly instructions.
- R1-F4: Endorse — the unattended-bypass problem is the most critical real-world gap; unattended override records are distinct from approvals and must be logged as such.
- R1-F5: Endorse — the ChunkState reverse-implication gap is verified; this is a prerequisite for R2-F7 above.
- R1-F9: Endorse — the Customer/PO role is missing from the doc's most important tier (U); the acceptance gate in FR-J7 has no named holder without it.
- R1-F12: Endorse — the code-exemplar vs non-code-artifact reuse ambiguity in FR-J5 is the highest-frequency loophole in the approval model.
