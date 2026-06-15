# Track 2 P1+P2 — Implementation Plan

**Version:** 1.0 (paired with requirements v0.2)
**Date:** 2026-06-15
**Status:** Plan

> Built by planning against `languages/`, `benchmark_matrix/behavioral/`, the seeds, and `demo.proto`.
> Discoveries fed back into requirements §0. Provisioning is per-language; suites are invariant-based.

## Approach
Extend the proven pilot machinery. The Python gRPC client stubs are already generated from the **full**
`demo.proto` (`behavioral/demo_pb2*.py` has `CurrencyServiceStub`/`ShippingServiceStub`/`AdServiceStub`),
so new suites are language-agnostic over the wire — only the **serve hook** (per language) and the
**provisioning** (per language) are new. Pilot-each-once gates spend.

## Steps

### S1 — P1 provisioning (FR-P1-1/1a/2, FR-P1-4/5/6)
Generalize `behavioral/execute.py:prepare_node_workdir` → a per-language `provision_workdir(workdir,
language, target_files)` that runs at prepare time (network allowed; the *scored* run stays sandboxed):
- **Node** — keep the `node_runtime/` curated closure copy (current behavior); top-up declared `package.json`.
- **Go** — `go mod tidy` in the service dir (derives deps from imports) then `go build`; reuse a warmed
  `GOMODCACHE`/`GOCACHE` (FR-P1-6). Curated fallback = grpc/protobuf modules if tidy under-resolves.
- **Python** — `pip install` the curated set (grpcio, protobuf) into a venv/target + `requirements.txt` if present.
- **Java** — gradle build (resolves `build.gradle`); curated fallback = grpc-java.
Toolchain absent (`shutil.which`) → return degrade reason (FR-P1-5). Idempotent: skip if already provisioned.
- **Security (CRP R1 — FR-P1-SEC-1..5, blockers):** every install runs **scripts-disabled**
  (`npm install --ignore-scripts`, pip `--only-binary=:all:`, etc.), under a **scrubbed env** (reuse
  `sandbox.scrub_env` — no secrets), **fs-confined to the cell workdir**, with network restricted to
  package registries (allowlist). Use **lockfiles + integrity** (npm ci/`package-lock`, pip hashes,
  `go.sum`). Shared module caches mounted **read-only** with a **per-cell writable overlay** (no
  cross-cell poisoning). An offline run **fails closed → degrade** (never silently opens the network).
- *Files:* `behavioral/provision.py` (new) + `execute.run_behavioral_cell` calls it by `seed` language;
  `prepare_node_workdir` becomes the Node branch. Reuse `sandbox.scrub_env`; raise the per-cell timeout
  for Go/Java build (S-1 / OQ-7).

### S2 — P2 serve hooks (FR-P2-1)
Extend `behavioral/contract.py:_DEFAULTS` + `resolve_serve_command` (additive, NOT the Protocol) with:
- **Go** — `["go", "run", "<entry.go>"]` (or run the built binary from S1), PORT via env/arg.
- **Java** — gradle `run` or `["java", "-cp", "<build>", "<MainClass>"]`, PORT via env/arg.
Each keeps the seed `startup` contract authoritative; the default is the per-language fallback.
- *Tests:* command construction per language; unknown → None → degrade.

### S3 — P2 invariant suites (FR-P2-2/5)
New suites reusing the generated stubs, registered in `execute._SUITES` by service:
- `currency_suite.py` — `Convert`: identity (USD→USD == input), unknown code → error, negative/zero
  handling, determinism; `GetSupportedCurrencies`: non-empty list.
- `shipping_suite.py` — `GetQuote`: non-negative, valid currency code, deterministic.
- `ad_suite.py` — `GetAds`: ≥1 ad, non-empty text, respects requested count.
Each returns `SuiteResult` (coverage = invariants passed / total) like `charge_suite`. **No exact-value
asserts** (no pinned data). 
- *Tests:* a known-good + known-broken reference server per RPC (Python, over the wire) proving each
  suite **discriminates** (good=1.0, broken<1.0) — mirrors the charge_suite fixtures.

### S4 — P2 seeds (FR-P2-3)
Add `startup` blocks to shipping/ad/currency in `scripts/gen_ob_benchmark_seeds.py` (per-language run
cmd + PORT + tcp readiness); regenerate; `--check` byte-stable; update `test_ob_benchmark_seeds`.

### S5 — Pilot-each-once + discrimination gate (FR-P2-4)
Extend `scripts/run_behavioral_pilot.py` to accept `--service`/`--services` (default paymentservice) so
each new RPC runs **once across the roster** first; the report flags an RPC as **non-discriminating** if
all models pass all invariants (saturated) — the signal to drop it or sharpen the invariant before N.

### S6 — $0 re-score unaffected
`rescore_behavioral.py` already iterates `cells.json` by service → picks up new suites for free; no change.

## Risks
- **Build cost/timeout (OQ-7):** Go `go mod tidy`+build and Java gradle can exceed the per-cell timeout
  on a cold cache → warm `GOMODCACHE`/gradle cache + raise timeout for those languages.
- **Invariant saturation (OQ-9):** the curated invariants may all pass for every flagship (non-
  discriminating) — that's the FR-P2-4 gate doing its job; report and drop, don't inflate coverage.
- **Provisioning network at prepare:** confirmed prepare runs *before* `run_service_sandboxed` (the only
  sandboxed step), so install network use is fine; assert the scored run is still egress-denied.
- **Cross-language wire compat:** the Python client + a polyglot server must agree on the proto — they
  do (same `demo.proto`); the model's server-side stub generation is its own concern (+ common set).

## Test strategy
Unit (no LLM): provisioning per-language toolchain-absent degrade + common-set present; serve-command
construction (Go/Java); each suite vs known-good/known-broken reference server (discrimination proof);
seed byte-stability. Integration: pilot-each-once dry-run shape. No live-model test in CI.

## Sequencing
S1 (provisioning — unblocks all) → S2 + S3 (serve hooks + suites, per language, parallelizable) →
S4 (seeds) → S5 (pilot-each-once). Land one language end-to-end (Go/shipping) first as a vertical slice,
then the others.

## Out of scope (this plan)
Stateful (cart/Redis), downstream (recommendation), orchestration (checkout), Python/C# serve hooks,
full Round-1 run — later phases (P3–P6).
