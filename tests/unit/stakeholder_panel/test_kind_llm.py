# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""FR-12 — opt-in LLM input_kind refinement: index-alignment, enum-validation, fail-open (H-13..H-15)."""
from __future__ import annotations

from startd8.stakeholder_panel.synthesis_bridge import Candidate, InputKind, Lane
from startd8.stakeholder_panel.synthesis_bridge.kind_llm import refine_input_kinds


def _cands():
    return [
        Candidate(title="a", source_section="Open Questions", raw_text="Q?",
                  lane=Lane.NON_DECIDABLE, input_kind=InputKind.question),  # not refinable (typed)
        Candidate(title="b", source_section="(unsectioned)", raw_text="a weekly digest",
                  lane=Lane.UNSTRUCTURED, input_kind=InputKind.content),   # refinable [subset 0]
        Candidate(title="c", source_section="(unsectioned)", raw_text="never leave the network",
                  lane=Lane.UNSTRUCTURED, input_kind=InputKind.uncategorized),  # refinable [subset 1]
    ]


def test_refines_only_input_kind_never_lane_or_text():
    cands = _cands()
    refined, warn = refine_input_kinds(cands, generate=lambda p: '{"0": "feedback", "1": "constraint"}')
    assert warn is None and refined == 2
    assert cands[1].input_kind is InputKind.feedback
    assert cands[2].input_kind is InputKind.constraint
    # lane + raw_text untouched
    assert cands[1].lane is Lane.UNSTRUCTURED and cands[1].raw_text == "a weekly digest"
    # the already-typed question was not in the refinable subset
    assert cands[0].input_kind is InputKind.question


def test_out_of_enum_and_out_of_range_discarded():
    cands = _cands()
    # index 0 → invalid kind (discard); index 9 → out of range (discard)
    refined, warn = refine_input_kinds(cands, generate=lambda p: '{"0": "banana", "9": "risk"}')
    assert refined == 0 and warn is None
    assert cands[1].input_kind is InputKind.content       # kept deterministic
    assert cands[2].input_kind is InputKind.uncategorized  # untouched


def test_fail_open_on_generate_error():
    cands = _cands()

    def boom(_prompt):
        raise RuntimeError("no api key")

    refined, warn = refine_input_kinds(cands, generate=boom)
    assert refined == 0
    assert warn and "degraded to the deterministic result" in warn
    assert cands[1].input_kind is InputKind.content  # deterministic result stands


def test_unparseable_response_is_ignored():
    cands = _cands()
    refined, warn = refine_input_kinds(cands, generate=lambda p: "sorry, I cannot comply")
    assert refined == 0 and warn is None
    assert cands[1].input_kind is InputKind.content


def test_no_refinable_targets_is_noop():
    typed = [Candidate(title="a", source_section="Open Questions", raw_text="Q?",
                       lane=Lane.NON_DECIDABLE, input_kind=InputKind.question)]
    called = []
    refined, warn = refine_input_kinds(typed, generate=lambda p: called.append(p) or "{}")
    assert refined == 0 and warn is None and not called  # generate never called


def test_run_cap_bounds_items():
    many = [Candidate(title=str(i), source_section="(unsectioned)", raw_text=f"line {i}",
                      lane=Lane.UNSTRUCTURED, input_kind=InputKind.content) for i in range(10)]
    seen = {}

    def gen(prompt):
        # map every local index in the batch to 'feedback'
        import re
        idxs = [int(m) for m in re.findall(r"\[(\d+)\]", prompt)]
        for i in idxs:
            seen[i] = True
        return "{" + ", ".join(f'"{i}": "feedback"' for i in idxs) + "}"

    refined, warn = refine_input_kinds(many, generate=gen, max_items_per_run=3, max_items_per_call=2)
    assert refined == 3  # capped at 3 of 10, in batches of 2
