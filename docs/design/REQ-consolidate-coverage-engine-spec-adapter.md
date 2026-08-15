# Consolidate per-language coverage generators into a CoverageEngine + spec + adapter — Requirements

**Project:** startd8-sdk · language×domain coverage-map engine   **Criticality:** medium
**Version:** 0.2 (Post-planning — self-reflective update)   **Date:** 2026-08-15
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** `PLAN-consolidate-coverage-engine-spec-adapter.md`
**Inherits standards:** det-req-kit · DIDL · `dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md` (the pattern this engine-ifies)
**Audience:** operator (SDK maintainer running/extending the coverage generators)

> **DIDL:** Semantic name — *Consolidate per-language coverage generators into one CoverageEngine + a
> per-language CoverageSpec + a CoverageAdapter*. Planned canonical ref —
> `cc:intent:coverage-map:requirement:engine-consolidation`. Readable handle —
> `REQ-consolidate-coverage-engine-spec-adapter.md`.

## 0. Planning Insights (Self-Reflective Update)

> Four language variants (Python/Go/Java/Node) were built by mirroring one skeleton — the recurrence is
> proven (past the 3× "don't abstract early" bar), and the duplication is now the accidental complexity to
> distill. Grounding the existing SDK layer + the OpenAPI work reshaped the spec twice.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| We need a new language-adapter abstraction | `startd8/languages/protocol.py` **already** defines `LanguageProfile` with `import_pattern_template` (the per-language import regex template), `framework_imports`, `source_extensions`, `package_alias_map`. | Reuse/extend `LanguageProfile`; don't invent a parallel adapter (Mottainai). → FR-3, NR-3 |
| The 6 scripts differ meaningfully | Analyzers are ~90% identical; the only real per-language deltas are **import-extractor · path separator · extensions · annotations-yes/no**. | The shared engine is large; the adapter is tiny. → FR-1, FR-2 |
| Coverage might overlap the OpenAPI work | **No — different altitude.** `deterministic-openapi` (Role 1/2/3) + `backend_codegen/openapi_*` own HTTP **endpoint precision** (paths/methods/schemas); we own domain **touch** (imports). | Add a boundary: HTTP precision is OpenAPI's; the engine never rebuilds it. → NR-5 |
| Build a general parser/DSL | The reusable core is a *matcher + generator skeleton*, not a parser (the SDK already parses). A regex DSL / parser-combinator layer would be over-abstraction. | Thin factoring only — one module + one spec + one adapter shape. → NR-4 |

**Resolved open questions:**
- **OQ-1 → The engine is functional + data-driven:** `CoverageEngine(spec, adapter)`; spec = data, adapter = the 4 deltas.
- **OQ-2 → HTTP precision is out of scope** and owned by the OpenAPI work; the coverage engine stays at domain-touch granularity.

## Overview

Distill the four near-identical per-language coverage generators/analyzers into **one reusable engine**
(`startd8/coverage_map/engine.py`) + a per-language **`LanguageCoverageSpec`** (the data: L1 forms, L3
composites, L4 crosswalk φ, floor, resolution-pending) + a thin **`CoverageAdapter`** (the 4 deltas:
import-extractor, path separator, source extensions, has-annotations), reusing `LanguageProfile` where it
fits. Each `gen_*`/`analyze_*` script becomes a thin spec+adapter handed to the engine. Behaviour-preserving:
the emitted artifacts and coverage numbers stay byte-identical. This is the `/complexity-distiller`
consolidation of the pattern proven across Go/Java/Node.

## Objectives

- O-1: One shared engine consumed by all per-language scripts; the copy-pasted skeleton removed.
- O-2: Byte-identical outputs — Go 46.2%(6), Java 38.5%(5), Node 23.1%(3) unchanged; all 62 tests green.
- O-3: A `LanguageCoverageSpec` that is *also* a reusable artifact — drivable by future views (instrumentation-gap, cross-repo domain matrix) beyond coverage.
- O-4: Reuse `LanguageProfile`/`PARSER_KIND_SETS`; add no parser, no DSL, no plugin framework (Mottainai + anti-accidental-complexity).

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | The refactor silently changes an emitted artifact or coverage number | `--check` must stay exit 0 for all 3; diff analyzer summaries before/after; 62 tests green | high |
| quality | Over-abstraction — a framework that serves only 3 languages | Hard guard: one module + one dataclass + one adapter; reject any indirection that doesn't remove duplication | high |
| quality | Forcing a fit onto `LanguageProfile` where it doesn't match | If it doesn't fit cleanly, document why and keep a minimal adapter rather than contort | medium |

## Profile

Declared profile: **internal**

## Functional requirements

- **FR-1 — Shared functional core.** `startd8/coverage_map/engine.py` owns the reusable skeleton:
  `serialize`/`sha`, `write_or_check` (drift guard, exit 1 on drift), `render_index_md(spec)`, and a
  `Detector` (`matches(spec, sig, separator)` + `hyp(imports, annotations, crosswalk)` +
  `coverage_report` with the achievable-vs-floor split). Touches: engine-module. Verify: the three generators produce byte-identical JSON+.md via the engine (`--check` exits 0). Serves: O-1, O-2
- **FR-2 — `LanguageCoverageSpec` dataclass.** The per-language DATA (structure_forms, composites +
  not_witnessable, crosswalk, floor, resolution_pending, substrate/tier) as one typed object the engine
  consumes. Touches: engine-module. Verify: each language's spec round-trips to the same on-disk JSON as today. Serves: O-1, O-3
- **FR-3 — `CoverageAdapter` reusing `LanguageProfile`.** The per-language deltas (source extensions,
  import-extractor callable, path separator, has_annotations) bound to the existing
  `startd8/languages/protocol.py` `LanguageProfile` (`import_pattern_template`/`source_extensions`) where it
  fits; a minimal standalone adapter only where it does not (documented). Touches: engine-module, `src/startd8/languages/protocol.py`. Verify: the Go/Node adapters use the same import mechanism they do today; the Java adapter carries the annotation flag; no `*_parser.py` modified. Serves: O-1, O-4
- **FR-4 — Thin per-language scripts.** Each `gen_*`/`analyze_*` becomes a spec+adapter handed to the
  engine, with no duplicated skeleton. Touches: gen-scripts, analyze-scripts. Verify: the 6 scripts shrink to spec+adapter+`main` shims; combined LOC drops materially; behaviour byte-identical. Serves: O-1, O-2
- **FR-5 — Parity harness.** A characterization test asserts the engine's output equals the committed
  artifacts for all three languages (guards the behaviour-preserving contract). Touches: parity-test. Verify: mutating the engine in a behaviour-changing way fails the harness; the 62 existing tests still pass unchanged. Serves: O-2

## Non-goals

- **NR-1 — Do not refactor the Python generator** (`gen_python_ast_capability_index.py`) — it is reflection-based, structurally different; cite as prior art, leave it.
- **NR-2 — Do not touch any `*_parser.py`.** The engine consumes parsers; it does not change them.
- **NR-3 — Do not invent a parallel language-adapter registry** if `LanguageProfile` fits — extend it.
- **NR-4 — Do not build a regex DSL / parser-combinator / plugin framework / config-file layer.** The
  reusable core is a matcher + skeleton; over-abstraction is itself accidental complexity.
- **NR-5 — Do not extract endpoint/operation precision for ANY domain.** The precision layer is a
  **per-domain contract-IDL registry**, and each IDL has an SDK owner to *cite, never rebuild* — the engine
  stays at domain-*touch* granularity and a future precision pivot **consumes** these:
  - **http → OpenAPI** — `deterministic-openapi` (Role 1/2/3) + `backend_codegen/openapi_*` + `validators/openapi_spec_gate.py`.
  - **rpc → Protocol Buffers (`.proto`)** — `proto_codegen/proto_parser.py` + `grpc_manifest.py` + `backend_codegen/context_grpc_client_renderer.py`.
  - **db → Prisma schema / DDL** — `languages/prisma_parser.py` + `validators/prisma_zod_symmetry.py`.
  - **graphql → GraphQL SDL** — *partial* (`benchmark_matrix/behavioral/graphql_pricing_suite.py` only; no SDL contract extractor yet — a build-if-needed frontier).
  - **messaging → AsyncAPI / CloudEvents** — *absent* (the other build-if-needed frontier).
  The precision layer is coverage's twin: coverage = "domain → import signatures"; precision = "domain → contract IDL + its extractor".

## Owned fields

Only humans enter: the per-language signature tables (they stay authored data in each spec).

## Contract projection

- **Backend:** python-cli-surface
- **Vocabulary home (cite):** `det-req-kit/SCHEMA.md` §8; the pattern = `dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md`; the adapter home = `startd8/languages/protocol.py` (`LanguageProfile`).

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| engine-module | console-script | structure | `src/startd8/coverage_map/engine.py` — the shared functional core (consumed by the scripts) |
| gen-scripts | console-script | structure | `gen_{go,java,node}_structure_comm_index.py` — thinned to spec+adapter |
| analyze-scripts | console-script | structure | `analyze_{go,java,node}_comm_coverage.py` — thinned to spec+adapter |
| parity-test | console-script | structure | characterization harness (behaviour-preserving guard) |

> The engine module is a library consumed by the console-scripts; named as a file-path Touches entry, not a CLI verb.

---

## Appendix A — Accepted (with where merged)

## Appendix B — Rejected (with rationale)

## Appendix C — Incoming review rounds

---

### 0.1 Lessons-Learned Hardening (v0.3)

- **[Phantom-reference audit]** — verified extant: `LanguageProfile` + `import_pattern_template` +
  `framework_imports` (protocol.py), `PARSER_KIND_SETS`, the 6 scripts, the 62 tests, `deterministic-openapi`
  + `backend_codegen/openapi_*` + `openapi_spec_gate`.
- **[Single-source vocabulary ownership]** — the pattern is owned by `dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md`;
  this engine is its executable single-source; per-language signatures stay authored data (owned fields).
- **[Prune phantom scope]** — HTTP-precision was pruned to NR-5 (owned by OpenAPI); the parser-DSL to NR-4.
- **[CRP steering]** — least-reviewed surface = the `LanguageProfile` fit (FR-3) — does the existing profile
  cleanly carry the import-extractor, or is a minimal adapter needed?

### 0.2 Design-Principle Hardening (v0.3.1)

- **[Accidental-Complexity (anti) — dominant]** — the whole REQ is this principle: distill duplication to a
  single source, with a hard guard against replacing it with a heavier framework (NR-4). Prefer deleting
  duplication to adding a layer.
- **[Mottainai]** — reuse `LanguageProfile`/`PARSER_KIND_SETS`; cite the OpenAPI work for HTTP precision; add
  no parser (NR-2/3/5).
- **[Kagami]** — the engine keeps the generated-artifact/drift-guard discipline (the `--check` contract) intact.
- **[Genchi Genbutsu]** — the behaviour-preserving contract is verified against the *real* committed artifacts
  + the 62 real tests (FR-5 characterization harness), not asserted.

*v0.3.1 — Post lessons + principle hardening. 4 planning discoveries (LanguageProfile reuse; OpenAPI boundary;
thin-factoring-not-DSL; engine-is-functional). Behaviour-preserving consolidation, guarded against over-abstraction.*
