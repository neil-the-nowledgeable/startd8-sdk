"""Tests for the Concierge write-action builders (FR-C3a/C7/C9) + round-trip via the safe-writer."""

from __future__ import annotations

import json

import pytest

from startd8.concierge.safe_write import apply_write_plan
from startd8.concierge.writes import (
    FRICTION_LOG,
    ConciergeWriteError,
    build_friction_entry,
    build_instantiate_plan,
    to_planned_writes,
)


# ── instantiate-kickoff (FR-C7) ──────────────────────────────────────────────

def test_instantiate_plans_kickoff_package(tmp_path):
    plan = build_instantiate_plan(tmp_path, "prototype")
    dests = {w["path"] for w in plan["writes"]}
    assert "docs/kickoff/KICKOFF_INTRO.md" in dests
    assert "docs/kickoff/inputs/conventions.yaml" in dests
    assert all(w["action"] == "new" and w["status"] == "new" for w in plan["writes"])
    assert plan["posture"] == "prototype"


def test_posture_renders_conventions_provenance(tmp_path):
    proto = build_instantiate_plan(tmp_path, "prototype")
    prod = build_instantiate_plan(tmp_path, "production")
    conv_proto = next(w["content"] for w in proto["writes"] if w["path"].endswith("conventions.yaml"))
    conv_prod = next(w["content"] for w in prod["writes"] if w["path"].endswith("conventions.yaml"))
    assert "provenance_default: templated" in conv_proto
    assert "provenance_default: authored" in conv_prod
    assert "<authored | templated>" not in conv_proto  # placeholder resolved


def test_production_warns_about_owners(tmp_path):
    plan = build_instantiate_plan(tmp_path, "production")
    assert any("owners" in w for w in plan["warnings"])


def test_with_authoring_adds_trio(tmp_path):
    base = build_instantiate_plan(tmp_path, "prototype")
    extended = build_instantiate_plan(tmp_path, "prototype", with_authoring=True)
    assert len(extended["writes"]) > len(base["writes"])
    assert any(w["path"].endswith("REQUIREMENTS_TEMPLATE.md") for w in extended["writes"])


def test_bad_posture_rejected(tmp_path):
    with pytest.raises(ConciergeWriteError):
        build_instantiate_plan(tmp_path, "banana")


def test_existing_file_marked_exists_not_new(tmp_path):
    (tmp_path / "docs" / "kickoff").mkdir(parents=True)
    (tmp_path / "docs" / "kickoff" / "KICKOFF_INTRO.md").write_text("already here", encoding="utf-8")
    plan = build_instantiate_plan(tmp_path, "prototype")
    intro = next(w for w in plan["writes"] if w["path"].endswith("KICKOFF_INTRO.md"))
    assert intro["status"] == "exists"


# ── FR-C3a — disclosure bound (the live OQ-7 leak) ───────────────────────────

def test_plan_never_contains_existing_file_content(tmp_path):
    """A pre-existing target with secret content must not leak into the plan (stat-only)."""
    secret = "SUPER-SECRET-API-KEY-9f3a"
    p = tmp_path / "docs" / "kickoff" / "inputs"
    p.mkdir(parents=True)
    (p / "conventions.yaml").write_text(f"stolen: {secret}\n", encoding="utf-8")
    plan = build_instantiate_plan(tmp_path, "prototype")
    blob = json.dumps(plan)
    assert secret not in blob  # builder stat'd, never read the existing file


# ── log-friction (FR-C9) ─────────────────────────────────────────────────────

def test_friction_entry_is_one_jsonl_line(tmp_path):
    plan = build_friction_entry(
        tmp_path, friction="F", what_happened="W", implication="I",
        entry_id="fixed123", timestamp="2026-06-15T00:00:00Z",
    )
    w = plan["writes"][0]
    assert w["path"] == FRICTION_LOG and w["action"] == "append"
    line = w["append_text"]
    assert line.endswith("\n")
    obj = json.loads(line)
    assert obj == {"id": "fixed123", "ts": "2026-06-15T00:00:00Z", "friction": "F",
                   "what_happened": "W", "implication": "I"}


def test_friction_requires_fields(tmp_path):
    with pytest.raises(ConciergeWriteError):
        build_friction_entry(tmp_path, friction="", what_happened="W", implication="I")


def test_friction_id_is_unique_without_reading_log(tmp_path):
    (tmp_path / FRICTION_LOG).write_text('{"id":"old"}\n', encoding="utf-8")
    a = build_friction_entry(tmp_path, friction="a", what_happened="a", implication="a")
    b = build_friction_entry(tmp_path, friction="b", what_happened="b", implication="b")
    ida = json.loads(a["writes"][0]["append_text"])["id"]
    idb = json.loads(b["writes"][0]["append_text"])["id"]
    assert ida != idb  # no parse-to-increment; ids are self-contained
    assert a["writes"][0]["status"] == "exists"  # log present ⇒ append to it


# ── round-trip: builder → safe-writer actually writes correctly ──────────────

def test_instantiate_roundtrip_writes_files(tmp_path):
    plan = build_instantiate_plan(tmp_path, "prototype")
    res = apply_write_plan(tmp_path, to_planned_writes(plan))
    assert not res.blocked and not res.errors
    assert (tmp_path / "docs" / "kickoff" / "KICKOFF_INTRO.md").is_file()
    assert (tmp_path / "docs" / "kickoff" / "inputs" / "conventions.yaml").is_file()
    # re-apply is idempotent: all skipped (exist), nothing rewritten
    res2 = apply_write_plan(tmp_path, to_planned_writes(plan))
    assert res2.written == [] and len(res2.skipped) == len(plan["writes"])


def test_friction_roundtrip_appends(tmp_path):
    for i in range(2):
        plan = build_friction_entry(tmp_path, friction=f"f{i}", what_happened="w", implication="i")
        res = apply_write_plan(tmp_path, to_planned_writes(plan))
        assert (tmp_path / FRICTION_LOG).name in [w for w in res.written]
    lines = (tmp_path / FRICTION_LOG).read_text().splitlines()
    assert len(lines) == 2 and all(json.loads(line) for line in lines)


# ── Step 0 anti-fork: packaged templates == canonical docs tree ──────────────

def test_packaged_templates_match_canonical():
    from importlib import resources
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    canonical = repo_root / "docs" / "design" / "kickoff" / "templates"
    packaged = resources.files("startd8.concierge_templates")
    for f in canonical.rglob("*"):
        if f.is_dir() or "__pycache__" in f.parts:
            continue
        rel = f.relative_to(canonical).as_posix()
        assert (packaged / rel).read_text(encoding="utf-8") == f.read_text(encoding="utf-8"), (
            f"packaged template diverged from canonical: {rel}"
        )


# ── dispatch: write actions return a PREVIEW and never touch disk (OQ-7) ──────

def test_handle_dispatch_instantiate_is_preview_only(tmp_path):
    from startd8.concierge import handle_concierge_tool

    before = sorted(p.name for p in tmp_path.rglob("*"))
    plan = handle_concierge_tool("instantiate-kickoff", tmp_path, posture="prototype")
    after = sorted(p.name for p in tmp_path.rglob("*"))
    assert plan["action"] == "instantiate-kickoff" and plan["writes"]
    assert before == after  # handle_concierge_tool wrote nothing — preview only


def test_handle_dispatch_logfriction_requires_fields(tmp_path):
    from startd8.concierge import ConciergeError, handle_concierge_tool

    with pytest.raises(ConciergeError):
        handle_concierge_tool("log-friction", tmp_path)  # missing required fields
