# Truncation Handling Improvement

**Status**: IMPLEMENTED (2026-02-09)

## Problem

The `LeadContractorWorkflow` has two truncation detection mechanisms that are conflated under single control flags:

1. **API-level detection**: Checks if `finish_reason == "max_tokens"` - indicates the model was forcibly cut off
2. **Heuristic detection**: Analyzes output for structural incompleteness (unclosed braces, missing sections)

Current flags:
- `check_truncation=True` - enables heuristic analysis
- `fail_on_truncation=True` - fails on ANY truncation (API or heuristic)

**Issue**: Heuristic detection produces false positives on certain output formats (Jsonnet, YAML, config files) where the model finishes naturally but the output doesn't match expected code structure patterns.

Example: A task generates 1077 tokens of valid Jsonnet, but heuristic detection flags it as "truncated" due to brace patterns. The workflow fails despite no actual truncation occurring.

## Implemented Solution

Split `fail_on_truncation` into two separate flags:

```python
fail_on_api_truncation: bool = True       # Fail when API returns max_tokens/length
fail_on_heuristic_truncation: bool = False # Fail when heuristic detects incomplete code
```

### Behavior Matrix

| API Truncated | Heuristic Truncated | fail_on_api | fail_on_heuristic | Result |
|---------------|---------------------|-------------|-------------------|--------|
| Yes | - | True | - | FAIL (with auto-retry if iterations remain) |
| Yes | - | False | - | WARN |
| No | Yes | - | True | FAIL (with auto-retry if iterations remain) |
| No | Yes | - | False | WARN |
| No | No | - | - | OK |

### Backward Compatibility

Existing `fail_on_truncation=True` maps to:
- `fail_on_api_truncation=True`
- `fail_on_heuristic_truncation=True`

Existing `fail_on_truncation=False` maps to:
- `fail_on_api_truncation=False`
- `fail_on_heuristic_truncation=False`

New granular flags take precedence if specified alongside the legacy flag.

## Files Modified

### 1. `src/startd8/workflows/builtin/lead_contractor_models.py`

Added `truncation_source` field to `DraftResult` dataclass:

```python
@dataclass
class DraftResult:
    # ... existing fields ...
    was_truncated: bool = False
    truncation_source: Optional[str] = None  # "api" or "heuristic"
```

### 2. `src/startd8/workflows/builtin/lead_contractor_workflow.py`

#### A. Config extraction (sync `_execute` ~line 425, async `_aexecute` ~line 960)

Both sync and async paths updated with identical logic:

```python
check_truncation = config.get("check_truncation", True)
strict_truncation = config.get("strict_truncation", False)

# Granular truncation failure control
legacy_fail_on_truncation = config.get("fail_on_truncation")
if legacy_fail_on_truncation is not None:
    fail_on_api_truncation = config.get("fail_on_api_truncation", legacy_fail_on_truncation)
    fail_on_heuristic_truncation = config.get("fail_on_heuristic_truncation", legacy_fail_on_truncation)
else:
    fail_on_api_truncation = config.get("fail_on_api_truncation", True)
    fail_on_heuristic_truncation = config.get("fail_on_heuristic_truncation", False)
```

#### B. Draft loop truncation handling (sync ~line 529, async ~line 1057)

Both paths updated with source-aware logic preserving the 3-way branch:
1. **Auto-retry** if `should_fail` and iterations remain
2. **Error** if `should_fail` and no iterations remain
3. **Warn** if truncation detected but `should_fail` is False

```python
if check_truncation and draft.was_truncated:
    is_api = draft.truncation_source == "api"
    should_fail = (
        (is_api and fail_on_api_truncation)
        or (not is_api and fail_on_heuristic_truncation)
    )

    if should_fail and iteration < max_iterations:
        # Auto-retry with continuation prompt
        ...
    elif should_fail:
        # Fail with source-specific error message
        ...
    else:
        # Warn and continue
        ...
```

#### C. `_create_draft` and `_acreate_draft` truncation source tracking

Both sync and async paths now track the truncation source separately:

```python
api_truncated = token_usage.was_truncated if token_usage else False
truncation_source = "api" if api_truncated else None

heuristic_truncated = False
if check_truncation and not api_truncated and implementation_code:
    # ... heuristic detection ...
    if truncation_result.is_truncated and ...:
        heuristic_truncated = True
        truncation_source = "heuristic"

was_truncated = api_truncated or heuristic_truncated

draft = DraftResult(
    ...,
    was_truncated=was_truncated,
    truncation_source=truncation_source,
)
```

#### D. Class docstring and WorkflowInput declarations

Updated to document the new config keys and use-case recommendations.

## Testing

Recommended tests (not yet created):

```python
def test_api_truncation_fails_by_default():
    """API truncation should fail with default settings."""

def test_heuristic_truncation_warns_by_default():
    """Heuristic truncation should warn but continue with new defaults."""

def test_legacy_fail_on_truncation_true():
    """Legacy flag=True should fail on both types."""

def test_legacy_fail_on_truncation_false():
    """Legacy flag=False should warn on both types."""

def test_granular_flags_override_legacy():
    """Granular flags should take precedence over legacy flag."""

def test_auto_retry_on_api_truncation():
    """Auto-retry branch is preserved — skip review, re-draft with continuation prompt."""

def test_auto_retry_on_heuristic_truncation():
    """Auto-retry also works for heuristic truncation when fail_on_heuristic_truncation=True."""
```

## Migration

1. Existing users with `fail_on_truncation=True` get same behavior (both fail)
2. Existing users with `fail_on_truncation=False` get same behavior (both warn)
3. New users get safer defaults: API fails, heuristic warns
4. Users can opt into granular control for specific use cases

## Summary

| Change | Impact |
|--------|--------|
| New `fail_on_api_truncation` flag | Users can allow API truncation (rare) |
| New `fail_on_heuristic_truncation` flag | Users can ignore false positives |
| New default: heuristic=False | Reduces false positive failures |
| `truncation_source` in DraftResult | Better debugging info |
| Auto-retry preserved | Both truncation types trigger retry when iterations remain |
| Async path updated | `_aexecute` and `_acreate_draft` have identical changes |
| Backward compatible | Existing configs unchanged |
