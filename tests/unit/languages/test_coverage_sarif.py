"""SARIF 2.1.0 renderer — the coverage-map engine's GitHub-code-scanning / IDE surface.

Behaviour-additive companion to the per-language index-parity tests. Builds a tiny Go corpus,
runs the Go analyzer's ``analyze()`` (the real report shape, not a hand-mocked dict), renders it
through ``render_sarif``, and validates the emitted doc against the SARIF 2.1.0 shape:

  1. top-level ``$schema`` + ``version == "2.1.0"`` (validators key on these);
  2. ``runs[0].tool.driver.rules`` non-empty (one rule per achievable §5 pattern);
  3. ``runs[0].results`` well-shaped — every result's ``ruleId`` is a declared rule,
     and each result carries a physical-location ``uri``.

This file must NOT be edited by the parity-test author (it is the SARIF-only guard).

Spec: docs/design/REQ-crosswalk-go-structure-to-otel-comm-domains.md · FR-4 (analyzer surface)
Pattern: dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from startd8.coverage_map import render_sarif

REPO = Path(__file__).resolve().parents[3]
_ANALYZER_PATH = REPO / "scripts" / "analyze_go_comm_coverage.py"


def _load_analyzer():
    spec = importlib.util.spec_from_file_location("analyze_go_comm_coverage", _ANALYZER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_ANALYZER = _load_analyzer()


def _tiny_go_corpus(tmp_path: Path) -> Path:
    """A minimal Go corpus that imports net/http (→ GO-OTEL-5.1-HTTP) + database/sql."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "main.go").write_text(
        "package main\n"
        'import (\n'
        '  "net/http"\n'
        '  "database/sql"\n'
        ")\n"
        "func main() { _ = http.Get; _ = sql.Open }\n",
        encoding="utf-8",
    )
    return corpus


def test_render_sarif_is_valid_2_1_0(tmp_path):
    corpus = _tiny_go_corpus(tmp_path)
    report = _ANALYZER.analyze(corpus)

    doc = render_sarif(report, tool_name="otel-comm-coverage-go", corpus=report["corpus"])

    # (1) SARIF 2.1.0 top-level shape
    assert "$schema" in doc, "SARIF doc must carry a top-level $schema"
    assert "sarif" in doc["$schema"].lower()
    assert doc["version"] == "2.1.0"
    assert isinstance(doc["runs"], list) and len(doc["runs"]) == 1

    run = doc["runs"][0]

    # (2) tool.driver + non-empty rules, one per achievable §5 pattern
    driver = run["tool"]["driver"]
    assert driver["name"] == "otel-comm-coverage-go"
    assert "informationUri" in driver
    rules = driver["rules"]
    assert rules, "driver.rules must be non-empty (one per achievable §5 pattern)"
    rule_ids = {r["id"] for r in rules}
    assert "GO-OTEL-5.1-HTTP" in rule_ids, "the HTTP pattern should be an achievable rule"
    for r in rules:
        assert r["shortDescription"]["text"] is not None  # = semconv_domain (may be a domain string)

    # (3) results well-shaped: ruleId in the rules set, a uri present, and the corpus detected HTTP
    results = run["results"]
    assert results, "the tiny corpus imports net/http → at least one result expected"
    seen_rule_ids = set()
    for res in results:
        assert res["ruleId"] in rule_ids, f"result ruleId {res['ruleId']!r} not in declared rules"
        assert res["level"] == "note"
        loc = res["locations"][0]["physicalLocation"]["artifactLocation"]
        assert loc["uri"], "each result must carry a physicalLocation uri"
        seen_rule_ids.add(res["ruleId"])
    assert "GO-OTEL-5.1-HTTP" in seen_rule_ids, "net/http import should surface as an HTTP result"
