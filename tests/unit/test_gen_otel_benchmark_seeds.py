"""Tier 1 OTel benchmark seed generator tests."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.gen_otel_benchmark_seeds import (  # noqa: E402
    BEHAVIORAL_LANGUAGES,
    SERVICES,
    behavioral_eligible,
)

SEEDS_DIR = _REPO / "docs" / "design" / "model-benchmark" / "seeds-otel"
GEN = _REPO / "scripts" / "gen_otel_benchmark_seeds.py"


@pytest.mark.unit
def test_gen_otel_seeds_check_passes() -> None:
    proc = subprocess.run(
        [sys.executable, str(GEN), "--check"],
        cwd=_REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.unit
def test_seeds_index_lists_seven_services() -> None:
    index = json.loads((SEEDS_DIR / "seeds-index.json").read_text(encoding="utf-8"))
    assert index["corpus"] == "otel-demo"
    assert len(index["services"]) == 7
    assert index["proto_sha256"] == "712594c1e1a144c2211ff0695d8db05864b4ddccfad2e9862cadff8ce311225f"


@pytest.mark.unit
def test_behavioral_eligible_flags() -> None:
    by_key = {s["key"]: behavioral_eligible(s) for s in SERVICES}
    assert by_key["payment"] is True
    assert by_key["product-catalog"] is True
    assert by_key["recommendation"] is False
    assert by_key["product-reviews"] is False
    assert by_key["checkout"] is False
    assert by_key["cart"] is False
    assert by_key["ad"] is False


@pytest.mark.unit
def test_product_reviews_seed_shape() -> None:
    seed = json.loads((SEEDS_DIR / "seed-product-reviews.json").read_text(encoding="utf-8"))
    meta = seed["service_metadata"]
    assert meta["language"] == "python"
    assert set(meta["rpcs"]) == {"GetProductReviews", "GetAverageProductReviewScore"}
    assert "AskProductAIAssistant" not in meta["rpcs"]
    req = seed["tasks"][0]["config"]["requirements_text"]
    assert "AskProductAIAssistant" not in req.split("RPCs to implement")[1].split("\n")[0]


@pytest.mark.unit
def test_matrix_dry_run_seven_cells() -> None:
    sys.path.insert(0, str(_REPO / "src"))
    from startd8.benchmark_matrix.budget import estimate_run_cost
    from startd8.benchmark_matrix.run_spec import BenchmarkRunSpec

    index = json.loads((SEEDS_DIR / "seeds-index.json").read_text(encoding="utf-8"))
    services = tuple(s["service"] for s in index["services"])
    spec = BenchmarkRunSpec(
        name="otel-corpus-dry-run",
        models=("mock:mock-model",),
        services=services,
        repetitions=1,
        budget_ceiling_usd=1.0,
    )
    assert spec.total_cells == 7
    est = estimate_run_cost(spec)
    assert est.total_cells == 7


@pytest.mark.unit
def test_has_runtime_dep_no_cart_substring_false_positive() -> None:
    from scripts.gen_otel_benchmark_seeds import _has_runtime_dep

    assert _has_runtime_dep(["product-catalog"]) is True
    assert _has_runtime_dep(["products.json (catalog data file)"]) is False
    # "cart" must not match inside "product-catalog"
    assert _has_runtime_dep(["PostgreSQL (declared)"]) is True


@pytest.mark.unit
def test_check_ignores_startup_capture_unless_explicit(tmp_path: Path) -> None:
    cap = tmp_path / "startup-capture.json"
    cap.write_text(
        json.dumps(
            {
                "services": [
                    {
                        "compose_service": "payment",
                        "startup": {"cmd": ["node", "x.js"], "port_env": "PORT", "readiness": "tcp"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    proc = subprocess.run([sys.executable, str(GEN), "--check"], cwd=_REPO, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    proc_explicit = subprocess.run(
        [sys.executable, str(GEN), "--check", "--startup-capture", str(cap)],
        cwd=_REPO,
        capture_output=True,
        text=True,
    )
    assert proc_explicit.returncode == 1, "explicit startup-capture should drift committed seeds"


@pytest.mark.unit
def test_startup_capture_embedded_when_present() -> None:
    from scripts.gen_otel_benchmark_seeds import build_seed

    capture = {
        "payment": {
            "cmd": ["node", "src/payment/index.js"],
            "port_env": "PAYMENT_PORT",
            "readiness": "tcp:50051",
        }
    }
    svc = next(s for s in SERVICES if s["key"] == "payment")
    proto = (SEEDS_DIR / "demo.proto").read_text(encoding="utf-8").rstrip("\n")
    sha = "712594c1e1a144c2211ff0695d8db05864b4ddccfad2e9862cadff8ce311225f"
    seed = build_seed(svc, proto, sha, startup_capture=capture)
    assert seed["startup"] == capture["payment"]
    empty = build_seed(svc, proto, sha, startup_capture={})
    assert "startup" not in empty
