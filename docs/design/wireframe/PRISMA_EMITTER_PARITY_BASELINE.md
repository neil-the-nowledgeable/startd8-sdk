# Prisma Emitter — Parity Baseline (slices 1–2)

**Date:** 2026-06-08
**Branch:** `feat/prisma-emitter`
**Measures:** the slice-1 emitter (FR-PE-1/2/3) + slice-2 semantic diff (FR-PE-4) against the **live
strtd8 contract** (`strtd8/prisma/schema.prisma`), graph built from `REQUIREMENTS_v0.5-draft.md`.

## Result

- **16 models emitted** (13 entities + 3 joins) — matches the live 16-model count.
- **0 unrenderable fields** — every doc field type is in the plain-type vocabulary.
- **10 semantic-parity drift lines** total. Categorized:

| # | Line | Category | Owner |
|---|------|----------|-------|
| 1 | `TailoredMatch.matchScore: attr @default(0) in live, not emitted` | **FR-PE-5(a)** field default | emitter/grammar (slice 3) |
| 2 | `TailoredMatch.matchScore: type Int? vs Int` | consequence of (a) — default ⇒ required | resolved by (a) |
| 3 | `TailoredMatch: @@unique([jobDescriptionId,subjectType,subjectId])` | **FR-PE-5(b)** compound unique | emitter/grammar (slice 3) |
| 4 | `TailoredMatch: @@index([jobDescriptionId])` | **FR-PE-5(b)** index | emitter/grammar (slice 3) |
| 5 | `TailoredAsset: @@index([jobDescriptionId,kind])` | **FR-PE-5(b)** index | emitter/grammar (slice 3) |
| 6 | `TailoredMatch.jobDescription: emitted, absent from live` | **FR-PE-5(c)** loose-ref (OQ-PE-3) | emitter/grammar (slice 3) |
| 7 | `JobDescription.tailoredMatchs: emitted, absent from live` | (c) reverse-list of the loose-ref | resolved by (c) |
| 8 | `ProofPoint.profile: emitted, absent from live` | doc-vs-live divergence | **app-side (FR-PE-7)** |
| 9 | `ProofPoint.profileId: emitted, absent from live` | doc-vs-live divergence | **app-side (FR-PE-7)** |
| 10 | `Profile.proofPoints: emitted, absent from live` | reverse-list of #8/#9 | **app-side (FR-PE-7)** |

## What this tells slice 3 (FR-PE-5)

The emitter/grammar worklist is **exactly three constructs**:
- **(a) field `@default`** — `TailoredMatch.matchScore Int @default(0)` (the only non-bookkeeping default).
- **(b) explicit `@@index` + compound `@@unique` on non-join entities** — `TailoredMatch` (both),
  `TailoredAsset` (`@@index`).
- **(c) loose-reference marker (OQ-PE-3 / OQ-SBE-2 seam)** — let the doc declare `jobDescriptionId`
  on `TailoredMatch` as a **non-FK scalar reference** so the emitter renders a plain scalar (no
  `@relation`, no reverse list). This also retro-tightens this session's source-bound derivation.

Closing (a)(b)(c) takes the drift from 10 → **3** (lines 8–10), which are **not emitter bugs**: the
doc declares `ProofPoint belongs to Profile` but the live schema models ownership via `ownerId`, not
an FK. That is the **app-side prerequisite** (FR-PE-7) — reconcile doc vs contract — and the diff
surfacing it is the parity oracle working as intended.

## Slice 3 result (FR-PE-5 shipped)

The three grammar constructs are implemented (`default:` Notes clause, `Indexes:`/`Unique:` lines,
the `references` loose-ref verb) and emit correctly. Re-measuring with the FR-PE-5 grammar applied
to the strtd8 entities drives parity drift **10 → 3**:

```
BEFORE: 10 drift lines
AFTER:   3 drift lines
   Profile.proofPoints: emitted, absent from live
   ProofPoint.profile:  emitted, absent from live
   ProofPoint.profileId: emitted, absent from live
```

The remaining **3 are not emitter gaps** — the doc declares `ProofPoint belongs to Profile` but the
live contract models ownership via the implicit `ownerId` bookkeeping field, not an FK. Closing them
is the **app-side FR-PE-7 reconciliation** (drop the doc relation *or* add the FK to the contract) —
an owner decision, captured here, not an emitter change. The emitter now reproduces **every Prisma
construct the live 16-model contract actually uses.**

## Positive findings

- Loose-reference **scalars already emit correctly** (a `text` field with no relationship sentence
  renders as a plain scalar). The (c) work is only about letting the doc *suppress* an unwanted
  belongs-to relation, not about rendering the scalar.
- The 6-field bookkeeping convention, join models (FK + `@relation(onDelete: Cascade)` + compound
  `@@unique`), and reverse-relation lists all reproduce the live contract exactly.
