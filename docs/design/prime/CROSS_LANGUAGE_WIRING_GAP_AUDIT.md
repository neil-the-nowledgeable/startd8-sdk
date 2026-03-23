# Cross-Language Wiring Gap Audit — Prime Contractor Pipeline

> **Version:** 1.0.0
> **Date:** 2026-03-23
> **Status:** FINDINGS COMPLETE
> **Scope:** All 5 languages (Python, Go, Node.js, Java, C#) + cross-cutting infrastructure
> **Method:** Parallel agent audit of semantic checks, repair routing, Kaizen suggestion wiring, quality scoring, integration engine, language profiles, and exemplar system
> **Trigger:** Run-107 Node.js evaluation revealed pattern of near-complete features with minor wiring issues silently blocking quality improvements

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Critical Gaps — Silent Quality Loss](#2-critical-gaps--silent-quality-loss)
3. [High Gaps — Feedback Loop Broken](#3-high-gaps--feedback-loop-broken)
4. [Medium Gaps — Quality Signal Degradation](#4-medium-gaps--quality-signal-degradation)
5. [Wiring Completeness by Language](#5-wiring-completeness-by-language)
6. [Wiring Completeness by Pipeline Stage](#6-wiring-completeness-by-pipeline-stage)
7. [Gap Detail: Node.js](#7-gap-detail-nodejs)
8. [Gap Detail: Python](#8-gap-detail-python)
9. [Gap Detail: Go](#9-gap-detail-go)
10. [Gap Detail: Java](#10-gap-detail-java)
11. [Gap Detail: C#](#11-gap-detail-c)
12. [Gap Detail: Cross-Cutting](#12-gap-detail-cross-cutting)

---

## 1. Executive Summary

The Prime Contractor pipeline has **substantial language support** across all 5 languages, but a pattern of **near-complete features with minor wiring disconnections** is silently preventing quality improvements. The pipeline detects issues but fails to act on them — checks fire but suggestions aren't generated, suggestions are generated but repair routes don't exist, or entire language dialects are silently skipped.

**Key finding:** The accidental complexity is not in the individual components (semantic checks, repair steps, Kaizen hints are all well-implemented) but in the **wiring between components** — the connective tissue that turns detection into improvement.

### Impact Quantification

| Severity | Count | Pattern |
|----------|-------|---------|
| CRITICAL | 4 | Entire code paths silently skipped (Python integration, TS/JSX, orphaned checks, package.json) |
| HIGH | 5 | Feedback loops broken (missing suggestion mappings, language context not injected, repair routes missing) |
| MEDIUM | 6 | Quality signal degradation (language-blind scoring, terminology divergence, missing extensions) |
| **Total** | **15** | |

### Language Completeness

| Language | Wiring % | Biggest Gap |
|----------|----------|-------------|
| Python | 40% | Semantic checks never run; 0/4 Kaizen mappings |
| Go | 95% | MicroPrime language profile timing bug |
| Node.js | 75% | TS/JSX skip validation; package.json uncollected |
| Java | 70% | 6/12 semantic checks have no repair route |
| C# | 65% | 5/9 semantic checks have no repair route; missing block_scoped check |

---

## 2. Critical Gaps — Silent Quality Loss

### C-1: Python Semantic Checks Never Run in Integration Engine

**Files:** `integration_engine.py:1687-1936`
**Impact:** Python files get ZERO semantic validation at INTEGRATE time.

`_run_semantic_checks()` dispatches to C#, Java, Go, and Node.js validators — but has no branch for Python files. Python is the primary language and the most common target, yet it's the only language that gets no semantic checks during integration.

### C-2: TypeScript/JSX Files Skip Semantic Validation

**Files:** `forward_manifest_validator.py:655-656`
**Impact:** All TypeScript projects silently miss semantic quality scoring.

`_validate_non_python_file()` only routes `.js`, `.mjs`, `.cjs` to `_validate_js_file()`. The extensions `.ts`, `.tsx`, `.jsx` are valid Node.js files (listed in `NodeLanguageProfile.source_extensions`) but receive no semantic checks. This is a one-line fix.

### C-3: 4 Python Semantic Checks Are Orphaned Code

**Files:** `validators/semantic_checks.py:225-264`
**Impact:** Code exists but never executes — zero detection.

`run_semantic_checks()` defines 4 checks:
1. `check_duplicate_main_guards()` → `duplicate_main_guard`
2. `check_duplicate_definitions()` → `duplicate_definition`
3. `check_bare_except_pass()` → `bare_except_pass`
4. `check_phantom_dependencies()` → `phantom_dependency`

No call site exists in the Prime Contractor or integration pipeline. Python validation was refactored to use `validate_disk_compliance()` (L1-L10 suite), but these 4 checks were left behind and never integrated into the new path.

### C-4: Package.json Semantic Checks Never Collected

**Files:** `forward_manifest_validator.py:1198-1212`
**Impact:** Broken package.json can score 1.0.

`_validate_package_json()` performs basic structural validation but does NOT call `run_nodejs_semantic_checks()`. Three Node.js semantic check categories (`invalid_package_json`, `invalid_node_version`, `missing_module_type`) never enter `DiskComplianceResult.semantic_issues`, so they don't affect quality scores or generate Kaizen suggestions.

---

## 3. High Gaps — Feedback Loop Broken

### H-1: 4 Python Semantic Categories Missing from Kaizen Suggestions

**Files:** `prime_postmortem.py:859-919`
**Impact:** Kaizen feedback loop is dead for Python's 4 semantic checks.

Even if C-3 were fixed and the checks started running, no suggestions would be generated because `_SEMANTIC_CATEGORY_TO_SUGGESTION` has no entries for:
- `duplicate_main_guard`
- `duplicate_definition`
- `bare_except_pass`
- `phantom_dependency`

This is a pure dictionary edit — no logic changes required.

### H-2: Language Role + Coding Standards Never Injected into LLM Prompts

**Files:** `spec_builder.py:312-386`, `prime_contractor.py`
**Impact:** LLM prompts lack language-specific coding guidance for ALL languages.

Every `LanguageProfile` implements `coding_standards` (returns language-specific style rules) and has a `language_role` concept. The `spec_builder.py` extracts `language_profile` from context but **never calls** `language_profile.coding_standards` to populate `gen_context`. The drafter's `get_drafter_system_prompt()` accepts `coding_standards` parameter but always receives `None`.

This is the single most impactful gap — it directly prevents the LLM from receiving the language guidance that would prevent defects like CJS/ESM mixing, `var` usage, bare `except:pass`, etc.

### H-3: 11 Java/C# Semantic Checks Detected but Unroutable to Repair

**Files:** `repair/routing.py:111-128`
**Impact:** Detection without repair = passive-only feedback.

**Java (6 orphaned checks):**
| Check | Category | Repair Route | Repair Step |
|-------|----------|:---:|:---:|
| `_check_raw_type_usage()` | `raw_type_usage` | Missing | Missing |
| `_check_missing_override()` | `missing_override` | Missing | Missing |
| `_check_interface_file_contains_class()` | `interface_file_contains_class` | Missing | Missing |
| `_check_package_filepath_alignment()` | `package_filepath_mismatch` | Missing | Missing |
| `_check_duplicate_methods()` | `duplicate_method` | Missing | Missing |
| `_check_gradle_version()` | `invalid_java_version` | Missing | Missing |

**C# (5 orphaned checks):**
| Check | Category | Repair Route | Repair Step |
|-------|----------|:---:|:---:|
| `_check_console_writeline()` | `console_writeline_in_service` | Missing | Missing |
| `_check_missing_async_await()` | `missing_async_await` | Missing | Missing |
| `_check_missing_access_modifiers()` | `missing_access_modifier` | Missing | Missing |
| `_check_namespace_filepath_alignment()` | `namespace_filepath_mismatch` | Missing | Missing |
| `_check_missing_nullable_in_csproj()` | `missing_nullable_in_csproj` | Missing | Missing |

Note: All 11 checks have working Kaizen suggestion mappings — they generate hints for the next run. The gap is only in runtime repair.

### H-4: MicroPrime Language Profile Initialization Timing Bug

**Files:** `prime_contractor.py:766-773, 3885-3923`
**Impact:** Stub detection falls back to Python patterns for Go/Java/C#/Node.js.

`enable_micro_prime()` is called early (line 701) when `self._language_profile = None`. Later, `_build_generation_context()` resolves the language (line 3829), and `_apply_language_profile_to_engine()` updates `self._engine._language_profile` — but does NOT update `self.code_generator._language_profile`. MicroPrime operates with `None` language profile during generation.

### H-5: Python Repair Routing Uses `language=None`

**Files:** `repair/routing.py:103-110`
**Impact:** Works by accident — breaks if routing logic is tightened.

Python routes in `_ROUTING_TABLE` have `language=None` (legacy pattern) while all other languages use explicit language IDs. The filter logic happens to fall through correctly, but explicit `language_id="python"` routing is technically broken.

---

## 4. Medium Gaps — Quality Signal Degradation

### M-1: Quality Scoring is Language-Blind

**Files:** `forward_manifest_validator.py:461-503`

`compute_disk_quality_score()` uses hardcoded error=0.3/warning=0.1 penalties regardless of language. A Go `unchecked_error` (critical in Go culture) gets the same penalty as a Python `bare_except` (moderate concern). No dispatch mechanism for language-specific scoring formulas.

### M-2: Post-Mortem Doesn't Pass Language Context to Scoring

**Files:** `prime_postmortem.py:1568-1578`

`_evaluate_disk_quality()` calls `validate_disk_compliance()` without `language_id` or `LanguageProfile`. Same root cause as M-1.

### M-3: Python Semantic Category Terminology Diverges

**Files:** Multiple

`semantic_checks.py` uses `duplicate_definition`; `validate_disk_compliance()` uses `cross_scope_duplicate`. These are different checks with overlapping names, creating mapping confusion.

### M-4: C# Missing `block_scoped_namespace` Semantic Check

**Files:** `validators/csharp_semantic_checks.py`

Kaizen hint exists (`block_scoped_namespace_detected`, line 585), `_SEMANTIC_CATEGORY_TO_SUGGESTION` mapping exists (line 891), but NO semantic check implementation detects block-scoped namespaces. The entire suggestion path is wired but can never fire.

### M-5: Exemplar System Missing `.mjs/.cjs` Extensions

**Files:** `exemplars/models.py:134-144`

`_ext_to_language()` doesn't map `.mjs`/`.cjs` to `"nodejs"`. These files get `language="unknown"` fingerprints, preventing proper exemplar classification.

### M-6: No Per-Language Semantic Repair Config

**Files:** `repair/config.py:36,45`

`RepairConfig.semantic_repair_categories` is a single `frozenset` with no language dimension. Can't enable Go error-checking repair without also enabling Python import repair.

---

## 5. Wiring Completeness by Language

| Language | Semantic Checks | Integration Wiring | Repair Routes | Repair Steps | Kaizen Suggestions | Quality Scoring | Overall |
|----------|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| **Python** | 4 checks exist, **never run** | **MISSING** | 4 routes (`None` lang) | 4 steps | **0/4 mapped** | Generic | **40%** |
| **Go** | 6 checks, all wired | Wired | 5 routes | 4 steps | All mapped | Generic | **95%** |
| **Node.js** | 9 checks (6 impl'd) | Wired | 3 routes | 3 steps | All mapped | Generic, TS/JSX skipped | **75%** |
| **Java** | 12 checks, all wired | Wired | 4/10 routes | 3 steps | All mapped | Generic | **70%** |
| **C#** | 9 checks, all wired | Wired | 4/9 routes | 2 steps | All mapped | Generic | **65%** |

---

## 6. Wiring Completeness by Pipeline Stage

| Pipeline Stage | Python | Go | Node.js | Java | C# |
|---------------|:---:|:---:|:---:|:---:|:---:|
| **Language Profile** | Complete | Complete | Complete | Complete | Complete |
| **Semantic Detection** | Orphaned | Complete | Partial (TS skip) | Complete | Partial (missing block_scoped) |
| **Integration Validation** | **MISSING** | Complete | Complete | Complete | Complete |
| **Repair Routing** | Complete (fragile) | Complete | Partial (3/9) | Partial (4/10) | Partial (4/9) |
| **Repair Steps** | Complete | Complete | Partial | Partial | Partial |
| **Kaizen Suggestions** | **0/4 mapped** | Complete | Complete | Complete | Complete |
| **Quality Scoring** | Generic | Generic | Generic | Generic | Generic |
| **Prompt Injection** | **Missing** | **Missing** | **Missing** | **Missing** | **Missing** |
| **Exemplar Fingerprint** | Complete | Complete | Partial (.mjs/.cjs) | Complete | Complete |

---

## 7. Gap Detail: Node.js

### Fully Wired
- 6/6 implemented semantic checks execute during integration
- 3 repair routes with working steps (`var_to_const`, `dedup_require`, `contamination_strip_js`)
- All 9 semantic categories mapped to Kaizen suggestions
- `_validate_js_file()` collects semantic issues into `DiskComplianceResult`

### Gaps
1. **C-2**: `.ts/.tsx/.jsx` extensions skipped in `_validate_non_python_file()` dispatch
2. **C-4**: `_validate_package_json()` doesn't collect semantic issues
3. **H-3**: 6 unrouted categories (`console_log_in_service`, `unhandled_promise`, `module_system_mixing`, `invalid_package_json`, `invalid_node_version`, `missing_module_type`) — 3 are intentionally advisory, 3 are package.json checks that should be collected first
4. **M-5**: Exemplar system missing `.mjs/.cjs` mappings

### 5 PLANNED Semantic Checks (Not Yet Implemented)
- `check_callback_hell()` — deferred
- `check_unused_requires()` — deferred
- `check_missing_exports()` — deferred
- `check_typescript_any_overuse()` — deferred
- `check_cross_language_contamination()` Go support — deferred

---

## 8. Gap Detail: Python

### Fully Wired
- 10-layer validation suite in `validate_disk_compliance()` (import resolution, cross-scope duplicates, factory returns, discarded returns, method resolution, reachability)
- 4 repair routes with working steps (syntax, import, method_resolution, duplicate_main_guard)
- Repair steps: `semantic_duplicate_main_fix`, `semantic_import_fix`, `semantic_method_resolution_fix`, `semantic_discarded_return_fix`

### Gaps
1. **C-1**: `_run_semantic_checks()` in integration engine has no Python branch
2. **C-3**: `run_semantic_checks()` in `semantic_checks.py` is orphaned — 4 checks never execute
3. **H-1**: 4 semantic categories missing from `_SEMANTIC_CATEGORY_TO_SUGGESTION`
4. **H-5**: Python repair routes use `language=None` instead of `"python"`
5. **M-3**: Category terminology divergence between `semantic_checks.py` and `validate_disk_compliance()`

### Note on Dual Validation Systems
Python has TWO semantic validation systems:
1. **`semantic_checks.py`** — 4 simple checks (orphaned, never runs)
2. **`validate_disk_compliance()` L1-L10** — 10-layer suite (active, runs in postmortem)

The 4 checks in system 1 are NOT duplicated in system 2. They need to be either migrated into `validate_disk_compliance()` or wired into the integration engine independently.

---

## 9. Gap Detail: Go

### Fully Wired (95%)
- 6 semantic checks, all integrated
- 5 repair routes with 4 working steps
- All Kaizen suggestions mapped
- Forward manifest extractor handles Go
- Go parser + splicer fully implemented
- Comprehensive test coverage

### Gaps
1. **H-4**: MicroPrime language profile initialization timing bug — `code_generator._language_profile` is `None` during generation

---

## 10. Gap Detail: Java

### Fully Wired
- 12 semantic checks, all integrated into INTEGRATE phase
- All Kaizen suggestion mappings present
- Language profile complete (15 properties)
- Entry point registered

### Gaps
1. **H-3**: 6/12 semantic checks have no repair route or step
2. Repair capability limited to: syntax validation, import sorting, SQL parameterization, wildcard import cleanup (4 routes, 3 steps)

---

## 11. Gap Detail: C#

### Fully Wired
- 9 semantic checks, all integrated (including C#-specific `check_using_coverage()`)
- All Kaizen suggestion mappings present (9 entries)
- Language profile most comprehensive (18 properties, including `.sln` generation)
- Anzen gate deduplication for SQL injection
- Entry point registered

### Gaps
1. **H-3**: 5/9 semantic checks have no repair route or step
2. **M-4**: `block_scoped_namespace` — Kaizen hint exists, suggestion mapping exists, but no semantic check to detect it
3. Repair capability limited to: syntax validation, convention fixing, SQL parameterization (4 routes, 2 steps)

---

## 12. Gap Detail: Cross-Cutting

### H-2: Language Context Not Injected into Prompts

This is the most impactful cross-cutting gap. Every language profile implements `coding_standards` with rich guidance:

- **Python**: PEP 8, type hints, docstrings
- **Go**: Effective Go, error handling, package naming
- **Node.js**: CJS vs ESM rules, `const` preference, structured logging
- **Java**: Spring conventions, `@Override`, SLF4J logging
- **C#**: File-scoped namespaces, `ILogger<T>`, async/await patterns

This guidance is exactly what prevents the defects that semantic checks later detect. But `spec_builder.py` never extracts it from the language profile, so prompts always have `coding_standards=None`.

### M-1 + M-2: Language-Blind Scoring

The quality scoring formula applies Python-centric severity weights to all languages:
```
semantic_penalty = max(0.0, 1.0 - (error_count * 0.3) - (warning_count * 0.1))
```

This means:
- A Go `unchecked_error` (critical defect, unique to Go) penalizes the same as any other error
- A Java `raw_type_usage` (moderate concern) penalizes the same as a Python `phantom_dependency`
- No mechanism exists to dispatch to language-specific scoring formulas

### M-6: Repair Config Not Language-Aware

`RepairConfig.semantic_repair_categories` is a flat set. Adding a new Go repair category enables it for all languages. This creates coupling between language repair investments.
