# Precision layer — extract §5 operations from contract IDLs (Tier 2) — Requirements

**Project:** startd8-sdk · OTel comm coverage map · Tier 2   **Criticality:** medium
**Version:** 0.2 (Post-planning — self-reflective update)   **Date:** 2026-08-15
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** `PLAN-precision-layer-contract-idl-operations.md`
**Inherits standards:** det-req-kit · DIDL · `dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md` (§ three-tier stack)
**Audience:** operator (SDK maintainer running the precision analyzer)

> **DIDL:** Semantic name — *Extract precise §5 operations from a repo's contract IDLs (the precision tier)*.
> Planned canonical ref — `cc:intent:coverage-map:requirement:precision-tier`. Readable handle —
> `REQ-precision-layer-contract-idl-operations.md`.

## 0. Planning Insights (Self-Reflective Update)

> This tier answers the open question the session's headline finding raised: **domain coverage saturates at
> imports; value is in precision.** Grounding was decisive enough (all three IDL parsers already exist in the
> SDK, verified against real IDLs) that I built the first slice *before* the full spec — a defensible deviation
> for a pure-wiring task; §0 records the discoveries.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| Precision needs new IDL parsers | **All three already exist**: `backend_codegen.openapi_normalize.load_openapi_document`, `proto_codegen.proto_parser.parse_proto`, `languages.prisma_parser.parse_prisma_schema` — verified on real IDLs (kestra 173 paths, otel 10 services). | Pure wiring (Mottainai). → FR-1, NR-1 |
| Precision extracts from code | The IDL-based path is far cheaper + authoritative; the SDK owns IDL parsers, not code-route extractors. | Scope = **IDL-file-based**; code-route extraction is a harder future path. → NR-2 |
| Every repo has precision | Precision exists only where a contract IDL is in the repo (many don't ship one). | `precision_available: false` = coverage-only, a **correct-absence** (mirrors the coverage floor). → FR-2 |
| OpenAPI parser is version-agnostic | `load_openapi_document` accepts only OpenAPI 3.0.x (rejects swagger 2.0 — e.g. Harbor). | Un-parseable IDLs are recorded as `parse_errors`, not crashes. → FR-4 |

## Overview

The Tier-2 **precision layer**: given a repo the coverage map says *touches* a §5 domain, extract *which
operations* by parsing the domain's **contract IDL** via the SDK's existing parsers — http→OpenAPI,
rpc→Protocol Buffers, db→Prisma. It is coverage's structural twin (coverage = "domain → import signatures";
precision = "domain → contract IDL + its parser"), keyed on the same §5 domains. Adds **no parser**.

## Objectives

- O-1: For http/rpc/db, extract the precise operation set from a repo's contract IDL(s), with provenance.
- O-2: Honest `precision_available` — no IDL ⇒ coverage-only (correct-absence), never a false zero.
- O-3: Zero new parsing — wire `load_openapi_document` / `parse_proto` / `parse_prisma_schema` (Mottainai).

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | A malformed / wrong-version IDL crashes the analyzer | per-file try/except → `parse_errors`; verified on swagger 2.0 | high |
| quality | IDL globs miss real specs (unusual filenames) | broad globs (openapi*/swagger*/api.yaml, *.proto, *.prisma); extend as corpora surface | medium |

## Profile

Declared profile: **internal**

## Functional requirements

- **FR-1 — Per-domain precision registry wiring the SDK IDL parsers.** `coverage_map/precision.py` maps
  http→`load_openapi_document`, rpc→`parse_proto`, db→`parse_prisma_schema`, each with IDL file-globs and an
  operation extractor. Touches: precision-module. Verify: `PRECISION_DOMAINS` has http/rpc/db; each extractor imports the named SDK parser; no `*_parser` reimplemented. Serves: O-1, O-3
- **FR-2 — `extract_precision(repo, domain)` → operations + provenance + availability.** Returns idl_files
  (path + operations + count), total_operations, parse_errors, and `precision_available`. Touches: precision-module. Verify: over a repo with an OpenAPI spec, returns the endpoints with SERVER role + the spec path; a repo with no IDL returns `precision_available=false`, `total=0`, `parse_errors=[]`. Serves: O-1, O-2
- **FR-3 — Precision analyzer CLI.** `analyze_precision.py --workdir <repo> [--domain d] [--out]` reports
  per-domain operation counts + samples + provenance. Touches: analyze-precision, opt-domain. Verify: over `OSS/kestra --domain http` prints the 192 endpoints + `openapi.yml`; over the otel-demo `--domain rpc` prints the proto service methods. Serves: O-1
- **FR-4 — Un-parseable IDLs are recorded, not fatal.** A non-3.0 / malformed IDL becomes a `parse_errors`
  entry; other IDLs still extract. Touches: precision-module. Verify: a swagger-2.0 spec yields a parse_error, not an exception. Serves: O-2
- **FR-5 — Test the wiring on fixtures.** Fixtures for OpenAPI/proto/Prisma assert the extractors wire the
  real parsers. Touches: precision-test. Verify: `test_precision_layer.py` green (endpoints, service.methods, models, correct-absence). Serves: O-1

## Non-goals

- **NR-1 — Do not reimplement any IDL parser.** Cite `openapi_normalize` / `proto_parser` / `prisma_parser`.
- **NR-2 — Do not do code-based route/endpoint extraction** (route decorators in source). IDL-file-based only;
  code-route extraction is a separate, harder future path (and overlaps the resolution tier).
- **NR-3 — Do not extend the coverage domain set here.** Precision is keyed on the existing §5 domains.
- **NR-4 — Do not add GraphQL/AsyncAPI extraction yet.** The SDK doesn't own those parsers (build-if-needed
  frontier); http/rpc/db are the three it already owns.

## Owned fields

Only humans enter: any curated glob additions in `PRECISION_DOMAINS`.

## Contract projection

- **Backend:** python-cli-surface
- **Vocabulary home (cite):** `det-req-kit/SCHEMA.md` §8; IDL parsers = `backend_codegen/openapi_normalize.py`, `proto_codegen/proto_parser.py`, `languages/prisma_parser.py`.

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| precision-module | console-script | structure | `src/startd8/coverage_map/precision.py` — the per-domain IDL registry |
| analyze-precision | console-script | structure | `python3 scripts/analyze_precision.py` |
| opt-domain | option | words | `--domain {http,rpc,db}` |
| precision-test | console-script | structure | `tests/unit/languages/test_precision_layer.py` |

---

## Appendix A — Accepted (with where merged)
## Appendix B — Rejected (with rationale)
## Appendix C — Incoming review rounds

---

### 0.1 Lessons-Learned Hardening (v0.3)

- **[Phantom-reference audit]** — verified extant + smoke-tested: `load_openapi_document` (kestra 173 paths),
  `parse_proto` (otel 10 services), `parse_prisma_schema` (PrismaSchema.models). No phantom parsers.
- **[Single-source vocabulary ownership]** — the IDL semantics are owned by their SDK parsers; precision cites them.
- **[Prune phantom scope]** — code-route extraction + GraphQL/AsyncAPI pruned to NR-2/NR-4 (not SDK-owned).

### 0.2 Design-Principle Hardening (v0.3.1)

- **[Mottainai — dominant]** — the entire tier is wiring three existing parsers; no new parser (NR-1).
- **[Genchi Genbutsu]** — extractors verified against real IDLs (kestra/otel/email-py), not assumed.
- **[Accidental-Complexity (anti)]** — resisted a generic "IDL framework"; three small extractors + one registry.
- **[Kagami]** — the analyzer output is a report (not a drift-guarded index); no hand-edit surface.

*v0.3.1 — Post lessons + principle hardening. 4 planning discoveries. Built-first (decisive grounding, pure wiring);
proves the precision tier the whole map was building toward. Ready for CRP-lite.*
