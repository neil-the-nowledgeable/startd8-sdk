# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Out-of-band staging for elicited requirement candidates (FR-RP-8 / FR-PD-3).

Now built on the shared ``persona_drafting.JsonSessionStore`` base (FR-PD-2) — same on-disk path
(``.startd8/requirements-panel/candidates/``, no migration), and it **gains the session GC** the
hand-rolled copy lacked (backlog #9). ``session_ids`` / ``latest_session`` are provided as module-level
functions for CLI back-compat.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from startd8.persona_drafting.staging import JsonSessionStore
from startd8.requirements_panel.models import RequirementCandidate

__all__ = ["CANDIDATES_DIR", "CandidateStore", "latest_session", "session_ids"]

CANDIDATES_DIR = Path(".startd8") / "requirements-panel" / "candidates"


class CandidateStore(JsonSessionStore):
    """Persist / load one elicitation session's staged candidates."""

    SUBDIR = CANDIDATES_DIR
    FILE_PREFIX = "candidates-"
    RECORD_CLS = RequirementCandidate

    def save(self, candidates: List[RequirementCandidate]) -> None:  # type: ignore[override]
        super().save(candidates)

    def load(self) -> List[RequirementCandidate]:  # type: ignore[override]
        return super().load()


def session_ids(project_root: Path | str) -> List[str]:
    return CandidateStore.session_ids(project_root)


def latest_session(project_root: Path | str) -> Optional[str]:
    return CandidateStore.latest_session(project_root)
