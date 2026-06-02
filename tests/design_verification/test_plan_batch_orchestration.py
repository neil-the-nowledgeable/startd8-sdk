"""Baseline characterization for Plan Batch Orchestration (Increment 0).

This is the ``t-baseline-characterization`` task from
``docs/design/PLAN_BATCH_ORCHESTRATION_PLAN.md`` (R3 Part 4, v1.2). It pins the
behaviors the batch-orchestration MVP relies on, so that any drift in the
underlying SDK primitives fails loudly in CI *before* the orchestrator is built
on top of them.

It also encodes the R4 behavioral verification (requirements v0.4): the
checkpoint-v4 ``wave_*`` fields are a PHANTOM — documented and migration-populated
but stripped by the loader's ``known_fields`` filter before the dataclass is
constructed, so they never reach disk. ``test_workflow_checkpoint_*`` pins that
fact: if someone adds the ``wave_*`` fields to the dataclass, these tests flip,
forcing a conscious decision rather than a silent reactivation of the dormant
parallel path.

Why this exists (R3-F3 / Forward-Manifest precedent): a ``file.py:NNN`` citation
in a design doc decays or is wrong from day one. Cited load-bearing behavior must
be pinned by a test, not trusted on faith.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import pytest

from startd8.contractors.artisan_contractor import (
    JsonFileCheckpointStore,
    WorkflowCheckpoint,
    compute_lanes,
)
from startd8.contractors.batch_postmortem import (
    compute_seed_checksum,
    derive_batch_id,
    load_or_create_ledger,
    save_ledger,
)
from startd8.contractors.context_seed.shared import _topological_sort

pytestmark = pytest.mark.unit


# --- minimal duck-typed task ------------------------------------------------
# _topological_sort and compute_lanes only access .task_id / .depends_on /
# .target_files, so a real (32-field) SeedTask is unnecessary here.
@dataclass
class _T:
    task_id: str
    depends_on: list[str] = field(default_factory=list)
    target_files: list[str] = field(default_factory=list)


# --- _topological_sort (ordering primitive) ---------------------------------
def test_topological_sort_orders_dependencies_before_dependents():
    tasks = [
        _T("C", depends_on=["B"]),
        _T("A", depends_on=[]),
        _T("B", depends_on=["A"]),
    ]
    ordered = [t.task_id for t in _topological_sort(tasks)]
    assert ordered.index("A") < ordered.index("B") < ordered.index("C")


def test_topological_sort_falls_back_to_input_order_on_cycle():
    # A -> B -> A is a cycle; the documented contract is: log + return input
    # order (never raise). The batch orchestrator depends on this no-raise
    # fallback so a bad seed cannot abort partitioning.
    tasks = [_T("A", depends_on=["B"]), _T("B", depends_on=["A"])]
    ordered = _topological_sort(tasks)
    assert [t.task_id for t in ordered] == ["A", "B"]


# --- compute_lanes (file-cohesion primitive) --------------------------------
def test_compute_lanes_unions_tasks_sharing_target_files():
    tasks = [
        _T("A", target_files=["lib/util.ts"]),
        _T("B", target_files=["lib/util.ts"]),  # shares a file with A
        _T("C", target_files=["app/page.tsx"]),  # independent
    ]
    lanes = compute_lanes(tasks)
    lane_of = {t.task_id: i for i, lane in enumerate(lanes) for t in lane}
    assert lane_of["A"] == lane_of["B"]
    assert lane_of["C"] != lane_of["A"]


def test_compute_lanes_unions_on_depends_on_even_without_shared_files():
    # compute_lanes folds depends_on into the union-find, so a dependent pair
    # is one lane even with disjoint target_files.
    tasks = [
        _T("A", target_files=["a.ts"]),
        _T("B", target_files=["b.ts"], depends_on=["A"]),
    ]
    lanes = compute_lanes(tasks)
    lane_of = {t.task_id: i for i, lane in enumerate(lanes) for t in lane}
    assert lane_of["A"] == lane_of["B"]


# --- WorkflowCheckpoint: pin the field set + the wave_* phantom --------------
_EXPECTED_CHECKPOINT_FIELDS = {
    "workflow_id",
    "last_completed_phase",
    "phase_results",
    "cumulative_cost",
    "timestamp",
    "status",
    "metadata",
    "context_snapshot",
    "schema_version",
    "completed_features",
    "current_feature",
    "current_feature_phase",
    "feature_partial_results",
}

_PHANTOM_WAVE_FIELDS = {
    "wave_assignments",
    "completed_waves",
    "current_wave",
    "wave_resume_count",
}


def test_workflow_checkpoint_field_set_is_pinned():
    actual = {f.name for f in fields(WorkflowCheckpoint)}
    assert actual == _EXPECTED_CHECKPOINT_FIELDS, (
        "WorkflowCheckpoint schema changed. If wave_* fields were added to "
        "persist cross-batch state, STOP: the batch orchestrator deliberately "
        "uses BatchLedger (batch_postmortem.py), not checkpoint-v4. Update the "
        "design docs (requirements R4) before changing this set."
    )
    # The documented-but-phantom v4 wave_* fields must NOT be on the dataclass.
    assert not (_PHANTOM_WAVE_FIELDS & actual), (
        "checkpoint-v4 wave_* fields are documented but were verified to never "
        "reach disk (loader strips them). They must not silently become real."
    )


def test_workflow_checkpoint_round_trips_all_fields(tmp_path):
    store = JsonFileCheckpointStore(str(tmp_path))
    ckpt = WorkflowCheckpoint(
        workflow_id="wf-batch-test",
        last_completed_phase="IMPLEMENT",
        phase_results=[{"phase": "DESIGN", "ok": True}],
        cumulative_cost=1.23,
        timestamp="2026-05-31T00:00:00",
        status="OK",
        metadata={"k": "v"},
        context_snapshot={"seed": "x"},
        schema_version=4,
        completed_features=["PI-001", "PI-002"],
        current_feature="PI-003",
        current_feature_phase="TEST",
        feature_partial_results={"PI-003": {"draft": "..."}},
    )
    store.save(ckpt)
    loaded = store.load("wf-batch-test")
    assert loaded is not None
    assert asdict(loaded) == asdict(ckpt)


def test_checkpoint_loader_strips_phantom_wave_fields(tmp_path):
    # Inject the phantom wave_* keys into a checkpoint file and confirm the
    # loader silently strips them (known_fields filter) rather than carrying
    # them — the exact behavior that makes checkpoint-v4 unusable for the
    # batch ledger and forced the fresh-artifact decision (R3-S1/R3-S2).
    store = JsonFileCheckpointStore(str(tmp_path))
    ckpt = WorkflowCheckpoint(
        workflow_id="wf-phantom",
        last_completed_phase=None,
        phase_results=[],
        cumulative_cost=0.0,
        timestamp="2026-05-31T00:00:00",
        status="OK",
    )
    store.save(ckpt)
    path = next(tmp_path.glob("wf-phantom*.json"))
    data = json.loads(path.read_text())
    data.update(
        {
            "wave_assignments": {"PI-001": 0},
            "completed_waves": [0, 1],
            "current_wave": 1,
            "wave_resume_count": {"0": 2},
        }
    )
    path.write_text(json.dumps(data))

    loaded = store.load("wf-phantom")
    assert loaded is not None
    for phantom in _PHANTOM_WAVE_FIELDS:
        assert not hasattr(loaded, phantom)


# --- BatchLedger: the artifact the orchestrator resumes off of --------------
def test_batch_ledger_round_trips_and_pins_on_seed_hash(tmp_path):
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps({"tasks": [{"task_id": "PI-001"}]}))
    ledger_path = tmp_path / "batch-ledger.json"

    checksum = compute_seed_checksum(str(seed))
    ledger = load_or_create_ledger(str(ledger_path), str(seed), checksum, total_tasks=1)
    assert ledger.batch_id == derive_batch_id(checksum)
    assert ledger.seed_checksum == checksum
    save_ledger(ledger, str(ledger_path))

    # Same seed -> same ledger reloaded (resume reuses the pinned partition).
    reloaded = load_or_create_ledger(str(ledger_path), str(seed), checksum, 1)
    assert reloaded.batch_id == ledger.batch_id

    # Changed seed -> a NEW batch id (FR-12: fail-loud / re-key on seed change).
    seed.write_text(json.dumps({"tasks": [{"task_id": "PI-001"}, {"task_id": "PI-002"}]}))
    new_checksum = compute_seed_checksum(str(seed))
    assert new_checksum != checksum
    new_ledger = load_or_create_ledger(str(ledger_path), str(seed), new_checksum, 2)
    assert new_ledger.batch_id != ledger.batch_id


# --- R3-F3: cited .py:NNN paths in the design docs must exist ---------------
_DESIGN_DOCS = [
    "docs/design/PLAN_BATCH_ORCHESTRATION_REQUIREMENTS.md",
    "docs/design/PLAN_BATCH_ORCHESTRATION_PLAN.md",
]
_CITE_RE = re.compile(r"\b([A-Za-z_][\w./-]*\.py):\d+")


def _repo_root() -> Path:
    # tests/design_verification/<this file> -> repo root is two parents up.
    return Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("doc_rel", _DESIGN_DOCS)
def test_design_doc_code_citations_reference_existing_files(doc_rel):
    root = _repo_root()
    doc = root / doc_rel
    if not doc.is_file():
        pytest.skip(f"{doc_rel} not present")
    cited = {m.group(1) for m in _CITE_RE.finditer(doc.read_text(encoding="utf-8"))}
    # Resolve each cited .py basename under the repo's code roots (catches a
    # file renamed/deleted out from under a load-bearing citation). Both src/
    # (package) and scripts/ (runners) are cited in these docs.
    code_roots = [root / "src", root / "scripts"]
    missing = sorted(
        name
        for name in cited
        if not any(list(r.rglob(Path(name).name)) for r in code_roots if r.is_dir())
    )
    assert not missing, (
        f"{doc_rel} cites .py files that no longer exist under src/: {missing}. "
        "Update the citation or the doc (R3-F3 verification protocol)."
    )
