"""Tests for PostgreSQL patterns — Npgsql, psycopg2, node-postgres."""

import pytest

from startd8.query_prime.models import DatabaseType
from startd8.query_prime.patterns import DatabasePatternRegistry


class TestPostgresqlPatterns:
    def test_npgsql_registered(self):
        pattern = DatabasePatternRegistry.get(DatabaseType.POSTGRESQL, "csharp")
        assert pattern is not None
        assert pattern.client_library == "Npgsql"

    def test_psycopg2_registered(self):
        pattern = DatabasePatternRegistry.get(DatabaseType.POSTGRESQL, "python")
        assert pattern is not None
        assert pattern.client_library == "psycopg2"

    def test_node_pg_registered(self):
        pattern = DatabasePatternRegistry.get(DatabaseType.POSTGRESQL, "nodejs")
        assert pattern is not None
        assert pattern.client_library == "pg"

    def test_npgsql_safe_patterns_match(self):
        pattern = DatabasePatternRegistry.get(DatabaseType.POSTGRESQL, "csharp")
        text = 'cmd.Parameters.AddWithValue("@userId", userId);'
        assert any(p.search(text) for p in pattern.safe_patterns)

    def test_npgsql_unsafe_patterns_match(self):
        pattern = DatabasePatternRegistry.get(DatabaseType.POSTGRESQL, "csharp")
        text = '$"DELETE FROM items WHERE id = \'{id}\'"'
        assert any(p.search(text) for p in pattern.unsafe_patterns)

    def test_psycopg2_safe_patterns_match(self):
        pattern = DatabasePatternRegistry.get(DatabaseType.POSTGRESQL, "python")
        text = 'cur.execute("SELECT * FROM t WHERE id = %s", (id,))'
        assert any(p.search(text) for p in pattern.safe_patterns)

    def test_get_all_for_database(self):
        patterns = DatabasePatternRegistry.get_all_for_database(DatabaseType.POSTGRESQL)
        assert len(patterns) >= 3  # csharp, python, nodejs

    def test_health_check_query(self):
        pattern = DatabasePatternRegistry.get(DatabaseType.POSTGRESQL, "csharp")
        assert pattern.health_check_query == "SELECT 1"
