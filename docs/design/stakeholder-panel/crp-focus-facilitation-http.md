# CRP Focus — Facilitation over HTTP (F1)

## Least-reviewed / highest-risk (spend budget here)
- **Async fire-and-poll orchestration (FR-1/3/4/6):** the background worker thread + its own event loop —
  lifecycle/cleanup (unregister on terminal, no leak, server shutdown doesn't hang); single-flight
  idempotency by run_key (no double-spawn/double-spend on a retried POST); cross-thread cancel via the
  existing registry; a status poll during a crash/error → terminal `error`, not a stuck `in_progress`.
- **Dry-run cost accuracy per tier (FR-2/FR-10):** does `projected_calls × per-call-estimate` reflect the
  chosen tier? Round-context growth (later rounds carry more tokens) — is the estimate honest or wildly low?
  run_key must bind `{posture, tier, cap, roster_version}` so a cheap dry-run can't authorize a premium run.
- **Fail-closed budget (FR-5):** missing budget config, a run that outlives the daily ceiling mid-flight,
  the cost tracker shared across concurrent runs (panel-costs.db serialization).
- **Plugin poll/error/timeout (FR-9):** a run that halts vs errors vs never terminates; the token staying
  server-side through the proxy; cancel wiring.

## Settled — do NOT relitigate
- The facilitator itself + postures (#172–174); fire-and-poll (OQ-1); the existing `/run` auth + run_key
  idempotency pattern; the kickoff-panel transcript as the status/persistence store (NR-4).
