"""CKG Phase 2 — Knowledge Provider (read-only, pre-generation contract injection).

A deterministic **view over the Phase-1 resolver** (CROSS_FILE §11) that injects
the project's authoritative contract surface — real Prisma field sets, canonical
module paths + explicit negatives, omissions — into a feature's spec prompt
*before* generation, so the drafter uses real fields/paths instead of inventing
them. Detection (Phase 1 Verifier) verifies; this (Phase 2) prevents.

See `docs/design/CODE_KNOWLEDGE_GRAPH_PHASE2_KNOWLEDGE_PROVIDER_REQUIREMENTS.md`.
"""

from __future__ import annotations

from .models import (
    EnumAuthority,
    FieldSetAuthority,
    FieldSpec,
    Negative,
    ProjectKnowledge,
)
from .negatives import SEEDED_NEGATIVES, relevant_negatives
from .producer import (
    DraftModeProducer,
    ProjectKnowledgeProducer,
    canonical_specifier,
)
from .render import estimate_tokens, render
from .scoping import module_closure, referenced_entities

__all__ = [
    "FieldSpec",
    "FieldSetAuthority",
    "EnumAuthority",
    "Negative",
    "ProjectKnowledge",
    "ProjectKnowledgeProducer",
    "DraftModeProducer",
    "canonical_specifier",
    "SEEDED_NEGATIVES",
    "relevant_negatives",
    "module_closure",
    "referenced_entities",
    "render",
    "estimate_tokens",
]
