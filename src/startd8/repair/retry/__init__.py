"""Repair-retry: deterministic, no-LLM post-job repair driven by a failed run's
``prime-postmortem-report.json``.

See ``docs/design/repair-pipeline/REPAIR_RETRY_REQUIREMENTS.md`` (v0.6) and
``REPAIR_RETRY_PLAN.md`` (v1.4). Increment 1 = report loader + violation extraction.
"""

from .classifier import ClassifyResult, RetryClass, classify
from .models import RetryDisposition, RetryViolation
from .report_loader import load_violations
from .search import DiskTargetSearch, TargetExistenceSearch

__all__ = [
    "RetryDisposition",
    "RetryViolation",
    "load_violations",
    "TargetExistenceSearch",
    "DiskTargetSearch",
    "RetryClass",
    "ClassifyResult",
    "classify",
]
