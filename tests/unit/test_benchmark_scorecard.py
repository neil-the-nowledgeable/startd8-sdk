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
        .split("\n## ")[0]  # just the Behavioral section (pricing-lane sections follow it)
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


# --------------------------------------------------------------------------- pricing lane (D2/D3)


def _pricing_cell(model, *, service="resolvedpriceservice", fc=1.0, cases=None, degraded=False):
    """A pricing-lane cell. ``cases`` = [(name, passed), ...] persisted at behavioral.suite.results.
    ``degraded=True`` → behavioral present but no ``suite`` key (the FR-6 degrade path)."""
    beh = {"ready": not degraded, "isolation_level": "loopback-allowed/egress-denied"}
    if not degraded:
        beh["suite"] = {
            "suite_version": "resolved-pricing-suite/1",
            "coverage": fc,
            "results": [{"name": n, "passed": p, "detail": ""} for n, p in (cases or [])],
        }
    c = CellResult(
        cell_id=f"{model}-{service}-c", service=service, model=model, language="python",
        repetition=1, status=STATUS_OK, quality=0.9, cost_usd=0.5,
        functional_coverage=(None if degraded else fc),
    )
    c.behavioral = beh
    return c


def test_pricing_lane_section_ranks_and_shows_leaf_delta(tmp_path):
    _write_spec(tmp_path)
    _write_cells(tmp_path, [
        _pricing_cell("anthropic:claude-opus-4-8", fc=0.5,
                      cases=[("sum_strategy", True), ("half_even_rounding", False)]),
        _pricing_cell("gemini:gemini-2.5-pro", fc=1.0,
                      cases=[("sum_strategy", True), ("half_even_rounding", True)]),
        _cell("anthropic:claude-opus-4-8", fc=1.0),  # OB-leaf for the delta
    ])
    md = build_scorecard(tmp_path, now=_NOW)
    sec = md.split("## Pricing lane")[1].split("\n## ")[0]
    # ranked best-first: gemini (1.0) above opus (0.5)
    assert sec.index("gemini:gemini-2.5-pro") < sec.index("anthropic:claude-opus-4-8")
    # opus de-saturation vs its own OB-leaf 1.0 → leaf Δ -0.500
    assert "-0.500" in sec
    assert "Not computed" not in sec


def test_pricing_discriminators_expose_per_case_divergence(tmp_path):
    _write_spec(tmp_path)
    _write_cells(tmp_path, [
        _pricing_cell("anthropic:claude-opus-4-8", fc=0.5,
                      cases=[("half_even_rounding", False)]),
        _pricing_cell("gemini:gemini-2.5-pro", fc=1.0,
                      cases=[("half_even_rounding", True)]),
    ])
    md = build_scorecard(tmp_path, now=_NOW)
    sec = md.split("## Pricing discriminators")[1].split("\n## ")[0]
    assert "resolvedpriceservice" in sec and "half_even_rounding" in sec
    # opus fails the rounding case (0/1), gemini passes (1/1) — the divergence aggregate hides
    assert "0/1" in sec and "1/1" in sec


def test_pricing_lane_degrade_honest_when_no_pricing_cells(tmp_path):
    _write_spec(tmp_path)
    _write_cells(tmp_path, _five_cells())  # all service "s1", none in the lane
    md = build_scorecard(tmp_path, now=_NOW)
    lane = md.split("## Pricing lane")[1].split("\n## ")[0]
    disc = md.split("## Pricing discriminators")[1].split("\n## ")[0]
    assert "Not computed" in lane and "Not computed" in disc


def test_pricing_discriminators_degrade_when_suite_missing(tmp_path):
    _write_spec(tmp_path)
    # a pricing cell that ran but degraded (no suite results) — coverage section still 'not computed'
    # for coverage (fc=None), and per-case must degrade WITHOUT crashing on the missing suite key.
    _write_cells(tmp_path, [_pricing_cell("openai:gpt-5.5", degraded=True)])
    md = build_scorecard(tmp_path, now=_NOW)
    disc = md.split("## Pricing discriminators")[1].split("\n## ")[0]
    assert "Not computed" in disc


def test_pricing_lane_in_html(tmp_path):
    _write_spec(tmp_path)
    _write_cells(tmp_path, [
        _pricing_cell("gemini:gemini-2.5-pro", fc=1.0, cases=[("sum_strategy", True)]),
    ])
    html = build_scorecard_html(tmp_path, now=_NOW)
    assert "Pricing lane" in html and "Pricing discriminators" in html
    assert "sum_strategy" in html
