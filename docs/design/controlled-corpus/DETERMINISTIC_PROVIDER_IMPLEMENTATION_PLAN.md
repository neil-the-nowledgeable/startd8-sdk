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

### I1 — Durable proven-content store (FR-9, FR-2)
- New `corpus/content_store.py`: `put(term_id, source_checksum, target_file, content)` →
  `.startd8/corpus-content/<term_id>/<source_checksum>`; `get(term_id, source_checksum) -> str|None`.
- Write at postmortem: in `_extract_corpus` (already wired), for each served-eligible feature copy the
  freshly-generated proven content into the store, keyed by the feature's `source_checksum`. Gated by
  `STARTD8_CORPUS_ENABLED`; non-fatal.
- `content_store_resolver(corpus, store)` implementing FR-2's `content_resolver`.
- **Tests:** put→get round-trip; checksum-miss → None (OQ-2 invalidation); missing store → None.
- **Exit:** resolver returns durable content cross-run on the trove replay (no run-dir dependency).

### I2 — Provider on the durable store + validation (FR-1/2/3/4/5)
- Point `DeterministicCorpusProvider` at `content_store_resolver`; add `AstParseValidator` as the
  default validator (FR-5). Keep `dict_content_resolver` as the test double.
- **Tests:** serve-from-store; false_pass refuse; stale-checksum fall-through; corrupt-content
  fall-through (AST fail). (Extends the I0 suite.)
- **Exit:** provider serves real trove content from the durable store with the validation gate live.

### I3 — Live wiring: Phase 0.7 `_try_corpus_shortcut` (FR-7/8) — flag default OFF
- Add `_try_corpus_shortcut(feature, ...)` in `prime_contractor.py` after Phase 0.6: load corpus +
  store (project-scoped), `provider.generate(target_file)`; on hit, write the file, mark feature
  `GENERATED` at `$0.00`, return shortcut; else `None` (→ existing flow unchanged).
- Gate by `STARTD8_CORPUS_DETERMINISTIC` (default **off**) — zero behavior change until flipped.
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
