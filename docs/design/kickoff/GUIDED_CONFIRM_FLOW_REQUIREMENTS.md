# Guided Multi-Field Confirm Flow — Requirements

**Version:** 0.3 (Post lessons-learned hardening)
**Date:** 2026-07-06
**Status:** Draft
**Owner:** kickoff kernel (`src/startd8/concierge/`, `src/startd8/cli_concierge.py`)

---

## 0. Planning Insights (Self-Reflective Update)

> This is the deferred **NR-1** from value-input confirmation (PRs #112/#113). The draft assumed we'd
> reuse the legacy red-carpet driver and treat non-TTY like the read-only `guided` flow. Planning
> (read-only investigation) corrected both.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| Reuse `run_red_carpet_driver` (`orchestrator.py`) for the loop. | It's pure-of-IO and idiomatic, but built around `WizardAction`/proposals/stall-counters/interview — heavier than a confirm walk, and it lives in the **deprecated** red-carpet surface. | **FR-8 redefined:** a *new dedicated* pure-of-IO loop in the kernel, reusing the same injected-callback idiom (`read_input`/`emit_line`), not the legacy driver. |
| Non-TTY behaves like `guided` — suppress/no-op. | `guided` is **read-only** (FR-GE-1 byte-identical), so suppression is safe there. This flow **writes**; silently no-op'ing a write verb under a pipe is dishonest. | **FR-7 redefined:** hard-**refuse** under non-TTY/`--json`, printing the scriptable single-field alternative — never a silent no-op. |
| `confirmable_fields()` already carries the prompt text. | It returns `{value_path, label, domain, widget, choices}` — **not** `grammar_help`/`value_help`. Those live on `FieldDef`. And none of the 3 confirmable fields set `value_help`. | **FR-2 refined:** reach `FieldDef` (via `default_config().field_by_value_path`) for `grammar_help`; `value_help` is optional/absent today. |
| Per-field what/why is available. | `explain_input_domain` is per-**domain** (`{label, question, who, prose}`), not per-field. A field joins to its domain via its slug. | **FR-2 refined:** show the field's *domain* what/why (the `question` one-liner), joined by slug. |
| It's obviously a flag on `kickoff confirm`. | Genuine fork: the scriptable single-shot `confirm` has a clean `--json`/TTY contract; folding an interactive loop in muddies it. Precedent: `red-carpet --wizard` is a *separate* interactive entry from scriptable verbs. | **OQ-1 (surfaced for decision):** bare `kickoff confirm` (value_path optional → guided) vs `--all` flag vs a new verb. |

**Resolved open questions:** see §4 — OQ-2..OQ-4 carry planning-informed recommendations; OQ-1 is a
product/UX fork surfaced for decision.

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied SDK lessons before CRP.

- **[Phantom-reference audit]** — verified every symbol the plan names: `confirmable_fields`/
  `confirmed_value_paths`/`build_confirm_plan`/`apply_confirm`/`_read_field_value`
  (`confirmation.py:86/69/178/230/117`), `field_by_value_path`/`FieldDef.grammar_help`
  (`manifest.py:120/62`), `explain_input_domain` → `question` + `KICKOFF_INPUT_REGISTRY[slug].ordinal`
  (`core.py:128/78`), the `_scripted_reader` test idiom (`test_chat_repl.py:27`). **Zero phantoms.**
- **[Single-source vocabulary ownership]** — the walk's per-field prompt reuses the domain `question`
  (registry) + `FieldDef.grammar_help` verbatim; **no new explanatory prose** is authored (FR-2).
- **[Prune phantom scope]** — the stale-revisit path (OQ-2), the guided TUI/web surface (NR-4), and any
  change to the confirmation core (NR-1) are kept OUT; this is a thin interactive layer over shipped
  primitives, not a re-architecture.
- **[CRP steering memory]** — least-reviewed = both new docs (v0.3 / plan v1.0). **Settled:** OQ-1 =
  bare `kickoff confirm`, OQ-4 = Enter-skip (user decisions); reuse the confirmation core unchanged;
  new dedicated loop (not the deprecated red-carpet driver); $0/no-LLM.

---

## 1. Problem Statement

Value-input confirmation shipped as a **single-field** verb: `startd8 kickoff confirm <value_path>
--value|--as-is`. To confirm all defaulted fields a user must run it once per field **and already know
each `value_path`** — undiscoverable and tedious. `kickoff assess` honestly shows "K awaiting", but
there is no interactive way to *act* on that list.

| Component | Current State | Gap |
|-----------|---------------|-----|
| `kickoff confirm <vp>` | Scriptable single field; user must know the value_path | No "walk me through the awaiting fields" experience |
| `kickoff assess` | Shows `N confirmed · K awaiting · S stale` | Read-only — surfaces the list but can't act on it |
| `confirmable_fields()` / `domain_confirmation()` | Expose the awaiting set + counts | Unused by any interactive surface |
| Interactive driver | Only the **deprecated** `red-carpet --wizard` (write-flow) | No kernel-native guided confirm |

**Target:** a $0/no-LLM interactive flow that walks the user through each **awaiting** confirmable
field — showing what it is, why it matters, and its current default — and confirms each via the
existing `build_confirm_plan`/`apply_confirm` path, persisting immediately (resumable).

## 2. Requirements

**FR-1 — Interactive guided walk over awaiting fields.** Provide a $0/no-LLM interactive flow that
iterates the **awaiting** confirmable fields (those in `confirmable_fields()` not in the ledger),
one at a time, until the user finishes or quits.

**FR-2 — Per-field context.** For each field, show: the `label`; the field's **domain** what/why (the
`explain_input_domain(slug).question` one-liner, joined by domain slug — reuse, no new prose);
`FieldDef.grammar_help` ("what to type"); the **current on-disk default** value; and, for `select`
widgets, the `choices`.

**FR-3 — Per-field actions.** At each field the user may: **enter a value** (→ `mode="set"`),
**confirm as-is** (→ `mode="as-is"`, the default is accepted unchanged), **skip** (leave it awaiting,
advance), or **quit** (end the flow). The default (Enter) action is defined in OQ-4.

**FR-4 — Reuse the confirmation path unchanged.** Every confirmation goes through
`build_confirm_plan` + `apply_confirm` (never a sentinel); the ledger, capture splice, safe-write
path, and partial-failure contract are reused verbatim (NR-1). A per-field `ConfirmError` is shown
and the field left awaiting — one bad field never aborts the whole walk.

**FR-5 — Resumable, progress persists per field.** Because each confirm persists immediately,
quitting mid-walk keeps every confirmation made so far. **Re-running only prompts fields still
awaiting** (confirmed fields are skipped); a `skip` this session leaves the field awaiting so it
reappears next run. This is the intended behavior, not a bug.

**FR-6 — Validation.** A `select` field rejects a value not in `choices` and re-prompts; a `set`
value that fails the capture round-trip is reported and re-prompted (or skipped). Reuse the
validation already in `build_confirm_plan` (`bad_value`, `capture_failed`).

**FR-7 — TTY-gated; refuse (don't no-op) when non-interactive.** The flow requires a TTY. Under
`--json`, a pipe, or a non-TTY stdin it must **refuse with a clear message** that points at the
scriptable single-field form (`kickoff confirm <value_path> --value …`) and lists the awaiting
value_paths — a write flow must never silently do nothing.

**FR-8 — $0/no-LLM; pure-of-IO loop; not the legacy driver.** No LLM. The loop is a **new dedicated**
kernel function with injected `read_input`/`emit_line`/confirm callbacks (mirroring the codebase's
pure-of-IO driver idiom) so it is unit-testable with a scripted reader — it does **not** reuse or
revive `run_red_carpet_driver`/the red-carpet surface.

**FR-9 — Honest completion summary.** On exit (finish or quit), print how many were confirmed this
session and how many remain awaiting (from `domain_confirmation`), so the user knows where they stand.

**FR-10 — Deterministic ordering.** Fields are walked in a stable order: by domain (the
`KICKOFF_INPUT_REGISTRY` ordinal), then by field within the domain.

## 3. Non-Requirements

- **NR-1** — Not modifying `build_confirm_plan`/`apply_confirm`/the ledger/`confirmable_fields`.
- **NR-2** — No LLM, no interview/drafting; human-authored values only.
- **NR-3** — Not reusing or reviving `run_red_carpet_driver` or the deprecated `red-carpet --wizard`.
- **NR-4** — CLI only; no TUI/web surface this pass.
- **NR-5** — Not re-confirming already-confirmed fields by default (skipped). Revisiting **stale**
  confirmed fields is out of scope (OQ-2).
- **NR-6** — Not touching non-confirmable (`authored`) fields.

## 4. Open Questions

> **Decisions (2026-07-06, user):** **OQ-1 → (A)** bare `kickoff confirm` (value_path optional → the
> guided walk; passing a value_path keeps the scriptable single-shot). **OQ-4 → Enter = skip.**
> OQ-2/OQ-3 recommendations below stand.

- **OQ-1 → RESOLVED (A) bare `kickoff confirm`.** Verb shape.
  - **(A) Bare `kickoff confirm` (value_path optional) → guided.** `kickoff confirm` with no
    value_path enters the walk; `kickoff confirm <vp> --value …` stays the scriptable single-shot.
    *Pro:* one discoverable verb; "confirm my stuff" just works. *Con:* one verb hosts two contracts
    (interactive vs scriptable) — must keep `--json`/non-TTY clean (FR-7 covers it).
  - **(B) `--all`/`--guided` flag on `kickoff confirm`.** Explicit opt-in flag. Similar tradeoffs to (A).
  - **(C) New sibling verb** (e.g. `kickoff confirm-all` / `kickoff review`). *Pro:* keeps `confirm`
    a clean single-shot; the interactive write flow gets its own contract (precedent: `red-carpet
    --wizard`). *Con:* a second confirm-shaped verb.
  - **Recommend (A)** — most discoverable; FR-7's non-TTY refuse keeps the scriptable contract honest.
    **Surface to the user.**
- **OQ-2 → recommend defer.** Revisit **stale** fields (confirmed but hand-edited) in the walk? MVP
  prompts only *awaiting*; a later `--include-stale` can re-offer stale ones.
- **OQ-3 → recommend refuse + list.** Non-TTY: hard-refuse (FR-7) AND print the awaiting value_paths
  so the user can script them — better than a bare error.
- **OQ-4 → RESOLVED Enter = skip.** A bare Enter skips (no write, stays awaiting); `a` = confirm
  as-is; a typed value = set; `q`/quit-words = quit. (`a`/`q` are reserved input tokens — no collision
  with the 3 current fields' valid values; a field legitimately needing those uses the scriptable
  single-shot.)

---

*v0.3 — Post lessons-learned hardening (phantom-audit 0, single-source prompt text, pruned scope, CRP
steering). Prior v0.2: FR-7/FR-8 redefined (refuse-not-no-op; new loop not the legacy driver), FR-2
refined; OQ-1/OQ-4 resolved by user (bare `kickoff confirm`, Enter-skip). Ready for CRP. Companion
`GUIDED_CONFIRM_FLOW_PLAN.md` (v1.0).*
