"""Gated live oracle self-validation for the emailservice suite (Track-2 expansion, Python LEAF).

Mirrors ``test_catalog_e2e_go.py`` but for a Python leaf launched via the Python startup contract
(``cd src/emailservice && exec python3 server.py`` with ``$PORT`` injected). The harness provisions
the jinja2 ``confirmation.html`` template (``execute.provision_email_template``); the fixture's gRPC
stubs are co-located next to the server (the demo_pb2_grpc co-located-import convention).

  - ``email_reference`` (validates email + order) → coverage 1.00 (proves the oracle).
  - ``email_broken``    (accepts a malformed email) → ``send_invalid_email_rejected`` fails ONLY
    (proves per-case attribution).

Both run through the REAL sandbox + Python serve path via ``run_behavioral_cell`` (registration +
template provisioning + python3 launch), scored from the live RPC statuses.

Gated: set ``STARTD8_RUN_INTEGRATION=1``. Skips when grpc/jinja2 are unavailable.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from startd8.benchmark_matrix.behavioral import execute

_BEHAVIORAL = Path(execute.__file__).parent
_FIXTURES = Path(__file__).parent / "fixtures"
_REFERENCE = _FIXTURES / "email_reference"
_BROKEN = _FIXTURES / "email_broken"

pytestmark = pytest.mark.skipif(
    os.environ.get("STARTD8_RUN_INTEGRATION") != "1",
    reason="gated: set STARTD8_RUN_INTEGRATION=1",
)

try:  # the live path needs grpc + jinja2 in the harness interpreter
    import grpc  # noqa: F401
    import jinja2  # noqa: F401
    _HAVE_DEPS = True
except ImportError:  # pragma: no cover
    _HAVE_DEPS = False

_SEED = {
    "service_metadata": {"language": "python"},
    "startup": {
        "cmd": ["sh", "-c", "cd src/emailservice && exec python3 server.py"],
        "port_env": "PORT",
        "readiness": "tcp",
    },
}
_TARGETS = ["src/emailservice/server.py"]


def _stage_source(fixture_dir: Path, workdir: Path) -> None:
    """Drop the fixture server + co-located gRPC stubs into the service dir. The harness itself
    provisions confirmation.html (provision_email_template) — we do NOT pre-stage it."""
    svc_dir = workdir / "src" / "emailservice"
    svc_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(fixture_dir / "server.py", svc_dir / "server.py")
    # Co-locate the gRPC stubs (the demo_pb2_grpc co-located-import fallback path).
    shutil.copy(_BEHAVIORAL / "demo_pb2.py", svc_dir / "demo_pb2.py")
    shutil.copy(_BEHAVIORAL / "demo_pb2_grpc.py", svc_dir / "demo_pb2_grpc.py")


@pytest.mark.skipif(not _HAVE_DEPS, reason="grpc/jinja2 not available")
def test_reference_email_full_coverage_via_run_behavioral_cell(tmp_path):
    _stage_source(_REFERENCE, tmp_path)
    res = execute.run_behavioral_cell(_SEED, tmp_path, "emailservice", _TARGETS)
    assert res.has_suite and not res.degraded and not res.model_fault, res.provenance
    assert res.functional == 1.0, res.provenance.get("suite")
    # The harness provisioned the ground-truth jinja2 template (oracle-first).
    assert res.provenance.get("email_template_files")


@pytest.mark.skipif(not _HAVE_DEPS, reason="grpc/jinja2 not available")
def test_broken_email_real_miss_via_run_behavioral_cell(tmp_path):
    _stage_source(_BROKEN, tmp_path)
    res = execute.run_behavioral_cell(_SEED, tmp_path, "emailservice", _TARGETS)
    assert not res.degraded and not res.model_fault, res.provenance
    assert res.functional == 2 / 3, res.provenance.get("suite")
    suite = res.provenance.get("suite", {})
    failed = {r["name"] for r in suite.get("results", []) if not r["passed"]}
    assert failed == {"send_invalid_email_rejected"}, suite
