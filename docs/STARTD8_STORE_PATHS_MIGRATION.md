# `.startd8` store-path migration — status + how to proceed safely

The `.startd8` store-dir literal was scattered across the SDK with no shared home. This note records
what's been consolidated, what remains, and **exactly how to finish it safely** — validated by a spike
(see the bottom). Produced by the `/complexity-distiller` S1 pass.

## The home (use this — don't re-type the literal)

`src/startd8/paths.py` is the single source of truth:

| Helper | Returns | Use for |
|--------|---------|---------|
| `STARTD8_DIRNAME` | `".startd8"` | the bare name (relative paths, default-arg values) |
| `startd8_dir(base)` | `base / ".startd8"` | a `.startd8` under **any** base (project root, `~`) |
| `default_data_dir()` | `Path.cwd() / ".startd8"` | project-scoped data root |
| `default_config_dir()` | `Path.home() / ".startd8"` | user-scoped config root |

`paths.py` is a **leaf module** (imports only stdlib) → importing it anywhere is **cycle-safe**.

## Done

| Batch | Commit | Scope |
|-------|--------|-------|
| SDK home + core | `0477b95e` | `paths.py` DRY + constant/helper; `framework.py`, `config.py` adopt |
| Kickoff feature group | `ed4a45d1` | `kickoff_experience/*` via `kickoff_experience/paths.py` (re-exports the SDK home) |
| Config family (`~/.startd8`) | `474e3ce9` | 16 files → `default_config_dir()` |
| CLI + project entry points | `b94deabe` | 7 files → `default_data_dir()` / `startd8_dir(root)` |

## Remaining (≈70 sites, ~35 files) — the contractor/pipeline tail

Pervasive project-data `.startd8` in the **construction engine**: `contractors/` (`prime_contractor` ~7,
`integration_engine` 3, `context_seed/phases/implement` ~7, `artisan_*`, `prime_contractor_config`),
`repair/`, `workflows/builtin/`, `benchmark_matrix/`, `micro_prime/`, `utils/manifest_*`, `project/init`,
plus small stores (`consultation/`, `stakeholder_panel/`, `requirements_panel/`, `manifest_suggester/`,
`persona_drafting/`, `service_assistant/`).

**Recommendation: migrate opportunistically, not in a big-bang sweep.** The essential distillation (one
home, adopted where it matters) is done. The tail is high-churn / low-marginal-value / some-risk (core
construction code). Per the Zero-Value-Precision anti-principle, don't perfect the means past user value —
route these when a file is touched for a real reason. The home is discoverable, so new code won't re-scatter.

## How to proceed safely (per-subsystem playbook)

Do **one subsystem per commit**, each guarded by that subsystem's own test suite.

1. **Ground first** — `grep -n '"\.startd8"' src/startd8/<subsystem>/`. Classify each site:
   - `project_root / ".startd8" / X`  →  `startd8_dir(project_root) / X`
   - `Path.cwd() / ".startd8"`        →  `default_data_dir()`
   - `Path.home() / ".startd8"`       →  `default_config_dir()`
   - `Path(".startd8") / X`  (**relative!**)  →  `Path(STARTD8_DIRNAME) / X`   ← the trap
   - `base_dir: str = ".startd8"` (default-arg value)  →  `= STARTD8_DIRNAME`
2. **Exclude the false positives.** `{".startd8", "dist", "build", …}` **scan-exclusion sets** are NOT
   store paths — leave them (`concierge/core.py`, `complexity/signals.py`, `forward_manifest_extractor.py`,
   `model_comparison.py`, `stakeholder_panel/facilitation.py`, `observability/…`, `validators/…`,
   `utils/manifest_cache.py`, `manifest_suggester`… the `_SKIP_DIRS`-style constants).
3. **Add the import** at the right depth (`from .paths import …` at top-level; `from ..paths import …`
   one level down; `from ...paths import …` two levels). Cycle-safe.
4. **Clean up after yourself** — after replacing, `Path` or `Path.cwd`/`Path.home` may become unused;
   remove the now-dead `from pathlib import Path` (ruff `F401`).
5. **Verify (behaviour-identical):**
   - import every changed module (catches undefined names / broken imports),
   - assert value-equivalence for a couple of resolved paths (incl. any relative one),
   - run the subsystem's test suite,
   - `ruff check` the changed files — isolate NEW `F401`/`F821` from the module's pre-existing lint debt.
6. **Merge** via the safe rebase → atomic FF-push pattern (shared `origin/main`); one subsystem per PR.

### Gotchas the spike surfaced
- **Relative-fallback trap:** `Path(".startd8")` is cwd-relative — `startd8_dir(Path("."))` would give
  `./.startd8`, changing behaviour. Use `Path(STARTD8_DIRNAME)` for these. (Seen at `repair/staging.py`.)
- **Substring safety:** replacing `project_root / ".startd8"` → `startd8_dir(project_root)` correctly
  handles all trailing subdirs (`… / "state"`, `… / "repair" / "artifacts"`) in one swap.
- **Pre-existing failures/lint:** these modules carry pre-existing debt (unused imports; a broken
  `test_cli_compare_models_e2e`, `test_skill_aware_workflow` import error). Confirm any red is pre-existing
  (stash your change, re-run) before blaming the migration. Don't fix unrelated debt in the same commit.
- **Test env:** OTel span-recording tests fail under `STARTD8_OTEL=disabled` — that's the env, not your
  change; run those without force-disabling OTel.

## Spike evidence (repair/, applied then reverted — not committed)

Validated the playbook on `repair/` (5 sites across `staging.py` + `orchestrator.py`, incl. the relative
fallback): transform applied → 0 raw literals left, imports OK, value-equivalence held (relative fallback
preserved as `.startd8/repair`, not `./.startd8/repair`), **637 repair tests passed**. Reverted. Conclusion:
the mechanical transform is behaviour-identical and the subsystem test suites are a sufficient guard —
proceed subsystem-by-subsystem whenever these files are next touched.
