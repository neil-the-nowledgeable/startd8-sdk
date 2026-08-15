# Precision layer — extract §5 operations from contract IDLs (Tier 2) — Plan

**Pairs with:** `REQ-precision-layer-contract-idl-operations.md` (v0.3.1)
**DIDL:** planned canonical ref `cc:intent:coverage-map:plan:precision-tier` (mirrors the REQ's; no integer-led identity).
**Date:** 2026-08-15   **Scope:** S-size wiring (built-first; decisive grounding)

> The three IDL parsers already exist in the SDK, so this is wiring, not building. Built-first because
> grounding was decisive (parsers verified on real IDLs). This plan records the shape for parity.

## Iterations

### IT-1 — Per-domain precision registry  → FR-1
- `coverage_map/precision.py`: `PRECISION_DOMAINS` = {http→`load_openapi_document`, rpc→`parse_proto`,
  db→`parse_prisma_schema`} with IDL file-globs + an operation extractor per domain. No parser reimplemented.
- **Exit:** the three extractors import the named SDK parsers; registry has http/rpc/db.

### IT-2 — `extract_precision` + correct-absence  → FR-2, FR-4
- `extract_precision(repo, domain)` → idl_files (path + operations + count), total, parse_errors,
  `precision_available`. Un-parseable IDL (swagger 2.0) → parse_errors, not crash.
- **Exit:** over a repo with an OpenAPI spec, endpoints + SERVER role + provenance; no IDL → `precision_available=false`.

### IT-3 — Analyzer CLI  → FR-3
- `analyze_precision.py --workdir [--domain] [--out]` reports per-domain ops + samples + provenance.
- **Exit:** `OSS/kestra --domain http` → 192 endpoints; otel-demo `--domain rpc` → proto methods.

### IT-4 — Tests  → FR-5
- `test_precision_layer.py`: OpenAPI/proto/Prisma fixtures + correct-absence + non-3.0 recorded.
- **Exit:** 6 tests green.

## Traceability

| FR | IT | Verify |
|----|----|--------|
| FR-1 | IT-1 | registry has http/rpc/db; SDK parsers imported |
| FR-2 | IT-2 | endpoints + provenance; no-IDL → coverage-only |
| FR-3 | IT-3 | kestra 192 endpoints; otel proto methods |
| FR-4 | IT-2 | swagger 2.0 → parse_error not crash |
| FR-5 | IT-4 | 6 tests green |

## Notes

- **All 4 ITs landed 2026-08-15** (built-first): precision.py + analyze_precision.py + test (6 green);
  proven on kestra (192 http endpoints) + otel-demo (21 rpc methods).
- Next: tie precision into the coverage analyzers (one run → coverage + precision per domain); then the
  GraphQL SDL / AsyncAPI frontier (not SDK-owned yet), and the resolution tier (SCIP).
