# Functional-Correctness Track 2 — Behavioral Execution Scoring (Requirements)

**Version:** 0.2 (Post-pilot — gaps the first paymentservice run exposed)
**Date:** 2026-06-15
**Status:** Draft — pilot ran end-to-end; harness provisioning gaps found, reqs updated before re-run
**Owner SDK area:** `startd8.benchmark_matrix` (sandbox + scoring) + `startd8.languages` (run hook)
**Parent:** `FUNCTIONAL_CORRECTNESS_SCORING_REQUIREMENTS_v0.1.md` (v0.2) — this promotes its deferred
Track 2 (FR-F3..F9, FT-5) from sketch to a buildable, milestone-decomposed spec.
**Consumers:** Summer 2026 benchmark — the *only* trustworthy frontier quality discriminator.

---

## 0. Grounding Insights (from reading the code before drafting)

> The parent doc deferred Track 2 with a one-line plan row. Reading `sandbox.py`,
> `languages/protocol.py`, the seeds, and `demo.proto` surfaces five concrete realities that
> shape the build — captured here so the milestones below are buildable, not aspirational.

| # | Assumption in the parent sketch | Code reality | Impact |
|---|--------------------------------|--------------|--------|
| G1 | "Extend the one-shot sandbox to a server" | `sandbox.py:run_sandboxed` is `subprocess.run` + wall timeout (`sandbox.py:148`); no long-lived process, no readiness, no client window | M-T2.1 adds a **new** `run_service_sandboxed` primitive (Popen + readiness probe + client callback + guaranteed process-group kill). Reuse `scrub_env`/`_rlimit_preexec`/`sandbox_caps`. |
| G2 | "Run with no network (FR-44)" | The no-network wrap is `(version 1)(allow default)(deny network*)` (`sandbox.py:114`) — blocks **loopback too** | **Loopback must be allowed while external egress stays denied.** A gRPC server+client over `127.0.0.1` cannot run under `deny network*`. New seatbelt/netns profile: allow loopback bind/connect, deny remote. (FR-T2-SEC) |
| G3 | "LanguageProfile exposes a run/serve hook (OQ-F6)" | It has `syntax_check_command`, `lint_command`, `test_command` — **no serve hook** (`protocol.py`) | M-T2.2 adds a **new run/serve hook** to the profile protocol; implement Node first (pilot is Node). |
| G4 | "currencyservice is the pure pilot" (parent already corrected → payment) | `seed-paymentservice.json` → `target_files: ['src/paymentservice/server.js']`, **language nodejs**, single file; `PaymentService.Charge` is input→`transaction_id` (Luhn/expiry only) | Pilot = **paymentservice (Node, single-file)**. The behavioral suite is **language-agnostic over the gRPC wire** — only the run hook is language-specific. |
| G5 | "Runtime deps from a vendored bundle (FR-F4)" | **No `vendor/` or vendored gRPC/protobuf bundle exists** in the repo | M-T2.3 must **create** the offline vendored gRPC/protobuf runtime + generated stubs (per-language for the server side; the client side is the SDK's chosen language). |
| G6 | "No startup contract exists (OQ-F3)" | Seeds fix only `target_files` + language; the model chose port/entrypoint freely | A uniform launch is impossible without a **startup contract** in the seeds → models must regenerate → **a benchmark re-run is part of Track 2** (FR-T2-CONTRACT, accepted by the user's choice). |

---

## 0b. Pilot Insights (v0.1 → v0.2)

> The first paymentservice pilot (3 flagships × 3 reps, real generation under Doppler) ran the
> whole pipeline end-to-end and proved the premise — **where a server actually started, behavior
> discriminated**: Opus produced a card-validating service (functional 1.00), gpt-5.5 produced a
> lenient mock that accepts invalid/expired cards (0.33). But 6 of 9 cells were lost to **harness
> provisioning gaps, not model quality** — and each gap traces to an incomplete v0.1 requirement,
> which the implementation then faithfully under-built. This is a reqs-completeness failure first.

| # | Pilot failure | v0.1 reqs state | Class | Fix (this version) |
|---|---------------|-----------------|-------|--------------------|
| P1 | Every generated server `require`s `pino`+`uuid` (the real OB paymentservice's deps); runtime only had gRPC → `Cannot find module 'pino'` | **FR-T2-DEPS scoped "gRPC/protobuf runtime" only** — never said "the service's full dependency closure" | reqs gap + impl | **FR-T2-DEPS expanded** (P1) + **FR-T2-DEPS2** (closure provisioning) |
| P2 | Models load the proto from divergent paths (`proto/`, `pb/`, root, `protos/`); harness provided only 2 → readiness fails | **No FR addresses proto location at all** | reqs gap + impl | **FR-T2-PROTO** (new) |
| P3 | Workdirs in `$TMPDIR` are OS-reaped; results only printed, never written → post-hoc review lost cells | FR-T2-PROV says provenance is "emitted," never "persisted to a durable location" | reqs gap + impl | **FR-T2-PERSIST** (new) |

**Confirmed working (no change needed):** the sandbox lifecycle (FR-T2-1), loopback/egress profile
(FR-T2-SEC), degrade-not-zero discipline (FR-T2-2 — every blocked cell degraded honestly, none was
falsely scored 0), the startup contract + Node serve hook (FR-T2-CONTRACT/HOOK), the Charge suite
(FR-T2-SUITE), and the composite fold-in (FR-T2-COMPOSITE) all behaved as specified.

## 1. Problem Statement

Round 1 quality saturates at every static layer: structural compliance (1.000), the compile gate
(saturates where it fires), and static contract-coverage (falsified — all models implement 100% of
proto RPCs; finer static signals have no trustworthy correctness *direction*). The only signal that
separates frontier models is **whether the generated service actually behaves correctly when run**:
start it, invoke each RPC over gRPC with known inputs, and check the responses against an
SDK-authored ground-truth suite.

| Dimension | Term | Discriminates frontier? |
|-----------|------|-------------------------|
| Structure / Buildability / static coverage | existing | **No — all saturate** |
| **Behavior (executed)** | **this spec** | **Yes — the gold standard** |

## 2. Goals & Non-Goals

**Goal:** A behavioral execution scoring term: run each generated service in an escalated sandbox,
drive its RPCs with an SDK-authored gRPC suite, and fold per-RPC pass/fail into the composite as an
added weighted term (gates still floor). Prove it on the **paymentservice pilot** before expanding.

**Non-Goals (this spec):** load/perf testing; grading model-written tests (self-grading); full
multi-service Online Boutique integration (single service, deps pinned/mocked); replacing the compile
gate (behavioral builds on top); expanding to all 9 services before the pilot proves discrimination.

## 3. Requirements

### Sandbox escalation (M-T2.1)
- **FR-T2-1** A `run_service_sandboxed(server_cmd, workspace, *, readiness, client, cfg)` primitive:
  Popen the server under the existing controls (`scrub_env`, rlimits, isolation caps), wait for
  `readiness` (port-listening probe with timeout), invoke the `client` callback against the live
  server, then **guarantee teardown** (process-group `SIGTERM`→`SIGKILL`, reap, workspace cleanup)
  even on client exception/timeout. Reuses `os.setsid()` group containment already in `_rlimit_preexec`.
- **FR-T2-SEC** *(G2)* The isolation profile for a behavioral cell **allows loopback** (`127.0.0.1`
  bind/connect) and **denies external egress**. If the host can express only all-or-nothing network
  policy, record `isolation_level` honestly (loopback-allowed/egress-unverified) — never silently
  downgrade and score it as if egress were blocked.
- **FR-T2-2** A behavioral run that fails for **environment** reasons (server never became ready,
  sandbox launch error, toolchain/dep absent, sandbox violation) is recorded **degraded** (FR-32),
  **not** scored 0 — same discipline as infra-fail/compile-toolchain-absent.

### Startup contract + run hook (M-T2.2)
- **FR-T2-CONTRACT** *(G6)* Seeds gain a `startup` block: the run command, the listen port (or a
  port-injection mechanism), and the readiness signal. This is part of the cell's fixed contract, so
  every model builds a launchable service. **Adding it requires a benchmark re-run** (accepted).
- **FR-T2-HOOK** *(G3)* `LanguageProfile` gains a run/serve hook returning the start command for a
  service of that language. Node implemented first (pilot); other languages stubbed as
  not-implemented → degraded, never crash (FR-32).

### Behavioral suite + vendored runtime (M-T2.3)
- **FR-T2-SUITE** An **SDK-authored** gRPC client suite per piloted RPC, with fixed inputs and
  asserted outputs. Pilot: `PaymentService.Charge` — Luhn-valid card + valid expiry → a
  `transaction_id`; invalid Luhn / expired card → the contract's error. Per-RPC pass/fail, language-
  agnostic over the wire.
- **FR-T2-DEPS** *(G5; expanded — P1)* Provision the generated service's **full runtime dependency
  closure** offline before the sandboxed run — **not just gRPC/protobuf**. The pilot showed every
  model faithfully reproduces the real OB paymentservice's deps (`pino`, `uuid`) without declaring
  them in `package.json`, so "vendor gRPC" is insufficient. Concretely: vendor the per-service known
  closure (paymentservice = `@grpc/grpc-js`, `@grpc/proto-loader`, `pino`, `uuid`); the run itself
  stays offline (dep quarantine — provisioning happens at prepare time, before the no-egress sandbox).
- **FR-T2-DEPS2** *(new — P1)* Dependency provisioning is **best-effort and self-reporting**: a server
  that still fails to start on a missing module is recorded **degraded** with the missing module named
  in provenance (FR-T2-2), never scored 0 and never silently passed. (Generalizing the closure beyond
  the pilot service — install each cell's declared deps + a curated common set — is tracked in OQ-T2-5.)
- **FR-T2-PROTO** *(new — P2)* The harness must make the contract proto resolvable **regardless of the
  path the model chose**. Provision `demo.proto` at every conventional location a generated server
  loads it from (workdir root, `protos/`, `proto/`, `pb/`, `src/<service>/`, `src/<service>/proto/`).
  A server that loads it from none of these degrades (FR-T2-2) with the attempted path in provenance.
  (Forward fix, deferred: pin the proto path in the startup contract so models target a known location
  — requires a re-gen; OQ-T2-6.)
- **FR-T2-PERSIST** *(new — P3)* Per-cell workdirs and the run's results must be **durable and
  inspectable** — written under a caller-provided persistent batch root (NOT an OS-reaped `$TMPDIR`),
  and the run must write `cells.json` (every CellResult incl. functional coverage + provenance) and a
  `report.md` (leaderboard + per-cell functional column). Post-hoc re-scoring and audit must not depend
  on artifacts that the OS may garbage-collect.
- **FR-T2-PROV** Provenance (FR-F9): suite version, per-RPC results + timings, isolation level applied,
  available-vs-degraded, **and (P1/P2) the missing module / attempted proto path on degrade** — emitted
  on every behavioral cell and persisted per FR-T2-PERSIST.

### Composite + pilot (M-T2.4)
- **FR-T2-COMPOSITE** Behavioral coverage ∈ [0,1] (fraction of suite RPCs passing) folds into
  `CompositeScore` as an **added weighted term**; compile/sandbox-violation floors still apply. Weight
  set so a behaviorally-incomplete service ranks below a complete one. Services with no behavioral
  analyzer remain scored on the existing terms (honest partial coverage), flagged in the report.
- **FR-T2-PILOT** Prove discrimination on paymentservice across the flagship roster before expanding.
  The pilot's result is the **decision gate** for M-T2.5 (all-service expansion + full re-run).

## 4. Non-Requirements / Deferred
- **NR-T2-1** All-service expansion + full Round-1 re-run — deferred behind the pilot decision gate.
- **NR-T2-2** Kernel-level isolation (gVisor/Firecracker/Docker) — the parent's deferred production
  hardening (R3-S2); behavioral cells run under the same best-effort host controls, recorded honestly.
- **NR-T2-3** Stateful services (currency/cart/catalog need pinned data) — pilot is the pure
  `Charge` RPC; stateful services come after the pilot proves the harness.

## 5. Open Questions
- **OQ-T2-1** Port allocation: fixed contract port vs. harness-injected ephemeral port (avoids
  collisions in serial runs; needs the contract to read a `$PORT`). Lean injected-ephemeral.
- **OQ-T2-2** Does behavior actually discriminate the flagships on `Charge`? (The whole premise — the
  pilot answers it. If `Charge` also saturates, escalate to a harder RPC before the full re-run.)
- **OQ-T2-3** Roster: **Fable 5 removed for now** (access-gated 404) — pilot runs the available
  flagships (Gemini 2.5 Pro / gpt-5.5 / Opus 4.8) + tier-2/3 as configured.
- **OQ-T2-4** Re-run cost with the startup contract (full Round-1 ~$150–200 at N=5); pilot is a tiny
  fraction (one service × roster × N).
- **OQ-T2-5** *(new — P1)* Generalizing dependency provisioning beyond the pilot service: install each
  cell's declared `package.json` deps + a curated OB common set at prepare time (network OK pre-sandbox),
  vs. per-service vendored closures. Pilot uses the paymentservice vendored closure; decide before
  all-service expansion (M-T2.5).
- **OQ-T2-6** *(new — P2)* Pin the proto path in the startup contract (models target a known location)
  vs. the harness multiplexing all conventional paths. Contract-pinning is cleaner but needs a re-gen;
  v0.2 multiplexes (no re-gen). Revisit at M-T2.5.

---

*v0.2 — Post-pilot self-reflective update. The first pilot proved the premise (behavior discriminated
where servers ran: Opus 1.00 vs gpt-5.5 0.33) but exposed three provisioning gaps that were
**requirements-completeness failures**, not just implementation bugs: dependency closure (FR-T2-DEPS
expanded + FR-T2-DEPS2), proto-path resolution (FR-T2-PROTO, new), and durable artifacts
(FR-T2-PERSIST, new). 3 FRs added/expanded, 2 open questions added; the confirmed-working core is
unchanged.*

<!-- RECOVERED 2026-06-18 — CRP review log re-attached.
This 3-round dual-document CRP review (R1 gemini-3.1-pro, R2 composer-2.5, R3 claude-3-5-sonnet;
2026-06-15) was a pre-existing UNCOMMITTED edit that a parallel merge-cleanup reverted to origin/main;
recovered from orphaned commit ed478cae and re-attached onto the committed v0.2 core (preserved as-is).
The committed v0.2 (ea29a7c0 "dep closure, proto paths, persistence") may already APPLY several of
these suggestions — the rounds are restored UNTRIAGED (Appendix A/B left "(none yet)"); the spec owner
should record final dispositions in Appendix A/B per the CRP "do not delete A/B" principle. -->

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
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — gemini-3.1-pro — 2026-06-15

- **Reviewer**: gemini-3.1-pro
- **Date**: 2026-06-15 21:26:00 UTC
- **Scope**: First breadth pass — sandbox networking, durability of artifacts, proto pathing, and dependency reporting gaps between requirements and plan.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Architecture | medium | **Clarify localhost vs 127.0.0.1 binding:** FR-T2-SEC states `127.0.0.1` bind/connect. Clarify if IPv6 `::1` and DNS `localhost` are also permitted or strictly excluded. Some language runtimes default to IPv6 `::1` for localhost. | "allow loopback (127.0.0.1)" could break servers binding to `localhost` if the system resolves it to `::1` and IPv6 is blocked. | FR-T2-SEC | Verify `server` binding to `::1` or `localhost` successfully completes readiness probe if permitted. |
| R1-F2 | Ops | medium | **Partial run durability:** FR-T2-PERSIST should define behavior for partial runs (e.g., the script crashes or is terminated early). Ensure `cells.json` and workdirs are continuously flushed or incrementally saved so that intermediate results are not lost. | If the batch consists of N*models cells and fails midway, losing all progress invalidates the purpose of moving away from `$TMPDIR`. | FR-T2-PERSIST | Interrupt benchmark runner midway; verify existing cells exist in the persistent path. |
| R1-F3 | Interfaces | low | **Clarify readiness timeout contract:** Clarify if `readiness_timeout_s` is a globally fixed constant or if the startup contract (FR-T2-CONTRACT) allows models/services to declare their expected boot time. | Some languages/services have drastically different cold-start times; a fixed global timeout might unnecessarily degrade slow-booting servers. | FR-T2-1 or FR-T2-CONTRACT | Slower server correctly boots if timeout allows, or fails deterministically. |

**Endorsements:** none
**Disagreements:** none

#### Review Round R2 — composer-2.5 — 2026-06-15

- **Reviewer**: composer-2.5
- **Date**: 2026-06-15 21:35:00 UTC
- **Scope**: Second-order architectural gaps — aggregation completeness, protocol stability, and scoring contradictions.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Architecture | high | **Correct FR-T2-HOOK protocol coupling:** FR-T2-HOOK MUST state that the serve hook is an internal resolver function (`resolve_serve_command`), NOT a method on `LanguageProfile`. Modifying the Protocol breaks `@runtime_checkable` for existing profiles. | The implementation explicitly avoids modifying `LanguageProfile` for backward compatibility. Requirements should reflect this architectural stability pattern. | FR-T2-HOOK | `LanguageProfile` remains unchanged; `contract.py` resolver correctly falls back to Node defaults. |
| R2-F2 | Validation | high | **Fix sandbox-violation flooring contradiction:** In FR-T2-COMPOSITE, remove "sandbox-violation floors still apply" and replace with "sandbox-violations degrade the functional term (FR-T2-2)". | FR-T2-COMPOSITE dictates a 0.0 floor for sandbox violations, but FR-T2-2 and the implementation record it as a missing term (`functional_degraded=True`), avoiding the floor. | FR-T2-COMPOSITE | A sandbox timeout results in a missing functional term and retains the structural score base, not a 0.0 floor. |
| R2-F3 | Ops | medium | **Clarify pilot weighting (OQ-T2-2):** Add a requirement that `FUNCTIONAL_WEIGHT` must run in shadow mode (e.g., recorded but not affecting `CompositeScore`) OR explicitly documented as a provisional 0.5 weight until the pilot proves discrimination. | The code immediately sets `FUNCTIONAL_WEIGHT = 0.5`. If the premise risk (OQ-T2-2) is real, scrambling the leaderboard with an unproven metric is dangerous. | FR-T2-COMPOSITE or OQ-T2-2 | The leaderboard report surfaces the functional score cleanly before fully committing to the 0.5 fold-in for all services. |

**Endorsements**
- R1-F1: Clarifying IPv6 vs IPv4 bindings avoids false degrades on modern runtimes.
- R1-F2: Highly relevant for expensive pipeline runs.

**Disagreements**
- R1-F3: (None).

#### Review Round R3 — claude-3-5-sonnet — 2026-06-15

- **Reviewer**: claude-3-5-sonnet
- **Date**: 2026-06-15 21:40:00 UTC
- **Scope**: Third-order pass — scoring inversion risks, sandbox deadlocks, and concurrent persist collisions.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Ops | high | **Define concurrent artifact isolation:** FR-T2-PERSIST MUST require that `cells.json` and `report.md` support safe concurrent writes (e.g., per-cell isolation merging at the end) or synchronized locking. | The matrix executes cells concurrently. Writing to a shared artifact file without concurrency controls leads to data races and lost cell results. | FR-T2-PERSIST | Parallel execution of N cells produces exactly N valid entries in the durable result set. |
| R3-F2 | Validation | high | **Mandate client timeouts:** FR-T2-SUITE MUST explicitly state that the SDK-authored suite enforces a strict timeout on every RPC. | A server that accepts a connection but hangs the RPC will deadlock the synchronous sandbox client window, preventing the guaranteed teardown. | FR-T2-SUITE | A server that sleeps infinitely fails the client suite cleanly with a timeout, without hanging the runner. |
| R3-F3 | Architecture | medium | **Resolve missing dependency score inversion:** FR-T2-DEPS2 MUST distinguish between "infrastructure missing" (e.g., a protocol-required package) and "model hallucination" (e.g., `express`). The latter MUST be floored, not degraded. | Degrading all missing modules grants a 1.0 structural score to models that completely fail the framework contract (hallucinating HTTP instead of gRPC), scoring higher than a valid gRPC service that fails the Luhn logic (0.5). | FR-T2-DEPS2 | A generated service that attempts to `require('express')` gets floored or heavily penalized instead of receiving a degraded 1.0 score. |

**Endorsements**
- R2-F1: Architectural stability of LanguageProfile is critical.
- R2-F2: Resolves the contradiction perfectly.

**Disagreements**
- (None).
