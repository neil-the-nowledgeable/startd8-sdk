"""M-D wiring — boot-smoke is invoked by the post-mortem and fails non-booting apps honestly.

This is the piece that converts the run-021..026 "compiles but won't import" hollow PASS into a
real FAIL. _evaluate_boot_smoke doesn't use self, so we call it unbound with a dummy self.
"""

from unittest.mock import patch

from startd8.contractors.prime_postmortem import (
    FeaturePostMortem,
    PrimePostMortemEvaluator,
)
from startd8.validators.boot_smoke import BootSmokeResult

_eval = PrimePostMortemEvaluator._evaluate_boot_smoke


def _feat(fid, files):
    return FeaturePostMortem(
        feature_id=fid, name=fid, status="ok", success=True,
        generated_files=list(files), verdict="PASS",
    )


def _project_with_app(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("app = None\n", encoding="utf-8")
    return str(tmp_path)


def test_boot_pass_leaves_features_untouched(tmp_path):
    root = _project_with_app(tmp_path)
    f = _feat("PI-001", ["app/ai/enrich_metrics.py"])
    with patch(
        "startd8.validators.boot_smoke.run_boot_smoke",
        return_value=BootSmokeResult(status="checked", ok=True, routes=("/metric",)),
    ):
        _eval(None, [f], root)
    assert f.success is True and f.verdict == "PASS"


def test_boot_failure_localized_fails_only_culprit(tmp_path):
    root = _project_with_app(tmp_path)
    good = _feat("PI-CRUD", ["app/routers.py"])
    bad = _feat("PI-005", ["app/ai/enrich_metrics.py"])
    failing = BootSmokeResult(
        status="checked", ok=False,
        message="ModuleNotFoundError: No module named 'ai'",
        diagnostics=["Traceback ... app/ai/enrich_metrics.py line 3 ..."],
    )
    with patch("startd8.validators.boot_smoke.run_boot_smoke", return_value=failing):
        _eval(None, [good, bad], root)
    assert bad.success is False and bad.verdict == "FAIL:boot"
    assert good.success is True and good.verdict == "PASS"  # not blamed — name not in trace


def test_boot_failure_unlocalized_fails_all_python_features(tmp_path):
    root = _project_with_app(tmp_path)
    f1 = _feat("PI-001", ["app/ai/a.py"])
    f2 = _feat("PI-002", ["app/ai/b.py"])
    failing = BootSmokeResult(
        status="checked", ok=False, message="ImportError: cannot import name 'X'", diagnostics=[]
    )
    with patch("startd8.validators.boot_smoke.run_boot_smoke", return_value=failing):
        _eval(None, [f1, f2], root)
    assert f1.verdict == "FAIL:boot" and f2.verdict == "FAIL:boot"
    assert not f1.success and not f2.success


def test_unavailable_is_warning_not_fail(tmp_path):
    root = _project_with_app(tmp_path)
    f = _feat("PI-001", ["app/ai/a.py"])
    with patch(
        "startd8.validators.boot_smoke.run_boot_smoke",
        return_value=BootSmokeResult(status="unavailable", message="no fastapi"),
    ):
        _eval(None, [f], root)
    assert f.success is True and f.verdict == "PASS"  # env issue, not a code fault
    cats = [i["category"] for i in f.disk_compliance.semantic_issues]
    assert "boot_smoke_unavailable" in cats


def test_no_app_entrypoint_is_noop(tmp_path):
    f = _feat("PI-001", ["app/ai/a.py"])
    with patch("startd8.validators.boot_smoke.run_boot_smoke") as m:
        _eval(None, [f], str(tmp_path))  # no app/main.py or app/server.py
    m.assert_not_called()
    assert f.success is True


def test_prefers_server_entrypoint_over_main(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("app=None\n", encoding="utf-8")
    (tmp_path / "app" / "server.py").write_text("app=None\n", encoding="utf-8")
    f = _feat("PI-001", ["app/ai/a.py"])
    with patch(
        "startd8.validators.boot_smoke.run_boot_smoke",
        return_value=BootSmokeResult(status="checked", ok=True),
    ) as m:
        _eval(None, [f], str(tmp_path))
    assert m.call_args.kwargs["app"] == "app.server:app"
