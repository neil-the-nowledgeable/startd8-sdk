"""Role 3 P2 — bucket-3 integration seam on the M4 two-app fixture."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from startd8.backend_codegen import render_backend
from startd8.backend_codegen.context_integration_renderer import CONTEXT_INTEGRATION_PATH
from startd8.contractors.context_integration import collect_context_integration_prompt
from startd8.contractors.prime_postmortem import CAUSE_TO_SUGGESTION
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
INTEGRATION_SEED = (
    Path(__file__).resolve().parents[2] / "fixtures" / "openapi_role3" / "integration_seed.json"
)


def _materialize(artifacts: dict[str, str], root: Path) -> None:
    for rel, content in artifacts.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    for pkg in ("app", "clients"):
        init_py = root / pkg / "__init__.py"
        if (root / pkg).is_dir() and not init_py.is_file():
            init_py.write_text("", encoding="utf-8")


def _bootstrap_m4_consumer(tmp_path: Path) -> Path:
    producer = tmp_path / "producer"
    producer.mkdir()
    artifacts = dict(render_backend(PRODUCER_SCHEMA))
    _materialize(artifacts, producer)
    spec = extract_openapi_spec_from_project(str(producer))
    assert spec is not None
    catalog_dir = producer / "openapi"
    catalog_dir.mkdir(parents=True, exist_ok=True)
    (catalog_dir / "catalog.json").write_text(
        json.dumps(spec, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    consumer = tmp_path / "consumer"
    consumer.mkdir()
    (consumer / "openapi").mkdir(parents=True, exist_ok=True)
    (consumer / "openapi" / "catalog.json").write_text(
        (producer / "openapi" / "catalog.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (consumer / "prisma").mkdir(parents=True, exist_ok=True)
    (consumer / "prisma" / "contexts.yaml").write_text(CONTEXTS_YAML, encoding="utf-8")
    (consumer / "prisma" / "schema.prisma").write_text(CONSUMER_SCHEMA, encoding="utf-8")
    arts = dict(
        render_backend(
            CONSUMER_SCHEMA,
            contexts_text=CONTEXTS_YAML,
            project_root=str(consumer),
        )
    )
    _materialize(arts, consumer)
    return consumer


def test_p2_emits_context_clients_registry(tmp_path: Path) -> None:
    consumer = _bootstrap_m4_consumer(tmp_path)
    registry = (consumer / CONTEXT_INTEGRATION_PATH).read_text(encoding="utf-8")
    assert "def get_catalog_client() -> CatalogClient:" in registry
    assert "python-context-integration" in registry


def test_p2_prompt_grounds_integration_pass(tmp_path: Path) -> None:
    consumer = _bootstrap_m4_consumer(tmp_path)
    prompt = collect_context_integration_prompt(project_root=str(consumer))
    assert "Do **NOT** invent raw httpx" in prompt
    assert "`catalog`" in prompt
    assert "get_catalog_client" in prompt


def test_p2_integration_seed_documents_pattern() -> None:
    """Checked-in seed shows bucket-3 task wording for outbound catalog reads."""
    data = json.loads(INTEGRATION_SEED.read_text(encoding="utf-8"))
    task = data["tasks"][0]
    desc = task["config"]["context"]["task_description"]
    assert "get_catalog_client" in desc
    assert "CatalogClient" in desc
    assert task["config"]["context"]["target_files"] == ["app/note_sync.py"]


def test_p2_kaizen_mappings_present() -> None:
    for key in ("context_contract_stale", "invented_outbound_client"):
        assert key in CAUSE_TO_SUGGESTION
        assert CAUSE_TO_SUGGESTION[key]["phase"] in ("spec", "draft")
        assert len(CAUSE_TO_SUGGESTION[key]["hint"]) > 20
