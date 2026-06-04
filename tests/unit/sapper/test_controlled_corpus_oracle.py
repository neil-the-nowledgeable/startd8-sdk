"""FR-SAP-7 v0.8 — ControlledCorpusOracle + CompositeOracle + oracle_for_project corpus wiring."""

from __future__ import annotations

import pytest

from startd8.corpus.canonical import canonical_key
from startd8.corpus.models import TermObservation
from startd8.corpus.registry import ControlledCorpusRegistry
from startd8.paths import controlled_corpus_path
from startd8.sapper.ground_truth import (
    CompositeOracle,
    ControlledCorpusOracle,
    GroundTruthAnswer,
    GroundTruthQuestion,
    GroundTruthVerdict,
    NullOracle,
    oracle_for_project,
)
from startd8.sapper.models import AssumptionKind

pytestmark = pytest.mark.unit


def _registry_with(*entities: str) -> ControlledCorpusRegistry:
    reg = ControlledCorpusRegistry(project_id="test")
    obs = [
        TermObservation(
            kind="entity",
            canonical_key=canonical_key("entity", surface_form=name),
            surface_form=name,
            confidence="explicit",
        )
        for name in entities
    ]
    reg.merge_run("run-1", obs)
    return reg


def _q(symbol: str) -> GroundTruthQuestion:
    return GroundTruthQuestion(assumption_id="a", kind=AssumptionKind.MODULE_SOURCE, claim="c", symbol=symbol)


# --- ControlledCorpusOracle ---------------------------------------------------


def test_canonical_entity_is_validated():
    oracle = ControlledCorpusOracle(_registry_with("CartService", "Cart"))
    ans = oracle.answer(_q("Cart"))
    assert ans.verdict is GroundTruthVerdict.VALIDATED
    assert "canonical" in ans.evidence


def test_near_miss_is_refuted_with_suggestion():
    oracle = ControlledCorpusOracle(_registry_with("Matches"))
    ans = oracle.answer(_q("Match"))            # invented, but close to canonical "Matches"
    assert ans.verdict is GroundTruthVerdict.REFUTED
    assert "Matches" in ans.evidence


def test_unrelated_symbol_omits_not_refutes():
    # Conservative: absence alone is not refutation (the corpus may be incomplete).
    oracle = ControlledCorpusOracle(_registry_with("Cart", "Checkout"))
    assert oracle.answer(_q("Zzzphabet")).verdict is GroundTruthVerdict.OMIT


def test_dotted_symbol_uses_last_segment():
    oracle = ControlledCorpusOracle(_registry_with("Cart"))
    assert oracle.answer(_q("app.tables.Cart")).verdict is GroundTruthVerdict.VALIDATED


# --- CompositeOracle ----------------------------------------------------------


def test_composite_first_non_omit_wins():
    corpus = ControlledCorpusOracle(_registry_with("Cart"))
    composite = CompositeOracle([corpus, NullOracle()])
    assert composite.answer(_q("Cart")).verdict is GroundTruthVerdict.VALIDATED


def test_composite_falls_through_omit_to_next():
    class AlwaysValidated:
        def answer(self, q):
            return GroundTruthAnswer(GroundTruthVerdict.VALIDATED, evidence="from #2")

    composite = CompositeOracle([NullOracle(), AlwaysValidated()])
    ans = composite.answer(_q("anything"))
    assert ans.verdict is GroundTruthVerdict.VALIDATED and ans.evidence == "from #2"


def test_composite_skips_raising_oracle():
    class Boom:
        def answer(self, q):
            raise RuntimeError("boom")

    composite = CompositeOracle([Boom(), ControlledCorpusOracle(_registry_with("Cart"))])
    assert composite.answer(_q("Cart")).verdict is GroundTruthVerdict.VALIDATED


# --- oracle_for_project (corpus resolved from the target project) -------------


def test_oracle_for_project_consults_the_projects_corpus(tmp_path):
    # Place a corpus where controlled_corpus_path() resolves it for this project.
    corpus_path = controlled_corpus_path(tmp_path)
    corpus_path.parent.mkdir(parents=True, exist_ok=True)
    _registry_with("CartService", "Cart").save(corpus_path)

    oracle = oracle_for_project(str(tmp_path))
    assert not isinstance(oracle, NullOracle)
    assert oracle.answer(_q("Cart")).verdict is GroundTruthVerdict.VALIDATED


def test_oracle_for_project_no_corpus_no_schema_is_null(tmp_path):
    # No corpus, no Prisma/TS → nothing to back the oracle → NullOracle.
    assert isinstance(oracle_for_project(str(tmp_path)), NullOracle)
