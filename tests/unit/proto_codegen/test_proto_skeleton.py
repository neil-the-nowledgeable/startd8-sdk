"""Proto skeleton renderer + provider tests (Tier-1 PR3)."""

from __future__ import annotations

import py_compile
import tempfile
from pathlib import Path

import pytest

from startd8.contractors.deterministic_providers import ProviderContext
from startd8.proto_codegen import (
    ProtoSkeletonProvider,
    is_owned_proto_skeleton,
    parse_grpc_manifest,
    proto_skeleton_in_sync,
    render_grpc_skeletons,
)

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_PROTO = REPO_ROOT / "docs" / "design" / "model-benchmark" / "seeds" / "demo.proto"

MINI_PROTO = """
syntax = "proto3";
package demo;
option go_package = "example.com/demo";

service EchoService {
  rpc Echo(EchoRequest) returns (EchoResponse) {}
}

message EchoRequest { string msg = 1; }
message EchoResponse { string msg = 1; }
""".strip()


@pytest.fixture()
def mini_project(tmp_path: Path) -> Path:
    proto = tmp_path / "echo.proto"
    proto.write_text(MINI_PROTO, encoding="utf-8")
    manifest = tmp_path / "grpc.yaml"
    manifest.write_text(
        """
services:
  - proto: echo.proto
    service: EchoService
    language: python
    out: echo_server.py
  - proto: echo.proto
    service: EchoService
    language: go
    out: server.go
""".strip(),
        encoding="utf-8",
    )
    return tmp_path


def test_parse_grpc_manifest():
    text = DEMO_PROTO.read_text(encoding="utf-8")
    assert "hipstershop" in text
    manifest = f"""
services:
  - proto: {DEMO_PROTO.relative_to(REPO_ROOT).as_posix()}
    service: ProductCatalogService
    language: python
    out: productcatalog_server.py
"""
    specs = parse_grpc_manifest(manifest)
    assert specs[0].language == "python"


def test_render_python_and_go_skeletons(mini_project: Path):
    manifest_text = (mini_project / "grpc.yaml").read_text(encoding="utf-8")
    artifacts = dict(render_grpc_skeletons(manifest_text, mini_project))
    py_text = artifacts["echo_server.py"]
    go_text = artifacts["server.go"]
    assert "EchoService" in py_text
    assert "add_EchoServiceServicer_to_server" in py_text
    assert "RegisterEchoServiceServer" in go_text
    assert is_owned_proto_skeleton(py_text)
    assert py_text == render_grpc_skeletons(manifest_text, mini_project)[0][1]


def test_python_skeleton_compiles(mini_project: Path):
    manifest_text = (mini_project / "grpc.yaml").read_text(encoding="utf-8")
    py_text = dict(render_grpc_skeletons(manifest_text, mini_project))["echo_server.py"]
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8") as f:
        f.write(py_text)
        path = f.name
    py_compile.compile(path, doraise=True)


def test_provider_sync(mini_project: Path):
    manifest_text = (mini_project / "grpc.yaml").read_text(encoding="utf-8")
    py_rel, py_text = render_grpc_skeletons(manifest_text, mini_project)[0]
    out_path = mini_project / py_rel
    out_path.write_text(py_text, encoding="utf-8")
    provider = ProtoSkeletonProvider()
    ctx = ProviderContext(
        project_root=mini_project,
        source_anchors=(str(mini_project / "grpc.yaml"),),
    )
    assert provider.owns(out_path, py_text)
    assert provider.is_in_sync(out_path, py_text, ctx)
    assert proto_skeleton_in_sync(manifest_text, mini_project, py_rel, py_text)


def test_demo_proto_catalog_service():
    manifest = f"""
services:
  - proto: {DEMO_PROTO.relative_to(REPO_ROOT).as_posix()}
    service: ProductCatalogService
    language: python
    out: productcatalog_server.py
"""
    py_text = dict(render_grpc_skeletons(manifest, REPO_ROOT))["productcatalog_server.py"]
    assert "ListProducts" in py_text
    assert "SearchProducts" in py_text
