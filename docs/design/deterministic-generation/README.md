# Deterministic Generation — extending the $0 path across all languages

**Started:** 2026-08-18 · **Frame:** determinism = *complete contract × total projection*. The language-agnostic
spine (contract IR + SARIF findings + verify/repair + realization-% scoreboard) is largely built; the missing
leaf is the per-language **renderer** (contract → skeleton). Micro-prime uses the LLM exactly where a renderer
would be. The strategy: grow per-language renderers via a **SARIF determinism-ratchet** (metabolize recurring
generation findings into $0 templates) — the generation-side twin of the CRP review-theme metabolizer.

## Docs

| Doc | What |
|-----|------|
| `REQ-determinism-gap-census.md` | 🥇 **the first move** — SARIF-instrument the polyglot path (LLM-call + repair per finding-class × language × element-kind), run over the Round-3 fleet, produce the per-language determinism-% "where the LLM is load-bearing" report (the code-side twin of `CRP-INDEX`). det-req/0.1, handle `…-044ea2e6`. |
| `REQ-go-pilot-renderer.md` | the pilot proving per-language $0 render — a Go skeleton renderer **extending the existing `proto_codegen/skeleton_go` provider**, tiered (skeleton $0 / simple template / moderate micro-prime / complex LLM), measured by realization-% lift. det-req/0.1, handle `…-b724a712`. |
| `ARCHITECTURE_sarif-determinism-ratchet.md` | the tiered-projector architecture + the ratchet loop (proposed LOOP_CATALOG #9) + det-plan `costClass` as the routing manifest + cross-language transfer via the shared registry. |
| `ANALYSIS_neutral-spine-enablers.md` | the 3 plumbing enablers ranked: **(3) protoc wire-layer skeletons for java/csharp/nodejs** (highest leverage) → **(1) contract PRODUCTION-from-plan** (verify side already 5-lang neutral) → **(2) toolchain→SARIF ingestion** (highest ceiling, L effort). |

## Grounding corrections (the spine is MORE built than the deep-dive assumed)

- **A $0 renderer already exists for 2 languages:** `proto_codegen/skeleton_go.py:render_go_skeleton` renders a Go gRPC server skeleton, registered as the `proto-skeleton` deterministic provider (`_VALID_LANGS = {python, go}`). The Go pilot *extends* it; the general gap is java/csharp/nodejs skeletons + the service-internal skeleton around the wire stub.
- **The forward-manifest VERIFY side is already 5-language-neutral** — `languages/manifest_adapter.build_multilang_file_manifest` + `ForwardManifest.validate_implementation`. Only contract *production-from-plan* (`_extract_api_signatures` hard-gates `.py/.pyi`) is Python-bound. `SourceReconciler` already reconciles 4 languages.
- **SARIF is a rendering SINK, not an ingestion IR** — raw compiler/linter diagnostics still enter via Python-flavored regex in `repair/diagnostics.py`; toolchain→SARIF adapters are the (L-effort) neutralizer.
- **The finding→contract seam (`sarif_to_req_stub`) lives in `dev-os/det-req-kit/`, not the SDK** — the cross-repo half of the loop.
- **`realization.py` (REQ-18/19) is the ready scoreboard** — `determinism_pct`/`corpus_realization` + the measured-vs-declared label; the pilot just stamps `regime` per element to flip it to `measured`. Go baseline today = 0% (whole-file LLM).
- **Round-3 fleet covers 4/5 languages** (go/node/python/csharp; **Java absent**) — the census reads Java `absent`, never a false 0 (absence-vs-error).
