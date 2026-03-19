"""Tests for SQLite patterns — sqlite3, Microsoft.Data.Sqlite, better-sqlite3."""

import pytest

from startd8.query_prime.models import DatabaseType
from startd8.query_prime.patterns import DatabasePatternRegistry


class TestSQLitePatterns:
    def test_sqlite_python_registered(self):
        pattern = DatabasePatternRegistry.get(DatabaseType.SQLITE, "python")
        assert pattern is not None
        assert pattern.client_library == "sqlite3"

    def test_sqlite_csharp_registered(self):
        pattern = DatabasePatternRegistry.get(DatabaseType.SQLITE, "csharp")
        assert pattern is not None

    def test_sqlite_nodejs_registered(self):
        pattern = DatabasePatternRegistry.get(DatabaseType.SQLITE, "nodejs")
        assert pattern is not None

    def test_sqlite_python_safe_patterns(self):
        pattern = DatabasePatternRegistry.get(DatabaseType.SQLITE, "python")
        text = 'cursor.execute("SELECT * FROM t WHERE id = ?", (id,))'
        assert any(p.search(text) for p in pattern.safe_patterns)

    def test_sqlite_python_unsafe_fstring(self):
        pattern = DatabasePatternRegistry.get(DatabaseType.SQLITE, "python")
        text = 'f"SELECT * FROM t WHERE id = \'{id}\'"'
        assert any(p.search(text) for p in pattern.unsafe_patterns)
