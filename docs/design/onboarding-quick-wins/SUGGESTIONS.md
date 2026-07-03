# Onboarding Value & Quick-Wins — Suggestions

**Date:** 2026-07-03
**Origin:** post-merge review of `startd8 project init` (PR #85) and the surrounding VIPP / Concierge
onboarding surface.
**Status:** Backlog. The **Top 3** are specced in [`REQUIREMENTS.md`](./REQUIREMENTS.md) and being
implemented on `feat/onboarding-quick-wins`.

> Grounding note: two claims below were verified against the code before writing. (a) `vipp negotiate`
> exits **2** on a missing inbox (`cli_vipp.py:110`). (b) The capability-index **derived artifacts are
> stale** — `agent-card.json` lists onboarding caps but not `startd8.project.init`; `mcp-tools.json`
> lists only MCP *tools*, and `project.init` is CLI-only (so it belongs in the agent card, **not**
> mcp-tools — a scope correction vs the original phrasing).

---

## Top 3 — highest value, hours not days

### 1. Fix the `init → negotiate` UX cliff (OQ-8)
`project init` makes "inbox-*ready* but no file" the normal state, but `vipp negotiate` still exits
**2** ("no proposals-inbox.json") when it finds no inbox — so the exact happy path we print as the
`next:` step **errors on a clean project**. Teach negotiate to treat a missing inbox on an
**opted-in** project as a clean **exit 0** ("inbox-ready; nothing to negotiate yet"), while keeping
exit 2 for a genuinely **not-opted-in** project (real mis-use signal).
*Value: high · Effort: trivial.*

### 2. Sync the capability-index derived artifacts
`startd8.project.init` is in `startd8.sdk.capabilities.yaml` but absent from `agent-card.json`, so
A2A/agent consumers reading the card can't discover it. Add the skill entry to the agent card.
`mcp-tools.json` correctly should **not** list it (no MCP tool exposes it).
*Value: medium (discoverability) · Effort: trivial.*

### 3. Harden `vipp.context.ensure_posting` at the source (scoped to VIPP)
`ensure_posting` has no confinement guard — it `mkdir`s + atomic-writes through a symlinked root
before any check. In `project init` we guard up front, but other callers (`vipp init`, `vipp
negotiate`) still have the hole. Since VIPP's write path (`vipp_seam`) **already** rejects symlinked
roots and its tests already `realpath`, moving the guard into `vipp.context.ensure_posting` is
consistent and low-risk. **FDE is explicitly out of scope**: it has no confined-write system anywhere
and its tests use raw tmp paths — hardening `fde.context.ensure_posting` would be inconsistent and
break them; that needs a separate "introduce confinement to FDE" design.
*Value: medium (closes a bug class) · Effort: small.*

---

## Functional quick wins (deferred backlog)

- **`startd8 onboard` one-shot** (or `project init --then negotiate`): collapse the 3-command flow
  (`init → negotiate → apply`) into a guided path — run init, and when an inbox was produced, drop
  into a negotiate *preview*.
- **`--proposals -` (stdin):** let agents pipe an authored proposal set instead of writing a temp
  file. `_load_proposals_file` already parses YAML/JSON text; accepting `-` is a few lines.
- **Surface cascade readiness in the init report:** `detect_shape` already folds in `concierge.assess`
  (which computes the `$0`-cascade readiness). Print "inbox-ready; cascade 3/4 ready (missing:
  conventions)" to turn a bare verdict into a next step.
- **Reconsider `not_greenfield` exit code:** `project init --instantiate` on a brownfield produces
  nothing and exits 0 — a user who explicitly asked to instantiate gets silent success. Consider exit
  2 or a louder hint.

## Architectural quick wins (deferred backlog)

- **Structured propose result:** `make_propose_handler` only returns a human string; init detects
  success via a buffer-length delta (a workaround). A first-class `try_propose() -> {ok, action,
  error}` would serve both the LLM tool and programmatic callers and delete the workaround.
- **Unify the three inbox producers:** Concierge chat, the TTY command, and `project init` all write
  the same inbox. Envelope *parity* is CI-guarded, but the *entry points* aren't unified.
- **Align `detect_shape`'s contract literal** to `CONVENTION_PATHS["schema"]` instead of the hardcoded
  `"prisma/schema.prisma"` (same value today; prevents silent drift).

## Operational / observability (deferred backlog)

- **Emit one onboarding event from `project init`** (`shape.verdict`, produced-vs-ready, exit) → an
  onboarding funnel, consistent with the existing `EV_PROPOSAL_MADE` telemetry.
- **Feed init friction into the Concierge friction log** (which is already treated as a role-spec
  source), closing the learning loop on `no_gap` / `not_greenfield`.

## Low-hanging fruit / test polish (deferred backlog)

- CLI-level tests for exit-3 (blocked), `--with-fde`, and the `not_greenfield` exit code.
- Ship an example `proposals.yaml` + a usage snippet (the `--proposals` grammar is code-only today).
- Extend `--check` to instantiated-package drift (reuse `concierge.writes.compute_drift`), not just
  the init scaffold.
