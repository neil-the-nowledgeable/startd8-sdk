"""Tests for Redis patterns — command safety, credential patterns."""

import pytest

from startd8.query_prime.models import DatabaseType
from startd8.query_prime.patterns import DatabasePatternRegistry


class TestRedisPatterns:
    def test_redis_csharp_registered(self):
        pattern = DatabasePatternRegistry.get(DatabaseType.REDIS, "csharp")
        assert pattern is not None
        assert pattern.client_library == "StackExchange.Redis"

    def test_redis_python_registered(self):
        pattern = DatabasePatternRegistry.get(DatabaseType.REDIS, "python")
        assert pattern is not None

    def test_redis_nodejs_registered(self):
        pattern = DatabasePatternRegistry.get(DatabaseType.REDIS, "nodejs")
        assert pattern is not None

    def test_redis_health_check_is_ping(self):
        pattern = DatabasePatternRegistry.get(DatabaseType.REDIS, "csharp")
        assert pattern.health_check_query == "PING"

    def test_redis_credential_names(self):
        pattern = DatabasePatternRegistry.get(DatabaseType.REDIS, "csharp")
        assert "password" in pattern.credential_variable_names or "Password" in pattern.credential_variable_names
