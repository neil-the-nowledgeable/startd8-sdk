# Functional-Correctness Scoring Term — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-14
**Status:** Planning complete; two-track scope (Track 1 buildable now, Track 2 deferred)
**Owner SDK area:** `startd8.benchmark_matrix` (scoring + analysis/execution) + `startd8.languages`
**Consumers:** Summer 2026 benchmark (the discriminating signal Round 1 lacks)

---

## 0. Planning Insights (Self-Reflective Update)

> Changes between v0.1 (pre-planning) and v0.2. The planning pass explored `sandbox.py`,
> `languages/protocol.py`, and the benchmark seeds, and found the v0.1 single-path
> (run-the-service) design is partly **blocked** and partly **deferrable** — yielding a two-track split.

| v0.1 assumption | Planning discovery | Impact |
|---|---|---|
| Execute the service as a **gRPC server + client** (FR-F3) | `benchmark_matrix/sandbox.py` is **one-shot** (`subprocess.run` + wall timeout) — no long-lived server + client model. | Server execution needs a **real sandbox extension** (Popen server, run client, guaranteed kill). Heavy → **Track 2 (deferred)**. |
| The harness can **start** any generated service (FR-F3/OQ-F3) | The seed fixes only `target_files` + language; **no startup/port/entrypoint contract** — the model chose freely. | Uniform startup is **impossible without mandating a startup contract in the seeds** → a **benchmark re-run** with new seeds. Deferred to Track 2. |
| `LanguageProfile` likely exposes a run/serve hook (OQ-F6) | It exposes `test_command` (the model's **own** tests — excluded, self-grading) and `syntax_check_command`, but **no serve command**. | Track 2 needs a **new per-language run hook**; not free. |
| Behavioral execution is the (only) path to functional signal | A **static, contract-aware spec-coverage** analysis (RPCs implemented, proto fields handled, input validation present) discriminates **without execution**, needs **no re-run**, and is **$0 re-scoreable on the existing run**. | New **Track 1**: a static functional term, buildable **now** against existing artifacts. Weaker than execution but available and honest. |
| `currencyservice` is a "pure" pilot (OQ-F2) | Currency `Convert` needs **exchange-rate data** (stateful). **`paymentservice.Charge`** is the truly pure RPC (input → transaction_id, Luhn/expiry only). | Track 2 pilot = **paymentservice**, not currency. |
| Functional **replaces** structural as primary (OQ-F4) | While the term is partial (Track 1 static, or Track 2 pilot-only), replacing would mis-rank services with no functional coverage. | Functional is an **added weighted term** alongside structural; revisit replacement once Track 2 has broad coverage. |

**Resolved open questions**
- **OQ-F1 →** split: Track 1 = static contract analysis (no execution); Track 2 = gRPC server+client (deferred).
- **OQ-F2 →** paymentservice (`Charge`) is the pure pilot; currency/cart/catalog are stateful (need pinned data).
- **OQ-F3 →** no startup contract exists; Track 2 must add one to the seeds (⇒ re-run). Deferred decision.
- **OQ-F4 →** added weighted term, not a replacement (while partial).
- **OQ-F5 →** sandbox is one-shot; long-lived server+client + kill/cleanup is a Track-2 extension.
- **OQ-F6 →** `LanguageProfile` has `test_command` (excluded) but no serve hook; Track 2 adds one.
- **OQ-F7 →** Track 1 is **$0** (static, re-score existing run, no per-cell exec); Track 2 adds startup + RPC time per cell (a budget item, deferred).

---

## 1. Problem Statement

Round 1 saturates: every model scores ~1.000. Structural compliance saturates, and the compile
gate saturates where it fires — **compilability is not a frontier discriminator.** The only signal
that can separate frontier models is **functional correctness**: does the generated service
implement the proto contract and *behave* correctly. Today nothing checks behavior at all.

### Gap table

| Dimension | Current term | Discriminates frontier? |
|-----------|--------------|-------------------------|
| Structure | `structural_quality` | No — saturates |
| Buildability | compile gate | No — saturates where it fires |
| **Behavior (static contract coverage)** | **none → Track 1** | **Partially — buildable now, $0** |
| **Behavior (executed)** | **none → Track 2** | **Yes — but blocked/expensive (deferred)** |

---

## 2. Requirements

### Track 1 — static contract-coverage term (buildable now, $0, no execution)
- **FR-F1.** Add a **functional-coverage term** to the composite (FR-11): score each service on how
  completely it implements its `demo.proto` contract — **every RPC implemented**, **request/response
  message fields referenced**, **declared input validation present** — by static analysis of the
  generated source (AST / structural, per language).
- **FR-F2.** Derived from `demo.proto` (the fixed contract) — model-agnostic, deterministic.
- **FR-F11.** **$0 re-scoreable:** runs against the existing run's artifacts via the shipped
  re-score path (no regeneration, no execution).
- **FR-F7.** Composite: functional-coverage is an **added weighted term** (gate floors still apply);
  define the weight so a partially-implemented service ranks below a complete one.
- **FR-F8.** **Degrade honestly (FR-32):** a service/language with no analyzer → recorded degraded,
  not 0.
- **FR-F10.** **Pilot:** start with multi-RPC services where coverage varies (catalog/cart/shipping)
  to confirm discrimination before wiring all 9.

### Track 2 — executed behavioral term (deferred; the gold standard)
- **FR-F3.** Per-service execution harness: start the generated service, gRPC client invokes each
  RPC, collect pass/fail. **Requires** FR-F5 + FR-F6 + a startup contract.
- **FR-F4.** Runtime deps from the SDK-committed vendored bundle (gRPC/protobuf + stubs), offline.
- **FR-F5.** **Sandbox execution escalation:** long-lived server + loopback client, CPU/mem/proc/wall
  limits, guaranteed kill/cleanup, ephemeral workspace, no fs escape — extends today's one-shot model.
- **FR-F6.** **Startup contract** in the seeds (fixed run command + port) + a new `LanguageProfile`
  run hook. **Implies a benchmark re-run.**
- **FR-F9.** **Provenance:** harness + suite version, per-RPC results, timings, isolation level,
  available-vs-degraded — for both tracks.

---

## 3. Non-Requirements

- **Not** load/performance testing — behavior only.
- **Not** grading model-written tests (self-grading; OQ-11) — SDK-authored suite.
- **Not** full multi-service Online Boutique integration — single service, deps pinned/mocked.
- **Not** every service in v1 — pilot then expand.
- **Not** replacing the compile gate — functional builds on top of it.
- **Track 2 is explicitly out of immediate scope** — deferred behind a sandbox extension + a re-run.

## 4. Implementation Plan (phased)

| Phase | Track | Deliverable | Gate |
|---|---|---|---|
| **FT-1** | 1 | `proto_contract.py`: parse `demo.proto` → per-service {RPCs, message fields}. Pure, tested. | — |
| **FT-2** | 1 | Per-language coverage analyzer (RPC-method + field presence) reusing existing AST/structural extractors; `functional_coverage ∈ [0,1]`. | reuse `languages/` parsers |
| **FT-3** | 1 | Fold into composite (FR-F7) + `$0` re-score the existing run (FR-F11); confirm discrimination. | **decision: weight** |
| **FT-4** | 1 | Provenance + honest degrade + leaderboard "functional" column. | — |
| **FT-5** | 2 | *Deferred.* Sandbox execution escalation (FR-F5) + startup contract + run hook + paymentservice pilot + re-run. | **decision: re-run + budget** |

## 4a. Validation Finding (falsifies Track 1 — $0 spike on the existing run)

> A $0 spike on `run-20260614T0505` (6 models that ran) tested Track 1's premise **before**
> building it. Result: **Track 1 as specified does not discriminate.**

- **RPC-presence coverage saturates:** all 6 models implement **100% of every service's proto
  RPCs** (cart 3/3, catalog 3/3, shipping 2/2, currency 2/2, payment 1/1 — every model). A
  coverage term adds another column of 1.000.
- **Finer static signals vary but are untrustworthy:** payment validation richness differs (luhn
  mentions 0–5, brand 0–5, LOC 128–244), **but the correctness *direction* is unknowable
  statically** — the reference OB payment is a thin mock, so "more validation" may be gold-plating.
  A richness-count metric rewards verbosity and is gameable.

**Conclusion:** static analysis cannot trustworthily separate frontier models on this task; the
variance has no reliable correctness direction without **behavioral ground truth**. **⇒ Do NOT
build Track 1.** Same lesson as compile-gate Tier-2 (P4): at the frontier, buildability/completeness
saturate; only *correctness* discriminates, and correctness is behavioral.

## 5. Open Decisions (user)
- **D0 (supersedes D1).** Track 1 is falsified. Real fork: **(a)** Track 2 behavioral execution
  (sandbox extension + startup contract + re-run — the only trustworthy discriminator); **(b)**
  a **harder task** so non-behavioral signals re-discriminate (cheaper — new seeds + re-run);
  **(c)** accept frontier-quality saturation and publish Round 1 on **cost / coverage /
  catastrophic-rate** (the axes that vary), quality disclosed as a frontier tie. Also evaluate
  **reference-similarity metrics (CodeBLEU)** — see the open question below.
- **D2.** Track-2 commitment — only if behavioral discrimination is worth the re-run + sandbox cost.

---

*v0.2 — Post-planning self-reflective update. 1 path split into 2 tracks (1 buildable now / 1
deferred), 7 open questions resolved, pilot service corrected (payment, not currency), a $0
static-coverage term added that the v0.1 draft missed.*
