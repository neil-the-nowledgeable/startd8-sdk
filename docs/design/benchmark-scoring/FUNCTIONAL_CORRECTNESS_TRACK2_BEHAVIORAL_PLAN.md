# Functional-Correctness Track 2 — Behavioral Execution (Implementation Plan)

**Version:** 1.1 (paired with Track 2 requirements v0.3)
**Date:** 2026-06-19
**Status:** Implemented — M-T2.1..M-T2.4 shipped; pilot decision gate passed; expanded to 7 suites /
3 transports. Recovered 3-round CRP review triaged into Appendix A/B; 3 items remain open backlog.

> Grounded in `sandbox.py`, `languages/protocol.py`, `benchmark_matrix/scoring.py` + `runner.py`,
> the seeds, and `demo.proto`. Milestones map 1:1 to tasks M-T2.1..M-T2.4.

## v1.0 → v1.1 — Post-implementation status + CRP triage

> All four milestones shipped; the plan is reconciled to reality and the recovered CRP review is
> triaged into Appendix A/B (mirroring the requirements doc). Open backlog below.

- **Delivered:** M-T2.1 `run_service_sandboxed` + loopback/egress profile; M-T2.2 startup contract +
  `resolve_serve_command` (resolver, **not** a `LanguageProfile` method — R2-S/F1); M-T2.3 vendored
  offline runtime + multi-path proto + SDK-authored suites; M-T2.4 composite fold-in
  (`FUNCTIONAL_WEIGHT=0.5`) + durable `batch_root` persistence. Pilot gate (OQ-T2-2) **passed** — `Charge`
  discriminated; harness expanded to **7 suites across gRPC/GraphQL/REST** and N=2 repeat-vs-flip runs
  (`compare_runs.py`) are done.
- **Open backlog (triaged → accepted, not yet built):**
  - **R2-S1** — extend `aggregate.py:summarize_group` with `functional_median`/`functional_iqr` so the
    leaderboard gets a real functional column (today only the pilot script prints a per-cell line).
  - **R3-S1 / R1-F2** — incremental/atomic per-cell persistence (`cell_<id>.json` written as each cell
    finishes, aggregate at the end) so a mid-run crash doesn't lose the batch.
  - **R3-S3 / R3-F3** — classify behavioral missing-deps in `execute.py`: floor a hallucinated framework
    (`express`) vs degrade a protocol dep (`@grpc/grpc-js`); today all missing modules degrade.
  - **R2-S2** (partial) — detect/rewrite a model that hardcodes a port and ignores `$PORT`.
  - **R2-S3** — make the known-broken-fixture test assert per-RPC failure reasons, not a generic failure.

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

<!-- v1.1 2026-06-19 — CRP review log TRIAGED. The 3-round dual-document review (R1 gemini-3.1-pro,
R2 composer-2.5, R3 claude-3-5-sonnet; 2026-06-15), recovered from orphaned commit ed478cae, is now
dispositioned: Appendix A (applied) and Appendix B (rejected) filled; accepted-but-open items remain
visible in Appendix C and the v1.1 backlog above. Per the CRP "do not delete A/B" principle, A/B are
append-only cross-model memory. The R2/R3 Requirements Coverage Matrices are preserved verbatim as the
analysis record (they describe pre-implementation coverage gaps, since closed or tracked open). -->

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
| R1-S1 | Add FR-T2-PERSIST durable batch root + cells.json/report.md to M-T2.4 | R1 gemini-3.1-pro | Implemented: `run_behavioral_pilot.py` writes `cells.json`+`report.md` under a caller-provided `batch_root`; `rescore_behavioral.py` re-scores from it. (Incremental flush remains open — R3-S1.) | 2026-06-19 |
| R1-S2 | Multi-path `demo.proto` provisioning + missing-proto degrade in M-T2.3 | R1 gemini-3.1-pro | Implemented: `provision.py`/`provision_workdir` place the proto at conventional paths; missing → degrade with attempted path in provenance. | 2026-06-19 |
| R1-S3 | Explicit egress-denial test (external IP fails, loopback succeeds) | R1 gemini-3.1-pro | Implemented: `test_benchmark_sandbox_service.py::test_loopback_profile_allows_localhost_denies_egress`. | 2026-06-19 |
| R1-S4 | Parse missing-module from stderr into provenance | R1 gemini-3.1-pro | Implemented: `execute.py` extracts `Cannot find module '<x>'` → `provenance["missing_module"]`. | 2026-06-19 |
| R3-S2 | Mandate strict client-side timeouts on every suite RPC | R3 claude-3-5-sonnet | Implemented: every suite enforces `timeout=` per RPC; a hanging server fails the suite and teardown still runs. | 2026-06-19 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | — | Nothing rejected outright. Accepted-but-unbuilt items (R2-S1, R3-S1, R3-S3, partial R2-S2, R2-S3) remain **open** in Appendix C / the v1.1 backlog rather than rejected. | 2026-06-19 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

> **Triage status (v1.1):** R1/R2/R3 below were triaged 2026-06-19. Items dispositioned **Applied** are
> in Appendix A. Still **open** (accepted, not yet built — see the v1.1 backlog): **R2-S1** (functional
> aggregation in `aggregate.py`), **R3-S1** (incremental/atomic per-cell persistence), **R3-S3** (floor
> hallucinated vs degrade protocol deps in `execute.py`). **Partial:** **R2-S2** ($PORT injected;
> hardcoded-port detection unbuilt), **R2-S3** (per-RPC known-broken assertion specificity). The original
> round blocks + R2/R3 coverage matrices are preserved verbatim below.

#### Review Round R1 — gemini-3.1-pro — 2026-06-15

- **Reviewer**: gemini-3.1-pro
- **Date**: 2026-06-15 21:26:00 UTC
- **Scope**: First breadth pass — sandbox networking, durability of artifacts, proto pathing, and dependency reporting gaps between requirements and plan.

**Executive summary**

- Plan lacks tasks for **FR-T2-PERSIST** (durable artifacts) and **FR-T2-PROTO** (multi-path provisioning).
- Plan lacks explicit testing of the **FR-T2-SEC** egress denial capability.
- Requirements could clarify partial-run behavior for durable results and `localhost` vs `127.0.0.1` binding.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | **Add FR-T2-PERSIST to Plan M-T2.4:** The plan omits the durable workdir and `cells.json`/`report.md` generation that FR-T2-PERSIST mandates. Extend M-T2.4 with a task to configure a persistent batch root and aggregate the cell outputs into these durable files, moving away from `$TMPDIR`. | Requirements call out the pilot failure (P3) due to `$TMPDIR` reaping, but the plan has no task to implement the durable persist logic. | M-T2.4 task list | Verify `cells.json` and `report.md` are created at the specified path and survive beyond process exit. |
| R1-S2 | Interfaces | high | **Add FR-T2-PROTO provisioning to Plan M-T2.3:** Expand M-T2.3 to explicitly implement the multi-path provisioning of `demo.proto` (workdir root, `protos/`, `pb/`, etc.) and the fallback degradation logic on missing proto. | Pilot failure P2 (proto path drift) was identified in requirements, but M-T2.3 only states "Vendor offline gRPC/protobuf + generated demo.proto stubs", missing the multi-path payload provisioning. | M-T2.3 task list | Sandbox tests verify `demo.proto` is available at all 5+ conventional paths before process start. |
| R1-S3 | Validation | medium | **Explicit network egress test:** In M-T2.1 tests, add an explicit test asserting that a sandboxed process attempting to connect to an external IP (e.g., `8.8.8.8`) fails, while loopback (`127.0.0.1`) succeeds. | M-T2.1 tests currently verify readiness, callback, and teardown, but do not explicitly verify that the loopback-allowed/egress-denied profile works or degrades gracefully. | M-T2.1 Tests list | Test process trying to `curl 8.8.8.8` receives immediate network error. |
| R1-S4 | Ops | medium | **Add FR-T2-DEPS2 error parsing:** Add a task to M-T2.4 (or M-T2.1) to parse stderr/stdout for missing module errors (e.g., `Cannot find module`) and surface them in the provenance record. | FR-T2-DEPS2 requires self-reporting missing dependencies, which means the harness must extract module names from the Node error trace and fold them into the degraded state. | M-T2.4 task list | Sandbox returns `SandboxResult(violation="missing module: pino")` when `require('pino')` fails. |

**Endorsements:** none
**Disagreements:** none

#### Review Round R2 — composer-2.5 — 2026-06-15

- **Reviewer**: composer-2.5
- **Date**: 2026-06-15 21:35:00 UTC
- **Scope**: Second-order architectural gaps — aggregation completeness, protocol stability, and scoring contradictions.

**Executive summary**
- **FR-T2-HOOK** is implemented as an internal dispatcher to preserve `LanguageProfile` stability, contrary to the requirement.
- `aggregate.py` drops `functional_coverage`, preventing the "functional leaderboard column" from materializing.
- FR-T2-COMPOSITE contradicts FR-T2-2 regarding sandbox violation flooring vs degrading.
- Hardcoded model ports break the `$PORT` injection assumption, leading to false degraded cells.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Ops | high | **Add functional aggregation to `aggregate.py`:** M-T2.4 must extend `aggregate.py:summarize_group` to compute `functional_median` and `functional_iqr` from `CellResult.functional_coverage`. | The runner saves the coverage on `CellResult`, but `aggregate.py` currently drops it, blocking the M-T2.4 requirement for a functional leaderboard column. | M-T2.4 task list | `aggregate_cells` outputs include `functional_median` and `functional_iqr` correctly. |
| R2-S2 | Risks | medium | **Handle hardcoded ports:** Add an inspection or rewrite step in M-T2.2 or M-T2.1 to handle models that hardcode the port (e.g. `8080`) instead of reading `process.env.PORT`. | The startup contract relies on injecting `$PORT`, but if the generated code ignores it, the cell will fail readiness and falsely record a degrade rather than a behavioral score. | M-T2.2 or Risks | Sandboxing a hardcoded-port service correctly identifies the port or overrides it so the client window succeeds. |
| R2-S3 | Validation | low | **Specify known-broken failure modes:** M-T2.3's known-broken fixture test must explicitly verify that specific RPCs fail for specific reasons (e.g., expiry check missing fails the future expiry test but passes Luhn). | A blanket failure in a broken fixture might just indicate a crash, not a discriminating behavioral suite. True validation requires checking specific suite assertions. | M-T2.3 tests list | Test asserts `Charge` suite fails the exact "invalid expiry" case on the broken fixture, not a generic timeout. |

**Endorsements**
- R1-S1: Crucial operational requirement for reproducibility.
- R1-S4: Important for honest degradation and actionable feedback.

**Disagreements**
- R1-S3: (None — egress test is a strong addition).

#### Review Round R3 — claude-3-5-sonnet — 2026-06-15

- **Reviewer**: claude-3-5-sonnet
- **Date**: 2026-06-15 21:40:00 UTC
- **Scope**: Third-order pass — scoring inversion risks, sandbox deadlocks, and concurrent persist collisions.

**Executive summary**
- **Scoring Inversion:** Models that hallucinate unsupported dependencies (e.g., `express`) fail to launch, degrading gracefully to 1.0. Models that successfully launch but fail behavioral tests get penalized to 0.5.
- **Client Deadlocks:** The sandbox client window is synchronous; without mandatory RPC timeouts, a hanging server will deadlock the entire harness.
- **Concurrent Persist:** `cells.json` and `report.md` will suffer data loss if multiple cells write to them concurrently during matrix execution.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | Ops | high | **Handle concurrent persistence in M-T2.4:** Update M-T2.4 to explicitly require per-cell atomic writes (e.g., `cell_<id>.json`) and a final aggregation step for `cells.json` and `report.md`. | The benchmark matrix runs cells concurrently. If all cells write to a shared `cells.json` or `report.md` without locking or separate files, race conditions will cause data loss, undermining FR-T2-PERSIST. | M-T2.4 task list | Matrix run with concurrency > 1 correctly aggregates all cell results into the final report without drops. |
| R3-S2 | Validation | high | **Mandate client timeouts in M-T2.3:** Add an explicit task to enforce strict client-side timeouts on every gRPC call made by the SDK-authored suite. | `run_service_sandboxed` only waits for TCP readiness, then yields to the synchronous client callback. If the server accepts the gRPC call but hangs, the harness will deadlock because the teardown `finally` block cannot execute until the client returns. | M-T2.3 task list | A generated server fixture that intentionally sleeps on `Charge` fails the suite timeout and allows the sandbox to tear down. |
| R3-S3 | Architecture | medium | **Distinguish model-caused vs infra-caused degrades:** Introduce logic in M-T2.4 to classify missing dependencies. If the missing dependency is a standard library of the protocol (e.g., `@grpc/grpc-js`), it's an infra failure (degrade). If it's a hallucinated framework (e.g., `express`), it's a model failure and should be floored. | Treating all launch failures as "degraded" creates a perverse incentive: a model that hallucinates `express` retains a 1.0 score, while a model that correctly uses gRPC but fails the Luhn check gets penalized to 0.5. | M-T2.4 task list | A cell requesting `express` receives a 0.0 or heavily penalized score, rather than a degraded 1.0. |

**Endorsements**
- R2-S1: Crucial for exposing the functional score to the final output.
- R2-S2: Hardcoded ports are a very common hallucination that needs patching.

**Disagreements**
- (None).

---

## Requirements Coverage Matrix — R2

Analysis only (not triage). Second pass — aggregation, hook divergence, and flooring contradictions.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-T2-1 (Sandbox escalation) | M-T2.1 | Partial | R1 gaps remain. Hardcoded port edge case unaddressed (R2-S2). |
| FR-T2-SEC (Loopback/Egress) | M-T2.1 | Partial | R1 gaps remain. |
| FR-T2-2 (Degrade honestly) | M-T2.1, M-T2.2, M-T2.4 | Partial | Contradicted by FR-T2-COMPOSITE sandbox flooring (R2-F2). |
| FR-T2-CONTRACT (Startup) | M-T2.2 | Full | — |
| FR-T2-HOOK (Language hook) | M-T2.2 | Gap | Implemented via internal map, not `LanguageProfile` protocol (R2-F1). |
| FR-T2-SUITE (Behavioral suite) | M-T2.3 | Partial | Known-broken fixture validation lacks specificity (R2-S3). |
| FR-T2-DEPS (Vendored runtime) | M-T2.3 | Full | — |
| FR-T2-DEPS2 (Self-reporting deps) | M-T2.4 | Partial | R1 gaps remain. |
| FR-T2-PROTO (Multi-path proto) | M-T2.3 | Partial | R1 gaps remain. |
| FR-T2-PERSIST (Durable results) | M-T2.4 | Partial | R1 gaps remain. Aggregation logic missing (R2-S1). |
| FR-T2-PROV (Provenance emission) | M-T2.4 | Full | — |
| FR-T2-COMPOSITE (Score folding) | M-T2.4 | Partial | Contradicts FR-T2-2 on sandbox violations (R2-F2); weight applied before discrimination proven (R2-F3). |
| FR-T2-PILOT (Paymentservice pilot) | M-T2.4 | Full | — |

Analysis only (not triage). Maps each requirement to the plan step(s) that implement it.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-T2-1 (Sandbox escalation) | M-T2.1 | Partial | Readiness timeout contract needs clarification regarding fixed vs dynamic boot times (R1-F3). |
| FR-T2-SEC (Loopback/Egress isolation) | M-T2.1 | Partial | Egress testing omitted from plan tests (R1-S3); `localhost` vs `127.0.0.1` binding unclarified (R1-F1). |
| FR-T2-2 (Degrade honestly) | M-T2.1, M-T2.2, M-T2.4 | Full | — |
| FR-T2-CONTRACT (Startup contract) | M-T2.2 | Full | — |
| FR-T2-HOOK (Language run hook) | M-T2.2 | Full | — |
| FR-T2-SUITE (Behavioral suite) | M-T2.3 | Full | — |
| FR-T2-DEPS (Vendored runtime) | M-T2.3 | Full | — |
| FR-T2-DEPS2 (Self-reporting missing deps) | M-T2.4 | Partial | No explicit task to parse stdout/stderr for missing modules (R1-S4). |
| FR-T2-PROTO (Multi-path demo.proto) | M-T2.3 | Partial | Plan M-T2.3 lacks multi-path provisioning task (R1-S2). |
| FR-T2-PERSIST (Durable workdirs/results) | M-T2.4 | Gap | Not addressed in plan (R1-S1); partial run durability undefined (R1-F2). |
| FR-T2-PROV (Provenance emission) | M-T2.4 | Full | — |
| FR-T2-COMPOSITE (Score folding) | M-T2.4 | Full | — |
| FR-T2-PILOT (Paymentservice pilot) | M-T2.4 | Full | — |

---

## Requirements Coverage Matrix — R3

Analysis only (not triaged). Third pass — concurrency, deadlocks, and scoring inversions.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-T2-1 (Sandbox escalation) | M-T2.1 | Partial | Client timeouts omitted; synchronous execution risks deadlock (R3-S2, R3-F2). |
| FR-T2-SEC (Loopback/Egress) | M-T2.1 | Partial | R1-R2 gaps remain. |
| FR-T2-2 (Degrade honestly) | M-T2.1, M-T2.2, M-T2.4 | Partial | Conflicts with FR-T2-DEPS2 logic on model-caused vs infra-caused degrades (R3-S3). |
| FR-T2-CONTRACT (Startup) | M-T2.2 | Full | — |
| FR-T2-HOOK (Language hook) | M-T2.2 | Gap | R2 gaps remain. |
| FR-T2-SUITE (Behavioral suite) | M-T2.3 | Partial | Explicit timeouts required (R3-F2). |
| FR-T2-DEPS (Vendored runtime) | M-T2.3 | Full | — |
| FR-T2-DEPS2 (Self-reporting deps) | M-T2.4 | Partial | Must distinguish hallucinated dependencies from missing infrastructure (R3-F3). |
| FR-T2-PROTO (Multi-path proto) | M-T2.3 | Partial | R1 gaps remain. |
| FR-T2-PERSIST (Durable results) | M-T2.4 | Partial | Concurrent execution overwrites shared files without atomic writes/aggregation (R3-S1, R3-F1). |
| FR-T2-PROV (Provenance emission) | M-T2.4 | Full | — |
| FR-T2-COMPOSITE (Score folding) | M-T2.4 | Partial | Score inversion due to degraded baseline (R3-S3). |
| FR-T2-PILOT (Paymentservice pilot) | M-T2.4 | Full | — |
