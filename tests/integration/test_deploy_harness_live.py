"""M1 full live-path integration test — real venv + pip + uvicorn boot.

Marked ``integration`` + ``slow``: creates a throwaway venv and pip-installs from the network. The
repo's ``tests/integration`` conftest gates these behind ``STARTD8_RUN_INTEGRATION=1``. Run on demand:

    STARTD8_RUN_INTEGRATION=1 pytest tests/integration/test_deploy_harness_live.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def _write_installed_app(root: Path, *, with_health: bool = True) -> None:
    app = root / "app"
    app.mkdir(parents=True, exist_ok=True)
    (app / "__init__.py").write_text("", encoding="utf-8")
    body = "from fastapi import FastAPI\napp = FastAPI()\n"
    if with_health:
        body += "@app.get('/health')\ndef health():\n    return {'ok': True}\n"
    (app / "main.py").write_text(body, encoding="utf-8")
    (root / "requirements.txt").write_text(
        "fastapi\n", encoding="utf-8"
    )  # uvicorn auto-added


def test_live_installed_app_reaches_health(tmp_path: Path) -> None:
    from startd8.deploy_harness import deploy_app_local

    _write_installed_app(tmp_path, with_health=True)
    res = deploy_app_local(
        tmp_path, model="m", install_timeout_s=400, boot_timeout_s=60
    )
    assert res.stages["install"].status.value == "pass"
    assert res.stages["boot"].status.value == "pass"
    assert res.stages["health"].status.value == "pass"
    assert (
        res.stages["health"].reason is None
    )  # /health answered → app-health, not liveness-only
    assert res.harness_env.port and res.harness_env.installed_deps


def test_live_app_without_health_is_liveness_only(tmp_path: Path) -> None:
    from startd8.deploy_harness import deploy_app_local

    _write_installed_app(tmp_path, with_health=False)
    res = deploy_app_local(tmp_path, install_timeout_s=400, boot_timeout_s=60)
    assert res.stages["health"].status.value == "pass"
    assert (
        res.stages["health"].reason == "pass:liveness-only"
    )  # only /openapi.json answered


def test_live_broken_app_fails_at_boot(tmp_path: Path) -> None:
    from startd8.deploy_harness import deploy_app_local

    app = tmp_path / "app"
    app.mkdir()
    (app / "__init__.py").write_text("", encoding="utf-8")
    (app / "main.py").write_text(
        "from fastapi import FastAPI\nraise RuntimeError('boom')\napp = FastAPI()\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    res = deploy_app_local(tmp_path, install_timeout_s=400, boot_timeout_s=30)
    assert res.stages["install"].status.value == "pass"
    assert res.stages["boot"].status.value == "fail"
    assert "early-exit" in (res.stages["boot"].reason or "")


# --------------------------------------------------------------------------- smoke-CRUD (M2)

_CRUD_APP = """\
from fastapi import FastAPI
from pydantic import BaseModel
app = FastAPI()
_db = []
class ItemIn(BaseModel):
    name: str
    qty: int = 0
@app.get("/items")
def list_items():
    return _db
@app.post("/items")
def create_item(item: ItemIn):
    row = {"id": len(_db) + 1, "name": item.name, "qty": item.qty}
    _db.append(row)
    return row
"""

_FK_APP = """\
from fastapi import FastAPI
from pydantic import BaseModel
app = FastAPI()
class OrderIn(BaseModel):
    customer_id: int
@app.get("/orders")
def list_orders():
    return []
@app.post("/orders")
def create_order(order: OrderIn):
    return {"id": 1, "customer_id": order.customer_id}
"""


def _write_raw_app(root: Path, body: str) -> None:
    app = root / "app"
    app.mkdir(parents=True, exist_ok=True)
    (app / "__init__.py").write_text("", encoding="utf-8")
    (app / "main.py").write_text(body, encoding="utf-8")
    (root / "requirements.txt").write_text("fastapi\n", encoding="utf-8")


def test_live_smoke_crud_round_trip_passes(tmp_path: Path) -> None:
    from startd8.deploy_harness import deploy_app_local

    _write_raw_app(tmp_path, _CRUD_APP)
    res = deploy_app_local(tmp_path, install_timeout_s=400, boot_timeout_s=60)
    assert res.stages["boot"].status.value == "pass"
    assert res.stages["smoke"].status.value == "pass"
    assert res.highest_stage == "smoke"


def test_live_smoke_fk_only_is_skipped_not_failed(tmp_path: Path) -> None:
    from startd8.deploy_harness import deploy_app_local

    _write_raw_app(tmp_path, _FK_APP)
    res = deploy_app_local(tmp_path, install_timeout_s=400, boot_timeout_s=60)
    assert res.stages["smoke"].status.value == "skipped"
    assert res.stages["smoke"].reason == "skipped:all-resources-fk-coupled"
