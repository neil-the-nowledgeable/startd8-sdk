"""Tests for project-level TS/Prisma toolchain verification (RUN-008 FR-4/5/9).

Pure parsing + the FR-9 degradation contract are tested without a Node toolchain;
the postmortem wiring is tested by monkeypatching the subprocess runner.
"""

from __future__ import annotations

import startd8.validators.ts_toolchain as tc
from startd8.validators.ts_toolchain import (
    ToolchainResult,
    TscDiagnostic,
    diagnostics_by_file,
    parse_tsc_output,
    run_project_typecheck,
)

# Real run-008 tsc output (from the spike).
RUN008_TSC = """\
app/api/profile/route-asis.ts(2,31): error TS2307: Cannot find module '@/lib/schemas' or its corresponding type declarations.
app/api/profile/route-asis.ts(15,7): error TS2322: Type '{ ownerId: string; }' is not assignable to type 'ProfileWhereUniqueInput'.
  Type '{ ownerId: string; }' is not assignable to type '{ id: string; }'.
    Property 'id' is missing in type '{ ownerId: string; }' but required in type '{ id: string; }'.
"""


class TestParse:
    def test_parses_run008_diagnostics(self):
        diags = parse_tsc_output(RUN008_TSC)
        assert len(diags) == 2  # continuation lines ignored
        assert diags[0].code == "TS2307"
        assert diags[0].line == 2 and diags[0].col == 31
        assert "Cannot find module '@/lib/schemas'" in diags[0].message
        assert diags[1].code == "TS2322"

    def test_empty(self):
        assert parse_tsc_output("") == []
        assert parse_tsc_output("Compilation complete. Watching for changes.") == []

    def test_group_by_file(self):
        grouped = diagnostics_by_file(parse_tsc_output(RUN008_TSC))
        assert "app/api/profile/route-asis.ts" in grouped
        assert len(grouped["app/api/profile/route-asis.ts"]) == 2


class TestVerdictContract:
    """FR-9: anything other than a clean check is non-pass."""

    def test_pass(self):
        assert ToolchainResult(status="checked", diagnostics=[]).verdict == "pass"
        assert ToolchainResult(status="checked", diagnostics=[]).is_pass is True

    def test_fail(self):
        r = ToolchainResult(status="checked", diagnostics=[TscDiagnostic("a.ts", 1, 1, "TS2307", "x")])
        assert r.verdict == "fail"
        assert r.is_pass is False

    def test_unavailable_is_not_pass(self):
        for status in ("unavailable", "timeout", "error"):
            r = ToolchainResult(status=status)
            assert r.verdict == "unavailable"
            assert r.is_pass is False  # the load-bearing FR-9 property


class TestDegradation:
    def test_no_node_modules_is_unavailable(self, tmp_path):
        # a TS project dir with no node_modules → unavailable, never a silent pass
        (tmp_path / "tsconfig.json").write_text("{}")
        result = run_project_typecheck(str(tmp_path))
        assert result.status == "unavailable"
        assert result.is_pass is False


class TestEnvGate:
    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("STARTD8_TS_TYPECHECK", raising=False)
        assert tc.typecheck_enabled() is False

    def test_enabled_values(self, monkeypatch):
        for v in ("1", "true", "on", "YES"):
            monkeypatch.setenv("STARTD8_TS_TYPECHECK", v)
            assert tc.typecheck_enabled() is True


class TestPostmortemWiring:
    def _feature(self):
        from startd8.contractors.prime_postmortem import FeaturePostMortem
        return FeaturePostMortem(
            feature_id="PI-012", name="profile route", status="completed",
            success=True, verdict="PASS", generated_files=["app/api/profile/route.ts"],
        )

    def test_disabled_is_noop(self, monkeypatch):
        from startd8.contractors.prime_postmortem import PrimePostMortemEvaluator
        monkeypatch.setattr(tc, "typecheck_enabled", lambda: False)
        feat = self._feature()
        PrimePostMortemEvaluator()._evaluate_ts_toolchain([feat], "/tmp/whatever")
        assert feat.success is True and feat.verdict == "PASS"

    def test_diagnostics_flip_feature_to_fail(self, monkeypatch):
        from startd8.contractors.prime_postmortem import (
            PrimePostMortemEvaluator, RootCause, PipelineStage,
        )
        monkeypatch.setattr(tc, "typecheck_enabled", lambda: True)
        monkeypatch.setattr(tc, "run_project_typecheck", lambda *a, **k: ToolchainResult(
            status="checked",
            diagnostics=[TscDiagnostic("app/api/profile/route.ts", 2, 31, "TS2307",
                                       "Cannot find module '@/lib/schemas'")],
        ))
        feat = self._feature()
        PrimePostMortemEvaluator()._evaluate_ts_toolchain([feat], "/tmp/proj")
        assert feat.success is False
        assert feat.verdict == "FAIL:typecheck"
        assert feat.root_cause == RootCause.CROSS_FILE_CONTRACT
        assert feat.pipeline_stage == PipelineStage.CROSS_FEATURE_CONTRACT
        cats = {i["category"] for i in feat.disk_compliance.semantic_issues}
        assert "tsc_TS2307" in cats

    def test_unavailable_warns_without_flipping(self, monkeypatch):
        from startd8.contractors.prime_postmortem import PrimePostMortemEvaluator
        monkeypatch.setattr(tc, "typecheck_enabled", lambda: True)
        monkeypatch.setattr(tc, "run_project_typecheck", lambda *a, **k: ToolchainResult(
            status="unavailable", message="node_modules not installed"))
        feat = self._feature()
        PrimePostMortemEvaluator()._evaluate_ts_toolchain([feat], "/tmp/proj")
        # FR-9: surfaced, not silent — but not a code-fault flip
        assert feat.success is True
        cats = {i["category"] for i in feat.disk_compliance.semantic_issues}
        assert "ts_verification_unavailable" in cats
