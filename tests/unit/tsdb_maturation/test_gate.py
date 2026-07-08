"""M4 gate-wiring tests (FR-7) — the promotion policy matrix.

Refuse empty (OQ-6); enforce the M2.5 confirmation; reuse emit_schema_draft→promote_schema;
greenfield gate = round-trip + non-empty + no-unrenderable; a re-promote computes parity.
"""

from __future__ import annotations

from itertools import product


from startd8.tsdb_maturation import (
    ReadResult,
    Series,
    Specimen,
    gate_and_promote,
    infer_schema,
    record_confirmation,
)
from startd8.tsdb_maturation.confirmation import ConfirmationStatus

METRIC = "gov_expenditure_amount"
ENTITY = "DepartmentBudget"
SCHEMA_REL = "prisma/schema.prisma"


def _specimen(records=None):
    records = records if records is not None else _composite_records()
    series = [Series(labels=dict(r), value=float(i), timestamp=0.0) for i, r in enumerate(records)]
    return Specimen.from_read_result(ReadResult(metric=METRIC, lookback="3000d", series=tuple(series)))


def _composite_records():
    return [{"department": d, "fiscal_year": fy}
            for d, fy in product(["corrections", "health"], ["2025", "2026"])]


def _inference(spec=None):
    return infer_schema(spec or _specimen(), entity_name=ENTITY)


def _confirm(project_root, result):
    record_confirmation(project_root, METRIC, result.entity, result.identity_fields, today="2026-07-08")


# --------------------------------------------------------------------------- #
# Confirmation enforcement (M2.5 ↔ M4).                                        #
# --------------------------------------------------------------------------- #
def test_unconfirmed_is_refused_not_promoted(tmp_path):
    res = _inference()
    out = gate_and_promote(res, _specimen(), metric=METRIC, project_root=tmp_path,
                           run_dir=tmp_path / "run")
    assert out.refused
    assert out.confirmation is ConfirmationStatus.UNCONFIRMED
    assert "confirmation required" in out.reason
    assert not (tmp_path / SCHEMA_REL).exists()  # nothing flipped


def test_confirmed_promotes_and_flips_schema(tmp_path):
    res = _inference()
    _confirm(tmp_path, res)
    out = gate_and_promote(res, _specimen(), metric=METRIC, project_root=tmp_path,
                           run_dir=tmp_path / "run")
    assert out.promoted
    assert out.confirmation is ConfirmationStatus.CONFIRMED
    schema_file = tmp_path / SCHEMA_REL
    assert schema_file.is_file()
    text = schema_file.read_text()
    assert "model DepartmentBudget" in text
    assert "@@unique([department, fiscalYear])" in text or "fiscalYear" in text


def test_stale_confirmation_is_refused(tmp_path):
    res = _inference()
    # Confirm a DIFFERENT key, then attempt promotion of the inferred one → STALE.
    record_confirmation(tmp_path, METRIC, ENTITY, ["department", "fiscal_year", "extra"], today="2026-07-08")
    out = gate_and_promote(res, _specimen(), metric=METRIC, project_root=tmp_path,
                           run_dir=tmp_path / "run")
    assert out.refused
    assert out.confirmation is ConfirmationStatus.STALE
    assert "re-confirm" in out.reason


def test_force_bypasses_confirmation(tmp_path):
    res = _inference()
    out = gate_and_promote(res, _specimen(), metric=METRIC, project_root=tmp_path,
                           run_dir=tmp_path / "run", require_confirmed=False)
    assert out.promoted  # bypassed, but status still reported
    assert out.confirmation is ConfirmationStatus.UNCONFIRMED


# --------------------------------------------------------------------------- #
# Empty materialization → refuse (OQ-6).                                       #
# --------------------------------------------------------------------------- #
def test_empty_specimen_refused(tmp_path):
    res = _inference()  # inference off a non-empty spec…
    empty = Specimen.from_records(METRIC, [])  # …but gate an empty specimen
    out = gate_and_promote(res, empty, metric=METRIC, project_root=tmp_path,
                           run_dir=tmp_path / "run")
    assert out.refused
    assert "empty materialization" in out.reason
    assert out.gate is None  # refused before the emit gate ran


# --------------------------------------------------------------------------- #
# The emit gate passes structurally for a valid inferred schema.               #
# --------------------------------------------------------------------------- #
def test_gate_ok_and_round_trips(tmp_path):
    res = _inference()
    _confirm(tmp_path, res)
    out = gate_and_promote(res, _specimen(), metric=METRIC, project_root=tmp_path,
                           run_dir=tmp_path / "run")
    assert out.gate is not None
    assert out.gate.ok
    assert out.gate.round_trips
    assert out.gate.unrenderable == ()


# --------------------------------------------------------------------------- #
# Re-promote parity (schema evolution) — a diverging live contract drifts.      #
# --------------------------------------------------------------------------- #
def test_re_promote_same_schema_has_no_drift(tmp_path):
    res = _inference()
    _confirm(tmp_path, res)
    # First promote writes the contract.
    first = gate_and_promote(res, _specimen(), metric=METRIC, project_root=tmp_path,
                             run_dir=tmp_path / "run")
    assert first.promoted
    # Second promote against the now-existing identical contract → parity, no drift.
    second = gate_and_promote(res, _specimen(), metric=METRIC, project_root=tmp_path,
                              run_dir=tmp_path / "run2")
    assert second.promoted
    assert second.gate.parity_drift == ()


def test_re_promote_diverging_schema_drifts_and_refuses(tmp_path):
    res = _inference()
    _confirm(tmp_path, res)
    gate_and_promote(res, _specimen(), metric=METRIC, project_root=tmp_path,
                     run_dir=tmp_path / "run")
    # Now infer a schema with an EXTRA label → different model → parity drift on re-promote.
    extra_spec = _specimen([{"department": d, "fiscal_year": fy, "note": n}
                            for d, fy, n in product(["corrections", "health"], ["2025", "2026"], ["x"])])
    res2 = infer_schema(extra_spec, entity_name=ENTITY)
    # confirm the new (changed) key so we're testing the PARITY gate, not the confirmation gate
    record_confirmation(tmp_path, METRIC, ENTITY, res2.identity_fields, today="2026-07-09")
    out = gate_and_promote(res2, extra_spec, metric=METRIC, project_root=tmp_path,
                           run_dir=tmp_path / "run3")
    assert out.refused
    assert out.gate.parity_drift != ()
    assert "parity drift" in out.reason


# --------------------------------------------------------------------------- #
# The surface is always populated (human-facing identity/gate summary).        #
# --------------------------------------------------------------------------- #
def test_surface_present_on_refusal_and_promotion(tmp_path):
    res = _inference()
    refused = gate_and_promote(res, _specimen(), metric=METRIC, project_root=tmp_path,
                               run_dir=tmp_path / "run")
    assert "inferred key" in refused.surface
    _confirm(tmp_path, res)
    promoted = gate_and_promote(res, _specimen(), metric=METRIC, project_root=tmp_path,
                                run_dir=tmp_path / "run2")
    assert "inferred key" in promoted.surface
