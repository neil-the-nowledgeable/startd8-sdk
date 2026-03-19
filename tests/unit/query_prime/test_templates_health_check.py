"""Tests for health check templates — all 5 DB x 3 languages."""

import pytest

from startd8.query_prime.models import (
    DatabaseType,
    OperationType,
    QueryWorkItem,
)
from startd8.query_prime.templates import generate, is_trivial


def _make_health_check(db: DatabaseType, lang: str) -> QueryWorkItem:
    return QueryWorkItem(
        id=f"hc-{db.value}-{lang}",
        description=f"Health check for {db.value}",
        database=db,
        operation_type=OperationType.HEALTH_CHECK,
        target_language=lang,
    )


class TestHealthCheckTemplates:
    """All 5 DB x 3 languages should have health check templates."""

    @pytest.mark.parametrize("db,lang", [
        (DatabaseType.POSTGRESQL, "csharp"),
        (DatabaseType.POSTGRESQL, "python"),
        (DatabaseType.POSTGRESQL, "nodejs"),
        (DatabaseType.SPANNER, "csharp"),
        (DatabaseType.SPANNER, "python"),
        (DatabaseType.SPANNER, "nodejs"),
        (DatabaseType.REDIS, "csharp"),
        (DatabaseType.REDIS, "python"),
        (DatabaseType.REDIS, "nodejs"),
        (DatabaseType.MYSQL, "csharp"),
        (DatabaseType.MYSQL, "python"),
        (DatabaseType.MYSQL, "nodejs"),
        (DatabaseType.SQLITE, "csharp"),
        (DatabaseType.SQLITE, "python"),
        (DatabaseType.SQLITE, "nodejs"),
    ])
    def test_health_check_exists(self, db, lang):
        wi = _make_health_check(db, lang)
        assert is_trivial(wi), f"No template for {db.value}/{lang}/health_check"
        code = generate(wi)
        assert code is not None
        assert len(code) > 20

    @pytest.mark.parametrize("db,lang", [
        (DatabaseType.POSTGRESQL, "csharp"),
        (DatabaseType.POSTGRESQL, "python"),
        (DatabaseType.POSTGRESQL, "nodejs"),
        (DatabaseType.MYSQL, "csharp"),
        (DatabaseType.MYSQL, "python"),
        (DatabaseType.MYSQL, "nodejs"),
        (DatabaseType.SQLITE, "csharp"),
        (DatabaseType.SQLITE, "python"),
        (DatabaseType.SQLITE, "nodejs"),
    ])
    def test_health_check_contains_select_1(self, db, lang):
        """SQL databases should use SELECT 1."""
        wi = _make_health_check(db, lang)
        code = generate(wi)
        assert "SELECT 1" in code

    @pytest.mark.parametrize("lang", ["csharp", "python", "nodejs"])
    def test_redis_health_check_contains_ping(self, lang):
        """Redis health check should use PING."""
        wi = _make_health_check(DatabaseType.REDIS, lang)
        code = generate(wi)
        assert "ping" in code.lower() or "PING" in code or "Ping" in code

    @pytest.mark.parametrize("db,lang", [
        (DatabaseType.POSTGRESQL, "csharp"),
        (DatabaseType.SPANNER, "csharp"),
        (DatabaseType.MYSQL, "csharp"),
        (DatabaseType.SQLITE, "csharp"),
        (DatabaseType.REDIS, "csharp"),
    ])
    def test_no_credential_logging(self, db, lang):
        """Health check templates must not log credentials."""
        wi = _make_health_check(db, lang)
        code = generate(wi)
        assert "Console.Write" not in code
        assert "connectionString" not in code.lower() or "string connectionString" in code

    @pytest.mark.parametrize("db,lang", [
        (DatabaseType.POSTGRESQL, "csharp"),
        (DatabaseType.POSTGRESQL, "python"),
        (DatabaseType.POSTGRESQL, "nodejs"),
    ])
    def test_has_error_handling(self, db, lang):
        """Health check templates must have error handling."""
        wi = _make_health_check(db, lang)
        code = generate(wi)
        assert "catch" in code or "except" in code or "try" in code
