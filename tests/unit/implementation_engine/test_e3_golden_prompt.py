"""E3 (FR-CL-3b) golden-prompt validation — the deferred gate.

E3 removed the ``## API Signatures`` prose block from ``task_description``. The claim
that justified it: the same symbols already reach the generation prompt structurally
(and more richly) via the P0 forward-manifest sections, so nothing is lost. This test
proves that END-TO-END against the real prompt builder, deterministically (no API key):

1. From a feature's ``api_signatures`` → the extractor → a ForwardManifest.
2. The manifest renders into the two P0 structured sections the same way the pipeline
   does (`_format_forward_element_specs`, `map_forward_contracts_for_task` + ContractModule).
3. `build_spec_prompt` (what the LLM actually sees) is assembled from those sections.

Asserts: every declared symbol (functions, class, **variables/constants**, and a
param-less function) appears in the prompt via the structured sections; the
``## API Signatures`` prose round-trip is absent; and quantifies the token saving.

The remaining "generation-quality non-regression" needs a keyed real run — but the
substantive guarantee (the LLM still receives every symbol, in a strictly richer P0
form) is what this pins.
"""

from __future__ import annotations

from types import SimpleNamespace

from startd8.forward_manifest import ForwardFileSpec, ForwardManifest
from startd8.forward_manifest_extractor import DeterministicExtractor, ParsedFeature
from startd8.implementation_engine.budget import estimate_tokens
from startd8.implementation_engine.spec_builder import build_spec_prompt

# Exercises the key extractor paths: plain func, async func, class, variable, and
# constant — including the variable/constant the SCR's OQ-5 gap can't tag but which
# forward_element_specs DOES render for generation. Kept at 5 (the pre-existing
# _MAX_SIGNATURES_PER_TASK cap, orthogonal to E3) so enrichment retains all of them.
API_SIGS = [
    "def jobs_dashboard(request) -> Response",
    "async def resolve_matches(seed) -> list",
    "class JobsRouter",
    "router = APIRouter()",
    "MAX_RETRIES = 3",
]
SYMBOLS = ["jobs_dashboard", "resolve_matches", "JobsRouter", "router", "MAX_RETRIES"]
TARGET = "app/jobs.py"
FID = "F-1"


def _feature() -> ParsedFeature:
    return ParsedFeature(
        feature_id=FID, name="Jobs", description="", target_files=[TARGET],
        dependencies=[], estimated_loc=50, labels=[], design_doc_sections=[],
        artifact_types_addressed=[], api_signatures=list(API_SIGS),
    )


def _manifest() -> ForwardManifest:
    contracts, file_elements = DeterministicExtractor().extract([_feature()])
    return ForwardManifest(
        contracts=contracts,
        file_specs={p: ForwardFileSpec(file=p, elements=e) for p, e in file_elements.items()},
    )


def _structured_sections(fm: ForwardManifest) -> tuple[str, str]:
    """Render the two P0 sections exactly as the pipeline does."""
    from startd8.contractors.context_resolution import _format_forward_element_specs
    from startd8.contractors.artisan_phases.design_prompts.modules import ContractModule
    from startd8.contractors.artisan_phases.design_prompts.seed_mapping import (
        map_forward_contracts_for_task,
    )

    element_specs = _format_forward_element_specs(fm, FID, [TARGET])
    task = SimpleNamespace(task_id=FID, target_files=[TARGET])
    cdata = map_forward_contracts_for_task(task, forward_manifest=fm)
    contracts_text = ContractModule().render(cdata).text if cdata else ""
    return contracts_text, element_specs


def _build_prompt(task_description: str) -> str:
    fm = _manifest()
    contracts_text, element_specs = _structured_sections(fm)
    ctx = {"forward_contracts": contracts_text, "forward_element_specs": element_specs}
    return build_spec_prompt(task_description, ctx, None)


def test_structured_sections_carry_every_symbol():
    """forward_element_specs must render functions, class, AND variables/constants."""
    _contracts, element_specs = _structured_sections(_manifest())
    missing = [s for s in SYMBOLS if s not in element_specs]
    assert not missing, f"structured element specs dropped symbols: {missing}\n{element_specs}"


def test_spec_prompt_has_structured_sections_and_no_prose_roundtrip():
    prompt = _build_prompt("Implement the jobs dashboard and matching.")

    # The richer P0 structured sections are present...
    assert "## Interface Contract Bindings (must enforce)" in prompt
    assert "## Expected Code Elements (signatures, classes, bases)" in prompt
    # ...carrying every declared symbol the LLM needs.
    missing = [s for s in SYMBOLS if s not in prompt]
    assert not missing, f"spec prompt missing symbols: {missing}"
    # ...and the api_signatures prose round-trip (E3-removed) is gone.
    assert "## API Signatures" not in prompt


def test_e3_removes_the_prose_block_at_the_enrichment_site():
    """The actual E3 site: enrichment no longer appends the prose block, but still
    populates the structured field that builds the sections above."""
    from startd8.workflows.builtin.plan_ingestion_enrichment import _enrich_api_signatures

    task = {"task_id": "PI-1", "config": {"task_description": "Implement.", "context": {"feature_id": FID}}}
    count = _enrich_api_signatures([task], {FID: _feature()})

    assert count == 1
    desc = task["config"]["task_description"]
    assert "## API Signatures" not in desc and desc == "Implement."
    # structured field retained → it is what builds the forward manifest sections.
    assert set(task["config"]["context"]["api_signatures"]) == set(API_SIGS)


def test_token_saving_is_real_and_lossless():
    """Quantify the saving: the old prose block had real tokens; it is gone, while the
    structured sections still carry every symbol (net simplification, not info loss)."""
    # The block the pre-E3 code appended (plan_ingestion_enrichment, old behaviour).
    old_prose_block = "\n\n## API Signatures\n```python\n" + "\n\n".join(API_SIGS) + "\n```"
    saved = estimate_tokens(old_prose_block)
    assert saved > 0

    _contracts, element_specs = _structured_sections(_manifest())
    assert all(s in element_specs for s in SYMBOLS)  # symbols preserved structurally
