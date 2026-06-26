"""M6 — value write-back path: merge fidelity, allow-list, round-trip, concurrency."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from startd8.kickoff_experience.capture import (
    CaptureCode,
    CaptureError,
    apply_capture,
    build_capture_plan,
    locate_key_line,
    splice_yaml_value,
)
from startd8.kickoff_experience.manifest import default_config


# --- splicer: merge fidelity (R1-S1) -----------------------------------------------------------

SAMPLE = textwrap.dedent(
    """\
    # header comment — must survive
    domain: conventions
    provenance_default: authored   # inline note kept

    language: python
    stack:
      framework: fastapi   # the web framework
      data_layer: sqlmodel
    data_model:
      money: cents
      datetime: utc
    """
)


def test_locate_top_level_and_nested_keys() -> None:
    lines = SAMPLE.split("\n")
    assert _line_text(lines, locate_key_line(lines, "language")) == "language: python"
    assert "framework: fastapi" in _line_text(lines, locate_key_line(lines, "stack.framework"))
    assert "money: cents" in _line_text(lines, locate_key_line(lines, "data_model.money"))
    assert locate_key_line(lines, "data_model.nonexistent") is None
    assert locate_key_line(lines, "stack.money") is None  # money is under data_model, not stack


def test_splice_touches_only_target_value_line() -> None:
    res = splice_yaml_value(SAMPLE, "data_model.money", "float")
    before = SAMPLE.split("\n")
    after = res.text.split("\n")
    assert len(before) == len(after)
    diffs = [i for i in range(len(before)) if before[i] != after[i]]
    assert diffs == [res.line_index], "exactly one line changed"
    # Comments + ordering preserved everywhere else, byte-for-byte.
    assert after[0] == "# header comment — must survive"
    assert "inline note kept" in res.text
    assert res.old_value == "cents"
    assert "money: float" in after[res.line_index]


def test_splice_preserves_inline_comment_on_target() -> None:
    res = splice_yaml_value(SAMPLE, "stack.framework", "starlette")
    assert "# the web framework" in res.new_line
    assert res.new_line.strip().startswith("framework: starlette")


def test_splice_quotes_dollar_values() -> None:
    text = 'budgets:\n  per_pipeline_run: "$5.00"\n'
    res = splice_yaml_value(text, "budgets.per_pipeline_run", "$12.00")
    assert 'per_pipeline_run: "$12.00"' in res.text


def test_splice_missing_key_raises_key_not_found() -> None:
    with pytest.raises(CaptureError) as ei:
        splice_yaml_value(SAMPLE, "data_model.nope", "x")
    assert ei.value.code == CaptureCode.KEY_NOT_FOUND


def test_splice_refuses_to_clobber_a_mapping_parent() -> None:
    # Targeting a mapping/block key (e.g. "stack", which has children) must NOT write a scalar
    # over it — that would silently destroy the nested block.
    with pytest.raises(CaptureError) as ei:
        splice_yaml_value(SAMPLE, "stack", "oops")
    assert ei.value.code == CaptureCode.KEY_NOT_FOUND
    assert "mapping" in str(ei.value)
    assert "framework: fastapi" in SAMPLE  # untouched


# --- build_capture_plan: allow-list, traversal, round-trip --------------------------------------


def _project_with_conventions(tmp_path: Path) -> Path:
    inputs = tmp_path / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "conventions.yaml").write_text(SAMPLE, encoding="utf-8")
    return tmp_path


def test_capture_plan_rejects_unknown_value_path(tmp_path: Path) -> None:
    root = _project_with_conventions(tmp_path)
    with pytest.raises(CaptureError) as ei:
        build_capture_plan(root, "conventions.yaml#/not_a_field", "x")
    assert ei.value.code == CaptureCode.VALUE_PATH_NOT_ALLOWED


def test_capture_plan_for_real_field_round_trips(tmp_path: Path) -> None:
    root = _project_with_conventions(tmp_path)
    # conv_money -> conventions.yaml#/data_model.money is in the seeded allow-list.
    plan = build_capture_plan(root, "conventions.yaml#/data_model.money", "float")
    assert plan.key == "data_model.money"
    assert plan.old_value == "cents"
    assert plan.new_value == "float"
    assert plan.base_sha
    assert "money: float" in plan.candidate_text
    # Preview is renderable (R2-S1) and names the file + provenance.
    pv = plan.preview()
    assert pv["file"] == "docs/kickoff/inputs/conventions.yaml"
    assert pv["old_value"] == "cents"


def test_capture_plan_missing_target_file(tmp_path: Path) -> None:
    (tmp_path / "docs" / "kickoff" / "inputs").mkdir(parents=True)
    with pytest.raises(CaptureError) as ei:
        build_capture_plan(tmp_path, "conventions.yaml#/language", "python")
    assert ei.value.code == CaptureCode.TARGET_FILE_MISSING


def test_value_path_is_in_seeded_allow_list() -> None:
    allowed = default_config().allowed_value_paths()
    assert "conventions.yaml#/data_model.money" in allowed
    assert "conventions.yaml#/language" in allowed


# --- apply_capture: concurrency precondition (R1-S6) + real write -------------------------------


def test_apply_capture_writes_and_preserves_file(tmp_path: Path) -> None:
    root = _project_with_conventions(tmp_path)
    plan = build_capture_plan(root, "conventions.yaml#/data_model.money", "float")
    result = apply_capture(root, plan)
    assert result.code == CaptureCode.OK and result.applied
    on_disk = (root / "docs" / "kickoff" / "inputs" / "conventions.yaml").read_text()
    assert "money: float" in on_disk
    assert "# header comment — must survive" in on_disk  # untouched
    assert "datetime: utc" in on_disk


def test_apply_capture_refuses_stale_file(tmp_path: Path) -> None:
    root = _project_with_conventions(tmp_path)
    plan = build_capture_plan(root, "conventions.yaml#/data_model.money", "float")
    # Simulate a concurrent external edit between plan and apply.
    target = root / "docs" / "kickoff" / "inputs" / "conventions.yaml"
    target.write_text(SAMPLE + "\nextra: changed\n", encoding="utf-8")
    with pytest.raises(CaptureError) as ei:
        apply_capture(root, plan)
    assert ei.value.code == CaptureCode.STALE_FILE
    # The concurrent edit was NOT clobbered.
    assert "extra: changed" in target.read_text()


def _line_text(lines, idx):
    return lines[idx] if idx is not None else None
