"""Unit tests for the Concierge read-only core (survey + assess).

Spike-grade coverage of CONCIERGE_MCP_REQUIREMENTS.md v0.3 read-only actions. Uses a synthetic
tmp project so it is hermetic (no dependency on navig8's absolute path). The MCP wrapper
(startd8_concierge) is exercised separately and needs the `mcp` package; these tests cover the
SDK logic the wrapper delegates to.
"""

from __future__ import annotations

import pytest

from startd8.concierge import (
    SCHEMA_VERSION,
    ConciergeError,
    build_survey,
    handle_concierge_tool,
)


@pytest.fixture
def project(tmp_path):
    """A small brownfield-ish project: a PRD, a fixture, a model, a PII file, pipeline noise."""
    root = tmp_path / "proj"
    (root / "docs").mkdir(parents=True)
    # A requirement doc that does NOT match the extraction format (F-4 case).
    (root / "docs" / "PRD_thing.md").write_text("# PRD\n\nSome requirements prose.\n", encoding="utf-8")
    # A requirement doc that DOES match (has all four anchor headings).
    (root / "REQUIREMENTS_app.md").write_text(
        "# Reqs\n## Entities\n...\nAI assists\nOwned fields\nCoverage\n", encoding="utf-8"
    )
    # A fixture, a Pydantic model, and a PII-flagged file.
    (root / "TEST_USERS.md").write_text("rows\n", encoding="utf-8")
    (root / "models.py").write_text("from pydantic import BaseModel\nclass Foo(BaseModel):\n    x: int\n", encoding="utf-8")
    (root / "paystub_2025.pdf").write_bytes(b"%PDF-1.4 not really\n")
    # Pipeline scratch whose design docs must NOT be mistaken for product requirement docs.
    (root / ".cap-dev-pipe" / "design").mkdir(parents=True)
    (root / ".cap-dev-pipe" / "design" / "SOME_REQUIREMENTS.md").write_text("noise\n", encoding="utf-8")
    return root


def test_survey_shape_and_schema(project):
    s = build_survey(project)
    assert s["schema_version"] == SCHEMA_VERSION
    assert s["action"] == "survey"
    assert s["project_root"] == str(project.resolve())


def test_survey_extraction_format_detection(project):
    s = build_survey(project)
    by_path = {d["path"]: d["extraction_format"] for d in s["requirement_docs"]}
    assert by_path["REQUIREMENTS_app.md"] is True       # has all four anchor headings
    assert by_path["docs/PRD_thing.md"] is False         # prose only — needs the F-4 reformat


def test_survey_finds_models_fixtures_and_flags_pii(project):
    s = build_survey(project)
    assert "models.py" in s["model_files"]
    assert "TEST_USERS.md" in s["fixture_candidates"]
    assert "paystub_2025.pdf" in s["pii_risk_flags"]


def test_survey_excludes_pipeline_scratch(project):
    s = build_survey(project)
    paths = [d["path"] for d in s["requirement_docs"]]
    assert not any(p.startswith(".cap-dev-pipe") for p in paths)


def test_handle_unknown_action_raises(project):
    with pytest.raises(ConciergeError):
        handle_concierge_tool("nuke", project)


def test_handle_unknown_action_raises_not_crash(project):
    # All v1 actions (survey/assess/instantiate-kickoff/log-friction/derive-contract) are now
    # implemented — DEFERRED_ACTIONS is empty. An out-of-scope action degrades gracefully
    # (a clear ConciergeError listing the known actions), never an opaque crash.
    import pytest

    with pytest.raises(ConciergeError) as exc:
        handle_concierge_tool("teleport", project)
    assert "teleport" in str(exc.value) and "derive-contract" in str(exc.value)


def test_survey_is_pure_no_writes(project):
    """Read-only posture (FR-C2/C3): survey must not mutate the tree."""
    before = sorted(p.name for p in project.rglob("*"))
    build_survey(project)
    after = sorted(p.name for p in project.rglob("*"))
    assert before == after


def test_assess_kickoff_inputs_provenance(tmp_path):
    """assess reports per-domain provenance honestly (the kickoff-input half)."""
    root = tmp_path / "kp"
    inputs = root / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "conventions.yaml").write_text("domain: conventions\nprovenance_default: authored\n", encoding="utf-8")
    (inputs / "business-targets.yaml").write_text("domain: business-targets\nprovenance_default: estimate\n", encoding="utf-8")
    # observability + build-preferences deliberately absent.
    out = handle_concierge_tool("assess", root)
    domains = out["kickoff_inputs"]["domains"]
    assert domains["conventions"] == {"status": "present", "provenance_default": "authored"}
    assert domains["business-targets"]["provenance_default"] == "estimate"
    assert domains["observability"]["status"] == "absent"
    # cascade half always present (wraps wireframe); shape is env-dependent, status key is not.
    assert "status" in out["cascade"]


_COHERENT_DEPLOYED = (
    "app:\n  name: demo\n"
    "deployment:\n  mode: deployed\n"
    "persistence:\n  path: postgresql://db/app\n"
    "deploy:\n  trust_gateway: true\n  target_cloud: gke\n"
)


def test_assess_deployment_not_declared(tmp_path):
    """FR-CDA-1: no app.yaml → not-declared, never a crash."""
    dep = handle_concierge_tool("assess", tmp_path)["deployment"]
    assert dep["status"] == "not-declared" and dep["readiness"] == "not-declared"


def test_assess_deployment_installed(tmp_path):
    (tmp_path / "app.yaml").write_text("app:\n  name: d\n", encoding="utf-8")
    dep = handle_concierge_tool("assess", tmp_path)["deployment"]
    assert dep["mode"] == "installed" and dep["readiness"] == "not-declared"


def test_assess_deployment_declared_not_generated(tmp_path):
    (tmp_path / "app.yaml").write_text(
        _COHERENT_DEPLOYED + "  environments:\n    prod: {}\n    staging: {}\n", encoding="utf-8")
    dep = handle_concierge_tool("assess", tmp_path)["deployment"]
    assert dep["mode"] == "deployed"
    assert dep["deploy"]["target_cloud"] == "gke" and dep["deploy"]["trust_gateway"] is True
    assert dep["environments"] == ["prod", "staging"]      # sorted
    assert dep["readiness"] == "declared-not-generated"
    assert dep["verdict"] in ("ok", "soft")               # coherent → not hard


def test_assess_deployment_generated_and_stale(tmp_path):
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "infra-contract.yaml").write_text(
        "environments:\n  prod: {}\nbindings:\n  - {name: db, status: bound}\n"
        "  - {name: cache, status: pending}\n", encoding="utf-8")
    # declares prod (present) + staging (absent from contract) → stale, and 1 unbound binding.
    (tmp_path / "app.yaml").write_text(
        _COHERENT_DEPLOYED + "  environments:\n    prod: {}\n    staging: {}\n", encoding="utf-8")
    dep = handle_concierge_tool("assess", tmp_path)["deployment"]
    assert dep["readiness"] == "stale"
    assert dep["unbound_bindings"] == 1


def test_assess_deployment_never_leaks_secret_values(tmp_path):
    # A secret-looking value in the infra-contract must never appear in the assess JSON (R1-S9).
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "infra-contract.yaml").write_text(
        "bindings:\n  - {name: db_password, status: bound, value: SUPER_SECRET_123}\n",
        encoding="utf-8")
    (tmp_path / "app.yaml").write_text(_COHERENT_DEPLOYED, encoding="utf-8")
    import json
    blob = json.dumps(handle_concierge_tool("assess", tmp_path)["deployment"])
    assert "SUPER_SECRET_123" not in blob


def test_assess_deployment_malformed_fail_closed(tmp_path):
    (tmp_path / "app.yaml").write_text("app: [this: is, not: valid\n", encoding="utf-8")
    dep = handle_concierge_tool("assess", tmp_path)["deployment"]
    assert dep["status"] == "invalid" and dep["verdict"] == "hard"
