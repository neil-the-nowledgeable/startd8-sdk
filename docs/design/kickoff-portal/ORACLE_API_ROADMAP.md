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
| **C2/C3** | Decision-log + retrospective (`kickoff retrospective`) built on the oracle payload | ✅ Shipped |
| **C2/C3+** | Richer readout — `kickoff readout --full` (status + retrospective + activation; `startd8.kickoff.readout.v1`) | ✅ Shipped (additive; default readout unchanged) |
| **D** | Close-the-loop — momentum (readiness slope) + highest-leverage batch nudge | ✅ Shipped |
| **E** | Promotion dividend — `kickoff promote` / `exemplars` / `apply-exemplar` | ✅ Shipped |

> **Roadmap complete.** Every tier (A1 · A2 · C1 · B · D · C2/C3 · E) has shipped to `origin/main`.

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

## Tier C2/C3 — Decision log + retrospective (SHIPPED)

The "how this project got ready" story — two read-only views assembled from data the oracle already
folds (`src/startd8/kickoff_experience/retrospective.py`, `kickoff retrospective`, schema
`startd8.kickoff.retrospective.v1`):

- **Decision log (C2).** `decision_log(status)` reads the oracle payload's `pipeline.dispositions`
  (the persisted VIPP report) — what the concierge proposed and what was **adjudicated** (ACCEPT /
  REJECT / COUNTER, with the reason) — cross-referenced with the live inbox to also report what is
  still **pending**. Degrades cleanly: no dispositions ⇒ empty adjudicated set, pending still counts.
- **Retrospective (C3).** `build_retrospective(status, ledger_entries)` reconstructs the journey from
  the **Tier-B activation ledger's transition history** — readiness start→now, blockers cleared,
  proposals applied, snapshot promoted — as an ordered list of **milestones**. The ledger is exactly
  the event stream this needs, so no separate snapshot history is required (a cleaner substrate than
  the originally-envisioned first-vs-last snapshot diff). `kickoff retrospective` renders the journey
  milestones + the decision log; `--json` for tools.
- **Richer readout (`kickoff readout --full`) — SHIPPED.** The originally-deferred "one shareable
  artifact = status + how-we-got-here + what's-left" now ships behind an **additive `--full` flag**.
  `--format json --full` emits a combined `startd8.kickoff.readout.v1` payload nesting the `status` /
  `activation` / `retrospective` views (all fetched through `report.py`, none re-derived); md/html
  `--full` append "How it got here" (retrospective milestones + decision log) and "What's left" (open
  activation conditions) after the existing readout. **The default (non-`--full`) readout is byte-
  identical to before** — `readout --format json` still equals `status --json` (invariant preserved,
  `test_readout_json_matches_status`); the HTML path stays XSS-safe (every value through `html.escape`).

This is where the whole roadmap compounds: Tier-B records the transitions, Tier-D reads them as slope,
and Tier-C reads them as a narrative — all from the one oracle, no new generation.

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

## Tier E — Promotion dividend (SHIPPED)

The compounding payoff: a ready-state kickoff becomes a reusable **exemplar** so new projects start
from a proven setup instead of a blank slate. All built on the oracle
(`src/startd8/kickoff_experience/promotion.py`):

- **Eligibility.** `promotion_eligibility(status)` gates on *clean enough to promote* — readiness at
  target, zero blocked fields, zero pending proposals, has inputs. Tier-C's history is exactly what
  makes "clean" answerable.
- **Promote.** `startd8 kickoff promote` captures the project's **settled conventions** (the
  value-path→value pairs that reached `ok`) + provenance + decision summary into a portable
  `startd8.kickoff.exemplar.v1` record, saved to a cross-project registry
  (`~/.startd8/kickoff-exemplars/`, `$STARTD8_KICKOFF_EXEMPLARS_DIR` override). The id is
  content-derived, so re-promoting an unchanged project is idempotent. `--force` records a non-ready
  project anyway. `startd8 kickoff exemplars` lists the library.
- **Apply (the dividend) — the safe bridge.** `startd8 kickoff apply-exemplar <id> [target]` seeds a
  new project. Crucially it reuses the **vetted VIPP producer path** (`build_proposal` →
  `serialize_buffer`): it emits `capture` *proposals* into the target's inbox, so the target human
  reviews with `kickoff proposals` and applies through the existing confirm gate. Preview by default;
  `--emit` writes the inbox. A convention the target's manifest can't accept is skipped honestly
  (per-target validation), never forced. **No new write path**, every invariant preserved.

*This was the longest-horizon tier — and it only became clean because B/C/D landed first: eligibility
reads C's history, the exemplar captures D's settled state, and apply rides the same VIPP path the
whole system already trusts.*

---

## Refinement pass (post-E) — distill the accidental complexity, make the value self-fueling

After all tiers landed, a critical read of the accreted code found three pieces of accidental
complexity and one design gap. Fixed together, guarded by the full suite:

- **Distillation (pure refactor, zero behaviour change).** (1) All `startd8.kickoff.*` schema strings
  now live in one `schemas.py` — the CLI had drifted into re-hardcoding literals that module
  constants already defined. (2) The activation-ledger **row was an untyped contract** smeared across
  three modules (activation *wrote* keys; momentum + retrospective *read* them via raw `.get()`);
  activation now owns the row-field constants + a single `readiness_readings()`, and momentum +
  retrospective consume it — so the "readiness series from the ledger", previously implemented twice,
  is computed once. (3) `ActivationReport.severity_code` replaces a duplicated severity→code map.
- **Make it self-fueling (the design gap).** The whole B→D→C→E value chain runs on the activation
  ledger — but the ledger only filled when someone ran `kickoff check --record`, so on a normal
  project momentum / retrospective / promotion-history were **permanently dormant**. A best-effort
  `_record_transition` now fires at every state-changing write (`confirm` single/batch/guided,
  `proposals --apply`, `apply-exemplar --emit`); the ledger's dedup guard means only real transitions
  are recorded. The back half now populates passively as the user works.
- **One machine-readable surface (`report.py`).** `kickoff_report(root, view)` +
  `startd8 kickoff report` + the `startd8_kickoff_report` MCP tool put **every** read-only view
  (status / activation / retrospective / exemplars) behind ONE dispatcher — so agents get all views
  through one tool, not N, and the N views × M surfaces stop threatening N×M call sites. `report
  status` is byte-identical to `status --json` (dispatcher parity, verified).

---

## Invariants to preserve across all tiers

1. **One oracle, one schema.** Every surface (CLI, JSON, MCP, Grafana, readout) reads
   `build_agentic_view` → `to_dict()`; never re-derive status from raw stores. Schema strings live in
   `schemas.py` (one source); the machine-readable views dispatch through `report.py`. Bump the
   `schema` string on any breaking payload change; keep the version-degrade contract.
2. **Read-only by default.** The only writer is the explicit, `--yes`-gated `proposals --apply`
   (envelope flow). The MCP tool has **no** apply affordance and stays behind the read-only floor.
3. **$0 / bucket-1.** No tier introduces new LLM generation. Apply reuses the existing VIPP path.
4. **Degrade, don't crash.** Absent stores yield empty/`false` fields, never exceptions.

## Evidence

- Code: `src/startd8/kickoff_experience/schemas.py` (one home for every `startd8.kickoff.*` schema),
  `src/startd8/kickoff_experience/report.py` (`kickoff_report`, `REPORT_VIEWS` — the view dispatcher),
  `src/startd8/kickoff_experience/agentic_view.py` (`to_dict`, `kickoff_status`, momentum fold),
  `src/startd8/kickoff_experience/activation.py` (`evaluate_activation`, `ActivationLedger`, `readiness_readings`, row constants),
  `src/startd8/kickoff_experience/momentum.py` (`readiness_trend`, `leverage_groups`, `leverage_nudge`),
  `src/startd8/kickoff_experience/retrospective.py` (`decision_log`, `build_retrospective`, `kickoff_retrospective`),
  `src/startd8/kickoff_experience/promotion.py` (`promotion_eligibility`, `build_exemplar`, `ExemplarRegistry`, `apply_plan`, `emit_to_inbox`),
  `src/startd8/kickoff_experience/metrics.py` (`record_activation`),
  `src/startd8/cli_concierge.py` (`kickoff status|proposals|readout|check|ledger|retrospective|promote|exemplars|apply-exemplar|report` + `_record_transition`),
  `mcp/startd8-mcp-builder/startd8_mcp.py` (`startd8_kickoff_status`, `startd8_kickoff_report`).
- Tests: `tests/unit/kickoff_experience/test_status_proposals_cli.py`,
  `tests/unit/kickoff_experience/test_agentic_view.py`,
  `tests/unit/kickoff_experience/test_activation.py`,
  `tests/unit/kickoff_experience/test_check_ledger_cli.py`,
  `tests/unit/kickoff_experience/test_momentum.py`,
  `tests/unit/kickoff_experience/test_momentum_oracle.py`,
  `tests/unit/kickoff_experience/test_retrospective.py`,
  `tests/unit/kickoff_experience/test_promotion.py`,
  `mcp/startd8-mcp-builder/tests/test_16_kickoff_status.py`.
- Commits: `aa658ebb` (A1+A2), `869d5dc5` (C1), `e55ff4d6` (Tier B), `e680aa55` (Tier D),
  `87699721` (Tier C2/C3), Tier E (this change).
