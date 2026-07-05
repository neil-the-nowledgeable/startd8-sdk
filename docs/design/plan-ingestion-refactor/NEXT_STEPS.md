# Plan-Ingestion `_execute` Decomposition — Next Steps / Handoff

**As of:** 2026-07-04 (end of session)
**Branch:** `refactor/plan-ingestion-execute` (pushed to origin) · **Worktree:** `~/Documents/dev/startd8-planingest`
**Plan:** `PLAN.md` v1.1 (CRP-hardened) · **This doc:** resume Stage 4 cold.

---

## 1. TL;DR state

`_execute` (the #1 active god-method): **1,176 → 901 lines** so far.

| Stage | What | Status |
|---|---|---|
| 0 | Golden safety net (success + forced-`_fail` forensics) | ✅ **merged to main** |
| 1 | `_finalize_success` extracted | ✅ merged |
| CRP R1 | Code-grounded review, all 9 accepted (plan v1.1) | ✅ merged |
| 2 | `_IngestionRun` context + closures → `_rt_*` methods | ✅ merged |
| 3 | Setup sub-blocks (`_validate_entry_capabilities` / `_resolve_kaizen_threshold` / `_load_mottainai_capabilities`) | ✅ merged |
| **4a** | **DISCOVER + PREFLIGHT extracted; span-owning pattern PROVEN (OTel-verified)** | ✅ **on branch** (`60209995`, not merged) |
| 4b | MANIFEST · PARSE · ASSESS · TRANSFORM · REFINE · EMIT | ⏳ **remaining** |

**Everything through Stage 3 is on `origin/main`.** Stage 4a is on the branch only.

## 2. What's extracted vs. still inline in `_execute`

Extracted phase helpers: `_discover_contextcore_yaml` (DISCOVER), `_run_preflight` (PREFLIGHT).
Phase *logic* already lived in methods (do not touch): `_phase_parse/assess/transform/refine/emit`.

Still-inline glue blocks in `_execute` (anchor by the `# --- <PHASE> ---` marker, not L-numbers):

| Phase | Has phase span? | Notable traps |
|---|---|---|
| **MANIFEST** | No (optional load) | Simplest remaining — likely like DISCOVER (no span, no early-exit). Do first. |
| **PARSE** | Yes (`ingestion.parse`) | Acyclicity gate + degenerate-parse handling + **3 early-exit shapes** in one block (mid-span `return _rt_fail`, explicit-close-then-return, deferred cost-cap). Widest. |
| **ASSESS** | Yes | low-quality handling; "did not produce a route" `_rt_fail`; deferred cost-cap. |
| **TRANSFORM** | Yes | Smallest span-phase (1 `_phase_transform` call + 1 direct `_rt_fail` + 1 deferred cost-cap). Good second target after MANIFEST. |
| **REFINE** | Yes | **R1-S7 trap (do NOT reorder):** `state.total_cost += refine_cost` → zero-round guard clears `review_output` → **kaizen `persist_prompt_response` FILE WRITES** → `design_snapshot` → `check_cost("refine")` → span close → deferred return. The file-writes must stay *before* the cost-cap return. Do LAST. |
| **EMIT** | Yes | traceability; produces `emit_result` consumed by `_finalize_success`. |

## 3. The proven extraction recipe (apply per remaining phase)

Established + OTel-verified in Stage 4a (`_run_preflight` is the template).

1. **Signature:** `def _run_<phase>(self, run: "_IngestionRun", *, <inputs>) -> tuple[<outputs...>, WorkflowResult | None]`.
   - `<inputs>` = every local the block reads (root_span + the phase's config locals + prior-phase outputs).
   - `<outputs>` = every local the block produces that the pipeline uses downstream.
   - Last tuple element = the early-exit signal: **non-None `WorkflowResult` means "propagate it"**.
2. **Own the span with a `with` block (R1-S3):**
   ```python
   with _tracer.start_as_current_span("ingestion.<phase>") as _span:
       root_span.add_event("state.transition", {"phase": "<phase>"})
       run.progress("<Phase>")
       ...phase glue + self._phase_<x>(...)...
       # set _span attrs
   # span closed here (matches the old explicit __exit__/outer-finally, UNSET status)
   if <error>:
       return <Nones...>, self._rt_fail(run, <msg>)   # _rt_fail AFTER the with (parenting preserved)
   return <outputs...>, None
   ```
   - Replaces the manual `_active_phase_ctx = _tracer.start_as_current_span(...)` / `.__enter__()` / `.__exit__(None,None,None)` / deferred-close asymmetry.
   - For the **deferred cost-cap** shape: `cost_err = self._rt_check_cost(run, "<phase>")` inside/after the `with` as the original ordered it, then `return <Nones...>, cost_err` (which is None or a WorkflowResult) — do NOT drop it.
3. **Shared-by-reference (Stage 2):** `steps.append(...)` → `run.steps.append(...)`; `state`/`_forensics` stay the same objects via `run`. Don't rewrite `state.x` / `_forensics[...]` sites.
4. **Caller in `_execute`:**
   ```python
   <outputs...>, _early = self._run_<phase>(run, root_span=root_span, ...)
   if _early is not None:
       return _early
   ```
5. **When all phases are extracted:** the outer `_active_phase_ctx` tracking + the `finally: if _active_phase_ctx is not None: _active_phase_ctx.__exit__(...)` (L~5098) become dead — remove them (each phase now owns its span). The root-span `_root_span_ctx.__exit__` at the very end stays.

**Target:** `_execute` → ~150–200 lines (construct-run + `_build`/`_run_*` calls + return).

## 4. Safety net — run between EVERY phase extraction

```bash
cd ~/Documents/dev/startd8-planingest && export PYTHONPATH=src   # pin to THIS worktree
# the two decisive gates: both goldens + the OTel span test
python3 -m pytest tests/unit/test_plan_ingestion_golden.py tests/unit/test_plan_ingestion_otel.py -q -p no:cacheprovider
# broader phase surface + baseline
python3 -m pytest tests/unit/test_deterministic_parse_and_forensics.py tests/unit/test_plan_ingestion_preflight.py \
  tests/unit/test_plan_ingestion_manifest.py tests/unit/test_plan_ingestion_v01_format.py \
  tests/unit/test_seed_bloat_guards.py tests/unit/test_refine_yaml_corruption_guard.py -q -p no:cacheprovider
python3 -m ruff check --select F821,F811 src/startd8/workflows/builtin/plan_ingestion_workflow.py   # ignore pre-existing _logger/TaskTrackingConfig/PhaseEmitter
```
- **`test_plan_ingestion_golden.py`** — both artifacts goldens (success + forced-`_fail` forensics). Catches any behavioral drift; regen with `STARTD8_REGEN_GOLDEN=1` only for *intended* changes.
- **`test_plan_ingestion_otel.py`** — the span-lifecycle gate. Non-negotiable for the `with`-per-phase change.
- ruff catches missed params (it caught a missing `state`/`dataclass` earlier before tests even ran).

## 5. Gotchas (bit us this session)

- **pytest-cov SEGFAULTS under Python 3.14** on the large plan-ingestion test set — use **plain pytest** (no `--cov`). Coverage is not needed for the golden-guarded workflow.
- **~15 PRE-EXISTING failures** in `test_plan_ingestion_workflow.py` (`ContextContract` pydantic drift). Verified identical on the parent commit — **not this refactor**. Bar is "no NEW failures vs. parent," not "full green."
- **Multi-worktree hazard:** always `PYTHONPATH=src` pinned to this worktree; `git fetch` + check `origin/main` before any git op (it drifts between turns from concurrent agents).
- **Pre-existing F821s** (`_logger`, `TaskTrackingConfig`, `PhaseEmitter`) and F401s (`ast`, `Set`) are on origin/main — not introduced here; leave them.

## 6. Landing Stage 4 + broader backlog

- **Land 4a (and each 4b increment):** `origin/main` was a clean FF this session — but re-verify: `git fetch` → `git merge-base --is-ancestor origin/main HEAD` → if FF, `git push origin HEAD:main`; if diverged, worktree-off-`origin/main` + cherry-pick/merge + FF-push (never push a stale branch tip — it reverts others' work).
- **Broader god-file backlog** (on main): `docs/design/context-seed-refactor/FORWARD_LOOKING_ANALYSIS.md` — after plan-ingestion, the next candidates are `integration_engine.integrate` (947-line method, NR-6) and the compat-wrapper retirement (NR-7). The Artisan "quarantine" idea largely collapsed under an import-reachability check (see that doc §4.1).
- **context_seed refactor Part B** (method decomposition inside the extracted handlers) is also unfinished — separate branch, lower priority.
