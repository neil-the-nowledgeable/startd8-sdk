# Neutral-Spine Enablers for Deterministic Polyglot Generation

> **Analysis + spec-seeds.** Grounded against the real code (file:line), not the docs' claims.
> Scope: the three plumbing gaps that keep the *language-agnostic spine* — contract IR, SARIF
> findings bus, finding->contract loop — from being fully neutral across all 5 languages.
> These are **spec-seeds**, sized for a `/reflective-requirements` pass, not full REQ docs.

## Framing: what "neutral spine" means here

Deterministic generation = **complete contract x total projection**. The projection back-half
is already language-parameterized in several places. The *spine* is the set of language-neutral
data structures and loops that carry a contract from extraction -> verification -> repair:

| Spine layer | Neutral IR | Status |
|---|---|---|
| **Element/manifest shape** | `code_manifest.Element` / `FileManifest` | Neutral — 5-language adapter exists (`languages/manifest_adapter.py`) |
| **Contract shape** | `forward_manifest.InterfaceContract` / `ForwardManifest` | Neutral shape; **extraction into it is partly Python-bound** (Enabler 1) |
| **Findings bus** | `coverage_map.render_sarif_from_findings` + `rule_catalog_base.RuleCatalog` | Neutral SINK exists; **toolchain diagnostics enter via per-language regex, not SARIF** (Enabler 2) |
| **Wire/interface layer** | proto/protoc + `proto_codegen/` | Neutral IDL exists; **renderer covers 2 of 5 languages** (Enabler 3) |

The recurring shape of all three gaps: **the IR is already neutral; the ingestion INTO it (or
the projection OUT of it) still carries the identity of the language it was born on** — exactly the
"generic mechanism secretly input-bound" pattern.

---

## Enabler 1 — Neutralize CONTRACT EXTRACTION

### Grounded current state

The premise ("`forward_manifest_extractor.py` extracts from Python only") is **half true
and needs splitting into two distinct paths.** There are two consumers of the extractor, with very
different neutrality status:

**Path A — DESIGN-time extraction from plan `api_signatures` (Python-bound).**
`DeterministicExtractor._extract_api_signatures` (`forward_manifest_extractor.py:722`) hard-gates on
Python extensions:

```
_PYTHON_EXTENSIONS = frozenset((".py", ".pyi"))          # :720
if ext not in self._PYTHON_EXTENSIONS: ... return []      # :732 — non-Python signatures dropped
parsed_sig = _parse_python_signature(sig_str)             # :825 — ast.parse (:264), Python-only
```

So when a plan declares `api_signatures` for a Go/Java/C#/Node target, **the signatures are logged
and dropped**; only the file gets an empty `ForwardFileSpec` via `_register_non_python_targets`
(`:693`). Design-time contract richness (the `InterfaceContract`s the drafter is shown) is Python-only.

**Path B — SOURCE-time reconciliation from existing files (already 4 languages).**
`SourceReconciler.reconcile` (`:1517`) is **not** Python-only. It discovers extensions from the
`LanguageRegistry` (`:1536-1546`) and dispatches:

```
if src_file.suffix == ".py":   _reconcile_file          # :1566 (AST)
elif ".go":                    _reconcile_go_file       # :1571 (go_parser, regex) — :1669
elif ".java":                  _reconcile_java_file     # :1574 — :1736
elif ".cs":                    _reconcile_csharp_file   # :1578 — :1805
```

Each produces real `FUNCTION_NAME`/`CLASS_NAME` `InterfaceContract`s (e.g. Go at `:1705-1732`).

**GROUNDING SURPRISE — does `manifest_adapter` already neutralize contract extraction? Partially, YES,
but for the OTHER half of the loop.** `manifest_adapter.py` bridges all 5 languages' parser output
into the `Element`/`FileManifest` shape (`build_multilang_file_manifest`, `:285`), and
`ForwardManifest.validate_implementation` (`forward_manifest.py:518`) **already consumes it
multi-language** — the *verify* side of the loop is neutral (Python authoritative; C#/Java
authoritative; Go/Node/Vue advisory, `parser_tier`-calibrated). So the forward-manifest **verify
loop already works for all 5 languages** against generated code. What is NOT neutral is the
**design-time production of `InterfaceContract`s from a plan** (Path A). The verify side reads the
adapter; the design side does not.

### The specific gap

- Path A (`_extract_api_signatures`) parses plan `api_signatures` with `_parse_python_signature`
  only. There is **no** `_parse_go_signature` / `_parse_java_signature` / etc., and no dispatch on
  the target file's language. A polyglot plan's non-Python signatures never become contracts.
- `manifest_adapter` cannot help here: it parses *source text*, whereas Path A parses *signature
  strings from a plan* (`getJSONLogger(name: str) -> logging.Logger`), which are not full source.
- Net effect: the drafter for a Go/Java/C#/Node feature is shown **empty element specs** and only
  `IMPORT_PATH`/`INFRASTRUCTURE` contracts (which are language-neutral and DO flow — `:910`, `:932`).
  The *structural* contract (which functions/classes must exist) is silent for 4 of 5 languages at
  design time.

### Proposed fix (spec-seed)

**"Language-dispatched signature parsing in the DeterministicExtractor."** Introduce a small
`SignatureParser` protocol (`parse(sig_str) -> ParsedSignature | None`) and a per-language registry,
mirroring the `LanguageProfile` pattern. Route on the target file's `detect_language(target)` (already
imported at `:705`) instead of the hard `_PYTHON_EXTENSIONS` gate:

- Python: wrap the existing `_parse_python_signature` (no behaviour change — NFR: byte-identical for
  `.py` targets).
- Go/Node: the per-language parsers already emit structured elements; add a **signature-string**
  parser that reuses their existing regex tokenizers (`go_parser`, `nodejs_parser`) on a
  single-declaration string. For Java/C#, a minimal name+params regex (advisory tier, matching
  `manifest_adapter`'s tier convention) is enough to populate `ForwardElementSpec.name` (the
  validator's match key).
- Keep the `InterfaceContract`/`ForwardElementSpec` shape unchanged — only the *producer* becomes
  language-aware. Reuse `manifest_adapter.PARSER_KIND_MAP` for kind translation so the two halves of
  the loop share one kind authority.
- Advisory tier honesty: non-Python parses that recover only a name (not params) still emit a
  contract + a name-only `ForwardElementSpec` (the verify side already tolerates advisory manifests).

### Effort estimate

**M (medium, ~2-3 days).** The shape/verify side is done; this is a bounded producer refactor plus 4
thin signature parsers (2 reuse existing tokenizers). Risk concentrated in the byte-identity guard for
the Python path and in not regressing `_link_methods_to_classes` (`:612`), which assumes Python `self`/
`cls` semantics — it must become a no-op (or language-parameterized) for non-Python files.

### How it plugs into the neutral spine

Closes the design-time half of the finding->contract loop: after this, a polyglot plan produces
non-empty structural contracts for all 5 languages, and `validate_implementation` (already neutral)
can enforce them. The loop becomes symmetric — neutral in, neutral out.

---

## Enabler 2 — Per-language TOOLCHAIN -> SARIF adapters

### Grounded current state

There **is** a real, neutral SARIF spine, but it is a **rendering SINK for already-classified
SDK-internal findings**, not an ingestion path for raw toolchain output.

- The universal sink: `coverage_map.render_sarif_from_findings` (`findings_sarif.py:75`) reads a
  duck-typed finding: rule-id from `.check/.check_type/.rule_id/.category` (`:65`), file from
  `.file_path/.file/...` (`:92`). Producer catalogs share `rule_catalog_base.RuleCatalog` (the
  rule-of-three distillation; 4th producer = `repair`, data-only). This is genuinely neutral.
- `repair/sarif.py:19` (`render_repair_sarif`) forwards `repair.models.Diagnostic` to that sink and
  stamps `helpUris` from `repair/rule_catalog.py`. Its rule-ids are the SDK's own categories:
  `syntax | import | lint | test | size | semantic | contract_violation | convention | security`
  (`rule_catalog.py:25-36`) — **not** compiler rule-ids like `CS0246`, `SA1200`, `staticcheck:SA4006`,
  `eslint:no-unused-vars`.

**Where the per-language parsing actually lives (the gap):** `repair/diagnostics.py` turns raw
toolchain text into typed `Diagnostic`s with **hand-written regex** and a **Python-flavored**
knowledge base:

```
_LINT_RULE   = re.compile(r"...(?P<rule>\w+)\s+(?P<message>.+)")   # :71  ruff-shaped
_IMPORT_MODULE = ...ModuleNotFoundError...                          # :61  Python tracebacks
_WELL_KNOWN_IMPORTS = { "Flask": ("flask","Flask"), ... }          # :82  Python packages only
fixable = bool(re.match(r"^(E[79]|F)\d+$", rule))                  # :298 ruff rule namespace
```

`classify_checkpoint_category` (`:157`) keys on checkpoint *name* substrings (`"ruff"`, `"pytest"`),
not on structured rule metadata. Then `repair/routing.py` routes on the resulting
`(category, semantic_subcategory)` tuples: `_ROUTING_TABLE` (`routing.py:124`) has ~40 rows keyed by
SDK category + a `route_lang` column, and every non-Python row exists because a per-language
`*_semantic_checks` validator (or regex diagnostic) already re-derived that category by hand.

So the picture is: **every language re-implements "parse my toolchain's diagnostics into the SDK's
private taxonomy."** SARIF — the literal compiler-diagnostics interchange format — is used only at the
*output* boundary (rendering findings for humans/CI), never at the *ingestion* boundary.

### The specific gap

- Routing keys on SDK-internal categories, so onboarding a new toolchain check means (a) teaching
  `diagnostics.py`/a validator to emit the right category, and (b) adding a `route_lang` row. Two
  drifting places per check, per language — the shotgun-surgery seam.
- The compiler/linter *already emits* a stable, namespaced rule-id (`CS0246`, `SA1200`, `SA4006`,
  `no-unused-vars`). The SDK throws it away and re-guesses a coarse category from message text.
- `rule_catalog_base` gives a ready home for cross-producer namespaced ids
  (`qualified_id = PRODUCER.rule_id`, `rule_catalog_base.py:75`) — but no producer represents a raw
  toolchain, so that authority is unused for compiler diagnostics.

### Proposed fix (spec-seed)

**"Toolchain->SARIF ingestion adapters + rule-id routing."** For each of `{go, java, csharp, nodejs}`
add a thin adapter that runs the toolchain in its native SARIF (or SARIF-adjacent structured) mode and
normalizes to the existing neutral finding shape:

- `golangci-lint run --out-format sarif`; `dotnet build` + Roslyn analyzers already emit SARIF;
  `eslint -f @microsoft/eslint-formatter-sarif`; Java via SpotBugs/Checkstyle SARIF or a
  `javac`-diagnostic -> SARIF shim. Where a toolchain lacks SARIF, wrap its structured output in the
  same `Finding` duck-type (`.rule_id`, `.file_path`, `.region`) so it flows through
  `render_sarif_from_findings` unchanged.
- Add a `toolchain` producer per language (or one `toolchain` catalog with a `domain` axis) to
  `rule_catalog_base`, cataloguing the rule-ids the SDK actually routes on (data-only add — the
  base validates no-dot + severity at import).
- Make `routing.py` route on **SARIF rule-id** (via a small `rule_id -> repair-step-sequence` map)
  layered over today's category routing. Rule-id is language-neutral through the catalog's
  `qualified_id`; the `route_lang` column collapses into the id namespace (`csharp.CS0246`), removing
  the per-language duplication.
- Keep `diagnostics.py`'s Python path as one such adapter (ruff/pytest already have SARIF formatters),
  so Python stops being special-cased.

### Effort estimate

**L (large, ~1-2 weeks).** Four toolchain integrations, each needing the tool present in the sandbox
(availability/version gating like `_java_parse_authoritative`), plus a routing-key migration behind a
compatibility shim (category routing stays as fallback so nothing regresses). The neutral sink and
catalog base already exist, which removes the hardest architectural work.

### How it plugs into the neutral spine

Turns the SARIF bus from an **output** format into the **ingestion** IR for the repair loop. After
this, repair *routing* — the last per-language-parsing holdout — keys on the compiler's own neutral
rule-id, so adding a check anywhere becomes a data-only catalog + one routing row, and a new language
inherits routing for free the moment its toolchain emits SARIF.

---

## Enabler 3 — Lean on proto/protoc for the free cross-language wire skeleton

### Grounded current state

`proto_codegen/` is a **real, shipped, deterministic ($0) IDL renderer** — and the Round-3 OB fleet
is entirely gRPC/proto-defined, so protoc already generates client/server stubs in all 5 languages.
What exists:

- `proto_parser.parse_proto` (`proto_parser.py`) — a minimal proto reader (services, RPCs incl.
  `stream`, `go_package`) — language-neutral.
- `engine.render_grpc_skeletons` (`engine.py:29`) — orchestrates `grpc.yaml` + `.proto` -> server
  skeletons.
- `ProtoSkeletonProvider` (`provider.py:12`) — registered as a **deterministic-file provider**
  (`proto-skeleton`), so the prime-contractor skip-hook already treats owned proto skeletons as
  `$0`-owned (no LLM). This is exactly the "protoc is a solved slice, don't LLM it" posture — **for
  the languages it covers.**

**The ceiling:** the renderer covers **2 of 5** languages.

```
_RENDERERS = {"python": ..., "go": ...}          # engine.py:13
_VALID_LANGS = frozenset({"python", "go"})        # grpc_manifest.py:11
# skeleton_python.py, skeleton_go.py exist; no java/csharp/nodejs skeleton renderer
```

So for Java/C#/Node services, the wire layer is **not** claimed by the deterministic provider and
falls back to LLM generation — even though `protoc --java_out / --csharp_out / --grpc-web_out` (and
`ts-proto` / `@grpc/grpc-js`) produce the stubs deterministically and for free.

### The specific gap

- The deterministic projector treats proto/protoc as a $0 slice for only Python+Go. The other 3
  languages re-pay LLM cost for a layer protoc already solves.
- The manifest hard-rejects `language` outside `{python, go}` (`grpc_manifest.py:11`), so a polyglot
  fleet can't even *declare* a Java/C#/Node gRPC service to the deterministic path.
- The `ProtoSkeletonProvider.owns` check (`is_owned_proto_skeleton`) only recognizes the shapes the 2
  renderers emit, so even a hand-added Java skeleton wouldn't be claimed as $0-owned.

### Proposed fix (spec-seed)

**"protoc as the wire-layer renderer; SDK renders only the service-internal skeleton around it."**
Formalize a two-band split for every gRPC service:

- **Band 1 — generated stubs (protoc-owned, $0):** invoke `protoc`/`ts-proto`/`grpc-js` to emit
  `*_pb2` / `*.pb.go` / `*Grpc.cs` / `*_pb.js` etc. These are byte-deterministic from the `.proto`;
  the projector should treat them as an owned deterministic artifact (extend `ProtoSkeletonProvider`
  to recognize protoc output by header/marker), never LLM them.
- **Band 2 — service-internal skeleton (SDK-rendered):** add `skeleton_java.py`, `skeleton_csharp.py`,
  `skeleton_nodejs.py` mirroring `skeleton_python.py`/`skeleton_go.py` — the servicer class that
  imports the Band-1 stub and stubs each RPC method. Expand `_RENDERERS`/`_DEFAULT_OUT`
  (`engine.py:13-20`) and `_VALID_LANGS` (`grpc_manifest.py:11`) to 5.
- Only the RPC *method bodies* (the actual business logic) remain for the LLM (bucket-3 integration)
  — the interface/wire layer is fully deterministic.
- Reuse `manifest_adapter`/`proto_parser` for the RPC list so the skeleton and the contract agree on
  the method set (ties Enabler 3 to the Enabler-1 contract shape: a proto RPC is already extracted as
  an `API_ENDPOINT` contract by `ProtoExtractor`, `forward_manifest_extractor.py:1075`).

### Effort estimate

**M (medium, ~3-4 days).** Three skeleton renderers (each analogous to the existing two) + manifest/
engine table widening + a protoc-invocation wrapper with availability gating. Lower risk than
Enabler 2 because the pattern is already proven twice and the provider/skip-hook plumbing exists.

### How it plugs into the neutral spine

Maximizes the $0 deterministic slice at the language boundary that is *most* language-neutral: the
wire contract. Every service in a polyglot fleet gets its interface layer for free, shrinking the
LLM's job to method bodies. It also feeds the contract IR: proto RPCs -> `API_ENDPOINT` contracts
(already) -> verified by the neutral `validate_implementation` (Enabler 1's verify side) -> repaired via
the neutral SARIF bus (Enabler 2). All three enablers meet at the proto-defined service.

---

## Leverage ranking

| Rank | Enabler | Why | Effort | Unblocks |
|---|---|---|---|---|
| **1** | **Enabler 3 — protoc wire layer** | Highest value-per-effort. Pattern proven twice; plumbing (provider + skip-hook) exists; converts the *most* language-neutral layer of a polyglot fleet to $0 for the 3 uncovered languages, directly shrinking LLM cost. Also the meeting point of all three loops. | M | The largest already-solved slice, immediately, for Java/C#/Node fleets |
| **2** | **Enabler 1 — contract extraction** | Makes the design-time contract non-empty for 4 of 5 languages, which is the precondition for meaningful verify+repair on non-Python code. Verify side already neutral, so this is a bounded producer refactor. | M | Structural enforcement on all 5 languages; without it, enablers 2-3 verify against empty contracts |
| **3** | **Enabler 2 — toolchain->SARIF** | Highest ceiling (fully neutralizes repair routing) but highest effort and external-tool dependency. The category-routing fallback already works per-language, so this is an *elegance/scalability* win more than an unblock. | L | Data-only onboarding of new checks/languages; removes the last per-language parsing seam |

**Net:** ship **Enabler 3** first (fast, high $0 payoff, low risk), then **Enabler 1** (unblocks
honest polyglot verification), then **Enabler 2** (the long-tail elegance play that makes the whole
loop maintainable). The three are complementary and converge on the proto-defined service as the
canonical neutral unit.

## Cross-cutting grounding notes

- **The IR is already more neutral than the framing assumed.** Both the *element/manifest* shape
  (`manifest_adapter`, 5 languages) and the *verify* side of the forward-manifest loop
  (`validate_implementation`, 5 languages, tier-calibrated) are done. The neutrality gaps are all at
  ingestion/projection edges, not in the core data structures.
- **`manifest_adapter` neutralizes the VERIFY side of contract extraction, not the DESIGN side.** The
  Enabler-1 premise conflated the two; the honest statement is: verify-against-code is
  neutral, produce-from-plan is Python-bound.
- **`SourceReconciler` already reconciles 4 languages** (`.py/.go/.java/.cs`), so "source->contract" is
  further along than "plan->contract." Node/Vue are the only reconcile gaps there.
- **The SARIF spine is an output sink, not an input IR** — the single most load-bearing correction for
  Enabler 2. `rule_catalog_base` is ready for a toolchain producer; nobody has written one.
