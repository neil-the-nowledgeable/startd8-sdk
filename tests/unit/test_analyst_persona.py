"""Tests for the declarative analyst persona: A1 loader + A2 manifest + A3 analytical sections."""

from pathlib import Path

from startd8.observability.persona_config import load_personas

_MANIFEST = (
    Path(__file__).resolve().parents[2]
    / "docs/design/deterministic-sre-onboarding/benchmark.contextcore.yaml"
)


# --- A1: the persona-config loader (defaults + manifest overlay, no regression) ---

def test_load_personas_defaults():
    profiles = load_personas(None)
    assert set(profiles) == {"operator", "engineer", "manager", "executive"}
    assert "overview" in profiles["operator"].sections


def test_pure_alias_does_not_override_default():
    # a manifest persona with only id/portal_persona (no sections/value) keeps the built-in default
    before = load_personas(None)["manager"]
    after = load_personas([{"id": "project_manager", "portal_persona": "manager"}])["manager"]
    assert after.sections == before.sections and after.value == before.value


def test_manifest_analyst_adds_persona_as_data():
    personas = [{
        "id": "analyst", "portal_persona": "analyst",
        "sections": ["overview", "leaderboard", "exclusions"],
        "value": {"title": "Benchmark Analyst", "pain": "x", "headline": "h", "content": "c"},
    }]
    profiles = load_personas(personas)
    assert "analyst" in profiles
    assert profiles["analyst"].sections == frozenset({"overview", "leaderboard", "exclusions"})
    assert profiles["analyst"].value["title"] == "Benchmark Analyst"
    # built-ins still present (additive)
    assert {"operator", "engineer", "manager", "executive"} <= set(profiles)


def test_real_manifest_declares_analyst():
    import yaml
    manifest = yaml.safe_load(_MANIFEST.read_text())
    personas = manifest.get("personas") or []
    analyst = next((p for p in personas if p.get("id") == "analyst"), None)
    assert analyst is not None
    assert "leaderboard" in analyst["sections"] and "scoring-methodology" in analyst["sections"]


# --- A3: the analytical section builders render from aggregate data ---

def _agg_fixture():
    return {
        "pass_threshold": 0.5,
        "overall": {"n": 18, "n_ran": 18, "n_scored": 9, "infra_fail_count": 9,
                    "quality_median": 1.0, "quality_iqr": 0.0, "pass_rate": 1.0,
                    "catastrophic_count": 0, "cost_total_usd": 5.82},
        "by_model": {
            "anthropic:claude-opus-4-8": {"quality_median": 1.0, "quality_iqr": 0.0, "pass_rate": 1.0,
                                          "cost_total_usd": 2.83, "n_scored": 9, "infra_fail_count": 0,
                                          "catastrophic_count": 0},
            "gemini:gemini-2.5-flash-lite": {"quality_median": 1.0, "quality_iqr": 0.0, "pass_rate": 1.0,
                                             "cost_total_usd": 0.034, "n_scored": 9, "infra_fail_count": 0,
                                             "catastrophic_count": 0},
            "openai:gpt-5.5": {"quality_median": None, "quality_iqr": None, "pass_rate": None,
                               "cost_total_usd": 0.0, "n_scored": 0, "infra_fail_count": 9,
                               "catastrophic_count": 0},
        },
        "by_service": {
            "checkoutservice": {"quality_median": 0.82, "quality_iqr": 0.1},
            "adservice": {"quality_median": 1.0, "quality_iqr": 0.0},
        },
    }


def test_analyst_portal_renders_analytical_sections():
    from types import SimpleNamespace

    from startd8.observability.persona_config import PersonaProfile
    from startd8.observability.portal_spec_builder import build_portal_spec

    business = SimpleNamespace(project_id="startd8-benchmark", project_name="Benchmark",
                              criticality="high", owner="x")
    report = SimpleNamespace(project_id="startd8-benchmark", generated_at="2026-06-14", artifacts=[],
                             services_processed=1)
    metadata = {"aggregate": _agg_fixture(), "scoring": {"scoring_formula": "compile+0.4/0.2/0.2/0.2"}}
    profile = PersonaProfile(
        sections=frozenset({"overview", "scoring-methodology", "leaderboard", "quality-distribution",
                            "exclusions", "service-discrimination", "deeper-analysis", "provenance"}),
        value={"title": "Benchmark Analyst", "pain": "x", "headline": "h", "content": "c"},
    )
    spec = build_portal_spec(business, [], report, metadata, persona="analyst", profile=profile)
    titles = [p.get("title", "") for p in spec["panels"]]
    for expected in ["Scoring Methodology", "Leaderboard", "Quality Distribution",
                     "Exclusions", "Service Discrimination", "Deeper Analysis"]:
        assert expected in titles, f"missing analyst section: {expected}"
    assert spec["uid"] == "cc-portal-startd8-benchmark-analyst"
    # leaderboard ranks by quality then cost → flash-lite (cheapest at equal quality) ahead of opus
    content = " ".join(p.get("options", {}).get("content", "") for p in spec["panels"])
    assert "flash-lite" in content and "Cost / quality" in content
    # exclusions surface the 9 infra-excluded cells (OpenAI quota), not as model failures
    assert "9 cells excluded as infra/integrity" in content
