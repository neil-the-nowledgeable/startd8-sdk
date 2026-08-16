# Crosswalk Go structural surface to OTel communication domains (advisory tier) — Plan

**Pairs with:** `REQ-crosswalk-go-structure-to-otel-comm-domains.md` (v0.3.1)
**DIDL:** planned canonical ref `cc:intent:go-comm-index:plan:crosswalk-advisory` (mirrors the REQ's; readable handle = this filename, no integer-led identity).
**Date:** 2026-08-15   **Scope:** S-size single-surface generator (CRP-lite)
**Reference implementation to copy shape from (do not fork):**
`scripts/gen_python_ast_capability_index.py` · `scripts/analyze_otel_demo_python_coverage.py` ·
`docs/design/python-capability-index/*.json`

> The dependency chain is linear-with-one-fan-in: L1 forms are referenced by *both* composites (L3)
> and — transitively via the drift guard — the generator. φ (L4) is independent of L1 but shares the
> generator + drift guard. Coverage (validation) is strictly last.

## Iterations

### IT-1 — L1 structural forms + parity test  → FR-1
- Author `_go_structure_forms()` in a new `scripts/gen_go_structure_comm_index.py` returning
  `GO-STRUCT-###` entries for the ~8 forms `go_parser.parse_go_source` emits (function, method,
  class, type_alias, constant, variable) + struct/interface distinction (from `GoElement.is_interface`).
- Write a parity test (`tests/unit/languages/test_go_index_parity.py`): every `GO-STRUCT` form id
  maps to a kind in `manifest_adapter._PARSER_KIND_MAP["go"]`; a form absent from a Go fixture's
  `parse_go_source` output fails. **This test is the anti-drift guard for a hand-authored L1.**
- **Deps:** none. **Exit:** parity test green. **✅ LANDED 2026-08-15** — 7 forms; empirical test green on real Go fixtures.

### IT-2 — L3 composites on `go_forms`  → FR-3
- Author `_go_composites()` → `GO-LC-*` (goroutine, channel, defer, receiver-method,
  interface-satisfaction, struct-embedding), each referencing `go_forms` = `GO-STRUCT-###` ids.
- Assert (in the parity test) no entry carries an `ast_nodes` field and every `go_forms` id exists.
- **Deps:** IT-1 (references its form ids). **Exit:** composites validate against IT-1 ids.
  **✅ LANDED 2026-08-15** — 5 declaration-level composites; goroutine/channel/defer/interface_satisfaction
  moved to `not_witnessable` (body-level / cross-element — same substrate floor as L4).

### IT-3 — L4 crosswalk φ + detectability_floor  → FR-2, FR-5
- Author `_go_communication_crosswalk()` → `GO-OTEL-5.*` with the **15 semconv domains** copied
  key-for-key from `python-capability-index/communication-crosswalk.json`, `import_signatures`
  **re-authored for Go** (`google.golang.org/grpc`, `net/http`, `database/sql`, `Shopify/sarama`,
  `segmentio/kafka-go`, `go-redis`, `net`(dns), …). Ground signatures by grepping `OSS/Thanos` +
  `OSS/Istio` imports (don't invent).
- Add the `detectability_floor` block. **(IT-3 outcome:** floor = `5.2-HTTP-METRICS` + `5.7-CICD`,
  not GENAI — GENAI's SDK import is regex-visible, so it's detectable; CICD has no library import.**)**
  Assert id-suffix set AND domain-key set == Python file's (key parity).
- **Deps:** none (independent of L1). **Exit:** key-parity green (14 tests); every non-floor entry has ≥1 signature. **✅ LANDED 2026-08-15** — 15 patterns, 13 achievable, 2 floor.

### IT-4 — Generator assembly + drift guard + index doc  → FR-6
- `build_index()` assembles IT-1/2/3 → writes `go-capability-index/{go-structure-forms,
  language-composites,communication-crosswalk}.json` (sorted, sha-stamped) + regenerates
  `GO_STRUCTURE_COMMUNICATION_CAPABILITY_INDEX.md` from the JSON with a "generated — do not edit" banner.
- `--check` re-generates in-memory + sha-compares, exit-class `{0: match, 2: drift}` (mirror the Python
  generator's `_sha`/`--check`).
- **Deps:** IT-1, IT-2, IT-3. **Exit:** `--check` green on fresh gen; hand-edit a JSON → exit 1
  (not 2 — argparse reserves 2 for usage errors; mirrors the Python sibling).
  **✅ LANDED 2026-08-15** — generator emits 4 JSON + the `.md` index (banner + drift-guarded, proven
  on a hand-edit); 23-test suite green.

### IT-5 — Coverage analyzer over OSS/Thanos  → FR-4, O-3
- `scripts/analyze_go_comm_coverage.py` walks `*.go` under `--workdir` (default `OSS/Thanos`), calls
  `go_parser.parse_go_imports` per file, computes `hyp(f)` against φ `import_signatures`, emits the
  report (dimensions + per-file hyp + not-evidenced), with an **achievable-vs-floor split** in the
  denominator (floor patterns excluded from achievable).
- **Deps:** IT-3 (φ), IT-4 (index on disk). **Exit:** run detects `GO-OTEL-5.3-RPC` + `5.1-HTTP` on
  Thanos; floor patterns never in any `hyp(f)`; baseline coverage number recorded in O-3.
  **✅ LANDED 2026-08-15** — 46.2% achievable (6/13) over 602 files; 18-test suite green;
  matcher made collision-safe (dropped stdlib `net` from DNS — it prefix-collided with `net/http`).

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
| FR-1 | IT-1 | parity test: GO-STRUCT ⊆ parser kinds |
| FR-2 | IT-3 | domain-key set == Python set |
| FR-3 | IT-2 | no ast_nodes; go_forms ids exist |
| FR-4 | IT-5 | Thanos run; consumes parse_go_imports; no new regex |
| FR-5 | IT-3, IT-5 | floor never in hyp(f); achievable/floor split |
| FR-6 | IT-4 | hand-edit → --check exit 1; .md banner |

## Notes

- **One cell per commit** (pattern rule): land IT-1..IT-5 as small commits; the whole REQ is the "Go
  cell" of `dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md`.
- After landing, update that pattern doc's coverage table (Go row → built) and file the Go coverage
  number — that is the pattern's next-variant evidence.
