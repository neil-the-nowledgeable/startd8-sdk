"""REQ-CKG-522 / D2 — seeded explicit negatives, gated to real project modules."""

from __future__ import annotations

from startd8.contractors.project_knowledge import SEEDED_NEGATIVES, relevant_negatives
from startd8.contractors.project_knowledge.negatives import Negative


def test_seeds_cover_the_observed_recurrences():
    invented = {n.invented for n in SEEDED_NEGATIVES}
    assert "@/lib/prisma" in invented  # 3 recurrences RUN-008/009/011
    assert "@/lib/ai/client" in invented


def test_kept_when_replacement_is_a_real_module():
    out = relevant_negatives(["@/lib/db"])
    assert any(n.invented == "@/lib/prisma" and n.correct == "@/lib/db" for n in out)


def test_dropped_when_replacement_absent_from_project():
    # project has @/lib/db but no AI service → don't tell the model to use one
    out = relevant_negatives(["@/lib/db"])
    assert all(n.correct != "@/lib/ai/service" for n in out)


def test_no_known_modules_keeps_all_seeds():
    # nothing resolved yet → keep the well-attested seeds (warn rather than miss)
    assert relevant_negatives([]) == list(SEEDED_NEGATIVES)


def test_custom_seed_respected():
    seeds = (Negative(invented="@/utils/foo", correct="@/utils/bar"),)
    assert relevant_negatives(["@/utils/bar"], seeds=seeds) == list(seeds)
    assert relevant_negatives(["@/other"], seeds=seeds) == []
