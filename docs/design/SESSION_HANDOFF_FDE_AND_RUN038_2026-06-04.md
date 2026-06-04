# Session Handoff — Forward Deployed Engineer + RUN-038 Convention-Fidelity Fixes

**Date:** 2026-06-04
**Author:** Claude Opus 4.8 (1M) session
**Scope:** Built a new agent type (Forward Deployed Engineer), deployed it, extended it, and
implemented the RUN-038 convention-fidelity fixes (FR-RI-1/2, FR-CAR-12) with requirement docs.

> **Read this if:** you're reconciling the diverged `main` / feature branches (see §6), or picking
> up the RUN-038 work. Everything described here is **committed** (branch detail in §5). The one
> open git action is the merge (§6) — it has a *real* conflict (duplicate #4c) that needs a human call.

---

## 1. Forward Deployed Engineer (FDE) — new feature

A hybrid agent type per the **Tekizai-Tekisho** design principle: the *brain* (mechanism-authority
logic) lives in the SDK; the *posting* (`.startd8/fde/` context + `fde-*.md` protocol) deploys into
the project. It supplies the **MECHANISM (sdk)** half of a cross-boundary composition; the Service
Assistant supplies the **OBSERVED (project)** half.

- **Package:** `src/startd8/fde/` — `models` (Keiyaku contracts), `sources` (§6 source-of-truth
  readers + artifact trust gate), `explain` (compose SA evidence + SDK mechanism), `deterministic_compose`
  (zero-LLM render + labeling guard), `compose` (optional LLM narrative), `preflight` (two-track
  landmines + redaction), `assistant_bridge` (write-back), `notify`, `context` (posting + idempotency),
  `assistant` (orchestrator).
- **CLI:** `startd8 fde {explain,preflight,init}`; bare `explain` / `--latest` resolves the newest run
  with a triage (FR-28). Shim `scripts/run_fde.py`.
- **SA integration:** `FdeRef` + `fde_explanation` on `service_assistant.TriageReport` (one-directional,
  no import cycle); `FDE_EXPLAIN_COMPLETE`/`FDE_PREFLIGHT_COMPLETE` events.
- **Process:** built via the reflective-requirements loop → CRP R1–R5 → triage → v0.3.1. Specs in
  `docs/design/fde/` (`FORWARD_DEPLOYED_ENGINEER_REQUIREMENTS.md` v0.3.1, `_PLAN.md`, CRP artifacts).
- **Deployed to `strtd8`:** `.startd8/fde/` posting established; verified live on `run-038`
  (`fde explain` composed 3 failures × source-labeled claims).
- **cap-dev-pipe hook:** opt-in post-run FDE hook in `~/Documents/dev/cap-dev-pipe/run-prime-contractor.sh`
  (`STARTD8_FDE_AFTER_ASSIST=1`, off by default).

### FDE extension (RUN-038 diagnostics)
Two new mechanism readers so the FDE flags the RUN-038 classes on every run:
- `read_convention_status` — per-feature convention violations + the **safe-fix gap**: a
  `MECHANISM (sdk, conflict)` claim when a `safe_fixable` violation is hard-gated but
  `semantic_repairs_applied=0` (RUN-038 §2.5 worst-of-both).
- import-completion **own-goal flag** — when `import_completion` fired on a failed element.

---

## 2. RUN-038 convention-fidelity fixes (the 5 issues)

Driver: `docs/design/RUN_038_CONVENTION_FIDELITY_VALIDATION.md`. Status as of this session:

| # | Issue | Status | Fix (file) |
|---|-------|--------|-----------|
| **1** | resolver allow-list omits sqlmodel/sqlalchemy → correct files flagged unresolvable | ✅ implemented | `utils/import_resolution.py` (DB/ORM floor) + `forward_manifest_validator._discover_requirements_packages` (walks to project root; reads `requirements*.txt` + `pyproject`) — **FR-RI-1** |
| **2** | `import_completion` synthesizes `import <local-var>` → boot ModuleNotFoundError | ✅ implemented | `repair/steps/import_completion.py:_collect_local_definitions` now walks ALL scopes (params, for/with/comprehension/walrus, imports, nested, **match/case**) — **FR-RI-2** |
| **3** | spec field-set binding | ✅ closed (prior `dd95bbcb`) + residual verified | nuanced module-source rule rides `convention_guidance`; a coarse Python `SEEDED_NEGATIVE` would over-fire (verified) — no code change |
| **4 field-set** | test features invented entity names | ✅ closed (prior `2095457f`) | **FR-MPF-7** (retro-documented) |
| **4 convention** | convention authority absent on test/lead-cloud path | ✅ implemented (see §6 caveat) | thread `convention_guidance` into `prime_contractor` gen_context + `drafter` + `spec_builder` — **FR-CAR-12c** |
| **5** | FR-CAR-4 safe-fixer never applied on micro-prime app routers | ✅ implemented | **Implemented the missing `app.models→app.tables` module-source repoint** in `repair/steps/python_convention_fix.py` (the `safe_fixable` flag had NO transform); widened scope to generated app files; wired into `micro_prime/repair.py` file pipeline — **FR-CAR-12a/b** |

### Key technical decisions
- **#5 — two-scope reconciliation:** the dual-pattern-risky query→`session.get` rewrite stays
  **spine-only** (CANONICAL_LAYOUT, per CRP R1-F6); the **unambiguous** module-source repoint goes
  **app-package-wide** (reaches bespoke routers like `app/jobs.py`). The repoint splits tables (→
  `app.tables`) from schemas (stay in `app.models`).
- **#2 — conservative direction:** any name bound in *any* scope is excluded from import synthesis (a
  missed import-completion is far cheaper than an own-goal boot failure).
- **#3 — verified no-op:** the suggested Python `SEEDED_NEGATIVE` (`app.models→app.tables`) would
  over-fire because `app.models` legitimately holds Pydantic Schemas; the nuanced rule already rides
  `convention_guidance` (now extended to the lead path by #4c).

### Code-review pass (`/code-review --fix`)
- `python_convention_fix.__call__`: guarded `build_python_convention_authority()` (degrade, don't throw).
- `import_completion`: added `match`/`case` capture collection (py3.10+, `getattr`-guarded for 3.9).

---

## 3. Requirement docs updated/added

| Doc | Change |
|-----|--------|
| `repair-pipeline/CONVENTION_AWARE_REPAIR_REQUIREMENTS.md` → v0.7 | **FR-CAR-12 (a/b/c)** — cure must reach micro-prime + governed scope includes app files + convention authority reaches test-gen |
| `micro-prime/MICRO_PRIME_FIDELITY_REQUIREMENTS.md` → v0.4 | **FR-MPF-7** — field-set authority reaches test features (retro-doc `2095457f`) |
| `repair-pipeline/REPAIR_INTEGRITY_REQUIREMENTS.md` (new) | **FR-RI-1** (resolver honesty, #1) + **FR-RI-2** (import_completion scope-safety, #2) |
| `fde/FORWARD_DEPLOYED_ENGINEER_REQUIREMENTS.md` v0.3.1 + `_PLAN.md` | the FDE spec (reflective loop + CRP) |

---

## 4. Tests

All new/changed code is unit-tested. Suites touched (all green except one pre-existing failure):
`tests/unit/fde/` (39), `tests/unit/test_import_resolution.py`, `tests/unit/repair/test_import_completion.py`,
`tests/unit/repair/test_convention.py`, `tests/unit/micro_prime/test_repair.py`,
`tests/unit/implementation_engine/` (188).

**Pre-existing, NOT from this session** (confirmed against the committed baseline): `test_pip_alias_mapped`
(grpc→grpcio) fails; ruff debt in `forward_manifest_validator.py` (281/1192/1665/2645) and `drafter.py`
(8/30). Left untouched.

---

## 5. Commit inventory

**startd8-sdk** — branch `feat/determinism-metric-scaffold-spec` (local; the parallel agent renamed/owns it):
| Commit | Content |
|--------|---------|
| (earlier) `f6a11727` | FDE package, CLI, deployment — **pushed to `origin/main`** earlier this session |
| `7b30319c` | docs — requirement homes (FR-CAR-12, FR-MPF-7, FR-RI-1/2) |
| `f71d837d` | FDE diagnostic surfaces |
| `833eaa23` | the 5 RUN-038 fixes |
| `3c384e62` | code-review hardening |
| `640ab1ee` (parallel agent's) | **contains my `prime_contractor.py` #4c threading** (swept in via shared working tree) |

**cap-dev-pipe** — branch `main` (local, no remote): `ef67ecb` — SDK-bridge post-run hooks (FDE + the
prior-session SA hook that was sitting uncommitted).

> ⚠️ **Shared-working-tree collisions happened.** A parallel agent committed on the same tree; it swept
> my `prime_contractor.py` into `640ab1ee`, and I earlier had to un-sweep its sapper files from my docs
> commit. All *my* code is present and correct — only `prime_contractor.py`'s #4c is attributed to the
> parallel agent's commit.

---

## 6. Git state & the merge situation (the one open action)

`main` (local `d139cf09`) and the feature branch (`76e1bf41`) have **diverged** — both are the parallel
agent's active lines; my 4 commits rode along on the feature branch. `origin/main` is still at `dd95bbcb`.

A `git merge-tree` preview (non-destructive) shows **3 conflicts, all in `prime_contractor.py`,
`drafter.py`, `spec_builder.py`** — because **#4c was implemented twice**: by me (feature branch) and
independently on `main` (commit **`5001db21` "feat(lead): thread Python convention authority into
spec+draft"**). Same feature, same lines.

**Implications:**
- My *unique* work (FR-RI-1/2, FR-CAR-12a/b, FDE diagnostic, docs) does **not** conflict — only the
  duplicate #4c does. #4c is already on `main` via `5001db21`, so that gap is covered regardless.
- `prime_contractor.py` on the feature branch entangles the parallel agent's postmortem change with my
  #4c, so "take main's version" is not a safe blind resolution.

**Recommended resolution (needs a human call):**
1. **Preferred:** let the parallel agent converge the two diverged lines (it owns both + created the
   duplicate #4c). My work is safe on the feature branch meanwhile.
2. **Or:** resolve by keeping `main`'s canonical #4c (`5001db21`) and dropping my redundant #4c, landing
   only my unique work — but reconcile the entangled `prime_contractor.py` carefully, ideally after the
   parallel agent pauses.

No merge was executed; nothing is in a conflicted state.

---

## 7. Outstanding (non-commit) items

- **Merge to main** — blocked on the duplicate-#4c reconciliation above.
- **Run-validation of #4c/#5** — unit-tested but not validated by a cap-dev-pipe generation run (#4c is
  a prompt-shape change; FR-MPF-5 suggests these ride a measurement gate).
- **#5 post-gen reachability** — wired into the micro-prime *file* pipeline (verified live); whether the
  disk-validation `convention_violations` also feed the *integration* repair routing end-to-end was
  asserted from `routing.py` but not traced to a fixture.
- **Leftover branch** `feat/forward-deployed-engineer` (redundant with the FDE already on `origin/main`) —
  deletable.
- **Pre-existing** `test_pip_alias_mapped` failure + ruff debt — not ours.

---

## 8. How to use / verify

```bash
# FDE on the latest run (auto-resolves newest run with a triage)
cd <project>; startd8 fde explain
startd8 fde preflight --plan docs/PLAN.md --requirements docs/REQUIREMENTS.md

# RUN-038 fixes — run the touched suites
cd startd8-sdk && source .venv/bin/activate
pytest tests/unit/fde tests/unit/test_import_resolution.py \
       tests/unit/repair/test_import_completion.py tests/unit/repair/test_convention.py \
       tests/unit/micro_prime/test_repair.py -q
```
