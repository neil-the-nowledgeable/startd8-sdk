# Manifest-Driven Name Repair — Implementation Plan

**Version:** 1.4 (Post-CRP — R1+R2+R3+R4 triaged, 20/20 S-suggestions applied)
**Date:** 2026-06-01
**Status:** Draft for review — pairs with `MANIFEST_DRIVEN_NAME_REPAIR_REQUIREMENTS.md` v0.6

> Builds the post-generation repair backstop for run-011 Gap A (invented Prisma
> fields) + Gap B (invented TS import paths). Deterministic, no LLM, abstain-safe.
> Every step traces to a FR; every FR has a step.

---

## 0. Strategy & sequencing

Six increments, each independently testable, ordered so the truth-derivation core is
proven before it is wired into the live integration path:

```
Inc 1  TruthSource seam + truth re-derivation        (FR-2, FR-10)   — pure, no pipeline
Inc 2  Diagnostics + routing rows + content bridge    (FR-4)          — wiring, no behavior
Inc 3  Nearest-match engine (rewrite/abstain)         (FR-3, NFR-3)   — pure, decision core
Inc 4  The two repair steps                           (FR-5, FR-6)    — text rewrite + guard
Inc 5  Lift detection into pre-merge path             (FR-1, FR-7)    — integration seam
Inc 6  run-011 reproduction harness + observability   (FR-8, FR-9)    — headline gate
```

Inc 1–4 are pure/unit-testable with no pipeline dependency (de-risks the core). Inc 5 is
the only change to `integration_engine.py` — and it is the **riskiest** increment. Three CRP
rounds peeled it back: the pre-merge seam short-circuits **twice** internally (845-846 **and**
851-855), excludes `.ts`/`.tsx` (866), writes in place (879-882), updates the element registry
**before** re-validation (884-892 vs 895), and — the deepest gate, found in R3 — the method is
only *called* when `pre_validate` already FAILED (**2313-2317**), so it never runs for
clean-syntax invented names at all. `content_contract` is also absent from the default
`repairable_categories` (config.py:67) and `pre_checkpoint_repair` (config.py:68) is documented
but unwired. And the **exit** path (R4) is as load-bearing as the entry: an abstain leaves
`any_modified=False` → `return None` (910) → the file silently merges, so abstains must
synthesize a FAILED result, and re-validation must be strict-subset so a kept abstain doesn't
roll back a successful partial repair. Inc 5 (§6, steps 0-6) is redesigned around all of these.
Inc 6 is the acceptance gate.

---

## 1. Key seams (confirmed by grounding)

| Seam | Location | Role |
|------|----------|------|
| Pre-merge repair hook | `contractors/integration_engine.py:786 _attempt_pre_merge_repair` | where FR-1 detection + FR-5/6 repair slot in |
| Repair entry | `repair/orchestrator.py:499 run_file_repair(files, diagnostics, …)` | drives routed steps over files |
| Routing | `repair/routing.py` — `_ROUTING_TABLE`, `route_failures`, `_STEP_FACTORIES`, `_CANONICAL_ORDER` | add patterns + step factories |
| Diagnostic→step bridge precedent | `repair/semantic_bridge.py:translate_to_diagnostics` | pattern to mirror for content-contract bridge |
| Prisma truth | `languages/prisma_parser.py` — `parse_prisma_schema`, `PrismaModel.field_names`, `PrismaSchema.model(name)` | field-set derivation |
| Import truth | `contractors/upstream_interface.py:91 resolve_specifier_to_paths`; `extract_ts_exports`; `validators/cross_file_imports._resolves_on_disk` | path/export derivation |
| Detection (unchanged) | `validators/prisma_usage.py:scan_prisma_usage`, `validators/cross_file_imports.py:scan_unresolvable_imports` | trigger/locator source |
| Step protocol | `repair/protocol.py RepairStep`, `repair/models.py RepairStepResult` | new steps conform |

---

## 2. Increment 1 — TruthSource seam + re-derivation (FR-2, FR-10)

**New file:** `src/startd8/repair/truth_source.py`

- `class TruthSource(Protocol)`:
  - `prisma_fields(model: str) -> frozenset[str]` — valid field set, `frozenset()` if unknown.
  - `module_paths() -> Mapping[str, str]` — canonical specifier per logical module + the
    seeded negative→canonical map (`@/lib/prisma → @/lib/db`, `@/lib/ai/client → @/lib/ai/service`).
  - `resolvable_specifiers() -> frozenset[str]` — on-disk-resolvable import specifiers.
- `class LiveDiskTruthSource(TruthSource)` (v1):
  - lazily `parse_prisma_schema(Path(project_root)/"prisma"/"schema.prisma")`; cache per
    `project_root`. Missing schema → `prisma_fields` returns empty (NFR-3 degrade).
  - module paths from `extract_ts_exports` over project `lib/**` + `tsconfig` `paths`;
    on-disk resolution reuses `resolve_specifier_to_paths` / `_resolves_on_disk`.
  - seeded negatives as a module-level constant `_KNOWN_INVENTIONS` (extensible).
- **Approach-A backend (stub for FR-10):** `ArtifactTruthSource(artifact_path)` reading
  `forward_project_knowledge.json` — interface only, raises `NotImplementedError` until
  Approach A ships. Documents the swap point.

**Tests:** `tests/unit/repair/test_truth_source.py` — against a fixture schema +
fixture `lib/` tree: `prisma_fields("Capability")` == real set (no `aiRefId`);
`module_paths()["@/lib/prisma"] == "@/lib/db"`; missing schema → empty, no raise.

## 3. Increment 2 — Diagnostics + routing + content bridge (FR-4)

**Edit `repair/models.py`:** add
```python
@dataclass
class MisnamedFieldDiagnostic(Diagnostic):
    field: str = ""; model: str = ""; call_site_hint: str = ""
    def __post_init__(self): self.category = "content_contract"

@dataclass
class WrongImportPathDiagnostic(Diagnostic):
    specifier: str = ""
    def __post_init__(self): self.category = "content_contract"
```

**Additive `model` field on `PrismaUsageViolation` (R1-S3 — resolved).** The bridge cannot
read the model from the scan: `accessor` and `model_name` are function-locals in
`scan_prisma_usage` (verified `prisma_usage.py:134,185`), and the returned frozen dataclass
carries only `kind/source_file/field/detail/severity` (lines 41-49) — the model is embedded
in `detail` prose only. **Decision:** add a single additive field
`model: str = ""` to `PrismaUsageViolation` and populate it at the two construction sites that
already have `model_name` in scope. This is additive-only (NFR-6 amended in requirements
v0.3); the postmortem ignores it. *Rejected:* regex-parsing the model from `detail` (couples
repair to a human-readable string format).

**New file `repair/content_bridge.py`** (mirrors `semantic_bridge.translate_to_diagnostics`):
`scan_results_to_diagnostics(prisma_violations, import_violations) -> List[Diagnostic]`,
reading the now-structured `violation.model` into `MisnamedFieldDiagnostic.model`.

**Edit `repair/routing.py`:** add rows to `_ROUTING_TABLE`
```python
("content_contract", "prisma_unknown_field", ["prisma_field_rename", "js_syntax_validate"], "HIGH", "nodejs"),
("content_contract", "unresolvable_import", ["import_path_rename", "js_syntax_validate"], "HIGH", "nodejs"),
```
register factories in `_STEP_FACTORIES`; insert the two step names into `_CANONICAL_ORDER`
**before** `js_syntax_validate`.

**Add `content_contract` to `RepairConfig.repairable_categories` (R3-S2 — high).** The default
at `repair/config.py:67` is `frozenset({"syntax","import","lint","semantic","security",
"convention"})` — it omits `content_contract`. `route_failures` filters on this set at
`routing.py:290` (`if cat not in config.repairable_categories: continue`), **independently** of
the integration_engine `repairable` check (R2-S1). Both filters must admit `content_contract`
or the new routes are a silent no-op. Update the default + any prime-contractor config examples.

**Tests:** `test_routing.py` additions — new patterns return the new steps **with the default
`RepairConfig`**; a config that excludes `content_contract` skips them with an explicit log;
**snapshot the existing table to prove no existing route changed** (FR-4 regression guard).

## 4. Increment 3 — Nearest-match engine (FR-3, NFR-3)

**New file `repair/name_resolution.py`:** pure functions, no I/O.
- `best_match(invented, candidates, *, cutoff=0.6, margin=0.1) -> MatchDecision`.
- `MatchDecision = {decision: "rewrite"|"abstain", target: str|None, similarity: float, reason: str}`.
- **No `structural` parameter (R4-S3 — resolved).** Earlier drafts passed `structural=True` to
  force-abstain FK inventions, but **nothing produces that signal** — `MisnamedFieldDiagnostic`
  carries no FK flag and the detection scan only knows the field is unknown. v1 drops the
  parameter and relies on the **`no_candidates`** branch: a presumed FK like `Metric.outcomeId`
  has no near-match in `Metric`'s field set (`name, value, unit, direction, timeframe,
  description, notes`), so `get_close_matches` returns empty → abstain `no_candidates`. (Residual
  risk: a structural invention that *happens* to be near a real field would rewrite; deferred —
  if it bites, add an `is_fk_heuristic` field to the diagnostic later. Logged as a known v1
  limitation, not a silent cap.)
- **Decision branching (R1-S5 — fully specified).** Call
  `difflib.get_close_matches(invented, candidates, n=2, cutoff)` and branch on the count that
  clears the cutoff:
  - **0** → abstain `no_candidates` (also covers empty/`below_cutoff`).
  - **1** → **rewrite** to that candidate (no runner-up; margin vacuously satisfied).
  - **2** → compute `Δ = ratio(invented, c0) − ratio(invented, c1)` via
    `difflib.SequenceMatcher`; rewrite to `c0` iff `Δ ≥ margin`, else abstain `ambiguous_tie`
    (exactly-equal scores `Δ = 0` always abstain).

**Tests:** parametrized `test_name_resolution.py` covering the branches: `title`→`name`
(single dominant); `supportingEvidence`→`evidence`; `label` vs `{name, notes}` →
`ambiguous_tie`; empty candidates → `no_candidates`; two equal-scoring candidates → abstain;
**`outcomeId` vs `Metric`'s real fields → `no_candidates`** (the FK case handled without a
`structural` flag, R4-S3). This file is where OQ-4 (cutoff/margin) is tuned against the run-011
set.

## 5. Increment 4 — The two repair steps (FR-5, FR-6)

**New `repair/steps/prisma_field_rename.py`** — `RepairStep`, TS-text-based (regex over the
flagged `db.<model>.{create,update,where,upsert}({ … })` object-literal call sites, brace-
matched like the Go/C# text splicers — **not** Python AST):
- pull `MisnamedFieldDiagnostic`s from `context.diagnostics`; for each, candidates =
  `truth_source.prisma_fields(d.model)`; `best_match`; if rewrite, replace the **key** at the
  flagged call site only; else record abstain in `metrics`.
- never touches identifiers outside the flagged object literal.
- **Nesting scope (R1-S9 — bounded, abstain on the rest).** v1 rewrites **only top-level keys
  of the call-arg object literal** (the level the scan flags: `create`/`update`/`where`/`data`
  bodies). It **abstains** — never blind-rewrites — on constructs the flat matcher can't bound:
  nested object values (`data: { nested: { … } }`), spreads (`...obj`), computed/template-literal
  keys (`[k]:`), and relation-filter objects. Abstain reason `unbounded_construct`. This keeps a
  stray `aiRefId` deep inside an unrelated nested object from being corrupted.

**New `repair/steps/import_path_rename.py`** — `RepairStep`:
- for each `WrongImportPathDiagnostic`, first consult `truth_source.module_paths()` negatives
  (exact seeded map), then nearest-match against `resolvable_specifiers()`; sub-path collapse
  (`@/lib/db/<x>` → `@/lib/db`) only when the parent resolves on disk (OQ-6: no speculative
  collapse). Rewrite the specifier in `import … from '…'` / `require('…')`; else abstain.

Both register in `repair/steps/__init__.py` and the routing factories (Inc 2). Both rely on
the per-step non-destructive guard already applied by the orchestrator between steps (FR-7
first half).

**Tests:** `test_prisma_field_rename.py`, `test_import_path_rename.py` — unit-level with a
stub `TruthSource`: rewrite happy-path, abstain on structural/ambiguous, abstain on
nested/spread/computed-key fixtures (R1-S9 — never edit a nested unrelated key), idempotence
(re-running over repaired output is a no-op), and "only the flagged call site is touched."
- **Multi-model fixture (R1-S8 — resolves OQ-7 with a test, not just prose).** One `.ts` file
  with `db.capability.create({ aiRefId })` **and** `db.metric.update({ name })` where `name` is
  valid on `Metric`: assert `aiRefId` rewrites against `Capability`'s field set only, and the
  `Metric` call site is untouched — proving per-call-site model binding survives the
  bridge→step path. (This is also what makes the additive `model` field load-bearing.)

## 6. Increment 5 — Lift detection into the pre-merge path (FR-1, FR-7)

> **CRP-corrected (R1-S1/S2/S4 + R2-S1/S2/S3/S4/S5).** Live-code facts reshape this increment.
> Verified across both rounds: `_attempt_pre_merge_repair` short-circuits **twice** before
> `run_file_repair` — at `integration_engine.py:845-846` (`if not failed_results: return None`)
> **and** at `851-855` (`repairable = categories & repairable_categories; if not repairable:
> return None`), with `diagnostics` built from syntax/lint only at line 863. The
> `files_to_repair` filter at **866** excludes `.ts`/`.tsx`. The seam **writes in place at
> 879-882**, updates the **element registry at 884-892** (`set_phase_status(…, "repaired")`)
> *before* the `pre_validate` re-check at **895**, and that re-check's syntax result is only
> logged, not wired to any rollback. The increment is redesigned around all of these.

**Edit `contractors/integration_engine.py`:**

0. **Call-site gate — the OUTER short-circuit (R3-S1, critical).** `_attempt_pre_merge_repair`
   is only *invoked* inside `if pre_result.status == CheckpointStatus.FAILED:` at
   **lines 2313-2317**. Invented-but-valid names make `pre_validate` return PASSED, so the
   method is **never called** — every internal fix below (steps 1-5) is unreachable until this
   is addressed. R1/R2 fixed gates *inside* a method that doesn't run for the target class.
   **Fix:** call the content/name-repair path **even when `pre_validate` PASSED**, for TS+Prisma
   features. Preferred shape: split a `_attempt_content_name_repair(gen_paths, unit)` and call it
   unconditionally after the `pre_validate` at line 2302 (the existing FAILED branch keeps
   driving syntax/lint repair); the content path runs on PASS or FAIL. State explicitly that
   fixing 845-855 alone is insufficient while 2313 guards the call.

1. **Unconditional content gate — reconcile BOTH internal short-circuits (R1-S1 + R2-S1).** A
   clean-syntax feature falls past 845-846 but is still killed at **851-855** (`repairable`
   derived only from syntax/lint `failed_results`), and `diagnostics` at 863 is syntax/lint
   only. So it is not enough to fall through the first early-return. Specify: run the content
   scans, translate via `content_bridge`, and (a) **merge** the resulting content diagnostics
   into the `diagnostics` list passed to `run_file_repair` (872-874), **and** (b) make
   `content_contract` count toward the non-empty `repairable` decision (add it to the effective
   repairable set when the content scan fires). Acceptance asserts a `MisnamedFieldDiagnostic`
   is *present in the diagnostics arg*, not merely that repair ran.
2. **Single call vs sequential + fresh sources (R2-S2).** Define the two paths explicitly:
   - *syntax/lint failed* → **one** `run_file_repair` over a **merged** syntax+content
     diagnostics list; the content scan must read the **post-syntax-repair disk content**, not
     the pre-repair `files_to_repair` dict captured at 864-867 (else it diagnoses stale offsets).
   - *syntax/lint clean* → a content-only scan + a single `run_file_repair`.
   State that the content scan always operates on current on-disk bytes.
3. **TS extension inclusion (R1-S2).** Extend the `files_to_repair` filter (866) to include
   `.ts`/`.tsx`. Reconcile the docstring's "Import repair is excluded because generated files
   are not yet under `src_dirs`": name-repair resolves against the *Prisma schema + on-disk lib
   tree*, not `src_dirs`, so that rationale doesn't apply — note this so TS isn't re-excluded.
4. **Pre-image capture (R1-S4).** Before the name-repair steps run, capture a per-file
   pre-image `{path: original_bytes}` for the files the content gate will touch.
5. **Correct ordering + STRICT-SUBSET re-validation (R2-S3 + R2-S5 + R4-S2).** The live
   order (write 879-882 → registry 884-892 → pre_validate 895) is **wrong** for name-repair: it
   marks files `repaired` before validation, so a rolled-back file would lie. Reorder for the
   name-repair path:
   1. `run_file_repair` writes repaired bytes in place;
   2. **re-validate each repaired file with BOTH** the two content scans **and `check_syntax`**
      (R2-S5 — a rename can resolve its content violation while introducing a duplicate-key /
      unbalanced-brace *syntax* error that a content-only re-scan misses);
   3. **roll back only on a NEW defect, not a remaining one (R4-S2, critical).** A file with one
      typo (repaired) and one structural invention (abstained) still shows the abstained
      violation on re-scan — a naive "any content violation remains → roll back" would **discard
      the successful partial repair**. Roll back the pre-image **iff** `post_repair_content_diags
      − pre_repair_content_diags` is non-empty (a *newly introduced* violation) **or**
      `check_syntax` newly fails. A remaining *subset* of the original violations is the expected,
      kept outcome.
   4. update the element registry `set_phase_status(…, "repaired")` **only for files actually
      kept** (or explicitly downgrade rolled-back entries) — never before step 3.
   Rollback is owned by this seam and covers the *full envelope* (file bytes **and** registry),
   not just bytes.
6. **Exit path — abstain MUST NOT become a silent PASS (R4-S1, critical).** When the content
   scan finds a violation but the step **abstains** (structural / ambiguous), `outcome.any_modified`
   is `False`, so the live method falls to `return None` (910); the caller at 2318 then leaves
   `pre_result` **PASSED** and the invented name **merges**, bypassing the LLM-retry loop — the
   exact opposite of the "leave it for retry" intent. Specify: if **any** content violation
   remains un-repaired after the gate (whether the step abstained or a rewrite was rolled back),
   `_attempt_pre_merge_repair` MUST **synthesize and return a `CheckpointResult(status=FAILED)`**
   carrying the residual `content_contract` diagnostics, so the orchestrator routes the feature
   to retry. Only a fully-clean re-scan (zero residual content violations, syntax OK) returns a
   PASSED result. This is the seam where NFR-3 "abstain-safe" meets "abstain-honest": abstain
   neither corrupts the file **nor** silently passes it.

**Placement (OQ-5):** the content gate runs **after** the syntax/lint repair has had its
chance (a broken-syntax file is made valid first), and the content steps are ordered before
`js_syntax_validate` within `run_file_repair` via `_CANONICAL_ORDER` (Inc 2). **Ordering
invariant (R2-S4):** content steps MUST NOT run before syntax repair on the *same* file — the
brace-matcher tolerates syntax errors elsewhere in the file, but a syntax error *inside* the
flagged `db.<model>.<method>({…})` call site defeats it. State this as a precondition so a
future reorder can't silently break the matcher.

**Guard + rollout knob (R3-S3).** The content scans run only when `prisma/schema.prisma`
exists **and** the feature has `.ts`/`.tsx` files in `files_to_repair` — zero cost on
non-TS/Prisma features. (Existence of `.ts`/`.tsx` is necessary but not sufficient — they must
also be *included* per step 3.) Additionally, **wire `RepairConfig.pre_checkpoint_repair`**
(`config.py:68`, default `False`) as the **master enable** for the content gate: the
integration_engine docstring (line 803) already claims this flag controls the pre-merge path,
but neither the call site nor the method reads it today. Wiring it (rather than removing the
claim) gives a real staged-rollout toggle — `False` skips the content gate, `True` runs it when
the other preconditions hold. Update FR-1 docs to match.

**Tests:** `tests/unit/contractors/test_integration_engine_name_repair.py` —
(a0) a feature whose `pre_validate` returns **PASSED** with an invented `aiRefId` — assert the
content/name-repair hook **was invoked** (spy/mock on `_attempt_content_name_repair`), proving
the call-site gate at 2313-2317 no longer blocks it (R3-S1);
(a) the same feature comes out repaired, **with a `MisnamedFieldDiagnostic` present in the
`diagnostics` arg passed to `run_file_repair`** and `content_contract` admitted by the default
`RepairConfig.repairable_categories` (R1-S1 + R2-S1 + R3-S2);
(b) `files_to_repair` includes the feature's `.ts`/`.tsx` files (R1-S2);
(c) a feature with **both** a syntax error and an invented field — the rename lands on the
syntax-repaired content (correct offsets, no stale read, R2-S2);
(d) a rewrite that fails re-validation leaves the file **byte-identical** to its pre-image
**and** its element-registry entry **not** flagged `repaired` (full-envelope rollback, R1-S4 +
R2-S3);
(e) a rename that produces a duplicate-key / unbalanced-brace **syntax** error is rolled back
to byte-identical (re-validation includes `check_syntax`, R2-S5);
(f) a structural FK invention (`outcomeId`) comes out unchanged, the step abstains, and
`_attempt_pre_merge_repair` returns a **FAILED** `CheckpointResult` (not `None`/PASSED) so the
feature routes to LLM-retry instead of merging (abstain ≠ silent PASS, R4-S1);
(g) a file with **both** `aiRefId` (repaired) **and** `outcomeId` (abstained) keeps the
`aiRefId` fix — re-validation does **not** roll back on the remaining abstained violation
(strict-subset, R4-S2) — and still returns FAILED for the residual;
(h) the postmortem scan output is unchanged (NFR-6).

## 7. Increment 6 — run-011 reproduction harness + observability (FR-8, FR-9)

- **Harness** `tests/integration/test_run011_name_repair_repro.py`: fixtures derived from the
  five failed M4 features (PI-001/002/004/007 + PI-010 field portion). Assert: invented fields
  repaired except `Metric.outcomeId` (abstained); invented paths repaired; baseline (repair
  disabled) preserves today's failing behavior.
- **Observability (R1-S6 — measurable contract):** wire `RepairAttribution` (REQ-RPL-403)
  entries `{step, file, from, to, similarity, decision, reason}` + OTel span attributes
  (REQ-RPL-400/401). Emit aggregate counters `repair.name.{attempts, rewrites}` and
  `repair.name.abstains{step, reason}`, plus the derived gauge
  `repair.name.abstain_ratio{step} = abstains/attempts`. Kaizen consumes `abstain_ratio`: above
  a configurable threshold (default `0.5`) over a run → surfaced as an Approach-A prevention
  gap. Test: a 1-rewrite/1-abstain feature emits `attempts=2, rewrites=1, abstains=1,
  abstain_ratio=0.5`.
- **Fixpoint / cross-step idempotence (R1-S7):** an integration test that runs the full
  pre-merge name-repair twice over the same feature → the second pass makes **zero** edits, and
  interleaving with `js_syntax_validate` (the step ordered after the content steps in
  `_CANONICAL_ORDER`) reaches a stable fixpoint with no key re-introduction or shift.

---

## 8. Requirement → increment traceability

| FR | Increment(s) |
|----|--------------|
| FR-1 detection in pre-merge | Inc 5 |
| FR-2 truth re-derivation | Inc 1 |
| FR-3 nearest-match + abstain | Inc 3 |
| FR-4 diagnostics + routing | Inc 2 |
| FR-5 prisma_field_rename | Inc 4 |
| FR-6 import_path_rename | Inc 4 |
| FR-7 non-destructive + re-validate | Inc 4 (guard) + Inc 5 (re-validate) |
| FR-8 run-011 gate | Inc 6 |
| FR-9 observability | Inc 6 |
| FR-10 swappable truth | Inc 1 (protocol + stub) |

## 9. Risks & mitigations

| Risk | Mitigation |
|------|-----------|
| Auto-rename produces valid-but-wrong code | FR-3 single-high-confidence-match + margin; FR-7 re-validation; NFR-3 abstain-default. The structural-invention abstain is the explicit guard. |
| Model name only in `detail` prose, not structured | **Resolved (R1-S3):** add an additive `model: str` field to `PrismaUsageViolation` (Inc 2); the bridge reads it structurally. NFR-6 amended to additive-only. Regex-from-prose rejected. |
| Pre-merge seam writes in place, no staging to roll back | **Resolved (R1-S4):** Inc 5 captures a per-file pre-image before name-repair and restores byte-identical on re-validation failure (verified write-in-place at `integration_engine.py:879-882`). |
| Method never invoked (outer call-site gate) | **Resolved (R3-S1, critical):** Inc 5 step 0 adds a call-site hook at `integration_engine.py:2313-2317` that runs the content path even when `pre_validate` PASSES — without it every internal fix is unreachable for clean-syntax invented names. |
| Content scan never fires (internal syntax/lint short-circuit) | **Resolved (R1-S1 + R2-S1):** Inc 5's content gate reconciles **both** internal short-circuits (845-846 **and** 851-855) and merges content diagnostics into the `run_file_repair` call; verified the second gate + syntax/lint-only `diagnostics` build at line 863. |
| Category dropped by routing/config filter | **Resolved (R3-S2):** `content_contract` added to default `RepairConfig.repairable_categories`; verified the independent filter at `routing.py:290`. |
| `pre_checkpoint_repair` documented but unwired | **Resolved (R3-S3):** wired as the master rollout enable for the content gate; verified dead flag at `config.py:68` / docstring claim at line 803. |
| Abstain silently merges the invented name | **Resolved (R4-S1, critical):** §6 step 6 — an abstain/residual content violation synthesizes a **FAILED** `CheckpointResult` so the feature routes to LLM-retry instead of merging (verified `return None`→PASSED bypass at 910/2318). |
| Re-validation rolls back successful partial repairs | **Resolved (R4-S2, critical):** §6 step 5.3 — strict-subset re-validation; roll back only on a *newly introduced* violation or new syntax failure, not a remaining abstained one. |
| `structural=True` flag has no producer | **Resolved (R4-S3):** dropped the flag; the FK case (`outcomeId`) abstains via `no_candidates`. Residual-risk (near-match FK) logged as a known v1 limitation. |
| Rolled-back file left flagged `repaired` in the element registry | **Resolved (R2-S3):** Inc 5 reorders write → re-validate → rollback → registry; the `repaired` flag is applied only to kept files (verified registry update at 884-892 precedes `pre_validate` at 895). |
| Rename introduces a syntax error a content-only re-scan misses | **Resolved (R2-S5):** Inc 5 re-validation includes `check_syntax` per repaired file, wired to rollback. |
| Content scan reads stale pre-repair sources | **Resolved (R2-S2):** Inc 5 scans post-syntax-repair disk content, not the `files_to_repair` dict captured at 864-867. |
| Regex rewrite corrupts nested/spread/computed object literals | **Tightened (R1-S9):** v1 rewrites top-level call-arg keys only; abstains `unbounded_construct` on nested/spread/computed keys. Idempotence + non-destructive guard per step. |
| Wrong model binding in a multi-model file | **Pinned (R1-S8):** Inc 4/6 fixture asserts per-call-site model binding (OQ-7 now has a test, not just prose). |
| Placement masks errors (path fix hides field error) | OQ-5: content gate runs after syntax/lint repair; both scans re-run in FR-7 re-validation. |
| Scope creep into Zod-symmetry / type-class | Non-Requirements §5 fences v1 to field-name + import-path. |

## 10. Conventions checklist (per CLAUDE.md)

- [ ] `get_logger(__name__)` in every new module (not `logging.getLogger`).
- [ ] New files using string logger names added to `test_logger_acquisition_policy.py` allowlist.
- [ ] No hardcoded model strings (N/A — no LLM here, reinforce in review).
- [ ] `LanguageRegistry.discover()` already called by the integration path (reuse, don't re-add).
- [ ] `content_contract` added to `RepairConfig.repairable_categories` default (R3-S2) **and** the call-site gate at `integration_engine.py:2313` invokes the content path on PASS (R3-S1) — without both, name-repair silently no-ops.
- [ ] `pre_checkpoint_repair` wired as the content-gate master enable (R3-S3), not left as a dead documented flag.
- [ ] Run `pytest tests/unit/repair tests/unit/contractors -q` before commit.
- [ ] `ruff check src/ && black src/ && mypy src/` clean on new files.

---

*Plan v1.0 — six increments, core-first (Inc 1–4 pure/unit), one integration touch (Inc 5),
run-011 gate (Inc 6). Pairs with requirements v0.2.*

*Plan v1.1 — Post-CRP R1. All 9 S-suggestions applied. The three blocking findings (R1-S1
unconditional gate, R1-S2 `.ts`/`.tsx` inclusion, R1-S4 pre-image rollback) were verified
against `integration_engine.py` and redesigned Inc 5 — the highest-value catch of the review,
since the original Inc 5 was dead code with an unbacked rollback. R1-S3 (additive `model`
field), R1-S5 (best_match branching), R1-S6 (abstain_ratio), R1-S7 (fixpoint test), R1-S8
(multi-model fixture), R1-S9 (bounded nesting) all merged. Dispositions in Appendix A;
round history + coverage matrix retained in Appendix C. Pairs with requirements v0.3.*

*Plan v1.2 — Post-CRP R2 (focused on the Inc 5 delta). All 5 S-suggestions applied — all
second-order defects in R1's own Inc 5 redesign: a **second** short-circuit at 851-855 that
R1's fix missed (R2-S1); stale-source read (R2-S2); the registry-update-before-rollback
ordering that would leave a reverted file flagged `repaired` (R2-S3, the headline catch);
the same-file ordering invariant (R2-S4); and content-only re-validation blind to
rename-induced syntax errors (R2-S5). §6 step 5 now specifies the full
write → re-validate(content+syntax) → rollback → registry order. R2 justified itself: the
review of R1's fix found bugs R1 couldn't see. Pairs with requirements v0.4.*

*Plan v1.3 — Post-CRP R3 (a different model, `composer-2.5`, same Inc 5 focus). All 3
S-suggestions applied. R3 traced the call stack **upward** where R1/R2 stayed inside the
method, and found the deepest gate: `_attempt_pre_merge_repair` is only *invoked* on a FAILED
`pre_validate` (2313-2317), so it never runs for clean-syntax invented names — making every
prior internal fix unreachable (R3-S1, critical; new §6 step 0). Also: `content_contract`
missing from the default `repairable_categories` (R3-S2) and the unwired `pre_checkpoint_repair`
knob (R3-S3). The three-round arc is the lesson: each round found a real defect the prior
round's fix introduced or sat on top of (internal gates → ordering → the outer call gate).
Model diversity mattered — R3's catch came from a different lens. Pairs with requirements v0.5.*

*Plan v1.4 — Post-CRP R4 (`claude-opus-4-8-1m`). All 3 S-suggestions applied. R4 shifted from
*entry* to *exit*: even with R3's call-site fix, (1) an **abstain** leaves `any_modified=False`
→ `return None` → the invented name silently **merges**, bypassing LLM-retry — so §6 step 6 now
synthesizes a FAILED result on any residual content violation (R4-S1, critical); (2) naive
re-validation would **roll back a successful partial repair** when an abstained violation
remains — so §6 step 5.3 is now strict-subset (R4-S2, critical); (3) the `structural=True` flag
had no producer — dropped, FK case handled by `no_candidates` (R4-S3). Four rounds, each a layer
deeper: internal gates (R1) → ordering/registry (R2) → outer call gate (R3) → exit/retry
semantics (R4). Pairs with requirements v0.6.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

> Append-only convergent-review state. New reviewers add a round to **Appendix C**, then
> dispositions are recorded in **Appendix A** (applied) or **Appendix B** (rejected).
> Reviewers: scan A/B/C first and do **not** re-propose settled or rejected items.

### Appendix A: Applied Suggestions

**R1 triage (2026-06-01, orchestrator: claude-opus-4-8-1m).** All 9 S-suggestions ACCEPTED.
The three blocking findings (S1, S2, S4) were independently verified against
`integration_engine.py` before acceptance (early-return at 845-846; extension filter at 866;
write-in-place at 879-882).

| ID | Disposition | Where merged |
| -- | ----------- | ------------ |
| R1-S1 | ACCEPTED | §6 step 1 — unconditional content gate that reaches `run_file_repair` even when syntax+lint pass; §0 risk note. |
| R1-S2 | ACCEPTED | §6 step 2 — `.ts`/`.tsx` added to the `files_to_repair` filter; docstring exclusion reconciled. |
| R1-S3 | ACCEPTED | §3 — additive `model: str` field on `PrismaUsageViolation`; bridge reads it structurally. |
| R1-S4 | ACCEPTED | §6 step 3 + step 4 — per-file pre-image capture + byte-identical restore on re-validation failure. |
| R1-S5 | ACCEPTED | §4 — `best_match` 0/1/2-candidate branching + equal-score tie rule fully specified. |
| R1-S6 | ACCEPTED | §7 — `repair.name.{attempts,rewrites,abstains,abstain_ratio}` counters + 0.5 threshold + test. |
| R1-S7 | ACCEPTED | §7 — fixpoint/cross-step idempotence integration test (run twice → zero edits). |
| R1-S8 | ACCEPTED | §5 tests — multi-model `.ts` fixture pins per-call-site model binding (resolves OQ-7 with a test). |
| R1-S9 | ACCEPTED | §5 — v1 rewrites top-level call-arg keys only; abstains `unbounded_construct` on nested/spread/computed keys; §9 risk row tightened. |

**R2 triage (2026-06-01, focused on the Inc 5 delta).** All 5 S-suggestions ACCEPTED; each
verified against `integration_engine.py` before merge. R2 extended R1's accepted items rather
than re-proposing — it found second-order defects *in R1's own fix*.

| ID | Disposition | Where merged |
| -- | ----------- | ------------ |
| R2-S1 | ACCEPTED | §6 step 1 — reconcile **both** short-circuits (851-855 in addition to 845-846) + merge content diagnostics into the `run_file_repair` call; test asserts the diagnostics arg. |
| R2-S2 | ACCEPTED | §6 step 2 — single merged call when syntax/lint fail; content scan reads post-syntax-repair disk content, not the stale `files_to_repair` snapshot. |
| R2-S3 | ACCEPTED | §6 step 5 — reorder write → re-validate → rollback → registry; `repaired` flag applied only to kept files. Highest-value R2 catch. |
| R2-S4 | ACCEPTED | §6 Placement — same-file ordering invariant (content steps never before syntax repair on that file) stated as a precondition. |
| R2-S5 | ACCEPTED | §6 step 5 + tests — re-validation includes `check_syntax`, wired to rollback (catches rename-induced syntax regressions). |

**R3 triage (2026-06-01, focused review by `composer-2.5` — a different model).** All 3
S-suggestions ACCEPTED; each verified against live code. R3 found the **outer call-site gate**
that R1 and R2 both missed — the highest-value catch of the entire review series, because it
makes the prior two rounds' internal fixes unreachable until closed.

| ID | Disposition | Where merged |
| -- | ----------- | ------------ |
| R3-S1 | ACCEPTED | §6 **step 0** — call-site hook at `integration_engine.py:2313-2317` runs the content path even when `pre_validate` PASSES; §0 + §9 + test (a0). Critical. |
| R3-S2 | ACCEPTED | §3 — `content_contract` added to default `RepairConfig.repairable_categories`; §10 checklist; verified independent filter at `routing.py:290`. |
| R3-S3 | ACCEPTED | §6 Guard — `pre_checkpoint_repair` wired as the content-gate master enable; §10 checklist. |

**R4 triage (2026-06-01, `claude-opus-4-8-1m`).** All 3 S-suggestions ACCEPTED; the two
criticals verified against the live `return None`→PASSED→merge path (910 / 2318). R4 moved the
focus from *entry* (R1-R3: does the gate run?) to *exit* (does an un-repaired result route to
retry, and does a partial repair survive?).

| ID | Disposition | Where merged |
| -- | ----------- | ------------ |
| R4-S1 | ACCEPTED | §6 **step 6** — abstain/residual violation synthesizes a FAILED `CheckpointResult` (no silent PASS); §0 + §9 + test (f). Critical. |
| R4-S2 | ACCEPTED | §6 step 5.3 — strict-subset re-validation (roll back only on a newly introduced violation/syntax failure); test (g). Critical. |
| R4-S3 | ACCEPTED | §4 + §5 — dropped the unwireable `structural` flag; FK case abstains via `no_candidates`; residual risk logged. |

### Appendix B: Rejected Suggestions (with Rationale)

- _No S-suggestions rejected._ (The requirements-side sub-alternative for R1-F2 — regex-parse
  model from `detail` prose — was rejected; see the requirements doc Appendix B.)

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-01

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-01 21:30:00 UTC
- **Scope**: Plan review (S-suggestions) — architecture/integration correctness of the six increments, grounded against the live seams cited in §1. Dual-document mode; requirements reviewed separately (F-suggestions). Includes an adversarial stress-test subsection.

**Executive summary (top risks / opportunities / blocking gaps):**

- **Blocking (Inc 5):** §6 appends content diagnostics to "the `diagnostics` list passed to `run_file_repair`", but `_attempt_pre_merge_repair` returns early (`integration_engine.py:838-851`) unless a *syntax/lint* check already failed. Clean-syntax invented names never reach `run_file_repair`. Inc 5 needs an unconditional scan-and-route, not a piggyback on an existing failure.
- **Blocking (Inc 5):** the live `files_to_repair` filter is `(".py",".java",".go",".cs",".js")` — **no `.ts`/`.tsx`** (`integration_engine.py:859`). Every target file is excluded today. Inc 5 must add the TS extensions (and reconcile the comment "Import repair is excluded because generated files are not yet under src_dirs").
- **Blocking (Inc 2):** the content_bridge plans to recover the model name "from the scan's `accessor` map", but `accessor` is a local variable in `scan_prisma_usage`, never returned; `PrismaUsageViolation` carries no `model` field (`prisma_usage.py:41-49`). The bridge has no structured source.
- **High (Inc 5/FR-7):** the seam writes repaired files in place ("no staging needed", `integration_engine.py:877`). There is no staging to roll back; the re-validation/rollback in §6 needs an explicit pre-image snapshot.
- **Medium (Inc 3):** `get_close_matches(n=2)` returns *best-first*; the `margin` comparison and `ambiguous_tie` detection must be defined against the case where fewer than two candidates clear the cutoff.
- **Opportunity (Inc 1):** `_KNOWN_INVENTIONS` and abstain telemetry are 80%-built feeds for the Kaizen/Approach-A loop — cheap to persist as a learned-negatives artifact.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | critical | Inc 5: replace "append to the `diagnostics` list passed to `run_file_repair`" with an **unconditional** scan+route that runs even when `check_syntax`/`check_lint` pass. The current `_attempt_pre_merge_repair` short-circuits at `if not failed_results: return None` and `if not repairable: return None` before `run_file_repair`. | Verified `integration_engine.py:838-851`. Invented field/import names are syntactically valid and lint clean (esp. with `ignore_codes=["F401"]`), so the FR-1 detection path as planned is dead code for the target failure class. | §6 first bullet ("after assembly, before finalize: run `scan_prisma_usage`…") | Integration test: a feature that passes syntax+lint but contains `aiRefId` still triggers a name-repair attempt. |
| R1-S2 | Interfaces | critical | Inc 5: add `.ts`/`.tsx` to the `files_to_repair` extension filter and state it explicitly in the plan; today the filter is `(".py",".java",".go",".cs",".js")`. Also reconcile the existing comment that pre-merge "Import repair is excluded because generated files are not yet under `src_dirs`" — name-repair must not be silently excluded by that rule. | Verified `integration_engine.py:859` and the method docstring. Without the extension change, no TS file enters `run_file_repair` and the steps never see content. | §6 "Guard" bullet (which currently only checks for `.ts`/`.tsx` existence, not inclusion in the repair set) | Assert `files_to_repair` includes the `.ts`/`.tsx` feature files in the pre-merge invocation. |
| R1-S3 | Data | high | Inc 2: the content_bridge cannot read the model from `scan_prisma_usage`'s `accessor` map (it is a local, not on the violation). Specify the concrete source: either pin the `detail` prose format and parse it, or add a minimal additive `model` field to `PrismaUsageViolation`. The plan's §9 risk row hints at both but commits to neither. | Verified `prisma_usage.py:41-49,134,185`: `accessor` and `model_name` are locals; the returned dataclass has only `field`/`detail`. The bridge's stated recovery path does not exist. | §3 content_bridge paragraph ("recover it from the `accessor` mapping") + §9 risk row 2 | Bridge unit test produces `MisnamedFieldDiagnostic(model="Capability")` from a real `scan_prisma_usage` output fixture. |
| R1-S4 | Risks | high | Inc 5 / FR-7: define the rollback artifact. Since the pre-merge seam writes in place ("no staging needed"), add an explicit per-file pre-image capture before the name-repair steps run, and restore from it on re-validation failure. State this in the plan rather than assuming orchestrator staging. | Verified `integration_engine.py:877`. §6 says "the per-file staging for that file is discarded (the orchestrator already stages)" — not true for this method; the rollback has no backing mechanism. | §6 "Re-validation (FR-7 second half)" bullet | Test: a rewrite that fails the re-scan leaves the file byte-identical to its captured pre-image. |
| R1-S5 | Validation | medium | Inc 3: specify `best_match` semantics for the degenerate-candidate cases. With `get_close_matches(n=2, cutoff)`, the result may contain 0, 1, or 2 names. Define: 0 → `no_candidates`; 1 → rewrite (no runner-up; margin trivially satisfied) **or** an explicit "require ≥ cutoff" rule; 2 → apply margin for `ambiguous_tie`. The plan lists the abstain reasons but not the branching that produces them. | The decision core is the highest-risk pure unit; ambiguity here directly drives FR-3/OQ-4 tuning and the `label` abstain case. | §4 `MatchDecision` / abstain-reasons bullets | Parametrized `test_name_resolution.py` covering 0/1/2-candidate branches and an exact-tie. |
| R1-S6 | Ops | medium | Inc 6: define the abstain metric's denominator and a surfacing threshold so FR-9's "high abstain rate surfaces a prevention gap" is actionable. Emit `attempts`, `rewrites`, `abstains{reason}` and a derived ratio with labels `{step, reason}`; document the Kaizen consumption point. | §7 wires attribution entries and span attributes but no aggregate rate; without a denominator the "prevention gap" signal can't be alerted or trended. | §7 "Observability" bullet | Assert a 1-rewrite/1-abstain feature emits the expected counters and a 0.5 ratio. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S7 | Risks | high | Idempotence under re-entry: the pre-merge path may run name-repair, then `pre_validate` re-runs and (on other categories) repair could re-enter. Prove the prisma/import steps are **idempotent and order-independent** with the existing syntax/import-completion steps in the *same* `run_file_repair` invocation, not just standalone. The plan asserts idempotence only at the unit level (Inc 4 tests). | `_CANONICAL_ORDER` places content steps before `js_syntax_validate`, but a syntax-completion step that rewrites the same call site after a field rename could re-introduce or shift the key; cross-step interaction is untested. | §5 Inc 4 tests + §6 placement (OQ-5) | Integration test: run name-repair twice over the repaired output → zero further edits; interleave with `js_syntax_validate` → stable fixpoint. |
| R1-S8 | Data | medium | Multi-model file correctness (OQ-7) is a *plan-level* test gap, not just an open question. Add an explicit Inc 4/Inc 6 fixture: one `.ts` file with `db.capability.create({ aiRefId })` and `db.metric.update({ name })` where `name` is valid on `Metric` but the invented `aiRefId` must map only to `Capability`'s field set — proving per-call-site model binding survives the bridge → step path. | OQ-7 is flagged as unresolved but no test pins it; a wrong model binding silently rewrites to the wrong field set (a valid-but-wrong outcome — the exact failure NFR-3 forbids). | §3 (bridge) + §5 tests + OQ-7 | Fixture-based test asserting each call site rewrites against its own model's field set. |
| R1-S9 | Interfaces | medium | Brace-matched regex on `db.<model>.<method>({...})` will mis-handle nested object literals (e.g. `data: { nested: { aiRefId } }`, `where` with relation filters, spread `...obj`, and template-literal keys). Specify which nesting depths are in-scope for v1 and abstain (don't blind-rewrite) on constructs the matcher can't bound. | §5/§9 reuse the Go/C# splicer brace technique, but TS object literals nest deeper than the flat call-arg the example implies; an over-eager key rewrite inside a nested unrelated object is a corruption risk. | §5 `prisma_field_rename` paragraph + §9 risk row 3 | Test: nested/spread/computed-key fixtures either rewrite only the correct top-level flagged key or abstain — never edit a nested unrelated key. |

**Endorsements / Disagreements:** none (first review round; Appendix A/B empty).

#### Review Round R2 — claude-opus-4-8-1m — 2026-06-01

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-01 21:45:00 UTC
- **Scope**: FOCUSED R2 — the un-reviewed Increment 5 redesign only (PLAN §6 + the FR-1/FR-7 changes it implements). Read the live `integration_engine.py:786-910 _attempt_pre_merge_repair` and `checkpoint.py:549 pre_validate` before writing. R1 architecture/FR-set/Inc 1–4/6 are out of scope. Every suggestion anchored to real line numbers.

**Sponsor asks — direct answers (orchestrator triages; no ACCEPT/REJECT here):**

- **Ask 1 — Unconditional content gate / double-run / stale sources.**
  - **Summary answer:** Partial — the fall-through is expressible, but §6 step 1 under-specifies two real hazards: a *second* short-circuit and the diagnostics-provenance/stale-read interaction.
  - **Rationale:** Inc 5 only names the `if not failed_results: return None` early-return (line 845-846). The live method has a **second** gate at lines 851-855 (`repairable = categories & repairable_categories; if not repairable: return None`) computed purely from syntax/lint `failed_results`, and `diagnostics` is built at line 863 as `parse_checkpoint_diagnostics(failed_results)` — syntax/lint only. A clean syntax/lint result has empty `failed_results`, so even after falling past 845-846 the content diagnostics must be (a) injected into the `categories`/`repairable` decision and (b) merged into the `diagnostics` list passed to `run_file_repair` at line 872-874, or the content gate reaches `run_file_repair` with an empty diagnostics set and no-ops. On double-run: when syntax/lint *did* fail, the existing block (845-873) already runs `run_file_repair` and writes files at 881-882; the content gate must run *after* that write and re-read post-repair disk content (not the pre-repair `files_to_repair` dict captured at 864-867), or it scans stale sources. This is genuinely expressible but is two gates feeding one merged `diagnostics`/one `run_file_repair`, not "fall through to a second invocation."
  - **Assumptions / conditions:** that `run_file_repair` routes by per-diagnostic category (it does, via `_ROUTING_TABLE`), so a merged syntax+content diagnostics list is safe in one call.
  - **Suggested improvements:** see R2-S1 (second short-circuit + diagnostics merge) and R2-S2 (single-invocation vs sequential, stale-read seam).

- **Ask 2 — Pre-image rollback vs element-registry update (race / lying registry).**
  - **Summary answer:** No — as currently ordered the registry **lies** after a rollback.
  - **Rationale:** Lines 884-892 call `set_phase_status(entry, "integrate", "repaired", {"repair_stage": "pre_merge"})` for every file in `outcome.repaired_files`, and this happens *before* the `pre_validate` re-check at line 895 and before any §6-step-3 rollback. A pre-image restore (file bytes) does not touch the registry, so a rolled-back file stays flagged `repaired`. Correct ordering: **write → re-validate (content + syntax) → rollback reverted files → update registry only for files actually kept** (or downgrade the status for rolled-back files). The re-validation at line 895 re-reads disk (`pre_validate → check_syntax(gen_paths)`, verified `checkpoint.py:549-566`), *not* `outcome.repaired_files`; so rollback must write the pre-image to disk *before* line 895 runs, or 895 validates the un-rolled-back content.
  - **Assumptions / conditions:** the element registry is the source of truth Kaizen/postmortem reads for `repair_stage`; a false `repaired` flag corrupts the abstain/repair attribution FR-9 depends on.
  - **Suggested improvements:** see R2-S3 (reorder registry update after rollback) — high severity.

- **Ask 3 — Placement vs `_CANONICAL_ORDER` / circular syntax-vs-name dependency.**
  - **Summary answer:** Mostly sound — "after syntax/lint repair, before merge" is the right seam, with one caveat the plan should state.
  - **Rationale:** §6 placement + OQ-5 correctly run the content gate after the syntax/lint repair has made a broken file valid, and order content steps before `js_syntax_validate` within `run_file_repair`. The regex field/import rename does not require a *fully* parseable file (it brace-matches a `db.<model>.<method>({...})` call site locally), so a syntax error elsewhere does not block the scan — no hard circular dependency. The caveat: a syntax error *inside the flagged call site itself* would defeat the brace-matcher, which is why running after syntax repair is correct, and the plan should assert the content steps must not run before syntax repair on the *same* file.
  - **Assumptions / conditions:** `scan_prisma_usage`/`scan_unresolvable_imports` tolerate non-parseable regions (regex-based, per §1).
  - **Suggested improvements:** see R2-S4 (assert ordering invariant in §6 placement).

- **Ask 4 — Re-validation scope misses a syntax regression.**
  - **Summary answer:** Yes — a content-only re-scan can miss a rename-induced syntax error.
  - **Rationale:** §6 step 4 re-validation re-runs "the two content scans." A key rewrite that resolves its content violation but breaks syntax (e.g. an unbalanced brace from a botched key replacement, or a collision producing a duplicate key) is **not** a `content_contract` violation, so the content-only re-scan keeps the file and the rollback never fires. The existing `pre_validate` at line 895 *does* run syntax, but its result is only logged/returned — it is not wired to drive the §6-step-3 rollback decision. Rollback must also re-run `check_syntax` per file and restore on a *new* syntax failure, not just a new content violation.
  - **Assumptions / conditions:** rollback granularity is per-file (matches the pre-image dict).
  - **Suggested improvements:** see R2-S5 (re-validation must include `check_syntax`, wired to rollback).

- **Ask 5 — Requirements/plan rollback coherence (FR-7 ↔ §6).**
  - **Summary answer:** Mostly consistent on bytes, but FR-7's "byte-identical" acceptance is incomplete because of the registry side effect.
  - **Rationale:** FR-7 (byte-identical file restore) and §6 (per-file pre-image) agree on file content. But the pre-image captures *bytes only* (§6 step 3: `{path: original_bytes}`); the registry mutation at 884-892 is out-of-scope of the restore. So "byte-identical restore" can be true for the file while the registry diverges — the acceptance test as written (FR-7 *Acceptance*) would pass yet leave a lying registry. The two docs are coherent on the narrow claim but jointly under-specify the full rollback envelope.
  - **Assumptions / conditions:** see Ask 2.
  - **Suggested improvements:** see R2-F1 (FR-7: extend rollback envelope to registry/side-effects) and R2-S3.

**Executive summary (top risks for the Inc 5 delta):**

- **High (Inc 5):** registry update at lines 884-892 runs before re-validation/rollback → a rolled-back file is left flagged `repaired` (Ask 2). Corrupts FR-9 attribution.
- **High (Inc 5):** §6 step 1 addresses only the 845-846 early-return; the **second** short-circuit (851-855, `repairable`) and the syntax/lint-only `diagnostics` build (863) are not reconciled — content gate can reach `run_file_repair` with no content diagnostics.
- **Medium (Inc 5):** content-only re-validation (§6 step 4) misses a rename-induced *syntax* regression; the disk-based `pre_validate` (895) that would catch it is not wired to rollback (Ask 4).
- **Low/Medium (Inc 5):** stale-source read risk — content gate must scan post-syntax-repair disk content, not the pre-repair `files_to_repair` snapshot (Ask 1).
- **Endorsement:** the §6 placement-vs-`_CANONICAL_ORDER` design and the pre-image-rollback *concept* are sound; the gaps are in ordering and re-validation scope, not the approach.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Architecture | high | §6 step 1 must reconcile **both** pre-`run_file_repair` short-circuits, not just the 845-846 one. After falling through `if not failed_results` (845-846), the live method still gates at lines 851-855 (`repairable = categories & repairable_categories; if not repairable: return None`) using categories derived only from syntax/lint `failed_results`, and builds `diagnostics = parse_checkpoint_diagnostics(failed_results)` at line 863 (syntax/lint only). Specify that content diagnostics are (a) merged into the `diagnostics` list passed to `run_file_repair` (line 872-874) and (b) cause `repairable` to be non-empty (e.g. add `content_contract` to the effective repairable set when the content scan fires). | Without this, a clean-syntax feature falls past 845-846 but is still killed by 851-855, or reaches `run_file_repair` with an empty content-diagnostics set → silent no-op. The "unconditional gate" is only half-wired. | §6 step 1 ("Refactor the early `return None`…") | Test: a feature passing syntax+lint with an invented field reaches `run_file_repair` **with a `MisnamedFieldDiagnostic` present in the passed `diagnostics`** (assert the diagnostics arg, not just that repair was attempted). |
| R2-S2 | Architecture | medium | §6 step 1 must state whether the content gate is a **separate `run_file_repair` invocation** or a **merged single call** with the syntax/lint diagnostics, and which sources it scans. When syntax/lint failed, the existing block writes repaired files in place at lines 881-882; the content scan must then read the **post-repair disk content**, not the pre-repair `files_to_repair` dict captured at lines 864-867. Recommend: one `run_file_repair` call over a merged diagnostics list when syntax/lint fail; a second scan+call only on the clean-syntax path. | A stale in-memory scan would diagnose against pre-repair text and rewrite the wrong offsets. The plan's "reusing the in-scope `project_root`" is ambiguous about source freshness. | §6 step 1 + the "Placement (OQ-5)" paragraph | Test: a feature with **both** a syntax error and an invented field — assert the content rename lands on the syntax-repaired content (offsets correct after the syntax fix). |
| R2-S3 | Risks | high | §6 steps 3-4 must move the **element-registry update (lines 884-892) to AFTER re-validation and rollback**, and apply it only to files actually kept. Today `set_phase_status(…, "repaired", {"repair_stage": "pre_merge"})` runs at 884-892 before `pre_validate` (895) and before any §6 rollback, so a rolled-back file stays flagged `repaired`. Specify ordering: write → re-validate (content+syntax) → restore pre-image for failing files → update registry for kept files only (or explicitly downgrade rolled-back entries). | A lying registry corrupts FR-9 `RepairAttribution`/abstain accounting and any Kaizen consumer reading `repair_stage`. This is the highest-value Inc 5 catch this round. | §6 step 3 + step 4; add an explicit ordering list | Test: a rewrite that fails re-validation leaves the file byte-identical **and** its element-registry entry NOT flagged `repaired` (assert both). |
| R2-S4 | Architecture | low | §6 "Placement (OQ-5)" should assert the invariant that content steps never run before syntax repair on the **same** file. The brace-matcher tolerates syntax errors *elsewhere* in the file (no hard circular dependency), but a syntax error *inside* the flagged `db.<model>.<method>({…})` call site defeats it — running after syntax repair is correct and should be stated as a precondition, not left implicit. | Makes the OQ-5 resolution a checkable invariant rather than prose; prevents a future reorder from breaking the brace-matcher. | §6 "Placement (OQ-5)" paragraph | Test: a fixture with a syntax error inside the flagged call site is syntax-repaired first, then renamed (assert order via step trace). |
| R2-S5 | Validation | medium | §6 step 4 re-validation must re-run **`check_syntax` per repaired file**, not only the two content scans, and wire a new syntax failure to the §6-step-3 rollback. A key rewrite can resolve its content violation while introducing a syntax error (unbalanced brace, duplicate key) that is **not** a `content_contract` violation — the content-only re-scan keeps the broken file. The existing `pre_validate` at line 895 runs syntax but its result is only returned, not used to drive rollback. | A content-only gate is blind to rename-induced syntax regressions — exactly the valid-but-broken outcome FR-7 exists to prevent. | §6 step 4 ("re-run the two scans") | Test: a fixture whose rename produces a duplicate-key / unbalanced-brace syntax error is rolled back to byte-identical pre-image (asserts syntax is in the rollback gate). |

**Endorsements (prior untriaged items — none remain untriaged):** R1-S1/S2/S4 (the three Inc 5 blockers) are all in Appendix A; this round extends them rather than re-proposing. R2-S1 extends R1-S1 (second short-circuit it missed); R2-S3 extends R1-S4 (rollback ordering vs registry it did not consider).

**Disagreements:** none.

#### Review Round R3 — composer-2.5 — 2026-06-01 20:15 UTC

- **Reviewer**: composer-2.5
- **Date**: 2026-06-01 20:15:00 UTC
- **Scope**: Fresh R3 pass on the Inc 5 delta only, per `.crp-r2-focus-inc5.md`. Read live `integration_engine.py:786-910` and the call site at `2313-2317` before writing. R1 settled architecture and R2 addressed internal short-circuits + rollback ordering; this round hunts the interaction gaps R2 merged into §6 but did not name.

**Sponsor asks — direct answers:**

- **Ask 1 — Unconditional content gate / double-run / stale sources.**
  - **Summary answer:** No — §6 step 1 is necessary but **not sufficient**; a third outer gate prevents the method from being called at all when syntax+lint pass.
  - **Rationale:** R2-S1/S2 correctly reconcile the internal early-returns (845-846, 851-855) and stale-read risk. But the caller at `integration_engine.py:2313-2317` wraps `_attempt_pre_merge_repair` in `if pre_result.status == CheckpointStatus.FAILED`. Invented field/import names are syntactically valid → `pre_validate` (549-610) returns PASSED → the entire pre-merge repair method is **never invoked**, regardless of internal refactors. Fixing 845-855 alone still leaves FR-1 dead for the headline failure class.
  - **Assumptions / conditions:** `gen_paths` includes `.ts`/`.tsx` via `language_profile.source_extensions` (2292-2300); the outer gate is independent of the 866 filter.
  - **Suggested improvements:** R3-S1 (call-site unconditional content hook); endorse R2-S1/S2.

- **Ask 2 — Pre-image rollback vs registry.**
  - **Summary answer:** Endorse R2-S3/R2-F1 — still the highest-value ordering fix; no new position.
  - **Rationale:** Verified 884-892 runs before 895; rollback envelope must include registry (already in §6 after R2 merge).
  - **Suggested improvements:** Endorse R2-S3, R2-F1.

- **Ask 3 — Placement vs `_CANONICAL_ORDER`.**
  - **Summary answer:** Endorse R2-S4 — sound; no new position.

- **Ask 4 — Re-validation scope.**
  - **Summary answer:** Endorse R2-S5/R2-F2 — content-only re-scan is insufficient; `check_syntax` must gate rollback.

- **Ask 5 — Requirements/plan coherence.**
  - **Summary answer:** Partial — FR-7/§6 agree on bytes after R2 merge, but neither names the **RepairConfig** gate that can silently drop `content_contract` diagnostics before `run_file_repair` routes them.
  - **Suggested improvements:** R3-S2, R3-F2.

**Executive summary:**

- **Critical:** Outer call-site gate at 2313-2317 — `_attempt_pre_merge_repair` runs only when `pre_validate` FAILED. Clean-syntax invented names never enter the method; §6 internal fixes alone cannot satisfy FR-1.
- **High:** `RepairConfig.repairable_categories` default (`repair/config.py:67`) omits `content_contract`; `route_failures` drops the category at `routing.py:290` even if diagnostics reach `run_file_repair`.
- **Medium:** Docstring claims `pre_checkpoint_repair` controls this path (803) but neither the call site nor the method reads that flag — config/docs lie about the enablement surface.
- **Endorsement:** R2's Inc 5 redesign (dual short-circuit merge, stale-disk read, registry-after-rollback, syntax in re-validation, ordering invariant) is sound once R3-S1/S2 close the remaining gates.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | Architecture | critical | §6 must add a **call-site change** at `integration_engine.py:2313-2317`: invoke the content/name-repair path **even when `pre_validate` returns PASSED**, not only inside `if pre_result.status == CheckpointStatus.FAILED`. Options: (a) always call a refactored `_attempt_pre_merge_repair` that runs syntax/lint repair on fail then unconditionally runs the content gate; or (b) split `_attempt_content_name_repair` and call it after every successful `pre_validate` for TS+Prisma features. State explicitly that fixing 845-846/851-855 is insufficient while 2313 guards the call. | Verified: 2313-2317 only enters pre-merge repair on FAILED pre_validate. The target failure class (invented `aiRefId`, `@/lib/prisma`) passes syntax+lint → PASSED → method never called. This is the third short-circuit R2 did not name. | §6 new step 0 ("Call-site gate") before step 1; cross-ref §1 seam table | Test (a) in §6: feature passing syntax+lint with invented field — assert `_attempt_pre_merge_repair` (or the split content hook) **was invoked** (mock/spy), not only that internal diagnostics would be non-empty if called. |
| R3-S2 | Interfaces | high | §6 step 1 must also add `content_contract` to **`RepairConfig.repairable_categories`** (default in `repair/config.py:67` and prime-contractor config examples). `route_failures` (`routing.py:290`) skips any category not in that set — merging content diagnostics into the list passed to `run_file_repair` (R2-S1) still no-ops if the config omits the category. | R2-S1 fixes the integration_engine `repairable` set at 851-855 but not the orchestrator routing gate. Two independent category filters must both admit `content_contract`. | §6 step 1 + Inc 2 routing note; §10 conventions checklist | Test: with default `RepairConfig`, content diagnostics route to `prisma_field_rename`/`import_path_rename`; with `repairable_categories` excluding `content_contract`, repair is skipped and logged. |
| R3-S3 | Ops | medium | Reconcile the **`pre_checkpoint_repair` config knob**: docstring at 803 says it "controls this pre-merge path" but neither 2313 nor `_attempt_pre_merge_repair` reads `RepairConfig.pre_checkpoint_repair` (default `False`, `repair/config.py:68`). Either wire the flag as the master enable for the content gate (recommended for staged rollout) or remove the false claim from the docstring and FR-1 acceptance docs. | Operators reading config reference will believe toggling `pre_checkpoint_repair` enables/disables name repair; it currently does nothing. Accidental complexity from a dead config surface. | §6 rollout/guard + §10 checklist | Config test: `pre_checkpoint_repair=False` skips content gate; `True` runs it when other preconditions met. |

**Endorsements** (prior untriaged R2 items this reviewer agrees with):

- R2-S1: Second internal short-circuit (851-855) + diagnostics merge — necessary, not sufficient without R3-S1.
- R2-S2: Post-syntax-repair disk read for content scan — correct stale-source seam.
- R2-S3: Registry update after rollback — prevents lying `repaired` flags.
- R2-S4: Same-file ordering invariant — checkable precondition for OQ-5.
- R2-S5: Re-validation must include `check_syntax` — closes rename-induced syntax regressions.

**Disagreements:** none.

#### Review Round R4 — claude-opus-4-8-1m — 2026-06-01 22:00 UTC

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-01 22:00:00 UTC
- **Scope**: Fresh R4 pass on the Inc 5 delta and FR-1/FR-7, focusing on the interaction between abstains, re-validation, and integration outcome. Prior rounds fixed the invocation gates; this round fixes the exit paths.

**Executive summary (top risks):**

- **Critical (Abstain = False PASS):** Even with the call-site fixed (R3-S1), an abstain results in `outcome.any_modified == False`. The method returns `None`, leaving the `pre_result` as PASSED, which causes the integration engine to merge the file, bypassing the LLM-retry loop. Un-repaired content violations must synthesize a FAILED result.
- **Critical (Rollback destroys partial repairs):** Re-validation (§6 step 4) will roll back a file if *any* content violation remains. In a file with one typo (repaired) and one structural invention (abstained), re-validation will see the abstained violation and roll back the file, undoing the successful repair.
- **High (Unwireable Structural Flag):** FR-3 specifies a `structural=True` flag, but `MisnamedFieldDiagnostic` has no such field to pass this signal from detection to repair.
- **Endorsement:** R3-S1 and R3-S2 are essential prerequisites for this round's fixes.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-S1 | Architecture | critical | Address the "Abstain Bypass": If `run_file_repair` abstains on a content diagnostic, `outcome.any_modified` is False, so `_attempt_pre_merge_repair` returns `None`. If the original `pre_result` was PASSED, returning `None` leaves it PASSED, and the broken file is merged, skipping the LLM retry loop. `_attempt_pre_merge_repair` MUST synthesize and return a `CheckpointResult(status=FAILED)` containing the un-repaired content diagnostics. | The core goal is to send structural/abstained inventions back to the LLM retry loop. Bypassing the FAILED return merges the hallucination silently. | §6 step 1 + new step 5 (Exit path) | Test: Feature with `outcomeId` (structural abstain) passes syntax/lint, triggers content scan, abstains, and `_attempt_pre_merge_repair` returns FAILED. |
| R4-S2 | Validation | critical | Fix "Strict-Subset Re-validation": The re-validation content scan (§6 step 4) will still detect *abstained* violations in the file. If re-validation rolls back on *any* content diagnostic, it will discard successful partial repairs. Re-validation must diff the diagnostics and only roll back if `new_diagnostics - original_diagnostics` is non-empty (or if syntax fails). | A file with both `aiRefId` (repaired) and `outcomeId` (abstained) will fail a naive re-validation because `outcomeId` remains, rolling back the `aiRefId` fix. | §6 step 4 | Test: A multi-violation file where one is repaired and one is abstained passes re-validation without rollback. |
| R4-S3 | Data | high | Remove the `structural=True` parameter expectation from Inc 3 `best_match` call site, or add an `is_fk_heuristic` to `MisnamedFieldDiagnostic`. The step currently has no way to pass `structural=True` because the diagnostic carries no such flag. | The step cannot know a field is a presumed FK unless the detection layer tells it or it uses a generic threshold (0 matches). | Inc 3 and Inc 4 (`prisma_field_rename`) | Test: Remove `structural` flag from `MatchDecision` and assert `no_candidates` alone handles the `outcomeId` FK case. |

**Endorsements** (prior untriaged R3 items this reviewer agrees with):

- R3-S1: The outer call-site gate is the true blocker for clean-syntax features.
- R3-S2: `content_contract` must be in `repairable_categories`.

#### Review Round R5 — gpt-5.5 — 2026-06-01 21:35 UTC

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-01 21:35:00 UTC
- **Scope**: Fresh R5 pass on the Inc 5 delta only, after reading the current R1-R4 state and the live `integration_engine.py:786-910`, call site `2290-2351`, and `checkpoint.py:549-610`. R1-R3 accepted items and R4 abstain/strict-subset findings are not re-proposed; this round focuses on making R4 implementable and observable.

**Sponsor asks — direct answers:**

- **Ask 1 — Unconditional content gate / double-run / stale sources.**
  - **Summary answer:** R3 closes the entry gate; R5 adds that the final gate emission and metadata must reflect the post-content-repair state, not the pre-repair `GateEmitter.emit` at `integration_engine.py:2303-2308`.
  - **Rationale:** The call site emits a GateResult immediately after `pre_validate` (2302-2308), before any repaired content is written or abstain failure is synthesized. If Inc 5 runs on the PASSED path, observability can still show a clean pre-merge gate while the content gate later repairs, abstains, or fails. That creates an operator-facing false PASS even if the returned `CheckpointResult` is correct.
  - **Suggested improvements:** R5-S3.

- **Ask 2 — Pre-image rollback vs registry.**
  - **Summary answer:** Endorse R2-S3 and R4-S2; add that rollback/re-validation comparisons need stable per-occurrence diagnostic identity or they cannot safely distinguish repaired, abstained, and newly introduced violations.
  - **Suggested improvements:** R5-S1.

- **Ask 3 — Placement vs `_CANONICAL_ORDER`.**
  - **Summary answer:** Endorse R2-S4; no new placement change.

- **Ask 4 — Re-validation scope.**
  - **Summary answer:** R4's strict-subset rule is right, but currently under-specified: define a diagnostic multiset identity before implementing it.
  - **Suggested improvements:** R5-S1.

- **Ask 5 — Requirements/plan coherence.**
  - **Summary answer:** Inc 5 now contradicts NFR-2's original "one scan per feature" bound because R2/R4 require initial scan plus re-validation scans; update the bounded-cost contract instead of leaving stale prose.
  - **Suggested improvements:** R5-S2.

**Executive summary:**

- **High:** R4-S2's strict-subset re-validation needs a stable diagnostic identity/multiset. Without it, repeated `aiRefId` occurrences can collapse into one logical key, or shifted line hints can make an unchanged abstain look "new."
- **High:** NFR-2 still says one scan per feature, but Inc 5 now requires an initial scan, post-repair content re-scan, and syntax re-check. Bound the real algorithm, not the obsolete one.
- **Medium:** `GateEmitter.emit` currently runs before repair at 2303-2308 and `repair_summaries` is appended only inside the FAILED branch at 2318-2329 with `any_modified=True`. Inc 5 needs final gate and metadata semantics for success, abstain, rollback, and no-op.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-S1 | Data | high | Define a stable **content diagnostic identity multiset** before implementing R4-S2 strict-subset re-validation. Suggested key: `{check_id, rel_path, category, model, field/specifier, occurrence_ordinal_or_range}` with multiset counts, plus a documented fallback when ranges shift after rewrite. Do not diff only `{model, field}` or `{specifier}`. | R4-S2 requires `new_diagnostics - original_diagnostics`, but neither §6 nor FR-4 defines equality. A file can contain two `aiRefId` violations; repairing one and leaving one should not collapse to "same diagnostic." Conversely, an abstained `outcomeId` with shifted line hints should not look new and trigger rollback. | §6 step 4 and Inc 2 `content_bridge` diagnostics | Tests: (a) two identical invented fields in one file, one repaired and one remains → multiset count decreases but does not vanish; (b) abstained violation with shifted line number remains recognized as the same violation; (c) genuinely new violation after rewrite triggers rollback. |
| R5-S2 | Validation | high | Update the bounded-cost contract: replace "one scan per feature" with the actual Inc 5 budget after R2/R4: initial content scan once per eligible feature, post-repair content re-scan once over affected files, `check_syntax` once over affected files, and no retry loop inside the content gate. | R2-S5 and R4-S2 require additional re-validation scans. Leaving the old "one scan per feature" language contradicts the accepted design and makes performance tests assert the wrong behavior. | §6 Guard / Tests and §9 risk row; mirror in NFR-2 | Test spies assert scanner call counts for clean no-op, successful repair, abstain, and rollback cases; pathological flagged-token ceiling still applies. |
| R5-S3 | Ops | medium | Add final gate/metadata semantics for the content path: after content repair/abstain/rollback, emit or update a final pre-merge GateResult and append `repair_summaries` for PASSED-path content attempts. The current call site emits the gate before repair (`2303-2308`) and appends metadata only when `repaired_result is not None` inside the FAILED pre-validate branch (`2318-2329`), with `any_modified=True` hard-coded. | Otherwise operators can see "Pre-merge validation passed" while content repair later modified files or synthesized a failure, and Kaizen loses PASSED-path name-repair attempts. | §6 new step 6 (Reporting) + Inc 6 observability handoff | Test: successful content repair on an initially PASSED file records `phase=pre_merge`, `attempted=True`, accurate `any_modified`, `abstained`, `rolled_back`, and final gate status; abstain case emits FAILED gate. |

**Endorsements** (prior untriaged R4 items this reviewer agrees with):

- R4-S1: Abstains must force a FAILED checkpoint or the LLM retry path is bypassed.
- R4-S2: Strict-subset re-validation is the right shape, pending R5-S1 diagnostic identity.
- R4-S3: The structural flag must either be wired through diagnostics or removed.

---

## Requirements Coverage Matrix — R5

Focused on the Inc 5 delta only. Analysis only (no triage).

| Requirement | Plan Step(s) | Coverage | Gaps (R5) |
| ---- | ---- | ---- | ---- |
| FR-1 Detection (unconditional trigger) | Inc 5 §6 | Partial | Entry and abstain exit are covered by R3/R4; final GateResult and `repair_summaries` still reflect the pre-repair state unless R5-S3 is added. |
| FR-7 Rollback envelope | Inc 5 §6 steps 3-5 | Partial | Strict-subset rollback needs stable diagnostic identity/multiset semantics (R5-S1). |
| NFR-2 Bounded | §6 Guard / Tests | Partial | Accepted re-validation design now exceeds "one scan per feature"; bound the real scan budget (R5-S2). |
| OQ-5 placement | Inc 5 §6 placement | Full | No new gap; endorse R2-S4. |
| RepairConfig / rollout | §6 guard, §10 | Partial | Unchanged from R3 unless triaged. |

---

## Requirements Coverage Matrix — R4

Focused on the Inc 5 delta only. Analysis only (no triage).

| Requirement | Plan Step(s) | Coverage | Gaps (R4) |
| ---- | ---- | ---- | ---- |
| FR-1 Detection (unconditional trigger) | Inc 5 §6 | Partial | R3-S1 fixes entry, but exit path is broken. Abstaining leaves `pre_result` PASSED, bypassing LLM-retry (R4-S1). |
| FR-7 Rollback envelope | Inc 5 §6 steps 3-5 | Partial | Re-validation will roll back successful partial repairs if an abstained violation remains (R4-S2). Must implement strict-subset re-validation. |
| OQ-5 placement | Inc 5 §6 placement | Full | Endorse R2-S4 invariant. |
| RepairConfig / rollout | §6 guard, §10 | Partial | `pre_checkpoint_repair` documented but unwired (R3-S3). |

---

## Requirements Coverage Matrix — R3

Focused on the Inc 5 delta only. Analysis only (no triage).

| Requirement | Plan Step(s) | Coverage | Gaps (R3) |
| ---- | ---- | ---- | ---- |
| FR-1 Detection (unconditional trigger) | Inc 5 §6 | Partial | R2 addressed internal gates; **outer call-site gate at 2313-2317 still blocks invocation on PASSED pre_validate** (R3-S1). `content_contract` missing from default `RepairConfig.repairable_categories` → routing no-op (R3-S2). |
| FR-7 Rollback envelope | Inc 5 §6 steps 3-5 | Partial | R2 merge covers bytes + registry ordering + syntax re-validation. Unchanged pending R3-S1 (rollback path unreachable if method never called). |
| OQ-5 placement | Inc 5 §6 placement | Full | Endorse R2-S4 invariant. |
| RepairConfig / rollout | §6 guard, §10 | Partial | `pre_checkpoint_repair` documented but unwired (R3-S3). |

---

## Requirements Coverage Matrix — R1

Analysis only (no triage). Maps each requirements section/FR to the plan increment(s) that address it.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 Detection in integration path | Inc 5 (§6) | Partial | Plan piggybacks on the syntax/lint-failure path (`integration_engine.py:838-851`) which won't fire for valid-but-invented names (R1-S1); `.ts`/`.tsx` excluded from repair set (R1-S2). |
| FR-2 Truth re-derivation | Inc 1 (§2) | Full | `TruthSource` + `LiveDiskTruthSource` cover re-derivation; degrade-on-missing-schema covered. |
| FR-3 Nearest-match + abstain | Inc 3 (§4) | Partial | Degenerate-candidate branching (0/1/2 matches) and tie/margin rule underspecified (R1-S5, R1-F4). |
| FR-4 Dedicated diagnostics + routing | Inc 2 (§3) | Partial | Model-name sourcing for the bridge is unbacked by the live violation shape (R1-S3, R1-F2); routing regression snapshot is well-specified. |
| FR-5 prisma_field_rename | Inc 4 (§5) | Partial | Nested/spread/computed-key object-literal handling unspecified (R1-S9); multi-model binding untested (R1-S8). |
| FR-6 import_path_rename | Inc 4 (§5) | Full | Seeded negatives + nearest-match + guarded parent-collapse (OQ-6) specified; abstain path covered. |
| FR-7 Non-destructive + re-validation | Inc 4 (guard) + Inc 5 (re-validate) | Partial | Rollback assumes orchestrator staging; pre-merge seam writes in place with no staging (R1-S4, R1-F3). |
| FR-8 run-011 gate | Inc 6 (§7) | Partial | Expected abstain set has an unspecified `<ties>` member, not yet a frozen set (R1-F5). |
| FR-9 Observability & attribution | Inc 6 (§7) | Partial | Per-attempt attribution covered; aggregate abstain-rate denominator/threshold missing (R1-S6, R1-F6). |
| FR-10 Swappable truth source | Inc 1 (§2) | Full | `TruthSource` protocol + `ArtifactTruthSource` stub document the swap point. |
| NFR-1 Deterministic | Inc 1/3/4 | Full | No LLM anywhere; difflib deterministic. |
| NFR-2 Bounded | Inc 5 guard | Partial | "One scan per feature" stated; no numeric cost ceiling for pathological flagged-token counts (noted in R1-F6 area). |
| NFR-3 Abstain-safe | Inc 3/4 | Full | Abstain-default is the core invariant; reinforced by R1-S8/S9 tests. |
| NFR-4 TS/Prisma-first, extensible | Inc 1/4 | Full | `TruthSource` + step abstraction generalize. |
| NFR-5 Truth-source-swappable | Inc 1 | Full | Same as FR-10. |
| NFR-6 Detection-layer-stable | Inc 2 | Partial | In tension with FR-2/FR-5 model-name need; may require an additive field (R1-S3, R1-F2). |

## Requirements Coverage Matrix — R2

Focused on the Inc 5 delta (FR-1 / FR-7) only — the R2 scope. Other rows are unchanged from the R1 matrix above. Analysis only (no triage).

| Requirement | Plan Step(s) | Coverage | Gaps (R2) |
| ---- | ---- | ---- | ---- |
| FR-1 Detection in integration path (unconditional trigger) | Inc 5 §6 step 1 | Partial | Only the 845-846 early-return is addressed; the **second** short-circuit at 851-855 (`repairable`) and the syntax/lint-only `diagnostics` build at line 863 are not reconciled — content gate can reach `run_file_repair` with no content diagnostics (R2-S1). Stale-source read risk: must scan post-syntax-repair disk content, not the pre-repair `files_to_repair` snapshot (R2-S2). |
| FR-7 Non-destructive + pre-image rollback | Inc 5 §6 steps 3-4 | Partial | Registry update (lines 884-892) runs before re-validation/rollback → rolled-back file left flagged `repaired` (R2-S3); re-validation is content-only and misses rename-induced syntax regressions (R2-S5); FR-7 "byte-identical" acceptance does not cover the registry side effect (R2-F1). |
| OQ-5 placement vs `_CANONICAL_ORDER` | Inc 5 §6 placement | Full | Seam ("after syntax/lint repair, before merge") is correct; no hard circular dependency. Minor: assert the same-file ordering invariant (R2-S4). |
