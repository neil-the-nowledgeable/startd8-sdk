"""Promotion dividend (Tier E) — eligibility, exemplar registry, apply-as-proposals."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from typer.testing import CliRunner

from startd8.cli_concierge import kickoff_kernel_app
from startd8.kickoff_experience.promotion import (
    EXEMPLAR_SCHEMA,
    ExemplarRegistry,
    assemble_exemplar,
    exemplar_id,
    promotion_eligibility,
    settled_conventions,
)

pytestmark = pytest.mark.unit
runner = CliRunner()


def _ready_status(**over):
    base = {
        "project_root": "/tmp/myproj",
        "readiness_percent": 100,
        "attention_counts": {"ok": 3, "review": 0, "blocked": 0, "backlog": 0},
        "field_count": 3,
        "proposals": [],
    }
    base.update(over)
    return base


def test_eligibility_ready_project_is_eligible():
    e = promotion_eligibility(_ready_status())
    assert e.eligible and e.reasons == ()


def test_eligibility_lists_every_blocking_reason():
    e = promotion_eligibility(
        _ready_status(
            readiness_percent=60,
            attention_counts={"ok": 1, "blocked": 2},
            proposals=[{"id": "P-1"}],
        )
    )
    assert not e.eligible
    joined = " ".join(e.reasons)
    assert "60% < target 100%" in joined and "2 blocked" in joined and "1 proposal" in joined


@dataclass
class _F:
    value_path: str
    attention: str
    value: object


@dataclass
class _State:
    fields: list


def test_settled_conventions_takes_ok_valued_fields_sorted():
    state = _State(
        fields=[
            _F("conventions.tz", "ok", "UTC"),
            _F("conventions.locale", "ok", "en-US"),
            _F("data_model.orders", "blocked", None),  # not ok → excluded
            _F("conventions.empty", "ok", None),  # ok but no value → excluded
        ]
    )
    convs = settled_conventions(state)
    assert convs == [
        {"value_path": "conventions.locale", "value": "en-US"},
        {"value_path": "conventions.tz", "value": "UTC"},
    ]


def test_exemplar_id_is_content_deterministic():
    convs = [{"value_path": "a", "value": "1"}]
    assert exemplar_id("MyProj", convs) == exemplar_id("MyProj", convs)
    assert exemplar_id("MyProj", convs).startswith("myproj-")
    assert exemplar_id("MyProj", convs) != exemplar_id("MyProj", [{"value_path": "a", "value": "2"}])


def test_assemble_exemplar_shape():
    convs = [{"value_path": "conventions.tz", "value": "UTC"}]
    ex = assemble_exemplar(_ready_status(), convs, {"adjudicated": 2, "counts": {"ACCEPT": 2}}, generated_at="t")
    assert ex["schema"] == EXEMPLAR_SCHEMA and ex["convention_count"] == 1
    assert ex["source_project"] == "myproj" and ex["decisions"]["adjudicated"] == 2
    json.dumps(ex)


def test_registry_save_get_list_roundtrip(tmp_path):
    reg = ExemplarRegistry(root=tmp_path)
    ex = assemble_exemplar(_ready_status(), [{"value_path": "a", "value": "1"}], {}, generated_at="t")
    path = reg.save(ex)
    assert path.exists()
    assert reg.get(ex["id"])["id"] == ex["id"]
    assert [e["id"] for e in reg.list()] == [ex["id"]]


def test_promote_cli_gate_and_registry(tmp_path, monkeypatch):
    # not-ready project → refused with reasons (exit 3)
    monkeypatch.setenv("STARTD8_KICKOFF_EXEMPLARS_DIR", str(tmp_path / "reg"))
    out = runner.invoke(kickoff_kernel_app, ["promote", str(tmp_path)])
    assert out.exit_code == 3 and "not promoted" in out.output
    # empty registry lists nothing
    lst = runner.invoke(kickoff_kernel_app, ["exemplars"])
    assert "No exemplars yet" in lst.output


def test_apply_exemplar_unknown_id(tmp_path, monkeypatch):
    monkeypatch.setenv("STARTD8_KICKOFF_EXEMPLARS_DIR", str(tmp_path / "reg"))
    out = runner.invoke(kickoff_kernel_app, ["apply-exemplar", "nope-000000000000", str(tmp_path)])
    assert out.exit_code == 2 and "no such exemplar" in out.output


def test_apply_plan_skips_target_incompatible_conventions(tmp_path):
    from startd8.kickoff_experience.promotion import apply_plan

    ex = {"id": "x", "conventions": [{"value_path": "nonexistent.path.xyz", "value": "v"}]}
    plan = apply_plan(ex, tmp_path)  # empty project → the path isn't allowed → skipped, not crash
    assert plan["applicable_count"] == 0 and plan["skipped_count"] == 1
    assert plan["skipped"][0]["value_path"] == "nonexistent.path.xyz"


def test_emit_to_inbox_no_applicable_writes_nothing(tmp_path):
    from startd8.kickoff_experience.promotion import emit_to_inbox

    ex = {"id": "x", "conventions": [{"value_path": "nonexistent.path.xyz", "value": "v"}]}
    res = emit_to_inbox(ex, tmp_path)  # nothing applicable → no inbox write, honest report
    assert res["emitted"] is False and res["seeded"] == [] and res["skipped"]
    assert not (tmp_path / ".startd8" / "vipp" / "proposals-inbox.json").exists()
