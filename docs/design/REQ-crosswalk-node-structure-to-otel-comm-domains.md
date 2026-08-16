# Crosswalk Node/TS structural surface to OTel communication domains (imports-only, advisory) — Requirements

**Project:** startd8-sdk · Node/JS/TS structure→OTel §5 capability index   **Criticality:** medium
**Version:** 0.2 (Post-planning — self-reflective update)   **Date:** 2026-08-15
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** `PLAN-crosswalk-node-structure-to-otel-comm-domains.md`
**Inherits standards:** det-req-kit · DIDL · `dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md` (the pattern) · `REQ-crosswalk-go-structure-to-otel-comm-domains.md` (advisory sibling)
**Audience:** operator (SDK maintainer running the index/coverage generator)

> **DIDL:** Semantic name — *Crosswalk Node/TS structural surface to OTel communication domains, imports-only
> advisory tier*. Planned canonical ref — `cc:intent:node-comm-index:requirement:crosswalk-imports-only`.
> Readable handle — `REQ-crosswalk-node-structure-to-otel-comm-domains.md`.

## 0. Planning Insights (Self-Reflective Update)

> Node was the "easiest remaining" (Tier A, advisory — a Go-playbook repeat). Grounding surfaced three
> differences from Go/Java that make it *slightly* harder and shape the spec — plus it lets us
> **prospectively apply the Java precision-vs-coverage lesson** (skip the decorator axis by design).

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| `parse_nodejs_imports` exists (like Go/Java) | **ABSENT** — `nodejs_parser` exposes only `parse_nodejs_source`; no import extractor. | The analyzer needs its **own thin import regex** (ESM `import…from` + CJS `require()`) — the one new mechanism vs Go/Java. → FR-4, NR-1 |
| TS decorators give an annotation axis (like Java) | `nodejs_parser` **does not extract decorators** (`@Controller` dropped); AND Java IT-5 proved the annotation axis adds **0 marginal domain coverage** (annotation ⊆ import). | φ is **imports-only** — no decorator axis, by design. Applies the pattern's precision-vs-coverage lesson prospectively. → FR-2, NR-2 |
| Call-site φ is far off (like Go/Java) | **TypeScript is scip-typescript Phase 1** — the *nearest* SCIP unlock of all languages (`CODE_KNOWLEDGE_GRAPH_DESIGN.md`). | The `resolution-pending` floor is closest to lifting here; note it as the first resolution candidate. → FR-5 |
| Corpus reuse | Go/Java corpora are `.go`/`.java`. First-party TS/JS locally is thin (the bulk was `node_modules`). | Corpus = **`MCP/`** (539 first-party files, 51 §5-import-hits — coherent, comms-heavy). → FR-4, O-3 |

**Resolved open questions:**
- **OQ-1 → φ = imports-only.** No decorator/annotation axis; matches parser reality + the Java lesson.
- **OQ-2 → The import extractor is the analyzer's, not the parser's** (NR-1 keeps `nodejs_parser` untouched).

## Overview

A Node/JS/TS analogue of the Go index: an **imports-only** crosswalk from the advisory-tier structural
surface (`nodejs_parser` declarations + an analyzer-local ESM/CJS import regex) to the **same 15 OTel §5
semconv domains**. Deliberately skips the decorator axis (parser doesn't surface it; Java proved it adds no
domain coverage). Adds **no parser**; reuses the shared `ElementKind` layer. TS's SCIP indexer is Phase 1,
so this is the language whose call-site φ is nearest to unlocking.

## Objectives

- O-1: A Node index whose L4 crosswalk keys are **key-for-key identical** to the Python/Go/Java pilots' 15
  §5 semconv domains (invariant portability — now across four languages).
- O-2: An ESM+CJS import extractor in the analyzer (`import…from '<pkg>'`, `require('<pkg>')`) — the one new
  mechanism, kept out of `nodejs_parser`.
- O-3: A coverage number for `MCP/` — **baseline 23.1% (3/13) over 599 files** (IT-5): HTTP (55, express),
  RPC (42, `@modelcontextprotocol/sdk` JSON-RPC + grpc), GENAI (3); narrow spread (MCP is a focused protocol
  codebase). The **4th ecosystem confirmation** that domain coverage is an imports-only game.
- O-4: Zero new parser; reuse `nodejs_parser` + shared `ElementKind` (Mottainai).

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | ESM/CJS import regex misses dynamic `import()`, re-exports, aliased requires | Cover the two dominant forms; mark advisory; note the recall floor | high |
| quality | Hand-authored Node L1 forms drift from `nodejs_parser` kinds | `--check` + parity test (forms ⊆ `PARSER_KIND_SETS["nodejs"]`) | high |
| quality | npm scope/subpath imports (`@scope/pkg/sub`) vs bare specifiers | Match on package specifier prefix; handle `@scope/pkg` | medium |

## Profile

Declared profile: **internal**

## Functional requirements

- **FR-1 — Author the Node structural-element surface (L1) as a maintained constant.** Emit
  `node-structure-forms.json` for `PARSER_KIND_SETS["nodejs"]` = {function, class, method, const_function,
  interface, type_alias}, each `NODE-STRUCT-###`. Touches: gen-index, `docs/design/node-capability-index/node-structure-forms.json`. Verify: every form's `parser_kind` ∈ `PARSER_KIND_SETS["nodejs"]`; a kind `parse_nodejs_source` emits on a fixture with no form fails the parity test. Serves: O-1, O-4
- **FR-2 — Author the L4 crosswalk φ, imports-only, 15 §5 keys.** Emit `communication-crosswalk.json`
  (`NODE-OTEL-5.*`) with the same 15 semconv domains, `import_signatures` = npm specifiers (`express`,
  `@grpc/grpc-js`, `pg`, `kafkajs`, `axios`, `@aws-sdk/*`, …), `grounding: corpus|ecosystem`, and **no
  `annotation_signatures`** (by design). Touches: `docs/design/node-capability-index/communication-crosswalk.json`. Verify: `semconv_domain` set == Python's; each non-floor entry has ≥1 import_signature; no entry carries annotation_signatures. Serves: O-1
- **FR-3 — Author the Node composites (L3) keyed on `node_forms`.** Emit `language-composites.json`
  (`NODE-LC-*`) for declaration-level idioms (arrow-function-export, interface-decl, type-alias, async-function,
  default-export), each referencing `node_forms`; a `not_witnessable` block records body-level idioms
  (promise-chain, dynamic-import, callback). Touches: `docs/design/node-capability-index/language-composites.json`. Verify: no `ast_nodes` field; every `node_forms` id is a `NODE-STRUCT-###`. Serves: O-1
- **FR-4 — Analyzer with an analyzer-local ESM/CJS import extractor.** `analyze_node_comm_coverage.py`
  walks `*.{js,mjs,cjs,ts,tsx}`, extracts imports via a **local regex** (`import…from '<spec>'` and
  `require('<spec>')` — NOT in `nodejs_parser`, NR-1), computes `hyp(f)` against φ, reports achievable-vs-floor
  coverage. Touches: analyze-cov, opt-workdir. Verify: over `MCP/` detects `NODE-OTEL-5.1-HTTP` (express) and
  the MCP RPC path; the import regex handles both ESM and CJS. Serves: O-2, O-3, O-4
- **FR-5 — `detectability_floor` + resolution-pending (nearest unlock).** Floor = `5.2-HTTP-METRICS`,
  `5.7-CICD` (advisory). `resolution_pending` records the call-site axis, noting TS's **scip-typescript is
  CKG Phase 1 — the nearest resolution unlock of any language**. Touches: `docs/design/node-capability-index/communication-crosswalk.json`, analyze-cov. Verify: floor never in `hyp(f)`; resolution_pending cites scip-typescript Phase 1. Serves: O-2
- **FR-6 — Drift-guard + regenerate (Kagami).** `gen_node_structure_comm_index.py --check` re-generates +
  sha-compares (exit 1 on drift); the `.md` index is regenerated with a generated-do-not-edit banner. Touches: opt-check, exit-drift, `docs/design/NODE_STRUCTURE_COMMUNICATION_CAPABILITY_INDEX.md`. Verify: hand-edit a JSON → `--check` exits 1; `.md` carries the banner. Serves: O-2

## Non-goals

- **NR-1 — Do not modify `nodejs_parser.py`.** The ESM/CJS import extractor lives in the analyzer (the parser
  exposes no import fn; adding one is a separate SDK change, not ours).
- **NR-2 — Do not build a decorator/annotation axis for Node.** The parser drops decorators and Java proved
  the axis adds no domain coverage — imports-only is the deliberate, evidence-backed choice.
- **NR-3 — Do not attempt call-site / resolution.** Resolution-pending (scip-typescript Phase 1); do not fork it.
- **NR-4 — Do not re-derive `ElementKind` (L2) or restate the 15 semconv domains.** Cite them.

## Owned fields

Only humans enter: `reason` strings in `detectability_floor`; any φ entry `note` marked advisory.

## Contract projection

- **Backend:** python-cli-surface
- **Vocabulary home (cite):** `det-req-kit/SCHEMA.md` §8; 15 §5 keys = `docs/design/python-capability-index/communication-crosswalk.json`; Node kinds = `startd8/languages/nodejs_parser.py` + `PARSER_KIND_SETS["nodejs"]`.

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| gen-index | console-script | structure | `python3 scripts/gen_node_structure_comm_index.py`; emits JSON + .md; drift guard |
| analyze-cov | console-script | structure | `python3 scripts/analyze_node_comm_coverage.py`; analyzer-local ESM/CJS import regex |
| opt-check | option | structure | `--check` drift guard |
| opt-workdir | option | words | `--workdir` corpus root (default `MCP/`) |
| exit-drift | exit-class | structure | `exit 1` on drift; `exit 0` on match |

> The emitted `node-capability-index/*.json` + the `.md` are **outputs** of gen-index, named as file paths
> in FR `Touches:` — not CLI vocabulary entries.

---

## Appendix A — Accepted (with where merged)

## Appendix B — Rejected (with rationale)

## Appendix C — Incoming review rounds

---

### 0.1 Lessons-Learned Hardening (v0.3)

- **[Phantom-reference audit]** — verified: `parse_nodejs_source`, `PARSER_KIND_SETS["nodejs"]`,
  `map_parser_kind`. Verified ABSENT (and designed around): `parse_nodejs_imports`, decorator extraction.
- **[Single-source vocabulary ownership]** — 15 §5 domains + sibling crosswalk shape owned upstream; cite.
- **[Prune phantom scope]** — the decorator axis was pruned to NR-2 on two grounds (parser + Java evidence).
- **[CRP steering]** — least-reviewed surface = the analyzer-local ESM/CJS import regex (new; no sibling has it).

### 0.2 Design-Principle Hardening (v0.3.1)

- **[Mottainai]** — reuse `nodejs_parser` + `ElementKind`; the only new code is the analyzer import regex, kept out of the parser (NR-1).
- **[Genchi Genbutsu]** — φ signatures grounded in real `MCP/` npm imports; corpus is real first-party TS/JS, not node_modules.
- **[Kagami]** — JSON + `.md` derived; `--check` regen; banner (FR-6).
- **[Accidental-Complexity (anti)]** — resisted re-adding the decorator axis "for symmetry with Java"; the
  Java evidence says it buys no coverage, so imports-only is the simpler correct choice (the generality-audit
  move: predict-and-skip rather than build-then-measure-zero).

*v0.3.1 — Post lessons + principle hardening. 4 planning discoveries; imports-only by design (Java lesson
applied prospectively). The new mechanism is one ESM/CJS import regex. Ready for CRP-lite.*
