# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""P2: §2.12 observability prose participates in kickoff-check extraction (Slice 1)."""

from __future__ import annotations

import textwrap

import pytest

from startd8.manifest_extraction import extract_manifests
from startd8.manifest_extraction.models import Status

pytestmark = pytest.mark.unit

GOOD = textwrap.dedent("""\
    ## Observability

    - Provenance default: config-default

    ### Alerting

    #### Receivers

    | Name | Type | Target | Severities |
    |------|------|--------|------------|
    | default | webhook | ${WEBHOOK_URL} | critical, warning |

    #### Thresholds

    | Metric | Op | Value | Unit | Severity | For |
    |--------|----|-------|------|----------|-----|
    | app_error_rate | > | 0.02 | ratio | critical | 5m |
    | chore_overdue | > | 0 | count | warning | 0m |
""")


def _obs_records(res):
    return [r for r in res.records if r.manifest == "observability.yaml"]


def test_observability_extracts_and_round_trips():
    res = extract_manifests({"observability.md": GOOD})
    assert "observability.yaml" in res.manifests            # emitted + round-tripped (no RoundTripError)
    recs = _obs_records(res)
    assert {r.status for r in recs} == {Status.EXTRACTED}
    paths = {r.value_path for r in recs}
    assert paths == {
        "/alerting/metric_thresholds/app_error_rate",
        "/alerting/metric_thresholds/chore_overdue",
        "/alerting/receivers/default",
    }
    # traceability: each record carries a structured source ref
    assert all(r.source and r.source.doc == "observability.md" for r in recs)


def test_grammar_version_bumped():
    res = extract_manifests({"observability.md": GOOD})
    assert res.grammar_version == "authoring-contract-v0.4"


def test_bad_op_flagged_not_extracted():
    bad = GOOD.replace("| > | 0.02 |", "| => | 0.02 |")
    res = extract_manifests({"observability.md": bad})
    recs = _obs_records(res)
    assert any(r.status == Status.NOT_EXTRACTED for r in recs)
    assert "observability.yaml" not in res.manifests        # strict parser rejected the section


def test_literal_secret_target_flagged():
    bad = GOOD.replace("${WEBHOOK_URL}", "https://hooks.slack.com/services/SECRET")
    res = extract_manifests({"observability.md": bad})
    recs = _obs_records(res)
    assert any(r.status == Status.NOT_EXTRACTED and "secret" in (r.reason or "") for r in recs)


def test_no_observability_section_is_silent():
    res = extract_manifests({"some.md": "# A doc\n\nNo observability here.\n"})
    assert _obs_records(res) == []
    assert "observability.yaml" not in res.manifests
