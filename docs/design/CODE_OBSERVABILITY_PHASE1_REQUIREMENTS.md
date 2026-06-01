# Code Observability — Phase 1 Requirements (`CodeGraph` IR + Python/Go Backends + OTel Emission)

> **⛔ SUPERSEDED (2026-06-01)** by `CODE_KNOWLEDGE_GRAPH_PHASE1_REQUIREMENTS.md`. The substrate
> here (tree-sitter-everywhere + OTel-traces-as-store, Python/Go-first) was the "throw-one-away"
> prototype. Kept for the rationale and the REQ-MIE acceptance ideas that carried forward; do not
> implement against this doc. See `CODE_KNOWLEDGE_GRAPH_DESIGN.md` §0 for what changed and why.

> **Version:** 0.1 (DRAFT — informed by the Phase 0 spike, not yet CRP-reviewed)
> **Date:** 2026-06-01
> **Status:** Draft for review
> **Component:** startd8 SDK — new `code_observability/` module + `languages/` backends + `forward_manifest_extractor.py` integration
> **Principle:** [MIERUKA_DESIGN_PRINCIPLE.md](../design-princples/MIERUKA_DESIGN_PRINCIPLE.md)
> **Parent design:** [CODE_OBSERVABILITY_DESIGN.md](./CODE_OBSERVABILITY_DESIGN.md)
> **Phase 0 evidence:** `scripts/spikes/code_observability/PHASE0_FINDINGS.md`

---

## Table of Contents

1. [Overview & Scope](#1-overview--scope)
2. [Planning Insights (from Phase 0)](#2-planning-insights-from-phase-0)
3. [CodeGraph IR (REQ-MIE-1xx)](#3-codegraph-ir-req-mie-1xx)
4. [Extraction Backends (REQ-MIE-2xx)](#4-extraction-backends-req-mie-2xx)
5. [OTel Emission (REQ-MIE-3xx)](#5-otel-emission-req-mie-3xx)
6. [Pre-Generation Integration (REQ-MIE-4xx)](#6-pre-generation-integration-req-mie-4xx)
7. [Dependencies & Infrastructure (REQ-MIE-5xx)](#7-dependencies--infrastructure-req-mie-5xx)
8. [Non-Functional Requirements (NFR)](#8-non-functional-requirements-nfr)
9. [Non-Requirements (Out of Scope)](#9-non-requirements-out-of-scope)
10. [Traceability Matrix](#10-traceability-matrix)
11. [Verification Strategy](#11-verification-strategy)
12. [Open Questions](#12-open-questions)

---

## 1. Overview & Scope

Phase 1 delivers the **observable model and its transport** — the foundation every later
capability rides on. It does **not** deliver graph-aware splicing (Phase 2) or path-based
security validation (Phase 3); it makes those possible by locking the IR and the DATAFLOW
emission contract they will consume.

**Phase 1 ships:**

| Deliverable | Where |
|---|---|
| `CodeGraph` / `CodeElement` / `CodeEdge` typed IR (Keiyaku contract) | new `src/startd8/code_observability/graph.py` |
| Python extraction backend (native `ast`) | `code_observability/backends/python_backend.py` |
| Go extraction backend (tree-sitter) | `code_observability/backends/go_backend.py` |
| OTel emitter (metrics + call-graph traces + DATAFLOW representation) | `code_observability/emit.py` |
| Pre-generation target index wired into the forward manifest | `forward_manifest_extractor.py` integration point |
| Dependency-pin resolution (tree-sitter vs codebleu) | `pyproject.toml` + extractor env strategy |

The Phase 0 spike (`scripts/spikes/code_observability/`) is the **executable prototype** of
these; Phase 1 productizes it inside the SDK with a stable contract, cardinality controls,
and tests. Spike code is reference, not the shipped module.

### Current State → Gap

| Concern | Current | Phase 1 Gap to Close |
|---|---|---|
| Structural model | Per-language, divergent depth (Python AST; Go regex via `go_parser.py` — **0 call edges**, per its own docstring) | One `CodeGraph` IR; Go gets real call/dataflow edges via tree-sitter |
| Cross-file edges | None | `CALLS`, `IMPORTS`, `REFERENCES`, `DATAFLOW` (coarse) captured |
| Code as telemetry | Not emitted | `code_*` metrics + call-graph traces on the existing OTel stack |
| Pre-gen understanding | `forward_manifest_extractor.py` re-extracts shallowly | Consumes `CodeGraph` of the existing target |

---

## 2. Planning Insights (from Phase 0)

> The Phase 0 spike *was* the reflective planning pass. These empirical findings reshape the
> requirements before any production code is written.

| Pre-spike assumption | Phase 0 finding | Requirement impact |
|---|---|---|
| TraceQL span-link traversal can express data-flow taint | **PARTIAL** — `>>` traverses span *nesting* (CALLS), not *links* (DATAFLOW); no transitive link-chase; can't distinguish call from value-flow | DATAFLOW is **data in the IR + a documented attribute contract** (REQ-MIE-330), *not* a query-language feature. The traversal helper is **Phase 2**, but Phase 1 must lock the contract it consumes. |
| OTel span Links cleanly model dataflow edges | Links require the **target SpanContext to already exist** — a top-down call tree can't link to unborn children | REQ-MIE-320 forces an explicit choice: two-pass span-id pre-allocation vs. resolved-ID attributes. |
| tree-sitter installs cleanly | `tree-sitter-go` 0.25 needs core ≥0.25 (ABI 15); a `codebleu` pin requires `<0.23` | REQ-MIE-500 (dependency resolution) is a **blocking** Phase 1 item, not cleanup. |
| Cardinality is a "later" concern | Spans scale ~1:1 with functions; per-element gauge labels multiply Mimir cardinality | NFR-2 cardinality controls are **in-scope for Phase 1**, baked into the emission contract. |
| Coarse reachability ≈ the value-add | The coarse `>>` filter works against live Tempo, but the *value over today's regex* is **precise taint**, which needs flow-sensitive extraction | REQ-MIE-230 makes Go dataflow extraction quality an explicit, measured requirement; the risk is concentrated here. |

**Validated and retained:** the end-to-end pipeline (tree-sitter → `CodeGraph` → OTel →
TraceQL) ran against a live Tempo/Mimir/Loki/Grafana stack; `{ span.code.is_source = true }
>> { span.code.is_sink = true }` returned exactly the tainted trace and excluded the safe
parameterized path. Phase 1 preserves this as the coarse Layer-3 filter.

---

## 3. CodeGraph IR (REQ-MIE-1xx)

### REQ-MIE-100: Typed `CodeGraph` contract
Define Pydantic models `CodeGraph`, `CodeElement`, `CodeEdge` as a **Keiyaku-compliant**
typed contract (per the project's A2A boundary policy). `CodeGraph` is the single value
passed across extractor → emitter → (future) splicer/validator boundaries.

- `CodeElement`: `id` (stable, see REQ-MIE-110), `kind` ∈ {`module`,`class`,`function`,`method`,`field`}, `language`, `file` (repo-relative), `span` (start/end line), `signature` (string), `is_stub` (bool), optional `docstring`/contract, free-form `attributes: dict`.
- `CodeEdge`: `src_id`, `dst_id`, `kind` ∈ {`CALLS`,`IMPORTS`,`DEFINES`,`INHERITS`,`REFERENCES`,`DATAFLOW`}, `attributes: dict` (e.g. dataflow `via` param, call-site line).
- `CodeGraph`: `elements: list[CodeElement]`, `edges: list[CodeEdge]`, `language`, `source_fingerprint` (checksum set), `schema_version` (semver string).

**Acceptance:** round-trips to/from JSON; schema_version present; mypy-clean.

### REQ-MIE-110: Stable element IDs
Element `id` MUST be deterministic and stable across re-extraction of unchanged code —
derived from `(repo-relative file path, fully-qualified symbol name, kind)`, NOT line
numbers (which churn on edits). Required so incremental re-extraction and cross-run diffing
(Kaizen) are possible.

**Acceptance:** editing an unrelated function does not change the `id` of its neighbors.

### REQ-MIE-120: Stub awareness
`CodeElement.is_stub` MUST be populated using the per-language `stub_patterns` already
defined on `LanguageProfile` (e.g. Go `panic("not implemented")`, Python `raise NotImplementedError`). This is the bridge to `code_stub_count` (REQ-MIE-310) and Kaizen.

### REQ-MIE-130: Schema versioning + persistence
`CodeGraph` MUST carry a `schema_version` and be persistable to `.startd8/state/` as a
Mottainai artifact (built once, reused across phases). Follow the existing 3-layer resume
validation pattern (schema version → source checksum → per-element fingerprint).

---

## 4. Extraction Backends (REQ-MIE-2xx)

### REQ-MIE-200: Backend Protocol
Define a `CodeGraphBackend` Protocol (mirroring `LanguageProfile`) with one method:
`extract(files: list[Path]) -> CodeGraph`. Backends are resolved per dominant language using
the existing `resolve_language()` machinery. Add an optional `code_graph_backend` member to
each `LanguageProfile`.

### REQ-MIE-210: Python backend (native `ast` + stdlib resolution)
Implement `PythonBackend` over the stdlib `ast` module, reusing logic from
`utils/code_manifest.py`. MUST emit `DEFINES`, `IMPORTS`, `INHERITS`, and `CALLS` edges, and
populate signatures from `ast` argument nodes (`ast.unparse` for reconstruction).

Python is the **high-fidelity reference lane**: unlike tree-sitter (parse-only), Python can
resolve names natively. The backend SHOULD use stdlib **`symtable`** (intra-module scope/name
binding) and **`importlib.util.find_spec`** (cross-file import → path resolution) to produce
*resolved* `CALLS` edges, not just syntactic ones. The existing bytecode/`dis` path in
`code_manifest` (v1.4.0) MAY refine call resolution where code is importable, but MUST NOT be
required (it needs executable, side-effect-safe code). See RT-D4 for the resolver decision
(stdlib + Jedi/astroid vs. a shared stack-graphs resolver).

**Caveat (links NFR-1):** native `ast` raises `SyntaxError` on incomplete code and is bound to
the running interpreter's grammar. For partial/inner-loop Python, prefer the tree-sitter path;
reserve native `ast`+stdlib for the **complete target index** (REQ-MIE-400). The Python lane is
therefore *also* a hybrid, not ast-only.

**Acceptance:** on a fixture with a 3-level cross-file call chain, all call edges are resolved
to their target declarations (not just present as syntactic calls).

### REQ-MIE-220: Go backend (tree-sitter)
Implement `GoBackend` over `tree-sitter` + `tree-sitter-go`, productizing the spike's
`extractor.py`. MUST extract functions/methods/types and emit `CALLS` edges from function
bodies (the precise gap vs. regex `go_parser.py`, which emits **0** call edges).

**Acceptance:** on the spike fixture, ≥5 `CALLS` edges and correct nested-call resolution;
parses **incomplete/non-compiling** Go without error (partial-file tolerance, NFR-1).

### REQ-MIE-230: Go DATAFLOW extraction (coarse, measured)
`GoBackend` MUST emit coarse `DATAFLOW` edges where a value passes from one function into
another (argument flow) and tag elements with `is_source`/`is_sink` markers (untrusted-input
readers; raw-SQL / exec sinks). This is intentionally **coarse** in Phase 1; precision
(flow-sensitivity, sanitizer awareness) is Phase 2/3.

- MUST NOT flag the parameterized/safe path (the spike's `execSQLParams`) as a sink-reaching source.

**Acceptance:** on the spike fixture, the tainted source→sink path is present in the edge
set and the safe path is absent; false-positive rate on the fixture = 0. The doc MUST state
plainly that this is candidate-level, not proof-level, taint (de-risking note from §2).

### REQ-MIE-240: Backend fallback
If a backend's parser/grammar is unavailable at runtime, extraction MUST degrade to an empty
-but-valid `CodeGraph` with a logged warning (never raise into the pipeline). Mirrors the Go
tooling "assume best-effort" fallback already used for `gofmt`/`goimports`.

---

## 5. OTel Emission (REQ-MIE-3xx)

### REQ-MIE-300: Emit via existing OTel infrastructure
Emission MUST use `otel.py` / `logging_otel.py` and the ContextCore span conventions
(SpanState v2). No parallel telemetry system. Exporter selection: OTLP if an endpoint is
reachable, else console; always mirror to JSON for offline inspection (per the spike).

### REQ-MIE-310: Structural metrics
Emit the `code_*` gauge family, dimensioned by `run_id`, `commit`, `language`, and (subject
to NFR-2) `module`:
`code_element_count`, `code_fan_in`, `code_fan_out`, `code_stub_count`,
`code_unresolved_import_count`, `code_duplicate_definition_count`.

**Acceptance:** datapoints land in Mimir (or JSON in offline mode); names use the `code_` prefix.

### REQ-MIE-320: Call-graph traces + span-link decision
Emit the `CALLS` graph as a span tree (root = entrypoint, children = callees), one connected
trace per entrypoint, so TraceQL `>>` works (validated in Phase 0). **Phase 1 MUST decide
and document** the DATAFLOW representation (Phase 0 OQ#6):
- **(a)** native OTel span Links via two-pass span-id pre-allocation, OR
- **(b)** resolved-target-span-id **attributes** (the spike's approach), traversed by the
  Phase 2 graph helper.

Decision is recorded in REQ-MIE-330; either way the attribute `span.code.dataflow_target` (or Link) MUST be present and resolvable.

### REQ-MIE-330: DATAFLOW emission contract (locked for Phase 2)
The DATAFLOW representation MUST be specified as a stable contract that the Phase 2
graph-traversal helper consumes, including: span attributes `span.code.is_source`,
`span.code.is_sink`, `span.code.element_id`, and the chosen dataflow-target encoding. Once
published, changes require a `schema_version` bump. *This is the single most important
forward-compatibility requirement in Phase 1* (per §2: TraceQL won't chase links for us).

### REQ-MIE-340: Findings log (LogQL surface)
Emit one structured Loki log line per `CodeElement` and per structural finding, labeled by
`element_id`/`file`/`language`/`severity`, so "find all X" is a LogQL query. (Findings
content beyond stubs is Phase 3; the channel is established here.)

---

## 6. Pre-Generation Integration (REQ-MIE-4xx)

### REQ-MIE-400: Target-index extraction
Provide a `build_target_index(target_root) -> CodeGraph` entry point that extracts the
**existing target project** once, up front. This is the "✅ strong fit" use case from the
design — complete, buildable code; no license gate on OSS benchmark targets.

### REQ-MIE-410: Forward-manifest consumption
`forward_manifest_extractor.py` MUST be able to consume a `CodeGraph` (cross-file `CALLS`/
`INHERITS`/`IMPORTS`) to enrich `InterfaceContract` extraction, replacing shallow re-extraction
where a graph is available. Integration MUST be additive and behind a feature flag
(`code_observability_enabled`), defaulting **off** until Phase 1 verification passes.

**Acceptance:** with the flag on, the forward manifest for a Go target includes call-edge-
derived context absent in the regex path; with the flag off, behavior is byte-identical to today.

---

## 7. Dependencies & Infrastructure (REQ-MIE-5xx)

### REQ-MIE-500: Resolve the tree-sitter / codebleu pin conflict (BLOCKING)
`tree-sitter-go` 0.25 requires `tree-sitter` ≥0.25 (grammar ABI 15); a pre-existing
`codebleu` dependency pins `tree-sitter<0.23`. Phase 1 MUST resolve via one of:
- isolate the extractor in its own optional extra / subprocess env, OR
- vendor the compiled Go grammar against the pinned core, OR
- relax/replace the `codebleu` dependency.

**Acceptance:** `pip install -e ".[code-observability]"` (proposed extra) installs without
conflict and `GoBackend` imports cleanly; CI documents the chosen strategy.

### REQ-MIE-510: Optional-dependency hygiene
tree-sitter MUST be an **optional** extra. The SDK core, and all existing tests, MUST import
and run with tree-sitter absent (REQ-MIE-240 fallback covers runtime).

---

## 8. Non-Functional Requirements (NFR)

- **NFR-1 — Partial-file tolerance.** Extraction MUST succeed on incomplete, stubbed, or
  non-compiling source (the property that disqualifies CodeQL for our inner loop). Verified
  by a deliberately broken fixture. **Note:** native Python `ast` does NOT satisfy this (raises
  `SyntaxError`) — so the inner-loop Python path uses tree-sitter, and native `ast`+stdlib is
  reserved for complete-code target indexing (see REQ-MIE-210). Tolerance is a property of the
  *backend chosen per context*, not of every backend.
- **NFR-2 — Cardinality controls.** Per-element span/label cardinality MUST be bounded:
  configurable depth cap on call-graph traces, optional per-module sub-traces, and per-module
  aggregate metrics as an alternative to per-element gauges. (Phase 0 confirmed this is
  necessary, not optional.)
- **NFR-3 — Incremental extraction.** Re-extraction after a single-element change SHOULD
  re-process only the affected file(s) and emit deltas (enabled by stable IDs, REQ-MIE-110).
  Full implementation may slip to Phase 2; the ID design MUST not preclude it.
- **NFR-4 — Inner-loop latency.** Single-file extraction + emission MUST complete in
  sub-second wall-clock on the fixture scale (contrast: CodeQL DB creation is minutes).
- **NFR-5 — Clean-room.** No CodeQL CLI/binaries/QL libs/query packs/DB format/extractors;
  only tree-sitter (MIT), `ast`, OTel (Apache-2.0), Prometheus/Loki/Tempo/Grafana. Enforced
  by dependency review.

---

## 9. Non-Requirements (Out of Scope)

- **Graph-aware splicing** (blast-radius pre-check, graph-diff post-check) — Phase 2.
- **The DATAFLOW graph-traversal taint helper** — Phase 2 (Phase 1 only locks its contract).
- **Path-based security validation** replacing `query_prime/security` keyword matching — Phase 3.
- **Java / Node.js / C# backends + the Grafana dashboard pack** — Phase 4.
- **Precise, flow-sensitive, sanitizer-aware dataflow** — Phase 2/3 (Phase 1 is coarse).

---

## 10. Traceability Matrix

| REQ | Design §  | Principle Rule | Phase 0 Evidence |
|-----|-----------|----------------|------------------|
| REQ-MIE-100/110/120/130 | §2.3 Layer 1 | Rule 2 (One Model), Mottainai | `extractor.py` CodeGraph JSON |
| REQ-MIE-200–240 | §2.3, §2.6-A | Rule 1, Rule 3 (Partial-file) | tree-sitter vs regex (5 vs 0 edges) |
| REQ-MIE-230 | §2.6-C, §1.2 | Rule 6 (Reachability) | source/sink tagging; safe-path exclusion |
| REQ-MIE-300–340 | §2.4 Layer 2 | Rule 4 (Emit on owned stack) | live Tempo/Mimir emit; `>>` TraceQL run |
| REQ-MIE-320/330 | §2.4 | Rule 4 | OQ#6 span-link mechanics finding |
| REQ-MIE-400/410 | §1.4 "strong fit", §2.6-A | Mieruka core | n/a (new integration) |
| REQ-MIE-500/510 | Part 5 plan | NFR-5 clean-room | OQ#7 pin conflict |
| NFR-1/4 | §2.7 | Rule 3 | partial-file parse OK |
| NFR-2 | Part 6 OQ#1 | — | cardinality ~1:1 confirmed |

---

## 11. Verification Strategy

1. **Unit** — IR round-trip; stable-ID invariance under unrelated edits (REQ-MIE-110);
   per-backend edge extraction on fixtures (REQ-MIE-210/220).
2. **Contamination/safety** — taint fixture: tainted path present, safe parameterized path
   absent (REQ-MIE-230); broken-syntax fixture parses (NFR-1).
3. **Emission** — metrics carry `code_` prefix + required labels; one connected trace per
   entrypoint; DATAFLOW contract attributes present (REQ-MIE-330). Offline JSON mode asserted
   in CI; live-OTLP path validated manually against the kind o11y stack (as in Phase 0).
4. **Integration** — feature-flag off ⇒ forward manifest byte-identical to baseline;
   flag on ⇒ call-edge-derived enrichment present (REQ-MIE-410).
5. **Dependency** — clean install of the `[code-observability]` extra; core test suite green
   with tree-sitter absent (REQ-MIE-510).
6. **Regression budget** — no change to existing `forward_manifest` / `go_parser` behavior
   when the flag is off.

---

## 12. Open Questions

- **OQ-1.1** — Native span Links (two-pass pre-alloc) vs. resolved-ID attributes for DATAFLOW
  (REQ-MIE-320)? Leaning attributes (simpler, matches spike, the Phase 2 helper traverses them
  anyway) — confirm before locking REQ-MIE-330.
- **OQ-1.2** — Where does `build_target_index` cache live and what invalidates it — per
  benchmark run, or keyed on target commit?
- **OQ-1.3** — Separate Mimir tenant/namespace for `code_*` vs business metrics (design Part 6 #4)?
- **OQ-1.4** — Is coarse argument-flow DATAFLOW good enough to be *useful* in Phase 1, or
  should REQ-MIE-230 wait for the Phase 2 flow-sensitive extractor? (The honest risk from §2.)
- **OQ-1.5** — Module/package boundary definition for per-module aggregation (NFR-2) across
  Python vs Go.
