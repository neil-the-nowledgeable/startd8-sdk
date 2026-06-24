"""Unit tests for Go hipstershop stub provisioning (``setup_go_stubs``) — no Go toolchain required.

Covers the asymmetry fix: a MODEL-GENERATED checkout often imports the upstream gRPC stubs at
``github.com/GoogleCloudPlatform/microservices-demo/hipstershop`` but leaves its ``go.mod`` BARE (no
``require``). The old regex keyed off a ``require ... v`` line, found nothing, and let `go mod tidy`
chase ``@latest`` (which restructured and dropped ``hipstershop``) → provision failed. The fix
discovers the import from the SOURCES and injects both a ``require`` and a local ``replace`` to the
vendored stubs, so the build resolves the stubs offline regardless of upstream ``@latest``.
"""
from __future__ import annotations

import re
from pathlib import Path

from startd8.benchmark_matrix.behavioral.provision import (
    _GO_STUB_MODULE_MARKER,
    _find_stub_import,
    setup_go_stubs,
)

_STUB_IMPORT = f"{_GO_STUB_MODULE_MARKER}/hipstershop"

_BARE_GOMOD = "module checkoutservice\n\ngo 1.23\n"
_REQUIRE_GOMOD = (
    "module checkoutservice\n\ngo 1.21\n\n"
    f"require (\n\t{_STUB_IMPORT} v0.0.0\n\tgoogle.golang.org/grpc v1.81.1\n)\n"
)
_MAIN_GO = (
    "package main\n\n"
    "import (\n"
    '\t"google.golang.org/grpc"\n'
    f'\tpb "{_STUB_IMPORT}"\n'
    ")\n\n"
    "var _ = pb.PlaceOrderRequest{}\n"
)


def _stage(workdir: Path, gomod: str, main_go: str = _MAIN_GO) -> Path:
    svc = workdir / "src" / "checkoutservice"
    svc.mkdir(parents=True, exist_ok=True)
    (svc / "go.mod").write_text(gomod)
    (svc / "main.go").write_text(main_go)
    return svc


def test_find_stub_import_from_sources():
    """The stub module is discovered from the .go import, not go.mod."""
    wd = Path("__unused__")
    svc = Path("/tmp/_find_stub_test")
    svc.mkdir(parents=True, exist_ok=True)
    (svc / "main.go").write_text(_MAIN_GO)
    assert _find_stub_import(svc) == _STUB_IMPORT
    del wd


def test_find_stub_import_none_when_absent(tmp_path):
    svc = tmp_path / "svc"
    svc.mkdir()
    (svc / "main.go").write_text("package main\n\nfunc main() {}\n")
    assert _find_stub_import(svc) is None


def test_bare_gomod_gets_require_and_replace(tmp_path):
    """The model-generated case: bare go.mod + stub import in sources. The OLD code returned None
    (nothing to vendor) and the build chased @latest; the fix injects require + replace."""
    svc = _stage(tmp_path, _BARE_GOMOD)
    err = setup_go_stubs(tmp_path, svc)
    assert err is None, err
    out = (svc / "go.mod").read_text()
    # require makes the stub module part of the build graph; replace points it at the vendored copy.
    assert re.search(rf"require {re.escape(_STUB_IMPORT)}\s+v", out), out
    assert re.search(rf"replace {re.escape(_STUB_IMPORT)}\s*=>", out), out
    localmod = tmp_path.resolve() / ".gostubs"
    assert f"replace {_STUB_IMPORT} => {localmod}" in out
    # the vendored stub module + the two generated .go files are materialized locally
    assert (localmod / "go.mod").read_text().startswith(f"module {_STUB_IMPORT}")
    assert (localmod / "demo.pb.go").is_file()
    assert (localmod / "demo_grpc.pb.go").is_file()


def test_existing_require_gets_replace_only_not_duplicated(tmp_path):
    """The fixture case: go.mod already declares the require. We must NOT add a second require, only
    the replace — preserving the existing working path byte-for-byte aside from the appended replace."""
    svc = _stage(tmp_path, _REQUIRE_GOMOD)
    err = setup_go_stubs(tmp_path, svc)
    assert err is None, err
    out = (svc / "go.mod").read_text()
    # exactly one require line for the stub module (no duplicate injected)
    assert len(re.findall(rf"{re.escape(_STUB_IMPORT)}\s+v", out)) == 1, out
    assert re.search(rf"replace {re.escape(_STUB_IMPORT)}\s*=>", out), out


def test_idempotent_replace_not_doubled(tmp_path):
    """Running provisioning twice must not append a second replace directive."""
    svc = _stage(tmp_path, _BARE_GOMOD)
    assert setup_go_stubs(tmp_path, svc) is None
    assert setup_go_stubs(tmp_path, svc) is None
    out = (svc / "go.mod").read_text()
    assert out.count(f"replace {_STUB_IMPORT} =>") == 1, out


def test_no_stub_import_returns_none_no_changes(tmp_path):
    """A self-contained Go cell (no upstream stub import) is left untouched."""
    plain = "package main\n\nfunc main() {}\n"
    svc = _stage(tmp_path, _BARE_GOMOD, main_go=plain)
    before = (svc / "go.mod").read_text()
    assert setup_go_stubs(tmp_path, svc) is None
    assert (svc / "go.mod").read_text() == before
    assert not (tmp_path / ".gostubs").exists()


def test_missing_gomod_degrades(tmp_path):
    svc = tmp_path / "src" / "checkoutservice"
    svc.mkdir(parents=True)
    (svc / "main.go").write_text(_MAIN_GO)
    assert setup_go_stubs(tmp_path, svc) == "go.mod missing"
