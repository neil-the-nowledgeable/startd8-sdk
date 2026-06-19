# Tier 1 — OTel Demo Corpus & Pattern Coverage — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-18
**Status:** Reviewed-against-plan; pre-implementation
**Derived from:** [OTEL_DEMO_COVERAGE_QUICK_WINS.md](../OTEL_DEMO_COVERAGE_QUICK_WINS.md) Tier 1
**Companion plan:** [TIER1_CORPUS_PLAN.md](./TIER1_CORPUS_PLAN.md)
**Builds on:** [TIER0_REFERENCE_ENV_REQUIREMENTS.md](./TIER0_REFERENCE_ENV_REQUIREMENTS.md) (consumes its `startup-capture.json` + `coverage-attestation.json`)
**Pre-existing spec it operationalizes:** [OTEL_DEMO_SEED_EXTRACTION_PLAN.md](./OTEL_DEMO_SEED_EXTRACTION_PLAN.md)

---

## 0. Planning Insights (Self-Reflective Update)

> Planning Tier 1 against the actual benchmark harness (`src/startd8/benchmark_matrix/`, the seed
> generator, the Track-2 behavioral sandbox, and the contamination firewall) falsified **most** of
> the quick-wins framing. This is a large revision (>50% of v0.1) — the loop working: Tier 1 is far
> smaller and differently shaped than "close messaging/SQL/feature-flag sections."

| v0.1 assumption (from quick-wins Tier 1) | Planning discovery | Impact |
| --- | --- | --- |
| 1.1 Kafka messaging is the "best functional ROI." | The Track-2 sandbox (`behavioral/provision.py`, `execute.py`) is **egress-denied** with no broker; Kafka services (accounting, fraud-detection) are **consumers, not gRPC servers**. Messaging yields **zero benchmark cells** — structural *or* behavioral. | **FR-4 re-scopes** messaging/SQL/flag to *verification of Tier-0 attestation* + a *cross-repo derivation* follow-up. **NR-2** forbids messaging as a cell. |
| 1.1–1.3 "close" landscape §5.4/§5.5/§5.6. | **Tier 0's `coverage-attestation.json` already evidences these live** (its §4 acceptance rows). The sections are already closed for the coverage purpose. | **FR-4** turns 1.1–1.3 into an *assertion* against the Tier-0 attestation, not new build. |
| 1.4 needs a fresh plan. | It is **already fully specced** in `OTEL_DEMO_SEED_EXTRACTION_PLAN.md` (7 covered services, OQ-OT-1..5, byte-schema parity, contamination probe). | **FR-1 operationalizes** that plan; **NR-1** forbids re-speccing it. |
| All 5 covered languages get behavioral seeds. | `provision.py` provisions only **Python/Go/Node** securely; **Java/C# degrade** (FR-32, never 0). Worse, every existing behavioral suite is for a **leaf** service — services with live downstream/DB deps can't run in the sandbox. | **FR-6** restricts behavioral eligibility to *supported-language AND dependency-free* services; everything else ships **structural-only**. |
| 1.2 Postgres is a "service to add." | product-reviews/accounting need a **runtime DB**; the sandbox has none. Seed-plan OQ-OT-2 already says the DB dep must be **declarable, not required-at-generation**. | **FR-3** ships product-reviews as a **structural** seed (DB declared, behavioral degrades). |
| Derivation extension is in-repo. | `_PROTOCOL_METRICS`/`_OTEL_SDK_MAP`/`_DATABASE_IMPORT_PATTERNS` live in the **sibling ContextCore repo** (not in this tree). | **NR-5** + **FR-7**: emit the inputs (Tier-0 `observed_names`); document the ContextCore-side extension as a follow-up. |
| 1.5 Envoy/nginx is worth doing. | Infra proxies, not RPC services, not interesting telemetry for corpus or derivation. | **NR-6 defers** 1.5. |
| OTel and OB scores can share a leaderboard. | Seed-plan OQ-OT-5: different services → **not poolable**. `firewall.py` already bans `otel`/`opentelemetry`/`online boutique` tokens (contamination). | **FR-5** mandates per-corpus reporting + a no-pool guard; reuses the existing firewall. |

**Resolved open questions:**
- **OQ-OT-1 (behavioral startup) → resolved by Tier 0.** `startup-capture.json` (Tier-0 FR-7) supplies each service's serve/readiness; Tier 1 *consumes* it (FR-2).
- **OQ-OT-2 (product-reviews DB) → declarable, not required.** Structural seed; behavioral degrades (FR-3).
- **OQ-OT-5 (cross-corpus comparability) → per-corpus only.** No pooling (FR-5 / NR-7).

**Quick wins / functional low-hanging fruit surfaced by planning:**
- **QW-1 — product-reviews is the flagship.** It is the single *genuinely new* task (new Python service, low OB-overlap) — prioritize it over restating OB services.
- **QW-2 — behavioral startup is free.** Tier 0's `startup-capture.json` resolves OQ-OT-1; the generator just embeds it. No hand-derivation.
- **QW-3 — contamination gating is reuse, not build.** `firewall.py`'s `BANNED_CORPUS_TOKENS` + the FR-47 perturbation probe already exist; Tier 1 just registers the corpus + reports per-corpus.
- **QW-4 — `--check` byte-parity guard is free.** Copy `gen_ob_benchmark_seeds.py`'s `--check` mode → a $0 CI regression guard that seeds never drift.
- **QW-5 — pattern coverage is a cross-reference, not code.** Tier 0 already attests §5.4/5.5/5.6; Tier 1's "coverage" deliverable is a one-line attestation reference + a ContextCore TODO.
- **QW-6 — behavioral-eligibility flag is reusable corpus metadata.** Computing `behavioral_eligible` per seed (language + dependency-free) is cheap and tells the runner which cells can score Track-2 vs structural-only — useful beyond OTel.

---

## 1. Problem statement

Tier 1's headline ("close messaging/SQL/feature-flag sections, extract the 5-language corpus") is, after planning, **mostly already done or already planned**: Tier 0 attests the pattern sections live, and the seed extraction is specced in `OTEL_DEMO_SEED_EXTRACTION_PLAN.md`. The genuine, non-redundant Tier-1 work is to **operationalize the OTel-Demo *structural* benchmark corpus** (consuming Tier-0 outputs), **gate it for contamination**, **verify** the pattern coverage Tier 0 attests, and **hand off** the derivation extension to ContextCore.

| Component | Current state | Gap |
| --- | --- | --- |
| OTel-Demo seeds | `gen_ob_benchmark_seeds.py` (OB only); OTel generator specced but not built | No `seeds-otel/` corpus |
| Behavioral startup blocks | Tier-0 `startup-capture.json` (FR-7) | Generator doesn't consume it yet |
| Pattern coverage (§5.4/5.5/5.6) | Tier-0 attestation evidences them live | Not cross-referenced as "covered"; no derivation in ContextCore |
| Contamination | `firewall.py` bans OTel tokens; FR-47 probe exists | OTel corpus not registered/reported per-corpus |
| Behavioral eligibility | `provision.py` supports Python/Go/Node; suites are leaf-only | No per-seed `behavioral_eligible` signal |

**Goal:** a byte-stable, contamination-gated `seeds-otel/` **structural** corpus (with behavioral startup where Tier 0 supplied it and the service is dependency-free), reported strictly per-corpus, plus a documented ContextCore derivation handoff.

---

## 2. Requirements

### Corpus extraction

- **FR-1 — Operationalize `gen_otel_benchmark_seeds.py`.** Implement the generator per `OTEL_DEMO_SEED_EXTRACTION_PLAN.md`: copy the `gen_ob_benchmark_seeds.py` shape, swap the `SERVICES` list (7 covered), the proto (`oteldemo` `demo.proto` + its sha), corpus/attribution strings, and output dir (`seeds-otel/`). MUST be byte-stable with sorted keys and a `--check` drift guard (matching OB).
- **FR-2 — Consume Tier-0 `startup-capture.json`.** For each covered service, embed the `startup` block captured by Tier-0 FR-7 (resolves OQ-OT-1). Where no capture exists, the seed ships **structural-only** (no `startup`); behavioral degrades honestly (never errors).
- **FR-3 — product-reviews flagship seed (Python).** Ship `ProductReviewService` with RPCs `GetProductReviews` + `GetAverageProductReviewScore`; **omit `AskProductAIAssistant`** (LLM dep). The Postgres dependency MUST be **declared in `dependencies`, not required at generation**; behavioral execution degrades if no DB.
- **FR-8 — Selection wiring, zero runner change.** A benchmark run MUST be able to target `seeds-otel/` purely by pointing at the seeds dir (verify the dir is a parameter, not hardcoded). No change to `runner.py`/`scoring.py`/`aggregate.py`.

### Scope honesty

- **FR-6 — Behavioral-eligibility signal.** Each seed MUST carry a `behavioral_eligible` flag, true **iff** (a) language ∈ {python, go, nodejs} (the securely-provisioned set) **and** (b) the service has no required-at-runtime external dependency (downstream gRPC, DB, broker). All others ship **structural-only**. Java (`ad`) and C# (`cart`) are structural-only until secure provisioning lands.

### Coverage verification & contamination

- **FR-4 — Pattern coverage = verify, not build.** Tier 1 MUST assert (not re-implement) that Tier-0's `coverage-attestation.json` evidences §5.4 messaging, §5.5 database, §5.6 feature flags. The deliverable is a recorded cross-reference; NO new build for these sections.
- **FR-5 — Contamination gate + per-corpus reporting.** The OTel corpus MUST be registered with the FR-47 perturbation/rename probe and `firewall.py`, and a **per-corpus** contamination index emitted. Scores from OTel and OB MUST NOT be pooled into one leaderboard (OQ-OT-5).
- **FR-7 — Derivation handoff (emit inputs only).** Tier 1 MUST record the messaging/db/flag `observed_names` from Tier-0's attestation as the handoff payload for a ContextCore `_PROTOCOL_METRICS`/`_DATABASE_IMPORT_PATTERNS` extension. Building that extension is out of scope (NR-5).

---

## 3. Non-requirements

- **NR-1** — Does NOT re-spec the seed extraction (references `OTEL_DEMO_SEED_EXTRACTION_PLAN.md`).
- **NR-2** — Does NOT add Kafka/messaging as a benchmark cell (not RPC; egress-denied sandbox).
- **NR-3** — Does NOT build behavioral DB/broker stubs (Postgres-backed services degrade).
- **NR-4** — Does NOT modify the Track-2 sandbox or add Java/C# secure provisioning.
- **NR-5** — Does NOT extend ContextCore derivation tables (cross-repo; only emits inputs — FR-7).
- **NR-6** — Does NOT implement Envoy/nginx (quick-wins 1.5) — deferred (infra, low value).
- **NR-7** — Does NOT pool OTel + OB scores into one leaderboard.
- **NR-8** — Does NOT modify `gen_ob_benchmark_seeds.py` or the OB `seeds/`.

---

## 4. Acceptance

Tier 1 is "done" when:

| # | Acceptance criterion | Evidence |
| --- | --- | --- |
| A1 | `seeds-otel/` contains the 7 covered-service seeds + `seeds-index.json` | files present, sha-indexed |
| A2 | `gen_otel_benchmark_seeds.py --check` passes (byte-stable) | exit 0 |
| A3 | product-reviews seed present, Python, RPCs = {GetProductReviews, GetAverageProductReviewScore}, no AskProductAIAssistant | seed JSON |
| A4 | Every seed has a correct `behavioral_eligible` flag | payment/product-catalog = true (leaf, supported lang); cart/ad = false (lang); product-reviews = false (DB dep) |
| A5 | A matrix **dry-run** targets `seeds-otel/` with $0 and **0 runner code changes** | dry-run log: 7 cells |
| A6 | Per-corpus contamination index emitted; no OTel↔OB pooling | report + a no-pool assertion |
| A7 | Pattern-coverage cross-reference to Tier-0 attestation recorded (§5.4/5.5/5.6) | doc reference |
| A8 | Derivation handoff payload (observed_names) written for ContextCore | handoff note |

---

## 5. Open questions (remaining)

- **OQ-1** — For a covered service whose Tier-0 `startup-capture` is missing/ambiguous, ship structural-only or hand-derive a `startup`? **Lean:** structural-only for v1 (FR-2 default).
- **OQ-2** — product-reviews behavioral: build a tiny in-memory DB shim (small, but is "no service touched"-violating?) or degrade? **Lean:** degrade in v1; in-memory shim is a candidate Tier-1.5.
- **OQ-3** — Contamination: generate rename/perturbation seed variants now, or emit the index only? **Lean:** index-only v1; variants when a clean-room track is needed.

---

*v0.2 — Post-planning self-reflective update. 1.1 (Kafka cell) rejected, 1.5 deferred, 1.1–1.3 "coverage" reframed to verification (FR-4), 1.4 operationalized (FR-1), 3 new scope-honesty requirements added (FR-2/FR-6/FR-3), 3 open questions resolved, 6 quick wins surfaced. Tier 1 is materially smaller than the quick-wins framing implied.*
