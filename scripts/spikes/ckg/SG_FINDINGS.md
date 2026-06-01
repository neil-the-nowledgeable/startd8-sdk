# CKG Phase 1 Spike — Findings (SG-1 / SG-2 / SG-3)

> **Date:** 2026-06-01
> **Target:** the REAL run-009 stack at `/Users/neilyashinsky/Documents/dev/strtd8/strtd8/`
> (Next.js + TS + Prisma; `node_modules` installed; 12 Prisma models incl. `ProofPoint`/`AiCall`).
> **Tools:** scip-typescript 0.4.0 (Apache-2.0), protobuf 6.33 + grpcio-tools (gen `scip_pb2`),
> existing SDK validators (`prisma_parser`, `prisma_zod_symmetry`). All CodeQL-independent.

## Executive summary

| Gate | Result | Evidence |
|------|--------|----------|
| **SG-1** Prisma facts | ✅ **PASS — already built** | `prisma_parser.parse_prisma_schema` parsed all 12 real models; confirmed ProofPoint lacks `claim`/`category`, AiCall has `promptTokens`/`responseTokens` (the #12/#13 drift sources). No DMMF needed. |
| **SG-3** Zod⇄Prisma CONFORMS_TO | ✅ **PASS — already built** | `prisma_zod_symmetry.evaluate_cross_file_integrity` flagged the RUN_009 #13 drift (`claim`,`category` → `field_missing_in_prisma`, error) and produced **0** violations on a coherent ProofPoint Zod. No new binder needed. |
| **SG-2** scip-typescript | ✅ **PASS — the genuine gap, delivered** | indexed the full app source (10 docs) in **7s**; resolves cross-file def→ref; resolves external `.d.ts` members with full paths (`zod .../ZodObject#extend()`, `@prisma/client`, `next`). |

**Headline:** the spike *de-scoped* Phase 1. SG-1 and SG-3 were proposed to build but are **already
shipped** (run-009 work) and verified here against the real target. SG-2 (scip-typescript) is the
**only genuine gap** and it works. CKG Phase 1 therefore collapses from "build a new substrate" to
"wire scip-typescript for the one missing Approach-B signature (f) + route-shape checks, and unify
the already-shipped checks under the Verifier."

---

## SG-1 — Prisma fact extraction  ✅ already built
**BLUF:** `src/startd8/languages/prisma_parser.py` already extracts the load-bearing facts; DMMF is
unnecessary for the contract-check use case.
- [verified] Parsed 12 models from the real `strtd8/prisma/schema.prisma`; fields/types/optionality/
  `@id`/`@unique`/compound `@@unique` all available (`sg1_sg3_confirm.py`).
- [verified] `ProofPoint` has no `claim`/`category`; `AiCall` has `promptTokens`/`responseTokens`
  (not `inputTokens`/`outputTokens`) — the exact #12/#13 drift sources.
- **Decision impact:** REQ-CKG-230/SG-1 → use existing `prisma_parser` as the CKG Prisma fact
  source. DMMF demoted to optional fidelity upgrade (field ordering, implicit back-relations), not
  Phase 1. **Confidence:** High.

## SG-3 — Zod⇄Prisma CONFORMS_TO  ✅ already built
**BLUF:** `validators/prisma_zod_symmetry.py` already binds Zod↔Prisma structurally and diffs field
sets/type classes; it catches the real run-009 drift.
- [verified] BAD Zod (ProofPointSchema with `claim`,`category`) → 2 errors,
  `field_missing_in_prisma` for both. GOOD Zod → 0 violations (no false-positive).
- [verified] Binding = suffix-normalized name (`ProofPointSchema`→`ProofPoint`), with `entity_map`
  override; field diff covers presence/absence, type-class, invented FKs.
- **Decision impact:** REQ-CKG-320/SG-3 → CONFORMS_TO + field diff already exist; do **not** rebuild.
  The SG-2-hinge worry (does SCIP expose Zod object field names?) is **moot** — the existing
  regex Zod extractor already provides them. **Confidence:** High.

## SG-2 — scip-typescript: cross-file + external `.d.ts` resolution  ✅ the real gap, delivered
**BLUF:** scip-typescript gives exactly the capabilities the existing regex validators cannot:
real cross-file symbol resolution and external-package `.d.ts` member resolution — fast, full-coverage.
- [verified] **Ops:** 7.1s wall-clock on the installed project; needs `node_modules`; indexed all
  10 real source docs (`app/**`, `lib/**`, `next-env.d.ts`). (The "55 .ts files" were historical
  `.cap-dev-pipe/pipeline-output` artifacts, not app source.) → suitable for a **per-batch
  authoritative index**, not the inner loop.
- [verified] **Cross-file resolution:** 5 symbols defined in one file and referenced from another.
- [verified] **External `.d.ts` resolution (the missing signature f):** occurrence symbols carry
  full member paths into installed packages — e.g. `scip-typescript npm zod 3.25.76
  v3/`types.d.cts`/ZodObject#extend().`, `@prisma/client 5.22.0`, `next 14.2.35 .../ProcessEnv#NODE_ENV.`
  So a referenced external member (`Anthropic.TextBlockParam`) resolves to a precise symbol; an
  invented one (`Anthropic.ContentBlockParam`) resolves to nothing → **detectable**.
- [verified] **Correction to the automated check:** scip-typescript 0.4.0 leaves the top-level
  `Index.external_symbols` table **empty**; external symbols appear as **occurrence** symbols. Read
  occurrences, not `external_symbols`. (`@anthropic-ai/sdk` = 0 only because current source doesn't
  import it yet — zod/prisma/next prove the capability.)
- **Decision impact:** REQ-CKG-220 → scip-typescript is the TS authoritative extractor; signature
  (f) (external-type-presence) is now feasible. **Confidence:** High for cross-file + external
  resolution; Medium for *enumerating all of a package's exports without a reference* (would need to
  index the `.d.ts` directly, since `external_symbols` is empty in 0.4.0).

---

## Decision matrix outcome
`SG-1 ✅ (already built) · SG-3 ✅ (already built) · SG-2 ✅` — better than the plan's best row.
**Action:** do not build DMMF or a new CONFORMS_TO binder. Reframe Phase 1 (below).

## Reframed CKG Phase 1 (post-spike)
1. **Wire scip-typescript** as a per-batch authoritative TS index (subprocess; read SCIP via
   `scip_pb2`); normalize occurrences/symbols into CKG facts.
2. **Add the one missing Approach-B signature (f)** — external-type-presence — by checking
   referenced external members resolve against the SCIP index (kills RUN_009 #11). To enumerate a
   package's valid exports, index its `.d.ts` directly (external_symbols table is empty in 0.4.0).
3. **Add route request/response-shape checks** (api-shape category #9/#15/#16) using resolved TS
   types — the other genuine gap regex can't cover.
4. **Unify** the already-shipped checks (unresolvable-import, missing-dep, Prisma field-site,
   Zod⇄Prisma symmetry, compound-key) under one Verifier surface that also emits CKG facts.
5. **Do not rebuild** SG-1/SG-3 — promote the existing validators to CKG fact sources.

## Remaining experiments (smaller than before)
- Index a package's `.d.ts` directly to enumerate valid external exports (for signature f without a reference).
- Extract `Route` request/response types from SCIP for shape checks.
- Confirm scip-typescript behavior when the project does **not** install cleanly (→ tree-sitter draft fallback, REQ-CKG-240).

## Artifacts (this dir)
`sg1_sg3_confirm.py` · `sg2_read_scip.py` · `scip.proto` + generated `scip_pb2.py` · `strtd8.scip` (index, gitignore the binary).
