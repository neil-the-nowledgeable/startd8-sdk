# AL-100 Phase 1 Migration Checklist

Generated: 2026-02-27
Scope: `src/startd8/contractors/**/*.py` (including `__init__.py`, module-level logger vars, class-level logger attrs, and helper/fallback logger acquisition)

## Baseline Inventory

- Total Python files in scope: `48`
- Files with any logger acquisition (`get_logger(...)` or `logging.getLogger(...)`): `35`
- Files requiring migration in Phase 1 (policy violations): `20`
- Direct `logging.getLogger(...)` call sites: `21` across `15` files
- Non-allowlisted `get_logger("...")` call sites: `13` across `6` files
- Currently allowlisted `get_logger("...")` call sites: `1` (registry only)
- Currently compliant `get_logger(__name__)` files (no detected policy violations): `14`
- Files with no logger acquisition in scope: `13`

## Regeneration Commands

```bash
rg --files src/startd8/contractors -g '*.py' | wc -l

rg -n "\blogging\.getLogger\(" src/startd8/contractors -g '*.py' \
  | rg -v "Default:|``logging\.getLogger\(\)``"

rg -n "\bget_logger\(\"" src/startd8/contractors -g '*.py' \
  | rg -v "src/startd8/contractors/registry.py"

rg -n "\bget_logger\(__name__\)" src/startd8/contractors -g '*.py'
```

## A. Non-Compliant: Direct `logging.getLogger(...)`

All items below violate AL-100 and must migrate to `get_logger(...)`.

| Status | File | Line(s) | Notes |
|---|---|---|---|
| [ ] | `src/startd8/contractors/artisan_contractor.py` | 1419 | Dynamic per-workflow logger name |
| [ ] | `src/startd8/contractors/artisan_phases/context.py` | 966 | Module logger |
| [ ] | `src/startd8/contractors/artisan_phases/design_prompts/__init__.py` | 58 | Module logger |
| [ ] | `src/startd8/contractors/artisan_phases/design_prompts/seed_mapping.py` | 16 | Module logger |
| [ ] | `src/startd8/contractors/artisan_phases/domain_checklist.py` | 27, 306 | Module + class logger |
| [ ] | `src/startd8/contractors/artisan_phases/final_assembly.py` | 899 | Class-name logger |
| [ ] | `src/startd8/contractors/artisan_phases/final_testing.py` | 362 | Fixed string logger |
| [ ] | `src/startd8/contractors/artisan_phases/lessons_discovery.py` | 48 | Module logger |
| [ ] | `src/startd8/contractors/artisan_phases/plan_deconstruction.py` | 20 | Module logger |
| [ ] | `src/startd8/contractors/artisan_phases/prompts/__init__.py` | 29 | Module logger |
| [ ] | `src/startd8/contractors/artisan_phases/retrospective.py` | 434, 861, 1278 | Class loggers |
| [ ] | `src/startd8/contractors/artisan_phases/runner.py` | 95 | Fixed string logger |
| [ ] | `src/startd8/contractors/context_schema.py` | 21, 159 | Module + helper logger |
| [ ] | `src/startd8/contractors/context_strategy.py` | 19 | Module logger |
| [ ] | `src/startd8/contractors/forensic_log.py` | 552, 624, 646 | Debug/fallback direct logger calls |

## B. Non-Compliant: Non-Allowlisted `get_logger("...")`

Per AL-101 policy freeze, non-`__name__` logger names are non-compliant unless in the allowlist table.

| Status | File | Line(s) | Current Logger Name(s) |
|---|---|---|---|
| [ ] | `src/startd8/contractors/adapters/contextcore.py` | 25 | `startd8.contractors.contextcore` |
| [ ] | `src/startd8/contractors/adapters/standalone.py` | 28 | `startd8.contractors` |
| [ ] | `src/startd8/contractors/artisan_phases/development.py` | 523, 615, 1023, 2478, 3543, 3629, 3963 | `startd8.development.*` |
| [ ] | `src/startd8/contractors/artisan_phases/test_construction.py` | 1226 | `startd8.test_construction.llm_gen` |
| [ ] | `src/startd8/contractors/forensic_log.py` | 455, 622 | `startd8.forensic` |
| [ ] | `src/startd8/contractors/generators/lead_contractor.py` | 18 | `startd8.contractors.generators` |

## C. Current AL-101 Allowlisted Exception

| Status | File | Line(s) | Allowed Logger Name |
|---|---|---|---|
| [x] | `src/startd8/contractors/registry.py` | 30 | `startd8.contractors.registry` |

## D. Currently Compliant Files (`get_logger(__name__)`, No Detected Violations)

- `src/startd8/contractors/artisan_phases/design_documentation.py`
- `src/startd8/contractors/artisan_phases/self_consistency.py`
- `src/startd8/contractors/checkpoint.py`
- `src/startd8/contractors/context_resolution.py`
- `src/startd8/contractors/context_seed_handlers.py`
- `src/startd8/contractors/design_collision.py`
- `src/startd8/contractors/edit_first_gate.py`
- `src/startd8/contractors/gate_contracts.py`
- `src/startd8/contractors/handoff.py`
- `src/startd8/contractors/integration_engine.py`
- `src/startd8/contractors/postmortem.py`
- `src/startd8/contractors/prime_contractor.py`
- `src/startd8/contractors/queue.py`
- `src/startd8/contractors/review_call_graph_context.py`

## E. Files with No Logger Acquisition Detected

- `src/startd8/contractors/__init__.py`
- `src/startd8/contractors/adapters/__init__.py`
- `src/startd8/contractors/artisan_models.py`
- `src/startd8/contractors/artisan_phases/__init__.py`
- `src/startd8/contractors/artisan_phases/design_prompts/budget.py`
- `src/startd8/contractors/artisan_phases/design_prompts/modules.py`
- `src/startd8/contractors/artisan_phases/preflight.py`
- `src/startd8/contractors/artisan_prompts.py`
- `src/startd8/contractors/cli_helpers.py`
- `src/startd8/contractors/context_formatters.py`
- `src/startd8/contractors/generators/__init__.py`
- `src/startd8/contractors/prompt_utils.py`
- `src/startd8/contractors/protocols.py`

## Phase 1 Execution Checklist

- [ ] Migrate all Section A sites to `get_logger(...)`.
- [ ] Migrate Section B sites to `get_logger(__name__)` or expand allowlist with rationale.
- [ ] Re-run inventory commands and confirm Section A + B are empty.
- [ ] Update status counts in `ARTISAN_LOGGING_REQUIREMENTS.md` to match post-migration state.
