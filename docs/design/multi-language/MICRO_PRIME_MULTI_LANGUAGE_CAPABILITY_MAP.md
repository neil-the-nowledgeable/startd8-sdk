# Micro Prime Multi-Language Capability Map

**Purpose:** Document the MicroPrime engine's capabilities in language-agnostic terms, catalog all Python-specific mechanisms, map each to Go/Node.js/Java, and establish the porting roadmap.

**Status:** Design document. Non-Python languages currently bypass MicroPrime (routed to LeadContractor cloud path via COMPLEX tier override).

**Current state:** MicroPrime is Python-only. 13 major mechanism categories, ~195 AST operations across 12 files, ~165+ hardcoded Python references. Non-Python features are routed to COMPLEX tier in `_route_complexity()` to bypass MicroPrime entirely.

---

## 1. MicroPrime Capability Inventory

MicroPrime handles SIMPLE and MODERATE tier tasks locally (Ollama/Haiku) instead of routing to expensive cloud models. It relies on 13 language-sensitive capabilities:

### MP-1: AST-Based Syntax Validation

**What:** Verify generated code parses without syntax errors. Gate for every generation, splice, and repair step.

**Python:** `ast.parse(code)` — 14 call sites in `engine.py`, 13 in `splicer.py`, 19 in `structural_verify.py`. Every quality gate.

**Scale:** ~195 `ast.parse`/`ast.walk` operations across 12 files. This is the most pervasive Python dependency.

### MP-2: Element Location and Extraction

**What:** Find a specific function/class/method in an AST tree by name, extract its body (lines between signature and end), handle docstrings and decorators.

**Python:** `ast.walk()` → match `ast.FunctionDef`/`ast.ClassDef` by `node.name` → compute body range from `node.body[0].lineno` to `node.end_lineno`.

**Files:** `engine.py:648-705`, `splicer.py:247-305`, `repair.py:220-330`, `_ast_utils.py` (entire file)

### MP-3: Signature Rendering

**What:** Convert a `Signature` dataclass (params with kinds, types, defaults) into language-specific syntax for prompts and stubs.

**Python:** Renders `(self, name: str, *, timeout: int = 30) -> bool` with positional-only `/`, var-positional `*args`, var-keyword `**kwargs`, return annotation `->`.

**Files:** `decomposer.py:158-203`, `decomposer.py:610-630`

### MP-4: System Prompts

**What:** Tell the LLM what language to generate, what syntax rules to follow, what output format to use.

**Python:** Hardcoded strings: "You are a Python code generator", "raw Python code — no ```python fences", "4-space indentation", "raise NotImplementedError".

**Files:** `engine.py:607-645, 707-723`

### MP-5: Keyword and Builtin Reserves

**What:** Validate generated identifiers (helper function names, variable names) don't collide with language keywords or builtins.

**Python:** `_PYTHON_RESERVED = frozenset(keyword.kwlist + keyword.softkwlist + dir(builtins))` — 546 items.

**Files:** `decomposer.py:14-17, 542-546`, `templates.py:116-125`

### MP-6: Stub Pattern Detection

**What:** Detect functions the LLM left unimplemented (body is a stub placeholder).

**Python:** AST walk checks for `pass`, `...` (Ellipsis), `raise NotImplementedError` as sole body statements.

**Go equivalent:** `panic("not implemented")`, empty body `{}`, `// TODO`.
**Node equivalent:** `throw new Error("not implemented")`, empty body.
**Java equivalent:** `throw new UnsupportedOperationException()`.

### MP-7: Body Splicing

**What:** Replace stub function bodies in skeleton files with generated implementations. Preserve indentation, inject imports, validate result.

**Python:** AST-based stub location → line-range replacement → AST round-trip validation.
**Go:** Now wired via `go_splicer.py` (brace-based text matching).

**Files:** `splicer.py:153-183` (dispatch), Go dispatch added in last commit.

### MP-8: Structural Verification

**What:** Post-generation check that all expected elements (from ForwardManifest) exist in the output — correct function names, class names, method presence, non-empty bodies, return statements when annotated.

**Python:** Full AST walk checking `ast.FunctionDef`, `ast.ClassDef`, `ast.Return`, `ast.Assign`, `ast.AnnAssign` nodes by name.

**Files:** `structural_verify.py` (entire file, 310 lines), `prime_adapter.py:265-315`

### MP-9: Dunder Method Templates

**What:** Generate deterministic implementations for common boilerplate methods (`__init__`, `__repr__`, `__eq__`, `__hash__`, `__enter__`, `__exit__`).

**Python:** Hardcoded template functions in `_DUNDER_TEMPLATES` dict. Pure Python idiom with no equivalent in other languages.

**Files:** `templates.py:206-309, 538-546`

### MP-10: Class Decomposition

**What:** Break a MODERATE-complexity class into SIMPLE sub-elements (methods) that can be generated independently, then reassembled.

**Python:** `ClassDecomposeStrategy` extracts methods from class AST, renders stub class with `raise NotImplementedError` bodies, generates each method separately, splices back.

**Files:** `decomposer.py:300-500`

### MP-11: Function Chain Decomposition

**What:** Break a MODERATE-complexity function into a chain of SIMPLE helper functions, then assemble into calling function.

**Python:** Extracts responsibilities from docstring, generates helper function names (slugified), validates against `_PYTHON_RESERVED`.

**Files:** `decomposer.py:500-850`

### MP-12: Repair Pipeline

**What:** Fix common LLM generation defects: fence stripping, over-generation trimming (remove AST nodes not in manifest), definition reordering, octal literal fixing (Python 2→3).

**Python:** Heavy AST manipulation — parse, walk, identify extraneous nodes by name, compute line ranges, delete.

**Files:** `repair.py` (entire file, 1000+ lines)

### MP-13: Literal Value Coercion

**What:** Safely serialize constant/default values from contracts into code-safe literals, preventing injection.

**Python:** `ast.literal_eval()` → `repr()` for safe round-tripping. Handles `True`, `False`, `None`, numeric, string literals.

**Files:** `templates.py:154-169, 438-444`

---

## 2. Language Mechanism Mapping

| # | Capability | Python | Go | Node.js | Java |
|---|-----------|--------|-----|---------|------|
| MP-1 | Syntax Validation | `ast.parse()` | `go build` subprocess | `node --check` subprocess | `javalang.parse()` from Python |
| MP-2 | Element Location | `ast.walk()` + node types | `go_parser.py` regex | Regex (low accuracy) | `javalang` AST |
| MP-3 | Signature Rendering | Python def syntax | `func (r *T) Name(p Type) RetType` | `function name(p) {}` | `public RetType name(Type p)` |
| MP-4 | System Prompts | Hardcoded Python strings | Language-parameterized templates | Same | Same |
| MP-5 | Keyword Reserves | `keyword.kwlist` + builtins | Go 25 keywords | JS ~80 keywords | Java ~50 keywords |
| MP-6 | Stub Detection | AST body inspection | Text patterns (done) | Text patterns (done) | Text patterns (done) |
| MP-7 | Body Splicing | AST-based | `go_splicer.py` (done) | Text-based brace matching | Text-based brace matching |
| MP-8 | Structural Verify | Full AST walk | `go_parser.py` element check | Regex element check | `javalang` element check |
| MP-9 | Dunder Templates | 6 templates | Skip (no equivalent) | Skip | Skip |
| MP-10 | Class Decomposition | ClassDecomposeStrategy | Skip (no classes) | Regex-based (fragile) | `javalang`-based |
| MP-11 | Function Decomposition | FunctionChainStrategy | Portable (keyword swap) | Portable (keyword swap) | Portable (keyword swap) |
| MP-12 | Repair Pipeline | AST manipulation | `goimports` + compiler | Limited (no tools) | Limited (compiler) |
| MP-13 | Literal Coercion | `ast.literal_eval` | Language-specific literals | `JSON.parse` semantics | Java literal syntax |

---

## 3. Per-Language MicroPrime Feasibility

### 3.1 Go — Most Feasible (after Python)

**Key advantage:** Go's compiler and `goimports` replace MP-1 (validation), MP-6 (stubs — compiler catches unused), MP-8 (structural verify — if it compiles, elements exist), and MP-12 (repair — `goimports` fixes imports, compiler catches the rest).

**What can be skipped entirely:**
- MP-9 Dunder templates (Go has no equivalent)
- MP-10 Class decomposition (Go has no classes — structs with methods)
- MP-12 Repair pipeline (compiler + `goimports` handle it)

**What already works:**
- MP-6 Stub detection (text patterns in `GoLanguageProfile`)
- MP-7 Body splicing (`go_splicer.py`)
- MP-2 Element location (`go_parser.py`)

**What needs building:**

| Capability | Effort | Approach |
|-----------|--------|----------|
| MP-1 Syntax validation | Low | `go build` subprocess (already in profile) |
| MP-3 Signature rendering | Medium | `func (r *Type) Name(params) ReturnType` — different structure than Python |
| MP-4 System prompts | Low | Parameterize existing templates with language context |
| MP-5 Keyword reserves | Low | 25 Go keywords — trivial set |
| MP-8 Structural verify | Medium | Use `go_parser.py` to check element presence in output |
| MP-11 Function decomposition | Low | Keyword swap (`func` vs `def`), remove `_PYTHON_RESERVED` |
| MP-13 Literal coercion | Low | Go literals: `true`/`false`/`nil` vs Python `True`/`False`/`None` |

**Estimated effort:** 1-2 weeks

### 3.2 Java — Medium Feasibility

**Key advantage:** `javalang` PyPI package provides Python-native AST parsing — can replace `ast.parse()` for MP-1, MP-2, MP-8 without subprocesses.

**What can be skipped:**
- MP-9 Dunder templates
- MP-12 Repair pipeline (compiler catches most issues)

**What needs building:**

| Capability | Effort | Approach |
|-----------|--------|----------|
| MP-1 Syntax validation | Low | `javalang.parse.parse(code)` |
| MP-2 Element location | Low | `javalang` AST traversal |
| MP-3 Signature rendering | Medium | Java's verbose syntax: `public static ReturnType methodName(Type param)` |
| MP-5 Keyword reserves | Low | ~50 Java keywords |
| MP-8 Structural verify | Medium | `javalang` element presence check |
| MP-10 Class decomposition | Medium | Java classes are central — need `javalang`-based decomposition |
| MP-13 Literal coercion | Low | Java: `true`/`false`/`null` |

**Estimated effort:** 2-3 weeks (MP-10 class decomposition is the largest item)

### 3.3 Node.js — Least Feasible

**Key disadvantage:** No Python-native JS parser, no compiler safety net, irregular syntax makes all regex-based approaches fragile.

**What can be skipped:**
- MP-9 Dunder templates

**What needs building:**

| Capability | Effort | Approach |
|-----------|--------|----------|
| MP-1 Syntax validation | Low | `node --check` subprocess |
| MP-2 Element location | Hard | Regex unreliable (arrow fns, destructuring, CJS/ESM) |
| MP-3 Signature rendering | Medium | `function name(p) {}` and `(p) => {}` dual syntax |
| MP-5 Keyword reserves | Low | ~80 JS keywords + global objects |
| MP-8 Structural verify | Hard | No reliable parser from Python |
| MP-10 Class decomposition | Hard | JS classes are optional; object methods, prototypes complicate |
| MP-11 Function decomposition | Medium | `const` vs `function` vs arrow fn duality |
| MP-12 Repair pipeline | Hard | No authoritative fixer like `goimports` |
| MP-13 Literal coercion | Low | JS: `true`/`false`/`undefined`/`null` |

**Estimated effort:** 4-5 weeks (MP-2 and MP-8 are the blockers due to JS syntax irregularity)

---

## 4. Implementation Priority

Based on the same Go-first strategy as the Prime Contractor map:

| Priority | Work Item | Capabilities | Effort | Status |
|----------|-----------|-------------|--------|--------|
| **MP-P0** | Bypass MicroPrime for non-Python | All | Small | **Done** (COMPLEX tier override) |
| **MP-P1** | Language-parameterized system prompts | MP-4 | Small | |
| **MP-P2** | Go keyword reserves | MP-5 | Small | |
| **MP-P3** | Go structural verification via go_parser | MP-8 | Medium | |
| **MP-P4** | Go signature rendering | MP-3 | Medium | |
| **MP-P5** | Go literal coercion | MP-13 | Small | |
| **MP-P6** | Go function decomposition (keyword swap) | MP-11 | Low | |
| **MP-P7** | Pluggable syntax validation interface | MP-1 | Medium | |
| **MP-P8** | Java `javalang` integration | MP-1, MP-2, MP-8 | Medium | |
| **MP-P9** | Node.js parser integration | MP-1, MP-2, MP-8 | Hard | |

**MP-P0 is done.** MP-P1 through MP-P6 would enable Go in MicroPrime (~1-2 weeks). MP-P7 through MP-P9 are for Java and Node.js.

**Recommendation:** Do not pursue MicroPrime multi-language support until Go generation via LeadContractor (cloud path) is validated end-to-end on online-boutique. MicroPrime's value is cost optimization — correctness via the cloud path must come first.

---

## 5. Difficulty Ranking (MicroPrime-specific)

Same ordering as the Prime Contractor map, but with higher absolute effort:

### Go — Easiest (1-2 weeks)

The compiler and `goimports` replace 4 of 13 capabilities. `go_parser.py` and `go_splicer.py` already exist. Main remaining work: signature rendering, structural verification via existing parser, and prompt parameterization.

### Java — Medium (2-3 weeks)

`javalang` provides a Python-native AST parser, covering the hardest mechanisms (MP-1, MP-2, MP-8). Class decomposition is needed because Java is class-centric. Compiler handles repair.

### Node.js — Hardest (4-5 weeks)

No Python-native parser, no compiler, irregular syntax. Every mechanism that relies on structural analysis is unreliable. Recommend deferring indefinitely — Node.js services should use the LeadContractor cloud path.

---

## 6. Architecture: Current vs Target

### Current (Python-only)

```
classify_tier() → SIMPLE/MODERATE → MicroPrimeEngine
                                      ├── ast.parse() validation
                                      ├── Python prompts
                                      ├── Python splicer
                                      └── Python repair
                → COMPLEX → LeadContractor (cloud, language-aware)
```

### Target (multi-language)

```
classify_tier() → non-Python + MicroPrime enabled?
                    ├── YES → force COMPLEX → LeadContractor (current bypass)
                    └── NO  → normal routing
                      → SIMPLE/MODERATE → MicroPrimeEngine
                                           ├── LanguageParser.parse() validation
                                           ├── Language-parameterized prompts
                                           ├── Language-dispatched splicer (done for Go)
                                           └── Language-dispatched repair
                      → COMPLEX → LeadContractor (cloud, language-aware)
```

The bypass (current state) is the safe default. MicroPrime Go support is an optimization to enable after cloud-path Go generation is proven.
