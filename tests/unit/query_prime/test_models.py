"""Tests for query_prime.models — enums, serialization, converters."""

import pytest

from startd8.complexity.models import ComplexityTier
from startd8.query_prime.models import (
    DatabaseType,
    JoinSpec,
    OperationType,
    ParameterSpec,
    QueryClassificationResult,
    QueryResult,
    QuerySignals,
    QueryWorkItem,
    SecurityCheckType,
    SecurityContract,
    SecurityFinding,
    SecurityVerdict,
    SecurityVerificationResult,
    TransactionBoundary,
)


# ---------------------------------------------------------------------------
# Enum membership
# ---------------------------------------------------------------------------

class TestEnums:
    def test_database_type_values(self):
        assert DatabaseType.POSTGRESQL.value == "postgresql"
        assert DatabaseType.SPANNER.value == "spanner"
        assert DatabaseType.REDIS.value == "redis"
        assert DatabaseType.MYSQL.value == "mysql"
        assert DatabaseType.SQLITE.value == "sqlite"

    def test_operation_type_values(self):
        assert OperationType.SELECT.value == "select"
        assert OperationType.HEALTH_CHECK.value == "health_check"

    def test_transaction_boundary_values(self):
        assert TransactionBoundary.NONE.value == "none"
        assert TransactionBoundary.DISTRIBUTED.value == "distributed"

    def test_security_verdict_values(self):
        assert SecurityVerdict.PASS.value == "pass"
        assert SecurityVerdict.FAIL.value == "fail"
        assert SecurityVerdict.WARN.value == "warn"

    def test_security_check_type_values(self):
        assert SecurityCheckType.INJECTION.value == "injection"
        assert SecurityCheckType.CREDENTIAL_LEAKAGE.value == "credential_leakage"
        assert SecurityCheckType.LIFECYCLE.value == "lifecycle"


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_query_work_item_to_dict(self):
        wi = QueryWorkItem(
            id="qw-1",
            description="test",
            database=DatabaseType.POSTGRESQL,
            operation_type=OperationType.SELECT,
            tables=["users"],
        )
        d = wi.to_dict()
        assert d["database"] == "postgresql"
        assert d["operation_type"] == "select"
        assert d["tables"] == ["users"]

    def test_query_signals_to_dict(self):
        s = QuerySignals(table_count=3, join_count=2)
        d = s.to_dict()
        assert d["table_count"] == 3
        assert d["join_count"] == 2

    def test_security_verification_result_to_dict(self):
        r = SecurityVerificationResult(
            file_path="test.cs",
            verdict=SecurityVerdict.PASS,
            checks_passed=3,
        )
        d = r.to_dict()
        assert d["verdict"] == "pass"
        assert d["checks_passed"] == 3

    def test_security_contract_to_dict(self):
        c = SecurityContract(
            service_id="cart",
            databases=[DatabaseType.POSTGRESQL, DatabaseType.REDIS],
        )
        d = c.to_dict()
        assert d["databases"] == ["postgresql", "redis"]

    def test_security_contract_checksum(self):
        c = SecurityContract(
            service_id="cart",
            databases=[DatabaseType.POSTGRESQL],
            client_libraries=["Npgsql"],
        )
        checksum = c.compute_checksum()
        assert len(checksum) == 16
        # Deterministic
        assert c.compute_checksum() == checksum


# ---------------------------------------------------------------------------
# Tuple unpacking
# ---------------------------------------------------------------------------

class TestQueryClassificationResult:
    def test_tuple_unpacking(self):
        signals = QuerySignals()
        result = QueryClassificationResult(
            tier=ComplexityTier.SIMPLE,
            reason="test reason",
            signals=signals,
        )
        tier, reason = result
        assert tier == ComplexityTier.SIMPLE
        assert reason == "test reason"


# ---------------------------------------------------------------------------
# SecurityFinding converter
# ---------------------------------------------------------------------------

class TestSecurityFinding:
    def test_to_semantic_issue(self):
        finding = SecurityFinding(
            check_type=SecurityCheckType.INJECTION,
            severity="error",
            message="SQL injection detected",
            line=42,
            file_path="store.cs",
        )
        issue = finding.to_semantic_issue()
        assert issue.check == "query_security_injection"
        assert issue.severity == "error"
        assert issue.message == "SQL injection detected"
        assert issue.line == 42
        assert issue.file_path == "store.cs"
