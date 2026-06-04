"""FR-SAP-12 finding-injection tests: content blocks, gen_context population, consumer forwarding."""

from __future__ import annotations

import pytest

from startd8.sapper.injection import REPORT_ENV, populate_gen_context
from startd8.sapper.models import (
    AssumptionKind,
    AssumptionVerdict,
    FrictionFinding,
    FrictionReport,
    Severity,
    avoidable_cost_stage,
    finding_fingerprint,
)
from startd8.sapper.report import file_blocks, file_blocks_from_json

pytestmark = pytest.mark.unit


def _report():
    return FrictionReport(
        findings=[
            FrictionFinding(
                id="f1",
                kind=AssumptionKind.MODULE_SOURCE,
                verdict=AssumptionVerdict.REFUTED,
                severity=Severity.MEDIUM,
                avoidable_cost_stage=avoidable_cost_stage(AssumptionKind.MODULE_SOURCE),
                fingerprint=finding_fingerprint(AssumptionKind.MODULE_SOURCE, "app/jobs.py", "Match"),
                file="app/jobs.py",
                expected="Match in app.tables",
                found="absent",
                symbol="Match",
            ),
            FrictionFinding(
                id="f2",
                kind=AssumptionKind.FRAMEWORK_IDIOM,
                verdict=AssumptionVerdict.REFUTED,
                severity=Severity.MEDIUM,
                avoidable_cost_stage=avoidable_cost_stage(AssumptionKind.FRAMEWORK_IDIOM),
                fingerprint=finding_fingerprint(AssumptionKind.FRAMEWORK_IDIOM, "app/jobs.py", "flask"),
                file="app/jobs.py",
                expected="FastAPI not Flask",
                found="flask",
            ),
        ]
    )


def test_file_blocks_groups_by_file():
    blocks = file_blocks(_report())
    assert set(blocks) == {"app/jobs.py"}
    assert "Match" in blocks["app/jobs.py"] and "flask" in blocks["app/jobs.py"]


def test_file_blocks_from_json_matches_model():
    blocks = file_blocks_from_json(_report().to_json())
    assert "Match" in blocks["app/jobs.py"]


def test_populate_no_report_is_noop(monkeypatch):
    monkeypatch.delenv(REPORT_ENV, raising=False)
    ctx = {}
    assert populate_gen_context(ctx, ["app/jobs.py"]) is False
    assert "sapper_guidance" not in ctx and "sapper_alignment" not in ctx


def test_populate_with_report_sets_both_keys(tmp_path):
    rpt = tmp_path / "sapper-friction-report.json"
    rpt.write_text(_report().to_json())
    ctx = {}
    ok = populate_gen_context(ctx, ["app/jobs.py"], report_path=str(rpt))
    assert ok is True
    assert "Match" in ctx["sapper_guidance"]       # → micro-prime
    assert ctx["sapper_alignment"] == ctx["sapper_guidance"]  # → lead/drafter spec


def test_populate_skips_files_without_findings(tmp_path):
    rpt = tmp_path / "r.json"
    rpt.write_text(_report().to_json())
    ctx = {}
    assert populate_gen_context(ctx, ["app/other.py"], report_path=str(rpt)) is False
    assert ctx == {}


def test_micro_prime_context_forwards_sapper_guidance():
    from startd8.forward_manifest import ForwardManifest
    from startd8.micro_prime.context import MicroPrimeContext

    gen_context = {"sapper_guidance": "## heed: Match absent"}
    ctx = MicroPrimeContext.from_prime(
        gen_context, ForwardManifest(), ["app/jobs.py"], ollama_available=False
    )
    assert ctx.sapper_guidance == "## heed: Match absent"


def test_env_var_path_is_honored(tmp_path, monkeypatch):
    rpt = tmp_path / "r.json"
    rpt.write_text(_report().to_json())
    monkeypatch.setenv(REPORT_ENV, str(rpt))
    ctx = {}
    assert populate_gen_context(ctx, ["app/jobs.py"]) is True
    assert "sapper_guidance" in ctx
