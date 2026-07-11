# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Out-of-band staging for screen candidates (FR-MS-7) + missing-only dedupe (FR-MS-3).

The store is built on the shared ``persona_drafting.JsonSessionStore`` (the same base the Requirements
Panel uses) — atomic write, ``0700`` dir, sorted/diffable JSON, session GC, path-traversal guard — so
this sibling reuses the toolkit rather than hand-rolling a third copy. Dedupe (FR-MS-3) matches by the
extractor-derived slug (``nfkd_kebab``), so a candidate colliding with an already-authored screen is
dropped at stage time, not discovered at apply (R1-F5/R1-S7).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional, Set

from startd8.persona_drafting.staging import JsonSessionStore

from startd8.manifest_suggester.models import ScreenCandidate

__all__ = [
    "SCREENS_DIR",
    "ScreenCandidateStore",
    "latest_session",
    "session_ids",
    "dedupe_missing",
]

SCREENS_DIR = Path(".startd8") / "manifest-suggester" / "screens"


class ScreenCandidateStore(JsonSessionStore):
    """Persist / load one suggestion session's staged screen candidates."""

    SUBDIR = SCREENS_DIR
    FILE_PREFIX = "screens-"
    RECORD_CLS = ScreenCandidate

    def save(self, candidates: List[ScreenCandidate]) -> None:  # type: ignore[override]
        super().save(candidates)

    def load(self) -> List[ScreenCandidate]:  # type: ignore[override]
        return super().load()


def session_ids(project_root: Path | str) -> List[str]:
    return ScreenCandidateStore.session_ids(project_root)


def latest_session(project_root: Path | str) -> Optional[str]:
    return ScreenCandidateStore.latest_session(project_root)


def dedupe_missing(
    candidates: Iterable[ScreenCandidate], existing_slugs: Iterable[str]
) -> List[ScreenCandidate]:
    """Keep only candidates whose slug is not already present (FR-MS-3 — augment, don't duplicate)."""
    seen: Set[str] = {s for s in existing_slugs}
    out: List[ScreenCandidate] = []
    for c in candidates:
        if c.slug in seen:
            continue
        seen.add(c.slug)  # also dedupe within the incoming batch
        out.append(c)
    return out
