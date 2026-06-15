# Functional-Correctness Track 2 — Behavioral Execution Scoring (Requirements)

**Version:** 0.1 (Draft — pre-implementation; grounded against real code)
**Date:** 2026-06-15
**Status:** Draft — user committed to Track 2 (behavioral execution) after Track 1 was falsified
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
- **FR-T2-DEPS** *(G5)* Vendor the offline gRPC/protobuf runtime + generated stubs (server-side per
  language as needed; client-side in the SDK's language). No network fetch at run time (dep quarantine).
- **FR-T2-PROV** Provenance (FR-F9): suite version, per-RPC results + timings, isolation level applied,
  available-vs-degraded — emitted on every behavioral cell.

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

---

*v0.1 — grounded pre-implementation draft. Track 2 promoted from a deferred sketch to a 4-milestone
build (M-T2.1 sandbox → M-T2.2 contract+hook → M-T2.3 suite+deps → M-T2.4 composite+pilot), with the
loopback-vs-egress sandbox nuance (G2) and the re-run requirement (G6) made explicit up front.*
