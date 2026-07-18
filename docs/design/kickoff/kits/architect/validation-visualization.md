# Architect — The Visualization Layer of Validation (FR-J9 c, deepened)

> **How the architect actually reviews** the convention manifest + contract at the DATA MODEL
> bookend — not by reading raw output, but through a **visualization layer** that makes the planned
> shape *glance-approvable*. This is where the session's whole visualization thread lands: the
> architect is **who the Requirements Navigator was built for**, and their approval is its
> **acceptance test**. Companion to [`validation.md`](./validation.md).

## The three layers the architect looks through

```
contract + conventions ──▶ WIREFRAME ──▶ DESCRIPTIVE LAYER ──▶ NODE NAVIGATOR
   (the artifact)          (the shape)    (the meta layer)      (glance / drill)
   schema.prisma +         startd8         FR-DL: what/why/do/   NODE-SCHEMA: fsn-colored
   conventions.yaml        wireframe       next per section      by definition-status,
                           (data, $0)      (single-sourced)      browse/drill/facet
```

1. **Wireframe (data).** `startd8 wireframe --project <root>` — the deterministic planned shape
   (entities→CRUD, pages, forms, views) + the five definition statuses (`planned / defaults /
   placeholder / not_defined / invalid`). Raw, on its own: *"no meta layer"* — the exact gap that
   started this.
2. **Descriptive layer (meaning).** `FR-DL-*` (`startd8-sdk/docs/design/descriptive-layer/`) wraps
   each planned section with **WHAT / WHY / DO / NEXT** + `route_state`, so the architect sees not
   just *"views: not_defined"* but *"no composite views will exist → if the user works across
   entities, author `views.yaml` → here's the command."*
3. **Node navigator (the review UI).** `NODE-SCHEMA.md` — the planned shape as a **colored
   landscape** (definition-status → color, à la fsn), browse/drill to the `schema.prisma` line
   (`lives`), facet by section. The architect *flies over* the shape and *drills* where risk is.

## Glance-approve criteria (what the architect confirms at a glance)
- [ ] **Shape matches intent** — the entity/CRUD/page/form/view landscape is the app the business asked for.
- [ ] **Every `not_defined` is a *decision*, not a miss** — each undefined section is visibly flagged
      and *intentionally* deferred (the descriptive layer's `route_state: declared_unimplemented`,
      not a silent hole).
- [ ] **No `invalid`** — nothing the contract declares fails to parse/derive.
- [ ] **Drill confirms** — any surprising section drills to its `schema.prisma` line and reads right.
- [ ] **A customer wouldn't be surprised** — the visualized shape is defensible as *this* business's.

Approve → record per [`validation.md`](./validation.md) (hash-bound, FR-J3). The visualization is
the *medium*; the convention manifest + contract is still the artifact approved.

## The reciprocal: this is the visualization layer's acceptance test
The architect's DATA MODEL bookend is not only *served by* the visualization layer — it **validates
it**. The acceptance criterion for the entire NODE-SCHEMA / FR-DL / navigator body of work is:

> **Can an architect approve the planned shape at a glance, and confidently reject or flag when it's
> wrong?** If yes, the visualization layer works. If not — if it reads as a raw wall (the original
> wireframe) — it has failed, no matter how elegant the grammar.

So the Architect kit is where the visualization layer earns its keep: a *read/approve* node
consumer (per NODE-SCHEMA §7 — the read counterpart to the benchmark reviewer's write node), in the
**visual** modality (invariant 8; the same review is also renderable as the *spoken* planned shape
for a non-visual architect).

## Cited (not copied)
- Wireframe (data) → `wireframe/WIREFRAME_REQUIREMENTS.md` · Descriptive layer → `startd8-sdk/docs/design/descriptive-layer/`
- Node grammar → `dev-os/NODE-SCHEMA.md` (fsn rendering §4, read/write §7, modality inv. 8)
- Rendered navigators (the pattern) → `kickoff/README.md`, `wireframe/README.md`

---
*Deepens the Architect kit from "names a validation artifact" to "names **how** the artifact is made
glance-approvable" — and, in doing so, gives the visualization layer its first named acceptance
test and its archetypal read/approve user.*
