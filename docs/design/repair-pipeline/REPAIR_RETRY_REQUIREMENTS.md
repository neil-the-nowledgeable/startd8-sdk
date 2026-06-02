# Repair-Retry — Re-runnable Post-Job Repair Requirements

**Version:** 0.6 (Post-CRP — R1–R5 triaged, 24/24 F-suggestions applied)
**Date:** 2026-06-02
**Status:** Draft for review — pairs with `REPAIR_RETRY_PLAN.md` (v1.4)
**Source incident:** `run-012-20260601T1838` (0.67 / FAIL, 5/15 features, all
`unresolvable_import`). Evidence: `REPAIR_RETRY_RUN012_INVESTIGATION.md`.
**Builds on:** the merged name-repair pipeline (`import_path_rename`,
`content_bridge`, `TruthSource`, `_attempt_content_name_repair`, `run_file_repair`)
and the existing `startd8 repair [FILES]` CLI (REQ-RPL-205, `cli.py:923`).

> **What this is.** A deterministic, **no-LLM** repair pass that can be run **after** a
> prime-contractor job has failed — driven by the run's `prime-postmortem-report.json` plus
> the on-disk generated artifacts — to fix the cross-file contract violations the run already
> detected, re-validate, and emit a disposition report. For violations it cannot fix
> deterministically, it emits a precise **targeted-regen worklist** rather than failing
> silently.

---

## 0. Planning Insights (Self-Reflective Update)

> Changes between v0.1 ("re-run the name-repair pipeline against the failed run's files") and
> v0.2 (after reading run-012's on-disk reality + the existing repair CLI/postmortem code). The
> grounding pass **inverted the primary lever** — a >50% revision; the loop working.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| Re-running the merged name-repair pipeline fixes run-012 | The name-repair `import_path_rename` step would **abstain on all 5** run-012 violations: 4 are *missing-target* (`*.module.css` ×3, barrel `steps/index` ×1 — verified absent across the run dir **and** the project), and the 5th is rewritable only if the resolver is broadened. There is **nothing on disk to rewrite to** for 4 of 5. | **FR-5/FR-6 added:** a **scaffold** repair class (create the missing resolvable target) is the *primary* lever for run-012 — path-rewrite alone fixes 1 of 5. |
| The dominant failure lever is path-rewrite | **4 of 5 are scaffold-the-missing-target**; only **1 of 5** (`../../../types/wizard`) is a wrong path — and its real target (`components/wizard/types.ts`, PI-006, success) exists. | **FR-4 reframed:** rewrite is the *minority* lever and needs the name-repair `TruthSource` **broadened beyond `@/lib/*`** to the whole project surface (else even #4 abstains). |
| Some violations need LLM regeneration | **0 of 5 need regen.** With rewrite + scaffold, every run-012 failure is deterministically fixable with **zero LLM calls** — a 0.67/FAIL could flip to PASS on a pure repair pass. | **FR-8 reframed:** the needs-regen worklist is a **general safety net**, not the run-012 path; run-012 acceptance (FR-12) expects 0 regen. |
| `startd8 repair` is greenfield | It **already exists** (`cli.py:923`, REQ-RPL-205): Python-only, self-discovers issues via `ast.parse` + `ruff`, calls `run_file_repair`. It does **not** read a postmortem, handle TS/content-contract, or do cross-file re-validation. | **FR-1 reframed:** repair-retry is a **new mode** on the existing command (`--from-run`), extending it to report-driven discovery + TS content-contract + scaffold, not a new tool. |
| The postmortem report has the data we need | Confirmed: per-feature `disk_compliance.semantic_issues` carries `category`/`message`/`severity`, and the on-disk `file_path`; plus `target_files`/`generated_files`/`missing_files`. Reliable structured input. | **FR-2 firmed up:** extract directly from `disk_compliance.semantic_issues`; no prose parsing. |

**Resolved open questions:**
- **OQ-A → Scaffold is a first-class repair lever, not out of scope.** Run-012 is unfixable
  without it.
- **OQ-B → Repair-retry is report-driven, not file-list-driven.** The postmortem is the
  authoritative work-list of what failed and where.

Remaining open questions: OQ-1…OQ-6 in §6.

---

## 1. Problem Statement & Gap Table

When a prime-contractor run fails on cross-file contract violations, the only recourse today is
**hand-fix** or **full/`--task-filter` regeneration** (LLM cost + nondeterminism). Yet the run
has already *detected and localized* every violation in `prime-postmortem-report.json`, and —
as run-012 proves — most are **deterministically fixable on disk** (rewrite a wrong path, create
a missing co-file). There is no way to act on that detection without regenerating.

| Run-012 failure | Class | Deterministic fix | Covered today? |
|-----------------|-------|-------------------|----------------|
| PI-012 `../../../types/wizard` | rewritable-path | rewrite → `@/components/wizard/types` (real PI-006 output) | ❌ (name-repair resolver too narrow) |
| PI-007/005/011 `./X.module.css` | missing-cofile | scaffold empty `X.module.css` | ❌ (no scaffold lever) |
| PI-008 `@/components/wizard/steps` | missing-barrel | scaffold `steps/index.ts` re-exporting siblings | ❌ (no scaffold lever) |

**Why repair-retry (vs regen).** Regenerating a feature to fix a missing CSS import is a
$0.10–0.32 LLM call that may re-invent the same or new violations (run-012's PI-008 was the
$0.32 cost outlier). A deterministic scaffold/rewrite is **free, instant, and idempotent**. The
detection already exists; repair-retry closes the loop from *detected* to *fixed*.

---

## 2. Goal

Given a failed run's `prime-postmortem-report.json` and its on-disk generated tree,
deterministically resolve the cross-file contract violations it detected — by rewriting wrong
paths to real on-disk targets and scaffolding missing resolvable targets (empty CSS modules,
barrel indexes) — re-validate, and report per-violation dispositions, emitting a targeted-regen
worklist for anything not deterministically fixable. Zero LLM calls. Re-running is a fixpoint.
(Resolving the imports clears the detected violations; whether the *overall* multi-factor
postmortem score reaches PASS is reported, not guaranteed — R1-F3.)

---

## 3. Functional Requirements

### FR-1 — Run-driven entry mode
Extend the existing `startd8 repair` CLI with `startd8 repair --from-run <PATH>` where `<PATH>`
is a `prime-postmortem-report.json` **or** a run directory containing one. The command loads the
report, selects failed features, and discovers violations from it (vs the existing
`[FILES]`-mode which self-discovers via ast/ruff).

**Mode interaction (R1-S6).** `--from-run` and a positional `[FILES]` are mutually exclusive:
supplying both is a usage error; supplying neither is a usage error (preserves today's
`[FILES]`-required behavior). `--scaffold` is only meaningful with `--from-run`; passing it in
`[FILES]` mode is a usage error. These are defined, not silent.
*Acceptance:* `startd8 repair --from-run <run-012 report>` enumerates exactly the 5
`unresolvable_import` violations with their on-disk `file_path`s; the legacy `[FILES]` mode is
unchanged; `--from-run` + `[FILES]` together → usage error; neither → usage error;
`--scaffold` without `--from-run` → usage error.

### FR-2 — Violation extraction from the postmortem
For each failed feature, read `disk_compliance.semantic_issues` (each carrying
`category`/`message`/`severity`) and the issue's on-disk `file_path`; normalize into a
`RetryViolation{feature_id, file_path, category, specifier, message}`.

**Specifier-parse contract (R1-F1).** The `specifier` is the backtick-quoted token immediately
following `imports` in the structured message
(`` `<file>` imports `<specifier>` which resolves to neither … ``). This grammar is the
load-bearing primitive for the whole pass, so it MUST be pinned by a golden test against the
real run-012 message strings. A message from which **no** specifier can be parsed is **not
dropped** — it is emitted as a `needs-regen` worklist entry with `reason="unparseable_message"`
(NFR-3: never silently lose a detected violation).
*Acceptance:* the 5 violations normalize with the correct `specifier`
(`./StepNav.module.css`, `../../../types/wizard`, `@/components/wizard/steps`, …) and
`file_path`; a malformed/empty message yields a `needs-regen` worklist entry, not a skip.

### FR-3 — Deterministic violation classifier
Classify each `RetryViolation` by a **target-existence search**. The search MUST be fully
specified to be deterministic (NFR-1):
- **Scope & precedence (R1-F2):** search the run's `generated/` tree **first**, then the on-disk
  project tree, **excluding `node_modules`**.
- **Class precedence:** evaluate in order **rewritable-path → scaffoldable-barrel →
  scaffoldable-cofile → needs-regen**; the first match wins (a specifier is tested as a module
  before being treated as a style co-file).
- **Multi-match rule:** if the import's intended module name resolves at **>1** location, it is
  **NOT** rewritable (ambiguous) → `needs-regen` with `reason="ambiguous_target"` (never a
  guessed rewrite). See FR-4.
- **Single "target exists" predicate (R3-F3):** the classifier's ambiguity count and the rewrite
  step's resolvability check MUST be the **same** predicate over the **same** surface. The
  classifier asks `locations_for(module_name)` (name → paths) while the rewriter consumes a
  specifier set — these answer *different questions* and can disagree (a name present once but
  reachable by two specifiers; a specifier that resolves but whose base name also matches an
  unrelated file). Pin one authoritative predicate so the classifier's `rewritable` verdict and
  the rewriter's abstain decision always agree.

Classes:
- **rewritable-path** — the intended target exists on disk at **exactly one** resolvable
  specifier different from the one used (→ FR-4).
- **scaffoldable-barrel** — a `@/…`/relative specifier resolving to a *directory* that exists
  with sibling modules but no `index.{ts,tsx,js}` (→ FR-6).
- **scaffoldable-cofile** — a style/asset specifier (`.module.css`, `.css`, …), relative to the
  importer, whose file is missing (→ FR-5).
- **needs-regen** — none of the above, or ambiguous (→ FR-8).
*Acceptance:* run-012 classifies as `{#4: rewritable-path, #1-3: scaffoldable-cofile, #5:
scaffoldable-barrel}`, 0 needs-regen; a base name resolving in two dirs → `needs-regen`
(`ambiguous_target`); a `.module.css` that also matches a stray file elsewhere stays
`scaffoldable-cofile` (precedence pinned).

### FR-4 — Rewrite lever (broadened resolver + explicit relative-rewrite algorithm)
For `rewritable-path` violations, rewrite the specifier to the real target via the name-repair
`import_path_rename` step.

**The relative-rewrite path does not exist in the merged step today (R5-F1, critical).** Verified:
`LiveDiskTruthSource._enumerate_specifiers` enumerates **only `lib/**`** (`truth_source.py:100-124`),
and `_resolve_specifier` has **no relative-depth branch** — only seeded negatives, `@/` parent
collapse, and nearest-match against the lib-only set. So run-012 #4 (`../../../types/wizard` →
`components/wizard/types.ts`) — the **only** rewrite case — is **currently unreachable**. FR-4
therefore requires, as named work (not a tweak):
1. **Broaden the surface** beyond `@/lib/*` to the project's full resolvable surface (FR-3 shared
   predicate), `tsconfig`-`paths`-driven (R1-S5).
2. **An explicit relative-specifier rewrite algorithm**, separate from nearest-match: given
   `(importer_path, bad_specifier)`, resolve the intended module via the FR-3 predicate, then emit
   a **canonical form that passes the blind resolver** (R3-F2) at **import sites only** (R4-F3) —
   not a `best_match` against the lib-only specifier set.
3. **Sub-namespace collapse** (validated against RUN-013 PI-004): when an importer invents an
   *interior* path segment (`@/lib/export/renderers/markdown` where `@/lib/export/markdown`
   exists), drop one interior segment at a time and take the unique collapsed form that resolves
   on disk. This is the **opposite token shape** from the RUN-012 relocation (there the *real*
   path has the extra segment), so the resolver tries **collapse first, then token-match**.
   *Validated end-to-end:* the implemented `repair/retry` loads the real run-013 report and
   rewrites both invented `renderers` imports deterministically (the postmortem's Tier-1
   direct-fix), with PI-005's TS2322 type error correctly out of scope (0 `unresolvable_import`).

**Abstain on ambiguity (R1-F4).** Broadening the surface materially raises false-rewrite risk:
if the intended module name resolves at **≥2** locations, `import_path_rename` MUST **abstain**
and the violation routes to `needs-regen` (`reason="ambiguous_target"`) — never a guessed
rewrite. This is a first-class, separately-tested behavior, not just a risk note.

**Rewrites MUST be anchored to import/require statements (R4-F3).** The merged
`import_path_rename._rewrite_specifier` does a **global** `str.replace` of the quoted specifier
token — so a specifier that also appears in an unrelated string literal or comment (e.g.
`console.log("Check '@/lib/x'")`) would be corrupted, violating non-destructiveness. The rewrite
MUST replace the specifier **only within `import … from '…'` / `require('…')` / `export … from
'…'` positions**, not globally. (This also fixes a latent bug in the merged name-repair step.)
*Acceptance (added):* a file containing the bad specifier in **both** an import statement **and** a
string literal has **only** the import rewritten; the string literal is untouched.

**Alias-form selection must agree with the (tsconfig-blind) resolver (R3-F2).** Re-validation
resolves via `_resolves_on_disk`/`resolve_specifier_to_paths`, which are **`tsconfig`-blind**
(`@/` is tried against the project root and `src/` **only**, ignoring `tsconfig` `paths`). So the
rewrite MUST select a form that **this blind resolver** will resolve: choose the `@/…` alias only
when it resolves under the root/`src` convention; otherwise emit the **relative** form. Never emit
a `tsconfig`-`paths` alias that repair-retry's own re-scan (or a stricter real `tsc`) would not
resolve. (Consequence: the #4 fixpoint holds **without** any `tsconfig`.)
*Acceptance:* PI-012's `../../../types/wizard` rewrites to a form that **resolves under the blind
resolver** to `components/wizard/types.ts`; a project with two name-matching `types.ts` under
different dirs → **abstain**; a `tsconfig` aliasing `@/* → src/*` with the target **outside**
`src/` → the rewrite picks the **relative** form (the `@/` alias would not resolve blind).
**Negative control (R5-F1):** the **lib-only** nearest-match path **abstains** on
`../../../types/wizard` — i.e. #4 is fixed by the new relative-rewrite algorithm, not by the
existing `@/lib/*` `best_match` (proving the algorithm, not an accident of the lib surface).

### FR-5 — Scaffold lever: missing style co-file
For `scaffoldable-cofile`, create the missing target file (e.g. an **empty** `X.module.css`) at
the path the importer expects, **only if absent** and **only if the resolved write path is
confined within the run's `generated/` root** (R1-F10 — a specifier escaping via `../` must
refuse the write and route to `needs-regen`; the very failure class being repaired is the attack
surface). The import then resolves and the component compiles; styling is intentionally deferred.
Gated behind `--scaffold` (OQ-1).

**Scaffolds are tracked, never silent (R1-F5).** Every scaffolded file is recorded as a
machine-enumerable `deferred` entry in the report (FR-10) so a scaffold is not a silent
acceptance of a missing-styling gap (NFR-3 binds cofiles too, not just `needs-regen`).
*Acceptance:* PI-007/005/011 each get an empty `*.module.css` co-file; the `unresolvable_import`
clears on re-scan; existing files are never overwritten; the report's `deferred` array lists each
scaffolded path (count == files created); a `../`-escaping specifier writes nothing → `needs-regen`.

### FR-6 — Scaffold lever: barrel index
For `scaffoldable-barrel`, generate an `index.ts` in the imported directory that re-exports the
sibling modules already on disk there (deterministically from the file list), **only if absent**.

**The generated barrel must itself be valid (R1-F6).** Re-validation (FR-7) MUST re-scan the
**generated `index.ts`**, not only the original importer.

**Bounded to what the extractor can soundly prove (R2-F1).** Export-name computation reuses the
**regex** `upstream_interface.extract_ts_exports`, which collapses every `export default` to the
literal `"default"` and cannot expand `export *`/type-only re-exports into a name list. So v1
barrel generation is **narrowed to default-export component siblings**, taking the re-export name
from the **sibling filename** (e.g. `StepNav.tsx → export { default as StepNav } from './StepNav'`).
On a sibling the extractor can't soundly name (anonymous default + non-matching filename,
`export *`-only, type-only), the generator **abstains on that sibling** (logs it) rather than
guessing — never a blind `export *`. A name collision across siblings → abstain on the colliding
name.
*Acceptance:* PI-008's `@/components/wizard/steps` resolves after a generated `steps/index.ts`
with `export { default as <Name> } from './<Name>'` per default-export `*Step.tsx`; fixtures for
anonymous-default / `export * from` / `export type { X }` each yield a deterministic barrel **or**
an abstain-with-reason — never a colliding `export *`.

### FR-7 — Re-validation (strict-subset, reused semantics)
After applying rewrites/scaffolds, re-run the content scans (`scan_unresolvable_imports`, etc.)
over the **affected files and any artifacts generated** (the new `index.ts`/scaffolded files,
R1-F6), **plus a syntax check** (R4-F2). A violation is **resolved** iff its target now resolves;
a fix is rolled back if it introduces a *new* content violation **or a new syntax error** — a
string-based rewrite can break a quote/brace, and a content-only re-scan would falsely accept a
syntactically-broken file. The strict-subset rule from `_attempt_content_name_repair` (which
already pairs content + `check_syntax`) is reused.

**Violation identity (R5-F2).** "New violation" is computed over a stable key — the
**`{source_file, specifier}` multiset**. A fix is rolled back only when
`post_repair_violations − pre_repair_violations` (by that key) is non-empty (or a new syntax
error). An *unchanged* specifier (e.g. a co-located abstained violation that legitimately remains)
does **not** count as "new" and must not trigger rollback of a successful co-located rewrite.

**Shared-importer scoping — pre-image + kept-subset replay (R2-F4 + R3-F1).** The reused rewrite
primitive (`import_path_rename._rewrite_specifier`) is a **whole-file `str.replace` of the quoted
specifier token** (replace-all, **no offsets**) — so an `(offset, old, new)` edit-scoped undo is
**undefinable** (there are no spans, and one specifier used twice — e.g. an `import` and an
`export … from` — is replaced in both places by a single `replace`). Therefore: (a) the rewrite
step MUST **return the set of `{specifier → target}` substitutions it applied** (not offsets); and
(b) partial rollback is defined as **capturing the importer's pre-image, then re-applying only the
*kept* substitutions to that pre-image** — never an offset undo. When one importer hosts ≥2 fixes,
apply all, re-validate once, and reconstruct from the pre-image with the kept subset so a kept fix
is never clobbered by a co-located rolled-back one.
*Acceptance:* after repair, re-scan (including generated artifacts) reports 0 of the original 5
`unresolvable_import`s and no new content-contract violation; a file importing `'../x'` **twice**
(import + `export … from`) round-trips correctly; a file with one kept rewrite + one rolled-back
fix equals `pre-image + kept substitution only` (not an offset-corrupted hybrid, not a wholesale
byte revert).

### FR-8 — Targeted-regen worklist for the residue
Violations classified `needs-regen` (or whose deterministic fix rolled back) are emitted as a
structured worklist. **Two residue dispositions (R1-F7 + R2-F5)** — a `.module.css` is *not* a
Prime feature, so don't pretend `--task-filter` can regenerate one:
- **`needs_regen_feature`** — a feature-level invention (ambiguous/absent module). Schema
  `{feature_id, importer_file, missing_target, reason, task_filter_token}`; `task_filter_token` is
  the exact token the prime-contractor `--task-filter` parser consumes (round-trip-tested).
- **`unscaffolded_asset`** — a non-feature co-file left missing (`--no-scaffold`, a rolled-back
  scaffold, or a confinement refusal). Schema `{owning_feature_id, importer_file, missing_target,
  reason}` with **no** `task_filter_token` (regen of the *owning feature*, or manual authoring, is
  the remedy — not a CSS task filter).
Never a silent pass.
*Acceptance:* a `--no-scaffold` missing CSS yields an `unscaffolded_asset` entry with the owning
feature/importer and **no** bogus CSS `task_filter_token`; a truly ambiguous module yields a
`needs_regen_feature` whose token round-trips through the existing `--task-filter` parser; run-012
(`--scaffold`) produces an **empty** worklist (all 5 fixed).

### FR-9 — Deterministic, no LLM
The entire repair-retry pass makes **zero** LLM/network calls. Same run state → same edits.
*Acceptance:* the pass runs with no API keys configured and produces identical output across two
runs.

### FR-10 — Disposition report
Emit `repair-retry-report.json` (+ a human `repair-retry-summary.md`): per-violation disposition
(`rewritten`/`scaffolded`/`rolled_back`/`needs_regen`) with from/to or created-path; a `deferred`
array enumerating every scaffolded path (FR-5); and an aggregate `resolution` verdict
(`"N/M unresolvable_import resolved"`). **The report MUST NOT claim "would PASS" (R1-F3):** the
postmortem score is multi-factor and repair-retry only re-validates `unresolvable_import`. The
recomputed score MAY be recorded for visibility, explicitly labeled *not asserted*.

**Artifact location (R5-F3).** All three artifacts MUST be written **under the resolved run
directory** (e.g. `<run>/plan-ingestion/repair-retry/`, beside `prime-postmortem-report.json`) —
**never** the process cwd (which breaks cap-dev-pipe and multi-run workspaces). The R1-S10 stdout
contract prints their **absolute** paths, stable across invocations from any cwd. (Resolves the
report-placement half of OQ-5/OQ-6.)
*Acceptance:* run-012's report lists 1 `rewritten` + 4 `scaffolded`, 0 residue, resolution
"5/5 resolved"; no `would_pass: true` field is emitted; artifacts land **under the run dir** and
the printed paths are absolute and identical when invoked from two different cwds.

### FR-11 — Non-destructive, confined & idempotent (live-state-aware)
Scaffolds only **create missing** files (never overwrite); writes are **confined within the run's
`generated/` root** (R1-F10); rewrites pass the existing non-destructive guard.

**Live-state pre-filter — the postmortem is a STATIC snapshot (R4-F1, critical).** The
`prime-postmortem-report.json` is generated *before* repair, so a second `--from-run` pass re-reads
the **same** 5 violations even though the tree is already fixed — the rewrite then abstains
(`not_found_in_source`) and scaffolds skip (file present). Without a guard, those
abstains/skips would flood the `needs-regen` worklist and exit non-zero, **defeating the
fixpoint**. Therefore, **before classifying** each report violation, repair-retry MUST re-check it
against the **current on-disk state**: if the specifier is already resolved (or absent from the
importer), mark it `already_resolved` and **exclude it from the worklist** — it is neither
repaired-again nor regen-listed. The static report is a *candidate* list, validated against live
disk before action.
*Acceptance:* a second `--from-run` pass over the repaired tree marks all 5 as `already_resolved`,
produces an **empty** worklist, makes no file changes, and **exits 0**; the run-012 rewrite (#4) is
not re-rewritten; no existing file is modified by scaffolding.

### FR-12 — Run-012 acceptance gate (headline)
A reproduction over a **checked-in fixture derived from the real run-012 report + generated tree**
(R1-F9 — the fixture's 5 specifiers/`file_path`s asserted byte-for-byte against the investigation
doc §2 table, with a provenance note linking the run id; guards the gate against silently drifting
from the real incident) resolves all 5 violations (1 rewrite + 4 scaffold), 0 needs-regen, **with
zero LLM calls**. The gate asserts **0 residual `unresolvable_import` on re-scan** — **not** that
the overall postmortem flips to PASS (the score is multi-factor; FR-7 re-validates only
`unresolvable_import`). The recomputed score is recorded but not gated. A baseline (`--from-run`
without `--scaffold`) repairs only #4 and lists the 4 cofile/barrel cases as actionable, proving
the scaffold gate's effect.

---

## 4. Non-Functional Requirements

- **NFR-1 Deterministic.** No LLM/network; reproducible.
- **NFR-2 Reuse-not-rebuild.** Build on the merged name-repair pipeline + the existing `startd8
  repair` CLI + `run_file_repair`; add the report-driven discovery, classifier, and scaffold
  levers — don't re-implement detection or routing.
- **NFR-3 Abstain/worklist-safe.** When a violation isn't deterministically fixable, emit a regen
  worklist entry — never a silent pass and never a guessed file.
- **NFR-4 No-overwrite + realpath-confinement.** Scaffolding creates only missing files; never clobbers existing content. **All** scaffold/rewrite write paths MUST resolve **within the run's `generated/` root**. The containment check MUST normalize first: `Path.resolve(strict=False)` on **both** the candidate write path and `run_root/generated`, **then** `is_relative_to` (R2-F3/R3-S2) — a string-prefix or pre-resolve check is bypassable by `../` or a symlink escaping the tree. A specifier that escapes (the exact run-012 bug class) refuses the write and routes to residue; a legitimate importer-relative `./X.module.css` beside the importer is **allowed**. No realpath/containment guard exists in `src/startd8/repair/` today — this is net-new.
- **NFR-5 TS/Next-first, extensible.** v1 targets the TS + CSS-module + barrel surface run-012
  failed on; the classifier/scaffold abstraction extends to other ecosystems without rework.
- **NFR-6 Report-source-stable.** Consumes `disk_compliance.semantic_issues` as-is; no change to
  how the postmortem is produced.

---

## 5. Non-Requirements (v1)

- **Not** LLM regeneration (that's the `--task-filter` path FR-8 hands off to).
- **Not** *styling* the scaffolded CSS — an empty, valid `*.module.css` that unblocks compile is
  the deliverable; visual styling is a separate human/LLM task.
- **Not** fixing logic/type errors, missing dependencies, or non-`unresolvable_import` classes in
  v1 (the classifier may tag them `needs-regen`).
- **Not** prevention (that's Approach A / richer specs) — repair-retry is the after-the-fact net.
- **Not** interactive (consistent with the rejected REQ-RPL R4-S2); batch + report only.
- **Not** auto-merging the repaired tree into the project — repair-retry fixes the run's
  generated artifacts in place; promotion stays with the existing pipeline.

---

## 6. Open Questions

- **OQ-1 — Scaffold default.** On-by-default or `--scaffold` opt-in? Empty CSS unblocks compile
  but leaves components unstyled; a barrel index is higher-confidence. *(Lean: `--scaffold`
  opt-in for cofiles, barrel on by default — barrel is unambiguous.)*
- **OQ-2 — Barrel re-export heuristic.** Re-export *all* sibling modules, or only those the
  importer references? *(Lean: all default-exported sibling components; log what was included.)*
- **OQ-3 — Rewrite specifier form.** Prefer the `@/…` alias (if `tsconfig` `paths` covers it) or
  a relative path? *(Lean: alias when available — matches the project's dominant style.)*
- **OQ-4 — cap-dev-pipe wiring.** A `run-prime-contractor.sh --repair-retry <run>` entry, or
  CLI-only for v1? *(Plan to resolve.)*
- **OQ-5 — Where repair-retry writes.** In-place in the run's `generated/` tree (simple,
  idempotent) vs a copy. *(Lean: in-place.)*
- **OQ-6 — Verdict surface.** Does repair-retry update the postmortem / verification-ledger, or
  emit only its own `repair-retry-report.json`? *(Lean: own report in v1; ledger integration
  later — pairs with RUN-011 Gap D.)*

---

## 7. Relationship to the roadmap

- **Closes the loop** from the postmortem's *detection* (Approach B classifiers) to deterministic
  *repair*, without regen — complements the in-pipeline name-repair seam (which acts pre-merge,
  during the run) by adding an **after-the-run** path.
- **Generalizes** the name-repair `TruthSource`/`import_path_rename` (FR-4 broadening) and adds a
  new **scaffold** repair class the in-pipeline path can later adopt too.
- **Feeds** the `--task-filter` regen path (FR-8) for the genuine residue.
- **Pairs with** the verification-ledger consolidation (RUN-011 Gap D) for a single post-repair
  verdict (OQ-6).

---

*v0.2 — Post-planning self-reflective update: primary lever inverted from path-rewrite to
**scaffold-the-missing-target** (run-012 is 4/5 scaffold, 1/5 rewrite, 0 regen, verified on
disk); repair-retry reframed as a `--from-run` mode on the existing `startd8 repair` CLI; resolver
broadening (FR-4) named as the precondition for the one rewritable case.*

*v0.3 — Post-CRP R1 (dual-document review by claude-opus-4-8-1m). All 10 F-suggestions applied.
Headline catch: the "0.67/FAIL → PASS" framing was an unprovable acceptance criterion (the score
is multi-factor; repair-retry only re-validates `unresolvable_import`) — FR-12/FR-10/Goal now
assert "imports cleared," with the recomputed score recorded-not-gated. Also hardened: the
specifier-parse contract (don't silently drop), classifier scope/precedence/ambiguity, scaffold
path-confinement, generated-barrel validity, shared-importer edit-scoped rollback, worklist
schema, and a provenance-pinned run-012 fixture. Dispositions in Appendix A. Pairs with
`REPAIR_RETRY_PLAN.md` v1.1.*

*v0.4 — Post-CRP R2 (gpt-5.5) + R3 (claude-opus-4-8-1m), focused on the R1-fix delta. 8
F-suggestions applied, grounded in live source. Headline: FR-7's edit-scoped `(offset,old,new)`
rollback referenced a primitive that doesn't exist — `import_path_rename._rewrite_specifier` is a
whole-file `str.replace`, so rollback is now **pre-image + kept-substitution replay** and the
rewrite step returns its substitution set. Also corrected: barrel generation narrowed to what the
regex extractor can prove (R2-F1); alias-vs-relative selection reconciled with the `tsconfig`-blind
resolver (R3-F2); realpath-before-containment (R2-F3/R3-S2); residue split feature-regen vs
non-feature asset (R2-F5); and a single shared "target exists" predicate (R3-F3). Each round found
defects in the *prior round's fix* — the multi-round/multi-model arc earning its keep. Pairs with
`REPAIR_RETRY_PLAN.md` v1.2.*

*v0.5 — Post-CRP R4 (gemini-3.1-pro, a third reviewer model). 3 new F-suggestions applied. Headline
(R4-F1, critical): the postmortem is a **static snapshot**, so the claimed fixpoint was actually
unachievable — a second `--from-run` would re-read the same violations, abstain, and flood the
worklist. FR-11 now mandates a **live-state pre-filter** (validate each report violation against
current disk; `already_resolved` → excluded). Also: syntax re-validation (R4-F2) and
import-anchored rewrites instead of global `str.replace` (R4-F3, which also fixes a latent merged
name-repair bug). Four rounds / three models; each found a real defect the last missed. Pairs with
`REPAIR_RETRY_PLAN.md` v1.3.*

*v0.6 — Post-CRP R5 (composer-2.5, a fourth reviewer model). 3 new F-suggestions applied. Headline
(R5-F1, critical): the **relative-specifier rewrite path does not exist** in the merged step
(`truth_source` enumerates only `lib/`; `_resolve_specifier` has no relative branch), so run-012
#4 — the one rewrite case — is currently unreachable; FR-4 now names the broadened surface + an
explicit relative-rewrite algorithm. Also: violation-identity multiset for strict-subset (R5-F2)
and run-dir-co-located artifacts (R5-F3). Five rounds / four models. Pairs with
`REPAIR_RETRY_PLAN.md` v1.4.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

> Append-only convergent-review state. New reviewers add a round to **Appendix C**, then
> dispositions are recorded in **Appendix A** (applied) or **Appendix B** (rejected).
> Reviewers: scan A/B/C first and do **not** re-propose settled or rejected items.

### Appendix A: Applied Suggestions

**R1 triage (2026-06-01, orchestrator: claude-opus-4-8-1m).** All 10 F-suggestions ACCEPTED.
The headline (R1-F3) was verified against the postmortem score model before acceptance.

| ID | Disposition | Where merged |
| -- | ----------- | ------------ |
| R1-F1 | ACCEPTED | FR-2 — specifier-parse grammar pinned (golden test); unparseable → `needs-regen` worklist, not dropped. |
| R1-F2 | ACCEPTED | FR-3 — search scope/precedence + class precedence + multi-match → `ambiguous_target` defined. |
| R1-F3 | ACCEPTED | FR-12 + FR-10 + Goal §2 — "would PASS" removed; gate asserts 0 residual `unresolvable_import`, score recorded-not-gated. **The headline catch.** |
| R1-F4 | ACCEPTED | FR-4 — abstain-on-ambiguous as a first-class, separately-tested behavior. |
| R1-F5 | ACCEPTED | FR-5 + FR-10 — scaffolds recorded in a `deferred` array; cofiles bound by NFR-3. |
| R1-F6 | ACCEPTED | FR-6 + FR-7 — generated barrel re-validated; named re-exports / abstain on export collision. |
| R1-F7 | ACCEPTED | FR-8 — worklist schema pinned (`importer_file` vs `missing_target` disambiguated; `task_filter_token`). |
| R1-F8 | ACCEPTED | FR-7 — shared-importer edit-scoped rollback (kept fix not clobbered). |
| R1-F9 | ACCEPTED | FR-12 — checked-in fixture from the real report, specifiers asserted byte-for-byte + provenance. |
| R1-F10 | ACCEPTED | NFR-4 + FR-5 + FR-11 — path-confinement invariant (no `../` escape → `needs-regen`). |

**R2 triage (gpt-5.5) + R3 triage (claude-opus-4-8-1m) — focused on the R1-fix delta.** Both
rounds existed untriaged (R2 added externally, R3 by the focused run endorsing/grounding R2); 8
F-suggestions ACCEPTED, merged together (R3 as the authoritative grounding where it refines R2).
The headline (R3-F1) was verified against `import_path_rename._rewrite_specifier` (a whole-file
`str.replace`) before acceptance.

| ID | Disposition | Where merged |
| -- | ----------- | ------------ |
| R2-F4 + R3-F1 | ACCEPTED | FR-7 — rollback is **pre-image + kept-subset replay**; the rewrite step returns its `{specifier→target}` substitution set (no offsets — the primitive is `str.replace`). **The headline catch.** |
| R2-F1 | ACCEPTED | FR-6 — barrel narrowed to default-export components named from the **filename**; abstain on what the regex `extract_ts_exports` can't soundly name. |
| R2-F2 + R3-F2 | ACCEPTED | FR-4 — alias-form selection must agree with the **`tsconfig`-blind** resolver (prefer relative when the `@/` alias wouldn't resolve blind); fixpoint holds without `tsconfig`. R2-F2's two-fixture test folded into R3-F2. |
| R2-F3 + R3-S2 | ACCEPTED | NFR-4 — realpath (`resolve()`) **before** containment (`is_relative_to`) + symlink handling + positive confined-write case. |
| R2-F5 | ACCEPTED | FR-8 — residue split into `needs_regen_feature` (with token) vs `unscaffolded_asset` (non-feature cofile, no token). |
| R3-F3 | ACCEPTED | FR-3 — a single authoritative "target exists" predicate shared by the classifier's count and the rewriter's resolvability (the two query shapes must agree). |

**R4 triage (gemini-3.1-pro) — fresh third-model pass.** All 3 F-suggestions ACCEPTED; each a
**new** issue R1–R3 missed. R4-F3 verified against the merged `_rewrite_specifier` (global
`str.replace`) before acceptance.

| ID | Disposition | Where merged |
| -- | ----------- | ------------ |
| R4-F1 | ACCEPTED | FR-11 — **live-state pre-filter**: the static postmortem is validated against current disk before action; already-fixed violations → `already_resolved`, excluded from the worklist. Without it the fixpoint was unachievable (second pass would flood the worklist). **Critical, new.** |
| R4-F2 | ACCEPTED | FR-7 — re-validation now includes a **syntax check**; a rewrite that resolves the import but breaks syntax is rolled back. |
| R4-F3 | ACCEPTED | FR-4 — rewrites **anchored to import/require/export-from positions**, not a global `str.replace` (which would corrupt a matching string literal). Also fixes a latent bug in the merged name-repair step. |

**R5 triage (composer-2.5) — fourth reviewer model.** All 3 F-suggestions ACCEPTED; R5-F1 verified
against `truth_source.py:100-124` (lib-only) + `_resolve_specifier` (no relative branch).

| ID | Disposition | Where merged |
| -- | ----------- | ------------ |
| R5-F1 | ACCEPTED | FR-4 — the relative-rewrite path **does not exist** in the merged step (lib-only enumeration, no relative branch), so run-012 #4 is currently unreachable; FR-4 now names the broadened surface + an explicit relative-rewrite algorithm + a lib-only-abstains negative control. **Critical, new.** |
| R5-F2 | ACCEPTED | FR-7 — violation identity = `{source_file, specifier}` multiset; rollback iff `post − pre` non-empty (or new syntax); an unchanged co-located abstain doesn't trigger rollback. |
| R5-F3 | ACCEPTED | FR-10 — artifacts written **under the run dir** (`<run>/plan-ingestion/repair-retry/`), absolute stable paths, never cwd. |

### Appendix B: Rejected Suggestions (with Rationale)
_None yet._

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-01

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-01 20:10:00 UTC
- **Scope**: Requirements review (F-prefix) — testability/traceability of FR-1..FR-12 and NFRs; adversarial probe of the classifier target-existence search, broadened-resolver ambiguity, scaffold safety/rollback, the specifier-parsing contract, and the run-012 "0 needs-regen → would PASS" claim.

**Executive summary (top requirement gaps):**

- FR-2's `specifier` extraction is the load-bearing primitive for the whole pass, yet it is specified only as "parsed from the structured message" with no message grammar, no malformed-message behavior, and no failure disposition — an untestable contract for the one thing every downstream FR depends on.
- FR-3's "target-existence search" is asserted, never defined: no search-scope precedence (run batch vs project tree), no tie-break when a base name exists in *multiple* locations, and no rule for the classifier→class precedence order (a `.module.css` that also exists elsewhere could match two classes).
- FR-12's headline claim "verdict flips from FAIL to resolved" conflates *import-resolvable* with *PASS*; the postmortem score (0.67) is multi-factor, so resolving 5 imports does not provably yield PASS — the acceptance criterion overstates what re-validation proves (FR-7 only re-scans `unresolvable_import`).
- FR-4 broadening lacks an ambiguity acceptance criterion: "enumerate the project's full resolvable surface" with a base-name match (`types`) invites multiple candidates and a wrong rewrite; there is no required negative test for abstain-on-ambiguous.
- FR-5 scaffolding an empty CSS module masks a genuine missing-styling gap; the requirement asserts "an empty CSS module is valid" but has no acceptance criterion that the scaffolded gap is *tracked* (worklist/report flag) so it is not silently lost (NFR-3 "never a silent pass" is violated in spirit for cofiles).
- FR-6/OQ-2 barrel re-export `export *` of all siblings can produce *name collisions / ambiguous re-exports* that themselves fail TS compile; the acceptance only checks the barrel import resolves, not that the generated barrel is itself valid.
- FR-7 rollback granularity is ambiguous: if two violations touch the same importer file, the per-file pre-image restore for one rolled-back fix can clobber a kept fix in the same file — no acceptance for interacting fixes on a shared file.
- FR-11 idempotence acceptance ("second pass is a no-op") is necessary but insufficient: it does not test that a *rewrite* is idempotent (the rewritten specifier must re-classify as resolved, not re-trigger), only that scaffolds are not re-created.

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Interfaces | high | Specify the FR-2 specifier-parse contract explicitly: give the message grammar (the backtick-quoted token after `imports`), and require that a message from which no specifier can be parsed is **not** dropped but emitted as a `needs-regen` worklist entry with `reason="unparseable_message"`. | "Parsed from the structured message" is untestable and silently lossy; a schema drift in the message format would make violations vanish, violating NFR-3 and NFR-6's defensive intent. | FR-2, after the `specifier` sentence | Unit test: a malformed/empty message yields a worklist entry, not a skipped violation; a golden test pins the exact run-012 message strings → expected specifiers. |
| R1-F2 | Data | high | Define FR-3's target-existence search precisely: (a) search scope and precedence (run `generated/` tree first, then project tree, excluding `node_modules`), (b) the class-precedence order when more than one class could match, (c) the rule that a base-name match found in **>1** location does **not** classify as rewritable (→ needs-regen). | The classifier is the routing brain; "target-existence search over the run's generated batch + project surface" leaves scope, precedence, and multi-match undefined, so two implementers (or two runs) could classify differently — non-deterministic in spirit (contradicts NFR-1). | FR-3, replacing the bare bullet list intro | Unit tests: a specifier whose base name exists in two dirs → needs-regen; a `.module.css` that also matches a stray file elsewhere stays cofile (precedence pinned). |
| R1-F3 | Validation | high | Weaken/qualify FR-12's headline: change "the re-validation verdict flips from FAIL to resolved" to "all 5 `unresolvable_import` violations clear on re-scan (FR-7); whether the overall postmortem flips to PASS is reported but **not asserted**, since the score is multi-factor." Add an explicit acceptance that re-validation only covers `unresolvable_import`. | The 0.67 score is composite; resolving imports may not lift it to PASS. Claiming a PASS flip is an unprovable acceptance criterion and sets a false success bar. The investigation doc says "*could* become a PASS" (conditional) — the requirement hardened it to a guarantee. | FR-12 acceptance sentence; Goal §2 last sentence | Test asserts 0 residual `unresolvable_import`; a separate (non-gating) assertion records the recomputed score without requiring PASS. |
| R1-F4 | Risks | high | Add an FR-4 acceptance for **abstain-on-ambiguous**: when the broadened resolver finds the intended module name at two or more resolvable locations, the rewrite must abstain and the violation routes to `needs-regen`, never a guessed rewrite. | FR-4 broadens the surface "to the whole project" which materially raises false-rewrite risk (named in plan §10) but the requirement has no negative acceptance — only the happy-path PI-012 case. Without it, the broadening's headline risk is untested. | FR-4, new acceptance bullet | Unit test: two `types.ts` under different dirs both name-match → import_path_rename abstains; violation appears in worklist with `reason="ambiguous_target"`. |
| R1-F5 | Risks | medium | FR-5/NFR-3: require that every scaffolded cofile/barrel is recorded as a tracked "deferred" item (in the report **and**, for cofiles, optionally the worklist) so a scaffold is never a silent acceptance of a missing-styling gap. State the acceptance that the report's `scaffolded` entries are machine-enumerable for follow-up. | Scaffolding an empty CSS module trades a hard failure for a silent styling gap; "an empty CSS module is valid" is true for *compile* but the design must not lose the gap. NFR-3's "never a silent pass" should bind cofiles too, not just needs-regen. | FR-5; cross-link NFR-3 | Test: report lists each scaffolded path under a `deferred_styling`/`scaffolded` array; an assertion that the count matches files created. |
| R1-F6 | Validation | medium | FR-6: add an acceptance that the **generated barrel itself is valid** (re-validation re-scans the new `index.ts`, not just the original importer), and define the OQ-2 collision rule: if two siblings export the same name, abstain on that name (or emit named re-exports) rather than `export *`-colliding. | FR-7 re-validates "affected files" but FR-6's acceptance only checks the original import resolves; a barrel that itself fails to compile (duplicate `export *` names) would pass the stated criterion yet break the build. | FR-6 acceptance; OQ-2 | Test: two siblings exporting `default`/same symbol → barrel uses named re-exports or abstains; re-scan includes the generated `index.ts`. |
| R1-F7 | Interfaces | medium | FR-8: pin the worklist schema and the `target_files` semantics — for a `needs-regen` import, is `target_files` the *importer* file or the *missing target*? Specify which, and require the `--task-filter` token format that the prime-contractor regen path actually consumes. | FR-8 says `{feature_id, target_files, reason}` "consumable by `--task-filter`" but doesn't define whether `target_files` is the thing to regen or the thing that imports it, nor the filter token — making the hand-off untestable end-to-end. | FR-8 | Test: a synthetic needs-regen produces a worklist whose `feature_id`+filter token is accepted by the existing `--task-filter` parser (assert round-trip). |
| R1-F8 | Risks | medium | FR-7/FR-11: add an acceptance for **multiple violations in the same importer file** — define that fixes to one file are applied and re-validated together (not independently rolled back), so a kept rewrite is not clobbered by rolling back a co-located fix. | Per-file pre-image rollback is unsafe when one file hosts two fixes; the requirement's "per-file pre-image" wording assumes one fix per file, which run-012 may not honor (a component importing both a missing CSS and a wrong path). | FR-7 rollback clause | Test: a synthetic file with one valid rewrite + one rolled-back fix retains the valid rewrite (file is not byte-reverted wholesale). |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F9 | Validation | high | Add a requirement that run-012 acceptance is driven by a **checked-in fixture derived from the real report+tree**, with a provenance note, and that the fixture's 5 specifiers/file_paths are asserted byte-for-byte — guarding against the acceptance silently drifting from the real incident it claims to reproduce. | FR-12 is the headline gate but the source incident lives in an external run dir that may be GC'd; if the fixture is hand-edited the "would PASS" claim becomes self-referential. Pin it to the investigation doc's §2 table. | FR-12; new NFR or acceptance note | Test: fixture specifiers == investigation §2 table; a provenance comment links the run id. |
| R1-F10 | Security | low | NFR-4/FR-11: state the path-confinement invariant explicitly — scaffolds and rewrites may only write **within the run's `generated/` tree**, never escape via a `../` specifier (a malicious/garbled `../../../../etc/...` specifier must not cause a write outside the run root). | Scaffold paths are computed from importer-relative specifiers that themselves contain `../` (the very bug class run-012 hit, e.g. `../../../types/wizard`); without a confinement check, scaffold_cofile could write outside the tree. | NFR-4; FR-5 acceptance | Test: a specifier resolving outside the run root is refused (no file created) and routed to needs-regen. |

#### Review Round R2 — gpt-5.5 — 2026-06-02 00:17 UTC

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-02 00:17:00 UTC
- **Scope**: Focused R2 requirements review of R1-applied repair-retry fixes only: edit-scoped rollback, barrel export computation, worklist schema, rewrite fixpoint, path confinement, and TargetExistenceSearch/ProjectTruthSource coherence. R1 accepted items are not re-litigated.

**Executive summary:**

- **High:** FR-7's edit-scoped rollback does not define a safe algorithm after multiple edits shift offsets in the same importer.
- **High:** FR-6 over-promises barrel export-name computation relative to the existing regex-based export extractor.
- **Medium:** FR-11's #4 rewrite fixpoint depends on alias resolution and candidate-path scope that are not guaranteed when the run dir lacks `tsconfig`.
- **Medium:** FR-8 worklist schema should distinguish feature-level regeneration from non-feature scaffold/cofile residue.
- **Endorsement:** R1-F3's "imports cleared, not PASS" correction remains the right end-user claim.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Validation | high | Narrow FR-6 barrel export collision requirements to deterministic cases supported by the current extractor, or require a TypeScript-aware extractor. Today the cited helper (`upstream_interface.extract_ts_exports`) is regex-based, collapses any `export default` to `"default"`, and has limited understanding of star/type-only re-exports. | The requirement says "compute each sibling's exported names; on collision emit named re-exports or abstain." That is only safe if export-name computation is sound. For default-export React components, the usable re-export name may come from filename, not source export name. | FR-6 generated-barrel validity paragraph + OQ-2 | Fixtures for `export default function Step()`, anonymous default export, `export * from`, and `export type { X }`; each either yields a deterministic barrel or an abstain with reason. |
| R2-F2 | Validation | medium | Strengthen FR-11 fixpoint acceptance for the #4 rewrite: after `../../../types/wizard` is rewritten to the selected specifier, re-run `scan_unresolvable_imports` with the same generated-batch candidate set and project root used by repair-retry, and assert the alias/relative form resolves even when `tsconfig` is absent. | `_resolves_on_disk` falls back to `@/` against project root and `src`, and `resolve_specifier_to_paths` resolves only against the provided candidate paths. If `@/components/wizard/types` exists only in the run's generated tree and is not included as a candidate, the second pass can still flag it. | FR-11 acceptance + FR-4 rewrite form | Two fixpoint tests: one fixture with `tsconfig` alias, one without `tsconfig` where the target exists only in generated artifacts; both must re-classify as resolved or the rewrite must choose a relative form. |
| R2-F3 | Security | medium | Make NFR-4 path confinement explicitly require realpath normalization before containment: resolve importer, candidate write path, and `run_root/generated` with `Path.resolve(strict=False)` (or equivalent), reject symlinks escaping the tree, and include a positive case for a confined relative write. | R1-F10 says "within generated root" but does not mandate how. A string-prefix or non-realpath check is bypassable with `..` or symlinks, while an over-broad guard could accidentally block legitimate importer-relative cofile writes. | NFR-4 + FR-5 acceptance | Tests: `../` escape rejected; symlink inside generated pointing outside rejected; normal `./Step.module.css` beside importer accepted. |
| R2-F4 | Risks | high | Replace FR-7's "track each rewrite's `(offset, old, new)` span" with a precise replay algorithm: capture pre-image, apply all fixes to a working copy, then on partial failure reconstruct from pre-image by replaying only kept edits in deterministic original-span order (or re-derive kept spans). | Offset-scoped undo is not well-defined after multiple edits in one file: applying edit A can shift edit B, so undoing A at its original offset may mutate the wrong text. | FR-7 Shared-importer scoping | Test: two edits in one file, first length-changing and rolled back, second kept; final bytes equal pre-image with only the kept edit. |
| R2-F5 | Interfaces | medium | Split FR-8 residue dispositions into at least two schema cases: `needs_regen_feature` for feature-level LLM retry and `unscaffolded_asset` / `deferred_asset` for missing non-feature cofiles when `--no-scaffold` or rollback leaves a CSS module absent. Do not require a `task_filter_token` for non-feature assets unless it maps to an owning feature. | A `.module.css` is not itself a Prime feature. The current schema `{feature_id, importer_file, missing_target, reason, task_filter_token}` can imply `--task-filter` regenerates the CSS file directly, which it cannot. | FR-8 worklist schema | Tests: `--no-scaffold` missing CSS yields an asset residue with owning feature/importer but no bogus CSS task filter; true ambiguous module yields `needs_regen_feature` with valid `task_filter_token`. |

**Endorsements** (prior accepted R1 items this reviewer agrees with):

- R1-F3: Repair-retry should claim residual import clearance, not an overall PASS.
- R1-F10: Path confinement is necessary; R2-F3 tightens how to implement it.

#### Review Round R3 — claude-opus-4-8-1m — 2026-06-02 00:20 UTC

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-02 00:20:00 UTC
- **Scope**: Focused review of the same six R1-fix deltas the sponsor flagged, **after** R2 (gpt-5.5) already filed F1–F5. R2 was read first; this round endorses where R2 is correct and adds only what R2 missed by grounding deeper in the **actual** rewrite/resolver source (`import_path_rename._rewrite_specifier`, `cross_file_imports._resolves_on_disk`, `upstream_interface.resolve_specifier_to_paths`). Not re-litigating R1 (Appendix A) or restating R2's untriaged F1–F5.

**Executive summary (delta to R2):**

- **High:** The edit-scoped-rollback problem is *worse* than R2-F4 states. The existing rewrite primitive (`import_path_rename._rewrite_specifier`) is a **global `str.replace` of the quoted token**, not an offset-anchored edit — so there are **no offsets to track**, and the same specifier appearing twice in one file is rewritten in both places. FR-7's `(offset, old, new)` model presumes a primitive the codebase does not have.
- **Medium (partial disagreement with R2-F2):** The #4 fixpoint is probably **sound, not fragile**, but for a reason R2 missed: re-validation runs through `_resolves_on_disk`, which is **`tsconfig`-blind** (`@/` is tried against project root and `src/` unconditionally). So `@/components/wizard/types` resolves on re-scan **without** any `tsconfig`. The real inconsistency is the opposite of R2-F2: the rewrite *selects* the `@/` alias form per OQ-3 using `tsconfig` `paths`, but resolution **ignores** `tsconfig` — a form that the project's real `tsc` would reject could still be reported "resolved" by repair-retry's own scan (false-resolved), and vice-versa.
- **Medium:** The Inc2/Inc3 divergence (R2-F3/R2-S3) is real, but the sharper failure is a **semantics mismatch**, not just duplicated code: the classifier's name-based `locations_for(module_name)` and the rewriter's specifier-set `resolvable_specifiers()` answer *different questions*, so a parity test over "same answer" must first define what "the same target exists" means across the two query shapes.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Risks | high | FR-7 must stop describing rollback as undoing a `(offset, old, new)` span and instead specify it against the **real** rewrite primitive. `import_path_rename._rewrite_specifier` does `out.replace(q+spec+q, q+target+q)` — a whole-file token replace with **no offset** and **replace-all** semantics. FR-7 should (a) require the rewrite step to return the *set of (specifier→target) substitutions it applied* (not offsets), and (b) define partial rollback as **re-applying the kept substitutions to the captured pre-image** (R2-F4's replay), since per-edit offset undo is not expressible over `str.replace`. | The focus prompt asks whether edit-scoped undo is "well-defined without re-deriving spans." Against this source it is not even definable: there are no spans, and one specifier used twice (e.g. an import + a re-export `from`) is replaced in both spots by a single `replace`. FR-7's current wording would mislead the implementer into building an offset tracker the primitive can't feed. | FR-7 "Shared-importer scoping" paragraph | Test: a file importing `'../x'` twice (import + `export … from`) gets one rewrite; rollback restores **both** occurrences from pre-image; a second co-located kept fix survives byte-for-byte. |
| R3-F2 | Interfaces | medium | Resolve the `tsconfig` resolution-vs-selection inconsistency in FR-4/FR-11/OQ-3. State explicitly that re-validation (FR-7) resolves via the `tsconfig`-**blind** `_resolves_on_disk`/`resolve_specifier_to_paths` (root + `src/` only), and therefore (a) the fixpoint for #4 holds **without** a `tsconfig`, and (b) any `@/` alias form selected from `tsconfig` `paths` that does **not** also resolve under the blind root/`src` convention must be **rejected at rewrite time** (prefer the relative form), so repair-retry never emits an alias that its own re-scan — or a stricter real `tsc` — would not resolve. | FR-11's fixpoint claim is currently justified by hand-wave; the source shows resolution ignores `tsconfig`, which both *saves* the claim (no `tsconfig` needed) and *creates* a new gap (alias chosen by `tsconfig` but validated by a different, blind resolver). The two resolvers must agree on the chosen form. | FR-4 alias-form selection sentence; FR-11 acceptance; OQ-3 | Test: with a `tsconfig` aliasing `@/* → src/*` but the target at `<root>/components/...`, the rewrite must pick the **relative** form (the `@/` alias would not resolve under the blind resolver), and the second pass re-classifies resolved. |
| R3-F3 | Data | medium | FR-3 should define "target exists" as a **single predicate** shared by the classifier and the rewrite resolver, because they currently query different shapes: the classifier asks `locations_for(module_name)` (name → paths, used for ambiguity counting) while the rewrite path consumes `resolvable_specifiers()` (a flat specifier set) — these can disagree (a name present once but reachable by two specifiers, or a specifier that resolves but whose base name also matches an unrelated file). Pin which one is authoritative for the rewritable-vs-ambiguous decision. | This is the substance behind R2-S3/R2-F3's "divergence." Sharing an implementation is necessary but insufficient if the two call sites ask semantically different questions; the ambiguity gate (FR-4 abstain) and the classifier's multi-match rule (FR-3) must count the **same** thing. | FR-3 multi-match rule; FR-4 abstain clause | Test: a fixture where a module name matches 2 files but only 1 is reachable by a valid specifier → classifier and rewriter agree (both rewritable, or both abstain) under the shared predicate. |

#### Review Round R4 — gemini-3.1-pro — 2026-06-02 00:25 UTC

- **Reviewer**: gemini-3.1-pro
- **Date**: 2026-06-02 00:25:00 UTC
- **Scope**: Fresh R4 pass focusing on the exit conditions, fixpoint (idempotence) requirements, string-replacement blast radius, and re-validation scope. Grounded against `cross_file_imports.py` and `import_path_rename.py`.

**Executive summary:**

- **Critical:** FR-11 (fixpoint) is unachievable if the pipeline blindly trusts the static postmortem. A second run will attempt to repair already-fixed files, fail to find the bad specifiers, and emit a massive false-positive regen worklist.
- **High:** FR-7 must re-validate syntax, as string-based rewrites can introduce fatal AST errors.
- **High:** The rewrite primitive performs a global string replacement of the specifier, which can corrupt unrelated string literals in the file, violating the non-destructive requirement.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F1 | Architecture | critical | Amend FR-11 (Fixpoint) to require a **live-state verification step** before acting on the static postmortem. If a violation from the report is no longer present or is already resolvable on disk, it MUST be discarded or marked resolved, not routed to the `needs-regen` worklist. | The postmortem is generated *before* repair. On a re-run, the report still contains the violations. If the engine treats "specifier not found" (because it was fixed) as an abstain, it will dump it into the worklist, causing the second pass to fail and defeating idempotence. | FR-11 Non-destructive & idempotent | Test: A second pass on a fully repaired tree produces an empty worklist and exits 0. |
| R4-F2 | Validation | high | Expand FR-7 to require that re-validation checks for **new syntax errors**. A repair that resolves an import but breaks file syntax must be rolled back. | The rewrite lever is string-based. If it accidentally breaks a quote or brace, a content-only re-scan will falsely accept the file. | FR-7 Re-validation | Test: A repair that introduces a syntax error is rolled back, leaving the pre-image intact. |
| R4-F3 | Security | high | Amend FR-4 / NFR-4 to explicitly require that rewrites are **anchored to import/require statements**, preventing global replacement of the specifier string. | The current implementation globally replaces the quoted specifier string. If the specifier appears in a string literal or comment, it will be corrupted, violating the non-destructive contract. | NFR-4 No-overwrite | Test: A file containing the bad specifier in a non-import string literal is rewritten without corrupting the string literal. |

**Endorsements** (prior accepted R2/R3 items):
- R3-F1: Returning the applied substitutions instead of tracking offsets is the only way to make rollback work with `str.replace`.
- R2-F5: Splitting feature regen from unscaffolded non-feature assets in the worklist schema is essential to avoid breaking `--task-filter`.

**Endorsements** (untriaged R2 items this reviewer agrees with — do not re-triage here):

- R2-F4: Pre-image + kept-subset replay is the correct rollback model; R3-F1 grounds *why* (the primitive is `str.replace`, not span-based) and tightens the acceptance.
- R2-F1: Barrel export computation is over-promised against the regex extractor. Confirmed against `upstream_interface.extract_ts_exports`: it collapses every `export default` to the literal `"default"` and cannot expand `export * from './x'` siblings (no name list without reading the re-export target). Narrowing v1 to default-export components (name taken from the sibling filename, not the source) is the only deterministic path; the collision check as written is otherwise infeasible.
- R2-F5: Splitting non-feature cofile/asset residue from feature-level `needs_regen` is correct — a `.module.css` has no `task_filter_token`.

**Disagreements / refinements (untriaged R2 items):**

- R2-F2 (refine, not reject): the fixpoint is more likely **sound** than fragile because `_resolves_on_disk` is `tsconfig`-blind; the real residual risk is the alias-selection mismatch captured in R3-F2, not "the alias may stay flagged without tsconfig." Recommend folding R2-F2's two-fixture test into R3-F2's alias-vs-relative selection test.

#### Review Round R5 — composer-2.5 — 2026-06-02 01:10 UTC

- **Reviewer**: composer-2.5
- **Date**: 2026-06-02 01:10:00 UTC
- **Scope**: Fresh R5 requirements pass after R1–R4 triage. Requirements v0.5 already merges R4; this round adds only gaps grounded in live source that R1–R4 did not pin: `LiveDiskTruthSource` lib-only enumeration vs FR-4 "full surface," missing relative rewrite algorithm, strict-subset identity, and artifact co-location. Does not re-litigate accepted R1–R4 items.

**Executive summary:**

- **Critical:** FR-4 acceptance for run-012 #4 assumes a relative→canonical rewrite, but the merged step only nearest-matches against a **lib-only** specifier set — the requirement should name the algorithm explicitly.
- **Medium:** FR-7 strict-subset needs a violation identity key; FR-10 should pin where reports are written relative to the run dir.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-F1 | Architecture | critical | FR-4 must specify the **relative-specifier rewrite algorithm** separately from nearest-match: resolve the flagged relative/`@/` specifier through the shared target-existence predicate (FR-3), select a canonical form that passes the blind resolver (R3-F2), apply at import sites only (R4-F3). Acceptance must assert run-012 #4 without relying on `LiveDiskTruthSource`'s lib-only `resolvable_specifiers()`. | Verified `truth_source.py:100-124` enumerates only `lib/**/*.{ts,tsx}`; `_resolve_specifier` has no `../../../` branch. FR-4 says "depth correction" but the merged code path cannot perform it today. | FR-4 rewrite lever paragraph + acceptance | PI-012 fixture: `../../../types/wizard` → form resolving to `components/wizard/types.ts`; lib-only nearest-match abstains (negative control). |
| R5-F2 | Validation | medium | FR-7 strict-subset: define violation identity as **`{file_path, specifier}` multiset**. Re-validation rolls back a fix only when `post_repair_violations − pre_repair_violations` (by that key) is non-empty, or a new syntax error appears (R4-F2). Unchanged specifiers must not count as "new." | Without a stable key, partial repair + remaining abstained violation can false-trigger rollback or miss a genuinely new import break. | FR-7 re-validation paragraph | Test: one repaired + one abstained violation same file — kept repair survives; introducing a second distinct unresolvable import triggers rollback. |
| R5-F3 | Ops | medium | FR-10 / FR-1: pin **artifact output location** — `repair-retry-report.json`, `regen-worklist.json`, and `repair-retry-summary.md` MUST be written under the resolved run directory (e.g. `<run>/repair-retry/` or beside `prime-postmortem-report.json`), not the process cwd. R1-S10 stdout contract assumes discoverable absolute paths. | OQ-5 says in-place fixes in `generated/` but omits report placement; cwd-relative output breaks cap-dev-pipe and multi-run workspaces. | FR-10 + FR-1 acceptance; resolve OQ-5 | Test: CLI `--from-run <run-dir>` writes artifacts under that run dir; stdout paths are absolute and stable across invocations from different cwds. |

**Endorsements:**

- R4-F1/F2/F3: Correct and merged; plan body sync still pending (see R5-S1 in plan doc).
- R3-F2: Blind-resolver-compatible alias selection is necessary but insufficient without R5-F1's relative rewrite path.
