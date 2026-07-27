# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""SDK side of the ContextCore first-class work-item `task.*` carry (REQ-CCL-109).

See `docs/design/WORKITEM_TASK_CARRY_HANDOFF.md`. ContextCore adds first-class WorkItems
as an **additive overlay** under `attributes["contextcore.workitem"]` on the SpanState v2
files the SDK already emits — the carry is consume-only, no emitter change. These tests are
the SDK's part: T1 reader tolerance, T2 emitter-stays-put guard, T3 the canonical fixture
helper (so ContextCore's parity job compares against the *real* emitter shape, not a
hand-authored stand-in), and T4 a task.* semconv parity guard.
"""

from __future__ import annotations

import json

import pytest

from startd8.workflows.builtin.task_tracking_emitter import (
    _SCHEMA_VERSION,
    _TERMINAL_STATUSES,
    emit_canonical_fixture,
)

_TOP_LEVEL_STATUSES = {"OK", "ERROR", "UNSET"}


# ── T3: the canonical fixture helper (the one real cross-repo deliverable) ──────────

def test_canonical_fixture_is_deterministic():
    # ContextCore checks in a golden fixture generated from this; it MUST be byte-stable.
    a = emit_canonical_fixture()
    b = emit_canonical_fixture()
    assert a == b
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_canonical_fixture_is_valid_spanstate_v2():
    fx = emit_canonical_fixture()
    # SpanState v2 invariants ContextCore's reader + overlay depend on (FR-13).
    assert fx["schema_version"] == 2
    assert fx["status"] in _TOP_LEVEL_STATUSES
    attrs = fx["attributes"]
    assert attrs["task.status"] == "in_progress"
    assert attrs["task.type"] == "task"
    assert attrs["task.id"] == fx["task_id"]
    # zero-point task.created event at percent_complete 0 (burndown invariant).
    created = next(e for e in fx["events"] if e["name"] == "task.created")
    assert created["attributes"]["percent_complete"] == 0


def test_canonical_fixture_routes_through_the_real_emitter():
    # It must equal the emitter's own builder output for the frozen inputs — proves it is
    # NOT a hand-authored dict that can silently drift from the emitter (the bug T3 fixes).
    from startd8.workflows.builtin.task_tracking_emitter import (
        _CANONICAL_FIXTURE_INPUTS,
        _build_state_file,
    )

    assert emit_canonical_fixture() == _build_state_file(**_CANONICAL_FIXTURE_INPUTS)


# ── T1: reader tolerates the additive ContextCore overlay ───────────────────────────

def _write_state(project_dir, state: dict) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / f"{state['task_id']}.json").write_text(json.dumps(state), encoding="utf-8")


def test_reader_tolerates_additive_workitem_overlay(tmp_path):
    from startd8.integrations.contextcore import ContextCoreTaskSource

    project = "carry-proj"
    pdir = tmp_path / project

    # baseline: the plain emitter fixture (status forced into the default filter).
    base = emit_canonical_fixture()
    base["attributes"]["task.status"] = "todo"
    _write_state(pdir, base)

    src = ContextCoreTaskSource(project_id=project, state_dir=str(tmp_path))
    before = src.get_task_by_id(base["task_id"])
    before_pending = {t.task_id for t in src.get_pending_tasks()}
    assert before is not None and base["task_id"] in before_pending

    # now overlay the additive ContextCore work-item keys — the reader must be unaffected.
    overlaid = json.loads(json.dumps(base))
    overlaid["attributes"]["contextcore.workitem"] = {
        "version": 7,
        "resolution": "fixed",
        "external_ref": {"system": "github", "id": "42", "url": "https://x/42"},
        "promoted_from": {"kind": "blocker", "id": "blk-9"},
    }
    overlaid["attributes"]["task.resolution"] = "fixed"
    overlaid["attributes"]["task.external_ref.system"] = "github"
    overlaid["attributes"]["task.relation.type"] = "duplicates"
    _write_state(pdir, overlaid)

    src2 = ContextCoreTaskSource(project_id=project, state_dir=str(tmp_path))
    after = src2.get_task_by_id(base["task_id"])
    after_pending = {t.task_id for t in src2.get_pending_tasks()}
    # key-based reads ignore unknown additive keys → identical behavior.
    assert after is not None
    assert after.task_id == before.task_id
    assert after_pending == before_pending


def test_reader_status_filter_unaffected_by_overlay(tmp_path):
    from startd8.integrations.contextcore import ContextCoreTaskSource

    project = "carry-filter"
    pdir = tmp_path / project
    st = emit_canonical_fixture()  # task.status == "in_progress" → NOT in default filter
    st["attributes"]["contextcore.workitem"] = {"resolution": "wontfix"}
    _write_state(pdir, st)

    # default filter {todo, backlog} excludes in_progress — overlay must not change that.
    assert st["task_id"] not in {t.task_id for t in ContextCoreTaskSource(project_id=project, state_dir=str(tmp_path)).get_pending_tasks()}
    # explicit filter including in_progress finds it (overlay still irrelevant).
    src = ContextCoreTaskSource(project_id=project, state_dir=str(tmp_path), status_filter=["in_progress"])
    assert st["task_id"] in {t.task_id for t in src.get_pending_tasks()}


# ── T2: emitter stays put (no schema bump, no closed allowlist) ─────────────────────

def test_schema_version_is_pinned_at_2():
    # Bumping to 3 breaks the ContextCore reader (handoff R4-F6). This guards it.
    assert _SCHEMA_VERSION == 2
    assert emit_canonical_fixture()["schema_version"] == 2


def test_terminal_status_mapping_unchanged():
    assert _TERMINAL_STATUSES == frozenset({"done", "cancelled"})


# ── T4: task.* semconv parity guard (skips when ContextCore absent) ─────────────────

def test_emitted_task_status_and_type_are_known_to_contextcore():
    """The emitter's canonical status/type MUST be members of ContextCore's enums.

    Mirrors tests/unit/observability/test_vocabulary_parity_contextcore.py: an
    optional-dependency cross-repo guard that fails loudly if the vocabularies drift.
    """
    ctypes = pytest.importorskip("contextcore.contracts.types")
    status_values = {s.value for s in ctypes.TaskStatus}
    type_values = {t.value for t in ctypes.TaskType}
    attrs = emit_canonical_fixture()["attributes"]
    assert attrs["task.status"] in status_values, (
        f"emitter task.status {attrs['task.status']!r} not in ContextCore TaskStatus {sorted(status_values)}"
    )
    assert attrs["task.type"] in type_values, (
        f"emitter task.type {attrs['task.type']!r} not in ContextCore TaskType {sorted(type_values)}"
    )
