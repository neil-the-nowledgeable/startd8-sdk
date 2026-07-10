# CRP Focus — Triage Panel Mode

## Least-reviewed targets (weight review here)

Both docs are **brand new** (zero prior review). Concentrate on:

1. **FR-8 — the paid `extract` step in a dashboard.** Is the dry-run→confirm cost gate + fail-closed
   budget (412) + `max_cost_usd` ceiling + checksum-echo (409 on stale) sufficient to make a *paid*
   action safe to expose in a Grafana panel? Any way to spend without the confirm? Idempotent-replay
   (`deduped`) correctness?
2. **FR-9/10 — the write surface** (disposition → serialize → VIPP inbox). These write intermediate
   stores (proposal store, inbox) but NOT the source of record. Is that boundary clear + safe? Failure
   modes: 404 "stage it first", 409 "none accepted", partial serialize.
3. **FR-11 — compose-with-Apply / no-duplicate-gate.** The panel ends at serialize; the existing Apply
   mode ratifies. Is the hand-off coherent, or does splitting the flow across two panel modes create a
   confusing/lossy UX or a state-desync hazard?
4. **Session UX (OQ-3/5/6)** — latest-or-explicit `session_id`; single stepped panel vs discrete modes;
   should the paid extract be its own mode so "paid" is unmistakable?
5. **Multi-step state machine (R3)** — idle→triaged→staged→dispositioned→serialized in one React
   component. Race/stale-state hazards; what happens if the synthesis changes mid-flow (checksum
   guards extract, but does triage/disposition go stale?).
6. **The M1 server change** — adding `backlog_markdown` to `_triage`. Additive + safe? Any consumer
   that exact-key-matches the triage response?

## Settled — do NOT relitigate

- The **shipped route contracts** (`/stakeholders/{triage,extract,disposition,serialize,apply/*}`) and
  their request/response shapes — they are live + tested; take them as given.
- The **apply challenge/nonce HMAC gate** (FR-R7) — reused as-is via the existing Apply mode; not in
  scope to redesign.
- The **two-store architecture** (ask-all vs facilitation/kickoff-panel) and that triage/extract read
  the facilitation synthesis.
- The **3-lane** (FIELD_LEVEL/NON_DECIDABLE/UNSTRUCTURED) + **10-kind** InputKind taxonomy.
- **Token-never-a-panel-option** / datasource-proxy routing (settled since the run panel).
- **posture/tier**, F1 fire-and-poll, the prototype/scrutiny postures.
- That the **TS is typecheck-pending** (no node_modules; Actions disabled) — a known constraint, not a
  finding.
- Backlog-file append is **out of scope** (NR-2) — don't propose it.

## Steering

Prefer S-/F- suggestions anchored to FR-8/9/10/11 and the state-machine/UX risks. Deprioritize generic
"add tests"/"add logging" unless tied to the paid+write surface.
