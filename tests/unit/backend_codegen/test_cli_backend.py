"""Step 7 (FR-13) `startd8 generate backend` + Step 8 (FR-12) the ProofPoint+Metric pilot.

The pilot is the path's acceptance milestone: author the .prisma → generate the full backend →
re-check reports in-sync ($0.00 skip on regen) → the Python build gate is green.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from startd8.cli_generate import generate_app

pytestmark = pytest.mark.unit

runner = CliRunner()

# The locked pilot bounded context.
PILOT = """\
enum Confidence {
  draft
  confirmed
}

model ProofPoint {
  id         String     @id
  situation  String
  action     String
  result     String
  confidence Confidence
  tags       String[]
  metricId   String?
}

model Metric {
  id      String @id
  value   Float
  unit    String
  context String?
}
"""

EXPECTED_FILES = [
    "app/__init__.py",
    "app/models.py",
    "app/tables.py",
    "app/routers.py",
    "app/db.py",
    "app/main.py",
    "app/web.py",
    "app/export.py",
    "app/ai_schemas.py",
    "app/completeness.py",
    "app/templates/base.html",
    "app/templates/_field_error.html",
    "app/templates/proofpoint/list.html",
    "app/templates/proofpoint/form.html",
    "app/templates/metric/detail.html",
    "requirements.txt",
]


def _schema(tmp_path):
    p = tmp_path / "prisma" / "schema.prisma"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(PILOT, encoding="utf-8")
    return p


def test_generate_backend_writes_full_spine(tmp_path):
    schema = _schema(tmp_path)
    result = runner.invoke(
        generate_app, ["backend", "--schema", str(schema), "--out", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    for rel in EXPECTED_FILES:
        assert (tmp_path / rel).exists(), f"missing {rel}"
    # spot-check the cross-layer projection landed coherently
    assert (
        "class ProofPointSchema(BaseModel):" in (tmp_path / "app/models.py").read_text()
    )
    assert (
        "class ProofPoint(SQLModel, table=True):"
        in (tmp_path / "app/tables.py").read_text()
    )
    assert 'prefix="/proofpoint"' in (tmp_path / "app/routers.py").read_text()


def test_check_before_generate_reports_drift(tmp_path):
    schema = _schema(tmp_path)
    # nothing written yet -> --check must report drift (missing) and exit 1
    result = runner.invoke(
        generate_app,
        ["backend", "--schema", str(schema), "--out", str(tmp_path), "--check"],
    )
    assert result.exit_code == 1


def test_pilot_regen_is_zero_cost_and_gate_green(tmp_path):
    """FR-12 acceptance: generate → re-check in-sync ($0.00 regen) → build gate green."""
    schema = _schema(tmp_path)
    gen = runner.invoke(
        generate_app,
        ["backend", "--schema", str(schema), "--out", str(tmp_path), "--gate"],
    )
    assert gen.exit_code == 0, gen.output
    assert "build gate: pass" in gen.output

    # re-check: every owned artifact is recognized in-sync -> the skip-hook would mark it $0.00
    chk = runner.invoke(
        generate_app,
        ["backend", "--schema", str(schema), "--out", str(tmp_path), "--check"],
    )
    assert chk.exit_code == 0, chk.output
    assert "in_sync" in chk.output


PAGES = """\
pages:
  - slug: "/"
    title: "Home"
    nav_label: "Home"
    content: pages/home.md
"""


def _with_pages(tmp_path):
    schema = _schema(tmp_path)
    (tmp_path / "prisma" / "pages.yaml").write_text(PAGES, encoding="utf-8")
    (tmp_path / "app" / "pages").mkdir(parents=True, exist_ok=True)
    (tmp_path / "app" / "pages" / "home.md").write_text("# Home\n\nHi.\n", encoding="utf-8")
    return schema


def test_generate_with_pages_then_recheck_in_sync(tmp_path):
    schema = _with_pages(tmp_path)
    pages = tmp_path / "prisma" / "pages.yaml"
    gen = runner.invoke(
        generate_app,
        ["backend", "--schema", str(schema), "--pages", str(pages), "--out", str(tmp_path)],
    )
    assert gen.exit_code == 0, gen.output
    assert (tmp_path / "app/pages.py").exists()
    assert (tmp_path / "app/templates/pages/home.html").exists()
    # nav is now the always-on default-nav partial (FR-13/14): base.html includes it; the <nav>
    # markup + the runtime visibility module live in the generated nav files.
    assert '{% include "_nav.html"' in (tmp_path / "app/templates/base.html").read_text()
    assert (tmp_path / "app/templates/_nav.html").exists()
    assert (tmp_path / "app/nav.py").exists()
    assert "<nav" in (tmp_path / "app/templates/_nav.html").read_text()
    chk = runner.invoke(
        generate_app,
        ["backend", "--schema", str(schema), "--pages", str(pages), "--out", str(tmp_path), "--check"],
    )
    assert chk.exit_code == 0, chk.output
    assert "in_sync" in chk.output


def test_pages_authoring_requires_pages(tmp_path):
    schema = _schema(tmp_path)
    result = runner.invoke(
        generate_app,
        ["backend", "--schema", str(schema), "--out", str(tmp_path), "--pages-authoring"],
    )
    assert result.exit_code != 0
    assert "requires --pages" in result.output


def test_generate_with_pages_authoring_emits_ui_and_pyyaml(tmp_path):
    schema = _with_pages(tmp_path)
    pages = tmp_path / "prisma" / "pages.yaml"
    gen = runner.invoke(
        generate_app,
        [
            "backend", "--schema", str(schema), "--pages", str(pages),
            "--pages-authoring", "--out", str(tmp_path),
        ],
    )
    assert gen.exit_code == 0, gen.output
    assert (tmp_path / "app/pages_admin.py").exists()
    assert (tmp_path / "app/pages_io.py").exists()
    assert "pyyaml" in (tmp_path / "requirements.txt").read_text()


def test_generate_with_views_forms_then_recheck_in_sync(tmp_path):
    """--views feeds views.yaml's `forms:` section (per-entity on_create) into the web routes."""
    schema = _schema(tmp_path)
    views = tmp_path / "prisma" / "views.yaml"
    views.write_text(
        "views: []\nforms:\n  ProofPoint: { on_create: confirmation }\n", encoding="utf-8"
    )
    gen = runner.invoke(
        generate_app,
        ["backend", "--schema", str(schema), "--views", str(views), "--out", str(tmp_path)],
    )
    assert gen.exit_code == 0, gen.output
    web = (tmp_path / "app/web.py").read_text()
    assert "fastapi-web-forms" in web and "forms-sha256:" in web
    assert 'RedirectResponse(f"/ui/proofpoint/{obj.id}/created", status_code=303)' in web
    assert (tmp_path / "app/templates/proofpoint/created.html").exists()
    assert not (tmp_path / "app/templates/metric/created.html").exists()
    chk = runner.invoke(
        generate_app,
        ["backend", "--schema", str(schema), "--views", str(views), "--out", str(tmp_path), "--check"],
    )
    assert chk.exit_code == 0, chk.output
    # editing the manifest flags the forms-configured artifacts stale
    views.write_text(
        "views: []\nforms:\n  ProofPoint: { on_create: list }\n", encoding="utf-8"
    )
    chk = runner.invoke(
        generate_app,
        ["backend", "--schema", str(schema), "--views", str(views), "--out", str(tmp_path), "--check"],
    )
    assert chk.exit_code == 1, chk.output


def test_views_with_bad_on_create_fails_loud(tmp_path):
    schema = _schema(tmp_path)
    views = tmp_path / "prisma" / "views.yaml"
    views.write_text("forms:\n  ProofPoint: { on_create: nope }\n", encoding="utf-8")
    result = runner.invoke(
        generate_app,
        ["backend", "--schema", str(schema), "--views", str(views), "--out", str(tmp_path)],
    )
    assert result.exit_code != 0
    assert "unknown on_create" in result.output


def test_check_detects_handedit(tmp_path):
    schema = _schema(tmp_path)
    runner.invoke(
        generate_app, ["backend", "--schema", str(schema), "--out", str(tmp_path)]
    )
    # tamper an owned file -> --check exits 1
    models = tmp_path / "app" / "models.py"
    models.write_text(
        models.read_text().replace("situation: str", "situation: int"), encoding="utf-8"
    )
    chk = runner.invoke(
        generate_app,
        ["backend", "--schema", str(schema), "--out", str(tmp_path), "--check"],
    )
    assert chk.exit_code == 1


def test_export_openapi_writes_json(tmp_path):
    schema = _schema(tmp_path)
    result = runner.invoke(
        generate_app,
        ["backend", "--schema", str(schema), "--out", str(tmp_path), "--export-openapi"],
    )
    assert result.exit_code == 0, result.output
    export_path = tmp_path / "openapi.json"
    assert export_path.is_file()
    data = __import__("json").loads(export_path.read_text(encoding="utf-8"))
    assert data["openapi"] == "3.0.3"
    assert "/proofpoint/" in data["paths"]


def test_export_openapi_includes_merged_overlay_paths(tmp_path):
    schema = _schema(tmp_path)
    api = tmp_path / "prisma" / "api.yaml"
    api.write_text(
        "paths:\n  /webhooks/stripe:\n    post:\n      responses:\n        '200':\n"
        "          description: OK\n",
        encoding="utf-8",
    )
    result = runner.invoke(
        generate_app,
        [
            "backend",
            "--schema",
            str(schema),
            "--out",
            str(tmp_path),
            "--api",
            str(api),
            "--export-openapi",
        ],
    )
    assert result.exit_code == 0, result.output
    data = __import__("json").loads((tmp_path / "openapi.json").read_text(encoding="utf-8"))
    assert "/webhooks/stripe" in data["paths"]
    assert "/proofpoint/" in data["paths"]


def test_gate_runs_openapi_spec_validation(tmp_path):
    pytest.importorskip("openapi_spec_validator")
    schema = _schema(tmp_path)
    result = runner.invoke(
        generate_app,
        ["backend", "--schema", str(schema), "--out", str(tmp_path), "--gate"],
    )
    assert result.exit_code == 0, result.output
    assert "openapi spec gate: pass" in result.output


def test_generate_with_api_overlay_merges_contract(tmp_path):
    schema = _schema(tmp_path)
    api = tmp_path / "prisma" / "api.yaml"
    api.write_text(
        "paths:\n  /webhooks/stripe:\n    post:\n      responses:\n        '200':\n"
        "          description: OK\n",
        encoding="utf-8",
    )
    result = runner.invoke(
        generate_app,
        [
            "backend",
            "--schema",
            str(schema),
            "--out",
            str(tmp_path),
            "--api",
            str(api),
        ],
    )
    assert result.exit_code == 0, result.output
    contract = (tmp_path / "app" / "openapi_contract.py").read_text(encoding="utf-8")
    assert "/webhooks/stripe" in contract
    assert "# api-sha256:" in contract
    chk = runner.invoke(
        generate_app,
        [
            "backend",
            "--schema",
            str(schema),
            "--out",
            str(tmp_path),
            "--api",
            str(api),
            "--check",
        ],
    )
    assert chk.exit_code == 0, chk.output


def test_generate_with_validation_only_overlay_warns(tmp_path):
    schema = _schema(tmp_path)
    api = tmp_path / "prisma" / "api.yaml"
    api.write_text(
        "paths:\n  /ai/extract:\n    x-startd8-validation-only: true\n    post:\n"
        "      responses:\n        '200':\n          description: OK\n",
        encoding="utf-8",
    )
    result = runner.invoke(
        generate_app,
        [
            "backend",
            "--schema",
            str(schema),
            "--out",
            str(tmp_path),
            "--api",
            str(api),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "validation-only" in result.output
    contract = (tmp_path / "app" / "openapi_contract.py").read_text(encoding="utf-8")
    assert "/ai/extract" not in contract


def test_generate_with_contexts_emits_consumer_client(tmp_path):
    schema = _schema(tmp_path)
    contexts = tmp_path / "prisma" / "contexts.yaml"
    contexts.write_text(
        "outbound:\n  - id: catalog\n    local: true\n    routes: crud\n",
        encoding="utf-8",
    )
    result = runner.invoke(
        generate_app,
        [
            "backend",
            "--schema",
            str(schema),
            "--out",
            str(tmp_path),
            "--contexts",
            str(contexts),
        ],
    )
    assert result.exit_code == 0, result.output
    client = tmp_path / "clients" / "catalog_client.py"
    assert client.is_file()
    assert "CatalogClient" in client.read_text(encoding="utf-8")
    chk = runner.invoke(
        generate_app,
        [
            "backend",
            "--schema",
            str(schema),
            "--out",
            str(tmp_path),
            "--contexts",
            str(contexts),
            "--check",
        ],
    )
    assert chk.exit_code == 0, chk.output
