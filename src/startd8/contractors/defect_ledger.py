"""Defect ledger — a consolidated, non-collapsed record of every quality flaw the
integration pipeline can detect (FR-B2 / FR-A3).

Motivation (see Summer2026 QUALITY_MASKING_REMEDIATION_REQUIREMENTS): the pipeline treats
"it parses" as "it's acceptable" — advisory downgrade clears import/lint errors, repair only
fires on FAILED checkpoints, and the benchmark compile gate collapses quality to "structural"
the moment a file compiles. The ledger is the antidote: it gathers all detected defects, by
category / severity / source, and keeps them — nothing is cleared or collapsed. It is additive
and read-only (it never mutates code or alters control flow), so it is safe to build on every
run; persistence/surfacing is gated by ``expose_defects`` at the call site.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..logging_config import get_logger

logger = get_logger(__name__)

# Checkpoint display-name -> defect category (defensive; unknown names fall back to "checkpoint").
_CHECKPOINT_CATEGORY = {
    "Syntax Check": "syntax",
    "Import Check": "import",
    "Lint Check": "lint",
    "Test Check": "test",
}


@dataclass
class DefectEntry:
    """One detected flaw. ``source`` is the detector that found it."""

    category: str          # syntax | import | lint | stub | duplicate | contract | semantic | ...
    severity: str          # error | warning | info
    source: str            # checkpoint name / "disk_compliance" / "semantic" / "security"
    file: str = ""
    message: str = ""
    line: Optional[int] = None


@dataclass
class DefectLedger:
    """All defects detected for one integration unit — nothing collapsed or cleared."""

    unit: str
    entries: List[DefectEntry] = field(default_factory=list)

    def add(self, **kw: Any) -> None:
        self.entries.append(DefectEntry(**kw))

    def by_category(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for e in self.entries:
            out[e.category] = out.get(e.category, 0) + 1
        return out

    def by_severity(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for e in self.entries:
            out[e.severity] = out.get(e.severity, 0) + 1
        return out

    def error_count(self) -> int:
        return sum(1 for e in self.entries if e.severity == "error")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "unit": self.unit,
            "total": len(self.entries),
            "by_category": self.by_category(),
            "by_severity": self.by_severity(),
            "entries": [asdict(e) for e in self.entries],
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Defect ledger — {self.unit}",
            f"total={len(self.entries)}  ·  by_severity={self.by_severity()}  ·  by_category={self.by_category()}",
            "",
            "| category | severity | source | file | message |",
            "|---|---|---|---|---|",
        ]
        for e in self.entries:
            msg = (e.message or "").replace("|", "\\|")[:120]
            lines.append(f"| {e.category} | {e.severity} | {e.source} | {e.file} | {msg} |")
        return "\n".join(lines) + "\n"


def collect_defects(
    unit_name: str,
    results: Optional[List[Any]] = None,
    compliance_results: Optional[Dict[str, Any]] = None,
    *,
    failed_status: Any = None,
) -> DefectLedger:
    """Build a :class:`DefectLedger` from checkpoint results + disk-compliance data.

    Args:
        unit_name: integration unit name.
        results: checkpoint results (objects with ``.name``, ``.status``, ``.errors``). Only
            FAILED entries become defects. ``failed_status`` is the CheckpointStatus.FAILED
            sentinel to compare against (passed in to avoid importing checkpoint here).
        compliance_results: the ``{rel_path: {ast_valid, stubs_remaining, ...}}`` dict produced
            by ``IntegrationEngine._run_semantic_checks`` (per-file disk compliance).
        failed_status: CheckpointStatus.FAILED (or any value comparing equal to a failed status).
    """
    ledger = DefectLedger(unit=unit_name)

    for r in results or []:
        status = getattr(r, "status", None)
        is_failed = (status == failed_status) if failed_status is not None else (
            getattr(status, "value", str(status)).upper() == "FAILED"
        )
        if not is_failed:
            continue
        name = getattr(r, "name", "checkpoint")
        category = _CHECKPOINT_CATEGORY.get(name, "checkpoint")
        errs = getattr(r, "errors", None) or [getattr(r, "message", "") or "failed"]
        for err in errs:
            ledger.add(category=category, severity="error", source=name,
                       message=str(err)[:200])

    for fpath, d in (compliance_results or {}).items():
        if not isinstance(d, dict):
            continue
        if not d.get("ast_valid", True):
            ledger.add(category="syntax", severity="error", source="disk_compliance",
                       file=fpath, message="ast invalid (file does not parse)")
        stubs = int(d.get("stubs_remaining", 0) or 0)
        if stubs > 0:
            ledger.add(category="stub", severity="warning", source="disk_compliance",
                       file=fpath, message=f"{stubs} stub(s) remaining")
        dups = int(d.get("duplicate_definitions", 0) or 0)
        if dups > 0:
            ledger.add(category="duplicate", severity="warning", source="disk_compliance",
                       file=fpath, message=f"{dups} duplicate definition(s)")
        ic = float(d.get("import_completeness", 1.0) or 1.0)
        if ic < 1.0:
            ledger.add(category="import", severity="warning", source="disk_compliance",
                       file=fpath, message=f"import_completeness={ic:.2f}")
        cc = float(d.get("contract_compliance", 1.0) or 1.0)
        if cc < 1.0:
            ledger.add(category="contract", severity="warning", source="disk_compliance",
                       file=fpath, message=f"contract_compliance={cc:.2f}")
        for si in d.get("semantic_issues", []) or []:
            if not isinstance(si, dict):
                continue
            ledger.add(
                category=si.get("category", "semantic"),
                severity=si.get("severity", "warning"),
                source="semantic", file=fpath,
                message=str(si.get("message", ""))[:200],
            )

    return ledger


def write_ledger(ledger: DefectLedger, project_root: Path) -> None:
    """Persist the ledger as JSON + markdown under ``.startd8/defect-ledger/`` (FR-B2)."""
    import json

    try:
        out_dir = Path(project_root) / ".startd8" / "defect-ledger"
        out_dir.mkdir(parents=True, exist_ok=True)
        safe = ledger.unit.replace("/", "_")
        (out_dir / f"{safe}.json").write_text(
            json.dumps(ledger.to_dict(), indent=2), encoding="utf-8")
        (out_dir / f"{safe}.md").write_text(ledger.to_markdown(), encoding="utf-8")
    except Exception:
        logger.warning("Failed to write defect ledger", exc_info=True)
