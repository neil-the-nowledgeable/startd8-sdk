"""Unit tests for cost_linkage (T2.1 / FR-17 / CRP R1-F5)."""

import json
from contextlib import contextmanager
from types import SimpleNamespace

from startd8.integrations.cost_linkage import (
    attribute_cost,
    cell_cost_rollup,
    cell_costs_from_cells_json,
    cost_tags,
    milestone_cost_rollup,
    rollup_by_prefix,
)


def test_cost_tags_only_provided():
    assert cost_tags(milestone_id="M3") == ["milestone:M3"]
    assert cost_tags(cell_id="abc:cart:opus:r0") == ["cell:abc:cart:opus:r0"]
    assert cost_tags(milestone_id="M3", run_id="abc123") == ["milestone:M3", "run:abc123"]
    assert cost_tags() == []


class _FakeTracker:
    def __init__(self):
        self.project = None
        self.tags = None

    @contextmanager
    def tracking_context(self, project=None, tags=None):
        self.project, self.tags = project, tags
        yield


def test_attribute_cost_threads_tags():
    tracker = _FakeTracker()
    with attribute_cost(tracker, project="startd8-benchmark", milestone_id="M3"):
        pass
    assert tracker.project == "startd8-benchmark"
    assert tracker.tags == ["milestone:M3"]


def test_rollups_from_summary():
    summary = SimpleNamespace(by_tag={
        "milestone:M0": 1.5,
        "milestone:M3": 4.0,
        "cell:abc:cart:opus:r0": 0.12,
        "feature-x": 9.9,  # unrelated tag — excluded
    })
    assert milestone_cost_rollup(summary) == {"M0": 1.5, "M3": 4.0}
    assert cell_cost_rollup(summary) == {"abc:cart:opus:r0": 0.12}
    assert rollup_by_prefix(summary, "run:") == {}


def test_rollup_handles_missing_by_tag():
    assert milestone_cost_rollup(SimpleNamespace()) == {}


def test_cell_costs_from_cells_json(tmp_path):
    cells = [
        {"cell_id": "h:cart:opus:r0", "service": "cart", "model": "opus", "cost_usd": 0.10},
        {"cell_id": "h:cart:opus:r1", "service": "cart", "model": "opus", "cost_usd": 0.20},
        {"cell_id": "h:email:gem:r0", "service": "email", "model": "gem", "cost_usd": 0.05},
        {"cell_id": "h:email:gem:r1", "service": "email", "model": "gem", "cost_usd": None},  # infra_fail $0
    ]
    p = tmp_path / "cells.json"
    p.write_text(json.dumps(cells))
    out = cell_costs_from_cells_json(p)
    assert out["by_service"] == {"cart": 0.30, "email": 0.05}
    assert out["by_model"] == {"opus": 0.30, "gem": 0.05}
    assert out["total"] == 0.35
    assert out["per_cell"]["h:email:gem:r1"] == 0.0  # None cost coerced to 0
