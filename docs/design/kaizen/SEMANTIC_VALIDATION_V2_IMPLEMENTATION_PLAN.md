# Semantic Validation v2 — Implementation Plan

**Date:** 2026-03-16
**Status:** Ready for Development
**Requirements:** [SEMANTIC_VALIDATION_V2_REQUIREMENTS.md](SEMANTIC_VALIDATION_V2_REQUIREMENTS.md)
**Prerequisite:** Phases 1–4 (L1–L6) complete, severity-weighted scoring active, verdict gate active, L5 wired, aggregate score recomputation wired.

---

## Phase 5: Harden Existing Detectors

**Priority:** P0 — fixes the grade-F Dockerfile and eliminates ~60% of L1 false positives.
**Estimated:** ~65 impl LOC + ~60 test LOC. Single commit.

### Step 5.1: L3+ Dockerfile Digest Plausibility (REQ-SV2-100)

**File:** `src/startd8/forward_manifest_validator.py`

**Location:** Inside `_validate_dockerfile()`, after the existing length check (~line 560).

**Implementation:**

```python
def _digest_looks_fabricated(digest: str) -> bool:
    """Heuristic: real SHA256 digests have high entropy and no sequential patterns."""
    # 1. Shannon entropy — real digests average ~3.9 bits/char
    from math import log2
    freq: dict[str, int] = {}
    for c in digest:
        freq[c] = freq.get(c, 0) + 1
    entropy = -sum((n / len(digest)) * log2(n / len(digest)) for n in freq.values())
    if entropy < 3.0:
        return True

    # 2. Sequential byte detection — 8+ consecutive bytes forming arithmetic sequence
    bytes_list = [int(digest[i:i+2], 16) for i in range(0, len(digest) - 1, 2)]
    run = 1
    for i in range(1, len(bytes_list)):
        if bytes_list[i] - bytes_list[i-1] == bytes_list[1] - bytes_list[0]:
            run += 1
            if run >= 8:
                return True
        else:
            run = 1

    return False
```

Wire into existing digest check: after `len(match) != 64` check, add:
```python
elif _digest_looks_fabricated(match):
    result.semantic_issues.append({
        "category": "dockerfile_digest_fabricated",
        "severity": "error",
        "message": f"SHA256 digest appears fabricated (low entropy or sequential pattern)",
        "line": lineno,
        "symbol": f"sha256:{match[:16]}...",
    })
```

**Tests** (`tests/unit/test_semantic_validation_scope_and_dockerfile.py`):
- `test_fabricated_sequential_digest_flagged` — the PI-013 pattern `9b4929a7826e4b8...`
- `test_fabricated_low_entropy_flagged` — repeated patterns like `aaaa...`
- `test_real_digest_passes` — use actual digests from PI-010/PI-011 (64 hex, high entropy)
- `test_truncated_still_caught` — 8-char digest still caught by existing length check (no regression)

### Step 5.2: L1 GCP False Positive Reduction (REQ-SV2-200)

**File:** `src/startd8/implementation_engine/package_aliases.py`

Add to `_PYPI_TO_IMPORT`:
```python
"google-api-core": "google.api_core",
"google-auth": "google.auth",
"google-cloud-secret-manager": "google.cloud.secretmanager",
"google-cloud-storage": "google.cloud.storage",
"google-cloud-aiplatform": "google.cloud.aiplatform",
"google-cloud-bigquery": "google.cloud.bigquery",
"google-cloud-logging": "google.cloud.logging",
"google-cloud-profiler": "googlecloudprofiler",
```

**File:** `src/startd8/forward_manifest_validator.py`

In `_validate_import_resolution()`, after the existing resolution chain, add a prefix-family downgrade:

```python
# Downgrade google.* imports to warning when any google-* package is in requirements
if module_top == "google" and severity == "error":
    if any(pkg.startswith("google-") for pkg in requirements_packages):
        severity = "warning"
        message = f"Import '{module_name}' may resolve via a google-* package in requirements.in (could not determine exact package)"
```

**Tests** (`tests/unit/test_semantic_validation_imports.py`):
- `test_google_api_core_resolves_via_alias` — `google.api_core` with `google-api-core` in requirements → no issue
- `test_google_cloud_with_any_google_pkg_downgrades` — `google.cloud.secretmanager` with `google-cloud-storage` in requirements → warning (not error)
- `test_non_google_import_stays_error` — `from phantom import x` with `google-api-core` in requirements → still error

### Step 5.3: L5 Alias Resolution Fix (REQ-SV2-300)

**File:** `src/startd8/forward_manifest_validator.py`

In `_validate_requirements_coverage()`, extend the `found` check (~line 785):

```python
found = any(
    imp == expected_import
    or imp.startswith(expected_import + ".")
    or imp == package
    or imp.startswith(package + ".")
    # Reverse prefix: `from google.cloud import secretmanager` produces
    # imp="google.cloud", expected="google.cloud.secretmanager"
    or expected_import.startswith(imp + ".")
    for imp in all_imports
)
```

One line added to the `any()` comprehension.

**Tests** (`tests/unit/test_semantic_validation_factory_and_reqs.py`):
- `test_reverse_prefix_import_resolves` — `google-cloud-secret-manager` in requirements, `google.cloud` in imports → no orphan warning

### Step 5.4: Kaizen Category Aggregation (REQ-SV2-700)

**File:** `scripts/run_prime_postmortem.py`

After existing metrics emission (~line 486), add:

```python
# Per-category semantic issue breakdown
category_breakdown: dict[str, dict[str, int]] = {}
verdict_downgrades = 0
features_with_errors: list[str] = []
for fpm in report.features:
    if fpm.semantic_error_count > 0:
        features_with_errors.append(fpm.feature_id)
    if "semantic" in (fpm.verdict or ""):
        verdict_downgrades += 1
    for issue in getattr(fpm.disk_compliance, "semantic_issues", []) or []:
        if isinstance(issue, dict):
            cat = issue.get("category", "unknown")
            sev = issue.get("severity", "warning")
            entry = category_breakdown.setdefault(cat, {"error": 0, "warning": 0})
            entry[sev] = entry.get(sev, 0) + 1

metrics["semantic_issue_breakdown"] = category_breakdown
metrics["semantic_verdict_downgrades"] = verdict_downgrades
metrics["features_with_semantic_errors"] = features_with_errors
```

**No tests required** — metrics emission is verified by the next production run.

---

## Phase 6: New Diagnostic Layers

**Priority:** P1–P2. Two commits.
**Estimated:** ~130 impl LOC + ~150 test LOC.

### Commit 6a: L8 Service Identity + L9 Method Resolution

### Step 6.1: L8 Service Identity Mismatch (REQ-SV2-400)

**File:** `src/startd8/forward_manifest_validator.py`

New function after `_validate_discarded_returns()`:

```python
def _validate_service_identity(
    tree: ast.AST,
    file_path: str,
    sibling_files: Optional[List[str]] = None,
) -> List[Dict[str, object]]:
    """Flag logger/formatter calls with wrong service directory name (REQ-SV2-400)."""
    issues: List[Dict[str, object]] = []

    # Derive expected service name from parent directory
    parts = Path(file_path).parts
    if len(parts) < 2:
        return issues
    expected_service = parts[-2]  # e.g., "recommendationservice"

    # Collect other service directory names for comparison
    other_services: set[str] = set()
    for sib in (sibling_files or []):
        sib_parts = Path(sib).parts
        if len(sib_parts) >= 2:
            other_services.add(sib_parts[-2])
    other_services.discard(expected_service)
    if not other_services:
        return issues  # No siblings to compare against

    # Walk AST for string literals in logger/formatter calls
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = _extract_callee_name(node)
        if callee is None:
            continue
        # Match logger factory calls and keyword args
        targets = ("getlogger", "getjsonlogger", "get_logger", "basicconfig")
        if callee.lower().split(".")[-1] not in targets:
            # Also check keyword args: component=, service=, name=
            for kw in node.keywords:
                if kw.arg in ("component", "service", "name"):
                    if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        found = kw.value.value.lower()
                        for other in other_services:
                            if other.lower() in found and expected_service.lower() not in found:
                                issues.append({
                                    "category": "service_identity_mismatch",
                                    "severity": "error",
                                    "message": f"Keyword '{kw.arg}' contains '{other}' but file is in '{expected_service}/'",
                                    "line": node.lineno,
                                    "symbol": kw.value.value,
                                })
            continue

        # Check positional string arg
        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            found = node.args[0].value.lower()
            for other in other_services:
                if other.lower() in found and expected_service.lower() not in found:
                    issues.append({
                        "category": "service_identity_mismatch",
                        "severity": "error",
                        "message": f"Logger initialized with '{node.args[0].value}' but file is in '{expected_service}/'",
                        "line": node.lineno,
                        "symbol": node.args[0].value,
                    })

    return issues
```

Wire into `validate_disk_compliance()` after L6, passing `sibling_files` from the caller.

**Tests** (`tests/unit/test_semantic_validation_service_identity.py`, new file):
- `test_correct_service_name_passes` — `getJSONLogger("recommendationservice-server")` in `recommendationservice/` → no issue
- `test_wrong_service_name_flagged` — `getJSONLogger("emailservice")` in `recommendationservice/` → error
- `test_keyword_component_flagged` — `CustomJsonFormatter(component="emailservice")` in `recommendationservice/` → error
- `test_no_siblings_skips_check` — no sibling files → no issues (can't determine other service names)
- `test_generic_name_not_flagged` — `getLogger("myapp")` → no issue (doesn't match any sibling service)

### Step 6.2: L9 Method Resolution (REQ-SV2-500)

**File:** `src/startd8/forward_manifest_validator.py`

New function:

```python
def _validate_method_resolution(tree: ast.AST) -> List[Dict[str, object]]:
    """Flag self.name() calls where name is a module-level function, not a method (REQ-SV2-500)."""
    issues: List[Dict[str, object]] = []

    # Pass 1: collect module-level function names
    module_funcs: set[str] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            module_funcs.add(node.name)

    # Pass 2: for each class, collect its methods and check self.x() calls
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        class_methods: set[str] = set()
        for item in ast.iter_child_nodes(node):
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                class_methods.add(item.name)

        # Walk class body for self.attr() calls
        for child in ast.walk(node):
            if (
                isinstance(child, ast.Attribute)
                and isinstance(child.value, ast.Name)
                and child.value.id == "self"
                and child.attr in module_funcs
                and child.attr not in class_methods
            ):
                issues.append({
                    "category": "method_resolution",
                    "severity": "warning",
                    "message": f"'self.{child.attr}()' called but '{child.attr}' is a module-level function, not a method of '{node.name}'",
                    "line": child.lineno,
                    "symbol": child.attr,
                })

    return issues
```

Wire into `validate_disk_compliance()` after L8.

**Tests** (`tests/unit/test_semantic_validation_method_resolution.py`, new file):
- `test_self_dot_module_func_flagged` — `self.index()` where `index` is module-level → warning
- `test_self_dot_real_method_passes` — `self.on_start()` where `on_start` is a class method → no issue
- `test_module_func_not_in_class_passes` — `index(self)` called normally → no issue
- `test_self_dot_inherited_not_flagged` — only checks the immediate class, not bases (conservative)

### Commit 6b: L10 Dead Code + FP Tracking

### Step 6.3: L10 Dead Code Detection (REQ-SV2-600)

**File:** `src/startd8/forward_manifest_validator.py`

New function:

```python
def _validate_reachability(tree: ast.AST) -> List[Dict[str, object]]:
    """Flag module-level functions never referenced within the file (REQ-SV2-600)."""
    issues: List[Dict[str, object]] = []

    # Collect module-level function defs (exclude private, main, class methods)
    func_defs: dict[str, int] = {}  # name → lineno
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_") or node.name == "main":
                continue
            func_defs[node.name] = node.lineno

    if not func_defs:
        return issues

    # Collect all Name references outside of function def headers
    referenced: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            referenced.add(node.id)
        # Also check dict values, list elements, decorator arguments
        # that reference function names (e.g., tasks = {index: 1})

    # Check __all__
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    # All names in __all__ are considered referenced
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                referenced.add(elt.value)

    # Functions defined but never referenced elsewhere
    for name, lineno in func_defs.items():
        if name not in referenced:
            issues.append({
                "category": "unreachable_function",
                "severity": "warning",
                "message": f"Module-level function '{name}' is defined but never called within the file",
                "line": lineno,
                "symbol": name,
            })

    return issues
```

**Tests** (`tests/unit/test_semantic_validation_reachability.py`, new file):
- `test_uncalled_function_flagged` — `def foo(): pass` never referenced → warning
- `test_called_function_passes` — `def foo(): pass; foo()` → no issue
- `test_dict_value_reference_passes` — `tasks = {foo: 1}` → `foo` considered referenced
- `test_private_function_not_flagged` — `def _helper(): pass` → no issue
- `test_main_not_flagged` — `def main(): pass` → no issue
- `test_all_export_not_flagged` — `__all__ = ["foo"]` → `foo` considered referenced

### Step 6.4: FP Tracking Infrastructure (REQ-SV2-800)

**File:** `src/startd8/forward_manifest_validator.py`

Add optional `known_false_positives` parameter to `validate_disk_compliance()`:

```python
def validate_disk_compliance(
    file_path: str,
    project_root: str,
    manifest: Optional[ForwardManifest] = None,
    *,
    sibling_files: Optional[List[str]] = None,
    sibling_imports: Optional[Dict[str, Set[str]]] = None,
    import_map: Optional[Dict[str, str]] = None,
    factory_patterns: Optional[List[str]] = None,
    known_false_positives: Optional[Dict[str, str]] = None,  # {symbol: reason}
) -> DiskComplianceResult:
```

After all semantic checks, annotate matching issues:

```python
if known_false_positives:
    for issue in result.semantic_issues:
        if isinstance(issue, dict) and issue.get("symbol") in known_false_positives:
            issue["false_positive"] = True
            issue["fp_reason"] = known_false_positives[issue["symbol"]]
```

**File:** `src/startd8/contractors/prime_postmortem.py`

In the Kaizen metrics section, compute per-category FP rates:

```python
fp_rates: dict[str, float] = {}
for cat, counts in category_breakdown.items():
    total = counts.get("error", 0) + counts.get("warning", 0)
    fp_count = sum(
        1 for fpm in report.features
        for issue in getattr(fpm.disk_compliance, "semantic_issues", []) or []
        if isinstance(issue, dict)
        and issue.get("category") == cat
        and issue.get("false_positive", False)
    )
    fp_rates[cat] = fp_count / total if total > 0 else 0.0
metrics["semantic_fp_rate"] = fp_rates
```

**Tests:** Extend `test_kaizen_quality.py` with FP annotation test.

---

## Phase 7: Correlation Infrastructure

**Priority:** P2. Single commit.
**Estimated:** ~30 LOC. No new tests — validated by production run output.

### Step 7.1: Per-Category Correlation (REQ-SV2-900)

**File:** `scripts/run_prime_postmortem.py` (kaizen correlation section)

After existing Spearman correlation computation, add per-category breakdown:

```python
# Per-category correlations (REQ-SV2-900)
category_correlations = {}
for cat in all_categories:
    cat_mask = [
        1 if any(
            isinstance(i, dict) and i.get("category") == cat
            for i in features_data[idx].get("semantic_issues", [])
        ) else 0
        for idx in range(len(features_data))
    ]
    if sum(cat_mask) >= 5:  # Need 5+ data points
        for prompt_feature in prompt_features:
            rho, _ = spearmanr(cat_mask, prompt_feature_values[prompt_feature])
            if abs(rho) > 0.3:
                category_correlations.setdefault(cat, []).append({
                    "feature": prompt_feature,
                    "rho": round(rho, 3),
                })
```

This only produces output when sufficient data accumulates (5+ data points per category). Until then, the section is empty — which is correct.

---

## Phase 8: Upstream Repair (Deferred)

**Not implemented.** Phase 8 activates per-category when:
1. FP rate < 5% across 10+ runs (from Phase 6 FP tracking)
2. |ρ| > 0.3 correlation identified (from Phase 7)
3. Human approval of repair strategy

The implementation will be a new `generate_kaizen_suggestions()` enhancement that emits `repair_type: "prompt_enrichment"` suggestions targeting specific pipeline config keys.

---

## Execution Order

```
Phase 5  ← DO FIRST (single commit, fixes grade-F, reduces FPs)
  ↓
Phase 6a ← L8 + L9 (catches grade-D logger, grade-B- locust bug)
  ↓
Phase 6b ← L10 + FP tracking (dead code warnings, measurement infrastructure)
  ↓
Phase 7  ← Correlation (build now, accumulates data over 10+ runs)
  ↓
Phase 8  ← Repair (deferred until gate criteria met)
```

**Total across Phases 5–7:** ~225 impl LOC + ~210 test LOC across 4 commits.

---

## Verification

Each phase is verified against the run-053 postmortem data:

| Phase | Verification |
|-------|-------------|
| Phase 5 | Re-run `validate_disk_compliance()` on PI-013 Dockerfile → `dockerfile_digest_fabricated` error. Re-run on PI-003 → 0 GCP FP errors (down from 2). PI-016 → 0 orphan FPs. |
| Phase 6a | Re-run on PI-002 logger.py → `service_identity_mismatch` error. Re-run on PI-009 locustfile.py → `method_resolution` warning. |
| Phase 6b | Re-run on PI-004/PI-007 → `unreachable_function` warnings for dead client functions. |
| Phase 7 | Verify `category_correlations` section appears in `kaizen-correlation.json` (empty until data accumulates). |

---

## Cross-References

| Document | Relationship |
|----------|-------------|
| [SEMANTIC_VALIDATION_V2_REQUIREMENTS.md](SEMANTIC_VALIDATION_V2_REQUIREMENTS.md) | Requirements this plan implements |
| [SEMANTIC_VALIDATION_IMPLEMENTATION_PLAN.md](SEMANTIC_VALIDATION_IMPLEMENTATION_PLAN.md) | v1 plan (Phases 1–4, complete) |
| `forward_manifest_validator.py` | Primary implementation target |
| `package_aliases.py` | GCP alias expansion target |
| `prime_postmortem.py` | Scoring, FP tracking, Kaizen metrics |
| `run_prime_postmortem.py` | Kaizen metrics emission, correlation |
