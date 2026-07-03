# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""The `$0` deterministic requirements baseline (FR-RP-1 — persona-less, no LLM).

From the brief + on-disk schema, scaffold a starting requirements doc: a Problem-Statement note, an
**entity-touching FR stub per primary entity**, and standard NR/OQ headings. It never invents intent —
every stub carries the ``<needs-owner>`` placeholder (so the readiness gate blocks approving it
un-owned). This is the "manifest suggester without a designated persona" alternative — always cheap,
always safe.

**"Primary entity" is deterministic (R2-F5):** a parsed ``PrismaModel`` **excluding** join tables,
detected via a compound ``@@id`` PK over relation FKs with no single ``@id`` field — using
``PrismaModel.block_attributes`` / ``compound_unique_keys`` (``prisma_parser.py:100-111``). No LLM.
"""

from __future__ import annotations

from typing import List

from startd8.languages.prisma_parser import (
    PrismaModel,
    PrismaSchema,
    parse_prisma_schema,
)

from startd8.requirements_panel.models import (
    NEEDS_OWNER,
    PROV_BASELINE,
    RequirementCandidate,
    RequirementDoc,
)

__all__ = ["is_join_table", "primary_entities", "scaffold"]


def is_join_table(model: PrismaModel) -> bool:
    """True iff *model* is a pure join table: a compound ``@@id`` PK and no single-column ``@id``.

    A join model's identity is a composite over its relation FKs — emitting a CRUD FR stub for it is
    noise, so the baseline drops it (R2-F5).
    """
    has_compound_id = any(a.startswith("@@id") for a in model.block_attributes)
    has_single_id = any(f.is_id for f in model.fields)
    return has_compound_id and not has_single_id


def primary_entities(schema: PrismaSchema) -> List[PrismaModel]:
    """Domain models in schema-declaration order, excluding join tables (R2-F5)."""
    return [m for m in schema.models.values() if not is_join_table(m)]


def scaffold(brief: str, schema_text: str, *, session_id: str = "") -> RequirementDoc:
    """Build the `$0` baseline doc from *brief* + *schema_text*. Deterministic, no LLM."""
    schema = parse_prisma_schema(schema_text or "")
    candidates: List[RequirementCandidate] = []
    for model in primary_entities(schema):
        title = f"Manage {model.name} records"
        candidates.append(
            RequirementCandidate(
                area="data",
                title=title,
                body=(
                    f"The system MUST let an authorized user create, read, update, and delete "
                    f"{model.name} records. {NEEDS_OWNER}"
                ),
                rationale=f"{model.name} is a primary entity in the schema.",
                entities_referenced=(model.name,),
                provenance=PROV_BASELINE,
                session_id=session_id,
            )
        )

    problem = (
        ((brief.strip() + "\n\n") if brief and brief.strip() else "")
        + f"Scaffolded from {len(candidates)} primary schema entities. Owners still needed."
    )

    return RequirementDoc(
        title="Requirements (draft)",
        problem=problem,
        candidates=candidates,
        non_requirements=[
            "Real product content / copy (bucket-4 — the company's).",
            "The implementation plan and code (separate artifacts).",
        ],
        open_questions=[
            "Which non-entity screens/flows does the product need? (elicit with --roles)",
        ],
    )
