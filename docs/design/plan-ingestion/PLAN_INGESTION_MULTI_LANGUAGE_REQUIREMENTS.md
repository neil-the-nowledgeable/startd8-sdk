# Plan Ingestion — Multi-Language Support Requirements

**Date:** 2026-03-17
**Status:** Active
**Derived From:** MULTI_LANGUAGE_CAPABILITY_MAP.md (C-1 through C-12), Go Prime Contractor Requirements (REQ-GO-*), Java Prime Contractor Requirements (REQ-JMP-*), OpenSpec-Inspired Improvements (REQ-OI-001–005)
**Scope:** Plan ingestion workflow (`plan_ingestion_workflow.py`, `plan_ingestion_emitter.py`), seed derivation (`seeds/derivation.py`), and language detection (`lang_detect.py`)

---

## 1. Context

### 1.1 What Plan Ingestion Does

The plan ingestion workflow transforms a human-written plan document into structured seed tasks that the Prime Contractor can execute. It runs a 5-phase pipeline:

1. **PARSE** — LLM extracts features from the plan (name, description, target files, dependencies, API signatures)
2. **ASSESS** — Classify features by complexity and risk
3. **TRANSFORM** — Normalize features into `SeedTask` format with dependency ordering
4. **REFINE** — Multi-round iterative refinement of task descriptions
5. **EMIT** — Produce `ContextSeed` with `ForwardManifest`, `ForwardFileSpec`, dependency graph

### 1.2 The Multi-Language Problem

Plan ingestion was built for Python projects. When Go projects were first run (run-066, Online Boutique), several failures occurred:

| Failure | Root Cause | Impact |
|---------|-----------|--------|
| Python stubs in `.go` files | EMIT phase used Python DFA for all files | F-grade go.mod and HTML templates |
| Missing `go.mod` metadata | PARSE prompt didn't ask for Go module path | build.gradle generation failed |
| Wrong import format in prompts | Available-imports section assumed `pip install` format | LLM generated Python-style imports |
| Circular dependencies | LLM-generated bidirectional deps in PARSE output | 0 features processed (deadlock) |
| go.mod in wrong directory | Dependency file placed at project root, not service root | Multi-service repos broken |

These were fixed in commits `fdf40c2` and `0902ff1` (2026-03-17). This document captures those fixes as requirements and extends them to Java and future languages.

### 1.3 Relationship to Multi-Language Capability Map

The Capability Map (MULTI_LANGUAGE_CAPABILITY_MAP.md) defines 12 language-sensitive capabilities (C-1 through C-12) at the Prime Contractor level. Plan ingestion touches a **subset** of these — the ones that affect seed task construction and forward manifest population:

| Capability Map | Plan Ingestion Relevance |
|---------------|------------------------|
| **C-1: Structure Extraction** | Forward manifest element extraction in EMIT |
| **C-3: Import Resolution** | Available-imports section in prompts |
| **C-7: Stub Detection** | Not applicable (no code generated yet) |
| **C-11: Framework Preamble** | Framework detection from plan text |
| **C-12: Package Manager Artifacts** | Dependency file metadata in seed tasks |

The remaining capabilities (C-2 merge, C-4 validation, C-5 lint, C-6 import audit, C-8 dedup, C-9 splicing, C-10 blast radius) apply during code generation, not plan ingestion.

---

## 2. Current State: What Was Built for Go

### 2.1 PARSE Phase — Language-Aware Feature Extraction

**Commit:** `fdf40c2`

The PARSE prompt was extended to extract Go-specific metadata:

```
"module_path": "optional Go module path e.g. github.com/org/repo/src/svc",
"service_name": "optional service directory name e.g. shippingservice"
```

These fields are declared in `_CONTEXT_THREADABLE_FIELDS` (QP-1 pattern) so they auto-propagate from feature to task context without explicit wiring at each pipeline stage.

**Files:** `plan_ingestion_workflow.py:110, 332-333, 359-360`

### 2.2 EMIT Phase — Language Detection and ForwardFileSpec

**Commit:** `fdf40c2`

The emitter detects file language from extension and sets `ForwardFileSpec.language`:

```python
lang = detect_language(fpath)
file_specs[fpath] = ForwardFileSpec(
    ...
    language=lang if lang != "python" else None,
)
```

This ensures the Python DFA is not applied to Go or Java files downstream.

**Files:** `plan_ingestion_emitter.py:332-344`, `micro_prime/lang_detect.py`

### 2.3 Seed Derivation — Service Metadata Inference

**Commit:** `fdf40c2`

`_infer_service_metadata()` derives per-service metadata from parsed features:

- **`primary_language`**: Dominant language from target file extensions
- **`module_path`** (Go): From `ParsedFeature.module_path` or `api_signatures` (`module ...` line)
- **`service_name`** (Go): From `ParsedFeature.service_name` or directory structure
- **`go_version`** (Go): From onboarding data or default `"1.23"`
- **`api_signatures`**: Aggregated across features for service-level context
- **`negative_scope`**: Aggregated exclusions

**Files:** `plan_ingestion_workflow.py:673-777`, `seeds/derivation.py:238-334`

### 2.4 Prompt Pipeline — Go Module Context

**Commit:** `fdf40c2`

`spec_builder.py:_build_go_module_section()` generates Go-specific prompt context:
- Package declaration guidance
- Module path context
- Go import rules (stdlib first, no unused imports)
- Go structural conventions (context.Context first param, error last return)

`spec_builder.py:_build_available_imports_section()` detects Go modules by `/` in dependency names and strips version differently (`github.com/sirupsen/logrus v1.9.4` → `github.com/sirupsen/logrus`).

### 2.5 Acyclicity Gate

**Commit:** `0902ff1` (REQ-OI-002)

`_break_dependency_cycles()` uses iterative DFS to detect and break circular dependencies in PARSE output. This is language-agnostic but was motivated by Go run-066 where all 17 tasks had circular deps.

---

## 3. Requirements

### 3.1 Language Detection (REQ-PLI-100 series)

#### REQ-PLI-100: File Extension Language Mapping

`lang_detect.py:detect_language()` MUST map file extensions to language identifiers for all supported languages.

**Current mappings:**

| Extension | Language ID | Status |
|-----------|------------|--------|
| `.py`, `.pyi` | `"python"` | IMPLEMENTED |
| `.go` | `"go"` | IMPLEMENTED |
| `.java` | `"java"` | IMPLEMENTED |
| `.js`, `.ts`, `.tsx`, `.mjs`, `.cjs` | `"text"` | GAP — should map to `"nodejs"` |
| `.kt` | `"text"` | GAP — should map to `"kotlin"` (future) |
| `.rs` | `"text"` | GAP — should map to `"rust"` (future) |

**Acceptance criteria:**
- Every language with a registered `LanguageProfile` has its extensions mapped in `lang_detect.py`
- `ForwardFileSpec.language` is set correctly for all recognized extensions
- Unknown extensions default to `"unknown"` (not `"python"`)

**Status:** PARTIAL — Go and Java mapped; Node.js extensions mapped to `"text"` instead of `"nodejs"`

#### REQ-PLI-101: Language ID Consistency

The language ID returned by `lang_detect.py` MUST match the `LanguageProfile.language_id` for that language. This ensures downstream consumers (DFA, splicer, validator) route correctly.

| Source | Go | Java | Node.js | Python |
|--------|-----|------|---------|--------|
| `lang_detect.py` | `"go"` | `"java"` | `"text"` ❌ | `"python"` |
| `resolution.py` | `"go"` | `"java"` | `"nodejs"` | `"python"` |
| `LanguageProfile.language_id` | `"go"` | `"java"` | `"nodejs"` | `"python"` |

**Gap:** `lang_detect.py` maps `.js`/`.ts` to `"text"` but `LanguageProfile` uses `"nodejs"`. This mismatch means Node.js files in ForwardFileSpec get `language="text"` instead of `language="nodejs"`, preventing Node.js-specific downstream routing.

**Status:** GAP for Node.js

#### REQ-PLI-102: Filename-Based Language Detection

Files without standard extensions MUST be detected by exact name matching:

| Filename | Language ID | Status |
|----------|------------|--------|
| `Dockerfile`, `Dockerfile.*` | `"dockerfile"` | IMPLEMENTED |
| `go.mod`, `go.sum` | `"go"` | NOT in lang_detect (in `_NON_PYTHON_FILENAMES`) |
| `build.gradle`, `build.gradle.kts` | `"java"` | NOT IMPLEMENTED |
| `pom.xml` | `"java"` | NOT IMPLEMENTED |
| `settings.gradle` | `"java"` | NOT IMPLEMENTED |
| `package.json` | `"nodejs"` | NOT IMPLEMENTED |
| `Makefile` | `"text"` | NOT IMPLEMENTED |

**Status:** PARTIAL — only Dockerfile variants implemented

---

### 3.2 PARSE Phase — Language-Aware Feature Extraction (REQ-PLI-200 series)

#### REQ-PLI-200: Language-Specific Metadata Fields in PARSE Prompt

The PARSE prompt MUST request language-specific metadata fields when the plan's target language is detectable from context.

**Current Go fields (IMPLEMENTED):**
```json
{
  "module_path": "optional Go module path",
  "service_name": "optional service directory name"
}
```

**Needed Java fields:**
```json
{
  "java_package": "optional Java package e.g. com.example.service",
  "build_system": "optional: gradle or maven (default: gradle)",
  "java_version": "optional Java version e.g. 21 (default: 21)",
  "spring_boot": "optional: true if Spring Boot project"
}
```

**Needed Node.js fields:**
```json
{
  "module_system": "optional: commonjs or esm (default: esm)",
  "node_version": "optional Node.js version e.g. 20"
}
```

**Threading:** All new fields MUST be added to `_CONTEXT_THREADABLE_FIELDS` (QP-1 pattern) so they auto-propagate through the pipeline without per-stage wiring.

**Status:** IMPLEMENTED for Go; NOT IMPLEMENTED for Java and Node.js

#### REQ-PLI-201: Language-Agnostic PARSE Prompt Structure

The PARSE prompt SHOULD use a language-agnostic base with language-specific extensions, rather than embedding Go-specific text in the base prompt.

**Current state:** Go-specific guidance is inlined in the PARSE prompt (lines 359-360):
```
module_path: (Go projects only) the Go module path...
service_name: (Go projects only) the service directory name...
```

**Target state:** A conditional section injected based on detected language:
```
{language_specific_fields}
```
Where `{language_specific_fields}` is populated from a language-keyed template dict.

**Status:** NOT IMPLEMENTED — Go fields are hardcoded in prompt

#### REQ-PLI-202: Primary Language Detection from Plan Text

Before running PARSE, the workflow SHOULD detect the plan's primary language from:
1. Explicit language mentions in the plan text ("Java Spring Boot application", "Go microservices")
2. File extensions in any referenced paths (`.java`, `.go`, `.js`)
3. Framework mentions ("Spring Boot", "gRPC", "Express.js")
4. Build file mentions ("build.gradle", "go.mod", "package.json")

This enables language-specific PARSE prompt injection without requiring the user to specify the language explicitly.

**Status:** NOT IMPLEMENTED — language is inferred post-PARSE from target file extensions

---

### 3.3 Seed Derivation — Service Metadata (REQ-PLI-300 series)

#### REQ-PLI-300: Language-Aware Service Metadata Inference

`_infer_service_metadata()` MUST derive language-specific metadata from parsed features for all supported languages.

**Current Go implementation (IMPLEMENTED):**
- `module_path`: From feature field or `api_signatures` scan
- `service_name`: From feature field or directory structure
- `go_version`: From onboarding data or default

**Needed Java implementation:**
- `java_package`: From target file paths (derive from `src/main/java/com/example/...`)
- `build_system`: From plan text or build file targets (`build.gradle` → `"gradle"`, `pom.xml` → `"maven"`)
- `java_version`: From plan text, feature metadata, or default `"21"`
- `spring_boot`: From annotation mentions or dependency keywords

**Needed Node.js implementation:**
- `module_system`: From `.mjs`/`.cjs` extensions or `"type": "module"` in package.json ref
- `node_version`: From plan text or default

**Status:** IMPLEMENTED for Go; NOT IMPLEMENTED for Java and Node.js

#### REQ-PLI-301: Context Threading of Language Metadata

All language-specific metadata fields MUST be included in `_CONTEXT_THREADABLE_FIELDS` so the QP-1 auto-threading pattern propagates them from PARSE output through TRANSFORM/REFINE/EMIT without manual wiring at each stage.

**Current threadable fields:**
```python
_CONTEXT_THREADABLE_FIELDS = {
    "module_path",    # Go
    "service_name",   # Go
    ...
}
```

**Needed additions:**
```python
_CONTEXT_THREADABLE_FIELDS = {
    # Go
    "module_path",
    "service_name",
    # Java
    "java_package",
    "build_system",
    "java_version",
    "spring_boot",
    # Node.js
    "module_system",
    "node_version",
    # Language-agnostic
    "primary_language",
}
```

**Status:** PARTIAL — Go fields present; Java and Node.js fields missing

#### REQ-PLI-302: Primary Language in Seed Output

The emitted `ContextSeed` MUST include `primary_language` in its `service_metadata` dict so downstream consumers (Prime Contractor, spec builder, drafter) can resolve the correct language profile without re-inferring from file extensions.

**Status:** IMPLEMENTED — `_infer_service_metadata()` sets `primary_language` from target file analysis

---

### 3.4 EMIT Phase — Forward Manifest Population (REQ-PLI-400 series)

#### REQ-PLI-400: Language-Tagged ForwardFileSpec

Every `ForwardFileSpec` emitted by plan ingestion MUST have its `language` field set via `detect_language()`. Files with `language != "python"` MUST NOT be routed through the Python `DeterministicFileAssembler`.

**Status:** IMPLEMENTED

#### REQ-PLI-401: Language-Appropriate Element Extraction

When populating `ForwardFileSpec.elements` during EMIT, the emitter SHOULD use language-appropriate parsing:

| Language | Parser | Status |
|----------|--------|--------|
| Python | `ast.parse()` → `ForwardElementSpec` | IMPLEMENTED |
| Go | `go_parser.parse_go_source()` → `GoElement` → contract | IMPLEMENTED |
| Java | `java_parser.parse_java_source()` → `JavaElement` → contract | IMPLEMENTED |
| Node.js | Regex-based extraction | NOT IMPLEMENTED |

**Note:** Element extraction during EMIT is for forward manifest contract reconciliation, not for code generation. The `ForwardElementSpec` list in each `ForwardFileSpec` is populated from the PARSE phase LLM output, not from source code parsing (which happens in `forward_manifest_extractor.py` post-generation).

**Status:** IMPLEMENTED for Python, Go, Java

#### REQ-PLI-402: Dependency File Identification

The EMIT phase MUST identify dependency files in target_files and tag them appropriately:

| File Pattern | Language | Treatment |
|-------------|----------|-----------|
| `requirements.txt`, `*.in` | Python | Deterministic generation via `requirements_generator.py` |
| `go.mod` | Go | Deterministic generation via `GoLanguageProfile.generate_dependency_file()` |
| `build.gradle`, `build.gradle.kts` | Java | Deterministic generation via `JavaLanguageProfile.generate_dependency_file()` |
| `pom.xml` | Java | File-whole LLM generation (too complex for templates) |
| `package.json` | Node.js | Deterministic generation via `NodeLanguageProfile.generate_dependency_file()` |
| `settings.gradle` | Java | File-whole LLM generation |
| `application.yml`, `application.properties` | Java | File-whole LLM generation |

**Status:** IMPLEMENTED for Python, Go, Java (Gradle); NOT IMPLEMENTED for Maven, Node.js

---

### 3.5 Prompt Context — Language-Specific Sections (REQ-PLI-500 series)

#### REQ-PLI-500: Available-Imports Section Language Awareness

`spec_builder.py:_build_available_imports_section()` MUST format dependency lists using the target language's package syntax:

| Language | Input Format | Output in Prompt |
|----------|-------------|-----------------|
| Python | `grpcio==1.76.0` | `import grpc` (via alias map) |
| Go | `google.golang.org/grpc v1.68.0` | `import "google.golang.org/grpc"` |
| Java | `io.grpc:grpc-netty:1.68.0` | `import io.grpc.Server;` (via framework_imports) |
| Node.js | `@grpc/grpc-js@1.10.0` | `const grpc = require('@grpc/grpc-js')` or `import ... from '@grpc/grpc-js'` |

**Status:** IMPLEMENTED for Python and Go; PARTIAL for Java (framework_imports detected but not fully formatted); NOT IMPLEMENTED for Node.js

#### REQ-PLI-501: Language-Specific Module Section

When the resolved language is not Python, the spec builder MUST inject a language-specific module context section:

| Language | Section Content | Status |
|----------|----------------|--------|
| Go | Package declaration, module path, Go import rules, structural conventions | IMPLEMENTED (`_build_go_module_section()`) |
| Java | Package statement, class naming, Java import ordering, annotation conventions | NOT IMPLEMENTED |
| Node.js | Module system (CJS vs ESM), export patterns, import syntax | NOT IMPLEMENTED |

**Target:** `_build_java_module_section()` and `_build_nodejs_module_section()` parallel to `_build_go_module_section()`.

**Status:** IMPLEMENTED for Go; NOT IMPLEMENTED for Java and Node.js

#### REQ-PLI-502: Framework Detection from Plan Text

During PARSE or TRANSFORM, the workflow SHOULD detect framework indicators from the plan text and seed them into `service_metadata`:

| Framework | Detection Signals | Languages |
|-----------|-------------------|-----------|
| Spring Boot | "Spring Boot", "@SpringBootApplication", "spring-boot-starter" | Java |
| JPA/Hibernate | "@Entity", "JPA", "Hibernate", "jakarta.persistence" | Java |
| gRPC | "gRPC", "protobuf", ".proto" | Go, Java, Node.js |
| Express.js | "Express", "express", "middleware" | Node.js |
| React | "React", "JSX", "useState", "component" | Node.js |

**Status:** PARTIAL — Go gRPC detection exists; Java framework detection exists in `spec_builder.detect_java_frameworks()` but not wired to plan ingestion PARSE phase

---

### 3.6 Dependency Graph — Multi-Language Considerations (REQ-PLI-600 series)

#### REQ-PLI-600: Acyclicity Gate (Language-Agnostic)

The PARSE output MUST be validated for circular dependencies before TRANSFORM. The `_break_dependency_cycles()` DFS algorithm breaks back-edges with WARNING logs.

**Status:** IMPLEMENTED (REQ-OI-002, commit `0902ff1`)

#### REQ-PLI-601: Cross-Language Dependency Ordering

In multi-language projects (e.g., Go gRPC services + HTML templates + Dockerfiles), the dependency graph MUST respect language-specific build order:

1. **Shared libraries** before **services** (shared proto definitions before gRPC services)
2. **Source code** before **build files** (`.java` before `build.gradle`)
3. **Build files** before **deployment files** (`go.mod` before `Dockerfile`)
4. **Configuration** before **application code** (`application.yml` before `Application.java`)

**Status:** PARTIAL — dependency ordering exists but is not language-aware

#### REQ-PLI-602: Per-Service Dependency File Placement

For multi-service repos, dependency files MUST be placed in the correct service directory:

| Pattern | Correct Location | Example |
|---------|-----------------|---------|
| Go monorepo | `src/{service}/go.mod` | `src/shippingservice/go.mod` |
| Gradle multi-module | `{module}/build.gradle` | `service-a/build.gradle` |
| Maven multi-module | `{module}/pom.xml` | `service-a/pom.xml` |
| Node.js monorepo | `{package}/package.json` | `packages/api/package.json` |

**Status:** IMPLEMENTED for Go; IMPLEMENTED for Java (Gradle); NOT IMPLEMENTED for Maven, Node.js

---

### 3.7 ParsedFeature Model Extensions (REQ-PLI-700 series)

#### REQ-PLI-700: Language-Specific Fields on ParsedFeature

`ParsedFeature` (in `plan_ingestion_models.py`) MUST support language-specific optional fields:

**Current fields (Go):**
```python
module_path: str = ""      # Go module path
service_name: str = ""     # Go service directory
```

**Needed fields (Java):**
```python
java_package: str = ""     # Java package e.g. com.example.service
build_system: str = ""     # "gradle" or "maven"
java_version: str = ""     # Java version e.g. "21"
spring_boot: bool = False  # Spring Boot project indicator
```

**Needed fields (Node.js):**
```python
module_system: str = ""    # "commonjs" or "esm"
node_version: str = ""     # Node.js version e.g. "20"
```

**Status:** IMPLEMENTED for Go; NOT IMPLEMENTED for Java and Node.js

#### REQ-PLI-701: SeedTask Language Metadata

`SeedTask` (in `seeds/models.py`) MUST mirror the language-specific fields from `ParsedFeature` so they are available to the Prime Contractor at execution time.

**Status:** IMPLEMENTED for Go (module_path, service_name); NOT IMPLEMENTED for Java and Node.js

---

## 4. Implementation Status Summary

### Implemented (All Languages)

| REQ | Description | Commit |
|-----|-------------|--------|
| REQ-PLI-100 | Language detection for .py, .go, .java, .js/.ts/.tsx/.mjs/.cjs → "nodejs" | `fdf40c2`, `04c9457`, 2026-03-18 |
| REQ-PLI-101 | Language ID consistency (lang_detect ↔ resolution.py) | 2026-03-18 |
| REQ-PLI-102 | Filename-based detection (build.gradle, pom.xml, package.json, settings.gradle) | 2026-03-18 |
| REQ-PLI-302 | Primary language in seed output | `fdf40c2` |
| REQ-PLI-400 | Language-tagged ForwardFileSpec | `fdf40c2` |
| REQ-PLI-401 (partial) | Element extraction for Python, Go, Java | `fdf40c2`, `04c9457` |
| REQ-PLI-600 | Acyclicity gate | `0902ff1` |

### Implemented (Go)

| REQ | Description | Commit |
|-----|-------------|--------|
| REQ-PLI-200 (Go) | PARSE prompt Go metadata fields | `fdf40c2` |
| REQ-PLI-300 (Go) | Service metadata inference (module_path, service_name, go_version) | `fdf40c2` |
| REQ-PLI-301 (Go) | Context threading for Go fields | `fdf40c2` |
| REQ-PLI-402 (Go) | go.mod deterministic generation | `fdf40c2` |
| REQ-PLI-500 (Go) | Available-imports Go formatting | `fdf40c2` |
| REQ-PLI-501 (Go) | `_build_go_module_section()` | `fdf40c2` |
| REQ-PLI-602 (Go) | Per-service go.mod placement | `fdf40c2` |
| REQ-PLI-700 (Go) | ParsedFeature Go fields | `fdf40c2` |
| REQ-PLI-701 (Go) | SeedTask Go fields | `fdf40c2` |

### Implemented (Java)

| REQ | Description | Commit |
|-----|-------------|--------|
| REQ-PLI-100 (Java) | `.java` → `"java"` in lang_detect | `04c9457` |
| REQ-PLI-200 (Java) | PARSE prompt Java metadata fields (java_package, build_system, java_version) | 2026-03-18 |
| REQ-PLI-300 (Java) | Java service metadata inference (package, build_system, version, spring_boot) | 2026-03-18 |
| REQ-PLI-301 (Java) | Context threading for Java fields | 2026-03-18 |
| REQ-PLI-402 (Java) | build.gradle deterministic generation | `04c9457` |
| REQ-PLI-500 (Java) | Available-imports Java formatting (`:` coord stripping) | 2026-03-18 |
| REQ-PLI-501 (Java) | `_build_java_project_section()` | 2026-03-18 |
| REQ-PLI-502 (Java, partial) | Framework detection in spec_builder | `23c7af3` |
| REQ-PLI-700 (Java) | ParsedFeature Java fields | 2026-03-18 |
| REQ-PLI-701 (Java) | SeedTask Java fields | 2026-03-18 |

### Implemented (Node.js)

| REQ | Description | Commit |
|-----|-------------|--------|
| REQ-PLI-100 (Node.js) | `.js`/`.ts`/`.tsx`/`.mjs`/`.cjs`/`.jsx` → `"nodejs"` in lang_detect | 2026-03-18 |
| REQ-PLI-200 (Node.js) | PARSE prompt Node.js metadata fields (module_system, node_version) | 2026-03-18 |
| REQ-PLI-300 (Node.js) | Node.js service metadata inference (module_system, node_version) | 2026-03-18 |
| REQ-PLI-301 (Node.js) | Context threading for Node.js fields | 2026-03-18 |
| REQ-PLI-500 (Node.js) | Available-imports Node.js formatting (`@scope/pkg@ver` stripping) | 2026-03-18 |
| REQ-PLI-501 (Node.js) | `_build_nodejs_module_section()` (ESM/CJS guidance) | 2026-03-18 |
| REQ-PLI-700 (Node.js) | ParsedFeature Node.js fields | 2026-03-18 |
| REQ-PLI-701 (Node.js) | SeedTask Node.js fields | 2026-03-18 |

### Implemented (Cross-Language Infrastructure)

| REQ | Description | Commit |
|-----|-------------|--------|
| REQ-PLI-201 | Language-agnostic PARSE prompt structure (template dict + `_build_parse_prompt()`) | 2026-03-18 |
| REQ-PLI-202 | Pre-PARSE language detection from plan text (`_detect_plan_language()`) | 2026-03-18 |
| REQ-PLI-601 | Cross-language dependency ordering guidance (Go, Java, Node.js) | 2026-03-18 |

### All Requirements Implemented

REQ-PLI-402 (Node.js package.json generation) was already implemented — `NodeLanguageProfile.generate_dependency_file()` produces valid package.json, and `PrimeContractorWorkflow._ensure_dependency_file()` is fully generic (routes any language with `build_file_patterns` + `generate_dependency_file()`).

---

## 5. Data Flow: Plan Ingestion Multi-Language Pipeline

```
Plan Document (markdown)
  |
  v
[Pre-PARSE] Language hint detection (REQ-PLI-202)
  Scan plan text for language keywords, file extensions, framework mentions
  → primary_language_hint: "go" | "java" | "nodejs" | "python" | None
  |
  v
[PARSE Phase] LLM feature extraction
  PARSE prompt includes language-specific field templates (REQ-PLI-200/201):
    - Go: module_path, service_name
    - Java: java_package, build_system, java_version, spring_boot
    - Node.js: module_system, node_version
  → List[ParsedFeature] with language fields populated
  |
  v
[Acyclicity Gate] (REQ-PLI-600)
  _break_dependency_cycles() → removes back-edges
  |
  v
[TRANSFORM Phase] Feature → SeedTask normalization
  Language fields auto-threaded via QP-1 (REQ-PLI-301)
  |
  v
[Service Metadata Inference] (REQ-PLI-300)
  _infer_service_metadata():
    - primary_language from target file extensions
    - Go: module_path, service_name, go_version
    - Java: java_package, build_system, java_version, spring_boot
    - Node.js: module_system, node_version
    - api_signatures, negative_scope (all languages)
  → service_metadata dict
  |
  v
[EMIT Phase] ContextSeed production
  For each target_file:
    detect_language(file_path) → language ID (REQ-PLI-100)
    ForwardFileSpec(language=lang_id) (REQ-PLI-400)
  Dependency files identified (REQ-PLI-402):
    go.mod → Go profile.generate_dependency_file()
    build.gradle → Java profile.generate_dependency_file()
    package.json → Node profile.generate_dependency_file()
  → ContextSeed with ForwardManifest + service_metadata
  |
  v
[Prime Contractor] receives seed
  resolve_language(target_files) → LanguageProfile
  _build_generation_context():
    language_role from profile
    coding_standards from profile
    service_metadata from seed
  → Java/Go/Node-appropriate generation
```

---

## 6. Go Pattern Leverage for Other Languages

The Go implementation established patterns that generalize. For each new language, the following checklist applies:

### Per-Language Plan Ingestion Checklist

| Step | Go Example | Java Equivalent | Node.js Equivalent |
|------|-----------|----------------|-------------------|
| 1. Add extensions to `lang_detect.py` | `.go` → `"go"` ✅ | `.java` → `"java"` ✅ | `.js`/`.ts` → `"nodejs"` ✅ |
| 2. Add PARSE prompt fields | `module_path`, `service_name` ✅ | `java_package`, `build_system` ✅ | `module_system`, `node_version` ✅ |
| 3. Add to `_CONTEXT_THREADABLE_FIELDS` | `module_path`, `service_name` ✅ | `java_package`, `build_system`, `java_version` ✅ | `module_system`, `node_version` ✅ |
| 4. Extend `_infer_service_metadata()` | Go-specific block ✅ | Java-specific block ✅ | Node-specific block ✅ |
| 5. Add `ParsedFeature` fields | `module_path`, `service_name` ✅ | `java_package`, `build_system`, `java_version`, `spring_boot` ✅ | `module_system`, `node_version` ✅ |
| 6. Add `SeedTask` fields | Same as ParsedFeature ✅ | Same ✅ | Same ✅ |
| 7. Add `_build_X_module_section()` | `_build_go_module_section()` ✅ | `_build_java_project_section()` ✅ | `_build_nodejs_module_section()` ✅ |
| 8. Add dep file generation routing | `go.mod` → `generate_dependency_file()` ✅ | `build.gradle` → `generate_dependency_file()` ✅ | `package.json` → `generate_dependency_file()` ✅ |
| 9. Add filename detection | N/A | `build.gradle` → `"java"` ✅ | `package.json` → `"nodejs"` ✅ |

---

## 7. Priority Ordering

### P1 — Immediate (enables first Java plan ingestion run) — ALL DONE ✅

1. ~~**REQ-PLI-200 (Java)**: Add Java fields to PARSE prompt~~ ✅
2. ~~**REQ-PLI-300 (Java)**: Java service metadata inference~~ ✅
3. ~~**REQ-PLI-301 (Java)**: Add Java fields to `_CONTEXT_THREADABLE_FIELDS`~~ ✅
4. ~~**REQ-PLI-501 (Java)**: `_build_java_project_section()` in spec_builder~~ ✅
5. ~~**REQ-PLI-700 (Java)**: Add Java fields to `ParsedFeature` and `SeedTask`~~ ✅

### P2 — Quality (improves multi-language robustness) — MOSTLY DONE

6. ~~**REQ-PLI-100 (Node.js)**: Fix `.js`/`.ts` → `"nodejs"` in lang_detect~~ ✅
7. ~~**REQ-PLI-101**: Fix lang_detect ↔ resolution.py ID consistency~~ ✅
8. ~~**REQ-PLI-102**: Filename-based detection (build.gradle, package.json, etc.)~~ ✅
9. ~~**REQ-PLI-201**: Refactor PARSE prompt to language-agnostic base + extensions~~ ✅
10. ~~**REQ-PLI-500 (Java)**: Java-formatted available-imports section~~ ✅

### P3 — Future (Node.js and cross-language) — MOSTLY DONE

11. ~~**REQ-PLI-200 (Node.js)**: Node.js PARSE prompt fields~~ ✅
12. ~~**REQ-PLI-300 (Node.js)**: Node.js service metadata inference~~ ✅
13. ~~**REQ-PLI-501 (Node.js)**: `_build_nodejs_module_section()`~~ ✅
14. ~~**REQ-PLI-601**: Cross-language dependency ordering~~ ✅
15. ~~**REQ-PLI-202**: Pre-PARSE language detection from plan text~~ ✅

---

## 8. Comparison: Plan Ingestion Capability by Language

| Capability | Python | Go | Java | Node.js |
|-----------|--------|-----|------|---------|
| File extension detection | ✅ | ✅ | ✅ | ✅ |
| Filename detection | N/A | Partial | ✅ | ✅ |
| PARSE prompt fields | N/A (default) | ✅ | ✅ | ✅ |
| Context threading (QP-1) | N/A | ✅ | ✅ | ✅ |
| Service metadata inference | N/A (default) | ✅ | ✅ | ✅ |
| ForwardFileSpec.language | ✅ | ✅ | ✅ | ✅ |
| Module context section | N/A (default) | ✅ | ✅ | ✅ |
| Available-imports formatting | ✅ | ✅ | ✅ | ✅ |
| Dependency file generation | ✅ | ✅ | ✅ (Gradle) | ✅ |
| Dep file placement | ✅ | ✅ | ✅ | ✅ |
| Acyclicity gate | ✅ | ✅ | ✅ | ✅ |
| Element extraction (post-gen) | ✅ | ✅ | ✅ | ❌ |
| Per-file syntax validation | ✅ | ✅ | ✅ (javalang) | Partial (node --check) |
| Security enrichment (Anzen) | ✅ | ✅ | ✅ | ✅ |

**Legend:** ✅ = Implemented, ❌ = Not implemented, Partial = Some support

---

## 9. Anzen Security Enrichment at EMIT (2026-03-20)

**Commit:** `db30fb0`

During task derivation in `_derive_tasks_from_features()`, each feature's description and target files are scanned for database keywords via `security_prime.enrichment.enrich_security_fields()` (which delegates to `query_prime.decomposer.detect_database_type()`). When a database surface is detected:

- `ctx["security_sensitive"] = True` — signals the complexity classifier to enforce a MODERATE floor
- `ctx["detected_database"] = "postgresql"` (or spanner/redis/mysql/sqlite) — enables spec_builder P1 guidance injection

This makes the seed file self-describing for security: `jq '.tasks[] | select(.config.context.security_sensitive)' prime-context-seed.json` shows security-sensitive tasks before any contractor run. Graceful degradation: `ImportError` on `security_prime` is silently caught; plan ingestion works identically without the package.

See [SECURITY_PRIME_REQUIREMENTS.md](../security-prime/SECURITY_PRIME_REQUIREMENTS.md) for the full Anzen pipeline design.
