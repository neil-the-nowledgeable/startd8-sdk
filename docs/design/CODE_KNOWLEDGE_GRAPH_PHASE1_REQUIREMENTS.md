# Code Knowledge Graph — Phase 1 Requirements (Post-Spike, Reframed)

> **Version:** 2.2 (2026-06-01 — CRP triage applied; verdict-consumption gap closed)
> **Status:** Draft for review
> **Supersedes:** v1.0 of this file (which proposed building DMMF + a CONFORMS_TO binder + a new
> SQLite substrate — the spike proved most of that is already shipped). Also supersedes
> `CODE_OBSERVABILITY_PHASE1_REQUIREMENTS.md` (REQ-MIE-*).
> **Design:** [CODE_KNOWLEDGE_GRAPH_DESIGN.md](./CODE_KNOWLEDGE_GRAPH_DESIGN.md)
> **Spike evidence:** `scripts/spikes/ckg/SG_FINDINGS.md` (run against the real target `strtd8/`)
> **Forcing context:** [CROSS_FILE_CONTRACT_RESOLUTION.md](./CROSS_FILE_CONTRACT_RESOLUTION.md)

---

## 0. Thesis (what the spike changed)

The SG-1/2/3 spike, run against the real run-009 stack (`/Users/neilyashinsky/Documents/dev/strtd8/strtd8/`),
found that **most of the proposed Phase 1 is already shipped**:

- **Prisma fact extraction** — `languages/prisma_parser.py` already parses all 12 real models. *(was SG-1)*
- **Zod⇄Prisma CONFORMS_TO** — `validators/prisma_zod_symmetry.py` already binds + diffs, and caught the real #13 drift with zero false-positives. *(was SG-3)*
- **5 of the 6 Approach-B cross-file signatures** are implemented and wired into
  `contractors/prime_postmortem.py:_evaluate_cross_file_integrity`.

So Phase 1 is **not** "build a substrate." It is **three new checks** (two SCIP-backed —
external-type-presence and route-shape — plus one toolchain-free tsconfig-paths check) plus
**wiring scip-typescript** (which the spike proved works: full app-source index in ~7s, real
cross-file + external `.d.ts` resolution) **and making the verifier verdict actually gate the run**
(see §0.2 / REQ-CKG-240). The SQLite store, OTel projection, taint, and the Go/Python/Java/C#
backends from the design are **all deferred** — Phase 1 needs none of them.

---

## 0.1 Planning Insights (v2.0 → v2.1, reflective update)

> Writing the implementation plan ([CODE_KNOWLEDGE_GRAPH_PHASE1_PLAN.md](./CODE_KNOWLEDGE_GRAPH_PHASE1_PLAN.md))
> stress-tested v2.0. Six corrections — the requirements still carried premature specifics.

| v2.0 assumption | Planning discovery | Impact |
|---|---|---|
| Need a separate fact normalizer (REQ-CKG-220) | The 3 checks consume the SCIP reader's accessors directly; a separate `ScipFacts` model is an unneeded layer in Phase 1 | **220 collapsed into 210** (reader exposes typed accessors) |
| Route-shape (620) is a firm deliverable | SCIP route/response-type fidelity is unverified (OQ-2); it's the only med-high-risk item | **620 made spike-gated** with a narrowed fallback acceptance |
| Signature-(f) enumeration strategy open (OQ-1) | Validating *referenced* members against resolved occurrences (strategy a) suffices for #4/#11 | **OQ-1 resolved → strategy (a) for Phase 1** |
| Corpus (690) is an end-of-phase gate | The regression half must land *first* to lock the 5 shipped signatures before editing the shared Verifier | **690 split: 690a regression-lock (precondition) / 690b acceptance** |
| Extending `_evaluate_cross_file_integrity` is safe | Modifying a shipped, wired surface risks regressing the existing 5 checks | **600 strengthened: behavior-preserving, enforced by 690a** |
| Need a `[code-observability]` pip extra + scip_pb2 generation | `protobuf` already present; vendor a pinned `scip_pb2.py` → no protoc/grpcio-tools runtime dep; only the Node tool is new | **Dependencies simplified** (no new pip extra required) |

**Resolved open questions:** OQ-1 → strategy (a). OQ-3 → run per-batch SCIP against the installed
disk state; treat in-flight generated files as the batch under test.

---

## 0.2 CRP Triage (v2.1 → v2.2)

> 4-model Convergent Review (gpt-5.5, composer-2.5, claude-opus-4-8, gemini-3.1-pro). All
> requirements-side suggestions **ACCEPTED** (one plan-side refactor rejected — see plan Appendix B).
> Full dispositions in Appendix A. **The review found a code-verified critical gap the reflective
> loop missed:** the cross-file verifier runs in a detached `daemon=False` thread *after* the run
> returns (`launch_prime_postmortem_async`, `prime_postmortem.py:2728-2733` → `prime_contractor.py:5241`),
> and the batch verdict is `mean(disk_scores)` vs a `0.8` threshold (`prime_postmortem.py:1459`) — so a
> single cross-file FAIL averages away and **the verdict never gates the run**. As wired, *even perfect
> checks could not close the inversion.*

**New/changed requirements from triage:** REQ-CKG-240 (synchronous verdict consumption — **decision:
gate the run**, not advisory-only), REQ-CKG-245 (aggregate any-error rule), REQ-CKG-235 (finding
contract + availability states + local/cross-file scope tag), REQ-CKG-236 (disk-materialization
precondition). REQ-CKG-630 corrected to **real tsconfig `paths`+`extends` parsing** (the shipped
import checker only heuristically resolves `@/`). REQ-CKG-600 now mandates extraction to a
`cross_file_verifier.py` registry returning a typed verdict, and forbids the per-feature LLM reviewer
from enforcing cross-file checks.

---

## 1. The 16 RUN_009 failures — coverage after the spike

This is the scope, evidence-based. "Existing" = already shipped & verified; "**NEW**" = Phase 1 work.

| # / category | Status | Owner |
|---|---|---|
| 1,2 module-path | ✅ existing | `cross_file_imports.scan_unresolvable_imports` |
| 3 dependency-availability | ✅ existing | `cross_file_imports.scan_missing_dependencies` |
| 6,8,12 canonical-schema (fields/compound-key) | ✅ existing | `prisma_usage.scan_prisma_usage` + `prisma_parser` |
| 13 Zod field-in-Zod-not-in-Prisma | ✅ existing | `prisma_zod_symmetry.evaluate_cross_file_integrity` |
| 9 destructure of fields absent from the Zod schema | ⚠ **verify in 690a** | `prisma_zod_symmetry` checks Zod↔Prisma, **not** destructure↔Zod — coverage unconfirmed (R2-F3) |
| 7 type-class mismatch | ✅ existing | `prisma_zod_symmetry` |
| **4, 11 external-library-API** (`Anthropic.ContentBlockParam`, `next` `defineConfig`) | ❌ **NEW** | **REQ-CKG-610 signature (f)** |
| **15 api-response-shape** (UI `body` field not on model) | ❌ **NEW** | **REQ-CKG-620 route-shape** |
| **5 project-config** (tsconfig alias → nonexistent `src/`) | ⚠ **NEW (small)** | **REQ-CKG-630** |
| 10 unused params; 16 framework-rendering-mode | ⏸ deferred | tsc-gate / framework-config (out of Phase 1) |

**Phase 1 closes #4, #11, #15, and #5.** Everything else is already caught — Phase 1 must keep it caught (regression).

---

## 2. Reuse, do not rebuild (promote existing code to CKG fact sources)

| Existing | Role in Phase 1 |
|---|---|
| `languages/prisma_parser.py` | Prisma facts (no DMMF — demoted to optional fidelity) |
| `validators/cross_file_imports.py` | signatures (a) unresolvable-import, (b) missing-dep |
| `validators/prisma_usage.py` | signatures (c) field-site, (e) compound-key |
| `validators/prisma_zod_symmetry.py` | signature (d) Zod⇄Prisma CONFORMS_TO + field diff |
| `contractors/prime_postmortem.py:_evaluate_cross_file_integrity` | the Verifier surface to **extend**, not replace |
| `contractors/upstream_interface.py:render_prisma_field_sets` | generation-time Prisma field inheritance (already live) |

---

## 3. Requirements (new work only)

### 3.1 scip-typescript authoritative TS index (REQ-CKG-2xx)

**REQ-CKG-200 — scip-typescript runner.** Wrap `scip-typescript index` as a subprocess producing
a per-batch SCIP index for the target project. Authoritative mode: requires `node_modules`
installed; runs once per batch (the spike measured ~7s; **not** the inner loop). Output to a
transient path under `.startd8/state/` (no persistent store required in Phase 1).

**REQ-CKG-210 — SCIP reader.** Read the index via generated `scip_pb2` (vendor `scip_pb2.py`
or generate from `scip.proto` at build). **Read external symbols from `Document.occurrences`,
not `Index.external_symbols`** (empty in scip-typescript 0.4.0 — verified). Expose: per-document
occurrences (symbol string, roles, range), cross-file def→ref edges, and external-package member
symbols (e.g. `… npm zod 3.x …/ZodObject#extend().`).

**REQ-CKG-220 — (collapsed into 210 per Planning Insights).** No separate fact-normalizer model
in Phase 1. The reader (REQ-CKG-210) exposes the typed accessors the three checks need —
`external_member_refs()`, `cross_file_edges()`, `routes()` — and that *is* the fact surface. A
general-purpose CKG schema/store is deferred (§5). Revisit only if a second consumer needs facts
in a shape the reader doesn't already provide.

**REQ-CKG-230 — Fallback with explicit availability state (R1-F1).** If the target doesn't
install/index cleanly, skip the SCIP-backed checks (signature f, route-shape) and **emit an explicit
availability state per check** — `ran` / `failed` / `skipped_unavailable` — never raise, and **never
let `skipped_unavailable` read as PASS**. The aggregate summary MUST report SCIP-backed categories as
`unverified` (not verified-clean) when the index was unavailable, and MUST NOT claim full 16/16
verification. The 5 toolchain-free signatures continue to run regardless. (Pre-flight: validate
`package.json`/`tsconfig.json` are parseable before invoking scip-typescript; corruption → advisory
degrade, R4-S3.)

### 3.2 The two new checks + unification (REQ-CKG-6xx)

**REQ-CKG-610 — Signature (f): external-type-presence.** For each reference to an external
package member in generated code (e.g. `Anthropic.ContentBlockParam`, `import { defineConfig }
from 'next'`), assert it resolves to a real symbol. **Mechanism (OQ-1 resolved → strategy a):**
validate the *referenced* member against the resolved occurrence set from the SCIP index; a
referenced member that resolves to nothing / `local` is a violation. Strategy (b) — indexing the
package's `.d.ts` directly to enumerate valid exports — is a fallback used **only if (a) produces
false-positives** (not Phase 1 default). **Acceptance (R1-F2 import-form matrix):** beyond the two
RUN_009 cases, fixtures must state expected pass/fail/fallback for each common TS import form —
namespace import, named, default, `import type`, re-exports, subpath exports, conditional exports,
and package helper types — with **≥1 false-positive guard**. The matrix also defines when an
unresolved occurrence is a *bad reference* vs a *SCIP/indexing limitation* (the strategy-b fallback
trigger). Baseline: flags invented `Anthropic.ContentBlockParam` and `import { defineConfig } from
'next'`; passes real `Anthropic.TextBlockParam` (#11, #4).

**REQ-CKG-620 — Route request/response-shape check. ⚠ SPIKE-GATED (OQ-2).** *Before committing
this requirement,* a 0.5d sub-spike must confirm SCIP exposes Next.js handler request/response
types with enough fidelity (Response generics, inferred returns). **If confirmed:** extract `Route`
request/response types and assert a UI consumer's expected response shape matches the producing
route's actual shape — **acceptance:** flags RUN_009 #15 (UI consumes a `body` field absent from
the route's response). **If fidelity is poor:** the sub-spike MUST record exactly one decision from a
fixed table (R1-S4) — *(i)* SCIP type field-set check, *(ii)* literal `NextResponse.json(...)`
body field-set check, *(iii)* tsc-only diagnostic handoff, or *(iv)* unsupported → **#15 removed
from the 690b zero-false-PASS claim and tracked by the tsc/framework gate**. **The contradiction
between "may move to tsc-gate" and 690b's 16/16 is resolved by this rule:** 690b counts #15 only if
(i) or (ii) lands; otherwise #15 is explicitly excluded from CKG Phase 1 acceptance (R1-F3). This is
the only RUN_009 failure depending on 620.

**REQ-CKG-630 — tsconfig path-alias target existence (R2-F1: real parsing, not heuristic).**
Parse `tsconfig.json` / `tsconfig.*.json` `compilerOptions.paths` **following `extends` chains**,
map each pattern to its filesystem target(s), and flag targets that don't exist. **Do NOT rely on
`cross_file_imports.py`'s hardcoded `alias_bases=("", "src")` heuristic** — verified: that code does
not read `paths` today, so this is real new work (not a 0.5d extension). `@/` *import* resolution
stays with the existing unresolvable-import signature; this check owns the *alias-definition*
validity. **Acceptance:** flags #5 (`@/* → ./src/*` with no `src/`); a multi-level `extends` fixture
resolves correctly; valid alias passes (no false positive).

**REQ-CKG-600 — Unify under one Verifier (behavior-preserving + extracted registry).** Extract the
cross-file checks into a new `validators/cross_file_verifier.py` exposing a typed `CrossFileCheck`
registry; `_evaluate_cross_file_integrity` becomes a **thin caller** (stable name/call-site for
behavior preservation, R1-S2/R2-S2). The verifier **returns a typed batch result** (verdict +
per-check availability + findings) to the caller — not only written to report files (R3-S4) — so
REQ-CKG-240/245 can consume it. All 5 existing + 3 new checks run behind this surface with the
existing attribution + Kaizen suggestion. New checks gate on SCIP availability (REQ-CKG-230). The
extension MUST be behavior-preserving for the 5 existing checks — verified by landing REQ-CKG-690a
*before* the refactor (byte-equivalent feature verdicts). **Phase 1 explicitly does NOT invoke
`cross_file_verifier`/`scip_runner` from `PrimaryContractorWorkflow` or `implementation_engine`**
(batch-only; R2-S2).

**REQ-CKG-690a — Regression lock (precondition).** Encode the categories the 5 shipped signatures
already catch (#1–3, 7, 12, 13) as fixtures and assert current behavior **before** modifying the
verifier surface. This is the safety net for REQ-CKG-600 and must land first. **Plus a Zod
composition audit (R1-F5/S3):** fixtures for nested `z.object`, `z.union`, discriminated unions,
`.extend()`, `.merge()`, `z.lazy`, and imported/composed schemas — each either detected, classified
`warning`/`unverified`, or **explicitly excluded with a named downstream gate**. (This is where the
"is Phase 1 under-scoped?" question gets a concrete answer; #9 destructure-coverage is confirmed or
reclassified here.)

**REQ-CKG-690b — New-check acceptance (end of phase), at TWO levels (R3-F4/F5).** Extend the corpus
to all 16 failures. Assert **(a)** the offending feature FAILs **and (b)** the aggregate/run verdict
is non-PASS, for each of #4/#11/#5 (and #15 iff 620 lands per its decision table) — with **zero
false-PASS** across the full set. Include an explicit **single-failure dilution fixture** (12 clean
features + 1 cross-file FAIL → run verdict non-PASS). This is the operational definition of "the
score-vs-reality inversion is closed for this stack" — and it is only achievable given REQ-CKG-240
(verdict gating) and REQ-CKG-245 (aggregate any-error rule).

### 3.3 Verdict consumption, aggregation & finding contract (the critical CRP cluster)

> These exist because the review proved (in code) that the verifier as wired is non-gating. Without
> them, REQ-CKG-690b is unachievable and every other check improves a report nobody acts on.

**REQ-CKG-240 — Synchronous verdict consumption (R3-F1, critical). Decision: GATE the run.** The
cross-file verifier verdict MUST be consumed by the prime run result and surfaced (e.g. CLI exit
status / returned verdict) — **not** computed in the detached `daemon=False` postmortem thread that
currently runs *after* `result_dict` is returned (`prime_contractor.py:5241`). Phase 1 makes the
batch cross-file verifier **synchronous/joined before final status** (CKG Phase 1 is *not*
advisory-only). **Acceptance:** a batch containing #4/#11 yields a non-PASS run result/exit code,
not merely a FAIL line in an async report.

**REQ-CKG-245 — Aggregate any-error rule (R3-F2, critical).** Any **error**-severity cross-file
finding caps the batch verdict at **FAIL** (at most PARTIAL), **independent of** the
`mean(disk_scores)` aggregate (`prime_postmortem.py:1459`, `_PASS_THRESHOLD=0.8`). Cross-file
failures are build-breaking and must not be averaged away. **Acceptance:** 12 clean features + 1
cross-file FAIL → aggregate verdict non-PASS.

**REQ-CKG-235 — Finding contract (R1-F6/R4-F2/R1-S6).** Every finding (existing + new) emits a
normalized record: `check_id`, `source_file`, `owning_feature`, `severity`, `expected_vs_actual`
(where available), `evidence_source`, **`availability_state`** (`ran`/`failed`/`skipped_unavailable`),
**`scope`** (`local` | `cross_file`), `user_message`, and a `remediation_hint`. Golden-output tests
assert representative failures carry remediation-grade messages + availability state.

**REQ-CKG-236 — Materialization precondition (R2-F4/R2-S3).** Cross-file checks run only after all
batch `generated_files` are flushed to `project_root` and readable. A path generated but not on disk
emits `skipped_not_materialized` (explicit unverified record) — **never silently omitted** from
`sources` (today's postmortem reads on-disk files only, so a missing flush looks like a clean batch).

---

## 4. Non-functional requirements

- **NFR-1 — Toolchain-free baseline preserved.** The 5 existing signatures must keep running with
  no Node toolchain; only the 3 SCIP-backed checks require it (and degrade gracefully, REQ-CKG-230).
- **NFR-2 — Per-batch at the postmortem hook, not inner-loop (R2-F2).** SCIP indexing runs once per
  Prime **batch**, at the `launch_prime_postmortem_async` cross-file evaluation window (after all
  `generated_files` are on disk), ~7s verified. It is **not** invoked per `PrimaryContractorWorkflow`
  feature. Per-feature checks are queries against the already-built index.
- **NFR-3 — Clean-room.** scip-typescript (Apache-2.0), protobuf, existing SDK validators — no
  CodeQL artifacts. Record tool versions/licenses.
- **NFR-4 — Anti-deferral.** The new external-API + route-shape + tsconfig checks ship in Phase 1;
  they are the only RUN_009 categories still uncaught.
- **NFR-5 — Determinism (R3-F3).** In CI/acceptance, the SCIP index + cross-file verifier MUST
  complete (awaited/joined) before the run reports final status; an un-joined `daemon=False` thread is
  not an acceptable home for a gating check. Test: 20 repeats yield an identical verdict (no race).
- **NFR-6 — LLM inner-loop reviewer defers cross-file (R4-F1).** The `PrimaryContractorWorkflow`
  per-feature LLM review prompt (`contractor_prompts.yaml`) MUST explicitly mark cross-file/external-
  type checks **out of scope for that review** (they depend on the per-batch SCIP index, which doesn't
  exist mid-batch) — preventing hallucinated-FAIL retry loops that waste retry budget.

## 5. Non-requirements (explicitly deferred — the spike removed these from Phase 1)

- **DMMF Prisma probe** — `prisma_parser` suffices; DMMF is an optional fidelity upgrade later.
- **New CONFORMS_TO binder** — already exists (`prisma_zod_symmetry`).
- **SQLite CKG store + OTel projection + Grafana** — Phase 1 uses the transient SCIP index; persist
  only if incremental needs force it.
- **Go / Python / Java / C# authoritative backends** — later phases.
- **Taint / injection (Pysa, IFDS-lite)** — Phase 3.
- **tree-sitter draft mode** — only needed once we want inner-loop partial extraction; not Phase 1.
- **Failures #10 (unused params), #16 (rendering-mode)** — tsc-gate / framework-config track.

## 6. Dependencies

- **Node tools (subprocess):** `@sourcegraph/scip-typescript` (verified v0.4.0). Documented as a
  prerequisite for the SCIP-backed checks, not a Python import.
- **Python:** **vendor a pinned `scip_pb2.py`** (generated from `scip.proto`; no protoc/grpcio-tools
  at *runtime* — grpcio-tools is dev-time-only for regeneration). The reader parses it via
  **`protobuf`**, which is **NOT a declared startd8 dependency** — correction found during Inc-0: v2.2
  wrongly assumed it was present (it was only pulled in transitively by grpcio-tools). Phase 1 therefore
  adds **one optional extra**: `[code-observability] = ["protobuf>=4.21.0"]`. The SCIP **reader**
  requires that extra; the package stays **import-safe without it** (guarded import — `parse_symbol`
  and `scip_runner` work; the reader raises a clear "install the extra" error only when used). The Node
  `scip-typescript` tool is a separate (non-pip) prerequisite. Core suite + the 5 toolchain-free
  signatures run with both the extra and the Node tool absent (REQ-CKG-230/710).

## 7. Verification strategy

1. **Regression** — the RUN_009 corpus: 5 existing signatures still catch #1–3,6–9,12,13 (no behavior change).
2. **New checks** — signature (f) catches #4/#11 (invented external member); route-shape catches #15; tsconfig check catches #5.
3. **Ops** — SCIP index builds on the real `strtd8/` in seconds; reader extracts external member symbols from occurrences.
4. **Graceful degrade** — with `node_modules` absent / project not indexable, SCIP-backed checks downgrade to advisory; toolchain-free 5 still run.
5. **Total** — 16/16 detected, zero false-PASS (REQ-CKG-690).

## 8. Open questions

- **OQ-1 → RESOLVED (strategy a).** Validate *referenced* external members against the resolved
  occurrence set; index a package's `.d.ts` directly only as a fallback if (a) false-positives.
- **OQ-2 — OPEN, gates REQ-CKG-620.** Route-shape extraction fidelity from SCIP handler signatures
  (Next.js `Response` generics) — the Inc-3 sub-spike resolves this before 620 is committed.
- **OQ-3 → RESOLVED (sharper).** Per-batch SCIP runs at the `launch_prime_postmortem_async` window
  against the materialized disk state (REQ-CKG-236), **synchronously gating the run** (REQ-CKG-240).
  Lifecycle: materialize batch → validate/install deps (or declare unavailable) → run scip once →
  run SCIP-backed checks → aggregate (any-error rule) → return verdict (R1-S1/R2-S3/R2-S4).
- **OQ-4 → RESOLVED (closed, R2-F5).** The unified verifier emits an optional
  `.startd8/state/ckg-findings-{run_id}.json` (normalized findings per REQ-CKG-235 + availability
  summary) on FAIL — a durable operator/Kaizen artifact (Mottainai) with **no SQLite store and no OTel
  projection** in Phase 1. Stays check-only otherwise.

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-F{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-F1 | Availability states; advisory ≠ PASS | gpt-5.5 | → REQ-CKG-230 (ran/failed/skipped_unavailable; unverified not PASS) | 2026-06-01 |
| R1-F2 | 610 import-form acceptance matrix | gpt-5.5 | → REQ-CKG-610 acceptance (namespace/named/default/import type/re-export/subpath/conditional + FP guard) | 2026-06-01 |
| R1-F3 | 620 fallback vs 690b #15 contradiction | gpt-5.5 | → REQ-CKG-620 decision-table rule; 690b counts #15 only if (i)/(ii) lands | 2026-06-01 |
| R1-F4 | Scope language "two" vs 3rd check | gpt-5.5 | → §0 thesis: "three new checks (2 SCIP-backed + 1 config)" | 2026-06-01 |
| R1-F5 | Zod composition coverage audit | gpt-5.5 | → REQ-CKG-690a (nested/union/discriminated/extend/merge/lazy/imported fixtures) | 2026-06-01 |
| R1-F6 | Remediation-grade finding fields | gpt-5.5 | → REQ-CKG-235 finding contract | 2026-06-01 |
| R2-F1 | 630 real tsconfig paths+extends parsing | composer-2.5 | → REQ-CKG-630 rewritten (verified: cross_file_imports does NOT read `paths`) | 2026-06-01 |
| R2-F2 | SCIP at batch postmortem hook, not per-feature | composer-2.5 | → NFR-2 + REQ-CKG-600 (batch-only; not from PrimaryContractor/impl-engine) | 2026-06-01 |
| R2-F3 | Split failure #9 vs #15 | composer-2.5 | → §1 table: #9 reclassified ⚠ verify-in-690a; #15 already NEW | 2026-06-01 |
| R2-F4 | Disk-materialization guard | composer-2.5 | → REQ-CKG-236 (skipped_not_materialized) | 2026-06-01 |
| R2-F5 | Close OQ-4 w/ optional JSON findings export | composer-2.5 | → OQ-4 resolved (`.startd8/state/ckg-findings-{run_id}.json`, no store/OTel) | 2026-06-01 |
| R3-F1 | **Synchronous verdict consumption (CRITICAL)** | claude-opus-4-8 | **verified** async detached thread; → REQ-CKG-240, decision = GATE the run | 2026-06-01 |
| R3-F2 | **Aggregate any-error rule (CRITICAL)** | claude-opus-4-8 | **verified** mean@0.8 dilution; → REQ-CKG-245 | 2026-06-01 |
| R3-F3 | Deterministic completion (join) | claude-opus-4-8 | → NFR-5 | 2026-06-01 |
| R3-F4 | Zero-false-PASS defined at feature + run level | claude-opus-4-8 | → REQ-CKG-690b two-level acceptance + dilution fixture | 2026-06-01 |
| R4-F1 | NFR: LLM inner-loop reviewer defers cross-file | gemini-3.1-pro | → NFR-6 | 2026-06-01 |
| R4-F2 | Finding `scope: local\|cross_file` tag | gemini-3.1-pro | → REQ-CKG-235 (scope field) | 2026-06-01 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | All requirements-side (F) suggestions accepted. | — | The one rejected suggestion is plan-side R4-S2 — see the plan's Appendix B. | 2026-06-01 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — gpt-5.5 — 2026-06-01 18:45 UTC

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-01 18:45:00 UTC
- **Scope**: Requirements robustness review focused on verifier semantics, route-shape uncertainty, external API edge cases, and end-user value of postmortem output.

##### Executive Summary

- The requirements should distinguish "detected," "not run," and "unverified" so graceful degradation does not recreate the false-PASS problem.
- The headline scope has a small inconsistency: "two genuinely-missing checks" coexists with the new tsconfig alias check and a 3-new-check plan.
- REQ-CKG-610 needs acceptance criteria for normal TypeScript import forms, not only the two RUN_009 examples.
- REQ-CKG-620 is correctly spike-gated, but its fallback conflicts with the current 16/16 acceptance wording unless the requirement defines how #15 is counted.
- The requirements can improve end-user value by requiring remediation-grade findings, not just internal semantic issues.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Risks | high | Revise REQ-CKG-230 so advisory fallback cannot be interpreted as PASS: require each SCIP-backed check to emit an availability state such as ran, failed, skipped_unavailable, or unverified, and require aggregate reports to preserve that distinction. | The sentence "skip the SCIP-backed checks ... downgrade them to advisory — never raise" conflicts with the user-facing goal of "zero false-PASS" when the missing checks are exactly #4/#11/#15. | REQ-CKG-230 and Verification strategy item 4 "Graceful degrade" | Add acceptance criteria where `node_modules` is absent: the 5 toolchain-free checks still run, SCIP-backed categories are listed as unverified, and the aggregate summary cannot claim full 16/16 verification. |
| R1-F2 | Interfaces | high | Expand REQ-CKG-610 acceptance beyond `Anthropic.ContentBlockParam` and `defineConfig`: specify import-form fixtures for namespace imports, named imports, default imports, `import type`, re-exports, subpath exports, conditional exports, and package helper types. | The current mechanism says "validate the referenced member against the resolved occurrence set," but it does not define how normal TS import patterns map to referenced members or when direct `.d.ts` indexing is required. | REQ-CKG-610 after "Strategy (b)" | The requirement is satisfied only when fixtures state expected pass/fail/fallback behavior for each import form and at least one false-positive guard is included. |
| R1-F3 | Validation | high | Make REQ-CKG-620's fallback contract explicit: if SCIP cannot recover route response field sets, either define a narrower literal-body or tsc-backed checker that still covers #15, or remove #15 from the Phase 1 690b zero-false-PASS claim. | The requirement says "#15 may move to the tsc-gate track" while REQ-CKG-690b still expects 16-failure closure. That contradiction will confuse implementers and later reviewers. | REQ-CKG-620 and REQ-CKG-690b | After the sub-spike, the requirements must contain one of two testable outcomes: #15 caught by a named Phase 1 checker, or #15 explicitly excluded from CKG Phase 1 acceptance and tracked by the tsc/framework gate. |
| R1-F4 | Architecture | medium | Normalize the Phase 1 scope language so "two genuinely-missing checks" accounts for REQ-CKG-630, or rename the scope to "two SCIP-backed checks plus one toolchain-free config check." | Section 0 says Phase 1 is "the two genuinely-missing checks plus wiring scip-typescript," while Section 1 and REQ-CKG-630 add the tsconfig alias target check. This is minor but can cause scope mistakes during planning. | Section 0 Thesis and Section 1 failure table | A reader should be able to count the Phase 1 new work from the thesis and get the same set as REQ-CKG-610, REQ-CKG-620, and REQ-CKG-630. |
| R1-F5 | Validation | medium | Add an explicit existing-validator coverage requirement for `prisma_zod_symmetry`: flat object coverage is accepted only if the corpus also covers or documents exclusions for nested objects, `z.union`, discriminated unions, `.extend()`, `.merge()`, and imported schema composition. | The requirements rely on SG-3 as "already built," but the spike evidence proves one coherent and one drifting flat schema. Phase 1 may be under-scoped if common Zod composition forms can hide RUN_009-class drift. | Section 2 "Reuse, do not rebuild" or REQ-CKG-690a | Add 690a fixtures for each Zod composition pattern; each fixture must either be detected, classified as warning/unverified, or explicitly excluded with a downstream gate named. |
| R1-F6 | Ops | medium | Add a finding-quality requirement: every verifier finding should include source file, owning feature, check id, expected vs actual where available, evidence source, availability state, and one remediation hint suitable for the end user. | The current requirements emphasize internal attribution and Kaizen suggestions, but end users need actionable diagnostics to fix generated code without reading validator internals. This also makes future OTel/store projection cheaper without requiring a Phase 1 store. | REQ-CKG-600 and Verification strategy | Golden-output tests should assert that representative failures for external API, route shape, tsconfig alias, and Zod/Prisma drift include remediation-grade messages and availability state. |

#### Review Round R2 — composer-2.5 — 2026-06-01 19:15 UTC

- **Reviewer**: composer-2.5
- **Date**: 2026-06-01 19:15:00 UTC
- **Scope**: Second-pass requirements review — code-accurate REQ-CKG-630 scope, batch vs primary-contractor boundaries, failure-table precision, and operator-facing artifacts without a SQLite store.

##### Executive Summary

- REQ-CKG-630 must require real tsconfig `paths` parsing; the shipped import checker only guesses `@/` layout when tsconfig is absent.
- OQ-3 should name the Prime batch postmortem hook, not imply SCIP runs during each PrimaryContractor feature.
- Failure #9 and #15 need distinct acceptance language to avoid false confidence in "existing" Zod symmetry.
- Resolve OQ-4 with a lightweight JSON findings export for operators (Mottainai) instead of silent check-only output.
- Endorse R1-F1, F2, F3, F5, F6 pending triage.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Validation | high | Rewrite REQ-CKG-630 mechanism: parse `tsconfig.json` / `tsconfig.*.json` `compilerOptions.paths` (follow `extends`), map each pattern to filesystem targets, flag targets that do not exist; do not rely on `cross_file_imports` `alias_bases=("", "src")` heuristics alone. | The requirement says "every tsconfig path alias" but the only related shipped code resolves `@/` heuristically when tsconfig is missing (`cross_file_imports.py`). Without this clarification, implementers will under-ship #5. | REQ-CKG-630 body | Acceptance uses RUN_009 #5 plus a multi-level `extends` fixture; `@/` imports may still use existing unresolvable-import checks separately. |
| R2-F2 | Architecture | high | Amend OQ-3 / NFR-2 / REQ-CKG-200: SCIP indexing runs once per **Prime batch** immediately before postmortem cross-file evaluation (`launch_prime_postmortem_async`), not per `PrimaryContractorWorkflow` feature. Cross-file checks remain batch-scoped; primary/lead contractor per-feature review stays manifest + LLM only in Phase 1. | Requirements say "in-flight generated files are the batch under test" but do not name the integration point. Wiring SCIP into the implementation engine would duplicate postmortem work and add accidental complexity to the lead-contractor path. | §8 OQ-3, NFR-2, REQ-CKG-200 | Architecture note in reqs + test that `implementation_engine` does not invoke `scip_runner`; SCIP invoked only from postmortem/batch orchestration path. |
| R2-F3 | Validation | medium | Split Section 1 failure table row "13 + 9 Zod/api field drift" into explicit rows: #9 (Zod/route handler field drift via `prisma_zod_symmetry` where applicable) vs #15 (UI consumer ↔ route response shape via REQ-CKG-620). | The combined row implies Phase 1 already covers api-shape failures; #15 is still NEW and structurally different from Prisma↔Zod symmetry. | Section 1 table | Reader can map each failure ID to exactly one owner check without double-counting acceptance. |
| R2-F4 | Ops | medium | Add REQ-CKG-691 (or extend REQ-CKG-600): before cross-file evaluation, all batch outputs must be persisted under `project_root`; if a path is missing on disk, emit `skipped_not_materialized` rather than silently omitting it from `sources`. | Postmortem `_evaluate_cross_file_integrity` only reads files that exist on disk. Missing flush looks like a clean batch. | New bullet under §3.2 or REQ-CKG-600 | Test with generated_files listed but not written → explicit unverified/skipped record, not PASS. |
| R2-F5 | Data | low | Close OQ-4 for Phase 1: emit optional `.startd8/state/ckg-findings-{run_id}.json` (normalized findings + availability summary) from the unified verifier; no SQLite store, no OTel projection requirement. | Gives operators and Kaizen a durable artifact (Mottainai) without building L4 storage; satisfies "check-only" while improving end-user debuggability. | §8 OQ-4 and Verification strategy | Golden test asserts JSON written on FAIL and includes per-check availability counts. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):

- R1-F1: Availability states must prevent SCIP degrade from reading as PASS.
- R1-F2: REQ-CKG-610 needs import-form acceptance matrix.
- R1-F3: REQ-CKG-620 vs 690b must not contradict on #15.
- R1-F5: Zod composition coverage audit belongs in 690a.
- R1-F6: Remediation-grade finding fields are required for end-user value.

#### Review Round R3 — claude-opus-4-8 — 2026-06-01 19:30 UTC

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-06-01 19:30:00 UTC
- **Scope**: Third-pass requirements review focused on *verdict consumption* gaps that prior rounds did not reach: the cross-file verifier currently runs in a fire-and-forget background thread after the run reports its result, and the aggregate verdict is a mean that dilutes any single cross-file FAIL below the PASS threshold. Both make "zero false-PASS" unachievable at the run level as written.

##### Executive Summary

- REQ-CKG-690b's "zero false-PASS" is unachievable as written because the verifier verdict never gates the run: `launch_prime_postmortem_async` computes it in a background thread *after* `result_dict` is returned. Requirements must either mandate synchronous verdict feedback or explicitly scope CKG Phase 1 as advisory-only.
- Aggregate verdict semantics are unspecified: the implementation averages per-feature disk scores against a 0.8 PASS threshold, so one cross-file FAIL in a ~13-feature batch still reads PASS. Requirements must mandate an any-error aggregation rule for cross-file findings.
- "Zero false-PASS" must be defined at both the feature and aggregate/run levels to be testable.
- Determinism: a gating check cannot run on an un-joined `daemon=False` thread; requirements should mandate deterministic completion before final status in CI/acceptance.
- Endorse R1-F1, R1-F6, R2-F2, R2-F4 — they are preconditions for the above.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Risks | critical | Add a requirement that the cross-file verifier verdict is consumed synchronously by the prime run result (and surfaced via CLI exit status), OR explicitly declare CKG Phase 1 advisory-only and remove the run-level "zero false-PASS" claim. As written, the postmortem (`launch_prime_postmortem_async`) runs detached after the run returns, so no check result can change the reported outcome. | "Zero false-PASS" (REQ-CKG-690b) is the headline user value, but the only consumer of cross-file findings is an async background thread whose verdict is logged, not returned. Every check requirement is moot until this is fixed. | New REQ-CKG-240 (Verdict consumption) + REQ-CKG-690b | Acceptance: a batch with #4/#11 produces a non-PASS run result/exit code, not merely a FAIL line in an async report. |
| R3-F2 | Validation | critical | Specify aggregate-verdict semantics: any error-severity cross-file finding forces the batch verdict to at most PARTIAL (preferably FAIL), independent of the mean disk-quality score. | The implementation sets `aggregate_score = mean(disk_scores)` against `_PASS_THRESHOLD = 0.8`; a single zeroed feature among ~13 still aggregates ≈ 0.92 → PASS. Cross-file failures are build-breaking and must not be averaged away. | REQ-CKG-690b and §4 NFR-4 | Test: 12 clean features + 1 cross-file FAIL → aggregate verdict non-PASS; include an explicit single-failure dilution fixture. |
| R3-F3 | Ops | high | Require deterministic completion: in CI/acceptance modes the SCIP index + cross-file verifier must finish (awaited/joined) before the run reports final status; an un-joined `daemon=False` postmortem thread is not an acceptable home for a gating check. | A gating verdict computed on a detached thread races short-lived CLI exits and cannot be asserted deterministically in CI. | §4 NFR (new NFR-5 Determinism) | Test: run returns only after verifier completes; 20 repeats yield identical verdict (no race). |
| R3-F4 | Data | medium | Make REQ-CKG-690b's "zero false-PASS" operational definition explicit at two levels: (a) the offending feature FAILs, and (b) the aggregate/run verdict is non-PASS. | The current single-level phrasing lets a per-feature FAIL coexist with an aggregate/run PASS (via dilution or async detachment), which is itself a false-PASS to the end user. | REQ-CKG-690b | Acceptance asserts both feature-level and run-level verdicts for each of #4/#11/#5/#15. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):

- R1-F1: Availability states are a precondition for trustworthy run-level verdicts.
- R1-F6: Remediation-grade fields make the gating verdict actionable.
- R2-F2: Batch-scoped SCIP at the postmortem hook is the correct (but currently non-gating) integration point.
- R2-F4: Disk-flush / materialization guard is required before the verifier can be trusted to gate.

#### Review Round R4 — gemini-3.1-pro — 2026-06-01 19:40 UTC

- **Reviewer**: gemini-3.1-pro
- **Date**: 2026-06-01 19:40:00 UTC
- **Scope**: Fourth-pass requirements review focused on clarifying the boundary between deterministic CKG postmortem checks and stochastic LLM inner-loop reviews, addressing adjacent accidental complexity in `PrimaryContractorWorkflow`.

##### Executive Summary

- Because SCIP runs per-batch (NFR-2) and the LLM review loop (`PrimaryContractorWorkflow`) runs per-feature mid-batch, the LLM is "flying blind" on cross-file compliance. The requirements must explicitly forbid the LLM reviewer from gating features on cross-file checks, leaving this to the deterministic batch postmortem.
- Unnecessary complexity exists because "cross-file" and "local semantic" errors aren't cleanly delineated in the unified verifier's contract (REQ-CKG-600), causing upstream workflow confusion on what is actionable during a retry loop.
- Endorse R3-F1 (sync verdict consumption) and R3-F2 (aggregate fail semantics).

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F1 | Architecture | high | Update NFR-2 to explicitly prohibit LLM-based inner-loop reviews from attempting to enforce cross-file contracts or external type resolutions that depend on the CKG phase 1 features. | Mid-batch features cannot be reliably validated for cross-file compliance because the batch isn't finished and SCIP isn't run yet. Tasking the LLM with this produces "hallucinated FAIL" cycles, wasting retry budgets and adding accidental complexity. | §4 NFR-2 | Verify that the `PrimaryContractorWorkflow` review prompt explicitly lists cross-file checks as "out of scope for this review" and defers them. |
| R4-F2 | Interfaces | medium | Enhance REQ-CKG-600 (Unified Verifier) to require that the emitted finding contract explicitly distinguishes between "local" errors (fixable in the inner loop) and "cross-file" errors (only fixable by adjusting the batch plan or dependencies). | Without this distinction, the upstream orchestrator or operator cannot easily tell if a failure was caused by the LLM drafting incorrectly, or by a flawed multi-file architectural plan. | REQ-CKG-600 | Acceptance criteria includes a test where the verifier emits findings with a clear `scope: "local" | "cross_file"` tag. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):

- R3-F1: Making the verifier synchronous and gating the run is absolutely critical for the value of CKG.
- R3-F2: The aggregate mean dilution completely nullifies cross-file validation.
- R2-F2: The batch-scoped integration point is correct and must be strictly adhered to.
