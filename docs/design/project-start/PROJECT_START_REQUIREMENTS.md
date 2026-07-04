# Project-Start Distillation — Requirements

**Version:** 0.4 (Design-conversation update — panel reclassified)
**Date:** 2026-07-04
**Status:** Draft
**Lens:** `docs/design-princples/ACCIDENTAL_COMPLEXITY_ANTI_PRINCIPLE.md`

---

## 0. Planning Insights (Self-Reflective Update)

> Documents what changed between v0.1 (pre-planning) and v0.2 (post-planning).
> The planning pass grounded every claim against real code and found the
> distillation wrong in three material places. Evidence is `file:line`.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| The kernel is one subsystem fronted by one metaphor surface. | There are **three** live onboarding surfaces, not two: `startd8 concierge` (kernel), `startd8 kickoff` (metaphor), **and `startd8 project init`** (`cli_project.py:65`) — a deterministic onboarding command the inventory never listed, and it is VIPP-coupled by construction (`project/init.py:138,142`). | "One surface" (FR-1) is false until `project init` is folded or scoped out. New FR-1a. |
| `derive` is one of four symmetric start-verbs. | `derive` is **brownfield-only** — it raises `ConciergeError("derive-contract requires 'modules'")` on greenfield (`core.py:352`). The greenfield "get your `schema.prisma`" path is a *different, existing* command: `generate contract --promote` from prose (`cli_generate.py:734-771`). | The greenfield kernel is **three** verbs — `survey → instantiate → assess`. `derive` demoted to the brownfield on-ramp (belongs with the un-bundled brownfield capability). FR-1/FR-3 rewritten. |
| `assess` already names the next command (FR-5). | `build_assess` emits blockers with `section/status/consequence` but **no command** (`core.py:298`). Command emission lives only in the Red Carpet advisor (`red_carpet_advisor.py:348`). | FR-5 is **new logic** — absorb the ~40-60-LOC command map only, *not* the ~650-LOC ranked playbook. |
| Un-bundling Panel + VIPP is a doc + default-off change; SOTTO byte-identical "already satisfied" (FR-15). | **Split verdict.** VIPP *seam* is genuinely SOTTO-clean (opt-in, no `import vipp`, `vipp_seam.py:11,250`). The **Panel edge is not**: `assess` **unconditionally** imports `stakeholder_panel` and always injects a `stakeholders` domain (`core.py:256,267`), and `PANEL_CONSUMABLE=True` now couples kernel assess to the panel's ship-state. `project init` **hard-imports** `vipp`. | FR-13/FR-14/FR-15 rewritten: real import-edge surgery, not doc-only. |
| Retiring Red Carpet loses only a re-presentation of assess blockers. | Red Carpet advisor also owns **schema-shape diagnostics** (missing-FK, no-PK, island tables, empty enum) that neither `survey` nor `assess` compute (`red_carpet_advisor.py:181-250`). | New optional FR-5a: port the ~90-LOC diagnostic loop into `assess`, or accept the capability loss (call it out in the navig8 migration note). |
| MCP is read/preview-only *by design* (FR-7). | The MCP tool calls `handle_concierge_tool`, not the `handle_concierge_read` allow-list floor (`startd8_mcp.py:3200`) — it is safe only because write branches *return previews*, not because the action set is gated. | FR-7 nit: make the read-only guarantee **structural** (route through the floor). |

**Resolved open questions:**
- **OQ-1 → Clean map, one function to absorb.** All four verbs already dispatch through `handle_concierge_tool` (`core.py:313`). The only thing the metaphor layer owns that the kernel needs is `_blocker_command` (next-command) + optionally `_schema_advisories`.
- **OQ-2 → Rename `concierge`→`kickoff`, but sequence it.** The name `kickoff` is already taken by the metaphor group `kickoff_app` (`cli.py:1256`). The kernel rename is **blocked** until `kickoff_app` is renamed/retired. Do **not** fold into `project init` — that would drag VIPP into the kernel.
- **OQ-3 → New logic, small.** Absorb `_blocker_command` (~40-60 LOC); reject the ranked playbook (re-imports the retired metaphor).
- **OQ-4 → Keep MCP, rename verbs**, and fix the structural read-only gap (OQ-1/D9).
- **OQ-6 → Real edges.** VIPP seam clean; Panel-in-assess and VIPP-in-`project init` are code changes.
- **OQ-7 → `derive` is brownfield.** Greenfield kernel = 3 verbs; schema from `generate contract --promote`.

### 0.1 Lessons-Learned Hardening (v0.3)

> Consulted `Lessons_Learned/sdk/` (deterministic-codegen + design-docs legs).
> Each check below changed or firmed the draft:

- **[Phantom-reference audit]** — verified every load-bearing `file:line` this
  doc cites directly against source (not via sub-agent). **All pass** (±1 line):
  `derive` raise (`core.py:353`), panel injection (`core.py:256,260`,
  `PANEL_CONSUMABLE` import `core.py:267,274`), VIPP import (`project/init.py:138,142`),
  greenfield `generate contract --promote` (`cli_generate.py:735`), `kickoff`
  name collision (`cli.py:1256-1257`). The distillation rests on real code.
- **[Single-source vocabulary ownership]** — `core.py:38-41` documents that
  `stakeholders` is co-located in the shared assess input-domain list *on
  purpose*, so "which inputs count" cannot drift between `assess` and the
  advisor. **Impact:** FR-13's edge-cut must **preserve that single-source of
  "which inputs count" without importing `stakeholder_panel`** — i.e. move the
  domain list ownership into the kernel, don't just delete the injection. Added
  to FR-13.
- **[Prune phantom scope]** — `derive` as a greenfield start-verb was phantom
  scope (architecturally brownfield); already pruned to FR-3 / the brownfield
  on-ramp in v0.2.
- **[Depth-of-coupling check]** — `project init` is VIPP-coupled at ~7 sites
  (posting, inbox scaffold, seq, gitignore, negotiate/apply guidance, status),
  not one import (`project/init.py:138-408`). **Impact:** FR-1a's "fold" option
  is a larger lift than a single opt-in flag; noted there.
- **[CRP steering]** — least-reviewed artifact = this doc (brand-new, no prior
  external review). Settled / do-not-relitigate for CRP: the essential model, the
  3-verb kernel + brownfield on-ramp, and the anti-principle lens. Carried into
  the focus file for Phase 5. *(Note: "un-bundle Panel" is no longer settled — it
  was reopened and re-decided in §0.2 below.)*

### 0.2 Design-Conversation Update (v0.4) — the Stakeholder Panel reclassified

> v0.1–v0.3 tagged the Stakeholder Panel a **`[COMPENSATORY]` scope breach** and
> slated it for un-bundling. A design conversation reversed that. This section
> records the reversal and its reasoning; FR-13 is rewritten accordingly.

**The error being corrected.** The v0.1–v0.3 analysis collapsed two different
jobs and swung the bucket rule at both:
- **Authoring the real value content** (bucket 4 — the SDK correctly shouldn't).
- **Surfacing high-level capability ideas for the human to judge** — *requirements
  discovery*, which is **not a bucket at all**. It is the DATA-MODEL *front
  bookend* CLAUDE.md itself names as the highest-leverage human activity
  (*"human leverage concentrates at DATA MODEL … the contract bucket-1 derives
  from"*). The panel feeds that bookend; the bucket rule (a fence around bucket 4)
  does not reach it. **The bucket-rule breach finding was wrong** — see the
  corrected §1 callout.

**The distinction that carries it (breadth vs. precision).** The panel's personas
are strong at *breadth* and structurally weak at *precision*:
- **Breadth = discovery** (*"you have no funnel KPIs at all — a demo-stage product
  usually tracks signup and activation"*). Real value; the LLM can do it from a
  thin brief because it is pattern-level; the human keeps the judgment.
- **Precision = value-drafting** (*`signup_rate: 8%`*). Fake value; the specific
  number needs project grounding the persona (brief-only, no product/market
  context — `persona.py:48`) cannot have. This is the "something an LLM estimated
  had value" the panel must **not** do.

**Concrete evidence (the 8% example).** `panel recommend` on a blank
`product_funnel.signup_rate` sends the Product Owner persona a one-line drafting
prompt (`recommend.py:94-106`) and gets back `TARGET: 8% || WHY: …realistic launch
baseline…`, persisted as `provenance:"estimate"`. The persona has no way to know
the real rate — it is industry-generic filler in a confident wrapper. This is the
ghost; it is dropped (new NR-7).

**"Still needs human ratification" was misread as a weakness — it is the feature.**
It is the guardrail that keeps the panel on the discovery side of the line: the
panel brings raw material, the human brings vision/judgment/insight. A discovery
aid that did *not* require human judgment would be the real scope breach.

**The reclassified model** (governing principle: *meet the user where they are;
offer tools where needed* — StartDate-style solo projects rarely need this, a
multi-stakeholder benchmark portal does):

| Function | Status | Cost |
|----------|--------|------|
| **ID what needs populating** (coverage) | **Essential — already exists** in the `instantiate` templates (`<...>` placeholders) + `assess` unfilled-field reporting | $0, keep |
| **Discovery** — persona surfaces *missing dimensions* the templates don't list | **Essential, conditionally offered** by project shape | LLM, breadth |
| **Shaping range** — persona offers an estimated *range* + reasoning to help the human place the real value | **Optional, honest** — the salvaged sliver of Teian | LLM, envelope-not-point |
| **Value-drafting** (`8%`) | **Dropped — ghost** (NR-7) | gone |

The three survivors chain: the $0 coverage signal **triggers** the conditional
discovery offer, discovery **invokes** a persona, who may offer a **shaping range**
on a specific field. One flow, three honest steps, no fabricated answers. The
essential act is **identifying a value that needs populating — never the
population itself**; and that identification is the cheapest thing in the stack,
already deterministic.

**What did NOT change:** VIPP is still un-bundled (FR-14). Welcome Mat / Red Carpet
still retire (FR-9–12). Teian's *drafting* dies (NR-7); its *coverage signal*
survives as the discovery trigger.

---

## 1. Problem Statement

The process to start a new project with the SDK has accreted into a stack of
overlapping metaphors — **Concierge**, **Welcome Mat**, **Red Carpet**,
**Stakeholder Panel / Kaigi**, **Teian**, **VIPP** — each shipped as its own
subsystem. No single decision was wrong; the *accumulation* is (anti-principle
L5). The result is a disjointed user experience for the one job that matters:
getting a project to a build-ready set of inputs.

Applying the **Rube Goldberg Test** (*"does this layer solve the problem, or
compensate for a decision made by a previous layer?"*) to the stack finds one
shared upstream decision (L3) driving all the accidental layers:

> **"The SDK should *host* project setup as an interactive, agentic,
> multi-surface experience"** — rather than *define the input contract cleanly
> and let the human's own agent fill it in.*

The user already has an agent (Claude Code / Cursor). The SDK built its own chat
panel, conductor, and persona council — re-implementing, inside the SDK, the
conversational surface the user already has open. That is the deepest accidental
complexity: **the SDK duplicating the harness.**

### The essential problem, restated

Move a project from *raw/nothing* → *a complete, honest, build-ready set of
input files the $0 cascade can consume*. The irreducible transformations are
five: **discover** what exists → **translate** it into the grammar → **fill**
what's missing → **validate** readiness → **write** safely at human privilege.

### Inventory, tagged (anti-principle discipline)

| Subsystem | What it really is | Tag | Verdict |
|-----------|-------------------|-----|---------|
| **Concierge** (`concierge/`) — survey/assess/instantiate/derive-contract | The read+translate+write core; maps 1:1 onto the five transformations | **`[ESSENTIAL]`** | The kernel. Keep, rename by function. |
| **Welcome Mat** (`kickoff_experience/`, 26 mod) — served web/TUI GUI + per-field capture-write | A *rendering* of `assess` + a read-modify-write-into-YAML seam | **`[COMPENSATORY]`** | Retire (phased). The report is essential; the served app is not. |
| **Red Carpet** (`red_carpet*.py`) — conductor + advisor + wizard | A second ranked re-presentation of `assess` blockers | **`[COMPENSATORY]`** | Retire. Its own docs: "never a gate; removing it does not change `cascade_offerable`." |
| **Stakeholder Panel / Kaigi** (`stakeholder_panel/`) — personas surface missing capabilities/dimensions | Requirements *discovery* at the data-model bookend (breadth, human judges) | **`[ESSENTIAL]`, conditionally offered** | Keep as a project-shape-triggered discovery tool (§0.2). |
| **— Teian value-drafting** (`recommend`) — persona drafts specific blank-field *values* (`8%`) | LLM estimating precision it can't ground | **`[GHOST]`** | Drop (NR-7). Its $0 coverage signal survives as the discovery trigger. |
| **VIPP** (`vipp/`, 10 mod) — cross-process negotiator/applier | Automates "human applies," across a process boundary, vs. Sapper | **`[COMPENSATORY]`/`[DEFENSIVE]`** | Un-bundle → separate "brownfield migration" capability. |

### Bucket-rule scope — where it applies, and where it does NOT (corrected)

CLAUDE.md fixes the SDK's LLM-generation scope: bucket 2 (placeholder content) is
"~zero importance… do not invest in making it good"; bucket 4 (real content) is
"the USER's job, NOT the SDK's." The rule is a fence around **bucket 4**.

An earlier draft (v0.1–v0.3) swung that fence at the Stakeholder Panel and called
it a scope breach. **That was wrong** (reversed in §0.2). The rule does not reach
the panel's essential job, because that job is not in any bucket:
- **`[GHOST]` — Teian value-drafting** *does* violate the rule's spirit: it has the
  LLM estimate specific value content (`signup_rate: 8%`). Dropped (NR-7).
- **`[ESSENTIAL]` — discovery** does **not**: surfacing *which capabilities/values
  a project of this shape typically needs* is **requirements discovery** — the
  DATA-MODEL front bookend CLAUDE.md names as the *highest-leverage* human
  activity, feeding bucket 1. The human keeps vision/judgment/insight; the panel
  only surfaces raw material for that judgment. Fencing this off mis-applies a
  bucket-4 rule to the front bookend.

The discriminator is **breadth vs. precision** (§0.2): the LLM may surface *what
might be missing* (breadth, real value); it may not *estimate the specific value*
(precision it cannot ground).

---

## 2. Requirements

### The kernel — `startd8 kickoff` (four plain verbs, zero metaphor)

- **FR-1 — Single surface, three greenfield verbs.** The project-start process is
  exactly one CLI surface, `startd8 kickoff`, whose **kernel** is three
  subcommands named by function: `survey`, `instantiate`, `assess`. `derive`
  (FR-3) is a fourth subcommand on the same surface but is the **brownfield
  on-ramp**, not a greenfield start-verb. No metaphor names survive in the
  user-facing vocabulary (no "Concierge", "Welcome Mat", "Red Carpet", "VIPP",
  "Panel"). *Sequencing constraint (OQ-2): the name `kickoff` is currently held
  by the metaphor group `kickoff_app` (`cli.py:1256`); the kernel rename of
  `concierge`→`kickoff` is blocked until `kickoff_app` is renamed/retired
  (FR-9/FR-12).*

- **FR-1a — Reconcile the third surface (`project init`).** `startd8 project
  init` (`cli_project.py:65`) is a fourth accidental onboarding surface the v0.1
  inventory omitted, and it **always establishes a VIPP posting via a hard import**
  (`project/init.py:138,142`). Its disposition must be decided: either (a) fold
  its greenfield instantiate path into `kickoff instantiate` and make its VIPP
  posting opt-in (FR-14), or (b) explicitly scope it out of the kernel. It may
  not remain an always-on, VIPP-coupled second onboarding entrypoint while FR-1
  claims "one surface."

- **FR-2 — `survey` (discover).** Read-only, $0, no LLM. Reports what the project
  already has that is relevant to the input contract: requirement/PRD docs (and
  whether each matches the deterministic extraction format), existing
  Pydantic/data models, test-fixture candidates, and filename-based PII/personal-
  material risk flags. Never opens a flagged file (path/name heuristics only).
  *Already fully implemented (`build_survey`, `core.py:91`) — overspecified;
  no new work.*

- **FR-3 — `derive` (brownfield translate — NOT a greenfield start-verb).**
  Reverse-derive a *candidate* `schema.prisma` from **existing** data models. It
  hard-requires `modules` and raises on greenfield (`core.py:352`), so it cannot
  *start* a greenfield project. Output carries an `unratified` provenance header;
  `derive` never writes the live contract — it emits a candidate for the human
  (their agent) to review and ratify. `--check` reports drift. **Greenfield users
  get their `schema.prisma` from the existing `generate contract --promote`**
  (from prose, $0, `cli_generate.py:734`), which NR-6 says not to re-author.
  `derive` is presented on the kickoff surface as the brownfield on-ramp and is
  the natural companion to the un-bundled brownfield capability (FR-14).

- **FR-4 — `instantiate` (scaffold inputs).** Write the honest starter input-file
  package into the consuming project at human privilege: the four kickoff-input
  domain YAMLs (business-targets, observability, conventions, build-preferences),
  the stakeholders roster YAML, and the intro/inputs-explained docs. Every
  written value is **provenance-marked** and never faked as authored. Preview by
  default; `--apply` to write.

- **FR-5 — `assess` (validate + next step).** Read-only, $0. Report onboarding
  readiness keyed to the exact input domains the $0 cascade consumes: per-domain
  provenance, the cascade shape/status/blockers (reusing the wireframe machinery,
  never recomputing provisioning state), and deployment posture. **Critically,
  `assess` names what is missing AND emits the exact next command** to move
  forward — this is the handoff surface. *This is **new logic**: `build_assess`
  today emits blockers with no command (`core.py:298`). Scope = port only the
  section→command map `_blocker_command` + constants (~40-60 LOC,
  `red_carpet_advisor.py:63-73,348-358`), attaching a `next_command` to each
  blocker and a headline `next_command` to the report. **Explicitly reject**
  absorbing the ranked playbook (`build_playbook`/`derive_advisories`/`ranking.py`,
  ~650 LOC) — it re-imports the very metaphor being retired.*

- **FR-5a — (Optional) Preserve schema-shape diagnostics.** Red Carpet's advisor
  is the *only* place that computes $0 schema-shape diagnostics — missing-FK,
  no-PK, island tables, empty enum (`red_carpet_advisor.py:181-250`). Retiring
  Red Carpet loses this signal unless it is ported into `assess` (~90 LOC). This
  requirement is optional: either port it, or accept the loss and name it
  explicitly in the navig8 migration note (FR-11).

- **FR-6 — The handoff, not the host.** The SDK's job ends at "here are honest
  input files and here is exactly what is still blank + the command to address
  it." The human's own agent fills the blanks by editing the input files
  directly. The SDK does **not** serve a web app, embed a chat loop, run an
  agentic conductor, or role-play stakeholders as part of project-start.

### The safe-write floor

- **FR-7 — Human-privilege, confined writes; no silent LLM writes.** All kernel
  writes (`instantiate`, and any future capture) go through a single safe-write
  chokepoint that enforces root confinement (no traversal/symlink escape, atomic
  dir-fd-relative writes). Over any LLM-invoked surface (e.g. MCP), the kernel is
  read/preview-only; the CLI, running at the human's own privilege, is the sole
  writer. `--apply` is a safety control (no silent writes), not an authorization
  control. *Nit (D9): today the MCP tool routes through `handle_concierge_tool`,
  not the `handle_concierge_read` allow-list floor (`startd8_mcp.py:3200`), so
  read-only is incidental (write branches happen to return previews) rather than
  structural. Make it structural — route the MCP path through the read floor.*

- **FR-8 — Honest inputs (provenance discipline).** Every value the kernel writes
  carries provenance (`default` / `config-default` / `unratified` /
  `estimate` / `authored`). The kernel never writes a value labeled as `authored`
  that it did not receive from a human. It leaves blanks as clearly-marked TODOs
  rather than synthesizing content to fill them.

### Phased retirement of the COMPENSATORY layers

- **FR-9 — Nothing deleted until the kernel spec lands.** Welcome Mat GUI, Red
  Carpet, and Teira/Teian code remain in the tree during the transition. This
  requirement gates removal on the kernel being the documented, shipped surface.

- **FR-10 — Deprecation markers.** Each retiring surface (Welcome Mat serve/web,
  Red Carpet CLI commands, Teian `panel recommend`) emits a deprecation notice
  pointing to the `startd8 kickoff` verb that replaces it, and is documented as
  `[COMPENSATORY]` debt in this doc's retirement table.

- **FR-11 — Consumer migration (navig8).** The one known live consumer of the
  onboarding surface is `navig8`. Retirement must include a migration note /
  runbook so navig8 (and any other consumer) can move from the retiring surfaces
  to the four kernel verbs without losing capability it actually used.

- **FR-12 — Removal criteria.** Define the objective condition under which the
  retired code is deleted (not just deprecated): kernel verbs shipped +
  consumer(s) migrated + no external caller in the deterministic-provider entry
  points. Removal is a later, separate change.

### Discovery (conditionally offered — the reclassified panel)

- **FR-13 — Discovery is a project-shape-triggered tool, not a mandatory step
  (reclassified in §0.2).** The Stakeholder Panel's *discovery* function — personas
  surfacing **missing capabilities/dimensions** a project of this shape typically
  needs — is retained as an **`[ESSENTIAL]`, conditionally-offered** aid at the
  data-model bookend, **not** un-bundled (reverses v0.1–v0.3). Governing rule:
  *meet the user where they are; offer tools where needed.*
  - **Coverage (the trigger) already exists and is $0.** "Which values need
    populating" is surfaced today by `instantiate` templates (`<...>`
    placeholders) + `assess` unfilled-field reporting. The essential act is
    **identifying** the gap, not filling it — and it is already the cheapest thing
    in the stack. No new subsystem for the coverage core.
  - **The offer is conditional.** `survey`/`assess` decide *whether to offer*
    discovery from project-shape signals (number of distinct stakeholder roles,
    regulatory/domain surface, solo-vs-team, blank-canvas-vs-rich-brownfield).
    Solo single-user projects (StartDate) get silence; multi-stakeholder projects
    (benchmark portal) get the offer. Offering costs $0; only accepting spends.
  - **Discovery output is breadth, human-judged.** A persona surfaces *what might
    be missing*; the human decides. Every surfaced item is provenance-marked
    non-authored and requires human ratification — that ratification is the
    guardrail (§0.2), not a weakness.
  - **Preserve the single-source (`core.py:38-41`).** The "which inputs count"
    domain list is deliberately shared so `assess` and any advisor can't drift.
    Ownership of that list moves **into the kernel**; discovery reads it. The
    kernel must not hard-import `stakeholder_panel` for its coverage core — the
    persona/discovery layer loads only when the offer is accepted (SOTTO,
    FR-15).

- **FR-13a — Shaping ranges, never point values (the "no-8%" rule).** When a
  persona speaks to a *specific* field value, it may offer an **estimated range +
  reasoning** to shape the human's answer (e.g. *"early demo funnels typically
  land 5–15%"*) — it may **not** emit a single point value as a draft (e.g.
  `signup_rate: 8%`). A range wears its uncertainty on its face and hands the
  human an envelope to place the real value in; a point value hides its
  uncertainty and invites blind acceptance. This is the breadth/precision line
  (§0.2) made enforceable. See NR-7 for the dropped point-value drafter.

### Un-bundling (out of the project-start story)

- **FR-14 — VIPP → separate capability (requires de-coupling `project init`).**
  VIPP is removed from the project-start narrative and re-filed as an independent
  "brownfield migration / auto-adjudication" capability. Its value is concentrated
  in brownfield (real Sapper ground truth); greenfield start is near-pure
  pass-through. **Correction:** VIPP coupling does not live in the kernel
  (`concierge/` has zero `vipp` imports) — it lives in `project init`, which
  **hard-imports `startd8.vipp` and always posts it** (`project/init.py:138,142`).
  Un-bundling requires making that VIPP posting **opt-in** (`--with-vipp` for
  brownfield), so the default onboarding path is byte-identical without VIPP.

- **FR-15 — Per-seam SOTTO invariant (split claim).** The v0.1 blanket "byte-
  identical when absent — already satisfied" is **half wrong**:
  - **VIPP seam — satisfied.** `vipp_seam.py` does not `import vipp`, is opt-in
    (`vipp_opted_in`), and `maybe_serialize_buffer` writes nothing when absent
    (`vipp_seam.py:11,82,250`). Keep this invariant; assert it per-seam with
    evidence.
  - **Panel-in-assess — must become opt-in-loaded.** Today the package's mere
    presence ⇒ a populated `stakeholders` block (`core.py:256,267`); the
    try/except only degrades on partial checkout. Under the reclassification
    (FR-13) the **coverage core is kernel-owned and imports nothing from
    `stakeholder_panel`**; the persona/discovery layer loads **only when the
    conditional offer is accepted**. Target invariant: with no discovery accepted,
    `assess` output is byte-identical to a build that never knew the panel
    existed — the offer is additive, the acceptance is where cost/effect begin.
  Only assert byte-identical-when-absent **per seam, with evidence** — never as a
  blanket claim.

---

## 3. Non-Requirements

- **NR-1 — No served web/TUI onboarding app.** Project-start does not ship or
  serve an interactive GUI. Readiness is a CLI report.
- **NR-2 — No embedded agentic loop for project-start.** The kernel does not run
  an LLM chat/conductor. The user's own agent is the interactive surface.
- **NR-3 — No *mandatory* stakeholder role-play, no point-value drafting.** The
  kernel does not force stakeholder role-play on every project and never
  auto-drafts specific field *values*. *(Nuanced in §0.2: discovery — surfacing
  which capabilities/values may be missing — IS retained, but only as a
  project-shape-triggered offer (FR-13), and personas may offer shaping *ranges*
  not point values (FR-13a). The prohibition is on precision the LLM can't
  ground, not on breadth-level discovery.)*
- **NR-4 — No cross-process applier in the kernel.** No proposal-serialization
  inbox, no auto-adjudication against ground truth, as part of project-start.
- **NR-5 — Not deleting the un-bundled/retired code in this change.** This is a
  requirements + phased-retirement plan, not a deletion PR.
- **NR-6 — Not re-authoring the deterministic $0 cascade.** The kernel produces
  inputs *for* `generate backend/scaffold/views/frontend`; it does not change how
  the cascade consumes them.
- **NR-7 — No point-value field drafting (Teian dropped).** The proactive
  value-drafter (`panel recommend` → `Recommendation` with `provenance:"estimate"`,
  `recommend.py`) is removed. Evidence it is the ghost: on a blank
  `product_funnel.signup_rate` it emits `8%` from a persona that sees only its own
  brief — industry-generic filler pretending to project knowledge (§0.2). Its one
  worth-keeping byproduct — the **$0 coverage signal** ("these fields are blank")
  — survives as the FR-13 discovery *trigger*, not as a drafter.

---

## 4. Open Questions

_OQ-1 through OQ-4, OQ-6, OQ-7 resolved in §0 by the planning pass. Remaining:_

- **OQ-5 — Retirement blast radius (navig8).** What exactly does navig8 consume
  today — which verbs / which surfaces? Planning verified navig8 uses
  `derive-contract` (`derive/mapper.py`, `introspect.py`) but could not read the
  navig8 repo to confirm whether it touches Welcome Mat / Red Carpet. Determines
  the migration note's contents (FR-11) and whether FR-5a (schema diagnostics) is
  load-bearing for them. **Needs a look at `~/Documents/dev/navig8/`.**
- **OQ-8 — `project init` disposition (FR-1a).** Fold-and-opt-out-VIPP vs.
  scope-out. Leaning fold (single surface), but the greenfield instantiate paths
  of `project init` vs. `instantiate-kickoff` must be diffed first to know if
  they are the same package or two divergent ones.
- **OQ-9 — Does `derive` stay on the `kickoff` surface or move entirely to the
  brownfield capability?** It is on-surface today (`concierge derive-contract`).
  Keeping it there preserves one surface but blurs the "greenfield kernel = 3
  verbs" story; moving it fully to the brownfield capability sharpens the story
  but splits the surface. Decide during CRP.
- **OQ-10 — The discovery-offer trigger (FR-13).** What exact, cheap signals make
  `survey`/`assess` offer discovery? Candidates: count of distinct stakeholder
  roles in the roster, count of high-value blank fields, presence of a
  regulatory/compliance domain, solo-vs-team, greenfield-vs-brownfield. Must be
  $0/deterministic (the trigger can't itself spend). Needs a concrete rule + a
  default-off bias so a false trigger is a quiet, ignorable one-line offer, never
  a gate. Decide during CRP.
- **OQ-11 — Where does the retained discovery capability live?** The persona/agent
  machinery (`stakeholder_panel/` minus `recommend`) is still ~20 modules. Is the
  *conditionally-offered discovery* a thin caller the kernel owns that invokes a
  slimmed panel, or does the panel package stay whole and the kernel just gates
  the call? Reconcile "keep discovery" with the anti-principle: rescuing the
  *purpose* did not bless the current module count — a distillation pass on the
  discovery implementation is still owed.

---

*v0.2 — Post-planning self-reflective update. 3 requirements materially
corrected (FR-1 four→three verbs + `derive` demoted; FR-5 confirmed new logic;
FR-13/14/15 confirmed code-not-doc changes), 2 requirements added (FR-1a third
surface, FR-5a schema diagnostics), 6 open questions resolved, 3 new ones
surfaced. The distillation survives — but "one surface, four symmetric verbs" was
wrong: it is one surface, **three greenfield verbs + a brownfield on-ramp**, and
un-bundling is real import surgery in `assess` and `project init`.*

*v0.3 — Post lessons-learned hardening. Applied 5 lessons: phantom-reference
audit (all `file:line` verified against source), single-source vocabulary
ownership (FR-13 must preserve the "which inputs count" list), prune phantom
scope (`derive` demoted), depth-of-coupling check (`project init` VIPP-coupled at
~7 sites), CRP steering (focus file assembled). Ready for CRP review.*

*v0.4 — Design-conversation update. **Reversed** the Stakeholder Panel un-bundling:
its *discovery* function is reclassified `[ESSENTIAL]`, conditionally offered
(FR-13) — requirements discovery is the DATA-MODEL front bookend, not a bucket-4
breach; the earlier bucket-rule finding was wrong (§1 corrected). Split the panel:
discovery kept (breadth), point-value drafting dropped as the ghost (NR-7, the
"8%" example). Added FR-13a (shaping ranges, never point values), nuanced NR-3,
reframed the panel half of FR-15 (opt-in-loaded, kernel-owned coverage core),
added OQ-10 (offer trigger) + OQ-11 (discovery still owes a distillation pass).
Governing rule: meet the user where they are; offer tools where needed. VIPP
un-bundling and Welcome Mat / Red Carpet retirement unchanged.*
