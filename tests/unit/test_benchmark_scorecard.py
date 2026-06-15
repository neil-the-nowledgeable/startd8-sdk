"""Tests for the unified benchmark scorecard renderer (SCORECARD_FORMAT v2.0, inverted-pyramid)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from startd8.benchmark_matrix.runner import STATUS_OK, CellResult
from startd8.benchmark_matrix.scorecard import (
    build_scorecard,
    build_scorecard_html,
    write_scorecard,
    write_scorecard_html,
)

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
# real provider prefixes + two flagships so grouping is exercised
_MODELS = [
    "anthropic:claude-opus-4-8",
    "anthropic:claude-haiku-4-5",
    "openai:gpt-5.5",
    "gemini:gemini-2.5-pro",
    "gemini:gemini-2.5-flash",
]
_SPEC = {
    "name": "test-run",
    "spec_hash": "abc123def456",
    "services": ["s1"],
    "models": _MODELS,
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


def _five_cells():
    # opus best, then gpt, pro, flash, haiku worst
    qs = {
        "anthropic:claude-opus-4-8": 0.95,
        "openai:gpt-5.5": 0.90,
        "gemini:gemini-2.5-pro": 0.85,
        "gemini:gemini-2.5-flash": 0.70,
        "anthropic:claude-haiku-4-5": 0.60,
    }
    return [_cell(m, quality=q) for m, q in qs.items()]


# --------------------------------------------------------------------------- structure / ordering


def test_inverted_pyramid_scoreboard_first(tmp_path):
    _write_spec(tmp_path)
    _write_cells(tmp_path, _five_cells())
    md = build_scorecard(tmp_path, now=_NOW)
    assert "**Headline:**" in md
    # Scoreboard precedes every supporting dimension
    for later in [
        "## Consistency",
        "## Credibility",
        "## Behavioral",
        "## Determinism",
        "## By language",
    ]:
        assert md.index("## Scoreboard") < md.index(later)


def test_scoreboard_five_grouped_tables(tmp_path):
    _write_spec(tmp_path)
    _write_cells(tmp_path, _five_cells())
    md = build_scorecard(tmp_path, now=_NOW)
    for sub in [
        "### Flagship comparison",
        "### Anthropic models",
        "### Google models",
        "### OpenAI models",
        "### All models",
    ]:
        assert sub in md


def test_flagship_table_only_flagships_ranked_best_first(tmp_path):
    _write_spec(tmp_path)
    _write_cells(tmp_path, _five_cells())
    md = build_scorecard(tmp_path, now=_NOW)
    flag = md.split("### Flagship comparison")[1].split("### Anthropic")[0]
    assert (
        "anthropic:claude-opus-4-8" in flag
        and "openai:gpt-5.5" in flag
        and "gemini:gemini-2.5-pro" in flag
    )
    assert (
        "claude-haiku" not in flag and "gemini-2.5-flash" not in flag
    )  # non-flagships excluded
    assert (
        flag.index("opus-4-8") < flag.index("gpt-5.5") < flag.index("gemini-2.5-pro")
    )  # best→worst


def test_provider_tables_partition_by_prefix(tmp_path):
    _write_spec(tmp_path)
    _write_cells(tmp_path, _five_cells())
    md = build_scorecard(tmp_path, now=_NOW)
    anth = md.split("### Anthropic models")[1].split("### Google")[0]
    assert (
        "claude-opus-4-8" in anth and "claude-haiku" in anth and "gpt-5.5" not in anth
    )
    goog = md.split("### Google models")[1].split("### OpenAI")[0]
    assert (
        "gemini-2.5-pro" in goog
        and "gemini-2.5-flash" in goog
        and "anthropic" not in goog
    )


def test_headline_names_flagship_winner(tmp_path):
    _write_spec(tmp_path)
    _write_cells(tmp_path, _five_cells())
    md = build_scorecard(tmp_path, now=_NOW)
    assert "`anthropic:claude-opus-4-8` leads the flagship scoreboard" in md


def test_degrade_honest_empty_run(tmp_path):
    _write_spec(tmp_path)
    md = build_scorecard(tmp_path, now=_NOW)
    for h in [
        "## Scoreboard",
        "## Consistency",
        "## Credibility",
        "## Behavioral",
        "## Determinism",
        "## By language",
    ]:
        assert h in md
    assert "Not computed for this run" in md and "N/A for this run" in md


def test_headline_falls_back_to_credibility(tmp_path):
    _write_spec(tmp_path)  # no cells.json
    _write_contam(
        tmp_path,
        [
            {
                "service": "s1",
                "model": "x:clean",
                "language": "go",
                "codebleu": 0.2,
                "available": True,
            },
        ],
    )
    md = build_scorecard(tmp_path, now=_NOW)
    assert (
        "quality not computed" in md
        and "cleanest contamination" in md
        and "`x:clean`" in md
    )


# --------------------------------------------------------------------------- credibility / behavioral


def test_credibility_ranks_ascending_with_verdict(tmp_path):
    _write_spec(tmp_path)
    _write_contam(
        tmp_path,
        [
            {
                "service": "s1",
                "model": "openai:gpt-5.5",
                "language": "python",
                "codebleu": 0.20,
                "available": True,
            },
            {
                "service": "s1",
                "model": "gemini:gemini-2.5-pro",
                "language": "go",
                "codebleu": 0.40,
                "available": True,
            },
        ],
    )
    cred = (
        build_scorecard(tmp_path, now=_NOW)
        .split("## Credibility")[1]
        .split("## Behavioral")[0]
    )
    assert cred.index("openai:gpt-5.5") < cred.index(
        "gemini:gemini-2.5-pro"
    )  # ascending
    assert "no model shows elevated memorization" in cred and "🟩 ok" in cred


def test_behavioral_present_only_when_coverage(tmp_path):
    _write_spec(tmp_path)
    _write_cells(tmp_path, [_cell("m:x", fc=0.66)])
    beh = (
        build_scorecard(tmp_path, now=_NOW)
        .split("## Behavioral")[1]
        .split("## Determinism")[0]
    )
    assert "functional coverage" in beh and "0.660" in beh and "Not computed" not in beh


# --------------------------------------------------------------------------- HTML renderer


def test_html_self_contained_inverted_pyramid(tmp_path):
    _write_spec(tmp_path)
    _write_cells(tmp_path, _five_cells())
    html = build_scorecard_html(tmp_path, now=_NOW)
    assert html.startswith("<!doctype html>") and html.rstrip().endswith("</html>")
    assert "<link" not in html and 'src="http' not in html and 'href="http' not in html
    assert "cdn" not in html.lower()
    assert "Scoreboard" in html and html.index("Scoreboard") < html.index("Consistency")
    assert "Headline" in html
    for grp in [
        "Flagship comparison",
        "Anthropic models",
        "Google models",
        "OpenAI models",
        "All models",
    ]:
        assert grp in html


def test_html_credibility_pills_meter_and_verdict(tmp_path):
    _write_spec(tmp_path)
    _write_contam(
        tmp_path,
        [
            {
                "service": "s1",
                "model": "clean:m",
                "language": "python",
                "codebleu": 0.20,
                "available": True,
            },
            {
                "service": "s1",
                "model": "hot:m",
                "language": "go",
                "codebleu": 0.75,
                "available": True,
            },
        ],
    )
    html = build_scorecard_html(tmp_path, now=_NOW)
    assert 'class="pill pill-ok"' in html and 'class="pill pill-bad"' in html
    assert 'class="meter"' in html and "⚠ Review." in html


def test_write_both_files(tmp_path):
    _write_spec(tmp_path)
    assert write_scorecard(tmp_path, now=_NOW).name == "SCORECARD.md"
    out = write_scorecard_html(tmp_path, now=_NOW)
    assert out.name == "SCORECARD.html" and out.read_text().startswith(
        "<!doctype html>"
    )
