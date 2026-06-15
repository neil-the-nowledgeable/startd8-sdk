"""Tests for the unified benchmark scorecard renderer (SCORECARD_FORMAT v1.0)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from startd8.benchmark_matrix.runner import STATUS_OK, CellResult
from startd8.benchmark_matrix.scorecard import build_scorecard, write_scorecard

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
_SPEC = {
    "name": "test-run",
    "spec_hash": "abc123def456",
    "services": ["s1"],
    "models": ["anthropic:opus", "openai:gpt"],
    "repetitions": 2,
    "micro_prime_enabled": False,
}


def _write_spec(d):
    (d / "run-spec.json").write_text(json.dumps(_SPEC), encoding="utf-8")


def _cell(model, lang="python", quality=0.9, fc=None):
    return CellResult(
        cell_id=f"{model}-c",
        service="s1",
        model=model,
        language=lang,
        repetition=1,
        status=STATUS_OK,
        quality=quality,
        cost_usd=0.5,
        functional_coverage=fc,
    )


def _write_cells(d, cells):
    (d / "cells.json").write_text(
        json.dumps([c.to_dict() for c in cells]), encoding="utf-8"
    )


def _write_contam(d, rows):
    (d / "contamination-probe.json").write_text(
        json.dumps(
            {
                "reference_root": "/ref",
                "n_cells": len(rows),
                "n_scored": sum(r["available"] for r in rows),
                "cells": rows,
            }
        ),
        encoding="utf-8",
    )


def test_all_section_headers_always_present(tmp_path):
    _write_spec(tmp_path)
    md = build_scorecard(tmp_path, now=_NOW)
    for h in [
        "# Benchmark Scorecard — test-run",
        "## 1. Quality",
        "## 2. Consistency",
        "## 3. Credibility",
        "## 4. Behavioral",
        "## 5. Determinism",
        "## 6. By language",
    ]:
        assert h in md
    # header provenance
    assert "spec `abc123def456`" in md and "micro-prime **off**" in md


def test_degrade_honest_when_sources_absent(tmp_path):
    _write_spec(tmp_path)  # nothing else
    md = build_scorecard(tmp_path, now=_NOW)
    assert (
        "Not computed for this run" in md
    )  # quality/consistency/credibility/behavioral
    assert "N/A for this run" in md  # determinism (microservices, no spine)


def test_quality_and_consistency_from_cells(tmp_path):
    _write_spec(tmp_path)
    _write_cells(
        tmp_path,
        [_cell("anthropic:opus", quality=0.95), _cell("openai:gpt", quality=0.80)],
    )
    md = build_scorecard(tmp_path, now=_NOW)
    assert "| 1 | `anthropic:opus`" in md  # ranked first by quality
    assert "0.950" in md and "0.800" in md
    assert "Not computed" not in md.split("## 3.")[0]  # §1/§2 are computed


def test_credibility_ranks_and_verdicts(tmp_path):
    _write_spec(tmp_path)
    _write_contam(
        tmp_path,
        [
            {
                "service": "s1",
                "model": "openai:gpt",
                "language": "python",
                "codebleu": 0.20,
                "available": True,
            },
            {
                "service": "s1",
                "model": "anthropic:opus",
                "language": "python",
                "codebleu": 0.40,
                "available": True,
            },
        ],
    )
    md = build_scorecard(tmp_path, now=_NOW)
    cred = md.split("## 3.")[1].split("## 4.")[0]
    assert (
        "`openai:gpt`" in cred and "`anthropic:opus`" in cred
    )  # ascending: gpt(0.20) before opus(0.40)
    assert cred.index("openai:gpt") < cred.index("anthropic:opus")
    assert "no model shows elevated memorization" in cred  # max < 0.50
    assert "🟩 ok" in cred


def test_credibility_flags_elevated(tmp_path):
    _write_spec(tmp_path)
    _write_contam(
        tmp_path,
        [
            {
                "service": "s1",
                "model": "m",
                "language": "go",
                "codebleu": 0.72,
                "available": True,
            },
        ],
    )
    md = build_scorecard(tmp_path, now=_NOW)
    assert "🟥 verbatim?" in md and "inspect for memorization" in md


def test_behavioral_present_only_when_coverage(tmp_path):
    _write_spec(tmp_path)
    _write_cells(tmp_path, [_cell("m", fc=0.66)])
    md = build_scorecard(tmp_path, now=_NOW)
    beh = md.split("## 4.")[1].split("## 5.")[0]
    assert "functional coverage" in beh and "0.660" in beh and "Not computed" not in beh


def test_write_scorecard_writes_file(tmp_path):
    _write_spec(tmp_path)
    out = write_scorecard(tmp_path, now=_NOW)
    assert out.name == "SCORECARD.md" and out.read_text().startswith(
        "# Benchmark Scorecard"
    )
