# Java Prime Contractor — Requirements & Design

**Date:** 2026-03-17
**Status:** Draft
**Derived From:** Go Prime Contractor Requirements (REQ-GO-*), `JavaLanguageProfile` in `languages/java.py`, MULTI_LANGUAGE_TEMPLATE_AND_VALIDATION_REQUIREMENTS.md (REQ-MLT-100–401)
**Project:** TBD — first Java Prime Contractor run pending

---

## 1. Context

The Prime Contractor workflow generates code for multi-file features across a project. All prior ~50 runs targeted Python; run-066 was the first Go run. No Java runs have been attempted yet.

The `JavaLanguageProfile` exists in `languages/java.py` (~198 lines) with basic properties but no validation wiring, no Java-specific disk validators, and no post-generation cleanup tooling.

### Java Language Profile — Current State

**File:** `src/startd8/languages/java.py` (198 lines)

#### Implemented Capabilities

| Capability | Status | Implementation |
|-----------|--------|----------------|
| Language ID & display name | Done | `"java"` / `"Java"` |
| Source extensions | Done | `[".java"]` |
| Build file patterns | Done | `["build.gradle", "settings.gradle", "pom.xml", "build.gradle.kts"]` |
| Syntax check | Stub | `gradle compileJava` (requires Gradle wrapper + project context) |
| Lint | Disabled | No lightweight Java linter callable from CLI |
| Test | Stub | `gradle test` (requires project context) |
| Framework imports | Done | gRPC (`io.grpc`), Logging (`log4j`) |
| Stdlib prefixes | Done | 4 prefixes (`java.`, `javax.`, `jdk.`, `sun.`) |
| Post-generation cleanup | Disabled | No authoritative import fixer; `google-java-format` requires JRE |
| Syntax validation | Stub | Always returns `(True, "")` — no lightweight checker |
| `build.gradle` generation | Done | `generate_dependency_file()` with plugins, java version, dependencies, mainClass |
| Docker images | Done | Builder: `eclipse-temurin:21-jdk`, Runtime: `eclipse-temurin:21-jre-alpine` |
| Coding standards | Done | PascalCase classes, camelCase methods, explicit access modifiers, no wildcard imports |
| Merge strategy | Done | `"simple"` (whole-file replacement) |
| Repair | Disabled | Java compiler validates; Python AST repair is not applicable |
| Stub patterns | Done | 4 patterns (`throw new UnsupportedOperationException`, TODO comments, etc.) |
| Function start pattern | Done | Regex matching access modifiers + return type + method name |

#### Missing (vs Go Profile)

| Capability | Go Status | Java Gap |
|-----------|-----------|----------|
| Syntax validation (real) | `gofmt -e` | No lightweight CLI checker — `javac` requires classpath |
| Post-generation cleanup | `goimports -w` | No equivalent — `google-java-format` needs JRE + jar |
| Import fixing | `goimports` adds/removes | No CLI tool — IDE-only (IntelliJ, Eclipse) |
| Text-based parser | `go_parser.py` (363 lines) | Not implemented |
| Text-based splicer | `go_splicer.py` (100 lines) | Not implemented |

---

## 2. Target Project Characteristics

Java Prime Contractor runs are expected to target projects with these structures:

### 2.1 Gradle Multi-Module (Microservices)

```
project-root/
├── settings.gradle          (includes all subprojects)
├── build.gradle             (root: shared deps, plugins)
├── service-a/
│   ├── build.gradle         (service-specific deps)
│   └── src/main/java/com/example/servicea/
│       ├── Application.java
│       ├── controller/
│       └── service/
├── service-b/
│   ├── build.gradle
│   └── src/main/java/com/example/serviceb/
│       └── ...
└── shared-lib/
    ├── build.gradle
    └── src/main/java/com/example/shared/
        └── ...
```

### 2.2 Maven Multi-Module

```
project-root/
├── pom.xml                  (parent POM)
├── service-a/
│   ├── pom.xml              (child POM, inherits parent)
│   └── src/main/java/...
└── service-b/
    ├── pom.xml
    └── src/main/java/...
```

### 2.3 Spring Boot Application

```
project-root/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/app/
    │   │   ├── Application.java
    │   │   ├── config/
    │   │   ├── controller/
    │   │   ├── service/
    │   │   ├── repository/
    │   │   └── model/
    │   └── resources/
    │       ├── application.yml
    │       └── templates/     (Thymeleaf)
    └── test/
        └── java/com/example/app/
```

---

## 3. Requirements

### 3.1 Generation Path (REQ-JAVA-100 series)

#### REQ-JAVA-100: File-Whole Generation for All Java Files

All Java source files (`.java`) MUST use file-whole LLM generation, not element-by-element MicroPrime decomposition.

**Rationale:** MicroPrime is Python-AST-based. Java files bypass it via `EscalationReason.NON_PYTHON_BYPASS` (REQ-MLT-101, implemented 2026-03-17 for Go; same mechanism applies to Java).

**Status:** IMPLEMENTED (same `_is_non_python_file()` check as Go)

#### REQ-JAVA-101: Non-Source File Generation

Non-source files in Java projects (`build.gradle`, `settings.gradle`, `pom.xml`, `application.yml`, `.properties`, `Dockerfile`, `Thymeleaf .html`) MUST either:
1. Use file-whole LLM generation (for complex content), or
2. Use language-appropriate templates (for trivial content like `build.gradle` skeletons)

They MUST NOT receive Python skeleton stubs.

**Status:** IMPLEMENTED (REQ-MLT-100/101/102 — same cross-language mechanism as Go)

#### REQ-JAVA-102: Java System Prompt Injection

The spec and draft prompts MUST include Java-specific context when the resolved language is Java:
- `system_prompt_role`: "an expert Java engineer"
- `coding_standards`: PascalCase classes, camelCase methods, explicit access modifiers, no wildcard imports, try-with-resources
- Framework preamble based on detected frameworks (gRPC, Spring Boot, Log4j)

**Acceptance criteria:**
- `spec_builder.py` checks `language_profile.system_prompt_role` and injects it
- `drafter.py` includes `coding_standards` in the draft system prompt
- Framework imports from `framework_imports` are listed as available when relevant

**Status:** PARTIAL — Properties exist on `JavaLanguageProfile` but wiring into `spec_builder.py`/`drafter.py` is not confirmed for Java runs. Same gap as REQ-GO-102.

#### REQ-JAVA-103: build.gradle Template Generation

When a `build.gradle` file is classified as TRIVIAL, generate it from seed metadata using `JavaLanguageProfile.generate_dependency_file()`.

**Inputs extracted from seed:**
- `module_path`: Main class fully-qualified name (e.g., `com.example.servicea.Application`)
- `java_version`: From seed metadata or default `"21"`
- `dependencies`: From seed task `dependencies` field (Gradle coordinate format: `group:artifact:version`)

**Status:** NOT IMPLEMENTED — `generate_dependency_file()` exists but is not wired into the template-match path. Currently, `build.gradle` files escalate to file-whole generation (acceptable fallback).

#### REQ-JAVA-104: settings.gradle Generation for Multi-Module Projects

When generating a multi-module Gradle project, the pipeline MUST generate a root `settings.gradle` that includes all subprojects.

**Acceptance criteria:**
- Seed enrichment detects multi-module structure (multiple `build.gradle` files in subdirectories)
- `settings.gradle` content: `rootProject.name`, `include` directives for each subproject
- Generated before any subproject build files

**Status:** NOT IMPLEMENTED

#### REQ-JAVA-105: pom.xml Generation (Maven Projects)

When the target project uses Maven (detected via existing `pom.xml` or seed metadata), generate `pom.xml` files with:
- Parent POM with `<modules>` for multi-module projects
- Child POMs inheriting `<parent>` with correct `groupId`, `artifactId`, `version`
- Dependency declarations in `<dependencies>` block

**Status:** NOT IMPLEMENTED — `generate_dependency_file()` currently produces Gradle only. Maven support is P2.

#### REQ-JAVA-106: application.yml / application.properties Generation

Spring Boot projects require configuration files. When detected:
- Generate `application.yml` (preferred) or `application.properties`
- Include server port, database connection, and logging configuration from seed metadata
- Use Spring Boot property naming conventions (`spring.datasource.url`, `server.port`)

**Status:** NOT IMPLEMENTED

#### REQ-JAVA-107: Thymeleaf Template Generation for Spring Boot Projects

HTML template files in Spring Boot frontend services MUST use Thymeleaf syntax when the project uses Spring Boot with Thymeleaf dependency.

**Acceptance criteria:**
- Seed enrichment detects Spring Boot + Thymeleaf (dependency on `spring-boot-starter-thymeleaf`)
- HTML spec prompt includes Thymeleaf syntax guidance (`th:text`, `th:each`, `th:if`)
- Generated HTML uses `th:*` attributes (not Go template `{{.Field}}` or Jinja `{{ field }}`)

**Status:** NOT IMPLEMENTED

---

### 3.2 Validation & Scoring (REQ-JAVA-200 series)

#### REQ-JAVA-200: Java File Validation

Generated `.java` files SHOULD be validated for basic structural correctness when no Java compiler is available.

**Text-based validation checks:**
1. Contains `class` or `interface` or `enum` or `record` declaration
2. Contains `package` statement matching expected directory structure
3. Balanced braces (`{` vs `}`)
4. No Python content (cross-language guard via REQ-GO-203)

**If `javac` is available** (detected on PATH with valid classpath), use compiler validation as the primary check.

**Acceptance criteria:**
- `validate_syntax()` on `JavaLanguageProfile` performs text-based checks (current stub replaced)
- Syntax errors logged as warnings (non-blocking)
- If `javac` is on PATH and classpath is resolvable, prefer compiler validation

**Status:** NOT IMPLEMENTED — current `validate_syntax()` is a stub returning `(True, "")`.

#### REQ-JAVA-201: build.gradle Disk Validation

`validate_disk_compliance()` MUST validate `build.gradle` files for:
- Contains `plugins` or `apply plugin` block (required)
- Contains `dependencies` block or no dependencies needed
- No Python content (cross-language guard)
- Valid Gradle syntax markers (no bare Python `import`, `def`, `class` statements)

**Scoring:**

| Condition | `ast_valid` | `contract_compliance` |
|-----------|-------------|----------------------|
| Missing `plugins`/`apply plugin` | False | 0.0 |
| Python content detected | False | 0.0 |
| Missing `dependencies` when deps expected | True | 0.5 |
| Valid | True | 1.0 |

**Status:** NOT IMPLEMENTED

#### REQ-JAVA-202: pom.xml Disk Validation

`validate_disk_compliance()` MUST validate `pom.xml` files for:
- Well-formed XML (parseable)
- Contains `<project>` root element
- Contains `<groupId>`, `<artifactId>`, `<version>` (GAV coordinates)
- No Python content (cross-language guard)

**Scoring:**

| Condition | `ast_valid` | `contract_compliance` |
|-----------|-------------|----------------------|
| Not valid XML | False | 0.0 |
| Missing `<project>` root | False | 0.0 |
| Missing GAV coordinates | True | 0.5 |
| Python content | False | 0.0 |
| Valid | True | 1.0 |

**Status:** NOT IMPLEMENTED

#### REQ-JAVA-203: application.yml Disk Validation

`validate_disk_compliance()` MUST validate `application.yml` for:
- Valid YAML syntax (parseable)
- Contains at least one Spring Boot property key (`spring.*`, `server.*`, `logging.*`)
- No Python content

**Status:** NOT IMPLEMENTED — generic `_validate_yaml_file()` exists but has no Spring Boot awareness.

#### REQ-JAVA-204: Cross-Language Content Detection (Java)

The existing `_detect_language_mismatch()` (REQ-GO-203) MUST also detect Java content in non-Java files.

**Detects:**
- Java fingerprints (`public class`, `import java.`, `package com.`) in non-Java files

**Status:** PARTIAL — `_detect_language_mismatch()` exists for Python detection. Java fingerprints not yet added.

#### REQ-JAVA-205: Python-Stub Integration Guard (Java)

Same as REQ-GO-204 — the integration engine MUST block Python stubs from being written to Java target files.

**Status:** IMPLEMENTED (same `_detect_python_stub_in_non_python()` mechanism — extension-based, covers `.java`)

---

### 3.3 Post-Generation Cleanup (REQ-JAVA-300 series)

#### REQ-JAVA-300: google-java-format Execution (Best-Effort)

After generating `.java` files, the pipeline SHOULD run `google-java-format` to normalize formatting if available.

**Prerequisites:**
- `google-java-format` jar on PATH (or configured location)
- Java runtime available

**Fallback:** Skip with warning if not available. Java generated code is still valid without formatting.

**Status:** NOT IMPLEMENTED — `post_generation_cleanup()` returns empty list.

#### REQ-JAVA-301: Import Organization (Best-Effort)

Unlike Go (`goimports`), Java has no standard CLI import organizer. The pipeline SHOULD:
1. Include explicit imports in the generation prompt (no wildcard imports)
2. Rely on LLM to produce correct imports
3. Flag likely missing imports via text-based analysis (optional, P3)

**Status:** NOT IMPLEMENTED — coding standards include "no wildcard imports" guidance; import correctness depends on LLM prompt quality.

#### REQ-JAVA-302: Package Statement Validation

After generation, validate that each `.java` file's `package` statement matches its directory path relative to `src/main/java/`.

**Example:** `src/main/java/com/example/service/MyService.java` MUST contain `package com.example.service;`

**Status:** NOT IMPLEMENTED

---

### 3.4 Multi-Module Project Handling (REQ-JAVA-400 series)

#### REQ-JAVA-400: Gradle Multi-Module Recognition

The pipeline MUST recognize that Java multi-module projects have:
- A root `settings.gradle` with `include` directives
- Per-module `build.gradle` files
- Shared dependency management in root `build.gradle`

**Acceptance criteria:**
- Seed enrichment detects multi-module structure from `settings.gradle` or multiple `build.gradle` files
- Each module's `build.gradle` specifies its own dependencies
- Cross-module dependencies use Gradle project references (`implementation project(':shared-lib')`)

**Status:** NOT IMPLEMENTED

#### REQ-JAVA-401: Maven Multi-Module Recognition

Same as REQ-JAVA-400 but for Maven:
- Root `pom.xml` with `<modules>` section
- Child `pom.xml` files with `<parent>` reference
- Shared dependency management via `<dependencyManagement>` in parent

**Status:** NOT IMPLEMENTED

#### REQ-JAVA-402: Standard Directory Layout Enforcement

Java projects follow a canonical directory layout. Generated files MUST be placed in the correct locations:

| File Type | Expected Location |
|-----------|-------------------|
| Java source | `src/main/java/{package/path}/` |
| Java tests | `src/test/java/{package/path}/` |
| Resources | `src/main/resources/` |
| Test resources | `src/test/resources/` |
| Thymeleaf templates | `src/main/resources/templates/` |
| Static assets | `src/main/resources/static/` |

**Status:** NOT IMPLEMENTED — depends on seed enrichment and path resolution.

#### REQ-JAVA-403: Shared Library Dependencies

When multiple modules depend on a shared library module, the pipeline MUST:
1. Order generation so shared libraries are generated before consumers
2. Include the shared library's public API in consumer module specs
3. Use correct Gradle/Maven cross-module dependency syntax

**Status:** PARTIAL — `FeatureQueue` dependency ordering exists (same as REQ-GO-402). Cross-module dependency syntax in specs is not yet wired.

---

### 3.5 Framework-Specific Requirements (REQ-JAVA-500 series)

#### REQ-JAVA-500: Spring Boot Project Detection

The pipeline MUST detect Spring Boot projects and inject framework-specific context:
- `@SpringBootApplication` main class pattern
- `@RestController` / `@Service` / `@Repository` annotation patterns
- Spring dependency injection (`@Autowired`, constructor injection)
- Spring Boot starter dependencies

**Acceptance criteria:**
- `framework_imports` on `JavaLanguageProfile` includes Spring Boot detection
- Spec prompts include Spring Boot patterns when detected
- Generated code follows Spring Boot conventions

**Status:** NOT IMPLEMENTED — `framework_imports` currently only has gRPC and Log4j. Spring Boot is the most common Java framework and MUST be added.

#### REQ-JAVA-501: gRPC Service Generation

Java gRPC services reference generated protobuf stubs. The pipeline MUST:
1. Not flag generated protobuf imports as phantom dependencies
2. Include proto package paths in the seed's `dependencies` field
3. Generate correct `import` statements for generated stub classes

**Status:** PARTIAL — `framework_imports` has gRPC detection. Protobuf import handling same gap as REQ-GO-401.

#### REQ-JAVA-502: Logging Framework Detection

Detect and generate code using the project's logging framework:
- SLF4J + Logback (Spring Boot default)
- Log4j2
- java.util.logging (JUL)

**Acceptance criteria:**
- `framework_imports` detects logging framework from dependencies
- Generated code uses the correct logging API
- Logger field pattern matches framework (`private static final Logger logger = LoggerFactory.getLogger(X.class)`)

**Status:** PARTIAL — Log4j detection exists. SLF4J (most common) not yet in `framework_imports`.

---

### 3.6 Postmortem & Kaizen (REQ-JAVA-600 series)

#### REQ-JAVA-600: Non-Python Postmortem Accuracy (Java)

The postmortem MUST NOT score Java files as 1.0 by default. Each file type must have at least a basic validator.

**File types requiring validators:**

| Type | Validator | Status |
|------|-----------|--------|
| `.java` | Text-based structural check | NOT IMPLEMENTED |
| `build.gradle` | `_validate_build_gradle()` | NOT IMPLEMENTED |
| `pom.xml` | `_validate_pom_xml()` | NOT IMPLEMENTED |
| `application.yml` | `_validate_yaml_file()` (Spring-aware) | PARTIAL (generic YAML only) |
| `Dockerfile` | `_validate_dockerfile()` | Pre-existing |
| `.properties` | Basic key=value check | NOT IMPLEMENTED |

#### REQ-JAVA-601: Language Mismatch Postmortem Pattern (Java)

Same as REQ-GO-501 — when 2+ files in a run have `language_mismatch` errors, emit a cross-feature pattern.

**Status:** NOT IMPLEMENTED (REQ-MLT-401 — shared with Go)

---

## 4. Implementation Priority

### P0 — Required Before First Java Run

| REQ | Description | Effort | Depends On |
|-----|-------------|--------|------------|
| REQ-JAVA-100 | File-whole generation bypass | Done | REQ-MLT-101 |
| REQ-JAVA-101 | Non-source file protection | Done | REQ-MLT-100/101/102 |
| REQ-JAVA-205 | Python-stub guard | Done | REQ-GO-204 |
| REQ-JAVA-200 | Java file text-based validation | S | — |
| REQ-JAVA-201 | build.gradle disk validation | S | — |
| REQ-JAVA-500 | Spring Boot framework detection | M | JavaLanguageProfile |

### P1 — First Run Quality

| REQ | Description | Effort | Depends On |
|-----|-------------|--------|------------|
| REQ-JAVA-102 | Java system prompt injection | S | Confirm spec/draft builder wiring |
| REQ-JAVA-302 | Package statement validation | S | — |
| REQ-JAVA-402 | Standard directory layout | M | Seed enrichment |
| REQ-JAVA-502 | SLF4J logging detection | S | JavaLanguageProfile |
| REQ-JAVA-600 | Postmortem accuracy | M | REQ-JAVA-200/201 |

### P2 — Multi-Module & Build System

| REQ | Description | Effort | Depends On |
|-----|-------------|--------|------------|
| REQ-JAVA-103 | build.gradle template | S | — |
| REQ-JAVA-104 | settings.gradle generation | S | REQ-JAVA-400 |
| REQ-JAVA-105 | pom.xml generation (Maven) | M | — |
| REQ-JAVA-202 | pom.xml disk validation | S | — |
| REQ-JAVA-400 | Gradle multi-module | M | — |
| REQ-JAVA-401 | Maven multi-module | M | — |
| REQ-JAVA-403 | Shared lib dependencies | S | REQ-JAVA-400/401 |
| REQ-JAVA-204 | Java fingerprint detection | S | REQ-GO-203 |

### P3 — Nice to Have

| REQ | Description | Effort | Depends On |
|-----|-------------|--------|------------|
| REQ-JAVA-106 | application.yml generation | S | — |
| REQ-JAVA-107 | Thymeleaf template generation | S | REQ-JAVA-500 |
| REQ-JAVA-203 | application.yml validation | S | — |
| REQ-JAVA-300 | google-java-format | S | JRE on PATH |
| REQ-JAVA-301 | Import organization | M | — |
| REQ-JAVA-501 | gRPC stub awareness | S | REQ-GO-401 |
| REQ-JAVA-601 | Language mismatch postmortem | S | REQ-MLT-401 |

---

## 5. Test Coverage (Current)

| Test File | Tests | Covers |
|-----------|-------|--------|
| `tests/unit/languages/test_protocol.py` | ~5 (Java subset) | Protocol conformance |
| `tests/unit/languages/test_registry.py` | ~3 (Java subset) | Entry point discovery |
| `tests/unit/languages/test_resolution.py` | ~2 (Java subset) | Language resolution |
| `tests/unit/micro_prime/test_non_python_bypass.py` | Shared | REQ-JAVA-100 (same mechanism as Go) |
| **Total (Java-specific)** | **~10** | |

### Test Coverage Needed

| Test File (Proposed) | Tests (Est.) | Covers |
|----------------------|--------------|--------|
| `tests/unit/validators/test_java_validators.py` | ~20 | REQ-JAVA-200, 201, 202, 302 |
| `tests/unit/languages/test_java_capabilities.py` | ~15 | JavaLanguageProfile properties, generate_dependency_file, framework detection |
| `tests/unit/contractors/test_integration_engine_java.py` | ~8 | REQ-JAVA-205 (Java-specific cross-language) |
| **Total needed** | **~43** | |

---

## 6. Known Limitations

1. **No lightweight Java syntax checker** — Unlike Go's `gofmt -e`, Java has no standalone syntax-only checker. `javac` requires classpath resolution. Text-based validation is the primary path.

2. **No CLI import organizer** — Go has `goimports`; Java has no equivalent. Import correctness depends entirely on LLM prompt quality and the `coding_standards` guidance.

3. **Dual build system** — Java projects use either Gradle or Maven (sometimes both via wrapper). The pipeline must detect and support both, unlike Go (only `go.mod`).

4. **Deep directory structure** — Java's `com.example.package` convention creates deep directory trees (`src/main/java/com/example/package/`). Path resolution and `package` statement validation are more complex than Go's flat layout.

5. **MicroPrime bypass** — Same as Go: Java files skip element-by-element generation entirely. File-whole generation quality depends on LLM prompt.

6. **Spring Boot complexity** — Spring Boot is the dominant Java framework, using annotation-driven configuration, dependency injection, and auto-configuration. The pipeline must understand Spring conventions to generate idiomatic code — a much broader surface area than Go's stdlib-centric approach.

7. **Protobuf generation** — Same limitation as Go (REQ-GO-401): the pipeline generates Java source that imports gRPC stubs but does not run `protoc` to generate them.

---

## 7. Differences from Go Requirements

| Aspect | Go (REQ-GO-*) | Java (REQ-JAVA-*) |
|--------|---------------|---------------------|
| Build system | `go.mod` only | Gradle OR Maven (dual support needed) |
| Syntax validation | `gofmt -e` (lightweight, reliable) | No lightweight checker; text-based fallback |
| Import fixing | `goimports` (excellent) | None available from CLI |
| Post-gen cleanup | `goimports -w` / `gofmt -w` | `google-java-format` (optional, needs JRE) |
| Directory layout | Flat (package per directory) | Deep (`src/main/java/com/...`) |
| Template syntax | Go `html/template` (`{{.Field}}`) | Thymeleaf (`th:text="${field}"`) |
| Framework surface | Minimal (stdlib-centric) | Large (Spring Boot ecosystem) |
| Multi-module | Per-service `go.mod` | `settings.gradle` / parent `pom.xml` |
| Config files | None standard | `application.yml` / `.properties` |
| Text parser | `go_parser.py` (exists) | Not implemented |
| Text splicer | `go_splicer.py` (exists) | Not implemented |
