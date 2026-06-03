# Controlled Corpus v0 — Extraction Findings

**Date:** 2026-06-03
**Source trove:** `/Users/neilyashinsky/Documents/dev/online-boutique-demo/.cap-dev-pipe/pipeline-output/online-boutique/`
**Artifacts produced (reproducible, deterministic scripts):**
- `extract_corpus_v0.py` → `controlled-corpus-v0.json`
- `build_scr_replay_set.py` → `scr-variance-segregation.json`, `scr-labeled-replay-set.json`

This is the empirical foundation for the deterministic-English-transformation / controlled-corpus
program. Two tracks were run in parallel: (A) distill a v0 corpus from the trove; (B) segregate real
variance and build the SCR labeled replay set.

---

## Track B — Variance segregation (resolves the cached-vs-fresh caveat)

**Finding: the prior "consistent inputs" assumption is half-right and needs correction.**

- **37 runs with seeds; all 37 have DISTINCT `source_checksum`.** Seeds were *freshly re-derived* every
  run (NOT cached) — so cross-run consistency is genuine stochastic signal. **But** the inputs also
  *evolved across the dev phase* — these are not N runs of one frozen input.
- Runs partition into **input-scope clusters by feature count**: `{7:3, 10:1, 15:7, 17:21, 40:5}`.
  The clean determinism signal lives **within** a cluster.
- **Anchor = the 17-feature Python cluster (21 runs)** — the largest, most-repeated scope
  (emailservice + recommendationservice + shoppingassistantservice + loadgenerator).
- Model mix: 34 Claude-default + 3 Gemini (model inferred from run-id prefix; `run-*` runs do not
  record the model in `run-metadata.json` — documented caveat).

**Join-key correction (load-bearing):** `PI-NNN` ids are **positional**, not stable identities. Within
the 17-feature cluster, `PI-001` → `src/emailservice/logger.py` is stable across all runs incl. Gemini,
but its *title* drifts ("Shared JSON Logger — emailservice" vs "Email Service JSON Logger"). The replay
set therefore joins kaizen labels on **`target_file`**, not `PI-id`.

---

## Track B — The determinism oracle (`scr-labeled-replay-set.json`)

Per-`target_file` PASS/FAIL stability within the anchor cluster (49 labeled observations across the
runs kaizen-correlation covered; segregated by model):

| target_file | stability | n | title variants | class |
|---|---|---|---|---|
| emailservice/logger.py | 1.00 | 4 | 3 | deterministic_candidate |
| loadgenerator/locustfile.py | 1.00 | 4 | 1 | deterministic_candidate |
| emailservice/email_server.py | 1.00 | 3 | 2 | deterministic_candidate |
| emailservice/templates/confirmation.html | 1.00 | 3 | **7** | deterministic_candidate |
| recommendationservice/recommendation_server.py | 1.00 | 3 | 2 | deterministic_candidate |
| …(12 total at stab=1.0)… | | | | |
| emailservice/Dockerfile | 0.67 | 3 | 3 | residue_corpus_gap |
| loadgenerator/Dockerfile | 0.67 | 3 | 3 | residue_corpus_gap |
| shoppingassistantservice/Dockerfile | 0.67 | 3 | 3 | residue_corpus_gap |
| emailservice/email_client.py | 0.33 | 3 | 4 | residue_corpus_gap |
| **shoppingassistantservice/shoppingassistantservice.py** | **0.00** | 4 | 1 | residue_corpus_gap |

**12 deterministic candidates, 5 residue gaps.**

**The headline result — title-drift is orthogonal to stability — is direct empirical proof of the
corpus thesis:**
- `confirmation.html`: **stability 1.00 with 7 different titles.** The *binding* (construct) is perfectly
  deterministic while the natural-language label drifts maximally. → The corpus should key on the
  binding, discard the label. This file is a deterministic-provider candidate today.
- `shoppingassistantservice.py` (Flask RAG): **stability 0.00 with 1 stable title.** Consistent naming,
  consistently fails. → This is a genuine LLM-hard feature (real logic complexity / spec ambiguity),
  not a naming problem. It is the **corpus gap** that most needs design-intent enrichment — and exactly
  the kind of feature the SCR should always escalate.

This is the "which arrow to make deterministic next" prioritizer the program needs, derived from data:
high-stability features → promote to deterministic providers (the move we made on TRANSFORM);
low-stability features → corpus/spec gaps to close.

---

## Track A — Controlled corpus v0 (`controlled-corpus-v0.json`)

Four layers distilled from the trove:

**Layer 1 — Canonical terms (from `demo.proto`, package `hipstershop`):** 9 services, 15 RPCs, 32 entities.
- Services + RPCs: `CartService{AddItem,GetCart,EmptyCart}`, `ProductCatalogService{ListProducts,
  GetProduct,SearchProducts}`, `ShippingService{GetQuote,ShipOrder}`, `CurrencyService{GetSupportedCurrencies,
  Convert}`, `RecommendationService{ListRecommendations}`, `PaymentService{Charge}`,
  `EmailService{SendOrderConfirmation}`, `CheckoutService{PlaceOrder}`, `AdService{GetAds}`.
- Entities incl. `Money{currency_code,units,nanos}`, `Cart`, `CartItem`, `Product`, `Address`,
  `CreditCardInfo`, `Order*`, `Ad` — identical field schemas, language-agnostic by construction.

**Layer 2 — Explicit bindings (curated):** EXPLICIT-confidence `forward_manifest` contracts only
(228 of 1,883; the 1,655 `inferred` are excluded as noise). In the representative run: `config_key:77,
formula:59, render_pattern:79, infrastructure:13`. *(Caveat: this single run is config-heavy; explicit
`class_name`/`function_name` bindings exist in other clusters, e.g. the cartservice run — v0 should
aggregate explicit contracts across multiple seeds.)*

**Layer 3 — SRE/observability vocab:** metrics `rpc_server_duration_bucket/_count`,
`rpc_server_request_size_bucket`, `http_server_duration_*`; SLO targets `availability=99.9%`,
`latency_p99=500ms` *(note: 500ms in the actual SLO artifacts, not the 100ms quoted in an earlier
summary)*; alert patterns `{Service}LatencyP99High/ErrorRateHigh/AvailabilityLow`.

**Layer 4 — Determinism evidence:** merged from Track B (12 deterministic candidates, 5 residue gaps).

---

## Honest caveats / fidelity gaps (for v0.2)

1. **Small labeled overlap.** kaizen-correlation covered ~20 runs; only **49 labeled observations** fall
   in the 17-feature cluster with a target mapping. Enough to demonstrate the method; too small to set
   the SCR's X/Y success thresholds with confidence. Widening requires running the kaizen correlation
   over more of the 21-run cluster.
2. **Model imbalance.** 34 Claude vs 3 Gemini — cross-model determinism claims are Claude-dominated.
3. **Explicit-binding coverage is single-run.** Aggregate explicit contracts across clusters for a
   fuller binding layer (cartservice run has the class/interface bindings missing here).
4. **`env_vars` extraction returned empty** — the regex didn't match the onboarding payload shape;
   the env-var lexicon (`COLLECTOR_SERVICE_ADDR`, `PRODUCT_CATALOG_SERVICE_ADDR`, `ENABLE_TRACING`,
   `CART_STORE_TYPE`) is known from the design docs and should be added manually or via a better probe.
5. **Inferred contracts dropped wholesale.** Some `inferred` contracts are real corpus terms; v0 is
   conservative (explicit-only) to avoid noise. v0.2 could promote `inferred` terms that recur across
   ≥N runs (recurrence as a confidence proxy).

---

## Next steps

1. **Widen the determinism oracle**: run kaizen correlation across all 21 anchor-cluster runs so the
   per-binding stability has more observations → set the SCR success thresholds (X/Y) from it.
2. **Aggregate explicit bindings across clusters** (esp. the cartservice 15-feature cluster) for a
   complete term→construct binding layer.
3. **Formalize the corpus capability** (`/reflective-requirements` → `CONTROLLED_CORPUS_REQUIREMENTS.md`)
   using this v0 as the worked example and the determinism oracle as the acceptance harness.
4. **Wire the oracle into the SCR triage** (FR-4): replace keyword `requirement_score` with
   target_file stability + term-binding realization; calibrate threshold on the labeled set.

---

## Oracle v2 — widened + multi-signal (`scr-labeled-replay-set-v2.json`, `build_oracle_v2.py`)

v1 joined kaizen-correlation's sparse PASS/FAIL (49 obs). v2 reads each anchor run's
`prime-postmortem-report.json` **directly** — wider and multi-signal (`requirement_score`,
`disk_quality_score`, `assembly_delta`, `semantic_error_count` per `target_file`).

- **Coverage:** 9/21 anchor runs have a postmortem (the rest predate postmortem emission or failed) →
  **59 observations across 23 target_files** (vs v1's 49). Still Claude-dominated; honest caveat.

### The headline discovery: structural stability ≠ semantic compliance

`src/shoppingassistantservice/shoppingassistantservice.py` (the Flask RAG): **stability 1.00,
disk_quality 1.00 — but mean `requirement_score` 0.50.** It "passes" every run structurally while
satisfying only half the requirement. This is precisely the **false-PASS** the SCR exists to catch,
surfaced automatically from real data.

This forced a **classifier correction** (a reflection-during-implementation moment): a `corpus_class`
based on success-stability alone *mislabels this known false-PASS as a deterministic candidate*. The
oracle now combines both axes:

| class | rule | meaning |
|-------|------|---------|
| `deterministic_candidate` | stability ≥0.95 **and** requirement_score ≥0.9 | promote to a deterministic provider |
| **`false_pass_risk`** | stability ≥0.95 **but** requirement_score <0.7 | **stable build, unmet requirement — SCR must always escalate** |
| `residue_corpus_gap` | stability <0.7 | LLM-hard / corpus gap |
| `mixed` | otherwise | |

Result: ~15 `deterministic_candidate`, **1 `false_pass_risk`** (shoppingassistant.py), 2
`residue_corpus_gap` (emailservice + shoppingassistant Dockerfiles). The single false_pass_risk is the
most valuable row in the whole trove — a labeled, reproducible false-PASS to anchor the SCR's success
metric (FR §2's "false-PASS detection rate ≥Y").

**Implication for the corpus (feeds CONTROLLED_CORPUS_REQUIREMENTS FR-7/8):** a binding's determinism
must carry *both* `success_stability` and `requirement_score`; the corpus must never promote a
`false_pass_risk` binding to a deterministic provider on structural stability alone.
