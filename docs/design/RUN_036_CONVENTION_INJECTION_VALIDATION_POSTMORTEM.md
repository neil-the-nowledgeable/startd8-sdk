# RUN-036 — Convention/Field-Set Injection Validation Postmortem

**Date:** 2026-06-04
**Run:** `strtd8/.cap-dev-pipe/pipeline-output/startd8/run-036-20260604T1245`
**Score:** 0.44 PARTIAL (4/9) · **Baseline:** RUN-032 0.51 PARTIAL (4/7)
**Purpose:** validate the just-landed convention-aware-repair machinery end-to-end —
Phase C 8b (`convention_guidance`), FR-MPF-1 (field-set authority → micro-prime),
Phase B.2 safe-fixer, the FR-CAR-11 verdict gate — against the RUN-032 baseline.
**Verdict:** the prevention **works where it reaches**, but the failures have **moved to paths
injection does not cover**, plus a stub false-pass and the requirements-dep gap. **Not** a clean
score win, and **not** a green light to tighten FR-MPF-3/4 routing (FR-MPF-5 gate stays closed).

> ⚠️ **Not apples-to-apples.** RUN-036 is a *different, larger* plan (9 features vs 7) — new
> `PI-008` "Integrate new routers", more test features. The raw 0.44-vs-0.51 delta is not a
> regression signal; the per-file evidence below is.

---

## 1. The genuine win — 8b injection fired on the micro-prime production path

`app/jobs.py` received 2 micro-prime (`simple`) elements and now generates the **correct house style**:

```python
from sqlmodel import Session, select                       # not sqlalchemy.orm
statement = select(TailoredMatch).where(TailoredMatch.jd_id == jd_id)
matches = session.exec(statement).all()                    # not session.query(...)
```

In **RUN-032** this exact file was Flask + `from sqlalchemy.orm import Session` + `session.query(...)`.
**The FR-CAR-5b convention-idiom prevention demonstrably fired** on the cheapest tier — the class is
fixed where injection reaches. Entity names used are real schema entities (`TailoredMatch`,
`JobDescription` both exist in `schema.prisma`).

---

## 2. Why the score did not improve — four issues, none addressed by what landed

### 2.1 `job_export.py` "PASS" is a stub false-pass (RUN-007 under-generation class)
`PI-003` scored disk **1.0** while the entire generated file is:
```python
from __future__ import annotations
job_export_router = None
__all__ = ["job_export_router"]
```
It scores perfectly by generating *nothing* — no code → no convention violations → no stubs detected.
**FR-MPF-3 would NOT catch this** (a 1-element file is below any surface threshold); this is an
under-generation / fillability problem, not a surface-area one.

### 2.2 Injection bypasses the test-generation path entirely
`tests/test_jobs.py` and `tests/test_job_export.py` had **0 micro-prime elements** — they route
through a different generator that never receives `from_prime`'s injected authority. They retain the
**full** class:
```python
from sqlalchemy.pool import StaticPool
from app.models import Asset, JobDescription, JobMatch     # module_source: should be app.tables
```
plus `CONV[module_source] from app.models import Asset, JobDescription, JobMatch (safe_fixable=True)`.
**The structural bypass moved one level out** — from "micro-prime doesn't get it" (RUN-028/032) to
"test-gen and 0-element features don't get it" (RUN-036). 2 of the 5 failures are test files.

### 2.3 The `Match` name-invention originates in the spec, and cascades to a boot failure
The spec artifact (`Tests_for_job_export-spec.md:373`) literally says:
```
from app.models import Match    # existing model
```
But the schema has **`JobMatch`/`TailoredMatch` in `app.tables`** — there is no `Match`. The field-set
authority that knows the real names is **not correcting the spec/draft path**, so
`ImportError: cannot import name 'Match' from 'app.tables'` breaks `app.server:app` and **cascades to
fail 3 features** (`PI-001`, `PI-002`, `PI-008` — all `cross_feature_contract` / boot-smoke). The
draft/impl also disagree on module (`app.models` vs `app.tables` vs `.models`) — a spec-ingestion
fidelity defect, not a model-invention-at-generation defect.

### 2.4 `sqlmodel` / `sqlalchemy` still absent from generated `requirements.in`
`import_resolution: 'sqlmodel' is not stdlib, not in requirements.in, not a local module` — the
dep-declaration gap (flagged in the RUN-032 analysis) persists, tripping the import-resolution checks
even on correctly-written files.

---

## 3. Cross-cutting lesson
**Reaching micro-prime is necessary but not sufficient.** The validated injection (8b + FR-MPF-1) is
wired into `MicroPrimeContext.from_prime` → micro-prime prompts. The failures now live on the paths
that *don't* go through that seam:
- **test generation** (0-element features → not micro-prime),
- **spec/draft construction** (the lead path *should* carry field-set authority, yet the spec invented `Match`),
- **0-element "integrate" features** (`PI-008` user_routers — no elements, no injection).

The same shape that motivated FR-CAR-5 in the first place, one altitude up.

---

## 4. FR-MPF-5 gate verdict
Injection efficacy is **partial and not cleanly isolable** on this run: the one production file that
received it (`jobs.py`) is idiom-correct, but the spec and test paths still invented `Match`/wrong
modules, and `job_export.py` degenerated to a stub. **Do not tighten FR-MPF-3/4 routing thresholds.**
The FR-MPF-2/3 worktree branch (`feat/fr-mpf-2-3-surface-routing`) stays **permissive/unmerged** until
injection reaches the bypassed paths and a run shows a clean lift.

---

## 5. Next steps (re-prioritized by this run)

| # | Action | Rationale | Size |
|---|--------|-----------|------|
| 1 | **Reach the test-generation path** with the same field-set + convention authority (sibling to FR-MPF-1, applied to whatever generates the 0-element test features) | Biggest new hole — 2 of 5 failures are test files with the full class | M |
| 2 | **Correct entity names/modules at spec-build time** — the spec said `from app.models import Match`; field-set authority must reach + bind the spec/draft prompt, not just micro-prime | Root of the `Match` boot-cascade (3 failures); the "spec must adhere" half | M |
| 3 | **Under-generation / stub guard** for the `job_export_router = None` false-pass | A $0 stub scoring 1.0 is a measurement integrity hole | S–M |
| 4 | **Declare `sqlmodel`/`sqlalchemy` in generated `requirements.in`** | Mechanical; unblocks import-resolution on correct files | S |

**Sequencing:** #4 (cheap, mechanical) and #3 (measurement integrity) first; #1/#2 (reach the
spec + test paths) are the substantive prevention work and are the real gate for re-running the
FR-MPF-5 measurement. Hold FR-MPF-2/3 (surface routing) until after.

---

## Appendix — evidence
- Report: `…/run-036-20260604T1245/plan-ingestion/prime-postmortem-report.json`
- `job_export.py` stub: `…/generated/app/job_export.py` (full file = 8 lines, `router = None`)
- `jobs.py` correct idiom: `…/generated/app/jobs.py:9,13,21` (`sqlmodel`, `select`, `session.exec`)
- spec `Match` invention: `…/generated/.artifacts/Tests_for_job_export-spec.md:373`
- module disagreement: `…/generated/.artifacts/Per-job_workspace___gap___assets-review-3.md:24`
- Baseline: `docs/design/repair-pipeline/CONVENTION_AWARE_REPAIR_REQUIREMENTS.md §0.5` (RUN-032)
