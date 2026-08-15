# Crosswalk Go structural surface to OTel communication domains (advisory tier) — Requirements

**Project:** startd8-sdk · Go structure→OTel §5 capability index   **Criticality:** medium
**Version:** 0.2 (Post-planning — self-reflective update)   **Date:** 2026-08-15
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** `PLAN-crosswalk-go-structure-to-otel-comm-domains.md`
**Inherits standards:** det-req-kit · DIDL · `dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md` (the pattern this instantiates)
**Audience:** operator (SDK maintainer running the index/coverage generator)

> **DIDL:** Semantic name — *Crosswalk Go structural surface to OTel communication domains at advisory
> tier*. Planned canonical ref — `cc:intent:go-comm-index:requirement:crosswalk-advisory`. Readable
> handle — `REQ-crosswalk-go-structure-to-otel-comm-domains.md`. No integer-led identity.

## 0. Planning Insights (Self-Reflective Update)

> v0.1 assumed the Go index is a near-clone of the Python generator. Planning against the real
> startd8 code (`go_parser.py`, `manifest_adapter.py`, `gen_python_ast_capability_index.py`) falsified
> five assumptions — two *narrowed* scope (imports already extracted; no new parser), three *reshaped*
> the artifact (L1 hand-authored, composite schema diverges, φ re-authored not copied). This is the
> Go instantiation of the pattern in `dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md` and its friction §.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| Generator mirrors `gen_python_ast_capability_index.py` | Python L1 is **reflected** from the stdlib `ast` module (`_build_ast_nodes()` introspects 132 node classes → drift-free by construction). Go has **no in-process reflectable grammar** — `go_parser.py` is regex. | Go L1 is a **hand-authored constant** (~8 declaration forms), not derived. The generator is *simpler* (no reflection) but L1 can drift → the `--check` guard matters *more* for Go. → FR-1 |
| Coverage analyzer needs a new import-extraction regex (go_parser is declaration-only) | **FALSE** — `go_parser.parse_go_imports(source) -> List[str]` already extracts single + block imports (go_parser.py:359). | No new import mechanism. The analyzer **consumes `parse_go_imports`** for φ. Scope narrows. → FR-4, NR-1 |
| Go composites reference `ast_nodes` like Python's `PY-LC-*` | Python composites key on `ast_nodes`; Go has no AST nodes, only regex-detected forms. | Go composite schema keys on **`go_forms`** (struct / interface / receiver-method / goroutine / channel / defer), a deliberate divergence from the Python schema. → FR-3 |
| φ copies Python `import_signatures` | Python signatures are Python-ecosystem (`requests`, `grpc`, `boto3`); Go differs (`google.golang.org/grpc`, `net/http`, `database/sql`, `Shopify/sarama`). | φ is a **Go-ecosystem re-authoring** of the same 15 keys. Parity is on the 15 KEYS + semconv domains, **not** the signature strings. → FR-2 |
| All 15 §5 patterns are detectable | Advisory/regex tier has **no call graph**. | 2 patterns are **correct-absences** → a `detectability_floor` block is required. → FR-5 |
| (v0.2) Floor = `5.2-HTTP-METRICS` + `5.6-GENAI` | **(IT-3, impl-time)** Applying the import=domain-hypothesis standard uniformly: **GENAI is import-detectable** (Go LLM SDK import is regex-visible) → out; **CICD has no library import** (env/pipeline evidence) → in. | Floor = `{5.2-HTTP-METRICS, 5.7-CICD}`; GENAI is a normal detectable entry. → FR-5, generator `_detectability_floor()` |
| (v0.2) Composites include goroutine/channel/defer | **(IT-2, impl-time)** Those are **body statements** `go_parser.py` doesn't parse; only declaration-level idioms are witnessable — the same substrate floor as L4. | Composites = 5 declaration-level; goroutine/channel/defer/interface_satisfaction → `not_witnessable`. → FR-3 |
| DNS signature includes stdlib `net` | **(IT-5, impl-time)** Under prefix-matching, `net` collides with `net/http` (every HTTP file → false DNS). | Dropped `net`; DNS = `github.com/miekg/dns` only. → FR-2 note, matcher `_matches` |

**Resolved open questions:**
- **OQ-1 → No new parser.** Consume `parse_go_source` (L1/L3) + `parse_go_imports` (L4 φ). NR-1.
- **OQ-2 → Schema parity is on the 15 §5 keys + semconv domains, not field-for-field.** L1 and composite fields legitimately differ by substrate.

## Overview

A Go analogue of the Python AST Communication Capability Index: a numbered, versioned crosswalk from
Go's *advisory-tier* structural surface (regex-visible package imports + top-level declarations, via
`startd8/languages/go_parser.py`) to the **same 15 OpenTelemetry §5 semconv communication domains** the
Python pilot maps. The deliverable is (a) a generator console-script that emits the index JSON + a
markdown index doc and drift-checks them, and (b) a coverage pass over a real Go corpus (`OSS/Thanos`).
It is the second variant of the pattern in `dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md`; it adds **no
parser** and re-uses the language-agnostic `ElementKind` layer.

## Objectives

- O-1: A Go index whose L4 crosswalk keys are **key-for-key identical** to the Python pilot's 15
  `§5` semconv domains (portability of the invariant across languages).
- O-2: An explicit, machine-readable **detectability floor** so an empty §5 cell reads as
  *substrate-can't-witness* (correct-absence), never as *coverage gap*.
- O-3: A coverage number for a **real** Go corpus (`OSS/Thanos`) — **baseline 46.2% achievable (6/13)
  over 602 files** (IT-5, 2026-08-15); the 6 detected == the 6 `corpus`-grounded patterns exactly.
- O-4: Zero new parsing machinery — consume existing `go_parser.py` (Mottainai).

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | Hand-authored Go L1/composite constants drift from what `go_parser.py` actually emits | `--check` drift guard + a parity test asserting L1 forms ⊆ parser's emitted kinds | high |
| quality | φ import-signatures overfit to Thanos and miss other Go idioms (gin, chi, pgx) | Ground signatures in ≥2 corpora signals (Thanos + Istio); mark advisory | medium |
| quality | The floor is misused to hide a *detectable* pattern as "floor" | Floor entries must cite *why* (needs call-body); reviewer checks each | medium |

## Profile

Declared profile: **internal**

## Functional requirements

- **FR-1 — Author the Go structural-element surface (L1) as a maintained constant.** The generator
  emits a `go-structure-forms.json` enumerating the ~8 declaration forms `go_parser.py` recognizes
  (function, method, class, type_alias, constant, variable, + struct/interface distinction), each
  `GO-STRUCT-###`. Touches: gen-index, `docs/design/go-capability-index/go-structure-forms.json`. Verify: every form id maps to a kind in `manifest_adapter._PARSER_KIND_MAP["go"]`; a form not emitted by `go_parser.parse_go_source` on a fixture fails the parity test. Serves: O-1, O-4
- **FR-2 — Author the L4 crosswalk φ with the 15 §5 keys, Go-ecosystem import signatures.** Emit
  `communication-crosswalk.json` whose entries are `GO-OTEL-5.*` with the **same 15 semconv domains**
  as `python-capability-index/communication-crosswalk.json`, but `import_signatures` re-authored for Go
  (`google.golang.org/grpc`, `net/http`, `database/sql`, `Shopify/sarama`, …). Touches: `docs/design/go-capability-index/communication-crosswalk.json`. Verify: the set of `semconv_domain` values equals the Python file's set (key parity); each non-floor entry has ≥1 `import_signature`. Serves: O-1
- **FR-3 — Author the Go composites (L3) keyed on `go_forms`, not `ast_nodes`.** Emit
  `language-composites.json` with `GO-LC-*` entries for the **declaration-level** Go idioms the parser
  can witness (receiver_method, pointer_receiver, struct_embedding, interface_contract, exported_api),
  each referencing `go_forms`; a sibling `not_witnessable` block records the **body-level** idioms the
  advisory tier cannot see. **(IT-2 correction, 2026-08-15:** `goroutine` / `channel` / `defer` are
  body statements `go_parser.py` does not parse, and `interface_satisfaction` needs cross-element
  matching — all four moved to `not_witnessable`, not composites.**)** Touches: `docs/design/go-capability-index/language-composites.json`. Verify: no entry contains an `ast_nodes` field; every `go_forms` value is a `GO-STRUCT-###` id from FR-1; goroutine/channel/defer appear only in `not_witnessable`. Serves: O-1
- **FR-4 — Coverage analyzer consumes `parse_go_imports` for φ (no new extraction).** A
  `analyze_go_comm_coverage.py` walks `*.go`, calls `go_parser.parse_go_imports` per file, computes
  `hyp(f)` by matching against φ's `import_signatures`, and emits a coverage report (dimensions +
  per-file hyp + "not evidenced" set), mirroring `analyze_otel_demo_python_coverage.py`. Touches: analyze-cov, opt-workdir. Verify: run over `OSS/Thanos` detects `GO-OTEL-5.3-RPC` (grpc) and `GO-OTEL-5.1-HTTP` (net/http); no call to any new parser/regex for imports. Serves: O-3, O-4
- **FR-5 — Carry a `detectability_floor` block naming un-witnessable patterns.** The crosswalk JSON
  includes a `detectability_floor` listing each §5 pattern the advisory (import-only) tier cannot
  statically witness — **`5.2-HTTP-METRICS`** (metric emission is call-body; the http import is
  already claimed by 5.1-HTTP) and **`5.7-CICD`** (evidenced by pipeline config/env, not a Go import) —
  each with a `reason` and `tier: advisory`. **(IT-3 reclassification, 2026-08-15:** `5.6-GENAI` is
  **not** floor — by the same import=domain-hypothesis standard used for every other domain, importing
  a Go LLM SDK is regex-visible, so GENAI is detectable; `5.7-CICD` replaced it.**)** Coverage
  reporting excludes floor patterns from the achievable denominator (or marks them `floor`). Touches: `docs/design/go-capability-index/communication-crosswalk.json`, analyze-cov. Verify: floor patterns never appear in any file's `hyp(f)`; the coverage report shows an "achievable vs floor" split. Serves: O-2
- **FR-6 — Drift-guard + regenerate (Kagami).** `gen_go_structure_comm_index.py --check` re-generates
  the JSON in-memory and sha-compares to disk, exiting non-zero on drift; the markdown index doc is
  regenerated from the JSON, never hand-edited. Touches: opt-check, exit-drift, `docs/design/GO_STRUCTURE_COMMUNICATION_CAPABILITY_INDEX.md`. Verify: editing a JSON file by hand then running `--check` exits non-zero; the .md carries a "generated — do not edit" banner. Serves: O-2

## Non-goals

- **NR-1 — Do not modify `go_parser.py` or add a Go parser/tree-sitter.** Consume the existing regex
  parser + `parse_go_imports` as-is. Upgrading Go to authoritative tier is a separate future variant.
- **NR-2 — Do not attempt call-site / call-graph detection for Go.** That is the substrate floor
  (FR-5), not a gap to close here.
- **NR-3 — Do not re-derive the `ElementKind` (L2) layer.** It is already language-agnostic
  (`manifest_adapter.map_parser_kind`); cite it.
- **NR-4 — Do not restate the 15 semconv domain definitions.** Cite the Python crosswalk + OTel
  semantic-conventions as the vocabulary home (single-source).

## Owned fields

Only humans enter: the `reason` strings in `detectability_floor`; any `note` on a φ entry marked advisory.

## Contract projection

- **Backend:** python-cli-surface
- **Vocabulary home (cite):** `det-req-kit/SCHEMA.md` §8 (python-cli-surface); signature vocabulary home = `docs/design/python-capability-index/communication-crosswalk.json` (the 15 §5 keys) + `startd8/languages/go_parser.py` (Go structural forms).

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| gen-index | console-script | structure | `python3 scripts/gen_go_structure_comm_index.py`; emits the 3 JSON artifacts + .md; owns the drift guard |
| analyze-cov | console-script | structure | `python3 scripts/analyze_go_comm_coverage.py`; coverage pass; consumes `parse_go_imports` |
| opt-check | option | structure | `--check` drift guard; exit non-zero on mismatch |
| opt-workdir | option | words | `--workdir` corpus root (default `OSS/Thanos`) |
| exit-drift | exit-class | structure | `exit 1` on drift; `exit 0` on match (exit 2 is reserved by argparse for usage errors — mirrors the Python sibling) |

> The three emitted data artifacts (`go-capability-index/{go-structure-forms, language-composites,
> communication-crosswalk}.json`) and the `.md` index are **outputs** of `gen_go_structure_comm_index.py`,
> named as file paths in FR `Touches:` — not CLI vocabulary entries.

---

## Appendix A — Accepted (with where merged)

## Appendix B — Rejected (with rationale)

## Appendix C — Incoming review rounds

---

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied craft/SDK lessons before review. Each changed or hardened the draft:

- **[Phantom-reference audit]** — grepped every code symbol the REQ names. Verified extant:
  `go_parser.parse_go_source`, `go_parser.parse_go_imports` (go_parser.py:209/359),
  `manifest_adapter._PARSER_KIND_MAP["go"]` + `map_parser_kind`, `gen_python_ast_capability_index.py`,
  `analyze_otel_demo_python_coverage.py`. No phantom symbols → FR Touches are all real. Added the
  parity-test binding in FR-1's Verify.
- **[Single-source vocabulary ownership]** — the 15 §5 domains and the signature vocabulary are
  **owned** by the Python crosswalk + OTel semconv; the Go crosswalk **cites** them (NR-4) and does not
  restate the definitions, only re-authors the Go signature strings.
- **[Prune phantom scope]** — the "new import regex" sub-feature was architecturally unnecessary
  (`parse_go_imports` exists) → moved to NR-1/NR-2 and narrowed FR-4.
- **[CRP steering]** — least-reviewed artifact = the Go crosswalk JSON content (φ signatures + floor);
  name it as the CRP focus. Settled / do-not-relitigate: the four-layer model and the 15-key invariant
  (owned by the pattern doc + Python pilot).

### 0.2 Design-Principle Hardening (v0.3.1)

> Checked against `dev-os/PRINCIPLE-INDEX.md`. Each changed or hardened the draft:

- **[Mottainai]** — forced the check "does a later stage rebuild what an earlier stage produced?" →
  the generator consumes `go_parser` + `parse_go_imports` and cites `ElementKind`; **no parser, no
  import regex, no L2** rebuilt (NR-1/NR-3, FR-4). This is the dominant principle here.
- **[Kagami]** — the crosswalk JSON + index .md are **derived artifacts**; routed edits to the
  source (the generator's constants) + a **runnable regen** (`--check`), not hand-edits to the mirror
  → FR-6, and the .md carries a generated-do-not-edit banner.
- **[Genchi Genbutsu]** — bind φ and coverage to the **real running artifact**: signatures grounded in
  actual `OSS/Thanos` imports (grpc 169 / net/http 108 / database/sql / native OTel), coverage measured
  on the real 602-file corpus, not the demo (whose Go services aren't even present) → FR-2, FR-4, O-3.
- **[Accidental-Complexity (anti)]** — resisted adding a Go-AST/tree-sitter engine to "match Python's
  132-node L1"; the hand-authored ~8-form constant + drift guard is the minimum that fits the advisory
  substrate → FR-1, NR-1.

*v0.3.1 — Post lessons + principle hardening. Applied 4 lessons + 4 principles. 5 planning discoveries
(2 narrowing, 3 reshaping). Ready for CRP-lite (single Appendix-C round; S-size single-surface generator).*
