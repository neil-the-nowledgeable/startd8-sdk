# Architect — Draft Template (FR-J9 a)

> The **generated-draft** the architect starts from and refines. Per HITM §3.3, architecture
> *options* are LLM-draftable (tier G); the **choice** and the **contract design** are the
> architect's (tier U/E). This template names the three deliverables of the DATA MODEL bookend —
> it does not restate their schemas (cite the canonical homes).

## 1. Convention manifest (`conventions.yaml`)
The frameworks + conventions the cascade will assume. Draft from the requirements; the architect
picks for *this* business.
- **Draft it with:** `startd8 generate` conventions scaffold (the deterministic projection).
- **Decide (U/E):** persistence framework · display framework (SPA vs server-render) · language ·
  auth posture · naming/layout conventions.
- **Canonical schema:** the kickoff conventions input (Group A–E, `kickoff/ASSEMBLY_INPUTS_TEMPLATE.md`).

## 2. Contract (`schema.prisma`)
The data model — the single most consequential architect artifact (it drives ~89% of the cascade).
- **Draft it with:** the requirements + `startd8 generate contract` (where available).
- **Decide (U/E):** entities, relations, ownership/`human_inputs`, the composite `views.yaml` shape.
- **Preview the consequences before approving:** `startd8 wireframe --project <root>` — the
  pre-generation shape (entities → CRUD, pages, forms, views) *and what's still `not_defined`*.

## 3. Architecture Decision Records (ADRs)
One short ADR per non-obvious choice (why this framework, why this contract shape, what was
rejected). Reuse the CRP **Appendix A/B** disposition pattern (accepted / rejected + rationale) so
the reasoning is durable cross-model memory.

---
*Fill order: contract → conventions → ADRs. The contract is the anchor; conventions and ADRs
justify and frame it. Then take it to the [review checklist](./review-checklist.md).*
