# Guided Experience — Requirements

**Version:** 0.3 (Post lessons-learned hardening — ready for CRP)
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
  the three CLI groups are exactly `kickoff`/`concierge`/`panel` (`cli.py:1260-1262`,
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
| Routing / "which experience" | Ad-hoc; no detection of agent-present vs. standalone/cloud | New: offer-not-force routing on deployment/agent/project signals |
| Deployment (cloud/standalone) | Deployment-mode capability exists; guided experience not wired as the no-agent surface | New: the guided experience is the primary surface when no agent is present |

---

## 2. Requirements

### The optional layer

- **FR-GE-1 — Optional layer over the kernel (SOTTO).** The guided experience is an
  **additive, opt-in layer** over the kernel. The kernel works fully and
  **byte-identically without it**; engaging it leaves no trace in the kernel's
  outputs when subsequently absent. The kernel never depends on the guided layer.

- **FR-GE-2 — Available but not required; complement not substitute.** The guided
  experience is **offered, never forced**. A BYO-agent user is never pushed into it;
  a no-agent user is never left without it. It **never replaces** the kernel — every
  input it helps produce is the same input a BYO-agent user would author.

### Routing — "meet the user where they are"

- **FR-GE-3 — Offer-not-force routing (re-keyed, v0.2).** The SDK decides *whether to
  offer* the guided experience from cheap signals, in this precedence (the
  `concierge_agent.py:59-75` ladder reused verbatim): **(1) explicit preference** —
  `--guided/--no-guided` flag > per-project `build-preferences.yaml` > global
  `~/.startd8/config.json` > default; **(2) surface** — a served/TUI invocation
  implies no-agent ⇒ offer; **(3) project-shape** — `build_assess` greenfield-blank
  ⇒ stronger offer, rich-brownfield ⇒ quieter. The result is an *offer*, never a
  forced path; default bias quiet (a wrong offer is one ignorable line, never a
  gate). **Not a signal:** "presence of a driving agent" is **not detected** — a CLI
  human with their own agent and a standalone human are byte-identical to the
  process (planning D1). Agent-presence is expressed only through the explicit
  preference, never inferred.

- **FR-GE-4 — Explicit override always wins.** A user can always force-on
  (`--guided`) or force-off (`--no-guided`) regardless of the detected signals.
  Detection is a convenience, not an authority.

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

- **FR-GE-6 — Over the SAME kernel; no new engine.** The guided experience adds
  **sequencing, presentation, and prompts only**. It reuses the kernel verbs
  (`survey`/`instantiate`/`assess`/`derive`) and the safe-write floor; it introduces
  **no new extractor, generator, writer, or readiness computation**. (Anti-principle:
  the guided layer is orchestration, not a second implementation.)

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

- **FR-GE-9 — Surface parity across CLI / TUI / served.** The same guided experience
  is reachable from CLI, TUI, and a served (web) surface, differing only in
  rendering. Cross-surface parity is a test requirement.

### The facilitation panel (hardened)

- **FR-GE-10 — Facilitation hardening (FR-13c H1/H2/H3).** The discovery/facilitation
  phase carries the parent hardening: **H1** artifact-grounding fidelity (ground on
  the real system, not just a schema/description), **H2** assumptions-check-as-gate
  (halt + surface "validate the premise" on ≥N high-impact/low-confidence
  assumptions), **H3** cost tracking (real per-call spend, budget-gated).

- **FR-GE-11a — Promote the facilitation process into the package, then harden
  (v0.2, planning D2/D8).** The facilitated multi-round process currently exists
  **only** as an un-packaged, un-tested script (`scripts/run_kickoff_panel.py`, 438
  LOC) whose transcript writes **bypass the safe-write floor**. Before FR-GE-10/11/12
  can hold, the orchestration must be **promoted into `stakeholder_panel/
  facilitation.py`** — built over the existing `StakeholderPanel`/roster/guards, with
  persistence routed through `concierge/safe_write.py` — so it is importable,
  testable, and confined. Hardening (H1/H2/H3, transcript persistence, anti-smoothing)
  applies to the *promoted* module, not the script.

- **FR-GE-11 — Persist raw per-round transcripts (R1-F6).** The facilitation phase
  **persists the raw per-round persona outputs** as the human-validation substrate
  for the LLM synthesizer, distinct from the synthesized register. This is a
  requirement (the value case relies on it), rendered by the observability UX
  (`KICKOFF_PANEL_OBSERVABILITY_UX_REQUIREMENTS.md` — reference, not duplicated here).

- **FR-GE-12 — Anti-smoothing is a requirement, not a behavior (R2-F7).** The
  synthesizer **must preserve open tensions** — a cross-role disagreement present in
  the raw rounds must appear in the synthesis as an explicit open item, never
  resolved into false consensus. Testable: named raw-round tensions must be present
  in the synthesis output.

### Safety

- **FR-GE-13 — All writes ride the kernel safe-write floor (FR-7 / R3-F4).** Every
  byte the guided experience writes — input files AND facilitation transcripts —
  goes through the kernel's **confined, human-privilege safe-write floor** (no
  traversal/symlink escape, atomic). Over any LLM-invoked surface it is
  read/preview-only; the human/CLI is the sole writer.

- **FR-GE-14 — Produces inputs for human ratification; never authors or decides.**
  The guided experience helps a human *produce and judge* inputs. It never authors
  real value content (bucket 4) and never makes a decision the human should make;
  every synthetic output is provenance-marked and human-ratified.

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

_OQ-GE-1 through GE-6 resolved by the planning pass (§0). Remaining:_

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
- **OQ-GE-8 (NEW) — Facilitation promotion scope.** Promoting `run_kickoff_panel.py`
  (438 LOC) into `stakeholder_panel/facilitation.py` (FR-GE-11a): does the promoted
  module reuse `StakeholderPanel.ask_all` directly, or does the multi-round/
  cross-pollination/synthesis logic need its own abstraction above it? Sizing the
  biggest lift.

---

*v0.2 — Post-planning self-reflective update. 5 requirements corrected (FR-GE-3
routing re-keyed, FR-GE-5 deterministic-first, FR-GE-8 cloud split, FR-GE-7
success-metric reframed, gap-table facilitation baseline), 1 added (FR-GE-11a
promote-then-harden), 6 OQs resolved, 2 new (cloud-write, promotion scope). The
consolidation survives — but "net-reduce modules" was the wrong headline; the real
win is one entry point / one vocabulary / one write path, and the detection signal I
assumed (SDK deployment-mode self-awareness) does not exist.*
