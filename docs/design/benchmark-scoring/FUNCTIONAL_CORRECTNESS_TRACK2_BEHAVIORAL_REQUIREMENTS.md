# Functional-Correctness Track 2 — Behavioral Execution Scoring (Requirements)

**Version:** 0.3 (Post-implementation — reality reconciliation + recovered CRP review triaged)
**Date:** 2026-06-19
**Status:** Implemented (M-T2.1..M-T2.4 shipped; pilot decision gate passed) — spec reconciled to the
shipped harness (7 suites, 3 transports) and the recovered 3-round CRP review triaged into Appendix A/B
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

## 0c. v0.2 → v0.3 — Reality Reconciliation + CRP Triage

> v0.2 described a single **gRPC `paymentservice` (`Charge`)** pilot. The harness has since shipped
> and grown well past that sketch; v0.3 reconciles the spec to what is on `main` and triages the
> recovered 3-round CRP review (R1 gemini-3.1-pro / R2 composer-2.5 / R3 claude-3-5-sonnet, 2026-06-15)
> into Appendix A/B. The v0.2 §0/§0b/§1–§5 core below is preserved; this section + the inline
> clarifications + the appendix are the only v0.3 additions.

**Shipped reality (as of 2026-06-19):**
- **7 behavioral suites across 3 transports**, not one gRPC service: gRPC (`charge`, `currency`,
  `ad`, `shipping`, `pricing`) + **GraphQL** (`graphql_pricing_suite`) + **REST** (`rest_pricing_suite`).
  The "language-agnostic over the gRPC wire" framing (§G4) generalizes to **transport-agnostic over the
  service wire** — the run hook + readiness probe select the transport (`readiness_mode != "http"` drives
  gRPC-vs-REST provisioning in `execute.py`).
- **Pilot decision gate (FR-T2-PILOT) passed**: `Charge` discriminated (Opus 1.00 vs gpt-5.5 0.33);
  expansion proceeded. N=2 repeat-vs-flip runs are done and `compare_runs.py` (cross-run variance /
  repeat-vs-flip) shipped. NR-T2-1 (all-service expansion) is therefore **partially realized**, not deferred.

**CRP triage outcome (full dispositions in Appendix A/B):**
- **Already applied in v0.2** (recorded in Appendix A with evidence): R2-F1 (HOOK is the
  `resolve_serve_command` resolver, Protocol unchanged), R2-F2 (sandbox violations degrade, not floor),
  R1-S4 (missing-module parse), R3-F2/R3-S2 (per-RPC client timeouts), R1-S3 (egress-denial test),
  R1-S1/R1-S2 (durable batch root + multi-path proto provisioning).
- **Folded into v0.3 as inline clarifications** (below): R1-F1 (loopback binding scope), R1-F3
  (readiness timeout is a fixed 30s global today), R2-F3 (FUNCTIONAL_WEIGHT=0.5 is provisional).
- **Implemented after the triage** (commit `46134128`, 2026-06-19 — recorded in Appendix A):
  - **R3-F3 / R3-S3** — `execute.py` now classifies a missing module against the service's wire
    contract: an HTTP/GraphQL framework on a gRPC (`tcp`) contract — or a gRPC pkg on an HTTP contract —
    is a **model fault** scored real zero coverage and floored to `COMPILE_FLOOR`, never degraded to a
    free structural 1.0. Protocol-appropriate/unknown deps still degrade; REST/GraphQL lanes unaffected.
  - **R2-S1** — `aggregate.py:summarize_group` now carries `functional_median`/`functional_iqr`/
    `n_functional`; the leaderboard gains a conditional `functional (med)` column.
  - **R3-S1 / R1-F2** — `runner.persist_cell_atomic` flushes each cell to `cells/<id>.json`
    (tmp+`os.replace`) via `run_matrix(on_cell=)`, so a mid-run crash no longer loses the batch.
  - **R2-S2** (commit `52695f61`) — `execute._detect_effective_port` reads the generated source and
    probes a hardcoded listen port when the model ignores `$PORT`; an env-read always keeps the injected
    port, so a well-behaved model is never demoted. Recorded as `provenance["port_source"]`.
  - **R2-S3** (commit `52695f61`) — a known-broken pricing fixture (ignores the discount cap) proves
    the suite discriminates per-RPC: it fails exactly `g6_cap_70` for the right reason, not a crash.
- **Open:** none of the CRP-logged items remain. (Operational follow-up only: re-render an existing
  behavioral batch's `report.md` to surface the R2-S1 functional column — needs a persisted batch.)

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
  *(Clarified v0.3 — R1-F3: the readiness timeout is a **fixed 30s global** in `execute.py` today, not a
  per-service declared budget; per-contract declarable boot time is deferred — fold into FR-T2-CONTRACT
  if a slow-booting runtime false-degrades.)*
- **FR-T2-SEC** *(G2)* The isolation profile for a behavioral cell **allows loopback** (`127.0.0.1`
  bind/connect) and **denies external egress**. If the host can express only all-or-nothing network
  policy, record `isolation_level` honestly (loopback-allowed/egress-unverified) — never silently
  downgrade and score it as if egress were blocked. *(Clarified v0.3 — R1-F1: the suites + readiness
  probe bind/connect IPv4 `127.0.0.1`; IPv6 `::1` / DNS `localhost` are not specially provisioned. A
  server that binds only `::1` may fail readiness and degrade honestly — revisit if a piloted runtime
  defaults to IPv6.)*
- **FR-T2-2** A behavioral run that fails for **environment** reasons (server never became ready,
  sandbox launch error, toolchain/dep absent, sandbox violation) is recorded **degraded** (FR-32),
  **not** scored 0 — same discipline as infra-fail/compile-toolchain-absent.

### Startup contract + run hook (M-T2.2)
- **FR-T2-CONTRACT** *(G6)* Seeds gain a `startup` block: the run command, the listen port (or a
  port-injection mechanism), and the readiness signal. This is part of the cell's fixed contract, so
  every model builds a launchable service. **Adding it requires a benchmark re-run** (accepted).
- **FR-T2-HOOK** *(G3; clarified v0.3 — R2-F1)* The serve hook is an **internal resolver function
  `resolve_serve_command`** (`benchmark_matrix/behavioral/contract.py`), **not** a method added to the
  `LanguageProfile` Protocol — adding a method would break `@runtime_checkable` `isinstance` gating for
  existing profiles (`languages/registry.py`). It returns the start command for a service of that
  language. Node implemented first (pilot); other languages fall back / are stubbed as not-implemented
  → degraded, never crash (FR-32).

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
  `CompositeScore` as an **added weighted term** at `FUNCTIONAL_WEIGHT` (*provisional 0.5 — R2-F3*; held
  at 0.5 now that the pilot proved discrimination, revisit per-service before full fold-in). **Only the
  compile gate floors** *(clarified v0.3 — R2-F2; supersedes "sandbox-violation floors")*: a
  sandbox/environment failure **degrades** the functional term (`functional_degraded=True`, FR-T2-2) and
  retains the structural base — it is **not** floored to 0. Weight set so a behaviorally-incomplete
  service ranks below a complete one. Services with no behavioral analyzer remain scored on the existing
  terms (honest partial coverage), flagged in the report.
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

*v0.3 — Post-implementation reconciliation. The harness shipped (M-T2.1..M-T2.4) and grew to 7 suites
across 3 transports (gRPC/GraphQL/REST); the pilot decision gate (FR-T2-PILOT) passed. The recovered
3-round CRP review (orphaned commit `ed478cae`, re-attached 2026-06-18) is now **triaged** into Appendix
A/B. Net: most suggestions were already applied in v0.2; three remain genuine open work — R2-S1
(functional aggregation column), R3-S1/R1-F2 (incremental/atomic persistence), and R3-F3/R3-S3
(behavioral hallucinated-dep flooring) — kept live in Appendix C and §0c.*

<!-- v0.3 2026-06-19 — CRP review log TRIAGED. The 3-round dual-document review (R1 gemini-3.1-pro,
R2 composer-2.5, R3 claude-3-5-sonnet; 2026-06-15), recovered from orphaned commit ed478cae and
re-attached onto the v0.2 core, is now dispositioned: Appendix A (applied) and Appendix B (rejected)
are filled; genuinely-open accepted items remain visible in Appendix C and are summarized in §0c.
Per the CRP "do not delete A/B" principle, A/B are append-only cross-model memory. -->

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
| R1-F1 | Clarify loopback binding scope (IPv6/localhost vs 127.0.0.1) | R1 gemini-3.1-pro | Clarified in FR-T2-SEC (v0.3): suites/readiness bind IPv4 `127.0.0.1`; `::1`/`localhost` not specially provisioned, IPv6-only bind degrades honestly. | 2026-06-19 |
| R1-F3 | Clarify readiness-timeout contract (fixed vs declarable) | R1 gemini-3.1-pro | Clarified in FR-T2-1 (v0.3): fixed **30s global** in `execute.py`; per-contract declarable budget deferred to FR-T2-CONTRACT. | 2026-06-19 |
| R2-F1 | HOOK must be an internal `resolve_serve_command` resolver, not a `LanguageProfile` method | R2 composer-2.5 | FR-T2-HOOK reworded (v0.3) to match shipped `behavioral/contract.py:resolve_serve_command`; Protocol unchanged (preserves `@runtime_checkable` gating). | 2026-06-19 |
| R2-F2 | Remove sandbox-violation flooring; degrade instead (FR-T2-2) | R2 composer-2.5 | FR-T2-COMPOSITE reworded (v0.3): only the compile gate floors; sandbox/env failure sets `functional_degraded=True` and retains structural base. Matches `scoring.py`. | 2026-06-19 |
| R2-F3 | Document FUNCTIONAL_WEIGHT=0.5 as provisional (shadow vs committed) | R2 composer-2.5 | FR-T2-COMPOSITE notes the 0.5 weight is provisional; held now that the pilot proved discrimination, revisit per-service. | 2026-06-19 |
| R3-F2 / R3-S2 | Mandate strict per-RPC client timeouts | R3 claude-3-5-sonnet | Implemented: every suite enforces `timeout=` on each RPC (`pricing_suite.py`, `charge_suite.py`, et al.); a hanging server fails the suite and teardown still runs. | 2026-06-19 |
| R1-S4 | Parse missing-module from stderr into provenance | R1 gemini-3.1-pro | Implemented: `execute.py` regex-extracts `Cannot find module '<x>'` → `provenance["missing_module"]`; `scoring.py` parses `No module named` for the compile path. | 2026-06-19 |
| R1-S3 | Explicit egress-denial test (external IP fails, loopback succeeds) | R1 gemini-3.1-pro | Implemented: `test_benchmark_sandbox_service.py::test_loopback_profile_allows_localhost_denies_egress`. | 2026-06-19 |
| R1-S1 | Durable batch root + cells.json/report.md (away from $TMPDIR) | R1 gemini-3.1-pro | Implemented (FR-T2-PERSIST core): `run_behavioral_pilot.py` writes `cells.json`+`report.md` under a caller-provided `batch_root`; `rescore_behavioral.py` re-scores from it. (Incremental flush is the open R3-S1 below.) | 2026-06-19 |
| R1-S2 | Multi-path proto provisioning + degrade on missing | R1 gemini-3.1-pro | Implemented: `provision.py`/`provision_workdir` place the proto at conventional paths; missing → degrade with attempted path in provenance. | 2026-06-19 |
| R3-F3 | Floor model-caused (off-contract dep) launch failures, don't degrade | R3 claude-3-5-sonnet | Implemented (commit `46134128`): `execute._is_off_contract_dep` classifies a missing module vs the wire contract → `BehavioralResult.model_fault`; runner threads `functional_model_fault` to `scoring.compute_composite`, which floors to `COMPILE_FLOOR`. Resolves the inversion (off-contract `express` now 0.15 < an honest-but-failing service's 0.5). Tests in `test_benchmark_functional_composite.py` + `test_execute_dep_classification.py`. | 2026-06-19 |
| R1-F2 | Partial-run durability — incremental/atomic per-cell flush | R1 gemini-3.1-pro | Implemented (commit `46134128`): `runner.persist_cell_atomic` writes `cells/<id>.json` (tmp+`os.replace`) per cell via `run_matrix(on_cell=)`; a mid-run crash leaves completed cells on disk. Test `test_incremental_persist_survives_midrun_crash`. | 2026-06-19 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | — | No suggestion was rejected outright — every R1/R2/R3 item was applied or clarified. | 2026-06-19 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

> **Triage status (v0.3, updated 2026-06-19):** All R1/R2/R3 items are now dispositioned **Applied**
> (Appendix A) or folded in as clarifications — none remain open. Post-triage implementation landed in
> two commits: `46134128` (R3-F3/R3-S3, R2-S1, R3-S1/R1-F2) and `52695f61` (R2-S2 hardcoded-port
> detection, R2-S3 known-broken fixture). The only remaining follow-up is operational, not a spec gap:
> re-render an existing behavioral batch's `report.md` to surface the R2-S1 functional column (needs a
> persisted batch). The original round blocks are preserved verbatim below.

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
