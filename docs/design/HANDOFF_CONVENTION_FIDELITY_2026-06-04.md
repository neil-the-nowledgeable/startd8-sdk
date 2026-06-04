# Handoff — Convention-Aware Repair + Micro-Prime Fidelity (2026-06-04)

**From:** session that landed FR-CAR-11 + FR-MPF-1 and validated against RUN-036.
**To:** the session continuing this work.
**Scope:** the "make the cheapest tier generate to the house style and stop inventing" thread —
`CONVENTION_AWARE_REPAIR_*` (FR-CAR-0..11) + `MICRO_PRIME_FIDELITY_*` (FR-MPF-1..6).
**Read first:** `docs/design/RUN_036_CONVENTION_INJECTION_VALIDATION_POSTMORTEM.md` (the live evidence),
then `docs/design/repair-pipeline/CONVENTION_AWARE_REPAIR_REQUIREMENTS.md §0.5` (status table).

---

## 0. TL;DR — where this stands

- **Convention idiom prevention (FR-CAR-5b / 8b) WORKS** where it reaches: RUN-036 `app/jobs.py` went
  from Flask/`session.query` (RUN-032) → FastAPI/SQLModel `session.exec(select())`. Real, demonstrated.
- **The failures have moved to the paths injection does NOT reach** — test generation, spec/draft
  construction, and 0-element "integrate" features. This is the *same structural bypass* that motivated
  the whole effort, one altitude up. **This is the #1 thing to fix.**
- **Score did not improve** (RUN-036 0.44 vs RUN-032 0.51) but it's a *different, larger plan* — judge by
  per-file evidence, not the aggregate.
- **FR-MPF-5 measurement gate is CLOSED.** Do **not** tighten FR-MPF-3/4 routing thresholds yet.

---

## 1. ⚠️ Immediate landmine — an in-progress merge on `main` (resolve FIRST)

As of this handoff there is a **conflicted merge in progress** on `main`:
`git merge feat/fr-mpf-2-3-surface-routing` (commit `db16f4b6`). **Both sessions implemented
near-identical FR-MPF-2/3** (one in a worktree, one on `main`), so the merge collides:
- `src/startd8/complexity/models.py` — **auto-resolved** (0 markers; both `manifest_element_count` and
  `manifest_element_simple_max` present) → just `git add`.
- `tests/unit/complexity/test_models.py` — **cosmetic** conflict only: both sides wrote
  `assert len(d) == 15`, differing only in the comment. Pick either, `git add`, commit.

**Before writing any new code, decide the merge:** either complete it (trivial) or `git merge --abort`
and keep `main`'s version (since `main` already has equivalent FR-MPF-2/3). Then
`git worktree remove ../startd8-sdk-mpf` and delete the `feat/fr-mpf-2-3-surface-routing` branch.
**Two untracked docs are waiting to be committed** once the merge settles:
`RUN_036_...POSTMORTEM.md` and this handoff. Also note `main` is **~28 commits ahead of origin** — push
once stable.

---

## 2. What landed (don't redo)

| FR | What | Where |
|----|------|-------|
| FR-CAR-0/1/2/3 | Python convention authority + detector (advisory) | `repair/convention.py`, `ConventionDiagnostic` in `repair/models.py` |
| FR-CAR-4 | safe-fixer + governed-scope guard | `repair/steps/python_convention_fix.py`, `repair/routing.py` |
| FR-CAR-6 | escalate-don't-silence residual | `RepairOutcome.unrepaired_diagnostics`, `EscalationHandoff` |
| FR-CAR-7 + **FR-CAR-11** | verdict hard-gate, **now behind `STARTD8_CONVENTION_GATING`** (default ON; measured FP 0% over N=19 governed files < X=5%) | `forward_manifest_validator.py:_convention_gating_enabled` + the gate |
| FR-CAR-5b (8b) | static convention idiom block → micro-prime prompt | `repair/convention.py:render_convention_guidance`, `MicroPrimeContext.convention_guidance` |
| **FR-MPF-1 (8a)** | **field-set/enum authority → micro-prime** (`gen_context["upstream_interfaces"]` forwarded; was dropped) | `MicroPrimeContext.upstream_interfaces`, `engine.py:process_file_with_context`, `_cap_authority_block` |
| FR-MPF-2/3 | surface signal + surface-aware SIMPLE guard (PERMISSIVE no-op default 999) | `complexity/{models,signals,classifier}.py` (in the conflicted merge) |

---

## 3. Most important next steps (re-prioritized by RUN-036, highest first)

1. **Reach the TEST-generation path.** RUN-036's `tests/test_jobs.py` / `test_job_export.py` had **0
   micro-prime elements** → they route through a different generator that never sees `from_prime`'s
   injected authority, and retain the *full* class (`from app.models import …, JobMatch`,
   `sqlalchemy.pool`). This is the biggest hole now (2 of 5 failures). Find the test generator and apply
   the same field-set + convention authority (sibling to FR-MPF-1).
2. **Make the SPEC adhere, not just micro-prime.** The `Match` name-invention that boot-cascaded 3
   features (`ImportError: cannot import name 'Match' from app.tables`) **originates in the spec
   artifact** (`…/.artifacts/Tests_for_job_export-spec.md:373` literally says
   `from app.models import Match  # existing model`). The lead/drafter path is *supposed* to carry
   field-set authority — verify it actually injects entity names/modules into the spec prompt **and**
   that the spec adheres (the `adherence.py` "injection ≠ adherence" guardrail is the warning here).
3. **Stub / under-generation guard.** `app/job_export.py` "PASSED" disk 1.0 while being literally
   `job_export_router = None` (8 lines, no functionality). A $0 stub scoring perfect is a **measurement
   integrity hole** — it makes the convention class look "fixed" when it was just *avoided by generating
   nothing*. FR-MPF-3 does NOT catch this (1-element file, below any surface threshold) — it's a
   fillability/`has_fillable_elements` problem on a single element. Don't conflate the two.
4. **`requirements.in` deps.** `sqlmodel`/`sqlalchemy` are not declared in the generated
   `requirements.in`, so the import-resolution semantic check fails even on correctly-written files.
   Mechanical fix in the requirements generator.

**Sequencing:** #4 + #3 are cheap and restore measurement honesty; #1 + #2 are the substantive
prevention work and are the real precondition for re-running the FR-MPF-5 measurement. Only after #1/#2
land and a run shows a clean lift should FR-MPF-3/4 thresholds be tightened.

---

## 4. Serious concerns / landmines (insights you won't get from the code alone)

- **"Reaches micro-prime" ≠ "reaches generation."** The validated injection seam is
  `MicroPrimeContext.from_prime` → micro-prime prompt. Anything NOT routed through micro-prime (test
  gen, 0-element features, the spec/draft lead path's *output adherence*) silently bypasses it. Every
  time you "fix" a bypass, **check the next tier out** — this bug keeps reappearing one level up
  (RUN-028: micro-prime; RUN-036: test-gen + spec). Audit *all* generation entry points, not just the
  one in front of you.
- **Stub false-passes corrupt the signal.** Disk-quality 1.0 on an empty `router = None` file means the
  postmortem will tell you the convention class is solved when it isn't. **Cross-check "PASS" features
  for actual content**, not just the score, when validating prevention work. (RUN-036 PI-003 is the trap.)
- **FR-CAR-11 gate is default-ON, but the FP measurement is in-architecture-only.** The 0% FP was
  measured on the deployed FastAPI/SQLModel `strtd8/app/`. The detector hardcodes that house style and
  would **false-fire on a legitimately-Flask/SQLAlchemy project** (e.g. the online-boutique corpus). The
  `STARTD8_CONVENTION_GATING=0` off-switch exists for exactly that. **Do not run the gate hot on a
  non-canonical Python project without re-measuring FP there.** (This is the unaddressed generalization
  gap — no per-project scoping of the detector/gate.)
- **The Controlled-Corpus FP set is the wrong architecture.** Its `false_pass_risk`/`deterministic_candidate`
  files are online-boutique (gRPC/Flask/polyglot). Running the FastAPI detector there measures
  architecture mismatch, not detector FP. That's why FR-CAR-11's measurement used the in-arch deployed
  app instead. Don't "fix" the gate by pointing it at that corpus.
- **FR-MPF-3 ships as a no-op (`manifest_element_simple_max=999`).** It is *present but inert* by design
  (FR-MPF-5). Don't assume rich-spec routing is active — it isn't until calibrated (OQ-2). A future run
  showing a stub'd schema-mirror routed SIMPLE is *expected* until you lower the threshold.
- **OQ-4 is resolved but subtle:** the surface guard yields to `complexity_tier_override` *by
  construction* — overrides are applied as a pre-classification bypass (`context_seed/core.py:4546`), so
  the classifier never runs when one is set. Don't add override logic into the classifier; you'd be
  double-handling it.
- **`corpus_class` is derived, not stored** (if you touch the controlled corpus): the saved JSON omits
  it; recompute via `ControlledCorpusRegistry.load(...)`. Reading the raw JSON gives `None`.
- **Detector module-source blind spot (suspected):** RUN-036 `jobs.py` imported tables from `.models`
  (relative) and was NOT flagged `module_source`, while absolute `app.models` *is* flagged. Verify the
  detector matches relative `.models` too, or it'll miss the relative-import form of the class.

---

## 5. Open questions still live (from `MICRO_PRIME_FIDELITY_REQUIREMENTS.md §3)

- **OQ-1 (token budget):** the field-set block + skeleton + few-shot must fit ~1024 tokens.
  `_cap_authority_block` caps it to ~¼ of the char budget — confirm it doesn't starve few-shot on real
  multi-entity features.
- **OQ-2 (FR-MPF-3 calibration):** what `manifest_element_simple_max` catches the RUN-007 schema-mirror
  class without false-elevating genuine trivials? Calibrate against RUN-007 stub'd files vs a known-good
  SIMPLE corpus.
- **OQ-3 (convention-strict at classify time):** is `CANONICAL_LAYOUT` ownership known *before*
  generation? FR-MPF-4 (route-away-when-strict) degrades to the Kaizen-feedback path if not.
- **OQ-5 (decomposer inheritance):** decomposed SIMPLE sub-elements inherit authority via
  `_current_domain_constraints` (verified for the convention path) — add a regression test that a
  decomposed sub-element's prompt contains the field-set block, and confirm the standalone
  `process_element()` path (leaves `_current_domain_constraints=None`) is an explicit non-goal.
- **OQ-6 (efficacy metric):** FR-MPF-4/5 need a defined structural-adherence metric + class granularity
  + N. RUN-036 showed efficacy is *not cleanly isolable* with the current artifacts — you'll need a
  per-file, per-class adherence score to make the gate decision rigorous.

---

## 6. Key seams (file:concept)
- Injection into micro-prime: `micro_prime/context.py:from_prime` → `micro_prime/engine.py:2566`
  (`process_file_with_context` merges `upstream_interfaces` then `convention_guidance` into
  `domain_constraints`) → rendered at `micro_prime/prompt_builder.py:306` (`# Domain constraints`).
- Field-set authority source (lead path, language-agnostic): `prime_contractor.py:4439`
  (`gen_context["upstream_interfaces"] = _collect_upstream_interfaces(feature)`; Prisma field-sets at
  `:4541-4582`, REQ-CKG-524/527).
- Verdict gate: `forward_manifest_validator.py:_convention_gating_enabled` + the hard-gate ~line 590.
- Detector + authority + guidance: `repair/convention.py` (`detect_conventions`,
  `build_python_convention_authority`, `render_convention_guidance`).
- Classifier guard: `complexity/classifier.py:_classify_tier_core` (the `_strict_simple`/`_relaxed_simple`
  precompute + FR-MPF-3 guard).

---

## 7. Validation discipline (how to judge the next run)
1. **Per-file, not aggregate** — the plans differ run to run; the aggregate score lies.
2. **Open "PASS" files and read them** — guard against stub false-passes.
3. **Trace each failure to its generation tier** — micro-prime vs test-gen vs lead/spec — and ask
   "did the injection reach *this* path?" That single question explains every RUN-036 failure.
4. **Separate spec-level inventions from generation-level inventions** — RUN-036's `Match` was a *spec*
   defect, fixable only upstream of generation.
