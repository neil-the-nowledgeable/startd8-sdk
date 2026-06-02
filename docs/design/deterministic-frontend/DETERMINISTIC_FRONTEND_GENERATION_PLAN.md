# Deterministic Frontend Generation — Implementation Plan

**Version:** 1.2 (post-CRP triage Batches 1+2 — R1–R4; pairs with `…_REQUIREMENTS.md` v0.4)
**Date:** 2026-06-02
**Status:** Draft for review — ready for implementation

> Build the one missing primitive — a **Prisma→Zod/TS renderer** — validate it with the
> existing `prisma_zod_symmetry` checker *by construction* (FR-3) **plus an independent fidelity
> self-check** (FR-3b, since the symmetry gate is blind to optionality/`.int()`/enum-values/lists),
> prove it on the real strtd8 schema (FR-9), then layer convention-detection + the gated skeleton
> generators on top. Reuse `prisma_parser`, `scaffold_*`, `generate_tsconfig/dependency_file`; the
> renderer is the only net-new code. No LLM anywhere.

---

## 0.1 CRP Triage Revisions — Batch 1 (R1 + R2)

> Per-increment revisions from the first two review rounds (dispositions in Appendix A/B). Inc 4
> and Inc 5 are revised inline above; the rest are captured here and fold into the named increments.

- **Inc 1 (§2) — `parse_models`:** (a) add a **parse-completeness guard** (R1-S4) — assert each
  model's parsed field count matches its field-shaped lines; surface mismatches, never rely on the
  lenient parser (`prisma_parser.py:282`). (b) **No join-table exclusion** (R1-S3 **rejected**,
  R2-S3) — emit 1 schema per model (12), join tables included. (c) **`SCALAR_MAP` additions:**
  `Int→z.number().int()`, scalar list `String[]→z.array(z.string())` (add a list branch to
  `render_field_base` — R2-S11), enum→`z.enum([values])`. (d) **`Decimal` resolution** (R2-S1):
  map `Decimal→z.string()` (money-safe) **and** widen `_PRISMA_TO_ZOD["Decimal"]` to include
  `"string"` in `prisma_zod_symmetry.py:58` (it's ours, NFR-2) so the render passes its own gate.
  (e) **Composite `type` blocks** (R2-S9): tag `kind="type"`, render inline or hard-flag — never a
  phantom top-level schema + dropped field. (f) Emit the **`z.infer` alias** per model.
- **Inc 2 (§3) — `apply_conventions`:** pin `@default` fields **required** (not `.optional()` —
  R2-S12); `@updatedAt`/`@id` → required string. (url-bare-field fix + type-guard land in Batch 2.)
- **Inc 3 (§4):** embed a **`schema-sha256`** in `GENERATED_HEADER` (R1-S9); add the
  **composite-aggregate step** decision for `ValueModelSchema` (declare-from-membership or
  out-of-scope — R2-S4).
- **Inc 7 (§8):** `generate_tsconfig`/`generate_dependency_file` are **`NodeProfile` instance
  methods** and `generate_tsconfig` emits a generic `src/**/*` config, **not** a Next.js `@/`-alias
  one (R1-S7) — parameterize for the FR-5 alias or generate the frontend tsconfig separately.
- **Inc 8 (§9):** model `GenerationManifest` on `artifact_generator`'s report+provenance shape
  (R1-S8); add **`--check` drift mode** with the exit-code contract + stale-vs-tampered two-stage
  (R1-S6/R2-S6).
- **Cross-cutting:** add a **pipeline-ordering invariant** (generate→write→exclude **before**
  Approach-A + repair-retry — R2-S8) and **OTel** emission via `get_meter("startd8.frontend_codegen")`
  mirroring `costs/otel_metrics.py:90-109` (R1-S10/R2-S7).

---

## 0.2 CRP Triage Revisions — Batch 2 (R3 + R4)

> Value/integration + adversarial rounds. The biggest change: a **minimal pipeline hook moves into
> v1** because the seam already exists. Dispositions in Appendix A/B; full text in
> `CRP_ROUND_R3.md` / `CRP_ROUND_R4.md`.

- **Sequencing change — convention detection moves *before* the renderer (R3-S4):** reorder so
  **Inc 6 (FR-5 alias/convention detection) runs before Inc 3** (or Inc 3 takes a `ProjectConventions`
  arg with a strict default). The renderer needs the `@/` alias to emit any cross-module specifier;
  `canonical_specifier` (`producer.py:44-55`) already had to hardcode `@/` for this reason. New
  order: **Inc 1 → Inc 2 → Inc 6 → Inc 3 → Inc 4 → Inc 5 → Inc 7 → Inc 8(+8b) → Inc 9.**
- **New Inc 8b — minimal pipeline hook (FR-8B, v1) (R3-S1/R3-S2):** extend
  `_try_deterministic_file_shortcut` (`prime_contractor.py:3592-3639`) with an `owned`-file predicate
  alongside `_DETERMINISTIC_BUILD_NAMES` (`:3584`); run the renderer in the pre-generation hook beside
  `_build_project_knowledge` (`:404-416`, which already parses the Prisma anchor once) and pre-write
  owned files so a feature targeting `value-model.ts` is marked `GENERATED $0.00`, no LLM call. **This
  is the only thing that makes the renderer prevent inventions in a real run** — was wrongly bundled
  into deferred Inc 9. *Test:* pre-write `value-model.ts`, run a feature targeting it → `FeatureStatus.GENERATED`,
  `$0.00`, no LLM call (+ an operator-facing e2e, R3-S6).
- **Inc 7 split (R3-S3):** keep owned skeletons (barrels/css/config/dir) in Inc 7; move **seeded
  route/page shells to a deferred Inc 7b**. v1 ships owned-only.
- **Reuse, don't duplicate (R3-F3/R3-S10, R3-F4):** the renderer consumes `project_knowledge`'s
  `FieldSpec`/`FieldSetAuthority` (`models.py:30`, `producer.py:130`) — **not** a parallel `FieldSpec`;
  a property test asserts `render_zod_schema` field set ≡ `DraftModeProducer.build(...).field_sets`
  per entity. Provenance lands in `forward_manifest.convention_provenance` (`forward_manifest.py:317`),
  redirecting R1-S8's manifest target to the consumer the review phase gates on.
- **Inc 2 — convention safety (R4-S2/R4-S3):** fix the url hint to match a **bare `url`** field
  (`Artifact.url` → `.url()`, `value-model.ts:166`; regex `Url$|Uri$` misses it) → anchor
  `^(url|uri)$|(Url|Uri)$`; **type-guard** all hints (apply `.email()`/`.url()` only when base type is
  `String`, else a `contactEmail Boolean`/`thumbnailUrlExpiry DateTime` gets an invalid chained method).
- **Inc 1 — failure policy (R4-S5/R4-S11):** replace whole-file `UnsupportedPrismaTypeError` abort
  with **per-field flagged-unrenderable + one aggregated report**; exit non-zero only under `--strict`.
- **Inc 4/new §5.5 — property tests (R4-S9/R4-S7/R4-F6):** Hypothesis round-trip
  (`parse(render(models)) ≡ models`) + byte-idempotence across two subprocesses with randomized
  `PYTHONHASHSEED`; pin source-order iteration (never the `field_names` frozenset). Add a **parser-drift
  test** (R4-S8) that fails when a new Prisma scalar appears un-mapped.
- **Inc 5 (R3-S7/R3-F5):** include ≥1 cross-module-import fixture (assert the specifier matches the
  detected `@/` alias, not a hardcoded path); add the operator e2e (R3-S6).
- **§12 risk table — new "prevention reachability" row (R3-S8/R3-S9):** the renderer can be 100%
  correct and gate-green yet a real run still re-invents `value-model.ts` if no hook pre-writes/excludes
  it (`_is_safe_to_overwrite` blocks only on git-dirty, not owned-file identity); mitigation = Inc 8b.

---

## 0. Strategy & sequencing

```
Inc 1  Field model + scalar/optionality mapping        (FR-1, FR-2)   — pure, the core
Inc 2  Convention layer (format hints, relation excl.) (FR-2)         — pure rules
Inc 3  Renderer → value-model.ts text + GENERATED hdr  (FR-1, FR-4)   — emit
Inc 4  Symmetry-by-construction gate                   (FR-3)         — wire prisma_zod_symmetry
Inc 5  strtd8 acceptance gate (real schema, 12 models) (FR-9)         — headline proof
Inc 6  Project-convention detection                    (FR-5)         — tsconfig + file scan
Inc 7  Gated skeleton generators (barrels/css/config)  (FR-6, FR-7)   — reuse scaffold_*
Inc 8  Owned/seeded manifest + CLI                     (FR-7, FR-8A)  — wiring
Inc 9  [deferred] pipeline ownership seam              (FR-8C)        — prime-contractor
```

Inc 1–5 deliver the headline (RUN-011 killed by construction, proven on real data). Inc 6–8
generalize to the rest of the mechanical surface. Inc 9 (pipeline ownership) is explicitly
deferred per FR-8/Non-Req v1.

**Module home (OQ-6 → resolve):** new `src/startd8/frontend_codegen/` package
(`schema_renderer.py`, `conventions.py`, `skeleton.py`, `manifest.py`), called by both the CLI
and (later) the prime-contractor. Sits beside `languages/` (reuses `prisma_parser`,
`nodejs`) and `repair/retry/scaffold` — does not extend `languages/nodejs` (keeps the
frontend-app concern out of the language-profile abstraction).

---

## 1. Key seams (what exists, what's new)

| Seam | Location | Role |
|------|----------|------|
| Prisma parse | `languages/prisma_parser.parse_prisma_schema(text)` | **reuse** — gives models, `field_names`, scalar types, optionality, relations |
| Field-set grounding | `contractors/upstream_interface.render_prisma_field_sets` | **reuse model, not output** — it emits *prompt text*; the new renderer emits the *file* (share the parsed field model) |
| Symmetry check | `validators/prisma_zod_symmetry.check_prisma_zod_symmetry` | **reuse as the FR-3 gate** — generator output must return `[]` |
| Barrel / CSS stub | `repair/retry/scaffold.{scaffold_barrel,scaffold_cofile}` | **reuse** for FR-6 |
| Config gen | `languages/nodejs.{generate_dependency_file,generate_tsconfig}` | **reuse** for FR-6 |
| Export introspection | `contractors/upstream_interface.{extract_ts_exports,resolve_specifier_to_paths}` | **reuse** for FR-5 convention detection |
| Precedent | `observability/artifact_generator`, `dashboard_creator/generator` | pattern to mirror (deterministic file emission) |
| **NEW** | `frontend_codegen/schema_renderer.py` | the one missing primitive — `render_zod_schema(models, conventions) -> str` |

---

## 2. Inc 1 — Field model + scalar/optionality mapping (FR-1, FR-2)

**`frontend_codegen/schema_renderer.py`:**
- `parse_models(schema_text) -> list[ModelSpec]` — thin wrapper over `parse_prisma_schema`
  producing `ModelSpec{name, fields:[FieldSpec{name, prisma_type, optional, is_relation,
  is_id, attrs}]}`. (If `parse_prisma_schema` already yields this, adapt rather than re-parse.)
- `SCALAR_MAP: dict[str,str]` — `String→z.string()`, `Int→z.number().int()`,
  `Float→z.number()`, `Boolean→z.boolean()`, `DateTime→z.string().datetime()`,
  `Json→z.unknown()`, `BigInt→z.bigint()`, `Decimal→z.string()` (per the documented mapping).
- `render_field_base(field) -> str` — scalar type + `?`→`.nullable()`.

**Tests:** every scalar maps; `String?` → `.nullable()`; an unknown Prisma type raises a
clear `UnsupportedPrismaTypeError` (no silent `z.any()`).

## 3. Inc 2 — Convention layer (FR-2)

**`frontend_codegen/conventions.py`:**
- `FieldConventions` (declared default rule set, overridable): format hints by field-name
  regex (`^email$|Email$`→`.email()`, `Url$|Uri$`→`.url()`), `@id`→`z.string()`,
  relation-exclusion predicate, id/provenance handling.
- `apply_conventions(field, base) -> str` — layer hints onto the base type; **deterministic,
  pure**.

**Tests:** `email`→`.email()`; `avatarUrl`→`.url()`; a relation field → excluded (predicate
True); same field → identical output twice (determinism). Seed the default rule set from the
documented `value-model.ts` mapping; do **not** infer from the (LLM-authored) existing file
(OQ-2 resolution).

## 4. Inc 3 — Renderer + GENERATED header (FR-1, FR-4)

- `render_zod_schema(models, conventions) -> str` — per model:
  `export const <Model>Schema = z.object({ <field>: <type>, … });` + (optional)
  `export type <Model> = z.infer<typeof <Model>Schema>;` (OQ-1 follow-on, behind a flag).
- `GENERATED_HEADER` constant: `// GENERATED from prisma/schema.prisma — do not edit by
  hand; regenerate via \`startd8 generate frontend\`. Source of truth: the Prisma schema.`
- Idempotent: deterministic field/model ordering (schema order), stable formatting.

**Tests:** two renders byte-identical (FR-4); header present; a 2-model schema renders the
expected text; relation fields absent.

## 5. Inc 4 — Symmetry-by-construction gate + fidelity self-check (FR-3, FR-3b)

- Wire the gate with the **real signature** (R1-S1): `assert_symmetric(rendered, schema_text)`
  must `prisma = parse_prisma_schema(schema_text)`, `zod = extract_zod_objects(rendered)`, then
  `check_prisma_zod_symmetry(prisma, zod, entity_map=…)` — args are parsed objects, order
  **(prisma, zod)**, not text (`prisma_zod_symmetry.py:264`).
- Add `verify_render_fidelity(rendered, schema, conventions) -> [Issue]` (FR-3b) **alongside** the
  symmetry gate, asserting what the checker provably ignores: per-field optional/nullable, `.int()`
  for `Int`, `z.array(…)` for lists, `z.enum([exact values])`, format hints, field count + order
  (`prisma_zod_symmetry.py:252-348`). The symmetry gate is the cross-check; fidelity is the
  by-construction proof.
- **Negative test (R1-S2/R4-S10):** the dropped field must be a **required, non-defaulted scalar**
  — the Prisma→Zod direction skips `@default`/`@id`/optional (`:336-340`), and on strtd8 the
  **only** such field is `Profile.name` (`schema.prisma:26`); dropping any other field passes
  silently. Drop `Profile.name` → symmetry gate fails; drop an optional field → document it does
  NOT fail and is covered by the fidelity check. Add a second negative test: render `Int` as
  `z.string()` → caught.

**Tests:** rendered strtd8 output → `[]` symmetry **and** `[]` fidelity; drop `Profile.name` →
symmetry fails; drop `.int()`/flip a `?`/drop a `z.array` wrapper → fidelity (not symmetry) catches it.

## 6. Inc 5 — strtd8 acceptance gate (FR-9, headline)

**`tests/unit/frontend_codegen/test_strtd8_acceptance.py`:**
- Load the real strtd8 `prisma/schema.prisma` (**12 models**) — committed as a fixture (or read
  via a path env, skipif absent for CI portability).
- Render → assert per-model scalar-field-set + optionality + **`.int()`** equality vs the committed
  `lib/value-model.ts`; the **3 join-table schemas are present** (`value-model.ts:195,208,221` — do
  **not** exclude them; R1-S3 rejected); assert the **12 `z.infer` aliases** are emitted (byte-equality
  needs them, `:249-260`).
- The composite **`ValueModelSchema`** (`:236-245`) is **out of v1 scope** (no single-model renderer
  derives a cross-model aggregate) — assert it is explicitly excluded/seeded, not silently absent.
- Assert 0 `prisma_zod_symmetry` **and** 0 `verify_render_fidelity` violations.
- Per-model invented-name assertion (not global): `outcomeId` absent from **`OutcomeSchema`**
  specifically (it is a real column on the join models — R1-F5/R1-S?).
- Emit a diff report of *intentional* convention differences (format hints) — informational.

**This is the proof — but only of the trivial path.** strtd8 exercises **no** enums/scalar-arrays/
`@map`/native-types/`Decimal`/composites/self-relations (verified across all 12 models), so the
real per-construct robustness (FR-2 matrix) is proven by a **synthetic fixture suite**
(`test_construct_fidelity.py`, one fixture per dangerous construct), authored in Inc 1–3 **before**
this gate so a green strtd8 run is not mistaken for robustness.

## 7. Inc 6 — Project-convention detection (FR-5)

**`frontend_codegen/conventions.py` (extend):**
- `detect_project_conventions(project_root) -> ProjectConventions{alias, alias_root,
  uses_barrels, uses_css_modules, types_dir}` — read `tsconfig.json` `paths` for the alias
  (`@/*`→`./*`); scan for any `index.ts` re-export barrels (`extract_ts_exports`); scan for
  `*.module.css`; detect a top-level `types/` dir.
- Absence is first-class: `uses_barrels=False` is an explicit "do not generate / project does
  not use barrels" signal (the RUN-012 anti-invention).

**Tests:** against a strtd8 fixture → `alias=@/→./`, `uses_barrels=False`,
`uses_css_modules=False`; against a synthetic barrel-using fixture → `uses_barrels=True`.

## 8. Inc 7 — Gated skeleton generators (FR-6, FR-7)

**`frontend_codegen/skeleton.py`:**
- `generate_skeleton(plan_manifest, schema, conventions, out_dir) -> SkeletonResult` —
  - schema types (Inc 3) — always (owned);
  - barrels via `scaffold_barrel` — **only if** `conventions.uses_barrels` (FR-6 gate);
  - CSS stubs via `scaffold_cofile` — only if `uses_css_modules`;
  - `package.json`/`tsconfig` via `nodejs.generate_*` — if absent;
  - directory skeleton from the plan's file manifest (mkdir the canonical dirs — prevents
    RUN-013 sub-namespace invention);
  - route/page **seeded shells** (FR-7): imports + handler signature + a guarded body region.
- Each output tagged `owned` or `seeded` in the result.

**Tests:** barrel-using project → barrel emitted; strtd8 (no barrels) → none emitted, none
invented; route shell is `seeded` with a guarded body; the directory skeleton matches the
manifest.

## 9. Inc 8 — Manifest + CLI (FR-7, FR-8 Phase A)

**`frontend_codegen/manifest.py`:** `GenerationManifest` — lists each generated path with
`{path, ownership: owned|seeded, source: schema|scaffold|config|dir, regenerable: bool}`.

**`cli.py`:** new `generate` command group → `startd8 generate frontend --schema <path>
--out <dir> [--project <root>] [--types-only] [--emit-interfaces]`. Renders schema types
(always) + skeleton (if `--project` given for convention detection); writes the manifest;
prints owned/seeded summary. No LLM, no network.

**Tests:** CLI renders types to `--out`; `--types-only` skips skeleton; manifest written.

## 10. Inc 9 — [DEFERRED] pipeline ownership seam (FR-8 Phase C)

Out of scope for v1 (Non-Req). Sketch for OQ-3: a `provided_files` input to the
prime-contractor that (a) pre-writes owned files before generation, (b) excludes them from the
LLM feature set, (c) orders dependent features after them via the forward manifest. Resolve the
mechanics (manifest tag vs plan annotation) in a follow-up requirements pass.

---

## 11. Requirement → increment traceability

| FR | Increment |
|----|-----------|
| FR-1 renderer | Inc 1, 3 |
| FR-2 convention layer | Inc 1, 2 |
| FR-3 symmetry-by-construction | Inc 4 |
| FR-4 marker + idempotent | Inc 3 |
| FR-5 project-convention detection | Inc 6 |
| FR-6 gated skeletons | Inc 7 |
| FR-7 owned/seeded ownership | Inc 7, 8 |
| FR-8A CLI | Inc 8 |
| FR-8C pipeline seam | Inc 9 (deferred) |
| FR-9 strtd8 acceptance | Inc 5 |
| FR-10 no-LLM/idempotent | all (NFR-1, enforced by tests) |

## 12. Risks & mitigations

| Risk | Mitigation |
|------|-----------|
| `parse_prisma_schema` doesn't expose optionality/relations cleanly | Inc 1 adapts/normalizes into `FieldSpec`; if a gap, extend the parser (it's ours) — verify in Inc 1 first. |
| Convention hints (email/url) diverge from the hand-authored file | FR-9 emits a **diff report**; intentional differences are reviewed, not silently accepted; the rule set is the single declared source. |
| Symmetry gate is tautological (renderer + checker share a bug) | Inc 4 negative test (broken render must be caught) proves the gate bites. |
| strtd8 schema not available in CI | Commit a schema fixture; `skipif` on the live-path variant. |
| Skeleton generation overwrites an LLM-authored file | FR-7 owned/seeded split + GENERATED header; owned files are inert to the LLM (Phase C enforces exclusion). |
| Scope creep into business logic | Non-Req fences `lib/ai/*`, route/page bodies as LLM-owned (seeded shells only). |
| `z.infer` interface emission drifts from Zod | Behind `--emit-interfaces` flag (OQ-1); default off in v1. |

## 13. Conventions checklist
- [ ] `get_logger(__name__)` in new modules.
- [ ] **No hardcoded model strings** (there is no LLM here — assert zero provider imports).
- [ ] Reuse `parse_prisma_schema`/`scaffold_*`/`generate_tsconfig`/`prisma_zod_symmetry` — don't re-implement.
- [ ] New files added to `test_logger_acquisition_policy.py` allowlist if using string logger names.
- [ ] `pytest tests/unit/frontend_codegen -q` green; `ruff`/`black`/`mypy` clean.
- [ ] CLI `generate frontend` documented in `--help` + a docs entry.

---

*Plan v1.0 — renderer-first (Inc 1–5 kill RUN-011 by construction and prove it on the real
strtd8 schema), then convention-detection + gated skeletons (Inc 6–8); pipeline ownership
deferred (Inc 9). The only net-new code is the renderer; everything else reuses an existing
primitive. Pairs with requirements v0.2. CRP review offered before Inc 1.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Appendix A: Applied Suggestions

**Batch 1 (R1 + R2) — triaged 2026-06-02.**

| ID | Disposition | Merged into | Date |
|----|-------------|-------------|------|
| R1-S1 | ACCEPT | Inc 4 — real gate signature `(prisma, zod, entity_map=…)` | 2026-06-02 |
| R1-S2 | ACCEPT | Inc 4 — negative test drops a required non-defaulted scalar (`Profile.name`) | 2026-06-02 |
| R1-S4 | ACCEPT | §0.1 Inc 1 — parse-completeness guard | 2026-06-02 |
| R1-S5 | ACCEPT | Inc 4 `verify_render_fidelity` (optionality equality) | 2026-06-02 |
| R1-S6 | ACCEPT | §0.1 Inc 8 — `--check` drift mode | 2026-06-02 |
| R1-S7 | ACCEPT | §0.1 Inc 7 — `NodeProfile` method + `src/**/*` vs `@/` alias fix | 2026-06-02 |
| R1-S8 | ACCEPT | §0.1 Inc 8 — manifest mirrors `artifact_generator` (redirected to forward-manifest in Batch 2) | 2026-06-02 |
| R1-S9 | ACCEPT | §0.1 Inc 3 — `schema-sha256` header | 2026-06-02 |
| R1-S10 | ACCEPT | §0.1 cross-cutting — OTel emission | 2026-06-02 |
| R1-S11 | ACCEPT | §0.1 Inc 1 — enum render + dedicated test | 2026-06-02 |
| R1-S12 | ACCEPT | §0.1 Inc 1 — `Unsupported(…)`/silent-drop flagged (policy refined in Batch 2) | 2026-06-02 |
| R2-S1 | ACCEPT | §0.1 Inc 1 — `Decimal` map + widen checker acceptance | 2026-06-02 |
| R2-S2 | ACCEPT | Inc 4/5 — explicit `.int()` assertion | 2026-06-02 |
| R2-S3 | ACCEPT | Inc 5 — 12 schemas incl. join tables (supersedes R1-S3) | 2026-06-02 |
| R2-S4 | ACCEPT | §0.1 Inc 3 / Inc 5 — composite-aggregate policy | 2026-06-02 |
| R2-S5 | ACCEPT | Inc 4 — `verify_render_fidelity` self-check | 2026-06-02 |
| R2-S6 | ACCEPT | §0.1 Inc 8 — exit-code contract + stale-vs-tampered | 2026-06-02 |
| R2-S7 | ACCEPT | §0.1 cross-cutting — OTel via `get_meter` | 2026-06-02 |
| R2-S8 | ACCEPT | §0.1 cross-cutting — pipeline-ordering invariant | 2026-06-02 |
| R2-S9 | ACCEPT | §0.1 Inc 1 — composite `type` block handling | 2026-06-02 |
| R2-S10 | ACCEPT | Inc 5 — synthetic construct fixtures | 2026-06-02 |
| R2-S11 | ACCEPT | §0.1 Inc 1 — scalar list `String[]` branch | 2026-06-02 |
| R2-S12 | ACCEPT | §0.1 Inc 2 — `@default` stays required | 2026-06-02 |

**Batch 2 (R3 + R4) — triaged 2026-06-02.**

| ID | Disposition | Merged into | Date |
|----|-------------|-------------|------|
| R3-S1 | ACCEPT | §0.2 / new **Inc 8b** — minimal pipeline hook (v1) | 2026-06-02 |
| R3-S2 | ACCEPT | §0.2 Inc 8b — renderer in pre-gen hook beside `_build_project_knowledge` | 2026-06-02 |
| R3-S3 | ACCEPT | §0.2 — split seeded shells into deferred Inc 7b | 2026-06-02 |
| R3-S4 | ACCEPT | §0.2 — reorder convention detection before Inc 3 | 2026-06-02 |
| R3-S5 | ACCEPT | §0.2 / Inc 8 — `--check` as primary CLI deliverable | 2026-06-02 |
| R3-S6 | ACCEPT | §0.2 Inc 8b — operator-facing e2e | 2026-06-02 |
| R3-S7 | ACCEPT | §0.2 Inc 5 — cross-module-import fixture | 2026-06-02 |
| R3-S8 | ACCEPT | §0.2 §12 — prevention-reachability risk row | 2026-06-02 |
| R3-S9 | ACCEPT | §0.2 §12 — "correct generator, zero prevention" adversarial → motivates 8b | 2026-06-02 |
| R3-S10 | ACCEPT | §0.2 — shared `FieldSpec` property test | 2026-06-02 |
| R4-S2 | ACCEPT | §0.2 Inc 2 — bare-`url` hint anchored | 2026-06-02 |
| R4-S3 | ACCEPT | §0.2 Inc 2 — type-guarded hints | 2026-06-02 |
| R4-S4 | ACCEPT | §0.2 / Inc 5 — synthetic fixture matrix before the headline | 2026-06-02 |
| R4-S5 | ACCEPT | §0.2 Inc 1 — per-field flagged, no whole-file hard-fail | 2026-06-02 |
| R4-S6 | ACCEPT | §0.2 Inc 8 — `--check` pre-commit/CI + hash short-circuit | 2026-06-02 |
| R4-S7 | ACCEPT | §0.2 §5.5 — byte-idempotence determinism (subprocess hashseed) | 2026-06-02 |
| R4-S8 | ACCEPT | §0.2 — parser-drift coupling test | 2026-06-02 |
| R4-S9 | ACCEPT | §0.2 §5.5 — Hypothesis round-trip + idempotence property test | 2026-06-02 |
| R4-S10 | ACCEPT | Inc 4 — negative test drops `Profile.name` specifically | 2026-06-02 |
| R4-S11 | ACCEPT | §0.2 Inc 1 — aggregate unrenderable into one report | 2026-06-02 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Disposition | Rejection Rationale | Date |
|----|-------------|---------------------|------|
| R1-S3 | **REJECT** | Join-table **exclusion** predicate is wrong — `value-model.ts` renders all 3 join-table schemas 1:1 (`:195,208,221`); excluding them emits 9 vs the committed 12 and fails Inc 5. The "fix the count" intent is kept; correct rule = 1 schema per model (12), via R2-S3. (Independently confirmed by R2-S3, R4-S1.) | 2026-06-02 |
| R1-F1 hard-fail framing | **PARTIAL REJECT** | The completeness-guard intent is accepted (R1-S4), but `UnsupportedPrismaTypeError` aborting the whole render is rejected — one exotic field would block 11 correct models. Replaced by per-field flagged-unrenderable (R4-S5). | 2026-06-02 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-01

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-01 00:00:00 UTC
- **Scope**: Plan architecture/interfaces/sequencing/ops review, grounded in the actual signatures of `prisma_parser.parse_prisma_schema`, `prisma_zod_symmetry.check_prisma_zod_symmetry`, `repair/retry/scaffold.{scaffold_barrel,scaffold_cofile}`, `languages/nodejs.NodeProfile.generate_*`, and `observability/artifact_generator`, plus the real strtd8 schema and `value-model.ts`.

##### Executive summary (top risks / opportunities)

- **FR-3 gate signature in the plan is wrong.** Inc 4/§5 calls `check_prisma_zod_symmetry(rendered_text, schema_text)` — but the real signature is `check_prisma_zod_symmetry(prisma_schema: PrismaSchema, zod_schemas: Dict[str, ZodObjectSchema], *, entity_map=...)` (`prisma_zod_symmetry.py:264`). Args are **(prisma, zod)**, parsed objects, not text. `assert_symmetric` must call `extract_zod_objects(rendered)` + `parse_prisma_schema(schema_text)` first.
- **The Inc 4 negative test is weaker than claimed.** Dropping a field only fails the gate if the checker checks it; the Prisma→Zod direction is *warning-only* and skips optional/`@default`/`@id`/`@updatedAt` fields (`prisma_zod_symmetry.py:331-346`). Dropping a `@default` or optional field passes silently — the "gate bites" proof must drop a *required, non-defaulted scalar* to be valid.
- **The headline proof (Inc 5) exercises only the trivial path.** The strtd8 schema has no enums, no scalar arrays, no `@map`, no native types, no `Decimal/Bytes/BigInt`, no self-relations — all value-model fields are `String/Int/Float/Boolean/DateTime` + `.nullable()`. The robustness the focus file worries about is **never tested** by the headline. Add synthetic-construct fixtures (Inc 1/2) so robustness is proven independently of strtd8.
- **`generate_tsconfig`/`generate_dependency_file` are instance methods on `NodeProfile`, not module functions** (`nodejs.py:280,449`), and `generate_tsconfig` emits a generic `src/**/*` config — **not** a Next.js/`@/*`-alias config. Reusing it for FR-6 would emit a tsconfig that contradicts the FR-5-detected `@/` alias.
- **`scaffold_barrel`/`scaffold_cofile` write to disk and require existing sibling files + a `generated_root` for realpath confinement** (`scaffold.py:49-131`); they do not return text and cannot build a barrel from a manifest before files exist. Inc 7's "emit via scaffold_*" needs an ordering contract (files first, then barrel).
- **Join-table model count mismatch:** 12 `model` blocks but `value-model.ts` has 9 `z.object` schemas; the renderer needs a tested join-table-exclusion predicate or Inc 5 fails (see R1-S3).
- **Mottainai / quick win:** `artifact_generator` already emits a `report` with per-artifact provenance + a written summary (`artifact_generator.py:457,1083-1095`) — mirror its manifest shape for the GenerationManifest rather than hand-rolling (R1-S8).
- **Opportunity:** a `--check` drift mode is ~the same renderer + a diff; pulling it into Inc 5/8 turns the symmetry checker into a real-run CI gate and partially covers NFR-4 *before* the deferred Inc 9 (R1-S6).

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Interfaces | critical | Fix the FR-3 gate call: `assert_symmetric(rendered, schema_text)` must `parse_prisma_schema(schema_text)` and `extract_zod_objects(rendered)` then call `check_prisma_zod_symmetry(prisma_schema, zod_schemas, entity_map=...)` — note arg order **(prisma, zod)** and that both args are parsed objects, not text. | §5 Inc 4 and the §1 seam table show `check_prisma_zod_symmetry(rendered_text, schema_text)`, which does not match the real signature (`prisma_zod_symmetry.py:264`); as written the wiring will not type-check. | §5 Inc 4; §1 seam-table row "Symmetry check" | Unit test calls the helper and asserts it returns `[]` for a correct render and a `field_missing_in_prisma` for an invented field. |
| R1-S2 | Validation | high | Strengthen the Inc 4 negative test: the dropped field must be a **required, non-defaulted scalar** (e.g. `name String`), not a `@default`/`@id`/optional field, or the symmetry gate will pass silently. Add a second negative test for a *type* mismatch (e.g. render `Int` field as `z.string()`). | The Prisma→Zod direction is advisory and skips defaulted/id/optional fields (`prisma_zod_symmetry.py:336-340`); a naive "drop a field" test can pass and give false confidence the gate bites. | §5 Inc 4 *Tests* | Drop `name` (required) → gate fails; drop `notes` (optional) → document that it does NOT fail and is covered by the separate optionality assertion (R1-S5). |
| R1-S3 | Data | high | Add an explicit, tested **join-table exclusion** step before render: 12 strtd8 models but `value-model.ts` has 9 schemas (join tables `ProofPointCapability/ProofPointOutcome/CapabilityOutcome` excluded). Define the predicate (model whose only non-id/meta fields are relation FKs) in Inc 1's `parse_models`. | Inc 5 asserts "structurally equivalent to value-model.ts (12 models)"; without exclusion the renderer emits 12 schemas and the acceptance fails. | §2 Inc 1; §6 Inc 5 | Assert rendered schema-name set == the 9 names in `value-model.ts`; assert the 3 join models are excluded by the predicate. |
| R1-S4 | Risks | critical | Inc 1: add a **parse-completeness guard** — after `parse_prisma_schema`, assert each model's field count matches the field-shaped lines in its body and raise on mismatch; do not rely on the lenient parser to surface dropped fields. | The parser silently skips unmatched lines (`prisma_parser.py:282`); `Unsupported(...)`/native-only fields vanish, so a "complete by construction" render can silently omit a column. | §2 Inc 1 *Tests* | Fixture with an `Unsupported("...")` field → renderer raises; without the guard, the model would render minus that field. |
| R1-S5 | Validation | high | Inc 3/5: add an explicit **optionality/nullability equality** assertion (per field `is_optional` ⇔ `.nullable()`) separate from the symmetry gate, which does not check it. | The symmetry checker never compares optionality (`prisma_zod_symmetry.py:296-348`); FR-4/FR-9's optionality claims are otherwise unverified. | §4 Inc 3 / §6 Inc 5 *Tests* | Parse both rendered + hand-authored files; assert per-field nullable flags match; mutate one `?` and assert the test catches it. |
| R1-S6 | Ops | high | Pull a **`--check` drift mode** into Inc 5/8: render in-memory, diff against the on-disk `value-model.ts`, exit non-zero on divergence + print the diff. This is ~the renderer + a string diff and delivers a real-run CI gate before the deferred Inc 9. | Focus 2/4: detects owned-file drift (NFR-4) and makes `prisma_zod_symmetry` a CI gate on real runs without the pipeline seam. | §9 Inc 8 CLI flags; §6 Inc 5 | CI test mutates the on-disk file; `generate frontend --check` exits non-zero with a diff. |
| R1-S7 | Interfaces | high | §1/§8: correct the `nodejs` reuse — `generate_tsconfig`/`generate_dependency_file` are **`NodeProfile` instance methods** (`nodejs.py:280,449`), and `generate_tsconfig` emits a generic `src/**/*` config, not a Next.js `@/*`-alias one. Either parameterize it for the FR-5 alias or generate the frontend tsconfig separately. | The plan cites them as `languages/nodejs.{...}` module functions; as-is they would emit a tsconfig that contradicts the detected `@/` alias (FR-5), re-introducing an inconsistency. | §1 seam table; §8 Inc 7 | Assert generated tsconfig `paths` includes the detected `@/*`→`./*`; assert no `src/**/*`-only include when alias root differs. |
| R1-S8 | Architecture | medium | §9 Inc 8: model `GenerationManifest` on `artifact_generator`'s existing report+provenance shape (per-artifact records, written summary) rather than hand-rolling; reuse its emission/summary helpers. | Mottainai / Lens 1: `artifact_generator.generate_observability_artifacts` already produces a per-artifact report with provenance counts and a written summary (`artifact_generator.py:457,1083-1095`); mirroring it gets manifest + summary nearly free and keeps conventions consistent. | §9 Inc 8 | Manifest dataclass field-parity test vs the artifact_generator record; summary written to disk in the same shape. |
| R1-S9 | Ops | medium | §4 Inc 3: embed a **schema content hash** in `GENERATED_HEADER` (`// schema-sha256: <hex>`) so staleness is deterministically detectable by `--check`/CI (ties to R1-S6). | Idempotence alone doesn't tell an operator a regen is *needed*; a header hash makes drift/staleness a deterministic check. | §4 Inc 3 | Change one schema field; assert header hash changes; `--check` flags stale. |
| R1-S10 | Ops | low | §13: add OTel span/metrics emission (models rendered, fields, excluded join tables, unrenderable count) per SDK observability conventions, consistent with how `artifact_generator`/Kaizen emit run metrics. | Focus 4: the SDK instruments its generators; a no-LLM generator should still emit counts for the prime-contractor operator's run telemetry. | §13 conventions checklist | Assert a span/metric is emitted with the rendered-model count on a CLI run. |

##### Stress-test / adversarial pass (attempts to break "invention impossible by construction")

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S11 | Risks | high | **Break case — enum silently mis-rendered as `z.string()`.** If `SCALAR_MAP` lacks enum handling, an enum field either raises `UnsupportedPrismaTypeError` (blocks all 12 models) or, if a fallback maps it to `z.string()`, the symmetry gate **accepts** it (`prisma_zod_symmetry.py:254-255` treats enum→string as compatible). Plausible-but-wrong output passes the gate. Require enum rendering + a dedicated assertion in Inc 1–3, not Inc 7. | The "by construction" thesis fails for enums: the gate cannot catch the error. strtd8 has no enums so Inc 5 never surfaces it. | §2 Inc 1 / §4 Inc 3 | Synthetic enum fixture; assert `z.enum([...])` emitted and that a `z.string()` render is rejected by an explicit test. |
| R1-S12 | Risks | high | **Break case — `Unsupported(...)`/odd-spacing field silently dropped.** `_FIELD_RE` won't match `Unsupported("...")` (parens) so the line is skipped (`prisma_parser.py:42,282,276`); the render omits the column with no error — a silent omission that *looks* correct and even passes symmetry (a Zod schema may legitimately omit columns). Hard-fail or flag it (ties R1-S4/F1). | This is the cleanest counterexample to "invention impossible": omission-by-construction is still wrong-by-construction, and the gate is blind to it. | §2 Inc 1; §12 risk table | Fixture with `geom Unsupported("geometry")`; assert renderer raises or records an `unrenderable` manifest entry, never silently drops. |

**Endorsements**: none (first round).

#### Review Round R2 — claude-opus-4-8-1m — 2026-06-01

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-01 00:00:00 UTC
- **Scope**: R2 lens — **data-modeling depth + validation semantics + operational/CI**. Goes beyond R1 on the Prisma→Zod fidelity surface in the plan's `SCALAR_MAP`/`FieldSpec`, the post-render self-check FR-3 needs, and drift/staleness/telemetry/exit-code/pipeline-ordering ops. Grounded in `prisma_zod_symmetry.py`, `prisma_parser.py`, `costs/otel_metrics.py`, and the real strtd8 `schema.prisma` (12 models) + `lib/value-model.ts` (re-counted: **13** `z.object`s = 12 model schemas incl. all 3 join tables + 1 composite). **Corrects R1-S3's join-table claim.**

##### Executive summary (top risks / opportunities)

- **The plan's `SCALAR_MAP` `Decimal → z.string()` (§2) is rejected by its own FR-3 gate.** `check_prisma_zod_symmetry` only accepts `number` for `Decimal` (`_PRISMA_TO_ZOD`, `prisma_zod_symmetry.py:58`) and `string` is a concrete class (`:65`), so the renderer's money-safe output emits a `field_type_mismatch`. The "by construction" gate and the mapping contradict each other (R2-S1).
- **`Int → z.number().int()` is invisible to the gate.** `z.number()` and `z.number().int()` share type-class `number` (`_ZOD_BASE_TO_CLASS:32`); a renderer that drops `.int()` passes Inc 4/5 but diverges from every `Int` in `value-model.ts` (`:48,169,183,189`). Inc 1's `SCALAR_MAP` already has `Int→z.number().int()` — good — but nothing **asserts** it survives to output (R2-S2).
- **R1-S3's join-table count is wrong.** `value-model.ts` has **12** model `z.object`s including all 3 join tables (`:195,208,221`), not 9. A join-table-*exclusion* predicate (R1-S3) would delete 3 correct schemas and fail Inc 5. The renderer should emit **1 schema per model (12)**; the "8-member" set is only the composite aggregate's membership (R2-S3).
- **`ValueModelSchema` (`value-model.ts:236-245`) is not renderable from any single model.** It's a composite of `z.array(XSchema)` references. Inc 3/5 must either declare it from a membership list or mark it seeded/out-of-scope — else Inc 5's "structurally equivalent" assertion fails on it regardless of per-model correctness (R2-S4).
- **Inc 4's self-test must add a fidelity check the symmetry gate can't do.** Optionality, `.int()`, list shape, enum values, format hints, ordering are all unverified by `check_prisma_zod_symmetry` (`:252-348`); FR-3 "by construction" needs a second `verify_render_fidelity` helper (R2-S5).
- **Inc 8 `--check` needs an exit-code contract + a stale-vs-tampered split** (R2-S6); telemetry should mirror `costs/otel_metrics.py:90-109` (`get_meter("startd8.frontend_codegen")`, R2-S7).
- **Pipeline-ordering invariant missing:** owned files must be written + feature-excluded **before** Approach-A injection and repair-retry, or repair "fixes" the correct owned file toward the LLM prior (R2-S8).
- **Composite `type` block double-failure:** a `type` block renders a phantom top-level schema AND drops the composite-typed field; the gate catches neither (R2-S9, adversarial).

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Data | critical | §2 Inc 1: resolve the **`Decimal` self-contradiction**. `SCALAR_MAP` has `Decimal→z.string()`, but the FR-3 gate only accepts `number` for `Decimal` (`prisma_zod_symmetry.py:58`; `string` is concrete, `:65`) → it emits `field_type_mismatch`. Either (a) widen the checker's Decimal acceptance to include `string` (it's *ours*, per NFR-2), or (b) change the map. Document the choice in §2 and the risk table. | As written, Inc 4 fails on any `Decimal` field; the plan claims symmetry-by-construction but the construction violates the gate. | §2 Inc 1 `SCALAR_MAP`; §12 risks | Add a `Decimal` field fixture; assert render passes the (chosen) gate and matches the money-safe form. |
| R2-S2 | Validation | high | §5 Inc 4 / §6 Inc 5: add an **explicit `.int()` assertion** for `Int` fields, independent of the symmetry gate (which treats `z.number()` ≡ `z.number().int()`, `_ZOD_BASE_TO_CLASS:32`). | strtd8's `sizeBytes`/`yearsExp`/token counts are all `z.number().int()` (`value-model.ts:48,169,183,189`); a `.int()`-less render passes Inc 4/5 yet diverges, defeating FR-9 structural equivalence. | §5 Inc 4 / §6 Inc 5 *Tests* | Assert rendered `Int?` field contains `.int()`; mutate renderer to drop it and assert the new assertion (not the gate) catches it. |
| R2-S3 | Data | high | §2 Inc 1 / §6 Inc 5: **remove the join-table-exclusion predicate (R1-S3) and emit 1 schema per model (12)**. `value-model.ts` renders all 3 join tables 1:1 (`ProofPointCapabilitySchema:195`, `ProofPointOutcomeSchema:208`, `CapabilityOutcomeSchema:221`). The "9" in R1-S3 is the composite aggregate's membership, not the schema count. | A join-table exclusion would delete 3 schemas the real file contains and fail Inc 5 in the opposite direction; the renderer's job is per-model, no special join-table logic. | §2 Inc 1; §6 Inc 5; supersedes R1-S3 | Assert rendered schema-name set == 12 model names; assert the 3 join-table schemas are **present**. |
| R2-S4 | Data | critical | §4 Inc 3 / §6 Inc 5: add a **composite-aggregate step**. `ValueModelSchema` (`value-model.ts:236-245`) + the `ValueModel` TS type (`:262-271`) aggregate `z.array(XSchema)` across models and omit AiCall + joins **by product decision** (`:233-234`). Decide: generate from a declared membership list, or mark seeded/out-of-scope. Inc 5's "structurally equivalent" assertion must scope around this or it fails on the composite. | A model-by-model renderer cannot produce a cross-model aggregate; this is the one real "not derivable from a single model" artifact in the file. | §4 Inc 3; §6 Inc 5 | Assert the 12 per-model schemas match; assert `ValueModelSchema` is either declared-from-membership or excluded with a recorded reason — not silently missing. |
| R2-S5 | Validation | critical | §5 Inc 4: add `verify_render_fidelity(rendered, schema, conventions) -> list[Issue]` **alongside** `assert_symmetric`, asserting the dimensions the symmetry checker provably ignores: per-field optional/nullable equality, `.int()` for `Int`, `z.array(...)` for lists, `z.enum([exact values])` for enums, `.email()`/`.url()` per convention, field count + order. The symmetry gate stays as the cross-check; fidelity is the by-construction proof. | `check_prisma_zod_symmetry` never compares optionality/`.int()`/list/enum-values/format-hints/ordering (`:252-348`); FR-3 "by construction" is unsound without a second assertion covering exactly those gaps. | §5 Inc 4 (new helper) | Mutate each dimension (flip `?`, drop `.int()`, drop `z.array`, wrong enum value); assert each is caught by `verify_render_fidelity`, not the symmetry gate. |
| R2-S6 | Ops | high | §9 Inc 8: give `--check` an **exit-code contract** (0=in-sync, 1=drift, 2=usage/parse/IO error) and a **two-stage** check: (1) compare embedded `schema-sha256` header (R1-S9) vs live schema hash → distinguishes "schema changed, regen needed"; (2) if hashes match, full render-and-diff → distinguishes "owned file hand-edited/tampered." Distinct codes let CI act differently on stale vs tampered. | A single boolean diff conflates two operationally distinct failures and gives CI no actionable branch; this is the standalone drift win (Focus 2/4) made precise. | §9 Inc 8 CLI; §12 risks | CI matrix: edit schema→exit 1 stale; edit owned file→exit 1 tampered; bad schema→exit 2; in-sync→exit 0. |
| R2-S7 | Ops | medium | §13 / §9 Inc 8: emit OTel via `metrics.get_meter("startd8.frontend_codegen")` with counters `models_rendered`/`fields_rendered`/`join_tables_rendered`/`unrenderable_fields`/`format_hints_applied` + a `drift_check` histogram — **mirroring `costs/otel_metrics.py:90-109`** (the SDK's `get_meter` + `create_counter`/`create_histogram` convention), not hand-rolled. | Focus 4 + R1-S10: a no-LLM generator still runs inside instrumented prime-contractor runs; reusing the costs-emitter shape keeps conventions consistent and is near-free. | §13 checklist; §9 Inc 8 | Assert a meter `startd8.frontend_codegen` records `models_rendered=12` on a strtd8 render. |
| R2-S8 | Risks | high | §10 Inc 9 / §0 sequencing: state the **pipeline-ordering invariant** — owned files are rendered, written to disk, and excluded from the feature set **before** Approach-A injection and **before** repair-retry's worklist runs. Add it now even though Inc 9 is deferred, because the standalone CLI (Inc 8) already produces owned files a real run must order around. | The requirements say "composes with" Approach A + repair-retry but never fix the order; an unordered compose lets repair-retry rewrite a correct owned file toward the LLM prior, re-introducing RUN-011. | §0; §10 Inc 9 sketch | Integration test: owned file present + flagged; assert repair-retry excludes it from its worklist and does not rewrite it. |
| R2-S9 | Risks | medium | §2 Inc 1: add **composite `type` block** handling. The parser stores `type` blocks in `models` with no marker (`prisma_parser.py:291`); a model-iterating `parse_models` emits a phantom `<Type>Schema` AND drops the composite-typed field (treated as a relation). Inc 1 must tag composite blocks (kind=`type`) and decide inline-object vs raise. | Double wrong-render, both gate-invisible (the phantom schema has no Prisma *model* match so the checker skips it, `:287-288`). strtd8 has no composites so Inc 5 never surfaces it. | §2 Inc 1; §12 risks | `type Geo {lat Float lng Float}` + `geo Geo`; assert `geo: z.object({...})` inlined or a raise — never a dropped field + phantom schema. |
| R2-S10 | Validation | medium | §6 Inc 5: add **synthetic-construct fixtures** to Inc 5 (or a sibling Inc) since strtd8 exercises **none** of the exotic surface — no enums, no scalar lists, no `@map`, no native types, no `Decimal`/`Bytes`, no composites, no self-relations (verified across all 12 models). The headline proves only the trivial `String/Int/Float/Boolean/DateTime` path. | The robustness the focus file worries about is never tested by the real schema; without synthetic fixtures the "invention impossible" claim is unproven for every construct that actually produces wrong-but-plausible output. | §6 Inc 5 / new Inc | A `test_construct_fidelity.py` with one fixture per construct (enum, `String[]`, `Decimal`, composite `type`, `@map`); each asserts the exact Zod render. |

##### Stress-test / adversarial pass (data-model surface — constructs that yield wrong-but-plausible Zod)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S11 | Risks | high | **Break case — scalar list `String[]` silently omitted.** The parser sets `is_list` (`prisma_parser.py:233`), but the symmetry checker classifies any `array`-class Zod field as a relation and `continue`s (`prisma_zod_symmetry.py:298`); and a renderer with no list branch in `render_field_base` (§2 only shows scalar + `?`) drops it. So a `tags String[]` column vanishes with no error and passes the gate. Add a list branch + assertion in Inc 1/3. | The §2 `render_field_base` signature handles only scalar + `.nullable()`; lists are unhandled and the gate is blind to them — a clean omission-by-construction. | §2 Inc 1 `render_field_base`; §4 Inc 3 | Fixture `tags String[]`; assert `z.array(z.string())` emitted; assert a dropped-list render is caught by `verify_render_fidelity` (R2-S5), since the symmetry gate won't. |
| R2-S12 | Risks | medium | **Break case — `@default`-as-`.optional()` corrupts every base schema.** A common Zod idiom maps `@default` → `.optional()`, but `value-model.ts:20-22` keeps defaulted fields **required** (`ownerId`/`source`/`confirmed`/`createdAt` are non-optional). If the convention layer (Inc 2) applies the idiom, all 12 schemas diverge — and the symmetry checker, blind to optionality (`:296-348`), passes them. Pin "defaulted base fields stay required" in Inc 2. | The most plausible convention-layer bug: a widely-used Zod pattern that is *wrong* for this project's base-vs-input split and gate-invisible. | §3 Inc 2 `apply_conventions` | Render `ownerId String @default("local")`; assert `z.string()` with no `.optional()`/`.nullable()`. |

**Endorsements** (prior untriaged R1 items this reviewer agrees with):
- R1-S1: the gate-signature fix is correct and blocking — `check_prisma_zod_symmetry(prisma, zod, ...)` takes parsed objects, args (prisma, zod) (`prisma_zod_symmetry.py:264`).
- R1-S2: the negative test must drop a *required, non-defaulted* scalar — verified the Prisma→Zod direction skips defaulted/id/optional (`:336-340`).
- R1-S4: parse-completeness guard against the lenient parser's silent drops (`:282`) is foundational.
- R1-S5: optionality equality is genuinely unchecked — R2-S5 folds it into the broader fidelity helper.
- R1-S7: `generate_tsconfig` emits a generic `src/**/*` config and is a `NodeProfile` instance method — confirmed the FR-5 `@/` alias conflict.
- R1-S8: mirror `artifact_generator`'s report/provenance shape for the manifest (Mottainai).
- R1-S9: schema-hash header — R2-S6 extends it to the stale-vs-tampered exit-code split.

**Disagreements** (untriaged prior items I would push back on, for triage):
- R1-S3: the count "12 models but 9 schemas, exclude 3 join tables" is **wrong** — `value-model.ts` has 12 model schemas including all 3 join tables (`:195,208,221`). Adopt the "fix the count" intent but **reject the join-table-exclusion predicate**; the correct rule is 1 schema per model (R2-S3). Per CRP, revisiting with cause: the stated rationale ("9 hand-authored schemas") does not match the file.

---

## Requirements Coverage Matrix — R2

| Requirement | Plan Step(s) | Coverage | Gaps (R2-specific) |
| ---- | ---- | ---- | ---- |
| FR-1 Prisma→Zod/TS renderer | Inc 1 (§2), Inc 3 (§4) | Partial | No list (`String[]`) branch in `render_field_base` (R2-S11); composite `type` blocks render phantom schemas (R2-S9); per-model count must be 12 incl. join tables (R2-S3). |
| FR-2 Convention layer | Inc 1 (§2), Inc 2 (§3) | Partial | `Decimal→z.string()` conflicts with the gate (R2-S1); `.int()` for `Int` unasserted (R2-S2); `@default`-as-`.optional()` idiom would corrupt base schemas (R2-S12); per-construct fidelity matrix missing (R2-S10). |
| FR-3 Symmetry-by-construction | Inc 4 (§5) | Partial | Gate is blind to optionality, `.int()`, list shape, enum values, format hints, ordering (`prisma_zod_symmetry.py:252-348`); needs `verify_render_fidelity` (R2-S5). |
| FR-4 Marker + idempotent | Inc 3 (§4) | Partial | Staleness needs the two-stage (hash then diff) stale-vs-tampered check (R2-S6 extends R1-S9). |
| FR-5 Project-convention detection | Inc 6 (§7) | Full | (R1 covered; no new R2 gap — `@map` name-divergence is a forward-looking note, R2-F11.) |
| FR-6 Gated skeletons | Inc 7 (§8) | Partial | (R1 covered the `scaffold_*`/tsconfig issues; no new R2 gap.) |
| FR-7 Owned/seeded ownership | Inc 7 (§8), Inc 8 (§9) | Partial | The composite `ValueModelSchema` is a natural **seeded** candidate (not single-model derivable) — decide ownership (R2-S4). |
| FR-8A CLI | Inc 8 (§9) | Partial | `--check` lacks an exit-code contract (R2-S6); OTel emitter shape unspecified (R2-S7). |
| FR-8C Pipeline seam | Inc 9 (§10, deferred) | Partial | Ordering invariant (generate→write→exclude before Approach-A + repair) unstated even though Inc 8 already produces owned files (R2-S8). |
| FR-9 strtd8 acceptance | Inc 5 (§6) | Partial | Proves only the trivial scalar path — strtd8 has no enum/list/`@map`/native/`Decimal`/composite (verified); needs synthetic fixtures (R2-S10); composite `ValueModelSchema` not single-model derivable (R2-S4); model count is 12, not 9 (R2-S3). |
| FR-10 No-LLM/idempotent | all (§11, NFR-1) | Partial | OTel counts (R2-S7) strengthen the determinism evidence; otherwise covered. |
| NFR-1…NFR-5 | §11/§13 | Partial | NFR-5 "symmetry-by-construction" is unsound without the fidelity self-check (R2-S5); NFR-4 owned-file inertness needs the pipeline-ordering invariant (R2-S8). |

---

## Requirements Coverage Matrix — R1

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 Prisma→Zod/TS renderer | Inc 1 (§2), Inc 3 (§4) | Partial | No field-completeness guard against the lenient parser's silent drops (R1-S4); join-table exclusion unaddressed (R1-S3); `outcomeId`-impossibility claim over-broad (R1-F5). |
| FR-2 Convention layer | Inc 1 (§2), Inc 2 (§3) | Partial | Enums, scalar arrays, native types, composite `type` blocks not in `SCALAR_MAP`/policy (R1-S11, R1-F2, R1-F10). |
| FR-3 Symmetry-by-construction | Inc 4 (§5) | Partial | Wrong gate signature (R1-S1); negative test too weak (R1-S2); checker blind to optionality + enum-as-string (R1-S5, R1-F3). |
| FR-4 Marker + idempotent | Inc 3 (§4) | Partial | No schema-hash staleness mechanism (R1-S9, R1-F9); optionality idempotence unasserted (R1-S5). |
| FR-5 Project-convention detection | Inc 6 (§7) | Full | Detection of `@/` alias, barrels, css-modules, types-dir covered; absence-as-signal covered. |
| FR-6 Gated skeletons | Inc 7 (§8) | Partial | `scaffold_*` are disk-mutating + need existing siblings + `generated_root`; ordering contract unspecified; `generate_tsconfig` emits wrong (`src/**/*`) config vs `@/` alias (R1-S7). |
| FR-7 Owned/seeded ownership | Inc 7 (§8), Inc 8 (§9) | Partial | Minimal owned-only v1 not carved out (R1-F8); OQ-4 seeded-regen clobber unresolved. |
| FR-8A CLI | Inc 8 (§9) | Partial | No `--check`/drift mode (R1-S6, R1-F7); manifest shape not aligned to artifact_generator (R1-S8). |
| FR-8C Pipeline seam | Inc 9 (§10, deferred) | Partial | Explicitly deferred; acceptable for v1 but drift-detection (R1-S6) should partially cover NFR-4 in the interim. |
| FR-9 strtd8 acceptance | Inc 5 (§6) | Partial | Proves only the trivial scalar path (no enums/arrays/native types in strtd8); "12 models" vs 9 schemas mismatch (R1-S3, R1-F4); robustness must be proven on synthetic fixtures (R1-S11, R1-S12). |
| FR-10 No-LLM/idempotent | all (§11, NFR-1) | Full | Zero-provider-import assertion + byte-stability tests cover it. |
| NFR-1…NFR-5 | §11/§13 | Partial | NFR-4 (owned files inert/no drift) has no enforcement before Inc 9 — `--check` (R1-S6) recommended as interim. |

#### Review Round R3 — claude-opus-4-8-1m — 2026-06-02

- **Scope**: value/integration/sequencing. **Full text + coverage matrix:** `CRP_ROUND_R3.md`.
- **Plan suggestions (triaged Batch 2 — Appendix A):** R3-S1 (**critical** — minimal pipeline hook
  via existing `_try_deterministic_file_shortcut` → new Inc 8b, ACCEPT); R3-S2 (run renderer beside
  `_build_project_knowledge`, ACCEPT); R3-S3 (split seeded into Inc 7b, ACCEPT); R3-S4 (alias
  detection before Inc 3, ACCEPT — reorder); R3-S5 (`--check` as the CLI's primary deliverable,
  ACCEPT); R3-S6 (operator-facing e2e, ACCEPT); R3-S7 (cross-module-import fixture in Inc 5,
  ACCEPT); R3-S8/R3-S9 (adversarial "correct generator, zero prevention" → §12 risk row + motivates
  8b, ACCEPT); R3-S10 (shared `FieldSpec` property test, ACCEPT).

#### Review Round R4 — claude-opus-4-8-1m — 2026-06-02

- **Scope**: adversarial red-team + test strategy. **Full text + fixture matrix + coverage:** `CRP_ROUND_R4.md`.
- **Plan suggestions (triaged Batch 2 — Appendix A):** R4-S1 (**REJECT R1-S3** join-table exclusion,
  ACCEPT-as-reject); R4-S2 (bare-`url` hint, ACCEPT); R4-S3 (type-guard hints, ACCEPT); R4-S4
  (synthetic fixture matrix before Inc 5, ACCEPT); R4-S5 (per-field flagged, not hard-fail, ACCEPT);
  R4-S6 (`--check` as pre-commit/CI with hash short-circuit, ACCEPT); R4-S7 (byte-idempotence
  determinism, ACCEPT); R4-S8 (parser-drift coupling test, ACCEPT); R4-S9 (Hypothesis round-trip +
  idempotence property test, ACCEPT); R4-S10 (negative test drops `Profile.name` specifically,
  ACCEPT — folded into Inc 4); R4-S11 (aggregate unrenderable into one report, ACCEPT).
- Fixture matrix (enum/array/composite/`@map`/native-type/self-relation/`@@id`/Decimal/optional-default)
  adopted as the Inc 1–3 `test_construct_fidelity.py` deliverable.

