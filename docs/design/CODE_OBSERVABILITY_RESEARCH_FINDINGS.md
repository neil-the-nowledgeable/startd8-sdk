# Code Observability — Research Findings

> **Version:** 0.1  
> **Date:** 2026-06-01  
> **Researcher:** Cursor agent (P0 first-wave investigation)  
> **Scope:** P0 first wave — RT-A1, RT-D4, RT-C1, RT-C3, RT-D1, RT-A4+RT-B1

---

## Executive Summary

| Topic | One-line recommendation | Decision unblocked | Confidence (H/M/L) | Blocking issue? |
|-------|-------------------------|--------------------|--------------------|-----------------|
| **RT-A1** — stack-graphs / cross-file resolution | **Hybrid, not stack-graphs-everywhere:** adopt per-language resolvers; use stack-graphs only as reference/fork candidate for JS/TS/Java — **not** turnkey for Go/C# in Phase 1 | REQ-MIE-220/410 | M | No (path is clear; Go resolver is effort) |
| **RT-D4** — Python-native stack | **Stdlib `ast` + `symtable` + `importlib` + two-pass symbol table for Phase 1; add Jedi (MIT) for unresolved dynamic calls; Pysa via subprocess for Python taint proving ground** | REQ-MIE-210 | H | No |
| **RT-C1** — traces vs graph store | **traces + persisted `CodeGraph` helper** (not traces-only, not a separate graph DB): Tempo for coarse reachability + metrics/logs; `.startd8/state/` JSON graph for precise traversal | Substrate commitment (Phase 2) | H | No |
| **RT-C3** — span Links vs attributes | **Encode DATAFLOW as resolved-target-span-id attributes** (spike approach); skip native OTel Links for Phase 1 | REQ-MIE-320/330 | H | No |
| **RT-D1** — tree-sitter / codebleu pin | **Isolated `code-observability` optional extra** with `tree-sitter>=0.25`; never co-install with `codebleu` (pins `<0.23`); codebleu not currently in `pyproject.toml` | REQ-MIE-500 | H | Yes until extra lands |
| **RT-A4+RT-B1** — taint build vs embed | **Hybrid:** Pysa subprocess (MIT) for Python precise taint; **build** IFDS-class analysis on `CodeGraph` for Go/other; **reject** Semgrep CE embed for cross-file taint (intraprocedural only) | Phase 2/3 taint strategy | M | No (Python path clear; Go taint is risk) |

The single most consequential finding is that **TraceQL and OTel traces cannot carry the precise-taint workload** — Phase 0 was correct. Tempo gives cheap coarse reachability over the CALLS span tree, but transitive DATAFLOW, sanitizer-aware paths, and call-vs-value-flow distinction all require a **persisted graph helper** (the `CodeGraph` IR we already emit). That means the architecture is **traces + graph artifact**, not traces-only and not a new graph database — preserving Mieruka Rule 4 while honestly scoping Phase 2/3 taint work.

---

## RT-A1 — Name/scope resolution on tree-sitter

**Recommendation (BLUF):** Do **not** adopt GitHub stack-graphs as the one-resolver-everywhere component for Phase 1. Use a **hybrid, best-per-language** strategy: Python native resolution (RT-D4), syntactic + import-aware two-pass resolution for Go in Phase 1, and optional **SCIP indexers** (Apache-2.0 subprocess) for complete target-index extraction on Go/Java/C#/TS. Treat stack-graphs as a **fork/reference** for JS/TS/Java long-term, not a drop-in SDK dependency.

**Key findings:**

- tree-sitter parses syntax but does not bind call sites to declarations; cross-file resolution requires a separate name-binding layer [verified] — https://tree-sitter.github.io/tree-sitter/ (project scope: parsing only)
- GitHub **stack-graphs** / **tree-sitter-stack-graphs** is dual-licensed **MIT / Apache-2.0** and is **CodeQL-independent** (based on TU Delft scope graphs, not CodeQL's Datalog DB) [verified] — https://github.com/github/stack-graphs (2025-09-09 archive notice)
- The stack-graphs repository was **archived by GitHub on 2025-09-09** with explicit "no longer supported" notice; last release `tree-sitter-stack-graphs-v0.10.0` (2024-12-13) [verified] — https://github.com/github/stack-graphs
- Pre-built TSG (tree-sitter-graph) rules exist for **four languages only**: Python, JavaScript, TypeScript, and Java — **not Go, not C#** [verified] — https://github.com/github/stack-graphs/issues/420#issuecomment- (maintainer reply, 2024)
- Integration surface is **Rust** (crate + CLI); there is no maintained official Python binding for SDK embed [verified] — https://docs.rs/tree-sitter-stack-graphs/latest/tree_sitter_stack_graphs/
- **SCIP** indexers exist for Go (`scip-go`), Java, C#, TypeScript/JS, Python — Apache-2.0, compiler-grade cross-file symbols [verified] — https://github.com/scip-code/scip (2026-04-14 v0.7.1); trade-off: many indexers require buildable/partially-built projects (Go: `go mod`; Java: Gradle/Maven)
- For Go specifically, a practical Phase 1 path is **two-pass extraction**: (1) per-file export table (package-level func/type names + imports), (2) resolve call identifiers against import map + same-package symbols [inferred] — pattern described in open-source AST tooling discussions — https://github.com/safishamsi/graphify/issues/298

**Decision impact:** REQ-MIE-220/410 — Phase 1 Go backend ships **syntactic CALLS + import-linked REFERENCES** with a documented resolution quality tier; REQ-MIE-410 target-index mode may optionally invoke `scip-go` subprocess when the target is complete/buildable. REQ-MIE-220 acceptance ("resolved CALLS on 3-level cross-file chain") is met for **Python** in Phase 1; for **Go**, acceptance should be split into *syntactic* (Phase 1) and *resolved* (Phase 1.5 or Phase 2 with SCIP/two-pass resolver).

**Licensing & clean-room check:** stack-graphs = MIT/Apache-2.0, SDK-shippable as subprocess/fork; **not CodeQL-derived**. SCIP = Apache-2.0, SDK-shippable as optional subprocess tool, not vendored into core. Per-language custom resolvers = no third-party IP concern.

**Confidence:** Medium — stack-graphs maturity and archival status are verified; exact effort to write Go TSG rules or a lightweight Go resolver is inferred from analogous projects, not measured in this repo.

**Gaps / unknowns:** No benchmark of stack-graphs resolution accuracy on our Go fixture; no test of `scip-go` on partial/non-compiling Go (likely fails — needs spike). A focused RT-D2 spike on Go two-pass resolver accuracy would resolve Phase 1 acceptance wording.

**Sources:**

1. GitHub stack-graphs README (archive notice, license) — https://github.com/github/stack-graphs — primary — 2025-09-09
2. stack-graphs issue #420 (four languages with TSG) — https://github.com/github/stack-graphs/issues/420 — primary — 2024
3. tree-sitter-stack-graphs docs.rs — https://docs.rs/tree-sitter-stack-graphs/latest/tree_sitter_stack_graphs/ — primary
4. SCIP protocol repo — https://github.com/scip-code/scip — primary — 2026-04-14
5. graphify cross-file limitation discussion — https://github.com/safishamsi/graphify/issues/298 — secondary

---

## RT-D4 — Python-native resolution & taint stack

**Recommendation (BLUF):** Phase 1 Python backend = **`ast` + `symtable` + `importlib.util.find_spec` + two-pass export/call-site resolution**, reusing patterns from `utils/code_manifest.py`. Add **Jedi** (MIT) as an optional fallback for dynamic/unresolved calls in target-index mode. Validate **flow-sensitive taint in Python first** via **Pysa** (`pyre analyze` subprocess, MIT) — not via embedding. Reserve **LibCST** (MIT) for future splice-preserving edits, not extraction.

**Key findings:**

- Python **`symtable`** exposes per-module scope/binding (local/global/free/imported) but is **intra-module only** — it does not resolve cross-file call targets [verified] — https://docs.python.org/3/library/symtable.html
- Cross-file call resolution requires a **two-pass architecture**: pass 1 builds a corpus-wide export registry (module → exported symbols); pass 2 maps call AST nodes to registry entries via import aliases [verified] — https://github.com/safishamsi/graphify/issues/298 (accurate description of the general pattern)
- **`importlib.util.find_spec`** resolves import names to filesystem paths without executing imported modules (when used carefully) — suitable for static import → file mapping [verified] — https://docs.python.org/3/library/importlib.html#importlib.util.find_spec
- The SDK already uses **`symtable` + `dis` bytecode call analysis** in `code_manifest.py` (schema v1.2–1.4) — proven in-repo foundation for REQ-MIE-210 [verified] — `src/startd8/utils/code_manifest.py`
- **`dis` / `inspect` refinement** requires **importable, side-effect-safe code** — suitable for complete target index, not inner-loop partial stubs [verified] — design REQ-MIE-210 caveat + code_manifest implementation
- Native **`ast` raises `SyntaxError` on incomplete code** and grammar matches the **running interpreter version** — confirms hybrid ast (complete index) vs tree-sitter (inner loop) split [verified] — https://docs.python.org/3/library/ast.html ; Phase 1 reqs NFR-1
- **Jedi** provides cross-file `Script.goto()` / `Project`-scoped resolution; **MIT licensed**; does not execute user code by default (`load_unsafe_extensions=False`) [verified] — https://jedi.readthedocs.io/en/stable/docs/features.html ; https://github.com/davidhalter/jedi/blob/master/LICENSE.txt
- **astroid** (pylint's AST) is **LGPL-2.1** — usable internally but **discouraged as a hard SDK dependency** for proprietary distribution without legal review [verified] — https://pypi.org/project/astroid/
- **Pysa** is MIT-licensed, ships inside `pyre-check`, but is **not embeddable as a Python library** — analysis runs via **`pyre analyze` CLI** with `.pyre_configuration`, `taint.config`, and `.pysa` models [verified] — https://github.com/facebook/pyre-check ; https://pyre-check.org/docs/pysa-running/
- **LibCST** is MIT, lossless CST for codemods — complementary to extraction, not a resolver [verified] — https://github.com/Instagram/LibCST

**Decision impact:** REQ-MIE-210 — Python Phase 1 uses stdlib-first resolution with Jedi optional extra (`python-observability` or folded into `code-observability`); confirms **validate taint (RT-B1) in Python first** via Pysa subprocess before generalizing IFDS to Go.

**Licensing & clean-room check:** stdlib = PSF; Jedi = MIT (recommended optional dep); Pysa/Pyre = MIT (subprocess, not linked); astroid = LGPL (**reject** as required dep); LibCST = MIT (future splice lane). All CodeQL-independent.

**Confidence:** High for stdlib/Jedi/Pysa roles; Medium for exact cross-file resolution rate on dynamic Python (getattr, metaclass, star-import) without Jedi.

**Gaps / unknowns:** No measured precision/recall of stdlib-only vs Jedi-augmented resolver on a 3-level cross-file fixture in this SDK yet — a small unit-test harness would resolve REQ-MIE-210 acceptance. Pysa cold-start latency and watchman dependency for incremental runs not benchmarked.

**Sources:**

1. Python symtable docs — https://docs.python.org/3/library/symtable.html — primary
2. Jedi features / API — https://jedi.readthedocs.io/en/stable/docs/features.html — primary
3. Pysa running guide — https://pyre-check.org/docs/pysa-running/ — primary
4. pyre-check GitHub (MIT) — https://github.com/facebook/pyre-check — primary — 2026-05-25
5. astroid PyPI (LGPL) — https://pypi.org/project/astroid/ — primary
6. startd8 `code_manifest.py` — in-repo — primary

---

## RT-C1 — Traces vs a graph store (architectural bake-off)

**Recommendation (BLUF):** Commit to **`traces + helper`** — OTel traces/metrics/logs on Tempo/Mimir/Loki for observability UX, plus **persisted `CodeGraph` JSON** (`.startd8/state/`) as the authoritative graph for precise traversal. Do **not** introduce a parallel graph database (Neo4j, etc.); do **not** rely on traces-only for taint.

**Key findings:**

- Phase 0 proved TraceQL `{ span.code.is_source = true } >> { span.code.is_sink = true }` works for **coarse call-tree reachability** on live Tempo [verified] — `scripts/spikes/code_observability/PHASE0_FINDINGS.md`
- TraceQL **`>>` traverses span parent/child (CALLS nesting), not span links** — multi-hop DATAFLOW over non-nested paths is not expressible [verified] — Phase 0 §4b; Tempo TraceQL docs list `>>` as descendant over span structure only — https://grafana.com/docs/tempo/latest/traceql/construct-traceql-queries/
- TraceQL **`link` scope** filters link **metadata** on spans (e.g. `{ link:traceID = "..." }`) but **no production structural operator transits links**; cross-trace link traversal is **draft PoC only** (PR #6113, stale/draft, Dec 2025) [verified] — https://github.com/grafana/tempo/pull/6113
- Tempo practical limits: recommended **`max_bytes_per_trace` ~15 MB** (~50K spans at ~300 B/span); traces with **100K–1M spans** cause memory spikes; **`max_attribute_bytes` default 2048** truncates large attributes [verified] — https://grafana.com/docs/tempo/latest/troubleshooting/out-of-memory-errors/
- Projection from Phase 0: spans scale **~1:1 with functions**; monorepo entrypoint traces can exceed limits without **per-module sub-traces + depth caps** [verified] — PHASE0_FINDINGS §5
- Query classes **impossible on traces alone** (require graph helper or CodeGraph): (1) transitive DATAFLOW link closure, (2) sanitizer-on-path predicates, (3) distinguishing value-flow from call-reachability, (4) fan-in/fan-out edit-impact without re-aggregation [inferred] — Phase 0 divergence demo + TraceQL operator set

**Decision matrix:**

| Criterion | traces-only | traces + CodeGraph helper ✅ | traces + graph DB |
|-----------|-------------|------------------------------|-------------------|
| Reuse PromQL/LogQL/TraceQL dashboards | ✅ | ✅ (coarse) | ❌ new query lang |
| Coarse source→sink filter | ✅ `>>` | ✅ `>>` | ✅ |
| Precise multi-hop taint | ❌ | ✅ BFS on DATAFLOW edges | ✅ |
| Sanitizer-aware paths | ❌ | ✅ path predicates on graph | ✅ |
| Mieruka Rule 4 (stack we own) | ✅ | ✅ | ❌ parallel store |
| Cardinality at 100K+ functions | ⚠️ sub-traces required | ✅ graph JSON O(edges) | ⚠️ ops cost |
| Inner-loop incremental update | ⚠️ re-emit spans | ✅ patch CodeGraph | varies |

**Flip criteria:** Move from helper → external graph DB only if (a) CodeGraph exceeds practical JSON size (>~500MB per target) **and** (b) team accepts operating a graph store — neither is true for Phase 1–2 benchmark targets [inferred].

**Decision impact:** Locks substrate for Phase 2 graph-traversal helper (`taint_query_probe.py` productized) consuming **CodeGraph**, not Tempo queries. OTel emission remains valuable for Grafana dashboards and Kaizen trends.

**Licensing & clean-room check:** Tempo/Grafana stack already operated; NetworkX or stdlib graph traversal in helper = no new license surface. CodeQL-independent.

**Confidence:** High — Phase 0 empirical evidence + Tempo docs; graph-size flip threshold is inferred.

**Gaps / unknowns:** No load test at 50K-function target on live Tempo; RT-C4 (Mimir per-element gauge cardinality) still needs sizing. TraceQL link-traversal PoC may ship eventually — would not remove need for sanitizer-aware helper.

**Sources:**

1. Phase 0 findings — in-repo — primary — 2026-06-01
2. Tempo OOM / trace size limits — https://grafana.com/docs/tempo/latest/troubleshooting/out-of-memory-errors/ — primary
3. TraceQL query construction — https://grafana.com/docs/tempo/latest/traceql/construct-traceql-queries/ — primary
4. Tempo span-link traversal PoC PR #6113 — https://github.com/grafana/tempo/pull/6113 — primary — 2025-12-23

---

## RT-C3 — Span-link emission mechanics (= OQ-1.1)

**Recommendation (BLUF):** **Encode DATAFLOW targets as span attributes** (`span.code.dataflow_targets` / resolved span-id list per spike), **not** native OTel span Links, for the Phase 1 contract. The Phase 2 helper reads **CodeGraph edges first**; span attributes are a Tempo-visible mirror.

**Key findings:**

- OTel span **Links require a target `SpanContext` at span creation** when using native Link objects; top-down call-tree emission cannot link forward to not-yet-created children without **two-pass span-ID pre-allocation** [verified] — Phase 0 emit.py comments + PHASE0_FINDINGS §5; OTel spec: links specified at span creation — https://github.com/open-telemetry/opentelemetry-specification/blob/v1.55.0/specification/trace/api.md
- Spike implementation already uses **attribute backfill** (`dataflow_link_span_ids`) after subtree emission [verified] — `scripts/spikes/code_observability/emit.py`
- TraceQL can filter **`link:` scope attributes** on a span but **cannot transitively walk links** in production [verified] — https://grafana.com/docs/tempo/latest/traceql/construct-traceql-queries/ ; Tempo PR #6113 (draft)
- Native Links would add **two-pass complexity** (pre-allocate IDs, map element_id → SpanContext, second emit pass) for **no TraceQL benefit today** [inferred]
- Attribute encoding cost: one string/list attribute per span with outbound DATAFLOW — well under Tempo **`max_attribute_bytes` 2048** for typical fan-out [inferred]
- Phase 2 helper consumption: **CodeGraph `DATAFLOW` edges are canonical**; span attributes are optional observability mirror — avoids Tempo query dependency entirely [verified] — design + Phase 0 conclusion

**Decision impact:** REQ-MIE-330 — publish contract as:

- `span.code.element_id` (stable ID)
- `span.code.is_source` / `span.code.is_sink`
- `span.code.dataflow_targets`: list of `{element_id, via?}` (preferred) OR comma-separated target element IDs
- Native OTel Links: **deferred** (schema_version bump if added later)

**Licensing & clean-room check:** OTel spec/API = Apache-2.0; no CodeQL overlap.

**Confidence:** High — Phase 0 spike + OTel spec + Tempo TraceQL limits align.

**Gaps / unknowns:** Exact attribute naming should align with RT-C5 (OTel semantic conventions scan — none found for code structure); max links per span in backends (~128 cited in community docs) irrelevant if we choose attributes.

**Sources:**

1. OTel trace API (links at creation) — https://github.com/open-telemetry/opentelemetry-specification/blob/v1.55.0/specification/trace/api.md — primary
2. Phase 0 emit.py — in-repo — primary
3. Tempo TraceQL link scope — https://grafana.com/docs/tempo/latest/traceql/construct-traceql-queries/ — primary
4. Tempo link traversal PoC — https://github.com/grafana/tempo/pull/6113 — primary

---

## RT-D1 — tree-sitter ABI vs the codebleu pin (BLOCKING)

**Recommendation (BLUF):** Add a dedicated **`code-observability` optional extra** with `tree-sitter>=0.25,<0.26` and `tree-sitter-go>=0.25`. **Do not declare `codebleu` in any extra that shares the tree-sitter slot.** If CodeBLEU is needed later for evaluation, isolate it in a separate **`evaluation-codebleu` extra** or subprocess venv pinned to `tree-sitter~=0.22`.

**Key findings:**

- `tree-sitter-go` **0.25** requires tree-sitter core **≥0.25** (grammar **ABI 15**) [verified] — Phase 0 spike README; spike installed 0.25.2 successfully
- **`codebleu` 0.7.0** (PyPI, MIT) declares dependency **`tree-sitter<0.23.0,>=0.22.0`** — **hard incompatibility** with ABI 15 grammars [verified] — https://pypi.org/pypi/codebleu/0.7.0/json (2024-05-30 release; no newer version as of 2026-06-01)
- **`codebleu` is not currently a dependency** of `startd8` `pyproject.toml` and is **not imported anywhere in `src/`** [verified] — repo grep 2026-06-01; conflict is **latent** (environment/docs), not active CI failure
- Existing **`csharp` extra** already pins `tree-sitter>=0.24.0` — closer to but not equal to Go's 0.25 requirement; **`code-observability` extra should own the 0.25 pin** to avoid forcing csharp consumers onto 0.25 until validated [verified] — `pyproject.toml`
- Options evaluated:

| Strategy | Verdict |
|----------|---------|
| Optional extra isolation ✅ | **Recommended** — `pip install -e ".[code-observability]"` |
| Subprocess isolation | Valid for SCIP/heavy tools; overkill for in-process Go backend |
| Vendored grammar against pinned 0.22 core | **Reject** — loses ABI 15 / current `tree-sitter-go` wheels |
| Replace codebleu | **Acceptable** if evaluation needs it — CodeBLEU is MIT but stale (2024); not used in SDK today |
| Relax codebleu upstream | Out of scope — upstream unmoved since 2024-05 [verified] |

**Proposed `pip install` shape:**

```bash
pip install -e ".[code-observability,otel]"
# pyproject snippet:
# code-observability = [
#   "tree-sitter>=0.25,<0.26",
#   "tree-sitter-go>=0.25,<0.26",
# ]
# evaluation-codebleu = [  # optional, mutually exclusive env
#   "codebleu==0.7.0",
#   "tree-sitter>=0.22,<0.23",
# ]
```

**Decision impact:** REQ-MIE-500 — unblocks Phase 1 Go backend; CI documents "never install `[code-observability,code-observability]` + codebleu in one venv".

**Licensing & clean-room check:** tree-sitter = MIT; tree-sitter-go = MIT; codebleu = MIT (optional, separate extra). CodeQL-independent.

**Confidence:** High — PyPI metadata + repo state verified.

**Gaps / unknowns:** Whether any downstream script implicitly installs codebleu into the dev venv (spike README mentions pip resolver *warnings* when both present) — document in CI/dev guide. C# backend on tree-sitter 0.24 vs Go 0.25 may require two grammar-core versions if ever co-installed — keep language extras separate.

**Sources:**

1. codebleu 0.7.0 PyPI JSON (tree-sitter pin) — https://pypi.org/pypi/codebleu/0.7.0/json — primary — 2024-05-30
2. Phase 0 spike README — in-repo — primary
3. startd8 `pyproject.toml` — in-repo — primary

---

## RT-A4 + RT-B1 — Taint: build vs embed, and the algorithm

**Recommendation (BLUF):** **Hybrid taint strategy:** (1) **Python:** run **Pysa** as a subprocess (`pyre analyze --save-results-to`) for precise, sanitizer-aware taint in Phase 2/3 validation; (2) **Go/other:** **build** a lightweight **IFDS-inspired** taint pass over `CodeGraph` DATAFLOW + CALLS edges for Phase 2, escalating to full IFDS/IDE only if precision insufficient; (3) **Reject Semgrep CE embed** for cross-file taint — CE is **intraprocedural only**; interfile requires Semgrep Pro (commercial).

**Key findings:**

### Embed options

- **Semgrep CE engine** = **LGPL-2.1** — embeddable in principle (license + notices; dynamic link compliance) [verified] — https://github.com/semgrep/semgrep/blob/develop/LICENSE ; https://semgrep.dev/docs/faq/overview
- Semgrep CE **taint mode is intraprocedural only** — cannot track taint across functions or files [verified] — https://semgrep.dev/docs/writing-rules/data-flow/taint-mode/overview ; https://semgrep.dev/docs/faq/comparisons/opengrep
- **Interprocedural / interfile taint requires Semgrep Pro** (commercial) — explicitly not in CE [verified] — same sources
- Semgrep-maintained **rules** use Semgrep Rules License (not LGPL) — separate from engine; shipping default rules in SDK may be restricted [verified] — https://semgrep.dev/docs/faq/overview
- **Pysa** = **MIT**, flow-sensitive interprocedural taint for **Python only**, via **Pyre OCaml binary** — not a library embed; invocation = CLI + config files [verified] — https://github.com/facebook/pyre-check ; https://pyre-check.org/docs/pysa-basics/
- Pysa requires **type-aware resolution** (Pyre) — aligns with RT-D4 Python lane; ships prebuilt `.pysa` models for stdlib/framework sources/sinks [verified] — pyre-check `stubs/taint/`

### Build options (IFDS/IDE)

- **IFDS/IDE** (Reps–Horwitz–Sagiv) is the standard framework for interprocedural finite distributive subset problems including taint [verified] — academic baseline; survey: https://arxiv.org/abs/2103.16240
- **Heros** (soot-oss) = open IFDS/IDE **solver** (MIT/Apache-2.0) — language-agnostic *solver*, but requires custom **ICFG + flow functions per language** [verified] — https://github.com/soot-oss/heros
- FlowDroid uses a **specialized IFDS solver** (Java/Android) — pattern for high-performance taint, not reusable verbatim [reported] — Soot mailing list
- A **practical Phase 2 minimum** on our graph: treat `CodeGraph` DATAFLOW edges as def-use hints; run forward taint from tagged sources along **DATAFLOW ∪ CALLS** with sanitizer node subtraction — IFDS-lite without full SSA [inferred] — matches Phase 0 helper sketch
- Full IFDS on Go requires **CFG per function + call/return edges** — tree-sitter extraction must emit these graph facts (feeds REQ-MIE-330 evolution) [inferred]

**Decision impact:**

- Phase 2 Python taint: **Pysa subprocess** + ingest `taint-output.json` into findings logs (REQ-MIE-340) — validates RT-B1 before porting algorithm to Go
- Phase 2 Go taint: **build IFDS-lite on CodeGraph**; do not block on Semgrep/Pysa port
- REQ-MIE-330 DATAFLOW contract must include optional edge attrs: `via` (param name), `kind` (arg/return/field), `sanitizer` tags for future IFDS

**Licensing & clean-room check:**

| Tool | License | SDK embed? | CodeQL-independent? |
|------|---------|------------|---------------------|
| Semgrep CE | LGPL-2.1 | Possible but **insufficient** (intra only) | ✅ |
| Semgrep Pro | Commercial | ❌ | ✅ |
| Pysa/Pyre | MIT | Subprocess ✅ | ✅ |
| Heros IFDS solver | MIT/Apache-2.0 | Build path ✅ | ✅ |
| CodeQL | Custom/OSS-only | ❌ clean-room | ❌ (reference only) |

**Confidence:** Medium — licensing and capability limits verified; IFDS-lite effort on Go is estimated, not prototyped.

**Gaps / unknowns:** No head-to-head on our Go fixture: Pysa N/A; Semgrep CE intra-only baseline; coarse DATAFLOW vs IFDS-lite precision (RT-B4). LGPL subprocess Semgrep vs LGPL pip dependency legal review not performed — prefer subprocess if Semgrep ever used for intra-function rules only.

**Sources:**

1. Semgrep taint overview (interprocedural = Pro) — https://semgrep.dev/docs/writing-rules/data-flow/taint-mode/overview — primary
2. Semgrep CE languages / comparison — https://semgrep.dev/docs/semgrep-ce-languages — primary
3. Semgrep FAQ (LGPL engine) — https://semgrep.dev/docs/faq/overview — primary
4. Pysa basics — https://pyre-check.org/docs/pysa-basics/ — primary
5. Heros IFDS/IDE — https://github.com/soot-oss/heros — primary
6. IFDS taint with access paths (survey) — https://arxiv.org/abs/2103.16240 — secondary

---

## Cross-cutting

### Recommended P0 decisions, consolidated

1. **Resolver strategy (RT-A1):** Hybrid per language — Python stdlib+Jedi; Go syntactic + two-pass/import-aware Phase 1; optional SCIP subprocess for complete target index; do not depend on archived stack-graphs for Go/C# Phase 1.
2. **Python lane (RT-D4):** Stdlib-first extraction + Jedi optional; Pysa subprocess proves taint before Go IFDS port.
3. **Substrate (RT-C1):** `traces + persisted CodeGraph helper` — Tempo for coarse filters/dashboards; JSON graph for precision.
4. **DATAFLOW contract (RT-C3):** Attribute-encoded targets, not native Links, in Phase 1 schema.
5. **Dependencies (RT-D1):** Ship `[code-observability]` extra with tree-sitter ≥0.25; keep codebleu out of shared extras.
6. **Taint (RT-A4/B1):** Hybrid — Pysa (Python subprocess, MIT) + build IFDS-lite on CodeGraph (Go); reject Semgrep CE for cross-file taint.

### New questions surfaced (proposed RT-IDs)

| ID | Question | Why now |
|----|----------|---------|
| **RT-G1** | Go two-pass resolver spike: accuracy on cross-package CALLS vs `scip-go` on same fixture | RT-A1 left Go "syntactic vs resolved" acceptance split open |
| **RT-G2** | Pysa → CodeGraph findings ingest adapter (JSON schema mapping) | Hybrid taint needs a Keiyaku contract at the Pysa boundary |
| **RT-G3** | Can `csharp` extra migrate to tree-sitter 0.25 without breaking `tree-sitter-c-sharp` wheels? | pyproject already on 0.24; may need same isolation pattern as Go |
| **RT-G4** | Semgrep CE as **intra-function** rule engine only (subprocess) for quick wins alongside graph taint? | LGPL subprocess may be acceptable for narrow regex replacement |

### Suggested changes to existing docs

| File | REQ/OQ | Proposed edit |
|------|--------|---------------|
| `CODE_OBSERVABILITY_PHASE1_REQUIREMENTS.md` | REQ-MIE-210 | Clarify Jedi as optional `[code-observability]` dependency; split Go CALLS acceptance into syntactic (P1) vs resolved (P1.5) |
| `CODE_OBSERVABILITY_PHASE1_REQUIREMENTS.md` | REQ-MIE-320/330 | Record decision: DATAFLOW via `span.code.dataflow_targets` attributes; CodeGraph edges canonical |
| `CODE_OBSERVABILITY_PHASE1_REQUIREMENTS.md` | REQ-MIE-500 | Add concrete `code-observability` extra spec; note codebleu not in repo today — isolate if added |
| `CODE_OBSERVABILITY_DESIGN.md` | §2.4 / OQ#2 | State architecture = traces + CodeGraph helper explicitly (not traces-only) |
| `MIERUKA_DESIGN_PRINCIPLE.md` | Rule 4 | Footnote: "no parallel query system" permits persisted CodeGraph JSON + in-process helper, not a graph DB |
| `CODE_OBSERVABILITY_RESEARCH_AGENDA.md` | RT-A1 | Update priority note: stack-graphs archived 2025-09; add RT-G1 |
| `scripts/spikes/code_observability/PHASE0_FINDINGS.md` | — | Reference this findings doc as P0 research completion artifact |
