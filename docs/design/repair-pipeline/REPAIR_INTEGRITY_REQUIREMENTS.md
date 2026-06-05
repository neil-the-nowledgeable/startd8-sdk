# Repair & Import-Resolution Integrity Requirements

**Version:** 0.1 (Draft — RUN-038 #1/#2)
**Date:** 2026-06-04
**Status:** Draft
**Owner:** neil-the-nowledgable
**Driver:** [`RUN_038_CONVENTION_FIDELITY_VALIDATION.md`](../RUN_038_CONVENTION_FIDELITY_VALIDATION.md) §2.3, §2.4
**Predecessor evidence:** `RUN_036_CONVENTION_INJECTION_VALIDATION_POSTMORTEM.md` (#1, #4)

---

## 0. Why this doc exists

RUN-038 surfaced two defects that are **independent of the convention class** (FR-CAR) and the
field-set class (FR-MPF), and that **had no documented requirement** of their own — they lived only
in postmortems as "next steps." This doc gives them a home so they can be implemented against a
spec, not a postmortem bullet.

| RUN-038 issue | Pre-this-doc status | Class |
|---------------|---------------------|-------|
| #1 — resolver allow-list omits `sqlmodel`/`sqlalchemy` | **Not documented** (only postmortem next-steps) | Measurement integrity |
| #2 — `import_completion` synthesizes `import <local-var>` | **Combo** — the step is referenced in `SEMANTIC_REPAIR_REQUIREMENTS` but its scope-safety rule was undocumented | Repair safety (own-goal) |

Both are small, mechanical, and high-leverage per the postmortem's own sequencing (§5 #1/#2): they
restore **score honesty** and **boot integrity**.

---

## 1. Requirements

### FR-RI-1 — Import resolution reflects the project's real dependency surface (RUN-038 #1)

**Problem.** The disk validator's import-resolution check (`utils/import_resolution.py`,
`_WELL_KNOWN_PACKAGES`) lists `fastapi/starlette/jinja2/pydantic/…` but **not `sqlmodel` or
`sqlalchemy`**, and the strtd8 project has **no `requirements.in`**. So every `import sqlmodel` /
`from sqlalchemy.pool import …` on a **correctly-written** file flags as *unresolvable* — inflating
`semantic_error_count` and dragging test features to `PARTIAL:semantic (0.8)` purely on a measurement
artifact (RUN-038 §2.2/§2.4). The validator penalizes correct code.

**Requirement.**
- **FR-RI-1a:** the import resolver MUST recognize the project's **declared dependencies** as
  resolvable — reading `requirements.txt` / `requirements-app.txt` / `pyproject.toml`
  (`[project.dependencies]`) and/or the installed environment — not only a hard-coded allow-list.
- **FR-RI-1b:** `_WELL_KNOWN_PACKAGES` MUST include the common database/ORM packages as a **floor**
  (at minimum `sqlmodel`, `sqlalchemy`), so resolution is correct even when a project ships no
  dependency manifest. (The one-line floor is the immediate fix; FR-RI-1a is the durable fix.)

**Acceptance.** A correct file importing `sqlmodel` / `sqlalchemy` produces **zero**
import-resolution errors; the `import_completeness`/`semantic_error_count` for such files reflects
real defects only. Regression fixture: the RUN-038 `tests/test_jobs.py` import set resolves clean.

**Non-goal.** Not a full dependency solver — recognizing declared + well-known packages is
sufficient; deep version/transitive resolution is out of scope.

---

### FR-RI-2 — Import-synthesizing repair MUST NOT introduce boot failures (RUN-038 #2)

**Problem.** `import_completion` synthesized a top-level `import assets` for a name that is a **local
variable** bound in a function body (`assets = session.exec(select(TailoredAsset)…)`), producing a
guaranteed `ModuleNotFoundError: No module named 'assets'` on boot (RUN-038 §2.3). Root cause
(home-verified): `repair/steps/import_completion.py:_collect_local_definitions()` walks only
`ast.iter_child_nodes(tree)` = **module-level** definitions, so a name bound *inside* a function,
comprehension, or `with`/`for` target is invisible to the guard and gets a bogus import.

**Requirement.**
- **FR-RI-2a:** before synthesizing a top-level import for an unresolved name, `import_completion`
  MUST exclude names bound in **any** local scope reachable in the file — function/method parameters,
  local assignments, `for`/`with`/comprehension targets, walrus bindings, and nested-scope
  definitions — not only module-level definitions.
- **FR-RI-2b:** a repair step MUST NOT *introduce* a new boot/import failure. The
  `import_completion` step SHALL verify (parse + name-resolution check) that the file it returns has
  no newly-unresolvable top-level import it created.

**Acceptance.** A name bound locally (e.g., `assets` in a function body) never yields a synthesized
`import assets`; the RUN-038 `app/jobs.py` fixture (local `assets`) produces no own-goal import.
Property test: for any file, `import_completion` adds an import only for names that are (a) unresolved
**and** (b) not bound in any scope of the file.

> **RUN-038 diagnostic now standing:** the Forward Deployed Engineer flags this class on every run —
> when `import_completion` fired on a failed element it emits a `MECHANISM (sdk, conflict)`
> own-goal-risk claim (`fde/sources.py:read_element_mechanism`). FR-RI-2 is the fix; the FDE claim is
> the tripwire that keeps the own-goal from recurring silently.

---

## 2. Non-Requirements

- **NR-1.** No general dependency-graph solver (FR-RI-1 non-goal).
- **NR-2.** No new repair *category* — FR-RI-2 hardens the existing `import_completion` step; it does
  not add a step.
- **NR-3.** Not the convention class (FR-CAR) nor the field-set class (FR-MPF) — those are tracked
  separately. This doc is **measurement + repair-safety integrity** only.

---

## 3. Relationship to the other RUN-038 requirements

| RUN-038 issue | Home requirement |
|---------------|------------------|
| #1 resolver coverage | **FR-RI-1** (this doc) |
| #2 import_completion own-goal | **FR-RI-2** (this doc) |
| #3 spec field-set binding | FR-MPF-1 + FR-CAR-0/2 (Python convention authority) — *documented, implement residual* |
| #4 test-gen field-set half | FR-MPF-7 — *landed `2095457f`* |
| #4 test-gen convention half | FR-CAR-12c |
| #5 safe-fixer unreachable | FR-CAR-12a/12b |

---

*v0.1 — gives the two previously-undocumented RUN-038 integrity defects (#1 undocumented, #2 combo) a
home requirement. Small, mechanical, high-leverage per the postmortem's own §5 sequencing.*
