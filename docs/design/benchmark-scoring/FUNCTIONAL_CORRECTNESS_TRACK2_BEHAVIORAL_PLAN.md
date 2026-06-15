# Functional-Correctness Track 2 — Behavioral Execution (Implementation Plan)

**Version:** 1.0 (paired with Track 2 requirements v0.1)
**Date:** 2026-06-15
**Status:** Plan — build M-T2.1 first (foundational, no re-run needed)

> Grounded in `sandbox.py`, `languages/protocol.py`, `benchmark_matrix/scoring.py` + `runner.py`,
> the seeds, and `demo.proto`. Milestones map 1:1 to tasks M-T2.1..M-T2.4.

## Approach

Build bottom-up and de-risk early. The foundational slice (M-T2.1, the behavioral sandbox
primitive) needs **no seeds change and no re-run** — it's pure infra, testable against a trivial
local server fixture. Lock it down first. The startup contract (M-T2.2) and behavioral suite
(M-T2.3) layer on top; only M-T2.4 spends LLM budget (the paymentservice re-run) and only after the
machinery is proven on fixtures. The pilot's discrimination result gates the expensive full re-run.

## Milestones

### M-T2.1 — Behavioral sandbox primitive (build first; no LLM, no re-run)
New `run_service_sandboxed` in `benchmark_matrix/sandbox.py` (sibling to `run_sandboxed`):
1. `Popen(server_cmd, ...)` with `scrub_env`, `preexec_fn=_rlimit_preexec(cfg)` (gives `os.setsid()`
   group containment already present), `start_new_session=True`.
2. **Readiness probe**: poll `127.0.0.1:<port>` (socket connect) until ready or `readiness_timeout_s`.
   Not-ready → teardown + `SandboxResult(violation="server never became ready")` → degraded (FR-T2-2).
3. **Client window**: invoke a `client(port) -> ClientOutcome` callback against the live server.
4. **Guaranteed teardown** (`finally`): `os.killpg(os.getpgid(pid), SIGTERM)`, short grace, then
   `SIGKILL`; reap; bounded-capture the server's stdout/stderr; never leak a process.
5. **Network profile (FR-T2-SEC, G2)**: add a `loopback_only` mode to the no-network wrap — seatbelt
   `(allow default)(allow network* (local ip "localhost:*"))(deny network-outbound (remote ip "*"))`
   (allow loopback bind/connect, deny remote egress). On hosts that can't express it, set
   `isolation_level="loopback-allowed/egress-unverified"` and record honestly — never silent-downgrade.
- *Files:* `sandbox.py` (+ new primitive + loopback profile branch in `_wrap_no_network`).
- *Tests* (`tests/unit/test_benchmark_sandbox_service.py`, no network/LLM): a trivial Python
  `http.server`/socket fixture as the "service" — assert (a) readiness detected, (b) client callback
  runs against it, (c) process-group fully killed after (no orphan; pid gone), (d) never-ready →
  violation+degraded, (e) client timeout still tears down.

### M-T2.2 — Startup contract + per-language run hook
- Seed schema: add an optional `startup` block `{cmd, port_env|port, readiness}`. Document it; add to
  the paymentservice seed. (Validation: a Track-2 cell requires `startup`; absent → degraded.)
- `LanguageProfile`: add `serve_command(target_files, port) -> Optional[List[str]]`. Implement
  `NodeLanguageProfile.serve_command` (`node <server.js>` with `PORT` injected); others return `None`
  → degraded (FR-32), never crash. (OQ-T2-1: lean port-injection via `$PORT` env.)
- *Files:* `languages/protocol.py` (protocol + Node impl), seed schema doc + paymentservice seed.
- *Tests:* Node serve command construction; absent-hook → degraded; seed-contract parse.

### M-T2.3 — paymentservice.Charge behavioral suite + vendored runtime
- Vendor offline gRPC/protobuf + generated `demo.proto` stubs under a benchmark-owned vendored path
  (no run-time fetch — dep quarantine). Pin versions; document the regen step.
- SDK-authored client suite for `Charge`: Luhn-valid card + future expiry → expects a non-empty
  `transaction_id`; invalid Luhn / past expiry → expects the contract error. Returns per-RPC pass/fail
  + timings + suite version (FR-T2-PROV). Language-agnostic (talks gRPC to `127.0.0.1:$PORT`).
- *Files:* `benchmark_matrix/behavioral/` (suite + proto stubs), vendored deps.
- *Tests:* run the suite against a **known-good reference** `Charge` server (committed fixture) → all
  pass; against a deliberately-broken one → fails the right RPCs. (Proves the suite discriminates
  before any model output is involved.)

### M-T2.4 — Composite fold-in + paymentservice pilot (spends budget)
- Extend `CompositeScore` (scoring.py) with a `functional` term: `behavioral_coverage ∈ [0,1]` as an
  added weighted term; compile/sandbox-violation floors still apply (FR-T2-COMPOSITE). Services with
  no suite keep existing terms + a report flag.
- Runner: for a Track-2 cell, after the compile gate, start the service via the run hook inside
  `run_service_sandboxed`, run the suite, fold coverage in. Degrade honestly on any env failure.
- **Pilot run**: paymentservice × {Gemini 2.5 Pro, gpt-5.5, Opus 4.8} × N, with the startup contract
  (a scoped re-run of just this service). Add a "functional" leaderboard column + provenance.
- **Decision gate (OQ-T2-2):** does `Charge` behavior discriminate? If yes → M-T2.5 (expand + full
  re-run). If it also saturates → escalate to a harder RPC before funding the full re-run.

## Risks
- **Loopback-vs-egress (G2):** the central new security nuance. If a host can't express it, behavioral
  cells must be marked egress-unverified, not silently trusted — wrong here = untrusted code with net.
- **Orphan processes:** a server that double-forks can escape a naive kill. `start_new_session` +
  `killpg` mitigates; the never-leak test is mandatory.
- **Re-run cost & contract churn:** adding the startup contract invalidates Round-1 cells for piloted
  services; scope the re-run to paymentservice only until discrimination is proven.
- **Suite validity:** a weak suite gives a false "all pass." The known-good/known-broken fixture tests
  (M-T2.3) gate this before any model output is scored.
- **Premise risk (OQ-T2-2):** behavior may *also* saturate on a pure RPC. The pilot is explicitly the
  cheap probe of this; do not commit the full re-run until it answers.

## Sequencing
M-T2.1 (now, fixture-tested) → M-T2.2 + M-T2.3 (parallelizable; both fixture-tested, no LLM) →
M-T2.4 (composite + scoped paymentservice re-run) → **gate** → M-T2.5 expand (separate spec).

## Out of scope (this plan)
All-service expansion + full re-run (M-T2.5); kernel isolation (NR-T2-2); stateful services (NR-T2-3).
