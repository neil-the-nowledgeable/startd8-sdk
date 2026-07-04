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
    # All v1 actions (survey/assess/instantiate/log-friction/derive) are now implemented —
    # DEFERRED_ACTIONS is empty. The known-actions listing uses the M0b canonical names (the old
    # `instantiate-kickoff`/`derive-contract` values still dispatch via the alias window). An
    # out-of-scope action degrades gracefully (a clear ConciergeError), never an opaque crash.
    import pytest

    with pytest.raises(ConciergeError) as exc:
        handle_concierge_tool("teleport", project)
    assert "teleport" in str(exc.value) and "derive" in str(exc.value)


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


# ── M2: kernel-owned coverage; the panel-in-assess edge is cut (FR-13/FR-15, R1-F4/R2-F2) ──


def test_assess_reports_only_kernel_owned_domains(tmp_path):
    """assess coverage is the kernel-owned KICKOFF_INPUT_DOMAINS ONLY — no ``stakeholders`` domain.

    The Stakeholder Panel is an optional, later discovery offer (M4), not a kernel input domain, so
    it must never be injected into kernel ``assess`` output (FR-15 panel half).
    """
    from startd8.concierge.core import KICKOFF_INPUT_DOMAINS

    root = tmp_path / "kp"
    (root / "docs" / "kickoff" / "inputs").mkdir(parents=True)
    domains = handle_concierge_tool("assess", root)["kickoff_inputs"]["domains"]
    assert set(domains) == set(KICKOFF_INPUT_DOMAINS)
    assert "stakeholders" not in domains  # the panel-in-assess edge is cut (M2)


def test_assess_core_does_not_import_stakeholder_panel():
    """The kernel coverage core carries no reference to ``stakeholder_panel`` / ``PANEL_CONSUMABLE``.

    R1-F4: removing the domain-list coupling is not enough — the module source must not name the
    package or the ship-state flag anywhere in executable code.
    """
    import ast
    import inspect

    from startd8.concierge import core as core_mod

    tree = ast.parse(inspect.getsource(core_mod))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any(m.startswith("startd8.stakeholder_panel") for m in imported), imported
    # No bare-name reference to the removed coupling flag in any executable node.
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "PANEL_CONSUMABLE" not in names


def test_assess_byte_identical_when_panel_absent(tmp_path, monkeypatch):
    """R2-F2: with ``stakeholder_panel`` REMOVED from the import graph, ``assess`` output is
    byte-identical to a build that never knew the panel existed — true absence, not a degrading
    ``try/except ImportError`` that returns different output.

    Mechanism: capture the baseline ``assess`` output, then make the package genuinely
    un-importable — evict every ``startd8.stakeholder_panel*`` module from ``sys.modules`` AND wrap
    ``builtins.__import__`` to raise ``ImportError`` on any attempt to import it — and re-invoke
    ``build_assess``. If any code path still reached into the panel (e.g. a residual
    ``try/except ImportError`` that degrades to different output), the blocked run would either crash
    or diverge; asserting canonical-JSON byte-equality proves neither happens.

    (Companion coverage: ``test_assess_core_does_not_import_stakeholder_panel`` proves the SOURCE
    names no panel import, so this test does not need a module reload to exercise import-time
    coupling — a reload would replace the module object and break symbols other tests hold.)
    """
    import builtins
    import json
    import sys

    from startd8.concierge.core import build_assess

    root = tmp_path / "kp"
    (root / "docs" / "kickoff" / "inputs").mkdir(parents=True)
    (root / "docs" / "kickoff" / "inputs" / "stakeholders.yaml").write_text(
        # A perfectly valid roster — under the old edge this populated a `stakeholders` domain.
        "domain: stakeholders\n"
        "personas:\n"
        "  - role_id: product-owner\n"
        "    display_name: Product Owner\n"
        "    goals: ['ship']\n",
        encoding="utf-8",
    )

    def _canonical(obj) -> str:
        return json.dumps(obj, sort_keys=True, indent=2)

    baseline = _canonical(build_assess(root))

    # Make the panel package genuinely un-importable, then re-run assess.
    real_import = builtins.__import__

    def _blocking_import(name, *args, **kwargs):
        if name == "startd8.stakeholder_panel" or name.startswith("startd8.stakeholder_panel."):
            raise ImportError(f"blocked for test: {name}")
        return real_import(name, *args, **kwargs)

    for mod in [m for m in sys.modules if m.startswith("startd8.stakeholder_panel")]:
        monkeypatch.delitem(sys.modules, mod, raising=False)
    monkeypatch.setattr(builtins, "__import__", _blocking_import)

    blocked = _canonical(build_assess(root))

    assert blocked == baseline


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
