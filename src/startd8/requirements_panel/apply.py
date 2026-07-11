# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Approve = readiness-gated, atomic, one-shot markdown file-write (FR-RP-6).

Not a proposal kind — a plain markdown file at human privilege (NR-RP-3). Three CRP-driven properties:

* **Readiness-gated (R1-S2).** :func:`check_readiness` must pass; a blocked doc is never written.
* **Atomic / no-clobber (R1-S3).** ``O_CREAT | O_EXCL`` makes the create-if-absent test and the write a
  single kernel operation — a concurrent create between check and write cannot be overwritten (no TOCTOU).
* **One-shot lifecycle (R2-S4).** ``O_EXCL`` *also* means an existing versioned doc is **never**
  regenerated over — a second ``approve``/``elicit`` refuses and points to edit-in-place. The doc's
  purpose is to evolve via CRP/human; the capability writes v0.1 once, then gets out of the way.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from startd8.requirements_panel.models import RequirementDoc
from startd8.requirements_panel.readiness import check_readiness

__all__ = ["ApplyResult", "apply_requirements"]


@dataclass
class ApplyResult:
    written: bool
    path: Optional[Path] = None
    blockers: List[str] = field(default_factory=list)
    reason: str = ""

    @property
    def crp_handoff(self) -> str:
        """The ready-to-run dual-doc CRP command (FR-RP-6/9), printed on a successful write."""
        if not self.path:
            return ""
        return (
            f"/new-cnvrg-rvw-prmpt --requirements {self.path} "
            f"--plan <PLAN.md>   # external second gate"
        )


def apply_requirements(doc: RequirementDoc, target_path: Path | str) -> ApplyResult:
    """Readiness-gate, then atomically write *doc* to *target_path* iff it does not already exist."""
    readiness = check_readiness(doc)
    if not readiness.ok:
        return ApplyResult(
            written=False,
            blockers=readiness.blockers,
            reason="readiness gate blocked approve",
        )

    path = Path(target_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = doc.render().encode("utf-8")
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return ApplyResult(
            written=False,
            path=path,
            reason=(
                f"{path} already exists — a versioned requirements doc is never regenerated over "
                "(edit it in place / take it through CRP)"
            ),
        )
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
    except BaseException:
        try:
            os.unlink(path)
        except OSError:  # pragma: no cover
            pass
        raise
    return ApplyResult(written=True, path=path)
