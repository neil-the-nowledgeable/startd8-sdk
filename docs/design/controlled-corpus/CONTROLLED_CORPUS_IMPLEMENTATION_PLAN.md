# Controlled Corpus — Implementation Plan

**Version:** 0.2 (aligned with CONTROLLED_CORPUS_REQUIREMENTS.md v0.2)
**Date:** 2026-06-03
**Status:** Plan — pre-implementation

> Scope note from the reflective loop: this is **mostly reuse**. `ExemplarRegistry` already implements
> persistence + maturity ladder + fingerprint dedup + postmortem load/promote/save; `forward_manifest`
> defines source precedence; `trend_math` does the slope. The new code is a *terms* registry that
> mirrors the *exemplars* registry, a postmortem extractor, and read-view adapters.

---

## Module layout

| Artifact | Purpose | Reuses / Maps to |
|----------|---------|------------------|
| `src/startd8/corpus/__init__.py` | package | — |
| `src/startd8/corpus/models.py` | `CorpusTerm`, `Binding`, `Determinism` dataclasses | mirror `exemplars/models.py` (`ExemplarEntry`, `ConfigFingerprint`) — FR-2 |
| `src/startd8/corpus/registry.py` | `ControlledCorpusRegistry` (`load/merge/save`, maturity, eviction) | **copy the shape of `exemplars/registry.py`** — FR-1/3/4 |
| `src/startd8/corpus/extractor.py` | `extract_corpus_from_run(seed, postmortem, registry)` | mirror `exemplars/extractor.py:extract_exemplars_from_run` — FR-5/7 |
| `src/startd8/corpus/canonical.py` | `canonical_key(kind, surface_form, target_file)` surface-form dedup | new (OQ-6) — FR-4 |
| `src/startd8/corpus/view.py` | `as_project_knowledge(corpus, scope)` + `stability_for(target_file)` | adapter to `project_knowledge` / SCR — FR-9/10 |
| `src/startd8/corpus/bootstrap.py` | seed from `controlled-corpus-v0.json` + `scr-labeled-replay-set.json` | FR-6 |
| `prime_postmortem.py` (edit) | call `extract_corpus_from_run` next to exemplar extraction | the existing load/promote/save site — FR-5/11 |
| `paths.py` (edit) | `controlled_corpus_path()` → `.startd8/controlled-corpus.json` | `.startd8/` convention — FR-1 |

## Step-by-step

1. **Models (FR-2).** `CorpusTerm{term_id, kind, surface_forms[], bindings[], confidence, maturity,
   recurrence(source_run_ids[]), determinism{stability,n_observations,last_slope}}`; `Binding{language,
   construct_kind, construct_ref, source_reference}`. Mirror `ExemplarEntry`/`ConfigFingerprint` field
   discipline (frozen where possible, SHA digests for keys).

2. **Registry (FR-1/3/4).** Clone `ExemplarRegistry`'s `load/save` (atomic, schema_version,
   `MAX_*` ceiling, empty-on-missing). `merge_run(terms, run_id)`: dedup by `(kind, canonical_key)`,
   union `surface_forms`, upgrade `bindings` by `forward_manifest.SOURCE_PRECEDENCE`, append run_id,
   recompute `maturity` from `len(set(source_run_ids))` + `determinism.stability` (reuse the
   `promote_maturity` 2-runs→L2 / 3-runs→L3 thresholds; L4 = human-confirmed or stability==1.0×N).
   **Idempotent**: re-merging a run_id already in `recurrence` is a no-op (FR-4, success criterion).

3. **Canonicalization (FR-4, OQ-6).** `canonical_key`: anchor on `target_file` when available (the
   proven invariant), else normalized term surface. Collect all raw labels into `surface_forms`.
   *Decision needed at build (OQ-6); plan defaults to target_file-anchored.*

4. **Extractor (FR-5/7).** `extract_corpus_from_run`: read `prime-context-seed.json`
   (proto-derived service/rpc/entity terms via the same parse used in `extract_corpus_v0.py`; EXPLICIT
   forward_manifest contracts → bindings; `service_metadata`), join per-feature PASS/FAIL from the
   postmortem keyed on `target_file` → `determinism`. Returns terms to `registry.merge_run`.

5. **Determinism update (FR-7/8).** Accumulate per-`target_file` PASS/FAIL across runs; `stability =
   pass/total`; `last_slope = trend_math.linear_slope(stability_history)`; class by thresholds
   (≥0.95 candidate / <0.7 gap). Stored on the binding.

6. **Postmortem wiring (FR-5/11).** In `prime_postmortem.py` (where ExemplarRegistry is already
   loaded/promoted/saved), add the corpus load→extract→merge→save next to it. A `corpus_building`
   provenance flag labels deliberate accumulation runs (FR-11) — no separate path.

7. **Bootstrap (FR-6).** `bootstrap.py` ingests `controlled-corpus-v0.json` + `scr-labeled-replay-set.json`
   into an initial `.startd8/controlled-corpus.json` so the corpus starts populated.

8. **Read views (FR-9/10).** `view.as_project_knowledge(scope)` emits a `ProjectKnowledge`-shaped
   object (field_sets/negatives/interfaces) from stable corpus terms; `view.stability_for(target_file)`
   is the SCR-triage read. v1 ships the views; rewiring the ProjectKnowledge producer and the SCR
   triage are downstream tasks.

9. **Observability (FR-13).** Emit `corpus.terms_total`, `corpus.promotions`, `corpus.stability_delta`.

## Reuse map (don't reinvent)

| Need | Existing component |
|------|--------------------|
| Persistence + maturity + eviction + lifecycle | `exemplars/registry.py` + `prime_postmortem.py` load/promote/save |
| Entry/fingerprint discipline | `exemplars/models.py` (`ExemplarEntry`, `ConfigFingerprint`) |
| Binding source precedence | `forward_manifest` `SOURCE_PRECEDENCE` / `ManifestMerger` |
| Proto term parse | `docs/design/controlled-corpus/extract_corpus_v0.py:parse_proto` |
| Determinism oracle join | `scr-labeled-replay-set.json` + `build_scr_replay_set.py` logic |
| Stability trend | `utils/trend_math.linear_slope` |
| Persistent path convention | `paths.py` (`.startd8/`) |
| Consumer shape | `project_knowledge/models.py` + `render.py` |

## Sequencing
S1 models → S2 registry → (S3 canonical, S5 determinism in parallel) → S4 extractor → S6 postmortem wiring → S7 bootstrap → S8 views → S9 OTel.
Implement behind a `corpus_enabled` flag (default on at postmortem; zero effect on generation in v1 — accumulation only).

## Risks & validation
| Risk | Mitigation |
|------|------------|
| Surface-form dedup mis-merges distinct terms | target_file-anchored key (OQ-6); idempotency + order-independence tests (success criteria) |
| Corpus pollution from low-quality runs | maturity gate — only validated terms promote; recurrence + stability required for L2+ |
| Scope creep into NL parsing | NR-3 fences it; v1 only accumulates pipeline-structured terms |
| Divergence from ExemplarRegistry semantics | literally mirror its lifecycle; share helpers where practical |

**Validation:** replay the 17-feature anchor cluster through the extractor+registry; assert (a) every
≥2-run term reaches maturity ≥2, (b) every labeled `target_file` carries `determinism.stability`,
(c) merge is idempotent and order-independent (byte-identical corpus).

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

> Triage pass 1 (claude-opus-4-8, 2026-06-03). R1-S1/S2 were already addressed during the
> read-view increment; R2-S1/S2 fixed live defects. Tests in `tests/unit/corpus/`.

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-S1 | `view.py` / `as_project_knowledge` absent | R1 | Built `corpus/view.py` (read-view increment); `test_corpus_view.py` | 2026-06-03 |
| R1-S2 | `stability_for()` dead-code + O(n) scan | R1 | Removed dead `tid`; added O(1) `find_by_canonical_key` | 2026-06-03 |
| R1-S4 | Maturity L3 when `stab is None` | R1 | L3 requires observed stability (= R1-F2) | 2026-06-03 |
| R2-S1 | `project_root=None` writes per-run dir | R2 | `_extract_corpus` → `controlled_corpus_path()` (cwd `.startd8`) + warn; never per-run | 2026-06-03 |
| R2-S2 | Save failure swallowed at DEBUG | R2 | `WARNING` on `registry.save` `OSError` | 2026-06-03 |
| R2-S4 | Extractor drops all but `target_files[0]` | R2 | one observation per target_file; `test_extractor_multifile_keeps_all_targets` | 2026-06-03 |
| R3-S1 | `SOURCE_PRECEDENCE` forked from forward_manifest | R3 | import `_SOURCE_PRECEDENCE` + extend; module assertion; `test_source_precedence_extends_forward_manifest` | 2026-06-03 |
| R3-S2 | `stable_authorities` includes zero-evidence (`unobserved`) terms | R3 | exclude `n_observations==0`; `test_unobserved_terms_excluded_from_authorities` | 2026-06-03 |
| R3-S3 | `should_escalate` threshold decoupled from `_STABILITY_HIGH` | R3 | rewritten to defer to `corpus_class` (single source of truth) | 2026-06-03 |
| R4-S1 | Extractor never reads seed → vocabulary layer frozen at bootstrap | R4 | added `extract_seed_terms_from_context` (service terms); wired in `_extract_corpus`; `test_extract_seed_terms` | 2026-06-03 |
| R4-S3 | No `corpus_enabled` off-switch | R4 | `STARTD8_CORPUS_ENABLED` guard in `_extract_corpus` | 2026-06-03 |

**Accepted-pending (next increments):** R1-S3 (last_slope ordering = R1-F4), R2-S3 (`corpus_building`
flag — pairs with R4-S3), R4-S2 (wire `render_authorities_md` into `spec_builder` — generation-path
change, its own increment), R4-S4 (validation-doc + golden CI gate).

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-sonnet-4-5 — 2026-06-03

**Scope:** First-pass dual-document review (plan + requirements). Grounded in live codebase: `src/startd8/corpus/{models,registry,extractor,canonical,bootstrap}.py` + `src/startd8/exemplars/registry.py` + `src/startd8/forward_manifest_extractor.py` + `docs/design/controlled-corpus/CORPUS_V0_FINDINGS.md`. The corpus package is substantially implemented; `view.py` is the only absent module.

**Executive summary:** Three issues require immediate attention before validation: the `stability_for()` dead-code bug makes O(1) lookup silently degrade to O(n); the `stab is None` branch in `recompute_maturity()` violates FR-3 for proto terms; and `last_slope` sorts by `run_id` lexicographically which is meaningless for production UUIDs. Two design gaps need a decision: `view.py`'s `as_project_knowledge` has no interface contract, and OQ-5 (cross-project scope) is entirely absent from the sequencing plan.

| ID | Area | Severity | Summary |
|----|------|----------|---------|
| R1-S1 | Interfaces | high | `view.py` absent — FR-9 `as_project_knowledge` has no interface contract or implementation |
| R1-S2 | Architecture | high | `stability_for()` dead-code bug: computes `tid` then ignores it, O(n) scan instead of O(1) |
| R1-S3 | Data | high | `last_slope` sorts by lexicographic `run_id` — meaningless for UUID/hash run ids |
| R1-S4 | Architecture | high | Maturity L3 promoted when `stab is None` — violates FR-3 "stability ≥ θ" requirement |
| R1-S5 | Risks | medium | OQ-7 altitude gap: proto terms never receive determinism observations in the extractor |
| R1-S6 | Ops | low | OQ-5 (cross-project corpus scope) absent from the sequencing plan and `paths.py` |

---

#### R1-S1 — Interfaces — high
**Anchor:** Plan Step 8 / Module layout row `view.py`

**Finding:** `view.py` is listed in the module layout with two required functions: `as_project_knowledge(corpus, scope)` (FR-9) and `stability_for(target_file)` (FR-10). `stability_for` was correctly relocated inline to `registry.py`. However `as_project_knowledge` has no implementation and—critically—no interface contract. The `scope` parameter is undefined: it could mean a service scope, a file-path scope, or a maturity threshold. Without a concrete definition, FR-9 ("exposed a ProjectKnowledge-shaped view") cannot be tested or implemented.

**Suggestion:** Either (a) define `as_project_knowledge(corpus, min_maturity: int = 2) -> dict` with an explicit mapping to `project_knowledge/models.py` fields (`field_sets`, `negatives`, `interfaces`) in the plan, or (b) formally defer FR-9 to v2 and update the plan sequencing. If (a), document which corpus fields map to which `ProjectKnowledge` fields and what `min_maturity` gate applies. If (b), add a stub that raises `NotImplementedError` with a docstring pointing to the v2 ticket so the interface name is locked.

**Expected impact:** Prevents FR-9 from being a silent no-op when the postmortem wiring is validated. Gives implementers a concrete target.

---

#### R1-S2 — Architecture — high
**Anchor:** Plan Step 8 / `registry.py:stability_for()` (lines 106–112)

**Finding:** `stability_for(target_file)` at line 108 computes `tid = term_id_for_target(target_file)` then ignores it and performs an O(n) linear scan comparing `t.canonical_key == target_file`. The correct lookup is O(1) via `self._terms.get(tid)`. The current code is both wasteful and fragile: if a non-file-kind term has a `canonical_key` that happens to equal the target_file string, it would match incorrectly.

```python
# Current (buggy — dead variable + O(n) scan)
def stability_for(self, target_file: str) -> Optional[float]:
    tid = term_id_for_target(target_file)          # tid computed but never used
    for t in self._terms.values():
        if t.canonical_key == target_file:         # O(n), kind-unaware
            return t.determinism.success_stability
    return None

# Fix — O(1) dict lookup, kind-safe
def stability_for(self, target_file: str) -> Optional[float]:
    term = self._terms.get(term_id_for_target(target_file))
    return term.determinism.success_stability if term else None
```

**Suggestion:** Apply the one-line fix above. Add a unit test: seed a registry with one file-kind term, assert `stability_for(target_file)` returns the correct value AND that a different `target_file` returns `None`.

**Expected impact:** Correctness + performance. Eliminates the dead-code path and the false-match risk.

---

#### R1-S3 — Data — high
**Anchor:** Plan Step 5 / `corpus/models.py:Determinism.last_slope` (line 132)

**Finding:** `last_slope` sorts observations by `run_id` lexicographically (`for r in sorted(self.observations)`). For the bootstrap replay IDs (`"replay-{tgt}-p{i}"`), lexicographic ≈ insertion order, which is fine. For production run IDs derived from `stable_run_id()` — the function returns `cand.name` which starts with `"run-"` or `"gemini-"` followed by a hash (`benchmark-2b118f33dada` from the git status) — lexicographic order is hash order, not chronological. The slope is meaningless for real production runs.

**Suggestion:** Add a `observed_at: str` (ISO-8601) field to `Determinism.observations` entries (i.e., store `{"success": bool, "requirement_score": float|None, "observed_at": "<timestamp>"}`) and sort by `observed_at` when computing `last_slope`. Alternatively, if timestamps are unavailable, document that `last_slope` is `None` when run IDs are not sortably chronological and suppress it from classification logic. At minimum, plan Step 5 should state the ordering assumption explicitly.

**Expected impact:** Prevents misleading trend signals. The slope is used to determine "stabilized" state — a wrong ordering could flag degrading terms as stable.

---

#### R1-S4 — Architecture — high
**Anchor:** Plan Step 2 / `corpus/models.py:CorpusTerm.recompute_maturity()` (line 181)

**Finding:** `recompute_maturity()` contains:
```python
elif n_runs >= 3 and (stab is None or stab >= _STABILITY_HIGH):
    self.maturity = 3  # stable
```
The `stab is None` branch allows any term with zero determinism observations (i.e., all proto-level service/rpc/entity terms from bootstrap, which receive no `success/requirement_score`) to reach maturity L3 after appearing in 3 runs. FR-3 requires L3 = "≥3 runs **and** determinism.stability ≥ θ". This is a silent spec violation. The plan's Step 2 ("recompute `maturity` from `len(set(source_run_ids))` + `determinism.stability`") implies stability is required, not optional.

**Suggestion:** Change to `elif n_runs >= 3 and stab is not None and stab >= _STABILITY_HIGH:`. For terms that genuinely have no observations, they should cap at L2 until they accumulate determinism evidence. If proto terms are intentionally exempt from the stability requirement, add a separate maturity track for `kind in {"service", "rpc", "entity"}` with a documented rationale — do not silently bypass the stability gate for all unobserved terms.

**Expected impact:** Prevents inflated maturity for proto-level terms that have no stability evidence, which would cause false-positive `deterministic_candidate` classifications when crossed with classify_determinism.

---

#### R1-S5 — Risks — medium
**Anchor:** Plan Step 4 ("join per-feature PASS/FAIL from the postmortem keyed on `target_file` → `determinism`") / `extractor.py`

**Finding:** `extractor.py` correctly emits `file`-kind observations with determinism from the postmortem report. But the bootstrap seeds proto-level terms (`service`, `rpc`, `entity`, `metric`) that are never updated with determinism observations — the extractor skips any feature with no `target_files`, and proto terms have no `target_file`. The altitude gap is structural: a proto service `EmailService` maps to multiple files (`emailservice/logger.py`, `emailservice/email_server.py`, etc.), but nothing joins them. Plan Step 4 says the extractor should join PASS/FAIL "from the postmortem keyed on `target_file` → determinism" — but this join only works for `file`-kind terms, not proto-kind terms. As a result, proto terms accumulate to L3 on recurrence alone (see R1-S4).

**Suggestion:** Either (a) define a `service_to_files` mapping (derivable from the `prime-context-seed.json` `service_metadata`) and aggregate per-file observations up to the service level in the extractor, or (b) explicitly document in the plan that `service`/`rpc`/`entity` terms are determinism-unobserved in v1 and cap at L2. Option (b) is simpler for v1 and honest. The plan should state this limitation explicitly so the success criteria in §4 of the requirements can be correctly scoped.

**Expected impact:** Closes the altitude gap or correctly documents it. Prevents proto terms from claiming false-deterministic status.

---

#### R1-S6 — Ops — low
**Anchor:** Plan Sequencing section (S1→S9)

**Finding:** OQ-5 (cross-project corpus scope: `.startd8/` per-project vs `~/.startd8/corpus/` shared domain) is the focus file's top-ranked open question, yet it has zero representation in the S1→S9 sequencing. `paths.py` defines only `controlled_corpus_path()` (project-local). There is no `shared_corpus_path()` stub, no promotion mechanism, and no decision tree. The plan silently treats OQ-5 as a post-v1 concern without documenting that choice.

**Suggestion:** Add a Phase 2 stub to the sequencing: `S10 (Phase 2) — shared corpus scope: add `shared_corpus_path()` to `paths.py`; define promotion gate (maturity ≥4 AND n_observations ≥ N AND cross-project consent flag); implement `merge_into_shared(registry, shared_path)`.` Even if S10 is deferred, its interface (function names, promotion criteria) should be frozen in v1 so nothing in v1 blocks it. Also add a non-requirement: "v1 does NOT implement shared-corpus promotion" to the requirements doc.

**Expected impact:** Converts an open question into a documented decision. Locks the interface name so v1 code doesn't accidentally foreclose shared-corpus wiring.

---

#### Review Round R2 — claude-sonnet-4-6 — 2026-06-03

**Scope:** Second-pass dual-document review (plan + requirements). Fresh reviewer; read and deduped against R1. Grounded in live code not examined in R1: `prime_postmortem.py:1704–1708` (postmortem wiring guard), `extractor.py:50–67` (single-file selection), `FeaturePostMortem` fields, and the `corpus_building` flag gap. Endorses R1-S2, R1-S4.

**Executive summary:** Three production-class risks not in R1: (1) `project_root=None` silently writes the corpus to a per-run output directory, breaking cross-run accumulation; (2) corpus save failures are swallowed at `DEBUG` level — operators running with `INFO` will never know their corpus is not persisting; (3) the `corpus_building` provenance flag (FR-11, Plan Step 6) is entirely absent from the codebase. Two data-model gaps: the extractor silently discards all but the first `target_file`, and `disk_quality_score >= 0.9` is misused as a proxy for binding provenance confidence.

| ID | Area | Severity | Summary |
|----|------|----------|---------|
| R2-S1 | Risks | critical | `project_root=None` fallback writes corpus to output_dir — breaks cross-run accumulation |
| R2-S2 | Ops | high | Corpus save failure is swallowed at DEBUG — invisible to operators running INFO+ |
| R2-S3 | Architecture | medium | `corpus_building` provenance flag (FR-11, Plan Step 6) not defined or stored anywhere |
| R2-S4 | Data | medium | Extractor takes `target_files[0]` only — multi-file features lose all but one target |
| R2-F1 | Data | high | `confidence="explicit"` when `disk_quality_score >= 0.9` is a semantic mismatch with FR-2's binding-provenance intent |
| R2-F2 | Architecture | medium | `classify_determinism` "mixed" spans two distinct remediation paths, not one |
| R2-F3 | Validation | medium | FR-13 (OTel) has no named metrics, units, or testable acceptance criteria |

---

#### R2-S1 — Risks — critical
**Anchor:** Plan Step 6 ("load → merge → save the persistent corpus") / `prime_postmortem.py:2977–2980`

**Finding:** `_extract_corpus` builds the corpus path as:
```python
corpus_path = (
    controlled_corpus_path(Path(project_root)) if project_root
    else Path(output_dir) / "controlled-corpus.json"
)
```
When `project_root` is `None` (a legitimate caller state — the evaluator has no project_root if run from a batch script without `--project-root`), the corpus is written to `output_dir/controlled-corpus.json`. Each postmortem run with a different `output_dir` produces a new, isolated corpus file. The cross-run accumulation promised by FR-4/5 silently never happens. Worse, every subsequent run with `project_root=None` re-loads an empty corpus (the previous run's file is in a different directory), so the merge is always from scratch. No error or warning is emitted.

**Suggestion:** (a) Log a `WARNING` when `project_root is None` and fall back to the output_dir path, so operators know accumulation is degraded. (b) Alternatively, derive the project root from `output_dir` by walking upward to find `.startd8/` (the same strategy `stable_run_id()` uses to find `run-*` ancestors) — if found, use that as the project root. (c) Make `project_root` a required parameter at the call site and fail loudly if absent, since the whole value proposition requires a stable project-level path. Document the chosen behavior explicitly in Step 6.

**Expected impact:** Prevents silent accumulation failure in any deployment where `project_root` is not explicitly wired. This is the most severe operational gap — all runs would appear to succeed but the corpus would never grow.

---

#### R2-S2 — Ops — high
**Anchor:** Plan Step 6 / `prime_postmortem.py:1705–1708`

**Finding:**
```python
try:
    self._extract_corpus(report, project_root, output_dir)
except Exception:
    logger.debug("Corpus extraction failed (non-fatal)", exc_info=True)
```
Any failure — disk full, permissions error, JSON corruption, save() crash — is logged at `DEBUG` level and silently discarded. An operator running with the default `INFO` log level (or `WARNING`) will never see the failure. Since corpus accumulation is silent-on-success (only the INFO line inside `_extract_corpus` on success), a perpetually-failing corpus is indistinguishable from a healthy one in the logs. The plan's Step 6 ("load → merge → save") implies each save is required; if save silently fails, the maturity and determinism evidence is lost for that run.

**Suggestion:** Raise the failure log to `WARNING` level (not ERROR — non-fatal is appropriate, but WARNING means it appears in default deployments): `logger.warning("Corpus extraction failed — run %s will not be accumulated: %s", stable_run_id(output_dir), exc)`. If a failure rate metric is tracked (FR-13), emit a corpus extraction failure counter increment here so degradation is observable in Grafana.

**Expected impact:** Makes corpus degradation visible before the corpus becomes so stale it produces bad determinism classifications. This is a one-line fix with high operational value.

---

#### R2-S3 — Architecture — medium
**Anchor:** Plan Step 6 ("A `corpus_building` provenance flag labels deliberate accumulation runs (FR-11)") / `_extract_corpus` / `TermObservation` / `CorpusTerm`

**Finding:** The `corpus_building` flag is mentioned in Plan Step 6 and is a named deliverable in FR-11: "no separate engine — only a flag/marker so its provenance is labeled." Searching the codebase: this flag does not exist in `TermObservation`, `CorpusTerm`, `ControlledCorpusRegistry.merge_run()`, `_extract_corpus()`, or anywhere else. The corpus cannot distinguish normal production runs from deliberate corpus-building runs. Provenance audits (which runs drove maturity promotions?) are impossible.

**Suggestion:** Define a minimal provenance field: add `corpus_building: bool = False` to the run-level merge call and store it in `source_run_ids` as a tuple or in a separate `run_provenance: Dict[str, Dict]` dict on `CorpusTerm` (e.g., `{run_id: {"corpus_building": bool, "observed_at": ...}}`). The flag should be passable from the CLI or `PrimeContractorWorkflow` to `_extract_corpus`. This is low-effort (one parameter through the call chain) but closes the FR-11 provenance gap.

**Expected impact:** Enables corpus-building run identification for auditing, trend analysis, and future cross-project promotion decisions (OQ-5) where only human-curated runs should seed the shared corpus.

---

#### R2-S4 — Data — medium
**Anchor:** Plan Step 4 ("read the per-feature PASS/FAIL + `target_file` to update `determinism`") / `extractor.py:52`

**Finding:** `target = target_files[0]` — the extractor silently takes only the first target file when a feature specifies multiple. In the 17-feature Python cluster this is invisible (most features generate one file). But `FeaturePostMortem.target_files` is a list, and Go / Node.js / Vue features regularly generate 2–4 files per feature (e.g., `server.go` + `handler.go` + `types.go` for a single RPC implementation). For those features, only `server.go` accumulates determinism; `handler.go` and `types.go` are never observed in the corpus, even though they were part of the same PASS/FAIL outcome. This also means calling `stability_for("handler.go")` will always return `None` even for a perfectly stable feature.

**Suggestion:** Emit one `TermObservation` per `target_file` in the list — all carrying the same `success/requirement_score/surface_form` from the feature. The `canonical_key` and `term_id` differ per file (since they're anchored on `target_file`), so each gets its own corpus entry. This is a loop of one to three lines in the extractor:
```python
for target in target_files:  # was: target = target_files[0]
    obs.append(TermObservation(..., canonical_key=canonical_key("file", surface, target), ...))
```
Update Plan Step 4 to state "one observation per `target_file`".

**Expected impact:** Closes the multi-file coverage gap. Increases corpus density for non-Python languages. Required for SCR triage (FR-10) to have stability data on all generated files.

---

**Endorsements:**
- R1-S2 (dead-code `stability_for()`) — agree; this is a correctness bug that makes FR-10 unreliable. Highest triage priority of R1's S-items.
- R1-S4 (maturity L3 when `stab is None`) — agree; closes the spec violation. Should be paired with R1-F2 triage.

**Disagreements:** none.

---

#### Review Round R3 — claude-sonnet-4-6 — 2026-06-03

**Scope:** Third-pass dual-document review. Deduped against R1-S1/S2/S3/S4/S5/S6 and R2-S1/S2/S3/S4. Note: R1-S1 and R1-S2 appear **resolved in the live codebase** — `view.py` exists with `triage_signal`/`should_escalate`/`stable_authorities`/`as_project_knowledge`, and `stability_for()` now correctly uses `find_by_canonical_key()`. These should be moved to Appendix A by the orchestrator. New territory: `SOURCE_PRECEDENCE` divergence (the focus file's explicit ask #6), `stable_authorities()` semantic filter gap, `should_escalate()` threshold decoupling, and the `corpus_class` stored-computed anti-pattern.

**Executive summary:** Three issues that R1/R2 didn't reach. The focus file's item 6 ("interface fidelity to real seams") is partially unresolved: corpus `SOURCE_PRECEDENCE` has forked from `forward_manifest_extractor._SOURCE_PRECEDENCE` by adding `"inferred"=1`, `"framework-conventions"=1`, and `"human"=3` — labels that forward_manifest either doesn't recognize or would treat as precedence 0. `stable_authorities()` includes `"unobserved"` terms (maturity≥2, zero determinism observations) as prompt authorities. And `should_escalate()`'s `stability_threshold` default is hardcoded independently from `_STABILITY_HIGH`, creating a silent drift risk.

| ID | Area | Severity | Summary |
|----|------|----------|---------|
| R3-S1 | Architecture | high | `SOURCE_PRECEDENCE` in corpus has forked from `forward_manifest._SOURCE_PRECEDENCE` — impedance mismatch (focus item #6) |
| R3-S2 | Data | high | `stable_authorities()` includes `"unobserved"` terms (maturity≥2 but zero observations) as prompt authorities |
| R3-S3 | Risks | medium | `should_escalate(stability_threshold=0.95)` is decoupled from `_STABILITY_HIGH` — can drift independently |

---

#### R3-S1 — Architecture — high
**Anchor:** Plan Reuse Map row "Binding source precedence — `forward_manifest` `SOURCE_PRECEDENCE` / `ManifestMerger`" / `corpus/models.py:33–42`

**Finding:** The plan says "Reuse that precedence ordering for binding conflicts." The live `forward_manifest_extractor.py:_SOURCE_PRECEDENCE` has exactly four values:
```python
{"source-ast": 0, "deterministic": 1, "reference-ast": 2, "human-yaml": 3}
```
The corpus `corpus/models.py:SOURCE_PRECEDENCE` has eight:
```python
{"source-ast": 0, "inferred": 1, "deterministic": 1,
 "framework-conventions": 1, "reference-ast": 2, "proto": 2,
 "human-yaml": 3, "human": 3}
```
Three values exist only in the corpus: `"inferred"`, `"framework-conventions"`, `"human"`. In `ManifestMerger`, unknown values get `.get(key, 0)` → precedence 0 (same as `source-ast`). So a corpus binding with `source_reference="inferred"` (precedence 1 in corpus) would be treated as lowest-tier by `ManifestMerger`. A corpus binding with `source_reference="human"` (precedence 3 in corpus) would also be treated as 0 by `ManifestMerger`. The two precedence tables have permanently diverged without a comment explaining the fork or a test asserting they're compatible.

Additionally, `"proto"` appears in corpus at precedence 2 but is absent from `_SOURCE_PRECEDENCE` in the extractor (where proto contracts come in via a separate code path). The plan says "reuse" — the correct design would be `from startd8.forward_manifest_extractor import _SOURCE_PRECEDENCE as _FM_PREC` and augment it, not define a parallel constant.

**Suggestion:** (a) Import `_SOURCE_PRECEDENCE` from `forward_manifest_extractor` as the base and extend it: `SOURCE_PRECEDENCE = {**_FM_PREC, "inferred": 0, "framework-conventions": 1, "proto": 2, "human": 3}`. This makes the corpus a superset of the extractor's ordering with explicit extension semantics. (b) Add a module-level assertion that every key in `_FM_PREC` appears in corpus `SOURCE_PRECEDENCE` with the same or compatible value. (c) Add a comment: "corpus extends forward_manifest SOURCE_PRECEDENCE; do not change shared values." This converts a silent fork into a documented extension.

**Expected impact:** Closes the focus-file item #6 concern about impedance mismatches. Ensures binding conflicts between corpus-sourced and manifest-sourced bindings resolve consistently across both systems.

---

#### R3-S2 — Data — high
**Anchor:** Plan Step 8 / `corpus/view.py:stable_authorities()` (lines 73–100)

**Finding:** `stable_authorities()` filters by `t.maturity < min_maturity` and `t.determinism.corpus_class == "false_pass_risk"`, but does NOT filter on `corpus_class == "unobserved"`. Proto-level terms (service, rpc, entity) bootstrapped via `bootstrap.py` reach maturity L2 after two runs (via `recompute_maturity()`) without any success/fail observations. Their `corpus_class` is `"unobserved"` (from `classify_determinism(stability=None, ...)`). These terms pass both filters and are included in `stable_authorities()` — injected into prompts as "established project vocabulary." The generation pipeline would receive authority signals (e.g., "use `CartService.AddItem` exactly") that have zero empirical backing from actual run outcomes.

**Suggestion:** Add `if t.determinism.corpus_class == "unobserved": continue` to the filter loop in `stable_authorities()`. Proto-level terms without any success/fail evidence should be excluded from prompt authorities even if they're at maturity L2. Alternatively, add a minimum-observations gate: `if t.determinism.n_observations == 0: continue`. Update the plan's Step 8 description: "v1 authorities: terms with maturity≥2 AND n_observations>0 AND not false_pass_risk."

**Expected impact:** Prevents zero-evidence terms from being injected as authorities. Keeps the prompt authority signal grounded in measured outcomes, not just vocabulary extraction.

---

#### R3-S3 — Risks — medium
**Anchor:** Plan Step 5 ("class by thresholds (≥0.95 candidate / <0.7 gap)") / `corpus/view.py:should_escalate()` (line 55)

**Finding:** `should_escalate()` has `stability_threshold: float = 0.95` — numerically matching `_STABILITY_HIGH = 0.95` in `models.py`, but defined independently. If R1-F5 is accepted and `_STABILITY_HIGH` is made configurable (or recalibrated from 0.95 to, say, 0.92 based on more data), `should_escalate()`'s default will not update. Two calls to the same conceptual "is this binding stable enough to skip SCR review" threshold with potentially different numbers. This is a silent drift risk: the corpus classifies a term as `"deterministic_candidate"` (using `_STABILITY_HIGH=0.92`) but `should_escalate()` still escalates it (using `stability_threshold=0.95`).

**Suggestion:** Replace the hardcoded default with `from startd8.corpus.models import _STABILITY_HIGH` and use `stability_threshold: float = _STABILITY_HIGH`. This creates a single source of truth for the stability gate. If `_STABILITY_HIGH` becomes a configurable constant (per R1-F5), `should_escalate()` inherits the update automatically. Also: `should_escalate()` should check `corpus_class == "unobserved"` explicitly (returning `True`) rather than relying on `stab is None` — the intent is clearer.

**Expected impact:** Eliminates the threshold drift risk. Ensures `classify_determinism` and `should_escalate` use the same numerical boundary for what counts as stable.

---

**Endorsements:**
- R2-S1 (`project_root=None` silent accumulation break) — critical; highest operational severity in R1+R2.
- R2-S4 (`target_files[0]` only) — agree; easy fix with significant corpus density improvement for multi-language projects.
- R1-F2 (FR-3 ban L3 for unobserved terms) — still the highest-priority requirements item; directly causes R3-S2's issue.

**Correction note for orchestrator:** R1-S1 ("view.py absent") and R1-S2 ("stability_for dead-code bug") are RESOLVED in the live code. `view.py` exists with all four functions; `stability_for()` now delegates to `find_by_canonical_key()`. Please move both to Appendix A.

---

#### Review Round R4 — claude-sonnet-4-6 — 2026-06-03

**Scope:** Fourth-pass dual-document review. Deduped against R1–R3. Partial resolutions noted: R2-S1 now warns and uses `controlled_corpus_path()` cwd fallback (not per-run `output_dir`); R2-S2 save failures log at `WARNING`. New territory: FR-5 extractor vs plan Step 4 seed contract, FR-9 consumer wiring, validation harness vs §4 success criteria, and the plan's missing `corpus_enabled` gate.

**Executive summary:** The largest functional gap vs the written plan: Step 4 promises proto/forward_manifest extraction from `prime-context-seed.json`, but `extract_corpus_from_run()` only reads `FeaturePostMortem` rows — Layer 1–2 corpus terms never accumulate in production. Two low-effort wins: wire `render_authorities_md()` into the spec prompt path (FR-9 value without rewriting ProjectKnowledge producer), and point the plan's validation section at the existing `tests/unit/corpus/` suite plus a mandatory bootstrap replay test for §4.

| ID | Area | Severity | Summary |
|----|------|----------|---------|
| R4-S1 | Architecture | critical | Step 4 / FR-5: extractor does not read `prime-context-seed.json` — proto + explicit bindings never produced at postmortem |
| R4-S2 | Interfaces | medium | `render_authorities_md()` implemented but no plan step wires it into generation prompts (FR-9 end-user value) |
| R4-S3 | Ops | medium | Plan `corpus_enabled` flag absent — corpus always runs; no operator off-switch |
| R4-S4 | Validation | medium | Plan validation omits existing unit tests; no CI gate for §4 bootstrap replay / order-independence |

---

#### R4-S1 — Architecture — critical
**Anchor:** Plan Step 4 ("read `prime-context-seed.json` (proto-derived terms … EXPLICIT forward_manifest contracts → bindings; `service_metadata`)") / `extractor.py:45–68`

**Finding:** Step 4 and FR-5 describe a postmortem extractor that ingests both the postmortem report **and** the run seed. The live `extract_corpus_from_run(report, run_id)` iterates only `report.features` and emits `file`-kind observations from `target_files[0]`. It never opens `prime-context-seed.json`, never calls `extract_corpus_v0.py:parse_proto`, and never maps EXPLICIT forward_manifest contracts into `Binding` rows. Bootstrap (`bootstrap.py`) seeds proto/SRE terms via a one-shot CLI — but production postmortem runs do **not** re-execute that path. The v0 corpus's Layer 1 (9 services, 15 RPCs, 32 entities) and Layer 2 (explicit bindings) are therefore **frozen at bootstrap time** and cannot grow from normal runs. This is the core "runs as producers" promise (FR-11) unfulfilled for half the corpus layers.

**Suggestion:** Split Step 4 into two extractor functions with a single `merge_run` call site: (a) `extract_file_terms_from_postmortem(report, run_id)` — current behavior, one obs per `target_file`; (b) `extract_seed_terms_from_context(output_dir, run_id)` — read `prime-context-seed.json` (latest-by-mtime if multiple, same rule as SCR), emit `service`/`rpc`/`entity`/`metric` observations with `source_reference="proto"` or `"human-yaml"`. Wire both in `_extract_corpus` before `registry.merge_run`. Reuse `docs/design/controlled-corpus/extract_corpus_v0.py:parse_proto` rather than re-parsing. Add an integration test: postmortem on a trove run increases `kind=service` term count or updates `surface_forms` without re-running bootstrap.

**Expected impact:** Makes FR-5 truthful. Unlocks cross-run growth of the vocabulary layer — the primary user value of the corpus beyond per-file stability.

---

#### R4-S2 — Interfaces — medium
**Anchor:** Plan Step 8 ("`view.as_project_knowledge(scope)` + `view.stability_for(target_file)`") / `view.py:render_authorities_md`

**Finding:** Step 8 delivers read views, and `render_authorities_md()` produces a ready-to-inject markdown block ("Established project vocabulary …"). No sequencing step connects this to the generation pipeline. `implementation_engine/` has no reference to `stable_authorities` or `render_authorities_md`. FR-9 correctly defers rewriting the `ProjectKnowledge` producer, but the plan never states **where** corpus authorities enter prompts. Operators get accumulation with zero generation benefit — the main end-user payoff is deferred indefinitely.

**Suggestion:** Add **Step 8b (FR-9 wiring, v1 minimal)**: in `build_spec_prompt()` (or the lead-contractor spec path), if `.startd8/controlled-corpus.json` exists and `ControlledCorpusRegistry.load()` returns terms with `maturity >= 2`, append `render_authorities_md(registry)` as a P2 section (below requirements, above kaizen hints). Gate behind `corpus_authorities_enabled` (default on when corpus file exists). Document in the plan reuse map: "Consumer: `implementation_engine/spec_builder.py` ← `corpus.view.render_authorities_md`". One integration test: corpus with a mature `EmailService` term → spec prompt contains the canonical name.

**Expected impact:** Low-hanging fruit — ~20 lines of wiring for immediate reduction of title drift in generation. Delivers FR-9 user value without the full ProjectKnowledge producer rewrite.

---

#### R4-S3 — Ops — medium
**Anchor:** Plan Sequencing closing line ("Implement behind a `corpus_enabled` flag (default on at postmortem; zero effect on generation in v1)")

**Finding:** The plan explicitly sequences a `corpus_enabled` flag. No such flag exists in `PrimePostMortemEvaluator`, CLI, or environment config. `_extract_corpus` is always invoked inside a try/except (non-fatal). Operators cannot disable corpus I/O during large batch replays, corpus corruption recovery, or A/B runs where accumulation would pollute the registry. This contradicts the plan's stated default-on-but-disableable design.

**Suggestion:** Add `corpus_enabled: bool = True` to the postmortem evaluator constructor (or read `STARTD8_CORPUS_ENABLED=0`). Guard `_extract_corpus` with `if not self.corpus_enabled: return`. Document in Step 6. Pair with FR-11's `corpus_building` marker (R2-S3): `corpus_building=True` implies `corpus_enabled=True` but not vice versa.

**Expected impact:** Operational control without removing the feature. Enables safe debugging and selective accumulation runs.

---

#### R4-S4 — Validation — medium
**Anchor:** Plan section "Risks & validation" / §4 success criteria in requirements

**Finding:** The plan's validation paragraph describes replaying the 17-feature anchor cluster but does not reference the **existing** test suite: `tests/unit/corpus/test_corpus_registry.py` (idempotency, order-independence, false_pass_risk, title drift), `test_corpus_view.py` (SCR triage, authorities), `test_corpus_extractor.py` (extractor + optional trove integration). There is no test that runs `bootstrap.py` output through merge permutations to assert §4's byte-identical criterion on the full labeled set. `test_real_trove_cross_run_accumulation` is `skipif` trove absent — CI will not catch regressions on the empirical harness.

**Suggestion:** Update "Risks & validation" to: (1) list the three unit modules as the v1 regression gate (`pytest tests/unit/corpus/ -v`); (2) add **S9b**: commit a golden `controlled-corpus-golden.json` generated from bootstrap + permuted merge order (17-file subset), assert byte-identical on CI; (3) mark trove test as optional nightly, not release-blocking. Align plan Step 9 (OTel) with FR-13 metric names from R2-F3 when implemented.

**Expected impact:** Closes the gap between §4's ambitious success criteria and what CI actually enforces. Makes order-independence (focus item #5) continuously verified, not demo-only.

---

**Endorsements:**
- R4-S1 adjacent: R1-S5 (OQ-7 altitude) — seed extraction is the structural fix; file-only extractor cannot close OQ-7 without it.
- R3-S1 (`SOURCE_PRECEDENCE` fork) — still unresolved; blocks correct binding merge when seed path is added.
- R2-S4 (`target_files[0]` only) — do before seed work; multi-file obs are independent.

**Disagreements:** none.

---

## Requirements Coverage Matrix — R1

| FR / Section | Plan Coverage | Status |
|---|---|---|
| FR-1 (persistent registry, atomic save, schema_version, empty-on-missing) | Step 2 / registry.py | Covered |
| FR-2 (corpus entry shape) | Step 1 / models.py | Covered |
| FR-3 (maturity ladder, promotion from recurrence+stability) | Step 2 / recompute_maturity | Partial — `stab is None` violates L3 spec (R1-S4) |
| FR-4 (idempotent+order-independent merge, SOURCE_PRECEDENCE) | Step 2 / _merge_bindings | Covered |
| FR-5 (production at postmortem, load→merge→save) | Step 6 / prime_postmortem.py edit | Covered |
| FR-6 (bootstrap from v0.json + replay set) | Step 7 / bootstrap.py | Covered |
| FR-7 (stability per target_file, last_slope) | Step 5 / Determinism | Partial — last_slope sort order undefined (R1-S3) |
| FR-8 (two-axis classification, false_pass_risk) | Step 5 / classify_determinism | Partial — req_score=None treated as verified (see F1 in requirements) |
| FR-9 (ProjectKnowledge view) | Step 8 / view.py | Gap — view.py absent, interface undefined (R1-S1) |
| FR-10 (SCR triage read interface) | registry.stability_for() | Partial — dead-code bug (R1-S2) |
| FR-11 (corpus-building runs via flag) | Step 6 / corpus_building flag | Covered |
| FR-12 (provenance, corpus_version, last_updated) | registry.save() | Covered |
| FR-13 (OTel metrics) | Step 9 / not yet implemented | Gap — no OTel emit in corpus package |
| OQ-5 (cross-project scope) | Not in sequencing | Gap (R1-S6) |
| OQ-6 (surface-form canonicalization) | canonical.py | Covered — target_file-anchored v1 decision documented |
| OQ-7 (term↔target_file altitude) | Not in extractor | Partial — proto terms altitude unresolved (R1-S5) |
