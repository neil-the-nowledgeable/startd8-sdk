"""Python (and general) missing-dependency import classifier — Tier-1 fairness analog of the
Java/C# missing-dep degrade. A gRPC/protobuf/proto-stub import absent in the offline sandbox is
not the model's fault → excluded, not catastrophic."""
import pytest

from startd8.benchmark_matrix.scoring import is_missing_deps_failure
from startd8.benchmark_matrix.runner import STATUS_DEPS_MISSING, STATUS_FAILED, CellResult
from startd8.benchmark_matrix.aggregate import summarize_group


@pytest.mark.parametrize("err,expected", [
    ("1 file(s) have import errors: email_server.py: ModuleNotFoundError: No module named 'demo_pb2'", "demo_pb2"),
    ("ModuleNotFoundError: No module named 'grpc_health'", "grpc_health"),
    ("No module named 'grpc'", "grpc"),
    ("No module named 'demo_pb2_grpc'", "demo_pb2_grpc"),
    ("No module named 'google.protobuf'", "google.protobuf"),
])
def test_missing_dep_detected(err, expected):
    assert is_missing_deps_failure(err) == expected

@pytest.mark.parametrize("err", [
    "",
    None,
    "No module named 'my_fake_helper'",          # hallucinated import = model error
    "SyntaxError: invalid syntax",
    "No module named 'app.tables'",              # local module = model error
])
def test_non_dep_failures_not_matched(err):
    assert is_missing_deps_failure(err) is None

def _cell(status, q=None):
    return CellResult(cell_id="c", service="s", model="m", language="python",
                      repetition=0, status=status, quality=q)

def test_deps_missing_excluded_from_passrate_and_not_catastrophic():
    cells = [_cell(STATUS_DEPS_MISSING), _cell("ok", 1.0), _cell(STATUS_FAILED)]
    s = summarize_group(cells)
    # denominator excludes deps_missing: ran = ok + failed = 2 (not 3)
    assert s["pass_rate"] == pytest.approx(0.5)        # 1 ok of 2 ran
    assert s["catastrophic_count"] == 1                # only the FAILED, not deps_missing
