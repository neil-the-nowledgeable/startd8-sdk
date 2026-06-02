# Code Observability — Phase 0 Spike

Proof-of-concept for the "Code Observability (Mieruka)" design
(`docs/design/CODE_OBSERVABILITY_DESIGN.md`). Validates the end-to-end pipeline
**Go source → tree-sitter CodeGraph → OTel signals → taint reachability query**
and probes **Open Question #2** (can TraceQL / span-link traversal express
data-flow taint reachability?).

This is a **read-only spike**. It does not modify any SDK module. Everything
lives under `scripts/spikes/code_observability/`.

## Layout

| File | Purpose |
|------|---------|
| `fixture/sample.go` | Small realistic Go program: multi-level call chain + a deliberate source→sink taint path, plus a SAFE (parameterized) parallel path that must NOT be flagged. |
| `extractor.py` | tree-sitter Go → `CodeGraph` IR (CodeElement nodes; CALLS / DATAFLOW / DEFINES / REFERENCES edges). Writes `out/code_graph.json`. |
| `emit.py` | `CodeGraph` → OTel metrics + traces. CALLS = span tree, DATAFLOW = span links (recorded as resolved child span_ids). OTLP if reachable, else console; always mirrors to `out/spans.json` + `out/metrics.json`. |
| `taint_query_probe.py` | The OQ#2 experiment. Traverses the emitted spans two ways (CALLS-descendant ≈ TraceQL `>>`, vs. DATAFLOW-link chase) and reports the verdict. |
| `PHASE0_FINDINGS.md` | Findings + OQ#2 verdict + Phase 1 recommendation. |
| `out/` | Generated artifacts (gitignorable). |

## Setup (exact commands used)

The repo venv is Python 3.14. OTel SDK was already present. tree-sitter needed a
version bump (the Go grammar wheel is ABI 15; the installed core was 0.23.2 / ABI
13–14):

```bash
pip3 install --break-system-packages tree-sitter-go      # 0.25.0 (bundles Go grammar)
pip3 install --break-system-packages -U tree-sitter      # 0.23.2 -> 0.25.2 (ABI 15 support)
```

> Note: `--break-system-packages` was used because this environment's `python3`
> is a Homebrew interpreter under PEP 668. In the project venv, plain
> `pip3 install tree-sitter tree-sitter-go` (with tree-sitter >= 0.25) is enough.
> There is a pre-existing `codebleu` pin (`tree-sitter<0.23`) that warns on the
> upgrade; it is unrelated to this spike and unaffected at runtime.

Already installed (verified): `opentelemetry-sdk==1.39.1`,
`opentelemetry-exporter-otlp==1.39.1`.

## Run

```bash
python3 scripts/spikes/code_observability/extractor.py          # build CodeGraph
python3 scripts/spikes/code_observability/emit.py               # emit OTel signals
python3 scripts/spikes/code_observability/taint_query_probe.py  # OQ#2 experiment
```

Each is standalone; `emit.py` and the probe read the previous step's `out/` JSON.

### OTLP target

`emit.py` probes `localhost:4317` (gRPC). In this environment a full o11y stack
(kind cluster `o11y-dev-control-plane`: Grafana :3000, Mimir :9009, Loki :3100,
Tempo :3200, OTLP :4317/:4318) was running, so spans were exported to **real
Tempo**. If no collector is reachable it degrades to the console exporter; the
JSON mirror is always written so the probe runs regardless. Force console with
`--no-otlp`; point elsewhere with `--endpoint host:port`.

## What this proves

- tree-sitter gives a **real AST** with accurate, nested call resolution that the
  SDK's regex `go_parser.py` explicitly cannot (its own docstring, line 17: *"Does
  not parse function bodies (no call graph extraction)"*).
- The CodeGraph maps cleanly onto OTel: metrics (gauges), a CALLS span tree, and
  DATAFLOW span links.
- Taint reachability (`source → sink`) is answerable by traversing the emitted
  structure — see `PHASE0_FINDINGS.md` for the nuanced OQ#2 verdict.
