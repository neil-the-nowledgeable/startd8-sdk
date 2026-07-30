"""WP-B0: AffordanceMap load / plan / join / merge / exit codes (AC-G2, G6–G11)."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from startd8.observability.affordance_map_consume import (
    EXIT_ALL_SKIPPED,
    EXIT_MALFORMED,
    EXIT_OK,
    GEN_EMIT_RED,
    GEN_ENRICH_RUNBOOK,
    GEN_IMPROVE_COVERAGE,
    KNOWN_GEN_AFFORDANCES,
    LIVE_GEN,
    UNREACHABLE_GEN,
    AffordanceMapEntry,
    exit_code_for_plan,
    format_plan_for_dry_run,
    load_affordance_map,
    match_service_id,
    merge_manifest_artifacts,
    merge_quality_services,
    normalize_element_id,
    plan_affordance_actions,
    write_affordance_actions_report,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "affordance_map"
OBS_PKG = Path(__file__).resolve().parents[3] / "src" / "startd8" / "observability"


# ---- AC-G7: no contextcore import -------------------------------------------


def test_no_contextcore_import_in_observability_package():
    offenders = []
    for py in OBS_PKG.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "contextcore" or alias.name.startswith(
                        "contextcore."
                    ):
                        offenders.append(f"{py.name}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod == "contextcore" or mod.startswith("contextcore."):
                    offenders.append(f"{py.name}: from {mod}")
    assert not offenders, f"NR-G1 / AC-G7 violated:\n" + "\n".join(offenders)


# ---- Load -------------------------------------------------------------------


def test_load_slim_array():
    result = load_affordance_map(FIXTURES / "slim_array.json")
    assert result.ok
    assert result.source_shape == "array"
    assert len(result.entries) == 5
    assert not result.source_truncated


def test_load_scorecard_shape():
    result = load_affordance_map(FIXTURES / "scorecard_shape.json")
    assert result.ok
    assert result.source_shape == "scorecard"
    assert len(result.entries) >= 1


def test_load_truncated_history_stamps_flag():
    result = load_affordance_map(FIXTURES / "truncated_history.json")
    assert result.ok
    assert result.source_truncated is True


def test_load_malformed_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    result = load_affordance_map(bad)
    assert not result.ok
    assert exit_code_for_plan(result, plan_affordance_actions([], [])) == EXIT_MALFORMED


def test_known_gen_set_frozen():
    assert GEN_EMIT_RED in KNOWN_GEN_AFFORDANCES
    assert GEN_IMPROVE_COVERAGE not in LIVE_GEN
    assert GEN_ENRICH_RUNBOOK in LIVE_GEN
    assert GEN_ENRICH_RUNBOOK not in UNREACHABLE_GEN
    assert len(KNOWN_GEN_AFFORDANCES) == 5
    assert not UNREACHABLE_GEN


# ---- Join (FR-B6a / AC-G10) -------------------------------------------------


@pytest.mark.parametrize(
    "element_id,expected",
    [
        ("PRODUCT_CATALOG", "productcatalogservice"),
        ("PRODUCT_CATALOG_SERVICE", "productcatalogservice"),
        ("store", "store"),
        ("query-frontend", "query-frontend"),
    ],
)
def test_normalize_element_id(element_id, expected):
    assert normalize_element_id(element_id) == expected


def test_join_table_fixture():
    table = json.loads((FIXTURES / "join_table.json").read_text())
    for case in table["cases"]:
        assert normalize_element_id(case["element_id"]) == case["normalized"]
        matched = match_service_id(case["element_id"], case["hints"])
        assert matched == case["matched"], case


def test_env_form_map_produces_nonempty_plan():
    load = load_affordance_map(FIXTURES / "env_form_ids.json")
    plan = plan_affordance_actions(
        load.entries,
        ["productcatalogservice", "store"],
    )
    assert plan.actions, "ENV_FORM ids must join to slug services (AC-G10)"
    assert all(a.service_id == "productcatalogservice" for a in plan.actions)


# ---- Plan / dry-run / exit --------------------------------------------------


def test_plan_priority_and_advisory_skips():
    load = load_affordance_map(FIXTURES / "slim_array.json")
    plan = plan_affordance_actions(
        load.entries, ["store", "query-frontend"]
    )
    live_ids = [a.affordance_id for a in plan.actions]
    assert GEN_EMIT_RED in live_ids
    assert "gen.shrink_dashboard_lines" in live_ids
    skip_reasons = {s.affordance_id: s.reason for s in plan.skips}
    assert skip_reasons.get(GEN_IMPROVE_COVERAGE) == "no_deterministic_lever"
    assert GEN_ENRICH_RUNBOOK in live_ids
    # rex.* on unknown element_id → unknown_element_id; on known svc → non_gen
    assert any(
        s.reason.startswith("unknown_element_id") or s.reason == "non_gen_affordance"
        for s in plan.skips
    )
    # RED before shrink
    assert live_ids.index(GEN_EMIT_RED) < live_ids.index("gen.shrink_dashboard_lines")


def test_rex_affordance_skipped_as_non_gen():
    plan = plan_affordance_actions(
        [
            AffordanceMapEntry(
                element_id="store",
                gap_code="dead_sli_bucket",
                affordance_ids=["rex.ingest_dead_bucket"],
            )
        ],
        ["store"],
    )
    assert not plan.actions
    assert plan.skips[0].reason == "non_gen_affordance"


def test_dry_run_format_and_no_write(tmp_path):
    load = load_affordance_map(FIXTURES / "slim_array.json")
    plan = plan_affordance_actions(load.entries, ["store", "query-frontend"])
    text = format_plan_for_dry_run(plan)
    assert "AffordanceMap action plan:" in text
    assert "gen.emit_red_panels" in text
    dest = write_affordance_actions_report(
        tmp_path, plan=plan, load=load, dry_run=True
    )
    assert dest.name == "affordance_actions.json"
    assert not dest.exists()  # dry-run writes zero files


def test_exit_all_skipped():
    load = load_affordance_map(
        [
            {
                "element_id": "nope",
                "gap_code": "red_missing",
                "affordance_ids": ["gen.emit_red_panels"],
            }
        ]
    )
    plan = plan_affordance_actions(load.entries, ["store"])
    assert exit_code_for_plan(load, plan) == EXIT_ALL_SKIPPED


def test_exit_empty_map():
    load = load_affordance_map([])
    plan = plan_affordance_actions([], ["store"])
    assert exit_code_for_plan(load, plan) == EXIT_OK


def test_services_intersect_empty():
    load = load_affordance_map(FIXTURES / "slim_array.json")
    plan = plan_affordance_actions(
        load.entries, ["store"], service_filter=["other"]
    )
    assert not plan.actions and not plan.skips
    assert exit_code_for_plan(load, plan, empty_intersection=True) == EXIT_OK


# ---- Merge helpers (WP-B0.5) -------------------------------------------------


def test_merge_quality_preserves_untouched():
    prior = {
        "services": {
            "store": {"composite_score": 0.9, "dashboard_spec": {"score": 1.0}},
            "query": {"composite_score": 0.5, "dashboard_spec": {"score": 0.5}},
        },
        "aggregate": {"avg_composite_score": 0.7, "services_scored": 2},
    }
    touched = {"store": {"composite_score": 1.0, "dashboard_spec": {"score": 1.0}}}
    merged = merge_quality_services(prior, touched)
    assert merged["services"]["query"] == prior["services"]["query"]
    assert merged["services"]["store"]["composite_score"] == 1.0


def test_merge_manifest_preserves_untouched():
    prior = {
        "artifacts": [
            {"type": "dashboard_spec", "service": "store", "path": "a"},
            {"type": "alert_rule", "service": "store", "path": "alerts"},
            {"type": "dashboard_spec", "service": "query", "path": "b"},
        ]
    }
    touched = [{"type": "dashboard_spec", "service": "store", "path": "a-new"}]
    merged = merge_manifest_artifacts(
        prior, touched, touched_service_ids=["store"]
    )
    services = {a["service"] for a in merged["artifacts"]}
    assert services == {"store", "query"}
    store_dash = next(
        a
        for a in merged["artifacts"]
        if a["service"] == "store" and a["type"] == "dashboard_spec"
    )
    assert store_dash["path"] == "a-new"
    # Sibling legs for the same service must survive a dashboard-only upsert.
    store_alert = next(
        a
        for a in merged["artifacts"]
        if a["service"] == "store" and a["type"] == "alert_rule"
    )
    assert store_alert["path"] == "alerts"


# ---- Optional CC drift canary -----------------------------------------------


def test_normalize_matches_contextcore_when_installed():
    catalog = pytest.importorskip("contextcore.observability.catalog")
    cases = [
        "PRODUCT_CATALOG",
        "PRODUCT_CATALOG_SERVICE",
        "store",
        "query-frontend",
        "QUERY_FRONTEND",
    ]
    for raw in cases:
        local = normalize_element_id(raw)
        cc = catalog.catalog_service_id(raw)
        assert local == cc, f"drift on {raw!r}: local={local} cc={cc}"


# ---- CLI refuse / dry-run (AC-G2, AC-G9) -------------------------------------

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "generate_observability_artifacts.py"


def _load_gen_script():
    import importlib.util

    spec = importlib.util.spec_from_file_location("_gen_obs_affordance", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cli_refuses_check_with_affordance_map(monkeypatch, tmp_path, capsys):
    mod = _load_gen_script()
    onb = tmp_path / "onboarding-metadata.json"
    onb.write_text(json.dumps({"instrumentation_hints": {"store": {"transport": "grpc"}}}))
    amap = tmp_path / "map.json"
    amap.write_text(
        json.dumps(
            [
                {
                    "element_id": "store",
                    "gap_code": "red_missing",
                    "affordance_ids": ["gen.emit_red_panels"],
                }
            ]
        )
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "generate_observability_artifacts.py",
            "--onboarding-metadata",
            str(onb),
            "--output-dir",
            str(tmp_path / "out"),
            "--affordance-map",
            str(amap),
            "--check",
        ],
    )
    assert mod.main() == 1
    err = capsys.readouterr().err
    assert "cannot be combined" in err


def test_cli_dry_run_prints_plan(monkeypatch, tmp_path, capsys):
    mod = _load_gen_script()
    onb = tmp_path / "onboarding-metadata.json"
    onb.write_text(json.dumps({"instrumentation_hints": {"store": {"transport": "grpc"}}}))
    amap = FIXTURES / "slim_array.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "generate_observability_artifacts.py",
            "--onboarding-metadata",
            str(onb),
            "--output-dir",
            str(tmp_path / "out"),
            "--affordance-map",
            str(amap),
            "--dry-run",
        ],
    )
    rc = mod.main()
    out = capsys.readouterr().out
    assert "AffordanceMap action plan:" in out
    assert "gen.emit_red_panels" in out
    assert "[DRY RUN]" in out
    assert not (tmp_path / "out" / "affordance_actions.json").exists()
    assert rc == EXIT_OK


# ---- WP-B1: FR-B5 + apply ---------------------------------------------------

from startd8.observability.artifact_generator_generators import generate_runbook
from startd8.observability.artifact_generator_models import BusinessContext, ServiceHints
from startd8.observability.affordance_map_consume import (
    ActionOutcome,
    AffordanceMapEntry,
    GEN_COMPLETE_TRIPLET,
    GEN_EMIT_RED,
    GEN_SHRINK,
    apply_affordance_actions,
    exit_code_for_apply,
    plan_affordance_actions,
    write_apply_actions_report,
)


def _grpc_service(sid: str = "store", kinds=None) -> ServiceHints:
    return ServiceHints(
        service_id=sid,
        transport="grpc",
        language="go",
        kinds=kinds or ["rpc_server"],
        convention_metrics=[],
    )


def test_fr_b5_runbook_markers():
    content = generate_runbook(
        _grpc_service(), BusinessContext(criticality="high", availability="99.9")
    ).content
    assert "## Overview" in content
    assert "## Risks" in content
    assert "## Procedures" in content
    assert "## Escalation" in content
    assert "## Service summary" not in content
    assert "## First response" not in content
    # Risks has non-heading body (R2-F3)
    risks_idx = content.index("## Risks")
    after = content[risks_idx:].split("## ", 1)[0] if False else content[risks_idx:]
    section = after.split("\n## ")[0]
    assert "-" in section
    assert "Criticality" in section


_SKELETAL_RUNBOOK = """# Runbook: store

> Generated by startd8 observability artifact generator.

## Service summary

- **Transport:** grpc
- **Language:** go

## Dashboards

- Grafana: `/d/obs-store`

## First response

1. Open the dashboard above.

## Escalation

- Notify the owning team.
"""


def test_enrich_runbook_markdown_retrofit():
    from startd8.observability.affordance_map_consume import enrich_runbook_markdown
    from startd8.validators.observability_artifact_checks import (
        validate_extended_artifact,
    )

    svc = _grpc_service("store")
    biz = BusinessContext(criticality="high", availability="99.9")
    out = enrich_runbook_markdown(_SKELETAL_RUNBOOK, service=svc, business=biz)
    assert "## Overview" in out
    assert "## Risks" in out
    assert "## Procedures" in out
    assert "## Escalation" in out
    assert "## Service summary" not in out
    assert "## First response" not in out
    assert "Criticality is **high**" in out
    # idempotent
    assert enrich_runbook_markdown(out, service=svc, business=biz) == out
    q = validate_extended_artifact(
        out,
        {
            "completeness_markers": ["Overview", "Risks", "Escalation", "Procedures"],
            "max_lines": 300,
        },
    )
    assert q.score >= 0.80
    assert q.checks_passed >= 4


def test_apply_enrich_runbook_seven_services(tmp_path):
    """Map-mode retrofit writes Overview/Risks/Procedures without wiping Escalation."""
    from startd8.observability.affordance_map_consume import GEN_ENRICH_RUNBOOK
    from startd8.validators.observability_artifact_checks import (
        validate_extended_artifact,
    )

    sids = [
        "compact",
        "query",
        "query-frontend",
        "receive",
        "rule",
        "sidecar",
        "store",
    ]
    services = [_grpc_service(s) for s in sids]
    biz = BusinessContext(criticality="medium")
    rb = tmp_path / "runbooks"
    rb.mkdir()
    for s in sids:
        (rb / f"{s}-runbook.md").write_text(
            _SKELETAL_RUNBOOK.replace("store", s), encoding="utf-8"
        )
    entries = [
        {
            "element_id": s,
            "gap_code": "runbook_skeletal",
            "affordance_ids": [GEN_ENRICH_RUNBOOK],
            "locus_status": "partial",
        }
        for s in sids
    ]
    load = load_affordance_map(entries)
    plan = plan_affordance_actions(load.entries, sids)
    assert len(plan.actions) == 7
    assert all(a.affordance_id == GEN_ENRICH_RUNBOOK for a in plan.actions)
    apply = apply_affordance_actions(
        plan, services=services, business=biz, output_dir=tmp_path
    )
    applied = [
        e
        for e in apply.entries
        if e.affordance_id == GEN_ENRICH_RUNBOOK
        and e.outcome == ActionOutcome.APPLIED
    ]
    assert len(applied) == 7
    scores = []
    for s in sids:
        text = (rb / f"{s}-runbook.md").read_text(encoding="utf-8")
        assert "## Overview" in text and "## Escalation" in text
        q = validate_extended_artifact(
            text,
            {
                "completeness_markers": [
                    "Overview",
                    "Risks",
                    "Escalation",
                    "Procedures",
                ],
                "max_lines": 300,
            },
        )
        scores.append(q.score)
    assert sum(scores) / len(scores) >= 0.80


def test_apply_red_freshness_only_is_no_change(tmp_path):
    """AC-G12: kinds without throughput/availability → applied_no_change."""
    svc = ServiceHints(
        service_id="cron",
        transport="http",
        language="python",
        kinds=["cron"],
        convention_metrics=[],
    )
    biz = BusinessContext(criticality="medium")
    load = load_affordance_map(
        [
            {
                "element_id": "cron",
                "gap_code": "red_missing",
                "affordance_ids": [GEN_EMIT_RED],
            }
        ]
    )
    plan = plan_affordance_actions(load.entries, ["cron"])
    apply = apply_affordance_actions(
        plan, services=[svc], business=biz, output_dir=tmp_path
    )
    red = [e for e in apply.entries if e.affordance_id == GEN_EMIT_RED][0]
    assert red.outcome == ActionOutcome.APPLIED_NO_CHANGE
    assert not list(tmp_path.rglob("*-dashboard-spec.yaml"))


def test_apply_red_touches_only_target_service(tmp_path):
    """AC-G3: map for store only does not rewrite query quality/manifest rows."""
    import yaml

    store = _grpc_service("store")
    from startd8.observability.artifact_generator_models import ConventionMetric

    store.convention_metrics = [
        ConventionMetric(
            name="rpc.server.duration", type="histogram", source="otel_semconv:grpc"
        )
    ]
    query = _grpc_service("query")
    biz = BusinessContext(criticality="high", availability="99.9")

    # Prior quality + manifest for both services
    prior_q = {
        "services": {
            "store": {"dashboard_spec": {"score": 0.5}, "composite_score": 0.5},
            "query": {"dashboard_spec": {"score": 0.8}, "composite_score": 0.8},
        },
        "aggregate": {"avg_composite_score": 0.65, "services_scored": 2},
    }
    (tmp_path / "observability-quality.json").write_text(
        json.dumps(prior_q), encoding="utf-8"
    )
    prior_m = {
        "artifacts": [
            {"type": "dashboard_spec", "service": "store", "path": "dashboards/store-dashboard-spec.yaml"},
            {"type": "dashboard_spec", "service": "query", "path": "dashboards/query-dashboard-spec.yaml"},
        ]
    }
    (tmp_path / "observability-manifest.yaml").write_text(
        yaml.safe_dump(prior_m), encoding="utf-8"
    )
    query_row_before = json.dumps(prior_q["services"]["query"], sort_keys=True)

    load = load_affordance_map(
        [
            {
                "element_id": "store",
                "gap_code": "red_missing",
                "affordance_ids": [GEN_EMIT_RED],
            }
        ]
    )
    plan = plan_affordance_actions(load.entries, ["store", "query"])
    apply = apply_affordance_actions(
        plan, services=[store, query], business=biz, output_dir=tmp_path
    )
    from startd8.observability.affordance_map_consume import merge_and_write_reports

    merge_and_write_reports(tmp_path, apply)
    write_apply_actions_report(tmp_path, load=load, apply=apply)

    assert (tmp_path / "dashboards" / "store-dashboard-spec.yaml").is_file()
    assert not (tmp_path / "dashboards" / "query-dashboard-spec.yaml").is_file()
    q_after = json.loads((tmp_path / "observability-quality.json").read_text())
    assert json.dumps(q_after["services"]["query"], sort_keys=True) == query_row_before
    assert exit_code_for_apply(load, apply) == EXIT_OK
    sidecar = json.loads((tmp_path / "affordance_actions.json").read_text())
    assert sidecar["applied"] or sidecar["applied_no_change"]


# ---- WP-B2: shrink (FR-B4 / AC-G5) ------------------------------------------

from startd8.observability.affordance_map_consume import (
    SelectorParseError,
    content_hash,
    dashboard_metric_selectors,
    line_count,
    resolve_dashboard_max_lines,
    shrink_dashboard_lines,
)


def _fat_spec(n_extra: int = 8) -> dict:
    """DashboardSpec with RED trio + expendable panels."""
    panels = [
        {
            "id": 1,
            "title": "Request Rate",
            "group": "Throughput",
            "expr": 'rate(rpc_server_requests_total{service="store"}[5m])',
        },
        {
            "id": 2,
            "title": "Error Rate",
            "group": "Errors",
            "expr": 'rate(rpc_server_requests_total{service="store",status="error"}[5m])',
        },
        {
            "id": 3,
            "title": "Duration p99",
            "group": "Latency",
            "expr": 'histogram_quantile(0.99, rate(rpc_server_duration_bucket[5m]))',
        },
    ]
    for i in range(n_extra):
        panels.append(
            {
                "id": 10 + i,
                "title": f"Body size p95 {i}",
                "group": "Cost & Tokens",
                "expr": f'histogram_quantile(0.95, rate(body_size_bucket{{i="{i}"}}[5m]))',
            }
        )
    return {
        "uid": "store-dash",
        "title": "store",
        "panels": panels,
    }


def _fake_render(spec: dict) -> str:
    """Deterministic stand-in: ~25 lines per panel (no jsonnet required)."""
    n = len(spec.get("panels") or [])
    return "{\n" + "\n".join(f'  "line_{i}": {i},' for i in range(max(n * 25, 1))) + "\n}\n"


def _fat_spec_safe(n_extra: int = 10) -> dict:
    """RED trio + decorative extras that are safe to drop under FR-1.

    Unlike ``_fat_spec``'s numbered "Body size" panels (each a *distinct*
    metric selector via a differing label, so FR-1 must refuse to drop any
    of them), these extras carry no ``expr``/``targets`` at all — dropping
    one never shrinks the dashboard's selector set. Used wherever a test
    wants a shrink that actually *succeeds* while remaining metric-preserving.
    """
    spec = _fat_spec(0)
    panels = list(spec["panels"])
    for i in range(n_extra):
        panels.append(
            {
                "id": 10 + i,
                "title": f"Info panel {i}",
                "group": "Cost & Tokens",
                "text": "docs",
            }
        )
    spec["panels"] = panels
    return spec


def test_resolve_dashboard_max_lines():
    assert resolve_dashboard_max_lines(None) == 300
    assert resolve_dashboard_max_lines({"dashboard": {"max_lines": 120}}) == 120
    assert resolve_dashboard_max_lines({"dashboard": {}}) == 300


# ---- Step 1: dashboard_metric_selectors (FR-1 input) ------------------------


def test_dashboard_metric_selectors_basic_extraction():
    spec = _fat_spec(0)  # Request Rate / Error Rate / Duration p99 (histogram)
    selectors = dashboard_metric_selectors(spec)
    names = {s.split("{")[0] for s in selectors}
    assert "rpc_server_requests_total" in names
    # The histogram_quantile(rate(rpc_server_duration_bucket[5m])) leg has no
    # sibling _count/_sum in this fixture, so it is NOT merged into a family
    # (R1-S5: a lone leg keeps its own name rather than being widened away).
    assert "rpc_server_duration_bucket" in names


def test_dashboard_metric_selectors_distinct_label_matchers_stay_distinct():
    """R2-S2: same metric name, different label matcher => different selector."""
    spec = {
        "panels": [
            {"title": "a", "expr": 'thanos_x{cluster="a"}'},
            {"title": "b", "expr": 'thanos_x{cluster="b"}'},
        ]
    }
    selectors = dashboard_metric_selectors(spec)
    assert len(selectors) == 2


def test_dashboard_metric_selectors_collapses_confirmed_histogram_family():
    spec = {
        "panels": [
            {
                "title": "p99",
                "expr": 'histogram_quantile(0.99, rate(thanos_dur_bucket{job="x"}[5m]))',
            },
            {"title": "sum", "expr": 'rate(thanos_dur_sum{job="x"}[5m])'},
            {"title": "count", "expr": 'rate(thanos_dur_count{job="x"}[5m])'},
        ]
    }
    selectors = dashboard_metric_selectors(spec)
    # All three legs of one confirmed histogram family collapse to one entry.
    assert selectors == frozenset({'thanos_dur{job="x"}'})


def test_dashboard_metric_selectors_does_not_merge_unconfirmed_suffix():
    """A lone '_count' metric with no sibling '_bucket' is not a confirmed
    histogram leg — must not be merged away, or two distinct series could
    collapse into one and silently pass FR-1's subset check (R1-S5)."""
    spec = {"panels": [{"title": "c", "expr": "my_custom_count"}]}
    selectors = dashboard_metric_selectors(spec)
    assert selectors == frozenset({"my_custom_count{}"})


def test_dashboard_metric_selectors_recurses_nested_row_panels():
    """R2-S1: Grafana row panels nest their children under panels[].panels."""
    spec = {
        "panels": [
            {
                "title": "Row",
                "type": "row",
                "panels": [{"title": "child", "expr": "thanos_nested_metric"}],
            }
        ]
    }
    selectors = dashboard_metric_selectors(spec)
    assert any("thanos_nested_metric" in s for s in selectors)


def test_dashboard_metric_selectors_reads_rendered_targets_shape():
    rendered = {
        "panels": [
            {"title": "t", "targets": [{"expr": "thanos_rendered_only_metric"}]}
        ]
    }
    selectors = dashboard_metric_selectors(rendered)
    assert any("thanos_rendered_only_metric" in s for s in selectors)


def test_dashboard_metric_selectors_fails_closed_on_unbalanced_brace():
    """R1-F2: a parse failure must raise, never silently contribute ∅."""
    spec = {"panels": [{"title": "bad", "expr": "thanos_broken{cluster=\"a\""}]}
    with pytest.raises(SelectorParseError):
        dashboard_metric_selectors(spec)


def test_shrink_drops_non_red_to_budget():
    spec = _fat_spec_safe(10)
    pre_selectors = dashboard_metric_selectors(spec)
    result = shrink_dashboard_lines(
        spec, max_lines=80, preserve_red=True, render_fn=_fake_render
    )
    assert result.ok
    assert result.panels_dropped > 0
    assert result.lines_after <= 80
    assert line_count(result.rendered_json) <= 80
    titles = {p["title"] for p in result.spec["panels"]}
    assert "Request Rate" in titles
    assert "Error Rate" in titles
    ids = [p["id"] for p in result.spec["panels"]]
    assert len(ids) == len(set(ids))
    for p in result.spec["panels"]:
        assert "gridPos" in p
        assert "expr" in p
    # FR-1: a *successful* shrink still preserves every metric selector.
    assert dashboard_metric_selectors(result.spec) == pre_selectors


def test_shrink_refuses_would_delete_metric_coverage():
    """Each 'Body size' extra is a distinct selector (via a differing label)
    — dropping any of them shrinks coverage, so FR-1 must refuse even though
    a priority signal (the file-order tie-break among equal-scored extras)
    otherwise exists."""
    spec = _fat_spec(10)
    result = shrink_dashboard_lines(
        spec, max_lines=100, preserve_red=True, render_fn=_fake_render
    )
    assert not result.ok
    assert result.reason == "would_delete_metric_coverage"
    assert result.lost_selectors
    assert all("body_size_bucket" in s for s in result.lost_selectors)


def test_shrink_refuses_when_render_unavailable():
    result = shrink_dashboard_lines(
        _fat_spec(2), max_lines=10, preserve_red=True, render_fn=lambda _s: None
    )
    assert not result.ok
    assert result.reason == "render_unavailable"


def test_shrink_refuses_when_only_red_remains():
    # Tiny budget, all-RED panels: every candidate scores the same
    # (-1000, all RED-protected) — a global tie is "no signal", not a
    # RED-specific gate (FR-2/FR-3: the had_red precondition was deleted).
    red_only = {
        "uid": "store-dash",
        "title": "store",
        "panels": _fat_spec(0)["panels"],
    }
    result = shrink_dashboard_lines(
        red_only, max_lines=5, preserve_red=True, render_fn=_fake_render
    )
    assert not result.ok
    assert result.reason == "no_drop_signal"


def test_apply_shrink_oversize_writes_and_hashes(tmp_path):
    import yaml

    from startd8.observability.affordance_map_consume import merge_and_write_reports

    svc = _grpc_service("store")
    biz = BusinessContext()
    dash_dir = tmp_path / "dashboards"
    dash_dir.mkdir()
    before_text = yaml.safe_dump(_fat_spec_safe(12), sort_keys=False)
    dash_path = dash_dir / "store-dashboard-spec.yaml"
    dash_path.write_text(before_text, encoding="utf-8")
    before_hash = content_hash(before_text)
    # Prior full-generate index: sibling legs must survive dashboard-only repair.
    (tmp_path / "observability-manifest.yaml").write_text(
        yaml.safe_dump(
            {
                "artifacts": [
                    {
                        "type": "dashboard_spec",
                        "service": "store",
                        "path": "dashboards/store-dashboard-spec.yaml",
                    },
                    {
                        "type": "alert_rule",
                        "service": "store",
                        "path": "alerts/store.yaml",
                    },
                    {
                        "type": "slo_definition",
                        "service": "store",
                        "path": "slos/store.yaml",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    plan = plan_affordance_actions(
        [
            AffordanceMapEntry(
                element_id="store",
                gap_code="dashboard_oversize",
                affordance_ids=[GEN_SHRINK],
            )
        ],
        ["store"],
    )
    apply = apply_affordance_actions(
        plan,
        services=[svc],
        business=biz,
        output_dir=tmp_path,
        contracts={"dashboard": {"max_lines": 80}},
        max_lines=80,
        render_fn=_fake_render,
    )
    shrink = [e for e in apply.entries if e.affordance_id == GEN_SHRINK][0]
    assert shrink.outcome == ActionOutcome.APPLIED
    assert shrink.content_hash_before == before_hash
    assert shrink.content_hash_after is not None
    assert shrink.content_hash_after != before_hash
    assert shrink.rendered_hash_after is not None
    after = yaml.safe_load(dash_path.read_text(encoding="utf-8"))
    assert len(after["panels"]) < 15
    gj = tmp_path / "grafana" / "dashboards" / "store-dashboard.json"
    assert gj.is_file()
    assert line_count(gj.read_text(encoding="utf-8")) <= 80
    merge_and_write_reports(tmp_path, apply)
    manifest = yaml.safe_load(
        (tmp_path / "observability-manifest.yaml").read_text(encoding="utf-8")
    )
    types = {
        (a["type"], a["service"])
        for a in manifest["artifacts"]
        if a.get("service") == "store"
    }
    assert ("dashboard_spec", "store") in types
    assert ("alert_rule", "store") in types
    assert ("slo_definition", "store") in types


def test_shrink_already_under_budget_does_not_merge_wipe(tmp_path):
    import yaml

    from startd8.observability.affordance_map_consume import merge_and_write_reports

    svc = _grpc_service("store")
    dash_dir = tmp_path / "dashboards"
    dash_dir.mkdir()
    (dash_dir / "store-dashboard-spec.yaml").write_text(
        yaml.safe_dump(_fat_spec(0), sort_keys=False), encoding="utf-8"
    )
    prior_arts = [
        {
            "type": "dashboard_spec",
            "service": "store",
            "path": "dashboards/store-dashboard-spec.yaml",
        },
        {"type": "alert_rule", "service": "store", "path": "alerts/store.yaml"},
    ]
    (tmp_path / "observability-manifest.yaml").write_text(
        yaml.safe_dump({"artifacts": prior_arts}), encoding="utf-8"
    )
    plan = plan_affordance_actions(
        [
            AffordanceMapEntry(
                element_id="store",
                gap_code="dashboard_oversize",
                affordance_ids=[GEN_SHRINK],
            )
        ],
        ["store"],
    )
    apply = apply_affordance_actions(
        plan,
        services=[svc],
        business=BusinessContext(),
        output_dir=tmp_path,
        max_lines=300,
        render_fn=_fake_render,
    )
    shrink = [e for e in apply.entries if e.affordance_id == GEN_SHRINK][0]
    assert shrink.outcome == ActionOutcome.APPLIED_NO_CHANGE
    merge_and_write_reports(tmp_path, apply)
    after = yaml.safe_load(
        (tmp_path / "observability-manifest.yaml").read_text(encoding="utf-8")
    )
    assert len(after["artifacts"]) == 2


def test_apply_shrink_refuses_no_drop_signal(tmp_path):
    import yaml

    svc = _grpc_service("store")
    biz = BusinessContext()
    dash_dir = tmp_path / "dashboards"
    dash_dir.mkdir()
    (dash_dir / "store-dashboard-spec.yaml").write_text(
        yaml.safe_dump(_fat_spec(0), sort_keys=False), encoding="utf-8"
    )
    plan = plan_affordance_actions(
        [
            AffordanceMapEntry(
                element_id="store",
                gap_code="dashboard_oversize",
                affordance_ids=[GEN_SHRINK],
            )
        ],
        ["store"],
    )
    apply = apply_affordance_actions(
        plan,
        services=[svc],
        business=biz,
        output_dir=tmp_path,
        max_lines=5,
        render_fn=_fake_render,
    )
    shrink = [e for e in apply.entries if e.affordance_id == GEN_SHRINK][0]
    assert shrink.outcome == ActionOutcome.SKIPPED
    assert shrink.reason == "no_drop_signal"
    assert shrink.content_hash_before == shrink.content_hash_after


def test_apply_shrink_refuses_spec_render_drift(tmp_path):
    """The on-disk rendered artifact carries selectors the spec does not
    (or vice versa) — refuse before ever calling the shrinker (plan Step 3,
    R3-S1 symmetric check)."""
    import yaml

    svc = _grpc_service("store")
    biz = BusinessContext()
    dash_dir = tmp_path / "dashboards"
    dash_dir.mkdir()
    spec = _fat_spec(0)
    (dash_dir / "store-dashboard-spec.yaml").write_text(
        yaml.safe_dump(spec, sort_keys=False), encoding="utf-8"
    )
    gj_dir = tmp_path / "grafana" / "dashboards"
    gj_dir.mkdir(parents=True)
    rendered = {
        "panels": spec["panels"]
        + [
            {
                "title": "Extra render-only metric",
                "targets": [{"expr": 'thanos_receive_config_hash{cluster="a"}'}],
            }
        ]
    }
    (gj_dir / "store-dashboard.json").write_text(json.dumps(rendered), encoding="utf-8")
    plan = plan_affordance_actions(
        [
            AffordanceMapEntry(
                element_id="store",
                gap_code="dashboard_oversize",
                affordance_ids=[GEN_SHRINK],
            )
        ],
        ["store"],
    )
    apply = apply_affordance_actions(
        plan,
        services=[svc],
        business=biz,
        output_dir=tmp_path,
        max_lines=5,
        render_fn=_fake_render,
    )
    shrink = [e for e in apply.entries if e.affordance_id == GEN_SHRINK][0]
    assert shrink.outcome == ActionOutcome.SKIPPED
    assert shrink.reason == "spec_render_drift"
    assert shrink.render_available is True
    assert any("thanos_receive_config_hash" in s for s in shrink.legs or [])
    assert shrink.content_hash_before == shrink.content_hash_after


def test_apply_shrink_refuses_scored_artifact_over_budget(tmp_path):
    """Spec is already under budget, and its selectors match the on-disk
    render exactly (no drift) — but the *scored* rendered artifact is still
    over budget. APPLIED_NO_CHANGE would be a false green (plan Step 3)."""
    import yaml

    svc = _grpc_service("store")
    biz = BusinessContext()
    dash_dir = tmp_path / "dashboards"
    dash_dir.mkdir()
    spec = _fat_spec(0)  # 3 panels, well under any real budget
    (dash_dir / "store-dashboard-spec.yaml").write_text(
        yaml.safe_dump(spec, sort_keys=False), encoding="utf-8"
    )
    gj_dir = tmp_path / "grafana" / "dashboards"
    gj_dir.mkdir(parents=True)
    # Same selectors as the spec (no drift) but pretty-printed with non-metric
    # padding so the scored line count exceeds max_lines.
    (gj_dir / "store-dashboard.json").write_text(
        json.dumps(
            {"panels": spec["panels"], "padding": list(range(400))}, indent=2
        ),
        encoding="utf-8",
    )
    plan = plan_affordance_actions(
        [
            AffordanceMapEntry(
                element_id="store",
                gap_code="dashboard_oversize",
                affordance_ids=[GEN_SHRINK],
            )
        ],
        ["store"],
    )
    apply = apply_affordance_actions(
        plan,
        services=[svc],
        business=biz,
        output_dir=tmp_path,
        max_lines=80,
        render_fn=_fake_render,
    )
    shrink = [e for e in apply.entries if e.affordance_id == GEN_SHRINK][0]
    assert shrink.outcome == ActionOutcome.SKIPPED
    assert shrink.reason == "scored_artifact_over_budget"
    assert shrink.content_hash_before == shrink.content_hash_after


def test_apply_shrink_refusal_never_touches_quality_or_manifest(tmp_path):
    """FR-6: every refusal path must leave merge_and_write_reports a no-op."""
    import yaml

    from startd8.observability.affordance_map_consume import merge_and_write_reports

    svc = _grpc_service("store")
    biz = BusinessContext()
    dash_dir = tmp_path / "dashboards"
    dash_dir.mkdir()
    (dash_dir / "store-dashboard-spec.yaml").write_text(
        yaml.safe_dump(_fat_spec(0), sort_keys=False), encoding="utf-8"
    )
    plan = plan_affordance_actions(
        [
            AffordanceMapEntry(
                element_id="store",
                gap_code="dashboard_oversize",
                affordance_ids=[GEN_SHRINK],
            )
        ],
        ["store"],
    )
    apply = apply_affordance_actions(
        plan,
        services=[svc],
        business=biz,
        output_dir=tmp_path,
        max_lines=5,
        render_fn=_fake_render,
    )
    shrink = [e for e in apply.entries if e.affordance_id == GEN_SHRINK][0]
    assert shrink.outcome == ActionOutcome.SKIPPED
    assert not apply.quality_touched
    assert not apply.manifest_touched
    assert not (tmp_path / "observability-quality.json").is_file()
    assert not (tmp_path / "observability-manifest.yaml").is_file()
    merge_and_write_reports(tmp_path, apply)  # must remain a no-op
    assert not (tmp_path / "observability-quality.json").is_file()
    assert not (tmp_path / "observability-manifest.yaml").is_file()


# ---- WP-B3: sidecar completeness (FR-B7) ------------------------------------

from startd8.observability.affordance_map_consume import (
    SIDECAR_REQUIRED_KEYS,
    build_affordance_actions_payload,
    collect_source_provenance,
)


def test_sidecar_required_keys_and_provenance(tmp_path):
    load = load_affordance_map(FIXTURES / "truncated_history.json")
    assert load.source_truncated is True
    assert "catalog.attach" in collect_source_provenance(load)

    plan = plan_affordance_actions(load.entries, ["store", "query-frontend"])
    # Plan-only write (empty-intersect / no-op path shape)
    dest = write_affordance_actions_report(
        tmp_path, plan=plan, load=load, dry_run=False
    )
    sidecar = json.loads(dest.read_text(encoding="utf-8"))
    assert SIDECAR_REQUIRED_KEYS <= set(sidecar.keys())
    assert sidecar["source_truncated"] is True
    assert sidecar["source_provenance"] == ["catalog.attach"]
    assert sidecar["summary"]["planned"] == len(sidecar["planned"])
    assert sidecar["summary"]["skipped"] == len(sidecar["skipped"])
    assert isinstance(sidecar["written_paths"], list)


def test_apply_sidecar_echoes_unmapped_and_hashes(tmp_path):
    import yaml

    svc = _grpc_service("store")
    biz = BusinessContext()
    dash_dir = tmp_path / "dashboards"
    dash_dir.mkdir()
    (dash_dir / "store-dashboard-spec.yaml").write_text(
        yaml.safe_dump(_fat_spec_safe(10), sort_keys=False), encoding="utf-8"
    )
    load = load_affordance_map(
        [
            {
                "element_id": "store",
                "gap_code": "dashboard_oversize",
                "affordance_ids": [GEN_SHRINK],
                "provenance": "audit.v1",
            },
            {
                "element_id": "ghost",
                "gap_code": "red_missing",
                "affordance_ids": [],
                "unmapped_reason": "no_catalog_match",
                "provenance": "audit.v1",
            },
        ]
    )
    plan = plan_affordance_actions(load.entries, ["store"])
    apply = apply_affordance_actions(
        plan,
        services=[svc],
        business=biz,
        output_dir=tmp_path,
        max_lines=80,
        render_fn=_fake_render,
    )
    write_apply_actions_report(tmp_path, load=load, apply=apply)
    sidecar = json.loads((tmp_path / "affordance_actions.json").read_text())
    assert SIDECAR_REQUIRED_KEYS <= set(sidecar.keys())
    assert sidecar["source_provenance"] == ["audit.v1"]
    assert sidecar["all_skipped"] is False
    assert sidecar["summary"]["applied"] >= 1
    skipped_unmapped = [
        s for s in sidecar["skipped"] if s.get("unmapped_reason") == "no_catalog_match"
    ]
    assert skipped_unmapped
    applied = sidecar["applied"][0]
    assert applied["content_hash_before"] != applied["content_hash_after"]
    assert applied.get("rendered_hash_after")


def test_build_payload_all_skipped_flag():
    load = load_affordance_map(
        [
            {
                "element_id": "nope",
                "gap_code": "red_missing",
                "affordance_ids": ["gen.emit_red_panels"],
            }
        ]
    )
    plan = plan_affordance_actions(load.entries, ["store"])
    payload = build_affordance_actions_payload(
        load=load,
        planned=[],
        applied=[],
        applied_no_change=[],
        skipped=plan.skips,
        dry_run=False,
    )
    assert payload["all_skipped"] is True
    assert payload["summary"]["skipped"] >= 1


# ---- Refactor hardening ------------------------------------------------------

from startd8.observability.affordance_map_consume import (
    AffordanceMapEntry,
    _confined_dest,
    _coerce_confidence,
)


def test_coerce_confidence_soft_fails():
    assert _coerce_confidence(None) is None
    assert _coerce_confidence(1) == 1.0
    assert _coerce_confidence("0.5") == 0.5
    assert _coerce_confidence("nope") is None
    assert AffordanceMapEntry.from_dict(
        {"element_id": "store", "confidence": "bad"}
    ).confidence is None


def test_confined_dest_blocks_escape(tmp_path):
    assert _confined_dest(tmp_path, "dashboards/ok.yaml") == (
        tmp_path / "dashboards/ok.yaml"
    ).resolve()
    assert _confined_dest(tmp_path, "../escape.yaml") is None
    assert _confined_dest(tmp_path, "/tmp/abs.yaml") is None
    assert _confined_dest(tmp_path, "") is None


def test_shrink_refuse_does_not_mutate_returned_spec():
    red_only = {
        "uid": "store-dash",
        "title": "store",
        "panels": _fat_spec(0)["panels"],
    }
    original = json.loads(json.dumps(red_only))
    result = shrink_dashboard_lines(
        red_only, max_lines=5, preserve_red=True, render_fn=_fake_render
    )
    assert not result.ok
    assert result.reason == "no_drop_signal"
    assert len(result.spec["panels"]) == len(original["panels"])
    assert {p["title"] for p in result.spec["panels"]} == {
        p["title"] for p in original["panels"]
    }
