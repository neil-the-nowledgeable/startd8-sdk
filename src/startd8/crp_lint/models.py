"""Typed finding for the det-crp/0.1 conformance lint (SCHEMA_det-crp-0.1 §10).

det-crp is the **thin format+lint** member of the det-doc-kit family (not a projector — its `$0`
generator, the ``new-cnvrg-rvw-prmpt`` compiler, already runs). ``crp_lint`` is that lint: it
validates a det-crp artifact (a ``crp-focus-*.md`` and/or an Appendix-A/B/C review-log embedded in a
REQ/PLAN) and emits findings as SARIF via the ONE ``coverage_map/findings_sarif`` (imported, not
vendored — charter §5/§6).
"""

from __future__ import annotations

from dataclasses import dataclass

FORMAT_VERSION = "det-crp/0.1"
COMPANION_KIND = "CRP"


@dataclass(frozen=True)
class CrpFinding:
    """A conformance finding — duck-typed for ``findings_sarif`` (``check``/``severity``/``message``/
    ``file_path``/``line``)."""

    check: str
    severity: str
    message: str
    file_path: str
    line: int = 0
