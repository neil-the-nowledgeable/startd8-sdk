"""Role 3 M5 — cross-repo pinned contract with divergent consumer Prisma schema."""

from __future__ import annotations

import json
import py_compile
import sys
from pathlib import Path

import pytest

from startd8.backend_codegen import render_backend
from startd8.backend_codegen.context_client_renderer import client_method_paths
from startd8.backend_codegen.context_manifest import (
    contract_sha256,
    filter_spec_for_client,
    filter_spec_for_context,
    parse_contexts,
)
from startd8.deploy_harness.context_smoke import (
    context_base_url_env_key,
    run_outbound_context_smokes,
)
from startd8.validators.openapi_spec_gate import extract_openapi_spec_from_project

pytestmark = pytest.mark.unit

_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "design"
    / "deterministic-openapi"
    / "fixtures"
    / "cross-repo-seam"
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


def _write_producer(root: Path) -> dict:
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
    return spec


def _write_consumer(root: Path, *, contract_src: Path) -> dict[str, str]:
    (root / "openapi").mkdir(parents=True, exist_ok=True)
    (root / "openapi" / "catalog.json").write_text(
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
    return artifacts


def test_m5_pinned_filter_keeps_producer_paths_without_consumer_entity(
    tmp_path: Path,
) -> None:
    """Consumer Prisma has no Note — pinned crud still keeps /note/ from producer contract."""
    producer = tmp_path / "producer"
    producer.mkdir()
    spec = _write_producer(producer)

    (ctx,) = parse_contexts(CONTEXTS_YAML)
    consumer_filtered = filter_spec_for_client(spec, CONSUMER_SCHEMA, routes="crud")
    assert "/note/" not in consumer_filtered["paths"]

    pinned_filtered = filter_spec_for_context(spec, CONSUMER_SCHEMA, ctx)
    assert "/note/" in pinned_filtered["paths"]
    assert "NoteCreate" in pinned_filtered["components"]["schemas"]


def test_m5_cross_repo_client_without_app_tables_import(tmp_path: Path) -> None:
    """Pinned client uses dict bodies — no consumer app.tables DTO imports."""
    producer = tmp_path / "producer"
    producer.mkdir()
    _write_producer(producer)

    consumer = tmp_path / "consumer"
    consumer.mkdir()
    arts = _write_consumer(consumer, contract_src=producer / "openapi" / "catalog.json")
    client_text = arts["clients/catalog_client.py"]

    assert "class CatalogClient:" in client_text
    assert "from app.tables import" not in client_text
    assert "def list_note(self)" in client_text
    assert "def create_note(self" in client_text
    assert "dict[str, object]" in client_text
    py_compile.compile(str(tmp_path / "consumer" / "clients" / "catalog_client.py"), doraise=True)
    paths = client_method_paths(client_text)
    assert ("GET", "/note/") in paths
    assert ("POST", "/note/") in paths


def test_m5_contract_hash_uses_pinned_filter(tmp_path: Path) -> None:
    producer = tmp_path / "producer"
    producer.mkdir()
    _write_producer(producer)

    consumer = tmp_path / "consumer"
    consumer.mkdir()
    arts = _write_consumer(consumer, contract_src=producer / "openapi" / "catalog.json")
    (ctx,) = parse_contexts(CONTEXTS_YAML)
    raw = json.loads((producer / "openapi" / "catalog.json").read_text(encoding="utf-8"))
    expected = contract_sha256(filter_spec_for_context(raw, CONSUMER_SCHEMA, ctx))
    assert f"contract-sha256: {expected}" in arts["clients/catalog_client.py"]


def _producer_runtime_python(tmp_path: Path) -> Path:
    try:
        import uvicorn  # noqa: F401

        return Path(sys.executable)
    except ImportError:
        pass
    venv = tmp_path / "producer-venv"
    if not (venv / "bin" / "python").is_file():
        import subprocess

        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, timeout=60)
        subprocess.run(
            [
                str(venv / "bin" / "pip"),
                "install",
                "-q",
                "fastapi",
                "sqlmodel",
                "uvicorn[standard]",
                "httpx",
                "pydantic",
                "python-multipart",
                "jinja2",
            ],
            check=True,
            timeout=180,
        )
    return venv / "bin" / "python"


def test_m5_remote_smoke_divergent_schemas(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Live producer HTTP smoke passes when consumer schema does not share Note entity."""
    pytest.importorskip("fastapi")
    pytest.importorskip("sqlmodel")

    from startd8.deploy_harness import LiveServer

    producer = tmp_path / "producer"
    producer.mkdir()
    _write_producer(producer)
    monkeypatch.chdir(producer)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{producer / 'app.db'}")

    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _write_consumer(consumer, contract_src=producer / "openapi" / "catalog.json")

    python = _producer_runtime_python(tmp_path)
    work = tmp_path / "harness-work"
    work.mkdir()
    with LiveServer(
        python,
        "app.main:app",
        producer,
        boot_timeout_s=45.0,
        throwaway_home=work,
    ) as boot:
        assert boot.booted, boot.boot_reason
        base = f"http://127.0.0.1:{boot.port}"
        env = {context_base_url_env_key("catalog"): base}
        results = run_outbound_context_smokes(consumer, env=env)
    assert len(results) == 1
    assert results[0].outcome.status == "pass", results[0].outcome.reason
