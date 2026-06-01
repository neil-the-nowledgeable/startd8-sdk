# Where review input matters most — Approach A (Project-Knowledge Artifact)

Weight the review toward these five concerns:

1. **FR-2 CodeGraph-convergence schema (R4).** Is the `ProjectKnowledge` pydantic
   shape (models / module_paths / invalid_module_paths / packages / tsconfig /
   file_exports) the right contract for a future Mieruka `CodeGraph` producer to
   return — or does it bake in SDK-only assumptions that would force a rewrite? This
   is the load-bearing "converge on schema, not implementation" decision.

2. **S5 refactor risk.** Subsuming the shipped Mode-A/Mode-B inheritance + the
   heuristic-gated FR-3 Prisma injection into one artifact-sourced path. Is "keep the
   existing Mode-A/B tests green" a sufficient gate, or are there behaviors
   (`_collect_upstream_interfaces` edge cases, absent-anchor warnings, Mode-A
   not-yet-generated producers) that the refactor could silently change?

3. **OQ-4 adherence (R1).** Will a P0 section + explicit negatives + "use only these
   fields" actually move the LLM off its canonical-name prior, or is injection
   necessary-but-insufficient? Is the FR-8 reproduction harness a strong enough
   measurement, and what's the escalation if adherence measures weak?

4. **OQ-2 relevance scoping.** The whole-schema-when-≤12-models fallback vs
   import-closure scoping — token cost vs completeness. Is the entity-name match
   (target_files + description) robust, or will it miss entities a feature touches
   transitively?

5. **FR-4 negatives.** Seeding the recurring inventions (`@/lib/prisma`,
   `@/lib/db/<model>`, `@/lib/ai/client`) — is a hard-seeded negative list the right
   mechanism, or does it need to be derived to generalize beyond strtd8?

Also flag any FR without a testable acceptance criterion, and any plan step (S1–S7)
that is not traceable to an FR.
