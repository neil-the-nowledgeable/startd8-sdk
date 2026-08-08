"""Onboarding-metadata schema-version tolerance (CH-6 cross-repo version handshake).

The consumer reads an OPTIONAL top-level ``schema_version`` and WARNS — never fails — on a MAJOR it
doesn't understand, so a producer schema bump surfaces as a legible log line instead of silently
degrading into the structural ``.get()`` defaults. Absent ``schema_version`` is byte-identical to
today (no current producer stamps one).
"""

import json

from startd8.observability.artifact_generator_context import (
    SUPPORTED_ONBOARDING_SCHEMA_MAJOR,
    load_onboarding_metadata,
)


def _write(tmp_path, doc):
    p = tmp_path / "onboarding-metadata.json"
    p.write_text(json.dumps(doc))
    return p


def test_absent_schema_version_is_silent_and_loads(tmp_path, caplog):
    # back-compat: no version → no warning, load unchanged.
    doc = {"project_id": "p", "instrumentation_hints": {}}
    with caplog.at_level("WARNING"):
        data = load_onboarding_metadata(_write(tmp_path, doc))
    assert data == doc
    assert not [r for r in caplog.records if "schema_version" in r.message]


def test_matching_major_does_not_warn(tmp_path, caplog):
    doc = {"schema_version": f"{SUPPORTED_ONBOARDING_SCHEMA_MAJOR}.3", "project_id": "p"}
    with caplog.at_level("WARNING"):
        load_onboarding_metadata(_write(tmp_path, doc))
    assert not [r for r in caplog.records if "schema_version" in r.message]


def test_unsupported_major_warns_but_still_loads(tmp_path, caplog):
    doc = {"schema_version": f"{SUPPORTED_ONBOARDING_SCHEMA_MAJOR + 1}.0", "project_id": "p"}
    with caplog.at_level("WARNING"):
        data = load_onboarding_metadata(_write(tmp_path, doc))
    assert data["project_id"] == "p"  # never fails — degrade-safe
    warns = [r for r in caplog.records if "schema_version" in r.message]
    assert warns and "consumer supports MAJOR" in warns[0].message


def test_malformed_version_warns_not_raises(tmp_path, caplog):
    doc = {"schema_version": "not-a-version", "project_id": "p"}
    with caplog.at_level("WARNING"):
        data = load_onboarding_metadata(_write(tmp_path, doc))  # must not raise
    assert data["project_id"] == "p"
    assert [r for r in caplog.records if "unparseable schema_version" in r.message]


def test_int_major_only_is_accepted(tmp_path, caplog):
    # a bare "1" (no minor) parses fine and matches.
    doc = {"schema_version": str(SUPPORTED_ONBOARDING_SCHEMA_MAJOR), "project_id": "p"}
    with caplog.at_level("WARNING"):
        load_onboarding_metadata(_write(tmp_path, doc))
    assert not [r for r in caplog.records if "schema_version" in r.message]
