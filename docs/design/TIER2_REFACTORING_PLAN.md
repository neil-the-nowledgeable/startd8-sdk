# Tier 2 Refactoring Plan — `artifact_generator.py` & `micro_prime/templates.py`

**Status:** Planned (not started)
**Author:** generated 2026-06-01
**Context:** Follow-on to the completed TUI / code_manifest / cli refactors (Passes A–E).

---

## 1. Background & proven methodology

Five refactors have already landed on `main`, all using the same low-risk recipe:

| Pass | Target | Result |
|------|--------|--------|
| A | `tui_improved.py` helper classes | → `tui/` package (re-exports) |
| B | `ImprovedTUI` god-class | → 569-line shell + 14 mixins |
| C | 3 oversized mixins | → 17 focused mixins |
| D | `utils/code_manifest.py` models | → `code_manifest_models.py` (re-export) |
| E | `cli.py` command groups | → `cli_<group>.py` + `cli_shared.py` |

**The recipe (reuse it for Tier 2):**

1. **Move verbatim.** Cut whole functions/classes by AST line range; never hand-edit bodies.
2. **Keep depth constant when possible.** If new modules sit at the *same package depth* as the
   original (e.g. top-level `cli_*.py` siblings, or siblings inside the same subpackage), **no
   relative-import re-leveling is needed** and moved code is byte-identical. Only go one level
   deeper (a new subpackage) if you accept a `+1 dot` rewrite of every relative import in the
   moved code (line-based, safe — verified in Pass B).
3. **Break cycles with a `_shared` module.** Shared constants/helpers used by multiple new modules
   go into a leaf module that everything imports; the original module imports them back.
4. **Preserve the public surface with re-exports.** The original module re-imports the moved
   symbols so existing import sites stay green. `from .x import *` covers public (non-`_`) names;
   **underscore symbols that external code imports must be re-exported explicitly.**
5. **Verify with the standard harness** (see §4).

---

## 2. Candidate 1 — `micro_prime/templates.py` (1,543 lines)

### 2.1 Current shape
- 3 classes: `CodeTemplate`, `TemplateMatch`, `TemplateRegistry` (~102 lines).
- 98 functions, cleanly clustered **by language**: Go (20), Java (16), C# (16), Python `_template_*`
  (15), Node/JS (12), plus shared matchers (`_is_*`, 8) and utilities (`_safe_*`, `_try_*`).
- 5 module constants: `logger`, `_DFA_STUB_PATTERNS`, `_DFA_STUB_PASS`, `_APP_INSTANCE_NAMES`,
  `_FRAMEWORK_IMPORTS`.
- Per-language registry lists assembled at module level: `GO_TEMPLATES = [CodeTemplate(name="go_constructor",
  match_fn=_go_constructor_match, render_fn=_go_constructor_render), ...]`, plus `JAVA_TEMPLATES`,
  `CSHARP_TEMPLATES`, `NODEJS_TEMPLATES`, `TEMPLATES` (aggregate).

### 2.2 Why it is Tier 2 (not Tier 1)
- **Registry wiring couples lists to functions.** Each `*_TEMPLATES` list references that language's
  `_match`/`_render` functions. List + functions must move together as a unit.
- **Heavy, varied consumer surface.** ~10 production modules import from it (`cli_workflow`,
  `implementation_engine/spec_builder`, `workflows/scaffold`, `plan_ingestion_*`,
  `project/scaffolder`, `micro_prime/{__init__,classifier,clause_mapper}`). Imported symbols include
  `TemplateRegistry`, the per-language lists (`GO_TEMPLATES`, `JAVA_TEMPLATES`, `CSHARP_TEMPLATES`,
  `NODEJS_TEMPLATES`, `TEMPLATES`), and `try_template_match_with_name`. **All must remain importable
  from `micro_prime.templates`.**
- **Shared matcher/util coupling.** `_safe_*`, `_is_*`, and `_DFA_STUB_*`/`_FRAMEWORK_IMPORTS`
  constants are used across multiple languages.

### 2.3 Target layout (subpackage)
```
micro_prime/templates/
  __init__.py        # re-exports the full public surface (see §2.5); was templates.py
  _shared.py         # CodeTemplate, TemplateMatch, shared constants, _safe_*/_is_* matchers
  python.py          # _template_* fns + (PYTHON) TEMPLATES contribution
  go.py              # _go_* fns + GO_TEMPLATES
  java.py            # _java_* fns + JAVA_TEMPLATES
  csharp.py          # _csharp_* fns + CSHARP_TEMPLATES
  nodejs.py          # _js_* fns + NODEJS_TEMPLATES
  registry.py        # TemplateRegistry, TEMPLATES aggregate, try_template_match_with_name, generate
```
Converting `templates.py` → `templates/__init__.py` puts submodules **one level deeper**, so every
relative import inside moved code needs the `+1 dot` rewrite (`from .x` → `from ..x`). This is the
Pass-B transform and is safe (line-based; verified no string collisions in that pass — re-check here).

> **Lower-risk alternative:** keep `templates.py` and add same-depth siblings
> `micro_prime/templates_go.py`, `_java.py`, etc. Then **no dot-rewrite** is needed (Pass-E style),
> at the cost of a less tidy module layout. Recommended if the dot-rewrite re-check surfaces any
> ambiguity.

### 2.4 Dependency order (acyclic)
`_shared` ← {`python`,`go`,`java`,`csharp`,`nodejs`} ← `registry` ← `__init__`.
The language modules import `CodeTemplate`/matchers/constants from `_shared`; `registry` imports the
per-language `*_TEMPLATES` lists; `__init__` re-exports everything.

### 2.5 Public re-export surface (must stay green)
`__init__.py` must export at minimum: `TemplateRegistry`, `CodeTemplate`, `TemplateMatch`,
`GO_TEMPLATES`, `JAVA_TEMPLATES`, `CSHARP_TEMPLATES`, `NODEJS_TEMPLATES`, `TEMPLATES`,
`try_template_match_with_name`, `generate`, `is_trivial`. Build the exact list by running:
```
grep -rhoE "from .*micro_prime\.templates import [^\n]*" src tests | sort -u
```
and assert every name resolves on `micro_prime.templates` after the split.

### 2.6 Step plan
1. AST-extract the 5 language clusters + their `*_TEMPLATES` lists + the shared core.
2. Write `_shared.py` (models, constants, shared matchers/utils).
3. Write each language module (functions + its list), `+1 dot` rewrite relative imports.
4. Write `registry.py` (TemplateRegistry, TEMPLATES aggregate, dispatch fns).
5. Convert `templates.py` → `templates/__init__.py` with `from .registry import *`,
   `from .go import GO_TEMPLATES`, … plus explicit re-exports for any `_`-prefixed public imports.
6. Run §4 verification.

### 2.7 Estimated reward
1,543 → ~150-line `__init__` + 6 modules each ≤ ~400 lines. Language-isolated templates become
independently editable/testable.

---

## 3. Candidate 2 — `observability/artifact_generator.py` (3,083 lines)

### 3.1 Current shape
- 7 model dataclasses: `ConventionMetric`, `ServiceHints`, `BusinessContext`, `DerivationTrace`,
  `ArtifactResult`, `GenerationReport`, `ArtifactTypeSpec`.
- 61 functions, dominated by 8 public artifact generators: `generate_alert_rules`,
  `generate_dashboard_spec`, `generate_slo_definitions`, `generate_service_monitor`,
  `generate_notification_policy`, `generate_loki_rule`, `generate_runbook`,
  `generate_capability_index` — each with a fan of private helpers (e.g. dashboards have
  `_panel_*`, `_domain_*`, `_assign_gridpos`, `_ensure_red_coverage`).
- 11 module constants: `_DEFAULT_THRESHOLDS`, `_IMPLEMENTED_ARTIFACT_TYPES`,
  `_ALWAYS_PRODUCED_DECLARED_TYPES`, `_COMPOSITE_*_WEIGHT`, `_REQ_ID_PATTERN`, `_RUN_ID_PATTERN`,
  `_NON_SERVICE_NAMES`, `_ARTIFACT_TYPE_TO_CATEGORY`, `_CAPABILITY_INDEX_EXCLUDE`,
  `_EXTENDED_PER_SERVICE_GENERATORS`.

### 3.2 Why it is Tier 2
- **Shared constants + cross-generator helpers.** Threshold/severity/naming helpers
  (`_resolve_threshold`, `_severity_for`, `_prom_name`, `_metric_unit`, `_utc_now_iso`,
  `_derivation_comment`) and several constants are used by multiple generators → must live in a
  shared module (Pass-B `_shared` pattern), not duplicated.
- **Consumers import PRIVATE helpers.** `observability/portal_spec_builder.py` and tests import
  `_domain_panel_group`, `_domain_metric_type`, `_domain_query`, `_append_to_provenance`, plus models
  `ArtifactResult`, `GenerationReport`. **`import *` will NOT re-export these `_`-prefixed names** —
  they must be re-exported **explicitly** in the assembling module, or the consumers updated to import
  from the new submodule. Prefer explicit re-export to keep consumer diffs at zero.

### 3.3 Target layout (subpackage)
```
observability/artifact_generator/
  __init__.py        # re-exports full surface (incl. explicit private re-exports)
  models.py          # the 7 dataclasses
  _shared.py         # 11 constants + cross-cutting helpers (_resolve_threshold, _severity_for,
                     #   _prom_name, _metric_unit, _utc_now_iso, _derivation_comment, naming, etc.)
  context.py         # extract_service_hints, load_business_context, load_onboarding_metadata,
                     #   classify_route_state(s), resolve_artifact_spec
  alerts.py          # generate_alert_rules + _alert_*
  dashboards.py      # generate_dashboard_spec + _panel_*/_domain_*/_assign_gridpos/_ensure_red_coverage
  slos.py            # generate_slo_definitions
  monitors.py        # generate_service_monitor, generate_notification_policy, generate_loki_rule
  docs.py            # generate_runbook, generate_capability_index
```
Same depth note as §2.3 applies: subpackage ⇒ `+1 dot` rewrite of relative imports in moved code.

### 3.4 Dependency order (acyclic)
`models` + `_shared` ← {`context`,`alerts`,`dashboards`,`slos`,`monitors`,`docs`} ← `__init__`.
Watch `dashboards.py`: it owns the largest helper fan (`_domain_*`, `_panel_*`) — confirm none of
those are also called by `alerts`/`slos`; if shared, push them into `_shared.py`.

### 3.5 Public re-export surface (must stay green)
Derive exactly via:
```
grep -rhoE "from .*artifact_generator import [^\n]*" src tests | sort -u
```
Known so far: `ArtifactResult`, `GenerationReport`, **`_domain_panel_group`, `_domain_metric_type`,
`_domain_query`, `_append_to_provenance`** (private — explicit re-export required), and the 8
`generate_*` functions. Add an `__all__` to `__init__.py` documenting the contract.

### 3.6 Step plan
1. Confirm production importers (currently just `portal_spec_builder.py`) + the 4 test files.
2. Extract `models.py` first (lowest risk, like Pass D), verify, optionally land separately.
3. Extract `_shared.py` (constants + cross-cutting helpers); run the cross-generator helper-usage
   check to place each helper correctly.
4. Extract one generator module at a time (`alerts` → verify → `dashboards` → …), each followed by
   the §4 harness, so a break is isolated to one small step.
5. Assemble `__init__.py` with `from .X import *` **plus explicit `_`-prefixed re-exports**.

### 3.7 Estimated reward
3,083 → ~100-line `__init__` + 8 modules, largest (`dashboards.py`) ~600–800 lines. Each artifact
type becomes independently reviewable; the shared threshold/naming logic gets a single home.

---

## 4. Standard verification harness (run for every step)

Reuse exactly what gated Passes B–E. From the worktree:

```bash
# 1. compiles
python3 -m py_compile src/startd8/<...>/*.py

# 2. byte-faithfulness — every moved def identical to pre-refactor (modulo +1-dot import rewrite)
#    (AST-extract each function block from old vs new; assert zero mismatches)

# 3. public surface intact — every symbol any consumer imports still resolves on the original path
grep -rhoE "from .*<module> import [^\n]*" src tests | sort -u   # build expected set, assert hasattr

# 4. functional smoke
#    templates:  exercise TemplateRegistry + try_template_match_with_name on a sample element
#    artifacts:  call each generate_* and portal_spec_builder on a fixture

# 5. dependent test suites
python3 -m pytest tests/unit/observability tests/unit/micro_prime -q     # adjust per target

# 6. logger-acquisition policy (new modules must NOT use string getLogger; use get_logger(__name__)
#    in a leaf module and import the logger, per CLAUDE.md)
python3 -m pytest tests/unit/contractors/test_logger_acquisition_policy.py -q

# 7. collection-error parity — must stay at the repo baseline (16 as of 2026-06-01); zero new
python3 -m pytest tests/ --co -q 2>&1 | grep -c "^ERROR"
```

**Guardrails / gotchas (learned in Passes A–E):**
- Compare against a **clean baseline** before claiming a failure is yours — the repo carries
  ~16 pre-existing collection errors and at least two flaky/failing tests
  (`test_symtable_overhead_under_10ms`, `forward_manifest_validator_disk::test_pass_after_docstring`)
  unrelated to refactoring.
- Tests that assert on a module's **own structure** (e.g. "manifest of own source contains X") will
  legitimately break when symbols move — update them (see Pass D's `test_manifest_of_models_source`).
- `import *` skips `_`-prefixed names — re-export private symbols **explicitly** where consumers need
  them (the artifact_generator case).
- Each pass: own worktree + branch → commit → `--no-ff` merge → remove worktree. `main` advances
  under you (parallel run-009 work); rebase/merge is fine since these files are untouched there.

## 5. Recommended sequencing
1. **`artifact_generator/models.py` extraction first** — Pass-D-clean (pure dataclasses), smallest,
   builds confidence and can land standalone.
2. **Rest of `artifact_generator`** generator-by-generator.
3. **`templates.py`** last — highest consumer fan-out, so most re-export surface to validate.
