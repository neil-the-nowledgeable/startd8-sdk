"""CS-17 / M0 — scoring-method identity stamping + resolution, and its backward-compat guarantees.

Covers: the stamped→inferred→unknown resolution chain, the taxonomy, and the two A1/A2 adversarial
checks that stood in for a full CRP (plan §X): A2 here (spec_hash stable + scorecard output unchanged);
A1 (classify all real run dirs) is run as a Summer2026-side validation.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from startd8.benchmark_matrix import BenchmarkRunSpec, MethodSignature, method_signature
from startd8.benchmark_matrix.method import _derive_method
from startd8.benchmark_matrix.scorecard import build_scorecard


# --------------------------------------------------------------------------- helpers
def _write(run_dir: Path, *, spec: dict | None = None, cells: list | None = None) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    if spec is not None:
        (run_dir / "run-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    if cells is not None:
        (run_dir / "cells.json").write_text(json.dumps(cells), encoding="utf-8")
    return run_dir


def _cell(service="adservice", model="anthropic:claude-opus-4-8", rep=0, *, defect_total=None):
    return {
        "cell_id": f"abc123:{service}:{model}:r{rep}", "service": service, "model": model,
        "language": "go", "repetition": rep, "status": "ok", "quality": 0.97,
        "defect_total": defect_total,
    }


# --------------------------------------------------------------------------- taxonomy (OQ-8)
@pytest.mark.parametrize("repair,expose,expected", [
    ("apply", False, "naive"),
    ("apply", True, "expose"),
    ("shadow", True, "shadow+expose"),
    ("shadow", False, "shadow"),
    ("off", False, "raw"),
])
def test_derive_method_taxonomy(repair, expose, expected):
    assert _derive_method(repair, expose) == expected


# --------------------------------------------------------------------------- resolution chain
def test_stamped_signature_is_authoritative(tmp_path):
    rd = _write(tmp_path / "r", spec={
        "repair_mode": "shadow", "expose_defects": True,
        "sdk_version": "0.4.0", "scoring_formula": "compile_gate+...",
    })
    sig = method_signature(rd)
    assert sig.scoring_method == "shadow+expose"
    assert sig.expose is True
    assert sig.repair_mode == "shadow"
    assert sig.source == "stamped"
    assert sig.is_inferred is False
    assert sig.parity_key == ("shadow+expose", "0.4.0", "compile_gate+...")


def test_inferred_expose_from_defect_ledger(tmp_path):
    # no stamp; a cell carries defect_total ⇒ the ledger ran ⇒ expose (repair posture unknown)
    rd = _write(tmp_path / "r", spec={"sdk_version": "0.4.0"},
                cells=[_cell(defect_total=1), _cell(rep=1, defect_total=None)])
    sig = method_signature(rd)
    assert sig.scoring_method == "expose"
    assert sig.expose is True
    assert sig.repair_mode is None          # unrecoverable from cells
    assert sig.source == "inferred:defect_ledger"
    assert sig.is_inferred is True


def test_inferred_naive_when_no_ledger(tmp_path):
    rd = _write(tmp_path / "r", cells=[_cell(defect_total=None), _cell(rep=1, defect_total=None)])
    sig = method_signature(rd)
    assert sig.scoring_method == "naive"
    assert sig.expose is False
    assert sig.source == "inferred:no_ledger"


def test_unknown_when_nothing(tmp_path):
    rd = tmp_path / "empty"
    rd.mkdir()
    sig = method_signature(rd)
    assert sig.scoring_method == "unknown"
    assert sig.source == "none"


def test_tolerates_malformed_inputs(tmp_path):
    # CS-16: malformed run-spec + malformed cells must degrade, never raise.
    rd = tmp_path / "bad"
    rd.mkdir()
    (rd / "run-spec.json").write_text("{not json", encoding="utf-8")
    (rd / "cells.json").write_text("also not json", encoding="utf-8")
    assert method_signature(rd).scoring_method == "unknown"


def test_conservative_parity_inferred_vs_stamped(tmp_path):
    """An inferred `expose` must NOT match a stamped `shadow+expose` — over-cautious by design."""
    inferred = _write(tmp_path / "i", spec={"sdk_version": "0.4.0", "scoring_formula": "f"},
                      cells=[_cell(defect_total=1)])
    stamped = _write(tmp_path / "s", spec={
        "repair_mode": "shadow", "expose_defects": True, "sdk_version": "0.4.0", "scoring_formula": "f"})
    assert method_signature(inferred).parity_key != method_signature(stamped).parity_key


# --------------------------------------------------------------------------- A2: backward-compat
def _base_spec_kwargs():
    return dict(
        name="t", models=("anthropic:claude-opus-4-8",), services=("adservice",),
        repetitions=1, seed_hashes={"adservice": "deadbeef"}, proto_sha256="cafe",
    )


def test_new_fields_excluded_from_spec_hash(tmp_path):
    # Two specs differing ONLY in repair_mode/expose_defects must hash identically (archived
    # spec_hashes + cell_ids stay byte-stable — the CS-17 backward-compat guarantee).
    a = BenchmarkRunSpec(**_base_spec_kwargs(), repair_mode="apply", expose_defects=False)
    b = BenchmarkRunSpec(**_base_spec_kwargs(), repair_mode="shadow", expose_defects=True)
    assert a.spec_hash() == b.spec_hash()


def test_new_fields_serialize_and_roundtrip():
    spec = BenchmarkRunSpec(**_base_spec_kwargs(), repair_mode="shadow", expose_defects=True)
    d = json.loads(spec.to_json())
    assert d["repair_mode"] == "shadow" and d["expose_defects"] is True
    back = BenchmarkRunSpec.from_dict(d)
    assert back.repair_mode == "shadow" and back.expose_defects is True


def test_old_run_spec_without_fields_still_loads():
    # a pre-CS-17 run-spec (no repair_mode/expose_defects) loads with defaults — never raises.
    spec = BenchmarkRunSpec(**_base_spec_kwargs())
    assert spec.repair_mode == "apply" and spec.expose_defects is False


def test_scorecard_output_unchanged_by_new_fields(tmp_path):
    # A2: build_scorecard reads only name/spec_hash/micro_prime/services/models/reps from run-spec —
    # adding repair_mode/expose_defects must not change rendered output.
    cells = [_cell(defect_total=1)]
    without = _write(tmp_path / "wo", spec={"name": "x", "spec_hash": "h", "services": ["adservice"],
                                            "models": ["anthropic:claude-opus-4-8"], "repetitions": 1},
                     cells=cells)
    with_fields = _write(tmp_path / "wf", spec={"name": "x", "spec_hash": "h", "services": ["adservice"],
                                                "models": ["anthropic:claude-opus-4-8"], "repetitions": 1,
                                                "repair_mode": "shadow", "expose_defects": True},
                         cells=cells)
    from datetime import datetime, timezone
    now = datetime(2026, 6, 16, tzinfo=timezone.utc)
    assert build_scorecard(without, now=now) == build_scorecard(with_fields, now=now)
