# Kickoff Orchestrator + Quick-Win Sweep — Requirements

**Version:** 0.1
**Date:** 2026-07-03
**Status:** Draft → Building
**Owner:** neil-the-nowledgeable
**Backlog:** `../persona-drafting/PIPELINE_ENHANCEMENTS.md` (Tier 1 #1 + sweep #4/#5/#7/#10)
**Reuses:** `kickoff_experience.red_carpet.build_red_carpet_state` (ranked `next_steps` playbook),
`red_carpet_advisor` (command bank), the `persona_drafting` toolkit, `stakeholder_panel`.

> **What this is.** A guided **orchestrator** that turns the three parallel persona-drafting siblings +
> the `$0` cascade into **one legible greenfield path**, plus a **quick-win sweep** hardening the CLIs.
> The orchestrator is **read-only / advisory** (a map, not an auto-runner) — it renders the advisor's
> already-computed ranked playbook as a cost-labeled, ordered walkthrough. It does **not** spend, write,
> or auto-approve; execution of each step stays the human's explicit act (propose-confirm floor).

---

## 1. Problem Statement

All three siblings are built (`startd8 panel` / `requirements` / `screens`) on the shared toolkit, plus
`startd8 generate …`. But they are **disconnected**: the advisor (FR-MS-8) *points* at individual
commands; nothing presents the whole path as one guided flow, and the CLIs have leaked-session and
missing-`--json` gaps + duplicated paid-pass boilerplate.

## 2. Guiding Principles

- **P1 — Orchestrator is a map, not a driver.** It renders the ranked path (read-only, `$0`); it never
  spends, writes, or auto-runs a step. Execution is the human's explicit command (Concierge/propose-
  confirm floor). An `--execute` driver is explicitly **out of scope** for v1 (NR-KO-1).
- **P2 — Reuse the advisor's computed state.** The ranked `next_steps` playbook already exists in
  `build_red_carpet_state`; the orchestrator renders it, it does not recompute a parallel plan.
- **P3 — Quick wins are behavior-preserving.** The sweep adds `--json`, GC, and a toolkit extraction
  without changing existing command semantics (the built capabilities' tests stay green).

## 3. Requirements

### A. The orchestrator (`startd8 kickoff plan` / `next`)

- **FR-KO-1 — `startd8 kickoff plan` guided greenfield walkthrough.** From `build_red_carpet_state`,
  render: (a) a **"you are here"** header (`next_stage`, `cascade_offerable`, `unmet_gates`,
  `readiness_score`); (b) the ranked `next_steps` as a **numbered walkthrough**, each showing its
  stage, title, one-line detail, the **exact command**, and a **cost tag** derived from the command
  (`$0` deterministic / `paid` role-or-interview / `gate` human approval). `--json` emits the whole
  structure for scripting. A sibling **`startd8 kickoff next`** prints just the single top-ranked
  action (for scripting / "what do I do now?"). Read-only, `$0`, never spends.

### B. Quick-win sweep

- **FR-KO-2 — Wire session GC into the persona-drafting CLIs.** `startd8 requirements elicit` and
  `startd8 screens suggest` call the toolkit `JsonSessionStore.gc()` after staging, so old sessions do
  not leak (bounded to a keep-limit).
- **FR-KO-3 — `--json` across the loop commands.** Add `--json` to `requirements`
  `synthesize`/`review`/`approve` and `screens` `review`/`approve` (parity with `elicit`/`suggest`),
  emitting a structured result so the loop is scriptable / agentic-surface-drivable.
- **FR-KO-4 — Extract the paid-pass boilerplate into the toolkit.** A single
  `persona_drafting.run_paid_pass(project_root, *, roster_rel, run, model=None)` encapsulates load-roster
  → validate → build `StakeholderPanel` → `asyncio.run(run(panel))` → `close`, raising a typed
  `PaidPassError(kind)` (`no_roster` / `invalid_roster` / `failed`). `cli_requirements` and `cli_screens`
  both re-express their `_run_paid_pass` on it (behavior-preserving; exit-code mapping preserved).
- **FR-KO-5 — Capability-index entries.** Add Requirements Panel + Manifest Suggester to
  `docs/capability-index/` so they are discoverable via the manifest / agent card / MCP surface.

## 4. Non-Requirements

- **NR-KO-1 — No `--execute` driver in v1.** The orchestrator does not run steps, spend, or write — it
  is a read-only map. Driving the `$0` steps (and stopping at paid/human gates) is a deliberate later
  increment.
- **NR-KO-2 — No unified paid session yet.** Consolidating the 3 role passes into one panel/session
  (backlog Tier 1 #2) is out of scope here; the sweep only DRYs the per-CLI boilerplate (FR-KO-4).
- **NR-KO-3 — No new advisor logic.** The orchestrator renders `next_steps`; it does not add advisories
  or change the playbook/ranking.
- **NR-KO-4 — No behavior change to shipped commands.** The sweep is additive (`--json`, GC) + a
  behavior-preserving refactor (FR-KO-4).

## 5. Validation Strategy

- **FR-KO-1:** a fixture project at various states (greenfield / offerable) renders the expected ordered
  steps + cost tags; `--json` round-trips; `next` == the top step; the command spends/writes nothing.
- **FR-KO-2:** after N+ elicit/suggest runs, the session dir is bounded to the keep-limit.
- **FR-KO-3:** each command's `--json` emits valid JSON with the documented keys.
- **FR-KO-4:** the built capabilities' tests stay green; a test asserts both CLIs route through
  `run_paid_pass` and that `PaidPassError` kinds map to the right exit codes.

---

*v0.1 — Draft. Orchestrator = a read-only guided map over the advisor's existing ranked playbook (P1);
the sweep DRYs + hardens the sibling CLIs. `--execute` and the unified paid session are explicit
follow-ups.*
