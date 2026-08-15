# OTel Communication Coverage Map — what we're building, what it does, why

> **BLUF.** A per-language system that answers, *from static code*, **"which OpenTelemetry communication
> domains does this codebase touch, and how completely?"** — by crosswalking a language's parseable
> structural surface to the **OTel §5 semantic-convention domains** (http, rpc, mcp, messaging, db, graphql,
> faas, feature-flags, gen-ai, cicd, cli, dns, cloud, …; **16** after the 2026-08-15 registry calibration).
> Four languages are built (Python, Go, Java, Node/JS-TS); the shared machinery is consolidated into one
> reusable `CoverageEngine` (`src/startd8/coverage_map/`).
>
> **Pattern (the standard):** [`dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md`](../../../dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md).
> **This doc:** the initiative front-door for the startd8-sdk implementation.

---

## 1. What it is

For each language, a **four-layer index** cross-walking code structure → OTel semconv domains, plus a
**coverage analyzer** that runs it over a real corpus:

| Layer | What it holds |
|-------|---------------|
| **L1 — structural-element surface** | the declaration forms the language's parser exposes (`GO-STRUCT-*`, `JAVA-STRUCT-*`, …) |
| **L2 — element kinds** | the shared, language-agnostic `ElementKind` lattice (reused from `startd8/languages/manifest_adapter`) |
| **L3 — language composites** | idiom clusters (receiver-methods, interface-impl, async, …), declaration-level only |
| **L4 — crosswalk φ** | the map from each of the **16 §5 domains** → the signals that hypothesize it (import specifiers, and for Java, annotations), with a **detectability floor** for what the substrate can't witness |

The §5 domains (16 after calibration) are the **invariant** — identical across every language. Only the *signals* change.

## 2. What it can do

- **Domain coverage:** given any repo, report which §5 communication domains its code touches and a
  coverage % — e.g. Go/`OSS/Thanos` **46.2%** (http, rpc, object-store, cli, dns, cloud-sdk); Java/`OSS/kestra`
  **38.5%**; Node/`MCP/` **21.4%** (http, mcp, gen-ai).
- **Honest gaps:** distinguish a *coverage gap* (a domain the corpus doesn't touch) from a **correct-absence**
  (a domain the *substrate structurally can't witness* — e.g. HTTP-metrics/CICD at the import tier), so an
  empty cell never reads as a false negative.
- **Provenance-tagged signals:** each φ signature is `grounding: corpus | ecosystem`, which *predicted the
  coverage result exactly* (the corpus-tagged signatures are the ones that fire).
- **Drift-proof artifacts:** every index (JSON + `.md`) is generated and `--check`-guarded (hand-edits fail);
  the generator is the single source (Kagami).
- **Portable findings:** `--sarif <path>` emits **SARIF 2.1.0** (rules = §5 patterns, results = file×domain) — consumable by GitHub code scanning, IDEs, any static-analysis viewer.

## 3. Why (the findings that justify it)

- **Domain coverage is an imports-only game** (confirmed across 4 ecosystems). The φ-richness ladder —
  *imports < +annotations < +call-sites* — does **not** buy more coverage; Java's annotation axis added
  **0 marginal coverage** (annotations co-occur with their package imports). Coverage *saturates at imports*.
  → the cheap tier is the right tier for "does it touch domain X."
- **The richer signals buy PRECISION, not coverage** — *which* element is the endpoint, its CLIENT/SERVER
  role, whether the call happened. That reframed the whole program (see §5).
- **Substrate tiering is real and per-parse** — an "authoritative" parser (Java/javalang) that isn't
  installed **degrades to advisory (regex)** for that parse, emitting a *subset* of kinds. We test this
  empirically, not assume it.
- **No such crosswalk existed in the SDK** — this is genuine gap-fill (Mottainai-clear), and the crosswalk is
  a candidate reusable SDK asset (a static-code → semconv classifier).

## 4. How it's built (architecture)

**A three-tier stack, all keyed on the same 16 semconv domains:**

```
  imports (touch)  →  contract IDLs (precision)  →  SCIP (resolution / call-flow)
  [built now]         [mostly already in the SDK]    [SDK roadmap: scip-typescript Ph1 …]
```

- **Tier 1 — coverage (this system):** import (+annotation) signals → domain touch. Advisory-tier, cheap, done.
- **Tier 2 — precision:** a **per-domain contract-IDL registry**, coverage's twin — http→**OpenAPI**,
  rpc→**Protocol Buffers `.proto`**, db→**Prisma/DDL**, graphql→**GraphQL SDL**, messaging→**AsyncAPI**. The SDK
  already owns OpenAPI, proto (`proto_codegen`), and Prisma extractors — the pivot is mostly *wiring*, and only
  GraphQL SDL + AsyncAPI are a build-if-needed frontier.
- **Tier 3 — resolution:** real call-sites via **SCIP** indexers (CKG roadmap: scip-typescript Phase 1,
  scip-go Phase 3, scip-java/scip-dotnet Phase 4). Only Python resolves today.

**Reusable factoring (landed):** the four per-language generators/analyzers are ~90% identical, so they
are distilled into **one `CoverageEngine` + a per-language `LanguageCoverageSpec` (data) + a thin
`CoverageAdapter`** (import-extractor · path separator · extensions · has-annotations), reusing the existing
`LanguageProfile` (`import_pattern_template`) where it fits. Payoff: the next languages become *data, not code*.

## 5. Status & roadmap

| | State |
|---|---|
| **Tier A (parser exists)** | ✅ **complete** — Python 70.6%, Go 46.2%, Java 38.5%, Node 21.4% |
| **Consolidation** | ✅ landed — CoverageEngine + spec + adapter in `src/startd8/coverage_map/` (behaviour-preserving; 68 tests green) |
| **Tier B (build a parser first)** | ⏳ Ruby, Swift, PHP, Rust, C++, Erlang — each just a new spec+adapter once a regex parser exists |
| **Precision pivot (Tier 2)** | ⏳ wire the per-domain contract-IDL extractors (OpenAPI/proto/Prisma already exist) |
| **Resolution (Tier 3)** | ⏳ SCIP; TS is the nearest unlock |

## 6. Map of the work (pointers)

- **Pattern / standard:** `dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md` · adoption hardening in `dev-os/REFLECTIVE-ADOPTION.md` (Instances P, Q)
- **Per-language cells (REQ + PLAN, DIDL-named):**
  - `REQ-/PLAN-crosswalk-go-structure-to-otel-comm-domains.md`
  - `REQ-/PLAN-crosswalk-java-structure-to-otel-comm-domains.md`
  - `REQ-/PLAN-crosswalk-node-structure-to-otel-comm-domains.md`
- **Consolidation:** `REQ-/PLAN-consolidate-coverage-engine-spec-adapter.md`
- **Generated artifacts:** `docs/design/{go,java,node}-capability-index/` + `*_STRUCTURE_COMMUNICATION_CAPABILITY_INDEX.md`
- **Code:** `scripts/gen_<lang>_structure_comm_index.py` · `scripts/analyze_<lang>_comm_coverage.py` · tests `tests/unit/languages/test_<lang>_index_parity.py`
- **Consumed SDK layer (cite, don't rebuild):** `startd8/languages/` (parsers, `manifest_adapter`, `protocol.py`) · `deterministic-openapi` + `proto_codegen` + `prisma_parser` (Tier-2 IDLs) · `CODE_KNOWLEDGE_GRAPH_DESIGN.md` (Tier-3 SCIP)
