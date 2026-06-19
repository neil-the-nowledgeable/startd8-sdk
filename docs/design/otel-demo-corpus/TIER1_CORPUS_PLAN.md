# Tier 1 — OTel Demo Corpus & Pattern Coverage — Implementation Plan

**Version:** 0.2 (Post-reflection — aligned to requirements v0.2)
**Date:** 2026-06-18
**Status:** Pre-implementation
**Requirements:** [TIER1_CORPUS_REQUIREMENTS.md](./TIER1_CORPUS_REQUIREMENTS.md)
**Depends on:** Tier 0 (`startup-capture.json`, `coverage-attestation.json`) + `OTEL_DEMO_SEED_EXTRACTION_PLAN.md`

---

## 1. Planning discoveries (fed the requirements §0)

| # | Discovery (file evidence) | Requirement moved |
| --- | --- | --- |
| D-1 | `behavioral/provision.py` provisions **Python/Go/Node** only; Java/C# **degrade** (`_TOOLCHAIN`, FR-32). | FR-6 (behavioral eligibility) |
| D-2 | Track-2 sandbox is **egress-denied** (`provision.py` docstring; `behavioral/execute.py`); no broker/DB. Kafka services are **consumers, not gRPC servers**. | NR-2, FR-4 (messaging ≠ cell) |
| D-3 | Existing behavioral suites (`charge_suite`, `currency_suite`, `pricing_suite`, `ad_suite`, `shipping_suite`) are all **leaf** services — live-dependency services can't run in-sandbox. | FR-6 (dependency-free clause) |
| D-4 | `gen_ob_benchmark_seeds.py` is a curated `SERVICES` list + proto embed + byte-stable `--check`; seeds are pure JSON consumed by the matrix. | FR-1, FR-8, QW-4 |
| D-5 | `contract.py` `StartupContract.from_seed` reads an optional `startup` block; Node/Go defaults exist, else **degrade**. | FR-2 (consume Tier-0 capture) |
| D-6 | `firewall.py` `BANNED_CORPUS_TOKENS` already bans `otel`, `opentelemetry`, `online boutique`, `microservices-demo`. | FR-5 (contamination reuse) |
| D-7 | `_PROTOCOL_METRICS`/`_OTEL_SDK_MAP` are **not in this repo** (sibling ContextCore). | NR-5, FR-7 (emit inputs only) |
| D-8 | Tier-0 `coverage-attestation.json` §4 rows already evidence §5.4/5.5/5.6 live. | FR-4 (verify, not build) |

**Reflection verdict:** Tier 1 shrank dramatically — one quick-win (Kafka cell) is impossible, three (1.1–1.3 "coverage") are already done by Tier 0, one (1.4) is already specced, one (1.5) is deferred. The residual real work is: build the structural generator, consume Tier-0 outputs, gate contamination, report per-corpus. > 50% revision — the loop earning its keep before any code.

---

## 2. Approach overview

```
scripts/
└── gen_otel_benchmark_seeds.py     # S1: copy of gen_ob + data swap + --check (FR-1/FR-8)
docs/design/model-benchmark/
└── seeds-otel/                     # S1 output
    ├── demo.proto                  # vendored oteldemo proto (pinned sha)
    ├── seed-<svc>.json             # 7 covered services
    └── seeds-index.json            # sha-indexed, byte-stable
docs/design/otel-demo-corpus/
├── contamination-otel.md           # S5: per-corpus index + no-pool assertion (FR-5)
└── derivation-handoff.md           # S7: observed_names → ContextCore TODO (FR-7)
```

Nothing in the OTel Demo or the OB corpus is modified. The matrix runner is unchanged (FR-8).

---

## 3. Steps (traced to requirements)

### S1 — Generator (copy + data swap)  → FR-1, FR-8 (QW-4)
- Copy `gen_ob_benchmark_seeds.py` → `gen_otel_benchmark_seeds.py`. Swap: `SERVICES` (the 7 from the seed plan), `PROTO_PATH` → `seeds-otel/demo.proto` (oteldemo), `GENERATOR` string, corpus/attribution text, `SEEDS_DIR` → `seeds-otel/`.
- Keep the seed schema **byte-identical** to OB (the whole point — runner parity). Keep sorted-keys serialization + `--check` drift guard verbatim.

### S2 — Consume Tier-0 startup capture  → FR-2 (QW-2)
- Read Tier-0 `startup-capture.json`. For each `svc` in `SERVICES`, if a matching `startup` block exists, attach it to the seed (the generator already supports `svc["startup"]` → `seed["startup"]`, mirroring `build_seed`). Else omit → structural-only.
- Schema is already aligned (`contract.py StartupContract.from_seed` reads `cmd`/`port_env`/`readiness`).

### S3 — product-reviews flagship seed  → FR-3 (QW-1)
- Add `product-reviews` to `SERVICES`: language `python`, `proto_service` `ProductReviewService`, rpcs `["GetProductReviews", "GetAverageProductReviewScore"]` (**omit** `AskProductAIAssistant`), `deps` includes `"PostgreSQL (declared; not required at generation)"`, `target_file` per seed plan.
- `behavioral_eligible=false` (DB dep) — structural seed; behavioral degrades.

### S4 — behavioral-eligibility signal  → FR-6
- Compute per-seed `behavioral_eligible = language in {python,go,nodejs} and not has_runtime_dep(svc)`, where `has_runtime_dep` is true for any downstream gRPC / DB / broker dep.
- Resulting flags: `payment`=true, `product-catalog`=true (file-backed leaf), `recommendation`=false (downstream gRPC), `checkout`=false (6 deps), `product-reviews`=false (DB), `cart`=false (C#), `ad`=false (Java). Record in `service_metadata`.

### S5 — Contamination gate + per-corpus report  → FR-5, NR-7 (QW-3)
- Register corpus name with the FR-47 perturbation/rename probe; reuse `firewall.py` `BANNED_CORPUS_TOKENS` (already bans OTel tokens).
- Emit `contamination-otel.md`: per-corpus index; explicit assertion that OTel and OB results are reported separately (no pooled leaderboard).

### S6 — Selection wiring + parity check  → FR-8, FR-1
- Verify the matrix/runner takes a seeds dir as a parameter (not hardcoded); run a **dry-run** targeting `seeds-otel/` and confirm 7 cells at $0 with no runner code change.
- Wire `gen_otel_benchmark_seeds.py --check` into the same CI guard pattern as OB.

### S7 — Derivation handoff doc  → FR-7 (QW-5)
- Write `derivation-handoff.md`: copy the messaging/db/flag `observed_names` from Tier-0's `coverage-attestation.json` and frame them as the input contract for a ContextCore `_PROTOCOL_METRICS`/`_DATABASE_IMPORT_PATTERNS` extension. Mark explicitly **cross-repo / out of scope here** (NR-5).
- Record the §5.4/5.5/5.6 pattern-coverage cross-reference to the Tier-0 attestation (FR-4).

### S8 — Validation  → Acceptance §4
- A1/A2: generate + `--check` exit 0; 7 seeds + index.
- A3: product-reviews seed shape correct, no AskProductAIAssistant.
- A4: `behavioral_eligible` flags match S4 table.
- A5: matrix dry-run on `seeds-otel/` → 7 cells, $0, no runner diff.
- A6: contamination index emitted; grep for a no-pool assertion.
- A7/A8: cross-reference + handoff docs present.

---

## 4. Requirement → step traceability

| Requirement | Step(s) |
| --- | --- |
| FR-1 generator | S1 |
| FR-2 consume startup-capture | S2 |
| FR-3 product-reviews | S3 |
| FR-4 pattern coverage = verify | S7 |
| FR-5 contamination + per-corpus | S5 |
| FR-6 behavioral eligibility | S4 |
| FR-7 derivation handoff | S7 |
| FR-8 selection wiring | S6 |
| Acceptance §4 | S8 |

No orphans: every FR has a step; every step traces to an FR or acceptance.

---

## 5. Sequencing & effort

| Order | Step | Effort | Depends on |
| --- | --- | --- | --- |
| 1 | S1 generator + S3 product-reviews | ~½ day | seed plan (data) |
| 2 | S4 behavioral-eligibility | ~1 hr | S1 |
| 3 | S2 consume startup-capture | ~1 hr | **Tier 0 FR-7** |
| 4 | S5 contamination + S7 handoff | ~½ day | S1; Tier-0 attestation |
| 5 | S6 selection wiring + S8 validation | ~½ hr | all |

Critical path ≈ **1–1.5 days** of pure data/glue (no service code). **S2 is gated on Tier 0** producing `startup-capture.json`; without it, seeds ship structural-only and behavioral defers (honest degrade, not a blocker).

---

## 6. Risks

| Risk | Mitigation |
| --- | --- |
| Contamination (famous public repo) inflates scores | Per-corpus reporting + FR-47 probe (FR-5); never pool with OB (NR-7) |
| Behavioral cells silently score 0 on missing toolchain/DB | Degrade-not-zero is the harness default (`provision.py`/`contract.py`); `behavioral_eligible` flag sets expectations (FR-6) |
| Seed schema drifts from OB → runner breaks | Byte-identical schema + `--check` guard (FR-1) |
| Tier 0 startup-capture late/absent | Structural-only fallback (FR-2/OQ-1); behavioral is additive |
| Over-claiming "messaging/SQL coverage" as corpus | Reframed: attestation (Tier 0) + derivation handoff (FR-7), explicitly not cells (NR-2/NR-3) |

---

## 7. Phase 5 — Convergent Review offer

The requirements (v0.2) and this plan are aligned and traceable. Recommended before implementation: a **Convergent Review (`/new-cnvrg-rvw-prmpt`)** dual-document pass — the reflective loop fixed wrong *assumptions* (Kafka ROI, coverage already done); CRP would catch missing *concerns* — e.g. whether `behavioral_eligible` needs a richer dependency taxonomy, contamination-probe sufficiency for a memorized repo, and whether the FR-7 cross-repo handoff needs an owned schema before it's useful. That review would likely produce a v0.3.
