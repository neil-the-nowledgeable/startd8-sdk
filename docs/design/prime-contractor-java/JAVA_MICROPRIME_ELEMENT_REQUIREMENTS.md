# Java MicroPrime Element-Level Generation Requirements

> **Version:** 1.0.0
> **Status:** DRAFT
> **Date:** 2026-03-23
> **Inherits from:** [MICROPRIME_POLYGLOT_REQUIREMENTS.md](../prime/MICROPRIME_POLYGLOT_REQUIREMENTS.md)
> **Language Profile:** `JavaLanguageProfile` (`src/startd8/languages/java.py`)
> **Parser:** `java_parser.py` (regex-based) — IMPLEMENTED (12.4KB)
> **Splicer:** `java_splicer.py` (text brace-matching) — IMPLEMENTED (9.7KB)
> **Scope:** Wire existing Java parser/splicer into MicroPrime for element-level code generation

---

## 1. Current State

### 1.1 What Exists

| Component | File | Status | Capability |
|-----------|------|--------|-----------|
| Language profile | `languages/java.py` | IMPLEMENTED | All protocol properties (extensions, commands, docker images, stub patterns) |
| Regex parser | `languages/java_parser.py` | IMPLEMENTED | Extracts classes, methods, constructors, interfaces, enums, annotations; ~80% coverage |
| Text splicer | `languages/java_splicer.py` | IMPLEMENTED | Brace-matching body replacement with stub detection; handles instance/static methods, constructors, generics |
| Semantic checks | `validators/java_semantic_checks.py` | IMPLEMENTED | 9 check functions, 10 category strings |
| Repair steps | `repair/steps/java_*.py` | IMPLEMENTED | 3 steps: syntax validate, import sort, SQL parameterize |
| Complexity routing | `prime_contractor.py:_route_complexity` | ENABLED | Java tasks classified by actual complexity signals (no longer forced COMPLEX) |

### 1.2 What's Missing for Full MicroPrime

| Gap | Priority | Description |
|-----|----------|-------------|
| **Skeleton assembly** | P1 | No `JavaDeterministicFileAssembler` — skeleton must be produced by LLM or from forward manifest |
| **Template registration** | P1 | No `_LANGUAGE_TEMPLATES["java"]` entries — all Java elements go through LLM generation |
| **Element body extraction dispatch** | P1 | `_extract_element_body()` doesn't dispatch to `java_parser.py` for `.java` files |
| **Compilation validation** | P2 | Gradle `compileJava` requires full project context — too heavyweight for per-element validation |

---

## 2. Java Parser Capabilities

`java_parser.py:parse_java_source()` extracts:

| Element Kind | Example | Fields |
|-------------|---------|--------|
| `class` | `public class CartService` | name, modifiers, extends, implements, line |
| `interface` | `public interface ICartStore` | name, modifiers, extends, line |
| `enum` | `public enum Status` | name, modifiers, line |
| `method` | `public void addItem(...)` | name, return_type, modifiers, parameters, parent_class, line |
| `constructor` | `public CartService(...)` | name, modifiers, parameters, parent_class, line |
| `annotation` | `@Override`, `@Autowired` | name, line |
| `static_method` | `public static void main(...)` | name, return_type, modifiers, parameters, line |

**Known limitations:**
- Generic type parameters with nested brackets (`Map<String, List<Pair<K, V>>>`) may confuse the regex
- Anonymous inner classes are not extracted as named elements
- Lambda expressions assigned to fields are not detected
- Multi-line annotations with parameters may not parse

### Import/Package Extraction

| Function | What It Extracts |
|----------|-----------------|
| `parse_java_imports()` | All `import` statements (static and regular) |
| `parse_java_package()` | Package declaration |

---

## 3. Java Splicer Capabilities

`java_splicer.py:splice_java_bodies()` handles:

| Body Form | Example | Detection |
|-----------|---------|-----------|
| Block body `{ ... }` | `public void handle() { throw new UnsupportedOperationException(); }` | Standard brace depth |
| Single-line body | `public int getPort() { return port; }` | Same brace matching |
| Constructor | `public Service(int port) { this.port = port; }` | `_CONSTRUCTOR_DECL_RE` pattern |
| Static method | `public static void main(String[] args) { ... }` | `_METHOD_DECL_RE` with `static` modifier |
| Generic return type | `public List<String> getNames() { ... }` | `[\w.<>,\[\]?]+` return type pattern |

**Stub detection patterns:**
- `throw new UnsupportedOperationException(`
- `throw new RuntimeException("not implemented"`
- `throw new RuntimeException("TODO"`
- `// TODO` comment in body

**Splice result:** `JavaSpliceResult(code, methods_spliced, methods_skipped, warnings)`

---

## 4. Skeleton Assembly Requirements

### 4.1 Package Declaration

Derived from target file's directory path:
```
src/adservice/src/main/java/hipstershop/AdService.java
→ package hipstershop;
```

Convention: last directory segment before the filename IS the package. For deeper paths (`com/example/service/`), concatenate with dots: `package com.example.service;`

### 4.2 Import Block

Sources (in priority order):
1. `prescribed_imports` from forward manifest (most authoritative)
2. `dependency_imports` from `_collect_dependency_imports()` (Strategy 1-3)
3. Language profile defaults (gRPC, OTel, JUnit based on task type)

Import ordering convention:
```java
// 1. Java stdlib
import java.util.*;
import java.io.*;

// 2. Third-party
import com.google.protobuf.*;
import io.grpc.*;

// 3. Project-local
import hipstershop.proto.*;

// 4. Static imports (last)
import static org.junit.jupiter.api.Assertions.*;
```

### 4.3 Element Stubs

```java
public class AdService extends AdServiceGrpc.AdServiceImplBase {

    public AdService() {
        throw new UnsupportedOperationException("not implemented");
    }

    @Override
    public void getAds(AdRequest request, StreamObserver<AdResponse> responseObserver) {
        throw new UnsupportedOperationException("not implemented");
    }
}
```

---

## 5. Template Opportunities

| Pattern | Template | Frequency | Cost Savings |
|---------|----------|-----------|-------------|
| gRPC service method (unary) | Request → process → responseObserver.onNext/onCompleted | High (adservice) | ~$0.10/element |
| gRPC service method (streaming) | Request stream → collect → respond | Medium | ~$0.10/element |
| JUnit 5 test method | `@Test void test_...() { arrange/act/assert }` | High | ~$0.05/element |
| Main method (gRPC server) | Server.start() + shutdown hook | Low (1/service) | ~$0.10 |
| Build.gradle dependencies | Plugin + dependency block | Low (1/project) | $0.00 (deterministic) |
| Dockerfile (Gradle) | Multi-stage JDK→JRE | Low (1/service) | $0.00 (deterministic) |

---

## 6. Gradle Integration

### Compilation Validation (P2 — optional)

When `./gradlew` is available on PATH:
```bash
./gradlew compileJava -x test --no-daemon
```

**Constraints:**
- Requires full project structure (build.gradle, settings.gradle, src/ tree)
- Requires dependency download (network access)
- Too slow for per-element validation (~5-15s per invocation)
- Appropriate for post-assembly whole-file validation only

### Dependency File Generation

`JavaLanguageProfile.generate_dependency_file()` produces `build.gradle` with:
- Gradle Application plugin
- Dependencies from seed's `runtime_dependencies`
- Java version from seed's `java_version` or default (21)

---

## 7. Implementation Order

| Phase | What | Priority | Depends On |
|-------|------|----------|------------|
| 1 | Element body extraction dispatch (`.java` → `java_parser`) | P1 | Parser (done) |
| 2 | Skeleton assembly (`JavaDeterministicFileAssembler`) | P1 | Package/import derivation |
| 3 | Template registration (gRPC methods, test methods) | P1 | Template registry |
| 4 | Integration test with real Java run | P1 | Phases 1-3 |
| 5 | Gradle compilation validation (optional) | P2 | Full project context |
