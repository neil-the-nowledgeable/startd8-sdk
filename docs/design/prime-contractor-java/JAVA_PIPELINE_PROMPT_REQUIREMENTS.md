# Java Pipeline Prompt & Evaluation Requirements

> **Version:** 1.0.0
> **Status:** DRAFT
> **Date:** 2026-03-23
> **Language:** Java (.java, build.gradle, settings.gradle, gradlew)
> **Inherits from:** [PIPELINE_EVALUATION_PROMPT_REQUIREMENTS.md](../prime/PIPELINE_EVALUATION_PROMPT_REQUIREMENTS.md)
> **Kaizen requirements:** [KAIZEN_JAVA_REQUIREMENTS.md](KAIZEN_JAVA_REQUIREMENTS.md)
> **MicroPrime:** [JAVA_MICROPRIME_ELEMENT_REQUIREMENTS.md](JAVA_MICROPRIME_ELEMENT_REQUIREMENTS.md)

---

## 1. Java-Specific Grade Thresholds

### Per-Feature

| Grade | DQS | Semantic Errors | Boilerplate Inflation | System.out.println |
|-------|-----|-----------------|----------------------|--------------------|
| **A** | >= 0.95 | 0 errors | LOC within 1.5x of spec estimate | 0 |
| **B** | 0.85-0.94 | 0 errors, <= 3 warnings | LOC within 2.0x of spec | <= 2 |
| **C** | 0.70-0.84 | <= 3 errors | LOC within 3.0x of spec | <= 5 |
| **D** | 0.50-0.69 | 4+ errors | LOC > 3.0x of spec | any |
| **F** | < 0.50 | any | any | any |

**Boilerplate inflation** = generated LOC / estimated LOC from seed. Java's verbosity (getters/setters, checked exceptions, builder patterns) legitimately inflates LOC, so thresholds are more generous than Python's.

### Per-Domain

Inherits from parent doc. Java-specific notes:
- **Kaizen aggregate >= 0.93** is realistic (Java's boilerplate lowers DQS slightly vs Python)
- **MicroPrime** evaluation is new — Java just became eligible. Expect initial runs to show `complex: N` (all COMPLEX) until templates and skeleton assembly are wired
- **Query Prime**: Java has JDBC PreparedStatement and JPA/Criteria API patterns. The `java_sql_parameterize` repair step handles JDBC; JPA patterns are advisory-only

---

## 2. Java-Specific Evaluation Rubric

When evaluating a Java run, check these domain-specific items:

### Kaizen Section

| Check | Grade Impact | Details |
|-------|-------------|---------|
| Package declaration matches directory | error if mismatched | `package_filepath_mismatch` semantic check |
| Access modifiers present on all public API | warning if missing | Java convention: explicit `public`/`private` on methods |
| try-with-resources for AutoCloseable | warning if missing | `empty_catch_block` → C grade cap |
| No wildcard imports (`import java.util.*`) | warning | `wildcard_import` semantic check |
| SLF4J logging (not System.out.println) | warning | `system_out_in_service` semantic check |
| Gradle build.gradle well-formed | error if broken | `csharp_structure` equivalent for Java |

### MicroPrime Section

| Check | Expected State | Details |
|-------|---------------|---------|
| Tier distribution | Mix of SIMPLE + COMPLEX | Interfaces, POJOs → SIMPLE; services, controllers → COMPLEX |
| Parser element extraction | Classes, methods, constructors, interfaces | `java_parser.py` regex-based |
| Splicer effectiveness | Body replacement for stub methods | `java_splicer.py` brace-matching |
| Template matching | gRPC service methods, CRUD operations | When templates registered |

### Query Prime Section

| Check | Details |
|-------|---------|
| JDBC PreparedStatement | ALL SQL uses `?` placeholders, never string concatenation |
| JPA Criteria API | Type-safe queries over string-based JPQL where possible |
| Spanner Java client | `Statement.newBuilder()` with `bind()` parameters |
| Connection pool configuration | HikariCP or equivalent with reasonable pool size |
| Credential handling | No hardcoded database passwords; use environment variables or Secret Manager |

---

## 3. Key Files to Spot-Check (Java)

When evaluating generated Java source:

| File Pattern | What to Check |
|-------------|---------------|
| `*Service.java` / `*ServiceImpl.java` | gRPC service implementation, logging, error handling |
| `build.gradle` | Dependencies correct, no version conflicts, plugins applied |
| `Dockerfile` | Multi-stage, JDK build → JRE runtime, version consistency (DV-BP-012) |
| `*Test.java` | JUnit 5 annotations, meaningful assertions, mock setup |
| `*Repository.java` | Data access patterns, parameterized queries |
| `application.properties` / `log4j2.xml` | Configuration correctness, no hardcoded secrets |

---

## 4. Java Run Evaluation Condensed Checklist

```
## Quick Rubric — Java
- [ ] All features PASS verdict?
- [ ] Aggregate DQS >= 0.93?
- [ ] 0 semantic errors (warnings OK)?
- [ ] 0 SQL injection findings (JDBC PreparedStatement enforced)?
- [ ] 0 System.out.println in non-main classes?
- [ ] No wildcard imports?
- [ ] Package declarations match directory structure?
- [ ] Explicit access modifiers on public API?
- [ ] try-with-resources for AutoCloseable resources?
- [ ] Dockerfile: JDK build → JRE runtime, same major version?
- [ ] build.gradle: dependencies resolve, plugins correct?
- [ ] No cross-language contamination (Python artifacts in .java)?
- [ ] MicroPrime: tier distribution shows mix (not all COMPLEX)?
- [ ] Cost per feature <= $0.25 (Java is verbose)?
- [ ] Boilerplate within 2x of spec estimate?
```

---

## 5. Comparison with C# Evaluation

| Dimension | C# | Java | Key Difference |
|-----------|----|----|----------------|
| Build validation | `dotnet build` | Gradle `./gradlew compileJava` | Java needs full project; C# can validate single .csproj |
| SQL parameterization | Npgsql + Spanner ADO.NET | JDBC PreparedStatement + JPA | Different safe patterns |
| Logging anti-pattern | `Console.WriteLine` | `System.out.println` | Same concept, different API |
| Import ordering | `using` sorted | `import` with package grouping | Java has stronger convention (static imports last) |
| Boilerplate risk | Low (records, properties) | **High** (getters/setters, builders) | Java needs higher LOC thresholds |
| Runtime image | `runtime-deps:chiseled` (distroless) | `eclipse-temurin:JRE-alpine` | Java lacks distroless equivalent |
| MicroPrime parser | tree-sitter (100% grammar) | regex (~80% coverage) | Java parser less accurate for generics |
