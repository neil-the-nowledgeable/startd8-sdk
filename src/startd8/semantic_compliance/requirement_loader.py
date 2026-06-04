# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Requirement retrieval + seed-task join (FR-1).

Loads ``prime-context-seed*.json`` from the run dir itself (the post-mortem does not persist it),
indexes by feature id, and joins a feature to its requirement — **corroborated** by file overlap so
a mis-join never produces a confident-wrong verdict (S-R1-4). On multi-seed match, selects the
latest by mtime (R1-S5).

The real seed shape (verified): ``tasks[].config.context`` carries ``feature_id``, ``target_files``,
``negative_scope``, ``api_signatures``, ``language_id``, ``requirement_ids``; the requirement prose
is ``config.task_description`` (``requirements_text`` is often empty).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..logging_config import get_logger
from .models import InconclusiveReason, RequirementRef

logger = get_logger(__name__)

SEED_GLOB = "prime-context-seed*.json"
_MAX_EXCERPT_CHARS = 4000  # bound the requirement text in the report (R4-S3 spirit)


@dataclass
class LoadedRequirement:
    """Full requirement context for one feature (loader-internal; feeds the rubric)."""

    feature_id: str
    requirement_text: str
    target_files: List[str] = field(default_factory=list)
    negative_scope: List[str] = field(default_factory=list)
    api_signatures: List[str] = field(default_factory=list)
    requirement_ids: List[str] = field(default_factory=list)
    language: str = "python"

    def to_ref(self, corroborated: bool) -> RequirementRef:
        excerpt = self.requirement_text[:_MAX_EXCERPT_CHARS] or None
        return RequirementRef(
            seed_task_id=self.feature_id,
            text_excerpt=excerpt,
            join_corroborated=corroborated,
        )


def _select_seed_file(output_dir: Path) -> Optional[Path]:
    """Pick the seed file; on multiple matches use the latest by mtime (R1-S5)."""
    matches = sorted(
        output_dir.glob(SEED_GLOB),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else None


def _requirement_text(task: dict) -> str:
    cfg = task.get("config", {}) or {}
    parts = [cfg.get("requirements_text", ""), cfg.get("task_description", "")]
    return "\n".join(p for p in parts if p).strip()


class SeedIndex:
    """Feature-id → :class:`LoadedRequirement`, built from one run's seed file."""

    def __init__(self) -> None:
        self._by_id: Dict[str, LoadedRequirement] = {}
        self._collisions: set[str] = set()
        self.seed_path: Optional[Path] = None

    @classmethod
    def load(cls, output_dir: Path) -> "SeedIndex":
        idx = cls()
        seed = _select_seed_file(Path(output_dir))
        if seed is None:
            logger.info("SCR: no %s in %s — requirements unavailable", SEED_GLOB, output_dir)
            return idx
        idx.seed_path = seed
        try:
            data = json.loads(seed.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("SCR: could not parse seed %s", seed)
            return idx

        for task in data.get("tasks", []) or []:
            ctx = (task.get("config", {}) or {}).get("context", {}) or {}
            # The post-mortem keys features by ``task_id`` (e.g. "PI-001"); the seed also carries a
            # *design* ``context.feature_id`` (e.g. "F-201") that can DIVERGE (run-029). Register the
            # task under BOTH ids so a lookup by either resolves; ``task_id`` is the canonical key
            # since it is what the post-mortem (and thus the SCR) looks up by.
            task_id = task.get("task_id")
            ctx_fid = ctx.get("feature_id")
            keys = [str(k) for k in (task_id, ctx_fid) if k]
            if not keys:
                continue
            loaded = LoadedRequirement(
                feature_id=keys[0],  # task_id preferred — matches the post-mortem feature_id
                requirement_text=_requirement_text(task),
                target_files=list(ctx.get("target_files", []) or []),
                negative_scope=list(ctx.get("negative_scope", []) or []),
                api_signatures=list(ctx.get("api_signatures", []) or []),
                requirement_ids=list(ctx.get("requirement_ids", []) or []),
                language=str(ctx.get("language_id", "python") or "python"),
            )
            for key in keys:
                existing = idx._by_id.get(key)
                if existing is not None and existing.feature_id != loaded.feature_id:
                    idx._collisions.add(key)  # two distinct tasks claim one id → ambiguous (R1-S5)
                else:
                    idx._by_id[key] = loaded
        return idx

    def lookup(
        self,
        feature_id: str,
        generated_files: Optional[List[str]] = None,
    ) -> Tuple[Optional[LoadedRequirement], Optional[InconclusiveReason]]:
        """Resolve a feature's requirement, corroborating the join (S-R1-4).

        Returns ``(requirement, None)`` on a corroborated join, or ``(None, reason)`` when the
        requirement is unavailable or the join is ambiguous.
        """
        if feature_id in self._collisions:
            return None, InconclusiveReason.REQUIREMENT_JOIN_AMBIGUOUS
        loaded = self._by_id.get(feature_id)
        if loaded is None:
            return None, InconclusiveReason.REQUIREMENT_TEXT_UNAVAILABLE
        if not loaded.requirement_text:
            return None, InconclusiveReason.REQUIREMENT_TEXT_UNAVAILABLE

        # Corroborate: if both file lists are present they must overlap; an exact feature-id match
        # with no files to compare is itself the (weaker) corroboration.
        if generated_files and loaded.target_files:
            overlap = {Path(f).name for f in generated_files} & {
                Path(f).name for f in loaded.target_files
            }
            if not overlap:
                return None, InconclusiveReason.REQUIREMENT_JOIN_AMBIGUOUS
        return loaded, None

    def corroborated(self, feature_id: str, generated_files: Optional[List[str]]) -> bool:
        loaded, reason = self.lookup(feature_id, generated_files)
        return loaded is not None and reason is None
