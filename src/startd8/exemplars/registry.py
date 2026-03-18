"""Exemplar Registry — searchable store of proven-correct exemplars (REQ-PEP-001).

The registry accumulates across runs and supports exact and partial fingerprint
matching.  It is persisted as JSON at ``{project_output_dir}/exemplar-registry.json``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from startd8.exemplars.models import (
    ConfigFingerprint,
    ExemplarEntry,
    MAX_REGISTRY_SIZE,
    SCHEMA_VERSION,
)
from startd8.logging_config import get_logger

logger = get_logger(__name__)

__all__ = ["ExemplarRegistry"]


class ExemplarRegistry:
    """Searchable registry of proven-correct (spec, code, score) tuples.

    Thread-safety: not thread-safe.  Intended for single-threaded
    post-mortem and injection flows.
    """

    def __init__(self, project_id: str = "") -> None:
        self.schema_version: str = SCHEMA_VERSION
        self.project_id: str = project_id
        self.last_updated: str = ""
        self._exemplars: List[ExemplarEntry] = []

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def add(self, entry: ExemplarEntry) -> None:
        """Add an exemplar, enforcing the size bound (REQ-PEP-001 §4)."""
        # Deduplicate by ID
        self._exemplars = [e for e in self._exemplars if e.id != entry.id]
        self._exemplars.append(entry)
        self._evict_if_needed()
        self.last_updated = datetime.now(timezone.utc).isoformat()

    def find_best_match(
        self,
        fingerprint: ConfigFingerprint,
    ) -> Optional[ExemplarEntry]:
        """Find the best exemplar for the given fingerprint (REQ-PEP-100).

        Matching order:
        1. Exact match on all 4 dimensions
        2. Partial match (language, file_type, archetype) with any transport

        Within each tier, rank by: maturity (desc) → disk_quality_score (desc)
        → cost_usd (asc) → timestamp (desc, most recent).
        """
        exact = [
            e for e in self._exemplars
            if e.fingerprint.matches_exact(fingerprint) and e.maturity >= 1
        ]
        if exact:
            return self._rank(exact)

        partial = [
            e for e in self._exemplars
            if e.fingerprint.matches_partial(fingerprint) and e.maturity >= 1
        ]
        if partial:
            return self._rank(partial)

        return None

    def get_match_type(self, fingerprint: ConfigFingerprint) -> str:
        """Return 'exact', 'partial', or 'none' for match type reporting."""
        for e in self._exemplars:
            if e.fingerprint.matches_exact(fingerprint) and e.maturity >= 1:
                return "exact"
        for e in self._exemplars:
            if e.fingerprint.matches_partial(fingerprint) and e.maturity >= 1:
                return "partial"
        return "none"

    def promote_maturity(self) -> List[Dict[str, Any]]:
        """Auto-promote maturity based on cross-run evidence (REQ-PEP-003).

        Returns a list of promotion events for logging/metrics.
        """
        promotions: List[Dict[str, Any]] = []

        # Group by fingerprint string
        by_fp: Dict[str, List[ExemplarEntry]] = {}
        for e in self._exemplars:
            key = str(e.fingerprint)
            by_fp.setdefault(key, []).append(e)

        for fp_str, entries in by_fp.items():
            # Level 1 → 2: same fingerprint, different runs
            level_1 = [e for e in entries if e.maturity == 1]
            if len(level_1) >= 2:
                run_ids = {e.source_run_id for e in level_1}
                if len(run_ids) >= 2:
                    for e in level_1:
                        e.maturity = 2
                        promotions.append({
                            "id": e.id,
                            "old_level": 1,
                            "new_level": 2,
                            "fingerprint": fp_str,
                        })

            # Level 2 → 3: 3+ confirmed exemplars (structural similarity
            # check deferred to Phase 6 — for now, promote on count alone)
            level_2 = [e for e in entries if e.maturity == 2]
            if len(level_2) >= 3:
                for e in level_2:
                    e.maturity = 3
                    promotions.append({
                        "id": e.id,
                        "old_level": 2,
                        "new_level": 3,
                        "fingerprint": fp_str,
                    })

        if promotions:
            self.last_updated = datetime.now(timezone.utc).isoformat()
            logger.info("Exemplar promotions: %d entries promoted", len(promotions))
        return promotions

    @property
    def exemplars(self) -> List[ExemplarEntry]:
        return list(self._exemplars)

    def __len__(self) -> int:
        return len(self._exemplars)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str | Path) -> None:
        """Write registry to JSON file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "last_updated": self.last_updated,
            "exemplars": [e.to_dict() for e in self._exemplars],
        }
        p.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        logger.info("Exemplar registry saved: %s (%d entries)", p, len(self._exemplars))

    @classmethod
    def load(cls, path: str | Path) -> ExemplarRegistry:
        """Load registry from JSON file.  Returns empty registry on error."""
        p = Path(path)
        if not p.is_file():
            logger.debug("No exemplar registry at %s, returning empty", p)
            return cls()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            reg = cls(project_id=data.get("project_id", ""))
            reg.schema_version = data.get("schema_version", SCHEMA_VERSION)
            reg.last_updated = data.get("last_updated", "")
            for entry_dict in data.get("exemplars", []):
                try:
                    reg._exemplars.append(ExemplarEntry.from_dict(entry_dict))
                except (TypeError, KeyError, ValueError) as exc:
                    logger.warning("Skipping malformed exemplar entry: %s", exc)
            return reg
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load exemplar registry from %s: %s", p, exc)
            return cls()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _rank(candidates: List[ExemplarEntry]) -> ExemplarEntry:
        """Rank candidates by maturity → score → cost → recency."""
        return max(
            candidates,
            key=lambda e: (
                e.maturity,
                e.scores.disk_quality_score,
                -e.scores.cost_usd,
                e.timestamp,
            ),
        )

    def _evict_if_needed(self) -> None:
        """Evict lowest-maturity, oldest entries if over MAX_REGISTRY_SIZE."""
        while len(self._exemplars) > MAX_REGISTRY_SIZE:
            # O(n) eviction: find the lowest-ranked entry and remove it
            evicted = min(self._exemplars, key=lambda e: (e.maturity, e.timestamp))
            self._exemplars.remove(evicted)
            logger.info("Evicted exemplar %s (maturity=%d)", evicted.id, evicted.maturity)
