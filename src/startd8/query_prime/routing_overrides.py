"""Routing overrides for Query Prime — REQ-KQP-601.

Persists per-work-item or per-pattern tier overrides to
.startd8/query-prime-routing-overrides.json.

Loaded at engine init time. Router checks overrides dict (in-memory)
per-call — no file I/O in the hot path.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Optional

from startd8.complexity.models import ComplexityTier
from startd8.logging_config import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class RoutingOverride:
    """A single routing override entry."""

    pattern: str  # work_item_id prefix or glob pattern
    minimum_tier: str  # ComplexityTier value
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "RoutingOverride":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class RoutingOverrideStore:
    """In-memory store for routing overrides with JSON persistence.

    Loaded once at engine init. Lookups are O(n) on number of overrides
    (expected to be small, <50).

    Args:
        path: Path to the JSON persistence file.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path or Path(".startd8/query-prime-routing-overrides.json")
        self._overrides: Dict[str, RoutingOverride] = {}

    def load(self) -> None:
        """Load overrides from disk. No-op if file doesn't exist."""
        if not self._path.is_file():
            return
        try:
            data = json.loads(self._path.read_text())
            self._overrides = {
                k: RoutingOverride.from_dict(v)
                for k, v in data.get("overrides", {}).items()
            }
            logger.info(
                "Loaded %d routing overrides from %s",
                len(self._overrides), self._path,
            )
        except (json.JSONDecodeError, OSError, TypeError) as exc:
            logger.warning("Failed to load routing overrides: %s", exc)

    def save(self) -> None:
        """Persist overrides to disk. Advisory — never fails a run."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "overrides": {k: v.to_dict() for k, v in self._overrides.items()},
            }
            self._path.write_text(json.dumps(data, indent=2) + "\n")
        except OSError as exc:
            logger.warning("Failed to save routing overrides: %s", exc)

    def get_minimum_tier(self, work_item_id: str) -> Optional[ComplexityTier]:
        """Check if a work item has a routing override.

        Matches by exact work_item_id or prefix pattern.

        Args:
            work_item_id: The work item identifier to check.

        Returns:
            Minimum ComplexityTier if overridden, None otherwise.
        """
        # Exact match first
        override = self._overrides.get(work_item_id)
        if override:
            try:
                return ComplexityTier(override.minimum_tier)
            except ValueError:
                return None

        # Prefix match
        for pattern, override in self._overrides.items():
            if work_item_id.startswith(pattern):
                try:
                    return ComplexityTier(override.minimum_tier)
                except ValueError:
                    continue

        return None

    def add(self, override: RoutingOverride) -> None:
        """Add or update a routing override."""
        self._overrides[override.pattern] = override

    def remove(self, pattern: str) -> bool:
        """Remove a routing override by pattern. Returns True if found."""
        return self._overrides.pop(pattern, None) is not None

    @property
    def overrides(self) -> Dict[str, RoutingOverride]:
        """Read-only access to overrides."""
        return dict(self._overrides)

    def __len__(self) -> int:
        return len(self._overrides)
