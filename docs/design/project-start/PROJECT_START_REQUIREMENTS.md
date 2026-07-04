# Project-Start Distillation — Requirements

**Version:** 0.17 (Essential-model revision — guided experience available-not-required; R1-F3 resolved)
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

> **Two modes, not one — reconciliation (R3-F1).** The chain just described is the
> **COLD, single-persona, field-triggered** flow. The experiments (runs 1–3) measured
> that mode at **1 novel / 38 cold calls = a MIRROR** — it is NOT the validated
> product. The capability runs 4–8 validated (and FR-13b specifies as "the
> load-bearing requirement") is a **different product**: a *kickoff-time,
> project-shape-triggered, FACILITATED multi-round* panel (shared objective/strategy →
> means-ends → cross-role tension → synthesis, mixed-model). Different trigger
> (project shape, not a blank field), different granularity (a session, not a single
> persona call), different unit of invocation. **When implementing, build the
> facilitated multi-round process of FR-13b — not the cold blank-field→persona
> pipeline this chain sketches.** The cold chain is retained only as the honest
> low-water-mark description of the *coverage-signal → shaping-range* mechanics; the
> facilitated process is the actual capability. (See FR-13's evidence note + FR-13b.)

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

### 0.4 Essential-Model Revision — the guided experience is available, not required (v0.17)

> **Operator correction (2026-07-04), resolving CRP R1-F3.** v0.1–v0.16 rested on
> an unstated assumption: *the user always has a capable agent (Claude Code /
> Cursor).* From it, the distillation concluded the SDK's guided/agentic experience
> "duplicates the harness" and eliminated it (old NR-2 forbade an embedded agentic
> loop). **That assumption is false in the general case** — the SDK may be deployed
> to the cloud, installed standalone, or used by someone who has no other agent or
> does not want to bring one. For those users the SDK's guided experience is not a
> duplicate of their harness; it **is** their only harness — essential, not
> accidental.

**What the distillation got right (kept):** the **$0 deterministic kernel** is the
essential floor (works for everyone, standalone included); **five overlapping
metaphors was real sprawl**; the **point-value drafting ghost** (Teian) was real;
and **conflating the guided experience with the kernel — or forcing it on everyone —
was wrong.**

**What was wrong (corrected):** concluding "therefore *eliminate* the guided
experience." The fix was never *remove it* — it is *consolidate it and make it
optional.* The accidental complexity was the **sprawl** and the **conflation/
forcing**, never the *existence* of guidance.

**The revised essential model — a spectrum, "meet the user where they are":**
| The user is… | gets… |
|---|---|
| **bring-your-own-agent / power user** | the $0 deterministic **kernel** (survey/instantiate/assess/derive); their own agent fills the blanks. Minimal SDK hosting. |
| **standalone / no agent / wants guidance** | the SDK's **own guided experience** (a consolidated Welcome-Mat-style visual surface + Red-Carpet-style conductor + the optional facilitation panel) over the *same* kernel/contract. The SDK provides the harness. |

**Governing rule (revised NR-2 / FR-6):** the guided/agentic experience is
**available but NOT required** — a **complement, not a substitute**; never forced on
a user who has their own agent, never absent for a user who does not. It sits
*optionally on top of* the kernel; the kernel works fully without it (byte-identical
when the guided layer is absent).

**Cascade (tracked, not all applied here):** this **reverses the retirement of
Welcome Mat / Red Carpet** (FR-9–12) — they are no longer accidental complexity to
delete but the raw material for the **one consolidated optional guided experience**
(the sprawl-reduction win survives as *consolidation*, not *elimination*). It
**resolves CRP R1-F3** (the facilitation orchestrator is a legitimate part of the
optional guided layer, exempt from the revised NR-2) and unblocks its dependents
(R1-F6 transcript persistence, R2-F7 anti-smoothing, R3-F4 transcript-store-under-
safe-write → now real requirements of the guided-experience capability). NR-2, FR-6,
and §1's root-cause are revised below; the full retirement→consolidation re-spec and
the guided-experience requirements are the next work items (with the plan rewrite).

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

> **"The SDK should host a *sprawl* of overlapping metaphors and *force/conflate*
> the hosted experience with the kernel"** — five surfaces (chat panel, conductor,
> persona council, …) doing overlapping jobs, presented as the mandatory path.

The accidental complexity is the **sprawl** (five overlapping metaphors) and the
**conflation/forcing** (the hosted experience treated as *the* path, inseparable
from the kernel) — **not** the existence of a guided experience. *(v0.1–v0.16
mis-stated this root cause as "the SDK duplicating the harness," on the false
assumption that every user has their own agent. Corrected in §0.4: for
standalone/cloud/no-agent users the SDK's guided experience is essential, not a
duplicate. The real fixes are **consolidate the sprawl** and **make the guided
layer optional over the kernel** — see §0.4.)*

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

### The kernel — `startd8 kickoff` (three greenfield verbs + a brownfield on-ramp, zero metaphor)

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

- **FR-1a — `project init` → SCOPE OUT of the kernel (OQ-8 RESOLVED).** `startd8
  project init` (`cli_project.py:65`) always establishes a VIPP posting via a hard
  import (`project/init.py:138,142`). The v0.2 lean was "fold"; the code evidence
  reverses it to **scope-out**:
  - **Nothing greenfield-unique to fold.** `project init --instantiate` produces
    **byte-identical** template output to `concierge instantiate-kickoff` — both
    call the same `build_instantiate_plan` (`writes.py:132`; apply-time
    `proposals.py:281`); `project init` merely wraps it in a VIPP inbox envelope
    requiring a `vipp negotiate`/`apply` round-trip. On greenfield that round-trip
    is pure ceremony (no ground truth to adjudicate).
  - **"Opt-in VIPP" would gut the command.** Unlike the panel-in-`assess` seam
    (coverage core survives without the panel), `project init` minus VIPP is a
    near-empty shell — its shape-detection duplicates `survey` and everything else
    is VIPP plumbing (~7 sites; `--check`'s "initialized" *is* "has a VIPP
    posting", `init.py:330`). There is no residual kernel job to host.
  - **Correlates 1:1 with VIPP adoption (§0.3):** the 2/3 apps that used
    `project init` (household-o11y, benchmark portal) are exactly the two that
    adopted VIPP; navig8 (VIPP-free) used `concierge instantiate` directly.
  - **Resolution:** `project init` is **re-filed as the setup entrypoint of the
    un-bundled ground-truth-adjudication (VIPP) capability (FR-14)** — it keeps its
    VIPP coupling, which is now its declared home. Greenfield onboarding for all
    users is `kickoff instantiate` (writes the 7 files directly, as navig8 already
    did). **Consumer break = zero** (the 2 VIPP apps keep the same flow under the
    relocated name). FR-1's "one surface" now holds honestly — `project init` is no
    longer classified as kernel onboarding.
  - **Consumer-break = zero — stated condition (R1-F7/R2-F6).** "Zero" holds **only
    if the pre-change `project init` invocation keeps posting VIPP by default during
    the alias window.** The two apps that reach VIPP through `project init`'s always-on
    posting (household-o11y, benchmark portal, §0.3) break on **both** axes at once —
    the rename/relocation (FR-1a) *and* the VIPP opt-in flip (FR-14) — if both land in
    the same release with no alias window. The requirement: until the alias window
    closes, the old `project init` command still yields a VIPP posting (default-on),
    so neither the name nor the default changes under the two apps simultaneously.

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

- **FR-6 — Two entry points onto one kernel; the guided layer is optional
  (revised v0.17, §0.4).** The kernel (`survey`/`instantiate`/`assess`/`derive`) is
  $0/deterministic and complete on its own. **For a bring-your-own-agent user**,
  the SDK's job ends at the handoff — "here are honest input files, here is what is
  blank + the command to address it" — and the user's own agent fills the blanks;
  the SDK does **not** force a web app, chat loop, or conductor on them. **For a
  standalone/cloud/no-agent user**, the SDK **offers** a guided experience (the
  consolidated visual surface + conductor + optional facilitation panel) over the
  *same* kernel/contract. The guided layer is **available but not required, a
  complement not a substitute** — never forced on the first user, never absent for
  the second; the kernel is byte-identical whether or not it is engaged.

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
  - **Acceptance — MCP floor (structural, not preview-incidental):** an MCP `action`
    naming a write verb cannot reach a write branch even if the preview return is
    removed — the read floor rejects it before dispatch.
  - **Acceptance — CLI write confinement (R2-F3):** a CLI write to a path outside the
    project root (`../../etc/passwd`) is rejected at the chokepoint, and a symlink
    pointing outside root is followed-and-rejected, not silently followed-and-written.
    Both tests must still pass **after** the M1–M3 renames move the chokepoint.

- **FR-8 — Honest inputs (provenance discipline).** Every value the kernel writes
  carries provenance (`default` / `config-default` / `unratified` /
  `estimate` / `authored` / `shaping-range`). The kernel never writes a value labeled
  as `authored` that it did not receive from a human. It leaves blanks as
  clearly-marked TODOs rather than synthesizing content to fill them.
  - **`shaping-range` (R1-F5) is the distinct provenance for FR-13a discovery ranges**
    — an envelope + reasoning, never a point value. It must **not** reuse `estimate`:
    a `shaping-range` payload is a range (two bounds), so a scalar (single value)
    carrying `shaping-range` provenance is invalid and fails lint (this is what makes
    FR-13a's "envelope not point" and the NR-7 point-value prohibition enforceable at
    the data layer — a zero-width range `5–5%` is a point value and fails the
    width-floor check).

### Phased retirement of the COMPENSATORY layers

> **REFRAMED by §0.4 (v0.17) — retirement → CONSOLIDATION.** Welcome Mat and Red
> Carpet are **no longer slated for deletion.** They are the raw material for the
> **one consolidated, optional guided experience** (FR-6). This section still
> governs (a) collapsing the *sprawl* (five overlapping metaphors → one coherent
> guided surface) and (b) dropping the true ghost (Teian point-value drafting,
> NR-7). What changes: FR-9–12 below are re-read as "consolidate + make optional +
> drop the ghost," not "delete Welcome Mat / Red Carpet." The full re-spec of this
> section (and the guided-experience requirements) is a tracked next work item.

- **FR-9 — Nothing deleted until the kernel spec lands.** Welcome Mat GUI, Red
  Carpet, and Teira/Teian code remain in the tree during the transition. This
  requirement gates removal on the kernel being the documented, shipped surface.
  *(v0.17: for Welcome Mat / Red Carpet this is now permanent — they are retained
  and consolidated, not removed; only Teian's point-value drafter is dropped.)*

- **FR-10 — Deprecation markers.** Each retiring surface (Welcome Mat serve/web,
  Red Carpet CLI commands, Teian `panel recommend`) emits a deprecation notice
  pointing to the `startd8 kickoff` verb that replaces it, and is documented as
  `[COMPENSATORY]` debt in this doc's retirement table. **Hidden aliases must cover
  BOTH surfaces for the same one-release window (R1-F2):** the retired **CLI
  subcommand names** *and* the **MCP `ConciergeInput.action` enum values** (scripted/
  MCP callers key on the `action` strings, `startd8_mcp.py:3200`). A CLI-only alias
  window silently breaks programmatic MCP callers at rename. *Acceptance:* each old
  `action` enum value still dispatches (returns non-error) for one release and emits
  a deprecation warning.

- **FR-11 — Consumer migration (navig8).** The one known live consumer of the
  onboarding surface is `navig8`. Retirement must include a migration note /
  runbook so navig8 (and any other consumer) can move from the retiring surfaces
  to the four kernel verbs without losing capability it actually used.

- **FR-12 — Removal criteria.** Define the objective condition under which the
  retired code is deleted (not just deprecated): kernel verbs shipped +
  consumer(s) migrated + **no external caller resolving to the retiring code paths
  across the CLI subcommand set, the MCP `ConciergeInput.action` enum, and the
  documented consumers** (R1-F1 — *not* the `startd8.contractors.deterministic_providers`
  entry-point group; the retiring surfaces are CLI/MCP commands, not deterministic-
  provider plugins, so that gate would pass vacuously while a live caller still
  exists). Removal is a later, separate change. **Detection/notification (R2-F1):**
  the criteria must carry a named trigger that fires when all three are jointly met —
  a dated review issue, a CI staleness lint on the deprecated modules, or a named
  responsibility — so eligible code does not sit in the tree indefinitely (the
  accidental-complexity-accretes pattern the lens targets); a passive checklist with
  no trigger is a "delete when you feel like it" policy.

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
    lever. **Degraded-mode contract (R3-F5):** when fewer than 2 independent model
    families are available (missing keys, budget), the run must **degrade honestly** —
    every risk-register item carries per-item **model-family provenance**, and any
    convergence produced by a single family is labeled `single-model` (never
    "trustworthy"/cross-family). A silent single-family fallback (the default failure
    mode of a multi-provider script when keys are absent) would fabricate exactly the
    cross-family evidence class the fifth run says is the whole value — the
    benchmark-matrix `is_infra_error` lesson applied to the panel: a missing key must
    degrade or refuse, never masquerade as signal. (Note: the current
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
  - **External-validity caveat (R1-F9).** The "lens when facilitated" evidence
    (runs #4–#8) all probes variants of the **same two projects** (retail bundling /
    benchmark portal), and the doc itself notes value concentrates in roles with
    leverage against *the specific strategy probed*. The claim is therefore
    **domain-scoped as of v0.16**: before productizing, either re-run the facilitated
    probe on a **structurally different domain** (must reproduce ≥1 non-obvious
    cross-role derivation), or keep the "competent-generalist grade" claim explicitly
    marked single-strategy-family until that second-domain run exists.

- **FR-13a — Shaping ranges, never point values (the "no-8%" rule).** When a
  persona speaks to a *specific* field value, it may offer an **estimated range +
  reasoning** to shape the human's answer (e.g. *"early demo funnels typically
  land 5–15%"*) — it may **not** emit a single point value as a draft (e.g.
  `signup_rate: 8%`). A range wears its uncertainty on its face and hands the
  human an envelope to place the real value in; a point value hides its
  uncertainty and invites blind acceptance. This is the breadth/precision line
  (§0.2) made enforceable. See NR-7 for the dropped point-value drafter.
  - **Evidence status — HYPOTHESIS, untested as of v0.16 (R3-F2).** Across all eight
    runs no persona ever emitted a shaping range — run #4's bounds record "numeric
    guard never fired (grounded means-ends, not invention)," i.e. only the
    *prohibition* side (no point values appeared) was exercised, never the
    range-*offering* side FR-13a regulates. Unlike every other FR-13 claim (each
    carries a dropped/retained/low-yield/confirmed status), FR-13a rides on the Teian
    reversal narrative, not evidence. **Before FR-13a ships:** a ninth run must
    demonstrate a persona producing a well-formed range + reasoning a human found
    placeable, AND a width-floor/degenerate-range check must be specified (a range
    that collapses to a point — `5–5%` — fails validation; this is where a point-value
    drafter could quietly re-enter). Until then, FR-13a is a marked hypothesis.

- **FR-13c — Facilitation-orchestrator hardening (required before the panel is
  more than a prototype).** Experiments #7/#8 validated the capability *and*
  exposed three gaps the prototype orchestrator (`scripts/run_kickoff_panel.py`)
  must close before productization. In priority order:
  1. **Artifact-grounding fidelity (biggest lever).** R0 grounding currently reads
     only `schema.prisma` + a few truncated files, so it under-reads a running
     system (#8: said "a schema, not a running system" of a live app) and the
     assumptions check rates real capabilities LOW-confidence for lack of evidence
     it was never shown. Grounding must read the **actual system** — the running
     `app/` code and/or the SDK's own `survey`/Sapper project oracle — so the
     current-state and the assumptions confidence reflect reality, not the schema
     alone. Until fixed, grounding output is schema-blind.
  2. **Assumptions check as a GATE, not just a card** (spec v0.2.1). If R0's Key
     Assumptions Check returns **≥2 high-impact / low-confidence** assumptions,
     the orchestrator must **halt and surface "validate the premise first"** rather
     than spending the full panel rounds. Catching a false premise (#7) is the
     highest-value output; it should short-circuit, not footnote. **Threshold (R2-F4):
     the default is `≥2` high-impact/low-confidence assumptions and it is
     configurable** via a named flag/config key (e.g. `--assumptions-halt-threshold`);
     too low (≥1) halts on noise, too high (≥5) lets false premises through (#7 fired
     at N=5). The failure mode on trip is a **prominent halt** ("validate the premise
     first"), never a silent warn.
  3. **Cost tracking + budget gate (R3-F6).** Per-call `cost_usd` reads `0.0`
     (untracked, not free — run #8 spent ~68 flagship calls). Wire real cost
     attribution so runs report spend, and **consume the SDK's existing `startd8.costs`
     (CostTracker/budget) + the benchmark-matrix fail-closed preflight** rather than
     growing orchestrator-local tracking (Mottainai — don't duplicate shipped
     capability). Define the **budget gate** H3 references, which is otherwise a
     dangling term: a named cap (config key/flag), an **exceeded behavior = halt**
     (mirroring the H2 gate), and — because FR-13's "offering costs $0; only accepting
     spends" must be honest — the offer/acceptance prompt must **disclose an estimated
     call-count + cost band** so acceptance is informed spend authorization (an offer
     that hides its price is the monetary analogue of the FR-8 honesty violation).
  *(Bug already fixed post-#8: `PROJECT_NAME` is now the `--project-name` flag, so
  the default domain no longer leaks into a re-purposed run.)*

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
    - **`PANEL_CONSUMABLE` disposition (R1-F4).** The invariant is not just the
      domain-list move: `PANEL_CONSUMABLE=True` (`core.py:267,274`) couples kernel
      `assess` to the panel's ship-state. The kernel-owned coverage core must carry
      **no reference to `PANEL_CONSUMABLE`** — its removal from kernel `core.py` is
      part of the acceptance (test: with `stakeholder_panel` absent from the import
      graph, `assess` output is byte-identical AND no `PANEL_CONSUMABLE` reference
      remains in kernel `core.py`).
    - **Import-error semantics (R2-F2).** A `try/except ImportError` that degrades
      silently is **NOT** "opt-in-loaded" — a partial/half-loaded checkout can produce
      non-identical output. The coverage core must **lazy-import** the persona layer
      only on accept; a degrading `except` branch is disallowed. Acceptance: with
      `stakeholder_panel` *removed from the environment* (not merely caught by a
      try/except), `assess` output is byte-identical to the never-present baseline.
    - **Baseline is today's output, not a counterfactual (R3-F3 note).** Meeting this
      invariant *removes* the always-present `stakeholders` domain block from every
      current consumer's `assess` output — a visible output-schema change. That break
      has an owner: it is scheduled as a plan-side migration item (see plan R3-S3),
      not silently absorbed here.
  Only assert byte-identical-when-absent **per seam, with evidence** — never as a
  blanket claim.

---

## 3. Non-Requirements

- **NR-1 — No web/TUI GUI *required*; the KERNEL is CLI-only (revised v0.17).** The
  *kernel* (survey/instantiate/assess/derive) ships no interactive GUI — readiness
  is a CLI report. *(The optional guided experience (§0.4/FR-6) MAY serve a GUI; NR-1
  bounds the kernel, not the opt-in guided layer.)*
- **NR-2 — The kernel runs no agentic loop; the guided layer MAY, opt-in (revised
  v0.17, §0.4 — resolves CRP R1-F3).** The **kernel** does not run an LLM
  chat/conductor and is byte-identical without one. The **optional guided
  experience** (Welcome-Mat-style surface + conductor + facilitation panel) *is* an
  agentic experience — **available but not required, a complement not a
  substitute.** It is never forced on a user with their own agent, never withheld
  from one without. *(Prior NR-2 "no embedded agentic loop, the user's own agent is
  the interactive surface" was over-broad — it assumed every user has an agent;
  corrected in §0.4.)*
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
- **OQ-8 — RESOLVED → SCOPE-OUT (see FR-1a).** The diff settled it: `project init
  --instantiate` is byte-identical to `concierge instantiate-kickoff` (same
  `build_instantiate_plan`), just VIPP-enveloped; VIPP coupling is the command's
  spine (~7 sites), so opt-in VIPP would gut it. Re-filed as VIPP-capability setup;
  greenfield users use `kickoff instantiate`; consumer break = zero.
- **OQ-9 — RESOLVED → STAY on the `kickoff` surface** as the labeled brownfield
  on-ramp. `derive` self-rejects on greenfield (`core.py:352`), so on-surface
  placement can't dilute the greenfield path (a greenfield user gets a clean error,
  not a wrong result). **Moving it out would REGRESS navig8** — the sole proven
  `derive` consumer (§0.3), which is VIPP-free and used kernel-only; relocating
  `derive` into the VIPP capability would force navig8 to adopt an unrelated opt-in
  just to reach a verb it depends on. "One surface" (FR-1) outweighs the cosmetic
  "3 clean verbs" narrative. `derive` and VIPP are different jobs (produce a
  candidate schema vs. adjudicate proposals against one) — companion, not merged.
  *Refinement:* `assess`/`survey` should only surface `next_command: kickoff derive`
  when `survey` detected existing Pydantic models (`build_survey` model_files,
  `core.py:120`).
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
  a strong one. **Resolution path (R2-F5):** OQ-10's trigger signal set is the
  implementation input for M3's "compute cheap project-shape signals" — three CRP
  rounds ran and no reviewer could resolve it *for* the author, so "Decide during CRP"
  has failed its own mechanism. **The resolution must be recorded as a concrete,
  testable trigger spec (a resolved OQ-10 entry like OQ-5/OQ-8/OQ-9, or a named spec)
  BEFORE M3 exits** — M3 must not ship with placeholder/undefined trigger logic. Until
  then this is a hard M3 gate, not a CRP-deferred note.
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

*v0.12 — Seventh experiment (Tier-1 orchestrator v0.2: artifact grounding + Key
Assumptions Check + Outside View + adversary personas + independence re-sequence).
Strongest run of the series: grounding + assumptions caught that the ENTIRE PREMISE
was false (all six prior ungrounded runs optimized a business that doesn't exist) —
the problem-diamond > solution-diamond thesis demonstrated live. Adversary personas
earned their place; Outside View added a reference-class corrective. Design insight:
the assumptions check should GATE, not just inform. Fed FR-13c H1/H2.*

*v0.13 — Eighth experiment (Tier-1 on a VALID kickoff: the benchmark portal, real
13-entity schema + genuine objective). DECISIVE — Tier-1 LIFTS a valid kickoff (not
just catches a false premise): sharp portal-specific cross-family credibility-gap
register (plaintext vendor identities vs vendor-BLIND goal; mutable embargo flag; no
immutable published-result binding; XSS). Surfaced two orchestrator bugs (PROJECT_NAME
leak — FIXED; thin artifact-gatherer — TODO). Net #7+#8: catches false premises AND
lifts valid ones — FR-13b + Tier-1 additions validated end-to-end. Fed FR-13c.*

*v0.14 — FR-13c authored (facilitation-orchestrator hardening H1 artifact-grounding
fidelity / H2 assumptions-as-gate / H3 cost tracking), distilled from the #7/#8
caveats. Added as a hard pre-productization gate.*

*v0.15 — OQ-8 and OQ-9 RESOLVED as structural decisions: `project init` scoped OUT to
the VIPP/ground-truth-adjudication capability (OQ-8 → FR-1a); `derive` STAYS on the
`kickoff` surface as the labeled brownfield on-ramp (OQ-9). Header advanced to 0.15.*

*v0.16 — CRP R1–R3 triaged (this pass, 2026-07-04). Applied correctness fixes + gap
closures: FR-1 heading (three greenfield verbs + on-ramp), FR-1a consumer-break-zero
condition, FR-7 MCP-floor + CLI-confinement acceptance tests, FR-8 `shaping-range`
provenance, FR-10 MCP action-enum alias window, FR-12 corrected removal scope +
detection trigger, FR-13 external-validity caveat, FR-13a marked HYPOTHESIS/untested,
FR-13b(5) mixed-model degraded-mode contract, FR-13c H2 threshold default + H3 budget
gate wired to `startd8.costs`, FR-15 PANEL_CONSUMABLE + import-error semantics,
OQ-10 named resolution path, §0.2 cold-vs-facilitated two-mode reconciliation. Deferred
(human deciding): R1-F3 (FR-6/NR-2 vs facilitation-orchestrator conductor) and its
dependents R1-F6/R2-F7/R3-F4 (transcript persistence + anti-smoothing + transcript
floor). See Appendix A/B for full dispositions.*

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
| R1-F3 | FR-6/NR-2 vs facilitation-conductor contradiction | R1 | **RESOLVED by operator decision (§0.4, v0.17):** revised NR-2 + FR-6 — the guided/agentic experience is *available but not required* (complement not substitute; kernel non-agentic, guided layer opt-in). Not a violation; a legitimate optional layer. | 2026-07-04 |
| R1-F6 | Persist raw per-round transcripts as a requirement | R1 | **Accepted (unblocked by R1-F3).** Becomes a real requirement of the guided-experience/facilitation capability (already relied on in §4 + the observability UX reqs). To be written into the guided-experience re-spec (next work item). | 2026-07-04 |
| R2-F7 | Anti-smoothing (keep open tensions) as a requirement | R2 | **Accepted (unblocked by R1-F3).** Becomes a synthesis requirement of the guided-experience capability. Applied into the guided-experience re-spec (next work item). | 2026-07-04 |
| R3-F4 | Transcript store under the safe-write floor | R3 | **Accepted (unblocked by R1-F3).** Guided-experience transcript writes ride FR-7's confined safe-write floor. Applied in the guided-experience re-spec (next work item). | 2026-07-04 |
| R1-F1 | FR-12 cites wrong entry-point group | R1 | Applied — FR-12 rewritten to check CLI subcommands + MCP `action` enum + documented consumers; called out the vacuous deterministic-provider gate. | 2026-07-04 |
| R1-F2 | Alias window must cover MCP `action` enum | R1 | Applied — FR-10 now requires hidden aliases for BOTH CLI names AND MCP `ConciergeInput.action` enum for the one-release window, with non-error+deprecation-warning acceptance. | 2026-07-04 |
| R1-F4 | Name PANEL_CONSUMABLE in FR-15 invariant | R1 | Applied — FR-15 panel bullet adds a `PANEL_CONSUMABLE` disposition sub-bullet (no reference remains in kernel `core.py`; byte-identity test). | 2026-07-04 |
| R1-F5 | Provenance value for shaping ranges | R1 | Applied — FR-8 enum gains `shaping-range` (distinct from `estimate`); range-not-scalar lint + width-floor make FR-13a/NR-7 enforceable. | 2026-07-04 |
| R1-F7 | FR-1a "consumer break=zero" needs stated condition | R1 | Applied — FR-1a adds the alias-window condition (old `project init` keeps posting VIPP by default until the window closes); double-break named. | 2026-07-04 |
| R1-F8 | FR-1 heading says "four verbs" | R1 | Applied — heading changed to "three greenfield verbs + a brownfield on-ramp". | 2026-07-04 |
| R1-F9 | FR-13 evidence is single-domain | R1 | Applied — added external-validity caveat sub-bullet (domain-scoped as of v0.16; second-domain facilitated run required before productizing). | 2026-07-04 |
| R2-F1 | FR-12 needs detection/notification mechanism | R2 | Applied — FR-12 adds a named trigger (dated review issue / CI staleness lint / named owner) that fires when criteria jointly met. | 2026-07-04 |
| R2-F2 | FR-15 must specify import-error semantics | R2 | Applied — FR-15 panel bullet adds import-error-semantics sub-bullet (lazy-import required; degrading `except` disallowed; env-removed byte-identity test). | 2026-07-04 |
| R2-F3 | FR-7 CLI-confinement acceptance test | R2 | Applied — FR-7 adds CLI path-traversal + symlink-escape acceptance tests, must survive M1–M3 renames. | 2026-07-04 |
| R2-F4 | FR-13c H2 threshold default + tuning | R2 | Applied — H2 states default `≥2`, configurable flag, prominent-halt failure mode. | 2026-07-04 |
| R2-F5 | OQ-10 needs named resolution path | R2 | Applied — OQ-10 "Decide during CRP" converted to a hard M3-exit gate (testable trigger spec required before M3 ships). | 2026-07-04 |
| R3-F1 | Reconcile §0.2 cold vs facilitated model | R3 | Applied — added a two-modes reconciliation callout after the "three survivors chain" (build the FR-13b facilitated multi-round process, not the cold blank-field pipeline). | 2026-07-04 |
| R3-F2 | Mark FR-13a empirically unvalidated | R3 | Applied — FR-13a carries an "Evidence status — HYPOTHESIS, untested as of v0.16" note + ninth-run + width-floor gate before ship. | 2026-07-04 |
| R3-F3 | Restore changelog integrity (v0.12–v0.15) | R3 | Applied — added v0.12–v0.16 changelog entries; header now matches last footer. | 2026-07-04 |
| R3-F5 | FR-13b(5) degraded-mode contract | R3 | Applied — FR-13b(5) adds degraded-mode contract (per-item model-family provenance; single-family labeled `single-model`, never cross-family; `is_infra_error` analogue). | 2026-07-04 |
| R3-F6 | Define budget gate H3 + wire startd8.costs | R3 | Applied — FR-13c H3 defines the budget gate (cap + halt), requires consuming `startd8.costs` + benchmark-matrix preflight, and mandates offer-time call-count/cost-band disclosure. | 2026-07-04 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R2-F6 | State FR-1a "break=zero" condition in requirements text | R2 | Redundant — R1-F7 (accepted) already writes the alias-window condition directly into FR-1a's prose; R2-F6 asks for the same edit, now applied. | 2026-07-04 |

*Deferred (untriaged, human deciding): **R1-F3** (FR-6/NR-2 vs facilitation-orchestrator conductor contradiction) left in Appendix C. Its dependents **R1-F6** (transcript persistence as a requirement) and **R3-F4** (transcript store under the safe-write floor) and **R2-F7** (anti-smoothing as a requirement) are also deferred as blocked on R1-F3 — whether the orchestrator is an FR-6-exempt opt-in tool or a bounded violation determines whether/how these three land.*

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8 — 2026-07-04

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-07-04 00:00:00 UTC
- **Scope**: Requirements-side (F-prefix) review of the project-start distillation, weighted per the focus file toward FR-9..12 retirement soundness, FR-13/14/15 import-edge surgery, FR-7/8 safe-write floor, FR-13c orchestrator hardening, and consumer-migration risk. Independent reviewer (did not author). Appendix A/B/C were empty → this is R1.

**Focus-file asks (addressed first, per prompt template):**

- **Ask 1 — Are FR-9..12 retirement/removal criteria sufficient and safe? Ordering hazard?**
  - **Summary answer:** Partial — one real ordering hazard and one mis-scoped removal criterion.
  - **Rationale:** FR-12's removal criterion "no external caller in the deterministic-provider entry points" cites the wrong entry-point group; the retiring surfaces (Welcome Mat serve/web, Red Carpet, Teian) are CLI/MCP commands, not `startd8.contractors.deterministic_providers` plugins, so that gate would trivially pass while a live CLI/MCP caller still exists. The `kickoff` name-collision (FR-1 sequencing constraint) is a genuine hazard: the hidden-alias window (FR-10) must survive at least one release across BOTH the CLI subcommand names AND the MCP `ConciergeInput.action` enum, but FR-10 only names CLI notices.
  - **Assumptions / conditions:** MCP `action` enum values are a stable external contract for scripted callers.
  - **Suggested improvements:** see R1-F1 (removal-criterion scope) and R1-F2 (alias-window completeness).
- **Ask 2 — Are the FR-13/15 panel edge-cut and FR-14/FR-1a VIPP de-coupling fully specified? Residual coupling?**
  - **Summary answer:** Mostly — one residual coupling and one under-specified invariant.
  - **Rationale:** FR-13's "move the domain-list ownership into the kernel" preserves the single-source at `core.py:38-41`, but `PANEL_CONSUMABLE=True` (`core.py:267,274`) still couples kernel assess to the panel's ship-state and FR-15's target invariant does not name what happens to that flag. FR-13c/FR-13b introduce a *facilitation orchestrator* (`scripts/run_kickoff_panel.py`) that is nowhere reconciled with FR-6 ("SDK does not run an agentic conductor") — the orchestrator IS a conductor.
  - **Assumptions / conditions:** the facilitation orchestrator is intended to ship as a real capability, not stay a script.
  - **Suggested improvements:** see R1-F3 (FR-6 vs FR-13b/c reconciliation) and R1-F4 (PANEL_CONSUMABLE in the SOTTO invariant).
- **Ask 3 — Safe-write floor (FR-7) + provenance (FR-8) completeness; MCP structural-read-only nit.**
  - **Summary answer:** Sound in intent, under-specified in acceptance.
  - **Rationale:** FR-7's structural-read-only fix (route MCP through `handle_concierge_read`) has no acceptance test named, and FR-8's provenance enum lists five values without stating which the kernel may *emit* vs merely *pass through* — a discovery "shaping range" (FR-13a) needs a provenance value and none of the five obviously fits.
  - **Suggested improvements:** see R1-F5 (provenance value for shaping ranges) and R1-S3 (plan-side MCP-floor test).
- **Ask 4 — FR-13c hardening completeness (H1/H2/H3)?**
  - **Summary answer:** The three named gaps are right; a fourth (raw-round preservation as a *product* invariant) is implied by run #6/#8 but not required.
  - **Rationale:** §4 run #6/#8 repeatedly leans on "preserved raw rounds enable human validation of the LLM synthesizer," yet FR-13c requires only H1/H2/H3. If synthesis is LLM-produced, the raw-transcript retention is load-bearing for trust and belongs as a requirement, not an experiment footnote.
  - **Suggested improvements:** see R1-F6.
- **Ask 5 — Consumer-migration risk (navig8 + 2 VIPP apps)?**
  - **Summary answer:** navig8 covered; the 2 VIPP apps have an unstated rename-break.
  - **Rationale:** FR-1a re-files `project init` as VIPP-capability setup and FR-14 makes VIPP opt-in via `--with-vipp`, but §0.3 says household-o11y + portal reached VIPP *through* `project init`'s always-on posting. If `project init` is renamed/relocated (FR-1a) AND its VIPP posting becomes opt-in (FR-14) simultaneously, those two apps' existing invocation breaks on both axes; "consumer break = zero" (FR-1a) is only true if the old `project init` invocation keeps posting VIPP by default during the alias window.
  - **Suggested improvements:** see R1-F7.

**First-pass suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Ops | high | FR-12 removal criterion cites the wrong entry-point group. Replace "no external caller in the deterministic-provider entry points" with a concrete check that no CLI subcommand, MCP `action` enum value, or documented consumer still resolves to the retiring code paths. | The retiring surfaces are CLI/MCP commands, not `startd8.contractors.deterministic_providers` plugins, so the stated gate passes vacuously and code could be deleted while a live caller exists. | FR-12, sentence "no external caller in the deterministic-provider entry points" | grep the entry-point tables + CLI/MCP registries for references to `red_carpet*`, `kickoff_experience`, `panel recommend`; removal PR must show zero. |
| R1-F2 | Interfaces | high | FR-10 must require hidden aliases for BOTH the retired CLI subcommand names AND the MCP `ConciergeInput.action` enum values, for the same one-release window M1 grants (plan). | Scripts and MCP callers key on `action` strings (§0 D-notes cite `startd8_mcp.py:3200`); a CLI-only alias window silently breaks programmatic callers at rename. | FR-10, after "emits a deprecation notice pointing to the `startd8 kickoff` verb" | Assert old `action` enum values still dispatch (return non-error) for one release; add a deprecation-warning assertion test. |
| R1-F3 | Architecture | high | Reconcile FR-13b/FR-13c (a multi-round facilitation *orchestrator*, `run_kickoff_panel.py`) with FR-6/NR-2, which forbid the SDK "running an agentic conductor" as part of project-start. State explicitly whether the orchestrator is (a) out-of-kernel opt-in tooling exempt from FR-6, or (b) a violation to bound. | As written, FR-6/NR-2 and FR-13b/c contradict: the facilitation structure IS a conductor that role-plays stakeholders across rounds. An implementer cannot tell if this is allowed. | New sub-bullet under FR-13 or a carve-out clause in FR-6/NR-2 | A reader can state, from the doc alone, whether launching `run_kickoff_panel.py` violates NR-2. |
| R1-F4 | Data | medium | FR-15's panel-half target invariant must name `PANEL_CONSUMABLE` (`core.py:267,274`) explicitly — state its value/removal in the kernel-owned coverage core so "byte-identical when discovery not accepted" is verifiable, not just the domain-list move. | §0 flags `PANEL_CONSUMABLE=True` as coupling kernel assess to the panel's ship-state; FR-15 preserves the domain list but is silent on this flag, leaving a residual coupling path. | FR-15, "Panel-in-assess — must become opt-in-loaded" bullet | Test: with `stakeholder_panel` absent from the import graph, `assess` output byte-identical AND no `PANEL_CONSUMABLE` reference remains in kernel `core.py`. |
| R1-F5 | Data | medium | FR-8's provenance enum (`default`/`config-default`/`unratified`/`estimate`/`authored`) has no value for FR-13a "shaping ranges." Add an explicit `range`/`shaping` provenance (or state that ranges reuse `estimate` with a range-shaped payload) so FR-13a's "envelope not point" is machine-distinguishable from a dropped Teian point-value. | FR-13a permits ranges but forbids point values; if both serialize as `estimate`, the NR-7 prohibition is unenforceable at the data layer. | FR-8 enum list; cross-reference FR-13a | Schema/lint check: any `estimate`-provenance value that is a scalar (not a range) in a discovery-authored field fails. |
| R1-F6 | Validation | medium | Add a requirement that the facilitation orchestrator PERSIST raw per-round transcripts as the human-validation substrate for the LLM synthesizer (already relied on in §4 runs #6/#8 as `.startd8/kickoff-panel/<session>.json`). | Runs #6/#8 repeatedly justify trust in the synthesizer via "preserved raw rounds"; that is load-bearing for the value case but appears only as experiment prose, not a requirement. | New FR (e.g. FR-13d) or a fourth item under FR-13c | Verify a run writes a transcript file containing each round's raw persona outputs distinct from the synthesized register. |
| R1-F7 | Risks | high | FR-1a's "consumer break = zero" needs a stated condition: the old `project init` invocation must keep posting VIPP by default during the alias window, otherwise household-o11y + portal break on BOTH the rename (FR-1a) and the opt-in flip (FR-14) at once. | §0.3 shows those 2 apps reached VIPP *via* `project init`'s always-on posting; scoping-out + opt-in-flipping simultaneously is a double break the "zero" claim hides. | FR-1a "Consumer break = zero" clause; cross-ref FR-14 | Migration test: the exact pre-change `project init` command still produces a VIPP posting until the alias window closes. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F8 | Architecture | medium | The FR-1 heading still reads "four plain verbs" while its body and §0 establish "three greenfield verbs + a brownfield on-ramp." Fix the heading to avoid re-seeding the resolved OQ-1/OQ-7 confusion for downstream readers. | An internal contradiction between a section heading and its own body is exactly the accidental-complexity accretion the doc's lens warns against; it will mislead an implementer skimming headings. | Heading "The kernel — `startd8 kickoff` (four plain verbs, zero metaphor)" | Heading count of verbs matches FR-1 body (three greenfield + derive on-ramp). |
| R1-F9 | Risks | medium | FR-13's discovery-value evidence is entirely single-domain (retail bundling / benchmark portal). Add an explicit external-validity caveat OR a requirement to re-run the facilitated probe on a structurally different domain before productizing, so the "lens when facilitated" claim is not over-generalized from one strategy. | Runs #4–#8 all probe variants of the same two projects; "competent-generalist grade" is asserted but the lens result may be strategy-specific (the doc itself notes value concentrates in roles with leverage against *the specific strategy probed*). | FR-13 evidence note or OQ-11 | A second-domain facilitated run reproduces ≥1 non-obvious cross-role derivation, or the doc marks the claim domain-scoped. |

**Endorsements / Disagreements:** none — Appendix A/B/C were empty at R1 (no prior untriaged items to react to).

---

#### Review Round R2 — claude-sonnet-4-6 — 2026-07-04

- **Reviewer**: claude-sonnet-4-6
- **Date**: 2026-07-04 18:30:00 UTC
- **Scope**: Requirements-side (F-prefix) R2 review. R1 (claude-opus-4-8) covered FR-12 mis-scoped removal criterion, FR-10 MCP alias window, FR-6/NR-2 vs FR-13b/c reconciliation, PANEL_CONSUMABLE in FR-15, provenance for shaping ranges, raw transcript persistence, consumer double-break condition, FR-1 heading mismatch, and discovery external-validity. This pass brings a different lens: decision-routing completeness (OQ-10 ownership), the synthesizer trust model, the FR-13c assumptions-gate scope boundary, the FR-1a fold/scope-out asymmetry in requirements language, and the safe-write chokepoint verification gap. All R1 items are untriaged (none in Appendix A/B).

**Focus-file asks (addressed first, per prompt template):**

- **Focus Area 1 — Phased-retirement + removal-criteria soundness (FR-9..12), ordering hazard:**
  - **Summary answer:** Partial — R1 identified the real gaps (wrong entry-point group in FR-12, MCP alias window in FR-10). R2 adds: FR-12's criteria are stated as a checklist but have no *notification mechanism* — nothing tells anyone when the criteria are met, so deletion can silently qualify without notice.
  - **Rationale:** FR-12 lists three gates ("kernel verbs shipped + consumer(s) migrated + no external caller") but does not specify how their satisfaction is detected. In contrast, FR-9 and FR-10 each have observable events (kernel shipped, deprecation notice present). FR-12's gate is passive.
  - **Assumptions / conditions:** The criteria could be met between active work cycles (e.g., after M5 ships and the team moves to other work).
  - **Suggested improvements:** See R2-F1 (add a detection/notification mechanism to FR-12).

- **Focus Area 2 — Import-edge surgery (FR-13/15 panel cut, FR-14/FR-1a VIPP de-coupling):**
  - **Summary answer:** Mostly specified; R2 adds one missed coupling: `try/except ImportError` fallback in `core.py` that degrades on partial checkout (noted in §0's table row for FR-13/14/15) is not addressed in FR-15's target invariant. A try/except that silently degrades is not the same as "opt-in-loaded."
  - **Rationale:** FR-15 says the target invariant is "byte-identical when discovery not accepted." A try/except that catches ImportError on `stakeholder_panel` would satisfy this only if the except branch returns exactly the same output — but a degraded/partial import (half-loaded package) could produce different output. The `PANEL_CONSUMABLE` fix (R1-F4) addresses the flag; the import-error semantics are separate.
  - **Assumptions / conditions:** The try/except at `core.py:256` is load-bearing for degraded-checkout behavior.
  - **Suggested improvements:** See R2-F2 (FR-15 must specify import-error handling, not just flag removal).

- **Focus Area 3 — Safe-write floor (FR-7) and provenance discipline (FR-8):**
  - **Summary answer:** Partial — R1 identified the MCP structural-read-only gap and provenance-for-shaping-ranges. R2 adds: FR-7's confinement clause says "atomic dir-fd-relative writes" but provides no acceptance test at the requirements level. The MCP fix (route through `handle_concierge_read`) addresses the read-only guarantee but not the confinement guarantee for CLI writes.
  - **Rationale:** FR-7 bundles two guarantees (structural read-only for MCP + root-confined writes for CLI). R1-F5 + R1-S3 cover the MCP half. The CLI confinement half ("no traversal/symlink escape, atomic dir-fd-relative writes") has no stated acceptance test.
  - **Suggested improvements:** See R2-F3 (add acceptance criterion for CLI write confinement).

- **Focus Area 4 — FR-13c orchestrator-hardening completeness:**
  - **Summary answer:** H1/H2/H3 are the right three gaps; R2 adds a fourth: the assumptions-gate threshold (H2 says "≥2 high-impact/low-confidence assumptions ⇒ halt") is a hard-coded constant with no stated default, tuning mechanism, or validation. The threshold is the most operationally sensitive parameter in the hardening set.
  - **Rationale:** A too-low threshold (≥1) halts on noise; a too-high threshold (≥5) lets false premises through. The §4 run #7 description says the orchestrator "must halt" but never specifies the implementation parameter. Run #8 says "5 load-bearing assumptions LOW-confidence/HIGH-impact" — that is an empirical observation, not a required default.
  - **Suggested improvements:** See R2-F4 (FR-13c H2 must state the threshold default and its tuning surface).

- **Focus Area 5 — Consumer-migration risk:**
  - **Summary answer:** R1 identified the double-break risk for the 2 VIPP apps (R1-F7). R2 adds: the requirements language in FR-1a says "Consumer break = zero" as a claim, but the condition under which it holds (old invocation keeps VIPP by default during alias window) is stated in R1's suggestion, not in the requirements text. The doc makes a guarantee it doesn't support.
  - **Suggested improvements:** The FR-1a condition should be stated in the requirements, not just in a review suggestion.

- **Focus Area 6 — Requirements↔plan gaps:**
  - **Summary answer:** R1's coverage matrix captures the major gaps. R2 adds: OQ-10 is an open question the requirements tell the reviewer to "Decide during CRP," but neither doc records where the decision lands once made. This is a requirements-level gap — OQ-10 should either be resolved in the requirements or have a named resolution path.
  - **Suggested improvements:** See R2-F5 (OQ-10 needs a resolution path, not just a "Decide during CRP" placeholder).

**First-pass suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Ops | medium | FR-12 removal criteria need a stated detection/notification mechanism — not just a checklist. Add a concrete trigger: a dated review issue template, a CI lint that flags the deprecated modules once criteria are met, or a named responsibility. | FR-12 lists gates ("kernel verbs shipped + consumer(s) migrated + no external caller") but nothing detects their joint satisfaction. Without a trigger, eligible code stays in the tree indefinitely — exactly the accidental-complexity-accretes pattern the doc's anti-principle targets. | FR-12, after "Removal is a later, separate change." | The requirements name ≥1 mechanism that would alert an implementer when all three criteria are simultaneously met. |
| R2-F2 | Architecture | medium | FR-15's panel-half target invariant must specify the import-error semantics: a `try/except ImportError` on `stakeholder_panel` that degrades silently is NOT the same as "opt-in-loaded." State whether the except branch must (a) produce byte-identical output to the no-import path, or (b) be disallowed entirely in favor of lazy-import. | §0's table row for FR-13/14/15 notes "try/except only degrades on partial checkout" — that path can produce non-identical output. FR-15's current target ("byte-identical when discovery not accepted") is satisfied by exact import absence, but not guaranteed by a degrading try/except with no output contract. | FR-15, "Panel-in-assess — must become opt-in-loaded" bullet; cross-ref the §0 planning discovery row | Named test: with `stakeholder_panel` removed from the environment (not just absent from import), `assess` output is byte-identical to the test where the package was never present (not merely the test where the try/except caught ImportError). |
| R2-F3 | Security | medium | FR-7 currently states the CLI write guarantee ("atomic dir-fd-relative writes, no traversal/symlink escape") but provides no acceptance criterion. Add a named test: an attempt to write to a path outside the root directory via the CLI is rejected at the chokepoint, and a symlink pointing outside root is followed-and-rejected, not silently followed-and-written. | FR-7 bundles two guarantees (structural read-only for MCP + root-confined writes for CLI). R1-F5 + R1-S3 address the MCP half; the CLI confinement guarantee is stated in prose but not made testable. A security property without a named test is a policy aspiration. | FR-7, after the MCP nit sentence | A path-traversal test (`../../etc/passwd`) and a symlink-escape test pass (write rejected) against the chokepoint after M1–M3 renames are complete. |
| R2-F4 | Validation | medium | FR-13c H2 (assumptions-as-gate) must state the threshold default: "≥2 high-impact/low-confidence assumptions ⇒ halt." The runs description uses this threshold empirically (#7: 5 assumptions → halt was warranted) but never specifies what value ships as the default, whether it is configurable, and what the failure mode is when threshold is missed (halt silently vs. warn prominently). | The threshold is the most operationally sensitive parameter in the hardening set. Too low → halts on noise; too high → misses false premises (#7's lesson). Shipping an unspecified default means every deployment is a trial-and-error configuration. | FR-13c item 2 ("Assumptions check as a GATE") | The requirement states a numeric default and a named flag or config key for tuning; a test verifies the orchestrator halts (not warns) when the threshold is met. |
| R2-F5 | Architecture | medium | OQ-10 ("Decide during CRP") is an open question deferred to CRP with no stated resolution path. Neither the requirements nor the plan records where the decision lands once made, nor what milestone it gates. Convert OQ-10's trailing note from "Decide during CRP" to a named resolution target: "Resolution must be recorded in FR-13 or a named spec before M3 exits." | OQ-10's trigger signals are the implementation input for M3's "compute cheap project-shape signals" task. If the CRP decision is never written back into the requirements or a spec, M3 has no deterministic input and will make ad-hoc implementation choices that diverge from intent. | OQ-10, final sentence "Decide during CRP" | The requirements record a resolved OQ-10 entry (like OQ-5, OQ-8, OQ-9) with specific trigger signals before M3 is closed. |
| R2-F6 | Risks | low | FR-1a states "Consumer break = zero" as a claim but the condition under which it holds ("old invocation keeps posting VIPP by default during the alias window") is not in the requirements text — it appears only in R1-F7's suggestion. Add that condition as a parenthetical in FR-1a, alongside "Consumer break = zero," so the guarantee is self-contained. | As written, FR-1a makes a guarantee it doesn't support: a reader who implements FR-1a + FR-14 simultaneously (scope-out + opt-in flip) can break both VIPP apps while believing FR-1a's "zero" claim holds. R1-F7 identified this; the fix belongs in the requirements, not only in a review suggestion. | FR-1a, "Consumer break = zero" parenthetical | A reader can derive from FR-1a alone (without consulting review suggestions) what must hold during the alias window to keep the "zero" guarantee. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F7 | Architecture | low | The requirements never state what happens when the LLM synthesizer's output in FR-13b/c *contradicts* a raw-round persona output. R1-F6 requires raw transcripts to be persisted for human validation; but if the synthesizer smooths over a conflict (the anti-smoothing safeguard "WORKED" in run #6 but is described as behavioral, not required), the human has preserved evidence but no protocol for acting on it. Add a note to FR-13b or FR-13c: "synthesis must not resolve open tensions — open items are flagged for human adjudication, not deprioritized." | Run #6 notes "anti-smoothing safeguard WORKED — synthesis kept T1/T3/T6 explicitly OPEN." That safeguard is currently a behavioral property of one orchestrator run, not a requirement the synthesizer prompt must satisfy. Without making it a requirement, a future synthesizer prompt revision can silently re-introduce smoothing. | FR-13b item (4) synthesis, or a new item under FR-13c | Acceptance: a synthesis output with an unresolved cross-role tension (present in raw rounds) must carry that tension explicitly rather than resolving it; a test compares the raw T1–T7 tensions against the synthesis output and fails if any named tension is absent. |

**Endorsements (untriaged R1 items this reviewer agrees with):**

- **R1-F1** (FR-12 wrong entry-point group): strongly endorse — the gate passes vacuously against the stated registry; the correct scope is CLI subcommands + MCP action enum.
- **R1-F3** (FR-6/NR-2 vs FR-13b/c conductor contradiction): strongly endorse — this is a load-bearing ambiguity; an implementer cannot tell if the facilitation orchestrator violates NR-2 or is exempt from it.
- **R1-F4** (PANEL_CONSUMABLE must be named in FR-15): endorse — the flag is a residual coupling the target invariant must address explicitly.
- **R1-F7** (FR-1a "consumer break = zero" needs a stated condition): endorse — this is the highest-impact consumer-migration risk; R2-F6 proposes writing the condition directly into FR-1a.
- **R1-F8** (FR-1 heading says "four plain verbs"): endorse — heading/body contradiction is a clarity regression that will mislead an implementer skimming structure.

---

#### Review Round R3 — claude-fable-5 — 2026-07-04

- **Reviewer**: claude-fable-5
- **Date**: 2026-07-04 21:30:00 UTC
- **Scope**: Requirements-side (F-prefix) R3. R1 covered retirement/alias scope, the FR-6↔FR-13b/c conductor contradiction, PANEL_CONSUMABLE, provenance-for-ranges, transcript persistence, and the consumer double-break; R2 covered detection mechanisms, import-error semantics, CLI-confinement acceptance, the H2 threshold, and OQ-10's resolution path. **Third lens: (a) which capability the 8 experiments actually validated vs. which capability the requirements specify (empirical-claims traceability); (b) write-contract and output-contract stability for the artifacts the experiments introduced; (c) document-as-state integrity.** All claims below were verified against source (`red_carpet_advisor.py:61-73,348-358`, `core.py:256,267,274`, `run_kickoff_panel.py:365`).

**Focus-file asks — R3 deltas only (R1/R2 already answered each ask; per-ask template applied to the new material):**

- **Ask 1 (FR-9..12 soundness/ordering).** *Summary:* partial — one new hazard class. *Rationale:* R1-F1/F2 and R2-F1 cover scope and detection; what remains uncovered is that the `kickoff` transition is a **name REUSE, not a removal** — after the rename, old metaphor `startd8 kickoff …` invocations resolve to the *kernel* group with different semantics, which no deprecation notice on the old surface can intercept. *Assumptions:* some caller/doc somewhere still says `startd8 kickoff red-carpet` (the portal is "Red Carpet doc-referenced"). *Improvements:* plan-side R3-S2.
- **Ask 2 (import-edge surgery fully specified?).** *Summary:* one baseline error remains. *Rationale:* FR-15's target ("byte-identical to a build that never knew the panel existed") is anchored to a **counterfactual build, not to today's output** — today `assess` *always* emits a `stakeholders` domain (`core.py:256`), so meeting the invariant is a visible output-schema change for all three live consumers. Neither FR-15 nor FR-11 treats the disappearing block as a migration item. *Improvements:* plan-side R3-S3.
- **Ask 3 (FR-7/FR-8 floor).** *Summary:* one uncovered write path. *Rationale:* the panel orchestrator persists transcripts by direct `Path` write (`run_kickoff_panel.py:365`), outside the FR-7 chokepoint, and R1-F6 would *require* that persistence without placing it under the floor. *Improvements:* R3-F4.
- **Ask 4 (FR-13c completeness).** *Summary:* two additions beyond H1-H3 + R1-F6/R2-F4. *Rationale:* H3 references a "budget gate" that is defined nowhere (R3-F6), and FR-13b(5) mixed-model has no degraded-mode contract when <2 model families are available — a silent single-family fallback fabricates exactly the "trustworthy convergence" evidence the fifth run says only cross-family agreement provides (R3-F5).
- **Ask 5 (consumer migration).** *Summary:* the missed break vector is `assess` **output shape**, not command names — see Ask 2 / R3-S3.
- **Ask 6 (reqs↔plan staleness).** *Summary:* three concrete instances beyond R1's version finding: the plan's M2 ports command constants that point at *retiring* surfaces (R3-S1); M0 directs implementers to re-decide OQ-5/OQ-8, both RESOLVED in reqs v0.15 and SETTLED in the focus file (R3-S4); and the requirements' own changelog stops at v0.11 while the header claims v0.15 (R3-F3).

**Executive summary:**
- The **§0.2 "three survivors chain" specifies the cold single-persona flow the experiments disproved** (runs 1-3: 1 novel/38 cold calls = mirror); the capability runs 4-8 validated is a different product (facilitated multi-round panel, different trigger, different unit of invocation). The requirements currently spec the disproven flow and narrate the proven one.
- **FR-13a (shaping ranges) is required but empirically untested** — no run ever produced or evaluated a shaping range ("numeric guard never fired"); the doc's own evidence discipline should mark it a hypothesis.
- **The transcript store the trust model depends on is written outside the safe-write floor** and has no commit/gitignore/sensitivity disposition.
- **FR-13b(5) mixed-model has no degraded-mode contract** — single-family runs can masquerade as de-correlated convergence.
- **H3's "budget gate" is a dangling reference**; the SDK already ships the cost/budget infrastructure it should use.
- **Changelog integrity: v0.12–v0.15 entries are missing** — in a CRP process where "the document is the state," four version bumps are untraceable.

**First-pass suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Architecture | high | Reconcile §0.2's reclassified model with the experimental verdict. The chain "the $0 coverage signal **triggers** the conditional discovery offer, discovery **invokes** a persona, who may offer a **shaping range** on a specific field" specifies the COLD, single-persona, field-triggered flow — the mode runs 1-3 measured at 1 novel/38 calls and the doc itself calls "a MIRROR." The validated capability (runs 4-8, FR-13b) is a *kickoff-time, project-shape-triggered, facilitated multi-round* process — different trigger, different granularity, different invocation unit. Either rewrite the §0.2 table/chain to describe the facilitated model, or explicitly define BOTH modes and state which is offered when. | An implementer following §0.2 + FR-13's trigger bullets would build the blank-field→persona pipeline the experiments disproved, and never build the facilitation scaffold FR-13b says is "the load-bearing requirement." This is the deepest reqs-internal contradiction left: the spec text and the evidence text describe two different products under one FR number. | §0.2 "The three survivors chain…" paragraph + the reclassified-model table; cross-ref FR-13b | A reader can state, from §0.2 alone, what event triggers a discovery invocation and whether it is a single persona call or a facilitated multi-round session; the answer matches FR-13b and the run 4-8 evidence. |
| R3-F2 | Validation | high | Mark FR-13a as empirically UNVALIDATED and require a shaping-range experiment before it ships. Across all 8 runs, no persona ever emitted a shaping range: run #4's bounds state "numeric guard never fired (grounded means-ends, not invention)" — i.e. the range-offering behavior FR-13a regulates was never exercised, only the prohibition side (no point values appeared). The requirement currently rides on the Teian reversal narrative, not on evidence. | Every other FR-13 claim in this doc carries an explicit evidence status (dropped/retained/low-yield/confirmed); FR-13a alone has none. An untested "salvaged sliver of Teian" is exactly where a point-value drafter could quietly re-enter (a range of width zero, `5-5%`, is a point value). | FR-13a, after "This is the breadth/precision line (§0.2) made enforceable."; add an evidence-status note like FR-13's | Either a ninth run demonstrates a persona producing a well-formed range + reasoning that a human found placeable, or FR-13a carries an explicit "hypothesis — untested as of v0.15" marker. A width-floor/degenerate-range check (range collapse to a point fails validation) is specified. |
| R3-F3 | Ops | medium | Restore changelog integrity: the header reads "**Version:** 0.15" but the version-history footers end at "*v0.11 — Sixth experiment…*". Runs #7/#8, FR-13c, and the OQ-8/OQ-9 RESOLVED decisions appear in the body with no v0.12-v0.15 entries recording when/why they landed. Add the four missing entries (or renumber honestly). | CRP's premise is "the document is the state": R1 rated the plan stale by diffing version labels, and the focus file routes reviewer attention by version. Four silent bumps break the audit trail this whole review process depends on — the same class of drift as R2-S7's v1.0/v1.1 mismatch, but on the requirements side and 4 versions wide. | End of the version-history block, after the *v0.11* entry | Every version number ≥ the header version has a dated changelog entry naming what changed; a doc-lint check (header version == last footer version) passes. |
| R3-F4 | Security | high | Place the panel transcript store under the safe-write floor and give it a disposition. FR-7 says "All kernel writes (`instantiate`, and any future capture) go through a single safe-write chokepoint," yet the orchestrator writes `.startd8/kickoff-panel/<session>.json` via a direct `Path` write (`run_kickoff_panel.py:365`) — and R1-F6 (endorsed) would make that persistence a *requirement* without placing it under the floor. State: (a) transcript writes route through the chokepoint once the panel is productized (FR-13c); (b) whether sessions are gitignored or committed (they embed the business objective/strategy and full persona outputs — potentially sensitive/pre-decisional); (c) retention/redaction expectations. | The transcripts are the human-validation substrate for the LLM synthesizer (the trust model of runs #6/#8) — the highest-trust artifact in the panel is currently the one write path with no confinement, no provenance, and no committed/ignored decision. Interaction risk: accepting R1-F6 without this makes the gap normative. | FR-7 (extend "any future capture") or a new item under FR-13c; cross-ref R1-F6 | Test: transcript writes are rejected outside the project root and are atomic (same chokepoint tests as FR-7/R2-F3); the requirements name the gitignore-vs-commit disposition; a session file containing a `<...>` objective block is traceably non-`authored`. |
| R3-F5 | Data | medium | Add a degraded-mode contract to FR-13b(5) mixed-model. When fewer than 2 independent model families are available (missing API keys, budget), the requirements must state what happens: refuse, or proceed with the run's corroboration labels downgraded. Concretely: the risk register must carry per-item **model-family provenance**, and any "convergence" produced by a single family must be labeled single-model (not "trustworthy"), mirroring run #6's corroboration grading — which is currently experiment prose, not a requirement. | The fifth run's central claim is that ONLY cross-family agreement upgrades convergence from "plausible" to "model-independent → real." A silent single-family fallback (the default failure mode of any multi-provider script when keys are absent) fabricates exactly that evidence class. This is the benchmark-matrix `is_infra_error` lesson applied to the panel: a missing key must degrade honestly, never masquerade as signal. | FR-13b item (5), after "a first-class facilitation lever"; cross-ref FR-13c | Test: run the orchestrator with one family's key removed → the run completes (or refuses, per the chosen contract) and every register item's corroboration label reads single-model/unverified; no output says cross-family. |
| R3-F6 | Ops | medium | Define the "budget gate" FR-13c H3 references, and wire it to the SDK's existing cost infrastructure. H3 says "wire real cost attribution so runs report spend and the budget gate is honest" — but no budget gate is specified anywhere in this doc (no cap, no config key, no exceeded-behavior). Additionally: (a) the SDK already ships `startd8.costs` (CostTracker, budget) and the benchmark_matrix fail-closed budget preflight — require the orchestrator to consume those rather than grow orchestrator-local tracking; (b) FR-13's "Offering costs $0; only accepting spends" should require the offer/acceptance to disclose an estimated call count + cost band (run #8 = 68 flagship calls) so acceptance is informed spend authorization. | H3 as written makes an honest report feed a gate that does not exist. Hand-rolling cost tracking in the orchestrator would duplicate shipped platform capability (Mottainai), and an undisclosed-cost "accept" contradicts the doc's own honesty discipline — FR-8 forbids dishonest values; an offer that hides its price is the monetary analogue. | FR-13c item 3; FR-13 "The offer is conditional." bullet | The requirement names the budget source (config key/flag), the exceeded behavior (halt, like H2), and the tracking substrate (`startd8.costs`); a test verifies a run halts at the cap and the acceptance prompt displays a call-count/cost estimate. |

**Endorsements (untriaged prior items this reviewer agrees with):**

- **R1-F3** (FR-6/NR-2 vs FR-13b/c conductor contradiction): strongly endorse — after 8 experiment write-ups, the doc still never says whether the orchestrator is exempt from NR-2; this is the single highest-leverage clarification left.
- **R1-F6** (persist raw transcripts as a requirement): endorse — but triage it *together with* R3-F4: requiring the persistence without the write-floor/disposition normativizes an unconfined write path.
- **R1-F5** (provenance value for shaping ranges): endorse — and note it compounds with R3-F2: a provenance value for an untested capability should land with the experiment, not before.
- **R2-F2** (import-error semantics in FR-15): endorse — a degrading try/except is the exact silent-degradation path the Context-Contracts principle forbids.
- **R2-F4** (H2 threshold default + tuning surface): endorse — the gate's value was demonstrated at N=5; shipping it unparameterized invites both noise-halts and misses.
- **R2-F5** (OQ-10 needs a named resolution target): endorse — three CRP rounds have now run and no reviewer can resolve OQ-10 *for* the author; the "Decide during CRP" framing has empirically failed its own mechanism.

**Disagreements:** none.

