"""Simple Decomposer reporting (Phase 1, Cross-Cutting).

Typed dataclasses for the ``.startd8/reports/simple-decomposer.json``
report.  Advisory persistence — I/O failures never block a successful
generation run.
"""

from __future__ import annotations

import json
import platform
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict

from ..logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class CostSavings:
    """Estimated cost savings from deterministic generation."""

    llm_calls_avoided: int = 0
    usd_saved_estimate: float = 0.0
    per_call_rate_usd: float = 0.005


@dataclass
class ReportMeta:
    """Report metadata for schema evolution (Leg 10 #39)."""

    schema_version: str = "1.0.0"
    sdk_version: str = ""
    python_version: str = ""

    def __post_init__(self) -> None:
        if not self.python_version:
            self.python_version = platform.python_version()
        if not self.sdk_version:
            try:
                import startd8

                self.sdk_version = getattr(startd8, "__version__", "unknown")
            except ImportError:
                self.sdk_version = "unknown"


@dataclass
class SimpleDecomposerReport:
    """Per-run report for simple decomposer outcomes.

    Serialized to ``.startd8/reports/simple-decomposer.json`` via
    ``dataclasses.asdict()``.
    """

    run_id: str = ""
    timestamp: str = ""  # ISO-8601
    meta: ReportMeta = field(default_factory=ReportMeta)
    attempted: int = 0
    succeeded: int = 0
    rejected: int = 0
    rejection_reasons: Dict[str, int] = field(default_factory=dict)
    template_coverage: Dict[str, int] = field(default_factory=dict)
    cost_savings: CostSavings = field(default_factory=CostSavings)
    deterministic_ratio: float = 0.0


def persist_report(report: SimpleDecomposerReport, project_root: Path) -> None:
    """Write report to ``.startd8/reports/simple-decomposer.json``.

    Advisory — never raises on I/O failure (Leg 11 #70).
    """
    report_dir = project_root / ".startd8" / "reports"
    try:
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "simple-decomposer.json"
        report_path.write_text(
            json.dumps(asdict(report), indent=2, sort_keys=True),
            encoding="utf-8",
        )
    except OSError as err:
        logger.warning("Report write failed: %s", err)
