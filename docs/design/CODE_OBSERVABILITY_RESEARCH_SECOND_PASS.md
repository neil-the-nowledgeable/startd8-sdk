# Code Observability — Research Findings Second Pass

> **Date:** 2026-06-01  
> **Scope:** Independent second pass over P0 research topics from `CODE_OBSERVABILITY_RESEARCH_BRIEF.md`  
> **Relationship to first-pass findings:** Uses `CODE_OBSERVABILITY_RESEARCH_FINDINGS.md` as a hypothesis set, not as validated fact. This document records confirmations, corrections, and added recommendations.

---

## Executive Summary

| Topic | Second-pass recommendation | Confidence | Blocking? |
| --- | --- | ---: | --- |
| RT-A1 — Name/scope resolution | Hybrid resolver strategy. Do not rely on stack-graphs as universal resolver; use Python-native/Jedi, Go lightweight resolver or SCIP, and SCIP for buildable Java/C#/TS targets. | High | No |
| RT-D4 — Python-native stack | Stdlib is enough for a first static export/import resolver, but Jedi is the practical fallback. Pysa is subprocess-only, not an embeddable library. | High | No |
| RT-C1 — Traces vs graph store | Use traces plus persisted `CodeGraph` helper. Traces-only fails precise taint; graph DB is not justified yet. | High | No |
| RT-C3 — Span-link mechanics | Canonicalize DATAFLOW in `CodeGraph`; emit target IDs as attributes. Optionally also emit OTel Links as enrichment. | Medium-High | Yes, schema decision |
| RT-D1 — tree-sitter/codebleu | Isolate `[code-observability]`; keep CodeBLEU separate. First-pass overstated the exact `tree-sitter>=0.25` requirement. | High | Yes |
| RT-A4 + RT-B1 — Taint | Hybrid: Pysa for Python validation; build IFDS-lite/SSA-informed graph taint for Go/other; Semgrep CE is insufficient for cross-file taint. | Medium | No |

The first-pass research is directionally right: precise taint cannot be delegated to TraceQL, and the architecture should be `OTel + CodeGraph helper`, not traces-only. The second pass found three material corrections: current OTel specs allow Links after span creation while the span is open; `tree-sitter-go` 0.25 metadata does not by itself prove a hard Python core `>=0.25` dependency; and Heros appears to be LGPL-2.1, not permissive MIT/Apache.

---

## Disagreements And Corrections

### OTel Links

**Correction:** The first pass overstated that Links must be present only at span creation.

- [verified] OTel trace API says a span must support adding Links after creation, while the span is still active.
- [inferred] The real practical constraint is that the target `SpanContext` must exist and the source span must not yet be ended.
- [inferred] The Phase 1 schema should still not depend on native Links, because Tempo/TraceQL does not provide production-grade transitive link traversal for precise DATAFLOW.

**Revised recommendation:** Keep `CodeGraph.DATAFLOW` canonical. Emit `span.code.dataflow_target_ids` attributes for stable Tempo visibility. Optionally emit native OTel Links as enrichment when the emitter can do so without changing traversal semantics.

### tree-sitter-go / CodeBLEU Pin

**Correction:** The first pass overstated that `tree-sitter-go==0.25` definitively requires Python `tree-sitter>=0.25`.

- [verified] `codebleu==0.7.0` declares `tree-sitter<0.23.0,>=0.22.0`.
- [verified] `tree-sitter-go` 0.25 metadata points to `tree-sitter~=0.24`.
- [verified] tree-sitter 0.25 introduced ABI 15 support, but the packaging conflict should be proven by an install matrix before encoding exact pins.

**Revised recommendation:** Add a `[code-observability]` extra with tested pins, and keep CodeBLEU in a separate extra or subprocess environment. Do not document `tree-sitter>=0.25` as a verified requirement until a clean install probe confirms it.

### Heros License

**Correction:** The first pass listed Heros as MIT/Apache-2.0.

- [verified] Second-pass lookup reports `soot-oss/heros` as LGPL-2.1.
- [inferred] Heros should not be treated as a permissive embeddable SDK dependency without legal review.

**Revised recommendation:** Avoid Heros as an in-process SDK dependency. If an IFDS solver is needed, either build a small solver over `CodeGraph`, isolate any LGPL component by subprocess with legal review, or choose a confirmed permissive alternative.

---

## New Or Underweighted Insights

- [verified] `stack-graphs` language rules are hand-authored TSG files. Existing support does not make Go/C# adoption a configuration task; it is a language-engineering project.
- [verified] `github/stack-graphs` is archived and no longer GitHub-supported, which raises maintenance risk even though the license is SDK-compatible.
- [verified] SCIP deserves more weight for complete target indexing. Active Apache-2.0 indexers exist for Go, Java, TypeScript, and C#.
- [inferred] SCIP complements rather than replaces tree-sitter: it is strongest for complete/buildable target projects, while tree-sitter remains the partial-code extractor for inner-loop artifacts.
- [verified] `importlib.util.find_spec()` can import parent packages while resolving dotted names. Use path-based project import maps where side effects matter.
- [verified] Semgrep CE is useful for intra-function quick wins, but interprocedural and interfile taint are Semgrep Pro features.

---

## Consolidated Recommendations

1. **Resolver strategy:** Use per-language best fit. Python gets stdlib + optional Jedi. Go starts with lightweight two-pass import/package resolution and is compared against `scip-go` on buildable targets. Java/C#/TS consume SCIP where build context exists; tree-sitter remains the partial-code extractor.
2. **Substrate:** Keep Mieruka as `OTel + CodeGraph helper`, not traces-only and not a graph DB. Introduce a graph DB only after measured `CodeGraph` size or query latency forces it.
3. **DATAFLOW contract:** Treat `CodeGraph.DATAFLOW` as authoritative. Emit `span.code.dataflow_target_ids` attributes for Tempo visibility. Add native OTel Links only as optional enrichment.
4. **Dependency fix:** Add `[code-observability]` with tested tree-sitter pins. Add `[evaluation-codebleu]` or use a separate venv for CodeBLEU.
5. **Taint:** Validate Python with Pysa via `pyre analyze --save-results-to`. Build a small IFDS-lite/SSA-informed taint pass over `CodeGraph` for Go. Do not embed Semgrep CE as the cross-file taint engine.

---

## Remaining Gaps And Experiments

- Run a clean install matrix for `tree-sitter-go==0.25.0` with `tree-sitter` 0.24.x vs 0.25.x and `codebleu==0.7.0`.
- Benchmark stdlib-only Python resolver vs Jedi on a 3-level cross-file fixture with alias imports and star imports.
- Compare Go two-pass resolver vs `scip-go` on one buildable OSS target and one partial/non-compiling fixture.
- Prototype DATAFLOW emission both ways: attributes-only and attributes plus native Links; verify Python SDK exporter behavior after `add_link`.
- Measure IFDS-lite false positives on OWASP/Juliet-style fixtures before committing Phase 2 taint acceptance.

---

## Key Sources

1. [Stack-graphs repository metadata](https://api.github.com/repos/github/stack-graphs)
2. [Stack-graphs language rules discussion](https://api.github.com/repos/github/stack-graphs/issues/420/comments)
3. [tree-sitter-stack-graphs docs](https://docs.rs/tree-sitter-stack-graphs/latest/tree_sitter_stack_graphs/)
4. [SCIP protocol and indexers](https://github.com/sourcegraph/scip)
5. [`scip-go` package docs](https://pkg.go.dev/github.com/sourcegraph/scip-go)
6. [`scip-dotnet` repository](https://github.com/sourcegraph/scip-dotnet)
7. [Python `ast` docs](https://docs.python.org/3/library/ast.html)
8. [Python `symtable` docs](https://docs.python.org/3/library/symtable.html)
9. [Python `importlib.util.find_spec` docs](https://docs.python.org/3/library/importlib.html#importlib.util.find_spec)
10. [Jedi features](https://jedi.readthedocs.io/en/latest/docs/features.html)
11. [Pysa running guide](https://pyre-check.org/docs/pysa-running/)
12. [Tempo TraceQL docs](https://grafana.com/docs/tempo/latest/traceql/construct-traceql-queries/)
13. [Tempo trace-size troubleshooting](https://grafana.com/docs/tempo/latest/troubleshooting/out-of-memory-errors/)
14. [OpenTelemetry add-link API](https://opentelemetry.io/docs/specs/otel/trace/api/#add-link)
15. [Semgrep taint mode](https://semgrep.dev/docs/writing-rules/data-flow/taint-mode/overview)
16. [Semgrep FAQ and licensing](https://semgrep.dev/docs/faq/overview)
17. [`tree-sitter-go` 0.25 metadata](https://raw.githubusercontent.com/tree-sitter/tree-sitter-go/v0.25.0/pyproject.toml)
18. [CodeBLEU 0.7.0 PyPI metadata](https://pypi.org/pypi/codebleu/0.7.0/json)
19. [IFDS original paper](https://research.cs.wisc.edu/wpis/papers/popl95.pdf)
20. [IFDS taint with access paths](https://arxiv.org/abs/2103.16240)
