# Corpus-Driven Deterministic Provider — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-03
**Status:** Draft
**Related:** `CONTROLLED_CORPUS_REQUIREMENTS.md` (the oracle that targets this), `DETERMINISTIC_GENERATION_VISION.md` (why), `DETERMINISTIC_PROVIDER_IMPLEMENTATION_PLAN.md` (how), `SEMANTIC_COMPLIANCE_REVIEWER_REQUIREMENTS.md` (handles the residue this defers)

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass mapped the provider onto the real generation-loop seams and produced two
> material reframes plus one new requirement. ~3 of 8 FRs changed — the loop working.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| FR-7: the existing `DeterministicFileProvider` registry (`owns`/`is_in_sync`) is the live-wiring home | That registry is **verification-based** — it skips regenerating files already **in sync with a source-of-truth** (e.g. `.prisma`→models). The corpus provider is **emission-based on statistical proof** (no source to be "in sync" with; the file may not exist yet). The two don't share a basis. **The real home is the `_try_*_shortcut` phase chain** (`prime_contractor.py` Phase 0 copy / 0.5 uncomment / 0.6 deterministic-file, called @3423) — the corpus provider is a **new `_try_corpus_shortcut` (Phase 0.7)**. | **FR-7 reframed** to the shortcut-phase chain; the corpus provider is a *generation* shortcut, not an `is_in_sync` provider. |
| FR-2: exemplar content is resolvable at generation time | **No durable cross-run content store exists.** `ExemplarEntry.code_artifact_path` is **relative to the run dir** (which may be gone); `template_promoter` builds templates **in-memory**, never persisted. So proven content cannot be retrieved on a later run. | **FR-2 hardened + new FR-9**: proven content MUST be copied into a **durable content store** at extraction time; resolution reads that store, not a vanished run dir. This is net-new capability the prototype's `dict_content_resolver` stood in for. |
| FR-5/FR-6 need new machinery | `AstParseValidator` (`repair/protocol.py:61`) is reusable as-is for FR-5; `_emit_cost_metric(_FeatureCostRecord(... cost_usd=0.0 ...))` (`prime_contractor.py:4830`) is the FR-6 attribution path (the existing skip-hook logs $0 but emits no metric). | **FR-5/FR-6 confirmed feasible**, narrowed to "reuse these". |
| The corpus provider is "the" deterministic provider | There are now **two bases** for deterministic generation: **derivational** (schema→code: PrismaZod, PydanticSQLModel — the `is_in_sync` registry) and **statistical** (corpus-proven content — this). Both are legitimate; they coexist as different shortcut sources. | Vision + naming clarified; no requirement removed. |

**Resolved open questions:**
- **OQ-3 → RESOLVED (and deepened).** The fingerprint↔target_file join is `ConfigFingerprint.compute(target_file, language, transport)`; but the real blocker is **content durability** (FR-9), not the join.
- **OQ-1 → carried** (eligibility θ — start L3, tune on live data).
- **OQ-2 → sharpened** (content-freshness invalidation — now tied to the durable store's keying on `source_checksum`; see FR-9).

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
  (`content_resolver(target_file) -> str | None`). *(Revised — planning):* the v1 backend SHALL be the
  **durable proven-content store** of FR-9, **not** a direct `ExemplarRegistry.code_artifact_path` read
  (that path is run-dir-relative and non-durable). The provider SHALL NOT hardcode a store, so
  golden-seed / cache backends can be added later. The prototype's `dict_content_resolver` is the test
  double for this interface.
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
- **FR-7 — Live routing integration (phased).** *(Reframed — planning):* the provider SHALL be wired as
  a **new shortcut phase in the existing `_try_*_shortcut` chain** in `prime_contractor.py`
  (after Phase 0.6 `_try_deterministic_file_shortcut`, as **Phase 0.7 `_try_corpus_shortcut`**), which is
  the established pre-LLM skip pattern (copy / uncomment / deterministic-file). It SHALL **not** be
  forced into the `DeterministicFileProvider.is_in_sync` protocol (that is for source-derived files; the
  corpus basis is statistical, not derivational). On a corpus hit the phase SHALL write the proven
  content, mark the feature `GENERATED` at `$0.00`, and short-circuit before the LLM (mirroring the
  existing shortcuts). **v1 ships the provider standalone (prototype done); live wiring is a separate,
  flag-gated increment requiring the validation harness to confirm no regression.**
- **FR-8 — Operator control.** Routing SHALL be gated by a flag (`STARTD8_CORPUS_DETERMINISTIC` /
  config, default **off** until the live validation run passes), so it can be enabled per-project.

- **FR-9 — Durable proven-content store (new — planning).** Because exemplar `code_artifact_path` is
  run-dir-relative and non-durable, proven content SHALL be copied into a **durable, project-scoped
  content store** (e.g. `.startd8/corpus-content/<term_id>/<source_checksum>`) at the point content is
  proven (postmortem extraction, alongside the corpus merge). The store SHALL key content by
  `(term_id, source_checksum)` so that when a feature's requirement changes (`source_checksum` changes)
  the stale content is **not** served (resolves OQ-2 invalidation). The FR-2 resolver reads this store.
  Writing the store SHALL be gated by `STARTD8_CORPUS_ENABLED` (shares the write switch) and be
  non-fatal.

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
  L3; revisit with live data. (Carried.)
- **OQ-2 → RESOLVED by FR-9.** Stale content on requirement change is prevented by keying the durable
  store on `(term_id, source_checksum)` — a changed feature checksum simply misses the store → LLM
  fall-through.
- **OQ-3 → RESOLVED.** Join is `ConfigFingerprint.compute(target_file, language, transport)`; the
  durability problem (FR-9), not the join, was the real blocker.
- **OQ-4 (new) — Content-store growth/eviction.** The durable store accumulates per `(term_id,
  source_checksum)`; needs a size bound / GC (mirror ExemplarRegistry's ceiling). Defer to the FR-9
  increment.

---

*v0.2 — Post-planning self-reflective update. 2 FRs reframed (FR-2, FR-7), 2 confirmed-feasible
(FR-5, FR-6), 1 added (FR-9 durable content store), 2 OQs resolved, 1 new (OQ-4). Core reframe: the
provider is a statistical-proof **generation shortcut** (new Phase 0.7 in the `_try_*_shortcut` chain),
backed by a durable content store — not an `is_in_sync` source-derived provider.*
