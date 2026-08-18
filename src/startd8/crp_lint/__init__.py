"""det-crp/0.1 conformance lint — the thin format+lint member of the det-doc-kit family.

det-crp has no `$0` projector (its generator, the ``new-cnvrg-rvw-prmpt`` compiler, already runs); the
kit ships a **format + this lint**. ``crp_lint`` validates a det-crp artifact (focus + Appendix-A/B/C
review-log) against ``SCHEMA_det-crp-0.1 §10`` and emits SARIF via the imported ``findings_sarif``.
"""

from __future__ import annotations

from .lint import (
    findings_to_sarif,
    has_focus,
    has_review_log,
    lint_crp,
    lint_focus,
    lint_header,
    lint_review_log,
)
from .models import CrpFinding

__all__ = [
    "CrpFinding",
    "lint_crp",
    "lint_focus",
    "lint_review_log",
    "lint_header",
    "has_focus",
    "has_review_log",
    "findings_to_sarif",
]
