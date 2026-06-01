# Code Observability — CodeQL Assessment & Clean-Room Design

> **Status:** Draft design (2026-06-01)
> **Author:** Prime Contractor working session
> **Scope:** Assess CodeQL's value for the Prime Contractor workflow, then design an
> independent capability that captures that value on the OTel / time-series stack we
> already run for ContextCore business observability — without touching CodeQL IP.
> **One-line thesis:** *Model code structure as OTel telemetry ("code observability") so
> the same PromQL / LogQL / TraceQL surface we use for business o11y becomes the query
> interface for "what code exists, what it does, and how to edit it."*

---

## Part 1 — CodeQL Assessment

### 1.1 What CodeQL is

CodeQL treats **code as data in a relational database**. Three stages:

1. **Extraction** — parse a whole codebase into a database capturing full AST, type
   hierarchy, control-flow, and data-flow graphs.
2. **Database creation** (`codeql database create`) — compiled languages (Go, Java, C#,
   C/C++, Kotlin, Swift, Rust) require observing a **real build** (`--command=…`);
   interpreted languages (Python, JS/TS) do not.
3. **Query** (`codeql database analyze` / `query run`) — `.ql` queries in a Datalog-like
   language. First-class **call-graph** (`Call`/`Callable`), **global data-flow / taint
   tracking**, and **path queries** (source → sink). Security packs ship by default, but
   the engine is general (correctness / maintainability / dead-code queries are supported).

This maps directly onto the three things we care about: *what code exists* (symbol DB),
*what it does* (call/data-flow graphs), *how to edit it* (edit-impact via call sites + types).

### 1.2 How Prime Contractor does these today (gap baseline)

| Capability | Current implementation | Depth |
|---|---|---|
| Structural extraction | Python = real AST + bytecode (`utils/code_manifest.py`); Go/Node/Java/C# = **regex** parsers (`languages/*_parser.py`, "~80–90% of patterns") | Deep (Py) / shallow (rest) |
| Editing / splicing | Python = AST splice (`micro_prime/splicer.py`); others = **text/brace-matching** (`*_splicer.py`) | No edit-impact awareness |
| Validation | `forward_manifest_validator.py` (10 layers), per-language `*_semantic_checks.py`, `truncation_detection.py` — regex/single-file; `cross_file_imports.py` does limited import resolution | Mostly single-file |
| Security | `query_prime/security/{injection,credentials,lifecycle}.py` — **regex keyword matching** | No taint tracking |
| Cross-file | None — no call graphs, type/inheritance resolution, or data-flow | Absent |

The real gaps CodeQL would fill: **cross-file call graphs, type-aware edit-impact, and
genuine taint analysis** (real SQL-injection vs. "saw the word SELECT").

### 1.3 The three constraints that decide CodeQL fit

CodeQL is a **whole-program, post-hoc, buildable-codebase** analyzer. The Prime Contractor
inner loop is the opposite of that.

1. **Licensing.** CodeQL CLI is free **only** for OSI-licensed open-source code, academic
   research, or CI on OSS hosted on GitHub.com. Closed/proprietary code requires a paid
   **GitHub Advanced Security** license. → Fine for our OSS benchmark targets
   (online-boutique etc.); a blocker for real customer code.
2. **Needs a complete, buildable codebase.** Compiled-language extraction must watch a
   successful build. Mid-pipeline artifacts are **partial, stubbed, non-compiling** —
   exactly what CodeQL cannot ingest. DB creation takes **minutes** — fatal in a per-element
   splice/repair inner loop.
3. **Global data-flow is slow + memory-hungry** (GitHub's own docs warn this). Not an
   inner-loop tool.

### 1.4 Verdict

- **❌ Inner-loop generation / splice / repair** — wrong tool. Too slow, needs buildable
  code, conflicts with partial-artifact reality. Our fast text-splicers + regex checks are
  correct there.
- **✅ Pre-generation understanding of the existing target project** — index the target
  *once* up front (complete + buildable), feed call graph + type hierarchy into the forward
  manifest. Strongest fit; matches the stated goal.
- **🟡 Final validation gate** — run on a completed, compiling result as a post-assembly
  Kaizen signal (real taint-based injection, dead-code). Multi-minute gate = "final report,"
  not a loop step.

**Conclusion that motivates Part 2:** CodeQL's *value* is "query code as data." Its *delivery
mechanism* (relational DB, Datalog, build-coupled extraction, restrictive license) is a poor
fit for our pipeline and our proprietary targets. We already operate a query-able data
substrate — the ContextCore OTel / time-series stack — and already model **tasks as spans**.
We can capture the value on infrastructure we own, legally, and with better inner-loop ergonomics.

---

## Part 2 — Clean-Room Design: "Code Observability" (Mieruka)

> **Proposed design principle name:** **MIERUKA (見える化)** — the Toyota-Production-System
> term for *"making things visible."* It sits naturally beside our existing lean-derived
> principles (Kaizen, Mottainai). Where Kaizen says *don't discard lessons across runs* and
> Mottainai says *don't discard artifacts within a run*, **Mieruka says: make code
> structure observable — never act on code you cannot query.**

### 2.1 The core analogy

CodeQL: `code → relational DB → Datalog queries`.

Ours: `code → OTel signals → time-series/log/trace stores → PromQL/LogQL/TraceQL queries`.

We reuse the *exact* query languages and storage the team already uses for business
observability. A call graph **is** a span tree. A data-flow path **is** a set of span links.
A structural metric **is** a gauge over a run/commit dimension. This is not a metaphor we
are forcing — these graph structures are isomorphic to the OTel data model.

### 2.2 Three-layer architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│ LAYER 3 — QUERY SURFACE (reuse business-o11y tooling, zero new langs) │
│   PromQL  → structural metrics & cross-run trends                     │
│   LogQL   → structural facts & findings ("find all X")                │
│   TraceQL → call paths / reachability / taint ("source reaches sink") │
│   Grafana → "code observability" dashboards beside Kaizen dashboards  │
└───────────────▲──────────────────▲────────────────────▲──────────────┘
                │ Mimir            │ Loki              │ Tempo
┌───────────────┴──────────────────┴────────────────────┴──────────────┐
│ LAYER 2 — OTel EMISSION ("code as telemetry")                         │
│   Metrics: code_element_count, fan_in/out, cyclomatic, stub_count,    │
│            unresolved_import_count, contract_compliance  (per run)     │
│   Traces:  element = span; CALLS = parent/child; DATAFLOW = span link │
│   Logs:    one structured line per element + per finding (labeled)    │
└───────────────────────────────▲──────────────────────────────────────┘
                                 │ emit(CodeGraph)
┌────────────────────────────────┴─────────────────────────────────────┐
│ LAYER 1 — STRUCTURAL EXTRACTION → CodeGraph IR (one model, 5 langs)   │
│   Nodes: Module / Class / Function / Field (CodeElement)              │
│   Edges: CALLS, IMPORTS, DEFINES, INHERITS, REFERENCES, DATAFLOW      │
│   Python: native ast. Go/Java/Node/C#: tree-sitter (MIT) → real AST  │
│   Generalizes existing per-language parsers + ER-012 ElementRegistry │
└───────────────────────────────────────────────────────────────────────┘
```

### 2.3 Layer 1 — `CodeGraph` IR

A single typed intermediate representation that generalizes today's scattered extractors
(`languages/*_parser.py`, `utils/code_manifest.py`, the ER-012 `ElementRegistry` in
`prime_contractor.py`) into one graph:

- **`CodeElement`** node — `id`, `kind` (module/class/function/field), `language`, `file`,
  `span` (line range), `signature`, `docstring`/contract.
- **Typed edges** — `CALLS`, `IMPORTS`, `DEFINES`, `INHERITS`, `REFERENCES`, `DATAFLOW`.
- **Per-language backends** behind one Protocol (mirrors `LanguageProfile`):
  - **Python** keeps native `ast` (already deep).
  - **Go / Java / Node / C#** upgrade from regex to **tree-sitter** grammars (MIT-licensed,
    no build step, partial-file tolerant) → closes the depth gap legally and *without
    requiring the code to compile* — solving CodeQL constraint #2 for free.
- `CodeGraph` is a **Keiyaku-compliant contract** (typed) handed extractor → splicer →
  validator, and a **Mottainai artifact** persisted to `.startd8/state/` and reused across
  phases rather than re-derived.

This is also the **pre-generation target index**: build the graph for the existing target
project once, feed it into `forward_manifest_extractor.py` as real cross-file context.

### 2.4 Layer 2 — OTel emission

Reuse `otel.py` / `logging_otel.py` / the ContextCore span conventions (SpanState v2). Three
signal mappings:

| OTel signal | Code mapping | Store | Why this signal |
|---|---|---|---|
| **Metrics** | Structural gauges per element/module dimensioned by `run_id`, `commit`, `language` | Mimir | Time-series over runs = **Kaizen trends for structure, for free** |
| **Traces** | `CALLS` graph as span tree (root = entrypoint, children = callees); `DATAFLOW` as span links | Tempo | Call paths / reachability / taint become **TraceQL path queries** — the CodeQL killer feature on open infra |
| **Logs** | One structured line per element + per finding, labeled `element_id`/`file`/`severity` | Loki | "Find all X" becomes **LogQL** |

Proposed metric names (follow `gov_`-style prefix convention → `code_`):
`code_element_count`, `code_fan_in`, `code_fan_out`, `code_cyclomatic_complexity`,
`code_stub_count`, `code_unresolved_import_count`, `code_contract_compliance`,
`code_duplicate_definition_count`.

### 2.5 Layer 3 — Query surface (no new query language to learn)

- **PromQL** — `code_stub_count` trend across runs; modules whose `code_fan_in` grew
  (rising coupling); contract-compliance regressions. Plugs straight into Kaizen.
- **LogQL** — `{check="bare_except", module=~"services/.*"}`; all unresolved imports for a run.
- **TraceQL** — *the headline capability*: `{ .source = "http_handler" } >> { .sink = "raw_sql" }`
  expresses a taint reachability query (HTTP handler → raw SQL string) using span-link
  traversal. This is how we replace `query_prime/security`'s keyword matching with real
  **path-based** injection/credential-flow detection — on Tempo, not CodeQL.
- **Grafana** — a "Code Observability" dashboard pack alongside the existing Kaizen quality
  dashboards (build via `/dbrd-cr8r` → `/grafana-dashboards`, never hand-rolled JSON).

### 2.6 The three capability improvements ride on this substrate

These are exactly the three you flagged, each now backed by the graph instead of regex:

**A. Better structural extraction** = Layer 1. Tree-sitter unification + `CodeGraph` IR.
Feeds `forward_manifest_extractor.py` real cross-file semantics (call edges, inheritance,
import resolution) where today Go/Java/Node/C# get regex approximations.

**B. Better editing / splicing** = splicers become **graph-aware**, not just brace-aware.
- *Pre-edit:* resolve the target element + its `CALLS` fan-in to compute **blast radius**
  ("12 callers depend on this signature").
- *Post-edit:* diff the graph — did the splice break a caller's contract, orphan a symbol,
  or duplicate a definition? This is CodeQL's edit-impact, computed by querying our own graph.
  Wires into `micro_prime/splicer.py` + the per-language `*_splicer.py`.

**C. Better validation** = validators query graph/traces instead of regexing single files.
Cross-file unresolved call targets, signature mismatches *at call sites*, unreachable code,
and **real taint paths** (TraceQL) for injection/credential flow — upgrading
`query_prime/security` and `forward_manifest_validator.py` from single-file pattern checks
to path-based semantics.

### 2.7 Inner-loop ergonomics (where we beat CodeQL on purpose)

- **Partial-file tolerant** — tree-sitter parses incomplete/stubbed code; no build required.
  Directly fixes the constraint that disqualifies CodeQL mid-pipeline (§1.3 #2).
- **Incremental** — re-extract only changed elements after a splice; emit deltas. Sub-second,
  not minutes (§1.3 #3). Aligns with the **Hayai** principle (don't defer enforcement).
- **Always available** — no license gate on proprietary targets (§1.3 #1); runs on the stack
  we already operate.

---

## Part 3 — IP / Clean-Room Boundary

The concept *"query code as data"* is decades old and far broader than CodeQL — prior art
includes **Datalog program analysis** (1980s), Google **Kythe**, Meta **Glean**,
**tree-sitter**, and **srcML**. Our design is independently derived and categorically
different in both storage (time-series / trace, not a relational Datalog DB) and query
surface (PromQL / LogQL / TraceQL, not QL).

**Use freely (all open-source, mostly already in our stack):**
- tree-sitter (MIT), our own existing parsers, Python `ast`
- OpenTelemetry SDK (Apache-2.0)
- Prometheus / Mimir, Loki, Tempo, Grafana (Apache-2.0 / AGPL — already operated)

**Do NOT touch:**
- CodeQL CLI / binaries, the Semmle QL standard libraries, `.ql` query packs, the CodeQL
  database format, or CodeQL extractors.
- Do not transcribe or paraphrase specific CodeQL query semantics or query text.

**Defensibility note:** document the Kythe/Glean/tree-sitter/Datalog lineage in any
shipped artifact so derivation is demonstrably independent of CodeQL.

---

## Part 4 — Mapping to existing principles & modules

| Existing pattern | How Code Observability extends it |
|---|---|
| **Kaizen** (don't discard lessons across runs) | `code_*` metrics as time-series = structural Kaizen; reuses `kaizen-trends.json` machinery |
| **Mottainai** (don't discard artifacts within a run) | `CodeGraph` persisted to `.startd8/state/`, reused across phases |
| **Hayai** (don't defer enforcement) | Incremental graph emission + validation at each stage, not only post-assembly |
| **Keiyaku** (typed A2A contracts) | `CodeGraph` / `CodeElement` are typed contracts between extractor → splicer → validator |
| **Warm-up** (don't discard context across transitions) | Graph carries cross-file context through toolchain handoffs |
| `forward_manifest_extractor.py` | Consumes `CodeGraph` instead of re-extracting; gains cross-file edges |
| ER-012 `ElementRegistry` | Becomes the in-memory `CodeGraph` builder; gains OTel emission |
| `integrations/contextcore.py` (tasks-as-spans) | Same span infra now also carries code-elements-as-spans |
| `LanguageProfile` protocol | Add a `code_graph_backend` member per language (tree-sitter vs ast) |

---

## Part 5 — Phased plan (proposed)

- **Phase 0 — Spike (read-only, OSS target). ✅ DONE (2026-06-01).** tree-sitter backend
  for **Go** → emit `CodeGraph` → `code_*` metrics + call-graph trace. Built under
  `scripts/spikes/code_observability/` (`extractor.py`, `emit.py`, `taint_query_probe.py`,
  `compare_regex_vs_treesitter.py`, fixture, `PHASE0_FINDINGS.md`). **Validated end-to-end
  against a live kind o11y stack** (Tempo/Mimir/Loki/Grafana, OTLP :4317): spans landed in
  real Tempo and the TraceQL query `{ span.code.is_source = true } >> { span.code.is_sink =
  true }` returned exactly the tainted trace and excluded the safe parameterized path.
  Evidence for the depth gap: on the same fixture the SDK's regex `go_parser.py` extracts
  **0 call edges** (by its own docstring) vs. tree-sitter's 5 CALLS + 4 DATAFLOW edges.
- **Phase 1 — `CodeGraph` IR + Python/Go backends.** Formalize the contract; wire into
  `forward_manifest_extractor.py` as pre-generation target index.
- **Phase 2 — Graph-aware splicing (Capability B).** Blast-radius pre-check + graph-diff
  post-check in `micro_prime/splicer.py` and `go_splicer.py`.
- **Phase 3 — Path-based validation (Capability C).** TraceQL taint queries replace
  `query_prime/security` keyword matching; cross-file signature checks in
  `forward_manifest_validator.py`.
- **Phase 4 — Remaining backends (Java/Node/C#) + dashboard pack.**

## Part 6 — Open questions

1. **Trace cardinality** — large codebases → huge span trees. Cap depth? Per-module
   sub-traces? Sample? **🟡 Confirmed real by Phase 0:** spans scale ~1:1 with functions and
   per-element gauge labels multiply Mimir cardinality. The mitigations (per-module
   sub-traces, depth caps, per-module aggregate metrics) are **necessary, not optional** —
   bake them into the Phase 1 emission contract.
2. **TraceQL expressiveness** — can span-link traversal express data-flow queries, or do we
   need a thin graph-query helper? **✅ RESOLVED by Phase 0: PARTIAL.** TraceQL's native `>>`
   descendant operator works against live Tempo and isolates source→sink-*reachable* traces
   — use it as a coarse **Layer-3 filter**. But TraceQL traverses span *nesting* (CALLS), not
   span *links* (DATAFLOW), has no transitive link-chase operator, and cannot distinguish
   "calls" from "value-flows" or express sanitizer-on-path constraints (the probe's synthetic
   divergence demo shows `>>` over the call tree false-positives where no value flows).
   **Decision: precise multi-hop taint requires a thin graph-traversal helper over the
   `DATAFLOW` edge type** (productized form of `taint_query_probe.py`). Do NOT promise
   pure-TraceQL taint in Phase 2/3.
3. **Incremental extraction granularity** — element-level vs file-level deltas after a splice.
4. **Storage lifecycle** — per-run retention of code metrics vs. business metrics; separate
   tenant/namespace in Mimir?
5. **Principle name** — **✅ RESOLVED: "Mieruka" adopted**; principle doc written at
   `docs/design-princples/MIERUKA_DESIGN_PRINCIPLE.md`.
6. **Span-link emission mechanics (new, from Phase 0)** — OTel span Links require the target
   SpanContext to exist at creation time, so a top-down call tree can't natively link to
   not-yet-created children. Phase 0 emitted real CALLS nesting (so `>>` works) and recorded
   DATAFLOW targets as resolved span-id *attributes*. Phase 1 must choose: native Links via
   two-pass span-id pre-allocation, vs. resolved-ID attributes traversed by the graph helper.
7. **Dependency pin conflict (new, from Phase 0)** — tree-sitter-go 0.25 needs `tree-sitter`
   ≥0.25 (grammar ABI 15), but a pre-existing `codebleu` pin requires `tree-sitter<0.23`.
   Phase 1 must resolve this (vendor the grammar, isolate the extractor env, or replace/relax
   the codebleu dependency).
