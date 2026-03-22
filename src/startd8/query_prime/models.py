"""Query Prime data models — secure query generation domain.

Frozen dataclasses following the ``complexity/models.py`` pattern.
Provides enums for database types, operation types, security verdicts,
and dataclasses for query work items, classification signals, and
security findings.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Iterator, List, Optional, Union

from startd8.complexity.models import ComplexityTier


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DatabaseType(str, Enum):
    """Supported database backends for query generation."""

    POSTGRESQL = "postgresql"
    SPANNER = "spanner"
    REDIS = "redis"
    MYSQL = "mysql"
    SQLITE = "sqlite"


class OperationType(str, Enum):
    """Query operation categories."""

    SELECT = "select"
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    UPSERT = "upsert"
    TRANSACTION = "transaction"
    HEALTH_CHECK = "health_check"


class TransactionBoundary(str, Enum):
    """Transaction scope classification."""

    NONE = "none"
    SINGLE_STATEMENT = "single_statement"
    MULTI_STATEMENT = "multi_statement"
    DISTRIBUTED = "distributed"


class SecurityVerdict(str, Enum):
    """Security verification outcome."""

    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"


class SecurityCheckType(str, Enum):
    """Categories of security checks."""

    INJECTION = "injection"
    CREDENTIAL_LEAKAGE = "credential_leakage"
    LIFECYCLE = "lifecycle"
    HEALTH_CHECK_EXPOSURE = "health_check_exposure"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParameterSpec:
    """Specification for a query parameter."""

    name: str
    param_type: str = "string"
    source: str = "user_input"  # "user_input" | "internal" | "config"
    requires_parameterization: bool = True


@dataclass(frozen=True)
class JoinSpec:
    """Specification for a table join."""

    left_table: str
    right_table: str
    join_type: str = "INNER"
    on_clause: str = ""


@dataclass(frozen=True)
class QueryWorkItem:
    """A single query generation work item."""

    id: str
    description: str
    database: DatabaseType
    operation_type: OperationType
    tables: List[str] = field(default_factory=list)
    parameters: List[ParameterSpec] = field(default_factory=list)
    joins: List[JoinSpec] = field(default_factory=list)
    transaction_boundary: TransactionBoundary = TransactionBoundary.NONE
    credential_sources: List[str] = field(default_factory=list)
    target_language: str = "csharp"
    target_framework: str = ""
    containing_function: str = ""
    file_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for JSON storage."""
        d = asdict(self)
        d["database"] = self.database.value
        d["operation_type"] = self.operation_type.value
        d["transaction_boundary"] = self.transaction_boundary.value
        return d


@dataclass(frozen=True)
class QuerySignals:
    """Classification signals extracted from a query work item."""

    table_count: int = 0
    join_count: int = 0
    has_subquery: bool = False
    has_transaction: bool = False
    has_dynamic_columns: bool = False
    has_aggregate: bool = False
    parameter_count: int = 0
    has_upsert: bool = False
    target_framework_familiarity: float = 1.0
    prior_injection_failure: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for JSON storage."""
        return asdict(self)


@dataclass(frozen=True)
class QueryClassificationResult:
    """Query-specific classification result.

    Supports tuple unpacking for compatibility with ``ClassificationResult``::

        tier, reason = classify_query_tier(signals)
    """

    tier: ComplexityTier
    reason: str
    signals: QuerySignals
    forced_minimum: Optional[ComplexityTier] = None

    def __iter__(self) -> Iterator[Union[ComplexityTier, str]]:
        """Yield (tier, reason) for backward-compatible tuple unpacking."""
        return iter((self.tier, self.reason))


@dataclass(frozen=True)
class SecurityFinding:
    """A single security issue found during verification."""

    check_type: SecurityCheckType
    severity: str  # "error" | "warning"
    message: str
    line: Optional[int] = None
    file_path: Optional[str] = None
    database: Optional[str] = None
    pattern_hash: str = ""

    def to_semantic_issue(self) -> Any:
        """Convert to a SemanticIssue for DiskComplianceResult integration."""
        from startd8.validators.semantic_checks import SemanticIssue

        return SemanticIssue(
            check=f"query_security_{self.check_type.value}",
            severity=self.severity,
            message=self.message,
            line=self.line,
            file_path=self.file_path,
        )


@dataclass(frozen=True)
class SecurityVerificationResult:
    """Result of running the full security verification pipeline on a file."""

    file_path: str
    verdict: SecurityVerdict
    checks_passed: int = 0
    checks_failed: int = 0
    checks_warned: int = 0
    findings: List[SecurityFinding] = field(default_factory=list)
    verification_timing_ms: Optional[Dict[str, float]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for JSON storage."""
        d = asdict(self)
        d["verdict"] = self.verdict.value
        return d


@dataclass(frozen=True)
class SecurityContract:
    """Security contract for a service — databases, libraries, credentials."""

    service_id: str
    databases: List[DatabaseType] = field(default_factory=list)
    client_libraries: List[str] = field(default_factory=list)
    credential_sources: List[str] = field(default_factory=list)
    checksum: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for JSON storage."""
        d = asdict(self)
        d["databases"] = [db.value for db in self.databases]
        return d

    def compute_checksum(self) -> str:
        """Compute a stable checksum of this contract's contents."""
        parts = sorted(db.value for db in self.databases)
        parts.extend(sorted(self.client_libraries))
        parts.extend(sorted(self.credential_sources))
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


@dataclass(frozen=True)
class QueryResult:
    """Result of processing a single query work item."""

    work_item_id: str
    code: str = ""
    verification: Optional[SecurityVerificationResult] = None
    tier_used: Optional[ComplexityTier] = None
    model_used: str = ""
    cost_usd: float = 0.0
    escalations: int = 0
    retry_count: int = 0
