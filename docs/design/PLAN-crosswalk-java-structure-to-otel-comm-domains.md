# Crosswalk Java structural surface + annotations to OTel communication domains — Plan

**Pairs with:** `REQ-crosswalk-java-structure-to-otel-comm-domains.md` (v0.3.1)
**DIDL:** planned canonical ref `cc:intent:java-comm-index:plan:crosswalk` (mirrors the REQ's; readable handle = this filename, no integer-led identity).
**Date:** 2026-08-15   **Scope:** S-size single-surface generator (CRP-lite)
**Reference (copy shape, don't fork):** the Go sibling
`scripts/gen_go_structure_comm_index.py` · `scripts/analyze_go_comm_coverage.py` ·
`docs/design/go-capability-index/*.json`. **The delta vs Go = the annotation φ axis.**

> Same acyclic shape as Go (IT-1 forms → IT-2 composites; IT-3 φ independent; IT-4 assembly; IT-5 coverage).
> The one genuinely new thing is **`annotation_signatures`** in φ (IT-3) and the analyzer matching them (IT-5).

## Iterations

### IT-1 — L1 structural forms + parity test  → FR-1
- `_java_structure_forms()` → `JAVA-STRUCT-*` for `PARSER_KIND_SETS["java"]` = {class, interface, enum,
  record, method, constructor, field, constant}. Parity test: forms ⊆ that set; **ground the empirical
  half on the regex-fallback path** (javalang absent) using a real `.java` fixture.
- **Deps:** none. **Exit:** parity green on regex-fallback output. **✅ LANDED 2026-08-15** — 7 forms with
  `witnessable_at` tier markers; 9 tests incl. empirical per-parse-tiering (regex emits only `both` forms:
  {class,interface,enum,method}; drops field/constant; constructor→method) + annotation-extraction confirmed.

### IT-2 — L3 composites on `java_forms`  → FR-3
- `JAVA-LC-*`: annotated-type, interface-impl, generic-type, nested-class, annotation-bearing-method.
  `not_witnessable`: lambda-in-body, try-with-resources, stream-pipeline (body-level).
- **Deps:** IT-1. **Exit:** no `ast_nodes`; every `java_forms` id exists. **✅ LANDED 2026-08-15** — 5 composites
  (annotated_type, annotation_bearing_method, interface_impl, subclass, enum_type) keyed on **real JavaElement
  fields** (annotations/extends/implements — test guards against fabrication); 5 not_witnessable (body-level).

### IT-3 — L4 crosswalk φ (imports + **annotations**) + floor  → FR-2, FR-5
- `JAVA-OTEL-5.*`, 15 semconv domains key-for-key with Python. Each entry: `import_signatures`
  (`io.grpc`, `javax.sql`/`java.sql`, `org.apache.kafka`, `javax.ws.rs`/`jakarta.ws.rs`, …) **and**
  `annotation_signatures` where a declaration marker exists (`Path`/`GET`/`POST`→http, `GrpcService`→rpc,
  `KafkaListener`→messaging, `Repository`→db-ish). Ground both by grepping `OSS/kestra` (+ one Spring repo
  if available). Add `detectability_floor`: `5.2-HTTP-METRICS`, `5.7-CICD`, and a documented **call-site
  depth-floor** note. `grounding: corpus|ecosystem` per signature.
- **Deps:** none. **Exit:** domain-key parity vs Python; every non-floor entry has ≥1 import **or** annotation signature.
  **✅ LANDED 2026-08-15** — 15 patterns (13 achievable + 2 floor); 5 corpus-grounded (HTTP/RPC/DB/MESSAGING/CLI),
  8 ecosystem; `annotation_signatures` on HTTP/RPC/DB/MESSAGING/CLI/GRAPHQL; `resolution_pending` axis cites scip-java. 18 tests green.

### IT-4 — Generator assembly + drift guard + index doc  → FR-6
- Mirror the Go generator (`build_index`/`_files`/`_render_index_md`/`--check` exit 1). Emit 4 JSON +
  `JAVA_STRUCTURE_COMMUNICATION_CAPABILITY_INDEX.md` (banner). Index doc must surface the annotation column.
- **Deps:** IT-1, IT-2, IT-3. **Exit:** `--check` green; hand-edit → exit 1. **✅ LANDED 2026-08-15** —
  generator emits 4 JSON + the `.md` index (renders the **annotation-signatures column** + witnessable_at +
  resolution-pending note; banner + drift-guarded, proven on a hand-edit); 23-test suite green.

### IT-5 — Coverage analyzer over OSS/kestra  → FR-4, O-3
- `analyze_java_comm_coverage.py`: per file, `parse_java_source` → elements (`.annotations`) + imports;
  `hyp(f)` matches φ `import_signatures` ∪ `annotation_signatures`; report the **import-hits vs
  annotation-hits breakdown** (measures the annotation axis's marginal contribution) + achievable-vs-floor.
- **Deps:** IT-3, IT-4. **Exit:** `@Path`→`JAVA-OTEL-5.1-HTTP` detected on kestra; annotation-only patterns
  named; baseline recorded in O-3. **✅ LANDED 2026-08-15** — 38.5% (5/13) over 2106 files; 28-test suite green.
  **Headline finding: annotation-axis marginal = 0** (annotations co-occur with their package imports →
  redundant at domain granularity; value is element-precision/role, not coverage — template lesson folded into pattern doc).

## Dependency graph (acyclic)

```
IT-1 ──► IT-2 ──┐
                ├──► IT-4 ──► IT-5
IT-3 ───────────┘        ▲
   └─────────────────────┘   (IT-5 also depends on IT-3 for φ)
```

## Traceability

| FR | IT | Verify seed |
|----|----|-------------|
| FR-1 | IT-1 | JAVA-STRUCT ⊆ PARSER_KIND_SETS["java"] (regex-fallback empirical) |
| FR-2 | IT-3 | domain-key parity; import ∪ annotation ≥1 per non-floor |
| FR-3 | IT-2 | no ast_nodes; java_forms ids exist |
| FR-4 | IT-5 | kestra `@Path`→HTTP; import-vs-annotation breakdown |
| FR-5 | IT-3, IT-5 | floor (incl. call-site depth-floor) never in hyp(f) |
| FR-6 | IT-4 | hand-edit → exit 1; .md banner |

## Notes

- The variant's headline is **the annotation axis** — the first φ signal beyond imports since Python. IT-5's
  import-vs-annotation breakdown is the evidence for whether it earns its place.
- After landing, update `dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md` (Java row → built; record the annotation
  marginal contribution) — the third-variant evidence, now across three languages + the fidelity×depth×annotation model.
