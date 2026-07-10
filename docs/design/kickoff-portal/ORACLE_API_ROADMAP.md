# Oracle-as-API Roadmap — turning the single AgenticView oracle into a first-class API surface

> **Context.** The Workbook↔cockpit convergence made `AgenticView` (`build_agentic_view`) the
> **single oracle** for kickoff status — one read-model that folds `KickoffState` + the FR-1
> snapshot + the VIPP inbox/dispositions + stakeholder answers + roster + readiness/next-action, and
> feeds the Grafana cockpit, the terminal (`kickoff cockpit`), and the readout export. This doc tracks
> the value program that promotes that oracle from an internal object into an **addressable API**
> (CLI · JSON · MCP), plus the downstream activation/close-the-loop work it unlocks.
>
> **Scope discipline (CLAUDE.md bucket rule).** Everything here is bucket-1 **application** work over
> the deterministic $0 read-model. No new LLM generation is introduced; the VIPP apply path reuses the
> existing `run_vipp_negotiate` → `apply_dispositions` envelope flow. The oracle is read-only by
> default; the only state-changing affordance (`proposals --apply`) is an explicit, gated opt-in.

## Status at a glance

| Tier | Item | State |
|------|------|-------|
| **A1** | `kickoff status [--json]` + `kickoff proposals [--json] [--apply --yes]` | ✅ Shipped (`aa658ebb`) |
| **A2** | `AgenticView.to_dict()` + `kickoff_status()` callable + `readout --format json` | ✅ Shipped (`aa658ebb`) |
| **C1** | `startd8_kickoff_status` MCP tool (read-only, `startd8.kickoff.status.v1`) | ✅ Shipped (`869d5dc5`) |
| **B** | Activation surface — `kickoff check` gate + `kickoff.activation.*` gauges + activation ledger | ✅ Shipped |
| C2/C3 | Decision-log + retrospective built on the oracle payload | ⏳ Planned |
| **D** | Close-the-loop — momentum (readiness slope) + highest-leverage batch nudge | ✅ Shipped |
| E | Promotion dividend — oracle payload as the exemplar/promotion input | ⏳ Planned |

---

## Tier A — Oracle as API (SHIPPED)

The oracle stops being reachable only through the Grafana board or the interactive cockpit; it becomes
a stable, versioned payload any surface can consume.

- **A1 · CLI verbs.**
  - `kickoff status` — compact human summary (readiness %, attention counts, next action, snapshot
    at-a-glance + cost line, proposal count); `--json` emits the full oracle payload.
  - `kickoff proposals` — lists the VIPP inbox (id, kind, target, base); `--json` for machine use;
    `--apply --yes` runs `run_vipp_negotiate` → `apply_dispositions(confirm=…)` to apply envelope
    dispositions. Apply is **opt-in and gated** (`--yes`), never the default.
- **A2 · The payload contract.**
  - `AgenticView.to_dict()` → `schema: startd8.kickoff.status.v1` — readiness, attention counts,
    field count, next action, snapshot (+ at-a-glance + cost line), proposals, pipeline summary,
    panel answers, roster size, stakeholder summary, assistant/proposals hints.
  - `kickoff_status(project_root) -> dict` — module-level callable = `build_agentic_view(root).to_dict()`;
    the one function every non-Grafana consumer calls.
  - `kickoff readout --format md|html|json` — the JSON format returns the same oracle payload, so the
    exported readout and the live status can never drift.

**Design guarantees.** One schema string (`startd8.kickoff.status.v1`) is the version handle; the
payload is JSON-serializable end-to-end (verified by test); every field degrades safely when a store
is absent (no snapshot → `has_snapshot:false`, empty inbox → `proposals:[]`).

## Tier C1 — Oracle over MCP (SHIPPED)

`startd8_kickoff_status` exposes `kickoff_status(project_root)` as an MCP tool, mirroring
`startd8_concierge`: annotated `readOnlyHint=True` / `destructiveHint=False`, returns the
`startd8.kickoff.status.v1` JSON. This puts the Workbook oracle inside the same agent-callable surface
as the concierge, at **$0** and with **no write affordance** — an agent can *observe* kickoff readiness
but the MCP floor forbids it mutating state (the read-only floor is pinned by `test_16_kickoff_status`,
alongside the concierge floor guard in `test_15`).

---

## Tier B — Activation surface (SHIPPED)

The oracle already computes readiness %, attention counts, and a next action. Tier B turns those into
**push**, not just pull — a portable gate, stack-based alerting, and an audit trail:

- **`kickoff check` — the alert as a portable CLI gate.** `evaluate_activation(status)` scores the
  oracle payload against activation conditions — `no_inputs`, `blocked_fields` (severity *blocked*),
  `review_backlog`, `pending_proposals`, `readiness_below_target` — and yields an overall severity +
  **exit code** (`0` ok · `1` attention · `3` blocked; the codebase's existing convention). So CI/cron
  can gate on kickoff readiness *without* the Grafana stack. `--json` emits the
  `startd8.kickoff.activation.v1` verdict; `--min-readiness N` sets the target; `--record` also writes
  a ledger row. (`src/startd8/kickoff_experience/activation.py`, `kickoff check`.)
- **Grafana alerting on the same conditions.** `kickoff check` emits two gauges via the existing OTel
  Meter → Mimir path — `kickoff.activation.open` (count of firing conditions) and
  `kickoff.activation.severity` (0/1/2). A Grafana alert can fire on `kickoff_activation_open > 0` or
  `kickoff_activation_severity >= 2` — the *same* conditions the portable gate evaluates, so the two
  paths never disagree. (Live-verified in Mimir: `kickoff_activation_open{project=…}`.)
- **Activation ledger — how a project got ready.** `ActivationLedger` appends a row to
  `.startd8/kickoff/activation-ledger.jsonl` **only when the oracle signature changes** (readiness
  crossing, block/unblock, proposals applied, snapshot promotion) — a clean event stream, not a poll
  log. `kickoff ledger [--json]` renders it. It is the only writer in Tier B and only ever appends;
  it never touches kickoff inputs.

## Tier C2/C3 — Decision log + retrospective (PLANNED)

Build on the C1 payload: a **decision log** (what was proposed, what was applied/declined, by whom) and
a **retrospective view** that diffs the first snapshot against the ready-state snapshot — both are pure
reads over the oracle + VIPP dispositions, no new generation.

## Tier D — Close the loop (SHIPPED)

The oracle now feeds its *own history* back into the recommendation, so the cockpit **directs**
progress instead of only reporting it — the observe→act loop the oracle previously only half-served.
Both halves are pure, deterministic reads over data the oracle already holds
(`src/startd8/kickoff_experience/momentum.py`), and neither mutates the byte-stable
`ranking.next_action` (the web/TUI parity contract) — they *enrich* alongside it.

- **Momentum (the readiness slope).** `readiness_trend(ledger_entries)` reads the Tier-B activation
  ledger's readiness observations and returns **rising / stalled / falling** with a human summary
  ("readiness stalled at 60%"). This is where the Tier-B ledger pays off: `kickoff check --record`
  writes the transitions, and Tier-D reads them back as slope. Closed loop.
- **Leverage (the highest-leverage batch).** `leverage_groups(state)` groups the not-yet-ok fields by
  their class (value-path head) and ranks the classes by how many fields resolving each would clear.
  The top class is the highest-leverage next batch. `leverage_nudge()` combines it with momentum into
  one line: *"resolve `conventions` — clears 3 fields · readiness stalled at 60%"*.
- **Surfaced everywhere via the oracle.** `AgenticView` folds the ledger (`ledger_entries`) and
  `to_dict()` gains additive `momentum` / `leverage` / `leverage_nudge` keys (same
  `startd8.kickoff.status.v1` schema — additive, so CLI/JSON/MCP/readout all get it for free).
  `kickoff status` prints the leverage nudge + a 📈/⏸️/📉 momentum line.

## Tier E — Promotion dividend (PLANNED)

Use the oracle payload as the **exemplar/promotion input**: a project that reached ready-state with a
clean snapshot + applied-proposal history is a candidate template. The `startd8.kickoff.status.v1`
payload is already the structured fingerprint this would key on.

---

## Invariants to preserve across all tiers

1. **One oracle, one schema.** Every surface (CLI, JSON, MCP, Grafana, readout) reads
   `build_agentic_view` → `to_dict()`; never re-derive status from raw stores. Bump the `schema`
   string on any breaking payload change; keep the version-degrade contract.
2. **Read-only by default.** The only writer is the explicit, `--yes`-gated `proposals --apply`
   (envelope flow). The MCP tool has **no** apply affordance and stays behind the read-only floor.
3. **$0 / bucket-1.** No tier introduces new LLM generation. Apply reuses the existing VIPP path.
4. **Degrade, don't crash.** Absent stores yield empty/`false` fields, never exceptions.

## Evidence

- Code: `src/startd8/kickoff_experience/agentic_view.py` (`to_dict`, `kickoff_status`, momentum fold),
  `src/startd8/kickoff_experience/activation.py` (`evaluate_activation`, `ActivationLedger`),
  `src/startd8/kickoff_experience/momentum.py` (`readiness_trend`, `leverage_groups`, `leverage_nudge`),
  `src/startd8/kickoff_experience/metrics.py` (`record_activation`),
  `src/startd8/cli_concierge.py` (`kickoff status|proposals|readout|check|ledger`),
  `mcp/startd8-mcp-builder/startd8_mcp.py` (`startd8_kickoff_status`).
- Tests: `tests/unit/kickoff_experience/test_status_proposals_cli.py`,
  `tests/unit/kickoff_experience/test_agentic_view.py`,
  `tests/unit/kickoff_experience/test_activation.py`,
  `tests/unit/kickoff_experience/test_check_ledger_cli.py`,
  `tests/unit/kickoff_experience/test_momentum.py`,
  `tests/unit/kickoff_experience/test_momentum_oracle.py`,
  `mcp/startd8-mcp-builder/tests/test_16_kickoff_status.py`.
- Commits: `aa658ebb` (A1+A2), `869d5dc5` (C1), `e55ff4d6` (Tier B), Tier D (this change).
