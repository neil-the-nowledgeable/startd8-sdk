# Corpus-Driven Deterministic Provider — Iterative Implementation Plan

**Version:** 0.2 (aligned with DETERMINISTIC_PROVIDER_REQUIREMENTS.md v0.2)
**Date:** 2026-06-03
**Status:** Plan — pre-implementation (I0 prototype already shipped)

> Built **iteratively**: each increment is independently valuable, tested, and flag-gated so it can
> land on `main` without changing live behavior until the validation run (I5) flips the switch.
> Reuse-heavy — the live-wiring home, validator, cost path, and fingerprint join all already exist.

## Reuse map (don't reinvent)
| Need | Existing component | Note |
|------|--------------------|------|
| Live-wiring home (FR-7) | `_try_*_shortcut` chain in `prime_contractor.py` (Phase 0 copy / 0.5 uncomment / 0.6 deterministic-file, called @3423) | add Phase 0.7 `_try_corpus_shortcut` |
| Routing decision (FR-1) | `corpus/provider.py` `DeterministicCorpusProvider.route/generate` (I0, shipped) | done |
| Content SOURCE at extraction | `ExemplarRegistry` `code_artifact_path` + `extract_exemplars_from_run` | read once, copy into durable store |
| Fingerprint join (OQ-3) | `ConfigFingerprint.compute(target_file, language, transport)` | for exemplar lookup |
| Validation gate (FR-5) | `AstParseValidator.validate(code)` (`repair/protocol.py:61`) | language-agnostic AST check |
| Cost attribution (FR-6) | `_emit_cost_metric(_FeatureCostRecord(...cost_usd=0.0...))` (`prime_contractor.py:4830`) | emit on corpus hit |
| Persistence convention | `paths.py` `.startd8/` | new `corpus-content/` store |
| NOT reused | `DeterministicFileProvider`/`is_in_sync` registry | different basis (derivational vs statistical) — coexists, not extended |

## Increments

### I0 — Standalone provider prototype ✅ (shipped)
`corpus/provider.py` (`route`/`generate`/`dict_content_resolver`) + 8 tests + real-trove demo
(serves 12, refuses 7 false-PASS). Proves route→emit→fall-through + the guardrail.

### I1 — Durable proven-content store (FR-9, FR-2) ✅ (shipped — zero live impact)
- `corpus/content_store.py`: `ContentStore.put/get/has` →
  `.startd8/corpus-content/<safe_term_id>/<source_checksum>`; `content_store_resolver(corpus, store,
  source_checksum)` (FR-2, checksum-bound for OQ-2 invalidation); `populate_from_run(report,
  source_checksum, store)` (standalone copy of proven content from a run's `generated_files`).
- `paths.corpus_content_dir()` added. Exports + tests added.
- **Constraint honored:** the **postmortem write-wiring is DEFERRED to I3** (not added to
  `_extract_corpus`) so no live workflow changes. v1 populate is standalone (validator/bootstrap/tests).
  Only additive edits: `paths.py` (+func), `corpus/__init__.py` (+exports). `_extract_corpus` and
  `prime_contractor` untouched.
- **Done:** 6 unit tests (round-trip, checksum-miss/invalidation, missing-store, resolver,
  provider-from-store, populate); `validate_corpus_integration.py store` populates 231 files across 20
  trove runs and serves 12 **cross-run** from the durable store with checksum invalidation. 64 corpus
  tests green.

### I2 — Provider on the durable store + validation (FR-1/2/3/4/5) ✅ (shipped — zero live impact)
- `build_corpus_provider(corpus, store, source_checksum, ...)` factory wires `content_store_resolver`
  + `default_content_validator` (FR-5: empty→reject; `.py`→`AstParseValidator`/`ast` reuse;
  non-Python→non-empty bar). Raw `DeterministicCorpusProvider` stays validator-optional for tests.
- **Tests (7):** validator empty/py-valid/py-invalid/non-py; factory serves-valid, rejects-invalid-py
  (fall-through), checksum-mismatch fall-through, refuses false_pass_risk.
- **Done:** 71 corpus tests green. Only additive edits to `corpus/provider.py` + `__init__`; no live
  path touched.
- **Exit met:** provider serves durable-store content behind the live validation gate (offline).

### I3a — Postmortem content-store write (FR-9 write) ✅ (shipped — DEFAULT-OFF)
- `_extract_corpus` now calls `populate_from_run(report, seed_source_checksum(output_dir), store)` into
  `corpus_content_dir(project_root)`, gated by a **new default-off `STARTD8_CORPUS_CONTENT_STORE`** —
  so enabling corpus accumulation does NOT start persisting content; non-fatal.
- Added `extractor.seed_source_checksum(output_dir)`.
- **Done:** 2 tests (default-off → no content store written / byte-identical; flag-on → content
  persisted keyed by seed checksum, checksum-keyed miss). 73 corpus + 83 postmortem tests green.
  The only live edit is a default-off branch at the END of `_extract_corpus` (postmortem, not generation).

### I3b — Live read hook: Phase 0.7 `_try_corpus_shortcut` (FR-7/8) — PAUSED (first generation-loop edit)
- Add `_try_corpus_shortcut(feature) -> Optional[bool]` in `prime_contractor.py` mirroring
  `_try_deterministic_file_shortcut` (Optional[bool] contract, marks `GENERATED`/$0): load corpus +
  store (project-scoped; `source_checksum` from `self._seed_path`), `build_corpus_provider(...)`,
  `provider.generate(target_file)`; on hit write file(s) + mark + return True; else `None`.
- Add one call-site line + early-return after Phase 0.6 (~prime_contractor.py:3423), gated by
  `STARTD8_CORPUS_DETERMINISTIC` (default **off**).
- **Tests:** flag-off no-op (byte-identical regression); flag-on+hit skips drafter; false_pass never
  served; multi-target. Optionally fold I4's `_emit_cost_metric(cost_usd=0)` here.
- **Status:** PAUSED per the no-live-impact boundary — this is the first edit to the live generation
  loop. Probe confirmed no unknowns: contract is `Optional[bool]`, `self._seed_path`/`self.project_root`
  available, marking pattern precedented. ~1–2h when ready.
- **Tests:** eligible+content → shortcut taken (no drafter call, mock asserts); ineligible/flag-off →
  drafter runs; false_pass never shortcut.
- **Exit:** with flag off, byte-identical pipeline behavior (regression-safe merge).

### I4 — Cost-saved telemetry (FR-6)
- On a corpus shortcut, call `_emit_cost_metric(_FeatureCostRecord(..., cost_usd=0.0, fill_source=
  "corpus_deterministic"))` and record served files + cumulative cost-avoided in the postmortem.
- **Tests:** shortcut emits a $0 cost record tagged `corpus_deterministic`; postmortem totals reconcile.
- **Exit:** cost-avoided is observable per run.

### I5 — Live validation run (cap-dev-pipe) — the gate to default-on
- Bootstrap/accumulate a corpus on a target project (2 prime runs), then enable
  `STARTD8_CORPUS_DETERMINISTIC=1` and run; use `validate_corpus_integration.py postrun` +
  manual checks (files served $0, **0 false_pass served**, seed-quality unchanged, no broken emits).
- **Exit:** evidence that live serving reduces cost with no regression → decide default-on + θ (OQ-1).

### I6 — Content-store eviction (OQ-4)
- Size bound + GC on `.startd8/corpus-content/` (mirror `ExemplarRegistry` ceiling); prune stale
  `source_checksum`s. **Exit:** store bounded.

## Sequencing & dependencies
I0 ✅ → I1 (store) → I2 (provider on store) → I3 (live phase, flag-off) → I4 (telemetry) → **I5 (live validation gate)** → I6 (GC).
I1–I4 land behind flags with no live behavior change; I5 is the human-gated decision point; I6 is hardening.

## Risks
| Risk | Mitigation |
|------|------------|
| Stale content served after requirement change | FR-9 `source_checksum` keying → miss → LLM fall-through (I1 test) |
| Serving a false-PASS | I0 guardrail (`route` refuses) + I2 tests; never relaxed |
| Live wiring regression | flag default-off through I4; I3 asserts byte-identical with flag off; I5 validates on |
| Different basis confused with `is_in_sync` providers | explicit: corpus = statistical shortcut phase, not an `is_in_sync` provider (FR-7) |

## Validation
Per-increment unit tests in `tests/unit/corpus/`; the offline `validate_corpus_integration.py`
(`offline`/`provider`) extended per increment; I5 is the live cap-dev-pipe run via the runbook.
