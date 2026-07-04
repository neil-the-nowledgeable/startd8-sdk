# Project-Start Distillation — Requirements

**Version:** 0.13 (Eighth experiment — Tier-1 LIFTS a valid kickoff, on the real portal)
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

### 0.3 Consumer Validation — 3 real apps (natural experiment)

> Checked the three apps mid-kickoff against the distilled model. They form a
> near-perfect natural experiment (2 solo, 1 multi-stakeholder-domain). Evidence
> is on-disk artifacts, not assumptions.

| App | Shape | Consumed | Retiring surfaces used |
|-----|-------|----------|------------------------|
| **navig8** | solo, brownfield (legal) | kernel only: `instantiate` + `derive` (load-bearing), survey/assess → wireframe/generate | **none** — no roster, no `.startd8/vipp/` |
| **household-o11y** | solo, brownfield_ready | kernel: survey/assess/instantiate + **VIPP** ($0, ACCEPT 2/REJECT 1) | **none** — no roster, no Panel/Teian/RC/WM |
| **benchmark portal** | solo-operated, **multi-stakeholder domain** | kernel: instantiate + `generate contract` + **VIPP** ($0) + **Panel** (14-persona roster) + `project init` | Red Carpet doc-referenced only; WM/Teian none |

**Validated:**
- **Kernel is real** — all three consumed only kernel verbs (+ VIPP). `derive` is
  confirmed load-bearing for brownfield (navig8's whole contract came from it).
- **"Solo → silence" holds 2/2** — navig8 + household-o11y are solo, authored no
  roster, never touched the Panel. Confirms FR-13's conditional-offer default.
- **Retirement is de-risked** — Welcome Mat / Red Carpet / Teian used by **none**
  of the three (Red Carpet only as doc guidance). **OQ-5 resolved: navig8
  migration impact = zero.**

**Challenged / refined:**
- **VIPP is actively used (2/3 apps), always $0, doing real schema-adjudication**
  (household caught a typo'd field; portal adjudicated `Run.name` vs `Run.naem`).
  Un-bundle-as-opt-in is *confirmed correct* (apps **opted in** and got value;
  opt-in ≠ deleted), but the "brownfield migration" framing undersells it —
  VIPP's real job is *adjudicate proposals against existing ground-truth*, used
  continuously **once a schema exists**. "Greenfield near-pure pass-through" is
  still true; it's just that none of the live apps are *at* the greenfield moment
  anymore. FR-14 reframed.
- **Discovery value NOT proven end-to-end.** The portal's 14-persona roster is
  rich + partly adversarial, but was **provisioned, not exercised** (no `ask-all`
  output). Only the 5-role reviewer *pilot* is proven — and it *did* discriminate
  (frontend persona correctly *deferred* a Go question). **Wrinkle:** the human
  *authored* the 14 personas himself — so *"discover which stakeholders matter"*
  was done by the human, not the panel; only *"given personas, they answer
  discriminatingly"* is proven. Sharpens OQ-10 (trigger = domain viewpoint-
  multiplicity, not team size) and adds OQ-12 (discovery-proof gap).
- **`project init` is the actual onboarding path for 2/3 apps** (household +
  portal); navig8 used `concierge instantiate` directly. Confirms FR-1a's third
  surface is live, and the fold-vs-scope-out call affects the path most apps
  took (OQ-8).

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
  - **FR-13b — The value is the FACILITATION STRUCTURE, not the roster (v0.9,
    fourth-run evidence).** Cold "name a gap" questions make the panel a mirror
    (echo). What converts it to a **lens** is modeling a real kickoff: (1) a shared
    **project context + business objective + strategy** block the personas reason
    *from*; (2) **means-ends probing** ("given this objective/strategy, what tactics
    in YOUR domain, what breaks, what are we not thinking about?") that forces
    derivation rather than recall; (3) **cross-role tension/convergence** surfacing;
    (4) **synthesis**. This is the load-bearing requirement — a persona roster
    without this facilitation scaffold reverts to a mirror. The high-leverage
    implementation work is the scaffold, not the personas. **(5) mixed-model
    personas** — assign personas across independent model families (Claude / GPT /
    Gemini) so that cross-role *convergence* becomes model-independent evidence
    rather than a shared-model artifact (fifth-run finding); this is the concrete
    mitigation for the correlated-blind-spot limit and a first-class facilitation
    lever. (Note: the current
    `persona.py` "answer only from the brief" prompt did NOT block facilitated mode
    — personas engaged with context supplied in the question — but doing it *well/
    repeatably* wants first-class support for a shared-context/objective block,
    per-role means-ends templates, an optional cross-role round, and synthesis.)
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
    guardrail (§0.2), not a weakness. *Evidence status (OQ-12, experiment run
    2026-07-04): **roster-discovery is DROPPED** — the `panel ask-all` run
    surfaced no viewpoint the human hadn't already authored. **Capability-discovery
    is retained but honestly scoped: low-yield** (1 genuine novel gap per 14 paid
    calls) and **best from operationally-specific personas** (the one hit came from
    the operator; generic role-labels echoed or refused). FR-13's value is "an
    occasional real gap worth sifting for," NOT "systematic coverage of what you'd
    miss." This further raises the bar on OQ-11 (does a low-yield aid justify ~20
    modules?) and OQ-10 (offer only where operationally-specific personas exist).
    A second run (CONTENT question) yielded **0 novel items** but showed a distinct
    **consensus/prioritization** value (cross-audience agreement on load-bearing
    content) and confirmed the panel **stays out of bucket-4** even aimed at
    content (names requirements, never writes copy). Combined 28-call discovery
    rate = 1/28 → whatever survives must be thin. A **third** run (retail team,
    flagship) yielded 0/10 cold — confirming the mirror in cold mode. **But a
    FOURTH run reversed the framing: run as a faithful FACILITATED process (shared
    objective + strategy, means-ends probing), the mirror became a LENS** — ~4/10
    roles produced genuine non-obvious derivations (bundling → FX-margin trap;
    bundling → CurrencyService QPS + float risk) and finance+payments independently
    converged on a derived risk. **Net: mirror when cold, lens when facilitated.**
    FR-13's value is the **facilitation STRUCTURE** (context + objective→strategy→
    tactics + means-ends + cross-role tension + synthesis), not the roster — and the
    value concentrates in roles with analytical leverage against the specific
    strategy probed. Bounds: competent-generalist grade, synthetic/ratify. This
    revives FR-13 with a concrete design direction (see the reclassification below).*
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

- **FR-14 — VIPP → separate *opt-in* capability (requires de-coupling `project
  init`).** VIPP is removed from the project-start *kernel* and re-filed as an
  independent, **opt-in** capability. **Framing corrected by consumer evidence
  (§0.3):** VIPP is *actively used* — 2/3 live apps ran it, always at $0, doing
  real *proposal-adjudication against existing ground-truth* (catching a typo'd
  schema field; adjudicating `Run.name` vs `Run.naem`). So the earlier
  "brownfield migration" label is too narrow — VIPP's real job is *validate
  proposals against the project's ground-truth, once that ground-truth (a schema)
  exists*, and it is used continuously, not just at migration. The key variable is
  **"does the project have ground-truth yet,"** not solo-vs-team. **Un-bundle
  stays correct — as opt-in, not deletion:** the apps *opted in* and got value;
  the requirement is only that VIPP is not *mandatory kernel*. Coupling lives in
  `project init`, which **hard-imports `startd8.vipp` and always posts it**
  (`project/init.py:138,142`); make that posting **opt-in** (`--with-vipp`) so the
  default start path is byte-identical without VIPP. Rename the destination
  capability from "brownfield migration" → **"ground-truth proposal adjudication"**
  (brownfield migration is one use, not the definition).

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

- **OQ-5 — Retirement blast radius (navig8). RESOLVED (§0.3).** navig8 consumed
  **kernel only** — `instantiate` + `derive` (load-bearing, brownfield), survey/
  assess → wireframe/generate. **No** Welcome Mat / Red Carpet / Teian / Panel /
  VIPP; no `stakeholders.yaml`; no `.startd8/vipp/`. **Migration impact = zero.**
  Its friction is routed to an SDK-side markdown log (doc-only reference that goes
  stale if the friction path moves). FR-5a schema-diagnostics: no evidence navig8
  depends on them.
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
  `survey`/`assess` offer discovery? **Refined by §0.3:** the discriminator is
  **domain viewpoint-multiplicity, NOT team size** — all three live apps are
  solo-*operated*, yet only the benchmark portal has many distinct *viewpoints*
  (14, partly adversarial). So key on: an authored roster with N≥threshold
  distinct roles, presence of competing/external viewpoints (vendors, press,
  regulators), regulatory/compliance domain — not "is there a team." Must be
  $0/deterministic; default-off bias so a false trigger is a quiet one-line offer,
  never a gate. **Refined by OQ-12:** favor *operationally-specific* personas
  (concrete hands-on relationship to the artifact — operator, SRE, security) over
  generic role-labels (SE-manager, backend), which echoed or refused. A roster of
  abstract role-labels is a weak trigger; a roster with real operational owners is
  a strong one. Decide during CRP.
- **OQ-12 — Prove discovery end-to-end. RESOLVED — experiment run 2026-07-04.**
  Ran `panel ask-all` (Haiku, $0.00x) on the benchmark-portal 14-persona roster,
  one gap-elicitation question, judged against the portal's schema + FRs + known-
  deferred list. **Result:** 2 honest refusals (thin-brief personas deferred to
  the human — the guardrail working), **10 echoes** (persona restates its own
  briefed lens or a capability already on disk; the 3 vendor-comms personas gave
  the *same* spec-hash-lookup idea), 1 out-of-scope product idea (customer: "run
  it on my stack" — brushes a non-goal), and **1 genuine novel gap** (the
  **operator**: a *score-change audit trail* — who changed which cell's score,
  when, why — absent from the schema, which has only flat timestamps + a `locked`
  flag, and absent from the backlog). **Findings:**
  - **Roster-discovery DISPROVEN on this app** — the panel surfaced no viewpoint
    the human hadn't already authored. FR-13's "surfaces viewpoints you'd have
    missed" claim does not hold; **dropped** (see FR-13 evidence note).
  - **Capability-discovery = real but low-yield** — 1 genuine gap / 14 paid calls.
    Non-zero (the audit-trail gap genuinely matters for an adjudication system),
    but not systematic coverage.
  - **Usefulness tracks operational specificity, not stakeholder count** — the one
    hit came from the persona with a hands-on operational relationship to the
    artifact (the operator); generic role-labels echoed or refused. Refines OQ-10:
    the trigger/roster should favor operationally-specific personas.
  - **Second run — CONTENT question (same roster, 2026-07-04).** Asked "what
    content should the portal present." Result: 1 refusal (security correctly
    deferred content as out-of-remit — lens integrity), 3 off-question (dev/ops
    artifacts), 10 echoes, **0 genuinely novel content.** Two decisive findings:
    (i) **content-discovery yield is zero — even lower than capability (1/14)**;
    convergent publication content (provenance + methodology) leaves little to
    "discover." (ii) **The panel behaved as a CONSENSUS/prioritization
    instrument, not a discovery one** — ~6 personas independently converged on
    "spec-hash beside every result," ~4 on "methodology-first framing," telling
    you what content is load-bearing *across* audiences (soft validation value,
    changed nothing here). (iii) **The bucket-4 boundary HELD unprompted** — every
    persona named a content *requirement* ("display the spec-hash," "a methodology
    section"), **none wrote actual copy.** Direct evidence for §0.2: aimed straight
    at content, the panel still produces *what should exist*, not *the real
    words* — breadth-not-precision holds under pressure, so this is not a bucket-4
    breach.
  - **Third run — different project + FLAGSHIP model (2026-07-04).** Ran capability
    discovery on the **ContextCore Blue Planet Adventures retail team** (10 personas
    freshly migrated from the old `contextcore.io/v1alpha1 PersonaManifest` format —
    which the strict parser rejected — into the newest strict roster) using
    **Gemini 3 Pro flagship** (`gemini:gemini-3.1-pro-preview`), to test the
    counter-hypothesis "an unspecced project + a stronger model discovers more."
    **Result: 0 novel / 10 — every persona restated its own brief**, several reusing
    verbatim phrases authored into their `known_positions`. **The flagship produced
    MORE echo than Haiku, not more discovery** — a stronger model is better at
    staying in character (`persona.py`: "the brief above is your ENTIRE
    knowledge"), so capability amplifies *fidelity to the brief*, not insight.
  - **Combined verdict of runs 1-3 (38 cold calls = 1 novel): cold-question mode
    is a MIRROR.** With a thin/backward-looking brief + a generic "name a gap"
    question, the panel restates (rich brief → echo; thin brief → defer). This is
    real, but it is the DEGENERATE test — a roster with no facilitation process.
  - **Fourth run — FACILITATED process (2026-07-04, retail roster, Gemini 3 Pro
    flagship). The mirror became a LENS.** Modeled a faithful kickoff: shared
    project **context + business objective + strategy**, then a **means-ends +
    tension + blind-spot** question forcing each role to *derive from the objective
    into its domain* (not "name a gap"). Result changed materially:
    - **~4/10 roles produced genuine, non-obvious derivations absent from their
      briefs** — payments (bundling → CurrencyService QPS spike + bundle-price FX
      float risk), finance (bundling across 6 currencies → *AOV up while margin
      down*), merchandising (bundle price → 6-currency validation), compliance
      (fast cart iteration → PCI scope creep). Kickoff-grade risk-surfacing a solo
      founder would plausibly miss.
    - **Cross-role convergence on a derived, non-obvious risk:** finance AND
      payments *independently* flagged "bundling × 6-currency = FX-multiplication +
      margin." Two domains catching the same hazard = the productive-tension signal
      a real workshop produces.
    - **~6/10 roles recontextualized their briefs** (their existing asks reframed
      by the objective) — mild uplift, not new. **Value concentrated in roles with
      real analytical leverage against the *specific strategy* probed** (refines
      OQ-10's trigger: not just operational specificity, but causal relationship to
      the strategy).
    - **Bounds:** competent-generalist grade (obvious-to-expert, invisible-to-
      novice — the useful zone), NOT proprietary/specialist; still synthetic/
      ratify; numeric guard never fired (grounded means-ends, not invention).
  - **REVISED verdict: the panel is a mirror when run cold, a LENS when run as a
    faithful facilitated process.** The product is the **facilitation STRUCTURE**
    (context + objective→strategy→tactics + means-ends probing + cross-role tension
    + synthesis), NOT the roster. This substantially revives FR-13's value case and
    gives it a concrete design direction — see FR-13 + the reclassification decision.
  - **Fifth run — MIXED-MODEL de-correlation (2026-07-04).** Re-ran the facilitated
    probe with personas spread across **three independent model families** (Claude
    Opus 4.8 / GPT-5.5 / Gemini 3 Pro), the four high-signal roles deliberately moved
    OFF Gemini to compare same-role-different-model vs. the all-Gemini v0.9 run. Two
    effects, one of them important:
    - **Trustworthy convergence (the key win).** The top risk (bundling × 6-currency
      → FX-correctness + per-bundle margin, unowned) was independently flagged by
      payments (GPT), finance (Claude), merchandising (Claude), and eng-director
      (Claude) — **across two model families**. Cross-family agreement can't be a
      single-model artifact, so it upgrades convergence from "plausible" to
      "model-independent → real." This directly mitigates the correlated-blind-spot
      limit: de-correlation converts model-agreement into *evidence*.
    - **Modest coverage broadening.** Each family surfaced sharper facets the
      all-Gemini run missed (GPT-payments: duplicate-charge on bundled carts;
      GPT-compliance: the *data-flow mechanism* of PCI scope creep via personalization;
      Claude-finance: per-SKU bundle margin, high-volume≠profitable; Claude-product:
      "coordination is the bottleneck, not the 15-SKU bundle logic").
    - **Limits intact:** low-leverage roles (marketing, support, frontend, sre)
      echoed on every family; the generalist ceiling held (no proprietary knowledge
      appeared); strength/family are confounded (Opus/GPT-5.5 are strong) — but the
      cross-family-convergence finding is immune to that confound (it's about prior
      independence, not raw strength).
    - **Design implication:** assign personas across model families — especially to
      get believable, model-independent risk signals. Mixed-model is a first-class
      facilitation lever (FR-13b).
  - **Sixth run — FULL MULTI-ROUND process (2026-07-04, orchestrator
    `scripts/run_kickoff_panel.py`, mixed-model).** R1 means-ends → R2
    cross-pollination → R3 pre-mortem → R4 synthesis, 10 personas across
    Claude/GPT/Gemini, 31 flagship calls. **Material step-change over the single
    round — and the value came from the ROUNDS, not just the framing:**
    - **R2 produced genuine cross-role TENSIONS** (7 named, T1–T7) — impossible in a
      single round; verified real (personas explicitly name + react to each other).
    - **R4 produced an EMERGENT insight no single persona stated: the ownership gap**
      — the #1 cross-family risk (multi-currency bundle correctness) has *no owner*
      because multiple roles disclaim it as "outside my remit." Emerged only from
      colliding personas' `out_of_scope` — the kind of thing a facilitator catches
      and a solo founder misses.
    - **Corroboration grading** operationalized (risk register labels cross-family
      vs single-model; top-3 cross-family = deployment-truth, multi-currency
      correctness, PCI scope creep).
    - **Anti-smoothing safeguard WORKED** — synthesis kept T1/T3/T6 explicitly OPEN
      and flagged single-model risks for human verification, not deprioritization.
    - Output is decision-grade (risk register + tensions + prioritized recs +
      open-questions-for-the-human), not a list of role opinions.
    - **Limits intact:** competent-generalist grade; the synthesizer is itself an
      LLM (which is why the preserved raw rounds matter — human validates synthesis
      against them). **Orchestrator gap:** per-call cost tracking reads $0.0
      (untracked, not free — ~55k in / 9k out tokens actually spent); wire cost.
    - **Verdict: the full facilitated + de-correlated multi-round process is the
      real capability.** FR-13b confirmed end-to-end.
  - **Seventh run — TIER-1 additions (2026-07-04, orchestrator v0.2: artifact
    grounding + Key Assumptions Check + Outside View + adversary personas +
    independence re-sequence; 12 participants, 52 calls).** Strongest run of the
    series — validated the gap analysis dramatically:
    - **Grounding + assumptions caught that the ENTIRE PREMISE WAS FALSE.** The
      grounded read of the real repo found `contextcore-demo-retail` is *not an
      e-commerce system* (a ContextCore demo-authoring workspace; Blue Planet is a
      skin over Online Boutique the repo doesn't own/deploy/modify); the assumptions
      check rated 5 load-bearing assumptions LOW-confidence/HIGH-impact ("the entire
      objective collapses; there is nothing to optimize"). **All six prior
      (ungrounded) runs produced sophisticated tactics for a business that doesn't
      exist.** This is the gap analysis's #1 thesis (problem-diamond > solution-
      diamond) demonstrated live — and it caught the *facilitator's own* phantom
      framing, exactly the real-onboarding failure mode (stated goal ≠ actual system).
    - **Adversary personas earned their place** — distinct + sharper: fraud surfaced
      "no single authoritative server-side price validated at payment" + "ad/taxonomy
      links as alternate bundle-entry paths bypassing checkout" (an abuse surface no
      internal role raised); competitor reframed the slow-rollout risk as a
      competitive-timing threat. In synthesis the adversaries *strengthened*
      corroboration (top risk now flagged by all 4 families incl. both adversaries)
      and crystallized it into a checkable claim ("cart≠checkout≠payment total").
    - **Outside View** added an honest reference-class corrective (~20-35% clear
      success; "these initiatives often disappoint").
    - **Caveats:** (a) the retail demo was a *flawed test bed* — this proved "Tier-1
      catches a false premise" (decisively) but not "Tier-1 lifts a *valid* kickoff"
      (needs a real app + genuine objective, e.g. the benchmark portal); (b) **design
      insight → the assumptions check should GATE, not just inform**: N high-impact/
      low-confidence assumptions ⇒ halt and validate the premise before spending the
      panel rounds (we analyzed a phantom for 48 calls); (c) cost tracking still
      unwired (real spend ~few $, field reads 0.0).
  - **Eighth run — TIER-1 on a VALID kickoff (2026-07-04, the benchmark portal — a
    real app w/ a real 13-entity schema + a genuine objective: run the scored round
    & publish credibly; 16 participants incl. 2 domain-neutral adversaries, 68 calls).**
    **DECISIVE: Tier-1 LIFTS a valid kickoff** (answers the #7 caveat). Grounding
    *confirmed* a real system (not a phantom) and the panel produced a sharp,
    portal-specific, cross-family risk register of genuinely non-obvious credibility
    gaps: **vendor identities in plaintext contradict the vendor-BLIND review goal**
    (the standout — 9 roles); **embargo is a mutable flag not an enforced/audited
    transition**; **no immutable published-result entity binding specHash→cleared
    cells** (reproducibility has no home); **no pre-registration lock** (moved-
    goalposts attack); **reviewer-UI XSS** from unsanitized generated markup;
    **auto-score vs human adjudication not structurally separated**. The
    **domain-neutral adversaries excelled** — the Discreditor produced a precise
    "how a hostile vendor discredits your benchmark" analysis the internal roster
    wouldn't frame as sharply (validates the generalization: context makes generic
    adversaries domain-appropriate).
    - **Two real orchestrator bugs surfaced (one self-detected):** (1) `PROJECT_NAME`
      was hardcoded "outdoor-gear retailer", NOT overridden by `--objective/--desc`,
      leaking the wrong domain into prompts — **the synthesis flagged the mismatch
      itself**; grounded personas rejected it, generic ones got confused. **FIXED**
      (`--project-name` flag). (2) The artifact-gatherer is **too thin** (feeds only
      `schema.prisma` + truncated files, not the running `app/`), so grounding said
      "a schema, not a running system" (wrong) and the assumptions check rated
      everything LOW-confidence *for lack of evidence it wasn't shown* — the gaps are
      real, the confidence ratings unfair. **TODO:** feed the real running artifact
      (app code) or wire Sapper/`survey`. (3) cost tracking still unwired.
    - **Net across #7+#8: Tier-1 both catches a false premise AND lifts a valid one.**
      FR-13b + the gap-analysis Tier-1 additions validated end-to-end.
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

*v0.5 — Consumer-validated against 3 mid-kickoff apps (§0.3: navig8, household-
o11y, benchmark portal). **Validated:** kernel-only consumption, "solo → silence"
(2/2), retirement de-risked (OQ-5 resolved: navig8 = zero impact). **Refined:**
FR-14 (VIPP actively used at $0 — un-bundle-as-opt-in confirmed, "brownfield
migration" → "ground-truth proposal adjudication"); OQ-10 trigger = domain
viewpoint-multiplicity, not team size. **Exposed:** FR-13 roster-discovery is
unproven (human authored the one rich roster himself) → new OQ-12 (run `panel
ask-all` on the portal to get the missing data point). Distillation still holds;
one value claim is now honestly marked a hypothesis.*

*v0.6 — Discovery experiment run (OQ-12 resolved). `panel ask-all` on the portal's
14 personas yielded 2 refusals, 10 echoes, 1 out-of-scope idea, **1 genuine novel
gap** (operator's score-change audit trail). **Roster-discovery dropped** (no
missed viewpoint surfaced — human authored the roster); **capability-discovery
retained but scoped honestly: low-yield (1/14), best from operationally-specific
personas.** Updated FR-13 evidence note, OQ-10 (favor operational personas), OQ-11
(low yield sharpens the ~20-module justification). The panel earns a place — as an
occasional-gap-finder worth sifting, not a coverage engine.*

*v0.7 — Second discovery experiment (CONTENT question, same 14-persona roster).
Result: 0 genuinely novel content (even lower yield than capability's 1/14),
1 refusal, 3 off-question, 10 echoes. Three findings folded into OQ-12 + FR-13:
(i) content-discovery yield ≈ zero; (ii) the panel behaves as a CONSENSUS/
prioritization instrument, not discovery — strong cross-audience convergence on
"provenance beside results" + "methodology-first"; (iii) the **bucket-4 boundary
held unprompted** — aimed straight at content, personas named requirements, never
wrote copy (direct §0.2 evidence). Combined 28-call rate = 1/28 novel → the panel
is NOT a discovery engine; whatever survives OQ-11 must be thin.*

*v0.8 — Third experiment: capability discovery on the ContextCore Blue Planet
Adventures retail team (10 personas migrated from the old
`contextcore.io/v1alpha1` format the strict parser rejected → newest strict
roster), run with the **Gemini 3 Pro flagship**. Result: **0 novel / 10** — every
persona restated its own brief; the flagship gave MORE faithful echo than Haiku.
**Decisive: the panel is a MIRROR, not a telescope** — brief-bounded, so a
stronger model amplifies fidelity not insight. 3 runs / 2 models / 2 projects /
38 calls = 1 novel item. This removes most of the basis for FR-13's "discovery"
framing → surfaced a live reclassification decision (keep-thin-as-articulation
vs. demote-to-optional). Side effect: validated the roster-format migration path.*

*v0.9 — Fourth experiment: FACILITATED process (retail roster, flagship). Modeled
a real kickoff — shared objective+strategy + means-ends probing — instead of a
cold "name a gap." **The mirror became a lens:** ~4/10 roles produced genuine
non-obvious derivations (bundling→FX-margin trap; bundling→CurrencyService QPS +
float risk), finance+payments independently converged on a derived risk, ~6/10
recontextualized their briefs. **Revised verdict: mirror when cold, lens when
facilitated.** The product is the facilitation STRUCTURE (context + objective→
strategy→tactics + means-ends + cross-role tension + synthesis), NOT the roster
(FR-13b). Value concentrates in roles with analytical leverage against the
specific strategy; bounds = competent-generalist grade, synthetic/ratify. Revives
FR-13's value case with a concrete design direction; reframes the reclassification
decision from "keep-thin/demote/retire" toward "keep as a facilitation capability."*

*v0.10 — Fifth experiment: MIXED-MODEL de-correlation (personas across Claude Opus
4.8 / GPT-5.5 / Gemini 3 Pro; high-signal roles moved off Gemini vs v0.9). Key
finding: **de-correlation makes convergence trustworthy** — the top risk (bundling
× 6-currency → FX-correctness + per-bundle margin) was corroborated across TWO
model families, so it's model-independent, not a shared-model artifact. Also modest
coverage broadening (each family surfaced sharper facets). Limits intact (low-
leverage roles echo on every family; generalist ceiling held; strength/family
confounded — but the convergence finding is immune to that). Mixed-model added as a
first-class facilitation lever (FR-13b). Untested: the full multi-round process
(cross-pollination + pre-mortem + synthesis) on the mixed-model base = next.*

*v0.11 — Sixth experiment: FULL multi-round process via `scripts/run_kickoff_panel.py`
(R1→R2→R3→synthesis, 10 personas across Claude/GPT/Gemini, 31 flagship calls).
**Material step-change, driven by the ROUNDS not the framing:** R2 cross-
pollination produced 7 genuine cross-role tensions (impossible single-round,
verified real); R4 synthesis produced an emergent ownership-gap insight no single
persona stated (top risk has no owner — from colliding `out_of_scope`); corroboration
grading + anti-smoothing safeguard both worked (OPEN tensions kept, single-model
risks flagged for verification). Output is decision-grade. Ceiling intact
(generalist; synthesizer is an LLM → preserved raw rounds enable human validation).
Orchestrator TODO: wire per-call cost tracking (reads $0.0, ~55k/9k tokens actually
spent). **FR-13b confirmed end-to-end — the full facilitated + de-correlated
multi-round process is the real capability.** Spec: `KICKOFF_PANEL_FACILITATION_DESIGN.md`.
Next: user authors end-user observability UX reqs against the §6 transcript contract
(the run's `.startd8/kickoff-panel/<session>.json` is now a real fixture).*
