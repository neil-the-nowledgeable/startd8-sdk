"""FR-X4 — Tier-1 deterministic cascade smoke (offline, $0).

Exercises the scaffold + gRPC skeleton + events overlay generators end-to-end against one
project root and asserts (1) every emitted module imports/compiles, (2) the event payload
validates against its embedded JSON Schema, and (3) writing the artifacts to disk and running
each provider's drift check round-trips clean (in-sync). No live broker, gRPC stack, or OTel
collector is required, so this is a fast ``unit`` test rather than a billable ``integration`` one.
"""

from __future__ import annotations

import py_compile
from pathlib import Path

import pytest

from startd8.contractors.deterministic_providers import ProviderContext
from startd8.events_codegen import EventsFileProvider, render_events_artifacts
from startd8.proto_codegen import ProtoSkeletonProvider, render_grpc_skeletons
from startd8.scaffold_codegen import (
    ScaffoldFileProvider,
    render_scaffold,
    scaffold_in_sync,
)

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_PROTO = REPO_ROOT / "docs" / "design" / "model-benchmark" / "seeds" / "demo.proto"

SCHEMA_PRISMA = """
model Order {
  id String @id
  total Float
  currency String
  paid Boolean @default(false)
}
""".strip()

APP_YAML = """
app:
  name: boutique
  package: app
telemetry:
  enabled: true
  patterns:
    - http
    - db
    - messaging
messaging:
  backend: aiokafka
""".strip()

EVENTS_YAML = """
channels:
  order_paid:
    direction: publish
    topic: orders.paid
    payload: Order
  order_audit:
    direction: subscribe
    topic: orders.paid
    payload: Order
""".strip()

GRPC_YAML_TEMPLATE = """
services:
  - proto: {proto}
    service: ProductCatalogService
    language: python
    out: app/grpc/productcatalog_server.py
  - proto: {proto}
    service: ProductCatalogService
    language: go
    out: app/grpc/server.go
""".strip()


def _compile(path: Path) -> None:
    py_compile.compile(str(path), doraise=True)


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """A project root seeded with the four Tier-1 source manifests."""
    (tmp_path / "prisma").mkdir()
    (tmp_path / "prisma" / "schema.prisma").write_text(SCHEMA_PRISMA, encoding="utf-8")
    (tmp_path / "app.yaml").write_text(APP_YAML, encoding="utf-8")
    (tmp_path / "events.yaml").write_text(EVENTS_YAML, encoding="utf-8")
    (tmp_path / "grpc.yaml").write_text(
        GRPC_YAML_TEMPLATE.format(proto=str(DEMO_PROTO)), encoding="utf-8"
    )
    return tmp_path


def _write_all(project: Path, artifacts) -> None:
    for rel, content in artifacts:
        target = project / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def test_tier1_cascade_generates_compiles_and_roundtrips(project: Path):
    app_text = (project / "app.yaml").read_text(encoding="utf-8")
    schema_text = (project / "prisma" / "schema.prisma").read_text(encoding="utf-8")
    events_text = (project / "events.yaml").read_text(encoding="utf-8")
    grpc_text = (project / "grpc.yaml").read_text(encoding="utf-8")

    # --- 1. Render the whole cascade ---------------------------------------------------------
    scaffold = dict(render_scaffold(app_text))
    grpc = dict(render_grpc_skeletons(grpc_text, project))
    events = dict(
        render_events_artifacts(
            events_text, schema_text, messaging_backend="aiokafka", package="app"
        )
    )

    assert "app/telemetry.py" in scaffold
    assert "pyproject.toml" in scaffold
    assert "app/grpc/productcatalog_server.py" in grpc
    assert "app/grpc/server.go" in grpc
    assert "app/events/order_paid_producer.py" in events
    assert "app/events/order_audit_consumer.py" in events

    # --- 2. Write to disk + compile every Python artifact ------------------------------------
    _write_all(project, scaffold.items())
    _write_all(project, grpc.items())
    _write_all(project, events.items())

    for rel in (
        "app/telemetry.py",
        "app/grpc/productcatalog_server.py",
        "app/events/order_paid_producer.py",
        "app/events/order_audit_consumer.py",
    ):
        _compile(project / rel)

    # --- 3. Event payload validates against its embedded JSON Schema -------------------------
    jsonschema = pytest.importorskip("jsonschema")
    from startd8.openapi_contract import synthesize_body

    producer_ns: dict = {}
    exec(  # noqa: S102 — executing our own generated module in-process
        compile(
            (project / "app/events/order_paid_producer.py").read_text("utf-8"), "<gen>", "exec"
        ),
        producer_ns,
    )
    schema = producer_ns["PAYLOAD_SCHEMA"]
    payload = synthesize_body(schema, schema)
    jsonschema.validate(payload, schema)
    assert isinstance(producer_ns["serialize_payload"](payload), bytes)

    # --- 4. Drift round-trips clean for every provider ---------------------------------------
    ctx = ProviderContext(
        project_root=project,
        source_anchors=(
            str(project / "grpc.yaml"),
            str(project / "events.yaml"),
            str(project / "prisma" / "schema.prisma"),
        ),
    )

    tel_path = project / "app/telemetry.py"
    assert ScaffoldFileProvider().owns(tel_path, scaffold["app/telemetry.py"])
    assert scaffold_in_sync(app_text, scaffold["app/telemetry.py"])

    proto_path = project / "app/grpc/productcatalog_server.py"
    proto_provider = ProtoSkeletonProvider()
    assert proto_provider.owns(proto_path, grpc["app/grpc/productcatalog_server.py"])
    assert proto_provider.is_in_sync(proto_path, grpc["app/grpc/productcatalog_server.py"], ctx)

    prod_path = project / "app/events/order_paid_producer.py"
    events_provider = EventsFileProvider()
    assert events_provider.owns(prod_path, events["app/events/order_paid_producer.py"])
    assert events_provider.is_in_sync(prod_path, events["app/events/order_paid_producer.py"], ctx)


def test_tier1_cascade_is_byte_stable(project: Path):
    """Re-rendering from the same sources yields byte-identical artifacts (determinism)."""
    app_text = (project / "app.yaml").read_text(encoding="utf-8")
    schema_text = (project / "prisma" / "schema.prisma").read_text(encoding="utf-8")
    events_text = (project / "events.yaml").read_text(encoding="utf-8")
    grpc_text = (project / "grpc.yaml").read_text(encoding="utf-8")

    assert dict(render_scaffold(app_text)) == dict(render_scaffold(app_text))
    assert dict(render_grpc_skeletons(grpc_text, project)) == dict(
        render_grpc_skeletons(grpc_text, project)
    )
    assert dict(render_events_artifacts(events_text, schema_text, package="app")) == dict(
        render_events_artifacts(events_text, schema_text, package="app")
    )
