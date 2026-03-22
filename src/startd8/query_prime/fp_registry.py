"""False positive registry for Query Prime — REQ-KQP-200 through 202.

Tracks recurring false positives and auto-suppresses after a configurable
threshold of consecutive occurrences. Injection findings are NEVER suppressed.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from startd8.logging_config import get_logger

from .models import SecurityCheckType, SecurityFinding

logger = get_logger(__name__)


@dataclass
class FPEntry:
    """A tracked false positive pattern."""

    pattern_hash: str
    check_type: str
    message: str
    database: str
    framework: str
    occurrences: int = 0
    suppressed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "FPEntry":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class FalsePositiveRegistry:
    """Registry that accumulates and auto-suppresses recurring false positives.

    Injection findings are never suppressed regardless of occurrence count.

    Args:
        path: Path to the JSON persistence file.
        suppression_threshold: Number of consecutive occurrences before
            auto-suppression. Default: 3.
    """

    SUPPRESSION_THRESHOLD: int = 3

    def __init__(
        self,
        path: Optional[Path] = None,
        suppression_threshold: Optional[int] = None,
    ) -> None:
        self._path = path or Path(".startd8/query-prime-false-positives.json")
        self._entries: Dict[str, FPEntry] = {}
        if suppression_threshold is not None:
            self.SUPPRESSION_THRESHOLD = suppression_threshold

    def load(self) -> None:
        """Load registry from disk. No-op if file doesn't exist."""
        if not self._path.is_file():
            return
        try:
            data = json.loads(self._path.read_text())
            self._entries = {
                k: FPEntry.from_dict(v)
                for k, v in data.get("entries", {}).items()
            }
            logger.info(
                "Loaded %d FP registry entries from %s",
                len(self._entries), self._path,
            )
        except (json.JSONDecodeError, OSError, TypeError) as exc:
            logger.warning("Failed to load FP registry: %s", exc)

    def save(self) -> None:
        """Persist registry to disk. Advisory — never fails a run."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "entries": {k: v.to_dict() for k, v in self._entries.items()},
            }
            self._path.write_text(json.dumps(data, indent=2) + "\n")
        except OSError as exc:
            logger.warning("Failed to save FP registry: %s", exc)

    def register(
        self,
        finding: SecurityFinding,
        database: str = "",
        framework: str = "",
    ) -> None:
        """Register a finding as a potential false positive.

        Increments the occurrence counter. When the threshold is reached
        and the finding is NOT an injection, marks it as suppressed.

        Args:
            finding: The security finding to track.
            database: Database context for the finding.
            framework: Framework context (e.g. "npgsql", "ef-core").
        """
        key = finding.pattern_hash
        if not key:
            return

        if key in self._entries:
            entry = self._entries[key]
            self._entries[key] = FPEntry(
                pattern_hash=entry.pattern_hash,
                check_type=entry.check_type,
                message=entry.message,
                database=entry.database or database,
                framework=entry.framework or framework,
                occurrences=entry.occurrences + 1,
                suppressed=self._should_suppress(
                    finding.check_type, entry.occurrences + 1,
                ),
            )
        else:
            self._entries[key] = FPEntry(
                pattern_hash=key,
                check_type=finding.check_type.value,
                message=finding.message,
                database=database,
                framework=framework,
                occurrences=1,
                suppressed=False,
            )

    def is_suppressed(self, finding: SecurityFinding) -> bool:
        """Check if a finding should be suppressed.

        Injection findings are NEVER suppressed.

        Args:
            finding: The finding to check.

        Returns:
            True if the finding is suppressed.
        """
        if finding.check_type == SecurityCheckType.INJECTION:
            return False
        key = finding.pattern_hash
        if not key:
            return False
        entry = self._entries.get(key)
        return entry is not None and entry.suppressed

    def _should_suppress(
        self, check_type: SecurityCheckType, occurrences: int,
    ) -> bool:
        """Determine if a finding should be suppressed based on rules."""
        if check_type == SecurityCheckType.INJECTION:
            return False
        return occurrences >= self.SUPPRESSION_THRESHOLD

    @property
    def entries(self) -> Dict[str, FPEntry]:
        """Read-only access to registry entries."""
        return dict(self._entries)

    def __len__(self) -> int:
        return len(self._entries)
