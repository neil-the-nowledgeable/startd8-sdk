"""FR-2 — runnable-Verify grammar + its own parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.navigator import verify_oracle
from startd8.oracle_loop.grammar import (
    KIND_ASSERTION,
    KIND_MANUAL,
    KIND_ONESHOT,
    KIND_SERVICE,
    ProbeSpec,
    parse_spec,
    parse_verify_clause,
)

pytestmark = pytest.mark.unit

_FIX = Path(__file__).parent / "fixtures"


def test_pytest_clause_is_oneshot_and_maps_to_argv():
    c = parse_verify_clause("FR-1", "Verify: `pytest tests/test_health.py -q` exits 0.")
    assert c.kind == KIND_ONESHOT
    assert c.is_runnable
    assert c.command_argv == ("pytest", "tests/test_health.py", "-q")


def test_classify_would_yield_assertion_for_pytest_proving_reuse_fails():
    """The load-bearing R1-F2 claim: navigator classify() cannot extract a pytest clause."""
    descriptors = verify_oracle.classify(_FIX / "passing_spec.md")
    by_id = {d.fr_id: d for d in descriptors}
    # FR-1 is a pytest one-shot for the loop; navigator classify sees it as a bare assertion.
    assert by_id["FR-1"].kind == verify_oracle.KIND_ASSERTION
    # ...while the FR-2 grammar classifies the SAME clause as runnable.
    loop_clause = parse_verify_clause("FR-1", by_id["FR-1"].assertion_text)
    assert loop_clause.kind == KIND_ONESHOT


def test_probe_clause_is_data_only_service_struct():
    c = parse_verify_clause("FR-2", "Verify: probe `GET /health -> 200` — live.")
    assert c.kind == KIND_SERVICE
    assert c.probe == ProbeSpec(method="GET", path="/health", expected_status=200, body=None)


def test_probe_with_json_body():
    c = parse_verify_clause("FR-3", 'Verify: probe `POST /items body={"name":"x"} -> 201`.')
    assert c.kind == KIND_SERVICE
    assert c.probe.body == {"name": "x"}
    assert c.probe.expected_status == 201


def test_probe_rejects_injected_client_code_at_parse_time():
    """R1-F3: a clause trying to inject client code must not become runnable."""
    c = parse_verify_clause("FR-9", "Verify: probe `GET /x lambda: __import__('os') -> 200`.")
    assert c.kind == KIND_MANUAL
    assert c.probe is None


def test_probe_rejects_non_json_body():
    c = parse_verify_clause("FR-9", "Verify: probe `POST /x body=not-json -> 201`.")
    assert c.kind == KIND_MANUAL


def test_probe_rejects_bad_method_and_status():
    assert parse_verify_clause("FR-9", "Verify: probe `FETCH /x -> 200`.").kind == KIND_MANUAL
    assert parse_verify_clause("FR-9", "Verify: probe `GET /x -> 999`.").kind != KIND_SERVICE


def test_prose_clause_is_assertion_residue():
    c = parse_verify_clause("FR-4", "Verify: a reviewer confirms the factory pattern.")
    assert c.kind == KIND_ASSERTION
    assert not c.is_runnable


def test_multi_command_span_rejected_as_manual():
    c = parse_verify_clause("FR-5", "Verify: `pytest a` and `pytest b` two spans.")
    assert c.kind == KIND_MANUAL
    c2 = parse_verify_clause("FR-5", "Verify: `pytest a && pytest b`.")
    assert c2.kind == KIND_MANUAL


def test_console_script_token_is_oneshot():
    c = parse_verify_clause("FR-8", "Verify: `selfcheck --all` exits 0.")
    assert c.kind == KIND_ONESHOT
    assert c.is_console_script


def test_parse_spec_over_fixture():
    clauses = parse_spec(_FIX / "passing_spec.md")
    kinds = {c.fr_id: c.kind for c in clauses}
    assert kinds == {"FR-1": KIND_ONESHOT, "FR-2": KIND_SERVICE, "FR-3": KIND_ASSERTION}
