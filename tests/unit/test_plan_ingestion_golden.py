"""Golden-artifact characterization test for ``PlanIngestionWorkflow._execute``.

Stage-0 safety net for the `_execute` decomposition (docs/design/plan-ingestion-refactor/PLAN.md).
`_execute` is a 1,176-line orchestrator whose decomposition (introducing a run-context object,
converting the cost-cap / _fail closures to methods, extracting per-phase glue) is behavior-adjacent,
not a byte-move. This test pins the *observable output* of a fully-deterministic run — a v0.1-format
plan that drives the whole pipeline with **zero LLM calls** — so any decomposition that changes the
emitted artifacts (seed, tasks, state, traceability, review-config) fails loudly.

Normalization strips volatile fields (absolute paths, timestamps, durations, ms timings) so the golden
is stable across machines/runs while still catching behavioral drift. To (re)generate the golden after
an *intended* change, run:  STARTD8_REGEN_GOLDEN=1 pytest tests/unit/test_plan_ingestion_golden.py
"""

from __future__ import annotations

import json
import os
import re
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from startd8.workflows.builtin.plan_ingestion_workflow import PlanIngestionWorkflow

GOLDEN = Path(__file__).parent / "golden" / "plan_ingestion_v01_golden.json"

V01_PLAN = textwrap.dedent("""\
    # Deterministic Parse Test Plan

    | Feature | FRs | Target files | Est. LOC |
    |---------|-----|--------------|----------|
    | F-001 alpha module | FR-1 | src/alpha.py | 50 |
    | F-002 beta module | FR-2 | src/beta.py | 60 |
    | F-003 gamma module | FR-3 | src/gamma.py | 70 |

    ## Dependencies

    - F-002 after F-001
    """)

# JSON/YAML artifacts whose content carries behavioral meaning. The .md reports are
# checked for presence only (they are human-facing renderings of the same data).
SNAPSHOT_FILES = [
    ".startd8/plan_ingestion_state.json",
    "ingestion-traceability.json",
    "manifest-extraction-report.json",
    "plan-ingestion-diagnostic.json",
    "plan-ingestion-tasks.yaml",
    "prime-context-seed.json",
    "review-config.json",
]
PRESENCE_ONLY = [
    "manifest-extraction-report.md",
    "plan-ingestion-tasks-review.md",
]

# --- Failure path (R1-S6): a deterministic quality-gate _fail. The forensics ledger
# it writes is exactly the cross-phase state Stage 2/4 rethread, and is otherwise
# uncharacterized. Requirements that no plan feature satisfies + fail policy trip the gate.
GOLDEN_FAIL = Path(__file__).parent / "golden" / "plan_ingestion_v01_fail_golden.json"
REQS_UNSATISFIABLE = (
    "# Reqs\n\n| ID | Requirement |\n|---|---|\n"
    "| REQ-ZZZ-001 | unmatched one |\n"
    "| REQ-ZZZ-002 | unmatched two |\n"
)
FAIL_SNAPSHOT_FILES = [
    ".startd8/plan_ingestion_state.json",
    "plan-ingestion-failure-forensics.json",
]

# Keys whose values are volatile and must be blanked:
#  - timestamps / durations
#  - content hashes (derived from files that embed absolute paths, so machine-dependent;
#    the underlying files' *meaningful* content is compared directly via SNAPSHOT_FILES)
_VOLATILE_KEY = re.compile(
    r"(timestamp|created|_at$|generated|duration|elapsed|_ms$|started|finished|"
    r"time_ms|wall|latency|sha256|sha1|_hash$|digest|checksum)",
    re.IGNORECASE,
)


def _scrub_paths(s: str, prefixes: list[str]) -> str:
    """Replace every machine-specific path prefix (and its /private-resolved twin) + timestamps."""
    for pre in prefixes:
        s = s.replace(pre, "<OUTDIR>")
    s = re.sub(r"\d{4}-\d{2}-\d{2}T[\d:.+\-]+", "<TS>", s)
    return s


def _normalize(obj, prefixes: list[str]):
    """Recursively blank volatile fields + scrub machine-specific paths in both keys and values."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            key = _scrub_paths(str(k), prefixes)  # paths also appear AS keys (e.g. source_docs)
            out[key] = "<VOLATILE>" if _VOLATILE_KEY.search(str(k)) else _normalize(v, prefixes)
        return out
    if isinstance(obj, list):
        return [_normalize(v, prefixes) for v in obj]
    if isinstance(obj, str):
        return _scrub_paths(obj, prefixes)
    return obj


def _path_prefixes(*dirs: str) -> list[str]:
    """Each dir plus its realpath twin (macOS /var ↔ /private/var), longest-first for greedy match."""
    seen: list[str] = []
    for d in dirs:
        for form in (os.path.realpath(d), d):
            if form and form not in seen:
                seen.append(form)
    return sorted(seen, key=len, reverse=True)


def _snapshot(outdir: Path, repo: str, files: list[str] = SNAPSHOT_FILES) -> dict:
    prefixes = _path_prefixes(str(outdir), repo)
    snap: dict = {}
    for rel in files:
        p = outdir / rel
        if not p.exists():
            snap[rel] = "<MISSING>"
            continue
        text = p.read_text(encoding="utf-8")
        if p.suffix == ".json":
            snap[rel] = _normalize(json.loads(text), prefixes)
        else:  # .yaml — normalize as text
            snap[rel] = _scrub_paths(text, prefixes)
    return snap


def _run(tmp_path: Path):
    (tmp_path / "plan.md").write_text(V01_PLAN)
    agent = MagicMock()
    agent.name, agent.model, agent.max_tokens = "test-agent", "mock-model", 4096
    agent.generate.side_effect = Exception("LLM should not be needed")
    with patch(
        "startd8.workflows.builtin.plan_ingestion_workflow.resolve_agent_spec",
        return_value=agent,
    ):
        result = PlanIngestionWorkflow().run({
            "plan_path": str(tmp_path / "plan.md"),
            "output_dir": str(tmp_path),
            "review_rounds": 0,
        })
    return result, agent


def test_v01_run_is_deterministic_and_zero_llm(tmp_path: Path):
    """The whole pipeline runs to success with NO LLM call (the deterministic invariant)."""
    result, agent = _run(tmp_path)
    assert result.success is True
    agent.generate.assert_not_called()
    # every snapshot artifact was actually written
    for rel in SNAPSHOT_FILES + PRESENCE_ONLY:
        assert (tmp_path / rel).exists(), f"expected artifact missing: {rel}"


def test_v01_artifacts_match_golden(tmp_path: Path):
    """The emitted artifacts match the committed golden (behavior-preservation gate)."""
    result, _ = _run(tmp_path)
    assert result.success is True
    repo = str(Path(__file__).resolve().parents[2])
    snap = _snapshot(tmp_path, repo)

    if os.environ.get("STARTD8_REGEN_GOLDEN"):
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(snap, indent=2, sort_keys=True), encoding="utf-8")
        pytest.skip("regenerated golden")

    assert GOLDEN.exists(), (
        "golden missing — seed it with STARTD8_REGEN_GOLDEN=1 pytest "
        "tests/unit/test_plan_ingestion_golden.py"
    )
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    # compare per-file so a diff points at the drifted artifact
    assert set(snap) == set(expected), "artifact SET changed vs golden"
    for rel in sorted(expected):
        assert snap[rel] == expected[rel], f"artifact drifted vs golden: {rel}"


def _run_failing_gate(tmp_path: Path):
    """Trip the translation-quality gate deterministically (zero LLM) → _fail path."""
    (tmp_path / "plan.md").write_text(V01_PLAN)
    (tmp_path / "reqs.md").write_text(REQS_UNSATISFIABLE)
    agent = MagicMock()
    agent.name, agent.model, agent.max_tokens = "test-agent", "mock-model", 4096
    agent.generate.side_effect = Exception("LLM should not be needed")
    with patch(
        "startd8.workflows.builtin.plan_ingestion_workflow.resolve_agent_spec",
        return_value=agent,
    ):
        result = PlanIngestionWorkflow().run({
            "plan_path": str(tmp_path / "plan.md"),
            "requirements_path": str(tmp_path / "reqs.md"),
            "output_dir": str(tmp_path),
            "review_rounds": 0,
            "low_quality_policy": "fail",
            "min_requirements_coverage": 99.0,
            "max_contract_conflicts": 0,
        })
    return result, agent


def test_forced_fail_is_deterministic_and_zero_llm(tmp_path: Path):
    """The quality-gate _fail path runs deterministically with NO LLM call and writes forensics."""
    result, agent = _run_failing_gate(tmp_path)
    assert result.success is False
    agent.generate.assert_not_called()
    for rel in FAIL_SNAPSHOT_FILES:
        assert (tmp_path / rel).exists(), f"expected _fail artifact missing: {rel}"


def test_forced_fail_forensics_match_golden(tmp_path: Path):
    """The _fail-path artifacts (forensics + FAILED state) match the committed golden.

    R1-S6 (CRP): Stage 2/4 rethread the `_forensics` ledger + `_fail`/`_save_state` closures —
    this pins that path before those stages, closing the gap the success-only golden left.
    """
    result, _ = _run_failing_gate(tmp_path)
    assert result.success is False
    repo = str(Path(__file__).resolve().parents[2])
    snap = _snapshot(tmp_path, repo, files=FAIL_SNAPSHOT_FILES)

    if os.environ.get("STARTD8_REGEN_GOLDEN"):
        GOLDEN_FAIL.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_FAIL.write_text(json.dumps(snap, indent=2, sort_keys=True), encoding="utf-8")
        pytest.skip("regenerated fail golden")

    assert GOLDEN_FAIL.exists(), (
        "fail golden missing — seed it with STARTD8_REGEN_GOLDEN=1 pytest "
        "tests/unit/test_plan_ingestion_golden.py"
    )
    expected = json.loads(GOLDEN_FAIL.read_text(encoding="utf-8"))
    assert set(snap) == set(expected), "_fail artifact SET changed vs golden"
    for rel in sorted(expected):
        assert snap[rel] == expected[rel], f"_fail artifact drifted vs golden: {rel}"
