"""gap #4 (triplet completeness) Step 5 — declared-row-versus-disk gate (FR-3).

The locked tree (compare-live/post-fix-s2b-multi-shipper/observability/) is
this gate's required **negative fixture**: it must fail and name exactly the
skipped-absent alert_rule/slo_definition rows, even though
``artifact_type_coverage`` reads 1.0 on that same tree.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from startd8.observability.triplet_gate import (
    DECLARED_BASE_SLO_SUFFIX,
    SuppressionRecord,
    evaluate_triplet_gate,
    evaluate_triplet_gate_for_services,
    eligible_triplet_denominator,
)


def _locked_tree_manifest(service_id: str = "compact") -> dict:
    """Shape corroborated in plan.md Step 1: alert_rule + primary slo
    'skipped', declared-base slo 'generated', dashboard_spec 'generated'."""
    return {
        "artifacts": [
            {
                "type": "dashboard_spec",
                "service": service_id,
                "path": f"dashboards/{service_id}-dashboard-spec.yaml",
                "status": "generated",
            },
            {
                "type": "alert_rule",
                "service": service_id,
                "path": f"alerts/{service_id}-alerts.yaml",
                "status": "skipped",
            },
            {
                "type": "slo_definition",
                "service": service_id,
                "path": f"slos/{service_id}-slo.yaml",
                "status": "skipped",
            },
            {
                "type": "slo_definition",
                "service": service_id,
                "path": f"slos/{service_id}-declared-base-slo.yaml",
                "status": "generated",
            },
        ]
    }


def _locked_tree_quality(service_id: str = "compact") -> dict:
    return {
        "services": {
            service_id: {
                "dashboard_spec": {"score": 0.9167},
                # no alert_rule / slo_definition keys at all — absence, not 0.
            }
        }
    }


def _write_tree(tmp_path: Path, service_id: str, *, with_disk_files: bool) -> Path:
    root = tmp_path / "observability"
    root.mkdir(parents=True)
    (root / "observability-manifest.yaml")  # not read by the gate directly
    if with_disk_files:
        (root / "dashboards").mkdir()
        (root / "dashboards" / f"{service_id}-dashboard-spec.yaml").write_text("x")
        (root / "slos").mkdir()
        (root / "slos" / f"{service_id}-declared-base-slo.yaml").write_text("x")
        # deliberately no alerts/ dir and no primary slo file — matches the
        # locked tree exactly (P-A/P-B: generated-but-unscored declared-base
        # coexists with an absent primary SLO file).
    return root


class TestLockedTreeIsTheRequiredNegativeFixture:
    def test_locked_tree_shape_fails_gate(self, tmp_path):
        svc = "compact"
        root = _write_tree(tmp_path, svc, with_disk_files=True)
        result = evaluate_triplet_gate(
            service_id=svc,
            output_dir=root,
            manifest=_locked_tree_manifest(svc),
            quality=_locked_tree_quality(svc),
        )
        assert result.complete is False
        by_leg = {leg.leg: leg for leg in result.legs}
        assert by_leg["alert_rule"].problem == "declared_status_skipped"
        assert by_leg["slo_definition"].problem == "declared_status_skipped"
        # The gate must have resolved the *primary* slo row, not silently
        # substituted the declared-base row that happens to be "generated".
        assert by_leg["slo_definition"].declared_path == "slos/compact-slo.yaml"
        assert not by_leg["slo_definition"].declared_path.endswith(
            DECLARED_BASE_SLO_SUFFIX
        )
        # dashboard_spec is present, on disk, and scored — that leg alone
        # must pass even though the service overall fails.
        assert by_leg["dashboard_spec"].complete is True

    def test_report_only_over_named_evidence(self, tmp_path):
        """Step 5: report-only run over a tree records per-service verdicts
        without raising or mutating anything."""
        svcs = ["compact", "query"]
        for s in svcs:
            _write_tree(tmp_path / s, s, with_disk_files=True)
        results = evaluate_triplet_gate_for_services(
            service_ids=svcs,
            output_dir=tmp_path / "compact" / "observability",
            manifest=_locked_tree_manifest("compact"),
            quality=_locked_tree_quality("compact"),
        )
        assert set(results) == set(svcs)
        assert all(r.complete is False for r in results.values())


class TestUndeclaredOnDiskFixture:
    def test_undeclared_disk_file_is_named_not_ignored(self, tmp_path):
        root = tmp_path / "observability"
        root.mkdir()
        (root / "alerts").mkdir()
        (root / "alerts" / "store-alerts.yaml").write_text("x")
        manifest = {"artifacts": []}  # no declared row at all
        quality = {"services": {"store": {}}}
        result = evaluate_triplet_gate(
            service_id="store", output_dir=root, manifest=manifest, quality=quality
        )
        assert "alerts/store-alerts.yaml" in result.undeclared_on_disk
        assert result.complete is False


class TestPrefixOverlapNeverMisattributes:
    def test_query_frontend_file_never_flagged_undeclared_for_query(self, tmp_path):
        """Thanos names overlap by prefix (query / query-frontend); an open
        glob would misreport query-frontend's own alert file as an
        undeclared-on-disk finding for `query`."""
        root = tmp_path / "observability"
        root.mkdir()
        (root / "alerts").mkdir()
        (root / "alerts" / "query-frontend-alerts.yaml").write_text("x")
        manifest = {
            "artifacts": [
                {
                    "type": "alert_rule",
                    "service": "query-frontend",
                    "path": "alerts/query-frontend-alerts.yaml",
                    "status": "generated",
                }
            ]
        }
        result = evaluate_triplet_gate(
            service_id="query",
            output_dir=root,
            manifest=manifest,
            quality={"services": {"query": {}}},
            legs=["alert_rule"],
        )
        assert result.undeclared_on_disk == []


class TestScoringVisibilityGate:
    def test_present_but_scoreless_primary_slo_fails(self, tmp_path):
        """P-A: a 'generated' primary SLO with no score key must still fail —
        emitted does not imply scoring-visible."""
        root = tmp_path / "observability"
        root.mkdir()
        (root / "slos").mkdir()
        (root / "slos" / "store-slo.yaml").write_text("x")
        manifest = {
            "artifacts": [
                {
                    "type": "slo_definition",
                    "service": "store",
                    "path": "slos/store-slo.yaml",
                    "status": "generated",
                }
            ]
        }
        quality = {"services": {"store": {}}}  # no "slo_definition" key
        result = evaluate_triplet_gate(
            service_id="store",
            output_dir=root,
            manifest=manifest,
            quality=quality,
            legs=["slo_definition"],
        )
        leg = result.legs[0]
        assert leg.on_disk is True
        assert leg.declared_status == "generated"
        assert leg.problem == "not_scoring_visible"
        assert result.complete is False


class TestCompleteFixturePasses:
    def test_scoring_visible_complete_fixture_passes(self, tmp_path):
        root = tmp_path / "observability"
        root.mkdir()
        for d in ("alerts", "slos", "dashboards"):
            (root / d).mkdir()
        (root / "alerts" / "store-alerts.yaml").write_text("x")
        (root / "slos" / "store-slo.yaml").write_text("x")
        (root / "dashboards" / "store-dashboard-spec.yaml").write_text("x")
        manifest = {
            "artifacts": [
                {
                    "type": "alert_rule",
                    "service": "store",
                    "path": "alerts/store-alerts.yaml",
                    "status": "generated",
                },
                {
                    "type": "slo_definition",
                    "service": "store",
                    "path": "slos/store-slo.yaml",
                    "status": "generated",
                },
                {
                    "type": "dashboard_spec",
                    "service": "store",
                    "path": "dashboards/store-dashboard-spec.yaml",
                    "status": "generated",
                },
            ]
        }
        quality = {
            "services": {
                "store": {
                    "alert_rule": {"score": 1.0},
                    "slo_definition": {"score": 1.0},
                    "dashboard_spec": {"score": 0.9167},
                }
            }
        }
        result = evaluate_triplet_gate(
            service_id="store", output_dir=root, manifest=manifest, quality=quality
        )
        assert result.complete is True
        assert all(leg.complete for leg in result.legs)


class TestSuppression:
    def test_suppressed_row_requires_reason_date_and_evidence(self, tmp_path):
        root = tmp_path / "observability"
        root.mkdir()
        manifest = {
            "artifacts": [
                {
                    "type": "alert_rule",
                    "service": "store",
                    "path": "alerts/store-alerts.yaml",
                    "status": "skipped",
                }
            ]
        }
        quality = {"services": {"store": {}}}

        # Incomplete suppression (missing evidence) must NOT suppress.
        bad_supp = {("store", "alert_rule"): SuppressionRecord(
            reason="no alertable metrics for this service class", date="2026-07-30", evidence=""
        )}
        result = evaluate_triplet_gate(
            service_id="store",
            output_dir=root,
            manifest=manifest,
            quality=quality,
            legs=["alert_rule"],
            suppressions=bad_supp,
        )
        assert result.complete is False
        assert result.legs[0].suppressed is False

        good_supp = {("store", "alert_rule"): SuppressionRecord(
            reason="no alertable metrics for this service class",
            date="2026-07-30",
            evidence="freeze-export row X",
        )}
        result2 = evaluate_triplet_gate(
            service_id="store",
            output_dir=root,
            manifest=manifest,
            quality=quality,
            legs=["alert_rule"],
            suppressions=good_supp,
        )
        assert result2.complete is True
        assert result2.legs[0].suppressed is True


class TestDeclaredRowMissing:
    def test_no_declared_row_fails_with_named_problem(self, tmp_path):
        root = tmp_path / "observability"
        root.mkdir()
        result = evaluate_triplet_gate(
            service_id="store",
            output_dir=root,
            manifest={"artifacts": []},
            quality={},
            legs=["alert_rule"],
        )
        assert result.legs[0].problem == "declared_row_missing"
        assert result.complete is False


class TestEligibleDenominator:
    def test_excluded_elements_kept_out_of_numerator_and_denominator(self):
        all_ids = [
            "compact",
            "query",
            "query-frontend",
            "receive",
            "rule",
            "sidecar",
            "store",
            "thanos",
            "business-criticality",
        ]
        excluded = {
            "thanos": "no_source_locus",
            "business-criticality": "no_source_locus",
        }
        eligible, excluded_list = eligible_triplet_denominator(
            all_element_ids=all_ids, excluded=excluded
        )
        assert len(eligible) == 7
        assert "thanos" not in eligible
        assert "business-criticality" not in eligible
        assert {e["element_id"] for e in excluded_list} == set(excluded)
        for row in excluded_list:
            assert row["locus_reason"] == "no_source_locus"

    def test_adding_a_third_excluded_element_leaves_eligible_at_seven(self):
        all_ids = [
            "compact",
            "query",
            "query-frontend",
            "receive",
            "rule",
            "sidecar",
            "store",
            "thanos",
            "business-criticality",
            "ghost-element",
        ]
        excluded = {
            "thanos": "no_source_locus",
            "business-criticality": "no_source_locus",
            "ghost-element": "no_source_locus",
        }
        eligible, _ = eligible_triplet_denominator(
            all_element_ids=all_ids, excluded=excluded
        )
        assert len(eligible) == 7
