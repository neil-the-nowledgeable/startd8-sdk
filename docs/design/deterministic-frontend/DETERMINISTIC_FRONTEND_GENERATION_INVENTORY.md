# Deterministic Frontend Generation — Capability Inventory

**Date:** 2026-06-02
**Purpose:** Establish *what we can generate deterministically (pure Python, no LLM)*
on a Next.js/React/TS frontend — to stop having the LLM produce mechanical artifacts
it gets wrong (canonical names, paths, schema-derived types, barrels) and reserve the
LLM for genuinely semantic work. Grounds `DETERMINISTIC_FRONTEND_GENERATION_REQUIREMENTS.md`.
**Evidence base:** the strtd8 frontend (`/Users/.../strtd8/strtd8`) + the failure history
(RUN-011 Prisma fields, RUN-012 CSS modules/barrels/types-dir, RUN-013 sub-namespaces) +
an audit of existing SDK deterministic-generation primitives.

---

## 1. The thesis

Three consecutive postmortems (RUN-011/012/013) each end the same way: the failures are
**canonical-name / mechanical-structure inventions** the LLM produces because it fills gaps
with training-distribution priors — and each concludes that the **structural fix is a
deterministic project-knowledge artifact, not better prompting.** We have been treating these
as a *repair* problem (fix after the LLM invents). This inventory asks the inverse: **how much
of the artifact is mechanical enough to generate deterministically and never hand to the LLM?**

The answer, grounded below: **a large fraction — and the SDK already has nearly every primitive.**

---

## 2. The determinism boundary (per artifact kind, grounded in strtd8)

| Frontend artifact | strtd8 reality | Deterministic? | SDK primitive that exists |
|-------------------|----------------|:--------------:|---------------------------|
| **Zod/TS types from the schema** (`lib/value-model.ts`) | A documented field-by-field **Prisma mirror** — docstring: *"the Prisma schema is the source of truth; these schemas must not invent, omit, or drift"* + an explicit mapping table | ✅ **fully** (it *is* a projection) | `prisma_parser.parse_prisma_schema` → `field_names`/`scalar_fields`/types/optionality; `render_prisma_field_sets` (grounding text). **Missing: the renderer** that emits the `z.object({…})` text |
| **Barrel / index files** (`index.ts` re-exporting a dir) | **0 exist** — yet RUN-012 PI-008 invented `@/components/wizard/steps` expecting one | ✅ fully | `repair/retry/scaffold.scaffold_barrel` (already built) |
| **CSS-module stubs** (`*.module.css`) | **0 exist** — RUN-012 invented 3 | ✅ (stub) | `repair/retry/scaffold.scaffold_cofile` (already built) |
| **Module-import paths** | `@/*` → `./*` (one alias) | ✅ resolvable | `resolve_specifier_to_paths`, `_resolves_on_disk`, the repair-retry `DiskTargetSearch` |
| **Directory structure / sub-namespaces** | flat `lib/export/{markdown,json}.ts` — RUN-013 invented `/renderers/` | ✅ (from the plan's file manifest) | the plan already names target files; no SDK gap, just don't let the LLM invent dirs |
| **`package.json` / `tsconfig.json`** | standard; `@/*` alias | ✅ fully | `languages/nodejs.generate_dependency_file`, `generate_tsconfig` (already built) |
| **API-route / page *shells*** (imports + handler signature) | uniform `export async function POST(req): Promise<Response>`; `export default function Page(): JSX.Element` | ◑ **boilerplate yes, body no** | template-able; the *structure* is mechanical, the *logic* is not |
| **Business logic / enrichment** (`lib/ai/*`, page UX, route algorithms) | semantic, varied | ❌ **LLM-needed** | — (this is the LLM's actual job) |

**Net:** rows 1–6 (schema types, barrels, CSS stubs, import paths, directory structure, config)
are **deterministically generatable** and are *exactly* the rows RUN-011/012/013 failed on. Only
the route/page *bodies* and `lib/ai/*` need the LLM.

---

## 3. The single highest-leverage piece: the Prisma→Zod/TS renderer

`lib/value-model.ts` is the clearest case and the RUN-011 root cause:

- It is **100% derivable** from `prisma/schema.prisma` (12 models) by a documented mapping
  (`String→z.string()`, `String?→.nullable()`, `DateTime→z.string().datetime()`, `Json→z.unknown()`,
  `@id→z.string()`, `email`→`.email()`, `*Url`→`.url()`, relations excluded).
- Today it is **LLM-generated and only checked post-hoc** by `validators/prisma_zod_symmetry.py`,
  whose own docstring is the load-bearing rationale: *"`tsc` cannot see field/type divergence between
  a Prisma `model` and a Zod `z.object` … a Zod schema can invent `profileId`, rename `summary`→`bio`,
  or type `value` as `number` where Prisma stores `String`, and the project still compiles."*
- So the project **invests in detecting drift** in a file that **shouldn't be hand/LLM-authored at all.**

**Every input exists** (`parse_prisma_schema` gives fields/types/optionality; the mapping is documented
in the target file's own header). The **only** missing component is a renderer:
`parse_prisma_schema(text) → z.object(...) text`. Build that, and the RUN-011 Prisma-field-invention
class is **eliminated by construction** — not detected, not repaired: never generated wrong.

---

## 4. We already do exactly this pattern elsewhere (precedent)

The SDK already deterministically emits structured files from a spec:
- `languages/nodejs.generate_dependency_file` / `generate_tsconfig` — `package.json` / `tsconfig.json` text.
- `observability/artifact_generator` — dashboards/alerts/SLOs + Grafana JSON.
- `dashboard_creator/generator.generate_dashboard_jsonnet` + `compiler.compile_jsonnet` — jsonnet→JSON.
- `repair/retry/scaffold.{scaffold_barrel,scaffold_cofile}` — barrels + CSS stubs.

A Prisma→Zod/TS renderer is the **same pattern** applied to frontend source — not a new capability
class, a new *target*.

---

## 5. What this is NOT (the LLM's irreducible job)

- `lib/ai/*` enrichment logic, the actual algorithms, page interaction/UX, route business logic.
- Anything requiring product judgment, copy, or non-mechanical structure.

The goal is **not** to deterministically generate the whole app — it's to **carve the mechanical
skeleton out of the LLM's hands** so the LLM writes logic *into a correct, schema-true skeleton*
instead of inventing the skeleton (and getting the canonical names wrong).

---

## 6. Implication for the design (feeds the requirements)

Two complementary shapes, in leverage order:

1. **Deterministic schema-types renderer** (Prisma→Zod/TS) — kills RUN-011 by construction; the one
   missing primitive; smallest, highest-leverage build.
2. **Deterministic skeleton generator** — given the plan's file manifest + schema + tsconfig, emit the
   mechanical artifacts (schema types, barrels, CSS stubs, config, directory structure, route/page
   *shells* with correct imports) **before/around** the LLM, so the LLM fills bodies into a skeleton
   whose names/paths/types are already canonical.

Both are *prevention by construction* — the structural fix all three postmortems named, realized as
generation rather than injection (Approach A) or repair (repair-retry). Repair-retry remains the
after-the-fact net for whatever still slips.

---

*Companion to `DETERMINISTIC_FRONTEND_GENERATION_REQUIREMENTS.md`. Bottom line: the mechanical
frontend surface that RUN-011/012/013 failed on is deterministically generatable, every primitive
exists except a Prisma→Zod renderer, and the SDK already emits structured files this way elsewhere.*
