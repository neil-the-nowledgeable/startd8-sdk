"""EventsFileProvider drift tests (Tier-1 PR4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.contractors.deterministic_providers import ProviderContext
from startd8.events_codegen import EventsFileProvider, events_file_in_sync, render_events_artifacts

pytestmark = pytest.mark.unit

ORDER_SCHEMA = """
model Order {
  id String @id
  total Float
}
""".strip()

EVENTS_MANIFEST = """
channels:
  order_paid:
    direction: publish
    topic: orders.paid
    payload: Order
""".strip()


@pytest.fixture()
def mini_project(tmp_path: Path) -> Path:
    (tmp_path / "prisma").mkdir()
    (tmp_path / "prisma" / "schema.prisma").write_text(ORDER_SCHEMA, encoding="utf-8")
    (tmp_path / "events.yaml").write_text(EVENTS_MANIFEST, encoding="utf-8")
    (tmp_path / "app.yaml").write_text(
        "app:\n  package: app\nmessaging:\n  backend: aiokafka\n",
        encoding="utf-8",
    )
    return tmp_path


def test_provider_sync(mini_project: Path):
    rel, text = render_events_artifacts(
        EVENTS_MANIFEST,
        ORDER_SCHEMA,
        package="app",
    )[0]
    out_path = mini_project / rel
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")

    provider = EventsFileProvider()
    ctx = ProviderContext(
        project_root=mini_project,
        source_anchors=(
            str(mini_project / "events.yaml"),
            str(mini_project / "prisma" / "schema.prisma"),
        ),
    )
    assert provider.owns(out_path, text)
    assert provider.is_in_sync(out_path, text, ctx)
    assert events_file_in_sync(EVENTS_MANIFEST, ORDER_SCHEMA, rel, text, package="app")
