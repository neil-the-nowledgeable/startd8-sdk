"""End-to-end LLM-free regression for RUN_003 PI-003 (next.config.mjs).

Two independent cases so a CI failure attributes to the correct increment:
  FR-9a — a plan-declared forward-element section reaches the spec prompt (Fix 1).
  FR-9b — an extractor-only seed yields a non-empty convention spec (Fix 2).
"""

from startd8.forward_manifest_extractor import extract_forward_contracts
from startd8.implementation_engine.spec_builder import build_spec_prompt
from startd8.workflows.builtin.plan_ingestion_models import ParsedFeature


def test_fr9a_plan_declared_section_present_for_next_config():
    # Fix 1 active: a plan-declared forward-element section for next.config.mjs
    # must appear in the spec prompt (it previously never reached the drafter).
    ctx = {
        "target_files": ["next.config.mjs"],
        "forward_element_specs": (
            "next.config.mjs: CONSTANT config (NextConfig); export default config"
        ),
    }
    prompt = build_spec_prompt("Generate Next.js config", ctx, None)
    assert "## Expected Code Elements" in prompt
    assert "next.config.mjs" in prompt
    assert "config" in prompt


def test_fr9b_extractor_only_next_config_is_nonempty():
    # Fix 2 active: no plan-declared elements, but the framework-conventions
    # registry populates next.config.mjs so the contract is non-empty.
    feature = ParsedFeature(
        feature_id="PI-003",
        name="Next.js config",
        target_files=["next.config.mjs"],
    )
    _contracts, file_elements = extract_forward_contracts([feature])

    assert "next.config.mjs" in file_elements
    elems = file_elements["next.config.mjs"]
    assert elems, "convention registry should populate next.config.mjs"
    assert elems[0].name == "config"
    assert elems[0].decomposition_source == "framework-conventions"
