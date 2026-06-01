# CKG Phase 1 Spike Plan — SG-1 / SG-2 / SG-3

> **Version:** 1.0 (2026-06-01)
> **Status:** Executable plan (scope only — not yet run)
> **Requirements:** [CODE_KNOWLEDGE_GRAPH_PHASE1_REQUIREMENTS.md](./CODE_KNOWLEDGE_GRAPH_PHASE1_REQUIREMENTS.md) §1a
> **Goal:** De-risk the three unvalidated Phase-1 bets *before* building the CKG, against the
> stack that actually bled (RUN_009: Next.js + TypeScript + Prisma). Each gate has a binary exit
> and a defined fallback.
> **Total time-box:** ~2–3 working days. **Workspace:** `scripts/spikes/ckg/`.
> **Output:** runnable probes + `scripts/spikes/ckg/SG_FINDINGS.md` (brief per-topic format) +
> the seed of the REQ-CKG-690 regression corpus.

---

## Gate summary

| Gate | Bet under test | Blocks | Exit = PASS when… | Fallback on FAIL |
|------|----------------|--------|-------------------|------------------|
| **SG-1** | Prisma **DMMF** gives models/fields/types/constraints as JSON, programmatically | REQ-CKG-230, checks 640/650/660 | every model/field/constraint in the fixture schema is recoverable without a live DB | parse `schema.prisma` with a small custom probe (DSL grammar); re-scope effort |
| **SG-2** | **scip-typescript** yields compiler-grade cross-file + external resolution at RUN_009 scale, readable from Python | REQ-CKG-220 acceptance, checks 610/630/670 | resolves `@/` imports + external `.d.ts` symbols on the fixture (deps installed), seconds–low-minutes, SCIP readable in Python | REQ-CKG-240: tree-sitter **draft** facts, verdicts downgrade to advisory |
| **SG-3** | A defensible rule binds **Zod ⇄ Prisma** (`CONFORMS_TO`) so field-set diffs fire | REQ-CKG-320, checks 660/670 | ProofPointSchema binds to Prisma ProofPoint with no false-binding; diff flags `claim`/`category` | require explicit annotation (e.g. zod-prisma marker) instead of inference; narrow scope |

SG-1 ∥ SG-2 run in parallel (independent). **SG-3 depends on both** (needs DMMF field sets + the Zod object's field names).

---

## Step 0 — Establish the fixture (shared substrate)

The fixture is both the spike input and the **seed of the REQ-CKG-690 regression corpus**, so do
this once, faithfully.

1. **Recover real artifacts first.** The 16 failures were on committed run-009 output:
   ```bash
   git show d5016ee --stat ; git show 87b06f9 --stat        # locate the generated app files
   ```
   If the Next.js/TS/Prisma files (`prisma/schema.prisma`, `app/api/**/route.ts`,
   `lib/ai/*.ts`, `app/proof-points/page.tsx`, `tsconfig.json`, `package.json`) are present,
   copy a minimal faithful subset into `scripts/spikes/ckg/fixture/`.
2. **Else synthesize a minimal faithful fixture** reproducing ≥1 failure per category from the
   `CROSS_FILE_CONTRACT_RESOLUTION.md` §1 table. Minimum set to cover SG-1/2/3:

   | Fixture element | Reproduces (failure #) | Category |
   |---|---|---|
   | `prisma/schema.prisma` with `AiCall{promptTokens,responseTokens}`, `ProofPoint{}` (no claim/category/body), no `id_ownerId` unique, `Artifact{}` (no dataJson) | 6, 8, 12, 13 | canonical-schema |
   | `lib/ai/service.ts` using `inputTokens`/`outputTokens` + `Anthropic.ContentBlockParam` | 11, 12 | external-API / canonical-schema |
   | `app/api/.../route.ts` importing `@/lib/prisma` (real: `@/lib/db`) + `import pino` (not in package.json) | 1, 3 | module-path / dependency |
   | `lib/schemas.ts` with `ProofPointSchema = z.object({ id, name, claim, category })` | 9, 13 | api-shape / canonical-schema |
   | `tsconfig.json` with `"@/*": ["./src/*"]` but no `src/` | 5 | project-config |
   | `package.json` omitting `pino` | 3 | dependency |

3. Record in `SG_FINDINGS.md` which path (recovered vs synthesized) and the failure→fixture map.

---

## SG-1 — Prisma DMMF access

**Goal:** prove `@prisma/internals` `getDMMF` returns the model graph as JSON, datamodel-only (no
DB), with the exact facts checks 640/650/660 need.

**Prereqs:** Node ≥18; `npm i @prisma/internals` (record installed Prisma version + license — expect Apache-2.0).

**Method — `scripts/spikes/ckg/sg1_dmmf_probe.mjs`:**
```js
import { getDMMF } from '@prisma/internals';
import { readFileSync } from 'node:fs';
const datamodel = readFileSync(process.argv[2], 'utf8');           // schema.prisma path
const { datamodel: dm } = await getDMMF({ datamodel });
console.log(JSON.stringify(dm.models.map(m => ({
  name: m.name,
  fields: m.fields.map(f => ({ name: f.name, type: f.type, kind: f.kind,
    isRequired: f.isRequired, isId: f.isId, isUnique: f.isUnique, isList: f.isList,
    relationName: f.relationName })),
  primaryKey: m.primaryKey,        // compound @@id
  uniqueIndexes: m.uniqueIndexes,  // compound @@unique
})), null, 2));
```
Run: `node sg1_dmmf_probe.mjs fixture/prisma/schema.prisma > sg1_dmmf.json`

**Assertions (each ties to a real failure):**
- `AiCall` field names == {`promptTokens`,`responseTokens`,…}; **not** `inputTokens`/`outputTokens` → enables #12.
- `ProofPoint` field set has **no** `claim`/`category`/`body` → enables #13/#15.
- `Artifact` has **no** `dataJson` → enables #6.
- `uniqueIndexes`/`primaryKey` do **not** contain `[id, ownerId]` → enables #8 (compound-key invalidity).
- Field `type`/`kind` available for type-class checks → enables Zod↔Prisma symmetry (660).

**PASS:** all five recoverable, datamodel-only, no DB connection, license-clear.
**Risks:** `getDMMF` signature drift across Prisma versions; whether it needs schema *path* vs
*string*; provider/datasource block required for parse. **Fallback:** small custom `schema.prisma`
parser (the grammar is simple) — record the added effort against REQ-CKG-230.
**Deliverable:** `sg1_dmmf_probe.mjs`, `sg1_dmmf.json`, assertions script, SG-1 findings section.
**Time-box:** ~0.5 day.

---

## SG-2 — scip-typescript operational cost + fact coverage

**Goal:** determine whether scip-typescript gives the resolution checks 610/630/670 need, at
RUN_009 scale, and whether we can read the index from Python; record the **build requirement** and
**wall-clock**.

**Prereqs:** the fixture is a real npm project (`package.json`, `tsconfig.json`).
`npm i -g @sourcegraph/scip-typescript` (or `npx`). For Python reading: generate `scip_pb2.py`
from `sourcegraph/scip/scip.proto` via `protoc`, **or** use the `scip` CLI's `print` for a first look.

**Method — `scripts/spikes/ckg/sg2_scip_run.sh`:**
```bash
set -x
# A) WITHOUT deps installed — does it resolve anything?
rm -rf node_modules
( time npx @sourcegraph/scip-typescript index --output sg2_nodeps.scip ) 2> sg2_nodeps.time

# B) WITH deps installed
npm install
( time npx @sourcegraph/scip-typescript index --output sg2_withdeps.scip ) 2> sg2_withdeps.time

scip print sg2_withdeps.scip > sg2_withdeps.txt   # human-readable first look
```
**Then `scripts/spikes/ckg/sg2_read_scip.py`** (protobuf via generated `scip_pb2`): load the index,
enumerate Documents → Occurrences/Symbols, and answer:
- Does the `@/lib/prisma` import **fail to resolve** while `@/lib/db` resolves? (→ #1 detectable)
- Does `Anthropic.ContentBlockParam` resolve to **nothing** while `TextBlockParam` resolves against the installed `.d.ts`? (→ #11/#4)
- Are **types** attached to symbols (for 660/670)? Are **route handler** signatures present?

**Capture in findings (the operational truths):**
- Requires `npm install`? (expected: yes for external/`.d.ts` resolution.)
- Wall-clock A vs B on the fixture (and, if recoverable, on the real run-009 output for scale).
- Fact coverage matrix: imports / external `.d.ts` / types / routes / object-literal property names.
- Python readability: protobuf path confirmed.

**PASS:** with deps installed, resolves cross-file imports + external symbols, seconds–low-minutes,
SCIP readable in Python.
**Risks:** needs buildable/installed project (research flagged this) → fine for *authoritative
per-batch index*, **not** the inner loop; partial/non-compiling code likely fails. SCIP may **not**
surface `z.object` property names (expression-level) — note this explicitly; it is the hinge for SG-3.
**Fallback:** REQ-CKG-240 — tree-sitter draft facts; verdicts downgrade to advisory; SCIP used only
when the target builds.
**Deliverable:** `sg2_scip_run.sh`, `sg2_read_scip.py`, `scip_pb2.py`, timing files, fact-coverage
matrix, SG-2 findings section.
**Time-box:** ~1 day (protobuf plumbing + install matrix).

---

## SG-3 — Zod ⇄ Prisma `CONFORMS_TO` inference

**Goal:** prove a defensible binding rule + field-set diff catches the canonical-schema/api-shape
drift (#7, #9, #13) — the failures that survive *even when the model has the schema* (§3 of the
cross-file doc).

**Depends on:** SG-1 (Prisma field sets) **and** SG-2 (how/whether Zod object field names are
available). **First sub-step: resolve the hinge from SG-2** — does scip-typescript emit the Zod
object's property keys?
- **If yes:** read field names from SCIP.
- **If no (likely):** extract them with a tiny **ts-morph** (or TS compiler) read of `z.object({…})`
  literals — `scripts/spikes/ckg/sg3_zod_fields.mjs`. Record this as an added extraction dependency.

**Method — `scripts/spikes/ckg/sg3_conforms_to.py`:**
1. Load DMMF models (SG-1) and Zod schemas' field sets (SCIP or ts-morph).
2. **Binding rule (test all three, report which is reliable):**
   - (a) **naming:** `<Model>Schema` ↔ `<Model>` (ProofPointSchema ↔ ProofPoint);
   - (b) **structural:** field-set Jaccard overlap ≥ threshold;
   - (c) **explicit:** a zod-prisma generator marker / import, if present.
3. Emit `CONFORMS_TO` edges; for each, **diff** Zod field set vs Prisma field set.

**Assertions:**
- `ProofPointSchema` binds to Prisma `ProofPoint` (rule a, confirmed by b); **no** false-binding to
  another model.
- Diff flags `claim`/`category` as **in Zod, not in Prisma** → catches #13 (and the #9 destructure).
- Type-class disagreement (if seeded) is reported → 660.

**PASS:** correct binding for the ProofPoint case, zero false-binding on the fixture, diff surfaces
the mismatches.
**Risks:** naming convention not universal (false negatives); structural overlap false-binds
similar models; Zod field extraction harder than expected (the SG-2 hinge). **Fallback:** require an
explicit annotation/generator convention rather than inference — narrows REQ-CKG-320 scope but stays
sound.
**Deliverable:** `sg3_conforms_to.py` (+ `sg3_zod_fields.mjs` if needed), SG-3 findings section.
**Time-box:** ~0.5–1 day (contingent on the SG-2 hinge).

---

## Sequencing

```
Step 0 (fixture, shared) ─┬─► SG-1 (DMMF)      ─┐
                          └─► SG-2 (scip-ts)   ─┴─► SG-3 (CONFORMS_TO) ─► SG_FINDINGS.md + decision
```
Run SG-1 and SG-2 in parallel. Gate SG-3 on both. Write the consolidated findings + decision last.

## Decision matrix (outcome → requirements impact)

| Outcome | Meaning | Action |
|---------|---------|--------|
| SG-1 ✅ SG-2 ✅ SG-3 ✅ | All bets hold | Build CKG Phase 1 as specified; promote fixture to REQ-CKG-690 corpus |
| SG-1 ✅ SG-2 ✅ SG-3 ⚠ | Facts fine, binding inference weak | Adopt explicit-annotation `CONFORMS_TO` (REQ-CKG-320 narrowed); proceed |
| SG-2 ❌ (needs unavailable build / unreadable) | scip-ts not viable for our targets | Trigger REQ-CKG-240 draft path; verdicts advisory until build exists; re-scope 220 |
| SG-1 ❌ | DMMF not programmatically accessible | Custom Prisma parser (added effort to 230); architecture unchanged |
| Any FAIL | — | Record fallback chosen; update REQ-CKG-* acceptance + §1a before building |

## Prerequisites & environment

- Node ≥18, npm; Prisma (`@prisma/internals`), `@sourcegraph/scip-typescript`, `scip` CLI; optional `ts-morph`.
- `protoc` + `sourcegraph/scip/scip.proto` for `scip_pb2.py` (Python SCIP reading).
- Python 3 (`python3`); keep the spike out of the SDK import path (standalone scripts).
- Record every tool's **version + license** in `SG_FINDINGS.md` (clean-room discipline, NFR-4).

## Deliverables checklist

- [ ] `scripts/spikes/ckg/fixture/` (recovered or synthesized; failure→fixture map)
- [ ] `sg1_dmmf_probe.mjs` + `sg1_dmmf.json` + assertions
- [ ] `sg2_scip_run.sh` + `sg2_read_scip.py` + `scip_pb2.py` + timing + fact-coverage matrix
- [ ] `sg3_conforms_to.py` (+ `sg3_zod_fields.mjs` if the SG-2 hinge requires it)
- [ ] `SG_FINDINGS.md` — per-gate BLUF / findings / license / confidence / gaps, plus the decision-matrix row taken
- [ ] REQ-CKG-690 corpus seed committed
