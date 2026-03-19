"""Tests for QueryPrimeEngine — template path, LLM path, escalation, verify, signals."""

from unittest.mock import MagicMock, patch

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
from startd8.query_prime.router import QueryRouterConfig


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

    def test_llm_path_with_mock_agent(self, engine):
        """LLM path with a mock agent that returns safe code."""
        wi = QueryWorkItem(
            id="complex-1",
            description="Complex multi-table join",
            database=DatabaseType.POSTGRESQL,
            operation_type=OperationType.SELECT,
            tables=["a", "b", "c", "d", "e"],
            target_language="java",
        )
        agent = MagicMock()
        safe_code = (
            'Statement stmt = connection.createStatement();\n'
            'ResultSet rs = stmt.executeQuery("SELECT 1");\n'
        )
        agent.generate.return_value = MagicMock(
            text=safe_code,
            token_usage={"input_tokens": 100, "output_tokens": 50},
        )
        agent.name = "mock-agent"

        result = engine.process_work_item(wi, agent=agent)
        assert "SELECT 1" in result.code
        assert result.cost_usd > 0
        assert result.model_used == "mock-agent"

    def test_template_preferred_over_llm(self, engine):
        """Template-eligible work items use template even at higher tiers."""
        wi = QueryWorkItem(
            id="hc-2",
            description="Health check",
            database=DatabaseType.POSTGRESQL,
            operation_type=OperationType.HEALTH_CHECK,
            tables=["a", "b", "c", "d", "e"],  # 5 tables forces COMPLEX
            target_language="csharp",
        )
        result = engine.process_work_item(wi)
        assert result.tier_used == ComplexityTier.TRIVIAL
        assert result.model_used == "template"
        assert result.cost_usd == 0.0


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


class TestLLMEscalation:
    """LLM generation with escalation on verification failure."""

    def test_escalation_on_security_failure(self):
        """Mock verify_file to force FAIL on first call, PASS on second."""
        engine = QueryPrimeEngine(
            router_config=QueryRouterConfig(max_retries_per_tier=0),
        )
        wi = QueryWorkItem(
            id="esc-1",
            description="Delete user from Spanner",
            database=DatabaseType.SPANNER,
            operation_type=OperationType.DELETE,
            tables=["users"],
            parameters=[ParameterSpec(name="userId")],
            target_language="java",  # No CRUD template for spanner/java
        )

        from startd8.query_prime.models import (
            SecurityCheckType,
            SecurityFinding,
            SecurityVerificationResult as SVR,
        )

        call_count = 0
        def mock_verify(source, file_path, database, language, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return SVR(
                    file_path=file_path,
                    verdict=SecurityVerdict.FAIL,
                    checks_failed=1,
                    findings=[SecurityFinding(
                        check_type=SecurityCheckType.INJECTION,
                        severity="error",
                        message="mock injection",
                    )],
                )
            return SVR(
                file_path=file_path,
                verdict=SecurityVerdict.PASS,
                checks_passed=3,
            )

        agent = MagicMock()
        agent.generate.return_value = MagicMock(
            text="safe code here",
            token_usage={"input_tokens": 50, "output_tokens": 30},
        )

        with patch.object(engine, '_resolve_agent', return_value=agent), \
             patch('startd8.query_prime.generator.verify_file', side_effect=mock_verify):
            result = engine.process_work_item(wi)

        assert result.escalations >= 1
        assert result.cost_usd > 0

    def test_exhausted_returns_last_result(self):
        """All tiers exhausted returns last (failed) result."""
        engine = QueryPrimeEngine(
            router_config=QueryRouterConfig(
                max_retries_per_tier=0,
                max_escalations=0,
            ),
        )
        wi = QueryWorkItem(
            id="exhaust-1",
            description="Delete user",
            database=DatabaseType.POSTGRESQL,
            operation_type=OperationType.DELETE,
            tables=["users"],
            target_language="java",
        )

        agent = MagicMock()
        agent.generate.return_value = MagicMock(
            text='$"DELETE FROM users WHERE id = \'{id}\'"',
            token_usage={"input_tokens": 50, "output_tokens": 30},
        )
        agent.name = "failing-agent"

        with patch.object(engine, '_resolve_agent', return_value=agent):
            result = engine.process_work_item(wi)

        assert result.code != ""  # Has last attempt's code
        assert result.retry_count >= 1


class TestProcessFeature:
    """Feature decomposition + processing convenience method."""

    def test_database_feature(self):
        engine = QueryPrimeEngine()
        results = engine.process_feature(
            "cart",
            "Implement PostgreSQL health check for cart service",
            ["src/CartStore.cs"],
        )
        assert len(results) >= 1
        assert results[0].code != ""

    def test_non_database_feature(self):
        engine = QueryPrimeEngine()
        results = engine.process_feature(
            "ui",
            "Implement the profile card component",
            ["src/ProfileCard.tsx"],
        )
        assert results == []
