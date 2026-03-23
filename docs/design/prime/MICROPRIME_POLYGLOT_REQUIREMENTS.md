# MicroPrime Polyglot Requirements — Language-Agnostic

> **Version:** 1.0.0
> **Status:** DRAFT
> **Date:** 2026-03-23
> **Scope:** Define how ANY language with a parser + splicer integrates with MicroPrime for element-level code generation
> **Derived from:** `CSHARP_MICROPRIME_ELEMENT_REQUIREMENTS.md` v1.0 (generalized)
> **Language specializations:** Each language directory has a `{LANG}_MICROPRIME_ELEMENT_REQUIREMENTS.md` with language-specific details

---

## 1. Overview

MicroPrime enables **element-level code generation** — decomposing a file into individual functions, methods, and classes, generating each independently, then splicing them back into a skeleton. This produces higher-quality code at lower cost than file-whole generation because:

- Each element gets a focused prompt (less context pollution)
- Trivial elements use templates ($0.00) or local models (~$0.001)
- Only complex elements escalate to cloud models (~$0.10-0.20)
- Failed elements can be retried independently (no whole-file regeneration)

### Language Eligibility

A language is MicroPrime-eligible when it has:

| Capability | Required | Implementation |
|-----------|----------|---------------|
| **Parser** | Yes | Extracts structural elements (functions, classes, methods) with names and line numbers |
| **Splicer** | Yes | Replaces stub bodies with generated implementations via brace/indent matching |
| **Stub detection** | Yes | Identifies placeholder bodies (`throw new Error`, `panic("not implemented")`, `// TODO`) |
| **Skeleton assembly** | Recommended | Produces a compilable skeleton with stubs from a forward manifest |
| **Syntax validation** | Recommended | Validates generated code (compiler, linter, or text heuristics) |

---

## 2. Current Language Status

| Language | Parser | Splicer | Stub Detection | Skeleton | Syntax Validate | MicroPrime Status |
|----------|--------|---------|----------------|----------|----------------|------------------|
| **Python** | `ast` (stdlib) | `ast` (stdlib) | `raise NotImplementedError`, `pass` | `DeterministicFileAssembler` | `py_compile` | **Full** — element-level with AST merge |
| **C#** | `csharp_parser.py` (tree-sitter + regex) | `csharp_splicer.py` (tree-sitter byte-offset) | `NotImplementedException`, `NotSupportedException`, `// TODO` | `CSharpDeterministicFileAssembler` | `dotnet build` (optional) | **Wired** — parser/splicer connected, templates registered |
| **Go** | `go_parser.py` (regex) | `go_splicer.py` (text brace-matching) | `panic("not implemented")`, `// TODO` | Go skeleton templates | `gofmt -e` | **Eligible** — routing enabled, needs template registration |
| **Java** | `java_parser.py` (regex) | `java_splicer.py` (text brace-matching) | `UnsupportedOperationException`, `RuntimeException("TODO")` | Not implemented | `javac` (requires project) | **Eligible** — routing enabled, needs skeleton + templates |
| **Node.js** | `nodejs_parser.py` (regex) | `nodejs_splicer.py` (text brace-matching) | `throw new Error("not implemented")`, `// TODO` | Not implemented | `node --check` | **Eligible** — routing enabled, needs skeleton + templates |

---

## 3. Engine Integration Points

### 3.1 Element Body Extraction (`_extract_element_body`)

MicroPrime's engine calls `_extract_element_body(source, element_name, file_path)` to get the existing body of a function/method for context. The default implementation uses Python `ast.parse()`.

**Polyglot dispatch:** When the file extension maps to a non-Python language profile, the engine MUST dispatch to the language's parser instead:

```
.py  → ast.parse() (existing)
.cs  → csharp_parser.parse_csharp_source() + byte-offset extraction
.go  → go_parser.parse_go_source() + line-range extraction
.java → java_parser.parse_java_source() + line-range extraction
.js/.ts → nodejs_parser.parse_nodejs_source() + line-range extraction
```

### 3.2 Element System Prompt (`_build_element_system_prompt`)

Each language needs guidance for element-level generation:

| Guidance | Python | C# | Go | Java | Node.js |
|----------|--------|----|----|------|---------|
| Indentation | 4 spaces | 4 spaces | tabs (gofmt normalizes) | 4 spaces | 2 spaces |
| Async pattern | `async def` / `await` | `async Task` / `await` | goroutines + channels | `CompletableFuture` | `async` / `await` |
| Error handling | `try/except` | `try/catch` | `if err != nil` | `try/catch` | `try/catch` or `.catch()` |
| Stub marker | `raise NotImplementedError` | `throw new NotImplementedException()` | `panic("not implemented")` | `throw new UnsupportedOperationException()` | `throw new Error("not implemented")` |
| Import convention | Top of file, grouped | `using` at top | `import` block | `import` after package | `require`/`import` at top |

### 3.3 Template Registry

Templates provide $0.00 generation for common patterns. Each language registers templates in `_LANGUAGE_TEMPLATES[language_id]`:

**Common template categories (all languages):**
- Constructor / factory method
- Getter / setter (property accessor)
- Interface implementation stub
- gRPC service method
- HTTP handler / route
- Test method
- toString / String representation

### 3.4 Skeleton Assembly Contract

A skeleton is a compilable file with stub bodies that MicroPrime fills. Requirements:

1. **Namespace/package derivation** — from target file's directory path
2. **Import injection** — from `prescribed_imports` in the forward manifest + language defaults
3. **Element stubs** — each function/method/class has a body containing the language's stub marker
4. **Compilable** — the skeleton MUST pass the language's syntax validation (even with stubs)

---

## 4. Complexity Classification for Non-Python Languages

The complexity classifier (`complexity/classifier.py`) uses these signals:

| Signal | Source | Impact |
|--------|--------|--------|
| `estimated_loc` | Seed task | Higher LOC → higher tier |
| `target_file_count` | Seed task | Multiple files → COMPLEX |
| `element_count` | Forward manifest | More elements → higher tier |
| `has_dependencies` | Seed task | Dependencies → higher tier |
| `language_profile` | Resolution | Used for language-specific thresholds |

**Language-specific considerations:**
- Java/C# tend to have higher LOC than Go/Python for equivalent functionality (boilerplate)
- Go's single-return-error pattern inflates function count but not complexity
- Node.js arrow functions are often TRIVIAL despite appearing in SIMPLE-classified files

---

## 5. Repair Pipeline Integration

After MicroPrime generates element bodies, the repair pipeline runs:

| Step Category | All Languages | Language-Specific |
|--------------|--------------|-------------------|
| Fence strip | `FenceStripStep` | — |
| Bracket/brace balance | `BracketBalanceStep` | — |
| TODO uncomment | `TodoUncommentStep` | — |
| Syntax validate | — | `GoSyntaxValidateStep`, `CSharpSyntaxValidateStep`, `JavaSyntaxValidateStep`, `JsSyntaxValidateStep`, `AstValidateStep` |
| Semantic repair | — | Language-specific steps (Go contamination strip, C# convention fix, Java import sort, etc.) |

---

## 6. Language Specialization Contract

Each language MUST provide a `{LANG}_MICROPRIME_ELEMENT_REQUIREMENTS.md` that:

1. Lists the parser's capabilities (which element kinds it extracts)
2. Lists the splicer's capabilities (which body forms it handles)
3. Defines skeleton assembly rules (namespace derivation, import defaults, stub bodies)
4. Identifies template opportunities (common patterns in the language's ecosystem)
5. Specifies compilation/validation integration (if available)
6. Documents known limitations (what the parser/splicer can't handle)
