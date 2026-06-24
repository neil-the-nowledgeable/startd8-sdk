"""Gated live oracle self-validation for the recommendationservice 1-dep harness (Track-2, Python).

Mirrors ``test_checkout_e2e_go.py``'s direct-harness tests: it launches the reference / broken Python
RecommendationService via plain ``subprocess.Popen`` (the SUT) wired to the in-process
:class:`RecommendationDepHarness` (the productcatalog stub) over loopback, sends two
``ListRecommendations`` calls, and scores per-case coverage from the responses + the stub's
call-counter — proving the harness + ground-truth + reference oracle independently.

  - ``recommendation_reference`` (dials catalog, excludes input) → coverage 1.00 + catalog dialed > 0.
  - ``recommendation_broken``    (echoes input, never dials)    → coverage 0.00 + catalog dialed == 0.

This deliberately does NOT go through ``run_behavioral_cell`` for the LIVE dial: the egress-denied
macOS-Seatbelt profile permits a sandboxed SUT to ACCEPT loopback (leaf suites) but the grpc C-core
OUTBOUND connect to a loopback stub is denied by ``(remote ip "localhost:*")`` (a pre-existing
Seatbelt limitation, not specific to this suite). The dispatch/injection/teardown wiring of
``_run_recommendation_cell`` is covered by ``test_execute_recommendation_branch.py``; this test proves
the ORACLE end-to-end with real grpc, exactly as the checkout direct-harness tests do.

Gated: set ``STARTD8_RUN_INTEGRATION=1``. Skips when grpc is unavailable.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

from startd8.benchmark_matrix.behavioral import demo_pb2, demo_pb2_grpc, execute
from startd8.benchmark_matrix.behavioral.recommendation_stubs import (
    ENV_PRODUCT_CATALOG,
    RecommendationDepHarness,
)
from startd8.benchmark_matrix.behavioral.recommendation_suite import (
    INPUT_PRODUCT_IDS,
    TEST_USER_ID,
    score_recommendations,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("STARTD8_RUN_INTEGRATION") != "1",
    reason="gated: set STARTD8_RUN_INTEGRATION=1",
)

try:
    import grpc  # noqa: F401
    _HAVE_DEPS = True
except ImportError:  # pragma: no cover
    _HAVE_DEPS = False

_BEHAVIORAL = Path(execute.__file__).parent
_FIXTURES = Path(__file__).parent / "fixtures"
_REFERENCE = _FIXTURES / "recommendation_reference"
_BROKEN = _FIXTURES / "recommendation_broken"


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _stage(fixture_dir: Path, workdir: Path) -> Path:
    svc = workdir / "src" / "recommendationservice"
    svc.mkdir(parents=True, exist_ok=True)
    shutil.copy(fixture_dir / "server.py", svc / "server.py")
    shutil.copy(_BEHAVIORAL / "demo_pb2.py", svc / "demo_pb2.py")
    shutil.copy(_BEHAVIORAL / "demo_pb2_grpc.py", svc / "demo_pb2_grpc.py")
    return svc


def _run_and_score(svc_dir: Path, harness: RecommendationDepHarness):
    """Launch the SUT (plain subprocess) wired to the in-process stub; score the two RPCs."""
    addr_map = harness.start()
    port = _free_port()
    env = {**os.environ, "PORT": str(port), **addr_map, "GRPC_VERBOSITY": "ERROR"}
    proc = subprocess.Popen(
        ["python3", "server.py"], cwd=str(svc_dir), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        ch = grpc.insecure_channel(f"127.0.0.1:{port}")
        grpc.channel_ready_future(ch).result(timeout=30.0)
        stub = demo_pb2_grpc.RecommendationServiceStub(ch)

        def _list(ids):
            try:
                resp = stub.ListRecommendations(
                    demo_pb2.ListRecommendationsRequest(user_id=TEST_USER_ID, product_ids=list(ids)),
                    timeout=20.0)
                return list(resp.product_ids)
            except grpc.RpcError:
                return None

        with_input = _list(INPUT_PRODUCT_IDS)
        empty_input = _list([])
        ch.close()
        return score_recommendations(
            with_input, empty_input,
            catalog_ids=harness.catalog_ids, input_product_ids=INPUT_PRODUCT_IDS,
            stub_calls=harness.call_counts)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        harness.stop()


@pytest.mark.skipif(not _HAVE_DEPS, reason="grpc not available")
def test_reference_recommendation_scores_full_coverage(tmp_path):
    svc = _stage(_REFERENCE, tmp_path)
    harness = RecommendationDepHarness()
    suite = _run_and_score(svc, harness)
    failing = [r.__dict__ for r in suite.results if not r.passed]
    assert suite.coverage == 1.0, failing
    # The oracle actually DIALED the productcatalog dependency (the call-count observable).
    assert harness.call_counts[ENV_PRODUCT_CATALOG] > 0


@pytest.mark.skipif(not _HAVE_DEPS, reason="grpc not available")
def test_broken_recommendation_scores_zero_and_never_dials(tmp_path):
    svc = _stage(_BROKEN, tmp_path)
    harness = RecommendationDepHarness()
    suite = _run_and_score(svc, harness)
    # Echoes inputs + never dials the catalog → every case gated to fail (catalog_dialed=False).
    assert suite.coverage == 0.0, [r.__dict__ for r in suite.results]
    assert harness.call_counts[ENV_PRODUCT_CATALOG] == 0
