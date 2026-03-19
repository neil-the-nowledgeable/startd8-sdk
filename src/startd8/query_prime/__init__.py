"""Query Prime — Secure Query Generation Engine.

Domain instantiation of the Prime Contractor paradigm for generating
secure database queries. Implements the Anzen (安全) design principle:
security correctness by design.

Public API::

    from startd8.query_prime import QueryPrimeEngine, verify_file

    engine = QueryPrimeEngine()
    result = engine.process_work_item(work_item)

    # Standalone verification (no generation)
    verification = verify_file(source, "path.cs", "postgresql", "csharp")
"""

from startd8.query_prime.classifier import (
    QueryRoutingConfig,
    classify_query_tier,
)
from startd8.query_prime.engine import QueryPrimeEngine
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
from startd8.query_prime.security import verify_file

__all__ = [
    "QueryPrimeEngine",
    "QueryRoutingConfig",
    "classify_query_tier",
    "verify_file",
    "DatabaseType",
    "OperationType",
    "TransactionBoundary",
    "SecurityVerdict",
    "SecurityCheckType",
    "ParameterSpec",
    "JoinSpec",
    "QueryWorkItem",
    "QuerySignals",
    "QueryClassificationResult",
    "SecurityFinding",
    "SecurityVerificationResult",
    "SecurityContract",
    "QueryResult",
]
