# Descriptive Layer — Requirements

**Version:** 0.4.3 (Draft — + FR-DL-13, surface the buried signals / anti-`--json`-only, CL-14)
**Date:** 2026-07-17
**Status:** Draft
**Stable key:** `FR-DL-*` (concept-keyed; the presentation name "descriptive layer / meta layer" is a mutable alias — [[concept-key-not-presentation-name]])
**Plan:** [`DESCRIPTIVE_LAYER_PLAN.md`](DESCRIPTIVE_LAYER_PLAN.md)
**Reference pattern (emulate, cite — do not re-derive):** `~/Documents/dev/cui/3xl-kcui`
— declarative metadata manifest wrapping raw kubectl/docker output
(`packages/topic-kubectl/src/manifest.ts`, `packages/kernel/src/compose.ts`,
`packages/shell/src/render.ts`; reqs `docs/kubectl-cui-pilot-requirements.md`).
**Related (reuse by reference, do not re-spec):** `dev-os/NODE-SCHEMA.md` (the DATA grammar
`key/status/does/wont/lives`), `wireframe/WIREFRAME_REQUIREMENTS.md` (`FR-W*`, the raw plan +
FR-W5 `consequence`), the three capability-index manifests.

---

## 0. Planning Insights (Self-Reflective Update)

> What changed v0.1→v0.2. The planning pass (reading `wireframe/render.py`, `plan.py`, and the
> WIREFRAME reqs) revealed the descriptive layer is **not greenfield** — a seed already ships:

| v0.1 Assumption | Planning Discovery | Impact |
|---|---|---|
| The wireframe output has *no* descriptive layer at all | It already has the **WHY seed**: `WireframeSection.consequence` (FR-W5) renders `→ {consequence}` (italic) for non-`planned` sections (`render.py:170`) | Reframed: this spec **externalizes + completes** an existing seed, it does not build from zero. WHY partially exists (non-planned only, inline); WHAT/HOW/DO/NEXT are the genuinely-missing dimensions |
| Status vocabulary is 4 (planned/defaults/placeholder/invalid) | It is **5** — adds `not_defined` — with a `worst()` precedence roll-up (`plan.py:52,103`) | FR-DL-6 degradation covers all 5; roll-up already exists (reuse, don't rebuild) |
| A descriptive manifest is a new artifact | The consequence strings are **inline literals in `plan.py`** today (per-section, in code) | FR-DL-5: externalize them into the single-source manifest — the current inline form is the drift risk the manifest dissolves |
| "Logical next steps / workflow position" is a new abstraction | The **DATA MODEL front bookend** is already the named anchor — WIREFRAME R3-F3 ties the shape-summary to *"the primary kickoff question at the DATA MODEL bookend"* | FR-DL-4 workflow-grounding binds to a **real, pre-existing** workflow position, not an invented one |
| The layer renders its own output | `render.py` already owns a Rich **tree** renderer (`_section_node`, `render_plan`, `footer_lines`) | NR-5: the layer **wraps/augments** the existing renderer; it is not a new rendering engine |

**Resolved open questions (from planning):**
- **OQ-1 → the WHY dimension is half-built** (`consequence`); the layer adds the action-half + the other three dimensions.
- **OQ-4 → workflow position binds to the DATA MODEL bookend** (real), with room to *infer* earliness from the status mix (mostly `not_defined` ⇒ early).
- Still open: OQ-2 (manifest format), OQ-3 (interactivity), OQ-5 (navigator reuse) — see §4.

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied this session's own lessons (the strongest available base for this work):

- **[[concept-key-not-presentation-name]]** — key each descriptive record on a **stable concept key** (the output-unit's `FR-`/section key), not its display label; declared the `FR-DL` prefix as identity (see header, FR-DL-1).
- **Single-source vocabulary ownership** — the narration text must be **owned by one manifest and cited**, not restated across renderer + docs. Drove FR-DL-5 (externalize the inline `plan.py` consequences) and FR-DL-10 (cite NODE-SCHEMA fields, never copy them).
- **Phantom-reference audit** — every symbol this spec names was grep-verified to exist (`consequence`/FR-W5, `worst()`, `_section_node`, `render_plan`, `Status.NOT_DEFINED`); see §5 Reference Audit. No to-be-created symbol is asserted as existing.

### 0.2 Design-Principle Hardening (v0.3.1)

> Checked against `startd8-sdk/docs/design-princples/`. Each changed the draft:

- **Mottainai (dominant)** — an earlier stage already produced the WHY (`consequence`) and the data (the plan); the layer **forwards/externalizes** these, never regenerates them. Killed a drafted "recompute consequences" step. FR-DL-5/FR-DL-10.
- **Accidental-Complexity** — resisted a per-status special-case narrator; **one general record schema + template-fill** (3xl-kcui's model), not five hand-coded status branches. FR-DL-1/FR-DL-6.
- **Hitsuzen (derive the determinable)** — what/how/why/next are fully determined by (authored manifest × live plan); **deterministic template-fill, no LLM**. FR-DL-8.
- **Context-Correctness-by-Construction** — template placeholders MUST fill from **validated plan data**, never silently `None`; an unfillable placeholder is a typed error, not blank text. FR-DL-5.
- **Genchi Genbutsu** — the WHAT/WHY bind to the **actual** plan (real statuses/counts) and the **real** DATA MODEL bookend, not a generic template. FR-DL-4/FR-DL-9.

---

## 1. Problem Statement

The wireframe (and every raw `startd8` command, and the Requirements Navigator's Node data)
shows a user the **data** but not its **meaning**. `startd8 wireframe` emits a status tree; the
user reported it reads as raw output with *"no meta layer"* — you cannot approve the planned
shape at a glance, and nothing tells you what to *do* about what you see. `NODE-SCHEMA.md`
defines what a node *is* (`key/status/does/wont/lives`); the navigator READMEs are static
hand-drawn prototypes. **Neither defines the experience** — the descriptive wrapper that, per
thing shown, says WHAT it is, HOW it's shown, WHY it's shown, what to DO with it, and what the
logical NEXT step is *given where the user is in their build workflow*.

`3xl-kcui` solves exactly this for kubectl/docker: a declarative manifest wraps raw command
output with a framing intro (WHAT), a render+compose directive (HOW), a dry-run/blast-radius
(WHY), and chips + verify/success responses (NEXT), plus typed degradation messages that each
say what to do. This spec ports that pattern to `startd8` command output.

| Component | Current State | Gap |
|---|---|---|
| WHAT (framing intro) | none — the tree starts with section keys | no per-unit "what you're looking at" |
| HOW (render directive) | hardcoded Rich tree in `render.py` | render choice is implicit, not declared or consistent across units |
| WHY (purpose) | **partial** — FR-W5 `consequence` for non-`planned` sections, inline in `plan.py` | only non-planned; only consequence, not "what decision this serves"; inline, not single-sourced |
| DO (what to attempt) | none | the user is shown a gap but not the action to close it |
| NEXT (logical next steps) | none | no affordances, no workflow-grounded "now do Y"; the DATA MODEL bookend is named but not wired to actions |
| Degradation | status tags (`defaults`/`invalid`) shown | status shown, but not *what to do* about each |

## 2. Requirements

**FR-DL-1 — Descriptive record schema.** A declarative record per **output-unit** (a wireframe
section; generically, a Node or any wrapped command's output block). Each field's obligation
(R1-F4): **mandatory** `what`, `how`, `why`, `do`; **required-but-may-be-empty** `next[]`;
**conditional** `degrade{by-status}` — required for any unit that *can* be non-`planned` (keyed by
status), omittable for always-`planned` units. Optional `audience` (R1-F1): a record MAY provide
audience-keyed variants (`human` / `agent`, per 3xl-kcui) of `what`/`how`; absent ⇒ one form serves
all. Keyed on the unit's **stable key** (section key / `FR-`prefix), not its display label. (Ports
the 3xl-kcui `Intent`: `responses.text`=what, `tools`+`compose`=how, dry-run=why, `chips`=next.)
*Confidence is deliberately NOT a record field (R1-F1 → Appendix B): authored narration carries no
grounding-strength; the wrapped Node's `confidence` is surfaced by reference (FR-DL-10).*

**FR-DL-2 — The four dimensions are mandatory.** Every output-unit MUST declare `what/how/why/do`
(see FR-DL-1 for the full obligation table). `why` MAY reuse the existing FR-W5 `consequence`
where present rather than restate it.

**FR-DL-3 — Next-step affordances, static + derived.** `next[]` combines **authored** steps and
steps **derived from live plan data** — e.g. a `not_defined` `views` section yields the exact
authoring action (`define views.yaml → N composite views`); the DATA MODEL bookend yields the
next kickoff step. Before the cap, affordances are **ordered deterministically (R1-F5): derived
blocking actions (non-`planned` fixes) first, then authored-static, each a stable sort by section
key** — then **capped with an explicit overflow indicator — no silent truncation** ("+K more").
The surviving set and the "+K more" count are byte-stable for a given plan (FR-DL-8/9).

**FR-DL-4 — Workflow grounding.** Each record declares the **user's workflow position** it serves
(the DATA MODEL front bookend for the wireframe) and anchors `do`/`next` to that position. Position
is resolved **deterministically (R1-F2)**: an authored `position` on the record **wins**; else it
is **inferred** — **> 50% of sections `not_defined` ⇒ early (DATA MODEL); ≥ 50% `planned` and none
`invalid` ⇒ ready-to-generate; otherwise ⇒ mid (refining)**. Ties break toward the *earlier*
position (never over-claims readiness). `do`/`next` are never generic — they are "from *here*, do Y."

**FR-DL-5 — Single-sourced template composition.** Records are **templates** with placeholders
filled from the **validated** live plan; narration text is **owned by the manifest**, not scattered
in the renderer — this spec **externalizes** the inline `plan.py` consequence literals. "Validated"
(R1-F3) = the named source field is present and correctly typed on the `WireframePlan`; an
unfillable placeholder is a **typed error**, never silent blank text. Placeholder vocabulary and
fill-source:

| Placeholder | Fills from | Legal when |
|---|---|---|
| `{{count}}` | `plan.status_counts` / `section.items` length | section resolved |
| `{{missing}}` | keys absent from `plan.input_provenance` | always (may be empty) |
| `{{status}}` | `section.status` | always |
| `{{consequence}}` | `section.consequence` (FR-W5) | non-`planned` sections |
| `{{cmd}}` | derived authoring/generate command for the section key | section key ∈ known map |
| `{{shape}}` | `footer_lines()` shape summary | always |

**FR-DL-6 — Honest degradation → action.** Each non-`planned` status
(`defaults`/`placeholder`/`not_defined`/`invalid`) MUST render a typed message giving both
(a) the app-shape meaning [the existing FR-W5 consequence] **and** (b) the action to resolve it.
Extends FR-W5 with the missing action-half. Reuses the existing `worst()` roll-up.

**FR-DL-7 — One consistent presentation grammar.** Every output-unit renders in the same shape —
**WHAT header → HOW-rendered body → WHY note → DO/NEXT footer** — so the experience is uniform at
every altitude (the navigator's consistency rule; 3xl-kcui `renderReply` uniformity).

**FR-DL-8 — Deterministic, no-LLM.** The layer is authored manifest × deterministic template-fill.
No model calls (Hitsuzen). Preserves the wireframe's `$0`/read-only nature and matches 3xl-kcui.

**FR-DL-9 — Provenance by construction.** Each rendered descriptive unit is traceable to the
record/template that produced it (auditable/testable). (3xl-kcui provenance-by-construction.)

**FR-DL-10 — NODE-SCHEMA reuse, not re-spec.** Reuse node data fields (`status`→glyph, `does`,
`wont`, `lives`) **by reference**. The descriptive layer *adds* `why/do/next` + workflow grounding
— it is "how to present a Node to a human"; NODE-SCHEMA is "what a Node is." Cite, never copy
(Mottainai).

**FR-DL-11 — The three orthogonal axes (`category` / `orientation` / `route_state`).** Each record
MAY carry the three facets from NODE-SCHEMA v0.2 (cite `startd8-sdk/src/startd8/observability/taxonomy_enums.py`
— the canonical vocabulary; never restate its value lists):
- **`category`** — *what domain* the unit belongs to (the grouping / fsn pedestal).
- **`orientation`** — `system | human | bridge`; **supersedes the FR-DL-1 `audience` field**
  (attorney→`human`, agent→`system`-leaning; `bridge` = serves both at once, e.g. a cited card).
- **`route_state`** — `sdk_emitted | owned_elsewhere | declared_unimplemented | external_convention`;
  **supersedes the scalar status + `ships_when`** and reconciles `degrade{by-status}`: a
  `not_defined` section = `declared_unimplemented`; a section owned by another manifest =
  `owned_elsewhere` (cite, don't restate — FR-DL-10); the attorney `curated/auto/skipped` classifier
  is this same axis. **`owned_elsewhere` + `declared_unimplemented` are honest-skips excluded from
  the coverage denominator** — they never drag down roll-up.

The three are **orthogonal** — never infer one from another (NODE-SCHEMA invariant 5) — and are
**facets**, so a node is reachable by facet-filter and search, not only by drill (NODE-SCHEMA §3a).
Deterministic; no LLM (FR-DL-8).

**FR-DL-12 — The summary record (aggregate counts; NODE-SCHEMA §3b).** In addition to per-section
records, the manifest carries one **`summary`** record that renders the **summary altitude** *before*
the per-section landscape (SV-1). It is a describable unit (what/why/do/next) whose body is the
aggregate:
- **Key-object counts (SV-2):** entities · CRUD routes · pages · forms · views · AI passes (+ content
  inputs, completeness signals) — each with a one-clause WHAT and, if derived, its derivation (SV-3:
  `155 CRUD = ~5 × 31 entities`).
- **Core-vs-derived decomposition (SV-4):** the count the human must *judge* vs. what is derived —
  filled from the completeness signals vs. the `excluded` set (`31 entities → 6 core + 25 derived`).
  This is what makes "is the shape right?" glance-approvable.
- **Health roll-up (SV-5)** (`worst()` over status counts) + **readiness (SV-6)** (the cascade lines,
  with a *named blocker* when blocked — never silent zeros).

New placeholders (extend the FR-DL-5 table): `{{counts}}` ← `footer_lines()`; `{{core}}` / `{{derived}}`
← completeness signals vs `excluded`; `{{readiness}}` ← the cascade readiness lines. Deterministic +
**speakable** (SV-7, FR-DL-8); each count **drills to its section** (SV-1). This lifts the wireframe's
FR-W9 footer into the descriptive layer and gives the numbers *meaning*. Worked example (real data):
`kickoff/kits/architect/example-strtd8-summary.md`.

**FR-DL-13 — Surface the buried signals (the anti-`--json`-only requirement).** The descriptive
layer's job includes rendering *computed-but-hidden* data as node meaning, not side-effects
(NODE-SCHEMA SV-8 / CL-14 audit). Specifically:
- `content_coverage` (FR-WCI-2) → the summary's **content-readiness %** (via FR-DL-12) — "X% of
  pages/views/prompts/form-help authored," the handoff signal (today `--json`-only).
- the `human_inputs` human-authored set → a per-entity **AI boundary** note ("AI edge stops at:
  `Metric.value`, `ProofPoint.sourceDocumentId`"), not just an inline "omitted" tag.
- `display.yaml` (now catalogued by the wireframe, CL-14 gate 1) → the **Display** section's what/why.
- `input_provenance` / `status_override` → each node's **provenance** (convention / flag / declared).

Rule: a signal the plan computes *and the architect needs* is a `lives`/meta field on its node —
**never `--json`-only or a side-effect tag.** The SV-4 core/derived split was the first instance.

## 3. Non-Requirements

- **NR-1** — Not LLM narration. Deterministic, authored (FR-DL-8).
- **NR-2** — Not a re-spec of NODE-SCHEMA's data fields (FR-DL-10).
- **NR-3** — Not the mutation/confirm/blast-radius ceremony. The wireframe is **read-only**; 3xl-kcui's dry-run→confirm→verify pattern applies to future **wrapped mutating commands** and is noted, not specified here.
- **NR-4** — Not an interactive REPL/TUI. `startd8 wireframe` is one-shot; `next[]` renders as printed action hints **with their exact commands**, not selectable chips — until a REPL exists (OQ-3). **Forward-compat (R1-F6):** each `next[]` entry is shaped as an `{id, label, command}` triple (not a bare hint string), so a later REPL can make it selectable with no schema migration.
- **NR-5** — Not a new rendering engine. Wraps/augments the existing `render.py` Rich tree.

## 4. Open Questions

- **OQ-2 — Manifest format & home.** YAML data file (like the capability manifests) vs Python beside the renderer (3xl-kcui uses TS data). Leaning YAML for single-sourcing + tooling parity.
- **OQ-3 — Interactivity.** Printed action hints now (one-shot CLI) vs selectable affordances (needs a REPL). Defer interactivity to a REPL spec?
- **OQ-5 — Navigator reuse.** Does the same manifest also *generate* the navigator READMEs (kickoff/wireframe/capability-index), or drive CLI output only? (If yes, the descriptive layer becomes the single source behind both the static navigators and the live CLI — high Mottainai value.) **v1 boundary (R1-F7): v1 is CLI output only; README generation is a named follow-on gated behind a pilot Hansei** — "done" for v1 does not include it.

## 5. Reference Audit (phantom-reference check)

Every symbol this spec binds to was grep-verified in the current tree:

| Symbol | Location | Role in this spec |
|---|---|---|
| `WireframeSection.consequence` (FR-W5) | `wireframe/plan.py:133`, rendered `render.py:170` | the WHY seed FR-DL-6 extends |
| `Status.{PLANNED,DEFAULTS,PLACEHOLDER,NOT_DEFINED,INVALID}` | `wireframe/plan.py:52-57` | the 5 statuses FR-DL-6 covers |
| `worst()` precedence roll-up | `wireframe/plan.py:103` | reused by FR-DL-6 (not rebuilt) |
| `render_plan` / `_section_node` / `footer_lines` | `wireframe/render.py:256/168/239` | the renderer FR-DL-7 wraps (NR-5) |
| DATA MODEL bookend | `wireframe/WIREFRAME_REQUIREMENTS.md` §1, R3-F3 | the workflow position FR-DL-4 binds to |

---

*v0.3.1 — Post-planning (5 discoveries; the layer is a seed-completion, not greenfield) +
3 lessons + 5 principles. 3 open questions remain. Ready for CRP review.*

## Appendix A — Accepted (CRP)
*(empty — initialized for cross-model memory)*
## Appendix B — Rejected + rationale (CRP)
*(empty)*
## Appendix C — Incoming (CRP review rounds)
*(empty)*

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
| R1-F1 | Resolve audience/confidence schema question | CRP R1 | Adopted optional `audience` (human/agent variants) into FR-DL-1; `confidence` rejected → Appendix B | 2026-07-17 |
| R1-F2 | Make FR-DL-4 inference testable (threshold + tie-break + authored override) | CRP R1 | FR-DL-4: authored `position` wins; >50% not_defined⇒early / ≥50% planned & none invalid⇒ready / else mid; ties→earlier | 2026-07-17 |
| R1-F3 | Specify FR-DL-5 fill contract (placeholder→source table, define "validated") | CRP R1 | FR-DL-5: added placeholder vocabulary table + "validated"=present+typed on WireframePlan | 2026-07-17 |
| R1-F4 | Clarify mandatory-vs-optional per field | CRP R1 | FR-DL-1: mandatory what/how/why/do; next[] required-may-be-empty; degrade{} conditional | 2026-07-17 |
| R1-F5 | Define affordance ordering before the cap | CRP R1 | FR-DL-3: derived-blocking first, then authored-static, stable sort by section key; byte-stable | 2026-07-17 |
| R1-F6 | Forward-compat note: next[] as {id,label,command} | CRP R1 | NR-4: next[] entries shaped as {id,label,command} triples so a REPL needs no migration | 2026-07-17 |
| R1-F7 | OQ-5 v1 acceptance boundary | CRP R1 | §4 OQ-5: v1 = CLI output only; README generation is a Hansei-gated follow-on | 2026-07-17 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R1-F1b | Add `confidence` as a descriptive-record field | CRP R1 (sub-item) | Authored narration has no grounding-strength — `confidence` is a NODE-SCHEMA *data* property, not a *presentation* one. The wrapped Node's `confidence` is surfaced by reference (FR-DL-10); duplicating it onto the record would re-spec NODE-SCHEMA (Mottainai) and invite drift. `audience` (the other half of F1) WAS adopted. | 2026-07-17 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-17

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-17 UTC
- **Scope**: First external CRP pass on requirements v0.3.1. Weighted per the sponsor focus file toward record-schema completeness, FR-DL-4 inference robustness, FR-DL-5 fill risks, and the OQ-3/OQ-5 boundary questions. SETTLED items (no-LLM, FR-W5-seed extension, NODE-SCHEMA-by-reference, read-only, FR-DL naming) honored — not relitigated.

**Executive summary (top risks / gaps / opportunities):**

- The record schema (FR-DL-1) lists `what/how/why/do/next[]/degrade{}` but the focus file's own question — should a record carry `audience` and/or `confidence`? — is unanswered in the spec; 3xl-kcui carries `audience`, NODE-SCHEMA carries `confidence`. This is the single most consequential open gap because the schema is the frozen contract everything else fills.
- FR-DL-4 permits workflow position to be **inferred** from the status mix but gives no tie-break rule, no threshold for "predominantly/mostly", and no authored-override escape hatch — an untestable heuristic as written.
- FR-DL-5 asserts "unfillable placeholder is a typed error" but never defines the placeholder set, the fill-source contract, or what "validated plan data" means as an acceptance criterion — the CCbC guarantee is currently unverifiable.
- FR-DL-2 says four dimensions are mandatory (`what/how/why/do`) but FR-DL-1's schema also lists `next[]` and `degrade{}`; the optional/mandatory status of `next[]` and `degrade{}` is unstated (is a `planned` section with no degradation still required to carry `degrade{}`?).
- FR-DL-3 caps affordances with "+K more" but never says the ordering/priority rule that decides which affordances survive the cap — a determinism (FR-DL-8) and provenance (FR-DL-9) hole.
- OQ-3 (interactivity) and NR-4 together bake in "printed hints, no REPL"; the risk that `next[]` schema shape chosen now cannot represent a selectable affordance later is not called out — a forward-compat note would de-risk the deferral without relitigating it.
- OQ-5 (navigator reuse) is named but the requirements do not state the acceptance boundary for the pilot (CLI-only) vs the lever (also generating READMEs), so "done" for v1 is ambiguous.

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Data | high | Resolve the focus-file schema-completeness question explicitly: add a decision to FR-DL-1 on whether records carry `audience` (from 3xl-kcui) and/or `confidence` (from NODE-SCHEMA). If deferred, state so with rationale and a forward-compat note; if adopted, add the field(s) with fill semantics. | The schema is the frozen contract; adding a dimension after records are authored is a breaking migration. The focus file names this as the top unknown and the spec is currently silent. | FR-DL-1 (add a sentence resolving audience/confidence) + a new row in §4 or §0 recording the decision | A reviewer can confirm the resolution: FR-DL-1 either lists the field or §4 records an explicit defer-with-rationale. |
| R1-F2 | Risks | high | Make FR-DL-4's position inference testable: define the threshold (e.g. ">50% of sections `not_defined` ⇒ early DATA MODEL"), a deterministic tie-break for ambiguous mixes, and an **authored-override** field so a record can pin position rather than infer it. | As written ("predominantly", "mostly") the heuristic has no acceptance criterion and no failure-mode handling; the focus file flags "should position be authored, not inferred?" | FR-DL-4 (add threshold + tie-break + `position` override) | Golden test: three fixture plans (all `not_defined`, mixed 50/50, all `planned`) each map to a single deterministic position; an authored `position` overrides inference. |
| R1-F3 | Validation | high | Specify FR-DL-5's fill contract as acceptance criteria: enumerate the placeholder vocabulary (`{{count}}`, `{{missing}}`, `{{cmd}}`, …), name each placeholder's fill-source field on the live plan, and define "validated" (which fields must be present/typed for a fill to be legal). | "Typed error on unfillable placeholder" is untestable without knowing the placeholder set and its sources; CCbC needs a declared contract, not a described intent. | FR-DL-5 (add a placeholder→source table) | For each placeholder, a unit test asserts a legal fill from a valid plan and a typed error from a plan missing the source field. |
| R1-F4 | Data | medium | Clarify mandatory-vs-optional per field in the FR-DL-1 schema: FR-DL-2 mandates `what/how/why/do`; state explicitly whether `next[]` and `degrade{}` are required-but-possibly-empty or omittable, and what a `planned` (healthy) section's `degrade{}` contains. | FR-DL-1 and FR-DL-2 disagree on the field set without reconciling; an implementer cannot tell if an empty `degrade{}` is valid or a schema violation. | FR-DL-1 / FR-DL-2 (add a mandatory/optional annotation per field) | Schema validation test: a record missing `degrade{}` is accepted/rejected per the stated rule; a `planned` section validates. |
| R1-F5 | Data | medium | Define the affordance ordering/cap rule in FR-DL-3: state how `next[]` items are prioritized before the "+K more" cap is applied (e.g. derived-blocking-actions before authored-static, stable sort by section key) so the surviving set is deterministic. | FR-DL-8 (deterministic) and FR-DL-9 (provenance) require byte-stable output; an unspecified cap order makes the visible affordance set nondeterministic. | FR-DL-3 (add the ordering rule) | Golden test: same plan ⇒ identical surviving affordance list and identical "+K more" count across runs. |
| R1-F6 | Interfaces | low | Add a forward-compat note to NR-4/OQ-3: state that the `next[]` record shape (FR-DL-1) SHOULD be expressible as a selectable affordance later (id + label + command triple), so deferring the REPL does not bake in a one-shot-only schema. | The focus file asks whether deferring interactivity "bakes in a wrong boundary"; a schema-shape note answers it without relitigating the deferral (SETTLED-adjacent, framed as scope trade-off). | NR-4 or OQ-3 (add one sentence on next[] shape stability) | Review check: `next[]` entries carry a stable id and machine-usable command field, not only a rendered hint string. |
| R1-F7 | Architecture | low | Give OQ-5 an explicit v1 acceptance boundary: state that the pilot's "done" is CLI output only, and that README generation is a named follow-on gated behind a Hansei, so v1 scope is unambiguous even though the lever stays open. | OQ-5 is the highest-Mottainai lever but leaving its scope open makes the requirements' completion criterion ambiguous; the plan already says "pilot first, then Hansei" — the requirement should say the same. | §4 OQ-5 (add a one-line v1 boundary) | Review check: a reader can state what is in-scope for v1 without consulting the plan. |

**Endorsements & Disagreements:** none — no prior untriaged rounds exist (R1 is the first pass).
