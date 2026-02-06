# Downstream Workaround Catalog

**Date:** 2026-02-06
**Purpose:** Catalog of monkey patches, defensive workarounds, and overrides used in
downstream projects to work around startd8 SDK limitations. Each entry is a candidate
for an SDK-level fix.

**Projects surveyed:**
- `contextcore-demo-retail` (personas/run_prime_contractor.py, personas/clean_workspace.py)
- `ContextCore` (scripts/lead_contractor/, scripts/run_lead_contractor*.py)
- `wayfinder` (scripts/lead_contractor/, scripts/run_lead_contractor*.py)

---

## Status Legend

| Status | Meaning |
|--------|---------|
| **FIXED** | Already resolved in SDK (commit `ebc9e66`) |
| **OPEN** | Still needs an SDK-level fix |
| **WONTFIX** | Expected behavior or not an SDK concern |

---

## W-001: SafeCodeGenerator subclass (monkey-patch + subclass override)

| Field | Value |
|-------|-------|
| **Status** | FIXED |
| **Project** | contextcore-demo-retail |
| **File** | `personas/run_prime_contractor.py:32-153` |
| **Type** | Subclass override + module-level monkey-patch |
| **Fixed in** | `ebc9e66` (LeadContractorCodeGenerator params + resolve_agent_spec **agent_config) |

**Problem:** `LeadContractorCodeGenerator` hardcoded `max_tokens=16384` and
`fail_on_truncation=True` with no way to override. `resolve_agent_spec` didn't
forward `max_tokens` to providers.

**Workaround:** `SafeCodeGenerator` subclass that:
1. Accepts `max_tokens`, `fail_on_truncation`, `check_truncation`, `strict_truncation`
2. Monkey-patches `wf_mod.resolve_agent_spec` at runtime to inject `max_tokens` on
   every created agent

```python
# The monkey-patch (lines 64-78):
_orig_resolve = wf_mod.resolve_agent_spec
def _resolve_with_tokens(spec, *, name=None, validate=True):
    agent = _orig_resolve(spec, name=name, validate=validate)
    agent.max_tokens = desired_max_tokens
    return agent
wf_mod.resolve_agent_spec = _resolve_with_tokens
```

**SDK fix applied:** `LeadContractorCodeGenerator` now accepts all four params.
`resolve_agent_spec` now accepts `**agent_config` and forwards to `create_agent()`.
`LeadContractorWorkflow._execute()` reads `config["max_tokens"]` and passes it through.

---

## W-002: Post-construction size limit overrides

| Field | Value |
|-------|-------|
| **Status** | FIXED |
| **Project** | contextcore-demo-retail |
| **File** | `personas/run_prime_contractor.py:187-189` |
| **Type** | Post-construction attribute override |
| **Fixed in** | `ebc9e66` (PrimeContractorWorkflow constructor params) |

**Problem:** `PrimeContractorWorkflow` hardcoded `max_lines_per_feature=150` and
`max_tokens_per_feature=500` with no constructor params.

**Workaround:**
```python
wf = PrimeContractorWorkflow(...)
wf.max_lines_per_feature = 300   # override hardcoded 150
wf.max_tokens_per_feature = 1000 # override hardcoded 500
```

**SDK fix applied:** Both are now constructor parameters with the same defaults.

---

## W-003: External clean_workspace.py script

| Field | Value |
|-------|-------|
| **Status** | FIXED |
| **Project** | contextcore-demo-retail |
| **File** | `personas/clean_workspace.py` (165 lines) |
| **Type** | External compensating script |
| **Fixed in** | `ebc9e66` (PrimeContractorWorkflow.clean_workspace()) |

**Problem:** `--reset-state` only deletes the queue state JSON. Generated code
staging area, target files with accumulated AST-merge layers, `.backup` files,
and `__pycache__` directories all persist, causing bloat on re-runs.

**Workaround:** Standalone script that deletes `generated/`, target lib files,
`.backup` files, `__pycache__`, and state JSON.

**SDK fix applied:** `PrimeContractorWorkflow.clean_workspace(include_targets=False)`
method removes `generated/`, `.backup`, and `__pycache__`. Optional `include_targets=True`
also removes target files from the queue.

---

## W-004: AST merge accumulation (silent corruption)

| Field | Value |
|-------|-------|
| **Status** | FIXED |
| **Project** | contextcore-demo-retail |
| **File** | Documented in `personas/STARTD8_SDK_FIXES.md` |
| **Type** | Silent data corruption across re-runs |
| **Fixed in** | `ebc9e66` (ASTMergeStrategy accumulation detection + merge_mode) |

**Problem:** Each run's AST merge adds new definitions on top of existing ones.
Files grew from ~120 to 1078 lines across 3 runs (e.g., `loader.py` gained
`PersonaDataLoader` + `PersonaLoader` + standalone `load_roles()` from different runs).

**SDK fix applied:** `ASTMergeStrategy.merge()` now warns when target has >= 2x the
source's class/function definitions. New `merge_mode="replace"` option overwrites
target instead of additive merging.

---

## W-005: Relative target_files path ValueError

| Field | Value |
|-------|-------|
| **Status** | FIXED |
| **Project** | contextcore-demo-retail |
| **File** | `personas/run_prime_contractor.py:202-208` |
| **Type** | Wrapper function to normalize paths |
| **Fixed in** | `integrate_feature()` resolves relative paths + `_rel_display()` helper |

**Problem:** `PrimeContractorWorkflow.integrate_feature()` calls
`target_path.relative_to(project_root)` for display. If `target_files` are relative
strings, `Path(rel).relative_to(abs_root)` raises `ValueError`.

**Workaround:**
```python
def _abs(rel_path: str) -> str:
    p = Path(rel_path)
    return str(p if p.is_absolute() else (workflow.project_root / p))

q.add_feature("F1", "desc", target_files=[_abs("src/foo.py")])
```

**SDK fix applied:** `integrate_feature()` now resolves relative target paths against
`self.project_root`. All display calls use `_rel_display()` which falls back to
the full path on `ValueError`.

---

## W-006: Defensive WorkflowResult attribute access

| Field | Value |
|-------|-------|
| **Status** | FIXED |
| **Project** | ContextCore, wayfinder |
| **Files** | `ContextCore/scripts/run_lead_contractor_tui.py:966-1005`, `wayfinder/scripts/run_lead_contractor_tui.py:966-1005` |
| **Type** | Defensive programming pattern (hasattr/getattr/try-except) |
| **Fixed in** | `WorkflowResult.from_error()` now defaults `metrics` to `WorkflowMetrics()` |

**Problem:** `LeadContractorWorkflow.run()` returns a `WorkflowResult` that consumers
access with triple-defense patterns, suggesting the schema was unstable at some point:

```python
output = result.output if (hasattr(result, 'output') and result.output) else {}
if hasattr(result, 'metrics') and result.metrics:
    try:
        total_cost = result.metrics.total_cost if hasattr(result.metrics, 'total_cost') else 0
    except (AttributeError, TypeError):
        total_cost = 0
```

**Assessment:** `WorkflowResult` and `WorkflowMetrics` are `@dataclass` types with
explicit fields (`output`, `metrics`, `error`, `success`). The defensive patterns were
triggered because `from_error()` passed `metrics=None`, bypassing the `default_factory`.

**SDK fix applied:** `from_error()` now uses `metrics or WorkflowMetrics()` instead of
bare `metrics`, guaranteeing `result.metrics` is never `None`. Downstream code can
safely access `result.metrics.total_cost` without `hasattr` guards.

---

## W-007: Metrics token extraction with getattr fallbacks

| Field | Value |
|-------|-------|
| **Status** | OPEN |
| **Project** | ContextCore, wayfinder |
| **Files** | `ContextCore/scripts/lead_contractor/runner.py:121-131`, `wayfinder/scripts/lead_contractor/runner.py:121-131` |
| **Type** | Defensive getattr() usage |

**Problem:** `WorkflowMetrics` fields accessed via `getattr(result.metrics, "input_tokens", 0)`,
suggesting the object sometimes lacks expected attributes.

```python
input_tokens = getattr(result.metrics, "input_tokens", 0) or 0
output_tokens = getattr(result.metrics, "output_tokens", 0) or 0
model = getattr(result.metrics, "model", "") or LEAD_AGENT
```

**Assessment:** `WorkflowMetrics` is a dataclass with `input_tokens: int = 0` and
`output_tokens: int = 0`, so these fields always exist. However, `model` is **not** a
field on `WorkflowMetrics` — the consumers are reaching for a field that doesn't exist.

**Suggested SDK fix:** Either add `model: str = ""` to `WorkflowMetrics`, or document
that model info lives in `WorkflowResult.metadata["lead_agent"]` / step-level
`StepResult.agent_name`. The `or 0` guard after `getattr` suggests the field sometimes
returns `None` even when present.

---

## W-008: Manual sys.path manipulation for SDK import

| Field | Value |
|-------|-------|
| **Status** | WONTFIX |
| **Project** | ContextCore, wayfinder |
| **Files** | `ContextCore/scripts/lead_contractor/config.py:12-18`, `wayfinder/scripts/lead_contractor/config.py:12-18`, plus 4 other scripts |
| **Type** | sys.path.insert() before import |

**Problem:** SDK not always pip-installed; scripts manually add it to sys.path:
```python
STARTD8_SDK_PATH = Path(os.environ.get("STARTD8_SDK_PATH", PROJECT_ROOT.parent / "startd8-sdk" / "src"))
sys.path.insert(0, str(STARTD8_SDK_PATH))
```

**Assessment:** This is a development-time convenience, not an SDK bug. The SDK
installs fine via `pip install -e .` and is published to PyPI. The path manipulation
exists because these scripts run from repos that don't declare startd8 as a dependency.

---

## W-009: Markdown code fence stripping in integration

| Field | Value |
|-------|-------|
| **Status** | OPEN (partial) |
| **Project** | wayfinder |
| **File** | `wayfinder/scripts/lead_contractor/integrate_backlog.py:880-904` |
| **Type** | Post-processing cleanup function |

**Problem:** Generated code sometimes arrives wrapped in markdown fences even after
passing through the workflow.

**Workaround:**
```python
def clean_markdown_code_blocks(content: str) -> str:
    lines = content.split('\n')
    if lines and lines[0].strip().startswith('```'):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)
```

**Assessment:** The SDK's `_extract_code_from_response()` (lead_contractor_workflow.py:1438-1495)
already strips code fences from LLM responses. This workaround may be needed for code
that bypasses the workflow's extraction (e.g., direct file reads of `generated/` output
before the integration phase processes it), or for edge cases where the regex misses
nested fences.

**Suggested SDK fix:** Audit whether `_extract_code_from_response` handles all edge
cases (nested fences, fences without language specifier on same line as content,
triple-backtick inside strings). Consider exposing it as a public utility.

---

## W-010: Truncation detection in integration pipeline

| Field | Value |
|-------|-------|
| **Status** | FIXED |
| **Project** | wayfinder |
| **File** | `wayfinder/scripts/lead_contractor/integrate_backlog.py:907-990, 1178-1185` |
| **Type** | Pre-integration validation |
| **Fixed in** | `integrate_feature()` now calls `detect_truncation()` before merging |

**Problem:** The SDK's truncation detection runs during the draft phase inside the
workflow, but the **integration** step (file merge into target codebase) had no
equivalent check. Truncated code that slipped past the workflow (e.g., with
`fail_on_truncation=False`) could corrupt target files.

**Workaround:** Integration script independently validates files before merging:
- Unclosed triple-quoted strings
- Unmatched parentheses/brackets/braces
- Files ending with incomplete identifiers
- Missing `__all__` exports
- Syntax errors near EOF

```python
if truncation_issues:
    print(f"  REJECTED: File appears truncated or incomplete:")
    if fail_on_truncation:
        print(f"  Integration blocked to prevent corrupting target file.")
```

**SDK fix applied:** `PrimeContractorWorkflow.integrate_feature()` now calls
`detect_truncation()` on `.py` source files before merging, blocking integration
at confidence >= 70%. Controlled by `check_truncation` constructor param (default: True).

---

## Summary: SDK Backlog by Priority

### Already Fixed (commit `ebc9e66`)
| ID | Description |
|----|-------------|
| W-001 | SafeCodeGenerator monkey-patch (truncation/token config) |
| W-002 | Post-construction size limit overrides |
| W-003 | External clean_workspace.py script |
| W-004 | AST merge accumulation (silent corruption) |
| W-005 | Relative target_files path ValueError |
| W-006 | WorkflowResult.from_error() None metrics |
| W-010 | Pre-integration truncation check |

### Medium Priority (OPEN)
| ID | Description | Effort |
|----|-------------|--------|
| W-007 | Missing `model` field on WorkflowMetrics | Small — add field or document location |
| W-009 | Code fence edge cases in extraction | Small — audit + expose as public utility |

### Won't Fix
| ID | Description | Reason |
|----|-------------|--------|
| W-008 | sys.path manipulation | Development convenience, not SDK bug |
