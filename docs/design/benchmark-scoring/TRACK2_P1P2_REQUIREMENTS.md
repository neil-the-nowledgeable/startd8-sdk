# Track 2 P1+P2 — Generalized Dep Provisioning + Polyglot Stateless Breadth (Requirements)

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-15
**Status:** Draft
**Scope:** the curated P1+P2 slice of `TRACK2_M5_EXPANSION_SCOPING.md`. Builds on the merged pilot.
**Paired plan:** `TRACK2_P1P2_PLAN.md`.

---

## 0. Planning Insights (Self-Reflective Update)

> Planning against `languages/`, the seeds, `demo.proto`, and the pilot artifacts falsified two core
> v0.1 assumptions — one in each phase — flipping the design. >30% revised: the loop working.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| FR-P1-1: install each cell's **declared** deps fixes provisioning | The pilot's Node services declare **zero** deps (`payment package.json deps: <none>`) yet require pino/uuid/pino-pretty — they `require()` undeclared modules | **FR-P1-1 alone installs nothing useful.** The **curated common set (FR-P1-2) is primary**; declared-install is a secondary top-up. |
| Provisioning is one uniform "install declared deps" step | It's **language-specific**: Go `go mod tidy` derives deps **from imports** (self-provisioning, no manifest needed); Node/Python need the common set (managers only install *declared*); Java gradle resolves `build.gradle` | Split FR-P1 into a **per-language provisioning strategy** (FR-P1-1a). |
| FR-P2-2: `Convert`/`GetQuote` have **crisp** ground truth | Crisp only with **pinned service-specific data** (ECB rates / quote formula) the proto does **not** fix. Charge was crisp via a **universal** standard (Luhn/expiry), not service data | **Author suites around behavioral INVARIANTS** (identity conversion, validation/rejection, non-negativity, determinism, count limits) — not exact values that need pinned data. |
| Toolchains may be absent → many degrades | **All present** on host (node/npm/go/java 26/dotnet 10/pip) | FR-P1-5 (toolchain-absent degrade) still required for portability, but won't trigger here. (Note: Go uses `go version`, not `--version`.) |
| `LanguageProfile` may expose a serve/dep hook | Has `build_file_patterns`, `test_command`, `generate_dependency_file` — **no serve hook** | FR-P2-1 additive resolver confirmed; `build_file_patterns`/`generate_dependency_file` are reusable for provisioning. |

**Resolved open questions:**
- **OQ-1/OQ-6 → declared-install is insufficient (models under-declare); go with a language-specific
  strategy** (Go=`go mod tidy` from imports; Node/Python=curated common set [+ optional import-scan];
  Java=gradle from `build.gradle`), common set primary.
- **OQ-2 → all toolchains present;** degrade path kept for portability only.
- **OQ-3 → Go `go mod tidy` + `go run` (compile-on-run); Java gradle/`javac`+`java`.** Build cost is
  real per cell → cache module/build dirs (FR-P1-6).
- **OQ-4 → stateless RPCs lack universal ground truth → invariant-based suites** (the big P2 change).
- **OQ-5 → `node_runtime/` stays** as the Node common-set offline cache; declared-install layers on top.

---

## 1. Problem Statement

The paymentservice pilot proved behavior discriminates flagships (Opus 1.0 vs gpt-5.5/gemini 0.33),
but it works for exactly **one service, one language (Node), one RPC** and relies on a **hand-vendored
fixed dependency closure** (we hit pino→uuid→pino-pretty by hand). To expand even a little, two things
must generalize: **how dependencies get provisioned** (P1) and **how non-Node services are launched +
behaviorally scored** (P2). This slice proves behavioral scoring is **polyglot** on a **curated set of
stateless, plausibly-discriminating RPCs** — without committing to all 9 services or stateful/orchestration.

| Component | Current State | Gap |
|-----------|--------------|-----|
| Dep provisioning | hand-vendored fixed Node closure (`node_runtime/`) | doesn't scale; no per-cell declared-dep install; no Go/Python/Java |
| Serve hooks | Node only (`contract._DEFAULTS`) | no Go / Java launch |
| Suites | `charge_suite.py` (payment) | no shipping/ad/currency suites |
| Seeds | startup contract on paymentservice only | shipping/ad/currency lack startup blocks |

## 2. Requirements

### P1 — Generalized dependency provisioning
- **FR-P1-1** *(revised — D1)* The **curated common set is the primary mechanism**: provision a generous
  per-language runtime set at **prepare time** that covers what models `require`/`import` but routinely
  **don't declare** (the pilot proved Node services declare nothing yet need pino/uuid/pino-pretty). The
  gRPC/proto runtime + common logging/util libs per language. Declared-manifest install is a **secondary
  top-up**, not the foundation.
- **FR-P1-1a** *(new — D1)* Provisioning is **language-specific**, exploiting each toolchain's native
  dep resolution where it derives from source:
  - **Go** — `go mod tidy` (derives deps **from imports**, self-provisioning) then build/run; common set = grpc/protobuf modules as a fallback.
  - **Node** — copy/install the curated common set (npm only installs *declared*, which is empty); declared `package.json` deps installed on top.
  - **Python** — install the curated common set (grpcio/protobuf) + `requirements.txt` if present.
  - **Java** — gradle resolves `build.gradle`; common set = grpc-java fallback.
- **FR-P1-2** *(narrowed)* The curated common set per language is **maintained, versioned, and offline-cacheable**
  (Node keeps `node_runtime/`; analogous caches for other languages) so repeated cells/$0-rescores don't refetch.
- **FR-P1-3** **Dependency quarantine preserved:** provisioning (network) happens at prepare time only;
  the scored server run stays egress-denied (loopback-only sandbox). *(Assumption: prepare runs outside
  the sandbox, so it may use the network — confirm.)*
- **FR-P1-4** **Honest degrade (FR-T2-DEPS2, all languages):** a server that still fails to start records
  the missing module/package + degrades (never scored 0).
- **FR-P1-5** **Toolchain-absent → degrade (FR-32):** if a language's package manager (npm/go/pip/dotnet)
  isn't installed on the host, the cell degrades with that reason — not scored 0.
- **FR-P1-6** Provisioning is **idempotent/cacheable**: a $0 re-score must not re-install when deps are
  already present; provisioning cost is paid once per cell workdir.

### P2 — Polyglot stateless breadth
- **FR-P2-1** Add **additive** per-language serve resolvers for **Go** and **Java** (Node exists) — NOT
  on the `LanguageProfile` Protocol (it's `@runtime_checkable` + isinstance-gated). Each returns a launch
  command with PORT injection + TCP readiness.
- **FR-P2-2** *(revised — D4)* SDK-authored behavioral suites assert **invariants checkable without
  service-specific ground-truth data** (the proto pins neither rates nor formulas). Curated RPCs:
  - `currencyservice.Convert` (Node) — **identity** (USD→USD returns the same amount, rate-independent),
    **unknown currency code → error**, **negative/zero handling**, **determinism** (same input → same out).
  - `shippingservice.GetQuote` (Go) — **non-negative** quote, **valid currency code**, **determinism**,
    quote present for a valid cart.
  - `adservice.GetAds` (Java) — **returns ≥1 ad**, ads **non-empty**, **respects any requested count**.
  These mirror how Charge worked (validation invariants, not exact transaction values), so they
  discriminate a correct impl from a careless one **without** needing pinned data.
- **FR-P2-3** Add **startup contracts** to the shipping/ad/currency seeds (via the generator; byte-stable).
- **FR-P2-4** **Pilot-each-once:** before funding N reps × roster, run each new RPC **once** across the
  roster to confirm it actually discriminates (curated path); only then scale.
- **FR-P2-5** *(reframed — D4)* **Invariant-not-verbosity:** suites score on *invariants satisfied*, never
  on output volume (the Track 1 verbosity trap). An RPC whose invariants all pass for every model
  (saturates) is reported as **non-discriminating** (drop it / find a sharper invariant) rather than
  inflating coverage. Convert's identity+validation set is the strongest expected discriminator; GetAds
  is the weakest (flag if it saturates).

### Carried-forward (unchanged)
- **FR-P-CF1** degrade-not-zero (FR-T2-2); persist-then-$0-rescore; composite functional term already wired;
  behavioral scoring is $0/re-runnable (generation is the only real spend).

## 3. Non-Requirements
- **NR-1** Not all 9 services — curated stateless RPCs only.
- **NR-2** Stateful (cart/Redis), downstream-calling (recommendation), orchestration (checkout), and
  side-effect-only (email) RPCs are OUT (later phases).
- **NR-3** No C# / Python serve hooks here (cart=C#/stateful, email+recommendation=Python — later phases).
- **NR-4** No full Round-1 run; pilot-each-once + small N only.
- **NR-5** Not abandoning `node_runtime/` — it may remain the offline common-set cache (P1 decides).

## 4. Open Questions
*OQ-1..OQ-6 resolved during planning — see §0.* Remaining:
- **OQ-7** Go/Java **build cost per cell** (`go mod tidy`+compile, gradle) under the per-run timeout —
  may need a warmed module/build cache or a longer timeout for those cells.
- **OQ-8** Import-scan as a Node/Python top-up (parse `require`/`import` for undeclared deps and install
  them) — worth it, or does a generous common set suffice? (Lean common-set first; revisit if cells degrade.)
- **OQ-9** Whether `Convert` identity/validation invariants actually discriminate the flagships, or
  saturate like structural did — the pilot-each-once gate (FR-P2-4) answers this empirically before N.

---

*v0.2 — Post-planning self-reflective update. P1 inverted (common-set primary + per-language strategy,
not declared-install), P2 reframed (invariant-based suites, not pinned-data exact values), 6 OQs
resolved, 3 new ones opened. The two flips were each a single load-bearing assumption per phase — caught
at document cost.*
