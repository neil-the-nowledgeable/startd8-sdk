"""
Multi-dashboard batch processing (DC-111).

Process a list of DashboardSpec dicts with per-dashboard error isolation.
"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import yaml

from startd8.dashboard_creator.workflow import DashboardCreatorWorkflow
from startd8.exceptions import ConfigurationError
from startd8.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class DashboardReport:
    """Outcome of a single dashboard in a batch run."""

    uid: str
    title: str
    source: str
    success: bool
    error: Optional[str] = None
    json_path: Optional[str] = None
    duration_ms: int = 0


@dataclass
class BatchReport:
    """Aggregate outcome of a batch run (DC-111)."""

    timestamp: str = ""
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    dashboards: List[DashboardReport] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        """Exit code contract: 0 = all success, 2 = partial, 1 = all failed."""
        if self.failed == 0:
            return 0  # includes total=0 (vacuous success)
        if self.succeeded == 0:
            return 1
        return 2


def load_specs_from_directory(dir_path: Path) -> List[Dict[str, Any]]:
    """Load all YAML/JSON spec files from a directory, sorted alphabetically.

    Each returned dict includes a ``_source`` metadata key with the file path.
    Invalid files are included as error placeholders with ``_error`` set.
    """
    if not dir_path.is_dir():
        raise ConfigurationError(f"Spec directory does not exist: {dir_path}")

    specs: List[Dict[str, Any]] = []
    patterns = ["*.yaml", "*.yml", "*.json"]
    files: List[Path] = []
    for pattern in patterns:
        files.extend(dir_path.glob(pattern))
    files.sort(key=lambda p: p.name)

    for f in files:
        try:
            content = f.read_text(encoding="utf-8")
            if f.suffix in {".yaml", ".yml"}:
                data = yaml.safe_load(content)
            else:
                data = json.loads(content)
            if isinstance(data, dict):
                data["_source"] = str(f)
                specs.append(data)
        except Exception as exc:
            logger.warning("Failed to load spec from %s: %s", f, exc)
            # Include a placeholder so the failure is captured in the report
            specs.append({"_source": str(f), "_error": str(exc)})

    return specs


def run_batch(
    specs: Union[List[Dict[str, Any]], Path],
    config_overrides: Optional[Dict[str, Any]] = None,
    report_dir: Optional[Path] = None,
    on_progress: Optional[Callable[[int, int, str], None]] = None,
) -> BatchReport:
    """DC-111: Process specs with per-dashboard error isolation.

    Args:
        specs: A list of spec dicts or a directory Path to scan.
        config_overrides: Extra config keys merged into each workflow run.
        report_dir: Where to write the report JSON.
            Defaults to ``.startd8/reports/``.
        on_progress: Optional callback ``(current, total, message)``.

    Returns:
        BatchReport with per-dashboard outcomes.
    """
    if isinstance(specs, Path):
        specs = load_specs_from_directory(specs)

    report = BatchReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        total=len(specs),
    )

    workflow = DashboardCreatorWorkflow()

    for i, spec_dict in enumerate(specs):
        # Defensive copy — avoid mutating caller's dicts via pop()
        spec_dict = dict(spec_dict)
        source = spec_dict.pop("_source", f"spec[{i}]")
        load_error = spec_dict.pop("_error", None)

        title = spec_dict.get("title", source)
        uid = spec_dict.get("uid", "")

        if on_progress:
            try:
                on_progress(i + 1, len(specs), f"Processing {title}")
            except Exception:
                logger.debug("Progress callback error at %d/%d", i + 1, len(specs), exc_info=True)

        if load_error:
            report.dashboards.append(DashboardReport(
                uid=uid, title=title, source=source,
                success=False, error=f"Load error: {load_error}",
            ))
            report.failed += 1
            continue

        config: Dict[str, Any] = {"spec": spec_dict}
        if config_overrides:
            config.update(config_overrides)

        start = time.monotonic()
        try:
            result = workflow.run(config)
            duration_ms = int((time.monotonic() - start) * 1000)

            if result.success:
                report.dashboards.append(DashboardReport(
                    uid=result.output.get("uid", uid),
                    title=title,
                    source=source,
                    success=True,
                    json_path=result.output.get("json_path"),
                    duration_ms=duration_ms,
                ))
                report.succeeded += 1
            else:
                report.dashboards.append(DashboardReport(
                    uid=uid, title=title, source=source,
                    success=False, error=result.error,
                    duration_ms=duration_ms,
                ))
                report.failed += 1

        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            report.dashboards.append(DashboardReport(
                uid=uid, title=title, source=source,
                success=False, error=str(exc),
                duration_ms=duration_ms,
            ))
            report.failed += 1

    # Persist report
    _persist_report(report, report_dir)

    return report


def _persist_report(report: BatchReport, report_dir: Optional[Path]) -> Optional[Path]:
    """Write the batch report to a JSON file."""
    if report_dir is None:
        report_dir = Path(".startd8/reports")

    try:
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "dashboard-create-report.json"
        data = {
            "timestamp": report.timestamp,
            "total": report.total,
            "succeeded": report.succeeded,
            "failed": report.failed,
            "dashboards": [
                {
                    "uid": d.uid,
                    "title": d.title,
                    "source": d.source,
                    "status": "success" if d.success else "failure",
                    "duration_ms": d.duration_ms,
                    **({"output_path": d.json_path} if d.json_path else {}),
                    **({"error": d.error} if d.error else {}),
                }
                for d in report.dashboards
            ],
        }
        report_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Batch report written to %s", report_path)
        return report_path
    except OSError as exc:
        logger.warning("Failed to persist batch report: %s", exc)
        return None
