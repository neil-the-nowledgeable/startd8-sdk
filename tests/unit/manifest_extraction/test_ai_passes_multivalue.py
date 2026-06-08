"""F-1 (strtd8 fidelity note 2026-06-06): multi-value "Reads" cells must keep ALL entities.

The strtd8 derivation kept only one of two Reads entities for 4 of 5 passes (e.g.
``suggest_capabilities_outcomes`` lost ProofPoint; ``synthesize_value_propositions`` lost
Capability) — the human corrections in their ``prisma/ai_passes.yaml`` are the target shape.
The deriver must split multi-value cells on every human separator (comma, "·", "+", " and ")
and tolerate leading qualifiers ("confirmed ProofPoints"), while pure prose still derives a
text-mode pass (no ``input_entities``).
"""

from __future__ import annotations

import pytest
import yaml

from startd8.manifest_extraction import extract_manifests
from startd8.manifest_extraction.extractors import _split_multi_value

_ENTITY_BLOCK = """### {name}
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| label | text | yes | |
"""

DOC = (
    "# StartDate — Requirements (multi-value Reads fixture)\n\n"
    "## Entities\n\n"
    + "\n".join(
        _ENTITY_BLOCK.format(name=n)
        for n in ("ProofPoint", "Capability", "Outcome", "Metric", "Differentiator", "ValueProp")
    )
    + """
## AI assists

| Assist | Reads | Writes | Purpose |
|--------|-------|--------|---------|
| extract | pasted free text (résumé / wizard answer) | ProofPoint | first-pass capture |
| suggest_capabilities_outcomes | confirmed ProofPoints | Capability, Outcome (+ their link) | propose capabilities |
| quantify_metrics | confirmed ProofPoints, Outcomes | Metric (never the value) | prompt on WHAT to measure |
| synthesize_differentiators | confirmed ProofPoints · Capabilities | Differentiator | why you specifically |
| synthesize_value_propositions | confirmed Capabilities and Outcomes | ValueProp | headline value props |
| plus_separated | ProofPoints + Metrics | ValueProp | plus-separator coverage |
"""
)


@pytest.fixture(scope="module")
def passes_by_name():
    result = extract_manifests({"kickoff.md": DOC})
    data = yaml.safe_load(result.manifests["ai_passes.yaml"])
    return {p["name"]: p for p in data["passes"]}


def test_prose_reads_stays_text_mode(passes_by_name) -> None:
    assert "input_entities" not in passes_by_name["extract"]


def test_qualified_single_read_survives(passes_by_name) -> None:
    # Pre-fix this lost ProofPoint entirely ("confirmed" prefix defeated resolution).
    assert passes_by_name["suggest_capabilities_outcomes"]["input_entities"] == ["ProofPoint"]


def test_comma_separated_reads_keep_all_entities(passes_by_name) -> None:
    assert passes_by_name["quantify_metrics"]["input_entities"] == ["ProofPoint", "Outcome"]


def test_middot_separated_reads_keep_all_entities(passes_by_name) -> None:
    assert passes_by_name["synthesize_differentiators"]["input_entities"] == [
        "ProofPoint",
        "Capability",
    ]


def test_and_separated_reads_keep_all_entities(passes_by_name) -> None:
    assert passes_by_name["synthesize_value_propositions"]["input_entities"] == [
        "Capability",
        "Outcome",
    ]


def test_plus_separated_reads_keep_all_entities(passes_by_name) -> None:
    assert passes_by_name["plus_separated"]["input_entities"] == ["ProofPoint", "Metric"]


def test_multi_value_writes_keep_all_entities(passes_by_name) -> None:
    # The Writes column uses the same splitter; "(+ their link)" is policy, stripped first.
    assert passes_by_name["suggest_capabilities_outcomes"]["output_entities"] == [
        "Capability",
        "Outcome",
    ]


def test_split_multi_value_handles_every_separator() -> None:
    assert _split_multi_value("A, B · C + D and E") == ["A", "B", "C", "D", "E"]
    assert _split_multi_value("") == []
    # " and " requires surrounding whitespace — entity names containing "and" never split.
    assert _split_multi_value("Brandable") == ["Brandable"]
