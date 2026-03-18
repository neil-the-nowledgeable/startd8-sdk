# Multi-Language Capability Map

**Purpose:** Document the Prime Contractor pipeline's capabilities in language-agnostic terms, then map each to Go, Node.js, and Java — identifying which mechanisms exist, which need adaptation, and which require new implementations.

**Status:** Design document (pre-implementation analysis)

---

## 1. Pipeline Capability Inventory

The Prime Contractor pipeline relies on **12 language-sensitive capabilities**. Each is described below in terms of *what it does* (language-agnostic) and *how Python implements it* (current state).

### C-1: Static Structure Extraction

**What:** Parse source files into a structural model — classes, functions, methods, constants, their signatures, inheritance, decorators, and call relationships. Feeds the ForwardManifest, ElementRegistry, and complexity signals.

**Python implementation:** `ast.parse()` → walk the tree → extract `ClassDef`, `FunctionDef`, `AsyncFunctionDef`, `Import`, `ImportFrom` nodes. Single-pass, no external tools. Produces `CodeManifest` with `Element` objects carrying FQN, kind, signature, bases, decorators, call_graph.

**Files:** `forward_manifest_extractor.py`, `utils/code_manifest.py`, `forward_manifest_validator.py`

---

### C-2: Structural Merge (AST Merge)

**What:** Merge LLM-generated code into an existing file without corrupting structure. Deduplicate imports, merge class methods, detect overlap to auto-switch between additive and replace modes.

**Python implementation:** `ast.parse()` both source and target → categorize nodes (imports, classes, functions, other) → merge by category → `ast.unparse()` the result. Handles `__future__` import ordering, class method injection, and name-based overlap detection.

**Files:** `contractors/adapters/contextcore.py` (`ASTMergeStrategy`)

---

### C-3: Import Resolution and Dependency Scoping

**What:** Given generated code, determine which imports are stdlib, which are third-party (and map to package manager names), which are local/sibling, and which are unresolved hallucinations. Used for: dependency validation, requirements generation, import audit.

**Python implementation:** `ast.walk()` to extract `Import`/`ImportFrom` nodes → classify against `sys.stdlib_module_names`, `_PROTOBUF_STUB_RE`, sibling discovery via `Path.iterdir()`, and `_PYPI_TO_IMPORT` / `_IMPORT_TO_PYPI` bidirectional maps.

**Files:** `utils/import_resolution.py`, `implementation_engine/package_aliases.py`

---

### C-4: Syntax Validation

**What:** Verify generated code is syntactically valid before integration. Catch parse errors early.

**Python implementation:** `python3 -m py_compile {file}` subprocess call. Also `ast.parse()` as internal validation in splicer and code extraction.

**Files:** `contractors/checkpoint.py` (`check_syntax`)

---

### C-5: Lint / Static Analysis

**What:** Run language-specific static analysis to catch correctness issues (undefined names, unused imports, unreachable code) beyond syntax.

**Python implementation:** `python3 -m ruff check {file} --select=E7,E9,F` with auto-fix support (`--fix --unsafe-fixes`). Style-only codes (E741/E742/E743) downgraded to warnings.

**Files:** `contractors/checkpoint.py` (`check_lint`, `pre_validate`)

---

### C-6: Import Audit and Injection

**What:** Given generated code and declared dependencies, detect missing imports and inject them at the correct location. Prevent the #1 generation failure mode.

**Python implementation:** `ast.parse()` → collect imported names, referenced names (via `ast.Name`, `ast.Attribute`), defined names → compute `unresolved = referenced - imported - builtins - defined` → map unresolved to packages via alias map → inject `import` statements after the last existing import line.

**Files:** `utils/code_extraction.py` (`audit_imports`, `inject_missing_imports`)

---

### C-7: Stub Detection

**What:** Identify functions/methods the LLM failed to implement (body is `pass`, `...`, or `raise NotImplementedError`). Distinguish pipeline stubs (intentional, carry sentinel marker) from LLM stubs (generation failure).

**Python implementation:** `ast.walk()` → check function bodies: single-node bodies that are `Expr(Constant(...))`, `Pass`, or `Raise(NotImplementedError)` are stubs. Pipeline stubs carry `STUB_SENTINEL` string in source.

**Files:** `contractors/checkpoint.py` (`check_stubs`), `utils/ast_checks.py`

---

### C-8: Duplicate Detection

**What:** Detect duplicate class or function definitions at the same scope level within a file. Catches LLM hallucination of redundant definitions.

**Python implementation:** `ast.iter_child_nodes()` on the module tree → collect top-level `ClassDef` and `FunctionDef` names → flag duplicates.

**Files:** `contractors/checkpoint.py` (`check_duplicates`)

---

### C-9: Body Splicing (Skeleton Fill)

**What:** Given a skeleton file with stub functions and separately-generated function bodies, splice the bodies into the correct locations. Preserve indentation, inject new imports, validate the result.

**Python implementation:** `ast.parse()` the skeleton → locate stub functions by name → `_find_stub_line_via_ast()` → extract body from generated code → `textwrap.dedent()` + re-indent → replace stub lines → `ast.parse()` round-trip validation.

**Files:** `micro_prime/splicer.py`

---

### C-10: Blast Radius Scanning

**What:** Count how many source files in the project import a given target file. Measures coupling — high blast radius → higher complexity tier → more expensive model.

**Python implementation:** `os.walk()` project tree → for each source file, read first 8KB → string-match against import patterns like `import {stem}`, `from {stem} import`, `from {package}.{stem} import`.

**Files:** `complexity/signals.py` (`_compute_blast_radius`)

---

### C-11: Framework Import Preamble

**What:** Given detected frameworks (gRPC, Flask, OTel), inject canonical import templates into the spec to reduce post-generation import repair. Framework detection uses dependency names, description keywords, and file patterns.

**Python implementation:** `FRAMEWORK_IMPORTS` dict keyed by framework → `detect_frameworks()` matches against deps and description → `get_import_preamble()` formats as markdown with ` ```python` fences.

**Files:** `implementation_engine/framework_imports.py`

---

### C-12: Package Manager Artifact Generation

**What:** Generate or validate the language's dependency manifest (requirements.txt, go.mod, package.json, build.gradle) from service metadata and detected dependencies.

**Python implementation:** `requirements_generator.py` produces `requirements.txt` from runtime_dependencies, applying PyPI name normalization and protobuf stub filtering.

**Files:** `utils/requirements_generator.py`

---

## 2. Language Mechanism Mapping

For each capability, what mechanism does each language provide?

### Legend
- **Direct equivalent** — Language has a tool/API that maps 1:1
- **Partial equivalent** — Mechanism exists but covers a subset
- **Alternative needed** — Different approach required
- **N/A** — Capability doesn't apply to this language

| # | Capability | Python | Go | Node.js | Java |
|---|-----------|--------|-----|---------|------|
| C-1 | Static Structure Extraction | `ast` stdlib | `go/parser` + `go/ast` | `@babel/parser` or `acorn` | `javalang` (PyPI) or `javac -Xprint` |
| C-2 | Structural Merge | `ast.parse/unparse` | No `ast.unparse` equivalent | No equivalent | No equivalent |
| C-3 | Import Resolution | `ast` + `sys.stdlib_module_names` | `go list -m` + `golang.org/x/tools` | `package.json` deps | `build.gradle` deps |
| C-4 | Syntax Validation | `py_compile` | `go vet` / `go build` | `node --check` | `javac` / `gradle compileJava` |
| C-5 | Lint / Static Analysis | `ruff` | `go vet` (built-in) | `eslint` (optional) | `checkstyle` (optional) |
| C-6 | Import Audit + Injection | `ast` analysis | Compiler-enforced | Runtime detection only | Compiler-enforced |
| C-7 | Stub Detection | `ast` body inspection | Text pattern: `panic("not implemented")` | Text pattern: `throw new Error` | Text pattern: `throw new UnsupportedOperationException` |
| C-8 | Duplicate Detection | `ast` top-level scan | Compiler-enforced (won't compile) | Text-based dedup | Compiler-enforced |
| C-9 | Body Splicing | `ast` + `textwrap` | Text-based (no Go unparse) | Text-based | Text-based |
| C-10 | Blast Radius Scan | String match `import X` | String match `"module/path"` | String match `require/from` | String match `import pkg` |
| C-11 | Framework Import Preamble | Python `import` syntax | Go `import "pkg"` syntax | `require()` / `import from` | Java `import pkg.Class` |
| C-12 | Package Manager Artifacts | `requirements.txt` | `go.mod` | `package.json` | `build.gradle` |

---

## 3. Per-Language Analysis

### 3.1 Go

#### C-1: Static Structure Extraction

**Go mechanism:** The `go/parser` and `go/ast` packages in Go's standard library provide full AST parsing — equivalent power to Python's `ast` module. However, we're running from Python, not Go.

**Options:**
1. **Shell out to `go doc -json`** — Returns structured JSON for exported symbols. Covers exported functions, types, methods, but not unexported internals. Partial coverage.
2. **Shell out to custom Go tool** — Write a small Go binary that uses `go/parser` + `go/ast` to emit JSON element specs. Full coverage but requires a Go toolchain.
3. **Regex/heuristic parsing from Python** — Parse Go source text for `func`, `type`, `struct`, `interface` declarations. No external dependency. Covers ~80% of cases.
4. **Use `ctags` / `universal-ctags`** — Language-agnostic symbol extraction. Covers function/type/method names and signatures. Available on most systems.

**Recommendation:** Option 3 (regex heuristic) for MVP, upgrade to Option 2 if accuracy matters. Go's declaration syntax is regular enough that `func (\w+)`, `type (\w+) struct`, `type (\w+) interface` patterns cover most cases.

**What's different from Python:**
- Go has no classes — `type X struct` with method receivers `func (x *X) Method()` instead
- Package-level functions, not module-level
- Exported vs unexported determined by capitalization, not `__all__`
- Multiple files in one package share the namespace (no `__init__.py` equivalent)
- No decorators; build tags serve a different purpose

#### C-2: Structural Merge

**Go mechanism:** No Go equivalent of `ast.unparse()`. Go's `go/printer` package can format an AST back to source, but calling it from Python requires a subprocess.

**Options:**
1. **SimpleMergeStrategy only** — Replace entire file. Acceptable for greenfield generation (which online-boutique is).
2. **Text-based merge** — Parse both files with regex to identify function/type boundaries, merge by name. Fragile but workable for simple edits.
3. **Use `goimports` post-merge** — After any merge, run `goimports` to fix import blocks. Handles the hardest part (import dedup).

**Recommendation:** SimpleMergeStrategy (whole-file replace) for Go. The plan already sets `merge_strategy_preference = "simple"`. For edit-mode tasks, text-based function-boundary merge with `goimports` cleanup.

**What's different from Python:**
- Go files in the same package share a namespace — merging must respect package coherence
- `goimports` (standard tool) handles import dedup and formatting automatically
- No class hierarchy to merge; struct methods are top-level functions with receivers

#### C-3: Import Resolution

**Go mechanism:** `go list -m all` lists all module dependencies. `go list -deps ./...` lists all transitive deps. The Go toolchain resolves imports at build time — there's no ambiguity about what `"net/http"` means.

**Options:**
1. **Parse `go.mod`** — Direct file read for declared dependencies. Deterministic.
2. **Shell out to `go list`** — Full dependency resolution with version info.
3. **Regex on source** — Match `import "..."` blocks for import extraction.

**Recommendation:** Regex on source for extraction + `go.mod` parsing for declared deps. No PyPI alias map needed — Go module paths are canonical.

**What's different from Python:**
- No aliasing problem (go module paths ARE the import paths)
- Stdlib is a known set (starts with standard prefixes, no `google.` etc.)
- `go.mod` is the single source of truth for dependencies

#### C-4: Syntax Validation

**Go mechanism:** `go vet ./...` or `go build ./...`. Go's compiler is the validator — if it compiles, it's valid.

**Already wired:** `GoLanguageProfile.syntax_check_command` returns `["go", "vet", "./..."]`. Just needs checkpoint to actually use it (the critical gap identified earlier).

**What's different:** Go validation is all-or-nothing per package, not per-file. `go vet ./...` checks the entire package. A single-file `go vet main.go` may fail if it depends on other files in the package.

#### C-5: Lint / Static Analysis

**Go mechanism:** `go vet` is built into the toolchain. `golangci-lint` is the community standard for deeper analysis but is optional.

**Already wired:** Profile declares `go vet` as lint command.

**What's different:** `go vet` catches unused variables, unreachable code, etc. as compiler errors — there's no "warning" tier. Code either compiles or it doesn't.

#### C-6: Import Audit and Injection

**Go mechanism:** The Go compiler enforces import correctness — unused imports are compile errors. `goimports` automatically adds missing imports and removes unused ones.

**Options:**
1. **Run `goimports` as post-generation step** — Automatically fixes all import issues. This is the Go ecosystem's standard solution.
2. **Skip import audit entirely** — Let the compiler catch it via `go build`.

**Recommendation:** Run `goimports -w {file}` as a post-generation cleanup step. This replaces the entire Python import audit pipeline for Go.

**What's different:** Go's solution is strictly better — `goimports` is authoritative and deterministic. No heuristic needed.

#### C-7: Stub Detection

**Go mechanism:** No AST-based detection from Python. Text pattern matching.

**Patterns to detect:**
```go
func Foo() { panic("not implemented") }
func Foo() { /* TODO */ }
func Foo() {}  // empty body
```

**Recommendation:** Text-based detection: regex for `panic\("not implemented"\)`, empty function bodies `{\s*}`, and `// TODO` markers.

#### C-8: Duplicate Detection

**Go mechanism:** The compiler catches duplicate function/type names within a package. This is a compile error, not a warning.

**Recommendation:** Skip duplicate detection for Go — the compiler handles it. `go build` failure = duplicate detected.

#### C-9: Body Splicing

**Go mechanism:** No AST unparse. Text-based splicing.

**Approach:** Regex to find `func FunctionName(` → locate opening `{` → find matching `}` → replace body. More reliable than Python because Go's brace-delimited syntax is unambiguous.

**Recommendation:** Text-based splicing using brace matching. Run `gofmt` after to normalize formatting.

#### C-10: Blast Radius Scan

**Go mechanism:** Same approach — string match, different patterns.

**Go import patterns:**
```go
import "emailservice/logger"
import logger "emailservice/logger"  // aliased
```

**Already partially wired:** `GoLanguageProfile.get_import_patterns()` returns `['"module_stem"', '/module_stem"']`. Needs `_compute_blast_radius` to actually call it.

#### C-11: Framework Import Preamble

**Go mechanism:** Same concept, Go syntax.

**Already defined:** `GoLanguageProfile.framework_imports` contains Go-specific imports for grpc, http (gorilla/mux), logging (logrus). Needs `get_import_preamble()` to format with Go fences instead of Python fences.

#### C-12: Package Manager Artifacts

**Go mechanism:** `go.mod` file with module path and require directives.

**Format:**
```
module github.com/GoogleCloudPlatform/microservices-demo/src/frontend

go 1.23

require (
    google.golang.org/grpc v1.68.0
    github.com/sirupsen/logrus v1.9.3
)
```

**Recommendation:** Template-based generation from service metadata. Simpler than Python requirements.txt because Go module paths are canonical (no aliasing).

#### Go Summary

| Capability | Approach | Effort |
|-----------|----------|--------|
| C-1 Structure Extraction | Regex heuristic from Python | Medium |
| C-2 Structural Merge | SimpleMergeStrategy (whole-file replace) | None (already configured) |
| C-3 Import Resolution | Regex source scan + go.mod parse | Low |
| C-4 Syntax Validation | `go vet` (already in profile) | Low (wire checkpoint) |
| C-5 Lint | `go vet` (already in profile) | Low (wire checkpoint) |
| C-6 Import Audit | `goimports -w` post-generation | Low |
| C-7 Stub Detection | Text-based pattern matching | Low |
| C-8 Duplicate Detection | Skip (compiler catches) | None |
| C-9 Body Splicing | Text-based brace matching + `gofmt` | Medium |
| C-10 Blast Radius | Wire profile's import patterns | Low |
| C-11 Framework Preamble | Wire profile's framework_imports + Go fences | Low |
| C-12 go.mod Generation | Template from service metadata | Low |

---

### 3.2 Node.js

#### C-1: Static Structure Extraction

**Node mechanism:** JavaScript/TypeScript ASTs can be parsed by:
1. **`@babel/parser`** — Most popular JS parser. Produces ESTree-compatible AST. Requires Node.js runtime.
2. **`acorn`** — Lightweight ESTree parser. Also requires Node.js.
3. **`esprima`** — Older but well-known.
4. **`tree-sitter` with Python bindings** — Multi-language parser that works from Python. Has JS/TS grammars.

**From Python:** No stdlib JS parser. Options:
1. **Shell out to a Node.js script** using `@babel/parser` → JSON output. Full accuracy.
2. **Regex heuristic** — Match `function`, `class`, `const/let/var`, `export`, `module.exports`. Covers ~70% due to JS's syntactic flexibility.
3. **`tree-sitter`** Python bindings — Works from Python, multi-language, maintained.

**Recommendation:** Regex heuristic for MVP. JS/TS syntax is less regular than Go (arrow functions, destructuring, default exports, CommonJS vs ESM), so accuracy will be lower.

**What's different from Python:**
- Two module systems: CommonJS (`require()`) and ESM (`import from`)
- No classes required — functions, arrow functions, object literals are primary
- `export default` vs named exports vs `module.exports`
- Dynamic typing — no signatures to extract beyond parameter names
- No method receiver syntax — methods are properties of objects/classes

#### C-2: Structural Merge

**Node mechanism:** No JS equivalent of `ast.unparse()` callable from Python. `prettier` can reformat but not merge.

**Recommendation:** SimpleMergeStrategy (whole-file replace). For edit tasks, text-based section merge. Run `prettier` after.

#### C-3: Import Resolution

**Node mechanism:** `package.json` `dependencies` field is the source of truth.

**Dual import detection needed:**
```javascript
// CommonJS
const grpc = require('@grpc/grpc-js');

// ESM
import grpc from '@grpc/grpc-js';
import { Server } from '@grpc/grpc-js';
```

**Stdlib detection:** Node built-in modules are a known set (`fs`, `http`, `path`, etc.) or prefixed with `node:` in modern code.

**Recommendation:** Regex for both patterns + `package.json` parsing for declared deps.

#### C-4: Syntax Validation

**Already wired:** `node --check {file}` in profile. Only validates syntax, not imports.

**What's different:** `node --check` is per-file (unlike Go's per-package). CommonJS files with `require()` are validated at runtime, not statically.

#### C-5: Lint

**Node mechanism:** `eslint` is the standard but is optional and requires configuration. No built-in equivalent to `go vet` or `ruff`.

**Recommendation:** `node --check` for syntax. Skip lint unless `eslint` config exists in project.

#### C-6: Import Audit

**Node mechanism:** No compile-time enforcement. Missing imports crash at runtime.

**Options:**
1. **Regex-based audit** — Parse `require()` and `import from` statements, compare against `package.json` deps.
2. **Skip** — Rely on `node --check` for syntax and the LLM for correctness.

**Recommendation:** Regex-based check that declared `require`/`import` targets exist in `package.json` or are Node built-ins.

#### C-7: Stub Detection

**Patterns:**
```javascript
function foo() { throw new Error('not implemented'); }
function foo() { /* TODO */ }
const foo = () => {};  // empty arrow function
```

**Recommendation:** Text-based pattern matching.

#### C-8: Duplicate Detection

**Node mechanism:** JS allows function redefinition (last definition wins in non-strict mode). No compiler catch.

**Recommendation:** Text-based dedup — regex for `function X(` and `class X` at module scope.

#### C-9: Body Splicing

**Recommendation:** Text-based brace matching. Run `prettier` after. Less reliable than Go because JS has arrow functions, object methods, etc.

#### C-10: Blast Radius

**Patterns:** `require('module')`, `from 'module'`, `import 'module'`.

**Already defined:** `NodeLanguageProfile.get_import_patterns()` covers both.

#### C-11: Framework Import Preamble

**Already defined:** Profile has grpc, express, pino imports. Needs Go-fence → JS-fence formatting.

#### C-12: Package Manager Artifacts

**`package.json` generation:**
```json
{
  "name": "currencyservice",
  "version": "1.0.0",
  "dependencies": {
    "@grpc/grpc-js": "^1.10.0",
    "pino": "^8.0.0"
  }
}
```

**Recommendation:** Template-based from service metadata. JSON format is simpler to generate than YAML or TOML.

#### Node.js Summary

| Capability | Approach | Effort |
|-----------|----------|--------|
| C-1 Structure Extraction | Regex heuristic (limited accuracy) | Medium |
| C-2 Structural Merge | SimpleMergeStrategy | None |
| C-3 Import Resolution | Regex + package.json parse | Low |
| C-4 Syntax Validation | `node --check` (already in profile) | Low |
| C-5 Lint | Skip (no built-in linter) | None |
| C-6 Import Audit | Regex require/import vs package.json | Medium |
| C-7 Stub Detection | Text pattern matching | Low |
| C-8 Duplicate Detection | Text-based module-scope scan | Low |
| C-9 Body Splicing | Text-based brace matching + prettier | Medium |
| C-10 Blast Radius | Wire profile's import patterns | Low |
| C-11 Framework Preamble | Wire profile's framework_imports | Low |
| C-12 package.json Generation | Template from service metadata | Low |

---

### 3.3 Java

#### C-1: Static Structure Extraction

**Java mechanism:** Java has the richest tooling options:
1. **`javalang`** (PyPI) — Pure Python Java parser. Produces AST from Python. **This is the best option** — no subprocess needed.
2. **`javac -Xprint`** — Compiler flag that dumps class structure. Requires JDK.
3. **`javap`** — Disassembles .class files. Requires compilation first.
4. **Eclipse JDT** — Full Java parser (Java ecosystem). Heavyweight.

**Recommendation:** `javalang` PyPI package. It parses Java source directly from Python, extracting classes, methods, fields, interfaces, annotations, and inheritance. Closest equivalent to Python's `ast` module.

**What's different from Python:**
- One public class per file (filename must match class name)
- Package hierarchy maps to directory structure (`com.example.service` → `com/example/service/`)
- Access modifiers (`public`, `private`, `protected`, package-private) — richer than Python's `_`/`__`
- Interfaces + abstract classes + inheritance (more structured than Python's duck typing)
- Annotations (`@Override`, `@Inject`) — similar role to Python decorators
- Static typing with generics — signatures carry type information

#### C-2: Structural Merge

**Java mechanism:** `javalang` can parse but not unparse. No `ast.unparse()` equivalent.

**Recommendation:** SimpleMergeStrategy. Java's one-class-per-file convention makes whole-file replacement natural. For edit mode, text-based method-boundary merge using regex `(public|private|protected)\s+\w+\s+\w+\(`.

#### C-3: Import Resolution

**Java mechanism:** Java imports are fully qualified (`import io.grpc.Server`). Package → dependency mapping uses `build.gradle` or `pom.xml`.

**Stdlib detection:** Packages starting with `java.` or `javax.` are stdlib.

**Options:**
1. **`javalang` AST** — Extract `ImportDeclaration` nodes. Full accuracy.
2. **Regex** — Match `import\s+[\w.]+;` lines. Very reliable for Java.

**Recommendation:** Regex (Java's import syntax is highly regular). Cross-reference against `build.gradle` dependencies.

#### C-4: Syntax Validation

**Java mechanism:** `javac` or `gradle compileJava`. Compilation IS validation.

**Challenge:** Java compilation requires the full dependency tree to be resolved. You can't compile a single file in isolation like `python3 -m py_compile`.

**Recommendation:** `gradle compileJava` if Gradle exists, else skip single-file validation. Rely on `javalang.parse()` from Python for syntax-only checks (no type checking, but catches parse errors).

#### C-5: Lint

**Java mechanism:** `checkstyle`, `spotbugs`, `PMD`. All optional, all require configuration.

**Recommendation:** Skip lint unless project has existing configuration. Java's compiler catches most correctness issues.

#### C-6: Import Audit

**Java mechanism:** The compiler catches unused imports (warning) and missing imports (error). `google-java-format` can organize imports.

**Options:**
1. **`javalang` AST** — Parse imports, cross-reference against types used in code.
2. **Skip** — Let the compiler catch it.

**Recommendation:** Basic regex check that imported packages are in `build.gradle`. `google-java-format` for cleanup.

#### C-7: Stub Detection

**Patterns:**
```java
public void foo() { throw new UnsupportedOperationException(); }
public void foo() { /* TODO */ }
public void foo() {}  // empty body
```

**Recommendation:** Text-based pattern matching. Could also use `javalang` to inspect method bodies.

#### C-8: Duplicate Detection

**Java mechanism:** Compiler enforces — duplicate class/method definitions are compile errors.

**Recommendation:** Skip. Compiler handles it.

#### C-9: Body Splicing

**Recommendation:** Text-based brace matching. Java's regular syntax makes this reliable. Run `google-java-format` after.

**Alternative:** `javalang` parse → locate method → replace body text → format.

#### C-10: Blast Radius

**Patterns:** `import com.example.service.TargetClass`

**Already defined:** `JavaLanguageProfile.get_import_patterns()` covers `import` and `import static`.

#### C-11: Framework Import Preamble

**Already defined:** Profile has grpc and log4j imports.

#### C-12: Package Manager Artifacts

**`build.gradle` generation — most complex:**
```groovy
plugins {
    id 'java'
    id 'application'
    id 'com.google.protobuf' version '0.9.4'
}

dependencies {
    implementation 'io.grpc:grpc-netty:1.68.0'
    implementation 'org.apache.logging.log4j:log4j-core:2.23.0'
}
```

**Recommendation:** Template-based. Gradle's dependency syntax is `group:artifact:version` which maps cleanly from service metadata.

#### Java Summary

| Capability | Approach | Effort |
|-----------|----------|--------|
| C-1 Structure Extraction | `javalang` PyPI package (pure Python) | Low-Medium |
| C-2 Structural Merge | SimpleMergeStrategy | None |
| C-3 Import Resolution | Regex + build.gradle parse | Low |
| C-4 Syntax Validation | `javalang.parse()` from Python | Low |
| C-5 Lint | Skip | None |
| C-6 Import Audit | Regex import vs build.gradle | Low |
| C-7 Stub Detection | Text pattern matching | Low |
| C-8 Duplicate Detection | Skip (compiler catches) | None |
| C-9 Body Splicing | Text-based brace matching | Medium |
| C-10 Blast Radius | Wire profile's import patterns | Low |
| C-11 Framework Preamble | Wire profile's framework_imports | Low |
| C-12 build.gradle Generation | Template from service metadata | Medium |

---

## 4. Cross-Language Gap Summary

### Capabilities that work as-is (no language-specific code needed)
- **C-2 Structural Merge:** All three languages use SimpleMergeStrategy (whole-file replace)
- **C-10 Blast Radius:** String matching works for all — just need to wire profile patterns
- **C-11 Framework Preamble:** Profile data exists — just need language-aware fence formatting

### Capabilities that need wiring (profile exists, pipeline doesn't use it)
- **C-4 Syntax Validation:** Checkpoint must pass language_profile and use it
- **C-5 Lint:** Same wiring as C-4

### Capabilities that need new per-language implementations

| Capability | What's needed | Shared infrastructure? |
|-----------|--------------|----------------------|
| **C-1 Structure Extraction** | Regex heuristic parser per language (Go, JS); `javalang` for Java | Yes — `LanguageProfile.extract_elements(source) -> List[ElementSpec]` |
| **C-3 Import Resolution** | Per-language import regex + dep-file parser | Yes — `LanguageProfile.extract_imports(source)` + `LanguageProfile.parse_dependency_file(path)` |
| **C-6 Import Audit** | Go: `goimports`; Node: regex; Java: regex or skip | Partially — different strategies per language |
| **C-7 Stub Detection** | Per-language stub patterns | Yes — `LanguageProfile.stub_patterns -> List[str]` |
| **C-9 Body Splicing** | Text-based brace matching for all three | Yes — `brace_match_splice()` shared utility |
| **C-12 Dep File Generation** | go.mod template; package.json template; build.gradle template | No — each is unique |

### Capabilities that can be skipped for specific languages
- **C-8 Duplicate Detection:** Skip for Go and Java (compiler-enforced)
- **C-5 Lint:** Skip for Node and Java (no built-in linter)
- **C-6 Import Audit:** Go uses `goimports` instead; Java compiler catches errors

---

## 5. Implementation Priority

Based on impact to online-boutique Go success (4/7 services):

| Priority | Work Item | Capabilities | Effort | Status |
|----------|-----------|-------------|--------|--------|
| **P0** | Wire checkpoint + merge strategy to use language_profile | C-2, C-4, C-5 | Small | Done (a3c210f) |
| **P1** | Wire blast radius + framework preamble to use profile | C-10, C-11 | Small | Done (a3c210f) |
| **P2** | Go import post-processing (`goimports`) | C-6 | Small | Done (f7ddccd) |
| **P3** | Dependency file generation (go.mod, package.json, build.gradle) | C-12 | Small | Done (f7ddccd) |
| **P4** | Go structure extraction (regex heuristic) | C-1 | Medium | |
| **P5** | Go stub detection patterns | C-7 | Small | |
| **P6** | Go body splicing (brace matching) | C-9 | Medium | |
| **P7** | Node.js import resolution (dual CJS/ESM) | C-3 | Medium | |
| **P8** | Java structure extraction (`javalang`) | C-1 | Medium | |

**P0-P3 unblock Go for online-boutique.** P4-P6 improve quality. P7-P8 are for Node/Java.

---

## 6. Language Implementation Difficulty Ranking

Ranked by complexity of adding support beyond the existing Python baseline, easiest first.

### 6.1 Go — Easiest

**Why:** Go's compiler and standard tooling do the heavy lifting — we can *skip* entire capabilities that require complex Python implementation.

**Compiler safety net (strong):** Unused imports, unused variables, duplicate definitions, and type errors are all compile-time errors. The Go compiler enforces what Python needs AST analysis for (C-6 import audit, C-8 duplicate detection).

**Authoritative post-gen tools:** `goimports` replaces our entire import audit pipeline with one subprocess call — it adds missing imports, removes unused ones, and formats the import block. `gofmt` is the authoritative formatter with zero configuration. No equivalent exists for Python, Node.js, or Java.

**Regular syntax:** Go declarations are uniform (`func X()`, `type X struct`, `type X interface`, `func (x *X) Method()`). No classes, no decorators, no multiple module systems. Regex-based structure extraction (P4) is reliable because the syntax has minimal variation.

**What can be skipped entirely:**
- C-6 Import audit — `goimports` handles it
- C-8 Duplicate detection — compiler error

**Main remaining work:**
- P4: Regex structure extraction for ForwardManifest population
- P5: Stub detection (`panic("not implemented")`, empty bodies)
- P6: Text-based body splicing with brace matching + `gofmt`

**Key differences from Python:**
- No classes — structs with method receivers instead
- Package-level functions, not module-level
- Multiple files share a package namespace (no `__init__.py`)
- Exported vs unexported by capitalization, not `__all__`
- `go vet` validates per-package, not per-file

---

### 6.2 Java — Medium

**Why:** A Python-native AST parser exists (`javalang` on PyPI), and the compiler catches most correctness issues, but the build system is the most complex of the three.

**Compiler safety net (strong):** Same as Go — duplicate definitions and missing imports are compile errors. Unused imports are warnings. Type checking is enforced at compile time.

**Python-native AST parsing:** The `javalang` PyPI package parses Java source directly from Python, extracting classes, methods, fields, interfaces, annotations, and inheritance. No subprocess needed. This is the closest equivalent to Python's `ast` module across all three languages.

**Regular syntax:** Java's import syntax (`import pkg.Class;`) is highly regular — regex extraction is reliable. Method signatures carry type information. Annotations map to Python decorators.

**Main costs:**
- `build.gradle` generation is the most complex dependency file (Groovy DSL with plugins, source sets, dependency configurations, repository declarations)
- Package hierarchy ↔ directory structure mapping (`com.example.service` → `com/example/service/`) adds a layer Python doesn't have
- One public class per file (filename must match class name) — affects code extraction and file routing

**What can be skipped:**
- C-8 Duplicate detection — compiler error
- C-5 Lint — no built-in linter (checkstyle/spotbugs optional)

**No authoritative import fixer:** Unlike Go's `goimports`, Java has no single CLI tool that fixes imports. `google-java-format` organizes but doesn't add missing imports. IDE-level tools (IntelliJ, Eclipse) do this but aren't CLI-callable.

---

### 6.3 Node.js — Hardest

**Why:** Every design decision in JavaScript maximizes flexibility at the cost of static analyzability. No compiler, no authoritative tools, dual module systems, and irregular syntax compound into the highest implementation cost.

**No compiler safety net:** Missing imports, duplicate definitions, type errors, and unused variables are all runtime failures. Nothing catches them before execution. We must build detection for everything that Go and Java compilers provide for free.

**Dual module system:** CommonJS (`require()`) and ESM (`import from`) coexist. Every import-related capability requires handling both patterns:
```javascript
// CommonJS
const grpc = require('@grpc/grpc-js');
const { Server } = require('@grpc/grpc-js');

// ESM
import grpc from '@grpc/grpc-js';
import { Server } from '@grpc/grpc-js';
```
This doubles the regex patterns, test cases, and edge cases for C-3 (import resolution), C-6 (import audit), and C-10 (blast radius).

**Irregular syntax:** JavaScript's syntactic flexibility makes regex-based structure extraction unreliable:
- Arrow functions: `const handler = (req, res) => { ... }` vs `function handler(req, res) { ... }`
- Object methods: `module.exports = { handler() { ... } }`
- Destructured exports: `const { a, b } = require('pkg')`
- Default exports: `export default class X { ... }` vs `module.exports = X`
- Template literals containing braces break naive brace matching
- No static types — signatures carry only parameter names, not types

**No authoritative import fixer:** No `goimports` equivalent. `prettier` formats code but doesn't fix imports. `eslint --fix` can remove unused imports with plugins, but can't add missing ones. There is no single tool that authoritatively resolves import correctness.

**Weakest validation:** `node --check` is syntax-only. It verifies the file parses, but doesn't check whether `require('nonexistent')` will fail. Dynamic `require()` calls can't be statically analyzed at all.

**What can be skipped:** Nothing. We need to build everything ourselves.

**Main costs:**
- C-6 Import audit: Must build regex-based detection for both CJS and ESM, with no authoritative fixer as fallback
- C-1 Structure extraction: Limited accuracy due to arrow functions, object patterns, destructuring
- C-9 Body splicing: Fragile due to template literals, arrow functions in object methods
- C-8 Duplicate detection: Must implement (JS allows silent redefinition in non-strict mode)

---

### Summary Table

| Dimension | Go | Java | Node.js |
|-----------|-----|------|---------|
| **Compiler catches errors** | Yes (strong) | Yes (strong) | No |
| **Authoritative import fixer** | `goimports` | None | None |
| **Python-native AST parser** | No (regex) | `javalang` (PyPI) | No (regex, low accuracy) |
| **Syntax regularity** | High | High | Low |
| **Module system complexity** | Single | Single | Dual (CJS + ESM) |
| **Capabilities we can skip** | C-6, C-8 | C-8, C-5 | None |
| **Remaining effort after P0-P3** | Small (P4-P6) | Medium (P8 + build.gradle complexity) | Large (all capabilities) |

**The counterintuitive takeaway:** Go's strictness makes it the *easiest* to support. Node's flexibility makes it the *hardest*. The compiler does work for you in Go and Java that we'd have to build ourselves for Node.
