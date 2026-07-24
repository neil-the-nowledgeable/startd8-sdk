# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Tests for collector_enrichment (REQ_COLLECTOR_ENRICHMENT, SDK side).

Covers FR-1b (ServiceHints), FR-2 (registry), FR-3/4/5/6 (emitter), FR-8 (validation),
FR-10a/11 (semantic parity), and the presence-gated wiring.
"""

import random
from pathlib import Path

import pytest
import yaml

from startd8.observability.artifact_generator_context import (
    extract_service_hints,
    resolve_artifact_spec,
)
from startd8.observability.artifact_generator_generators import (
    _ottl_str,
    generate_collector_enrichment,
)
from startd8.observability.artifact_generator_models import (
    BusinessContext,
    GenerationReport,
    ServiceHints,
)
from startd8.observability.collector_enrichment_parity import (
    check_collector_enrichment_parity,
    extract_enrichment_map,
)
from startd8.observability.collector_enrichment_validation import (
    CollectorEnrichmentError,
    validate_collector_enrichment,
)
from startd8.observability.taxonomy_enums import Category, Orientation

_FIXTURE = (
    Path(__file__).parent / "fixtures" / "otelcol-business-enrichment.reference.yml"
)


def _report() -> GenerationReport:
    return GenerationReport(
        project_id="online-boutique", generated_at="2026-07-23T00:00:00Z"
    )


# --- Online-Boutique service→business map (from the reference block) -----------------------------
_CRIT = {
    "critical": ["frontend", "checkoutservice", "cartservice", "paymentservice"],
    "high": [
        "productcatalogservice",
        "currencyservice",
        "shippingservice",
        "quoteservice",
        "accountingservice",
    ],
    "medium": [
        "emailservice",
        "recommendationservice",
        "adservice",
        "frauddetectionservice",
    ],
}
_OWNER = {
    "Nicolaus Copernicus": ["checkoutservice", "cartservice"],
    "Annie Jump Cannon": ["frontend"],
    "Edmond Halley": ["paymentservice", "currencyservice"],
    "Charles Messier": ["productcatalogservice", "adservice"],
    "Henrietta Leavitt": ["recommendationservice"],
    "Maria Mitchell": ["shippingservice", "emailservice", "quoteservice"],
    "Urbain Le Verrier": ["accountingservice"],
    "Johannes Kepler": ["frauddetectionservice"],
}


def _boutique_services():
    svc_crit = {s: c for c, ss in _CRIT.items() for s in ss}
    svc_owner = {s: o for o, ss in _OWNER.items() for s in ss}
    allsvc = sorted(set(svc_crit) | set(svc_owner))
    return [
        ServiceHints(
            service_id=s,
            service_name=s,
            transport="grpc",
            criticality=svc_crit.get(s, ""),
            owner=svc_owner.get(s),
        )
        for s in allsvc
    ]


# ============================ FR-1b: ServiceHints extraction ============================


class TestFR1bExtraction:
    def test_reads_nested_business_block(self):
        meta = {
            "instrumentation_hints": {
                "cartservice": {
                    "transport": "grpc",
                    "service_name": "cartservice",
                    "business": {"criticality": "critical", "owner": "commerce-team"},
                }
            }
        }
        [svc] = extract_service_hints(meta)
        assert svc.criticality == "critical"
        assert svc.owner == "commerce-team"

    def test_absent_business_is_empty(self):
        meta = {
            "instrumentation_hints": {"s": {"transport": "http", "service_name": "s"}}
        }
        [svc] = extract_service_hints(meta)
        assert svc.criticality == ""
        assert svc.owner is None

    def test_partial_business_owner_only(self):
        meta = {
            "instrumentation_hints": {
                "s": {
                    "transport": "http",
                    "service_name": "s",
                    "business": {"owner": "team-x"},
                }
            }
        }
        [svc] = extract_service_hints(meta)
        assert svc.criticality == ""
        assert svc.owner == "team-x"

    def test_malformed_business_is_ignored(self):
        meta = {
            "instrumentation_hints": {
                "s": {
                    "transport": "http",
                    "service_name": "s",
                    "business": ["not", "a", "dict"],
                }
            }
        }
        [svc] = extract_service_hints(meta)
        assert svc.criticality == "" and svc.owner is None


# ============================ FR-2: registry row ============================


class TestFR2Registry:
    def test_row_present_project_system(self):
        spec = resolve_artifact_spec("collector_enrichment")
        assert spec is not None
        assert spec.category == Category.PROJECT.value
        assert spec.orientation == Orientation.SYSTEM.value
        assert spec.requires_declaration is False


# ============================ FR-3/4/5/6: emitter ============================


class TestFR3Emitter:
    def test_generates_expected_shape(self):
        r = generate_collector_enrichment(
            _boutique_services(), BusinessContext(project_id="ob"), _report()
        )
        assert r.status == "generated"
        assert r.output_path == "collector-enrichment/otelcol-business-enrichment.yaml"
        doc = yaml.safe_load(r.content)
        proc = doc["processors"]["transform/business"]
        assert proc["error_mode"] == "ignore"
        assert proc["trace_statements"][0]["context"] == "span"

    def test_statement_count_is_sum_of_present_pairs(self):
        # 13 services each carry criticality + owner ⇒ 26 statements (Σ present pairs, not |attr|×N).
        services = _boutique_services()
        expected = sum(bool(s.criticality) + bool(s.owner) for s in services)
        assert expected == 26
        r = generate_collector_enrichment(services, BusinessContext(), _report())
        stmts = yaml.safe_load(r.content)["processors"]["transform/business"][
            "trace_statements"
        ][0]["statements"]
        assert len(stmts) == expected

    def test_partial_context_counts_only_present(self):
        services = [
            ServiceHints(
                service_id="a", service_name="a", criticality="high"
            ),  # 1 stmt
            ServiceHints(service_id="b", service_name="b", owner="team-b"),  # 1 stmt
            ServiceHints(service_id="c", service_name="c"),  # 0 stmt
        ]
        r = generate_collector_enrichment(services, BusinessContext(), _report())
        stmts = yaml.safe_load(r.content)["processors"]["transform/business"][
            "trace_statements"
        ][0]["statements"]
        assert len(stmts) == 2

    def test_presence_gate_skips_when_no_business(self):
        r = generate_collector_enrichment(
            [ServiceHints(service_id="a", service_name="a")],
            BusinessContext(),
            _report(),
        )
        assert r.status == "skipped"
        assert r.content == ""

    def test_uses_real_service_name_not_id(self):
        r = generate_collector_enrichment(
            [
                ServiceHints(
                    service_id="mastodonweb",
                    service_name="mastodon/web",
                    criticality="high",
                )
            ],
            BusinessContext(),
            _report(),
        )
        assert 'resource.attributes["service.name"] == "mastodon/web"' in r.content
        assert "mastodonweb" not in r.content

    def test_falls_back_to_service_id_when_name_empty(self):
        r = generate_collector_enrichment(
            [ServiceHints(service_id="svc-x", service_name="", criticality="low")],
            BusinessContext(),
            _report(),
        )
        assert 'service.name"] == "svc-x"' in r.content

    def test_deterministic_across_shuffled_input(self):
        services = _boutique_services()
        a = generate_collector_enrichment(
            services, BusinessContext(project_id="ob"), _report()
        ).content
        shuffled = services[:]
        random.Random(7).shuffle(shuffled)
        b = generate_collector_enrichment(
            shuffled, BusinessContext(project_id="ob"), _report()
        ).content
        assert a == b

    def test_provenance_header_present(self):
        r = generate_collector_enrichment(
            _boutique_services(), BusinessContext(), _report()
        )
        assert "# GENERATED" in r.content
        assert "# provenance: sha256:" in r.content

    def test_criticality_statements_before_owner(self):
        r = generate_collector_enrichment(
            _boutique_services(), BusinessContext(), _report()
        )
        stmts = yaml.safe_load(r.content)["processors"]["transform/business"][
            "trace_statements"
        ][0]["statements"]
        first_owner = next(i for i, s in enumerate(stmts) if "business.owner" in s)
        last_crit = max(i for i, s in enumerate(stmts) if "business.criticality" in s)
        assert last_crit < first_owner


class TestFR6Escaping:
    def test_ottl_str_escapes_backslash_then_quote(self):
        assert _ottl_str('a"b\\c') == 'a\\"b\\\\c'

    def test_hostile_owner_roundtrips_intact(self):
        hostile = 'O"Brien\\ #1: lead'
        r = generate_collector_enrichment(
            [
                ServiceHints(
                    service_id="s",
                    service_name="team/a",
                    criticality="critical",
                    owner=hostile,
                )
            ],
            BusinessContext(),
            _report(),
        )
        assert r.status == "generated"
        assert yaml.safe_load(r.content) is not None  # valid YAML
        m = extract_enrichment_map(r.content)
        assert m["team/a"]["owner"] == hostile  # survived both escaping layers


# ============================ FR-8: fail-fast validation ============================


class TestFR8Validation:
    def test_valid_rows_pass(self):
        validate_collector_enrichment(
            [("s", "criticality", "low"), ("s", "owner", "t")], {"s"}
        )

    def test_out_of_enum_criticality_raises(self):
        with pytest.raises(CollectorEnrichmentError):
            validate_collector_enrichment([("s", "criticality", "bogus")], {"s"})

    def test_duplicate_pair_raises(self):
        with pytest.raises(CollectorEnrichmentError):
            validate_collector_enrichment(
                [("s", "owner", "x"), ("s", "owner", "y")], {"s"}
            )

    def test_empty_service_name_raises(self):
        with pytest.raises(CollectorEnrichmentError):
            validate_collector_enrichment([("", "criticality", "low")], {""})

    def test_business_service_with_zero_statements_raises(self):
        with pytest.raises(CollectorEnrichmentError):
            validate_collector_enrichment([], {"ghost"})

    def test_different_attrs_same_service_ok(self):
        validate_collector_enrichment(
            [("s", "criticality", "high"), ("s", "owner", "t")], {"s"}
        )


# ============================ FR-10a/11: semantic parity ============================


class TestParity:
    def test_generated_matches_reference(self):
        r = generate_collector_enrichment(
            _boutique_services(), BusinessContext(project_id="ob"), _report()
        )
        pr = check_collector_enrichment_parity(r.content, _FIXTURE.read_text())
        assert pr.matches, pr.summary()

    def test_value_mismatch_detected(self):
        gen = generate_collector_enrichment(
            [
                ServiceHints(
                    service_id="frontend",
                    service_name="frontend",
                    criticality="critical",
                )
            ],
            BusinessContext(),
            _report(),
        ).content
        bad_ref = (
            "processors:\n  transform/business:\n    trace_statements:\n    - context: span\n"
            '      statements:\n      - set(attributes["business.criticality"], "low") where '
            'resource.attributes["service.name"] == "frontend"\n'
        )
        pr = check_collector_enrichment_parity(gen, bad_ref)
        assert not pr.matches
        assert pr.value_mismatch["frontend"]["criticality"] == {
            "generated": "critical",
            "reference": "low",
        }

    def test_missing_service_detected(self):
        gen = generate_collector_enrichment(
            [ServiceHints(service_id="a", service_name="a", criticality="high")],
            BusinessContext(),
            _report(),
        ).content
        pr = check_collector_enrichment_parity(gen, "processors: {}\n")
        assert not pr.matches
        assert "a" in pr.only_in_generated

    def test_grouping_insensitive(self):
        # generator emits one-per-service; a grouped OR-chain reference is still equivalent
        services = [
            ServiceHints(service_id="a", service_name="a", criticality="critical"),
            ServiceHints(service_id="b", service_name="b", criticality="critical"),
        ]
        gen = generate_collector_enrichment(
            services, BusinessContext(), _report()
        ).content
        grouped = (
            "processors:\n  transform/business:\n    trace_statements:\n    - context: span\n"
            '      statements:\n      - set(attributes["business.criticality"], "critical") where '
            'resource.attributes["service.name"] == "a" or resource.attributes["service.name"] == "b"\n'
        )
        assert check_collector_enrichment_parity(gen, grouped).matches


# ============================ Wiring / SOTTO byte-identical absence ============================


class TestWiring:
    def test_end_to_end_emits_when_business_present(self, tmp_path):
        from startd8.observability.artifact_generator import (
            generate_observability_artifacts,
        )

        meta = {
            "instrumentation_hints": {
                "cartservice": {
                    "transport": "grpc",
                    "service_name": "cartservice",
                    "business": {"criticality": "critical", "owner": "commerce-team"},
                },
            },
            "declared_artifact_types": [],
        }
        mp = tmp_path / "onboarding.json"
        mp.write_text(__import__("json").dumps(meta))
        report = generate_observability_artifacts(
            onboarding_metadata_path=mp, output_dir=tmp_path / "out", dry_run=True
        )
        ce = [a for a in report.artifacts if a.artifact_type == "collector_enrichment"]
        assert len(ce) == 1
        assert ce[0].category == Category.PROJECT.value  # taxonomy stamped
        assert ce[0].orientation == Orientation.SYSTEM.value

    def test_no_artifact_when_no_business_context(self, tmp_path):
        from startd8.observability.artifact_generator import (
            generate_observability_artifacts,
        )

        meta = {
            "instrumentation_hints": {
                "cartservice": {"transport": "grpc", "service_name": "cartservice"},
            },
            "declared_artifact_types": [],
        }
        mp = tmp_path / "onboarding.json"
        mp.write_text(__import__("json").dumps(meta))
        report = generate_observability_artifacts(
            onboarding_metadata_path=mp, output_dir=tmp_path / "out", dry_run=True
        )
        assert not [
            a for a in report.artifacts if a.artifact_type == "collector_enrichment"
        ]


# ============================ enrichment-parity CLI (QW-1) ============================


class TestParityCLI:
    """`startd8 observability enrichment-parity` — exposes the parity gate for operators."""

    def _write_generated(self, tmp_path):
        r = generate_collector_enrichment(
            _boutique_services(), BusinessContext(project_id="ob"), _report()
        )
        p = tmp_path / "gen.yaml"
        p.write_text(r.content)
        return p

    def test_match_exits_zero(self, tmp_path):
        from typer.testing import CliRunner
        from startd8.observability.cli import observability_app

        gen = self._write_generated(tmp_path)
        res = CliRunner().invoke(
            observability_app,
            ["enrichment-parity", "-g", str(gen), "-r", str(_FIXTURE)],
        )
        assert res.exit_code == 0
        assert "PARITY OK" in res.stdout

    def test_mismatch_exits_one(self, tmp_path):
        from typer.testing import CliRunner
        from startd8.observability.cli import observability_app

        gen = self._write_generated(tmp_path)
        bad = tmp_path / "bad.yaml"
        bad.write_text(gen.read_text().replace('"critical"', '"low"'))
        res = CliRunner().invoke(
            observability_app,
            ["enrichment-parity", "-g", str(gen), "-r", str(bad), "--json"],
        )
        assert res.exit_code == 1
        assert '"matches": false' in res.stdout

    def test_missing_file_exits_two(self, tmp_path):
        from typer.testing import CliRunner
        from startd8.observability.cli import observability_app

        gen = self._write_generated(tmp_path)
        res = CliRunner().invoke(
            observability_app,
            ["enrichment-parity", "-g", str(tmp_path / "nope.yaml"), "-r", str(gen)],
        )
        assert res.exit_code == 2


# ============================ EC-1: per-service severity + owner ============================


class TestEC1PerServiceSeverity:
    def test_service_criticality_wins_over_project(self):
        from startd8.observability.artifact_generator_generators import _severity_for

        derivs = []
        sev = _severity_for(
            BusinessContext(criticality="low"),
            derivs,
            ServiceHints(service_id="s", service_name="s", criticality="critical"),
        )
        assert sev == "critical"  # per-service, not project "low"→info
        assert "instrumentation_hints[s].business.criticality" in derivs[0].source

    def test_absent_service_criticality_falls_back_to_project(self):
        from startd8.observability.artifact_generator_generators import _severity_for

        derivs = []
        sev = _severity_for(
            BusinessContext(criticality="low"),
            derivs,
            ServiceHints(
                service_id="s", service_name="s"
            ),  # no per-service criticality
        )
        assert sev == "info"
        # trace kept byte-identical to pre-EC-1 on the project path
        assert derivs[0].source == "manifest.spec.business.criticality"

    def test_no_service_arg_falls_back(self):
        from startd8.observability.artifact_generator_generators import _severity_for

        sev = _severity_for(BusinessContext(criticality="high"), [])
        assert sev == "critical"

    def test_alert_rule_uses_per_service_severity(self):
        from startd8.observability.artifact_generator_generators import (
            generate_alert_rules,
        )
        from startd8.observability.artifact_generator_models import ConventionMetric

        metrics = [
            ConventionMetric("http.server.duration", "histogram", "otel_semconv:http")
        ]
        svc = ServiceHints(
            service_id="cart",
            service_name="cart",
            transport="http",
            criticality="critical",
            convention_metrics=metrics,
        )
        out = generate_alert_rules(svc, BusinessContext(criticality="low")).content
        assert "severity: critical" in out  # per-service critical, not project low→info
        # control: same service without per-service criticality → project low→info
        svc_plain = ServiceHints(
            service_id="cart",
            service_name="cart",
            transport="http",
            convention_metrics=metrics,
        )
        out_plain = generate_alert_rules(
            svc_plain, BusinessContext(criticality="low")
        ).content
        assert "severity: info" in out_plain and "severity: critical" not in out_plain

    def test_runbook_uses_per_service_owner(self):
        from startd8.observability.artifact_generator_generators import generate_runbook

        svc = ServiceHints(
            service_id="cart",
            service_name="cart",
            transport="grpc",
            owner="commerce-team",
        )
        out = generate_runbook(svc, BusinessContext()).content
        assert "- Owner: commerce-team" in out


# ============================ EC-2: spanmetrics dimension + QW-3 coverage ============================


class TestEC2DimensionAndCoverage:
    def test_criticality_emits_spanmetrics_dimension(self):
        r = generate_collector_enrichment(
            [ServiceHints(service_id="a", service_name="a", criticality="critical")],
            BusinessContext(),
            _report(),
        )
        doc = yaml.safe_load(r.content)
        assert doc["connectors"]["spanmetrics"]["dimensions"] == [
            {"name": "business.criticality"}
        ]

    def test_owner_only_emits_no_dimension(self):
        # owner alone must NOT become a metric dimension (unbounded cardinality).
        r = generate_collector_enrichment(
            [ServiceHints(service_id="a", service_name="a", owner="team-x")],
            BusinessContext(),
            _report(),
        )
        doc = yaml.safe_load(r.content)
        assert "connectors" not in doc

    def test_dimension_does_not_break_parity(self):
        # the added connectors block must not affect the processors-only semantic parity gate
        r = generate_collector_enrichment(
            _boutique_services(), BusinessContext(project_id="ob"), _report()
        )
        assert check_collector_enrichment_parity(
            r.content, _FIXTURE.read_text()
        ).matches

    def test_fr_coverage_populated(self):
        rep = _report()
        generate_collector_enrichment(
            [
                ServiceHints(
                    service_id="a", service_name="a", criticality="high", owner="t"
                )
            ],
            BusinessContext(),
            rep,
        )
        cov = rep.fr_coverage["collector_enrichment"]
        assert cov["statements"] == 2
        assert cov["services_enriched"] == 1
        assert cov["criticality_dimension"] is True
        assert cov["provenance"].startswith("sha256:")


# ============================ QW-4/QW-5: append-safety + drift derivation ============================


class TestQW4AppendComment:
    def test_connectors_block_marked_append_only(self):
        r = generate_collector_enrichment(
            [ServiceHints(service_id="a", service_name="a", criticality="critical")],
            BusinessContext(),
            _report(),
        )
        # inline marker sits on the line directly above the connectors block (not just the header)
        assert "(see DEPLOYING.md).\nconnectors:\n" in r.content
        assert yaml.safe_load(r.content) is not None  # still valid YAML (it's a YAML comment)

    def test_no_append_comment_when_no_dimension(self):
        # owner-only ⇒ no connectors block ⇒ no append comment
        r = generate_collector_enrichment(
            [ServiceHints(service_id="a", service_name="a", owner="team")],
            BusinessContext(),
            _report(),
        )
        assert "# APPEND" not in r.content


class TestQW5DriftDerivation:
    def _deriv(self, crit):
        r = generate_collector_enrichment(
            [ServiceHints(service_id="cart", service_name="cart", criticality=crit)],
            BusinessContext(),
            _report(),
        )
        return r.derivations

    def test_emits_one_stable_keyed_provenance_derivation(self):
        [d] = self._deriv("critical")
        assert d.field == "collector_enrichment.business"
        assert d.source == "instrumentation_hints[*].business"
        assert d.transformation.startswith("sha256:")

    def test_key_stable_but_hash_changes_on_business_change(self):
        [a] = self._deriv("critical")
        [b] = self._deriv("high")
        assert (a.field, a.source) == (b.field, b.source)  # stable key
        assert a.transformation != b.transformation  # hash tracks the change

    def test_check_drift_flags_a_business_change(self):
        # exercise the real check_drift derivation-rule path end-to-end
        import json

        from startd8.observability.artifact_generator import (
            check_drift,
            generate_observability_artifacts,
        )

        def _meta(crit):
            return {
                "instrumentation_hints": {
                    "cart": {
                        "transport": "grpc",
                        "service_name": "cart",
                        "business": {"criticality": crit},
                    }
                },
                "declared_artifact_types": [],
            }

        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            mp = td / "onboarding.json"
            out = td / "out"
            # run 1: criticality=critical, write the index
            mp.write_text(json.dumps(_meta("critical")))
            generate_observability_artifacts(
                onboarding_metadata_path=mp, output_dir=out, dry_run=False
            )
            assert (out / "observability-manifest.yaml").exists()
            # unchanged manifest ⇒ no drift
            assert check_drift(mp, out) == 0
            # run 2: criticality flips ⇒ drift MUST be detected (was silently missed pre-QW-5)
            mp.write_text(json.dumps(_meta("high")))
            assert check_drift(mp, out) == 1
