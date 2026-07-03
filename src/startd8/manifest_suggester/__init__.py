# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Manifest Suggester — persona-driven screen (pages/views) suggestion.

The second sibling built on the ``persona_drafting`` toolkit: it drafts **composite views + non-entity
pages** (never entity CRUD, which the `$0` cascade already generates) for human approval, applied
through the existing ``manifest`` proposal kind. **Scope lock:** it proposes *which screens + their
structure* (bucket-1 authoring), never the screens' real content (bucket-4).

This increment ships the **deterministic `$0` core** — the schema-grounded baseline, the grounding
guard, and staging (reusing the toolkit). The paid role pass (FR-MS-2), the accumulation-aware apply
seam (FR-MS-5/7, R2-S1), and the ``startd8 screens`` CLI land in the next increment. See
``docs/design/kickoff/MANIFEST_SUGGESTER_{REQUIREMENTS,PLAN}.md``.
"""

from __future__ import annotations

from startd8.manifest_suggester.baseline import (
    baseline_views,
    build_graph,
    pick_root,
)
from startd8.manifest_suggester.grounding import GroundResult, ground
from startd8.manifest_suggester.models import (
    KIND_PAGE,
    KIND_VIEW,
    PROV_BASELINE,
    PROV_ESTIMATE,
    ScreenCandidate,
)
from startd8.manifest_suggester.store import (
    ScreenCandidateStore,
    dedupe_missing,
)

__all__ = [
    "ScreenCandidate",
    "KIND_PAGE",
    "KIND_VIEW",
    "PROV_BASELINE",
    "PROV_ESTIMATE",
    "baseline_views",
    "build_graph",
    "pick_root",
    "ground",
    "GroundResult",
    "ScreenCandidateStore",
    "dedupe_missing",
    # paid role pass (lazy)
    "suggest_screens",
    "SuggestRun",
]


def __getattr__(name: str):
    """Lazy-load the paid role pass (keeps the deterministic surface import-cheap)."""
    if name in ("suggest_screens", "SuggestRun"):
        from startd8.manifest_suggester import suggest

        return getattr(suggest, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
