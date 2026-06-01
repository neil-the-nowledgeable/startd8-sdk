# Mieruka Design Principle

Purpose: establish a cross-cutting design principle for the startd8-sdk pipeline — make the **structure of code** observable as first-class telemetry, so that "what code exists, what it does, and how to edit it safely" becomes a query against data we already store, not an ad-hoc regex pass over single files.

This document is intentionally living guidance. Update it as new code-observability capabilities are identified.

---

## The Principle

**Mieruka** (見える化) — "making things visible." In the Toyota Production System, Mieruka is the practice of surfacing the true state of a process visually so that problems become impossible to ignore and anyone can act on them. It is the discipline that makes Kaizen possible: you cannot improve what you cannot see.

Applied to the pipeline: **code structure — the symbols that exist, the calls between them, the data that flows through them — must be extracted into an observable model and emitted as telemetry. No generation, edit, or validation step should act on code it cannot first query. Understanding precedes mutation.**

The mechanism is deliberate: we model code as OpenTelemetry signals (metrics, traces, logs) and query it with the **same PromQL / LogQL / TraceQL surface** the team already uses for business observability. A call graph is a span tree; a data-flow path is a set of span links; a structural metric is a gauge over a run dimension. Code becomes observable on infrastructure we already operate.

---

## Relationship to Kaizen and Mottainai

Mieruka is the **visibility substrate** that the improvement principles depend on.

| Dimension | Mottainai | Kaizen | Mieruka |
|-----------|-----------|--------|---------|
| **Scope** | Single run | Across runs | Across the code itself |
| **Focus** | Don't discard artifacts | Don't discard lessons | Don't act on code you can't see |
| **Question** | "Has this been computed?" | "Have we seen this problem before?" | "What does this code actually contain and do?" |
| **Mechanism** | Artifact forwarding | Observe → Analyze → Act → Verify | Extract → Emit → Query |

The relationship is causal: **Mieruka makes structure visible → Kaizen observes that visibility over time to improve → Mottainai forwards the resulting artifacts within a run.** Concretely, code-structure metrics (`code_stub_count`, `code_contract_compliance`) emitted under Mieruka become Kaizen time-series for free — the same Mimir/Loki/Tempo stack, the same trend tooling.

---

## Why This Matters

The Prime Contractor workflow understands existing code shallowly today:

1. **Python** has real structural understanding (AST + bytecode introspection in `utils/code_manifest.py`).
2. **Go, Node.js, Java, C#** rely on **regex parsers** (`languages/*_parser.py`) covering "~80–90% of patterns" — no accurate call resolution, no type/inheritance, no cross-file graph.
3. **Editing/splicing** is **text/brace-matching** for non-Python languages — blind to whether an edit breaks a caller.
4. **Validation and security** (`forward_manifest_validator.py`, `query_prime/security/`) are largely single-file regex — they detect the *word* `SELECT`, not a *taint path* from an untrusted source to a SQL sink.

The gap is not "we need CodeQL." (See `docs/design/CODE_OBSERVABILITY_DESIGN.md` for why CodeQL is a poor fit: license-gated on proprietary code, requires a complete buildable codebase, multi-minute extraction — all hostile to a partial-artifact inner loop.) The gap is that **code structure is not observable**. Mieruka closes it on the stack we own, partial-file tolerant, with no license gate.

---

## The Mieruka Cycle

### Extract — build the observable model

Parse code into a single typed **`CodeGraph`** IR (nodes: module/class/function/field; edges: `CALLS`, `IMPORTS`, `DEFINES`, `INHERITS`, `REFERENCES`, `DATAFLOW`). Python uses native `ast`; Go/Java/Node/C# upgrade from regex to **tree-sitter** (real AST, no build step, tolerant of incomplete code). This generalizes today's per-language parsers and the ER-012 `ElementRegistry`.

### Emit — code as telemetry

Map the `CodeGraph` onto OTel signals: **metrics** (structural gauges per element/module, dimensioned by `run_id`/`commit`/`language`), **traces** (the `CALLS` graph as a span tree, `DATAFLOW` as span links), **logs** (one structured line per element and per finding).

### Query — reuse the business-o11y surface

PromQL for structural trends, LogQL for "find all X," TraceQL for reachability/taint ("does this source reach that sink?"). Grafana "Code Observability" dashboards sit beside the Kaizen quality dashboards.

---

## Application Rules

### Rule 1: Understanding Precedes Mutation

No splice or edit step may modify an element without first resolving that element and its dependents in the `CodeGraph`. Editing blind to call sites is the anti-pattern.

**Applies to:** `micro_prime/splicer.py` and all `languages/*_splicer.py`.

### Rule 2: One Model, All Languages

Structural understanding flows through a single `CodeGraph` contract regardless of language. Per-language extraction differences are an implementation detail behind one Protocol (mirroring `LanguageProfile`), not a reason for divergent downstream logic.

**Anti-pattern:** Python gets graph-aware tooling while Go/Java/Node/C# stay on regex single-file checks indefinitely.

### Rule 3: Partial-File Tolerant, Inner-Loop Fast

Extraction must work on incomplete, stubbed, non-compiling code and must be incremental (re-extract only changed elements after a splice). This is the explicit advantage over build-coupled analyzers and the reason Mieruka can run inside the loop, not only as a final gate. Aligns with the **Hayai** principle (don't defer enforcement).

### Rule 4: Emit on the Stack We Own

Code structure is emitted via the existing OTel infrastructure (`otel.py`, `logging_otel.py`, ContextCore span conventions) to Mimir/Loki/Tempo. Do not introduce a parallel storage or query system. The query surface is PromQL/LogQL/TraceQL — no new query language for the team to learn.

### Rule 5: Blast Radius Before, Graph Diff After

Graph-aware editing has two checkpoints: **pre-edit** resolve the target's `CALLS` fan-in to report blast radius ("N callers depend on this signature"); **post-edit** diff the graph to catch broken callers, orphaned symbols, and duplicate definitions. This is the structural-validation counterpart to truncation detection.

### Rule 6: Reachability Over Keywords

Cross-file and security validation should query paths, not match words. A SQL-injection finding should be a `DATAFLOW`/span-link path from an untrusted source to a raw-SQL sink (TraceQL), not the presence of a SQL keyword on a line.

**Anti-pattern:** keyword/regex matching where a reachability query is available.

---

## Clean-Room Boundary

Mieruka captures CodeQL's *value* ("query code as data") without its *IP*. The concept long predates and is broader than CodeQL — prior art includes Datalog program analysis, Google Kythe, Meta Glean, tree-sitter, and srcML. Our storage (time-series + traces) and query surface (PromQL/LogQL/TraceQL) are categorically different from CodeQL's relational/Datalog model.

**Permitted:** tree-sitter (MIT), our own parsers, Python `ast`, OpenTelemetry SDK (Apache-2.0), Prometheus/Mimir, Loki, Tempo, Grafana.
**Forbidden:** CodeQL CLI/binaries, Semmle QL standard libraries, `.ql` query packs, the CodeQL database format, CodeQL extractors, and any transcription of CodeQL query semantics.

---

## Existing Capabilities Inventory

Before building new capabilities, Mieruka leverages what already exists:

| Capability | Source | Mieruka Use |
|-----------|--------|-------------|
| Python AST + bytecode extraction | `utils/code_manifest.py` | Python `CodeGraph` backend (already deep) |
| Per-language structure parsers | `languages/*_parser.py` | Baseline to upgrade to tree-sitter backends |
| Cross-feature structural model | ER-012 `ElementRegistry` in `prime_contractor.py` | In-memory `CodeGraph` builder; gains OTel emission |
| Contract extraction | `forward_manifest_extractor.py` | Consumes `CodeGraph` instead of re-extracting; gains cross-file edges |
| OTel infrastructure | `otel.py`, `logging_otel.py` | Emission transport for code telemetry |
| Tasks-as-spans conventions | `integrations/contextcore.py` (SpanState v2) | Same span infra now also carries code-elements-as-spans |
| Cross-run trend tooling | Kaizen `kaizen-trends.json` machinery | Consumes `code_*` metrics as structural Kaizen series |
| Dashboard pipeline | `/dbrd-cr8r` → `/grafana-dashboards` | "Code Observability" dashboard pack (never hand-rolled JSON) |

---

## Current Gaps (Baseline)

### Gap M-1: No Unified Structural Model
Structure is extracted ad-hoc per language with divergent depth (AST for Python, regex for the rest). There is no single `CodeGraph` IR shared across extractor → splicer → validator.

### Gap M-2: No Cross-File Semantics
No call graphs, type/inheritance resolution, or data-flow across files. Edit-impact and reachability are uncomputable today.

### Gap M-3: Code Structure Is Not Emitted as Telemetry
The pipeline emits operational telemetry (task spans, costs) but not *code-structure* telemetry. There is no `code_*` metric family, no call-graph trace, no structural findings log.

### Gap M-4: Blind Editing
Non-Python splicers match braces, not semantics. There is no blast-radius pre-check or graph-diff post-check.

### Gap M-5: Keyword-Based Security
`query_prime/security/` matches SQL keywords and credential-named variables rather than tracing taint paths.

---

## Design Interactions

### With Kaizen
Code-structure metrics emitted under Mieruka are Kaizen time-series. Structural regression (rising `code_stub_count`, falling `code_contract_compliance`) becomes a Kaizen signal automatically.

### With Hayai
Incremental, partial-file extraction lets structural enforcement happen at each stage rather than being deferred to a post-assembly gate.

### With Keiyaku
`CodeGraph` / `CodeElement` are typed contracts at the extractor → splicer → validator boundaries.

### With Mottainai
The `CodeGraph` is a forwarded artifact: built once, persisted to `.startd8/state/`, reused across phases rather than re-derived.

---

## Success Criteria

1. A single `CodeGraph` IR is produced for all five languages, with tree-sitter backends replacing regex for Go/Java/Node/C#.
2. Code structure is queryable via the existing observability stack — at least one PromQL, one LogQL, and one TraceQL query answer a real pipeline question.
3. Splicing is graph-aware: blast radius is reported pre-edit and graph diff catches broken callers post-edit.
4. At least one security check (SQL injection) is expressed as a reachability/taint query rather than a keyword match.
5. Structural metrics flow into Kaizen trend analysis without bespoke plumbing.
