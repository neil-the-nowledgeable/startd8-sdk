"""Shared engine for the per-language structure -> OTel §5 communication coverage maps.

The Go/Java/Node ``gen_<lang>_structure_comm_index.py`` generators and
``analyze_<lang>_comm_coverage.py`` analyzers were ~identical skeletons wrapped around a
small set of per-language deltas. This package holds the reusable functional core; each
script keeps ONLY its language DATA (a :class:`LanguageIndexSpec`) plus, for analyzers, a
:class:`CoverageAdapter` (source extensions, import extractor, path separator,
has-annotations). See ``engine.py`` for the split rationale.

Python's ``gen_python_ast_capability_index.py`` is deliberately NOT a consumer — it is
reflection/AST-based (a structurally different substrate), not a hand-authored L1 constant.
"""

from __future__ import annotations

from .engine import (
    CoverageAdapter,
    Detector,
    LanguageIndexSpec,
    RenderSpec,
    build_index,
    coverage_report,
    index_files,
    render_coverage_md,
    render_index_md,
    render_sarif,
    serialize,
    sha,
    write_or_check,
)
from .findings_sarif import SARIF_SCHEMA_URI, render_sarif_from_findings

__all__ = [
    "SARIF_SCHEMA_URI",
    "CoverageAdapter",
    "Detector",
    "LanguageIndexSpec",
    "RenderSpec",
    "build_index",
    "coverage_report",
    "index_files",
    "render_coverage_md",
    "render_index_md",
    "render_sarif",
    "render_sarif_from_findings",
    "serialize",
    "sha",
    "write_or_check",
]
