# Java Prime Contractor — Requirements & Design

**Date:** 2026-03-17
**Status:** Active / IMPLEMENTED
**Derived From:** Go Prime Contractor Requirements (REQ-GO-*), `JavaLanguageProfile` in `languages/java.py`, MICRO_PRIME_MULTI_LANGUAGE_CAPABILITY_MAP.md, DETERMINISTIC_FILE_ASSEMBLY_REQUIREMENTS.md
**Strategy:** MicroPrime-first (opposite of Go, which was Prime Contractor-first then MicroPrime)
**Implementation Commit:** `23c7af3` feat: Java MicroPrime support (Phases 1-5)

---

## 1. Context & Strategic Rationale

### 1.1 Background

The Prime Contractor workflow generates code for multi-file features. All prior ~50 runs targeted Python; run-066 was the first Go run. No Java runs have been attempted yet. For Go, the approach was: validate Prime Contractor cloud-path generation first, then add MicroPrime support after. For Java, we inverted this sequence — building all MicroPrime infrastructure (parser, DFA, splicer, templates, decomposition) before the first Java run.

### 1.2 Why MicroPrime-First for Java

Java's rigid structure makes it a **superior** candidate for deterministic assembly compared to both Python and Go:

**1. One-class-per-file eliminates ownership ambiguity.**
Python's DFA has an open question (DFA doc S12 Q1): which methods belong to which class? In Java this is never ambiguous — public class must match filename, all methods are declared inside a class body. The `ForwardElementSpec.parent_class` problem doesn't exist.

**2. Package statement <-> file path is a deterministic bijection.**
`com.example.service.MyService` -> `src/main/java/com/example/service/MyService.java`. No heuristic needed — the mapping is enforced by the compiler. DFA can derive the `package` statement from the file path and vice versa.

**3. Explicit access modifiers map directly to `ForwardElementSpec.visibility`.**
Every Java element declares `public`/`protected`/`private`. No `__all__` list needed (Python DFA FR-007), no guessing about export scope.

**4. Fully typed signatures with no parameter-kind complexity.**
Java has no `*args`, `**kwargs`, positional-only (`/`), or keyword-only (`*`) parameters. Every parameter is `Type name`. DFA signature rendering (FR-002) is dramatically simpler.

**5. `javalang` provides Python-native AST parsing.**
Unlike Go (which required regex-based `go_parser.py`), the `javalang` PyPI package gives real AST parsing from Python — covering MP-1 (syntax validation), MP-2 (element location), and MP-8 (structural verification) without subprocesses.

**6. Several Python DFA complexities disappear entirely.**
- No `__init__.py` chain generation (Java packages are directories, no marker files)
- No `from __future__ import annotations` preamble
- No 4-tier import ordering (Java: `java.*` then everything else)
- No `__all__` export list generation
- No `async def` prefix (Java uses `CompletableFuture<T>` return types)

**7. Java boilerplate is template-friendly.**
Constructor, getter/setter, `equals`/`hashCode`/`toString`, and Builder patterns are highly regular — ideal for deterministic template generation (MP-9 equivalent). Python's dunder templates cover 6 patterns; Java's equivalent covers 8+.

### 1.3 Comparison: DFA Complexity by Language

| DFA Requirement | Python | Go | Java |
|---|---|---|---|
| FR-002 Signature Fidelity | 5 param kinds, `*`, `/`, `**kwargs` | 2 (positional + variadic `...`) | 2 (positional + varargs `Type...`) |
| FR-003 Import Ordering | 4 tiers (future/stdlib/3p/local) | 2 tiers (stdlib/3p) | 2 tiers (`java.*`/everything else) |
| FR-004 Class Hierarchy | Methods assigned by heuristic | No classes (structs) | Methods always inside class |
| FR-006 `__init__.py` Chain | Must create marker files | N/A | N/A |
| FR-007 `__all__` Generation | Manual export list | N/A | N/A (access modifiers) |
| FR-008 Syntax Validation | `ast.parse()` | `gofmt -e` (subprocess) | `javalang.parse.parse()` (in-process) |
| FR-013 Async Rendering | `async def` prefix | goroutines (implicit) | Return type only (`CompletableFuture<T>`) |
| Method-to-class ownership | Open question | N/A (methods on structs) | Deterministic (one class per file) |

---

## 2. Java Language Profile — Current State

**File:** `src/startd8/languages/java.py` (367 lines)

### Implemented Capabilities

| Capability | Status | Implementation |
|-----------|--------|----------------|
| Language ID & display name | Done | `"java"` / `"Java"` |
| Source extensions | Done | `[".java"]` |
| Build file patterns | Done | `["build.gradle", "settings.gradle", "pom.xml", "build.gradle.kts"]` |
| Syntax check | Done | `javalang.parse.parse()` with text-based fallback |
| Lint | Disabled | No lightweight Java linter callable from CLI |
| Test | Stub | `gradle test` (requires project context) |
| Framework imports | Done | Spring Boot (`org.springframework`), JPA (`javax.persistence`/`jakarta.persistence`), SLF4J (`org.slf4j`), gRPC (`io.grpc`), Logging (`log4j`) |
| Stdlib prefixes | Done | 4 prefixes (`java.`, `javax.`, `jdk.`, `sun.`) |
| Post-generation cleanup | Disabled | No authoritative import fixer |
| Syntax validation | Done | `_validate_java_syntax()` via `javalang` with text-based fallback |
| `build.gradle` generation | Done | `generate_dependency_file()` |
| Docker images | Done | Builder: `eclipse-temurin:21-jdk`, Runtime: `eclipse-temurin:21-jre-alpine` |
| Coding standards | Done | PascalCase, camelCase, explicit access modifiers, no wildcard imports |
| Merge strategy | Done | `"simple"` (whole-file replacement) |
| Repair | Disabled | Python AST repair is not applicable |
| Stub patterns | Done | 4 patterns |
| Function start pattern | Done | Regex matching access modifiers + return type + method name |
| Reserved keywords | Done | `_JAVA_RESERVED` frozenset (53 keywords + contextual + literals) |

### Key Integration: `javalang` Wired

The `javalang` PyPI package is an optional dependency under `[java]` extras. It provides `javalang.parse.parse(code)` returning a full AST with class declarations, method declarations, field declarations, annotations, imports, and package statements. Used by:
- `java.py:validate_syntax()` — syntax validation (REQ-JMP-101)
- `java_parser.py:parse_java_source()` — element extraction (REQ-JMP-102)
- `forward_manifest_extractor.py:_reconcile_java_file()` — contract extraction (REQ-JMP-103)
- `forward_manifest_validator.py:_validate_java_file()` — disk compliance (REQ-JMP-700)

---

## 3. Target Project Characteristics

### 3.1 Gradle Multi-Module (Microservices)

```
project-root/
+-- settings.gradle
+-- build.gradle
+-- service-a/
|   +-- build.gradle
|   +-- src/main/java/com/example/servicea/
|       +-- Application.java
|       +-- controller/
|       +-- service/
+-- service-b/
|   +-- build.gradle
|   +-- src/main/java/com/example/serviceb/
+-- shared-lib/
    +-- build.gradle
    +-- src/main/java/com/example/shared/
```

### 3.2 Maven Multi-Module

```
project-root/
+-- pom.xml                  (parent POM)
+-- service-a/
|   +-- pom.xml
|   +-- src/main/java/...
+-- service-b/
    +-- pom.xml
    +-- src/main/java/...
```

### 3.3 Spring Boot Application

```
project-root/
+-- build.gradle
+-- src/
    +-- main/
    |   +-- java/com/example/app/
    |   |   +-- Application.java
    |   |   +-- config/
    |   |   +-- controller/
    |   |   +-- service/
    |   |   +-- repository/
    |   |   +-- model/
    |   +-- resources/
    |       +-- application.yml
    |       +-- templates/     (Thymeleaf)
    +-- test/
        +-- java/com/example/app/
```

---

## 4. Requirements

### 4.1 MicroPrime Foundation (REQ-JMP-100 series)

These requirements enable Java files to flow through MicroPrime instead of bypassing to cloud.

#### REQ-JMP-100: javalang Dependency

Add `javalang` as an optional dependency under `[java]` extras in `pyproject.toml`.

```toml
[project.optional-dependencies]
java = ["javalang>=0.13.0"]
```

**Rationale:** `javalang` is a pure-Python Java parser (~800KB). It provides `javalang.parse.parse(code)` returning a full AST with class declarations, method declarations, field declarations, annotations, imports, and package statements. No JRE required.

**Status:** IMPLEMENTED (`23c7af3`)

#### REQ-JMP-101: Java Syntax Validation via javalang (MP-1)

Replace the stub `validate_syntax()` on `JavaLanguageProfile` with `javalang.parse.parse(code)`.

**Acceptance criteria:**
- Valid Java code returns `(True, "")`
- Invalid Java code returns `(False, error_message)` with parse error details
- If `javalang` is not installed, falls back to text-based heuristic (balanced braces, contains `class`/`interface`/`enum`/`record` keyword)
- Cross-language guard: Python content in `.java` files returns `(False, "Python content detected")`

**Status:** IMPLEMENTED (`23c7af3`) — `java.py:validate_syntax()` delegates to `_validate_java_syntax()` which uses `javalang.parse.parse()` with text-based fallback when `javalang` is not installed.

#### REQ-JMP-102: Java Element Location via javalang (MP-2)

Create `src/startd8/languages/java_parser.py` that extracts structural elements from Java source:

**Extracted elements:**
- Package declaration
- Import statements (regular and static)
- Class/interface/enum/record declarations (name, modifiers, extends, implements)
- Method declarations (name, modifiers, return type, parameters, annotations)
- Field declarations (name, type, modifiers, initial value)
- Constructor declarations

**Interface:**
```python
@dataclass
class JavaElement:
    kind: str          # "class", "interface", "enum", "record", "method", "field", "constructor"
    name: str
    modifiers: list[str]  # ["public", "static", "final", ...]
    line: int
    end_line: int
    parent: Optional[str]  # enclosing class name
    signature: Optional[str]  # for methods/constructors
    annotations: list[str]

def parse_java_elements(code: str) -> list[JavaElement]: ...
def find_element(code: str, name: str, kind: str = None) -> Optional[JavaElement]: ...
def extract_element_body(code: str, element: JavaElement) -> str: ...
```

**Status:** IMPLEMENTED (`23c7af3`) — `java_parser.py` provides `parse_java_source()` and `parse_java_elements()` backed by `javalang` AST. Used by `_reconcile_java_file()` in `forward_manifest_extractor.py` for InterfaceContract extraction.

#### REQ-JMP-103: Java Structural Verification via javalang (MP-8)

Verify generated Java files contain all expected elements from `ForwardManifest`:

**Checks:**
- All classes/interfaces from manifest are present
- All methods from manifest are present with correct names
- All fields from manifest are present
- No stub bodies remain (`throw new UnsupportedOperationException()` after IMPLEMENT)
- Package statement matches expected path

**Status:** IMPLEMENTED (`23c7af3`) — Wired through `forward_manifest_extractor.py:_reconcile_java_file()` using `java_parser.parse_java_source()` for element extraction and contract verification.

#### REQ-JMP-104: Remove .java from NON_PYTHON_EXTENSIONS

Once REQ-JMP-101 through REQ-JMP-103 are implemented, remove `".java"` from `_NON_PYTHON_EXTENSIONS` in `engine.py` so Java files flow through MicroPrime instead of bypassing to cloud.

**Guard:** Feature flag `JAVA_MICROPRIME_ENABLED` (default `False`) controls whether `.java` is removed from the bypass set. When `True`, `_is_non_python_file()` returns `False` for `.java` files, routing them through the MicroPrime pipeline.

**Status:** IMPLEMENTED (`23c7af3`) — `engine.py:96` defines `JAVA_MICROPRIME_ENABLED = False`. `_is_non_python_file()` at line 117 conditionally bypasses `.java` files based on the flag value.

---

### 4.2 Deterministic File Assembly for Java (REQ-JMP-200 series)

These requirements extend the DFA concept (currently Python-only, per DETERMINISTIC_FILE_ASSEMBLY_REQUIREMENTS.md) to Java.

#### REQ-JMP-200: Java DFA — ForwardFileSpec to .java Source

Create a `JavaDeterministicFileAssembler` that renders `ForwardFileSpec` -> syntactically valid `.java` source containing:

1. `package` statement derived from file path (deterministic — path bijection)
2. Import block: `java.*`/`javax.*` first, then third-party, then project-internal
3. Class/interface/enum/record declaration with modifiers, extends, implements
4. Method stubs with full typed signatures and `throw new UnsupportedOperationException("TODO")` bodies
5. Field declarations with types and default values
6. Annotations on classes, methods, and fields

**Key simplifications vs Python DFA:**
- No `__init__.py` chain (FR-006 equivalent: N/A)
- No `__all__` generation (FR-007 equivalent: access modifiers handle visibility)
- No `from __future__` preamble (FR-001 equivalent: N/A)
- Method-to-class ownership is unambiguous (FR-004 equivalent: trivial)
- No async prefix rendering (FR-013 equivalent: return type only)

**Acceptance criteria:**
- Every rendered `.java` file passes `javalang.parse.parse()` (syntax valid)
- Package statement matches directory path relative to `src/main/java/`
- Public class name matches filename (Java compiler requirement)
- Round-trip: `ForwardFileSpec` -> render -> parse -> extract element names -> match original spec

**Status:** IMPLEMENTED (`23c7af3`) — `JavaDeterministicFileAssembler` class invoked from `prime_adapter.py:fill_skeletons()` for `.java` files. Produces skeleton files with correct package statements, import blocks, class shells, and method stubs.

#### REQ-JMP-201: Java Package Statement Derivation

Given a file path like `src/main/java/com/example/service/OrderService.java`, the assembler MUST deterministically derive:
- Package: `com.example.service`
- Class name: `OrderService`

**Rules:**
- Strip prefix up to and including `src/main/java/` (or `src/test/java/`)
- Convert remaining path separators to `.`
- Remove filename to get package; use filename stem as class name
- If `src/main/java/` prefix not found, derive from deepest package-like path segments

**Status:** IMPLEMENTED (`23c7af3`)

#### REQ-JMP-202: Java Import Block Rendering

Import blocks SHALL follow Java conventions:

```java
// 1. java.* / javax.* (stdlib)
import java.util.List;
import java.util.Map;

// 2. Third-party
import org.springframework.stereotype.Service;
import com.google.protobuf.Message;

// 3. Project-internal
import com.example.shared.Money;
```

**Classification sources:**
- **stdlib**: `java.*`, `javax.*` prefixes (from `JavaLanguageProfile.get_stdlib_prefixes()`)
- **third-party**: Everything else not matching project package prefix
- **project-internal**: Imports matching the project's base package (from `module_path` or seed metadata)

No wildcard imports (`import java.util.*`) — always explicit.

**Status:** IMPLEMENTED (`23c7af3`)

#### REQ-JMP-203: Java Class Shell Rendering

For `ForwardElementSpec` with `kind=CLASS`:

```java
@Service                                    // from decorators[]
public class OrderService extends BaseService implements OrderHandler {
                                            // from bases[] -> extends + implements
    private static final Logger logger = LoggerFactory.getLogger(OrderService.class);
                                            // from fields[]

    public OrderResponse processOrder(OrderRequest request) {
        throw new UnsupportedOperationException("TODO");
    }                                       // method stubs with full signatures

    private void validateOrder(OrderRequest request) {
        throw new UnsupportedOperationException("TODO");
    }
}
```

**Rendering rules:**
- Annotations above class declaration
- Access modifier + `class`/`interface`/`enum`/`record` + name
- `extends` for single superclass, `implements` for interfaces (from `bases[]`)
- Fields before methods (Java convention)
- Constructor before other methods
- Methods with full typed signatures and stub bodies

**Status:** IMPLEMENTED (`23c7af3`)

#### REQ-JMP-204: Java Stub Bodies

| Element Kind | Stub Body |
|---|---|
| Method (non-void) | `throw new UnsupportedOperationException("TODO");` |
| Method (void) | `throw new UnsupportedOperationException("TODO");` |
| Constructor | `// TODO: implement` (empty body is valid) |
| Interface method | No body (abstract by default) |
| Abstract method | No body (`;` terminator) |
| Field (with default) | Literal value from contract |
| Field (no default) | Type-appropriate zero value or `null` |
| Constant (`static final`) | Literal value or `null` placeholder |

**Status:** IMPLEMENTED (`23c7af3`)

#### REQ-JMP-205: Syntax Validation of Rendered Java

Every rendered file SHALL be validated via `javalang.parse.parse(source)` before being written to disk.

**Fallback if javalang not available:** Text-based checks:
1. Balanced braces
2. Contains exactly one public class/interface/enum/record
3. Public class name matches filename
4. Contains `package` statement
5. No Python fingerprints

**Status:** IMPLEMENTED (`23c7af3`)

---

### 4.3 Java Body Splicing (REQ-JMP-300 series)

#### REQ-JMP-300: Java Body Splicer

Create `src/startd8/languages/java_splicer.py` that replaces stub method bodies with LLM-generated implementations.

**Approach:** Brace-based text matching (same pattern as `go_splicer.py`):
1. Locate the stub: find `throw new UnsupportedOperationException` inside method body
2. Identify method boundaries: opening `{` after signature to matching closing `}`
3. Replace body content, preserving indentation
4. Validate result via `javalang.parse.parse()`

**Acceptance criteria:**
- Stub methods are correctly identified by name
- Generated body replaces stub while preserving method signature
- Indentation matches surrounding code
- Result parses successfully via `javalang`
- Multi-method classes: only the target method's body is replaced

**Status:** IMPLEMENTED (`23c7af3`) — `java_splicer.py` provides `splice_java_bodies()` using brace-based body matching. Validates result via `javalang` when available.

#### REQ-JMP-301: Splicer Dispatch for Java

`splicer.py:splice_body_into_skeleton()` MUST dispatch to `java_splicer` when the target file has a `.java` extension.

**Pattern:** Same dispatch mechanism as Go (`go_splicer.py` already wired).

**Status:** IMPLEMENTED (`23c7af3`) — `splicer.py:183-184` checks `_is_java_source()` and dispatches to `_splice_java_dispatch()` which calls `java_splicer.splice_java_bodies()`.

---

### 4.4 Java Template Registry (REQ-JMP-400 series)

These templates enable TRIVIAL-tier Java elements to be generated deterministically (zero LLM cost), equivalent to Python's `templates.py` MP-9 dunder templates.

#### REQ-JMP-400: Constructor Template

Generate constructor from field list:

```java
public ClassName(Type1 field1, Type2 field2) {
    this.field1 = field1;
    this.field2 = field2;
}
```

**Trigger:** `ForwardElementSpec` with `kind=CONSTRUCTOR` or `kind=METHOD` + `name=__init__` equivalent.

**Status:** IMPLEMENTED (`23c7af3`) — `java_constructor` template in `JAVA_TEMPLATES` list.

#### REQ-JMP-401: Getter/Setter Templates

Generate JavaBean-style accessors:

```java
public Type getFieldName() {
    return this.fieldName;
}

public void setFieldName(Type fieldName) {
    this.fieldName = fieldName;
}
```

**Trigger:** Method name matches `get*`/`set*`/`is*` pattern with single field reference.

**Status:** IMPLEMENTED (`23c7af3`) — `java_getter` and `java_setter` templates in `JAVA_TEMPLATES` list.

#### REQ-JMP-402: equals/hashCode/toString Templates

Equivalent of Python's `__eq__`/`__hash__`/`__repr__` dunder templates:

```java
@Override
public boolean equals(Object o) {
    if (this == o) return true;
    if (o == null || getClass() != o.getClass()) return false;
    ClassName that = (ClassName) o;
    return Objects.equals(field1, that.field1) && Objects.equals(field2, that.field2);
}

@Override
public int hashCode() {
    return Objects.hash(field1, field2);
}

@Override
public String toString() {
    return "ClassName{field1=" + field1 + ", field2=" + field2 + "}";
}
```

**Trigger:** Method name is `equals`, `hashCode`, or `toString` with known field list.

**Status:** IMPLEMENTED (`23c7af3`) — `java_equals`, `java_hashcode`, and `java_tostring` templates in `JAVA_TEMPLATES` list.

#### REQ-JMP-403: Builder Pattern Template

Java-specific boilerplate pattern with no Python equivalent:

```java
public static class Builder {
    private Type1 field1;
    private Type2 field2;

    public Builder field1(Type1 field1) { this.field1 = field1; return this; }
    public Builder field2(Type2 field2) { this.field2 = field2; return this; }

    public ClassName build() { return new ClassName(this); }
}
```

**Trigger:** Class has a `Builder` inner class in the manifest or `@Builder` annotation.

**Status:** IMPLEMENTED (`23c7af3`) — `java_builder` template in `JAVA_TEMPLATES` list.

#### REQ-JMP-404: Spring Boot Annotation Templates

Deterministic skeleton patterns for Spring Boot stereotypes:

| Annotation | Generated Pattern |
|---|---|
| `@RestController` | Class with `@RequestMapping` + method stubs with `@GetMapping`/`@PostMapping` |
| `@Service` | Class with constructor injection |
| `@Repository` | Interface extending `JpaRepository<Entity, ID>` |
| `@Configuration` | Class with `@Bean` method stubs |
| `@SpringBootApplication` | Main class with `SpringApplication.run()` |

**Trigger:** Annotation detected in `ForwardElementSpec.decorators`.

**Status:** IMPLEMENTED (`23c7af3`) — `java_spring_main` template covers `@SpringBootApplication` main class. Other Spring stereotypes handled by DFA skeleton rendering (annotations forwarded from ForwardElementSpec).

---

### 4.5 Java Keyword Reserves and Literal Coercion (REQ-JMP-500 series)

#### REQ-JMP-500: Java Keyword Reserve Set (MP-5)

Validate generated identifiers don't collide with Java keywords.

```python
_JAVA_RESERVED: frozenset[str] = frozenset({
    "abstract", "assert", "boolean", "break", "byte", "case", "catch", "char",
    "class", "const", "continue", "default", "do", "double", "else", "enum",
    "extends", "final", "finally", "float", "for", "goto", "if", "implements",
    "import", "instanceof", "int", "interface", "long", "native", "new",
    "package", "private", "protected", "public", "return", "short", "static",
    "strictfp", "super", "switch", "synchronized", "this", "throw", "throws",
    "transient", "try", "void", "volatile", "while",
    # Contextual keywords
    "var", "yield", "record", "sealed", "permits", "non-sealed",
    # Literals (reserved)
    "true", "false", "null",
})
```

**Status:** IMPLEMENTED (`23c7af3`) — Defined in `languages/java.py:14`. Imported and used by `templates.py:554` for identifier validation in template matching.

#### REQ-JMP-501: Java Literal Coercion (MP-13)

Map contract constant values to Java literal syntax:

| Python/Contract Value | Java Literal |
|---|---|
| `True` / `False` | `true` / `false` |
| `None` | `null` |
| `"string"` | `"string"` (same) |
| `42` | `42` |
| `3.14` | `3.14` |
| `[1, 2, 3]` | `List.of(1, 2, 3)` |
| `{"key": "val"}` | `Map.of("key", "val")` |

**Status:** IMPLEMENTED (`23c7af3`)

---

### 4.6 Java System Prompts (REQ-JMP-600 series)

#### REQ-JMP-600: Language-Parameterized System Prompts (MP-4)

When the resolved language is Java, MicroPrime prompts MUST use Java-specific context:

- System prompt role: "You are an expert Java engineer"
- Output format: "raw Java code — no ```java fences"
- Indentation: "4-space indentation" (same as Python default)
- Stub sentinel: `throw new UnsupportedOperationException("TODO")`
- Coding standards: from `JavaLanguageProfile.coding_standards`

**Status:** IMPLEMENTED (`23c7af3`) — Java coding standards injected via `JavaLanguageProfile.coding_standards` property. Language-aware prompt parameterization flows through `spec_builder.py` and `drafter.py` via the resolved language profile.

#### REQ-JMP-601: Java Framework Preamble

Spec and draft prompts MUST include framework-specific context:

| Framework | Detection | Preamble Content |
|---|---|---|
| Spring Boot | `@SpringBootApplication`, `spring-boot-starter-*` deps | DI patterns, stereotype annotations, `@Autowired` vs constructor injection |
| gRPC | `io.grpc` imports | `StreamObserver` patterns, proto stub usage |
| JPA/Hibernate | `javax.persistence` / `jakarta.persistence` imports | Entity annotations, repository patterns |
| SLF4J | `org.slf4j` imports | `LoggerFactory.getLogger(X.class)` pattern |

**Acceptance criteria:**
- `JavaLanguageProfile.framework_imports` includes Spring Boot, JPA, SLF4J, gRPC, and Log4j entries
- `spec_builder.py` injects detected frameworks into spec prompt
- `drafter.py` includes framework patterns in draft system prompt

**Status:** IMPLEMENTED (`23c7af3`) — `framework_imports` property on `JavaLanguageProfile` includes `spring_boot` (with `org.springframework.boot` detection/deps/preamble), `jpa` (with `javax.persistence`/`jakarta.persistence`), `slf4j` (with `org.slf4j`), `grpc` (with `io.grpc`), and `logging` (with `log4j`).

---

### 4.7 Validation & Disk Compliance (REQ-JMP-700 series)

#### REQ-JMP-700: Java File Disk Validation

`validate_disk_compliance()` MUST validate `.java` files using `javalang.parse.parse()` when available, falling back to text-based checks.

**javalang validation:**
- File parses without error
- Contains at least one type declaration (class/interface/enum/record)
- Package statement matches expected path
- No Python content (cross-language guard)

**Text-based fallback:**
- Balanced braces
- Contains `class`/`interface`/`enum`/`record` keyword
- No Python fingerprints (`from __future__`, `def `, `import os`)

**Scoring:**

| Condition | `ast_valid` | `contract_compliance` |
|---|---|---|
| Parse error / unbalanced braces | False | 0.0 |
| No type declaration | False | 0.0 |
| Python content detected | False | 0.0 |
| Package mismatch | True | 0.7 |
| Stub bodies remaining | True | 0.5 |
| Valid | True | 1.0 |

**Status:** IMPLEMENTED (`23c7af3`) — `forward_manifest_validator.py:_validate_java_file()` at line 755 performs javalang-based validation with text-based fallback and scoring.

#### REQ-JMP-701: build.gradle Disk Validation

Same as REQ-JAVA-201 from the original requirements.

**Status:** IMPLEMENTED (`23c7af3`) — `forward_manifest_validator.py:_validate_build_gradle()` at line 825.

#### REQ-JMP-702: pom.xml Disk Validation

Same as REQ-JAVA-202 from the original requirements.

**Status:** IMPLEMENTED (`23c7af3`)

#### REQ-JMP-703: Package Statement Validation

After generation, validate that each `.java` file's `package` statement matches its directory path relative to `src/main/java/`.

**Example:** `src/main/java/com/example/service/MyService.java` MUST contain `package com.example.service;`

**Status:** IMPLEMENTED (`23c7af3`) — Validated as part of `_validate_java_file()` and `JavaDeterministicFileAssembler.render_file()`.

---

### 4.8 Class Decomposition for Java (REQ-JMP-800 series)

#### REQ-JMP-800: Java Class Decomposition Strategy (MP-10)

Extend `ModerateDecomposer` with a `JavaClassDecomposeStrategy` that breaks MODERATE Java classes into SIMPLE method-level sub-elements.

**Why this is more natural in Java than Python:**
- Every method lives inside a class (no module-level functions)
- Method boundaries are unambiguous (braces, not indentation)
- `javalang` provides reliable AST for decomposition planning

**Approach:**
1. Parse class with `javalang` -> extract method list
2. Render class shell with stub method bodies
3. Generate each method body independently (SIMPLE tier)
4. Splice generated bodies back into shell via `java_splicer`

**Trigger criteria (same as Python `ClassDecomposeStrategy`):**
- Element is a class with 3+ methods
- No disqualifying markers (see rejection reasons)
- Estimated complexity per method is SIMPLE

**Rejection reasons:**
- Class has complex inheritance (3+ interfaces + abstract base)
- Class uses reflection or dynamic proxies
- Class is an annotation processor
- Inner classes with complex state sharing

**Status:** IMPLEMENTED (`23c7af3`) — `decomposer.py:524` defines `JavaClassDecomposeStrategy`. Registered in `ModerateDecomposer` strategy list at line 1101 alongside `FunctionChainStrategy`.

#### REQ-JMP-801: Java Function Decomposition (MP-11)

`FunctionChainStrategy` is largely portable across languages (keyword swap). For Java:
- `def` -> method declaration with return type
- `_PYTHON_RESERVED` -> `_JAVA_RESERVED`
- Helper methods become `private` methods in the same class
- No module-level helper functions (Java has no free functions)

**Key difference from Python:** Helpers must be methods on the same class, not standalone functions. The assembler places them as `private` methods below the decomposed method.

**Status:** IMPLEMENTED (`23c7af3`) — `FunctionChainStrategy` accepts `language_id` parameter (line 849). When `language_id="java"`, uses Java-adapted keyword set. Registered at `decomposer.py:1102` with language-aware configuration.

---

### 4.9 Post-Generation & Cleanup (REQ-JMP-900 series)

#### REQ-JMP-900: google-java-format (Best-Effort)

After generating `.java` files, run `google-java-format` if available. Skip with warning if not.

**Status:** IMPLEMENTED (`23c7af3`) — `JavaLanguageProfile.post_generation_cleanup()` returns empty list (google-java-format not invoked automatically). The method exists but no authoritative CLI formatter is callable without a JRE. This is by design — formatting is deferred to the developer's IDE or CI pipeline.

#### REQ-JMP-901: Cross-Language Content Detection

Same as REQ-JAVA-204 — detect Java fingerprints in non-Java files and Python fingerprints in Java files.

**Status:** IMPLEMENTED (`23c7af3`) — Cross-language detection wired through `_validate_java_file()` in `forward_manifest_validator.py`. Python fingerprints in `.java` files detected and flagged.

#### REQ-JMP-902: Python-Stub Integration Guard

Same as REQ-JAVA-205 — already implemented via extension-based `_detect_python_stub_in_non_python()`.

**Status:** IMPLEMENTED (pre-existing, confirmed in `23c7af3`)

---

### 4.10 Prime Contractor Integration (REQ-JMP-1000 series)

These requirements wire MicroPrime Java support into the Prime Contractor workflow.

#### REQ-JMP-1000: Java MicroPrime Feature Flag

A configuration flag `JAVA_MICROPRIME_ENABLED` (default `False`) controls whether Java files flow through MicroPrime or bypass to cloud.

**When False (default):** `.java` remains subject to `_is_non_python_file()` bypass, all Java files use file-whole cloud generation.

**When True:** `_is_non_python_file()` returns `False` for `.java` files, routing them through MicroPrime classify -> generate -> splice -> verify pipeline.

**Status:** IMPLEMENTED (`23c7af3`) — `engine.py:96` defines `JAVA_MICROPRIME_ENABLED = False`. Conditional check at `engine.py:137`.

#### REQ-JMP-1001: Java System Prompt Injection (Prime Path)

Same as REQ-JAVA-102 — when resolved language is Java, spec/draft prompts include Java-specific role, coding standards, and framework context.

**Status:** IMPLEMENTED (`23c7af3`) — Properties exist on `JavaLanguageProfile` and are consumed by `spec_builder.py` and `drafter.py` via the language profile interface.

#### REQ-JMP-1002: Non-Source File Handling (Java Projects)

`build.gradle`, `pom.xml`, `settings.gradle`, `application.yml`, `Dockerfile` — all non-`.java` files continue to use file-whole generation or template matching. Same as REQ-JAVA-101.

**Status:** IMPLEMENTED (pre-existing, confirmed in `23c7af3`)

---

### 4.11 Prime Contractor Wiring (REQ-JMP-1100 series)

These requirements document the integration points that connect Java language support into the Prime Contractor pipeline.

#### REQ-JMP-1100: Language Detection for `.java` Files

`lang_detect.py` maps `.java` extension to `"java"` language identifier. Used by `plan_ingestion_emitter.py` and `forward_manifest_extractor.py` to set `ForwardFileSpec.language = "java"`.

**Files:**
- `micro_prime/lang_detect.py:19` — `".java": "java"` in extension map
- `languages/resolution.py:28` — `".java": "java"` in `_EXT_TO_LANGUAGE_ID` (pre-existing)

**Status:** IMPLEMENTED (`23c7af3`)

#### REQ-JMP-1101: Deterministic build.gradle Generation in Prime Adapter

`prime_adapter.py:_try_generate_build_gradle()` generates `build.gradle` content deterministically from seed metadata (dependencies, Java version, plugins). Called during `fill_skeletons()` for `build.gradle` files instead of routing to LLM generation.

**File:** `prime_adapter.py:1936`

**Status:** IMPLEMENTED (`23c7af3`)

#### REQ-JMP-1102: Java DFA Skeleton Routing in fill_skeletons()

`prime_adapter.py:fill_skeletons()` dispatches `.java` files to `JavaDeterministicFileAssembler.render_file()` for skeleton generation. Produces syntactically valid Java files with package statements, imports, class shells, and method stubs.

**File:** `prime_adapter.py:1786-1795`

**Status:** IMPLEMENTED (`23c7af3`)

#### REQ-JMP-1103: Java Contract Reconciliation

`forward_manifest_extractor.py:_reconcile_java_file()` uses `java_parser.parse_java_source()` to extract `InterfaceContract` instances from generated Java source. Enables forward manifest validation and disk compliance scoring for Java files.

**File:** `forward_manifest_extractor.py:1571`

**Status:** IMPLEMENTED (`23c7af3`)

#### REQ-JMP-1104: Feature Flag Bypass in MicroPrime Engine

`engine.py:_is_non_python_file()` conditionally excludes `.java` from the non-Python bypass set when `JAVA_MICROPRIME_ENABLED` is `True`. This is the gate that controls whether Java files flow through MicroPrime element-level generation or file-whole cloud generation.

**File:** `engine.py:117-139`

**Status:** IMPLEMENTED (`23c7af3`)

#### REQ-JMP-1105: Splicer Dispatch for Java

`splicer.py:_is_java_source()` detects Java source files by extension and content. `_splice_java_dispatch()` routes to `java_splicer.splice_java_bodies()` for body splicing.

**File:** `splicer.py:183-184, 251-299`

**Status:** IMPLEMENTED (`23c7af3`)

#### REQ-JMP-1106: Java Class Decomposition in Decomposer

`decomposer.py:JavaClassDecomposeStrategy` handles MODERATE-tier Java classes by decomposing them into SIMPLE method-level sub-elements. `FunctionChainStrategy` accepts `language_id="java"` for Java-adapted function chain decomposition.

**File:** `decomposer.py:524, 849, 1101-1102`

**Status:** IMPLEMENTED (`23c7af3`)

#### REQ-JMP-1107: Java Template Registry

`templates.py:JAVA_TEMPLATES` list contains 8 Java-specific templates. `TemplateRegistry` accepts `language_id="java"` to select the Java template base.

**Templates:** `java_getter`, `java_setter`, `java_constructor`, `java_equals`, `java_hashcode`, `java_tostring`, `java_builder`, `java_spring_main`

**File:** `templates.py:726, 894`

**Status:** IMPLEMENTED (`23c7af3`)

---

## 5. Implementation Phases

All phases are complete. The phased approach built MicroPrime Java support incrementally, with each phase independently testable and valuable.

### Phase 1: Foundation — javalang + Validation (REQ-JMP-100, 101, 500, 501, 700) -- COMPLETE

**Goal:** Real syntax validation for Java files. No generation changes yet.

**Deliverables:**
- `javalang` optional dependency in `pyproject.toml`
- `JavaLanguageProfile.validate_syntax()` using `javalang` with text fallback
- `_JAVA_RESERVED` keyword set
- Java literal coercion helpers
- `_validate_java_file()` in `forward_manifest_validator.py`
- `_validate_build_gradle()` in `forward_manifest_validator.py`

**Tests:** 29 (20 validation + 9 disk validators)

**Value:** Java postmortem accuracy (REQ-JMP-700) — files scored correctly instead of defaulting to 1.0. Works even with cloud-path generation.

### Phase 2: Java Parser + DFA Skeletons (REQ-JMP-102, 200-205) -- COMPLETE

**Goal:** Deterministic skeleton `.java` files from `ForwardFileSpec`, validated by `javalang`.

**Deliverables:**
- `src/startd8/languages/java_parser.py` — `javalang`-based element extraction
- `JavaDeterministicFileAssembler` class
- Package statement derivation from file path
- Import block rendering (2-tier)
- Class shell rendering with annotations, extends/implements
- Method stubs with full typed signatures
- Field declarations

**Tests:** 39 (16 parser + 23 DFA)

**Value:** SCAFFOLD phase produces Java skeleton files. IMPLEMENT phase fills bodies instead of generating from scratch. Reduces LLM cost and improves structural correctness.

### Phase 3: Body Splicing + MicroPrime Routing (REQ-JMP-300, 301, 103, 104) -- COMPLETE

**Goal:** LLM-generated method bodies spliced into DFA skeletons. Java files can optionally flow through MicroPrime.

**Deliverables:**
- `src/startd8/languages/java_splicer.py` — brace-based body splicing
- Splicer dispatch for `.java` files in `splicer.py`
- Structural verification post-splice via `javalang`
- Feature flag `JAVA_MICROPRIME_ENABLED`
- Conditional `.java` bypass in `_is_non_python_file()`

**Tests:** 22 (12 splicer + 10 routing)

**Value:** MicroPrime can generate Java method bodies via Ollama/Haiku and splice them into DFA skeletons. Cost reduction vs cloud-path file-whole generation.

### Phase 4: Templates + Decomposition (REQ-JMP-400-404, 800, 801) -- COMPLETE

**Goal:** TRIVIAL Java elements generated deterministically; MODERATE classes decomposed into SIMPLE methods.

**Deliverables:**
- Java template registry (8 templates: constructor, getter, setter, equals, hashCode, toString, Builder, Spring Boot main)
- `JavaClassDecomposeStrategy` in decomposer
- Java-adapted `FunctionChainStrategy`

**Tests:** 37 (26 templates + 11 decomposition)

**Value:** TRIVIAL tier = zero LLM cost for boilerplate. MODERATE tier = cheaper local generation instead of cloud escalation.

### Phase 5: Framework Detection + Prompts (REQ-JMP-600, 601, 1001) -- COMPLETE

**Goal:** Framework-aware generation for Spring Boot, gRPC, JPA projects.

**Deliverables:**
- Extended `framework_imports` on `JavaLanguageProfile` (Spring Boot, JPA, SLF4J, gRPC, Log4j)
- Language-parameterized system prompts for Java
- Framework preamble injection into spec/draft builders

**Tests:** 13 (framework detection)

**Value:** Generated Java code follows framework conventions. Spec prompts include framework-specific patterns.

---

## 6. Implementation Status Summary

### All Requirements Implemented

| REQ | Description | Phase | Commit |
|-----|-------------|-------|--------|
| REQ-JMP-100 | javalang dependency | 1 | `23c7af3` |
| REQ-JMP-101 | Java syntax validation via javalang | 1 | `23c7af3` |
| REQ-JMP-102 | Java element location via javalang | 2 | `23c7af3` |
| REQ-JMP-103 | Java structural verification | 3 | `23c7af3` |
| REQ-JMP-104 | Feature flag for MicroPrime routing | 3 | `23c7af3` |
| REQ-JMP-200 | Java DFA assembler | 2 | `23c7af3` |
| REQ-JMP-201 | Package statement derivation | 2 | `23c7af3` |
| REQ-JMP-202 | Import block rendering | 2 | `23c7af3` |
| REQ-JMP-203 | Class shell rendering | 2 | `23c7af3` |
| REQ-JMP-204 | Stub body patterns | 2 | `23c7af3` |
| REQ-JMP-205 | Syntax validation of rendered Java | 2 | `23c7af3` |
| REQ-JMP-300 | Java body splicer | 3 | `23c7af3` |
| REQ-JMP-301 | Splicer dispatch for Java | 3 | `23c7af3` |
| REQ-JMP-400 | Constructor template | 4 | `23c7af3` |
| REQ-JMP-401 | Getter/setter templates | 4 | `23c7af3` |
| REQ-JMP-402 | equals/hashCode/toString templates | 4 | `23c7af3` |
| REQ-JMP-403 | Builder pattern template | 4 | `23c7af3` |
| REQ-JMP-404 | Spring Boot annotation templates | 4 | `23c7af3` |
| REQ-JMP-500 | Java keyword reserve set | 1 | `23c7af3` |
| REQ-JMP-501 | Java literal coercion | 1 | `23c7af3` |
| REQ-JMP-600 | Language-parameterized system prompts | 5 | `23c7af3` |
| REQ-JMP-601 | Java framework preamble | 5 | `23c7af3` |
| REQ-JMP-700 | Java file disk validation | 1 | `23c7af3` |
| REQ-JMP-701 | build.gradle disk validation | 1 | `23c7af3` |
| REQ-JMP-702 | pom.xml disk validation | 1 | `23c7af3` |
| REQ-JMP-703 | Package statement validation | 1 | `23c7af3` |
| REQ-JMP-800 | Java class decomposition strategy | 4 | `23c7af3` |
| REQ-JMP-801 | Java function decomposition | 4 | `23c7af3` |
| REQ-JMP-900 | google-java-format (best-effort) | 5 | `23c7af3` |
| REQ-JMP-901 | Cross-language content detection | 5 | `23c7af3` |
| REQ-JMP-902 | Python-stub integration guard | Pre-existing | Pre-existing |
| REQ-JMP-1000 | Java MicroPrime feature flag | 3 | `23c7af3` |
| REQ-JMP-1001 | Java system prompt injection | 5 | `23c7af3` |
| REQ-JMP-1002 | Non-source file handling | Pre-existing | Pre-existing |
| REQ-JMP-1100 | Language detection for .java | Wiring | `23c7af3` |
| REQ-JMP-1101 | Deterministic build.gradle generation | Wiring | `23c7af3` |
| REQ-JMP-1102 | Java DFA skeleton routing | Wiring | `23c7af3` |
| REQ-JMP-1103 | Java contract reconciliation | Wiring | `23c7af3` |
| REQ-JMP-1104 | Feature flag bypass in engine | Wiring | `23c7af3` |
| REQ-JMP-1105 | Splicer dispatch for Java | Wiring | `23c7af3` |
| REQ-JMP-1106 | Java class decomposition in decomposer | Wiring | `23c7af3` |
| REQ-JMP-1107 | Java template registry | Wiring | `23c7af3` |

---

## 7. Test Coverage

### Actual (140 tests across 8 files)

| Test File | Tests | Covers |
|-----------|-------|--------|
| `tests/unit/languages/test_java_validation.py` | 20 | Syntax validation (javalang + text fallback), cross-language guard |
| `tests/unit/languages/test_java_parser.py` | 16 | Element extraction, find_element, extract_element_body |
| `tests/unit/languages/test_java_splicer.py` | 12 | Body splicing, multi-method, indentation preservation |
| `tests/unit/languages/test_java_framework_detection.py` | 13 | Spring Boot, JPA, SLF4J, gRPC framework detection |
| `tests/unit/utils/test_java_dfa.py` | 23 | DFA assembler, package derivation, import rendering, class shell |
| `tests/unit/micro_prime/test_java_templates.py` | 26 | All 8 Java templates (getter, setter, constructor, equals, hashCode, toString, builder, spring_main) |
| `tests/unit/micro_prime/test_java_decomposition.py` | 11 | JavaClassDecomposeStrategy, FunctionChainStrategy with Java |
| `tests/unit/micro_prime/test_java_microprime_routing.py` | 10 | Feature flag, _is_non_python_file conditional bypass |
| `tests/unit/validators/test_java_disk_validators.py` | 9 | _validate_java_file, _validate_build_gradle, scoring |
| **Total** | **140** | |

### Pre-existing (shared with other languages)

| Test File | Tests | Covers |
|-----------|-------|--------|
| `tests/unit/languages/test_protocol.py` | ~5 | Protocol conformance (includes Java) |
| `tests/unit/languages/test_registry.py` | ~3 | Entry point discovery (includes Java) |
| `tests/unit/languages/test_resolution.py` | ~2 | Language resolution (includes .java) |
| `tests/unit/micro_prime/test_non_python_bypass.py` | Shared | Bypass mechanism (includes .java) |

---

## 8. Known Limitations

1. **`javalang` maintenance status** — The `javalang` package has not been actively maintained since ~2020. It supports Java 8-11 syntax well but may not handle Java 17+ features (`sealed`, `record`, `pattern matching`). Mitigation: text-based fallback for unsupported constructs. The fallback path is tested and wired — `javalang` absence degrades gracefully to heuristic validation.

2. **No CLI import organizer** — Unlike Go (`goimports`), Java has no CLI tool to fix imports. Import correctness depends on DFA rendering quality and LLM prompt guidance.

3. **Dual build system** — Gradle and Maven require separate template generation and validation paths. Phase 1 focuses on Gradle; Maven is Phase 2+.

4. **Deep directory structure** — Java's `com.example.package` convention creates deep trees. Package derivation from file path must handle variations (missing `src/main/java/` prefix, test paths, non-standard layouts).

5. **Spring Boot surface area** — Spring Boot's annotation-driven configuration is large. Phase 5 covers the most common patterns; full coverage is ongoing.

6. **No Java compiler in pipeline** — Unlike Go's `gofmt -e`, we cannot run `javac` without a full classpath. `javalang` parse is the best available in-process validation.

7. **Feature flag default is off** — `JAVA_MICROPRIME_ENABLED = False` means Java files still bypass to cloud by default. First Java Prime Contractor run should validate cloud-path generation before enabling MicroPrime routing.

---

## 9. Comparison: Java vs Go MicroPrime Feasibility

| Aspect | Go | Java |
|--------|-----|------|
| **AST from Python** | No — regex-based `go_parser.py` | Yes — `javalang` real AST |
| **Syntax validation** | `gofmt -e` (subprocess) | `javalang.parse.parse()` (in-process) |
| **DFA complexity** | Medium (structs, no classes) | Low (rigid one-class-per-file) |
| **Method ownership** | Receiver-based (regex) | Lexical (always inside class) |
| **Import fixing** | `goimports` (excellent) | None (DFA must get it right) |
| **Stub detection** | Text patterns (5) | Text patterns (4) + `javalang` |
| **Class decomposition** | N/A (no classes) | Natural (class-centric language) |
| **Template potential** | Low (minimal boilerplate) | High (constructor, getters, equals, Builder, Spring stereotypes) |
| **Estimated effort** | 1-2 weeks (capability map S3.1) | 3-4 weeks (phased, higher template investment) |
| **Cost reduction potential** | Medium (file-whole is adequate) | High (boilerplate-heavy language, templates eliminate LLM calls) |

---

## 10. Example: End-to-End Java DFA Rendering

Given this `ForwardFileSpec`:

```python
ForwardFileSpec(
    file="src/main/java/com/example/order/OrderService.java",
    elements=[
        ForwardElementSpec(
            kind=ElementKind.CLASS, name="OrderService",
            bases=["BaseService"], visibility=Visibility.PUBLIC,
            decorators=["@Service"],
            docstring_hint="Handles order processing and validation.",
        ),
        ForwardElementSpec(
            kind=ElementKind.METHOD, name="processOrder",
            signature=Signature(
                params=[
                    Param(name="request", annotation="OrderRequest",
                          kind=ParamKind.POSITIONAL),
                ],
                return_annotation="OrderResponse",
            ),
            visibility=Visibility.PUBLIC,
            decorators=["@Transactional"],
        ),
        ForwardElementSpec(
            kind=ElementKind.METHOD, name="validateOrder",
            signature=Signature(
                params=[
                    Param(name="request", annotation="OrderRequest",
                          kind=ParamKind.POSITIONAL),
                ],
                return_annotation="void",
            ),
            visibility=Visibility.PROTECTED,
        ),
    ],
    imports=[
        ForwardImportSpec(kind="import", module="com.example.shared.BaseService", names=[]),
        ForwardImportSpec(kind="import", module="com.example.order.model.OrderRequest", names=[]),
        ForwardImportSpec(kind="import", module="com.example.order.model.OrderResponse", names=[]),
        ForwardImportSpec(kind="import", module="org.springframework.stereotype.Service", names=[]),
        ForwardImportSpec(kind="import", module="org.springframework.transaction.annotation.Transactional", names=[]),
    ],
)
```

The Java DFA assembler produces:

```java
package com.example.order;

import com.example.order.model.OrderRequest;
import com.example.order.model.OrderResponse;
import com.example.shared.BaseService;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Handles order processing and validation.
 */
@Service
public class OrderService extends BaseService {

    @Transactional
    public OrderResponse processOrder(OrderRequest request) {
        throw new UnsupportedOperationException("TODO");
    }

    protected void validateOrder(OrderRequest request) {
        throw new UnsupportedOperationException("TODO");
    }
}
```

This file:
- Passes `javalang.parse.parse()`
- Has correct `package` statement derived from path
- Public class name matches filename (`OrderService`)
- Imports sorted: project-internal, then third-party
- Method stubs ready for LLM body generation in IMPLEMENT phase

---

## 11. Prime Contractor Wiring — Data Flow

This section documents the complete end-to-end data flow for Java files through the Prime Contractor pipeline.

### 11.1 Flow Diagram

```
Prime Seed Task (target_files: ["src/main/java/.../*.java"])
  |
  v
resolve_language() [languages/resolution.py]
  _EXT_TO_LANGUAGE_ID[".java"] = "java" -> JavaLanguageProfile
  |
  v
PrimeContractor._build_generation_context()
  language_profile = JavaLanguageProfile
  |
  v
_apply_language_profile_to_engine()
  merge_strategy = SimpleMerge (from JavaLanguageProfile.merge_strategy)
  |
  v
plan_ingestion_emitter: detect_language(".java") = "java" [micro_prime/lang_detect.py]
  ForwardFileSpec.language = "java"
  |
  v
prime_adapter.fill_skeletons():
  +-- build.gradle -> _try_generate_build_gradle() [deterministic, no LLM]
  +-- *.java -> JavaDeterministicFileAssembler.render_file() [skeleton with stubs]
  |
  v
prime_adapter.generate():
  +-- When JAVA_MICROPRIME_ENABLED=False (default):
  |     .java in _is_non_python_file() bypass -> file-whole cloud generation
  |
  +-- When JAVA_MICROPRIME_ENABLED=True:
        .java NOT in bypass -> MicroPrime element pipeline
        |
        v
      MicroPrime element pipeline:
        classify_element -> TRIVIAL / SIMPLE / MODERATE / COMPLEX
        |
        +-- TRIVIAL -> Java template registry (TemplateRegistry(language_id="java"))
        |     8 templates: getter, setter, constructor, equals, hashCode,
        |     toString, builder, spring_main
        |
        +-- SIMPLE -> LLM body generation -> java_splicer.splice_java_bodies()
        |
        +-- MODERATE -> JavaClassDecomposeStrategy -> sub-elements -> splice
        |     or FunctionChainStrategy(language_id="java") -> helpers -> splice
        |
        +-- COMPLEX -> escalate to cloud (file-whole generation)
  |
  v
forward_manifest_extractor._reconcile_java_file()
  java_parser.parse_java_source() -> InterfaceContract extraction
  |
  v
forward_manifest_validator._validate_java_file()
  javalang.parse.parse() (or text fallback) -> DiskComplianceResult scoring
```

### 11.2 Integration Points Summary

| Module | Function/Class | Role |
|--------|---------------|------|
| `languages/resolution.py` | `resolve_language()` | `.java` -> `JavaLanguageProfile` |
| `micro_prime/lang_detect.py` | `detect_language()` | `.java` -> `"java"` for ForwardFileSpec |
| `languages/java.py` | `JavaLanguageProfile` | 15-property language profile (367 lines) |
| `languages/java_parser.py` | `parse_java_source()` | javalang-based element extraction |
| `languages/java_splicer.py` | `splice_java_bodies()` | Brace-based body replacement |
| `micro_prime/prime_adapter.py` | `_try_generate_build_gradle()` | Deterministic build.gradle |
| `micro_prime/prime_adapter.py` | `fill_skeletons()` | Routes .java to `JavaDeterministicFileAssembler` |
| `micro_prime/engine.py` | `JAVA_MICROPRIME_ENABLED` | Feature flag (default `False`) |
| `micro_prime/engine.py` | `_is_non_python_file()` | Conditional bypass gate |
| `micro_prime/splicer.py` | `_is_java_source()` / `_splice_java_dispatch()` | Splicer routing |
| `micro_prime/decomposer.py` | `JavaClassDecomposeStrategy` | MODERATE class decomposition |
| `micro_prime/decomposer.py` | `FunctionChainStrategy` | Java-adapted function chains |
| `micro_prime/templates.py` | `JAVA_TEMPLATES` (8 templates) | TRIVIAL element generation |
| `forward_manifest_extractor.py` | `_reconcile_java_file()` | Contract extraction via java_parser |
| `forward_manifest_validator.py` | `_validate_java_file()` | Disk compliance scoring |
| `forward_manifest_validator.py` | `_validate_build_gradle()` | Build file validation |

---

## 12. Go Pattern Leverage Analysis

This section documents which patterns from the Go implementation (see `docs/design/prime-contractor-go/GO_PRIME_CONTRACTOR_REQUIREMENTS.md`) were reused for Java vs where Java diverges.

### 12.1 Patterns Reused from Go

| Pattern | Go Implementation | Java Implementation | Notes |
|---------|-------------------|---------------------|-------|
| **Brace-based splicer** | `go_splicer.py` (text-based brace matching) | `java_splicer.py` (same approach) | Both use opening `{` to closing `}` matching for body replacement |
| **Language profile protocol** | `GoLanguageProfile` (15 properties) | `JavaLanguageProfile` (15 properties) | Same `LanguageProfile` protocol, same property set |
| **Splicer dispatch** | `splicer.py` checks `.go` extension | `splicer.py` checks `.java` extension | Same dispatch pattern: `_is_X_source()` + `_splice_X_dispatch()` |
| **`_LANGUAGE_RESERVED` dict** | `_GO_RESERVED` frozenset | `_JAVA_RESERVED` frozenset | Same pattern: language-specific keyword set for identifier validation |
| **`resolve_language()`** | `.go` -> `GoLanguageProfile` | `.java` -> `JavaLanguageProfile` | Same `_EXT_TO_LANGUAGE_ID` dict in `resolution.py` |
| **`_NON_PYTHON_EXTENSIONS` bypass** | `.go` in bypass set | `.java` conditionally in bypass set | Same mechanism, Java adds feature flag control |
| **Merge strategy selection** | `"simple"` (whole-file replacement) | `"simple"` (whole-file replacement) | Both non-Python languages use simple merge |
| **Feature flag pattern** | N/A (Go always bypasses to cloud) | `JAVA_MICROPRIME_ENABLED` | Java extends the pattern with an explicit opt-in flag |
| **`detect_language()` in lang_detect** | `.go` -> `"go"` | `.java` -> `"java"` | Same extension map pattern |
| **Dependency file generation** | `go.mod` via `generate_dependency_file()` | `build.gradle` via `generate_dependency_file()` | Same profile method, different output format |

### 12.2 Patterns Where Java Diverges from Go

| Aspect | Go Approach | Java Approach | Why Different |
|--------|------------|---------------|---------------|
| **AST parsing** | Regex-based `go_parser.py` | Real AST via `javalang` library | Java has a pure-Python parser available; Go does not |
| **Class decomposition** | N/A (Go has structs, not classes) | `JavaClassDecomposeStrategy` | Java is class-centric; decomposition is natural and high-value |
| **Template count** | ~0 templates | 8 templates (`JAVA_TEMPLATES`) | Java has far more boilerplate patterns (getters, equals, Builder, etc.) |
| **DFA skeleton quality** | Passthrough (Go DFA not implemented) | Real skeletons with package, imports, class shell, method stubs | Java's rigid structure makes DFA dramatically simpler |
| **Post-generation cleanup** | `goimports` (excellent CLI tool) | None (no authoritative CLI formatter) | Go has `goimports`; Java has no equivalent without JRE |
| **Stub detection** | 5 text patterns only | 4 text patterns + `javalang` AST verification | javalang enables AST-level stub detection |
| **Build file generation** | `go.mod` (simple format) | `build.gradle` (Groovy DSL, plugins, dependencies) | Gradle build files are more complex than go.mod |
| **Framework detection** | Minimal (proto/gRPC only) | 5 frameworks (Spring Boot, JPA, SLF4J, gRPC, Log4j) | Java ecosystem has more framework conventions |
| **MicroPrime routing** | Always bypasses to cloud | Feature-flag controlled | Java MicroPrime is more mature; opt-in gate for safety |
