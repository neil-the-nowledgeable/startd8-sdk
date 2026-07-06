"""Red Carpet Treatment N3 — the conductor's stage model (FR-RCT-2 / FR-RCT-10).

The stage state is a pure, read-only projection of build_assess + the on-disk manifests: it names the
next gap and gates the cascade offer on the R1-F7 predicate (schema + app + ≥1 page + ≥1 view). The
filesystem is the single source of truth, so the state is resumable by construction.
"""

from __future__ import annotations

from pathlib import Path

from startd8.kickoff_experience.proposals import ProposedAction, apply_proposal
from startd8.kickoff_experience.red_carpet import (
    STAGES,
    build_red_carpet_state,
)

_BRIEF = """## Entities

### Customer
A person.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| name | text | yes | |
"""

_PAGES = """## Pages

| Page | Purpose | Content file |
|------|---------|--------------|
| Home | the landing page | home.md |
"""

_VIEWS = """## Views

### View: Dashboard
- Kind: dashboard
- Root: Customer
- Shows: Customer counts
"""


def test_empty_project_is_at_data_model_with_no_cascade(tmp_path: Path) -> None:
    state = build_red_carpet_state(tmp_path)
    assert [s.key for s in state.stages] == list(STAGES)
    assert state.next_stage == "data_model"            # nothing built yet → start at the front bookend
    assert state.cascade_offerable is False
    assert "schema" in state.unmet_gates and "views" in state.unmet_gates


def test_data_model_stage_advances_after_schema_promote(tmp_path: Path) -> None:
    assert apply_proposal(tmp_path, ProposedAction("schema", {"brief": _BRIEF}, id="s1")).ok
    state = build_red_carpet_state(tmp_path)
    dm = next(s for s in state.stages if s.key == "data_model")
    assert dm.status == "done"                          # schema.prisma now present
    assert state.next_stage != "data_model"             # advanced past the front bookend
    assert "schema" not in state.unmet_gates


def test_cascade_offerable_only_with_the_full_minimal_subset(tmp_path: Path) -> None:
    # schema + app + pages + views (the R1-F7 predicate). Build them via the proposal kinds.
    assert apply_proposal(tmp_path, ProposedAction("schema", {"brief": _BRIEF}, id="s1")).ok
    assert not build_red_carpet_state(tmp_path).cascade_offerable   # only schema so far
    (tmp_path / "app.yaml").write_text('app:\n  name: demo\n  package: app\npersistence:\n  path: ./data/demo.db\ncontainer:\n  dockerfile: true\n')      # app manifest
    assert apply_proposal(tmp_path, ProposedAction("manifest", {"source": _PAGES}, id="m1")).ok
    assert not build_red_carpet_state(tmp_path).cascade_offerable   # still no views
    assert apply_proposal(tmp_path, ProposedAction("manifest", {"source": _VIEWS}, id="m2")).ok
    state = build_red_carpet_state(tmp_path)
    assert state.cascade_offerable is True and state.unmet_gates == ()
    assert state.next_stage in (None, "value_inputs", "content")   # past the gating manifests


def test_state_is_recomputed_from_filesystem(tmp_path: Path) -> None:
    # Resumability/R1-F6: no stale cursor — deleting a manifest moves the gap back on the next read.
    (tmp_path / "app.yaml").write_text('app:\n  name: demo\n  package: app\npersistence:\n  path: ./data/demo.db\ncontainer:\n  dockerfile: true\n')
    assert apply_proposal(tmp_path, ProposedAction("schema", {"brief": _BRIEF}, id="s1")).ok
    assert build_red_carpet_state(tmp_path).unmet_gates  # pages/views still missing
    (tmp_path / "prisma" / "schema.prisma").unlink()
    assert "schema" in build_red_carpet_state(tmp_path).unmet_gates  # reconciled to live state


def test_cli_red_carpet_json(tmp_path: Path) -> None:
    import pytest

    typer_testing = pytest.importorskip("typer.testing")
    from startd8.cli_kickoff import kickoff_app

    runner = typer_testing.CliRunner()
    result = runner.invoke(kickoff_app, ["red-carpet", str(tmp_path), "--json"])
    assert result.exit_code == 0
    import json
    payload = json.loads(result.stdout)
    assert payload["next_stage"] == "data_model" and payload["cascade_offerable"] is False


def test_invalid_manifest_is_not_offerable(tmp_path: Path) -> None:
    """FR-A1: a manifest that is PRESENT but INVALID must NOT count as a met gate — the guide must
    not offer to build over a broken contract (the old file-existence gate did)."""
    assert apply_proposal(tmp_path, ProposedAction("schema", {"brief": _BRIEF}, id="s1")).ok
    assert apply_proposal(tmp_path, ProposedAction("manifest", {"source": _PAGES}, id="m1")).ok
    assert apply_proposal(tmp_path, ProposedAction("manifest", {"source": _VIEWS}, id="m2")).ok
    # a present-but-invalid app.yaml (wrong top-level schema) — file exists, but generation would fail
    (tmp_path / "app.yaml").write_text("package_name: demo\n")
    state = build_red_carpet_state(tmp_path)
    assert not state.cascade_offerable
    assert "app" in state.unmet_gates
