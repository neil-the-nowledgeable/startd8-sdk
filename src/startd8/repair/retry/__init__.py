"""Repair-retry: deterministic, no-LLM post-job repair driven by a failed run's
``prime-postmortem-report.json``.

See ``docs/design/repair-pipeline/REPAIR_RETRY_REQUIREMENTS.md`` (v0.6) and
``REPAIR_RETRY_PLAN.md`` (v1.4). Increment 1 = report loader + violation extraction.
"""

from .classifier import ClassifyResult, RetryClass, classify
from .engine import RepairRetryEngine, RetryReport
from .models import RetryDisposition, RetryViolation
from .report_loader import load_violations
from .rewriter import Rewrite, apply_rewrite, compute_rewrite
from .scaffold import scaffold_barrel, scaffold_cofile
from .search import DiskTargetSearch, ResolveResult, TargetExistenceSearch

__all__ = [
    "RetryDisposition",
    "RetryViolation",
    "load_violations",
    "TargetExistenceSearch",
    "DiskTargetSearch",
    "ResolveResult",
    "RetryClass",
    "ClassifyResult",
    "classify",
    "Rewrite",
    "compute_rewrite",
    "apply_rewrite",
    "scaffold_cofile",
    "scaffold_barrel",
    "RepairRetryEngine",
    "RetryReport",
]
