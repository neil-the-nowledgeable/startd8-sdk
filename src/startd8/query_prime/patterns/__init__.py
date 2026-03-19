"""Database pattern registry for Query Prime.

Provides safe/unsafe regex patterns per database+language combination,
enabling security checks to distinguish parameterized queries from
injection-vulnerable string interpolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Pattern, Tuple

from ..models import DatabaseType


@dataclass(frozen=True)
class DatabasePattern:
    """Safe and unsafe query patterns for a specific database+language pair."""

    database: DatabaseType
    client_library: str
    language: str  # "csharp", "python", "nodejs", "go", "java"
    safe_param_syntax: Tuple[str, ...] = ()
    safe_patterns: Tuple[Pattern[str], ...] = ()
    unsafe_patterns: Tuple[Pattern[str], ...] = ()
    credential_variable_names: Tuple[str, ...] = ()
    resource_creation_patterns: Tuple[Pattern[str], ...] = ()
    dispose_patterns: Tuple[Pattern[str], ...] = ()
    health_check_query: str = "SELECT 1"


class DatabasePatternRegistry:
    """Registry of database-specific safe/unsafe patterns."""

    _patterns: Dict[Tuple[str, str], DatabasePattern] = {}

    @classmethod
    def register(cls, pattern: DatabasePattern) -> None:
        """Register a database pattern for a database+language pair."""
        key = (pattern.database.value, pattern.language)
        cls._patterns[key] = pattern

    @classmethod
    def get(
        cls, database: DatabaseType | str, language: str
    ) -> Optional[DatabasePattern]:
        """Get pattern for a database+language pair."""
        db_val = database.value if isinstance(database, DatabaseType) else database
        return cls._patterns.get((db_val, language))

    @classmethod
    def get_all_for_database(
        cls, database: DatabaseType | str
    ) -> List[DatabasePattern]:
        """Get all registered patterns for a database (any language)."""
        db_val = database.value if isinstance(database, DatabaseType) else database
        return [p for (db, _), p in cls._patterns.items() if db == db_val]

    @classmethod
    def clear(cls) -> None:
        """Clear all registered patterns (for testing)."""
        cls._patterns.clear()


# Import pattern modules to trigger auto-registration
from . import mysql, postgresql, redis, spanner, sqlite  # noqa: E402, F401
