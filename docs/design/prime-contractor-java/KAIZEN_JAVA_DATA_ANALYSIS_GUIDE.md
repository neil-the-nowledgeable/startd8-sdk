# Kaizen Data Analysis Guide — Java

> **Parent guide:** [KAIZEN_DATA_ANALYSIS_GUIDE.md](../prime/KAIZEN_DATA_ANALYSIS_GUIDE.md)
> **Requirements:** [KAIZEN_JAVA_REQUIREMENTS.md](./KAIZEN_JAVA_REQUIREMENTS.md)
> **Language profile:** `JavaLanguageProfile` (`src/startd8/languages/java.py`)

This guide covers Java-specific analysis workflows for Kaizen telemetry. For the general pipeline (enabling capture, directory structure, prompt/response pairs, cross-feature comparison, Ichigo Ichie compliance), see the parent guide. This document focuses on what's different when the target language is Java.

---

## 1. Java Generation Strategy

Java tasks route through the pipeline differently than Python:

| Property | Java | Python (for comparison) |
|----------|------|------------------------|
| **Generation path** | Element-level via MicroPrime (when `JAVA_MICROPRIME_ENABLED = True`) or file-whole fallback | Element-level via MicroPrime (always) |
| **Merge strategy** | `simple` (full file replacement) | `ast` (additive AST merge) |
| **Repair pipeline** | `fence_strip` only (no Java-specific repair steps) | 17 repair steps (Ruff, AST rewrite, import fix) |
| **Post-generation cleanup** | None (`post_generation_cleanup()` returns `[]`) | Ruff auto-fix |
| **Syntax validation** | `javalang.parse.parse()` with text-based fallback | `ast.parse()` |
| **Stub markers** | `throw new UnsupportedOperationException()`, `throw new RuntimeException("not implemented"/"TODO")`, `// TODO` | `raise NotImplementedError` |

### What this means for analysis

- **No AST merge corruption.** Java uses `simple` merge — the entire generated file replaces the target. You will never see the Python-specific failure modes (duplicate `__main__` guards, stale definitions preserved from the old file). If the draft is correct, the file on disk should match.
- **No auto-repair safety net.** Issues that Python auto-fixes (unused imports, formatting, lint violations) are hard failures in Java. When investigating a Java failure, the draft output *is* the final output — there's no repair layer that silently transformed it.
- **Compilation requires project context.** Unlike Python (`ast.parse()` works on any single file), Java compilation needs resolved dependencies. The `validate_syntax()` in the profile uses `javalang` (in-process) or text heuristics — it cannot catch import resolution errors or type mismatches. A file can pass `validate_syntax()` but fail `javac`.

---

## 2. Finding Java Telemetry

Java features appear in the same Kaizen directory structure as any other language:

```
kaizen-prompts/standalone/<FEATURE_ID>/
├── metadata.json              # includes language: "java"
├── spec_user_prompt.md
├── spec_system_prompt.md
├── spec_response.md
├── draft_user_prompt.md
├── draft_system_prompt.md      # contains Java project context section
├── draft_response.md           # raw LLM output (should be valid Java)
├── review_user_prompt.md
├── review_system_prompt.md
└── review_response.md
```

### Identifying Java features

In `metadata.json`, look for:
- `"language"`: `"java"` — the resolved language from `resolve_language()`
- `"target_files"`: paths ending in `.java`
- `"service_metadata"` containing `java_package`, `build_system`, `java_version`, `spring_boot`

In `kaizen-metrics.json`, Java features can be filtered by their target file extensions.

---

## 3. Draft vs Disk: Java-Specific Checks

### Step 1: Compare draft to disk

```bash
# Compare the LLM's raw output to the file written to disk
diff <(cat kaizen-prompts/standalone/PI-XXX/draft_response.md) \
     <(cat src/main/java/com/example/service/OrderService.java)
```

With `simple` merge, these should be identical (minus markdown fence stripping). If they differ, the only transformation is `fence_strip` — check if the draft was wrapped in ` ```java ... ``` ` fences.

### Step 2: Validate syntax

```bash
# Option A: javalang (in-process, no deps needed)
python3 -c "
import javalang
with open('src/main/java/com/example/service/OrderService.java') as f:
    javalang.parse.parse(f.read())
print('OK')
"

# Option B: javac (requires JDK, catches more issues)
javac -Xlint:all src/main/java/com/example/service/OrderService.java

# Option C: text-based heuristic (no external deps)
python3 -c "
from startd8.languages.java import _validate_java_syntax
with open('src/main/java/com/example/service/OrderService.java') as f:
    ok, msg = _validate_java_syntax(f.read())
print('OK' if ok else f'FAIL: {msg}')
"
```

### Step 3: Check for unfilled stubs

```bash
# Java stub patterns (from JavaLanguageProfile.stub_patterns)
grep -n 'throw new UnsupportedOperationException' src/main/java/**/*.java
grep -n 'throw new RuntimeException.*not implemented' src/main/java/**/*.java
grep -n 'throw new RuntimeException.*TODO' src/main/java/**/*.java
grep -n '^\s*// TODO' src/main/java/**/*.java
```

### Step 4: Cross-language contamination check

```bash
# Python fingerprints in Java files (the #1 cross-language failure)
grep -n 'def ' src/main/java/**/*.java
grep -n 'import os' src/main/java/**/*.java
grep -n 'from __future__' src/main/java/**/*.java
grep -n 'self\.' src/main/java/**/*.java
grep -n '^#!' src/main/java/**/*.java

# Go/JavaScript contamination (less common)
grep -n 'func ' src/main/java/**/*.java
grep -n ':=' src/main/java/**/*.java
grep -n 'const ' src/main/java/**/*.java
grep -n '=>' src/main/java/**/*.java
```

### Step 5: Java structural checks

```bash
# Package declaration matches directory path
# File: src/main/java/com/example/service/OrderService.java
# Should contain: package com.example.service;
head -5 src/main/java/com/example/service/OrderService.java | grep 'package'

# Public class name matches filename
# File: OrderService.java → should contain: public class OrderService
grep 'public class' src/main/java/com/example/service/OrderService.java

# Wildcard imports (quality warning)
grep 'import .*\*;' src/main/java/**/*.java

# Missing access modifiers (common LLM omission)
grep -n '^\s*class \|^\s*void \|^\s*String \|^\s*int \|^\s*boolean ' src/main/java/**/*.java
```

---

## 4. Java Quality Score Formula

The Java disk quality score (REQ-KZ-JV-300) uses six weighted components:

```
java_quality_score = (compilation_check     × 0.30)
                   + (import_validity       × 0.15)
                   + (stub_penalty          × 0.20)
                   + (type_safety           × 0.15)
                   + (contamination_check   × 0.10)
                   + (convention_compliance × 0.10)
```

> [!NOTE]
> **Current implementation status:** The Java-specific scoring formula is defined in requirements but **not yet implemented** in `prime_postmortem.py`. Non-Python files currently receive partial scoring (contract_compliance + import_completeness only). The `disk_quality_score` field in the exemplar registry will be `null` for Java features. Manual analysis using the component breakdown below is needed until the scorer is wired.

### Component reference

| Component | What it measures | How to check manually |
|-----------|-----------------|----------------------|
| `compilation_check` (0.30) | Does `validate_syntax()` pass? | Run javalang or text-based validation (Step 2 above) |
| `import_validity` (0.15) | Ratio of valid imports. Wildcard imports are 0.5 penalty each. | `grep 'import ' file.java \| wc -l` vs invalid count |
| `stub_penalty` (0.20) | Ratio of unfilled stubs to total methods | Count stub patterns (Step 3) vs total method count |
| `type_safety` (0.15) | Raw type usage deducts 0.1 per instance | `grep 'List \|Map \|Set \|Collection ' file.java` (without `<`) |
| `contamination_check` (0.10) | Binary: any Python/Go/JS fingerprint = 0.0 | Step 4 above |
| `convention_compliance` (0.10) | Average of: class-filename match, access modifiers present, @Override present | Steps 5 checks above |

---

## 5. Java Root Causes

When `kaizen-metrics.json` reports failures for Java features, the root causes fall into these categories:

### Critical (file is non-functional)

| Root Cause | Symptom | Investigation |
|-----------|---------|---------------|
| `CROSS_LANGUAGE_CONTAMINATION` | Python/Go/JS syntax in `.java` file | `draft_response.md` — did the LLM default to Python? Check `draft_system_prompt.md` for Java context section. |
| `COMPILATION_ERROR` | Unbalanced braces, missing type declaration, javalang parse error | `draft_response.md` — was the output truncated? Check `draft_response.meta.json` for truncation. |

### High (file compiles but has structural errors)

| Root Cause | Symptom | Investigation |
|-----------|---------|---------------|
| `MISSING_PACKAGE_DECLARATION` | No `package` statement | `draft_user_prompt.md` — was the package context injected? Check `build_project_context_section()` output in system prompt. |
| `CLASS_FILENAME_MISMATCH` | Public class doesn't match filename | `metadata.json` → `target_files` vs `draft_response.md` class name. Did the LLM use a different class name? |
| `MISSING_DEPENDENCY` | Import references a class not in `build.gradle` | Check if `generate_dependency_file()` was called and if the dependency was in the feature's `runtime_dependencies`. |

### Medium (quality issues)

| Root Cause | Symptom | Investigation |
|-----------|---------|---------------|
| `EMPTY_CATCH_BLOCK` | `catch (Exception e) { }` | `draft_response.md` — search for `catch` blocks. Common with LLM-generated boilerplate. |
| `RAW_TYPE_USAGE` | `List items` instead of `List<String> items` | `draft_response.md` — search for unparameterized generics. Often caused by the LLM mimicking Java 1.4 style. |
| `BUILD_GRADLE_ERROR` | Missing blocks, invalid syntax in `build.gradle` | Check `generate_dependency_file()` output. Was the service metadata correctly derived? |

### Low (style/convention issues)

| Root Cause | Symptom | Investigation |
|-----------|---------|---------------|
| `WILDCARD_IMPORT` | `import java.util.*` | Kaizen hint JV-H-04 targets this. Check if the hint was injected. |
| `MISSING_ACCESS_MODIFIER` | Package-private by default | Common LLM omission. Kaizen hint JV-H-05 targets this. |
| `MISSING_OVERRIDE_ANNOTATION` | `toString()` without `@Override` | Text heuristic only — checks known override-candidate method names. |
| `BOILERPLATE_INFLATION` | `boilerplate_ratio > 0.4` | Count getter/setter pairs, empty constructors, trivial delegation. |

---

## 6. Java-Specific Failure Patterns

### Pattern: Boilerplate Inflation

Java LLM output is typically 2-3x more verbose than equivalent Python output. This inflates token cost and increases the surface area for stubs and errors.

**Indicators:**
- `boilerplate_ratio > 0.4` (getters/setters, empty constructors, trivial Javadoc)
- Feature cost significantly higher than equivalent Python features
- Many methods with only a getter/setter body

**Debugging workflow:**
1. Open `draft_response.md` and count functional vs boilerplate lines
2. Check if the LLM could have used `record` types (Java 16+) instead of full classes
3. Check the `java_version` in `metadata.json` → `service_metadata` — if set to `21`, records are available
4. Review `draft_system_prompt.md` for Kaizen hint JV-H-06 (concise idioms hint)

### Pattern: Missing Package Declaration

The LLM omits the `package` statement, producing a file that compiles only in the default package.

**Debugging workflow:**
1. Check `draft_system_prompt.md` for the "Java Project Context" section
2. Verify `build_project_context_section()` was called with the correct `target_files`
3. If the package context is present in the prompt but missing in the output, this is an LLM compliance failure — Kaizen hint JV-H-07 targets this

### Pattern: Cross-Language Contamination (Python in Java)

The LLM generates Python syntax inside a `.java` file. This is the single most common cross-language failure.

**Debugging workflow:**
1. Open `draft_response.md` and search for Python fingerprints (`def `, `self.`, `import os`)
2. Check `draft_system_prompt.md` — is the language clearly identified as Java?
3. Check `metadata.json` → `language` — was the language correctly resolved?
4. If contamination is partial (Java structure with Python snippets), the LLM mixed languages mid-generation. This is more common with smaller models (Ollama/Haiku tier).
5. Kaizen hint JV-H-10 targets this. Check if it was injected for prior runs with the same issue.

### Pattern: Interface + Implementation Confusion

The LLM generates an implementation class inside an interface file, or puts the interface inside the implementation file.

**Debugging workflow:**
1. Check `coding_standards` in the system prompt — it says "Interface files MUST contain ONLY the interface definition"
2. If the feature's `target_files` includes both `FooService.java` and `FooServiceImpl.java`, check whether both files were generated
3. If only one file exists and it contains both interface and implementation, this is a structural failure

### Pattern: JUnit Version Mismatch

The LLM generates JUnit 4 tests (`@Before`, `Assert.assertEquals`) instead of JUnit 5 (`@BeforeEach`, `Assertions.assertEquals`).

**Debugging workflow:**
1. Check test files for `org.junit.Test` (JUnit 4) vs `org.junit.jupiter.api.Test` (JUnit 5)
2. Check `build.gradle` dependencies — does it declare `testImplementation 'org.junit.jupiter:junit-jupiter'`?
3. Kaizen hint JV-H-30 targets this

---

## 7. Java Feedback Loop (Kaizen Hints)

Kaizen hints are injected into the LLM prompt to address recurring root causes. The Java hint library has three categories:

### Standard hints (JV-H-01 through JV-H-10)

These target root causes from Section 5. They are injected when the corresponding root cause is detected in a prior run.

| Hint | Targets | Injected when |
|------|---------|---------------|
| JV-H-01 | `RAW_TYPE_USAGE` | Prior run detected unparameterized generics |
| JV-H-02 | `EMPTY_CATCH_BLOCK` | Prior run detected swallowed exceptions |
| JV-H-03 | `MISSING_OVERRIDE_ANNOTATION` | Prior run detected missing @Override |
| JV-H-04 | `WILDCARD_IMPORT` | Prior run detected `import *.` |
| JV-H-05 | `MISSING_ACCESS_MODIFIER` | Prior run detected package-private defaults |
| JV-H-06 | `BOILERPLATE_INFLATION` | Prior run detected boilerplate_ratio > 0.4 |
| JV-H-07 | `MISSING_PACKAGE_DECLARATION` | Prior run detected missing package statement |
| JV-H-08 | `CLASS_FILENAME_MISMATCH` | Prior run detected name/file mismatch |
| JV-H-09 | `MISSING_DEPENDENCY` | Prior run detected unresolved import |
| JV-H-10 | `CROSS_LANGUAGE_CONTAMINATION` | Prior run detected Python/Go/JS syntax |

### Build tool hints (JV-H-20, JV-H-21)

Injected when `build.gradle` generation is required. Target Gradle dependency notation and plugin configuration.

### Testing pattern hints (JV-H-30, JV-H-31)

Injected when test files are in the feature's `target_files`. Target JUnit 5 and Mockito conventions.

### Verifying hint injection

To verify a hint was injected:

```bash
# Check if the hint text appears in the system or user prompt
grep -l "parameterize generic types" kaizen-prompts/standalone/PI-XXX/draft_system_prompt.md
grep -l "UnsupportedOperationException" kaizen-prompts/standalone/PI-XXX/spec_user_prompt.md
```

To add a custom hint for the next run:

```json
// kaizen-config.json
{
  "hints": {
    "PI-XXX": {
      "custom": ["Always use SLF4J for logging, never System.out.println()"]
    }
  }
}
```

---

## 8. Repair Gap: What Java Cannot Auto-Fix

Unlike Python (17 repair steps), Java has no language-specific repair pipeline. The only repair that applies is `fence_strip` (removing markdown code fences from LLM output), which is language-agnostic.

### Impact on analysis

When a Java feature fails, the root cause is almost always in the LLM output itself — there's no intermediate repair layer that could have masked or introduced the issue. This simplifies debugging: `draft_response.md` is effectively the final output.

### What repair could fix (if implemented)

| Potential repair | Tool | What it would catch | Priority |
|-----------------|------|---------------------|----------|
| Code formatting | `google-java-format` | Indentation, spacing, brace style | P1 |
| Import sorting/removal | `google-java-format --fix-imports-only` | Unused imports, import ordering | P1 |
| Full lint + format | Spotless Gradle plugin (`spotlessApply`) | Combines formatting + imports | P2 |

Until these repair steps are implemented, the feedback loop (Kaizen hints) is the primary mechanism for reducing Java code quality issues. The system steers the LLM to produce correct code upfront rather than fixing it after generation.

---

## 9. Typical Java Debugging Workflow

1. **Identify the failure.** Open `kaizen-metrics.json` and filter for features with Java target files.
2. **Check root cause.** Is it `CROSS_LANGUAGE_CONTAMINATION`? `COMPILATION_ERROR`? `MISSING_PACKAGE_DECLARATION`?
3. **Read the draft.** Open `kaizen-prompts/standalone/<FEATURE_ID>/draft_response.md`. Since Java uses `simple` merge and has no repair pipeline, this is essentially what ended up on disk.
4. **Check the prompt.** Open `draft_system_prompt.md` and verify:
   - The "Java Project Context" section is present with correct package/class/version
   - The `coding_standards` were injected
   - Any Kaizen hints from prior runs were included
5. **Validate the file.** Run `javalang` or text-based validation (Section 3, Step 2).
6. **Check structural compliance.** Package declaration matches directory, public class matches filename, no wildcard imports.
7. **Check for contamination.** Search for Python/Go/JS syntax (Section 3, Step 4).
8. **Compute manual quality score.** Use the six-component formula (Section 4) until automated scoring is implemented.
9. **Classify and act.** Apply the Ichigo Ichie gate:
   - **[GENERAL]**: LLM always generates raw types → add JV-H-01 hint globally
   - **[CALIBRATION]**: This specific project's Spring Boot config confuses the LLM → project-specific seed adjustment only
   - **[GENERALIZABLE]**: The LLM omits package declarations when the target path is deeply nested → improve `build_project_context_section()` to emphasize package path more strongly
10. **Inject hints and rerun.** Add targeted hints to `kaizen-config.json` and rerun with `--kaizen-config`.

---

## 10. Java vs Python: Key Differences for Analysts

| Dimension | Python | Java |
|-----------|--------|------|
| **Merge strategy** | AST merge (additive, can corrupt) | Simple replace (draft ≈ disk) |
| **Repair pipeline** | 17 steps (masks many issues) | None (draft = final) |
| **Syntax validation** | `ast.parse()` (reliable, in-process) | `javalang` (optional dep) or text heuristic |
| **Quality scoring** | Full (4 components + semantic) | Partial (defined but not yet implemented) |
| **Stub markers** | `raise NotImplementedError` | `throw new UnsupportedOperationException()`, `throw new RuntimeException("TODO"/"not implemented")`, `// TODO` |
| **Common LLM failures** | Phantom imports, duplicate defs | Boilerplate inflation, cross-language contamination, missing package declaration |
| **Post-gen cleanup** | Ruff auto-fix | None |
| **Compilation validation** | Single-file (`ast.parse`) | Requires project context (build.gradle + deps) for full `javac` |
| **Import fixing** | `isort` + `autoflake` available | No CLI-callable import fixer without full IDE project |
| **Debugging focus** | Check repair layer transformations | Check LLM output directly (no transformations) |

The core insight: **Java debugging is simpler** (fewer moving parts between draft and disk) but **Java prevention is harder** (no auto-repair means the LLM must get it right the first time). This makes the Kaizen feedback loop (hints) more important for Java than for Python.
