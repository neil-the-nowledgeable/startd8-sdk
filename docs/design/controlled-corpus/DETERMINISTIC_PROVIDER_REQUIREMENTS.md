# Corpus-Driven Deterministic Provider — Requirements

**Version:** 0.1 (Draft — pre-planning)
**Date:** 2026-06-03
**Status:** Draft
**Related:** `CONTROLLED_CORPUS_REQUIREMENTS.md` (the oracle that targets this), `DETERMINISTIC_GENERATION_VISION.md` (why), `SEMANTIC_COMPLIANCE_REVIEWER_REQUIREMENTS.md` (handles the residue this defers)

---

## 1. Problem Statement

The Controlled Corpus oracle now proves, with cross-run + cross-model evidence, that a large fraction
of a stable workload's files are generated **identically every time** (online-boutique: ~18 of 23
file outputs are `deterministic_candidate` — stability 1.0, requirement_score ≥0.9). Today every one
of those files is still produced by a paid LLM call in the drafter. The corpus *identifies* the
deterministic-ready files but nothing *serves* them deterministically.

This capability closes that gap: a **Corpus-Driven Deterministic Provider** that, for a file the corpus
classifies as deterministic-ready, emits proven content **without an LLM call**, and falls through to
the existing LLM path otherwise. It is the step that turns the oracle's measurement into actual
LLM-cost reduction on application code (distinct from the ingestion-overhead savings already shipped).

### Gap table
| Component | Current | Gap |
|-----------|---------|-----|
| Which files are deterministic-ready | Corpus oracle (`deterministic_candidate`) | Not consumed by generation |
| Proven file content | `ExemplarRegistry.code_artifact_path` | Not retrieved at generation time |
| Per-file route (LLM vs deterministic) | Always LLM in the drafter | No corpus-driven pre-LLM check |
| Safety (don't template a false-PASS) | `false_pass_risk` class exists | No enforcement at routing |

---

## 2. Requirements

- **FR-1 — Corpus-driven routing decision.** A `route(target_file)` decision SHALL return *eligible*
  only when the corpus term for that `target_file` has `maturity ≥ θ` (default L3 = "stable") **and**
  `corpus_class == "deterministic_candidate"`. It SHALL return *ineligible* for every other class —
  explicitly **never** route `false_pass_risk`, `residue_corpus_gap`, `deterministic_candidate_unscored`,
  `needs_semantic_review`, `insufficient_samples`, or `unobserved`.
- **FR-2 — Content source abstraction.** Emitted content SHALL come from a pluggable resolver
  (`content_resolver(target_file) -> str | None`), v1 backed by `ExemplarRegistry` (read
  `code_artifact_path` for the matching fingerprint). The provider SHALL NOT itself hardcode a content
  store, so golden-seed / cache backends can be added later.
- **FR-3 — Deterministic emission.** When eligible **and** content resolves, the provider SHALL emit
  that content **byte-for-byte with no LLM call**, and the result SHALL be identical across invocations.
- **FR-4 — Safe fall-through.** When ineligible **or** content does not resolve, the provider SHALL
  return `None` and the existing LLM generation path SHALL run unchanged. The provider is purely
  additive — it can never *block* generation, only *skip* the LLM for proven files.
- **FR-5 — Post-emit validation gate.** Emitted content SHALL pass the same cheap structural check the
  pipeline already applies (language syntax/AST check) before being accepted; on failure the provider
  SHALL fall through to LLM rather than emit broken content (defense against a stale/poisoned exemplar).
- **FR-6 — Provenance & savings telemetry.** Each deterministic-served file SHALL be recorded
  (`fill_source="corpus_deterministic"`, term_id, exemplar id) and the **LLM cost avoided** SHALL be
  attributed via the existing `CostTracker`/post-mortem accounting so the savings are observable.
- **FR-7 — Live routing integration (phased).** The provider SHALL expose a single pre-LLM hook usable
  by the drafter / MicroPrime so a file can be served deterministically before the LLM call. **v1 ships
  the provider + decision standalone (prototype, not wired into the live loop);** the live wiring is a
  separate, gated step requiring the validation harness to confirm no regression.
- **FR-8 — Operator control.** Routing SHALL be gated by a flag (`STARTD8_CORPUS_DETERMINISTIC` /
  config, default **off** until the live validation run passes), so it can be enabled per-project.

---

## 3. Non-Requirements
- **NR-1.** v1 does NOT parameterize/template content — it emits the stored proven content verbatim.
  (Parameterized templates from `template_promoter` are a later step.)
- **NR-2.** Does NOT remove or modify the LLM drafter path — purely a pre-LLM skip.
- **NR-3.** Does NOT promote candidates without cross-model evidence — eligibility derives from the
  corpus oracle (which already requires recurrence + observed stability).
- **NR-4.** Does NOT serve `false_pass_risk` or any unproven class (FR-1).
- **NR-5.** v1 scope is single-file outputs (the corpus's `file` kind); multi-element splicing deferred.

---

## 4. Success Criteria (measurable)
- On a replay of the online-boutique 17-feature cluster, the provider routes **≥10** files
  deterministically (of the ~18 candidates), each emitted byte-identical to the proven content, with
  **zero LLM calls** for those files, and **0** `false_pass_risk` files routed.
- Disabling the flag yields byte-identical pipeline behavior to today (pure fall-through).
- A deliberately corrupted exemplar fails FR-5 and falls through to LLM (no broken emit).

---

## 5. Open Questions
- **OQ-1 — Eligibility threshold θ.** L3 (stable, ≥3 runs + stability ≥0.95) vs L4 (canonical)? Start
  L3; revisit with live data.
- **OQ-2 — Content freshness.** When the requirement changes but the corpus still says
  `deterministic_candidate` from old runs, the stored content is stale. Need an invalidation signal
  (seed `source_checksum` change for the file's feature?) — tracked for the live-wiring step.
- **OQ-3 — Fingerprint ↔ target_file join.** ExemplarRegistry keys on `ConfigFingerprint`; the corpus
  keys on `target_file`. Define the join (compute fingerprint from target_file + language) so content
  resolves unambiguously.

---

*Draft 0.1 — will be updated after a planning pass (the prototype below already surfaces OQ-3 as the
first thing to nail down).*
