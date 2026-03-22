# Kaizen Data Analysis Guide — Python

> **Parent guide:** [KAIZEN_DATA_ANALYSIS_GUIDE.md](../prime/KAIZEN_DATA_ANALYSIS_GUIDE.md)
> **Requirements:** [KAIZEN_PYTHON_REQUIREMENTS.md](./KAIZEN_PYTHON_REQUIREMENTS.md)
> **Language profile:** `PythonLanguageProfile` (`src/startd8/languages/python.py`)

This guide covers Python-specific analysis workflows for Kaizen telemetry. Python is the baseline language — the parent guide was originally written for Python runs. This companion doc consolidates all Python-specific details into a single reference, including the full quality scoring formula, all 18 repair steps, semantic check details, and file-type-specific analysis for Dockerfiles, HTML, and requirements files that commonly accompany Python services.

---

## 1. Python Generation Strategy

Python has the deepest pipeline integration of all supported languages:

| Property | Python | Other languages (for comparison) |
|----------|--------|----------------------------------|
| **Generation path** | Element-level via MicroPrime (always) | File-whole or feature-flagged element-level |
| **Merge strategy** | `ast` (additive AST merge) | `simple` (full file replacement) |
| **Repair pipeline** | 18 steps (fence strip → semantic method resolution) | 0–1 steps |
| **Post-generation cleanup** | Ruff auto-fix (inline in repair pipeline) | None or best-effort |
| **Syntax validation** | `ast.parse()` (stdlib, reliable) | Language-specific (javalang, gofmt, node --check) |
| **Semantic checks** | 4 AST-based checks | None |
| **Stub detection** | AST-based (empty function bodies, `raise NotImplementedError`) | Regex-based |
| **Stub marker** | `raise NotImplementedError` | Language-specific exceptions |

### What this means for analysis

- **AST merge can corrupt files.** Python is the only language using additive AST merge for `has_existing_files: true` features. This introduces failure modes unique to Python: duplicate `__main__` guards, duplicate definitions, stale target definitions preserved from the old file. See Section 4.
- **Repair masks issues.** The 18-step repair pipeline can silently fix problems that would be hard failures in other languages. When analyzing Python runs, check `semantic_repairs_applied` and `pre_semantic_repair_score` to see if repair improved the score — a high repair count may indicate the LLM output was poor but got rescued.
- **Semantic checks add signal.** Python's 4 semantic checks detect "correct but wrong" code that compiles fine but is logically broken. The `semantic_issue_breakdown` in `kaizen-metrics.json` shows aggregate counts across the run.

---

## 2. Finding Python Telemetry

Python features appear in the standard Kaizen directory structure. Identify them by:

- `metadata.json` → `"language": "python"` (or absence of language field, since Python is the default)
- `target_files` ending in `.py`
- Element-level telemetry present (MicroPrime artifacts)

### Accompanying non-Python files

Python services typically generate companion files that are **not** Python but are part of the same feature set:

| File Type | Examples | Validation | Quality Score |
|-----------|----------|------------|---------------|
| **Dockerfile** | `src/emailservice/Dockerfile` | Non-Python path (no AST) | Contract compliance only |
| **HTML templates** | `src/emailservice/templates/confirmation.html` | Non-Python path (no AST) | Contract compliance only |
| **requirements.in/txt** | `src/emailservice/requirements.in` | Non-Python path + orphan dependency check | Import completeness + orphan deps |
| **Config files** | `*.yaml`, `*.json`, `*.toml` | Non-Python path | Contract compliance only |

These files bypass the Python disk validation layers (L0–L10) and semantic checks. They receive `disk_quality_score` based on contract compliance and import completeness only, with a floor of 1.0 when no contract exists. **Orphan dependency** warnings on `requirements.in` files indicate packages declared but not imported by any sibling `.py` file — these are often false positives for transitive dependencies.

---

## 3. Draft vs Disk: Python-Specific Checks

### Step 1: Compare draft to disk

```bash
RUN_DIR=".cap-dev-pipe/pipeline-output/<project>/<run-id>/plan-ingestion"

# Compare the LLM's raw output to the file written to disk
diff <(cat $RUN_DIR/kaizen-prompts/standalone/PI-XXX/draft_response.md) \
     <(cat $RUN_DIR/generated/src/path/to/file.py)
```

Unlike other languages (which use `simple` merge), Python uses AST merge. The draft and disk **will often differ** due to:
- AST merge adding the generated code into the existing file's structure
- Repair steps fixing lint issues, sorting imports, removing duplicates
- Ruff auto-fix removing unused imports or fixing formatting

### Step 2: Validate syntax

```bash
# In-process (fastest, most reliable)
python3 -c "import ast; ast.parse(open('src/path/to/file.py').read()); print('OK')"

# Bytecode compilation (catches some issues ast.parse misses)
python3 -m py_compile src/path/to/file.py

# Ruff lint check (catches style + error-class violations)
python3 -m ruff check src/path/to/file.py --select=E7,E9,F --output-format=concise
```

### Step 3: Check for unfilled stubs

Python uses AST-based stub detection, not regex. The stubs to look for:

```bash
# Primary stub marker
grep -n "raise NotImplementedError" src/path/to/file.py

# Bare pass in function bodies (secondary stub indicator)
# Best checked via AST, but grep catches obvious cases:
grep -n "^\s*pass$" src/path/to/file.py
```

### Step 4: Run semantic checks

```bash
python3 -c "
from startd8.validators.semantic_checks import run_semantic_checks
with open('src/path/to/file.py') as f:
    issues = run_semantic_checks(f.read(), file_path='src/path/to/file.py')
for i in issues:
    print(f'  [{i.severity}] {i.check}: {i.message} (line {i.line})')
if not issues:
    print('  No semantic issues')
"
```

The 4 checks:
1. **Duplicate main guards** — more than one `if __name__ == "__main__"` block
2. **Duplicate definitions** — same function/class name defined twice at module level
3. **Bare except:pass** — `except: pass` silently swallowing all exceptions
4. **Phantom dependencies** — imports of packages not in known dependencies (requires `known_packages` set)

### Step 5: Check for AST merge artifacts (Python-only)

```bash
# Duplicate __main__ guards (AST merge artifact)
grep -c 'if __name__.*__main__' src/path/to/file.py
# Should be 0 or 1; >1 means AST merge duplicated it

# Duplicate class definitions
python3 -c "
import ast, collections
with open('src/path/to/file.py') as f:
    tree = ast.parse(f.read())
names = [n.name for n in ast.iter_child_nodes(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
dupes = [n for n, c in collections.Counter(names).items() if c > 1]
print(f'Duplicates: {dupes}' if dupes else 'No duplicates')
"
```

---

## 4. Python Quality Score Formula

The Python quality score uses 4 weighted components (the reference implementation in `compute_disk_quality_score()`):

```
composite = (contract_compliance × 0.4)
          + (import_completeness × 0.2)
          + (stub_penalty × 0.2)
          + (semantic_penalty × 0.2)
```

### Component reference

| Component | Weight | Computation | Range |
|-----------|--------|-------------|-------|
| `contract_compliance` | 0.4 | `max(0.0, 1.0 - (error_violations / total_checks))` | [0.0, 1.0] |
| `import_completeness` | 0.2 | `matched_imports / total_required_imports` | [0.0, 1.0] |
| `stub_penalty` | 0.2 | `max(0.0, 1.0 - stubs × 0.1)` — each stub deducts 0.1 | [0.0, 1.0] |
| `semantic_penalty` | 0.2 | `max(0.0, 1.0 - errors × 0.3 - warnings × 0.1)` — severity-weighted | [0.0, 1.0] |

**Short-circuit rules:**
- `compliance is None` → 0.0
- `ast_valid == False` → 0.0

**Security bonus:** When Anzen findings exist, a `security_penalty` (0.2 weight) is added.

### Derived metrics

- `disk_quality_score` — per-feature composite score
- `assembly_delta` — `requirement_score - disk_quality_score` (positive = quality loss from design to assembly)
- `avg_assembly_delta` — run-level average; negative values indicate disk quality exceeds requirement scoring
- `pre_semantic_repair_score` — score before semantic repairs were applied (null if no repairs)

---

## 5. Python Root Causes

16 `RootCause` enum values, each with Python-specific manifestations:

### Critical (file unusable)

| Root Cause | Symptom | Investigation |
|-----------|---------|---------------|
| `ast_failure` | `SyntaxError` from `ast.parse()` after all repair steps | `draft_response.md` — truncated? Malformed? Check `draft_response.meta.json` for truncation. |
| `repair_exhausted` | All 18 repair steps attempted, still fails | Check `repair_steps` array in element results. What was the last repair attempted? |

### High (file compiles but broken)

| Root Cause | Symptom | Investigation |
|-----------|---------|---------------|
| `unfilled_stub` | `raise NotImplementedError` or bare `pass` in function body | `filled_skeleton` field — splice failed? Cache hit with no code? |
| `scope_corruption` | Functions nested inside other functions; class methods at module level | `draft_response.md` — indentation issues in LLM output |
| `phantom_import` | Import of module not in requirements, stdlib, or local project | `draft_user_prompt.md` — was the dependency list complete? |
| `splicer_mismatch` | AST splicer couldn't find target anchor (function/class name) | Generated code uses different names than the skeleton |

### Medium (quality issues)

| Root Cause | Symptom | Investigation |
|-----------|---------|---------------|
| `duplicate_import` | Same import appearing multiple times | AST merge artifact or LLM duplicate |
| `size_regression` | Generated file significantly larger than original | LLM rewrote the entire file instead of surgical edit |
| `tier_escalation` | Element classified SIMPLE but needed MODERATE/COMPLEX | Decomposer couldn't break it down further |
| `generation_error` | LLM returned error string or non-code content | Check model availability and prompt length |

### Infrastructure

| Root Cause | Symptom | Investigation |
|-----------|---------|---------------|
| `ollama_timeout` | Generation exceeded 300s timeout | Large file or complex class hierarchy |
| `ollama_empty_response` | Empty or whitespace-only response | Model availability issue |
| `ollama_circuit_breaker` | Circuit breaker tripped after repeated failures | Batch abandoned |
| `skeleton_missing` | Target `.py` file not generated at all | Skeleton assembly failure |
| `dependency_blocked` | Feature blocked by unmet dependency | Prerequisite feature failed |

---

## 6. Python Repair Pipeline (18 Steps)

When investigating quality issues, check which repair steps were applied and in what order:

| Step | What It Fixes | Key Indicator |
|------|---------------|---------------|
| `fence_strip` | Markdown code fences from LLM output | Raw output starts with ` ```python ` |
| `ast_validate` | Reports `SyntaxError` location | `ast_valid_before_repair: false` |
| `bracket_balance` | Unmatched `(`, `[`, `{` | Common in truncated output |
| `indent_normalize` | Mixed tabs/spaces, wrong indent level | Scope corruption symptom |
| `future_import_reorder` | `from __future__ import` not at file top | AST merge artifact |
| `duplicate_removal` | Duplicate imports and definitions | AST merge + LLM duplication |
| `class_body_dedup` | Duplicate methods within a class | LLM regenerated existing methods |
| `definition_order_fix` | Callees after callers | LLM generated in wrong order |
| `dunder_all_fix` | `__all__` doesn't match exports | AST merge added symbols |
| `extended_lint_fix` | Ruff-detected lint errors | Auto-fixes via `ruff check --fix` |
| `error_import_completion` | Missing imports (NameError-based) | LLM forgot imports |
| `manifest_import_completion` | Missing imports (ForwardManifest-based) | Contract-driven completion |
| `variable_initialization` | Variables referenced before assignment | LLM forgot init |
| `unused_variable_removal` | Assigned but never read variables | LLM generated dead code |
| `semantic_duplicate_main` | Duplicate `if __name__` guards | AST merge artifact |
| `semantic_discarded_return` | Factory call return values discarded | `create_*()` without assignment |
| `semantic_import_fix` | Phantom/broken imports | Detected by semantic analysis |
| `semantic_method_resolution` | `self.x()` where `x` is module-level | Method/function confusion |
| `contract_violation_fix` | ForwardManifest contract violations | Auto-fixes structural issues |

**Analysis tip:** In the postmortem, each element's `repair_steps` array shows which steps were applied. High repair step counts (>3) suggest the LLM output was poor quality but got rescued. Zero repair steps means the LLM output was clean.

---

## 7. Semantic Issue Categories

The `semantic_issue_breakdown` in `kaizen-metrics.json` aggregates these categories across the run:

| Category | Severity | What It Means | Common in |
|----------|----------|---------------|-----------|
| `unreachable_function` | warning | Module-level function defined but never called within the file | Library/utility modules (expected for public APIs) |
| `discarded_return` | warning | Return value of a call is discarded (e.g., `os.environ.get(...)` with no assignment) | Service initialization code |
| `orphan_dependency` | warning | Package in `requirements.in` not imported by sibling `.py` files | Requirements files (often false positive for transitive deps) |
| `import_resolution` | error | Import cannot be resolved against stdlib, requirements, or local modules | Phantom imports — LLM hallucinated a module |
| `duplicate_main_guard` | warning | Multiple `if __name__ == "__main__"` blocks | AST merge artifact |
| `duplicate_definition` | warning | Same function/class name defined twice at module level | AST merge artifact |
| `bare_except_pass` | warning | `except: pass` silently swallowing all exceptions | LLM defensive error handling |
| `phantom_dependency` | warning | Import references package not in known dependencies | Hallucinated dependency |

### Interpreting semantic warnings vs errors

- **Warnings** reduce `semantic_penalty` by 0.1 each (quality signal, not blocking)
- **Errors** reduce `semantic_penalty` by 0.3 each (may indicate broken functionality)
- `semantic_verdict_downgrades` counts how many features had their verdict lowered due to semantic errors
- `features_with_semantic_errors` lists the affected feature IDs

---

## 8. Non-Python File Analysis (Dockerfiles, HTML, Requirements)

Python service runs typically include non-Python companion files. These bypass the Python validation pipeline but still receive quality scoring.

### Dockerfiles

**What Kaizen checks:**
- Contract compliance against ForwardManifest (if spec exists)
- No AST validation (not Python)
- No semantic checks

**What to check manually:**
```bash
# Verify Dockerfile syntax
docker build --check -f src/emailservice/Dockerfile .

# Check for common issues
grep -n 'COPY.*requirements' src/emailservice/Dockerfile   # requirements copied before install?
grep -n 'RUN pip install' src/emailservice/Dockerfile       # pip install present?
grep -n 'EXPOSE' src/emailservice/Dockerfile                # port exposed?
grep -n 'CMD\|ENTRYPOINT' src/emailservice/Dockerfile       # entry point defined?
```

**Common LLM failure patterns:**
- Missing `COPY requirements.txt .` before `RUN pip install`
- Wrong base image (e.g., `python:3.12` instead of `python:3.12-slim`)
- Missing `WORKDIR` directive
- `EXPOSE` port doesn't match the service's actual port

### HTML Templates

**What Kaizen checks:**
- Contract compliance only
- `disk_quality_score: 1.0` when no contract exists (default pass)

**What to check manually:**
```bash
# Validate HTML structure (if tidy is available)
tidy -errors -q src/emailservice/templates/confirmation.html

# Check for Jinja2/template markers (common in Python services)
grep -n '{{.*}}' src/emailservice/templates/confirmation.html
grep -n '{%.*%}' src/emailservice/templates/confirmation.html
```

### Requirements Files (requirements.in / requirements.txt)

**What Kaizen checks:**
- Contract compliance
- **Orphan dependency detection** — packages in `requirements.in` that no sibling `.py` file imports
- Import completeness

**What to check manually:**
```bash
# Verify all imported packages are declared
python3 -c "
import ast, pathlib
reqs = set()
for line in pathlib.Path('src/emailservice/requirements.in').read_text().splitlines():
    line = line.strip()
    if line and not line.startswith('#'):
        reqs.add(line.split('==')[0].split('>=')[0].split('<')[0].strip().lower())
print(f'Declared: {sorted(reqs)}')
"

# Cross-reference against actual imports
grep -h '^import\|^from' src/emailservice/*.py | sort -u
```

**Common orphan dependency causes:**
- **Transitive dependencies** — `python-json-logger` is used via `pythonjsonlogger` import name (PyPI vs import name mismatch; handled by `package_alias_map` but not always complete)
- **Runtime-only dependencies** — `rsa`, `requests` used by the gRPC/protobuf runtime, not directly imported
- **Build-time dependencies** — packages needed for compilation but not imported at runtime

---

## 9. Typical Python Debugging Workflow

1. **Check the summary.** Open `prime-postmortem-summary.md` — score, verdict, failed features.
2. **Check semantic breakdown.** Open `kaizen-metrics.json` → `semantic_issue_breakdown`. Are there `error`-severity issues?
3. **For each feature with issues:**
   a. Read the `disk_compliance` block in `prime-postmortem-report.json`
   b. Check `disk_quality_score` and `assembly_delta`
   c. If `assembly_delta > 0.2`: significant quality loss from design to disk — check repair steps
   d. If `semantic_error_count > 0`: unresolvable imports or structural issues
4. **For MicroPrime features (elements present):**
   a. Check `escalation_reason` per element — `structural_mismatch` means splicer couldn't find the anchor
   b. Check `repair_steps` per element — high count means poor LLM output
   c. Check `ast_valid_before_repair` — `false` means the LLM produced invalid Python
5. **For companion files (Dockerfile, HTML, requirements.in):**
   a. These get `disk_quality_score: 1.0` by default if no contract exists
   b. Check `semantic_issues` for orphan dependency warnings on requirements files
   c. Manually validate Dockerfiles and HTML (Section 8)
6. **Classify and act.** Apply the Ichigo Ichie gate before proposing fixes.
7. **Inject hints and rerun.** Add targeted hints to `kaizen-config.json`.

---

## 10. Python vs Other Languages: Key Differences for Analysts

| Dimension | Python | All Others |
|-----------|--------|------------|
| **Merge strategy** | AST merge (can corrupt) | Simple replace (draft = disk) |
| **Repair pipeline** | 18 steps (masks issues) | 0–1 steps (draft = final) |
| **Syntax validation** | `ast.parse()` (stdlib) | Language-specific tools |
| **Semantic checks** | 4 checks | None |
| **Quality scoring** | Full (4 components) | Partial (2 components) |
| **Stub detection** | AST-based | Regex-based |
| **Common failure mode** | AST merge corruption, phantom imports | Cross-language contamination |
| **Debugging focus** | Check repair transforms + merge artifacts | Check LLM output directly |
| **Non-Python companions** | Dockerfiles, HTML, requirements.in | Build files (build.gradle, go.mod) |

The core insight: **Python debugging is more complex** (18 repair steps + AST merge between draft and disk) but **Python prevention is easier** (repair catches many issues automatically). For other languages, the LLM must get it right the first time.
