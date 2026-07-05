# Guided Experience — Requirements

**Version:** 0.4 (Post-CRP triage — R1/R2/R3 applied)
**Date:** 2026-07-04
**Status:** Draft
**Parent:** `PROJECT_START_REQUIREMENTS.md` v0.17 (§0.4 essential-model revision, FR-6, NR-1/NR-2)
**Lens:** `docs/design-princples/ACCIDENTAL_COMPLEXITY_ANTI_PRINCIPLE.md`

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass grounded v0.1 against real code and corrected six things —
> including the load-bearing routing signal and the anti-sprawl success metric.
> Evidence is `file:line`.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| A "deployment-mode capability" knows the SDK's cloud/standalone context (FR-GE-3/8). | It **does not exist.** The only "deployment mode" (`deploy_harness/ladder.py:92`, `# startd8-mode:` header) grades the **generated app's** posture, not the SDK's own hosting context. No cloud/standalone/no-agent self-awareness anywhere in `src/startd8/`. | FR-GE-3 re-keyed: route on **explicit preference** (reuse the `concierge_agent.py:59-75` flag→project→global→default ladder) > **surface** (served ⇒ offer) > **project-shape** (`build_assess`). Drop "driving-agent presence" as a *detected* signal — a CLI human with an agent and a standalone human are byte-identical to the process; flag/config/TTY only. |
| The facilitation panel is a "prototype orchestrator" to harden in place. | The whole facilitated process (grounding/assumptions/adversary/anti-smoothing/rounds) lives **only in `scripts/run_kickoff_panel.py`** (438 LOC, un-packaged, un-tested, un-importable). `stakeholder_panel/` provides only the "mirror" (`panel.py:172/216`), not the "lens". | New FR-GE-11a: **promote the script into `stakeholder_panel/facilitation.py`** (over the existing `StakeholderPanel`/roster/guards) *before* hardening. The biggest lift; it *adds* a module (see the anti-sprawl reframe). |
| Facilitation writes ride the safe-write floor (FR-GE-13). | The script writes transcripts directly to `.startd8/kickoff-panel/` (`run_kickoff_panel.py:249,365`) — **bypassing** `concierge/safe_write.py`. FR-GE-13 is violated by the component FR-GE-11 most depends on. | Promotion must route persistence through the floor (folded into FR-GE-11a/FR-GE-13). |
| Cloud serve reuses the local loopback+token+CSP model (FR-GE-8). | The local model **refuses** cloud by construction (`consult/serve.py:75` raises on non-loopback; kickoff `web.py:314` pins loopback). Cloud auth = only a static `X-API-Key` on POST (`server/auth.py`) — no principal/tenancy/session. Cloud-**write** is net-new security, not reuse. | FR-GE-8 split: v-next cloud is **read/preview-only**; cloud-**write** deferred to a net-new auth/tenancy design (new OQ-GE-7). |
| The conductor is an "agentic from-nothing" loop. | It is **deterministic-first.** `red_carpet_advisor.py:3` is explicitly no-LLM and already emits the ranked, command-bearing guidance; `wizard.py:1` is a "$0 deterministic conductor"; the LLM is a strictly opt-in `--agent` branch (`cli_kickoff.py:409-482`). | FR-GE-5 "Guide" marked **deterministic-first, $0, LLM-optional** — so "never left without it" (FR-GE-2) is satisfied at **zero LLM**. Shrinks the conductor; no chat panel to re-host. |
| Consolidation "net-reduces modules" (anti-sprawl headline). | `kickoff_experience/` is **24 modules/6,422 LOC**; 3 CLI groups / **23 verbs**. Consolidation genuinely reduces **surfaces (23→~12 verbs, 3→1 groups), write paths (→1), vocabulary (5→1)** — but is a *detangling*, not a deletion (LOC ~flat), and facilitation promotion *adds* a module. | Reframe the anti-sprawl metric from "net-reduce modules" to **"one entry point, one vocabulary, one write path"** (honestly satisfiable). |

**Resolved open questions (see §4 for full text):** OQ-GE-1 → route on preference>surface>shape, no agent-detection. OQ-GE-2 → `startd8 kickoff` is the one group; retire `concierge`/`panel` groups into it. OQ-GE-3/GE-6 → reduction is at surface/vocab/write-path, not LOC; facilitation promotion adds a module. OQ-GE-4 → cloud read-only v-next, write deferred (new OQ-GE-7). OQ-GE-5 → deterministic-first, LLM opt-in.

### 0.1 Lessons-Learned Hardening (v0.3)

> Consulted the SDK lessons base. Applied:
- **[Phantom-reference audit]** — verified every load-bearing symbol directly:
  the reused routing ladder is *verbatim* flag→project→global→default
  (`concierge_agent.py:5-8`); `build_kickoff_plan` exists (`orchestrator.py:123`);
  the three CLI groups are exactly `kickoff`/`concierge`/`panel` (`cli.py:1258-1260`,
  confirming the retire-two-into-one target); `stakeholder_panel/facilitation.py` is
  **confirmed absent** (the promotion target, D2); the advisor is **confirmed no-LLM/$0**
  (`red_carpet_advisor.py:1,3`). **All pass** — the plan rests on real code.
- **[Single-source vocabulary ownership]** — the FR-13c hardening (H1/H2/H3), the
  safe-write floor (FR-7), and the SOTTO invariant are **owned by the parent**
  (`PROJECT_START_REQUIREMENTS.md`); this doc **cites** them (FR-GE-10/11a/13/1), it
  does not restate/fork the rules.
- **[Prune phantom scope]** — cloud-write was pruned (no trust substrate) → deferred
  to OQ-GE-7, not carried as an in-scope requirement.
- **[CRP steering]** — least-reviewed = this doc (brand-new). Settled/do-not-relitigate
  for CRP: the v0.17 essential model (available-not-required, complement-not-substitute),
  the deterministic-first conductor, and the "one entry point/vocabulary/write path"
  success metric.

---

## 1. Problem Statement

The project-start distillation established a **kernel** (`survey`/`instantiate`/
`assess`/`derive`, $0, deterministic) and — in v0.17 — corrected the assumption that
every user has their own agent. The revised essential model is a **spectrum, "meet
the user where they are"**: a bring-your-own-agent user drives the kernel with their
own agent; a **standalone / cloud / no-agent** user needs the SDK to provide **its
own guided experience** over the same kernel.

That guided experience must now be **built as one coherent, optional layer** — this
document specifies it. Two forces shape it:

1. **It is essential for a real audience** (standalone/cloud/no-agent users) — for
   them the SDK's guided experience is their *only* harness.
2. **It must not re-accrete the sprawl** the distillation removed. The prior state
   was five overlapping metaphors (Concierge, Welcome Mat, Red Carpet, Kaigi/
   Stakeholder Panel, Teian). The guided experience **consolidates** their real
   value into *one* experience; it does not resurrect five.

### Gap table

| Component (today) | Current state | Gap for the guided experience |
|---|---|---|
| Welcome Mat (`kickoff_experience/`) | Served visual readiness surface (readiness meter + per-field badges) | Keep the *visual-readiness* value; fold into one experience; drop the disjoint metaphor identity |
| Red Carpet (`red_carpet*.py`) | Agentic "from-nothing" conductor + advisor + wizard | Keep the *conductor* value (walk a no-agent user to build-ready); fold in; drop the separate metaphor |
| Facilitation panel (`run_kickoff_panel.py` + `stakeholder_panel/`) | Validated multi-perspective discovery (mirror→lens→convergence); prototype orchestrator | Keep as the *optional discovery pass* within the experience; apply FR-13c hardening |
| Teian point-value drafter | The dropped ghost | Stays dropped (NR-7) |
| Routing / "which experience" | Ad-hoc; no detection of agent-present vs. standalone/cloud | New: offer-not-force routing on **explicit-preference > surface > project-shape** signals (agent-presence is **never detected** — §0 D1) |
| Deployment (cloud/standalone) | **No SDK self-hosting-context capability exists** (§0 D1); the only "deployment mode" grades the *generated app's* posture, not the SDK's own hosting context; guided experience not wired as the no-agent surface | New: the guided experience is the primary surface when no agent is present |

---

## 2. Requirements

### The optional layer

- **FR-GE-1 — Optional layer over the kernel (SOTTO).** The guided experience is an
  **additive, opt-in layer** over the kernel. The kernel works fully and
  **byte-identically without it**; engaging it leaves no trace in the kernel's
  outputs when subsequently absent. The kernel never depends on the guided layer.
  **Residue acceptance (R1-F11):** engaging *then disengaging* the layer (a guided
  run, then a `--no-guided` run) must leave kernel outputs **byte-identical to a
  never-engaged run** — residue (config, cached transcripts, preference files) from a
  prior guided run must not perturb a later kernel-only run. Golden test: kernel-only
  run A vs guided-then-kernel-only run B ⇒ identical kernel bytes.

- **FR-GE-2 — Available but not required; complement not substitute.** The guided
  experience is **offered, never forced**. A BYO-agent user is never pushed into it;
  a no-agent user is never left without it. It **never replaces** the kernel — every
  input it helps produce is the same input a BYO-agent user would author.

### Routing — "meet the user where they are"

- **FR-GE-3 — Offer-not-force routing (re-keyed, v0.2; semantic contract v0.4).** The
  SDK decides *whether to offer* the guided experience from cheap signals, in this
  precedence — expressed as a **semantic contract**, using the same precedence
  *pattern* as the `concierge_agent.py:59-75` ladder but **not reused verbatim**
  (R2-F3): the source ladder is the reference, not the definition; a contract test
  owns these semantics and does not import `concierge_agent.py`. Precedence: **(1)
  explicit preference** — `--guided/--no-guided` flag > per-project
  `build-preferences.yaml` > global `~/.startd8/config.json` > default; **(2)
  surface** — a served/TUI invocation implies no-agent ⇒ offer; **(3) project-shape**
  — `build_assess` greenfield-blank ⇒ stronger offer, rich-brownfield ⇒ quieter. The
  result is an *offer*, never a forced path; default bias quiet (a wrong offer is one
  ignorable line, never a gate).
  - **Tri-state semantics (R3-F2).** Each preference layer is **tri-state** — `on` /
    `off` / `unset`. The guided preference's value domain is **not** the agent-spec
    ladder's (which resolves a *non-empty string* and skips falsy/unusable layers via
    `_usable()`): here an explicit **`off`** at a higher layer (`--no-guided`, or
    project `guided: false`) **terminates resolution** and must **never fall through**
    to a lower layer's `on`. A falsy/`None` fall-through here would silently violate
    FR-GE-4 — so "verbatim" is exactly the property that cannot hold.
  - **Non-interactive (R1-F4).** When stdout/stdin is non-interactive (piped, no TTY,
    CI), the offer line is **suppressed, never blocking**; `--guided` still runs
    without the offer prose; kernel bytes unchanged.
  - **Served-agent (R1-F5).** The surface heuristic (2) is **overridable**: an agent
    serving the UI is expected to set `--no-guided`/config to suppress the offer;
    explicit preference always beats the surface heuristic (a served surface *can* be
    agent-driven).
  - **Not a signal:** "presence of a driving agent" is **not detected** — a CLI human
    with their own agent and a standalone human are byte-identical to the process
    (planning D1). Agent-presence is expressed only through the explicit preference,
    never inferred.

- **FR-GE-4 — Explicit override always wins.** A user can always force-on
  (`--guided`) or force-off (`--no-guided`) regardless of the detected signals.
  Detection is a convenience, not an authority. **Force-off must not be lost to a
  falsy fall-through (R3-F2):** because the preference is tri-state (FR-GE-3), an
  explicit force-**off** must terminate ladder resolution and must **not** be dropped
  to a lower layer's `on` by a falsy/`None` skip in the reused precedence. Contract
  test: project `guided: false` + global `guided: true` ⇒ **no offer**; `--no-guided`
  beats any config `true` — both must pass without importing `concierge_agent.py`.

### One consolidated experience (anti-sprawl)

- **FR-GE-5 — ONE coherent experience, not three metaphors.** The guided experience
  presents as a **single mental model with one entry point and one vocabulary**,
  consolidating three *functions* (not three products):
  1. **Orient** — a visual/CLI **readiness surface** (the Welcome-Mat value): render
     `assess` — what's present, what's blank, what's next.
  2. **Guide** — a **conductor** (the Red-Carpet value): walk the user through
     `survey → instantiate → (derive) → assess`, filling inputs step by step, from
     nothing to build-ready.
  3. **Deepen (optional)** — the **facilitation panel** (the discovery capability):
     a multi-perspective pass that surfaces risks/gaps for human judgment.
  These are *phases of one flow*, not separate surfaces a user must juggle.
  **Guide is deterministic-first (v0.2):** the conductor's guidance is **$0 / no-LLM
  by default** — the existing deterministic advisor (`red_carpet_advisor.py`, no-LLM)
  + wizard already walk a no-agent user to build-ready. The LLM `--agent` loop stays
  **strictly opt-in and propose-only**; it is NOT required for "guided", so
  FR-GE-2's "never left without it" is satisfied at **zero LLM cost** (planning D5).
  **Deepen skip / early-exit (R2-F4):** Deepen is optional *mid-flow* too — a user who
  enters it and abandons before completion exits **cleanly**: Guide-phase outputs
  intact, **no partial transcript committed**, no kernel-visible residue (atomic per
  FR-GE-13). Test: a Deepen session interrupted (Ctrl-C / explicit skip) leaves Guide
  outputs unchanged and the safe-write store clean or atomically rolled back; kernel
  outputs after abort are byte-identical to a Guide-only run.

- **FR-GE-6 — Over the SAME kernel; no new engine.** The guided experience adds
  **sequencing, presentation, and prompts only**. It reuses the kernel verbs
  (`survey`/`instantiate`/`assess`/`derive`) and the safe-write floor; it introduces
  **no new extractor, generator, writer, or readiness computation**. (Anti-principle:
  the guided layer is orchestration, not a second implementation.) **Enforcement
  (R2-F2):** this is a **CI-enforceable gate**, not an assertion — an AST/grep check
  over the guided-layer modules **fails** if a new class or function matching the
  prohibited extractor/generator/writer/readiness-computation patterns is introduced;
  the check is part of the M2 exit gate (the M2 detangle is the riskiest window for
  accidental engine introduction).

- **FR-GE-7 — Consolidate; success metric = one entry point / one vocabulary / one
  write path (reframed v0.2).** The user-facing surface uses **one name** and **one
  entry point**: `startd8 kickoff` absorbs and retires the separate `concierge` and
  `panel` CLI groups (planning: 3 groups / 23 verbs → 1 group / ~12 verbs). The five
  metaphor names (Concierge / Welcome Mat / Red Carpet / Kaigi / Teian) are retired
  from user-facing vocabulary. **Honest success metric (planning D3/D7):** the win is
  measured in **surfaces (23→~12 verbs, 3→1 groups), vocabulary (5→1), and write
  paths (→1 via the safe-write floor)** — NOT in raw LOC. This is a *detangling*, and
  facilitation promotion (FR-GE-11a) *adds* a module; the anti-sprawl claim is
  "one entry point, one vocabulary, one write path," not "fewer lines."
  - **Anti-re-accretion conformance (R1-F1).** After M1 it is a **spec violation** to
    introduce a new top-level CLI group in the kickoff domain, or a second
    user-facing vocabulary for these functions. CI asserts `startd8 --help` exposes
    **exactly one** kickoff-domain group post-M1; a new group registration fails lint.
    Without a testable prohibition the sprawl re-accretes exactly as it did before.
  - **Vocabulary scope (R2-F7).** "User-facing vocabulary" covers not only `--help`
    and docs but CLI **error, `--verbose`, and traceback output** — internal names
    leak there and re-emerge as a second vocabulary. The five retired metaphor names
    must appear in none of these at the M1/M2 exit gate.
  - **Surfaces the metric covers (R3-F5).** The one-vocabulary metric enumerates CLI
    groups/verbs, TUI labels, served-UI text, **and the MCP `startd8_concierge` action
    enum** (a live vocabulary surface). Retiring the MCP action vocabulary rides the
    **parent's amended FR-10 alias window** (which the parent CRP extended to cover
    both CLI names *and* the MCP `ConciergeInput.action` enum) — cited, not forked
    (§0.1 single-source ownership); if MCP is scoped out of v-next, that is stated
    with rationale.

### Deployment contexts (first-class)

- **FR-GE-8 — Standalone first-class; cloud read-only (split, v0.2).** The guided
  experience is the **primary** surface when no agent is present, in: (a) a
  **standalone/local install** — CLI + optional **local served UI**, using the
  existing loopback+token+CSP trust model (`consult/serve.py`, kickoff `web.py`) for
  local **writes**; and (b) a **cloud deployment** — served UI, **read/preview-only**
  (Orient + Deepen-view; the human downloads produced inputs and writes locally,
  honoring FR-GE-13 "human/CLI is the sole writer"). **Cloud-write is out of scope
  for v-next** — the local trust model *refuses* cloud by construction (planning D6)
  and no principal/tenancy/session substrate exists; cloud-write needs a net-new auth
  design (OQ-GE-7). Note: there is **no SDK self-hosting-context capability** to tie
  into (planning D1); "cloud vs standalone" is known only from how the SDK is
  invoked/served, not detected.
  - **Cloud Deepen cost/abuse (R1-F8).** Cloud read/preview-only serves **only
    already-persisted transcripts** — a static preview with **no LLM call**.
    **LLM-invoking Deepen is disabled on cloud** for v-next, because cloud has only a
    static `X-API-Key` (no principal/tenancy) and a read-only surface that triggers
    paid LLM calls (FR-GE-10 H3) is an un-metered per-tenant cost/abuse surface,
    *distinct* from the write-trust problem OQ-GE-7 defers. Any future cloud
    LLM-invoking Deepen is folded into OQ-GE-7's net-new auth/tenancy design and gated
    by a per-tenant budget control.
  - **Download format (R2-F5).** What a cloud user downloads is **byte-identical to
    the local safe-write output** (the same YAML/JSON files the local floor would
    produce), so it feeds the kernel with no conversion and preserves FR-GE-2's
    same-input guarantee. Test: a file downloaded from cloud, written to local
    `.startd8/`, passes kernel `assess` identically to a locally produced file.

- **FR-GE-9 — Surface parity across CLI / TUI / served.** The same guided experience
  is reachable from CLI, TUI, and a served (web) surface. **Parity is of *produced
  inputs/artifacts*, not of interaction modality (R1-F12):** some phases are
  modality-bound (a served UI cannot run an interactive TTY wizard step), so
  "differing only in rendering" is scoped to *outcome* — each surface must produce the
  same inputs, and the parity test asserts identical produced artifacts, **not**
  identical interaction steps. Cross-surface parity is a test requirement.

### The facilitation panel (hardened)

- **FR-GE-10 — Facilitation hardening (FR-13c H1/H2/H3).** The discovery/facilitation
  phase carries the parent hardening: **H1** artifact-grounding fidelity (ground on
  the real system, not just a schema/description), **H2** assumptions-check-as-gate
  (halt + surface "validate the premise" on ≥N high-impact/low-confidence
  assumptions), **H3** cost tracking (real per-call spend, budget-gated).
  - **H2 is scoped to the Deepen phase only (R1-F7).** The halt fires **only** after
    the human has opted into Deepen; Orient/Guide **never** halt on assumptions, so H2
    never contradicts FR-GE-3's "never a gate" offer guarantee. Test: Orient/Guide
    never halt; only an explicitly-entered Deepen pass can.
  - **H3 scope (R2-F6).** "Budget-gated" is bounded: **per-round** cost is logged, the
    **session total** is surfaced in the Deepen output, and the budget cap is a **hard
    halt** checked **before** each LLM call — **no** call is made after the cap is
    breached (not a warning, not advisory).

- **FR-GE-11a — Promote the facilitation process into the package, then harden
  (v0.2, planning D2/D8).** The facilitated multi-round process currently exists
  **only** as an un-packaged, un-tested script (`scripts/run_kickoff_panel.py`, 438
  LOC) whose transcript writes **bypass the safe-write floor**. Before FR-GE-10/11/12
  can hold, the orchestration must be **promoted into `stakeholder_panel/
  facilitation.py`** — built over the existing `StakeholderPanel`/roster/guards, with
  persistence routed through `concierge/safe_write.py` — so it is importable,
  testable, and confined. Hardening (H1/H2/H3, transcript persistence, anti-smoothing)
  applies to the *promoted* module, not the script.
  - **Behavioral equivalence, promote-before-harden (R1-F2).** The promotion must
    **preserve behavior**: capture a **golden transcript** (fixed seed/personas) from
    `run_kickoff_panel.py` and assert the promoted module reproduces round structure,
    per-persona outputs, and FR-GE-12 named tensions **before any hardening begins**.
    A promotion that silently changes rounds/synthesis is a regression no other
    criterion catches.
  - **Depends-on OQ-GE-8 (R1-F3; now RESOLVED, §4).** The promoted module **reuses
    `StakeholderPanel.ask_all`** for each round's mirror and adds a **thin multi-round /
    cross-pollination / synthesis orchestration layer above it** — no new engine
    (FR-GE-6). This resolution unblocks the build; M3a (promote + equivalence gate)
    precedes M3b (harden).
  - **Transcript contract preservation (R3-F4).** Re-routing persistence through the
    safe-write floor must **preserve the transcript contract** the sibling
    observability-UX doc consumes: the path (`.startd8/kickoff-panel/<session_id>.json`,
    `KICKOFF_PANEL_OBSERVABILITY_UX_REQUIREMENTS.md` FR-UX-1), the
    `KICKOFF_PANEL_FACILITATION_DESIGN.md` §6 schema, and the **round-by-round
    incremental write cadence** (FR-UX-17 live-follow polls the file as rounds land).
    An end-of-session-only atomic write **breaks** live-follow even though every other
    FR-GE-11a bullet still passes; require **per-round atomic-replace**, or version the
    contract and update the UX doc in the same change.

- **FR-GE-11 — Persist raw per-round transcripts (parent-CRP R1-F6 — transcript
  persistence).** The facilitation phase
  **persists the raw per-round persona outputs** as the human-validation substrate
  for the LLM synthesizer, distinct from the synthesized register. This is a
  requirement (the value case relies on it), rendered by the observability UX
  (`KICKOFF_PANEL_OBSERVABILITY_UX_REQUIREMENTS.md` — reference, not duplicated here).

- **FR-GE-12 — Anti-smoothing is a requirement, not a behavior (parent-CRP R2-F7 —
  anti-smoothing).** The synthesizer **must preserve open tensions** — a cross-role
  disagreement present in the raw rounds must appear in the synthesis as an explicit
  open item, never resolved into false consensus. Testable: named raw-round tensions
  must be present in the synthesis output. **Tension-naming schema (R2-F1):** each
  raw-round tension carries a **machine-checkable identity** (`tension_id`, e.g. `T1`)
  in a structured field, so the anti-smoothing assertion is checked **structurally** —
  a synthesis run must surface each `tension_id` as an explicit open item, never
  resolved — **not** by prose-matching (which cannot distinguish a tension preserved
  from one paraphrased away). CI asserts this on a tagged fixture.

### Safety

- **FR-GE-13 — All writes ride the kernel safe-write floor (parent FR-7 / parent-CRP
  R3-F4 — safe-write store).** Every byte the guided experience writes — input files
  AND facilitation transcripts — goes through the kernel's **confined, human-privilege
  safe-write floor** (no traversal/symlink escape, atomic). Over any LLM-invoked
  surface it is read/preview-only; the human/CLI is the sole writer.
  **Config/preference writes are not exempt (R1-F6):** the guided layer's own routing
  writes — `build-preferences.yaml`, `~/.startd8/config.json` (FR-GE-3) — **also** ride
  the floor (confined, atomic, traversal-safe); "every byte the guided experience
  writes" includes them. **Atomicity granularity (R3-F4)** is load-bearing for the
  observability-UX live-follow consumer: transcript writes are **per-round
  atomic-replace**, not end-of-session-only, so FR-UX-17 polling still sees rounds
  land incrementally.

- **FR-GE-14 — Produces inputs for human ratification; never authors or decides.**
  The guided experience helps a human *produce and judge* inputs. It never authors
  real value content (bucket 4) and never makes a decision the human should make;
  every synthetic output is provenance-marked and human-ratified. **Acceptance
  (R1-F10):** every synthetic output carries a **machine-checkable provenance marker**
  and a **ratification state** (unratified by default); the kernel **refuses (or warns
  on) an unratified synthetic input** until the human explicitly ratifies it. Test: a
  synthetic input written by the guided layer is tagged unratified; feeding it to the
  kernel without ratification is refused/warned.
  - **Status — PARTIAL (prose-only ratification; structural gate DEFERRED).** Today the
    guided/deepen surfaces only *label* synthetic outputs as unratified in prose (e.g. the
    Deepen surface line "*(paid, synthetic — unratified input)*" in `concierge_view.py` /
    `web.py`). The **machine-checkable provenance marker** and the **structural refuse/warn
    gate** (the kernel rejecting an unratified synthetic input at the consume boundary) are
    **not yet implemented** — the acceptance test above is the target, not a delivered claim.

---

## 3. Non-Requirements

- **NR-GE-1 — Does not replace the kernel.** The BYO-agent path ($0 kernel + handoff)
  remains first-class and unchanged.
- **NR-GE-2 — Never forced.** No user is compelled into the guided experience.
- **NR-GE-3 — No point-value drafting.** The Teian ghost stays dropped (NR-7).
- **NR-GE-4 — Not a re-accretion of five metaphors.** One experience, one name.
- **NR-GE-5 — No new kernel engine.** Sequencing/presentation only; no new
  extractor/generator/writer/readiness.
- **NR-GE-6 — Does not author real content or decide.** Human ratifies.

---

## 4. Open Questions

_OQ-GE-1 through GE-6 resolved by the planning pass (§0); OQ-GE-8 resolved by CRP
triage (v0.4). Only OQ-GE-7 (cloud-write trust model) remains open._

- **OQ-GE-1 — RESOLVED.** No SDK self-hosting-context capability exists (D1). Route on
  explicit-preference > surface > project-shape; agent-presence is preference-only,
  never detected.
- **OQ-GE-2 — RESOLVED.** One group = `startd8 kickoff`; retire `concierge`/`panel`
  groups into it (`cli.py:1259-1260`). Add `kickoff guided` (or no-subcommand ⇒
  guided offer) sequencing Orient→Guide→Deepen over `orchestrator.py:build_kickoff_plan`.
- **OQ-GE-3/GE-6 — RESOLVED.** Reduction is at surface/vocab/write-path, not LOC;
  facilitation promotion adds a module. Detangle the concierge-UI quartet + the
  three "what's next" projections + the three chat constructors (D3/D7).
- **OQ-GE-4 — RESOLVED (split).** Cloud read/preview-only for v-next; cloud-write
  deferred → OQ-GE-7.
- **OQ-GE-5 — RESOLVED.** Deterministic-first ($0 advisor + wizard); LLM opt-in.
- **OQ-GE-7 (NEW) — Cloud-write trust model.** A cloud (non-loopback) guided
  experience that *writes* needs a net-new auth/tenancy/session design — none exists
  (`server/auth.py` is a static API-key on POST only, D6). What principal + tenancy +
  CSRF model does cloud-write require, and does it belong to the guided experience or
  to a broader SDK deployment-auth capability? Deferred; blocks FR-GE-8 cloud-write.
- **OQ-GE-8 — RESOLVED (v0.4, R1-F3).** Promoting `run_kickoff_panel.py` (438 LOC)
  into `stakeholder_panel/facilitation.py` (FR-GE-11a): the promoted module **reuses
  `StakeholderPanel.ask_all` directly** for each round's mirror and adds a **thin
  multi-round / cross-pollination / synthesis orchestration layer above it**
  (sequencing + per-round persistence + synthesis prompt) — orchestration only, **no
  new engine** (FR-GE-6). This is enough to unblock M3a; any deeper abstraction is an
  implementation detail, not a blocker. The build shape no longer depends on an open
  question (the prior circular dependency R1-F3 flagged is dissolved).

---

*v0.2 — Post-planning self-reflective update. 5 requirements corrected (FR-GE-3
routing re-keyed, FR-GE-5 deterministic-first, FR-GE-8 cloud split, FR-GE-7
success-metric reframed, gap-table facilitation baseline), 1 added (FR-GE-11a
promote-then-harden), 6 OQs resolved, 2 new (cloud-write, promotion scope). The
consolidation survives — but "net-reduce modules" was the wrong headline; the real
win is one entry point / one vocabulary / one write path, and the detection signal I
assumed (SDK deployment-mode self-awareness) does not exist.*

*v0.4 — Post-CRP triage (R1 claude-opus-4-8, R2 claude-sonnet-4-6, R3 claude-fable-5).
24 F-suggestions accepted and merged into prose: routing tri-state + non-interactive +
served-agent + semantic-contract (FR-GE-3/4), FR-GE-11a behavioral-equivalence +
transcript-contract + OQ-GE-8 resolution, FR-GE-12 tension-naming schema, FR-GE-6 CI
gate, FR-GE-7 anti-re-accretion + vocab-scope + MCP-surface, FR-GE-8 cloud-Deepen
cost/abuse + download format, safety acceptance criteria (FR-GE-1/13/14), gap-table
stale-row fix, and cross-doc review-ID namespacing (parent-CRP citations). Version
reconciled to v0.4 across header/footer; plan tracks v0.4. See Appendix A.*

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
| R1-F1 | Anti-re-accretion conformance clause | R1 | Merged into FR-GE-7 (spec-violation to add new kickoff group/vocab post-M1) | 2026-07-04 |
| R1-F2 | Behavioral-equivalence golden transcript | R1 | Merged into FR-GE-11a (promote-before-harden gate) | 2026-07-04 |
| R1-F3 | Block FR-GE-11a on OQ-GE-8 | R1 | Resolved OQ-GE-8 in §4; FR-GE-11a Depends-on clause added | 2026-07-04 |
| R1-F4 | Non-interactive offer suppression | R1 | Merged into FR-GE-3 (non-interactive clause) | 2026-07-04 |
| R1-F5 | Served-agent overridable heuristic | R1 | Merged into FR-GE-3 (served-agent clause) | 2026-07-04 |
| R1-F6 | Enumerate config/preference writes | R1 | Merged into FR-GE-13 (not-exempt clause) | 2026-07-04 |
| R1-F7 | Scope H2 halt to Deepen only | R1 | Merged into FR-GE-10 (H2 scope bullet) | 2026-07-04 |
| R1-F8 | Cloud Deepen cost/abuse gating | R1 | Merged into FR-GE-8 (LLM-Deepen disabled on cloud; fold to OQ-GE-7) | 2026-07-04 |
| R1-F9 | Reconcile version drift | R1 | Header/footer → v0.4; plan Tracks → v0.4 | 2026-07-04 |
| R1-F10 | FR-GE-14 provenance/ratification test | R1 | Merged into FR-GE-14 (acceptance criterion) | 2026-07-04 |
| R1-F11 | SOTTO engaged-then-disengaged residue | R1 | Merged into FR-GE-1 (residue acceptance) | 2026-07-04 |
| R1-F12 | Parity of outcome, not modality | R1 | Merged into FR-GE-9 | 2026-07-04 |
| R2-F1 | Tension-naming/tagging schema | R2 | Merged into FR-GE-12 (`tension_id` structural check) | 2026-07-04 |
| R2-F2 | FR-GE-6 CI-enforceable criterion | R2 | Merged into FR-GE-6 (AST/grep M2 gate) | 2026-07-04 |
| R2-F3 | Routing semantic contract (not verbatim) | R2 | Merged into FR-GE-3 (semantic-contract framing) | 2026-07-04 |
| R2-F4 | Deepen skip / early-exit guarantee | R2 | Merged into FR-GE-5 | 2026-07-04 |
| R2-F5 | Cloud download artifact format | R2 | Merged into FR-GE-8 (byte-identical to local safe-write) | 2026-07-04 |
| R2-F6 | Scope H3 cost tracking | R2 | Merged into FR-GE-10 (H3 scope bullet) | 2026-07-04 |
| R2-F7 | Vocabulary-retirement scope boundary | R2 | Merged into FR-GE-7 (covers errors/verbose/tracebacks) | 2026-07-04 |
| R3-F1 | Namespace cross-doc review-ID citations | R3 | Re-cited FR-GE-11/12/13 as `parent-CRP …` | 2026-07-04 |
| R3-F2 | Tri-state / force-off falsy fall-through | R3 | Merged into FR-GE-3 tri-state + FR-GE-4 | 2026-07-04 |
| R3-F3 | Fix stale v0.1 gap-table rows | R3 | Gap-table rows 5–6 + §0.1 line-ref corrected | 2026-07-04 |
| R3-F4 | Preserve transcript contract on re-route | R3 | Merged into FR-GE-11a + FR-GE-13 (per-round atomic cadence) | 2026-07-04 |
| R3-F5 | Enumerate surfaces incl. MCP action enum | R3 | Merged into FR-GE-7 (MCP rides parent FR-10 alias window) | 2026-07-04 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none — all R1/R2/R3 F-suggestions accepted; reviewers avoided SETTLED items and used Endorsements for overlaps) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R3 — claude-fable-5 — 2026-07-04

- **Reviewer**: claude-fable-5
- **Date**: 2026-07-04 21:05:00 UTC
- **Scope**: Third-pass review (F-prefix). R1 covered routing edges, promotion equivalence, cloud cost/abuse, version drift, ratification; R2 covered operationalization/testability. R3 lens: **cross-document consistency** (parent v0.17 as amended by its own CRP, the KICKOFF_PANEL_* siblings, and the code the doc cites), **identifier hygiene**, and **empirical verifiability of the consolidation claims**. All load-bearing numbers were re-verified against the worktree (24 modules on disk in `kickoff_experience/`; `run_kickoff_panel.py` = 438 LOC; 23 command registrations across the three groups; `concierge`/`panel` registered at `cli.py:1259-1260`). Settled items (focus §SETTLED 1–6) not relitigated.

##### Sponsor focus asks (R3 deltas only — R1's full ask answers stand)

**Ask 1 — Consolidation soundness (FR-GE-5/6/7).**
- **Summary answer:** Partial — the merge targets are real (verified on disk), but the "one entry point / one vocabulary" metric silently omits the **MCP surface**, and the gap table still carries stale v0.1 text that contradicts the doc's own planning discoveries.
- **Rationale:** The parent's FR-10 was amended by its own CRP (parent Appendix A, R1-F2) to require the alias window to cover **both** CLI names **and** the MCP `ConciergeInput.action` enum; the `startd8_concierge` MCP tool is a live vocabulary surface (`concierge/__init__.py:8`), yet FR-GE-7's metric counts only CLI groups/verbs.
- **Assumptions / conditions:** The MCP tool remains shipped in v-next.
- **Suggested improvements:** R3-F3 (stale gap-table rows), R3-F5 (extend the metric's surface enumeration).

**Ask 2 — FR-GE-11a facilitation promotion.**
- **Summary answer:** One binding interface is unstated: the promoted module must preserve the **transcript contract** the sibling observability-UX doc consumes, or FR-UX-1/FR-UX-17 break the moment persistence is re-routed. See R3-F4.

**Ask 3 — Routing (FR-GE-3/4).**
- **Summary answer:** The "reused **verbatim**" claim is empirically unsound for a tri-state preference — the cited ladder resolves *non-empty agent-spec strings* and **skips falsy/unusable layers** (`_usable()`), so verbatim reuse turns an explicit force-**off** into fall-through to a lower layer. This is a concrete defect in FR-GE-4's "explicit override always wins," not just the copy-dependency R2-F3 named. See R3-F2.

**Ask 4 — Safe-write (FR-GE-13/14).**
- **Summary answer:** Sound as amended by R1-F6; R3 adds only that the floor's **atomicity granularity** (per-round vs end-of-session) is load-bearing for the sibling doc's live-follow (folded into R3-F4; plan-side R3-S1).

**Ask 5 — Cloud read-only (FR-GE-8).**
- **Summary answer:** Coherent as a deferral; nothing beyond R1-F8/R2-F5, both endorsed below. No new suggestion.

**Ask 6 — Requirements↔plan / parent contradictions.**
- **Summary answer:** Two new cross-doc defects: **un-namespaced parent review-ID citations** in FR-GE-11/12/13 now collide with this doc's own Appendix C IDs (R3-F1 — note this very round mints an `R3-F4` that collides with the `R3-F4` cited in FR-GE-13), and the plan re-imports the **module-count metric** the requirements explicitly retired (plan-side R3-S4).

##### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Data | high | Namespace the cross-document review-ID citations: FR-GE-11 "(R1-F6)", FR-GE-12 "(R2-F7)", and FR-GE-13 "(FR-7 / R3-F4)" cite the **parent** doc's CRP round IDs (parent Appendix A rows R1-F6/R2-F7/R3-F4), but this doc's own Appendix C now contains a *different* R1-F6 (config writes) and R2-F7 (vocabulary scope) — and this round mints a third colliding `R3-F4`. Rewrite as `parent-CRP R1-F6` / `PS-R1-F6` (pick one convention) at all three sites. | Un-namespaced IDs are ambiguous provenance: a triager resolving "(R1-F6)" inside this doc will land on the *wrong* suggestion. The collision is not hypothetical — all three cited IDs now have same-named counterparts in this doc's own review log. | §2 FR-GE-11, FR-GE-12, FR-GE-13 provenance parentheticals | Grep: every `R{n}-[SF]{k}` citation in the doc body resolves unambiguously to exactly one appendix (this doc's or an explicitly named external doc's). |
| R3-F2 | Interfaces | high | FR-GE-3/FR-GE-4: drop "reused **verbatim**" and specify **tri-state semantics per layer** (force-on / force-off / unset). The cited ladder (`concierge_agent.py:59-75`) resolves a *non-empty string* and its `_usable()` guard **skips falsy layers** — verbatim reuse of that shape makes an explicit `guided: false` in `build-preferences.yaml` fall through to a global `guided: true`, violating FR-GE-4. Each layer must distinguish "explicitly off" from "unset", and explicit-off at a higher layer must terminate resolution. | The existing ladder answers "which model spec?" (never falsy); the guided preference answers "on/off/unset" (falsy is meaningful). Same precedence *shape*, incompatible value domain — the strongest word in the requirement ("verbatim") is exactly the part that cannot be true. Extends R2-F3 (semantic contract) with a concrete, testable fall-through defect. | §2 FR-GE-3 precedence clause + FR-GE-4 | Contract test: project-level `guided: false` + global `guided: true` ⇒ no offer; `--no-guided` + project `guided: true` ⇒ no offer. Both must pass without importing `concierge_agent.py`. |
| R3-F3 | Architecture | medium | Fix the stale v0.1 rows in the §1 gap table: row 6 says "Deployment-mode capability **exists**" — directly contradicting §0 planning row 1 ("It **does not exist**") and FR-GE-8's own note; row 5 says routing is on "deployment/**agent**/project signals" — contradicting FR-GE-3's re-keyed preference>surface>shape with agent-presence *never* a signal. (Also reconcile the §0.1 line-ref `cli.py:1260-1262` with the verified `1258-1260`.) | The gap table is the first thing an implementer reads after the problem statement; two of its six rows assert the exact claims the planning pass falsified. Neither R1 nor R2 caught the internal contradiction. | §1 Gap table, rows 5–6; §0.1 phantom-audit bullet | Doc lint: no body sentence asserts a deployment-mode/agent-detection capability; grep "capability exists" and "agent" in §1 against §0 D1. |
| R3-F4 | Interfaces | medium | FR-GE-11/11a: state that the promoted module's transcript persistence **preserves the transcript contract** the observability UX consumes — path convention (`.startd8/kickoff-panel/<session_id>.json`, FR-UX-1), schema (`KICKOFF_PANEL_FACILITATION_DESIGN.md` §6), and **round-by-round incremental write cadence** (FR-UX-17 live-follow polls-and-diffs the file as rounds land) — or explicitly version the contract and update the UX doc in the same change. | FR-GE-11 references the UX doc for *rendering*, but the re-route through the safe-write floor (FR-GE-11a/13) can silently change path, atomicity granularity, or write cadence; an end-of-session atomic write would kill FR-UX-17 live-follow even though every stated requirement here still passes. Cross-doc interface, unowned by either doc. | §2 FR-GE-11 (contract clause) + FR-GE-11a | Test: during a promoted-module run, the transcript file exists at the contract path and gains rounds incrementally; the UX viewer's FR-UX-3/FR-UX-17 fixtures pass against floor-written output. |
| R3-F5 | Architecture | medium | FR-GE-7: enumerate the **surfaces the metric covers** — CLI groups/verbs, the MCP `startd8_concierge` action enum, TUI, and the served UI — and state the retirement/alias story for the MCP action vocabulary (parent FR-10 *as amended* requires the alias window to cover the MCP action enum, not just CLI names). If MCP is deliberately out of scope for v-next, say so with rationale. | "One entry point / one vocabulary" measured only at the CLI leaves a second live vocabulary (MCP actions named after the retired metaphors) that the metric cannot see; the parent already learned this lesson (parent Appendix A, R1-F2). | §2 FR-GE-7, after the "honest success metric" sentence | Audit: the five retired metaphor names appear in no user-facing vocabulary across CLI help, MCP tool/action names+descriptions, TUI labels, and served-UI text at the M1/M2 exit gate. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R2-F1: the tension tagging schema is the only way FR-GE-12's test escapes prose-matching; strongly endorse.
- R2-F3: correct that the ladder needs a semantic contract — R3-F2 extends it with the falsy-fall-through defect that makes the contract urgent.
- R2-F5: the cloud download format question is real; note it should resolve to "byte-identical to the local safe-write output" to keep FR-GE-2's same-input guarantee.
- R1-F9: version drift; still unfixed as of this round (header v0.3, footer narrates v0.2, plan Tracks v0.2).
- R1-F11: the engaged-then-disengaged residue case is the SOTTO test that matters.

---

#### Review Round R2 — claude-sonnet-4-6 — 2026-07-04

- **Reviewer**: claude-sonnet-4-6
- **Date**: 2026-07-04 18:30:00 UTC
- **Scope**: Second-pass requirements review (F-prefix); focused on operationalization gaps, acceptance-criterion completeness, and cross-cutting issues R1 missed. R1 covered routing edges, safe-write coverage, cloud cost/abuse, version drift, and FR-GE-14 ratification well. R2 lens: what makes the stated requirements untestable or ambiguous once implementation begins.

##### Executive summary

- FR-GE-12's anti-smoothing test is currently untestable: "named tensions" has no naming/tagging schema; prose-match cannot distinguish a preserved tension from one paraphrased away.
- FR-GE-6's "no new engine" invariant has no enforcement mechanism stated in the requirements.
- FR-GE-3's "reused verbatim" routing ladder is a hidden copy dependency; the requirement should pin the semantics, not the source reference.
- FR-GE-5's "Deepen is optional" has no stated early-exit / skip guarantee for a user who enters Deepen then abandons.
- FR-GE-8's cloud "download-and-write-locally" path is underspecified: what format are downloaded inputs, and how does local write honor FR-GE-13 when the SDK is not the writer?
- H3 cost tracking in FR-GE-10 is asserted but the scope (per-round, session total, budget gate behavior on exceed) is not bounded.

##### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Validation | high | FR-GE-12: add a **tension naming/tagging schema** requirement — the anti-smoothing test ("named raw-round tensions must be present in the synthesis") requires a machine-checkable tag or structured field in the raw-round output so the assertion is not prose-matching. Without it, the test cannot distinguish a tension preserved from one paraphrased away. | "Named raw-round tensions" implies each tension has an identity that survives into the synthesis; without a schema, the test is subjective and will not pass CI. | §2 FR-GE-12, add an acceptance-criteria clause | Test: a facilitation run with a tagged tension (`tension_id: T1`) produces a synthesis where `T1` appears as an explicit open item, not resolved; CI asserts this structurally, not by prose search. |
| R2-F2 | Architecture | high | FR-GE-6 ("no new extractor/generator/writer/readiness computation"): add a **CI-enforceable criterion** — a static check that no new class or function matching the prohibited patterns is introduced in the guided layer. The anti-principle is currently an assertion, not a constraint. | FR-GE-6 is the key anti-sprawl backstop for the kernel; "no new engine" stated without enforcement is a soft intention, not a hard requirement. The M2 detangle is the riskiest window for accidental introduction. | §2 FR-GE-6, add an enforcement clause | CI gate: a AST/grep check on the guided-layer modules fails if a new extractor/generator/writer/readiness pattern appears; the check is part of the M2 exit gate. |
| R2-F3 | Interfaces | medium | FR-GE-3: replace "reused verbatim from `concierge_agent.py:59-75`" with a **semantic contract** for the routing ladder (enumerate the four levels: explicit-flag > project-config > global-config > default-quiet; enumerate what each level means for the offer decision). The source reference is a copy dependency, not a specification. | If `concierge_agent.py` changes, FR-GE-3 changes silently. The routing logic is a user-visible guarantee; it should be expressed as a requirement, with the current implementation as the reference, not the definition. | §2 FR-GE-3, precedence list | Test: the four-level ladder semantics are verified by a contract test that does not import `concierge_agent.py`; the test is owned by the guided-experience routing seam. |
| R2-F4 | Interfaces | medium | FR-GE-5: add an explicit **"Deepen skip / early-exit" guarantee** — a user who enters the Deepen phase and abandons before completion exits cleanly with Guide-phase outputs intact, no partial transcript committed, and no kernel-visible residue. | FR-GE-5 marks Deepen as optional but does not address the mid-flow abandonment case; FR-GE-1 (byte-identical) and FR-GE-13 (atomic writes) imply this, but the implication is not stated, leaving implementers without a clear contract for the error/cancel path. | §2 FR-GE-5 'Deepen (optional)' clause | Test: a Deepen session interrupted (user Ctrl-C or explicit skip) leaves Guide outputs unchanged and the safe-write store in a clean state; kernel outputs after abort are byte-identical to Guide-only run. |
| R2-F5 | Data | medium | FR-GE-8: specify the **cloud "download" artifact format** — what does a cloud user download when they "download produced inputs and write locally"? The requirement must state the format (e.g. the same YAML/JSON files the local safe-write floor would produce) so the local write path is unambiguous. | "Human downloads produced inputs, writes locally" presupposes a download format; if it is not the same files as the local write path, a user cannot feed them to the kernel without conversion, violating the "same input a BYO-agent user would author" guarantee in FR-GE-2. | §2 FR-GE-8 'cloud deployment' clause | Test: a file downloaded from the cloud Deepen-view, written to the local `.startd8/` directory, passes kernel `assess` with the same result as a locally produced file. |
| R2-F6 | Validation | medium | FR-GE-10 H3: scope the cost-tracking requirement — state what "wired end-to-end" means: (a) per-round cost is logged, (b) session total is surfaced in the Deepen output, (c) a configured budget cap halts the session (vs. warns vs. is advisory-only), and (d) the budget gate is checked before each LLM call, not after. | H3 is currently "real per-call spend, budget-gated" — this does not specify what "gated" means (hard halt? warning? advisory?) or at what granularity cost is tracked and surfaced. Implementers will produce different interpretations. | §2 FR-GE-10 H3 bullet | Test: (a) a session with budget cap N is halted before call K+1 when cumulative cost exceeds N; (b) the session transcript includes per-round and total cost; (c) the halt is hard (no LLM call is made after cap breach). |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F7 | Risks | low | FR-GE-7: the "five metaphor names retired from user-facing vocabulary" claim needs an explicit scope boundary — does it cover only CLI help text and documentation, or also internal module names, log output, and error messages? Internal vocabulary leaks become user-visible in stack traces, `--verbose` output, and error messages. | 'User-facing vocabulary' is undefined; if it means only `--help` and docs, the old names survive in logs and errors and will re-emerge as a second vocabulary in practice. | §2 FR-GE-7 | Acceptance: a vocabulary audit enumerates each of the five old names; the audit passes only if none appear in CLI output (including errors, verbose, tracebacks) at the M1/M2 exit gate. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-F2: Behavioral-equivalence requirement for FR-GE-11a is the single most important acceptance criterion missing from the requirements; strongly endorse.
- R1-F3: FR-GE-11a blocked-on OQ-GE-8 is correct — the requirement as written depends on an unresolved design question; endorse.
- R1-F7: Scoping H2 halt to Deepen phase only is essential to avoid contradiction with FR-GE-3's no-gate guarantee; endorse.
- R1-F8: Cloud Deepen LLM spend under a static API key is a real security/cost gap; endorse adding a cost/abuse OQ parallel to OQ-GE-7.
- R1-F10: FR-GE-14 provenance-marking + ratification-state acceptance criterion is well-specified; endorse.
- R1-F11: SOTTO residue test (engaged-then-disengaged) is the dangerous case for FR-GE-1; endorse.

---

#### Review Round R1 — claude-opus-4-8 — 2026-07-04

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-07-04 17:40:00 UTC
- **Scope**: Independent architectural review of the requirements doc (F-prefix). Weighted per the sponsor focus file: consolidation soundness, FR-GE-11a facilitation promotion, routing/offer-not-force edges, safe-write coverage, cloud read-only scoping, and requirements↔plan / parent-v0.17 consistency. Settled items (§SETTLED 1–6 in the focus file) were NOT relitigated.

##### Sponsor focus asks (addressed first)

**Ask 1 — Consolidation soundness (FR-GE-5/6/7): does the detangle genuinely reduce sprawl, or risk re-accreting it?**
- **Summary answer:** Partial — the *surface/vocabulary/write-path* reduction is real and defensible, but the requirement under-specifies the "one write path" leg and leaves a re-accretion vector open (nothing forbids a future capability from re-adding a top-level CLI group).
- **Rationale:** FR-GE-7 credibly reduces 3 groups→1 and 5 names→1 (verified against the plan's M1/M2 merge targets). But "one write path (→1 via the safe-write floor)" is asserted as a metric without an *enforcement* clause — FR-GE-13 requires writes to ride the floor, yet nothing in the requirements makes a *new* write path a spec violation. The un-packaged script that bypasses the floor (planning row 3) is exactly how the "one write path" invariant eroded the first time; without a gate it can erode again.
- **Assumptions / conditions:** The M2 merges (concierge-UI quartet, three "what's next" projections, three chat constructors) are real and land as planned.
- **Suggested improvements:** Add a *conformance* clause to FR-GE-7/FR-GE-13 (see R1-F1) making "any write not through the safe-write floor" and "any new top-level CLI group in the kickoff domain" testable violations, so the metric is enforced, not just declared.

**Ask 2 — FR-GE-11a facilitation promotion (biggest lift): fully specified? Ordering/hardening gaps?**
- **Summary answer:** No — the promotion is specified as intent but not as an *acceptance-testable* contract; two ordering hazards and one behavior-parity gap are unaddressed.
- **Rationale:** FR-GE-11a says "promote before harden" and "route persistence through the floor," but (a) does not require **behavioral equivalence** between the promoted module and the current script (a promotion that silently changes rounds/synthesis is a regression no criterion catches); (b) OQ-GE-8 (does it need an abstraction above `StakeholderPanel.ask_all`?) is *open* yet FR-GE-11a is stated as buildable — the requirement depends on an unresolved OQ; (c) H2 "assumptions-as-gate" halts the flow, which collides with FR-GE-3's "never a gate" offer guarantee for the *guided* flow unless the gate is scoped strictly to the Deepen phase.
- **Assumptions / conditions:** `stakeholder_panel/facilitation.py` is confirmed absent (stated in §0.1) and `run_kickoff_panel.py` is the sole source of the process.
- **Suggested improvements:** See R1-F2 (behavioral-equivalence acceptance criterion + golden transcript), R1-F3 (make FR-GE-11a explicitly blocked-on OQ-GE-8 with a decision date), and R1-F7 (scope H2's halt to Deepen so it never contradicts FR-GE-3's no-gate guarantee).

**Ask 3 — Routing / offer-not-force (FR-GE-3/4) edge cases.**
- **Summary answer:** Partial — the precedence ladder is sound but two edges are unspecified: (i) a served surface *driven by an agent*, and (ii) non-interactive/CI where "one ignorable line" has no human to ignore it.
- **Rationale:** FR-GE-3 maps "served ⇒ offer" on the premise that served implies no-agent, but the focus file itself notes a served surface can be agent-driven; the requirement resolves this only via the (2) surface heuristic, which would wrongly offer. And "a wrong offer is one ignorable line, never a gate" is a human-facing guarantee that is undefined for non-interactive/CI/piped stdout invocations.
- **Assumptions / conditions:** Agent-presence remains preference-only (SETTLED-2, not relitigated).
- **Suggested improvements:** R1-F4 (define behavior when `stdout`/`stdin` is non-interactive: suppress the offer, never block); R1-F5 (state that the served-⇒-offer heuristic is *overridable* by an agent-set `--no-guided`/config, and that a served-agent context is expected to set it).

**Ask 4 — Safe-write + safety (FR-GE-13/14).**
- **Summary answer:** Mostly sound; one coverage gap — FR-GE-13 names "input files AND facilitation transcripts" but not the routing/preference writes (`build-preferences.yaml`, `~/.startd8/config.json`) the guided layer itself sets.
- **Rationale:** FR-GE-3 has the guided layer *write* preference/config files to persist `--guided`. Those writes are not enumerated under FR-GE-13's "every byte the guided experience writes," creating an ambiguity about whether config writes must also ride the floor.
- **Suggested improvements:** R1-F6 (enumerate config/preference writes explicitly under FR-GE-13, or explicitly exempt them with rationale).

**Ask 5 — Cloud read-only (FR-GE-8) + OQ-GE-7: is "download-and-write-locally" coherent?**
- **Summary answer:** Coherent as a deferral, but the *read* scope is under-bounded — "read/preview-only" cloud still serves whatever the Deepen panel produces, and Deepen can invoke an LLM with real per-call spend (FR-GE-10 H3) on a multi-tenant cloud with only a static API key.
- **Rationale:** FR-GE-8 blocks cloud-*write* but permits "Deepen-view" on cloud; FR-GE-10 H3 says the panel does real budget-gated LLM spend. On cloud with only `server/auth.py`'s static `X-API-Key` (no principal/tenancy), a read-only surface that triggers paid LLM calls is an un-metered-per-tenant cost/abuse surface, distinct from the write-trust problem OQ-GE-7 defers.
- **Suggested improvements:** R1-F8 (clarify whether cloud read-only permits *LLM-invoking* Deepen or only static preview of already-produced transcripts; if the former, add a cost/abuse OQ parallel to OQ-GE-7).

**Ask 6 — Requirements↔plan gaps / parent-v0.17 contradictions.**
- **Summary answer:** One documentation-integrity defect (version drift) and one traceability gap (FR-GE-14 has no dedicated milestone).
- **Rationale:** The requirements header is **v0.3** but its own footer, the parent-ref line, and the plan's `Tracks:` line all say **v0.2** — a reviewer cannot tell which is authoritative (see R1-F9). Separately, FR-GE-14 (never authors/decides) is mapped to "all" milestones in the plan but has no acceptance test anywhere, making the safety invariant unverifiable.
- **Suggested improvements:** R1-F9 (reconcile version to v0.3 everywhere), R1-F10 (add a provenance-marking + human-ratification acceptance criterion to FR-GE-14).

##### Numbered suggestions (F-prefix)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Architecture | high | Add an anti-re-accretion conformance clause to FR-GE-7: "It is a spec violation to introduce a new top-level CLI group in the kickoff domain, or a second user-facing vocabulary for these functions, after M1." | The 'one entry point / one vocabulary' metric is declared but not defended; without a testable prohibition the sprawl re-accretes exactly as it did before. | §2 FR-GE-7, after the 'honest success metric' sentence | Static check / test: assert `startd8 --help` exposes exactly one kickoff-domain group post-M1; CI lint fails on a new group registration. |
| R1-F2 | Validation | high | FR-GE-11a must require **behavioral equivalence** between the promoted `facilitation.py` and the current `run_kickoff_panel.py`: capture a golden transcript (fixed seed/personas) from the script and assert the promoted module reproduces round structure and named tensions. | 'Promote before harden' has no criterion that the promotion preserved behavior; a silent regression in rounds/synthesis would pass every stated check. | §2 FR-GE-11a, add an acceptance-criteria bullet | Golden-file test: run script vs promoted module on a fixed fixture; diff round count, persona outputs, and FR-GE-12 tensions. |
| R1-F3 | Risks | high | State FR-GE-11a as **blocked on OQ-GE-8** and give OQ-GE-8 a resolution owner/date; a requirement whose build shape depends on an open question is not yet buildable. | FR-GE-11a asserts the promotion target (`facilitation.py` over `StakeholderPanel`) while OQ-GE-8 openly asks whether that very abstraction is sufficient. The dependency is circular as written. | §2 FR-GE-11a and §4 OQ-GE-8 | Traceability check: FR-GE-11a's 'Depends-on' names OQ-GE-8; plan M3 does not start until OQ-GE-8 is RESOLVED. |
| R1-F4 | Interfaces | medium | FR-GE-3: specify offer behavior when the invocation is **non-interactive** (piped stdout, no TTY, CI): the offer line is *suppressed*, never blocking, and `--guided` in non-interactive mode runs without the offer prose. | 'One ignorable line, never a gate' is a human guarantee undefined for CI/pipes, where an emitted offer line becomes noise or (worse) a prompt with no responder. | §2 FR-GE-3, add a non-interactive clause | Test: run kickoff with stdin closed / stdout piped; assert no offer prose, exit unchanged, kernel bytes identical. |
| R1-F5 | Interfaces | medium | FR-GE-3: make the 'served ⇒ offer' heuristic explicitly **overridable** and document the expected agent-driven-served contract (an agent serving the UI sets `--no-guided`/config to suppress). | The focus file flags that served can be agent-driven; as written, surface-heuristic (2) wrongly offers to an agent. Precedence already lets preference win — the requirement should say so for this case. | §2 FR-GE-3, in the 'surface' clause | Test: served invocation with `--no-guided` (or config) yields no offer; precedence table documents agent-served as preference-suppressed. |
| R1-F6 | Data | medium | FR-GE-13: enumerate the guided layer's **own config/preference writes** (`build-preferences.yaml`, `~/.startd8/config.json` from FR-GE-3) — either route them through the safe-write floor or explicitly exempt them with rationale. | FR-GE-13 says 'every byte the guided experience writes' rides the floor, but the routing feature writes config files not covered by 'inputs AND transcripts'; ambiguous whether the floor applies. | §2 FR-GE-13 | Test: assert preference/config writes use the safe-write API (or a documented exemption exists and is tested for traversal safety). |
| R1-F7 | Risks | medium | FR-GE-10 H2 (assumptions-as-gate halts the flow) must be **scoped to the Deepen phase only**, so it never contradicts FR-GE-3's 'never a gate' offer guarantee for Orient/Guide. | H2 introduces a halt; FR-GE-3 guarantees the *offer* is never a gate. Without scoping, a reviewer cannot tell whether a halted assumptions-check violates the no-gate invariant. | §2 FR-GE-10, H2 clause | Test: Orient/Guide never halt on assumptions; only an explicitly-entered Deepen pass can halt, and only after the human opted in. |
| R1-F8 | Security | high | FR-GE-8: disambiguate whether cloud 'read/preview-only' permits **LLM-invoking Deepen** (real per-call spend under FR-GE-10 H3) or only static preview of already-produced transcripts. If the former, add a per-tenant cost/abuse OQ parallel to OQ-GE-7. | Cloud has only a static API key (no principal/tenancy). A read-only surface that triggers paid LLM calls is an un-metered abuse/cost surface distinct from the write-trust deferral. | §2 FR-GE-8, 'Deepen-view' clause; §4 new OQ | Test: on cloud, Deepen either (a) serves only persisted transcripts (no LLM call), or (b) is gated by a documented per-tenant budget/auth control. |
| R1-F9 | Architecture | medium | Reconcile the version: header says **v0.3**, but the footer, the parent-ref line ('tracks v0.2'), and the plan's `Tracks:` line say **v0.2**. Pick one (presumably v0.3) and update all four sites. | Version drift makes it impossible to tell which requirement set the plan tracks; the plan claims to track v0.2 while the doc is v0.3. | Header (line 3), footer (line 258+), plan `Tracks:` line | Grep for 'v0.2'/'v0.3' across both docs; assert a single authoritative version. |
| R1-F10 | Validation | medium | FR-GE-14 needs an acceptance criterion: every synthetic output carries a machine-checkable **provenance marker** and a **ratification state** (unratified by default), and the kernel refuses to consume an unratified synthetic input without explicit human confirmation. | 'Never authors or decides / human ratifies' is currently an unverifiable assertion; provenance-marked is stated but not testable. | §2 FR-GE-14 | Test: a synthetic input written by the guided layer is tagged unratified; feeding it to the kernel without ratification is refused or warned. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F11 | Risks | medium | FR-GE-1 (byte-identical-when-absent / SOTTO): add a criterion that engaging *then disengaging* the guided layer (e.g. running guided once, then `--no-guided`) leaves the kernel outputs byte-identical to never having engaged it — not just 'absent from the start'. | 'Leaves no trace when subsequently absent' is asserted but the test only obviously covers never-engaged. The dangerous case is residue (config, cached transcripts, preference files) from a prior guided run that perturbs a later kernel-only run. | §2 FR-GE-1 | Golden test: kernel-only run A; guided-then-kernel-only run B; assert A and B kernel outputs are byte-identical. |
| R1-F12 | Interfaces | low | FR-GE-9 (surface parity) should define what 'parity' means when a surface *cannot* render a phase (e.g. served UI cannot run an interactive TTY wizard step) — parity of *outcome/inputs produced*, not of interaction modality. | 'Differing only in rendering' is too strong: some phases are modality-bound. Without scoping, the parity test is either impossible or vacuous. | §2 FR-GE-9 | Test asserts the same produced inputs/artifacts across surfaces, not identical interaction steps. |
