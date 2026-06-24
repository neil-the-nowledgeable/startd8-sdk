"""Docker-GATED live smoke for the Round 3 docker-compose FLEET substrate prototype (the compose
analog of the netns smoke in ``test_netns_substrate_smoke.py``).

This is the PROOF the compose substrate is viable: it builds + brings up a minimal 2-service Online
Boutique fleet (productcatalogservice + recommendationservice) and asserts BOTH things the macOS
Seatbelt process-sandbox could not give at once:

  (a) **service-DNS gRPC WORKS** — recommendationservice dials ``productcatalogservice:8080`` by name
      over the compose network (a REAL inter-service gRPC call), proven by the recommendation suite
      scoring coverage 1.0 AND productcatalog's container logs showing real ListProducts dials; AND
  (b) **external egress is DENIED** — a connect to 1.1.1.1:443 from inside the pure-backend
      productcatalog container (on the ``internal: true`` fleet network) fails (containment by
      construction; the internal network has no route out).

It runs ONLY where ``docker`` + ``docker compose`` are available AND ``STARTD8_RUN_INTEGRATION=1``
(builds pull base images over the network — opt-in, like the deploy-harness live tests). Everywhere
else it SKIPS with a clear reason — never a false pass.

The actual orchestration lives in ``drive_fleet.py`` next to the compose file (the reusable script
entrypoint); this test just shells out to it and asserts exit 0, so the script and the test can't
drift.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_PROTOTYPE_DIR = (
    Path(__file__).resolve().parents[1].parent
    / "docs" / "design" / "round3-full-app" / "compose-prototype"
)
_DRIVER = _PROTOTYPE_DIR / "drive_fleet.py"


def _docker_compose_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        r = subprocess.run(["docker", "compose", "version"], capture_output=True, timeout=15)
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return False


_RUN = os.environ.get("STARTD8_RUN_INTEGRATION") == "1"

if not _RUN:
    pytest.skip(
        "compose fleet smoke is opt-in (builds pull images over the network): set "
        "STARTD8_RUN_INTEGRATION=1 to run",
        allow_module_level=True,
    )
if not _docker_compose_available():
    pytest.skip("docker / docker compose not available", allow_module_level=True)
if not _DRIVER.is_file():
    pytest.skip(f"fleet driver missing: {_DRIVER}", allow_module_level=True)


@pytest.mark.slow
def test_compose_fleet_substrate_proven():
    """Build + run the 2-service fleet; the driver proves coverage 1.0 over the real inter-service
    gRPC call AND egress denial, then tears down. Exit 0 = substrate proven."""
    r = subprocess.run(
        [sys.executable, str(_DRIVER)],
        cwd=str(_PROTOTYPE_DIR),
        capture_output=True,
        text=True,
        timeout=1200,
    )
    out = (r.stdout or "") + "\n" + (r.stderr or "")
    # Surface the driver's structured RESULT line on failure for diagnosis.
    assert r.returncode == 0, f"fleet driver failed (rc={r.returncode}):\n{out}"
    assert "SUBSTRATE PROVEN" in out, out
    assert "coverage = 1.000" in out, out
    assert "DENIED" in out, out
