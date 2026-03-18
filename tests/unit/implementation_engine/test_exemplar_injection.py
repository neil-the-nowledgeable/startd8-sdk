"""Tests for exemplar injection into spec and draft prompts (REQ-PEP-101/102)."""

from __future__ import annotations

from typing import Any, Dict

import pytest

from startd8.implementation_engine.budget import EXEMPLAR_BUDGET_CHARS
from startd8.implementation_engine.drafter import build_supplementary_sections
from startd8.implementation_engine.spec_builder import _build_exemplar_section


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_exemplar_context(
    *,
    code_summary: str = "package main\n\nfunc main() {}\n",
    spec_excerpt: str = "## Requirements\n- Implement gRPC server",
    code_excerpt: str = "package main\n\nimport \"google.golang.org/grpc\"\n\nfunc main() {}",
    run_id: str = "run-042",
    fingerprint: str = "go:source:grpc:grpc_server",
    dq_score: float = 1.0,
    match_type: str = "exact",
) -> Dict[str, Any]:
    return {
        "source_run_id": run_id,
        "fingerprint": fingerprint,
        "match_type": match_type,
        "scores": {"disk_quality_score": dq_score},
        "code_summary": code_summary,
        "code_excerpt": code_excerpt,
        "spec_excerpt": spec_excerpt,
        "language": "go",
    }


# ---------------------------------------------------------------------------
# Tests: _build_exemplar_section (spec_builder)
# ---------------------------------------------------------------------------

class TestBuildExemplarSection:
    """REQ-PEP-101: spec prompt exemplar injection."""

    def test_returns_empty_when_no_exemplar(self):
        assert _build_exemplar_section({}) == ""

    def test_returns_empty_when_exemplar_is_none(self):
        assert _build_exemplar_section({"exemplar": None}) == ""

    def test_returns_section_with_exemplar(self):
        ctx = {"exemplar": _make_exemplar_context()}
        section = _build_exemplar_section(ctx)
        assert "## Verified Reference" in section
        assert "run-042" in section
        assert "1.00" in section

    def test_includes_spec_excerpt(self):
        ctx = {"exemplar": _make_exemplar_context()}
        section = _build_exemplar_section(ctx)
        assert "Spec that produced it" in section
        assert "gRPC server" in section

    def test_includes_code_excerpt(self):
        ctx = {"exemplar": _make_exemplar_context()}
        section = _build_exemplar_section(ctx)
        assert "Code that was validated" in section
        assert "google.golang.org/grpc" in section

    def test_partial_match_note(self):
        ctx = {"exemplar": _make_exemplar_context(match_type="partial")}
        section = _build_exemplar_section(ctx)
        assert "partial match" in section.lower()

    def test_no_partial_note_for_exact(self):
        ctx = {"exemplar": _make_exemplar_context(match_type="exact")}
        section = _build_exemplar_section(ctx)
        assert "partial match" not in section.lower()

    def test_budget_respected(self):
        # Create a very long exemplar
        long_code = "x = 1\n" * 500
        ctx = {"exemplar": _make_exemplar_context(
            code_excerpt=long_code, spec_excerpt="short spec",
        )}
        section = _build_exemplar_section(ctx)
        assert len(section) < EXEMPLAR_BUDGET_CHARS + 500  # some overhead for headers

    def test_falls_back_to_code_summary(self):
        ctx = {"exemplar": _make_exemplar_context(
            code_excerpt="", spec_excerpt="",
            code_summary="def main():\n    pass\n",
        )}
        section = _build_exemplar_section(ctx)
        assert "main()" in section

    def test_returns_empty_when_no_content(self):
        ctx = {"exemplar": _make_exemplar_context(
            code_excerpt="", spec_excerpt="", code_summary="",
        )}
        section = _build_exemplar_section(ctx)
        assert section == ""


# ---------------------------------------------------------------------------
# Tests: build_supplementary_sections (drafter)
# ---------------------------------------------------------------------------

class TestDrafterExemplarInjection:
    """REQ-PEP-102: drafter prompt exemplar injection."""

    def test_exemplar_in_p1_sections(self):
        context = {"exemplar": _make_exemplar_context()}
        result = build_supplementary_sections(context)
        assert "Verified Reference Implementation" in result
        assert "google.golang.org/grpc" in result

    def test_no_exemplar_no_section(self):
        context = {"kaizen_hints": "- hint 1"}
        result = build_supplementary_sections(context)
        assert "Verified Reference" not in result

    def test_exemplar_score_in_output(self):
        context = {"exemplar": _make_exemplar_context(dq_score=0.95)}
        result = build_supplementary_sections(context)
        assert "0.95" in result

    def test_exemplar_truncated_when_over_budget(self):
        long_code = "import foo\n" * 200
        context = {"exemplar": _make_exemplar_context(code_excerpt=long_code)}
        result = build_supplementary_sections(context, budget_chars=2000)
        assert len(result) <= 2100  # some overflow tolerance
