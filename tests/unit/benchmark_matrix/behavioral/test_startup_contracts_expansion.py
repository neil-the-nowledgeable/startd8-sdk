"""Structural validation of the Track-2 expansion STARTUP CONTRACTS + the new per-language
launchers (E6 / FR-X5-LANG / FR-X6-CONTRACT — the launchability slice).

No real service is launched here: these tests prove only that each expansion seed's ``startup``
block parses via ``StartupContract.from_seed`` and that ``resolve_serve_command`` produces a valid
launch plan (argv + ``$PORT`` injection) for that service's language, with declared dependency
address envs surfaced. The Python and C# default launchers are exercised directly. The existing
checkoutservice startup contract is re-checked as a regression guard.

This is the launchability prerequisite for the Round-3 fleet, NOT the per-service behavioral suites
(those are a later slice). No suite registration, no scoring touched.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from startd8.benchmark_matrix.behavioral.contract import (
    StartupContract,
    _csharp_default,
    _python_default,
    resolve_serve_command,
)

pytestmark = pytest.mark.unit

_SEEDS_DIR = Path(__file__).resolve().parents[4] / "docs/design/model-benchmark/seeds"

_PORT = 51515


def _load(service: str) -> dict:
    return json.loads((_SEEDS_DIR / f"seed-{service}.json").read_text())


def _target_files(seed: dict) -> list[str]:
    return seed["tasks"][0]["config"]["context"]["target_files"]


# --------------------------------------------------------------------------- #
# New launchers (resolve a command + inject $PORT per language)
# --------------------------------------------------------------------------- #


def test_python_launcher_resolves_command_with_port_env():
    argv, env = _python_default(["src/recommendationservice/recommendation_server.py"], _PORT)
    # Runs from the service dir, execs the python3 entry script.
    assert argv[0] == "sh" and argv[1] == "-c"
    assert "cd src/recommendationservice" in argv[2]
    assert "exec python3 recommendation_server.py" in argv[2]
    # OB convention: port injected via env, not argv.
    assert env == {"PORT": str(_PORT)}


def test_python_launcher_returns_none_without_target():
    assert _python_default([], _PORT) is None


def test_csharp_launcher_resolves_dll_with_port_and_aspnetcore_urls():
    argv, env = _csharp_default(["src/cartservice/src/services/CartService.cs"], _PORT)
    assert argv[0] == "sh" and argv[1] == "-c"
    # Walks up to the *service-named root and execs the published DLL.
    assert "cd src/cartservice" in argv[2]
    assert "exec dotnet ./.bin/server.dll" in argv[2]
    # .NET binds via PORT + ASPNETCORE_URLS (Kestrel) — both injected.
    assert env["PORT"] == str(_PORT)
    assert env["ASPNETCORE_URLS"] == f"http://127.0.0.1:{_PORT}"


def test_csharp_launcher_returns_none_without_target():
    assert _csharp_default([], _PORT) is None


# --------------------------------------------------------------------------- #
# Each expansion seed: from_seed parses + resolve_serve_command produces a plan
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "service",
    ["cartservice", "productcatalogservice", "recommendationservice", "emailservice"],
)
def test_expansion_seed_startup_block_parses(service):
    seed = _load(service)
    contract = StartupContract.from_seed(seed)
    assert contract is not None, f"{service} startup block must parse"
    assert contract.cmd, "cmd must be non-empty"
    assert contract.port_env == "PORT"
    assert contract.readiness == "tcp"


@pytest.mark.parametrize(
    "service",
    ["cartservice", "productcatalogservice", "recommendationservice", "emailservice"],
)
def test_expansion_seed_resolves_serve_command_with_port(service):
    seed = _load(service)
    plan = resolve_serve_command(seed, _target_files(seed), _PORT)
    assert plan is not None, f"{service} must resolve a launch plan"
    argv, env = plan
    assert argv, "argv must be non-empty"
    # The seed startup contract is authoritative; it injects the port via port_env.
    assert env.get("PORT") == str(_PORT)


def test_cartservice_csharp_launch_plan_shape():
    seed = _load("cartservice")
    argv, env = resolve_serve_command(seed, _target_files(seed), _PORT)
    assert "dotnet ./.bin/server.dll" in argv[-1]
    assert env["PORT"] == str(_PORT)


def test_productcatalog_go_launch_plan_shape():
    seed = _load("productcatalogservice")
    argv, env = resolve_serve_command(seed, _target_files(seed), _PORT)
    assert "exec ./.bin/server" in argv[-1]
    assert env["PORT"] == str(_PORT)


def test_python_services_launch_via_entry_script():
    for service, script in (
        ("recommendationservice", "recommendation_server.py"),
        ("emailservice", "email_server.py"),
    ):
        seed = _load(service)
        argv, env = resolve_serve_command(seed, _target_files(seed), _PORT)
        assert f"exec python3 {script}" in argv[-1]
        assert env["PORT"] == str(_PORT)


# --------------------------------------------------------------------------- #
# Dependency-address env is declared where (and only where) a service has a gRPC peer
# --------------------------------------------------------------------------- #


def test_recommendation_declares_productcatalog_dep_addr_env():
    seed = _load("recommendationservice")
    dep_envs = seed["startup"].get("dependency_addr_env", [])
    assert "PRODUCT_CATALOG_SERVICE_ADDR" in dep_envs


@pytest.mark.parametrize("service", ["emailservice", "productcatalogservice", "cartservice"])
def test_leaf_services_declare_no_dependency_addr_env(service):
    # email = leaf; catalog reads a local file; cart uses Redis (infra, not a gRPC peer).
    seed = _load(service)
    assert "dependency_addr_env" not in seed["startup"]


# --------------------------------------------------------------------------- #
# Regression: the existing checkoutservice startup contract still resolves unchanged
# --------------------------------------------------------------------------- #


def test_checkout_startup_contract_regression():
    seed = _load("checkoutservice")
    contract = StartupContract.from_seed(seed)
    assert contract is not None
    argv, env = resolve_serve_command(seed, _target_files(seed), _PORT)
    assert "cd src/checkoutservice && exec ./.bin/server" in argv[-1]
    assert env["PORT"] == str(_PORT)
    # The six downstream dependency address envs are still declared on the contract block.
    dep_envs = seed["startup"]["dependency_addr_env"]
    assert dep_envs == [
        "PRODUCT_CATALOG_SERVICE_ADDR",
        "CART_SERVICE_ADDR",
        "CURRENCY_SERVICE_ADDR",
        "SHIPPING_SERVICE_ADDR",
        "PAYMENT_SERVICE_ADDR",
        "EMAIL_SERVICE_ADDR",
    ]
