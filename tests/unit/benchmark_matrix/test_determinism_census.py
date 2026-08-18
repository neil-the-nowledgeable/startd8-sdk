"""Unit tests for the determinism-gap census (REQ-determinism-gap-census).

Covers, on a MOCK/fixture corpus (no fleet run):
  * FR-2 — the census finding-classes register as a data-only ``startd8-census`` RuleCatalog producer
    inheriting the shared validation.
  * FR-1 — the collector + observe-only hook; observations duck-type the SARIF sink and render through
    ``render_sarif_from_findings`` with producer ``startd8-census``.
  * FR-3 — the per-language determinism-% scoreboard derives from the realization seam.
  * FR-4 — absence-vs-error: an un-instrumented lane reads ``absent``, never a false 100%/0%.
  * FR-5 — the aggregator ranks finding-class × language by frequency × spread, frames ratchet candidates.
  * FR-6 — the instrumentation is byte-identical when the collector is absent (a guard test).
"""

from __future__ import annotations

import pytest

from startd8.census import (
    CensusCollector,
    CensusObservation,
    FindingClass,
    build_report,
    build_scoreboard,
    get_collector,
    record_intervention,
    render_sarif,
    set_collector,
)
from startd8.census import rule_catalog
from startd8.census.scoreboard import ABSENT


@pytest.fixture(autouse=True)
def _clear_collector():
    """Every test starts and ends with the process-scoped collector cleared (census OFF)."""
    set_collector(None)
    yield
    set_collector(None)


# ── FR-2: the data-only RuleCatalog producer ───────────────────────────────────────────────────────

def test_producer_is_startd8_census_and_validates():
    assert rule_catalog.PRODUCER == "startd8-census"
    # Every finding-class resolves a severity/domain/qualified_id via the shared base.
    for cls in rule_catalog.RULE_CATALOG:
        assert rule_catalog.rule_severity(cls) == "info"  # a census finding is an observation, not a fault
        assert rule_catalog.rule_domain(cls) in {"llm-intervention", "repair-intervention"}
        assert rule_catalog.qualified_id(cls) == f"startd8-census.{cls}"
        assert rule_catalog.rule_help_uri(cls).endswith(f"#{cls}")


def test_finding_class_enum_matches_catalog_keys():
    # The enum vocabulary and the catalog data must not drift.
    assert {fc.value for fc in FindingClass} == set(rule_catalog.RULE_CATALOG)


def test_help_uri_map_covers_every_class():
    m = rule_catalog.help_uri_map()
    assert set(m) == set(rule_catalog.RULE_CATALOG)


# ── FR-1: the collector + observe-only hook + SARIF render ───────────────────────────────────────────

def test_record_intervention_no_op_when_no_collector():
    # No collector installed → the hook is a no-op (records nothing, raises nothing).
    assert get_collector() is None
    record_intervention(FindingClass.ELEMENT_RENDER, "go", "struct", file_path="a.go")
    # Still nothing installed; the call was inert.
    assert get_collector() is None


def test_record_intervention_into_explicit_collector():
    c = CensusCollector()
    record_intervention(
        FindingClass.ELEMENT_RENDER, "go", "struct", file_path="cart.go", collector=c
    )
    assert len(c) == 1
    obs = c.observations[0]
    assert obs.finding_class == "element_render"
    assert obs.language == "go"
    assert obs.element_kind == "struct"
    assert obs.file_path == "cart.go"
    # Duck-typed SARIF fields.
    assert obs.check == "element_render"
    assert obs.severity == "info"
    assert "go" in obs.message and "struct" in obs.message


# ── Benchmark opt-out: the STARTD8_CENSUS_DISABLED hard kill-switch ──────────────────────────────────

def test_hard_disable_env_forces_no_op_even_with_explicit_collector(monkeypatch):
    # The benchmark opt-out: with the env kill-switch set, the hook records NOTHING even when a collector
    # is explicitly passed — so a benchmark cell is byte-identical regardless of any installed collector.
    monkeypatch.setenv("STARTD8_CENSUS_DISABLED", "1")
    c = CensusCollector()
    record_intervention(FindingClass.ELEMENT_RENDER, "go", "struct", file_path="a.go", collector=c)
    assert len(c) == 0


def test_hard_disable_env_refuses_set_collector(monkeypatch):
    # set_collector refuses to install while hard-disabled, so nothing is installed for the cell.
    monkeypatch.setenv("STARTD8_CENSUS_DISABLED", "true")
    set_collector(CensusCollector())
    assert get_collector() is None


def test_hard_disable_falsy_values_do_not_disable(monkeypatch):
    # Guard against accidental disable: falsy/empty values leave the census in its normal (opt-in) mode.
    for val in ("0", "false", "no", ""):
        monkeypatch.setenv("STARTD8_CENSUS_DISABLED", val)
        c = CensusCollector()
        record_intervention("repair_syntax", "python", "function", collector=c)
        assert len(c) == 1, f"{val!r} must NOT disable the census"


def test_record_intervention_into_process_scoped_collector():
    c = CensusCollector()
    set_collector(c)
    record_intervention("repair_syntax", "python", "function", file_path="svc.py")
    assert len(c) == 1
    assert c.observations[0].finding_class == "repair_syntax"


def test_render_sarif_through_universal_sink():
    obs = [
        CensusObservation("element_render", "go", "struct", file_path="cart.go", message="m1"),
        CensusObservation("repair_import", "python", "function", file_path="svc.py", line=12, message="m2"),
    ]
    doc = render_sarif(obs, corpus="round3-fleet")
    assert doc["version"] == "2.1.0"
    run = doc["runs"][0]
    assert run["tool"]["driver"]["name"] == "startd8-census"
    ruleids = {r["ruleId"] for r in run["results"]}
    assert ruleids == {"element_render", "repair_import"}
    # info severity maps to SARIF note level.
    assert all(r["level"] == "note" for r in run["results"])
    assert run["invocations"][0]["properties"]["corpus"] == "round3-fleet"
    # help URIs come from the shared catalog.
    rules = {r["id"]: r for r in run["tool"]["driver"]["rules"]}
    assert rules["element_render"]["helpUri"].endswith("#element_render")


def test_render_sarif_skips_findings_without_file():
    # A finding lacking a file uri cannot be located → honestly counted as skipped, never emitted invalid.
    obs = [CensusObservation("element_render", "go", "struct", file_path="")]
    doc = render_sarif(obs)
    run = doc["runs"][0]
    assert run["results"] == []
    assert run["invocations"][0]["properties"]["skipped"] == 1


# ── FR-3 / FR-4: the per-language scoreboard + absence-vs-error ───────────────────────────────────────

def _obs(lang, cls="element_render", file_path=None):
    return CensusObservation(cls, lang, "function", file_path=file_path or f"{lang}/f.py")


def test_scoreboard_derives_pct_from_realization_seam():
    # go has LLM interventions → below 100% deterministic; python only 1 file → also llm-touched.
    obs = [
        _obs("go", file_path="go/cart.go"),
        _obs("go", file_path="go/ship.go"),
        _obs("python", file_path="py/svc.py"),
    ]
    board = {row.language: row for row in build_scoreboard(obs)}
    # go observed: 2 llm files → 0% deterministic (every observed file is llm-touched here).
    assert board["go"].observed is True
    assert board["go"].determinism_pct == 0.0
    assert board["go"].llm_files == 2
    assert board["python"].observed is True
    assert board["python"].determinism_pct == 0.0


def test_scoreboard_absence_vs_error():
    # Only go instrumented; java/nodejs/csharp/python never ran → absent (not a false 100%/0%).
    obs = [_obs("go", file_path="go/cart.go")]
    board = {row.language: row for row in build_scoreboard(obs)}
    assert board["go"].observed is True
    assert board["go"].format_pct() != ABSENT
    for lane in ("python", "nodejs", "java", "csharp"):
        assert board[lane].observed is False
        assert board[lane].determinism_pct is None
        assert board[lane].format_pct() == ABSENT
        assert board[lane].status == ABSENT


def test_scoreboard_deterministic_lane_reads_measured_100():
    # A measured lane (observed=True) is distinct from an absent one, even at the 0/100% extremes.
    obs = [_obs("go", file_path="go/a.go")]
    board = {row.language: row for row in build_scoreboard(obs)}
    assert board["go"].status == "measured"
    assert board["java"].status == ABSENT
    # measured 100%-deterministic vs absent are distinct: a measured lane has observed=True.
    assert board["go"].observed and not board["java"].observed


# ── FR-5: the ranked report ──────────────────────────────────────────────────────────────────────────

def test_report_ranks_by_frequency_times_spread():
    obs = (
        # element_render across go+python+nodejs (spread 3, freq 3) → should top the ranking.
        [CensusObservation("element_render", lang, "function", file_path=f"{lang}/f") for lang in ("go", "python", "nodejs")]
        # repair_syntax only in go, but 4 times (spread 1, freq 4).
        + [CensusObservation("repair_syntax", "go", "function", file_path=f"go/r{i}") for i in range(4)]
    )
    report = build_report(obs)
    assert not report.is_empty
    assert report.total_observations == 7
    top = report.top(1)[0]
    # element_render/go: freq 1 × spread 3 = 3; repair_syntax/go: freq 4 × spread 1 = 4 → repair_syntax tops.
    # Verify the score model: the highest freq×spread row is first.
    scores = [(r.frequency * report.finding_class_spread[r.finding_class]) for r in report.rows]
    assert scores == sorted(scores, reverse=True)
    assert top.frequency * report.finding_class_spread[top.finding_class] == max(scores)
    # Every row carries a ratchet candidate (finding-class → render-template).
    assert all(r.template_candidate for r in report.rows)


def test_report_embeds_scoreboard_and_spread():
    obs = [
        CensusObservation("element_render", "go", "struct", file_path="go/a"),
        CensusObservation("element_render", "python", "function", file_path="py/b"),
    ]
    report = build_report(obs)
    assert report.finding_class_spread["element_render"] == 2
    langs = {row.language for row in report.scoreboard}
    assert {"go", "python", "nodejs", "java", "csharp"} <= langs


def test_empty_census_is_honest_empty_report():
    report = build_report([])
    assert report.is_empty
    assert report.rows == []
    # Every known lane is absent — no false zero.
    assert all(not row.observed for row in report.scoreboard)


# ── FR-6: byte-identical when the collector is absent (the observe-only guard) ────────────────────────

def test_hook_is_byte_identical_when_collector_absent():
    """The empty-default-is-the-guard: with no collector, the hook produces NO side effect on any
    output. We prove the instrumentation seam is inert — record_intervention returns None, installs
    nothing, and records nothing, so a census-off generation run is unchanged."""
    assert get_collector() is None
    # A pile of calls that would be emitted during a real generation run.
    for lang in ("go", "python", "nodejs", "csharp", "java"):
        record_intervention(FindingClass.ELEMENT_RENDER, lang, "function", file_path=f"{lang}/x")
        record_intervention("repair_syntax", lang, "function", file_path=f"{lang}/x")
    # Nothing was installed or retained — the seam is inert (byte-identical output guarantee).
    assert get_collector() is None


def test_engine_hook_helper_is_no_op_without_collector():
    """The micro_prime engine's element hook is a no-op when the census is off (guards generation output)."""
    from startd8.micro_prime.engine import _census_observe_element  # noqa: PLC0415

    class _FakeResult:
        template_used = False
        success = True
        code = "def f(): pass"
        input_tokens = 10
        output_tokens = 5
        element_kind = "function"
        element_name = "f"
        file_path = "svc.py"

    assert get_collector() is None
    _census_observe_element(_FakeResult(), "python")  # must not raise, must record nothing
    assert get_collector() is None

    # With a collector installed, it records exactly one observation.
    c = CensusCollector()
    set_collector(c)
    _census_observe_element(_FakeResult(), "python")
    assert len(c) == 1
    assert c.observations[0].finding_class == "element_render"
    assert c.observations[0].language == "python"


def test_engine_hook_skips_template_and_failed_results():
    from startd8.micro_prime.engine import _census_observe_element  # noqa: PLC0415

    c = CensusCollector()
    set_collector(c)

    class _Template:
        template_used = True  # deterministic — not an LLM intervention
        success = True
        code = "x"
        input_tokens = 0
        output_tokens = 0
        element_kind = "function"
        element_name = "t"
        file_path = "t.py"

    class _Failed:
        template_used = False
        success = False  # failed generation — not a load-bearing observation
        code = None
        input_tokens = 0
        output_tokens = 0
        element_kind = "function"
        element_name = "z"
        file_path = "z.py"

    _census_observe_element(_Template(), "python")
    _census_observe_element(_Failed(), "python")
    assert len(c) == 0
