"""Tests for QueryPrimeEngine — template path e2e, verify path, signal extraction."""

import pytest

from startd8.complexity.models import ComplexityTier
from startd8.query_prime.engine import QueryPrimeEngine
from startd8.query_prime.models import (
    DatabaseType,
    OperationType,
    ParameterSpec,
    QueryWorkItem,
    SecurityVerdict,
    TransactionBoundary,
)


@pytest.fixture
def engine():
    return QueryPrimeEngine()


class TestProcessWorkItem:
    """End-to-end template generation path."""

    def test_health_check_template_path(self, engine):
        wi = QueryWorkItem(
            id="hc-1",
            description="Health check",
            database=DatabaseType.POSTGRESQL,
            operation_type=OperationType.HEALTH_CHECK,
            target_language="csharp",
        )
        result = engine.process_work_item(wi)
        assert result.work_item_id == "hc-1"
        assert result.code != ""
        assert "SELECT 1" in result.code
        assert result.tier_used == ComplexityTier.TRIVIAL
        assert result.model_used == "template"
        assert result.cost_usd == 0.0
        assert result.verification is not None
        assert result.verification.verdict == SecurityVerdict.PASS

    def test_crud_template_path(self, engine):
        wi = QueryWorkItem(
            id="crud-1",
            description="Select user",
            database=DatabaseType.POSTGRESQL,
            operation_type=OperationType.SELECT,
            tables=["users"],
            parameters=[ParameterSpec(name="id")],
            target_language="csharp",
        )
        result = engine.process_work_item(wi)
        assert result.code != ""
        assert "@id" in result.code
        assert result.verification.verdict == SecurityVerdict.PASS

    def test_llm_path_raises_not_implemented(self, engine):
        """LLM generation not available in Phase 1."""
        wi = QueryWorkItem(
            id="complex-1",
            description="Complex multi-table join",
            database=DatabaseType.POSTGRESQL,
            operation_type=OperationType.SELECT,
            tables=["a", "b", "c", "d", "e"],
            target_language="java",  # No CRUD template for java
        )
        with pytest.raises(NotImplementedError, match="Phase 3"):
            engine.process_work_item(wi)


class TestVerifyExistingFile:
    """Standalone verification path."""

    def test_verify_safe_code(self, engine):
        source = '''
public async Task<User> GetUser(NpgsqlDataSource ds, string id)
{
    await using var conn = await ds.OpenConnectionAsync();
    await using var cmd = new NpgsqlCommand(
        "SELECT * FROM users WHERE id = @id", conn);
    cmd.Parameters.AddWithValue("@id", id);
    return await Map(cmd.ExecuteReaderAsync());
}
'''
        result = engine.verify_existing_file(
            source, "store.cs", DatabaseType.POSTGRESQL, "csharp",
        )
        assert result.verdict == SecurityVerdict.PASS

    def test_verify_unsafe_code(self, engine):
        source = '''
public void Delete(string userId)
{
    var cmd = new NpgsqlCommand(
        $"DELETE FROM users WHERE id = '{userId}'", conn);
    cmd.ExecuteNonQuery();
}
'''
        result = engine.verify_existing_file(
            source, "store.cs", DatabaseType.POSTGRESQL, "csharp",
        )
        assert result.verdict == SecurityVerdict.FAIL


class TestExtractSignals:
    """Signal extraction from work items."""

    def test_basic_signals(self, engine):
        wi = QueryWorkItem(
            id="sig-1",
            description="test",
            database=DatabaseType.POSTGRESQL,
            operation_type=OperationType.SELECT,
            tables=["users", "orders"],
            parameters=[ParameterSpec(name="id"), ParameterSpec(name="status")],
        )
        signals = engine._extract_signals(wi)
        assert signals.table_count == 2
        assert signals.parameter_count == 2
        assert signals.has_upsert is False

    def test_transaction_signals(self, engine):
        wi = QueryWorkItem(
            id="sig-2",
            description="test",
            database=DatabaseType.POSTGRESQL,
            operation_type=OperationType.TRANSACTION,
            tables=["accounts"],
            transaction_boundary=TransactionBoundary.MULTI_STATEMENT,
        )
        signals = engine._extract_signals(wi)
        assert signals.has_transaction is True

    def test_upsert_signals(self, engine):
        wi = QueryWorkItem(
            id="sig-3",
            description="test",
            database=DatabaseType.POSTGRESQL,
            operation_type=OperationType.UPSERT,
            tables=["items"],
        )
        signals = engine._extract_signals(wi)
        assert signals.has_upsert is True
