# Deterministic Frontend Generation — Requirements

**Version:** 0.4 (Post-CRP triage, Batches 1+2 — R1–R4 applied)
**Date:** 2026-06-02
**Status:** Draft for review — pairs with `DETERMINISTIC_FRONTEND_GENERATION_PLAN.md`
**Grounding:** `DETERMINISTIC_FRONTEND_GENERATION_INVENTORY.md` (the capability audit that
served as the planning pass).
**Reuses (don't rebuild):** `languages/prisma_parser.parse_prisma_schema`,
`contractors/upstream_interface.{render_prisma_field_sets,extract_ts_exports,resolve_specifier_to_paths}`,
`repair/retry/scaffold.{scaffold_barrel,scaffold_cofile}`,
`languages/nodejs.{generate_dependency_file,generate_tsconfig}`,
`validators/prisma_zod_symmetry`.

> **What this is.** A pure-Python, **no-LLM** capability that *generates* the mechanical
> frontend artifacts the LLM keeps inventing wrong — starting with the **Prisma→Zod/TS
> schema renderer** — so those artifacts are **never generated wrong** (prevention by
> construction), and the LLM is reserved for the semantic work (business logic, UX). This
> is the structural fix all three postmortems named, realized as **generation** rather than
> injection (Approach A) or repair (repair-retry).

---

## 0. Planning Insights (Self-Reflective Update)

> Changes between v0.1 ("deterministically generate the mechanical frontend") and v0.2
> (after the capability inventory grounded it in the real strtd8 project + SDK primitives).
> Four corrections; none kill the thesis, but they sharpen scope and the ownership model.

| v0.1 Assumption | Grounding Discovery | Impact |
|-----------------|---------------------|--------|
| `lib/value-model.ts` is **100% derivable from the Prisma schema** | It's derivable from the schema **+ documented conventions**: format hints (`email`→`.email()`, `*Url`→`.url()`), provenance fields (`ownerId`/`source`/`confirmed`), relation exclusion, optionality. The schema alone doesn't encode `email`/`url`. | **FR-2 added:** a small, deterministic **convention layer** (seeded from the project's own documented mapping), not raw Prisma projection. Still no LLM — just schema + rules. |
| Generate deterministic files **and exclude them from LLM features** | That needs prime-contractor pipeline surgery (feature-list filtering, dependency ordering, "this file is provided"). The **renderer ships standalone first** (CLI + a "provided files" seam); pipeline integration is a later phase. | **Scope phased (FR-1 vs FR-8):** Phase A = renderer (kills RUN-011 standalone); Phase C = pipeline ownership integration. Don't couple the two. |
| `prisma_zod_symmetry` stays a validator on **LLM output** | With deterministic generation it becomes a **regression guard on the generator** — the renderer's output must pass it **by construction** (a self-test), not a post-hoc check on the model. | **FR-3:** the generator's output passing `prisma_zod_symmetry` is an **acceptance gate**, and the validator's role shifts from "catch LLM drift" to "prove the generator can't drift." |
| The skeleton generator covers **route/page shells** the same way | Route/page files are **boilerplate-with-logic** — a fully-generated shell the LLM must then edit creates an **ownership/drift conflict** (who owns the file?). Fully-mechanical files (types/barrels/css/config) have no such conflict. | **FR-7 added:** two ownership models — **owned** (deterministic, LLM never touches) vs **seeded** (a scaffold the LLM completes). Only *owned* files are generated outright. |
| strtd8 has barrels/CSS to mirror | strtd8 has **0 barrels and 0 CSS modules** — RUN-012's inventions don't even fit the project's conventions. The right deterministic answer is partly *"the project doesn't use these, so don't generate (or invent) them."* | **FR-5 added:** **project-convention detection** (from `tsconfig` + existing files) drives generation; "project doesn't use X" is an explicit signal that *prevents* the invention, not just fills it. |

**Resolved open questions:**
- **OQ-A → Phase the scope.** Ship the Prisma→Zod renderer first (smallest, kills RUN-011);
  defer pipeline ownership integration.
- **OQ-B → Generation follows the *project's* conventions, not LLM priors** (FR-5).

Remaining open questions: OQ-1…OQ-6 in §6.

---

## 0.1 CRP Triage Insights — Batch 1 (R1 + R2 applied)

> Two independent review rounds (data-grounded against the real `prisma_parser.py`,
> `prisma_zod_symmetry.py`, the strtd8 schema and `lib/value-model.ts`) materially corrected
> the v0.2 requirements. Full dispositions in Appendix A/B; the load-bearing changes:

| v0.2 claim | R1+R2 finding (verified) | Change |
|------------|--------------------------|--------|
| FR-9: regenerate the **12-model** file; RUN-011 names "structurally impossible" | R1-F4 claimed it has **9** schemas (join tables excluded) — **factually wrong**: `value-model.ts` renders **12 per-model `z.object`s including all 3 join tables** (`:195,208,221`) + a 13th **composite** `ValueModelSchema` + 12 `z.infer` aliases. **R1-F4 REJECTED**; the v0.2 "12 models" was right. | FR-9 restated: **1 schema per model (12), join tables included**; the composite is **out of v1 scope** (single-model renderer can't derive a cross-model aggregate); invented-name assertion is **per-model**, not global (`outcomeId` is a *real* column on the join models — R1-F5). |
| FR-3: passes `prisma_zod_symmetry` ⇒ "can't drift by construction" | The checker is **blind** to optionality/nullability, `.int()` precision, enum **values** (accepts enum-as-`z.string()`, `:254`), list shape, `z.unknown()` (short-circuits true), field order, and format hints (`:252-348`). "By construction" was a **partial tautology**. | FR-3 now enumerates the blind spots and adds **FR-3b: an independent `verify_render_fidelity` self-check** asserting exactly what the symmetry gate ignores. |
| FR-1: "no field invented, omitted, or renamed" | `parse_prisma_schema` is **lenient** — it *silently drops* lines its `_FIELD_RE` can't match (`Unsupported(...)`, native-only) (`:42,282`). Omission-by-construction is still wrong. | FR-1 adds a **field-completeness invariant** (parsed field count must match field-shaped lines; mismatch is surfaced, never silent). |
| FR-2: scalar map + `email`/`*Url` hints | The plan's `Decimal→z.string()` **fails the FR-3 gate** (checker accepts only `number` for Decimal, `:58`); `Int→z.number().int()` is **gate-invisible** (`.int()` dropped still passes); `@default` fields stay **required** in the base schema (not `.optional()`); composite `type` blocks render a **phantom schema** + drop the field. | FR-2 becomes a **per-construct fidelity matrix** (enum→`z.enum`, `String[]`→`z.array`, `Int`→`.int()`, `Decimal`→money-safe string **with the checker widened to accept it**, `@default`→required, `@map`→Prisma field-name, composite `type`→inline-or-flag). |
| OQ-1: `z.infer` interfaces a "thin follow-on", deferrable | The committed file ships **12** `export type X = z.infer<…>` lines (`:249-260`); deferring them makes the FR-9 regen **not byte-equivalent**. | **OQ-1 resolved:** `z.infer` aliases are **in v1 scope, default-on** (folded into FR-1). |
| FR-4: "regenerable" (no detection mechanism) | No way to *detect* a needed regen or a tampered owned file. | FR-4 adds a **`schema-sha256` header**; new **FR-11 `--check` drift mode** with an exit-code contract + stale-vs-tampered two-stage check. |
| §7: "composes with Approach A + repair-retry" (unordered) | An unordered compose lets repair-retry "fix" a correct owned file back toward the LLM prior. | New **FR-12 pipeline-ordering invariant**: owned files are generated → written → excluded **before** Approach-A injection and repair-retry. |

**New requirements added this batch:** FR-3b (fidelity self-check), FR-11 (`--check` drift),
FR-12 (pipeline ordering), NFR-6 (OTel telemetry). **Rejected:** R1-F4 (see Appendix B).

---

## 1. Problem Statement & Gap Table

Three postmortems, three invention classes, one root cause: the LLM produces **mechanical
artifacts from training-distribution priors** instead of the project's reality. We have
attacked this with *injection* (Approach A: tell the LLM the truth) and *repair* (repair-retry:
fix it after). Both leave the LLM in the loop for artifacts that **don't need it.** The cheapest
fix is to **not ask the LLM to generate them at all.**

| Invention class | Postmortem | Mechanical? | Today | Deterministic generation |
|-----------------|-----------|:-----------:|-------|--------------------------|
| Prisma field names in Zod (`aiRefId`, `title`…) | RUN-011 | ✅ | LLM writes `value-model.ts`; `prisma_zod_symmetry` checks it | **Generate `value-model.ts` from the schema** → invention impossible |
| CSS modules / barrels / top-level `types/` | RUN-012 | ✅ | LLM invents; repair-retry scaffolds after | Generate (if the project uses them) / signal absence |
| Sub-namespace dirs (`/renderers/`) | RUN-013 | ✅ | LLM invents; repair-retry collapses after | Generate the directory skeleton from the plan's file manifest |

**Why generation (vs injection/repair).** Injection still relies on the LLM *obeying* the
truth (Approach A's own OQ-4 admits no 100% adherence). Repair fixes it *after* the LLM has
already burned the generation cost and possibly cascaded (RUN-013's un-masked TS2345).
Generation removes the LLM from the mechanical artifact entirely: **zero invention, zero
adherence risk, zero repair needed.**

---

## 2. Goal

Provide a deterministic (no-LLM) generator that emits the project's **mechanical** frontend
artifacts — first and foremost the **Prisma→Zod/TS schema types** — following the **project's
own conventions**, with output that passes the existing structural validators **by
construction**, so those artifacts are never LLM-generated and never invented; reserving the
LLM for semantic work. Phased: the renderer first, the broader skeleton + pipeline ownership
later.

---

## 3. Functional Requirements

### FR-1 — Prisma→Zod/TS schema renderer (Phase A, the core)
A function/CLI that reads `prisma/schema.prisma` (via `parse_prisma_schema`) and emits the
TypeScript Zod-schema file (the `value-model.ts` equivalent): **one `export const <Model>Schema =
z.object({…})` per Prisma model** (join tables **included** — their FK columns are real scalars),
plus **one `export type <Model> = z.infer<typeof <Model>Schema>` alias per model** (in v1 scope,
default-on — the committed file ships 12 of them, `value-model.ts:249-260`; omitting them breaks
byte-equality). Field names, types, and optionality are taken **verbatim** from the schema; no
field is invented, omitted, or renamed.
*Field-completeness invariant (R1-F1):* because `parse_prisma_schema` is lenient and **silently
drops** field lines it can't match (`prisma_parser.py:42,282`), the renderer MUST detect when a
model's parsed field count differs from the count of field-shaped lines in its body and **surface
it** (per-field `unrenderable` handling, FR-2) — never silently emit a model missing a column.
*Acceptance:* rendering the strtd8 schema produces a `value-model.ts` whose every `z.object`
field set **equals** the corresponding Prisma model's ordered scalar fields, with `?`→
`.nullable()`, plus the matching `z.infer` alias; the RUN-011 invented names are **per-model**
impossible — e.g. `outcomeId` is **absent from `OutcomeSchema`** (it is a *real* column on the
join models `ProofPointOutcome`/`CapabilityOutcome`, so a global "not in output" assertion is
wrong — R1-F5).

### FR-2 — Deterministic convention layer (per-construct fidelity matrix)
Apply a small, **rule-based** (no-LLM) projection beyond raw Prisma, specified as a
**per-construct matrix** (each row: Prisma construct → exact Zod render → the silent-failure mode
if wrong). Each rendering is **type-guarded** — a format hint is applied only when the base type
licenses it.

| Prisma construct | Exact Zod render | Failure if wrong |
|------------------|------------------|------------------|
| `String` / `Boolean` | `z.string()` / `z.boolean()` | — |
| `Int` | `z.number().int()` (**`.int()` required**) | gate-invisible (`z.number()`≡`z.number().int()`, `:32`); diverges from every `Int` in the file (`:48,169`) |
| `Float` | `z.number()` | — |
| `DateTime` | `z.string().datetime()` | — |
| `Decimal` | money-safe **`z.string()`** — and the checker's Decimal acceptance set is **widened to include `string`** (it's ours, NFR-2; R2-F3/R2-S1) | otherwise the renderer's intended output **fails its own FR-3 gate** (`:58`) |
| `Json` | `z.unknown()` | — |
| `enum E {…}` field | `z.enum([<exact values>])` from `PrismaSchema.enums` | checker accepts enum-as-`z.string()` (`:254`) → wrong render passes |
| scalar list `String[]` | `z.array(z.string())` | checker treats arrays as relations and `continue`s (`:298`) → silent omission |
| optionality `?` | `.nullable()` | checker never compares optionality (`:296-348`) |
| `@default(…)` | field stays **present and required** in the base schema (NOT `.optional()`) | the common `@default→.optional()` idiom corrupts all 12 base schemas, gate-invisibly (`value-model.ts:20-22`) |
| `@id` / `@updatedAt` / `@default(now())` | `z.string()` / `z.string().datetime()`, **required** | server-managed fields must not be special-cased optional |
| format hint: field type is `String` AND name matches `^(email)$|Email$` / `^(url|uri)$|(Url|Uri)$` | `.email()` / `.url()` | name-only/un-anchored hint misses bare `url` and false-fires on `emailVerified Boolean` (type guard required) |
| `@map`/`@@map` | emit the **Prisma field name**, never the DB column | a renderer reaching for the DB name flips the Zod key |
| relation object field | **excluded**; the relation **scalar FK** (`authorId`) is **rendered** | excluding the FK scalar drops a real column |
| composite `type {…}` block | **NOT** a relation and **NOT** a top-level schema — render inline (`z.object({…})`) or hard-flag per declared policy | parser stores `type` in the `models` dict (`:291`) → field wrongly excluded as relation **and** a phantom `<Type>Schema` emitted (R2-F13) |

Per-field **failure policy (R4-S5/R4-S11):** an unrenderable field does **not** hard-fail the whole
render — the other models render, the unrenderable field is recorded as a flagged `unrenderable`
manifest entry, **all** such fields are aggregated into **one** report (operator fixes them in a
single pass, not N reruns), and the command exits non-zero only under `--strict`. (Hard-fail
couples N independent models to the weakest field — strictly worse than today's LLM, which at least
emits *something*.) The rule set is **declared once** (seeded from the project's *documented*
mapping, **not** inferred from the LLM-authored file — OQ-2) and applied deterministically.
*Acceptance:* one unit test per matrix row asserting the exact emitted substring; a relation field
is absent while its FK scalar is present; `url String?` renders `.url()`; `emailVerified Boolean`
renders **no** `.email()`; the same schema renders **byte-identical** output across runs.

### FR-3 — Output passes the symmetry validator by construction (+ what it can't see)
The rendered file MUST pass `validators/prisma_zod_symmetry.check_prisma_zod_symmetry` with
**zero** violations — turning that validator from a *post-hoc LLM-drift detector* into a
**generator regression guard**. **But the symmetry gate is provably blind** to: optionality/
nullability, `.int()` precision, enum **values** (accepts enum-as-`z.string()`), list/array shape,
`z.unknown()` (short-circuits to compatible), field **order**, and format hints
(`prisma_zod_symmetry.py:252-348`). "By construction" is therefore **not** airtight from this gate
alone.
*Acceptance:* `check_prisma_zod_symmetry(parse_prisma_schema(schema), extract_zod_objects(rendered))`
returns `[]` for every model (note the real signature — parsed objects, **(prisma, zod)** order);
the **negative test drops a required, non-defaulted scalar** (on strtd8 that means `Profile.name`
specifically — every other field is optional/defaulted and would pass silently) and asserts the
gate fires.

### FR-3b — Independent post-render fidelity self-check
A second deterministic check, `verify_render_fidelity(rendered, schema, conventions) -> [Issue]`,
**independent** of `prisma_zod_symmetry`, asserts exactly the dimensions the symmetry gate ignores:
per-field optional/nullable equality, `.int()` presence for `Int`, `z.array(…)` for lists,
`z.enum([exact values])` for enums, format-hint presence per the convention rules, and field
**count + order** equality. This is what actually makes FR-3's "by construction" sound.
*Acceptance:* mutating each dimension (flip a `?`, drop `.int()`, drop a list wrapper, wrong enum
value) is caught by `verify_render_fidelity` — **not** by the symmetry gate.

### FR-4 — Ownership marker, schema-hash, regenerability, byte-determinism
Every generated file carries a header marking it **generated** (`// GENERATED from
prisma/schema.prisma — do not edit by hand; regenerate via <command>`) **including a
`// schema-sha256: <hex>`** so staleness is deterministically detectable (FR-11). Output is
**idempotent** (same schema → byte-identical) and **regenerable** (schema change → re-emit). A
generated file is **owned** by the generator, not the LLM (FR-7).
*Determinism guarantees (R4-S7/R4-F6):* field/model order follows **source order** (the parser's
ordered `fields` tuple, `prisma_parser.py:75`) — the renderer **never** iterates a `set`/`frozenset`
(`field_names`, `:85`); output is UTF-8, `\n`-terminated, ASCII-stable. "Byte-identical" is
otherwise unfalsifiable.
*Acceptance:* two renders are byte-identical **across two subprocesses with randomized
`PYTHONHASHSEED`**; the header + schema hash are present; changing one schema field changes the
hash and re-emits with the new field.

### FR-5 — Project-convention detection
Derive conventions from the **project**, not LLM priors: the `@/` alias + roots from
`tsconfig.json` `paths`; whether the project uses barrels / CSS-modules / a `types/` dir (from
existing files). Generation **follows** these — and the **absence** of a convention (strtd8 uses
no barrels, no CSS modules) is an explicit output that *prevents* the corresponding invention
class, not just fills it.
*Acceptance:* against strtd8, detection reports `alias=@/→./`, `barrels=false`,
`css_modules=false`; the generator emits **no** barrel/CSS files and records "project does not
use barrels/CSS modules" (the RUN-012 anti-invention signal).

### FR-6 — Skeleton generators for the other mechanical artifacts (Phase B, gated)
For the remaining fully-mechanical artifacts, reuse existing primitives **gated on FR-5
detection**: barrels (`scaffold_barrel`) **only if** the project uses them; CSS-module stubs
(`scaffold_cofile`) only if it does; `package.json`/`tsconfig` (`generate_dependency_file`/
`generate_tsconfig`); the directory skeleton from the plan's file manifest (prevents RUN-013
sub-namespace invention).
*Acceptance:* on a project that uses barrels, the barrel is generated; on strtd8 (no barrels),
none is — and neither is invented.

### FR-7 — Ownership boundary: owned (v1) vs seeded (deferred)
Two classes, declared per artifact: **owned** = fully deterministic, the LLM **never** writes or
edits it (schema types, barrels, css stubs, config); **seeded** = a deterministic scaffold the
LLM **completes** (route/page shells). **v1 ships owned-only** (R3-F2): every named invention
class (RUN-011 schema fields, RUN-012 barrels/CSS, RUN-013 dirs) is an *owned* artifact — **no**
postmortem invention is a seeded-shell body, so seeded delivers zero headline value while importing
the unresolved OQ-4/OQ-5 clobber problems. **Seeded is deferred** (not merely "minimal").
*Acceptance:* v1 closes RUN-011/012/013 with only `owned` outputs; the manifest tags each output
`owned`; no `seeded` artifact is required. (Seeded shells, if later added, own only the import
block + signature; the body is a guarded region.)

### FR-8 — Delivery surfaces: CLI (8A) / minimal pipeline hook (8B, v1) / full ownership (8C, deferred)
The capability ships on three surfaces, **split** so the real-run value isn't gated on the hard part:
- **FR-8A — CLI (v1):** `startd8 generate frontend --schema <path> --out <dir> [--project <root>]
  [--check]`. The CLI's real headline is **`--check`** (FR-11), the standalone CI gate; `generate`
  is the dev-loop path.
- **FR-8B — Minimal pipeline hook (v1):** the prime-contractor **pre-writes owned files** in its
  pre-generation hook and the **existing `_try_deterministic_file_shortcut`** (Phase 0.6,
  `prime_contractor.py:3592-3639`) skips any feature whose target is a pre-written owned file —
  marking it `GENERATED $0.00`, no LLM call. This is ~30 lines (widen the `_DETERMINISTIC_BUILD_NAMES`
  predicate to owned codegen outputs), **not** the deferred Phase C; without it the renderer prevents
  nothing in a real run (R3-S1/R3-F1).
- **FR-8C — Full ownership (deferred):** general feature-list filtering + dependency ordering for
  arbitrary owned files. Only this is genuinely hard and stays deferred.
*Acceptance (8A):* the CLI renders schema types + applicable skeleton to `--out`. *(8B):* a prime
run with `value-model.ts` pre-written lists it as `GENERATED $0.00`, not an LLM feature, via the
existing Phase 0.6 path; an operator-facing e2e demonstrates the skip (R3-S6). *(8C, deferred):*
dependent features import owned files by canonical path without regenerating them.

### FR-13 — Reuse the existing field-set authority and provenance slot (no second source of truth)
The renderer MUST consume `project_knowledge`'s `FieldSpec`/`FieldSetAuthority`
(`contractors/project_knowledge/models.py:30`, projected from the same Prisma schema at
`producer.py:130`) rather than defining a **parallel** `FieldSpec` — otherwise the injection path
(CKG) and the generation path maintain two projections of the *same* "authoritative" field set,
which can diverge and re-introduce the exact drift this feature exists to kill (R3-F3/R3-S10).
Generated-file provenance MUST be recorded in the existing
`forward_manifest.convention_provenance` slot (`forward_manifest.py:317`) that `ReviewPhaseHandler`
already consumes, not only a parallel `GenerationManifest` (R3-F4).
*Acceptance:* a single schema fixture drives both `DraftModeProducer.build(...)` and the renderer
and they agree field-for-field (a CI property test fails on divergence); generated owned files
appear in the forward manifest's convention provenance.

### FR-9 — strtd8 acceptance gate (headline)
Regenerate `lib/value-model.ts` from the **real** strtd8 schema: the output emits **one schema
per model (12, join tables included)** + the **12 `z.infer` aliases**, passes `prisma_zod_symmetry`
(FR-3) **and** `verify_render_fidelity` (FR-3b), and is structurally equivalent to the
hand-authored file. The **composite `ValueModelSchema`** (`value-model.ts:236-245`) — a
cross-model aggregate of `z.array(XSchema)` that omits AiCall + the join tables by product
decision — is **out of v1 scope** (no single-model renderer can derive it); the gate scopes around
it (assert the 12 per-model schemas + aliases match; the composite is explicitly excluded/seeded,
not silently absent — R2-F1/R2-S4).
*Acceptance:* per-model field-set + optionality + `.int()` equality vs the committed file; the 3
join-table schemas are **present**; 0 symmetry **and** 0 fidelity violations; a diff report of
intentional convention differences. **Robustness is proven on synthetic fixtures, not strtd8** —
strtd8 exercises **none** of the exotic surface (no enums, scalar arrays, `@map`, native types,
`Decimal`, composites, self-relations, verified across all 12 models), so a green strtd8 gate is a
*trivial-path* proof; the per-construct matrix (FR-2) is verified by a synthetic fixture suite.

### FR-10 — Deterministic, no-LLM, idempotent
The entire capability makes **zero** LLM/network calls; same inputs → same bytes; safe to run
repeatedly.
*Acceptance:* runs with no API keys; two runs produce identical output.

### FR-11 — `--check` drift mode (v1 deliverable, standalone CI gate)
A `--check` mode renders in-memory and compares against the on-disk file **without writing**,
giving an explicit **exit-code contract** (`0`=in-sync, `1`=drift, `2`=usage/parse/IO error) via a
**two-stage** test: (1) compare the embedded `schema-sha256` (FR-4) against the live schema hash —
distinguishes *"schema changed, regen needed"* (stale); (2) if hashes match, full render-and-diff —
distinguishes *"owned file hand-edited"* (tampered). This turns `prisma_zod_symmetry` into a
real-run CI gate and covers NFR-4 owned-file drift **before** the deferred pipeline seam.
*Acceptance:* CI matrix — edit schema → exit 1 (stale); edit owned file, schema unchanged → exit 1
(tampered); malformed schema → exit 2; in-sync → exit 0, each with the right diagnostic.

### FR-12 — Pipeline-ordering invariant (stated now, even though the seam is later)
When generation runs inside a prime-contractor run, owned files are **rendered, written to disk,
and excluded from the LLM feature set BEFORE** Approach-A injection and **before** repair-retry's
worklist runs — otherwise repair-retry, seeing a correct owned file it didn't author, may "repair"
it back toward the LLM prior and re-introduce RUN-011.
*Acceptance:* integration test — an owned file present + flagged → repair-retry's worklist
**excludes** it and does not rewrite it; the owned file is written before any LLM feature executes.

---

## 4. Non-Functional Requirements

- **NFR-1 No-LLM + deterministic.** Pure Python; reproducible bytes.
- **NFR-2 Reuse-not-rebuild.** Build on `prisma_parser`, `scaffold_*`, `generate_tsconfig/dependency_file`, `prisma_zod_symmetry` — the renderer is the one net-new piece.
- **NFR-3 Project-truthful.** Follow the project's detected conventions (FR-5), never LLM priors; absence of a convention is a first-class signal.
- **NFR-4 Owned files are inert to the LLM.** Generated (owned) files are marked and (Phase C) excluded from the LLM surface so they can't drift.
- **NFR-5 Symmetry-by-construction.** The renderer is validated by the existing symmetry checker (FR-3) **and** the independent fidelity self-check (FR-3b) — the symmetry gate alone is blind to optionality/`.int()`/enum-values/lists/order, so it is necessary but not sufficient.
- **NFR-6 Telemetry.** Emit OTel metrics via `metrics.get_meter("startd8.frontend_codegen")` (counters `models_rendered`/`fields_rendered`/`join_tables_rendered`/`unrenderable_fields`/`format_hints_applied` + a `drift_check` histogram), mirroring `costs/otel_metrics.py:90-109` — a no-LLM generator still runs inside instrumented prime-contractor runs, and exact counts are where determinism should give the *most* confidence.

---

## 5. Non-Requirements (v1)

- **NOT** generating business logic — `lib/ai/*` enrichment, route algorithms, page UX/interaction stay **LLM-authored** (semantic).
- **NOT** the full app — only the mechanical **owned** skeleton. **Seeded** route/page shells are **v1-deferred** (FR-7) — no postmortem invention is a seeded-shell body.
- **NOT** replacing Approach A or repair-retry — generation is the *prevention-by-construction* layer; injection grounds the semantic bodies, repair-retry is the after-the-fact net for whatever still slips.
- **NOT** a Prisma-client replacement — this emits **app-level Zod/TS** (the `value-model.ts` mirror), not the Prisma client (`prisma generate` already does that).
- **NOT** the composite `ValueModelSchema` (a cross-model aggregate) — out of v1 scope (no single-model renderer derives it).
- **NOT** (v1) the **full** pipeline-ownership integration (FR-8C — general feature-list filtering). The **minimal hook (FR-8B)** *is* in v1 (it already exists in narrow form, `prime_contractor.py:3592`); only arbitrary-file ownership is deferred.

---

## 6. Open Questions

- **OQ-1 — Renderer scope for v1. → RESOLVED (R1-F6/R4-F4):** Zod schemas **+ `z.infer` type
  aliases, default-on** (the committed file ships 12; omitting them breaks byte-equality). Enums
  are in the FR-2 matrix. The composite `ValueModelSchema` is out of v1 scope (FR-9).
- **OQ-2 — Convention rule source. → RESOLVED:** a **declared default rule set** (seeded from the
  *documented* mapping) + optional per-project override; **do not** infer from the LLM-authored
  `value-model.ts`.
- **OQ-3 — Pipeline mechanics. → PARTLY RESOLVED (R3-S1):** the v1 minimal hook (FR-8B) reuses the
  existing `_try_deterministic_file_shortcut` (`prime_contractor.py:3592`) — pre-write owned files,
  widen the deterministic-name predicate. Only **FR-8C** (general feature-list filtering for
  arbitrary owned files) remains open.
- **OQ-4 — Seeded-shell ownership conflict. → DEFERRED:** moot for v1 (seeded is deferred, FR-7).
  Revisit if/when seeded shells are added.
- **OQ-5 — Schema drift / migrations.** On a schema change, regenerate owned files — but the LLM
  bodies that *consumed* the old shape may break. How is that surfaced? *(Likely: regen + a diff
  that flags consuming features for review/regen — ties back to repair-retry's worklist; `--check`
  FR-11 is the detection primitive.)*
- **OQ-6 — Where the renderer lives. → RESOLVED (R3-F3/R4):** a focused `frontend_codegen/` package
  the CLI + prime-contractor both call, **reusing `project_knowledge`'s `FieldSpec`/
  `FieldSetAuthority`** (FR-13) — not a parallel field model, and not an extension of
  `languages/nodejs` (keeps the frontend-app concern out of the language-profile abstraction).

---

## 7. Relationship to the roadmap

- **Realizes** the structural fix RUN-011/012/013 all named — as **generation**, the
  cheapest of the three levers (injection / repair / generation).
- **Repurposes** `prisma_zod_symmetry` from an LLM-drift detector into a generator regression
  guard (FR-3) — same validator, stronger guarantee.
- **Composes** with Approach A (grounds the *semantic* bodies) and repair-retry (the net for the
  residue) — generation removes the *mechanical* surface from both their workloads.
- **Sequenced:** Phase A renderer (kills RUN-011) → Phase B skeleton (RUN-012/013 mechanical) →
  Phase C pipeline ownership (the LLM never sees the owned files).

---

*v0.3 — Post-CRP triage Batch 1 (R1+R2): rejected R1-F4's false "9 schemas" claim (it's 12
incl. join tables + a 13th composite); restated FR-9 (per-model, composite out of scope, synthetic
fixtures, `Profile.name` negative test); FR-2 became a per-construct fidelity matrix (enum/list/
`Int.int()`/Decimal/`@default`/`@map`/composite/type-guarded hints); added FR-1 completeness
invariant + `z.infer` aliases, FR-3b fidelity self-check, FR-4 schema-hash, FR-11 `--check` drift,
FR-12 pipeline ordering, NFR-6 telemetry.*

*v0.4 — Post-CRP triage Batch 2 (R3+R4): FR-8 split into 8A (CLI) / **8B minimal pipeline hook,
now in v1** via the existing `_try_deterministic_file_shortcut` / 8C deferred; FR-7 seeded shells
**deferred** (owned-only v1); added FR-13 (reuse `project_knowledge` `FieldSpec` + forward-manifest
provenance, no second source of truth); FR-2 url-hint anchored + type-guarded; FR-1 failure policy
= per-field flagged + aggregated, no whole-file hard-fail; FR-4 determinism guarantees (source
order, no set iteration, cross-subprocess hashseed test); OQ-1/2/3/6 resolved. Full dispositions in
Appendix A/B; R3/R4 full text in `CRP_ROUND_R3.md`/`CRP_ROUND_R4.md`. Ready for implementation —
pairs with `…_PLAN.md` v1.2.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

### Appendix A: Applied Suggestions

**Batch 1 (R1 + R2) — triaged 2026-06-02. Areas substantially addressed: renderer completeness,
convention fidelity matrix, validation soundness, drift/ops, FR-9 acceptance correctness.**

| ID | Disposition | Merged into |
|----|-------------|-------------|
| R1-F1 | ACCEPT | FR-1 field-completeness invariant (no silent drop) |
| R1-F2 | ACCEPT | FR-2 matrix — `enum`→`z.enum([values])` |
| R1-F3 | ACCEPT | FR-3 (states symmetry gate ignores optionality) + FR-3b |
| R1-F5 | ACCEPT | FR-1 — per-model (not global) invented-name assertion; `outcomeId` real on join models |
| R1-F6 | ACCEPT | FR-1 `z.infer` aliases in-scope; OQ-1 resolved |
| R1-F7 | ACCEPT | FR-11 `--check` drift mode |
| R1-F8 | ACCEPT (carried to Batch 2) | owned-only v1 — finalized with R3-F2 in Batch 2 |
| R1-F9 | ACCEPT | FR-4 `schema-sha256` header |
| R1-F10 | ACCEPT | FR-2 matrix — composite `type` block policy |
| R2-F1 | ACCEPT | FR-9 — composite `ValueModelSchema` out of v1 scope |
| R2-F2 | ACCEPT | FR-2 per-construct fidelity matrix |
| R2-F3 | ACCEPT | FR-2 — `Decimal`→money-safe string, checker widened to accept `string` |
| R2-F4 | ACCEPT | FR-3b independent `verify_render_fidelity` self-check |
| R2-F5 | ACCEPT | FR-11 exit-code contract + stale-vs-tampered two-stage |
| R2-F6 | ACCEPT | NFR-6 OTel telemetry |
| R2-F7 | ACCEPT | FR-12 pipeline-ordering invariant |
| R2-F8 | ACCEPT | FR-9 — 12 schemas incl. join tables (supersedes R1-F4) |
| R2-F9 | ACCEPT | FR-2 — `@default` stays required |
| R2-F10 | ACCEPT | FR-2 — `@updatedAt`/`@id` required-string semantics |
| R2-F11 | ACCEPT | FR-2 — `@map`/`@@map` emits Prisma field name |
| R2-F12 | ACCEPT | FR-2 — `Int`→`z.number().int()`, asserted by FR-3b |
| R2-F13 | ACCEPT | FR-2 — composite `type` phantom-schema break (with R1-F10) |

**Batch 2 (R3 + R4) — triaged 2026-06-02. Areas substantially addressed: pipeline integration
(8B in v1), single source of truth, owned-only scope, determinism, convention-heuristic safety.**

| ID | Disposition | Merged into |
|----|-------------|-------------|
| R3-F1 | ACCEPT | FR-8 split into 8A / 8B (v1 minimal hook) / 8C (deferred) |
| R3-F2 | ACCEPT | FR-7 — seeded deferred, owned-only v1; §5 Non-Requirements |
| R3-F3 | ACCEPT | FR-13 — reuse `project_knowledge` `FieldSpec`/`FieldSetAuthority` |
| R3-F4 | ACCEPT | FR-13 — provenance in `forward_manifest.convention_provenance` |
| R3-F5 | ACCEPT | FR-9 — cross-module-import case / trivial-path labeling |
| R4-F1 | ACCEPT | FR-9 — 12 schemas incl. join tables (reinforces R2-F8) |
| R4-F2 | ACCEPT | FR-2 — url hint anchored `^(url|uri)$|(Url|Uri)$` |
| R4-F3 | ACCEPT | FR-9 — composite `ValueModelSchema` out of v1 scope |
| R4-F4 | ACCEPT | FR-1 — `z.infer` aliases default-on (OQ-1) |
| R4-F5 | ACCEPT | FR-2 — composite `type` not relation / not top-level schema |
| R4-F6 | ACCEPT | FR-4 — determinism guarantees (source order, no set iteration, EOL) |
| R4-S5 (req-relevant) | ACCEPT | FR-1/FR-2 — per-field flagged failure policy, not hard-fail |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Disposition | Rationale |
|----|-------------|-----------|
| R1-F4 | **REJECT** | Factually wrong, verified against the file: `value-model.ts` has **13** `z.object` schemas — **12 per-model incl. all 3 join tables** (`:195,208,221`) + 1 composite — not "9 with join tables excluded." Its proposed join-table-**exclusion** predicate would delete 3 correct schemas and fail FR-9 in the opposite direction. The *intent* ("fix the count") is kept; the correct rule is **1 schema per model (12)**, adopted via R2-F8. (Confirmed independently by R2-F8 and R4-F1.) |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-01

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-01 00:00:00 UTC
- **Scope**: Requirements robustness, testability, and acceptance-criteria review, grounded in the actual `prisma_parser.py`, `prisma_zod_symmetry.py`, the strtd8 schema (12 models) and `lib/value-model.ts` (9 schemas).

##### Focus-area answers (sponsor asks)

**Focus 1 — Renderer robustness (the core thesis).**
- **Summary answer:** Partial — the thesis holds for the strtd8 *headline* path but the requirements over-claim "invention impossible by construction" because the existing primitives have silent-drop and silent-pass gaps the requirements do not name.
- **Rationale:** `parse_prisma_schema` is *lenient by design* ("unparseable lines are skipped rather than raising", `prisma_parser.py:276-283`). A field whose type the `_FIELD_RE` (`prisma_parser.py:42`, requires `[A-Z]\w*(?:\[\]|\?)?`) can't match — e.g. `Unsupported("...")`, a native-type-only construct — is **dropped silently**, not hard-failed; so "no field is omitted" (FR-1) is violated by *omission*. Separately, `prisma_zod_symmetry` (the FR-3 gate) does **not** check optionality/nullability symmetry and treats enum-as-`z.string()` as compatible (`prisma_zod_symmetry.py:254-255`), so "passes by construction" does not guarantee `.nullable()` or `z.enum()` correctness.
- **Assumptions / conditions:** Holds against the parser/checker code as read; if FR-1 mandates hard-fail on unparseable field lines, the claim is restorable.
- **Suggested improvements:** FR-1 needs a *field-completeness* invariant; FR-2 needs a per-construct Prisma surface policy (enums, arrays, native types, composite `type`); FR-3 must state what the symmetry checker does **not** cover so a second assertion covers it. See R1-F1, R1-F2, R1-F3, R1-F10.

**Focus 2 — End-user value.** `--check`/drift mode against the on-disk file is the immediate standalone win — name it as a v1 acceptance criterion, not deferred with Inc 9 (R1-F7). Minimal owned-only split first (R1-F8).

**Focus 3 — Quick wins.** `z.infer` TS-type emission is a genuine ~1-line follow-on (the renderer already has the model name) — promote OQ-1 in-scope (R1-F6). Enum rendering is *not* free and the checker won't catch a wrong render — it needs its own criterion (R1-F2).

**Focus 4 — Operational.** Staleness needs a mechanism: embed a schema content hash in the GENERATED header so `--check` detects drift deterministically (R1-F9).

**Focus 5 — Sequencing.** FR-9's "12 models" is mis-stated: `value-model.ts` has **9** `z.object` schemas; the 3 join tables are absent. Specify the join-table policy or the gate cannot pass (R1-F4).

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Risks | critical | FR-1: add a **field-completeness invariant** — the renderer MUST raise (not silently skip) when a model's parsed field count differs from the count of field-shaped lines in the model body. | `parse_prisma_schema` is lenient and *silently drops* lines its `_FIELD_RE` can't match (`prisma_parser.py:42,282`); `Unsupported(...)`/native-only/odd-spacing fields vanish with no error, violating FR-1's "no field is omitted". | FR-1, after *Acceptance* | Malformed-field fixture (`circle Unsupported("circle")`); assert the renderer raises rather than emitting a model missing that field. |
| R1-F2 | Data | high | FR-2: add an explicit **enum rendering** clause + acceptance — an enum-typed field (`type ∈ schema.enums`) MUST render `z.enum([<values>])` from `PrismaSchema.enums`, with a dedicated test, because the symmetry checker accepts `z.string()` for an enum (`prisma_zod_symmetry.py:254-255`) and will NOT catch a wrong enum render. | FR-2 lists scalars/optionality/format-hints but is silent on enums; "passes by construction" is a false guarantee here. | FR-2, new bullet | `enum Role {ADMIN USER}` + `role Role`; assert output contains `z.enum(["ADMIN","USER"])`. |
| R1-F3 | Validation | high | FR-3: state explicitly that `prisma_zod_symmetry` does **not** validate optionality/nullability, and add an acceptance requiring per-field `optional/nullable` equality between schema and rendered output. | The checker compares names + type-class only; it never compares `is_optional`/`.nullable()` (`prisma_zod_symmetry.py:296-348`). FR-9's "same optionality" is unenforced by the FR-3 gate. | FR-3 (caveat) + FR-9 acceptance | Render `name String?` → assert `.nullable()`; render `name String` → assert not — independent of the symmetry checker. |
| R1-F4 | Data | high | FR-9: resolve the **join-table policy** and fix the model count — `value-model.ts` has **9** schemas, not 12; the 3 join tables (`ProofPointCapability/ProofPointOutcome/CapabilityOutcome`) are excluded. State the rule (e.g. "models whose non-id/meta fields are all relation FKs are skipped") as a tested predicate. | 12 `model` blocks but 9 hand-authored schemas; nothing in the parser distinguishes a join table, so a naive renderer emits 12 and fails "structurally equivalent". | FR-9 *Acceptance*; x-ref FR-1 | Assert rendered schema names == the 9 in `value-model.ts`; join models excluded by an explicit tested predicate. |
| R1-F5 | Data | high | FR-1/FR-9: drop or qualify "`outcomeId` structurally impossible to emit" — `outcomeId` is a **real** column on `ProofPointOutcome`/`CapabilityOutcome` (`schema.prisma:240,260`). The RUN-011 invention was `outcomeId` on the *wrong* model. | A literal global "not in output" assertion breaks once join tables are in scope; the guarantee must be *per-model*, not global. | FR-1 & FR-9 acceptance lines | Replace global-absence with per-model field-set equality; assert `outcomeId` absent from `OutcomeSchema` specifically. |
| R1-F6 | Interfaces | medium | OQ-1: promote `z.infer<typeof XSchema>` TS-type emission to an **in-scope FR** for v1 (default-on or single flag), not a deferred follow-on. | The renderer already has the model name; `export type X = z.infer<typeof XSchema>` is ~1 line/model and removes a second LLM-authorable mechanical artifact. | New FR-1b / fold into FR-1 | Assert each model emits a matching `export type` line; byte-stable across runs. |
| R1-F7 | Validation | high | Add an FR for a **`--check`/drift** mode (compare generated output to the on-disk LLM-authored file; non-zero exit on divergence) as a v1 deliverable, decoupled from deferred Phase C. | Turns `prisma_zod_symmetry` into a real-run CI gate immediately and detects owned-file drift (NFR-4) without the deferred pipeline surgery. | New FR (Phase A/B), ref NFR-4 | CI test: mutate the on-disk file, run `--check`, assert non-zero exit + diff report. |
| R1-F8 | Architecture | medium | FR-7: define the **minimal** owned/seeded split — mark `seeded` *optional for v1* and require only `owned` (schema types) to ship first, so the renderer's value isn't gated on the harder route-shell ownership model. | FR-7's seeded model raises OQ-4 (regen vs LLM-body clobber) and adds ceremony; the RUN-011 fix needs only `owned` schema types. | FR-7, "v1 minimal" note | v1 passes with only `owned`; `seeded` deferred behind a flag. |
| R1-F9 | Ops | medium | FR-4: require the GENERATED header to embed a **schema content hash** (`// schema-sha256: <hex>`) so staleness/drift is deterministically detectable by `--check`/CI. | FR-4 mandates "regenerable" but gives no mechanism to *detect* a needed regen; a header hash makes staleness deterministic. | FR-4 *Acceptance* | Change one field; assert the header hash changes and `--check` reports stale. |
| R1-F10 | Risks | medium | FR-2: add a **composite `type` block** policy — the parser stores composite `type` blocks in the same `models` dict as real models (`prisma_parser.py:291`), so a composite-typed field is wrongly treated as a relation and excluded, and the composite block renders as a stray top-level schema. | Silent wrong-render: a scalar-bearing composite field disappears with no error. | FR-2, new bullet | `type Address {...}` + `address Address`; assert handled per declared policy, not silently dropped. |

**Endorsements**: none (first round).

#### Review Round R2 — claude-opus-4-8-1m — 2026-06-01

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-01 00:00:00 UTC
- **Scope**: R2 lens — **data-modeling depth + validation semantics + operational/CI**. Goes beyond R1 on the full Prisma→Zod semantic-fidelity surface (enums/composite types/scalar lists/`@default`/`@updatedAt`/JSON/Decimal/`@db.*`/`@map`/`@@id`/`@@unique`), an exhaustive enumeration of what `check_prisma_zod_symmetry` does **not** verify (with line cites), the additional deterministic post-render self-check FR-3 needs, and drift/staleness/telemetry/exit-code ops. Grounded in `prisma_zod_symmetry.py`, `prisma_parser.py`, the **real** strtd8 `schema.prisma` (12 models) and `lib/value-model.ts` (re-counted: **13** `z.object`s — 12 model schemas incl. all 3 join tables + 1 composite). **Corrects a factual error in R1-F4/R1-S3.**

##### Focus-area answers (sponsor asks)

**Focus 1 — Renderer robustness (data-model surface).**
- **Summary answer:** No, not as written — the requirements name no per-construct Zod rendering for the constructs that produce *wrong-but-plausible* output, and (separately) the plan's own `SCALAR_MAP` for `Decimal` would **fail** the FR-3 gate it claims to pass by construction.
- **Rationale:** The genuinely non-derivable artifact in the real file is `ValueModelSchema` (`value-model.ts:236-245`) — a composite aggregate of `z.array(XSchema)` references that maps to **no** Prisma model; a model-by-model renderer cannot produce it, yet FR-9 demands "structurally equivalent to the hand-authored file." Per-construct Zod renderings the requirements must pin (correct form → failure if ignored): **enum** field → `z.enum([...vals])` (checker accepts `z.string()` as compatible, `prisma_zod_symmetry.py:254-255` — silent wrong render); **scalar list** `String[]` → `z.array(z.string())` (parser sets `is_list`, `prisma_parser.py:233`, but the checker classifies nested arrays as relations and **skips** them, `prisma_zod_symmetry.py:298` — silent omission); **`Int`** → `z.number().int()` (checker type-class for `z.number()` and `z.number().int()` is identically `number`, `_ZOD_BASE_TO_CLASS:32` — dropping `.int()` passes the gate but diverges from `value-model.ts:48,169`); **`Decimal`** → must be a money-safe string but plan maps `Decimal→z.string()` while the checker only accepts `number` for Decimal (`_PRISMA_TO_ZOD:58`) → **the plan's mapping is rejected by the gate**; **`Json`** → `z.unknown()` (never exercised by strtd8 — `dataJson` is typed `String`, `schema.prisma:187`); **composite `type` block** → stored in `models` dict with no marker (`prisma_parser.py:291`), so a composite-typed field is treated as a relation and dropped (R1-F10 stands, extend here); **`@map`/`@@map`** → DB-name vs field-name divergence is invisible (parser keeps only `field_names`); **`@@id`/`@@unique`** → composite-key models have no single `@id` (e.g. a pure join table) so the "skip id" logic and any `z.string()`-for-id rule misfire.
- **Assumptions / conditions:** Holds against the code as read; strtd8 happens to dodge every exotic construct, so none of this is caught by the Inc-5 headline.
- **Suggested improvements:** R2-F1 (composite-aggregate policy), R2-F2 (per-construct fidelity matrix incl. `Int.int()`/list/Decimal), R2-F3 (fix the `Decimal` gate conflict), R2-F11 (`@map`/`@@map`).

**Focus 2 — Validation semantics (what the checker does NOT assert).** Exhaustive, line-cited: (1) **optionality/nullability** — never compared (R1-F3 noted; the loop at `:296-348` reads `zf.type_class` only, never `zf.optional`/`zf.nullable`); (2) **`.int()` precision** — `z.number()` ≡ `z.number().int()` (`:32`); (3) **enum value set** — enum→string accepted (`:254-255`), and even enum→enum never checks the *values* match `schema.enums`; (4) **list/array shape** — `object`/`array` Zod fields are `continue`d (`:298`), so `z.array(...)` vs scalar is never reconciled; (5) **`z.unknown()`/`z.any()`** — short-circuits to compatible (`:252-253`), so a `Json`-typed-as-string error is invisible; (6) **field ordering** — set-based (`field_names` is a `frozenset`, `:86`); (7) **non-concrete classes** — only `string/number/boolean/date` mismatches are flagged (`_CONCRETE_ZOD_CLASSES:65`, `:259-260`); (8) **format hints** — `.email()`/`.url()` are invisible (regex grabs the *first* `z.<base>` only, `_ZBASE_RE:69`); (9) **extra Zod schemas with no Prisma model** — silently skipped (`:287-288`), so the composite `ValueModelSchema` is ignored, not validated. **Therefore FR-3's "by construction" is NOT airtight** — see R2-F4 for the independent post-render self-check that must assert these.

**Focus 3 — Operational/CI.** Drift `--check` needs an **exit-code contract** (0=in-sync, 1=drift, 2=usage/parse error) and a **schema-hash staleness** check that is independent of content diff (R2-F5, extends R1-F9). Telemetry: emit OTel via `metrics.get_meter("startd8.frontend_codegen")` + counters, mirroring `costs/otel_metrics.py:90-109` (R2-F6).

**Focus 4 — Composition with repair/Approach A.** Generation MUST run **before** Approach-A injection and repair-retry, and the owned files must be written to disk + excluded from the feature set *first*, else repair-retry will "repair" a correct owned file toward the LLM's prior (R2-F7).

**Focus 5 — Factual correction.** R1-F4/R1-S3 assert `value-model.ts` has "9 schemas, the 3 join tables excluded." **This is wrong:** the file has **12** model `z.object`s including `ProofPointCapabilitySchema`/`ProofPointOutcomeSchema`/`CapabilityOutcomeSchema` (`value-model.ts:195,208,221`) plus a 13th composite `ValueModelSchema`. The "8/9" count is only the *membership of the composite aggregate* (`:236-245`, which omits AiCall + joins **by product decision**, per the comment at `:233-234`). FR-9 must state the real rule: **1 schema per model (12), join tables included**, plus a separately-specified composite (R2-F1, R2-F8).

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Data | critical | FR-9: add a **composite-aggregate policy**. `ValueModelSchema` (`value-model.ts:236-245`) and the `ValueModel` TS type (`:262`) are **not** derivable from any single Prisma model — they are a hand-curated aggregate of `z.array(XSchema)` references that *omits* AiCall + the 3 join tables by product decision (`:233-234`). State whether the generator (a) emits the 12 per-model schemas and **leaves the composite as a seeded/hand-authored region**, or (b) generates the composite from an explicit declared membership list. Without this, FR-9's "structurally equivalent to the hand-authored file" is unsatisfiable. | A model-by-model renderer cannot reproduce a cross-model aggregate; FR-9 will fail on the composite no matter how correct the per-model output is. | FR-9 *Acceptance*; new clause | Assert the 12 per-model schemas match 1:1; assert `ValueModelSchema`/`ValueModel` are either declared-from-a-membership-list or marked out-of-scope (seeded), not silently absent. |
| R2-F2 | Data | high | FR-2: replace the prose scalar list with a **per-construct fidelity matrix** (one row per Prisma construct → exact Zod render → the failure if wrong): `Int`→`z.number().int()` (**not** `z.number()` — the checker can't tell them apart, so this is the operator's burden); `String[]`→`z.array(z.string())`; `enum`→`z.enum([...])`; `Json`→`z.unknown()`; `Decimal`→ money-safe string (see R2-F3); `DateTime`→`z.string().datetime()`. Each row names the silent-failure mode. | `value-model.ts` uses `z.number().int()` for every `Int` (`:48,169,183,189`); a renderer dropping `.int()` passes FR-3 but breaks structural equivalence (FR-9). The checker is blind to `.int()`, lists, and enum values. | FR-2 (table) | One unit test per matrix row asserting the exact emitted substring; `Int` test asserts `.int()` present. |
| R2-F3 | Data | high | FR-2/FR-3: **resolve the `Decimal` conflict.** The plan's `SCALAR_MAP` maps `Decimal→z.string()` (money-safety), but `check_prisma_zod_symmetry` only accepts `number` for `Decimal` (`_PRISMA_TO_ZOD`, `prisma_zod_symmetry.py:58`) and `string` is a **concrete** class (`:65`) → the gate emits a `field_type_mismatch`. So the renderer's intended money-safe output **fails its own FR-3 gate**. Either widen the checker's Decimal acceptance set to include `string`, or change the mapping — pick one and state it. | FR-3 claims "passes by construction"; for `Decimal` the construction and the gate contradict each other. strtd8 has no `Decimal` so this never surfaces in Inc 5. | FR-2 mapping + FR-3 caveat | Render a `Decimal` field; assert it passes the (possibly-widened) gate **and** matches the documented money-safe form. |
| R2-F4 | Validation | critical | FR-3: specify an **independent deterministic post-render self-check** (separate from `prisma_zod_symmetry`) that asserts the dimensions the checker provably ignores: per-field **optional/nullable equality**, **`.int()`** presence for `Int`, **`z.array(...)`** for list fields, **`z.enum([exact values])`** for enums, **format-hint** presence (`.email()`/`.url()`) per the convention rules, and **field count + order** equality. FR-3 must enumerate the checker's blind spots (R2 Focus-2 list) so this self-check is scoped to cover exactly them. | The symmetry checker does not compare optionality, `.int()`, list shape, enum values, format hints, ordering, or `z.unknown()` (`:252-348`); "passes by construction" is a false guarantee unless a second assertion covers the gaps. | FR-3, new acceptance clause | A `verify_render_fidelity(rendered, schema, conventions)` returning `[]`; mutate each dimension (drop `.int()`, flip a `?`, drop a list wrapper) and assert each is caught. |
| R2-F5 | Ops | high | Extend R1-F7/R1-F9: give `--check` an explicit **exit-code contract** (0=in-sync, 1=drift detected, 2=usage/parse/IO error) **and** a two-stage staleness test: first compare the embedded `schema-sha256` header (R1-F9) against the live schema hash (cheap, detects "schema changed, file not regenerated"); then, if hashes match, do a full render-and-diff (detects "someone hand-edited the owned file"). Distinct exit codes let CI distinguish "regen needed" from "owned file tampered." | FR-4 says "regenerable" with no detection mechanism; a single boolean diff conflates two operationally different failures (stale-vs-tampered) and gives CI no actionable signal. | New FR / FR-4 *Acceptance* | CI matrix: (a) edit schema → exit 1 "stale"; (b) edit owned file, schema unchanged → exit 1 "tampered"; (c) malformed schema → exit 2; (d) in-sync → exit 0. |
| R2-F6 | Ops | medium | FR-10/NFR: require OTel emission via `metrics.get_meter("startd8.frontend_codegen")` with counters `models_rendered`, `fields_rendered`, `join_tables_excluded`, `unrenderable_fields`, `format_hints_applied`, and a `drift_check` histogram — mirroring `costs/otel_metrics.py:90-109` (the SDK's emitter convention). A no-LLM generator still runs inside instrumented prime-contractor runs. | The SDK instruments all its generators; without this the operator's run telemetry shows a blind spot exactly where determinism should give the *most* confidence (exact counts). | New NFR / FR-10 | Assert a meter named `startd8.frontend_codegen` records `models_rendered=12` on a strtd8 render. |
| R2-F7 | Risks | high | FR-8/Non-Req: state the **pipeline ordering invariant** — owned files are generated + written + excluded from the feature set **before** Approach-A injection and **before** repair-retry runs. Otherwise repair-retry, seeing a (correct) owned `value-model.ts` it didn't author, may "repair" it back toward the LLM prior, re-introducing RUN-011. | The requirements say generation "composes with" Approach A and repair-retry (§7) but never fix the *order*; an unordered compose lets repair clobber the deterministic artifact. | §7 / FR-8 Phase C; Non-Req | Integration test: owned file present + flagged; assert repair-retry's worklist excludes it and does not rewrite it. |
| R2-F8 | Data | high | FR-9: **correct the model count and drop the "9 schemas" framing** (introduced in R1-F4). `value-model.ts` has **12** model `z.object`s — the 3 join tables (`ProofPointCapabilitySchema:195`, `ProofPointOutcomeSchema:208`, `CapabilityOutcomeSchema:221`) **are** rendered 1:1. The renderer should emit **one schema per Prisma model (12)**, join tables included; the "8-member" set is only the composite aggregate's membership (`:236-245`). | A join-table-*exclusion* predicate (R1-F4/R1-S3) would wrongly drop 3 schemas that the real file contains, failing FR-9 in the opposite direction. | FR-9 *Acceptance*; supersedes the R1-F4 count | Assert rendered schema-name set == the 12 model names; assert join-table schemas present, not excluded. |
| R2-F9 | Data | medium | FR-2: pin the **`@default` → required-in-Zod** rule explicitly. Per `value-model.ts:20-22` the convention is *defaulted fields stay present and required* in the base schema (`ownerId`/`source`/`confirmed`/`createdAt` are `z.string()`/`z.boolean()`, **not** `.optional()`), while only *input* variants would mark them optional. The renderer must NOT confuse `@default` with optionality. | A naive "`@default` → `.optional()`" rule (a common Zod idiom) would diverge from every base schema in the real file; the symmetry checker won't catch it (blind to optionality). | FR-2, new bullet | Render `ownerId String @default("local")`; assert `z.string()` with no `.optional()`/`.nullable()`. |
| R2-F10 | Data | medium | FR-2: add a **`@updatedAt`/`@id` semantics** clause. `updatedAt DateTime @updatedAt` and `createdAt DateTime @default(now())` both render `z.string().datetime()` and stay **required** (`value-model.ts:37-38`); `@id` renders `z.string()` (CUIDs). State these as fixed rules so the renderer doesn't special-case server-managed fields into `.optional()`. | The hand-authored file treats server-managed timestamps as required strings; the checker skips them in the Prisma→Zod direction (`:339`) so a wrong render is invisible. | FR-2, new bullet | Assert `createdAt`/`updatedAt` → `z.string().datetime()` required; `id` → `z.string()`. |
| R2-F11 | Data | low | FR-2/FR-5: add a **`@map`/`@@map` name-divergence** policy. The parser keeps only the Prisma field name (`field_names`, `prisma_parser.py:85`) and never surfaces the `@map("db_col")` DB name; state that the renderer emits the **Prisma field name** (matching `value-model.ts`), not the DB column, so a future schema adding `@map` doesn't silently flip the Zod key. | Not present in strtd8, but a forward-looking gap: a renderer that reaches for the DB name would diverge from the app-level schema; making the rule explicit prevents a latent wrong-render. | FR-2 or FR-5 | Synthetic `email String @map("email_address")`; assert Zod key is `email`, not `email_address`. |

###### Stress-test / adversarial pass (data-model surface — schema constructs that yield wrong-but-plausible Zod)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F12 | Risks | high | **Break case — `Int` rendered as `z.number()` (no `.int()`) passes the gate but diverges.** Both classify as type-class `number` (`_ZOD_BASE_TO_CLASS:32`), so the FR-3 gate returns `[]`, yet every `Int` in `value-model.ts` is `z.number().int()` (`:48,169,183,189`). "Invention impossible by construction" silently degrades to "*precision* loss invisible by construction." | The most plausible wrong-but-passing render: a one-token omission the gate is structurally blind to and strtd8's headline can't surface without an explicit `.int()` assertion (R2-F4). | FR-2 / FR-3 | Render strtd8 `sizeBytes Int?`; assert exact `z.number().int().nullable()`; assert a `.int()`-less render is caught by the self-check (not the symmetry gate). |
| R2-F13 | Risks | high | **Break case — composite `type` block renders as a phantom top-level schema.** A composite `type Address {...}` is stored in `models` (`prisma_parser.py:291`); a model-iterating renderer emits a stray `AddressSchema` *and* drops the `address Address` field (treated as a relation). The symmetry checker then **skips** the extra `AddressSchema` (no matching Prisma *model* lookup hits the composite, `:287-288`) → both errors pass. Wrong-by-construction on two axes, gate-invisible on both. | Cleanest data-model counterexample to the thesis: extends R1-F10 with the *second* failure (phantom top-level schema) and proves the gate can't catch either. | FR-2 composite policy | `type Geo {lat Float lng Float}` + `geo Geo`; assert renderer either inlines `geo: z.object({...})` or raises — never drops the field and emits a phantom schema. |

**Endorsements** (prior untriaged R1 items this reviewer agrees with):
- R1-F1: the field-completeness invariant is the right defense against the lenient parser's silent drops (`prisma_parser.py:282`); foundational for everything else.
- R1-F2: enum rendering needs its own criterion — confirmed the checker accepts enum→string (`:254-255`).
- R1-F3: optionality is genuinely unchecked — verified; R2-F4 folds it into the broader self-check.
- R1-F6: `z.infer` TS-type emission is real and ~free — the real file already does it for all 12 (`value-model.ts:249-260`); promote in-scope.
- R1-F9: schema-hash header is the right staleness primitive; R2-F5 extends it to a two-stage stale-vs-tampered check.

**Disagreements** (untriaged prior items I would push back on, for the orchestrator's triage):
- R1-F4: the specific claim "value-model.ts has **9** schemas, 3 join tables excluded" is **factually wrong** — the file has 12 model schemas incl. all 3 join tables (`value-model.ts:195,208,221`) + 1 composite. The *predicate* it proposes (exclude join tables) would corrupt FR-9. Keep the "fix the count" intent, but the correct count is **12 model schemas**, and the join-table-exclusion predicate should be **rejected**. See R2-F8. (Cite-and-revisit per CRP rules: the rationale "12 models but 9 schemas" does not hold against the actual file.)

#### Review Round R3 — claude-opus-4-8-1m — 2026-06-02

- **Scope**: end-user value + pipeline integration + sequencing. **Full text:** `CRP_ROUND_R3.md`.
- **Requirements suggestions (triaged Batch 2 — see Appendix A):**
  - **R3-F1** — split FR-8 into **8A (CLI) / 8B (minimal v1 pipeline hook) / 8C (deferred full ownership)**; 8B is ~30 lines via the existing `_try_deterministic_file_shortcut` (`prime_contractor.py:3592`), the only thing that makes the renderer prevent inventions *in a real run*. **ACCEPT.**
  - **R3-F2** — mark FR-7 **seeded** route/page shells **v1-deferred** (owned-only is all of v1; no postmortem invention is a seeded-shell body). **ACCEPT.**
  - **R3-F3** — reuse `project_knowledge`'s `FieldSpec`/`FieldSetAuthority` (`models.py:30`, `producer.py:130`), not a parallel `FieldSpec` — two projections of the "authoritative" field set can diverge and re-introduce drift. **ACCEPT.**
  - **R3-F4** — record generated provenance in the existing `forward_manifest.convention_provenance` slot (`forward_manifest.py:317`), the consumer the review phase already gates on, not only a parallel manifest. **ACCEPT.**
  - **R3-F5** — FR-9 must include ≥1 **cross-module-import** artifact (or be labeled a trivial self-contained proof); strtd8's `value-model.ts` has none, so it can't exercise alias correctness. **ACCEPT.**

#### Review Round R4 — claude-opus-4-8-1m — 2026-06-02

- **Scope**: adversarial red-team + test strategy + maintainability. **Full text:** `CRP_ROUND_R4.md`.
- **Headline:** independently confirmed R1-F4 is wrong (12 schemas incl. join tables + composite + 12 `z.infer`) → reinforces the R1-F4 REJECT.
- **Requirements suggestions (triaged Batch 2 — see Appendix A):**
  - **R4-F1** — model count is **12** incl. join tables; join tables ARE rendered (their FKs are real columns). **ACCEPT** (reinforces R2-F8).
  - **R4-F2** — fix the url hint: regex `Url$|Uri$` misses the bare `Artifact.url` field that the committed file renders `.url()` (`value-model.ts:166`); anchor `^(url|uri)$|(Url|Uri)$`. **ACCEPT.**
  - **R4-F3** — declare the composite `ValueModelSchema` policy (out-of-v1-scope or membership-list generator); silence = unpassable gate. **ACCEPT** (out-of-v1-scope).
  - **R4-F4** — `z.infer` aliases **default-ON** (committed file ships 12; deferring breaks byte-equality). **ACCEPT** (OQ-1).
  - **R4-F5** — composite `type` block: parser stores it in `models` (`prisma_parser.py:291`) → field wrongly excluded as relation + phantom schema; declare "types are not relations, not top-level schemas." **ACCEPT.**
  - **R4-F6** — specify idempotence determinism (source order, never iterate `field_names` frozenset, UTF-8/`\n`/ASCII). **ACCEPT.**
- **Failure-policy disagreement with R1-F1:** prefer per-field **`unrenderable`→flagged**, not whole-file hard-fail (one exotic field shouldn't block 11 correct models). **ACCEPT** (refines FR-1/FR-2 failure policy).

