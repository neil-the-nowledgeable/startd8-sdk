# Plan Ingestion — Multi-Language Element Extraction Requirements

**Date:** 2026-03-19
**Status:** Draft
**Scope:** Enable MicroPrime element-level generation for Go, Java, Node.js, and C# by populating `ForwardFileSpec.elements` during plan ingestion PARSE and EMIT phases
**Depends On:** PLAN_INGESTION_MULTI_LANGUAGE_REQUIREMENTS.md (REQ-PLI-*), language profiles in `languages/`

---

## 1. Problem Statement

MicroPrime generates code at the **element level** — individual functions, methods, and classes. It needs `ForwardFileSpec.elements` populated with `ForwardElementSpec` entries to know what to generate. Without elements, the complexity classifier has no element metadata and routes everything to COMPLEX → Primary Contractor cloud path.

**Current state:** Elements are populated for Python only. All other languages get `elements=[]`, making MicroPrime element-level generation impossible.

### Root Cause Chain

```
PARSE Phase (LLM)
  → api_signatures: ["func GetQuote(items []Item) Money", "class AdService"]
     ↓
_extract_api_signatures() in forward_manifest_extractor.py
  → Line 625: if ext not in _PYTHON_EXTENSIONS: return []   ← BLOCKS ALL NON-PYTHON
     ↓
ForwardFileSpec.elements = []   ← EMPTY for Go, Java, Node.js, C#
     ↓
MicroPrime sees 0 elements → no element-level generation possible
     ↓
Classifier routes to COMPLEX → cloud-only generation ($$$)
```

### Two Element Sources

Elements can come from two places during plan ingestion:

| Source | When Available | Quality | Current Status |
|--------|---------------|---------|---------------|
| **PARSE LLM output** (`api_signatures`) | Always (LLM extracts from plan text) | Medium — LLM may hallucinate signatures | Python: parsed; Others: discarded |
| **Existing source code** (AST/regex parsers) | Only for edit-mode (files already exist) | High — ground truth from code | Go/Java: contracts only, not elements |

For **create-mode** (new files), PARSE LLM output is the only source. For **edit-mode**, existing source code should take precedence.

---

## 2. Requirements

### Layer 1: Multi-Language Signature Parsing (Foundation)

#### REQ-EE-100: Language-Dispatched Signature Parsing

`_extract_api_signatures()` in `forward_manifest_extractor.py` MUST dispatch to language-specific signature parsers instead of skipping non-Python files:

```python
def _extract_api_signatures(self, feature, file_elements):
    if not feature.target_files:
        return []
    ext = Path(feature.target_files[0]).suffix.lower()
    lang = detect_language(feature.target_files[0])

    if lang == "python" or ext in self._PYTHON_EXTENSIONS:
        return self._parse_python_signatures(feature, file_elements)
    elif lang == "go":
        return self._parse_go_signatures(feature, file_elements)
    elif lang == "java":
        return self._parse_java_signatures(feature, file_elements)
    elif lang == "nodejs":
        return self._parse_nodejs_signatures(feature, file_elements)
    elif lang == "csharp":
        return self._parse_csharp_signatures(feature, file_elements)
    else:
        # Non-decomposable files (Dockerfile, YAML, etc.)
        return []
```

**Why:** The current `return []` at line 625 discards all element information for non-Python languages. The LLM already extracts `api_signatures` (e.g., `"func GetQuote(items []Item) Money"`) — they just need language-appropriate parsing.

**Acceptance:** A Go feature with `api_signatures: ["func GetQuote(items []Item) Money"]` produces a `ForwardElementSpec(kind=FUNCTION, name="GetQuote")` in the manifest.

---

#### REQ-EE-101: Go Signature Parser

`_parse_go_signatures()` MUST parse Go function and type signatures from `api_signatures` strings:

**Input patterns:**
```
func GetQuote(items []*pb.CartItem, currency string) *pb.Money
func (s *ShippingService) ShipOrder(ctx context.Context, req *pb.ShipOrderReq) (string, error)
type ShippingService struct
interface CartStore
```

**Parsing rules:**
- `func Name(params) returns` → `ForwardElementSpec(kind=FUNCTION, name="Name")`
- `func (recv) Name(params) returns` → `ForwardElementSpec(kind=METHOD, name="Name", parent_class=recv_type)`
- `type Name struct` → `ForwardElementSpec(kind=CLASS, name="Name")`
- `type Name interface` → `ForwardElementSpec(kind=CLASS, name="Name", is_abstract=True)`

**Minimum viable:** Extract `kind` and `name`. Full `Signature` with typed params is desirable but not required for MicroPrime routing — MicroPrime needs the element inventory, not the exact parameter types.

**Status:** NOT IMPLEMENTED — `go_parser.py:parse_go_source()` parses source code but not plan-extracted signature strings

---

#### REQ-EE-102: Java Signature Parser

`_parse_java_signatures()` MUST parse Java class, method, and interface signatures:

**Input patterns:**
```
public class AdService extends AdServiceGrpc.AdServiceImplBase
public void getAds(AdRequest request, StreamObserver<AdResponse> responseObserver)
public static void main(String[] args)
interface CartStore
public record Ad(String redirectUrl, String text)
```

**Parsing rules:**
- `class Name [extends Base] [implements Iface]` → `ForwardElementSpec(kind=CLASS, name="Name", bases=[Base, Iface])`
- `[modifiers] type Name(params)` → `ForwardElementSpec(kind=METHOD, name="Name")`
  - If `static` present → `is_static=True`
  - Determine parent_class from context or dotted name: `AdService.getAds` → parent_class=`AdService`
- `interface Name` → `ForwardElementSpec(kind=CLASS, name="Name", is_abstract=True)`
- `record Name(...)` → `ForwardElementSpec(kind=CLASS, name="Name")`
- `enum Name` → `ForwardElementSpec(kind=CLASS, name="Name")`

**Status:** NOT IMPLEMENTED — `java_parser.py:parse_java_source()` parses source code but not signature strings

---

#### REQ-EE-103: Node.js Signature Parser

`_parse_nodejs_signatures()` MUST parse JavaScript/TypeScript function, class, and export signatures:

**Input patterns:**
```
function chargeServiceHandlers(charge)
async function main()
class CurrencyConverter
const convert = (from, to, amount) => Money
module.exports = { chargeServiceHandlers }
export default class PaymentService
export function processPayment(request: PaymentRequest): PaymentResponse
```

**Parsing rules:**
- `[async] function Name(params)` → `ForwardElementSpec(kind=FUNCTION, name="Name")`
- `class Name [extends Base]` → `ForwardElementSpec(kind=CLASS, name="Name", bases=[Base])`
- `const Name = (params) =>` → `ForwardElementSpec(kind=FUNCTION, name="Name")`
- `export [default] function/class Name` → same as above, mark `visibility=PUBLIC`
- `Name.prototype.method = function` → `ForwardElementSpec(kind=METHOD, name="method", parent_class="Name")`

**Simplification:** Node.js has high syntactic ambiguity (arrow functions, destructured exports, IIFE patterns). The parser should handle the **common 80%** and skip exotic patterns rather than attempting exhaustive coverage.

**Status:** NOT IMPLEMENTED

---

#### REQ-EE-104: C# Signature Parser

`_parse_csharp_signatures()` MUST parse C# class, method, interface, and record signatures:

**Input patterns:**
```
public class CartService : Hipstershop.CartService.CartServiceBase
public override async Task<Empty> AddItem(AddItemRequest request, ServerCallContext context)
public interface ICartStore
public record CartItem(string ProductId, int Quantity)
public static class HealthService
```

**Parsing rules:**
- `class Name [: Base, IFace]` → `ForwardElementSpec(kind=CLASS, name="Name", bases=[Base, IFace])`
- `[modifiers] ReturnType Name(params)` → `ForwardElementSpec(kind=METHOD, name="Name")`
  - `static` → `is_static=True`; `abstract` → `is_abstract=True`; `async` detected from `async Task<T>` return
  - parent_class from context or dotted name
- `interface IName` → `ForwardElementSpec(kind=CLASS, name="IName", is_abstract=True)`
- `record Name(props)` → `ForwardElementSpec(kind=CLASS, name="Name")`
- `enum Name` → `ForwardElementSpec(kind=CLASS, name="Name")`

**Status:** NOT IMPLEMENTED — `csharp_parser.py` exists but is for source code validation, not signature string parsing

---

### Layer 2: Source Code Element Extraction (Edit-Mode)

#### REQ-EE-200: Reconcile Existing Source into ForwardFileSpec.elements

When existing source code is available (edit-mode), the EMIT phase MUST populate `ForwardFileSpec.elements` from the language parser output, not just contracts:

**Current flow (broken):**
```
parse_go_source(code) → List[GoElement]
  → converted to InterfaceContract only
  → file_elements[path] stays empty
```

**Target flow:**
```
parse_go_source(code) → List[GoElement]
  → converted to InterfaceContract (for validation)
  → ALSO converted to ForwardElementSpec (for MicroPrime)
  → file_elements[path] = [ForwardElementSpec(...), ...]
```

**Implementation:** Add `_convert_to_element_specs()` converters:

```python
def _go_element_to_spec(el: GoElement) -> ForwardElementSpec:
    return ForwardElementSpec(
        kind=_GO_KIND_MAP[el.kind],
        name=el.name,
        parent_class=el.receiver_type,
        decomposition_source="source-go-parser",
    )

def _java_element_to_spec(el: JavaElement) -> ForwardElementSpec:
    return ForwardElementSpec(
        kind=_JAVA_KIND_MAP[el.kind],
        name=el.name,
        parent_class=el.parent_class,
        bases=el.extends + el.implements if hasattr(el, 'extends') else [],
        is_static=el.is_static,
        is_abstract=el.is_abstract,
        decomposition_source="source-java-parser",
    )
```

**Why:** Source-code-derived elements are higher quality than PARSE-derived (no hallucination risk). When available, they should be the primary element source.

**Precedence:** Source code elements > PARSE LLM elements. When both exist for the same file:
- Use source code elements (higher fidelity)
- Merge any PARSE-only elements that don't exist in source (new methods being added)

**Status:** NOT IMPLEMENTED for any language

---

#### REQ-EE-201: Node.js Regex Element Extractor

A `parse_nodejs_source()` function MUST extract structural elements from JavaScript/TypeScript source code using regex patterns (no AST — Node.js has no Python-native parser):

**Target elements:**
```python
@dataclass
class NodeElement:
    kind: str        # "function", "class", "method", "const_function"
    name: str
    is_async: bool
    is_exported: bool
    line: int
    parent_class: Optional[str] = None
```

**Regex patterns:**
```python
# Function declarations
r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\('

# Class declarations
r'(?:export\s+)?(?:default\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?'

# Arrow function assignments
r'(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>'

# Method declarations (inside class body)
r'(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{'
```

**Complexity budget:** ~100 lines. Handle the common patterns; skip edge cases (computed property names, Symbol-keyed methods, generators).

**Status:** NOT IMPLEMENTED

---

#### REQ-EE-202: C# Element Extraction from tree-sitter

When `tree-sitter-c-sharp` is available, `parse_csharp_source()` SHOULD use it to extract structural elements:

**Target elements:** Classes, interfaces, records, enums, methods, properties (top-level and nested).

**Fallback:** When tree-sitter is not installed, use regex extraction (same pattern as Go/Node.js). The regex fallback catches `class`, `interface`, `record`, `enum`, and method declarations.

**Status:** NOT IMPLEMENTED — `csharp_parser.py` has `validate_csharp_syntax()` but no element extraction

---

### Layer 3: PARSE Prompt Enhancement

#### REQ-EE-300: Language-Specific api_signatures Guidance in PARSE Prompt

The PARSE prompt MUST include language-specific examples for `api_signatures` based on the detected plan language:

**Go examples:**
```
"api_signatures": [
  "func GetQuote(items []*pb.CartItem, currency string) *pb.Money",
  "func (s *ShippingService) ShipOrder(ctx context.Context, req *pb.ShipOrderReq) (string, error)",
  "type ShippingService struct"
]
```

**Java examples:**
```
"api_signatures": [
  "public class AdService extends AdServiceGrpc.AdServiceImplBase",
  "public void getAds(AdRequest request, StreamObserver<AdResponse> responseObserver)",
  "public static void main(String[] args)"
]
```

**Node.js examples:**
```
"api_signatures": [
  "function chargeServiceHandlers(charge)",
  "async function main()",
  "class CurrencyConverter",
  "const convert = (from, to, amount) => Money"
]
```

**C# examples:**
```
"api_signatures": [
  "public class CartService : CartServiceBase",
  "public override async Task<Empty> AddItem(AddItemRequest request, ServerCallContext context)",
  "public interface ICartStore"
]
```

**Implementation:** Inject language-specific `{api_signature_examples}` into the PARSE prompt template via the existing `{language_specific_fields}` mechanism (REQ-PLI-201).

**Why:** The LLM's api_signatures quality depends heavily on the examples shown. Python-style examples cause the LLM to write `"def get_ads(request, context)"` for Java code instead of `"public void getAds(AdRequest request, StreamObserver<AdResponse> responseObserver)"`.

**Status:** NOT IMPLEMENTED — PARSE prompt has no language-specific signature examples

---

#### REQ-EE-301: Structured Element Extraction in PARSE

As an **alternative or supplement** to free-text `api_signatures`, the PARSE prompt MAY request structured element declarations:

```json
{
  "elements": [
    {
      "name": "AdService",
      "kind": "class",
      "extends": "AdServiceGrpc.AdServiceImplBase",
      "methods": ["getAds", "main"]
    },
    {
      "name": "getAds",
      "kind": "method",
      "parent": "AdService",
      "params": ["AdRequest request", "StreamObserver<AdResponse> responseObserver"],
      "returns": "void"
    }
  ]
}
```

**Trade-off:** Structured output is more reliable for parsing but increases prompt size and LLM token cost. For P1, free-text `api_signatures` with language-specific examples (REQ-EE-300) is sufficient.

**Priority:** P3 — evaluate after REQ-EE-100 through REQ-EE-104 are validated

**Status:** NOT IMPLEMENTED

---

### Layer 4: Decomposition Source Tracking

#### REQ-EE-400: Set `decomposition_source` on ForwardElementSpec

Every `ForwardElementSpec` created during plan ingestion MUST have `decomposition_source` set:

| Source | Value | Meaning |
|--------|-------|---------|
| PARSE LLM api_signatures | `"parse-llm"` | Element inferred from plan text by LLM |
| Source code parser (Go) | `"source-go-parser"` | Element extracted from existing `.go` file |
| Source code parser (Java) | `"source-java-parser"` | Element extracted from existing `.java` file |
| Source code parser (Node.js) | `"source-nodejs-regex"` | Element extracted from existing `.js`/`.ts` file |
| Source code parser (C#) | `"source-csharp-treesitter"` or `"source-csharp-regex"` | Element extracted from existing `.cs` file |
| Template match | `"template"` | Element matched a known template (already set by MicroPrime) |

**Why:** Downstream consumers (MicroPrime, postmortem, Kaizen) need to know where an element came from to calibrate trust. PARSE-derived elements may have hallucinated signatures; source-derived elements are ground truth.

**Status:** NOT IMPLEMENTED — field exists on `ForwardElementSpec` but is never set during plan ingestion

---

## 3. Implementation Plan

### Phase 1: Signature String Parsers (enables PARSE → elements for all languages)

| Step | REQ | Description | Files | Effort |
|------|-----|-------------|-------|--------|
| S-1 | EE-100 | Language-dispatch in `_extract_api_signatures()` | `forward_manifest_extractor.py` | ~20 lines |
| S-2 | EE-101 | Go signature string parser | `forward_manifest_extractor.py` | ~60 lines |
| S-3 | EE-102 | Java signature string parser | `forward_manifest_extractor.py` | ~80 lines |
| S-4 | EE-103 | Node.js signature string parser | `forward_manifest_extractor.py` | ~50 lines |
| S-5 | EE-104 | C# signature string parser | `forward_manifest_extractor.py` | ~70 lines |
| S-6 | EE-400 | Set `decomposition_source="parse-llm"` on all PARSE-derived elements | `forward_manifest_extractor.py` | ~5 lines |
| S-7 | — | Tests for all 4 parsers | `tests/unit/` | ~200 lines |

**~485 lines. Enables element population from LLM PARSE output for all languages.**

### Phase 2: Source Code → Elements (enables edit-mode element extraction)

| Step | REQ | Description | Files | Effort |
|------|-----|-------------|-------|--------|
| R-1 | EE-200 | Go `GoElement` → `ForwardElementSpec` converter | `forward_manifest_extractor.py` | ~30 lines |
| R-2 | EE-200 | Java `JavaElement` → `ForwardElementSpec` converter | `forward_manifest_extractor.py` | ~30 lines |
| R-3 | EE-200 | Wire converters into reconciliation path | `forward_manifest_extractor.py` | ~20 lines |
| R-4 | EE-201 | Node.js regex element extractor | `languages/nodejs_parser.py` (new) | ~100 lines |
| R-5 | EE-202 | C# element extraction (tree-sitter + regex fallback) | `languages/csharp_parser.py` | ~80 lines |
| R-6 | — | Source precedence logic (source > PARSE, merge new) | `forward_manifest_extractor.py` | ~30 lines |
| R-7 | — | Tests for converters and extractors | `tests/unit/` | ~200 lines |

**~490 lines. Enables high-fidelity element extraction from existing code.**

### Phase 3: PARSE Prompt Enhancement

| Step | REQ | Description | Files | Effort |
|------|-----|-------------|-------|--------|
| P-1 | EE-300 | Language-specific api_signature examples | `plan_ingestion_workflow.py` or YAML template | ~40 lines |
| P-2 | — | Test: verify Java plan produces Java-style signatures | `tests/unit/workflows/` | ~30 lines |

**~70 lines. Improves LLM signature extraction quality.**

### Total: ~1,045 lines across 3 phases

---

## 4. Priority Ordering

**P0 — Phase 1 (signature parsers):** Enables MicroPrime for all languages using data the LLM already produces. This is the highest-ROI change — it unblocks element-level generation without any new infrastructure.

**P1 — Phase 3 (PARSE prompt):** Improves signature quality so the parsers have better input. Should be done alongside or immediately after Phase 1.

**P2 — Phase 2 (source extractors):** Edit-mode enhancement. Only matters when generating code that modifies existing files. Lower priority for greenfield projects like Online Boutique.

---

## 5. Expected Impact

### Before (current state)

| Language | Elements in Manifest | MicroPrime Path | Cost per Feature |
|----------|---------------------|-----------------|-----------------|
| Python | Yes (from PARSE) | Element-level | ~$0.00 (Ollama) |
| Go | **0** | File-whole cloud | ~$0.50 |
| Java | **0** | File-whole cloud | ~$0.50 |
| Node.js | **0** | File-whole cloud | ~$0.50 |
| C# | **0** | File-whole cloud | ~$0.50 |

### After (Phase 1 implemented)

| Language | Elements in Manifest | MicroPrime Path | Cost per Feature |
|----------|---------------------|-----------------|-----------------|
| Python | Yes (from PARSE) | Element-level | ~$0.00 (Ollama) |
| Go | **Yes (from PARSE)** | **Element-level** | **~$0.00 (Ollama)** |
| Java | **Yes (from PARSE)** | **Element-level** | **~$0.00 (Ollama)** |
| Node.js | **Yes (from PARSE)** | **Element-level** | **~$0.00 (Ollama)** |
| C# | **Yes (from PARSE)** | **Element-level** | **~$0.00 (Ollama)** |

**Cost reduction:** ~$0.50 → ~$0.00 per feature for SIMPLE/MODERATE elements routed to Ollama. COMPLEX elements still use cloud.

---

## 6. ForwardElementSpec Minimum Viable Fields

For MicroPrime routing, the **minimum** fields needed per element are:

| Field | Required | Used By |
|-------|----------|---------|
| `kind` | Yes | Classifier (FUNCTION vs CLASS routing), template matching |
| `name` | Yes | Registry lookup, logging, code generation |
| `parent_class` | For methods | Classifier (method complexity), splicer (target class) |
| `signature` | Desirable | Spec prompt (parameter types), but can be None |
| `bases` | For classes | Template matching (e.g., gRPC base class detection) |
| `is_static` | Desirable | Classifier signal, generation guidance |
| `is_abstract` | Desirable | Skip generation for abstract methods |
| `decomposition_source` | Desirable | Trust calibration, postmortem analysis |

**Implication:** Phase 1 parsers only need to reliably extract `kind`, `name`, and `parent_class`. Full `Signature` parsing (with typed parameters) is nice-to-have but not blocking.

---

## 7. Risks

### Risk 1: LLM Signature Hallucination

The LLM may invent method signatures that don't match what the code should actually contain. Mitigation:
- Phase 2 (source code extraction) overrides PARSE-derived elements for edit-mode
- MicroPrime already handles missing/wrong element specs via escalation (K-6 contract)
- `decomposition_source="parse-llm"` flags low-trust elements for downstream consumers

### Risk 2: Regex Parser False Positives

Non-Python signature parsers are regex-based and may mis-parse complex generics, lambdas, or annotation-heavy signatures. Mitigation:
- Parse conservatively: skip ambiguous patterns rather than guessing
- MicroPrime fallback: if an element can't be generated locally, escalate to cloud
- Log parsing failures at WARNING level for Kaizen analysis

### Risk 3: Element Count Inflation

A file with 20 elements generates 20 MicroPrime calls. For small Ollama models, this may produce lower quality than a single file-whole cloud call. Mitigation:
- Classifier already routes COMPLEX elements to cloud
- MODERATE elements use file-whole Ollama (not per-element)
- Only SIMPLE elements get per-element generation

### Risk 4: Non-Code Files with Signatures

Plan text like "the config file defines MAX_CONNECTIONS" may produce `api_signatures: ["MAX_CONNECTIONS: int = 100"]` for a `.yaml` or `.properties` file. Mitigation:
- Signature parsers are gated by language detection — non-code languages still return `[]`
- Only `.go`, `.java`, `.js`/`.ts`, `.cs`, `.py` trigger parsing
