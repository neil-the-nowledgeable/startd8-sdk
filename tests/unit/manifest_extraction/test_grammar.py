"""P0 grammar primitives — spike-pinned rules F1/F2 + the CRP block-termination rule."""

from __future__ import annotations

from startd8.manifest_extraction.grammar import (
    key_lines,
    md_tables,
    nfkd_kebab,
    parse_sections,
    plural_candidates,
    strip_annotations,
)

TWO_ADJACENT_TABLES = """\
| Page | Purpose | Content file |
|------|---------|--------------|
| Home | Landing | home.md |
| About | About | about.md |

| Label | Target |
|-------|--------|
| Home | / |
| About | /about |
"""


def test_adjacent_tables_segment_as_separate_runs() -> None:
    """F1: the 21-phantom-pages regression — Pages + Nav must never flatten into one table."""
    tables = md_tables(TWO_ADJACENT_TABLES)
    assert len(tables) == 2
    assert tables[0].headers == ("page", "purpose", "content file")
    assert len(tables[0].rows) == 2
    assert tables[1].headers == ("label", "target")
    assert len(tables[1].rows) == 2


def test_pipe_run_without_separator_is_not_a_table() -> None:
    assert md_tables("| just\n| pipes\n| no separator\n") == []


def test_nfkd_kebab_unicode() -> None:
    """F2: Résumé → resume, never r-sum."""
    assert nfkd_kebab("Résumé") == "resume"
    assert nfkd_kebab("How it works") == "how-it-works"
    assert nfkd_kebab("Home") == "home"


def test_strip_annotations() -> None:
    assert strip_annotations("jobs.md *(not written yet)*") == "jobs.md"
    assert strip_annotations("/value-map        # OPTIONAL — overrides") == "/value-map"


def test_key_lines_terminate_at_first_non_key_line() -> None:
    """CRP rule: a Views block ends at the first non-`- Key:` line."""
    body = "- Kind: dashboard\n- Root: Widget\nSome trailing prose\n- Sneaky: after-prose\n"
    keys, order = key_lines(body)
    assert keys == {"Kind": "dashboard", "Root": "Widget"}
    assert order == ["Kind", "Root"]


def test_sections_carry_heading_paths() -> None:
    text = "## Entities\n\nintro\n\n### Widget\nbody\n\n## Pages\nbody\n"
    sections = parse_sections(text)
    widget = next(s for s in sections if s.title == "Widget")
    assert widget.heading_path == ("Entities", "Widget")
    assert widget.level == 3


def test_plural_candidates() -> None:
    assert "Capability" in plural_candidates("Capabilities")
    assert "ProofPoint" in plural_candidates("ProofPoints")
    assert "Widget" in plural_candidates("Widgets")
