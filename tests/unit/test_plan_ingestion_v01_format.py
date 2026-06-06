"""
Unit tests for requirements-and-plan-format v0.1 support in plan ingestion.

Covers the sapper-survey fixes (SAPPER_SURVEY_PLAN_INGESTION_2026-06-05):
1. Heuristic parser reads v0.1 feature tables + "F-xxx after F-yyy" dep lines.
2. count_plan_feature_tokens — the degenerate-parse tripwire signal.
3. fail_on_degenerate_parse config plumbing.
4. CRP appendix fencing (_strip_appendix_for_prompt variants).

No LLM calls — all deterministic.
"""

import textwrap

from startd8.workflows.builtin.architectural_review_log_constants import (
    _strip_appendix_for_prompt,
)
from startd8.workflows.builtin.plan_ingestion_models import PlanIngestionConfig
from startd8.workflows.builtin.plan_ingestion_parsing import (
    _HEURISTIC_FALLBACK_DESCRIPTION,
    _extract_dependency_lines,
    _extract_table_features,
    _heuristic_parse_plan,
    count_plan_feature_tokens,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

V01_PLAN = textwrap.dedent("""\
    # StartDate — Plan

    ## Goals

    - Ship the deterministic skeleton first

    ## Iterations

    ### Iteration 1 — foundation

    | Feature | FRs | Target files | Est. LOC |
    |---------|-----|--------------|----------|
    | F-101 project scaffold (config, logging) | FR-10 | pyproject.toml, app/main.py, Dockerfile, .env.example | 0 (deterministic) |
    | F-102 contract projection | FR-1, FR-4 | app/models.py, app/tables.py | 0 (deterministic) |

    ### Iteration 3 — integration

    | Feature | FRs | Target files | Est. LOC |
    |---------|-----|--------------|----------|
    | F-302 extract pass + prompt draft | FR-3 | app/ai/extract.py, prompts/extract.md | 150 |
    | F-304 guided wizard orchestration | — | app/wizard.py (generated home), templates | 200 |

    ## Dependencies

    - F-102 after F-101
    - F-302 after F-102
    - F-304 after F-302, F-101
    """)

HEADING_PLAN = textwrap.dedent("""\
    # Legacy Plan

    ### F-001: First feature

    Touch `src/alpha.py`. Depends on nothing.

    ### F-002: Second feature

    Touch `src/beta.py` after F-001.
    """)

CRP_APPENDIX = textwrap.dedent("""\

    ## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

    ### Reviewer Instructions (for humans + models)

    - Append suggestions to Appendix C using `R{round}-S{n}` IDs.

    ### Appendix A: Applied Suggestions

    ### Appendix B: Rejected Suggestions (with Rationale)

    ### Appendix C: Incoming Suggestions (Untriaged, append-only)
    """)


# ---------------------------------------------------------------------------
# v0.1 table parsing
# ---------------------------------------------------------------------------

class TestV01TableParsing:
    def test_extracts_all_table_features(self):
        plan = _heuristic_parse_plan(V01_PLAN)
        fids = [f.feature_id for f in plan.features]
        assert fids == ["F-101", "F-102", "F-302", "F-304"]

    def test_no_fallback_feature_emitted(self):
        plan = _heuristic_parse_plan(V01_PLAN)
        assert all(
            f.description != _HEURISTIC_FALLBACK_DESCRIPTION for f in plan.features
        )

    def test_target_files_distributed(self):
        plan = _heuristic_parse_plan(V01_PLAN)
        by_id = {f.feature_id: f for f in plan.features}
        assert by_id["F-101"].target_files == [
            "pyproject.toml", "app/main.py", "Dockerfile", ".env.example",
        ]
        # Parenthetical suffix dropped; bare non-path word "templates" dropped
        assert by_id["F-304"].target_files == ["app/wizard.py"]

    def test_deterministic_features_labeled_with_zero_loc(self):
        plan = _heuristic_parse_plan(V01_PLAN)
        by_id = {f.feature_id: f for f in plan.features}
        assert by_id["F-101"].estimated_loc == 0
        assert "deterministic" in by_id["F-101"].labels
        assert by_id["F-302"].estimated_loc == 150
        assert "deterministic" not in by_id["F-302"].labels

    def test_dependency_lines_populate_graph(self):
        plan = _heuristic_parse_plan(V01_PLAN)
        assert plan.dependency_graph == {
            "F-102": ["F-101"],
            "F-302": ["F-102"],
            "F-304": ["F-302", "F-101"],
        }

    def test_fr_refs_carried_into_description(self):
        plan = _heuristic_parse_plan(V01_PLAN)
        by_id = {f.feature_id: f for f in plan.features}
        assert "FR-1, FR-4" in by_id["F-102"].description

    def test_heading_format_still_parses(self):
        plan = _heuristic_parse_plan(HEADING_PLAN)
        fids = [f.feature_id for f in plan.features]
        assert fids == ["F-001", "F-002"]
        assert plan.features[1].dependencies == ["F-001"]

    def test_mixed_heading_and_table_dedupes_by_id(self):
        mixed = HEADING_PLAN + "\n" + textwrap.dedent("""\
            | Feature | FRs | Target files | Est. LOC |
            |---------|-----|--------------|----------|
            | F-002 duplicate of heading feature | FR-9 | src/dup.py | 10 |
            | F-003 table-only feature | FR-9 | src/gamma.py | 20 |
            """)
        plan = _heuristic_parse_plan(mixed)
        fids = [f.feature_id for f in plan.features]
        assert fids.count("F-002") == 1
        assert "F-003" in fids
        # Heading version wins for F-002 (name from the ### heading, not the table row)
        by_id = {f.feature_id: f for f in plan.features}
        assert by_id["F-002"].name == "Second feature"

    def test_non_feature_table_ignored(self):
        text = textwrap.dedent("""\
            # Plan

            | Key | Value |
            |-----|-------|
            | plan_path | docs/plan.md |
            """)
        plan = _heuristic_parse_plan(text)
        assert len(plan.features) == 1
        assert plan.features[0].description == _HEURISTIC_FALLBACK_DESCRIPTION

    def test_extract_table_features_unit(self):
        feats = _extract_table_features(V01_PLAN)
        assert len(feats) == 4
        assert feats[0].name.startswith("project scaffold")

    def test_extract_dependency_lines_multi_prereq(self):
        deps = _extract_dependency_lines("- F-304 after F-302, F-101\n")
        assert deps == {"F-304": ["F-302", "F-101"]}


# ---------------------------------------------------------------------------
# Degenerate-parse tripwire signal
# ---------------------------------------------------------------------------

class TestFeatureTokenCounter:
    def test_counts_distinct_feature_tokens(self):
        assert count_plan_feature_tokens(V01_PLAN) == 4

    def test_does_not_match_requirement_tokens(self):
        assert count_plan_feature_tokens("FR-10 REQ-7 F-1 OAT-041") == 1

    def test_zero_for_freeform_text(self):
        assert count_plan_feature_tokens("just prose, no features") == 0

    def test_duplicates_counted_once(self):
        assert count_plan_feature_tokens("F-101 F-101 F-101 F-102") == 2


class TestFailOnDegenerateParseConfig:
    def test_default_true(self):
        cfg = PlanIngestionConfig.from_dict({"plan_path": "plan.md"})
        assert cfg.fail_on_degenerate_parse is True

    def test_opt_out(self):
        cfg = PlanIngestionConfig.from_dict(
            {"plan_path": "plan.md", "fail_on_degenerate_parse": "false"}
        )
        assert cfg.fail_on_degenerate_parse is False


# ---------------------------------------------------------------------------
# CRP appendix fencing
# ---------------------------------------------------------------------------

class TestAppendixStripping:
    def test_strips_exact_heading(self):
        doc = "# Doc\n\nBody text.\n" + CRP_APPENDIX
        stripped = _strip_appendix_for_prompt(doc)
        assert "Appendix" not in stripped
        assert "Body text." in stripped

    def test_strips_variant_without_parenthetical(self):
        doc = "# Doc\n\nBody.\n\n## Appendix: Iterative Review Log\n\n### Appendix C\n"
        stripped = _strip_appendix_for_prompt(doc)
        assert "Appendix" not in stripped

    def test_strips_deeper_heading_level(self):
        doc = "# Doc\n\nBody.\n\n### Appendix: Iterative Review Log (Applied / Rejected Suggestions)\nstuff\n"
        stripped = _strip_appendix_for_prompt(doc)
        assert "Appendix" not in stripped

    def test_no_appendix_returns_doc_unchanged(self):
        doc = "# Doc\n\nNo review log here.\n"
        assert _strip_appendix_for_prompt(doc) == doc

    def test_unrelated_appendix_untouched(self):
        doc = "# Doc\n\n## Appendix: Glossary\n\nterms\n"
        assert _strip_appendix_for_prompt(doc) == doc

    def test_reviewer_instructions_fenced(self):
        doc = "# Requirements\n\nFR-1 something.\n" + CRP_APPENDIX
        stripped = _strip_appendix_for_prompt(doc)
        assert "Reviewer Instructions" not in stripped
        assert "Append suggestions" not in stripped
        assert "FR-1 something." in stripped
