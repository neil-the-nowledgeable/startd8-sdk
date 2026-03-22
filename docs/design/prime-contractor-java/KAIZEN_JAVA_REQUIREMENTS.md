# Kaizen for Prime Contractor — Java Language Requirements

> **Version:** 1.0.0
> **Status:** DRAFT
> **Date:** 2026-03-18
> **Parent:** [KAIZEN_PRIME_REQUIREMENTS.md](../prime/KAIZEN_PRIME_REQUIREMENTS.md)
> **Language Profile:** `JavaLanguageProfile` (`src/startd8/languages/java.py`)
> **Scope:** Java-specific quality measurement, validation, and feedback for the Kaizen system

---

## Table of Contents

1. [Overview](#1-overview)
2. [Disk Validation](#2-disk-validation)
3. [Semantic Checks](#3-semantic-checks)
4. [Quality Scoring](#4-quality-scoring)
5. [Repair Pipeline](#5-repair-pipeline)
6. [Feedback Loop Hints](#6-feedback-loop-hints)
7. [Generation Profile](#7-generation-profile)
8. [Traceability Matrix](#8-traceability-matrix)
9. [Verification Strategy](#9-verification-strategy)

---

## 1. Overview

Java is the newest language in the Prime Contractor pipeline and the least mature in terms of validation and generation infrastructure. Unlike Python (full AST-based repair, rich semantic validators) or Go (goimports auto-fix, regex parser, text-based body splicing), Java relies on a thinner validation layer with a text-based fallback when `javalang` is unavailable.

### Key Advantages

- **Strong static typing** — Compilation catches many errors that require semantic analysis in dynamic languages.
- **Gradle ecosystem** — Dependency resolution, compilation, and testing through a single build tool.
- **Mature tooling** — `google-java-format`, `checkstyle`, `spotbugs` available for formatting and static analysis.
- **javalang parser** — When installed, provides AST-level syntax validation; text-based fallback for environments without it.

### Key Challenges

- **Boilerplate inflation** — LLMs tend to generate verbose Java code (unnecessary getters/setters, excessive class hierarchies, redundant exception handling). This inflates token cost and increases stub surface area.
- **Build tool dependency** — Unlike Python (single-file executable) or Go (`go build` with module auto-resolution), Java requires a complete Gradle/Maven project structure for compilation validation. Per-file `javac` validation is limited without resolved dependencies.
- **No auto-import fixer** — Go has `goimports`; Python has `isort`+`autoflake`. Java has no CLI-callable import fixer that works without a full IDE project. Generated code with missing or incorrect imports cannot be auto-repaired.
- **Cross-language contamination risk** — The Python-stub-in-wrong-language problem (documented in MULTI_LANGUAGE_TEMPLATE_AND_VALIDATION_REQUIREMENTS.md) affects Java files routed through trivial/simple tiers.

### Generation Strategy

Java tasks use **file-whole generation** (MicroPrime bypass). Element-by-element splicing is not supported because:
- Java's one-public-class-per-file convention makes file-level generation natural.
- Package declarations, import ordering, and class-level structure require whole-file coherence.
- The `merge_strategy_preference` is `"simple"` (full file replacement, not merge).

---

## 2. Disk Validation

### REQ-KZ-JV-100: Java Disk Compliance

The Kaizen disk compliance check for Java files MUST validate the following properties. Each check populates the `DiskComplianceResult` fields used by the quality scoring formula (REQ-KZ-JV-300).

#### REQ-KZ-JV-100.1: Syntax Validity

Java source files MUST pass syntax validation via `JavaLanguageProfile.validate_syntax()`. This uses `javalang.parse.parse()` when available, falling back to text-based validation (balanced braces + type declaration presence).

**Acceptance criteria:**
- Files that fail `javalang` parsing are marked as syntax-invalid with the parser error message.
- Files that fail text-based fallback (unbalanced braces, no type declaration) are marked as syntax-invalid.
- Files containing Python fingerprints (`def `, `import os`, `from __future__`, `print(`, `self.`, shebang lines) are rejected as cross-language contamination before any other check runs.

#### REQ-KZ-JV-100.2: Package-Directory Consistency

The `package` declaration in each `.java` file MUST match the file's directory path within the source tree.

**Acceptance criteria:**
- `package com.example.service;` in a file at `src/main/java/com/example/service/Foo.java` passes.
- `package com.example.service;` in a file at `src/main/java/com/other/Foo.java` fails with root cause `PACKAGE_DIRECTORY_MISMATCH`.
- Files with no `package` declaration in a non-default-package directory fail with root cause `MISSING_PACKAGE_DECLARATION`.

#### REQ-KZ-JV-100.3: Class-Filename Match

The public class name MUST match the filename (without `.java` extension). This is a Java language requirement enforced by `javac`.

**Acceptance criteria:**
- `public class OrderService` in `OrderService.java` passes.
- `public class OrderService` in `Service.java` fails with root cause `CLASS_FILENAME_MISMATCH`.
- Files with no public class (package-private classes, interfaces, enums) are exempt from this check.

#### REQ-KZ-JV-100.4: Import Well-Formedness

All import statements MUST be syntactically valid Java imports.

**Acceptance criteria:**
- `import java.util.List;` — valid.
- `import static org.junit.Assert.assertEquals;` — valid.
- `import java.util.*;` — flagged as `WILDCARD_IMPORT` (warning severity, not error). The `JavaLanguageProfile.coding_standards` explicitly prohibits wildcard imports.
- `from java.util import List` — flagged as cross-language contamination (Python import syntax in Java file).
- Import statements without trailing semicolons — flagged as syntax error.

#### REQ-KZ-JV-100.5: Cross-Language Contamination Guard

Java files MUST NOT contain Python artifacts. This extends the `_PYTHON_FINGERPRINTS` check already present in `_validate_java_syntax()`.

**Acceptance criteria:**
- Any of the following in a `.java` file triggers `CROSS_LANGUAGE_CONTAMINATION`:
  - `def ` (Python function definition)
  - `import os` (Python stdlib import)
  - `from __future__ import annotations` (Python future import)
  - `print(` without a preceding `System.out.` (Python print vs Java)
  - `self.` (Python instance reference)
  - `#!/usr/bin/env python` or `#!/usr/bin/python` (Python shebang)
- Contamination is severity `error` — the file is non-functional.

#### REQ-KZ-JV-100.6: build.gradle Validity

Generated `build.gradle` files MUST have valid structure, as produced by `JavaLanguageProfile.generate_dependency_file()`.

**Acceptance criteria:**
- `plugins {}` block present and non-empty.
- `repositories {}` block present (at minimum `mavenCentral()`).
- `dependencies {}` block present when dependencies are declared.
- Dependency coordinates follow `group:artifact:version` format (or `group:artifact` without version for BOM-managed deps).
- `java { sourceCompatibility }` and `targetCompatibility` reference a valid Java version (11, 17, 21).
- No Python content in `build.gradle` (contamination guard).

### REQ-KZ-JV-101: Java-Specific Validation Tools

The following external tools are available for Java validation, ordered by weight (lightest to heaviest):

| Tool | Command | What It Catches | Weight |
|------|---------|-----------------|--------|
| Text-based fallback | `_text_based_java_validate()` | Balanced braces, type declaration presence, Python fingerprints | Trivial (in-process) |
| javalang parser | `javalang.parse.parse()` | Full Java syntax validation, AST structure | Light (in-process, optional dependency) |
| javac | `javac -Xlint:all {file}` | Compilation errors + all warnings (unchecked, deprecation, etc.) | Medium (requires JDK, single-file only without deps) |
| Gradle compile | `gradle compileJava` | Full compilation with dependency resolution | Heavy (requires project structure + network for deps) |
| checkstyle | `gradle checkstyleMain` | Style violations, naming conventions | Heavy (optional, configurable rules) |
| spotbugs | `gradle spotbugsMain` | Bug patterns, null dereference, resource leaks | Heavy (optional, analysis-intensive) |

**Kaizen disk validation** uses the text-based fallback or javalang parser (whichever is available). Gradle compilation is deferred to the integration/test phases where a complete project structure exists. Checkstyle and spotbugs are optional quality signals, not gating validators.

---

## 3. Semantic Checks

### REQ-KZ-JV-200: Java Semantic Validators

Semantic checks populate `semantic_issues` in `DiskComplianceResult`. Each check produces structured entries with `category`, `severity`, `message`, and optional `line`/`symbol` fields (per REQ-SV-101 from the parent Semantic Validation Requirements).

#### REQ-KZ-JV-200.1: `check_empty_catch_blocks()`

Detect `catch` blocks that swallow exceptions without any handling.

**Patterns detected:**
```java
catch (Exception e) { }
catch (IOException e) { /* empty */ }
catch (RuntimeException e) { // swallowed }
```

**Exempt patterns (not flagged):**
```java
catch (InterruptedException e) { Thread.currentThread().interrupt(); }
catch (Exception e) { logger.debug("ignored", e); }
```

**Severity:** warning
**Category:** `empty_catch_block`

#### REQ-KZ-JV-200.2: `check_missing_override_annotation()`

Detect methods that override a superclass or interface method without `@Override`.

**Detection heuristic (text-based):** Methods named `toString()`, `equals(Object)`, `hashCode()`, `run()`, `call()`, `close()`, `compare()`, `compareTo()`, `iterator()` without a preceding `@Override` annotation. This is an approximation — full detection requires type resolution.

**Severity:** warning
**Category:** `missing_override`

#### REQ-KZ-JV-200.3: `check_raw_type_usage()`

Detect raw type usage where generics should be parameterized.

**Patterns detected:**
```java
List items = new ArrayList();     // raw List
Map cache = new HashMap();        // raw Map
Set values = new HashSet();       // raw Set
```

**Not flagged:**
```java
List<String> items = new ArrayList<>();  // properly parameterized
Class<?> clazz = ...;                    // wildcard is acceptable
```

**Severity:** warning
**Category:** `raw_type_usage`

#### REQ-KZ-JV-200.4: `check_missing_access_modifiers()`

Detect class and method declarations without explicit access modifiers. Java defaults to package-private, which is sometimes intentional but often indicates the LLM forgot to specify visibility.

**Patterns detected:**
```java
class OrderService { ... }              // missing access modifier on class
void processOrder(Order order) { ... }  // missing access modifier on method
```

**Severity:** warning
**Category:** `missing_access_modifier`

#### REQ-KZ-JV-200.5: `check_missing_null_checks()`

Detect method parameters that are used without null validation in public methods. This is a heuristic check — it flags public methods where parameters are dereferenced (method call or field access) without a preceding null check.

**Severity:** warning (not error — the code compiles; null safety is a quality concern)
**Category:** `missing_null_check`

#### REQ-KZ-JV-200.6: `check_cross_language_contamination()`

Detect non-Java syntax patterns in `.java` files beyond the Python fingerprint check (REQ-KZ-JV-100.5). This includes:
- Go syntax: `func `, `package main`, `:=`, `fmt.Println`
- JavaScript/TypeScript syntax: `const `, `let `, `=>`, `console.log`
- Rust syntax: `fn `, `let mut`, `println!`

**Severity:** error
**Category:** `cross_language_contamination`

---

## 4. Quality Scoring

### REQ-KZ-JV-300: Java Quality Score Formula

The Java disk quality score uses the same composite formula structure as the parent Kaizen system, with Java-specific weights:

```
java_quality_score = (compilation_check   x 0.30)
                   + (import_validity     x 0.15)
                   + (stub_penalty        x 0.20)
                   + (type_safety         x 0.15)
                   + (contamination_check x 0.10)
                   + (convention_compliance x 0.10)
```

**Component definitions:**

| Component | Range | Calculation |
|-----------|-------|-------------|
| `compilation_check` | 0.0 or 1.0 | 1.0 if `validate_syntax()` passes; 0.0 otherwise |
| `import_validity` | 0.0 – 1.0 | `1.0 - (invalid_imports / total_imports)`. Wildcard imports count as 0.5 penalty each. |
| `stub_penalty` | 0.0 – 1.0 | `1.0 - (stub_count / total_methods)`. Stubs detected by `stub_patterns` (see below). |
| `type_safety` | 0.0 – 1.0 | `1.0 - (raw_type_count x 0.1)` (capped at 0.0). Each raw type usage deducts 0.1. |
| `contamination_check` | 0.0 or 1.0 | 1.0 if no cross-language contamination; 0.0 if any Python/Go/JS fingerprint detected. |
| `convention_compliance` | 0.0 – 1.0 | Average of: class-filename match (0/1), access modifiers present (ratio), @Override annotations present (ratio). |

**Java stub patterns** (from `JavaLanguageProfile.stub_patterns`):
- `throw new UnsupportedOperationException(...)` — standard Java "not implemented" idiom
- `throw new RuntimeException("not implemented...")` — variant
- `throw new RuntimeException("TODO...")` — variant
- `// TODO` at line start — comment-based stub marker

### REQ-KZ-JV-301: Java Root Causes

The following root cause categories are specific to Java. These populate the `root_causes` field in Kaizen metrics and drive the feedback loop (REQ-KZ-JV-500).

| Root Cause | Description | Severity |
|-----------|-------------|----------|
| `CROSS_LANGUAGE_CONTAMINATION` | Python, Go, JS, or other non-Java syntax detected in a `.java` file | Critical |
| `COMPILATION_ERROR` | File fails `validate_syntax()` — unbalanced braces, missing type declaration, javalang parse error | Critical |
| `MISSING_PACKAGE_DECLARATION` | No `package` statement in a file that is not in the default package | High |
| `CLASS_FILENAME_MISMATCH` | Public class name does not match the `.java` filename | High |
| `EMPTY_CATCH_BLOCK` | Exception caught and silently discarded | Medium |
| `RAW_TYPE_USAGE` | Generic type used without type parameters (`List` instead of `List<String>`) | Medium |
| `MISSING_DEPENDENCY` | Import references a class not provided by any dependency in `build.gradle` | Medium |
| `BUILD_GRADLE_ERROR` | Generated `build.gradle` has structural errors (missing blocks, invalid syntax) | Medium |
| `WILDCARD_IMPORT` | `import java.util.*` instead of explicit imports | Low |
| `MISSING_ACCESS_MODIFIER` | Class or method without explicit `public`/`private`/`protected` | Low |
| `MISSING_OVERRIDE_ANNOTATION` | Overridden method without `@Override` | Low |
| `BOILERPLATE_INFLATION` | Excessive code volume relative to functional content (getter/setter ratio, empty constructors, trivial delegation) | Low |

### REQ-KZ-JV-302: Boilerplate Inflation Detection

LLMs frequently generate excessive Java boilerplate. The Kaizen system MUST detect and measure boilerplate inflation to drive conciseness hints.

**Boilerplate indicators:**
- Getter/setter pairs for fields that could use `public final` or Java 16+ `record`
- Empty default constructors (Java provides these implicitly)
- Trivial delegation methods that add no logic
- Excessive Javadoc on self-documenting methods (e.g., `/** Gets the name. */ public String getName()`)

**Metric:** `boilerplate_ratio = boilerplate_lines / total_lines`. Ratios above 0.4 trigger `BOILERPLATE_INFLATION` root cause.

---

## 5. Repair Pipeline

### REQ-KZ-JV-400: Java Repair Capabilities

The `JavaLanguageProfile` has `repair_enabled = False`. This section documents the current state and recommendations for future repair support.

#### REQ-KZ-JV-400.1: Currently Available Repairs

| Repair Step | Available | Notes |
|-------------|-----------|-------|
| `fence_strip` | Yes | Removes markdown code fences from LLM output (language-agnostic) |
| `basic_formatting` | Limited | Indentation normalization only; no Java-aware formatting |
| `import_fix` | No | No equivalent to Python's `autoflake`/`isort` or Go's `goimports` |
| `AST-based repair` | No | `javalang` provides parsing but not code generation/transformation |
| `auto-import` | No | Would require classpath resolution and dependency analysis |

#### REQ-KZ-JV-400.2: Recommended Future Repairs

| Repair Step | Tool | Priority | Rationale |
|-------------|------|----------|-----------|
| Format | `google-java-format` | P1 | Canonical Java formatting; requires Java runtime but no project structure |
| Import sort | `google-java-format --fix-imports-only` | P1 | Removes unused imports and sorts remaining; does not add missing imports |
| Lint fix | Spotless Gradle plugin (`spotlessApply`) | P2 | Requires Gradle project structure; combines formatting + import sorting |
| Null annotation | Manual hint injection | P3 | Add `@Nullable`/`@NonNull` annotations; requires dependency on `jsr305` or `jakarta.annotation` |

#### REQ-KZ-JV-400.3: Repair Gap Impact

Without auto-import repair, Java files with missing imports fail compilation but cannot be auto-fixed. This makes the feedback loop (REQ-KZ-JV-500) the primary mechanism for reducing import errors: rather than repairing after generation, the system steers the LLM to produce correct imports upfront via Kaizen hints.

### REQ-KZ-JV-402: Java Semantic-to-Repair Bridge Convention

**Status:** Phase 1 (advisory-only; `sql_injection_risk` flows through shared bridge)
**Depends on:** REQ-KZ-JV-400, REQ-KZ-CS-402a (multi-language dispatch pattern)

Wire Java semantic check results into the repair pipeline, following the pattern established by C#'s REQ-KZ-CS-402a/b/c. Java's `java_semantic_checks.py` has 9 check functions producing 10 distinct category strings; each is classified as **repairable** (routed to a repair step) or **advisory-only** (surfaced as Kaizen hints in postmortem).

> **Note:** The module docstring in `java_semantic_checks.py` previously said "Eight checks" — corrected to "Nine checks (10 category strings)" as part of this requirement validation.

#### REQ-KZ-JV-402a: Multi-Language Dispatch

Add `.java` to `_SEMANTIC_REPAIR_EXTENSIONS` in `repair/orchestrator.py` and add `_repair_single_java_file()` dispatch function when at least one Java-specific repair step exists (Phase 2+). Pattern: `_repair_single_csharp_file()` in the same module.

`sql_injection_risk` already flows through the shared `_REPAIRABLE_CATEGORIES` entry added for C#.

#### REQ-KZ-JV-402a.1: Language-Aware Bridge Dispatch (NEW)

The semantic bridge (`semantic_bridge.py`) currently maps `sql_injection_risk` → `"csharp_sql_injection"` unconditionally via `_CATEGORY_TO_PATTERN`. This is **language-agnostic** — there is no dispatch logic based on file extension. To support Java SQL repair alongside C# SQL repair, the bridge MUST be extended with language-aware pattern resolution.

**Design options (choose one during implementation):**
1. **Composite key**: Change `_CATEGORY_TO_PATTERN` to `dict[tuple[str, str], str]` keyed by `(category, language_id)` — e.g., `("sql_injection_risk", "java") → "java_sql_injection"`.
2. **Language-agnostic pattern name**: Use a single pattern name like `"sql_injection"` and let the routing table discriminate by `language_id` column.
3. **Per-language override dict**: `_CATEGORY_TO_PATTERN_OVERRIDES: dict[str, dict[str, str]]` keyed by language_id, falling back to the base `_CATEGORY_TO_PATTERN`.

Option 2 is simplest but requires renaming the existing `"csharp_sql_injection"` routing entry. Option 3 is most backward-compatible.

**Acceptance criteria:**
- Java `.java` files with `sql_injection_risk` produce `Diagnostic(category="security", pattern="java_sql_injection")` (or equivalent).
- C# `.cs` files continue to produce `Diagnostic(category="security", pattern="csharp_sql_injection")` (no regression).

#### REQ-KZ-JV-402b: Category Registration

9 check functions produce 10 distinct category strings. `_check_package_filepath_alignment()` emits both `package_filepath_mismatch` and `package_case_mismatch`.

| Category | Severity | Classification | Rationale |
|---|---|---|---|
| `sql_injection_risk` | error | **Repairable** | Already in `_REPAIRABLE_CATEGORIES` (shared with C#). No Java-specific step yet — Phase 3 adds PreparedStatement conversion. |
| `wildcard_import` | warning | **Potentially repairable** | `google-java-format --fix-imports-only` removes unused imports and sorts remaining, but does **not** expand `*` wildcards to explicit imports. Phase 2 repair step must implement wildcard expansion independently (AST-based or regex-based). |
| `system_out_in_service` | warning | Advisory | Requires logging framework config knowledge. |
| `interface_file_contains_class` | warning | Advisory | Requires file splitting + import graph updates. |
| `empty_catch_block` | warning | Advisory | Correct fix depends on exception semantics. |
| `raw_type_usage` | warning | Advisory | Generic inference requires type-checker context. |
| `missing_override` | warning | Advisory | Requires class hierarchy resolution. |
| `missing_access_modifier` | warning | Advisory | Correct modifier depends on intended API surface. |
| `package_filepath_mismatch` | warning | Advisory | Fix has downstream ripple effects. |
| `package_case_mismatch` | warning | Advisory | Case variant of package-path mismatch. Emitted by same check function as `package_filepath_mismatch`. |

#### REQ-KZ-JV-402c: Compliance Results Collection

**Status:** IMPLEMENTED (2026-03-22). Java semantic results stored in `compliance_results` in `integration_engine.py:_run_semantic_checks()`.

#### REQ-KZ-JV-402d: RepairConfig Opt-In (NEW)

`RepairConfig.semantic_repair_categories` defaults to `frozenset()` (empty). The orchestrator skips repair when this set is empty (line 1084 of `orchestrator.py`). Each phase MUST document which categories to add to this set; otherwise new routes silently fail to activate.

**Acceptance criteria:**
- Phase 2 adds `"wildcard_import"` to `semantic_repair_categories` default.
- Phase 3 adds `"sql_injection_risk"` to `semantic_repair_categories` default (or documents explicit opt-in via config).

#### REQ-KZ-JV-402e: Phased Repair Step Plan

**Phase 1 (current):** All categories advisory-only. `sql_injection_risk` flows through shared bridge but no Java-specific repair step fires. The routing table has no `language_id="java"` entry for `"security"` category. This phase establishes wiring and placeholder routing only — no actual repairs are performed on Java files.

**Phase 1 deliverables:**
- Add `("security", "java_sql_injection", ["java_syntax_validate"], "HIGH", "java")` **placeholder route** in `routing.py`. This routes to syntax validation only; the actual parameterize step is added in Phase 3.
- Implement language-aware bridge dispatch (REQ-KZ-JV-402a.1) so Java files produce `java_sql_injection` pattern instead of `csharp_sql_injection`.
- Unit test confirming Java `.java` files with `sql_injection_risk` produce correct `Diagnostic` objects and match the Java routing entry.

**Phase 2:** `JavaImportSortStep` in `repair/steps/java_import_sort.py`. This step implements wildcard expansion via regex-based import rewriting (not `google-java-format`, which only sorts/removes unused imports without expanding wildcards).
- Register `wildcard_import` in `_REPAIRABLE_CATEGORIES`.
- Add route `("semantic", "wildcard_import", ["java_import_sort", "java_syntax_validate"], "MEDIUM", "java")`.
- Add `.java` to `_SEMANTIC_REPAIR_EXTENSIONS`.
- Add `_repair_single_java_file()` dispatch function in `orchestrator.py`.
- Add `"wildcard_import"` to `RepairConfig.semantic_repair_categories` default.
- Add `"java_import_sort"` to `_CANONICAL_ORDER` and `_STEP_FACTORIES` in `routing.py`.

**Phase 3:** `JavaSqlParameterizeStep` in `repair/steps/java_sql_parameterize.py` — deterministic rewrite of `"SELECT..." + var` to `PreparedStatement` with `?` placeholders and `setString()`/`setInt()` calls.
- Update Phase 1 placeholder route: `java_sql_injection` → `["java_sql_parameterize", "java_syntax_validate"]`.
- Add `"sql_injection_risk"` to `RepairConfig.semantic_repair_categories` default.
- Add `"java_sql_parameterize"` to `_CANONICAL_ORDER` and `_STEP_FACTORIES` in `routing.py`.
- Test patterns: string concatenation (`+`), `String.format()`, `StringBuilder.append()`.

---

## 6. Feedback Loop Hints

### REQ-KZ-JV-500: Java-Specific Kaizen Hints

Kaizen hints are injected into the LLM prompt context to address recurring root causes. Each hint maps to one or more root causes from REQ-KZ-JV-301.

#### REQ-KZ-JV-500.1: Standard Java Hint Library

| Hint ID | Root Cause Target | Hint Text |
|---------|------------------|-----------|
| `JV-H-01` | `RAW_TYPE_USAGE` | "Always parameterize generic types. Use `List<String>`, not `List`. Use `Map<String, Object>`, not `Map`." |
| `JV-H-02` | `EMPTY_CATCH_BLOCK` | "Never swallow exceptions silently. At minimum, log the exception: `logger.error(\"...\", e);`. For InterruptedException, restore the interrupt flag: `Thread.currentThread().interrupt();`." |
| `JV-H-03` | `MISSING_OVERRIDE_ANNOTATION` | "Always annotate overridden methods with `@Override`. This enables compile-time verification that the method signature matches the supertype." |
| `JV-H-04` | `WILDCARD_IMPORT` | "Use explicit imports, never wildcard imports. Write `import java.util.List;` not `import java.util.*;`." |
| `JV-H-05` | `MISSING_ACCESS_MODIFIER` | "Declare explicit access modifiers on all classes, methods, and fields. Prefer the most restrictive modifier that satisfies the design (`private` > package-private > `protected` > `public`)." |
| `JV-H-06` | `BOILERPLATE_INFLATION` | "Prefer concise Java idioms: use `record` types for immutable data classes (Java 16+), `var` for local variables with obvious types (Java 10+), try-with-resources for AutoCloseable. Omit trivial getters/setters when a public final field or record suffices." |
| `JV-H-07` | `MISSING_PACKAGE_DECLARATION` | "Every Java file must start with a `package` declaration matching its directory path. For example, `src/main/java/com/example/service/OrderService.java` must begin with `package com.example.service;`." |
| `JV-H-08` | `CLASS_FILENAME_MISMATCH` | "The public class name must exactly match the filename. `OrderService.java` must contain `public class OrderService`." |
| `JV-H-09` | `MISSING_DEPENDENCY` | "Only import classes from dependencies declared in `build.gradle`. If you use a third-party library, include it in the `dependencies {}` block with the correct Gradle coordinate (`group:artifact:version`)." |
| `JV-H-10` | `CROSS_LANGUAGE_CONTAMINATION` | "You are generating Java code. Do not use Python syntax (`def`, `self.`, `import os`, `from X import Y`), Go syntax (`func`, `:=`), or JavaScript syntax (`const`, `let`, `=>`)." |

#### REQ-KZ-JV-500.2: Build Tool Hints

| Hint ID | Context | Hint Text |
|---------|---------|-----------|
| `JV-H-20` | Gradle dependency | "Use Gradle dependency notation: `implementation 'group:artifact:version'`. For test dependencies use `testImplementation`. For compile-only dependencies use `compileOnly`." |
| `JV-H-21` | Gradle plugins | "Apply the `java` plugin and the `application` plugin (if the project has a main class). Use `sourceCompatibility` and `targetCompatibility` to set the Java version." |

#### REQ-KZ-JV-500.3: Testing Pattern Hints

| Hint ID | Context | Hint Text |
|---------|---------|-----------|
| `JV-H-30` | JUnit 5 | "Use JUnit 5 (`org.junit.jupiter.api.Test`), not JUnit 4. Annotate test methods with `@Test`, use `Assertions.assertEquals()` (not `Assert.assertEquals()`), and use `@BeforeEach`/`@AfterEach` (not `@Before`/`@After`)." |
| `JV-H-31` | Mockito | "For mocking, use Mockito with `@ExtendWith(MockitoExtension.class)` and `@Mock` annotations. Use `when(...).thenReturn(...)` for stubbing and `verify(...)` for interaction testing." |

---

## 7. Generation Profile

### REQ-KZ-JV-600: Java Generation Characteristics

This section documents the Java-specific generation profile as configured in `JavaLanguageProfile`, for reference by Kaizen analysis and prompt construction.

#### REQ-KZ-JV-600.1: Language Profile Properties

| Property | Value | Notes |
|----------|-------|-------|
| `language_id` | `"java"` | Used for language dispatch in validators and generators |
| `source_extensions` | `[".java"]` | Single extension for Java source |
| `build_file_patterns` | `["build.gradle", "settings.gradle", "pom.xml", "build.gradle.kts"]` | Gradle preferred; Maven supported |
| `syntax_check_command` | `None` | Per-file `javac` requires resolved deps; validation via `javalang` or text-based fallback |
| `lint_command` | `None` | No lightweight CLI linter; `checkstyle`/`spotbugs` require Gradle |
| `test_command` | `["gradle", "test"]` | Runs JUnit tests via Gradle |
| `merge_strategy_preference` | `"simple"` | Full file replacement (no element-by-element merge) |
| `repair_enabled` | `False` | No Java-specific repair steps available |
| `docker_base_image` | `"eclipse-temurin:21-jdk"` | Build-stage image with JDK 21 |
| `docker_runtime_image` | `"eclipse-temurin:21-jre-alpine"` | Runtime image (JRE only, Alpine for size) |

#### REQ-KZ-JV-600.2: Framework Detection

The `JavaLanguageProfile.framework_imports` provides detection and dependency mapping for:

| Framework | Detection Markers | Gradle Dependencies |
|-----------|------------------|---------------------|
| Spring Boot | `@SpringBootApplication`, `SpringApplication` | `spring-boot-starter`, `spring-boot-starter-web` |
| JPA | `@Entity`, `jakarta.persistence`, `JpaRepository` | `spring-boot-starter-data-jpa`, `jakarta.persistence-api` |
| SLF4J | `LoggerFactory`, `@Slf4j` | `slf4j-api` |
| gRPC | `grpc`, `proto`, `protobuf` | `grpc-netty`, `grpc-stub` |
| Log4j | `log4j`, `LogManager` | `log4j-core` |

#### REQ-KZ-JV-600.3: Dependency File Generation

`generate_dependency_file()` produces a `build.gradle` with:
- `plugins { id 'java'; id 'application' }`
- `java { sourceCompatibility = JavaVersion.VERSION_21; targetCompatibility = ... }` (configurable via `java_version` metadata)
- `repositories { mavenCentral() }`
- `dependencies { implementation '...' }` for each declared dependency
- `application { mainClass = '...' }` when a module path (main class) is provided

#### REQ-KZ-JV-600.4: Service Metadata Derivation

`derive_service_metadata()` extracts from plan features:
- `java_package` — from feature attribute or derived from target file paths via `_derive_package()`
- `build_system` — from feature attribute or inferred from build file presence (defaults to `"gradle"`)
- `java_version` — from feature attribute or onboarding config (defaults to `"21"`)
- `spring_boot` — detected from feature flags or dependency/API signature content

#### REQ-KZ-JV-600.5: Project Context Injection

`build_project_context_section()` injects into the LLM prompt:
- Package declaration requirement (derived from target file path)
- Public class name requirement (derived from filename)
- Java version and build system
- Import rules (fully qualified, grouped, no wildcards, semicolons)
- Structural rules (one public class per file, naming conventions, immutability preference, try-with-resources)

---

## 8. Traceability Matrix

### Requirements to Parent Kaizen Layers

| Java Requirement | Parent Kaizen Layer | Parent Requirement | Notes |
|-----------------|--------------------|--------------------|-------|
| REQ-KZ-JV-100 (Disk Compliance) | Layer 1 — Post-Mortem Parity | REQ-KZ-100 | Java-specific disk validation within the post-mortem pipeline |
| REQ-KZ-JV-101 (Validation Tools) | Layer 1 — Post-Mortem Parity | REQ-KZ-100 | External tool inventory for Java |
| REQ-KZ-JV-200 (Semantic Validators) | Layer 3 — Run Metrics | REQ-KZ-300 | Populates `semantic_issues` in `DiskComplianceResult` |
| REQ-KZ-JV-300 (Quality Score) | Layer 3 — Run Metrics | REQ-KZ-300 | Java-specific weight distribution in composite score |
| REQ-KZ-JV-301 (Root Causes) | Layer 4 — Cross-Run Aggregation | REQ-KZ-400 | Root cause taxonomy for trend analysis |
| REQ-KZ-JV-302 (Boilerplate Detection) | Layer 3 — Run Metrics | REQ-KZ-300 | Java-specific metric for LLM verbosity |
| REQ-KZ-JV-400 (Repair) | Layer 5 — Feedback Loop | REQ-KZ-500 | Repair gap drives higher reliance on feedback hints |
| REQ-KZ-JV-500 (Hints) | Layer 5 — Feedback Loop | REQ-KZ-500/501/502 | Java-specific hint library injected into `kaizen-config.json` |
| REQ-KZ-JV-600 (Generation Profile) | — | — | Reference documentation; no direct parent requirement |

### Requirements to Language Profile Implementation

| Java Requirement | `JavaLanguageProfile` Method/Property | Status |
|-----------------|--------------------------------------|--------|
| REQ-KZ-JV-100.1 | `validate_syntax()` | Implemented |
| REQ-KZ-JV-100.4 | `get_import_patterns()`, `get_import_syntax_guidance()` | Implemented |
| REQ-KZ-JV-100.5 | `_PYTHON_FINGERPRINTS` in `_validate_java_syntax()` | Implemented |
| REQ-KZ-JV-100.6 | `generate_dependency_file()` | Implemented |
| REQ-KZ-JV-200.1 | — | Not implemented (new semantic check) |
| REQ-KZ-JV-200.2 | — | Not implemented (new semantic check) |
| REQ-KZ-JV-200.3 | — | Not implemented (new semantic check) |
| REQ-KZ-JV-200.4 | — | Not implemented (new semantic check) |
| REQ-KZ-JV-200.5 | — | Not implemented (new semantic check) |
| REQ-KZ-JV-200.6 | `_PYTHON_FINGERPRINTS` (partial) | Partially implemented (Python only; Go/JS/Rust not checked) |
| REQ-KZ-JV-300 | — | Not implemented (scoring formula) |
| REQ-KZ-JV-301 | — | Not implemented (root cause taxonomy) |
| REQ-KZ-JV-302 | — | Not implemented (boilerplate detection) |
| REQ-KZ-JV-400 | `repair_enabled = False` | Documented; no repair pipeline |
| REQ-KZ-JV-402a.1 | `semantic_bridge.py` `_CATEGORY_TO_PATTERN` | Not implemented (language-aware dispatch) |
| REQ-KZ-JV-402c | `integration_engine.py` `_run_semantic_checks()` | Implemented |
| REQ-KZ-JV-402d | `repair/config.py` `RepairConfig.semantic_repair_categories` | Not implemented (opt-in defaults) |
| REQ-KZ-JV-500 | — | Not implemented (hint library) |
| REQ-KZ-JV-600.1 | All properties | Implemented |
| REQ-KZ-JV-600.2 | `framework_imports` | Implemented |
| REQ-KZ-JV-600.3 | `generate_dependency_file()` | Implemented |
| REQ-KZ-JV-600.4 | `derive_service_metadata()` | Implemented |
| REQ-KZ-JV-600.5 | `build_project_context_section()` | Implemented |

### Requirements to Multi-Language Template Requirements

| Java Requirement | MULTI_LANGUAGE Requirement | Relationship |
|-----------------|---------------------------|-------------|
| REQ-KZ-JV-100.5 | REQ-MLT-102 (Python-Stub Cross-Language Guard) | Java-specific instance of the cross-language guard |
| REQ-KZ-JV-200.6 | REQ-MLT-102 | Extended contamination detection (Go, JS, Rust in addition to Python) |
| REQ-KZ-JV-600.1 (`syntax_check_command = None`) | REQ-MLT-100 (Non-Python Trivial File Detection) | Java files bypass per-file CLI validation |

---

## 9. Verification Strategy

### Unit Tests

| Test | Requirement | Description |
|------|------------|-------------|
| `test_java_syntax_valid` | REQ-KZ-JV-100.1 | Valid Java source passes `validate_syntax()` via both javalang and text-based fallback |
| `test_java_syntax_invalid_braces` | REQ-KZ-JV-100.1 | Unbalanced braces detected by text-based fallback |
| `test_java_python_fingerprint` | REQ-KZ-JV-100.5 | Python `from __future__` in `.java` file triggers contamination error |
| `test_java_package_directory_match` | REQ-KZ-JV-100.2 | Package declaration vs directory path validation |
| `test_java_class_filename_match` | REQ-KZ-JV-100.3 | Public class name vs filename validation |
| `test_java_wildcard_import_warning` | REQ-KZ-JV-100.4 | `import java.util.*` flagged as warning |
| `test_java_empty_catch_block` | REQ-KZ-JV-200.1 | Empty catch block detected as semantic issue |
| `test_java_raw_type_usage` | REQ-KZ-JV-200.3 | `List items = new ArrayList()` flagged |
| `test_java_quality_score_compilation_fail` | REQ-KZ-JV-300 | Compilation failure zeroes the compilation component (0.30 weight) |
| `test_java_quality_score_clean` | REQ-KZ-JV-300 | Clean Java file scores 1.0 |
| `test_java_boilerplate_ratio` | REQ-KZ-JV-302 | File with >40% boilerplate triggers `BOILERPLATE_INFLATION` |
| `test_build_gradle_generation` | REQ-KZ-JV-100.6 | `generate_dependency_file()` produces valid build.gradle with correct blocks |
| `test_java_cross_language_go_syntax` | REQ-KZ-JV-200.6 | Go `func` keyword in Java file triggers contamination |
| `test_java_hint_injection` | REQ-KZ-JV-500 | Kaizen hint for `RAW_TYPE_USAGE` appears in prompt context after root cause detection |

### Integration Tests

| Test | Requirements | Description |
|------|-------------|-------------|
| `test_java_disk_compliance_full` | REQ-KZ-JV-100 (all) | End-to-end disk compliance on a generated Java file with known defects |
| `test_java_quality_scoring_e2e` | REQ-KZ-JV-300, 301 | Quality score computation with multiple root causes, verify composite formula |
| `test_java_kaizen_feedback_loop` | REQ-KZ-JV-500 | Root cause detection triggers hint injection in subsequent run prompt |
| `test_java_service_metadata_derivation` | REQ-KZ-JV-600.4 | `derive_service_metadata()` with Spring Boot features produces correct metadata |

### Validation Approach

1. **Text-based checks first** — All semantic checks (Section 3) use regex/text heuristics, not Java AST. This keeps them lightweight and avoids a hard dependency on `javalang`.
2. **Golden file comparison** — Quality score tests use pre-constructed Java files with known defect counts and compare against expected scores.
3. **Cross-language contamination corpus** — A test corpus of Java files containing Python, Go, and JavaScript fragments validates the contamination detector.
4. **No Gradle in CI** — Unit and integration tests do not require a Java runtime or Gradle. The `syntax_check_command = None` design means all validation runs in-process via Python.
