# Crosswalk Node/TS structural surface to OTel communication domains (imports-only) — Plan

**Pairs with:** `REQ-crosswalk-node-structure-to-otel-comm-domains.md` (v0.3.1)
**DIDL:** planned canonical ref `cc:intent:node-comm-index:plan:crosswalk-imports-only` (mirrors the REQ's; readable handle = this filename, no integer-led identity).
**Date:** 2026-08-15   **Scope:** S-size single-surface generator (CRP-lite)
**Reference (copy shape, don't fork):** the Go sibling (`gen_go_structure_comm_index.py` /
`analyze_go_comm_coverage.py`). **Deltas vs Go: (1) imports-only (no annotations); (2) the analyzer owns an
ESM/CJS import extractor** (nodejs_parser has none).

## Iterations

### IT-1 — L1 structural forms + parity test  → FR-1
- `_node_structure_forms()` → `NODE-STRUCT-*` for `PARSER_KIND_SETS["nodejs"]` = {function, class, method,
  const_function, interface, type_alias}. Parity test on `parse_nodejs_source` output (regex tier).
- **Deps:** none. **Exit:** parity green. **✅ LANDED 2026-08-15** — 6 forms.

### IT-2 — L3 composites on `node_forms`  → FR-3
- `NODE-LC-*`: arrow_function_export, interface_decl, type_alias, async_function, default_export.
  `not_witnessable`: promise_chain, dynamic_import, callback (body-level).
- **Deps:** IT-1. **Exit:** no `ast_nodes`; every `node_forms` id exists. **✅ LANDED** — 5 composites + 4 not-witnessable (incl. `decorator`, the Java-lesson omission).

### IT-3 — L4 crosswalk φ (imports-only) + floor  → FR-2, FR-5
- `NODE-OTEL-5.*`, 15 domains key-for-key with Python; `import_signatures` = npm specifiers
  (`express`/`@nestjs/common`/`fastify`→http, `@grpc/grpc-js`→rpc, `pg`/`mysql2`/`ioredis`/`mongodb`→db,
  `kafkajs`/`amqplib`→messaging, `graphql`→graphql, `@aws-sdk/client-s3`→object-store, …). **No
  annotation_signatures** (NR-2). Ground in `MCP/`. Floor: HTTP-METRICS, CICD; `resolution_pending` cites
  scip-typescript **Phase 1** (nearest unlock). `grounding: corpus|ecosystem`.
- **Deps:** none. **Exit:** domain-key parity vs Python; imports-only (no annotation fields). **✅ LANDED** — 15 patterns; RPC maps @modelcontextprotocol/sdk (JSON-RPC); resolution_pending cites scip-typescript Ph1 (nearest unlock).

### IT-4 — Generator assembly + drift guard + index doc  → FR-6
- Mirror the Go generator (`build_index`/`_files`/`_render_index_md`/`--check` exit 1). 4 JSON +
  `NODE_STRUCTURE_COMMUNICATION_CAPABILITY_INDEX.md` (banner).
- **Deps:** IT-1, IT-2, IT-3. **Exit:** `--check` green; hand-edit → exit 1. **✅ LANDED** — 4 JSON + `.md` (drift-guarded, proven).

### IT-5 — Coverage analyzer over MCP/ (with the ESM/CJS import extractor)  → FR-4, O-3
- `analyze_node_comm_coverage.py`: per file, extract imports via a **local regex** — ESM
  `import … from '<spec>'` / `import '<spec>'` and CJS `require('<spec>')` — match against φ (specifier-prefix,
  `@scope/pkg` aware). `hyp(f)` + achievable-vs-floor. Verify the regex on both ESM and CJS fixtures.
- **Deps:** IT-3, IT-4. **Exit:** `express`→HTTP + MCP RPC detected on `MCP/`; baseline recorded in O-3;
  4th-ecosystem confirmation of "coverage is imports-only." **✅ LANDED — 23.1% (3/13) over MCP/ 599 files** (HTTP 55, RPC 42, GENAI 3); ESM+CJS regex verified; 17-test suite green.

## Dependency graph (acyclic)

```
IT-1 ──► IT-2 ──┐
                ├──► IT-4 ──► IT-5
IT-3 ───────────┘        ▲
   └─────────────────────┘
```

## Traceability

| FR | IT | Verify seed |
|----|----|-------------|
| FR-1 | IT-1 | NODE-STRUCT ⊆ PARSER_KIND_SETS["nodejs"] |
| FR-2 | IT-3 | domain-key parity; imports-only (no annotation fields) |
| FR-3 | IT-2 | no ast_nodes; node_forms ids exist |
| FR-4 | IT-5 | MCP express→HTTP; ESM+CJS regex both work |
| FR-5 | IT-3, IT-5 | floor never in hyp(f); resolution_pending cites scip-typescript Ph1 |
| FR-6 | IT-4 | hand-edit → exit 1; .md banner |

## Notes

- **The one new mechanism** is the analyzer's ESM/CJS import regex — the CRP-lite focus + FR-4's Verify.
- Node is the last **Tier A** (parser-exists) variant; after it, the roadmap crosses into **Tier B**
  (build a regex parser first: Ruby/Swift/PHP/Rust/C++/Erlang).
- After landing, update `dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md` (Node row → built; 4th-ecosystem coverage
  number) — the imports-only invariant's 4th data point.
