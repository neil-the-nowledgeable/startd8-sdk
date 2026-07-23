# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Unit tests for the Tier-B merge, orchestrator, and CI gate — zero docker."""

from __future__ import annotations

import json

import pytest

from startd8.observability import compare_live, live_standup
from startd8.observability.compare import ComparisonReport
from startd8.observability.validate_promql import ExprVerdict, FidelityReport


# ── builders ────────────────────────────────────────────────────────────────

def _comparison(gaps=None, emitted=("FR-1",)):
    return ComparisonReport(emitted=list(emitted), gaps=gaps or {})


def _fidelity(status="pass", verdicts=()):
    return FidelityReport(
        status=status, reason=f"{status} reason", queries_replayed=len(verdicts) or 1,
        coverage=1.0 if status == "pass" else 0.0, min_coverage=1.0,
        binding_coverage=1.0 if status == "pass" else 0.0,
        verdicts=list(verdicts),
    )


def _v(verdict, service="web", signal="latency", source_file="slos/web.yaml", expr="histogram(x)"):
    return ExprVerdict(
        service=service, signal=signal, expr=expr, source_file=source_file,
        live_result_count=0 if verdict == "fail" else 3, verdict=verdict,
    )


# ── build_live_comparison — the rollup truth table ──────────────────────────

def test_merge_standup_failed_is_unknown_but_keeps_tier_a():
    gaps = {"empty_services": ["cartservice"]}
    r = compare_live.build_live_comparison(_comparison(gaps), None, {"reason": "no scrape landed"})
    assert r.status == "unknown"
    assert r.tier_b is None
    assert r.total_gaps == 1
    assert r.tier_a["gaps"] == gaps
    assert r.exit_code() == 3


def test_merge_all_pass_no_gaps_is_pass():
    r = compare_live.build_live_comparison(_comparison(), _fidelity("pass", [_v("pass")]), {"skipped": "x"})
    assert r.status == "pass"
    assert r.exit_code() == 0
    assert r.fail_verdicts == []


def test_merge_tier_b_fail_dominates_tier_a_pass():
    r = compare_live.build_live_comparison(
        _comparison(), _fidelity("fail", [_v("fail"), _v("pass")]), {"skipped": "x"})
    assert r.status == "fail"
    assert r.exit_code() == 2
    assert len(r.fail_verdicts) == 1


def test_merge_tier_a_gaps_advisory_by_default():
    gaps = {"unfulfilled": [{"id": "FR-9"}]}
    r = compare_live.build_live_comparison(_comparison(gaps), _fidelity("pass", [_v("pass")]), {})
    assert r.status == "pass"  # gaps present but advisory
    assert r.total_gaps == 1


def test_merge_tier_a_gaps_fail_under_strict():
    gaps = {"unfulfilled": [{"id": "FR-9"}]}
    r = compare_live.build_live_comparison(
        _comparison(gaps), _fidelity("pass", [_v("pass")]), {}, strict_tier_a=True)
    assert r.status == "fail"
    assert "static gap" in r.reason


def test_merge_fidelity_unknown_stays_unknown():
    r = compare_live.build_live_comparison(_comparison(), _fidelity("unknown"), {})
    assert r.status == "unknown"


# ── run_live_comparison — seam-injected orchestration ───────────────────────

def test_run_existing_prometheus_skips_standup(tmp_path):
    manifest = tmp_path / "m.yaml"
    manifest.write_text("fr_coverage: {}\n")
    seen = {}

    def fake_validate(**kw):
        seen.update(kw)
        return _fidelity("pass", [_v("pass")])

    def fake_standup(**kw):  # must NOT be called
        raise AssertionError("standup should be skipped on the --prometheus path")

    r = compare_live.run_live_comparison(
        manifest=manifest, prometheus="http://localhost:9090",
        artifacts_dir=tmp_path, onboarding_metadata=tmp_path / "md.json",
        validate_fn=fake_validate, standup_fn=fake_standup,
        read_fr_coverage_fn=lambda p: {},
    )
    assert r.status == "pass"
    assert seen["prometheus_url"] == "http://localhost:9090"


def test_run_standup_scrape_fail_is_unknown_and_tears_down(tmp_path):
    manifest = tmp_path / "m.yaml"
    manifest.write_text("fr_coverage: {}\n")
    torn = {"n": 0}

    def fake_standup(**kw):
        return live_standup.StandupHandle(
            prometheus_url="", job_name="subject", network="net",
            subject_container="s", prometheus_container="p",
            scrape_ready=False, reason="no scrape landed within 60s",
        )

    def fake_validate(**kw):
        raise AssertionError("validate must not run when the scrape never landed")

    r = compare_live.run_live_comparison(
        manifest=manifest, subject_image="s:1",
        standup_fn=fake_standup, validate_fn=fake_validate,
        teardown_fn=lambda h: torn.__setitem__("n", torn["n"] + 1),
        read_fr_coverage_fn=lambda p: {},
    )
    assert r.status == "unknown"
    assert torn["n"] == 1  # teardown fired


def test_run_teardown_fires_even_when_validate_raises(tmp_path):
    manifest = tmp_path / "m.yaml"
    manifest.write_text("fr_coverage: {}\n")
    torn = {"n": 0}

    def fake_standup(**kw):
        return live_standup.StandupHandle(
            prometheus_url="http://127.0.0.1:9", job_name="subject", network="net",
            subject_container="s", prometheus_container="p", scrape_ready=True,
        )

    def boom(**kw):
        raise RuntimeError("replay exploded")

    with pytest.raises(RuntimeError):
        compare_live.run_live_comparison(
            manifest=manifest, subject_image="s:1",
            standup_fn=fake_standup, validate_fn=boom,
            teardown_fn=lambda h: torn.__setitem__("n", torn["n"] + 1),
            read_fr_coverage_fn=lambda p: {},
        )
    assert torn["n"] == 1  # teardown still fired via finally


def test_run_keep_up_skips_teardown(tmp_path):
    manifest = tmp_path / "m.yaml"
    manifest.write_text("fr_coverage: {}\n")
    torn = {"n": 0}

    def fake_standup(**kw):
        return live_standup.StandupHandle(
            prometheus_url="http://127.0.0.1:9", job_name="subject", network="net",
            subject_container="s", prometheus_container="p", scrape_ready=True,
        )

    compare_live.run_live_comparison(
        manifest=manifest, subject_image="s:1", keep_up=True,
        standup_fn=fake_standup, validate_fn=lambda **kw: _fidelity("pass", [_v("pass")]),
        teardown_fn=lambda h: torn.__setitem__("n", torn["n"] + 1),
        read_fr_coverage_fn=lambda p: {},
    )
    assert torn["n"] == 0  # --keep-up left it running


def test_run_no_subject_and_no_prometheus_is_unknown(tmp_path):
    manifest = tmp_path / "m.yaml"
    manifest.write_text("fr_coverage: {}\n")
    r = compare_live.run_live_comparison(manifest=manifest, read_fr_coverage_fn=lambda p: {})
    assert r.status == "unknown"


# ── CI gate (FR-8) ──────────────────────────────────────────────────────────

def test_verdict_id_stable_across_whitespace_and_path():
    a = compare_live.verdict_id(
        {"service": "web", "signal": "lat", "source_file": "slos/web.yaml", "expr": "sum( x )"})
    b = compare_live.verdict_id(
        {"service": "web", "signal": "lat", "source_file": "/abs/slos/web.yaml", "expr": "sum(  x  )"})
    assert a == b  # dir-qualified key (slos/web.yaml) + normalized expr


def test_verdict_id_distinguishes_same_basename_different_dirs():
    # R1-F8/S2: a bare basename would collide alerts/foo.yaml with dashboards/foo.yaml,
    # letting a genuinely-new dead SLI slip a baseline built from the other file.
    alert = compare_live.verdict_id(
        {"service": "web", "signal": "lat", "source_file": "alerts/foo.yaml", "expr": "x"})
    dash = compare_live.verdict_id(
        {"service": "web", "signal": "lat", "source_file": "dashboards/foo.yaml", "expr": "x"})
    assert alert != dash


def test_ci_gate_new_fail_in_second_dir_not_masked_by_baseline():
    fail = _v("fail", source_file="dashboards/foo.yaml")
    r = compare_live.build_live_comparison(_comparison(), _fidelity("fail", [fail]), {})
    # baseline only accepts the SAME-basename fail from the OTHER dir
    baseline = {compare_live.verdict_id(
        {"service": "web", "signal": "latency", "source_file": "alerts/foo.yaml", "expr": "histogram(x)"})}
    code, new = compare_live.ci_gate(r, baseline=baseline)
    assert code == 2 and len(new) == 1  # not masked


def test_ci_gate_new_fail_exits_2():
    r = compare_live.build_live_comparison(_comparison(), _fidelity("fail", [_v("fail")]), {})
    code, new = compare_live.ci_gate(r, baseline=set())
    assert code == 2
    assert len(new) == 1


def test_ci_gate_baselined_fail_exits_0():
    fail = _v("fail")
    r = compare_live.build_live_comparison(_comparison(), _fidelity("fail", [fail]), {})
    baseline = {compare_live.verdict_id(r.fail_verdicts[0])}
    code, new = compare_live.ci_gate(r, baseline=baseline)
    assert code == 0
    assert new == []


def test_ci_gate_unknown_exits_3():
    r = compare_live.build_live_comparison(_comparison(), None, {"reason": "no scrape"})
    code, new = compare_live.ci_gate(r, baseline=set())
    assert code == 3


def test_ci_gate_fail_flipped_to_pass_exits_0():
    # a previously-baselined fail that now passes → no new fail → clean
    r = compare_live.build_live_comparison(_comparison(), _fidelity("pass", [_v("pass")]), {})
    code, new = compare_live.ci_gate(r, baseline={"web|latency|web.yaml|histogram(x)"})
    assert code == 0


def test_load_and_render_baseline_roundtrip(tmp_path):
    r = compare_live.build_live_comparison(
        _comparison(), _fidelity("fail", [_v("fail"), _v("fail", service="cart")]), {})
    payload = compare_live.render_baseline(r, subject="ref:1", note="seed")
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(payload))
    loaded = compare_live.load_baseline(path)
    assert len(loaded) == 2
    # gate is clean against its own baseline
    code, _ = compare_live.ci_gate(r, loaded)
    assert code == 0


def test_load_baseline_absent_is_empty(tmp_path):
    assert compare_live.load_baseline(tmp_path / "nope.json") == set()


# ── renderer ────────────────────────────────────────────────────────────────

def test_report_carries_a_versioned_schema():
    # R1-F7: --json is the CI-consumed contract; the key set is versioned.
    r = compare_live.build_live_comparison(_comparison(), _fidelity("pass", [_v("pass")]), {})
    d = r.to_dict()
    assert d["report_version"] == compare_live.LiveComparisonReport.REPORT_VERSION
    assert set(["status", "reason", "total_gaps", "fail_verdicts", "tier_a", "tier_b", "standup"]) <= set(d)


def test_pass_with_advisory_gaps_surfaces_gap_count():
    # R1-S1: a Tier-B pass must not silently bury a large Tier-A gap set.
    gaps = {"empty_services": ["a", "b", "c"], "unfulfilled": [{"id": "FR-9"}]}
    r = compare_live.build_live_comparison(_comparison(gaps), _fidelity("pass", [_v("pass")]), {})
    assert r.status == "pass"
    assert "4 advisory static gap" in r.reason  # count is load-bearing in the reason


def test_render_live_report_shows_status_and_dead_slis():
    r = compare_live.build_live_comparison(
        _comparison({"empty_services": ["cart"]}), _fidelity("fail", [_v("fail")]), {})
    out = compare_live.render_live_report(r)
    assert "FAIL" in out
    assert "Tier B" in out and "Tier A" in out
    assert "dead (fail) 1" in out


# ── FR-8a: the CLI surfaces the new-vs-baseline regression set (not just the exit code) ──

def _cli_report():
    # a FAIL live report with two dead SLIs on distinct services
    return compare_live.build_live_comparison(
        _comparison(), _fidelity("fail", [_v("fail", service="web"), _v("fail", service="cart")]), {})


def _invoke_compare_live(monkeypatch, tmp_path, *extra):
    from typer.testing import CliRunner
    from startd8.observability import compare_live as cl
    from startd8.observability.cli import observability_app

    monkeypatch.setattr(cl, "run_live_comparison", lambda **kw: _cli_report())
    manifest = tmp_path / "m.yaml"
    manifest.write_text("fr_coverage: {}\n")
    baseline = tmp_path / "baseline.json"
    baseline.write_text('{"accepted_fail_ids": []}')  # empty ⇒ every fail is NEW
    return CliRunner().invoke(
        observability_app,
        ["compare-live", "-m", str(manifest), "--subject-image", "x:1",
         "--baseline", str(baseline), *extra],
    )


def test_cli_surfaces_new_fails_human(monkeypatch, tmp_path):
    res = _invoke_compare_live(monkeypatch, tmp_path)
    assert res.exit_code == 2
    assert "2 NEW dead SLI(s) vs baseline" in res.output
    assert "web/latency" in res.output and "cart/latency" in res.output


def test_cli_new_fails_in_json(monkeypatch, tmp_path):
    res = _invoke_compare_live(monkeypatch, tmp_path, "--json")
    assert res.exit_code == 2
    payload = json.loads(res.output)
    assert len(payload["new_fail_verdicts"]) == 2
    # --json carries the machine field but not the human "NEW dead SLI(s)" block
    assert "NEW dead SLI(s) vs baseline" not in res.output


def test_cli_clean_gate_no_new_block(monkeypatch, tmp_path):
    # baseline that already accepts both fails ⇒ 0 new ⇒ exit 0, no NEW block
    from typer.testing import CliRunner
    from startd8.observability import compare_live as cl
    from startd8.observability.cli import observability_app

    report = _cli_report()
    monkeypatch.setattr(cl, "run_live_comparison", lambda **kw: report)
    manifest = tmp_path / "m.yaml"
    manifest.write_text("fr_coverage: {}\n")
    baseline = tmp_path / "baseline.json"
    ids = [compare_live.verdict_id(v) for v in report.fail_verdicts]
    baseline.write_text(json.dumps({"accepted_fail_ids": ids}))
    res = CliRunner().invoke(
        observability_app,
        ["compare-live", "-m", str(manifest), "--subject-image", "x:1", "--baseline", str(baseline)],
    )
    assert res.exit_code == 0
    assert "NEW dead SLI(s)" not in res.output
