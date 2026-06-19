"""Role 3 M4 — two-app producer→export→consumer pin→drift→remote smoke fixture.

Uses the checked-in fixture under
``docs/design/deterministic-openapi/fixtures/two-app-seam/``. Default pytest run is $0
and offline (LiveServer loopback only; no pip/network).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from startd8.backend_codegen import owned_file_in_sync, render_backend
from startd8.backend_codegen.context_client_renderer import client_method_paths
from startd8.backend_codegen.context_manifest import (
    contract_sha256,
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


def _write_producer(root: Path) -> dict:
    """Generate producer app and export ``openapi/catalog.json``."""
    artifacts = dict(render_backend(PRODUCER_SCHEMA))
    _materialize(artifacts, root)
    spec = extract_openapi_spec_from_project(str(root))
    assert spec is not None, "producer OPENAPI_SPEC must load"
    catalog_dir = root / "openapi"
    catalog_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = catalog_dir / "catalog.json"
    catalog_path.write_text(
        json.dumps(spec, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return spec


def _write_consumer(root: Path, *, contract_src: Path) -> dict[str, str]:
    """Generate consumer app with pinned contract and context client."""
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
    return artifacts


def test_m4_producer_export_matches_openapi_spec(tmp_path: Path) -> None:
    """Exported catalog.json is a canonical dump of owned OPENAPI_SPEC."""
    producer = tmp_path / "producer"
    producer.mkdir()
    spec = _write_producer(producer)
    exported = json.loads((producer / "openapi" / "catalog.json").read_text(encoding="utf-8"))
    assert exported == spec
    assert "/note/" in exported["paths"]


def test_m4_consumer_client_from_pinned_contract(tmp_path: Path) -> None:
    """Consumer emits CatalogClient from producer-exported contract (not local: true)."""
    producer = tmp_path / "producer"
    producer.mkdir()
    _write_producer(producer)

    consumer = tmp_path / "consumer"
    consumer.mkdir()
    arts = _write_consumer(consumer, contract_src=producer / "openapi" / "catalog.json")

    client_text = arts["clients/catalog_client.py"]
    assert "class CatalogClient:" in client_text
    assert "contract-sha256:" in client_text
    assert "local: true" not in client_text.lower()
    paths = client_method_paths(client_text)
    assert ("GET", "/note/") in paths
    assert ("POST", "/note/") in paths


def test_m4_contract_tamper_triggers_drift(tmp_path: Path) -> None:
    """Editing pinned catalog.json makes consumer --check semantics fail (contract-sha256)."""
    producer = tmp_path / "producer"
    producer.mkdir()
    _write_producer(producer)

    consumer = tmp_path / "consumer"
    consumer.mkdir()
    arts = _write_consumer(consumer, contract_src=producer / "openapi" / "catalog.json")
    client_text = arts["clients/catalog_client.py"]
    assert owned_file_in_sync(
        CONSUMER_SCHEMA,
        client_text,
        contexts_text=CONTEXTS_YAML,
        project_root=str(consumer),
    )

    catalog = consumer / "openapi" / "catalog.json"
    data = json.loads(catalog.read_text(encoding="utf-8"))
    # Tamper a CRUD-relevant schema field so filter_spec_for_client hash changes.
    data["components"]["schemas"]["NoteCreate"]["properties"]["title"]["minLength"] = 99
    catalog.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    assert not owned_file_in_sync(
        CONSUMER_SCHEMA,
        client_text,
        contexts_text=CONTEXTS_YAML,
        project_root=str(consumer),
    )


def test_m4_filtered_contract_hash_stable(tmp_path: Path) -> None:
    """contract-sha256 in client header matches filter_spec_for_client of pinned JSON."""
    producer = tmp_path / "producer"
    producer.mkdir()
    _write_producer(producer)

    consumer = tmp_path / "consumer"
    consumer.mkdir()
    arts = _write_consumer(consumer, contract_src=producer / "openapi" / "catalog.json")
    raw = json.loads((producer / "openapi" / "catalog.json").read_text(encoding="utf-8"))
    (ctx,) = parse_contexts(CONTEXTS_YAML)
    filtered = filter_spec_for_context(raw, CONSUMER_SCHEMA, ctx)
    expected = contract_sha256(filtered)
    assert f"contract-sha256: {expected}" in arts["clients/catalog_client.py"]


def _producer_runtime_python(tmp_path: Path) -> Path:
    """Python with generated-app runtime deps (uvicorn) for LiveServer."""
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


def test_m4_remote_smoke_against_live_producer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Live producer HTTP + consumer run_outbound_context_smokes list+create round-trip."""
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
    assert results[0].producer_id == "catalog"
    assert results[0].outcome.status == "pass", results[0].outcome.reason
    assert results[0].base_url == base.rstrip("/")
