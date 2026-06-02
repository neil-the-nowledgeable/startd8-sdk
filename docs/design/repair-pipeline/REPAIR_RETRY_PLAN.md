# Repair-Retry — Implementation Plan

**Version:** 1.4 (Post-CRP — R1–R5 triaged, 22/22 S-suggestions applied)
**Date:** 2026-06-02
**Status:** Draft for review — pairs with `REPAIR_RETRY_REQUIREMENTS.md` v0.6

> Deterministic, no-LLM post-job repair pass driven by `prime-postmortem-report.json`.
> Reuses the merged name-repair pipeline; adds report-driven discovery, a violation
> classifier, and a scaffold lever. Every step traces to an FR; every FR has a step.

---

## 0. Strategy & sequencing

Seven increments, classifier-and-levers first (pure/unit-testable), CLI + harness last:

```
Inc 1  Report loader + violation extraction        (FR-1 partial, FR-2)  — pure
Inc 2  TargetExistenceSearch + classifier          (FR-3)                — owns its search (R1-S1)
Inc 3  Broadened resolver + rewrite lever           (FR-4)                — extends name-repair
Inc 4  Scaffold levers (cofile + barrel)            (FR-5, FR-6, FR-11)   — fs writes, confined
Inc 5  revalidate.py — re-scan + scoped rollback    (FR-7)                — standalone module (R1-S2)
Inc 6  Engine + report + regen worklist             (FR-8, FR-9, FR-10)   — orchestration
Inc 7  CLI `--from-run` + run-012 acceptance        (FR-1, FR-12)         — wiring + gate
```

New package: `src/startd8/repair/retry/` (loader, search, classifier, scaffold, revalidate,
engine). Inc 3 edits the name-repair `truth_source.py`/`import_path_rename.py`.

**Dependency note (R1-S1).** Inc 2 must not depend on Inc 3's resolver while shipping first. It
owns a narrow `TargetExistenceSearch` interface (a resolvable-surface enumerator over the run/
project tree) that the classifier consumes; Inc 3's broadened `ProjectTruthSource` is a richer
*implementation* of the same search used by the rewrite lever, but Inc 2 tests against a
fixture-backed `TargetExistenceSearch` with **no Inc 3 code present** — proving the decoupling.
**One predicate, two callers (R2-S3 + R3-F3):** the classifier (`locations_for(name)`) and the
rewriter (`resolvable_specifiers()`) ask *different-shaped* questions; they MUST resolve to a
single authoritative "target exists" predicate (a parity test asserts both agree on run-012 #4,
the ambiguous two-`types.ts` case, the missing cofile, and the barrel dir).
**Increment-boundary honesty (R1-S2):** Inc 5 delivers a real `repair/retry/revalidate.py`
(re-scan + **pre-image + kept-subset replay** rollback — *not* offset-scoped, R2-S1/R3-S1), not
logic buried inside the Inc 6 engine.

---

## 1. Key seams (from the merged name-repair work + existing CLI)

| Seam | Location | Role |
|------|----------|------|
| Existing repair CLI | `cli.py:923 repair([FILES])` | add a `--from-run` branch (FR-1) |
| Postmortem schema | `contractors/prime_postmortem.py` (`disk_compliance.semantic_issues`, `file_path`) | violation source (FR-2) |
| Import resolver | `contractors/upstream_interface.resolve_specifier_to_paths`; `validators/cross_file_imports._resolves_on_disk` | target-existence search (FR-3) |
| Rewrite step | `repair/steps/import_path_rename.py` + `repair/truth_source.py` | rewrite lever (FR-4) |
| Re-scan | `validators/cross_file_imports.scan_unresolvable_imports` | re-validation (FR-7) |
| Strict-subset rollback | `contractors/integration_engine._attempt_content_name_repair` (steps 5-6) | rollback semantics to mirror (FR-7) |
| Orchestrator | `repair/orchestrator.run_file_repair` | apply routed steps to the rewritable subset |

---

## 2. Increment 1 — Report loader + violation extraction (FR-2)

**New `repair/retry/models.py`:** `RetryViolation` dataclass
`{feature_id, file_path, category, specifier, message}` + `RetryDisposition` enum
(`rewritten|scaffolded|rolled_back|needs_regen`).

**New `repair/retry/report_loader.py`:**
- `load_violations(report_or_dir: Path) -> list[RetryViolation]` — accept a
  `prime-postmortem-report.json` or a run dir (resolve `**/plan-ingestion/prime-postmortem-report.json`).
- Iterate `features[*]` where `success is False`; for each
  `disk_compliance.semantic_issues[*]` with `category == "unresolvable_import"`, parse the
  `specifier` from the message (the backtick-quoted token after `imports`), keep `file_path`.

**Tests:** `test_report_loader.py` against the real run-012 report fixture (copied small) — 5
violations, correct specifiers + file_paths.

## 3. Increment 2 — TargetExistenceSearch + classifier (FR-3)

**New `repair/retry/search.py`:** `TargetExistenceSearch` protocol + a v1
`DiskTargetSearch(run_root, project_root)` that enumerates the resolvable surface (run
`generated/` **first**, then project tree, **excluding `node_modules`**) and answers
`locations_for(module_name) -> list[Path]`. This is what the classifier consumes — **no Inc 3
dependency** (R1-S1).

**New `repair/retry/classifier.py`:** `classify(v, search) -> RetryClass`, with the FR-3
precedence **rewritable → barrel → cofile → needs-regen** and the multi-match rule:
- **rewritable-path:** the intended module resolves at **exactly one** location ≠ the used
  specifier. **>1 location → `needs-regen` (`ambiguous_target`)**, never rewritable (R1-F2/F4).
- **scaffoldable-barrel:** specifier resolves to a *directory* with sibling modules but no
  `index.{ts,tsx,js}`.
- **scaffoldable-cofile:** style/asset specifier (`.module.css`, `.css`, …), importer-relative,
  file missing.
- else **needs-regen.**

**Tests:** run green with **no Inc 3 code present** (fixture-backed search). run-012 fixtures →
`{#4: rewritable, #1-3: cofile, #5: barrel}`; a base name in **two** dirs → `needs-regen`
(`ambiguous_target`); a `.module.css` that also matches a stray file elsewhere stays cofile
(precedence pinned); bare-package / truly-absent → `needs-regen`. **Parity test (R2-S3/R3-F3):**
the classifier search and the Inc 3 rewrite resolver return the **same** "target exists" verdict
for run-012 #4, the ambiguous two-`types.ts` case, the missing cofile, and the barrel dir.

## 4. Increment 3 — Broadened resolver + rewrite lever (FR-4)

**Edit `repair/truth_source.py`:** add `ProjectTruthSource(LiveDiskTruthSource)` to enumerate the
**full** resolvable surface. **Root discovery is `tsconfig`-`paths`-driven (R1-S5)** — derive the
source roots from the project's `tsconfig` `paths`/`baseUrl` (the same config used to pick the
`@/…` alias form, OQ-3), with a documented fallback dir list only when no `tsconfig` is present.
Do **not** hardcode `components/types/lib/app` (contradicts NFR-5). Keep the seeded negatives.

**Edit `repair/steps/import_path_rename.py` — add an explicit relative-rewrite path (R5-S2,
critical).** This does **not exist** today: `_resolve_specifier` (`import_path_rename.py:111-127`)
has only seeded negatives, `@/` parent-collapse, and `best_match` against the **lib-only**
`resolvable_specifiers()` — so `../../../types/wizard` cannot reach `components/wizard/types.ts`.
Add a dedicated branch: given `(importer_path, bad_specifier)`, resolve the intended module via the
**shared FR-3 target-existence predicate** (the broadened `ProjectTruthSource`, *not* the lib-only
`best_match`), then emit a canonical form. **Abstain on ambiguity (R1-S4):** ≥2 locations → no
rewrite (→ residue). **Alias-form selection agrees with the blind
resolver (R3-F2):** `_resolves_on_disk` is `tsconfig`-blind (`@/` vs root + `src/` only), so emit
the `@/…` alias **only when it resolves under that convention**; otherwise emit the **relative**
form — never a `tsconfig`-`paths` alias the re-scan can't see. **Return the applied substitution
set (R3-S1):** the step must expose the `{specifier → target}` substitutions it applied (the
primitive is whole-file `str.replace`, no offsets) so Inc 5 can replay the kept subset.
**Anchor the replacement to import/require/export-from positions (R4-S3):** replace
`_rewrite_specifier`'s global `out.replace(q+spec+q, …)` with a match anchored to
`import … from '…'` / `require('…')` / `export … from '…'` — a global replace would corrupt the
same quoted token inside an unrelated string literal/comment (non-destructive violation; also a
latent bug in the merged step). The existing seeded-negative + nearest-match paths are unchanged.

**Tests:** `../../../types/wizard` (importer at `components/wizard/steps/`) → rewrites to a
specifier resolving to `components/wizard/types.ts`; **two name-matching `types.ts` under
different dirs → abstain (no rewrite), violation to worklist** (R1-S4); root discovery follows a
fixture `tsconfig` with non-default roots (R1-S5); **a file with the bad specifier in both an
import and a string literal → only the import is rewritten** (anchored, R4-S3); **negative control
(R5-S2): the lib-only `best_match` path abstains on `../../../types/wizard` — #4 is fixed by the
new relative branch, not the lib surface**; the run-011 `@/lib/*` cases still pass (regression).

## 5. Increment 4 — Scaffold levers (FR-5, FR-6, FR-11)

**New `repair/retry/scaffold.py`:**
- **Realpath path-confinement guard (R1-S9 + R3-S2), shared by both levers:**
  `_confined_target(importer, specifier, run_root) -> Path|None` — compute the candidate write
  path, then `Path.resolve(strict=False)` **both** it and `run_root/generated` and require
  `candidate.is_relative_to(generated_root)` (**realpath before containment** — a string-prefix or
  pre-resolve check is bypassable by `../`/symlinks). Escape → `None` → residue (no write); a
  legitimate `./X.module.css` beside the importer is **allowed**. No such guard exists in
  `src/startd8/repair/` today — net-new.
- `scaffold_cofile(importer, specifier, run_root) -> Path|None` — via the guard; if **missing**,
  write an empty CSS module (`/* scaffolded by repair-retry; styling TODO */\n`). Never overwrite.
- `scaffold_barrel(dir_path, run_root) -> Path|None` — if `index.{ts}` absent (and confined),
  generate `index.ts`. **Bounded to the regex extractor (R2-S2):** `extract_ts_exports` collapses
  every `export default` to `"default"` and can't expand `export *`/type-only re-exports — so v1
  emits `export { default as <Name> } from './<Name>'` for **default-export component siblings**
  (`<Name>` from the **filename**), and **abstains** (logs) on any sibling it can't soundly name
  (anonymous default + mismatched filename, `export *`-only, type-only) and on cross-sibling name
  collisions — never a blind `export *` (OQ-2).

**Tests:** cofile creates an empty `*.module.css` only when missing (idempotent: second call is a
no-op); confinement — `../`-escape → `None`, **symlink inside `generated/` pointing out → `None`**,
**legitimate `./Step.module.css` beside the importer → allowed** (R3-S2); barrel emits
`export { default as <Name> }` per default-export `*Step.tsx`; anonymous-default / `export * from`
/ type-only / colliding-name siblings → **abstain with reason**, never a blind `export *` (R2-S2).

## 6. Increment 5 — `revalidate.py`: re-scan + scoped rollback (FR-7)

**New `repair/retry/revalidate.py`** (a real module, R1-S2): `revalidate(fixes, run_root,
project_root) -> list[KeptOrRolledBack]`. After applying rewrites/scaffolds, re-run
`scan_unresolvable_imports` over the affected importers **and the generated artifacts** (new
`index.ts`/scaffolded files, R1-S8), **plus `check_syntax`** (R4-S2 — a string-replace rewrite can
break a quote/brace; a content-only re-scan would falsely accept a broken file). Mirror
`_attempt_content_name_repair`'s strict-subset rule (which already pairs content + syntax): a fix
is **kept** iff it introduces no *new* `unresolvable_import` **and** no new syntax error.
**Violation identity (R5-S3):** "new" is diffed over the **`{source_file, specifier}` multiset**
(`post − pre`), not raw counts or message strings — so an unchanged, co-located abstained
violation never false-triggers rollback of a successful rewrite, and a genuinely new import break
is caught.

**Rollback = pre-image + kept-subset replay (R2-S1 + R3-S1).** The reused rewrite step
(`import_path_rename._rewrite_specifier`) is a whole-file `out.replace(q+spec+q, …)` — **no
offsets, replace-all** — so an `(offset, old, new)` undo is impossible (and one specifier used
twice is replaced in both spots). Therefore: **(a)** change `import_path_rename` to **return the
set of `{specifier → target}` substitutions it applied** (R3-S1 — without this, Inc 5 has nothing
to replay from); **(b)** Inc 5 captures the importer's **pre-image**, applies all fixes to a
working copy, re-validates, then rebuilds the kept result by **re-applying only the kept
substitutions to the pre-image** (rollback = drop the failing substitution from the replay set).
Scaffolds roll back by **deleting** the created file. Rolled-back violations → residue (Inc 6).

**Tests:** a rewrite/scaffold that resolves its target is kept; a fix that introduces a new
violation is rolled back (scaffold file deleted / its substitution dropped from the replay);
**a file with one kept rewrite + one rolled-back fix == `pre-image + kept substitution only`**
(not an offset-corrupted hybrid, not a wholesale revert, R2-S1/R3-S1); a file using one specifier
**twice** (import + `export … from`) round-trips; **a rewrite that breaks syntax (quote mismatch)
is rolled back** (R4-S2); re-scan includes a generated `index.ts` (R1-S8).

## 7. Increment 6 — Engine + report + worklist (FR-8, FR-9, FR-10)

**New `repair/retry/engine.py`:** `RepairRetryEngine.run(report_or_dir, *, scaffold: bool) -> RetryReport`:
1. `load_violations` (Inc 1) → **live-state pre-filter (R4-S1, critical)**: the postmortem is a
   *static snapshot*, so before classifying, re-check each violation against current disk — if its
   specifier already resolves (or is absent from the importer), mark `already_resolved` and
   **drop it** (not repaired, not worklisted). This is what makes a second `--from-run` pass a true
   fixpoint (exit 0, empty worklist) instead of a worklist flood;
2. `classify` the survivors (Inc 2);
3. dispatch: rewritable → `import_path_rename` via `run_file_repair`; cofile/barrel → scaffold
   (Inc 4, gated by `scaffold`); needs-regen/ambiguous/unparseable/escape → worklist;
4. re-validate (content **+ syntax**, R4-S2) + scoped rollback (Inc 5 `revalidate`);
5. emit `repair-retry-report.json` (per-violation dispositions incl. `already_resolved` + `deferred` scaffold array +
   `resolution` "N/M resolved" + a **recorded-not-gated** recomputed score, R1-S3) +
   `repair-retry-summary.md`, and `regen-worklist.json` (schema
   `{feature_id, importer_file, missing_target, reason, task_filter_token}`, R1-F7 — empty for
   run-012). **No `would_pass` claim.** **Artifacts are written under the resolved run dir**
   (`<run>/plan-ingestion/repair-retry/`), never the process cwd (R5-F3).
No LLM anywhere (FR-9).

**Tests:** end-to-end over a run-012-shaped fixture: 1 rewritten + 4 scaffolded, 0 worklist,
resolution "5/5 resolved", **no `would_pass` field** (R1-S3); `scaffold=False` → 1 rewritten + 4
worklist entries; the worklist `task_filter_token` round-trips through the existing `--task-filter`
parser (R1-F7).

## 8. Increment 7 — CLI `--from-run` + run-012 acceptance (FR-1, FR-12)

**Edit `cli.py:repair`:** add `--from-run <PATH>` and `--scaffold/--no-scaffold`, making
`[FILES]` optional. **Mode validation (R1-S6):** `--from-run` + `[FILES]` → usage error;
**neither** → usage error; `--scaffold` without `--from-run` → usage error. When `--from-run` is
set, dispatch to `RepairRetryEngine.run`. **Output contract (R1-S10):** print the absolute paths
to `repair-retry-report.json` and `regen-worklist.json` on stdout (so cap-dev-pipe, OQ-4, consumes
them without guessing); exit non-zero **iff** the worklist is non-empty.

**Acceptance harness** `tests/unit/repair/retry/test_run012_repair_retry.py`: a **checked-in
fixture derived from the real run-012 report + generated tree** (R1-F9 — a provenance comment
links the run id; the 5 specifiers/`file_path`s are asserted byte-for-byte against the
investigation doc §2 table), mirroring
run-012's generated tree (the 6 `.tsx` + `types.ts`, missing the 3 CSS + barrel) →
`--from-run --scaffold` resolves all 5, empty worklist, **zero LLM**, and the gate asserts
**0 residual `unresolvable_import`** — **not** a PASS verdict (R1-S3; the recomputed score is
recorded for visibility, not gated).

**Fixpoint test pins the resolver (R3-S3).** The second-pass test must pin **which candidate
paths** are passed to `scan_unresolvable_imports` (generated batch + project root) and assert the
chosen #4 rewrite form resolves through the **`tsconfig`-blind** `_resolves_on_disk` (root + `src/`
only). Two fixtures: **(a)** `tsconfig` aliasing `@/* → src/*` with the target **outside** `src/`
→ the rewrite must pick the **relative** form (the `@/` alias would not resolve blind), second
pass resolved; **(b)** no `tsconfig`, target in the generated tree passed as a candidate →
resolved. Both prove the #4 rewrite re-classifies as resolved (FR-11), not oscillates.

**Second-pass fixpoint via live-state pre-filter (R4-S1):** a second `--from-run` over the
repaired tree marks all 5 report violations `already_resolved`, makes no file changes, emits an
**empty** worklist, and **exits 0** — proving the static-snapshot postmortem doesn't flood the
worklist on re-run.

CLI tests cover the three usage-error mode combinations (R1-S6) and that stdout prints both
artifact paths with the exit code matching worklist emptiness (R1-S10).

---

## 9. Requirement → increment traceability

| FR | Increment |
|----|-----------|
| FR-1 `--from-run` mode | Inc 1 (load) + Inc 7 (CLI) |
| FR-2 extraction | Inc 1 |
| FR-3 classifier | Inc 2 |
| FR-4 rewrite + broadened resolver | Inc 3 |
| FR-5/FR-6 scaffold levers | Inc 4 |
| FR-7 re-validation/rollback | Inc 5 |
| FR-8 regen worklist | Inc 6 |
| FR-9 no-LLM | Inc 6 (invariant) |
| FR-10 report | Inc 6 |
| FR-11 non-destructive/idempotent | Inc 4 + Inc 7 (fixpoint test) |
| FR-12 run-012 gate | Inc 7 |

## 10. Risks & mitigations

| Risk | Mitigation |
|------|-----------|
| Scaffolded empty CSS hides a real styling gap | FR-5 writes a `TODO` marker; report `deferred` array enumerates scaffolds; `--scaffold` opt-in. |
| Rollback offset model is undefinable (str.replace primitive) | **Resolved (R2-S1/R3-S1):** rewrite step returns its `{specifier→target}` substitution set; Inc 5 rollback = replay kept subset on the pre-image — no offsets. |
| Barrel export computation over-promised vs regex extractor | **Resolved (R2-S2):** v1 = default-export components named from the filename; abstain on `export *`/type-only/anonymous-default/collision; never blind `export *`. |
| `tsconfig`-alias chosen but blind resolver can't see it (oscillation) | **Resolved (R3-F2/S3):** rewrite picks the form the `tsconfig`-blind `_resolves_on_disk` resolves (relative if the alias wouldn't); fixpoint test pins the candidate set. |
| Classifier search & rewrite resolver disagree | **Resolved (R2-S3/R3-F3):** one authoritative "target exists" predicate; parity test asserts both callers agree. |
| Confinement guard bypassable by symlink/`..` | **Resolved (R3-S2):** realpath (`resolve()`) **before** `is_relative_to`; symlink-escape test + positive confined-write test. |
| Static postmortem → second pass floods worklist | **Resolved (R4-S1, critical):** live-state pre-filter in Inc 6 step 1 — already-fixed violations → `already_resolved`, dropped; second pass exits 0. |
| String-replace rewrite corrupts unrelated literals | **Resolved (R4-S3):** rewrite anchored to import/require/export-from positions, not global `out.replace`. |
| Rewrite resolves import but breaks syntax | **Resolved (R4-S2):** Inc 5 re-validation runs `check_syntax`; a new syntax error → rollback. |
| Run-012 #4 rewrite unreachable (lib-only resolver) | **Resolved (R5-S2, critical):** Inc 3 adds an explicit relative-rewrite branch over the broadened FR-3 predicate; lib-only `best_match` abstains (negative control). |
| Strict-subset diff false-triggers on unchanged abstain | **Resolved (R5-S3):** identity = `{source_file, specifier}` multiset; only `post − pre` counts as new. |
| Reports written to cwd (cap-dev-pipe can't find them) | **Resolved (R5-F3):** artifacts under `<run>/plan-ingestion/repair-retry/`, absolute stable paths. |
| Broadened resolver false-rewrites (more candidates → ambiguity) | **Resolved (R1-S4):** ≥2 locations → abstain → `needs-regen` (`ambiguous_target`), first-class tested; exact module-name match before nearest-match. |
| Writing outside the run tree via a `../` specifier | **Resolved (R1-S9):** path-confinement guard in Inc 4 — a specifier escaping `generated/` writes nothing → `needs-regen`. |
| Scaffold rollback clobbers a co-located kept fix | **Resolved (R1-S7):** Inc 5 edit-scoped rollback (track each rewrite span); shared-importer fixes re-validated once, only the failing edit undone. |
| Generated barrel itself fails to compile (export collision) | **Resolved (R1-S8):** named re-exports / abstain on colliding name; re-validation re-scans the generated `index.ts`, not just the importer. |
| "Would PASS" overclaim | **Resolved (R1-S3):** gate asserts 0 residual `unresolvable_import`; recomputed score recorded-not-gated; no `would_pass` field. |
| Hardcoded source roots break across projects | **Resolved (R1-S5):** root discovery is `tsconfig`-`paths`-driven with a documented fallback. |
| Writing into the run's generated tree corrupts a re-run | NFR-4 no-overwrite + FR-11 fixpoint (scaffold **and** rewrite); in-place is idempotent (OQ-5). |
| Postmortem schema/message drift | NFR-6 consumes `semantic_issues` defensively; unparseable message → `needs-regen` (`unparseable_message`), never dropped (R1-F1). |

## 11. Conventions checklist (per CLAUDE.md)
- [ ] `get_logger(__name__)` in every new module; new files added to logger-policy allowlist if needed.
- [ ] No hardcoded model strings (N/A — no LLM).
- [ ] Reuse `resolve_specifier_to_paths` / `_resolves_on_disk` / `scan_unresolvable_imports` — don't re-implement resolution.
- [ ] `pytest tests/unit/repair -q` green before commit; `ruff`/`black`/`mypy` clean on new files.

---

*Plan v1.0 — classifier + scaffold + broadened-resolver levers over the merged name-repair
pipeline, report-driven via `--from-run`. Pairs with requirements v0.2.*

*Plan v1.1 — Post-CRP R1. All 10 S-suggestions applied. Headline: the "would PASS" gate was an
overclaim (multi-factor score) → asserts 0-residual-imports, score recorded-not-gated (R1-S3).
Also: decoupled the classifier from the resolver (R1-S1), made Inc 5 a real `revalidate.py`
(R1-S2), added abstain-on-ambiguous (R1-S4), `tsconfig`-driven roots (R1-S5), CLI mode validation
(R1-S6), edit-scoped shared-importer rollback (R1-S7), barrel-collision safety + re-scan generated
artifacts (R1-S8), path-confinement (R1-S9), and the stdout artifact-path/exit-code contract
(R1-S10). Dispositions in Appendix A. Pairs with requirements v0.3.*

*Plan v1.2 — Post-CRP R2 (gpt-5.5) + R3 (claude-opus-4-8-1m), focused on the R1-fix delta. 6
S-suggestions applied. Headline: Inc 5's `(offset,old,new)` rollback was ungrounded — the reused
`import_path_rename._rewrite_specifier` is a whole-file `str.replace`, so the step now returns its
substitution set and rollback replays the kept subset on the pre-image (R2-S1/R3-S1). Also: barrel
narrowed to the regex extractor's sound cases (R2-S2), one shared target-existence predicate +
parity test (R2-S3/R3-F3), realpath-before-containment guard (R3-S2), and a fixpoint test pinned to
the `tsconfig`-blind resolver (R3-S3). The three-round / two-model arc kept finding defects in the
prior round's fixes. Pairs with requirements v0.4.*

*Plan v1.3 — Post-CRP R4 (gemini-3.1-pro). 3 new S-suggestions applied. Headline (R4-S1, critical):
the postmortem is a static snapshot, so a second `--from-run` would re-read the same violations and
flood the worklist — Inc 6 now live-state-pre-filters (already-fixed → `already_resolved`, dropped),
making the fixpoint real. Also: `check_syntax` in re-validation (R4-S2) and import-anchored rewrite
instead of global `str.replace` (R4-S3). Pairs with requirements v0.5.*

*Plan v1.4 — Post-CRP R5 (composer-2.5). R5-S1 was already closed by the v1.3 R4-sync; R5-S2/S3/F3
applied. Headline (R5-S2, critical): the relative-rewrite path doesn't exist in the merged step
(lib-only resolver, no relative branch), so run-012 #4 needs a real new algorithm over the FR-3
predicate — Inc 3 now specifies it with a lib-only-abstains negative control. Also: strict-subset
identity multiset (R5-S3) and run-dir-co-located artifacts (R5-F3). Pairs with requirements v0.6.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

> Append-only convergent-review state. New reviewers add a round to **Appendix C**, then
> dispositions are recorded in **Appendix A** (applied) or **Appendix B** (rejected).
> Reviewers: scan A/B/C first and do **not** re-propose settled or rejected items.

### Appendix A: Applied Suggestions

**R1 triage (2026-06-01, orchestrator: claude-opus-4-8-1m).** All 10 S-suggestions ACCEPTED.

| ID | Disposition | Where merged |
|----|-------------|--------------|
| R1-S1 | ACCEPTED | §0 + Inc 2 — `TargetExistenceSearch` interface owned by the classifier; Inc 2 tests with no Inc 3 code. |
| R1-S2 | ACCEPTED | §0 + Inc 5 — `revalidate.py` is a real standalone module, not engine-internal. |
| R1-S3 | ACCEPTED | Inc 6 + Inc 7 — gate asserts 0 residual `unresolvable_import`; score recorded-not-gated; no `would_pass`. **Headline.** |
| R1-S4 | ACCEPTED | Inc 3 — abstain-on-ambiguous (≥2 locations → `needs-regen`), separately tested. |
| R1-S5 | ACCEPTED | Inc 3 — `tsconfig`-`paths`-driven root discovery, fallback documented (not hardcoded). |
| R1-S6 | ACCEPTED | Inc 7 — `--from-run`/`[FILES]`/`--scaffold` mode validation (both/neither/legacy → usage error). |
| R1-S7 | ACCEPTED | Inc 5 — edit-scoped rollback; shared-importer fixes re-validated once. |
| R1-S8 | ACCEPTED | Inc 4 + Inc 5 — barrel collision → named re-exports/abstain; re-scan the generated `index.ts`. |
| R1-S9 | ACCEPTED | Inc 4 — path-confinement guard; `../`-escape → `needs-regen`, no write. |
| R1-S10 | ACCEPTED | Inc 7 — stdout prints both artifact paths; exit code matches worklist emptiness. |

**R2 (gpt-5.5) + R3 (claude-opus-4-8-1m) triage — focused on the R1-fix delta.** 6 S-suggestions
ACCEPTED, merged together (R3 grounds/sharpens R2; verified against live source before merge).

| ID | Disposition | Where merged |
|----|-------------|--------------|
| R2-S1 + R3-S1 | ACCEPTED | §0 + Inc 3 + Inc 5 — rewrite step **returns its substitution set**; rollback = pre-image + kept-subset replay (the primitive is `str.replace`, no offsets). **Headline.** |
| R2-S2 | ACCEPTED | Inc 4 — barrel narrowed to default-export components (filename-named); abstain on what the regex extractor can't prove. |
| R2-S3 + R3-F3 | ACCEPTED | §0 + Inc 2 — single "target exists" predicate; parity test asserts classifier ↔ rewriter agree. |
| R3-S2 | ACCEPTED | Inc 4 — realpath (`resolve()`) before `is_relative_to`; symlink + positive confined-write tests. |
| R3-S3 | ACCEPTED | Inc 7 — fixpoint test pins the candidate set + asserts alias-vs-relative against the `tsconfig`-blind resolver. |
| (R2-F2 fixpoint) | FOLDED | into R3-S3's two-fixture test (per R3's refinement). |

**R4 triage (gemini-3.1-pro).** All 3 S-suggestions ACCEPTED — each new. R4-S3 verified against the
merged `_rewrite_specifier` (global `str.replace`).

| ID | Disposition | Where merged |
|----|-------------|--------------|
| R4-S1 | ACCEPTED | Inc 6 step 1 — **live-state pre-filter** over the static postmortem; already-fixed → `already_resolved`, dropped. Makes the second-pass fixpoint real (exit 0). **Critical, new.** |
| R4-S2 | ACCEPTED | Inc 5 — re-validation adds `check_syntax`; a rewrite that breaks syntax → rollback. |
| R4-S3 | ACCEPTED | Inc 3 — `_rewrite_specifier` anchored to import/require/export-from, not global `out.replace` (fixes a latent merged-step bug). |

**R5 triage (composer-2.5).** 3 S-suggestions: R5-S1 was **already applied** (my R4 plan-sync, v1.3);
R5-S2/S3 ACCEPTED. R5-S2 verified against `truth_source.py:100-124` + `_resolve_specifier`.

| ID | Disposition | Where merged |
|----|-------------|--------------|
| R5-S1 | ALREADY-APPLIED | Plan v1.3 already synced R4 (Inc 6 pre-filter, Inc 5 syntax, Inc 3 anchor) — the drift R5 flagged was closed by the R4 triage. |
| R5-S2 | ACCEPTED | Inc 3 — explicit relative-rewrite branch over the broadened FR-3 predicate (the lib-only `best_match` can't reach #4); negative-control test. **Critical.** |
| R5-S3 | ACCEPTED | Inc 5 — strict-subset diff over the `{source_file, specifier}` multiset. |
| R5-F3 | ACCEPTED | Inc 6 — artifacts under `<run>/plan-ingestion/repair-retry/`, not cwd. |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-01

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-01 20:10:00 UTC
- **Scope**: Plan review (S-prefix) — increment sequencing/seams, broadened-resolver ambiguity, scaffold-vs-overwrite safety & rollback semantics, classifier target-existence correctness, CLI `--from-run`↔`[FILES]` interaction, report/worklist schema, and whether the run-012 "would PASS" claim is actually validated by the plan.

**Executive summary (top plan risks / gaps):**

- The plan's increment ordering has a latent dependency inversion: Inc 2 (classifier) "Implementation: enumerate the resolvable surface (Inc 3 `ProjectTruthSource`)" depends on Inc 3's broadened resolver, but Inc 2 ships first — the classifier cannot be unit-tested as "pure-ish" against the real resolver until Inc 3 exists. Either fold the surface enumerator earlier or stub it explicitly.
- §6/§7 place re-validation+rollback (Inc 5) inside the engine (Inc 6) — the increment boundary is fictional (Inc 5 has no standalone deliverable file), undermining the "classifier-and-levers first, unit-testable" sequencing claim.
- The plan never validates the headline "0.67/FAIL could flip to PASS": §7's end-to-end test asserts "verdict 'resolved'" (imports cleared), not a recomputed postmortem score. The strongest claim the plan actually tests is "5 imports cleared," which is weaker than "would PASS."
- Broadened resolver (Inc 3) walks "`components/`, `types/`, `lib/`, `app/`, …" but the seam table cites `resolve_specifier_to_paths`/`_resolves_on_disk`; the plan doesn't say whether root discovery is `tsconfig`-driven or a hardcoded dir list — a hardcoded list is brittle across projects (NFR-5 extensibility).
- The CLI change (§8) makes `[FILES]` optional when `--from-run` is set but doesn't specify the error when *both* are passed, or when *neither* is — the mode interaction is underspecified for a user-facing command.
- Rollback "restore the importer's pre-image for a rewrite; delete the scaffolded file" (§6) has no plan for the shared-file case (two violations, one importer) and no plan for re-validation *scope* (which files are re-scanned — only affected, or transitive importers?).
- The scaffold barrel (§5) `export * from './X'` over all siblings is asserted without a collision/validity check on the generated barrel itself; re-validation re-scans the importer, but the plan doesn't say it re-scans the generated `index.ts`.

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | Resolve the Inc 2 → Inc 3 dependency inversion: either (a) move the resolvable-surface enumerator (`ProjectTruthSource`) to Inc 2 so the classifier owns its search, or (b) define a narrow `TargetExistenceSearch` interface the classifier consumes and Inc 3 implements, and have Inc 2 test against a fixture-backed stub. State which. | §3 says Inc 2 classifier "enumerate the resolvable surface (Inc 3 `ProjectTruthSource`)" — it can't be "pure-ish, ships first" while depending on a later increment's resolver. The seam is circular as written. | §0 sequencing table + §3 Inc 2 | Inc 2 unit tests run green without Inc 3 code present (stub/interface), proving the decoupling. |
| R1-S2 | Architecture | medium | Make Inc 5 a real increment or merge it into Inc 6 honestly: §6 already says re-validation lives "In `repair/retry/engine.py` (Inc 6)". Either give Inc 5 a standalone `revalidate.py`/`rollback.py` module or relabel the sequencing so the "levers-first, engine last" claim isn't contradicted. | §0 lists Inc 5 as a discrete step but §6 implements it inside Inc 6's engine — the increment boundary is fictional and breaks the unit-testable-in-isolation premise. | §0 table + §6 heading | A reviewer can point to the file each increment delivers; Inc 5 has one. |
| R1-S3 | Validation | high | Add an explicit plan step (Inc 7 acceptance) that **recomputes and reports the postmortem score** post-repair and states clearly that the gate asserts "0 residual `unresolvable_import`," not "PASS." Drop or qualify "would PASS" wording to match what is tested. | §7/§8 assert verdict "resolved" (imports cleared) but the doc's framing (`> 0.67/FAIL could flip to PASS`) is never validated; the score is multi-factor. The plan should test what it claims or claim what it tests. | §7 test bullet; §8 acceptance harness | Acceptance asserts 0 residual `unresolvable_import`; a non-gating step records the recomputed score for visibility. |
| R1-S4 | Risks | high | Specify the broadened-resolver **ambiguity/abstain** behavior in Inc 3, not just §10 prose: when the intended module name resolves at ≥2 locations, `import_path_rename` must abstain → violation goes to needs-regen. Add a regression test in Inc 3 for the ambiguous case alongside the happy path. | §10 lists false-rewrite as a risk and §4 only tests the happy `../../../types/wizard` case; broadening "the whole project surface" is the precise change that creates ambiguity, so the abstain path must be a first-class tested behavior. | §4 Inc 3 tests; §10 row 3 | Unit test: two name-matching modules → abstain (no rewrite); violation lands in worklist. |
| R1-S5 | Interfaces | medium | Define root discovery for the broadened surface as `tsconfig` `paths`-driven (with a documented fallback dir list), not a hardcoded `components/types/lib/app` walk. Record where roots come from in the plan. | §4 hardcodes `components/`, `types/`, `lib/`, `app/`, … which is project-specific and contradicts NFR-5 (extensible without rework); `tsconfig paths` is already needed for alias selection (OQ-3), so reuse it. | §4 Inc 3 first paragraph | Test against a fixture `tsconfig` with non-default roots; surface enumeration follows the config, not the hardcoded list. |
| R1-S6 | Interfaces | high | Specify the `--from-run` ↔ `[FILES]` mode interaction in §8: error (or documented precedence) when both are supplied; clear error when neither is; and whether `--scaffold` is ignored/errors in `[FILES]` mode. Add CLI acceptance for each combination. | §8 only says `[FILES]` "becomes optional" — the both/neither/`--scaffold`-in-legacy cases are undefined for a user-facing command, inviting silent wrong-mode runs. | §8 Inc 7 | CLI tests: `--from-run` + FILES → defined behavior; neither → usage error; `--scaffold` without `--from-run` → defined behavior. |
| R1-S7 | Risks | medium | Add a shared-importer-file plan: when one importer hosts ≥2 violations, apply both fixes then re-validate the file once; on partial failure, roll back only the failing edit (line/AST-scoped), not the whole-file pre-image. Note this in Inc 5 and the §10 risk table. | §6 rollback "restore the importer's pre-image" is whole-file; two fixes in one `.tsx` (a missing CSS import + a wrong path) would let one rollback clobber the other's kept edit. | §6 Inc 5; §10 new row | Test: a file with one kept rewrite + one rolled-back fix retains the kept edit. |
| R1-S8 | Validation | medium | Have Inc 5 re-validation re-scan the **generated artifacts** (the new `index.ts` / scaffolded files), not only the original importers, and add an Inc 4 test that a barrel with colliding sibling exports is detected (named re-exports or abstain), per OQ-2. | §6 re-runs `scan_unresolvable_imports` "over the affected files"; a generated barrel that itself fails to compile (duplicate `export *`) resolves the importer but breaks the build — currently untested. | §5 Inc 4 tests; §6 Inc 5 | Test: two siblings with same export name → barrel uses named re-exports or abstains; re-scan includes generated `index.ts`. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S9 | Security | low | Add a path-confinement guard to Inc 4 scaffold levers: resolved scaffold/rewrite write paths must be confined under the run `generated/` root; a specifier escaping via `../` (the exact run-012 bug class) must refuse the write and route to needs-regen, not write outside the tree. | `scaffold_cofile` resolves importer-relative specifiers that contain `../`; an over-deep specifier could compute a write path outside the run root. The very failure class being repaired is the attack surface. | §5 Inc 4; §10 risk table | Test: a specifier resolving above the run root → no file written, violation → needs-regen. |
| R1-S10 | Ops | low | Specify `--from-run` exit-code and report-path contract in §8: exit non-zero iff worklist non-empty (already implied) **and** print the absolute path to `repair-retry-report.json`/`regen-worklist.json` so cap-dev-pipe (OQ-4) can consume them without guessing locations. | §8 prints "disposition summary" but the machine-consumable artifact paths aren't part of the contract; OQ-4 wiring needs stable, discoverable output paths. | §8 Inc 7; §10 | Test: CLI stdout includes the two artifact paths; exit code matches worklist emptiness. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- (none — R1 is the first round on this document.)

---

## Requirements Coverage Matrix — R1

Analysis only (no triage). Maps each requirement (FR/NFR) to the plan increment(s) that address it.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 Run-driven entry mode | Inc 1 (load), Inc 7 (CLI) | Partial | `--from-run`↔`[FILES]` both/neither interaction undefined (R1-S6); exit-code/report-path contract thin (R1-S10). |
| FR-2 Violation extraction | Inc 1 (`report_loader`) | Partial | Specifier-parse grammar + malformed-message disposition unspecified (R1-F1); loader "tolerates missing fields" but no test for dropped-vs-worklisted. |
| FR-3 Violation classifier | Inc 2 (`classifier`) | Partial | Search scope/precedence + multi-match rule undefined (R1-F2); depends on Inc 3 resolver despite shipping first (R1-S1). |
| FR-4 Rewrite (broadened resolver) | Inc 3 (`truth_source`, `import_path_rename`) | Partial | Ambiguity/abstain behavior tested only on happy path (R1-S4/R1-F4); root discovery hardcoded vs `tsconfig` (R1-S5). |
| FR-5 Scaffold cofile | Inc 4 (`scaffold.scaffold_cofile`) | Partial | Scaffolded styling gap not tracked as deferred item (R1-F5); path-confinement unspecified (R1-S9/R1-F10). |
| FR-6 Scaffold barrel | Inc 4 (`scaffold.scaffold_barrel`) | Partial | Generated barrel validity / export-collision not re-validated (R1-S8/R1-F6, OQ-2). |
| FR-7 Re-validation + rollback | Inc 5 (in engine) | Partial | Increment boundary fictional (R1-S2); shared-importer-file rollback unsafe (R1-S7/R1-F8); re-scan scope (generated artifacts) unstated (R1-S8). |
| FR-8 Targeted-regen worklist | Inc 6 (engine) | Partial | `target_files` semantics + `--task-filter` token format undefined (R1-F7). |
| FR-9 No-LLM | Inc 6 (invariant) | Full | Asserted as invariant; FR-9 acceptance (no-API-keys run) is testable as written. |
| FR-10 Disposition report | Inc 6 (engine) | Partial | Verdict claims "would PASS" not validated (R1-S3/R1-F3); scaffolded-deferred enumeration not in schema (R1-F5). |
| FR-11 Non-destructive/idempotent | Inc 4 + Inc 7 (fixpoint) | Partial | Fixpoint test covers scaffolds not rewrite idempotence (R1-F11 implied via FR-11 note); path-confinement (R1-S9). |
| FR-12 Run-012 acceptance gate | Inc 7 (harness) | Partial | Gate asserts imports cleared, not score/PASS (R1-S3/R1-F3); fixture provenance to real incident unpinned (R1-F9). |
| NFR-1 Deterministic | Inc 6 (FR-9), Inc 2 | Partial | Classifier non-determinism risk if search scope/precedence undefined (R1-F2). |
| NFR-2 Reuse-not-rebuild | §1 seams; §11 checklist | Full | Seam table + conventions checklist explicitly reuse `resolve_specifier_to_paths`/`scan_unresolvable_imports`. |
| NFR-3 Abstain/worklist-safe | Inc 6 (worklist) | Partial | Cofile scaffolds can silently swallow a styling gap (R1-F5); unparseable messages may drop silently (R1-F1). |
| NFR-4 No-overwrite | Inc 4 (no-overwrite); §10 | Partial | Confinement (no `../` escape) not covered by no-overwrite alone (R1-S9/R1-F10). |
| NFR-5 TS/Next-first, extensible | §0 new package; §4 | Partial | Hardcoded root dir list undercuts extensibility (R1-S5). |
| NFR-6 Report-source-stable | §10 schema-drift row; Inc 1 | Partial | Defensive loader good, but message-grammar drift handling unspecified (R1-F1). |

### Appendix C: Incoming Suggestions (continued)

#### Review Round R2 — gpt-5.5 — 2026-06-02 00:17 UTC

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-02 00:17:00 UTC
- **Scope**: Focused R2 — review only the R1-applied repair-retry deltas from `.crp-r2-focus-repair-retry.md`: edit-scoped rollback, barrel export computation, worklist schema, rewrite fixpoint, path confinement, and TargetExistenceSearch/ProjectTruthSource coherence. Grounded against `cross_file_imports.py`, `upstream_interface.py`, and `cli.py:923`.

**Executive summary (delta risks only):**

- **High:** Inc 5's edit-scoped rollback is under-specified. Tracking `(offset, old, new)` per edit is not coherent once multiple edits in the same importer shift offsets; the robust algorithm is re-apply the kept subset from the pre-image.
- **High:** Barrel export-name collision handling leans on regex extraction (`extract_ts_exports`), which collapses default exports to `"default"` and does not fully understand re-export/type-only forms. The plan should narrow v1 barrel generation to safe cases rather than promise full sibling export computation.
- **Medium:** The #4 rewrite fixpoint can be false without `tsconfig`: `_resolves_on_disk` only tries `@/` against root and `src`, while the rewrite target is `@/components/wizard/types`. If the run tree lacks `tsconfig` and generated artifacts are not passed into the scan as candidate paths, the alias form may remain flagged.
- **Medium:** Inc 2 and Inc 3 can still diverge: `TargetExistenceSearch` and `ProjectTruthSource` are described as related, but the plan does not require one implementation shared by classifier and rewrite.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Risks | high | Replace Inc 5's `(offset, old, new)` edit-scoped undo with a deterministic **pre-image + kept-subset replay** algorithm: capture the original importer bytes, apply all proposed edits to a working copy, re-validate, then rebuild the final content by replaying only the kept edits in sorted original-span order (or by re-deriving spans on the pre-image). | The focus prompt's offset-shift concern is real: after edit A changes length, edit B's offset in the working copy no longer matches its original offset. Undoing only A by the original span can corrupt B. Replay-from-pre-image makes partial rollback well-defined. | Inc 5 `revalidate.py` shared-importer scoping and §10 risk row "Scaffold rollback clobbers..." | Test: one importer with two fixes where edit A changes string length before edit B; roll back A and keep B. Final file equals pre-image plus only B, not an offset-corrupted hybrid. |
| R2-S2 | Validation | high | Narrow `scaffold_barrel` export-collision handling to what the regex extractor can soundly prove: default-export component siblings and simple named declarations/lists. If `extract_ts_exports` returns `default`, `export *`, or a re-export-only module in a way that cannot be assigned a stable exported name for the barrel, abstain or emit explicit default aliases; do not promise general TypeScript export computation. | `upstream_interface.extract_ts_exports` is regex-based: it adds `"default"` for any `export default`, parses `export { A as B }`, and does not provide source-aware semantics for default component names, type-only distinctions, or star re-export provenance. A generic "compute each sibling's exported names" promise overstates the source capability. | Inc 4 `scaffold_barrel` bullets and tests; OQ-2 | Fixtures: default-export-only components produce deterministic named aliases or abstain; `export * from`, type-only exports, and duplicate `default` names do not produce blind `export *`. |
| R2-S3 | Architecture | medium | Unify Inc 2 `TargetExistenceSearch` and Inc 3 `ProjectTruthSource` behind one concrete resolver implementation or one adapter contract, and require a parity test showing classifier and rewriter return the same answer for the same specifier/root set. | The plan says Inc 2 owns a narrow interface and Inc 3 is a richer implementation of "the same search," but does not force shared code. Two resolvers can disagree: classifier says `rewritable-path`, rewrite says ambiguous or absent. | §0 Dependency note and Inc 2/Inc 3 boundaries | Parity test: run-012 #4, ambiguous two-`types.ts`, missing CSS cofile, and barrel directory produce identical target-existence facts through the classifier search and rewrite truth source. |

**Endorsements** (prior accepted R1 items this reviewer agrees with):

- R1-S3: Keeping the gate to "0 residual `unresolvable_import`" avoids a misleading PASS claim.
- R1-S9: Path confinement is required; see R2-F3 for the additional realpath/symlink requirement.

#### Review Round R3 — claude-opus-4-8-1m — 2026-06-02 00:20 UTC

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-02 00:20:00 UTC
- **Scope**: Same six R1-fix deltas, **after** R2 (gpt-5.5) filed S1–S3. R2 read first; this round endorses R2 where correct and adds only plan-level gaps R2 missed by reading the actual rewrite/resolver/guard source (`import_path_rename._rewrite_specifier`, `cross_file_imports._resolves_on_disk`, and confirming **no `is_relative_to`/realpath guard exists in `src/startd8/repair/` today**). Not re-litigating R1 (Appendix A) or restating R2's untriaged S1–S3.

**Executive summary (delta to R2):**

- **High:** Inc 5's plan text still says "track each rewrite's (offset,old,new)" — but the step it reuses (`import_path_rename`) rewrites via `str.replace` of the quoted token, so there are **no offsets and replace-all semantics**. R2-S1's pre-image+replay fix is right; the plan must also change the rewrite step to **return its applied substitution set**, or Inc 5 has nothing to replay from.
- **Medium:** Inc 4's path-confinement guard (`_confined_target`) is specified by intent only; confirmed there is **no realpath/`is_relative_to` containment code in the repair tree today**, so this is net-new and must mandate `Path.resolve(strict=False)` **before** the containment test, plus a positive confined-write test (R2-F3 covers the requirement side; the plan increment needs the same).
- **Medium:** Inc 7's #4 fixpoint test should pin the candidate-path set passed into `scan_unresolvable_imports`. `_resolves_on_disk` is `tsconfig`-blind; if the rewrite picks a `tsconfig`-derived `@/` alias that the blind resolver can't see, the second pass flags it — an oscillation the current test plan wouldn't catch.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | Architecture | high | Inc 3/Inc 5: make the rewrite step **return the substitutions it applied** (list of `{specifier, target}`), and have Inc 5 build rollback on that, not on `(offset, old, new)`. `import_path_rename._rewrite_specifier` is `out.replace(q+spec+q, ...)` over the whole file — offset tracking is impossible and a specifier used twice is replaced twice. Re-word the §0 "edit-scoped (track each rewrite's (offset,old,new))" note and the Inc 5 body accordingly (replay kept subset from pre-image, per R2-S1). | The plan's own seam table reuses `import_path_rename`; its rewrite is whole-file token replace. Building Inc 5 against an offset model that the reused primitive cannot produce will fail at integration. R2-S1 fixed the *algorithm*; this fixes the *data the step must hand Inc 5*. | §0 Increment-boundary note; Inc 5 shared-importer scoping; §10 rollback row | Test: rewrite step result exposes applied substitutions; Inc 5 reconstructs final bytes by replaying kept substitutions on the captured pre-image; a doubly-used specifier round-trips correctly. |
| R3-S2 | Security | medium | Inc 4: spell out `_confined_target` as `resolve(strict=False)` on both the candidate write path and `run_root/generated`, then `is_relative_to` — **realpath before containment** — and add a positive test (a normal importer-relative `./X.module.css` write is allowed). There is currently no such guard anywhere in `src/startd8/repair/`, so the plan is introducing it from scratch and must not leave it as "stays under run_root/generated". | Focus item 5: a string-prefix or pre-resolve check is bypassable by `..`/symlinks; an over-eager guard could block legitimate confined writes. Grounded: `grep` finds no `is_relative_to`/containment realpath in the repair tree. | Inc 4 `_confined_target` bullet; §10 confinement row | Tests: `../`-escape → `None`; symlink inside `generated/` pointing out → `None`; sibling `./Step.module.css` → allowed path returned. |
| R3-S3 | Validation | medium | Inc 7: the #4 fixpoint test must pin **which candidate paths** are passed to `scan_unresolvable_imports` on the second pass (generated batch + project root), and assert the chosen rewrite form resolves through the `tsconfig`-blind `_resolves_on_disk` (root + `src/` only). If the rewrite emits a `tsconfig`-`paths` alias the blind resolver can't see, the rewrite must instead emit the relative form. | R2-S2/R2-F2 noted fixpoint risk; the precise, testable lever is the candidate set + the blind resolver. Without pinning it, "re-classifies as resolved" (FR-11) is asserted but not actually exercised against the resolver repair-retry uses. | Inc 7 acceptance harness fixpoint bullet | Two fixtures: (a) `@/*→src/*` tsconfig with target outside `src/` → rewrite picks relative, second pass resolved; (b) no tsconfig, target in generated tree passed as candidate → resolved. |

**Endorsements** (untriaged R2 items this reviewer agrees with — do not re-triage here):

- R2-S1: Pre-image + kept-subset replay is the correct rollback algorithm; R3-S1 supplies the missing data path (the step must return its substitutions, since the primitive is `str.replace`).
- R2-S2: Barrel export-name handling is over-promised vs `extract_ts_exports` (regex; default→`"default"`; can't expand `export *`). Narrow to default-export components with names from the sibling **filename**.
- R2-S3: Unify the classifier search and rewrite resolver — but require a parity predicate, not just shared code (see R3-F3 in the requirements doc: the two query *shapes* differ).

---

## Requirements Coverage Matrix — R2

Focused only on the R1-applied repair-retry deltas.

| Requirement | Plan Step(s) | Coverage | Gaps (R2) |
| ---- | ---- | ---- | ---- |
| FR-3 classifier / TargetExistenceSearch | Inc 2 + Inc 3 | Partial | Interface decoupling exists, but no parity requirement prevents classifier/rewrite resolver divergence (R2-S3/R2-F3). |
| FR-4 broadened rewrite + FR-11 fixpoint | Inc 3 + Inc 7 | Partial | Alias-form rewrite may remain unresolved without `tsconfig` or generated-batch candidate paths (R2-F2). |
| FR-6 barrel scaffold | Inc 4 | Partial | Export computation is over-promised relative to regex extractor limits (R2-S2/R2-F1). |
| FR-7 re-validation/rollback | Inc 5 | Partial | Edit-scoped rollback needs pre-image + kept-subset replay, not raw offset undo (R2-S1/R2-F4). |
| FR-8 targeted regen worklist | Inc 6 | Partial | Worklist schema still conflates feature regen and non-feature cofile/scaffold residue (R2-F5). |
| FR-11 confinement/idempotence | Inc 4 + Inc 7 | Partial | Path confinement must mandate `resolve()`/realpath + symlink handling and include positive confined-write tests (R2-F3). |

#### Review Round R4 — gemini-3.1-pro — 2026-06-02 00:25 UTC

- **Reviewer**: gemini-3.1-pro
- **Date**: 2026-06-02 00:25:00 UTC
- **Scope**: Fresh R4 pass over the repair-retry design and R1-R3 deltas. Grounded against `cli.py`, `cross_file_imports.py`, and `import_path_rename.py`. Focuses on fixpoint coherence, string-replacement blast radius, and re-validation scope.

**Executive summary (delta to R3):**

- **Critical (Fixpoint Failure):** The engine reads a static postmortem. On a second run, the violations are still listed. Since the files are already fixed, the wrong specifier isn't found in the source, the rewrite step abstains (`not_found_in_source`), and the scaffold step skips. If the engine routes these abstains/skips to the `needs-regen` worklist, a fully repaired tree will produce a massive false-positive worklist and exit non-zero, defeating FR-11 fixpoint.
- **High (Over-replacement Corruption):** R3 correctly noted that `_rewrite_specifier` is a global `str.replace`, but missed the blast radius. Replacing `q+spec+q` globally will corrupt any unrelated string literal or comment in the file that happens to match the specifier (e.g., `console.log("Check 'utils'")`). The replacement must be anchored to actual import/require statements.
- **High (Syntax Regressions):** Re-validation (Inc 5) only checks if imports resolve. The naive string-replace rewrite step can break syntax (e.g., overlapping replaces, quoting mismatches). A content-only re-scan will approve a file that resolves the import but breaks the build.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-S1 | Architecture | critical | Add a **live-state pre-filter** to Inc 1 or Inc 6: before classifying a violation from the static report, re-check if the specific specifier is still present and unresolvable in the current file. If it is already resolved or absent, mark it `already_resolved` and exclude it from the worklist. | The postmortem is a static snapshot. Running `--from-run` on an already-repaired tree reads the same violations. `import_path_rename` will abstain ("not_found_in_source") and scaffold will skip. Without a live pre-filter, these skip/abstain outcomes land in the `needs-regen` worklist, breaking fixpoint (FR-11) and exiting non-zero. | Inc 6 step 1 (before dispatch) and Inc 1 | Test: second pass over repaired tree marks all 5 violations `already_resolved` (or drops them); worklist is empty; exit code 0. |
| R4-S2 | Validation | high | Require Inc 5 `revalidate.py` to run `check_syntax` (or `ast.parse` / TS equivalent) on the affected files, rolling back if a *new* syntax error is introduced. | `_rewrite_specifier` is a string replacement. A malformed specifier or quote mismatch could break the AST. A content-only re-scan will approve a file that resolves the import but breaks the build. | Inc 5 `revalidate.py` | Test: a rewrite that breaks syntax (e.g. replacing a string inside another string inadvertently) triggers rollback. |
| R4-S3 | Security | high | Constrain `_rewrite_specifier` to only perform replacements within `import` or `require` AST nodes, or use a stricter regex anchored to `import ... from` / `require(...)`. Do not use a global `out.replace(q+spec+q, ...)`. | A global string replace of `'utils'` to `'@/utils'` will corrupt unrelated strings like `const msg = "Loaded 'utils'";`. This violates the non-destructive requirement (NFR-4/FR-11). | Inc 3 (Rewrite lever) | Test: a file containing the bad specifier in both an import statement and a string literal has only the import statement rewritten. |

**Endorsements** (prior accepted R2/R3 items):
- R3-S1: Returning the applied substitutions instead of tracking offsets is the only way to make rollback work with `str.replace`.
- R2-F5: Splitting feature regen from unscaffolded non-feature assets in the worklist schema is essential to avoid breaking `--task-filter`.

#### Review Round R5 — composer-2.5 — 2026-06-02 01:10 UTC

- **Reviewer**: composer-2.5
- **Date**: 2026-06-02 01:10:00 UTC
- **Scope**: Fresh R5 pass on the R1-fix delta after R1–R4. Read Appendix A/B/C first; requirements v0.5 already merges R4 but plan v1.2 body does not. Grounded against `truth_source.py` (`LiveDiskTruthSource._enumerate_specifiers` walks **only** `lib/`), `import_path_rename._resolve_specifier` (no relative-depth branch), and Inc 6 step 1 (still `classify each` with no live pre-filter). Does not re-litigate triaged R1–R3 items or restate R4 findings except where plan/requirements drift.

**Executive summary:**

- **Critical (plan/requirements drift):** Requirements v0.5 merges R4-F1/F2/F3 (live pre-filter, syntax re-validation, anchored rewrite) but plan Inc 6/5/3 body still omits all three — implementers reading only the plan will ship a broken fixpoint and global `str.replace`.
- **Critical (run-012 #4 unreachable):** Inc 3 promises relative-specifier depth correction, but `LiveDiskTruthSource.resolvable_specifiers()` enumerates **only `@/lib/*`** (`truth_source.py:100-124`) and `_resolve_specifier` has no relative→canonical branch — only seeded negatives, `@/` parent collapse, and nearest-match. `../../../types/wizard` cannot rewrite to `@/components/wizard/types` through the current step.
- **Medium:** Inc 5 mirrors strict-subset rollback but does not define violation identity for diffing rescans; partial repairs can false-trigger rollback.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-S1 | Completeness | critical | **Sync plan body with triaged R4** (requirements v0.5 already has it): Inc 6 step 0 — live-state pre-filter (`already_resolved` before classify/dispatch); Inc 5 — syntax check wired to rollback; Inc 3 — import-anchored rewrite (not global `str.replace`). Update §10 risk rows and Inc 7 fixpoint test to include the second-pass case. | Plan/requirements drift: R4 is ACCEPTED in requirements Appendix A but absent from plan Inc 6 (`load_violations → classify each`), Inc 5 (content-only re-scan), and Inc 3 (still assumes substitution-set replay over an unanchored primitive). | Inc 3, Inc 5, Inc 6 step 0, §10 | Diff plan vs requirements FR-7/FR-11/FR-4 R4 paragraphs; acceptance tests from R4-S1/S2/S3 pass against plan text. |
| R5-S2 | Architecture | critical | Inc 3 must add an explicit **relative-specifier rewrite path** separate from nearest-match: given `(importer_path, bad_spec)`, resolve the intended module via the shared target-existence predicate (Inc 2/3), pick a canonical `@/` or relative form that passes the blind resolver (R3-F2), and apply **only** at import sites (R4-F3). Do **not** rely on `LiveDiskTruthSource.resolvable_specifiers()` lib-only enumeration or `best_match` against `@/lib/*`. | Verified: `truth_source.py:100-124` only walks `lib/`; `_resolve_specifier` (`import_path_rename.py:111-127`) has no branch for `../../../…`. Run-012 #4 is the headline acceptance case and is unreachable without this algorithm. | Inc 3 first paragraph + tests; cross-ref FR-4 | Test: `../../../types/wizard` at `components/wizard/steps/Foo.tsx` rewrites to a blind-resolver-compatible form resolving to `components/wizard/types.ts`; nearest-match against lib-only surface abstains. |
| R5-S3 | Validation | medium | Inc 5 strict-subset rollback must diff **`{source_file, specifier}` multisets**, not raw violation counts or message strings. Define pre-fix and post-fix sets; roll back only when `post − pre` is non-empty (plus new syntax failures per R4-S2). A kept abstained violation must not trigger rollback of a co-located successful rewrite. | Plan says "introduces no *new* `unresolvable_import`" but not how equality is computed. Without a stable key, rescans after partial repair can treat unchanged specifiers as "new" or collapse duplicates. | Inc 5 strict-subset bullet; mirror FR-7 | Test: file with two violations same specifier in one importer — repair one, abstain one — kept repair survives re-validation. |

**Endorsements:**

- R4-S1/F1 (live pre-filter): Sound and critical; requirements merged it but plan body must catch up (R5-S1).
- R3-S3/R3-F2 (fixpoint pinned to blind resolver): Sound; pairs with R5-S2's relative rewrite path.
- R2-S1/R3-S1 (pre-image + substitution-set replay): Sound once R5-S2 supplies a rewrite that actually applies.

---

## Requirements Coverage Matrix — R5

Delta-only; focuses on gaps R1–R4 left open or plan/requirements drift.

| Requirement | Plan Step(s) | Coverage | Gaps (R5) |
| ---- | ---- | ---- | ---- |
| FR-4 rewrite (run-012 #4) | Inc 3 | Partial | Relative rewrite algorithm unspecified vs lib-only `LiveDiskTruthSource` + no relative branch in `_resolve_specifier` (R5-S2/R5-F1). |
| FR-7 strict-subset rollback | Inc 5 | Partial | Violation identity multiset undefined (R5-S3/R5-F2); plan body missing R4 syntax gate (R5-S1). |
| FR-11 fixpoint / live-state | Inc 6 + Inc 7 | Partial | Requirements merged R4-F1; plan Inc 6 still lacks pre-filter (R5-S1/R5-F3). |
| FR-10 artifact paths | Inc 6 + Inc 7 | Partial | Output directory not co-located with run (R5-F3). |

---

## Requirements Coverage Matrix — R4

Focused on fixpoint, validation, and static-vs-live coherence.

| Requirement | Plan Step(s) | Coverage | Gaps (R4) |
| ---- | ---- | ---- | ---- |
| FR-7 Re-validation/rollback | Inc 5 | Partial | Misses syntax validation (R4-S2/R4-F2); does not protect against over-replacement corruption (R4-S3/R4-F3). |
| FR-11 Non-destructive/idempotent | Inc 6 / Inc 7 | Partial | Idempotence is impossible if static postmortem violations are blindly classified into the worklist on a second run (R4-S1/R4-F1). |

## Requirements Coverage Matrix — R3

Delta-only; extends R2 with what grounding in live source (`import_path_rename`, `cross_file_imports`, repair tree) revealed. Analysis only.

| Requirement | Plan Step(s) | Coverage | Gaps (R3, beyond R2) |
| ---- | ---- | ---- | ---- |
| FR-7 re-validation/rollback | Inc 5 | Partial | Reused rewrite primitive is `str.replace` (no offsets, replace-all); Inc 5 must consume the step's **applied substitution set**, not offsets (R3-S1/R3-F1). R2-S1 fixed the algorithm; this fixes the data contract feeding it. |
| FR-11 confinement | Inc 4 | Partial | No realpath/`is_relative_to` guard exists in `src/startd8/repair/` today; plan must mandate `resolve()`-before-containment + a positive confined-write test (R3-S2). |
| FR-4 + FR-11 fixpoint | Inc 3 + Inc 7 | Partial | Resolution is `tsconfig`-blind (`_resolves_on_disk` = root + `src/`), so #4 fixpoint is likely **sound without tsconfig**; the real gap is alias-form selection (tsconfig-driven) vs blind validation — pin candidate set + reject unresolvable alias forms (R3-S3/R3-F2). |
| FR-3 classifier ↔ FR-4 rewrite parity | Inc 2 + Inc 3 | Partial | Beyond R2-S3's "shared code": the two call sites query different shapes (`locations_for(name)` vs `resolvable_specifiers()`); needs a single authoritative "target exists" predicate (R3-F3). |
