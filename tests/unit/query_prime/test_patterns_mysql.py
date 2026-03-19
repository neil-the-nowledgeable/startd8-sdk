"""Tests for MySQL patterns — MySqlConnector, mysql-connector-python."""

import pytest

from startd8.query_prime.models import DatabaseType
from startd8.query_prime.patterns import DatabasePatternRegistry


class TestMySQLPatterns:
    def test_mysql_csharp_registered(self):
        pattern = DatabasePatternRegistry.get(DatabaseType.MYSQL, "csharp")
        assert pattern is not None
        assert pattern.client_library == "MySqlConnector"

    def test_mysql_python_registered(self):
        pattern = DatabasePatternRegistry.get(DatabaseType.MYSQL, "python")
        assert pattern is not None

    def test_mysql_csharp_safe_patterns(self):
        pattern = DatabasePatternRegistry.get(DatabaseType.MYSQL, "csharp")
        text = 'cmd.Parameters.AddWithValue("@name", value);'
        assert any(p.search(text) for p in pattern.safe_patterns)

    def test_mysql_python_safe_patterns(self):
        pattern = DatabasePatternRegistry.get(DatabaseType.MYSQL, "python")
        text = 'cursor.execute("SELECT * FROM t WHERE id = %s", (id,))'
        assert any(p.search(text) for p in pattern.safe_patterns)
