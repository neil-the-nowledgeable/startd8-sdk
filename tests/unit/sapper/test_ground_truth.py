"""Phase 4 — FDE query interface (FR-SAP-7)."""

from __future__ import annotations

import pytest

from startd8.sapper.ground_truth import (
    CachingOracle,
    GroundTruthAnswer,
    GroundTruthQuestion,
    GroundTruthVerdict,
    NullOracle,
    ProjectKnowledgeOracle,
)
from startd8.sapper.models import AssumptionKind

pytestmark = pytest.mark.unit


def _q(kind, module="", symbol=""):
    return GroundTruthQuestion(assumption_id="a1", kind=kind, claim="c", module=module, symbol=symbol)


def test_null_fde_always_omits():
    ans = NullOracle().answer(_q(AssumptionKind.FRAMEWORK_IDIOM))
    assert ans.verdict is GroundTruthVerdict.OMIT


def test_project_knowledge_fde_refutes_known_negative():
    from startd8.contractors.project_knowledge.models import Negative, ProjectKnowledge

    pk = ProjectKnowledge(
        project_root=".",
        field_sets=(),
        interfaces=(),
        negatives=(Negative(invented="app.models", correct="app.tables", note="tables live here"),),
        enums=(),
        omissions=(),
    )
    fde = ProjectKnowledgeOracle(pk)
    ans = fde.answer(_q(AssumptionKind.MODULE_SOURCE, module="app.models"))
    assert ans.verdict is GroundTruthVerdict.REFUTED
    assert "app.tables" in ans.evidence


def test_project_knowledge_fde_omits_unknown_module():
    from startd8.contractors.project_knowledge.models import ProjectKnowledge

    pk = ProjectKnowledge(
        project_root=".", field_sets=(), interfaces=(), negatives=(), enums=(), omissions=()
    )
    ans = ProjectKnowledgeOracle(pk).answer(_q(AssumptionKind.MODULE_SOURCE, module="whatever"))
    assert ans.verdict is GroundTruthVerdict.OMIT


def test_framework_idiom_omits_on_python_graph():
    from startd8.contractors.project_knowledge.models import ProjectKnowledge

    pk = ProjectKnowledge(
        project_root=".", field_sets=(), interfaces=(), negatives=(), enums=(), omissions=()
    )
    ans = ProjectKnowledgeOracle(pk).answer(_q(AssumptionKind.FRAMEWORK_IDIOM))
    assert ans.verdict is GroundTruthVerdict.OMIT


def test_caching_fde_queries_inner_once():
    class Counting:
        def __init__(self):
            self.calls = 0

        def answer(self, question):
            self.calls += 1
            return GroundTruthAnswer.omit()

    inner = Counting()
    cached = CachingOracle(inner)
    q = _q(AssumptionKind.MODULE_SOURCE, module="m")
    cached.answer(q)
    cached.answer(q)
    assert inner.calls == 1, "identical question must hit cache on the second call (R4-F5)"
