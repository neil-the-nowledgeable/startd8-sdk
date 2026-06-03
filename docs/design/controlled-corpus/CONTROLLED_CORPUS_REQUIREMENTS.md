# Controlled Corpus — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-03
**Status:** Draft (pre-implementation)
**Related:** `CORPUS_V0_FINDINGS.md` (bootstrap data), `SEMANTIC_COMPLIANCE_REVIEWER_REQUIREMENTS.md` (downstream consumer), `DETERMINISTIC_INGESTION_REQUIREMENTS.md` (sibling deterministic-transformation work)

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass mapped the corpus onto real SDK seams and produced one large reframing
> (the corpus is not a new accumulation engine) plus two factual corrections. ~5 of the
> v0.1 assumptions changed — the loop working as intended.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| The corpus needs a new persistence + maturity + merge engine | **`ExemplarRegistry` is a near-exact prior art** (`exemplars/registry.py`): cross-run JSON persistence, a 0–4 **maturity ladder** (candidate→validated→confirmed→invariant→template), **fingerprint dedup/lookup** (`ConfigFingerprint = language:file_type:transport:archetype`), promotion by "same fingerprint in N runs / N source_run_ids", LRU eviction, and a **load-in-postmortem / promote / save** lifecycle (`prime_postmortem.py`). | **FR-1/3/4 narrowed.** The corpus is `ExemplarRegistry`'s pattern applied to *domain terms* instead of code exemplars — reuse the maturity ladder, the postmortem lifecycle, and the fingerprint key; don't invent. |
| `onboarding-metadata.json` could be the corpus production point | **It is EXTERNAL input**, user-provided in `context_files`, not SDK-produced (`_load_onboarding_metadata`). | **FR-5 corrected.** Production hooks into the **postmortem** (where ExemplarRegistry already extracts), reading the per-run seed; onboarding-metadata is at most a *seed input* to the corpus, never the store. |
| `ProjectKnowledge` (`field_sets`/`negatives`) is part of the corpus store | **It is rebuilt per-run and NOT persisted** (`project_knowledge/producer.py`) — context, not accumulation. | **FR-7 reframed.** ProjectKnowledge becomes a per-run **view/consumer fed by** the persistent corpus, not the corpus itself. The corpus is the durable layer beneath it. |
| The corpus needs its own merge-precedence rule | **`forward_manifest` already defines `SOURCE_PRECEDENCE`** (source-ast < deterministic < reference-ast/proto < human-yaml) via `ManifestMerger`. | **FR-4 narrowed.** Reuse that precedence ordering for binding conflicts; human-curated > proto/reference > deterministic > inferred. |
| Stability tracking needs new math | **`utils/trend_math.linear_slope()`** + the kaizen append-run-history/dedup-by-id pattern already exist. | **FR-8 narrowed.** Reuse `linear_slope` for per-binding stability trend; mark "stabilized" when slope→0 at high stability. |

**Resolved open questions:**
- **OQ-1 → RESOLVED.** Persist at `.startd8/controlled-corpus.json` (the `.startd8/` project-state convention; mirrors `exemplar-registry.json`).
- **OQ-2 → RESOLVED.** Reuse the ExemplarRegistry maturity ladder + postmortem load/promote/save lifecycle rather than a new engine.
- **OQ-3 → RESOLVED (correction).** onboarding-metadata is not a production point; postmortem-over-seed is.
- **OQ-4 → RESOLVED.** Binding-conflict precedence reuses `forward_manifest` `SOURCE_PRECEDENCE`.

**New open questions surfaced (see §5):** corpus scoping (project vs shared-domain), surface-form canonicalization (the title-drift dedup), and term↔target_file altitude mapping.

---

## 1. Problem Statement

The SDK's controlled-vocabulary signal is **scattered, per-run, and non-accumulating**. The terms,
bindings, and determinism evidence that should compound across runs are instead rebuilt and discarded
each run. We have just proven (CORPUS_V0_FINDINGS) that a coherent corpus is *latent* in the trove and
that its determinism is *measurable* — but nothing captures it as a durable, growing artifact.

The operating model makes this urgent and tractable at once: **the existing pipeline is a corpus
producer.** Every StartDate-app run (continuing on the existing method for now) and every deliberate
corpus-building run is a fresh sample that should strengthen the corpus — growing recurrence,
confidence, multi-language bindings, and per-binding determinism. Without a persistent corpus, that
signal evaporates run-to-run.

### Gap table

| Component | Current state | Gap |
|-----------|---------------|-----|
| Domain terms (services/RPCs/entities) | Re-parsed per run (proto, forward_manifest) | Not accumulated; recurrence/confidence not tracked |
| Term→construct bindings | `binding_text`, `field_sets`, per-run forward_manifest | Single-run; no multi-language, no maturity |
| Determinism evidence | Latent in kaizen-correlation; computed ad hoc | Not attached to terms; not updated as runs accumulate |
| NL label vs binding | Title drift discarded as noise | Surface-form variation not captured as corpus synonyms |
| Cross-run accumulation | Exists for *exemplars* (code) and *kaizen* (metrics) | No equivalent for *vocabulary/terms* |
| Consumption | ProjectKnowledge rebuilt per run, fed from live project | No persistent corpus feeding it |

---

## 2. Requirements

### Storage & shape
- **FR-1 — Persistent corpus registry.** A `ControlledCorpusRegistry` SHALL persist at
  `.startd8/controlled-corpus.json`, with `load()`/`save()` (atomic write), `schema_version`, and a
  size ceiling — mirroring `ExemplarRegistry`. It SHALL be safe to load when absent (empty corpus).
- **FR-2 — Corpus entry shape.** Each entry SHALL carry: `term_id`; `kind` ∈
  `{service, rpc, entity, field, metric, env_var, slo_target, alert_pattern, config_key}`;
  `surface_forms[]` (the natural-language label variants — the captured residue); `bindings[]`
  (per-language: `{language, construct_kind, construct_ref, source_reference}`); `confidence`
  — **binding PROVENANCE** reusing forward_manifest's `explicit`/`inferred`/`advisory`, **never
  derived from a runtime quality score** (R2-F1: `disk_quality_score` belongs in `determinism`,
  not `confidence`; deterministically-observed bindings are `inferred`, human/proto-declared are
  `explicit`); `maturity` (0–4); `recurrence` (`source_run_ids[]`); and `determinism`
  (`{stability, n_observations, last_slope}`).

### Accumulation (runs as producers)
- **FR-3 — Maturity ladder (reused).** Terms SHALL use the ExemplarRegistry 0–4 ladder, semantics
  adapted: 1=extracted-once, 2=cross-run-validated (≥2 distinct `source_run_ids`), 3=stable
  (≥3 runs **and** determinism.stability ≥ θ), 4=canonical (human-confirmed **or** stability==1.0 over
  ≥N runs). Promotion SHALL be computed at corpus-merge time from `recurrence` + `determinism`.
- **FR-4 — Cross-run merge.** Merging a run's extracted terms SHALL dedup by `(kind, canonical_key)`,
  union `surface_forms`, union/upgrade `bindings` using `forward_manifest` `SOURCE_PRECEDENCE`
  (human > proto/reference > deterministic > inferred), append the `source_run_id`, and recompute
  maturity. Merge SHALL be **idempotent** (re-merging the same run changes nothing).
- **FR-5 — Production at postmortem.** A corpus extractor SHALL run in the **postmortem phase**
  (alongside exemplar extraction), reading the run's `prime-context-seed.json` (proto-derived terms,
  EXPLICIT forward_manifest bindings, `service_metadata`) and the per-feature PASS/FAIL +
  `target_file` to update `determinism`. It SHALL `load → merge → save` the persistent corpus.
- **FR-6 — Bootstrap.** The registry SHALL be seedable from `controlled-corpus-v0.json` (terms +
  bindings) and `scr-labeled-replay-set.json` (determinism), so the corpus starts non-empty.

### Determinism oracle integration
- **FR-7 — Determinism is first-class & updated each run.** Each binding SHALL carry a
  `determinism.stability` updated from accumulated PASS/FAIL keyed on **`target_file`** (NOT positional
  feature id — per CORPUS_V0_FINDINGS), with `last_slope` via `trend_math.linear_slope()`. Surface-form
  count and stability SHALL be tracked as orthogonal axes (the title-drift-vs-stability finding).
- **FR-8 — Two-axis determinism classification.** *(Refined during oracle-v2 build — see
  CORPUS_V0_FINDINGS "Oracle v2".)* Determinism SHALL carry **both** `success_stability` (structural)
  **and** `requirement_score` (semantic), because they diverge: `shoppingassistantservice.py` showed
  stability 1.0 with requirement_score 0.5 (a false-PASS). Each binding SHALL be classed
  *(class set refined by CRP R1-F1/F5 + R2-F2)*:
  `deterministic_candidate` (stability ≥0.95 **and** req ≥0.9),
  `deterministic_candidate_unscored` (stability ≥0.95, **no** req_score — R1-F1),
  **`false_pass_risk`** (stability ≥0.95 **but** req <0.7),
  `needs_semantic_review` (stability ≥0.95, 0.7 ≤ req < 0.9 — R2-F2),
  `needs_more_runs` (0.7 ≤ stability < 0.95 — R2-F2),
  `residue_corpus_gap` (stability <0.7),
  `insufficient_samples` (< 2 observations — R1-F5), or `unobserved` (no determinism yet).
  The corpus SHALL **never promote a `false_pass_risk` binding to a deterministic provider** on
  structural stability alone, and SHALL surface `false_pass_risk` bindings as mandatory SCR
  escalations (FR-10).

### Consumption
- **FR-9 — ProjectKnowledge as a corpus view.** The per-run `ProjectKnowledge` SHALL be able to be
  **populated from the persistent corpus** (stable terms/bindings injected as authorities) rather than
  only from live project state — making accumulated knowledge available to generation. (Wiring is
  phased; v1 requires the corpus to *expose* a ProjectKnowledge-shaped view, not that the producer is
  rewritten.)
- **FR-10 — SCR triage feed (interface only in v1).** The corpus SHALL expose per-`target_file`
  stability + term-binding-realization so the SCR triage (its FR-4) can replace keyword
  `requirement_score`. v1 defines the read interface; the SCR rewire is downstream.

### Operating model
- **FR-11 — Runs are corpus producers.** Both normal StartDate-app runs and **deliberate
  corpus-building runs** SHALL contribute via FR-5. A corpus-building run is a normal pipeline run whose
  *purpose* is accumulation; no separate engine — only a flag/marker so its provenance is labeled.
- **FR-12 — Provenance & versioning.** Every entry SHALL trace to its `source_run_ids`; the corpus
  SHALL carry a `corpus_version` and `last_updated`; merges SHALL be reproducible/deterministic.
- **FR-13 — Observability.** Corpus growth SHALL emit metrics (terms added, maturity promotions,
  stability deltas) consistent with the SDK OTel bridge.

---

## 3. Non-Requirements
- **NR-1.** Not a new accumulation engine — reuses the ExemplarRegistry pattern + lifecycle.
- **NR-2.** Does not replace `forward_manifest`/`ProjectKnowledge` extraction — it *consumes and
  accumulates* their output.
- **NR-3.** v1 does NOT parse free-form business prose into corpus terms (the larger
  deterministic-English vision) — it accumulates terms already structured by the pipeline.
- **NR-4.** No gating/blocking; advisory + accumulation only.
- **NR-5.** v1 scope is the service-web-app (hipstershop) domain — not arbitrary domains.
- **NR-6.** Does not rewrite the SCR or the deterministic providers — it exposes the read interfaces they need.

---

## 4. Success Criteria (measurable)
- On replaying the 17-feature anchor cluster, the corpus SHALL: (a) reach maturity ≥2 for every term
  recurring in ≥2 runs; (b) attach a `determinism.stability` to every `target_file` binding present in
  the labeled set; (c) be **byte-identical** when the same run set is merged in any order (idempotent +
  order-independent merge). 
- A second merge of an already-merged run SHALL produce zero diffs (idempotency check).

---

## 5. Open Questions
- **OQ-5 — Corpus scope: project vs shared-domain.** Persist per-project (`.startd8/`) or promote a
  stable subset to a shared cross-project domain corpus (`~/.startd8/corpus/`)? The determinism oracle
  is workload-specific, but the term vocabulary (hipstershop) is reusable. Decide a promotion boundary.
- **OQ-6 — Surface-form canonicalization.** What function maps drifting NL labels ("Shared JSON Logger
  — emailservice" vs "Email Service JSON Logger") to one `canonical_key`? Candidates: target_file-anchored
  keys, normalized n-gram, or proto-term anchoring. This is the title-drift dedup (FR-4).
- **OQ-7 — Term↔target_file altitude.** Proto terms are per-service/RPC/entity; the determinism oracle
  is per-`target_file`. Define the mapping (which terms bind to which files) so stability attaches to
  the right term. Mirrors the SCR's OQ-9 (feature vs element altitude).

---

*v0.2 — Post-planning self-reflective update. 5 requirements narrowed/reframed (FR-1/3/4/5/7/8/9),
1 correction (onboarding-metadata), 4 open questions resolved, 3 new (OQ-5/6/7). Core reframe: the
corpus = ExemplarRegistry's accumulation pattern applied to domain terms, fed at postmortem, consumed
by a ProjectKnowledge view + the SCR triage.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

> Triage pass 1 (claude-opus-4-8, 2026-06-03) — first batch from rounds R1–R2. Several caught
> real defects in the live code; applied + covered by tests in `tests/unit/corpus/`. Remaining
> items are **accepted-pending** — to apply with the final round.

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-F1 | `deterministic_candidate_unscored` class (stable, no req_score) | R1 | `classify_determinism` adds the class; `test_classify_unscored_not_deterministic_candidate` | 2026-06-03 |
| R1-F2 | Ban L3 when `n_observations == 0` | R1 | `recompute_maturity` L3 requires observed stability; `test_proto_term_no_observations_caps_at_L2` | 2026-06-03 |
| R1-F3 | Schema migration contract on version mismatch | R1 | `registry.load` refuses incompatible MAJOR schema (empty+warn); `test_schema_major_mismatch_returns_empty` | 2026-06-03 |
| R1-F5 | Minimum-sample guard on thresholds | R1 | `_MIN_SAMPLES=2` → `insufficient_samples`; `test_classify_min_sample_guard` | 2026-06-03 |
| R1-F6 | `shared_corpus_path()` stub + v2 non-requirement | R1 | `paths.shared_corpus_path()` added | 2026-06-03 |
| R2-F1 | `confidence` is binding-provenance, not disk-quality | R2 | extractor → `confidence="inferred"`; `test_extractor_confidence_is_provenance_not_quality` | 2026-06-03 |
| R2-F2 | Split `"mixed"` into two remediation classes | R2 | `needs_more_runs` / `needs_semantic_review`; `test_classify_mixed_split` | 2026-06-03 |
| R3-F1 | Eviction must not remove `false_pass_risk` terms (FR-8 guarantee) | R3 | `_evict_if_needed` filters out false_pass_risk; `test_eviction_protects_false_pass_risk` | 2026-06-03 |
| R3-F2 | Don't persist derived `corpus_class` in canonical JSON | R3 | dropped from `to_dict`; added `as_debug_dict`; `test_corpus_class_not_in_canonical_dict` | 2026-06-03 |
| R4-F1 | Scope determinism by `input_scope_id` (cluster) | R4 | `Determinism` computes over dominant scope; `test_cross_scope_not_merged` | 2026-06-03 |
| R4-F2 | `should_escalate` uses both axes | R4 | escalate unless `deterministic_candidate`; `test_escalate_high_stability_mid_req` | 2026-06-03 |
| R4-F3 | Monotonic `corpus_version` separate from `schema_version` | R4 | registry bumps + persists `corpus_version`; `test_corpus_version_increments` | 2026-06-03 |

**Accepted-pending (next implementation increments):** R1-F4 (last_slope time-ordering — needs
`observed_at` on observations; pairs with R4-F1 scope work), R2-F3 (FR-13 OTel metric names), R3-F3
(canonical_key uniqueness warning/test — low), R4-F4 (bootstrap one-shot `--force` doc).

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-sonnet-4-5 — 2026-06-03

**Scope:** First-pass dual-document review of requirements only (F-prefix). Grounded in live code: `corpus/models.py`, `corpus/registry.py`, `corpus/extractor.py`, `CORPUS_V0_FINDINGS.md`. No items in Appendix A/B to dedup against. Addresses all six sponsor focus areas (OQ-5/6/7, FR-8 thresholds, merge idempotency, interface fidelity).

**Executive summary:** Four high-severity gaps: `classify_determinism` promotes structurally-stable but semantically-unscored terms to `deterministic_candidate` (FR-8 silent violation); the `stab is None` branch silently lets proto terms reach L3 maturity (FR-3 violation); `last_slope` is computed over an unspecified ordering (FR-7 incompleteness); and FR-1 has no schema migration contract. Two medium gaps: FR-8 thresholds lack a calibration mechanism given the small empirical base (49 obs); OQ-5 has no decision boundary or v2 commitment.

| ID | Area | Severity | Suggestion | Proposed Placement | Validation Approach |
|----|------|----------|------------|--------------------|---------------------|
| R1-F1 | Data | high | FR-8: add `deterministic_candidate_unscored` class for stability ≥ 0.95 with `req_score is None` | FR-8 ("never promote a `false_pass_risk` binding") | Unit test: `classify_determinism(0.98, None)` ≠ `"deterministic_candidate"` |
| R1-F2 | Risks | high | FR-3: explicitly ban L3 promotion when `n_observations == 0` | FR-3 ("≥3 runs **and** determinism.stability ≥ θ") | Unit test: proto term with 5 runs and no observations stays at L2 |
| R1-F3 | Architecture | high | FR-1: define schema migration contract for version mismatch | FR-1 ("safe to load when absent") | Test: load a corpus with schema_version "0.9.0" — behavior is documented and consistent |
| R1-F4 | Data | high | FR-7: specify that `last_slope` requires a time-ordered sequence (not lexicographic run_id sort) | FR-7 ("last_slope via `trend_math.linear_slope()`") | Test: observations inserted in reverse order produce same slope as forward order when timestamps are present |
| R1-F5 | Risks | medium | FR-8: thresholds must be externally configurable constants with minimum-sample guard | FR-8 thresholds (≥0.95/≥0.9/<0.7) | Parameterized unit test covering all four classes at boundary values |
| R1-F6 | Ops | medium | OQ-5: add a v2 commitment and `shared_corpus_path()` stub to requirements | §5 OQ-5 | Existence of `shared_corpus_path()` in `paths.py`; non-requirement "v1 does NOT implement shared promotion" |

---

#### R1-F1 — Data — high
**Anchor:** FR-8, sentence "The corpus SHALL **never promote a `false_pass_risk` binding to a deterministic provider** on structural stability alone"

**Finding:** `classify_determinism(stability=0.98, req_score=None)` currently returns `"deterministic_candidate"`. Proto-level terms (service, rpc, entity) extracted at bootstrap and never assigned a `requirement_score` (because they have no associated feature text or postmortem output) all fall into this path. They are classified as deterministic candidates despite having zero semantic verification. The FR-8 text only guards against the explicit `false_pass_risk` case (high stability + low score) — it silently treats the unscored case as fully verified, which is the same structural-stability-only promotion the requirement explicitly prohibits.

**Suggestion:** Add a fifth class to `classify_determinism`: `"deterministic_candidate_unscored"` (stability ≥ 0.95 but `req_score is None`). This is semantically distinct from a full `"deterministic_candidate"` (both axes verified) and from `"false_pass_risk"` (positive negative evidence). The corpus MAY promote an `_unscored` binding to a deterministic provider with an explicit caveat field (`"unscored": true`) so consumers can decide their own gating threshold. Add to FR-8: "A binding with `stability ≥ 0.95` and `requirement_score is None` SHALL be classified `deterministic_candidate_unscored`, not `deterministic_candidate`. SCR consumers SHALL treat unscored bindings as advisory, not authoritative."

**Expected impact:** Closes the semantic-verification gap for proto terms without blocking their accumulation. Gives the SCR triage a clear signal about what has and hasn't been semantically validated.

---

#### R1-F2 — Risks — high
**Anchor:** FR-3, sentence "Promotion SHALL be computed at corpus-merge time from `recurrence` + `determinism`"

**Finding:** FR-3 defines L3 = "≥3 runs **and** determinism.stability ≥ θ". The live implementation (`recompute_maturity()`) has `elif n_runs >= 3 and (stab is None or stab >= _STABILITY_HIGH)` — the `stab is None` branch silently bypasses the stability gate for any term with no observations (all proto-bootstrapped terms). These terms reach L3 purely on recurrence, with no determinism evidence. FR-3's acceptance criterion in §4 does not guard against this path. The net effect: the corpus reports proto terms as L3 "stable" when they are unobserved, which inflates the maturity distribution and misleads downstream consumers.

**Suggestion:** Add an explicit sub-clause to FR-3: "A term with `determinism.n_observations == 0` SHALL NOT be promoted above maturity level 2, regardless of `recurrence` count. The stability gate (determinism.stability ≥ θ) is not optional for L3." Also update the §4 success criterion to include: "No term with zero observations SHALL appear at maturity ≥3 in the post-replay corpus."

**Expected impact:** Enforces the intent of FR-3. Prevents the bootstrap corpus from containing L3 proto terms that have no empirical support for their stability claim.

---

#### R1-F3 — Architecture — high
**Anchor:** FR-1, sentence "It SHALL be safe to load when absent (empty corpus)"

**Finding:** FR-1 specifies `schema_version` and safe-load-on-absent. The current `load()` returns an empty registry on missing file (correct) and silently fills defaults for unknown fields on schema version mismatch (implicit). But there is no stated behavior when `schema_version` changes (e.g., "1.0.0" → "1.1.0" adds a new required field). The `load()` code uses `d.get(field, default)` throughout, so it silently succeeds on unknown schemas — which may produce a corpus with partially-missing fields that is structurally valid but semantically broken. This is a data quality risk that compounds as the corpus accumulates across schema versions.

**Suggestion:** Add to FR-1: "On `schema_version` mismatch, `load()` SHALL log a warning identifying the version delta. For backward-compatible changes (same major, higher minor), field defaults are acceptable. For incompatible changes (major version bump), `load()` SHALL either (a) migrate using a registered migration function, or (b) discard terms that cannot be parsed and log each discarded term_id. The behavior SHALL be documented in the module docstring and covered by a test fixture that loads a v0.9.0 corpus file."

**Expected impact:** Makes schema evolution safe and auditable. Prevents silent data corruption as the corpus grows and the schema matures.

---

#### R1-F4 — Data — high
**Anchor:** FR-7, sentence "with `last_slope` via `trend_math.linear_slope()`"

**Finding:** FR-7 specifies `last_slope` but not the ordering of observations. The implementation sorts by `run_id` lexicographically. CORPUS_V0_FINDINGS shows real production run IDs are hash-suffixed names (`benchmark-2b118f33dada`) — lexicographic order of these is hash order, not chronological. `linear_slope` on a hash-ordered sequence produces a random slope, not a trend. For the 17-feature cluster validation (§4 success criterion), the bootstrap replay IDs happen to sort correctly, but production would silently break.

**Suggestion:** Add to FR-7: "The stability history used to compute `last_slope` SHALL be ordered by observation time (ascending). `Determinism.observe()` SHALL record an `observed_at` ISO-8601 timestamp alongside each `run_id` entry. `last_slope` SHALL sort by `observed_at`, not lexicographically by `run_id`. If `observed_at` is absent (legacy entries), the slope computation is undefined and SHALL return `None`." Update the §4 success criterion: "Stability slope computation is validated by a test with 10 synthetic observations inserted in non-lexicographic order."

**Expected impact:** Makes `last_slope` reliable for production. Without this, the "stabilized when slope→0" signal is noise.

---

#### R1-F5 — Risks — medium
**Anchor:** FR-8, sentence "classed: `deterministic_candidate` (stability ≥0.95 **and** requirement_score ≥0.9), **`false_pass_risk`** (stability ≥0.95 **but** requirement_score <0.7), `residue_corpus_gap` (stability <0.7)"

**Finding:** CORPUS_V0_FINDINGS §"Honest caveats" states: "Enough to demonstrate the method; too small to set the SCR's X/Y success thresholds with confidence" (49 labeled observations). The thresholds 0.95/0.9/0.7 are hardcoded in `models.py` as `_STABILITY_HIGH`, `_REQSCORE_HIGH`, `_REQSCORE_LOW`, `_STABILITY_LOW`. There is no mechanism to recalibrate them as the corpus grows. If the effective distribution of stability scores differs from the v0 empirical sample (e.g., new services cluster at 0.85–0.92), the threshold boundaries would systematically misclassify.

**Suggestion:** Add to FR-8: "Thresholds SHALL be defined as named module constants (`STABILITY_CANDIDATE`, `REQSCORE_CANDIDATE`, `REQSCORE_RISK`, `STABILITY_GAP`) with a docstring citing their empirical basis (n, dataset, date). A minimum-sample guard SHALL log a warning when promoting a term to `deterministic_candidate` with fewer than N_MIN observations (suggested: 5). Thresholds SHALL be covered by a parameterized unit test that documents all four classification regions and their boundaries." Also define the gap between `residue_corpus_gap` (stability <0.7) and `deterministic_candidate` (stability ≥0.95) — the `"mixed"` class covers this 0.7–0.95 range but is not distinguished from the sub-case where `req_score in [0.7, 0.9)` with high stability. Consider `"near_candidate"` for high-stability, medium-score terms.

**Expected impact:** Makes threshold evolution safe and auditable. Prevents silent systematic misclassification as the corpus grows beyond the 49-observation bootstrap.

---

#### R1-F6 — Ops — medium
**Anchor:** §5 Open Questions, "OQ-5 — Corpus scope: project vs shared-domain … Decide a promotion boundary."

**Finding:** OQ-5 is the only open question without a resolution criterion, a decision owner, or a v2 commitment. The v0 data demonstrates that hipstershop proto terms (9 services, 15 RPCs, 32 entities) are domain-stable across models and runs — exactly the terms most worth sharing. Every new project that generates hipstershop code will independently re-learn these terms from scratch. The current framing ("decide a promotion boundary") is too open-ended to drive v2 planning.

**Suggestion:** Add to §5: "OQ-5 SHALL be resolved before v2 with a concrete decision: either (a) promote stable terms (maturity ≥4) to `~/.startd8/corpus/` with a read-merge-on-load lifecycle, or (b) keep corpora project-local with an explicit export/import CLI command. Add to v1 deliverables: `shared_corpus_path()` in `paths.py` (even if it raises `NotImplementedError`) and a NR: 'v1 does NOT implement shared-corpus promotion'. This locks the wiring point so v1 code does not foreclose option (a)." This converts an indefinite open question into a phase-gated decision with a named interface.

**Expected impact:** Unlocks the primary accumulation value proposition (cross-project domain term reuse) for v2 without requiring v1 implementation. Prevents architectural lock-in.

---

**Endorsements:** (no prior rounds to endorse)

---

#### Review Round R2 — claude-sonnet-4-6 — 2026-06-03

**Scope:** Second-pass (fresh reviewer). Read and deduped against R1-F1 through R1-F6. Three new requirements gaps not touched in R1: confidence semantics mismatch, ambiguous "mixed" class, and FR-13's untestable OTel commitment. Endorses R1-F2 and R1-F4 as highest priority.

**Executive summary:** Two data-model gaps in the requirements that the live code has already operationalized incorrectly: FR-2 defines `confidence` as reusing `forward_manifest`'s binding-provenance levels (EXPLICIT/INFERRED/ADVISORY), but the extractor uses `disk_quality_score >= 0.9` — a runtime code-quality metric, not a source-provenance label. FR-8's `"mixed"` class covers two remediation paths (low stability needs more runs; high-stability/mid-semantic-score needs SCR review) and is already observable in production as an ambiguous classifier output. FR-13 commits to OTel metrics without naming them, making it untestable.

| ID | Area | Severity | Suggestion | Proposed Placement | Validation Approach |
|----|------|----------|------------|--------------------|---------------------|
| R2-F1 | Data | high | FR-2: define `confidence` as binding-provenance source (not runtime quality score); clarify legal values and mapping to `forward_manifest` confidence levels | FR-2 ("confidence (reusing forward_manifest's EXPLICIT/INFERRED/ADVISORY)") | Unit test: confidence value is one of {explicit, inferred, advisory}; never derived from `disk_quality_score` |
| R2-F2 | Architecture | medium | FR-8: split `"mixed"` into two classes with distinct remediation paths | FR-8 (classification table) | Unit test covers all five classes with boundary inputs |
| R2-F3 | Validation | medium | FR-13: enumerate concrete metric names, units, and OTel attribute keys | FR-13 ("emit metrics … consistent with the SDK OTel bridge") | Acceptance test asserts emitted attribute names match the documented list |

---

#### R2-F1 — Data — high
**Anchor:** FR-2, sentence "confidence (reusing forward_manifest's EXPLICIT/INFERRED/ADVISORY)"

**Finding:** FR-2 specifies that `confidence` reuses `forward_manifest`'s EXPLICIT/INFERRED/ADVISORY levels — which measure *binding provenance* (where the binding came from: human YAML, proto, AST, etc.). The live extractor implementation sets: `confidence = "explicit" if (dqs is not None and dqs >= 0.9) else "inferred"` where `dqs` is `disk_quality_score` — a runtime measurement of whether the generated file passes disk validation checks. These two signals are orthogonal: a file can have perfect disk quality but be an incidentally-generated output with no explicit binding; conversely, a human-YAML-declared binding is EXPLICIT regardless of whether the generated file passes disk checks. Using `disk_quality_score >= 0.9` as the confidence gate means high-quality generation artifacts get promoted to `confidence="explicit"`, eventually reaching maturity L4 (which requires `confidence == "explicit"`). This is not what FR-2 intended.

**Suggestion:** Rewrite the `confidence` field definition in FR-2: "Each entry's `confidence` SHALL reflect **binding provenance**: `explicit` — binding declared in a human YAML or proto contract; `inferred` — binding derived from AST analysis or heuristic extraction; `advisory` — binding suggested by a model or pattern matcher. The extractor SHALL set `confidence` based on the `source_reference` of the binding's source (e.g., `proto` → `explicit`, `deterministic` → `inferred`), not from runtime code-quality metrics. `disk_quality_score` is a generation quality signal and SHALL NOT set `confidence`." Also update FR-3 (L4 canonical promotion) to require at least one `explicit` source_reference in the bindings, not `term.confidence == "explicit"`.

**Expected impact:** Prevents incidentally-high-quality generated files from being falsely promoted to L4 canonical status. Aligns the semantic meaning of `confidence` with its forward_manifest origin.

---

#### R2-F2 — Architecture — medium
**Anchor:** FR-8, sentence "Each binding SHALL be classed: `deterministic_candidate` … `false_pass_risk` … `residue_corpus_gap` (stability <0.7), or `mixed`."

**Finding:** The `"mixed"` class is a catch-all for all states not covered by the first three classes. In practice it conflates two operationally distinct situations:
1. **Low-mid stability** (`stability ∈ [0.7, 0.95)`, any `req_score`): the term is on its way to stability but needs more runs — remediation is *accumulate more data*.
2. **High stability, mid semantic score** (`stability ≥ 0.95`, `req_score ∈ [0.7, 0.9)`): structurally stable but semantically under-verified — remediation is *route to SCR for semantic review*.

Both are called `"mixed"` today, so the SCR triage feed (FR-10) cannot distinguish a term that needs more runs from a term that needs semantic escalation. The `classify_determinism` function's docstring does not acknowledge this gap.

**Suggestion:** Split `"mixed"` into two classes in FR-8: `"accumulating"` (stability ∈ [0.7, 0.95) — insufficient structural evidence; needs more runs) and `"near_candidate"` (stability ≥ 0.95, `req_score ∈ [0.7, 0.9)` — structurally stable, semantically underverified; recommend SCR escalation). The SCR triage (FR-10) should escalate `near_candidate` bindings alongside `false_pass_risk` bindings. Update the acceptance criteria in §4 to enumerate all five classes with boundary values.

**Expected impact:** Enables actionable downstream routing from the corpus class. Without the split, the SCR cannot know whether a `"mixed"` term needs more data or needs a semantic review — both would be treated the same way (ignored or escalated arbitrarily).

---

#### R2-F3 — Validation — medium
**Anchor:** FR-13, sentence "Corpus growth SHALL emit metrics (terms added, maturity promotions, stability deltas) consistent with the SDK OTel bridge."

**Finding:** FR-13 commits to OTel metrics but names only their *concepts* ("terms added", "maturity promotions", "stability deltas") — not their concrete metric names, units, attribute keys, or OTel instrument types (Counter vs Gauge vs Histogram). The R1 coverage matrix flagged Step 9 (OTel) as a "Gap — no OTel emit in corpus package." Without concrete names, the acceptance criteria cannot be stated, and the OTel bridge configuration cannot bind to the metrics. Compare: FR-16 in the SCR requirements was criticized (R1-F6) for the same issue, and was fixed by enumerating names/units explicitly.

**Suggestion:** Rewrite FR-13: "The corpus SHALL emit the following OTel metrics on each `merge_run()` call, using the SDK's `get_logger`/OTel bridge pattern: (a) `corpus.terms_total` — Gauge, unit=count, attributes={`project_id`, `kind`}; (b) `corpus.promotions_total` — Counter, unit=promotions, attributes={`from_maturity`, `to_maturity`, `kind`}; (c) `corpus.false_pass_risk_count` — Gauge, unit=count, attributes={`project_id`}; (d) `corpus.extraction_failures_total` — Counter, unit=failures, attributes={`reason`}. Metrics SHALL be emitted via the same OTel instrument pattern used in `costs/tracker.py`." Add to §4 success criteria: "An acceptance test asserts that a bootstrap + merge cycle emits `corpus.terms_total > 0` and `corpus.promotions_total` increments on first promotion."

**Expected impact:** Makes FR-13 testable. Provides Grafana dashboard authors (gov-budget-transparency skill territory) with fixed metric names. Adds the extraction-failures counter that R2-S2 (plan) recommends using for operational visibility.

---

**Endorsements:**
- R1-F2 (FR-3: ban L3 for unobserved terms) — highest requirement priority; without this fix the corpus stability claims are meaningless for proto terms.
- R1-F4 (FR-7: `last_slope` requires time-ordered sequence, not lexicographic sort) — agree; this is an implementation correctness requirement.

**Disagreements:** none.

---

#### Review Round R3 — claude-sonnet-4-6 — 2026-06-03

**Scope:** Third-pass requirements review (F-prefix). Deduped against R1-F1/F2/F3/F4/F5/F6 and R2-F1/F2/F3. New territory: eviction breaking the FR-8 "never promote" guarantee (not touched by R1/R2); the `corpus_class` computed field being persisted in JSON (schema anti-pattern); and OQ-6 normalization collisions for proto terms (the focus file's item #2 was assessed as covered but has a specific open gap).

**Executive summary:** Two high-severity requirements gaps. First: FR-8 guarantees "never promote a `false_pass_risk` binding" — but the eviction policy (`_evict_if_needed`) removes the lowest-maturity, fewest-run terms when the corpus is full. A `false_pass_risk` term at L2 with 3 runs can be evicted; on re-encounter it starts fresh at L1 with no history, and the `false_pass_risk` classification is never regenerated until enough runs re-accumulate. The guarantee is temporarily broken. Second: `CorpusTerm.to_dict()` stores `corpus_class` (a derived field) in the JSON — but `from_dict()` ignores it and recomputes dynamically. If classification thresholds change between writes, the JSON shows a stale class while the runtime shows the new one.

| ID | Area | Severity | Suggestion | Proposed Placement | Validation Approach |
|----|------|----------|------------|--------------------|---------------------|
| R3-F1 | Security | high | FR-8: eviction must not remove `false_pass_risk` terms — the "never promote" guarantee requires persistent negative evidence | FR-8 ("never promote a `false_pass_risk` binding") | Test: fill corpus to MAX_CORPUS_SIZE with L1 terms; assert `false_pass_risk` terms at L2 are NOT evicted |
| R3-F2 | Data | medium | FR-1/FR-2: remove `corpus_class` from the persisted JSON (derived field should never be stored) | FR-1 (corpus entry shape / schema_version) | Test: load saved corpus; assert runtime `corpus_class` differs from stored value after threshold change |
| R3-F3 | Risks | medium | OQ-6: require normalization uniqueness test for proto term names in the bootstrap corpus | §5 OQ-6 + FR-4 ("dedup by `(kind, canonical_key)`") | Test: `normalize_surface` applied to all v0 proto names produces no collisions within a kind |

---

#### R3-F1 — Security — high
**Anchor:** FR-8, sentence "The corpus SHALL **never promote a `false_pass_risk` binding to a deterministic provider** on structural stability alone"

**Finding:** The "never promote" guarantee is a corpus-level invariant. But `_evict_if_needed()` evicts the lowest-maturity, fewest-run term when the corpus exceeds `MAX_CORPUS_SIZE`. A `false_pass_risk` term can have maturity L2 (≥2 runs), which is NOT the lowest possible maturity (L1). However, if all other terms are at L2+ and the `false_pass_risk` term has the fewest runs among L2 terms, it can be evicted. Once evicted, the term's history is lost: the next extractor run that encounters the same `target_file` creates a fresh L1 entry with no `false_pass_risk` classification. With enough subsequent PASS observations, it can be re-promoted to `deterministic_candidate` — the exact outcome FR-8 prohibits.

This is not theoretical: the 17-feature cluster has `shoppingassistantservice.py` at stability 0.0 (always fails). If this file is re-encountered across runs after an eviction, it would re-accumulate PASS-only observations from a different model run and become a false deterministic candidate.

**Suggestion:** Add to FR-8: "The eviction policy SHALL NEVER remove a term whose `corpus_class` is `false_pass_risk`. Eviction candidates SHALL be filtered to exclude `false_pass_risk` terms regardless of maturity or run count." In `_evict_if_needed()`, the candidate selection must be: `victim = min(t for t in self._terms.values() if t.determinism.corpus_class != "false_pass_risk", key=lambda t: (t.maturity, ...))`. If ALL terms are `false_pass_risk`, no eviction occurs (the corpus grows beyond MAX_CORPUS_SIZE for this extreme case). Document this boundary in FR-1's ceiling definition.

**Expected impact:** Makes the "never promote" guarantee unconditional — not just "while the term is in memory." This is a correctness guarantee, not a performance tuning — the fix is mandatory for FR-8's intent to hold across long-running production deployments.

---

#### R3-F2 — Data — medium
**Anchor:** FR-1, sentence "with `schema_version`" / FR-2 (corpus entry shape) / `CorpusTerm.to_dict()` line 199: `"corpus_class": self.determinism.corpus_class`

**Finding:** `CorpusTerm.to_dict()` includes `"corpus_class"` as a persisted field. `from_dict()` does NOT read it back — `corpus_class` is recomputed dynamically from stored observations on each property access. The JSON file therefore contains a stale snapshot of the classification at time of last `save()`. If thresholds change (per R1-F5's recommendation to make `_STABILITY_HIGH` configurable), the stored `corpus_class` values are wrong while the runtime values are correct. This causes confusion for anyone reading the JSON file directly (e.g., for auditing or debugging), and would cause schema-validation tools to flag a mismatch. It's an anti-pattern: computed-from-stored-data fields should not appear in canonical storage.

**Suggestion:** Remove `"corpus_class"` from `CorpusTerm.to_dict()`. If human readability is desired, add a separate `as_debug_dict()` method that includes computed fields with a note: `"corpus_class_computed": ..., "_note": "derived field — recomputed on load"`. The canonical `to_dict()` format should contain only durable state (observations, bindings, surface_forms, source_run_ids, confidence, maturity). Add to FR-1: "Persisted corpus entries SHALL contain only durable state. Derived fields (including `corpus_class`) SHALL NOT be stored in the canonical JSON format."

**Expected impact:** Prevents schema confusion on threshold recalibration. Keeps the JSON as the single source of truth with no stale computed fields. Makes the schema cleaner for future migration (fewer fields to handle when schema changes).

---

#### R3-F3 — Risks — medium
**Anchor:** §5 OQ-6, sentence "What function maps drifting NL labels … to one `canonical_key`?" / FR-4 ("dedup by `(kind, canonical_key)`")

**Finding:** The plan's `canonical.py` resolves OQ-6 by anchoring on `target_file` when present. The R1 coverage matrix marked OQ-6 as "Covered." But for proto-level terms (service, rpc, entity) where no `target_file` exists, `canonical_key` falls back to `normalize_surface(surface_form)`. The normalization strips non-alphanumeric chars to hyphens and lowercases. Two proto service names that normalize identically would silently merge into one corpus term. Examples from the v0 corpus: would `"CartService"` and `"Cart-Service"` collide? (`normalize_surface("CartService")` = `"cartservice"`, `normalize_surface("Cart-Service")` = `"cart-service"` — these differ). But what about `"Email Service"` (from a NL label) and `"EmailService"` (from a proto name)? Both normalize to `"emailservice"`. If the bootstrap uses proto names and a run's NL extractor produces the NL label, they'd merge — which may or may not be correct depending on whether they refer to the same entity.

The deduplication in FR-4 is correct IF the canonical key is globally unique within a `kind`. But the requirements never state that `canonical_key` must be unique within a kind, and the `normalize_surface` fallback doesn't guarantee it.

**Suggestion:** Add to FR-4: "Within a given `kind`, `canonical_key` values SHALL be unique — `(kind, canonical_key)` is the primary key. For proto-level terms using the `normalize_surface` fallback, the corpus extractor SHALL log a warning on first encounter of a collision and prefer the proto-name-derived key over an NL-label-derived key when both resolve to the same normalized string." Add to §4 success criteria: "Replaying the v0 bootstrap produces no canonical_key collisions within any `kind`." This makes the uniqueness assumption explicit and testable.

**Expected impact:** Prevents silent merging of distinct proto terms with similar normalized names. Gives the operator visibility into canonicalization conflicts. Ensures the `(kind, canonical_key)` primary key guarantee in FR-4 is actually enforced.

---

**Endorsements:**
- R2-F1 (FR-2: `confidence` should be binding provenance, not `disk_quality_score`) — agree; this is a semantic mismatch already operationalized incorrectly.
- R2-F2 (FR-8: split "mixed" into "accumulating" vs "near_candidate") — agree; this directly enables the SCR triage routing improvement in `should_escalate()`.
- R1-F2 (FR-3: ban L3 for unobserved terms) — still the highest priority; now also the root cause of R3-S2 in the plan.

**Disagreements:** none.

---

#### Review Round R4 — claude-sonnet-4-6 — 2026-06-03

**Scope:** Fourth-pass requirements review (F-prefix). Deduped against R1–R3. Addresses crp-focus items not yet in requirements text: input-scope cluster validity (focus #5 / CORPUS_V0_FINDINGS), FR-10 two-axis triage completeness (focus #4), FR-12 `corpus_version`, and FR-6 bootstrap semantics vs production idempotency.

**Executive summary:** CORPUS_V0_FINDINGS established that cross-run determinism is only valid **within an input-scope cluster** (e.g. the 21-run 17-feature cluster) — mixing 7-feature and 17-feature runs poisons stability. This constraint is absent from FR-7/§4, so the corpus can legally compute misleading stability from heterogeneous runs. FR-10's `should_escalate()` uses only the structural axis, leaving the semantic axis (the reason for two-axis FR-8) unused at triage time.

| ID | Area | Severity | Suggestion | Proposed Placement | Validation Approach |
|----|------|----------|------------|--------------------|---------------------|
| R4-F1 | Data | high | FR-7: scope determinism observations to `input_scope_id` (feature-count / seed checksum cluster) | FR-7 + §4 success criteria | Test: merging runs from two scopes does not update the same term's stability |
| R4-F2 | Interfaces | high | FR-10: `should_escalate` SHALL use both axes (escalate `near_candidate` / high-stab + mid-req) | FR-10 ("replace keyword `requirement_score`") | Test: stability=1.0, mean_req=0.8 → escalate True |
| R4-F3 | Ops | medium | FR-12: persist `corpus_version` (monotonic) separate from `schema_version` | FR-12 ("corpus_version and last_updated") | Round-trip test: two merges increment `corpus_version` |
| R4-F4 | Validation | medium | FR-6: bootstrap is one-shot seeding; document non-idempotency of synthetic replay run_ids | FR-6 + NR boundary | Doc + test: re-running bootstrap CLI on same paths is documented as additive |

---

#### R4-F1 — Data — high
**Anchor:** §4 success criterion (c) "byte-identical when the same run set is merged in any order" / CORPUS_V0_FINDINGS §"Track B — Variance segregation"

**Finding:** CORPUS_V0_FINDINGS states: runs partition into input-scope clusters by feature count `{7:3, 10:1, 15:7, 17:21, 40:5}`; "the clean determinism signal lives **within** a cluster." Merging PASS/FAIL from a 7-feature run and a 17-feature run for the same `target_file` compares different inputs — stability becomes meaningless. FR-7 keys determinism on `target_file` only, with no `input_scope_id`, `source_checksum`, or `feature_count` guard. §4's order-independence test can pass in unit tests while production corpus silently blends incompatible scopes.

**Suggestion:** Add to FR-7: "Each determinism observation SHALL carry an `input_scope_id` derived from the run's seed `source_checksum` or feature-count cluster. Stability and `corpus_class` for a `(kind, canonical_key)` SHALL be computed **per input_scope_id** (or the term SHALL partition observations by scope and expose `stability_for(target_file, input_scope_id=...)` for SCR triage). Cross-scope observations MAY be stored but SHALL NOT be merged into a single stability aggregate without an explicit operator opt-in." Add to §4: "Validation replays use only runs from a single declared scope (default: 17-feature anchor cluster)."

**Expected impact:** Makes the determinism oracle scientifically valid. Directly addresses focus item #5 (order-independent merge) in production, not just in synthetic unit fixtures.

---

#### R4-F2 — Interfaces — high
**Anchor:** FR-10, sentence "replace keyword `requirement_score`" / FR-8 two-axis classification

**Finding:** FR-8 introduced `requirement_score` precisely because structural stability alone misclassifies bindings (`shoppingassistantservice.py`: stability 1.0, requirement_score 0.5). `view.should_escalate()` escalates on `false_pass_risk` and `residue_corpus_gap` and on `success_stability < threshold`, but a term with stability 1.0 and mean_requirement_score 0.75–0.89 is classed `"mixed"` and **not** escalated. That is the SCR's highest-value target (structurally stable semantic gap) — and FR-10 currently ignores it. R2-F2 proposed splitting `"mixed"` into `accumulating` vs `near_candidate`; even before that split, FR-10 should escalate the high-stability / mid-req band.

**Suggestion:** Extend FR-10: "`should_escalate()` SHALL return true when: (a) unseen; (b) `corpus_class` ∈ {`false_pass_risk`, `residue_corpus_gap`, `near_candidate`}; (c) `success_stability` is null or < θ; (d) `mean_requirement_score` is not null and < REQSCORE_CANDIDATE (0.9) while `success_stability` ≥ θ." Document that this replaces **both** keyword `requirement_score` triage and stability-only triage. Add acceptance test mirroring `test_should_escalate_false_pass_risk` for the 0.5-req case at stability 1.0.

**Expected impact:** Delivers the end-user value of two-axis FR-8 at the SCR boundary. Low implementation cost (extend `should_escalate` conditional).

---

#### R4-F3 — Ops — medium
**Anchor:** FR-12, sentence "the corpus SHALL carry a `corpus_version` and `last_updated`"

**Finding:** `ControlledCorpusRegistry.save()` persists `schema_version`, `project_id`, `last_updated`, and `terms` — but no `corpus_version` field. FR-12 requires both: `schema_version` is the **format** contract; `corpus_version` should monotonically increment on each successful merge (provenance / audit). Consumers cannot detect stale reads or compare corpus snapshots across pipeline versions without diffing the full JSON.

**Suggestion:** Add to FR-12: "`corpus_version` SHALL be a monotonic integer (or ISO merge counter) incremented on every successful `save()` after a merge that changed state; `schema_version` remains the serialization format." Implement in `merge_run`: `self.corpus_version += 1` when any term changed. Expose in OTel attributes (`corpus.version`).

**Expected impact:** Enables operators and dashboards to detect corpus freshness. Supports future shared-corpus promotion (OQ-5) with a clear "since version N" boundary.

---

#### R4-F4 — Validation — medium
**Anchor:** FR-6 ("seedable from `controlled-corpus-v0.json` … and `scr-labeled-replay-set.json`")

**Finding:** Bootstrap replays oracle aggregates by synthesizing **one distinct `run_id` per pass/fail observation** (`replay-{tgt}-p{i}`, `replay-{tgt}-f{i}`). Re-running the bootstrap CLI on the same inputs appends hundreds of synthetic runs — it is not idempotent as a "bootstrap operation." FR-4's idempotency applies to **production** `stable_run_id` merges, not bootstrap replay. The requirements do not state this boundary; implementers may assume bootstrap is safe to run twice.

**Suggestion:** Add to FR-6: "Bootstrap SHALL be documented and implemented as a **one-shot** initializer: either write to an empty registry or require `--force` to replace. Re-applying bootstrap observations to an existing corpus is out of scope for v1." Add NR or note: "Bootstrap synthetic run_ids are not production run ids; §4 idempotency tests use production-style run ids only."

**Expected impact:** Prevents accidental corpus inflation from repeated bootstrap during development. Clarifies focus item #5 (merge idempotency) applies to postmortem path, not oracle replay path.

---

**Endorsements:**
- R4-F1 complements R1-F4 (`last_slope` ordering) — scope partitioning is the other half of valid trend/stability math.
- R1-F1 (`deterministic_candidate_unscored`) — still required; FR-10 two-axis escalation (R4-F2) handles scored mid-band.
- R3-F1 (eviction must not drop `false_pass_risk`) — pairs with FR-8 "never promote" guarantee.

**Disagreements:** none.
