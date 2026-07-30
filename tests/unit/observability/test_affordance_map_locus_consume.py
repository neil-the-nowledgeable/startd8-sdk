"""Locus-grounded AffordanceMap consume (REQ_O11Y_LOCUS_GROUNDED_ARTIFACT_GENERATE)."""

from __future__ import annotations

import json
from pathlib import Path

from startd8.observability.affordance_map_consume import (
    ActionOutcome,
    AffordanceMapEntry,
    GEN_EMIT_RED,
    GEN_IMPROVE_COVERAGE,
    GEN_SHRINK,
    apply_affordance_actions,
    is_transport_or_component_only,
    load_affordance_map,
    merge_needed_where_into_entries,
    metric_loci,
    plan_affordance_actions,
    signal_kind_for,
)
from startd8.observability.artifact_generator_models import BusinessContext, ServiceHints


def _svc(sid: str = "receive") -> ServiceHints:
    return ServiceHints(
        service_id=sid,
        transport="http",
        language="go",
        kinds=["rpc_server"],
        convention_metrics=[],
    )


def test_signal_kind_and_metric_loci_filter():
    assert signal_kind_for("transport:grpc") == "transport"
    e = AffordanceMapEntry.from_dict(
        {
            "element_id": "receive",
            "gap_code": "red_missing",
            "affordance_ids": ["gen.emit_red_panels"],
            "locus_status": "source_backed",
            "source_loci": [
                {"family_or_signal": "transport:grpc", "signal_kind": "transport"},
                {
                    "family_or_signal": "thanos_receive_requests_total",
                    "signal_kind": "metric",
                },
            ],
        }
    )
    assert len(metric_loci(e)) == 1
    assert not is_transport_or_component_only(e)


def test_transport_only_skips_emit_red():
    e = AffordanceMapEntry.from_dict(
        {
            "element_id": "receive",
            "gap_code": "ec_grpc_neg",
            "affordance_ids": ["gen.emit_red_panels"],
            "locus_status": "source_backed",
            "source_loci": [
                {"family_or_signal": "transport:grpc", "signal_kind": "transport"}
            ],
        }
    )
    plan = plan_affordance_actions([e], ["receive"])
    assert not plan.actions
    assert any(s.reason == "transport_only_loci" for s in plan.skips)


def test_no_source_locus_blocks_red_allows_shrink():
    entries = [
        AffordanceMapEntry.from_dict(
            {
                "element_id": "business-criticality",
                "gap_code": "red_missing",
                "affordance_ids": ["gen.emit_red_panels"],
                "locus_status": "no_source_locus",
            }
        ),
        AffordanceMapEntry.from_dict(
            {
                "element_id": "store",
                "gap_code": "dashboard_oversize",
                "affordance_ids": ["gen.shrink_dashboard_lines"],
                "locus_status": "no_source_locus",
            }
        ),
    ]
    plan = plan_affordance_actions(entries, ["store", "business-criticality"])
    assert all(a.affordance_id != GEN_EMIT_RED for a in plan.actions)
    assert any(s.reason.startswith("locus_blocked") for s in plan.skips)
    # shrink is artifact-shape — may still be planned if known service matches
    assert any(a.affordance_id == GEN_SHRINK for a in plan.actions) or any(
        s.affordance_id == GEN_SHRINK for s in plan.skips
    )


def test_merge_needed_where_map_native_wins():
    entries = [
        AffordanceMapEntry.from_dict(
            {
                "element_id": "receive",
                "gap_code": "red_missing",
                "affordance_ids": ["gen.emit_red_panels"],
                "locus_status": "source_backed",
                "source_loci": [
                    {"family_or_signal": "thanos_receive_from_map", "signal_kind": "metric"}
                ],
            }
        )
    ]
    nw = {
        "needed_where": [
            {
                "element_id": "receive",
                "gap_code": "red_missing",
                "status": "partial",
                "source_loci": [
                    {"family_or_signal": "thanos_receive_from_nw", "signal_kind": "metric"}
                ],
            }
        ]
    }
    merged = merge_needed_where_into_entries(entries, nw)
    assert merged[0].source_loci[0]["family_or_signal"] == "thanos_receive_from_map"


def test_merge_needed_where_fills_empty():
    entries = [
        AffordanceMapEntry.from_dict(
            {
                "element_id": "receive",
                "gap_code": "red_missing",
                "affordance_ids": ["gen.emit_red_panels"],
            }
        )
    ]
    nw = {
        "needed_where": [
            {
                "element_id": "receive",
                "gap_code": "red_missing",
                "status": "source_backed",
                "reason": "ok",
                "source_loci": [
                    {"family_or_signal": "thanos_receive_requests_total", "signal_kind": "metric"}
                ],
            }
        ]
    }
    merged = merge_needed_where_into_entries(entries, nw)
    assert merged[0].locus_status == "source_backed"
    assert metric_loci(merged[0])


def test_coverage_planned_when_source_backed_metric_loci():
    e = AffordanceMapEntry.from_dict(
        {
            "element_id": "receive",
            "gap_code": "metric_coverage_empty",
            "affordance_ids": ["gen.improve_metric_coverage"],
            "locus_status": "source_backed",
            "source_loci": [
                {"family_or_signal": "thanos_receive_config_hash", "signal_kind": "metric"}
            ],
        }
    )
    plan = plan_affordance_actions([e], ["receive"])
    assert any(a.affordance_id == GEN_IMPROVE_COVERAGE for a in plan.actions)
    assert not any(
        s.affordance_id == GEN_IMPROVE_COVERAGE and s.reason == "no_deterministic_lever"
        for s in plan.skips
    )


def test_coverage_planned_when_partial_metric_loci():
    """qf tip depth: partial RED/dead loci must plan improve_metric_coverage."""
    e = AffordanceMapEntry.from_dict(
        {
            "element_id": "query-frontend",
            "gap_code": "red_missing",
            "affordance_ids": ["gen.improve_metric_coverage"],
            "locus_status": "partial",
            "source_loci": [
                {
                    "family_or_signal": "thanos_query_frontend_queries_total",
                    "signal_kind": "metric",
                }
            ],
        }
    )
    plan = plan_affordance_actions([e], ["query-frontend"])
    assert any(a.affordance_id == GEN_IMPROVE_COVERAGE for a in plan.actions)


def test_apply_locus_red_and_coverage(tmp_path):
    out = tmp_path / "out"
    (out / "dashboards").mkdir(parents=True)
    plan = plan_affordance_actions(
        [
            AffordanceMapEntry.from_dict(
                {
                    "element_id": "receive",
                    "gap_code": "red_missing",
                    "affordance_ids": ["gen.emit_red_panels"],
                    "locus_status": "source_backed",
                    "source_loci": [
                        {
                            "family_or_signal": "thanos_receive_requests_total",
                            "signal_kind": "metric",
                        },
                        {
                            "family_or_signal": "thanos_receive_request_errors_total",
                            "signal_kind": "metric",
                        },
                    ],
                }
            ),
            AffordanceMapEntry.from_dict(
                {
                    "element_id": "receive",
                    "gap_code": "metric_coverage_empty",
                    "affordance_ids": ["gen.improve_metric_coverage"],
                    "locus_status": "source_backed",
                    "source_loci": [
                        {
                            "family_or_signal": "thanos_receive_config_hash",
                            "signal_kind": "metric",
                        }
                    ],
                }
            ),
        ],
        ["receive"],
    )
    apply = apply_affordance_actions(
        plan,
        services=[_svc("receive")],
        business=BusinessContext(criticality="high", availability="99.9"),
        output_dir=out,
    )
    dash = (out / "dashboards/receive-dashboard-spec.yaml").read_text()
    assert "thanos_receive_requests_total" in dash
    assert "rpc.server" not in dash and "rpc_server" not in dash
    assert "thanos_receive_config_hash" in dash
    assert any(e.outcome == ActionOutcome.APPLIED for e in apply.entries)
    assert any(e.loci_used for e in apply.entries if e.outcome == ActionOutcome.APPLIED)


def test_load_x2_export_shape(tmp_path):
    p = tmp_path / "export.json"
    p.write_text(
        json.dumps(
            {
                "kind": "affordance-map-export",
                "affordance_map": [
                    {
                        "element_id": "receive",
                        "gap_code": "red_missing",
                        "affordance_ids": ["gen.emit_red_panels"],
                        "locus_status": "source_backed",
                        "source_loci": [
                            {
                                "family_or_signal": "thanos_receive_requests_total",
                                "signal_kind": "metric",
                            }
                        ],
                    }
                ],
            }
        )
    )
    load = load_affordance_map(p)
    assert load.ok
    assert load.entries[0].locus_status == "source_backed"
    assert metric_loci(load.entries[0])


def test_apply_locus_red_under_unresolved_tmp():
    """macOS /tmp → /private/tmp must not break written_paths relative_to."""
    import shutil
    import tempfile

    # Use /tmp explicitly so Darwin symlink resolve differs from Path string.
    candidate = Path(tempfile.mkdtemp(prefix="locus-tmp-", dir="/tmp"))
    try:
        out = Path("/tmp") / candidate.name  # unresolved /tmp/... form
        plan = plan_affordance_actions(
            [
                AffordanceMapEntry.from_dict(
                    {
                        "element_id": "compact",
                        "gap_code": "red_missing",
                        "affordance_ids": ["gen.emit_red_panels"],
                        "locus_status": "source_backed",
                        "source_loci": [
                            {
                                "family_or_signal": "thanos_compact_group_compactions_total",
                                "signal_kind": "metric",
                            }
                        ],
                    }
                )
            ],
            ["compact"],
        )
        apply = apply_affordance_actions(
            plan,
            services=[_svc("compact")],
            business=BusinessContext(criticality="high", availability="99.9"),
            output_dir=out,
        )
        assert any(e.outcome == ActionOutcome.APPLIED for e in apply.entries)
        assert any(
            p.endswith("compact-dashboard-spec.yaml") for p in apply.written_paths
        )
        assert (out / "dashboards/compact-dashboard-spec.yaml").is_file()
    finally:
        shutil.rmtree(candidate, ignore_errors=True)
