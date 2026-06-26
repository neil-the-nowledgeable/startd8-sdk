"""M2 — readiness surface wrapper + performance budgets."""

from __future__ import annotations

import textwrap
from pathlib import Path

from startd8.kickoff_experience import PerfSample, ReadinessView, build_readiness


SYNTH_ASSESS = {
    "schema_version": 1,
    "action": "assess",
    "project_root": "/x",
    "kickoff_inputs": {
        "inputs_dir": "docs/kickoff/inputs",
        "domains": {
            "business-targets": {"status": "present", "provenance_default": "authored"},
            "observability": {"status": "absent"},
        },
    },
    "cascade": {
        "status": "ok",
        "readiness": 0.5,
        "status_counts": {"defined": 3, "not_defined": 2},
        "blockers": [{"section": "Data model", "status": "not_defined", "consequence": "no build"}],
    },
}


def test_from_assess_projects_the_few_rendered_fields() -> None:
    rv = ReadinessView.from_assess(SYNTH_ASSESS)
    assert rv.readiness == 0.5
    assert rv.cascade_status == "ok"
    assert rv.status_counts == {"defined": 3, "not_defined": 2}
    assert len(rv.blockers) == 1
    assert rv.input_domains["business-targets"]["provenance_default"] == "authored"
    assert rv.input_domains["observability"]["status"] == "absent"


def test_from_assess_handles_inputs_error() -> None:
    rv = ReadinessView.from_assess(
        {"cascade": {"status": "inputs_error", "error": "bad inventory"}, "kickoff_inputs": {}}
    )
    assert rv.cascade_status == "inputs_error"
    assert rv.readiness is None
    assert rv.error == "bad inventory"


def test_to_dict_is_stable_and_sorted() -> None:
    a = ReadinessView.from_assess(SYNTH_ASSESS).to_dict()
    b = ReadinessView.from_assess(SYNTH_ASSESS).to_dict()
    assert a == b
    assert list(a["input_domains"]) == sorted(a["input_domains"])


def test_perf_sample_over_budget_flag() -> None:
    under = PerfSample(phase="readiness", elapsed_ms=10.0, budget_ms=2000)
    over = PerfSample(phase="readiness", elapsed_ms=9999.0, budget_ms=2000)
    assert not under.over_budget
    assert over.over_budget
    rv = ReadinessView.from_assess(SYNTH_ASSESS, perf=over)
    assert rv.over_budget is True
    assert rv.to_dict()["over_budget"] is True


def test_build_readiness_on_real_project_degrades_gracefully(tmp_path: Path) -> None:
    # A minimal project with one kickoff input domain present; no inventory -> convention paths.
    inputs = tmp_path / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "conventions.yaml").write_text(
        textwrap.dedent(
            """\
            provenance_default: authored
            stack: python
            """
        ),
        encoding="utf-8",
    )
    rv = build_readiness(tmp_path)
    # It produced a view without raising; the present domain is reflected, and timing was recorded.
    assert rv.input_domains.get("conventions", {}).get("status") == "present"
    assert rv.perf is not None and rv.perf.phase == "readiness"
    assert rv.cascade_status in {"ok", "inputs_error", "absent"}
