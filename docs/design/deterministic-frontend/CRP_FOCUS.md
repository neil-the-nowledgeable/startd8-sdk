# CRP Focus — Deterministic Frontend Generation

Where we most need independent review input. Weight suggestions toward these. Prefer
**anchored, actionable, testable** items over generic architecture commentary.

## 1. Robustness (the renderer must not silently mis-render the schema)
The whole thesis ("invention impossible by construction") collapses if the Prisma→Zod
renderer mishandles a schema construct and emits wrong-but-plausible output. Stress the
**Prisma surface area** the plan's `SCALAR_MAP`/`FieldSpec` must cover and the failure mode
for each:
- Arrays (`String[]`, `Int[]`), enums (`enum Role {…}` → `z.enum([...])`), `@map`/`@@map`
  (DB-name vs field-name divergence), native types (`@db.VarChar`), `@default`, `@updatedAt`,
  composite types (`type` blocks), `Unsupported(...)`, `Bytes`, `Decimal`.
- Relations: 1-1, 1-n, implicit m-n, **self-relations**, relation scalar FKs (`authorId` IS a
  scalar that must be rendered; the relation `author` must be excluded — does the plan
  distinguish the FK scalar from the relation object?).
- Optionality vs nullability vs default vs list — `String?` → `.nullable()` but what about
  `String[]?`, or a field with `@default` (still required in Zod?).
- **Failure policy:** the plan says unknown type → `UnsupportedPrismaTypeError`. Is hard-fail
  right, or should it be a recorded "unrenderable field → fall back to a flagged regen item"
  so one exotic field doesn't block generating the other 11 correct models? Argue the tradeoff.

## 2. Value to the end user (the prime-contractor operator)
- Beyond killing RUN-011: what makes this *usable*? CLI ergonomics, the manifest, the diff
  report. Is `startd8 generate frontend` the right surface, or should it be a
  `plan-ingestion`/forward-manifest hook from day one?
- **Drift detection as a standalone win:** even before pipeline ownership (deferred Inc 9), a
  `--check` mode that compares the generated output against the on-disk (LLM-authored) file and
  reports divergence would deliver value immediately and turn `prisma_zod_symmetry` into a
  CI gate on real runs. Worth pulling forward?
- Does the owned/seeded split (FR-7) actually help the operator, or add ceremony? Where's the
  minimal version that still prevents the inventions?

## 3. Functional & architectural quick wins / low-hanging fruit
- What can we get nearly free by reusing `observability/artifact_generator` /
  `dashboard_creator/generator` patterns (manifest shape, emission, provenance)?
- `z.infer<typeof XSchema>` TS-type emission (FR OQ-1) — is it actually a 1-line follow-on
  worth shipping in v1 rather than deferring?
- Enum rendering and the directory-skeleton-from-manifest (RUN-013 fix) — are these smaller
  than they look and worth folding into Inc 5 rather than Inc 7?
- Is there a cheaper proof than the full strtd8 acceptance harness (Inc 5) for an earlier
  signal?

## 4. Operational enhancements
- Regeneration-on-schema-change: how is staleness detected (schema hash in the GENERATED
  header? a `--check` that exits non-zero in CI?).
- Telemetry: should the generator emit OTel spans/metrics (models rendered, fields,
  unrenderable count) consistent with the SDK's observability conventions?
- How does this compose operationally with repair-retry and Approach A — ordering, and who
  runs first in a real pipeline run?
- Idempotence/ownership enforcement: how do we *detect* an LLM (or human) editing an `owned`
  GENERATED file (the drift FR-4/NFR-4 worries about) without the deferred pipeline seam?

## 5. Sequencing / scope sanity
- Is renderer-first (Inc 1–5 before convention detection) the right order, or does FR-5
  convention detection need to come first so the renderer knows the project's alias/conventions?
- Anything in v1 scope that should be deferred, or deferred (Inc 9) that's actually cheap
  enough to pull in?
