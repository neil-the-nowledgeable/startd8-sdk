"""Repair-retry orchestration engine (Inc 6, FR-8/FR-9/FR-10).

Drives the full deterministic, no-LLM pass: load → **live-state pre-filter**
(R4-S1) → classify → dispatch (rewrite / scaffold / worklist) → write →
re-validate + scoped rollback (Inc 5) → emit report + worklist under the run dir
(R5-F3). Zero LLM calls.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union

from ...logging_config import get_logger
from .classifier import RetryClass, classify
from .models import RetryViolation
from .report_loader import _resolve_report, load_violations
from .revalidate import balanced_syntax_ok, unresolvable_index
from .rewriter import Rewrite, apply_rewrite, compute_rewrite
from .scaffold import scaffold_barrel, scaffold_cofile
from .search import DiskTargetSearch

logger = get_logger(__name__)


@dataclass
class RetryReport:
    run_dir: Path
    resolution: str
    rewritten: int = 0
    scaffolded: int = 0
    already_resolved: int = 0
    rolled_back: int = 0
    needs_regen: int = 0
    dispositions: List[dict] = field(default_factory=list)
    worklist: List[dict] = field(default_factory=list)
    report_path: Optional[Path] = None
    worklist_path: Optional[Path] = None
    summary_path: Optional[Path] = None


def _to_gen_rel(file_path: str) -> str:
    s = file_path.replace("\\", "/")
    return s.split("/generated/", 1)[1] if "/generated/" in s else s.lstrip("./")


class RepairRetryEngine:
    """Deterministic post-job repair driven by a prime-postmortem report."""

    def __init__(self, report_or_dir: Union[str, Path]):
        self._report = _resolve_report(report_or_dir)
        # <run>/plan-ingestion/{prime-postmortem-report.json, generated/}
        self._ingestion = self._report.parent
        self._generated_root = self._ingestion / "generated"
        # Resolved form for relative-path display (the scaffold guard returns
        # realpath-resolved paths; on macOS /var -> /private/var would otherwise
        # break a relative_to against the unresolved root).
        self._gen_resolved = self._generated_root.resolve(strict=False)
        self._search = DiskTargetSearch(self._generated_root)

    def _rel_display(self, p: Path) -> str:
        try:
            return str(p.resolve(strict=False).relative_to(self._gen_resolved))
        except ValueError:
            return p.name

    # ── helpers ──────────────────────────────────────────────────────────────

    def _read(self, rel: str) -> Optional[str]:
        p = self._generated_root / rel
        try:
            return p.read_text(encoding="utf-8")
        except OSError:
            return None

    def _current_unresolved(self, rel: str, content: str) -> set:
        return unresolvable_index({rel: content}, str(self._generated_root))

    # ── main ─────────────────────────────────────────────────────────────────

    def run(self, *, scaffold: bool = True) -> RetryReport:
        violations = load_violations(self._report)
        # normalize importer paths to generated-relative
        violations = [
            RetryViolation(
                v.feature_id,
                _to_gen_rel(v.file_path),
                v.category,
                v.specifier,
                v.message,
                v.parse_ok,
            )
            for v in violations
        ]

        report = RetryReport(run_dir=self._ingestion, resolution="")
        # per-importer accumulation of rewrites (for batched apply + rollback)
        rewrites_by_file: Dict[str, List[Rewrite]] = {}
        pre_images: Dict[str, str] = {}
        survivors: List[RetryViolation] = []

        # 1. live-state pre-filter (R4-S1): drop violations already fixed on disk.
        for v in violations:
            content = self._read(v.file_path)
            if content is None:
                report.dispositions.append(_disp(v, "needs_regen", "importer_missing"))
                report.worklist.append(_wl_feature(v, "importer_missing"))
                report.needs_regen += 1
                continue
            if v.parse_ok and (
                v.file_path,
                v.specifier,
            ) not in self._current_unresolved(v.file_path, content):
                report.already_resolved += 1
                report.dispositions.append(_disp(v, "already_resolved", ""))
                continue
            survivors.append(v)
            pre_images.setdefault(v.file_path, content)

        # 2. classify + dispatch survivors.
        for v in survivors:
            res = classify(v, self._search)
            if res.retry_class == RetryClass.REWRITABLE_PATH:
                rw = compute_rewrite(v, self._search)
                if rw is None:
                    report.dispositions.append(
                        _disp(v, "needs_regen", "unresolvable_form")
                    )
                    report.worklist.append(_wl_feature(v, "unresolvable_form"))
                    report.needs_regen += 1
                    continue
                rewrites_by_file.setdefault(v.file_path, []).append(rw)
                report.dispositions.append(
                    _disp(v, "rewritten", f"{rw.strategy} -> {rw.target_specifier}")
                )
            elif res.retry_class == RetryClass.SCAFFOLDABLE_COFILE:
                self._do_cofile(v, scaffold, report)
            elif res.retry_class == RetryClass.SCAFFOLDABLE_BARREL:
                self._do_barrel(v, res.target, scaffold, report)
            else:  # NEEDS_REGEN
                report.dispositions.append(_disp(v, "needs_regen", res.reason))
                report.worklist.append(_wl_feature(v, res.reason))
                report.needs_regen += 1

        # 3. apply rewrites per importer + re-validate (content+syntax) + rollback.
        for rel, rws in rewrites_by_file.items():
            pre = pre_images[rel]
            new_content = pre
            for rw in rws:
                new_content, _ = apply_rewrite(new_content, rw)
            pre_unres = self._current_unresolved(rel, pre)
            post_unres = self._current_unresolved(rel, new_content)
            introduced = post_unres - pre_unres  # strict-subset identity (R5-S3)
            if introduced or not balanced_syntax_ok(new_content):
                # roll back this file (replay kept subset = none on a syntax break)
                report.rolled_back += len(rws)
                for rw in rws:
                    _retag(
                        report,
                        rel,
                        rw.specifier,
                        "rolled_back",
                        "introduced_violation" if introduced else "syntax_break",
                    )
                    report.worklist.append(
                        {
                            "feature_id": _feat_for(report, rel, rw.specifier),
                            "importer_file": rel,
                            "missing_target": rw.specifier,
                            "reason": "rolled_back",
                            "task_filter_token": _feat_for(report, rel, rw.specifier),
                        }
                    )
                continue
            (self._generated_root / rel).write_text(new_content, encoding="utf-8")
            report.rewritten += len(rws)

        # 4. resolution verdict (R1-S3: imports cleared, NOT a PASS claim).
        total = len(report.dispositions)
        resolved = report.rewritten + report.scaffolded + report.already_resolved
        report.resolution = f"{resolved}/{total} resolved"

        self._emit(report)
        return report

    def _do_cofile(
        self, v: RetryViolation, scaffold: bool, report: RetryReport
    ) -> None:
        if not scaffold:
            report.dispositions.append(
                _disp(v, "unscaffolded_asset", "scaffold_disabled")
            )
            report.worklist.append(_wl_asset(v, "scaffold_disabled"))
            return
        importer_abs = self._generated_root / v.file_path
        created = scaffold_cofile(importer_abs, v.specifier, self._generated_root)
        if created is None:
            report.dispositions.append(
                _disp(v, "unscaffolded_asset", "confinement_or_exists")
            )
            report.worklist.append(_wl_asset(v, "confinement_or_exists"))
            return
        # verify the import now resolves (R4-S2 re-validation for scaffolds)
        content = self._read(v.file_path) or ""
        if (v.file_path, v.specifier) in self._current_unresolved(v.file_path, content):
            created.unlink(missing_ok=True)  # scaffold didn't help -> roll back
            report.rolled_back += 1
            report.dispositions.append(
                _disp(v, "unscaffolded_asset", "scaffold_did_not_resolve")
            )
            report.worklist.append(_wl_asset(v, "scaffold_did_not_resolve"))
            return
        report.scaffolded += 1
        report.dispositions.append(_disp(v, "scaffolded", self._rel_display(created)))

    def _do_barrel(
        self, v: RetryViolation, directory, scaffold: bool, report: RetryReport
    ) -> None:
        if not scaffold:
            report.dispositions.append(
                _disp(v, "unscaffolded_asset", "scaffold_disabled")
            )
            report.worklist.append(_wl_asset(v, "scaffold_disabled"))
            return
        created = (
            scaffold_barrel(directory, self._generated_root) if directory else None
        )
        if created is None:
            report.dispositions.append(_disp(v, "needs_regen", "barrel_abstained"))
            report.worklist.append(_wl_feature(v, "barrel_abstained"))
            report.needs_regen += 1
            return
        content = self._read(v.file_path) or ""
        if (v.file_path, v.specifier) in self._current_unresolved(v.file_path, content):
            created.unlink(missing_ok=True)
            report.rolled_back += 1
            report.dispositions.append(
                _disp(v, "needs_regen", "barrel_did_not_resolve")
            )
            report.worklist.append(_wl_feature(v, "barrel_did_not_resolve"))
            report.needs_regen += 1
            return
        report.scaffolded += 1
        report.dispositions.append(_disp(v, "scaffolded", self._rel_display(created)))

    def _emit(self, report: RetryReport) -> None:
        out_dir = self._ingestion / "repair-retry"
        out_dir.mkdir(parents=True, exist_ok=True)
        report.report_path = (out_dir / "repair-retry-report.json").resolve()
        report.worklist_path = (out_dir / "regen-worklist.json").resolve()
        report.summary_path = (out_dir / "repair-retry-summary.md").resolve()

        report.report_path.write_text(
            json.dumps(
                {
                    "resolution": report.resolution,
                    "rewritten": report.rewritten,
                    "scaffolded": report.scaffolded,
                    "already_resolved": report.already_resolved,
                    "rolled_back": report.rolled_back,
                    "needs_regen": report.needs_regen,
                    "dispositions": report.dispositions,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        report.worklist_path.write_text(
            json.dumps({"worklist": report.worklist}, indent=2), encoding="utf-8"
        )
        report.summary_path.write_text(
            f"# Repair-Retry Summary\n\n- Resolution: {report.resolution}\n"
            f"- rewritten: {report.rewritten}\n- scaffolded: {report.scaffolded}\n"
            f"- already_resolved: {report.already_resolved}\n- rolled_back: {report.rolled_back}\n"
            f"- needs_regen: {report.needs_regen}\n\n"
            "NOTE: resolution counts cleared `unresolvable_import` violations only; it is NOT a postmortem PASS.\n",
            encoding="utf-8",
        )


# ── disposition / worklist helpers ──────────────────────────────────────────


def _disp(v: RetryViolation, disposition: str, detail: str) -> dict:
    return {
        "feature_id": v.feature_id,
        "importer_file": v.file_path,
        "specifier": v.specifier,
        "disposition": disposition,
        "detail": detail,
    }


def _wl_feature(v: RetryViolation, reason: str) -> dict:
    return {
        "feature_id": v.feature_id,
        "importer_file": v.file_path,
        "missing_target": v.specifier,
        "reason": reason,
        "task_filter_token": v.feature_id,
    }


def _wl_asset(v: RetryViolation, reason: str) -> dict:
    return {
        "owning_feature_id": v.feature_id,
        "importer_file": v.file_path,
        "missing_target": v.specifier,
        "reason": reason,
    }


def _retag(
    report: RetryReport, rel: str, specifier: str, disposition: str, detail: str
) -> None:
    for d in report.dispositions:
        if d["importer_file"] == rel and d["specifier"] == specifier:
            d["disposition"] = disposition
            d["detail"] = detail


def _feat_for(report: RetryReport, rel: str, specifier: str) -> str:
    for d in report.dispositions:
        if d["importer_file"] == rel and d["specifier"] == specifier:
            return d["feature_id"]
    return ""
