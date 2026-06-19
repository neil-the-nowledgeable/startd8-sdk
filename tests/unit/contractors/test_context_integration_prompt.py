"""Unit tests — Prime Contractor context_integration prompt (Role 3 P2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from startd8.backend_codegen import render_backend
from startd8.contractors.context_integration import (
    build_context_client_interfaces,
    collect_context_integration_prompt,
    render_context_integration,
)
from startd8.validators.openapi_spec_gate import extract_openapi_spec_from_project

pytestmark = pytest.mark.unit

_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "design"
    / "deterministic-openapi"
    / "fixtures"
    / "two-app-seam"
)
PRODUCER_SCHEMA = (_FIXTURE_ROOT / "producer" / "schema.prisma").read_text(encoding="utf-8")
CONSUMER_SCHEMA = (_FIXTURE_ROOT / "consumer" / "schema.prisma").read_text(encoding="utf-8")
CONTEXTS_YAML = (_FIXTURE_ROOT / "consumer" / "contexts.yaml").read_text(encoding="utf-8")


def _materialize(artifacts: dict[str, str], root: Path) -> None:
    for rel, content in artifacts.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    for pkg in ("app", "clients"):
        init_py = root / pkg / "__init__.py"
        if (root / pkg).is_dir() and not init_py.is_file():
            init_py.write_text("", encoding="utf-8")


def _write_m4_consumer(root: Path, *, contract_src: Path) -> None:
    contract_dir = root / "openapi"
    contract_dir.mkdir(parents=True, exist_ok=True)
    (contract_dir / "catalog.json").write_text(
        contract_src.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (root / "prisma").mkdir(parents=True, exist_ok=True)
    (root / "prisma" / "contexts.yaml").write_text(CONTEXTS_YAML, encoding="utf-8")
    (root / "prisma" / "schema.prisma").write_text(CONSUMER_SCHEMA, encoding="utf-8")
    artifacts = dict(
        render_backend(
            CONSUMER_SCHEMA,
            contexts_text=CONTEXTS_YAML,
            project_root=str(root),
        )
    )
    _materialize(artifacts, root)


def _write_m4_producer(root: Path) -> None:
    artifacts = dict(render_backend(PRODUCER_SCHEMA))
    _materialize(artifacts, root)
    spec = extract_openapi_spec_from_project(str(root))
    assert spec is not None
    catalog_dir = root / "openapi"
    catalog_dir.mkdir(parents=True, exist_ok=True)
    (catalog_dir / "catalog.json").write_text(
        json.dumps(spec, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_collect_context_integration_prompt_from_m4_fixture(tmp_path: Path) -> None:
    producer = tmp_path / "producer"
    producer.mkdir()
    _write_m4_producer(producer)

    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _write_m4_consumer(consumer, contract_src=producer / "openapi" / "catalog.json")

    prompt = collect_context_integration_prompt(project_root=str(consumer))
    assert "## Outbound context clients" in prompt
    assert "CatalogClient" in prompt
    assert "get_catalog_client" in prompt
    assert "python-context-integration" in prompt
    assert "list_note" in prompt or "create_note" in prompt


def test_build_context_client_interfaces_skips_missing_clients(tmp_path: Path) -> None:
    local_ctx = CONTEXTS_YAML.replace(
        "contract: openapi/catalog.json",
        "local: true",
    )
    (tmp_path / "prisma").mkdir()
    (tmp_path / "prisma" / "contexts.yaml").write_text(local_ctx, encoding="utf-8")
    (tmp_path / "prisma" / "schema.prisma").write_text(CONSUMER_SCHEMA, encoding="utf-8")
    ifaces = build_context_client_interfaces(
        project_root=str(tmp_path),
        schema_text=CONSUMER_SCHEMA,
        contexts_text=local_ctx,
    )
    assert ifaces == []


def test_render_context_integration_empty() -> None:
    assert render_context_integration([]) == ""


def test_collect_returns_empty_without_contexts(tmp_path: Path) -> None:
    assert collect_context_integration_prompt(project_root=str(tmp_path)) == ""
