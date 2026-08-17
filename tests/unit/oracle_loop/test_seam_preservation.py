"""FR-9 — additive / seam-preserving: the loop reuses classify/sandbox/ladder/Prime seams and
leaves the navigator oracle allow-list + goldens untouched.
"""

from __future__ import annotations

import inspect

import pytest

from startd8.navigator import verify_oracle

pytestmark = pytest.mark.unit


def test_navigator_allowlist_unchanged():
    """The navigator read-only allow-list + write-flag guard are the shipped values (NR-2)."""
    assert verify_oracle._ALLOWED_VERBS == frozenset({"startd8"})
    assert verify_oracle._READONLY_NAV_SUBCOMMANDS == frozenset(
        {"build", "view-definition", "govern"}
    )
    assert verify_oracle._WRITE_FLAGS == frozenset({"--out", "--fix"})


def test_oracle_loop_imports_the_sandbox_seam_not_reimpl():
    from startd8.oracle_loop import runner

    src = inspect.getsource(runner)
    assert "from ..benchmark_matrix.sandbox import" in src
    # Must reuse the sandbox entries, not define its own subprocess isolation.
    assert "run_sandboxed" in src and "run_service_sandboxed" in src
    assert "subprocess.run" not in src  # no re-implemented exec


def test_oracle_loop_imports_the_ladder_seam():
    from startd8.deploy_harness import ladder

    # The typed per-FR verdict home reuses the oracle_loop OracleVerdict (extends, not forks).
    assert "oracle_verdicts" in ladder.LadderResult.model_fields


def test_oracle_verdict_is_a_new_model_not_the_navigator_dataclass():
    """The loop's OracleVerdict is a NEW Pydantic model reusing only the VERDICT_* strings."""
    from pydantic import BaseModel

    from startd8.oracle_loop import OracleVerdict as LoopVerdict

    assert issubclass(LoopVerdict, BaseModel)
    assert LoopVerdict is not verify_oracle.OracleVerdict
    # It carries the FR-7 stateful disposition the navigator dataclass does not.
    assert "assertion_confirmed" in LoopVerdict.model_fields


def test_loop_does_not_route_to_repair():
    from startd8.oracle_loop import loop

    src = inspect.getsource(loop)
    assert "run_file_repair" not in src
    assert "repair" not in src.lower().replace("regenerate", "")  # only regen, never repair
