"""REQ-19 FR-1 / FR-7 — the realization-provenance contract (the modularity firewall).

The contract is the SOLE coupling surface between construction and the navigator. A malformed record fails
loud with a named error; the navigator's realization modules import ONLY this contract, never a
construction subsystem (AST-checked); and a schema drift fails this contract test (the reviewed coupling event).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from startd8.navigator.realization_contract import (
    RealizationContractError,
    RealizationRecord,
    make_record,
    parse_record,
)


def test_valid_record_parses_and_roundtrips():
    rec = parse_record({"file": "src/x.py", "regime": "llm", "source_confidence": 0.9,
                        "provenance": {"model": "claude-opus-4-8", "strategy": "class", "cost": 0.01}})
    assert isinstance(rec, RealizationRecord)
    assert rec.file == "src/x.py" and rec.regime == "llm" and rec.source_confidence == 0.9
    assert rec.provenance.model == "claude-opus-4-8"
    # deterministic record carries no provenance detail → omitted from the dict form
    assert "provenance" not in parse_record({"file": "a.py", "regime": "deterministic", "source_confidence": 1.0}).to_dict()


@pytest.mark.parametrize("bad,needle", [
    ({"regime": "llm", "source_confidence": 1.0}, "file"),                       # missing file
    ({"file": "", "regime": "llm", "source_confidence": 1.0}, "file"),           # empty file
    ({"file": "a", "regime": "banana", "source_confidence": 1.0}, "regime"),     # bad regime
    ({"file": "a", "regime": "unknown", "source_confidence": 1.0}, "regime"),    # unknown is not declarable
    ({"file": "a", "regime": "llm", "source_confidence": 1.5}, "source_confidence"),  # out of [0,1]
    ({"file": "a", "regime": "llm", "source_confidence": "hi"}, "source_confidence"), # not a number
    ({"file": "a", "regime": "llm", "source_confidence": True}, "source_confidence"), # bool is not a confidence
])
def test_malformed_record_rejected_with_named_error(bad, needle):
    with pytest.raises(RealizationContractError) as exc:
        parse_record(bad)
    assert needle in str(exc.value)


def test_make_record_emits_validated_conforming_dict():
    """FR-2 emit helper: a construction path builds a validated record; a bad emit fails loud at source."""
    d = make_record("app/models.py", "deterministic", 1.0)
    assert d == {"file": "app/models.py", "regime": "deterministic", "source_confidence": 1.0}
    with pytest.raises(RealizationContractError):
        make_record("app/models.py", "not-a-regime", 1.0)


def test_fr7_navigator_realization_imports_only_the_contract_never_construction():
    """FR-7 (NR-3): the navigator's realization modules import the contract + navigator-internal only —
    never backend_codegen / contractors / micro_prime. Inspected via AST (docstrings may name them)."""
    forbidden = ("backend_codegen", "contractors", "micro_prime")
    nav = Path(__file__).parents[3] / "src" / "startd8" / "navigator"
    for mod in ("realization.py", "realization_provenance.py", "realization_contract.py"):
        src = (nav / mod).read_text()
        imported = []
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                imported += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        assert not [m for m in imported if any(f in m for f in forbidden)], \
            f"{mod} must not import a construction subsystem; imports: {imported}"


# ── FR-3 — the normalizer (deterministic conflict resolution) ──────────────────────────────────────

def test_normalize_one_record_per_file():
    from startd8.navigator.realization_provenance import normalize
    m = normalize([
        {"file": "a.py", "regime": "deterministic", "source_confidence": 1.0},
        {"file": "b.py", "regime": "llm", "source_confidence": 0.8, "provenance": {"model": "x"}},
    ])
    assert set(m) == {"a.py", "b.py"}
    assert m["a.py"].regime == "deterministic" and m["b.py"].provenance.model == "x"


def test_normalize_resolves_conflict_by_confidence_then_priority():
    """FR-3: two sources disagreeing on a file resolve deterministically — higher confidence wins; a
    confidence tie breaks on the fixed regime priority (never input order)."""
    from startd8.navigator.realization_provenance import normalize
    # higher confidence wins
    m = normalize([
        {"file": "a.py", "regime": "llm", "source_confidence": 0.6},
        {"file": "a.py", "regime": "deterministic", "source_confidence": 0.95},
    ])
    assert m["a.py"].regime == "deterministic"
    # tie → fixed priority (human < llm < deterministic), order-independent
    forward = normalize([{"file": "a.py", "regime": "deterministic", "source_confidence": 0.5},
                         {"file": "a.py", "regime": "llm", "source_confidence": 0.5}])
    reverse = normalize([{"file": "a.py", "regime": "llm", "source_confidence": 0.5},
                         {"file": "a.py", "regime": "deterministic", "source_confidence": 0.5}])
    assert forward["a.py"].regime == reverse["a.py"].regime == "llm"  # llm outranks deterministic on tie


def test_load_provenance_missing_file_is_empty_map():
    from startd8.navigator.realization_provenance import load_provenance
    assert load_provenance(Path("/nonexistent/prov.json")) == {}


def test_load_provenance_reads_records(tmp_path):
    import json
    from startd8.navigator.realization_provenance import load_provenance
    p = tmp_path / "prov.json"
    p.write_text(json.dumps({"records": [{"file": "x.py", "regime": "llm", "source_confidence": 0.9}]}))
    m = load_provenance(p)
    assert m["x.py"].regime == "llm"


# ── FR-2 — the generation paths emit conforming records ────────────────────────────────────────────

def test_fr2_deterministic_path_emits_deterministic_records():
    from startd8.backend_codegen.realization_emit import deterministic_records
    recs = deterministic_records(["app/models.py", "app/crud.py", "app/models.py"])  # dupe dropped
    assert [r["file"] for r in recs] == ["app/models.py", "app/crud.py"]
    assert all(r["regime"] == "deterministic" and r["source_confidence"] == 1.0 for r in recs)
    # every emitted record round-trips through the contract (conforming by construction)
    for r in recs:
        parse_record(r)


def test_fr2_llm_path_emits_llm_records_with_model():
    from startd8.micro_prime.realization_emit import llm_record
    from startd8.navigator.realization_contract import RealizationContractError
    r = llm_record("app/service.py", model="claude-opus-4-8", strategy="class", confidence=0.9, cost=0.02)
    assert r["regime"] == "llm" and r["provenance"]["model"] == "claude-opus-4-8"
    parse_record(r)                                    # conforming
    with pytest.raises(RealizationContractError):
        llm_record("app/x.py", model="")               # an llm record MUST carry a model
