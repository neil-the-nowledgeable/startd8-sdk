"""Query work item decomposition from Prime Contractor features — REQ-QP-200.

Extracts discrete QueryWorkItem objects from a feature's description
and target files. This connects Query Prime to the broader Prime
Contractor pipeline.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from startd8.logging_config import get_logger

from .models import (
    DatabaseType,
    OperationType,
    ParameterSpec,
    QueryWorkItem,
    TransactionBoundary,
)

logger = get_logger(__name__)

# Heuristic patterns for detecting database type from text
_DATABASE_PATTERNS: Dict[str, DatabaseType] = {
    "postgresql": DatabaseType.POSTGRESQL,
    "postgres": DatabaseType.POSTGRESQL,
    "alloydb": DatabaseType.POSTGRESQL,
    "npgsql": DatabaseType.POSTGRESQL,
    "psycopg": DatabaseType.POSTGRESQL,
    "asyncpg": DatabaseType.POSTGRESQL,
    "node-postgres": DatabaseType.POSTGRESQL,
    "spanner": DatabaseType.SPANNER,
    "cloud spanner": DatabaseType.SPANNER,
    "spannerparameter": DatabaseType.SPANNER,
    "redis": DatabaseType.REDIS,
    "stackexchange.redis": DatabaseType.REDIS,
    "ioredis": DatabaseType.REDIS,
    "mysql": DatabaseType.MYSQL,
    "mariadb": DatabaseType.MYSQL,
    "mysql-connector": DatabaseType.MYSQL,
    "asyncmy": DatabaseType.MYSQL,
    "sqlite": DatabaseType.SQLITE,
    "sqlite3": DatabaseType.SQLITE,
    "sqlalchemy": DatabaseType.POSTGRESQL,  # default; ORM-level — assume PG
    "sqlclient": DatabaseType.POSTGRESQL,
    "microsoft.data": DatabaseType.POSTGRESQL,
    # REQ-QPA-200: Go database import patterns
    "database/sql": DatabaseType.POSTGRESQL,    # Go stdlib DB interface
    "pgxpool": DatabaseType.POSTGRESQL,         # pgx connection pool
    "jackc/pgx": DatabaseType.POSTGRESQL,       # pgx driver module path
    "lib/pq": DatabaseType.POSTGRESQL,          # Older Go PG driver
    "go-redis": DatabaseType.REDIS,             # Go Redis client
    "go-sql-driver/mysql": DatabaseType.MYSQL,  # Go MySQL driver
    "mattn/go-sqlite3": DatabaseType.SQLITE,    # Go SQLite driver
    # Java / JVM patterns
    "jdbc": DatabaseType.POSTGRESQL,            # JDBC (default PG)
    "r2dbc": DatabaseType.POSTGRESQL,           # Reactive DB (default PG)
}

# Heuristic patterns for detecting operation type from text
_OPERATION_PATTERNS: Dict[str, OperationType] = {
    "health check": OperationType.HEALTH_CHECK,
    "healthcheck": OperationType.HEALTH_CHECK,
    "health_check": OperationType.HEALTH_CHECK,
    "ping": OperationType.HEALTH_CHECK,
    "select": OperationType.SELECT,
    "get": OperationType.SELECT,
    "fetch": OperationType.SELECT,
    "query": OperationType.SELECT,
    "find": OperationType.SELECT,
    "list": OperationType.SELECT,
    "read": OperationType.SELECT,
    "insert": OperationType.INSERT,
    "add": OperationType.INSERT,
    "create": OperationType.INSERT,
    "put": OperationType.INSERT,
    "update": OperationType.UPDATE,
    "modify": OperationType.UPDATE,
    "edit": OperationType.UPDATE,
    "set": OperationType.UPDATE,
    "delete": OperationType.DELETE,
    "remove": OperationType.DELETE,
    "drop": OperationType.DELETE,
    "upsert": OperationType.UPSERT,
    "merge": OperationType.UPSERT,
    "transaction": OperationType.TRANSACTION,
}

# File extension to language mapping
_EXT_TO_LANGUAGE: Dict[str, str] = {
    ".cs": "csharp",
    ".py": "python",
    ".js": "nodejs",
    ".ts": "nodejs",
    ".go": "go",
    ".java": "java",
}

# Regex for extracting table names from descriptions
_TABLE_PATTERN = re.compile(
    r'\b(?:FROM|INTO|UPDATE|TABLE|JOIN)\s+[`"\']?(\w+)[`"\']?',
    re.IGNORECASE,
)

# Regex for extracting parameter-like names
_PARAM_PATTERN = re.compile(
    r'\b(\w+(?:Id|_id|Name|_name|Key|_key|Code|_code))\b',
)


def detect_database_type(text: str) -> Optional[DatabaseType]:
    """Detect the database type from a text description.

    Args:
        text: Feature description, metadata, or file content.

    Returns:
        Detected DatabaseType, or None if not detected.
    """
    text_lower = text.lower()
    for keyword, db_type in _DATABASE_PATTERNS.items():
        if keyword in text_lower:
            return db_type
    return None


def detect_operation_type(text: str) -> OperationType:
    """Detect the operation type from a text description.

    Args:
        text: Feature description or method name.

    Returns:
        Detected OperationType, defaults to SELECT.
    """
    text_lower = text.lower()
    for keyword, op_type in _OPERATION_PATTERNS.items():
        if keyword in text_lower:
            return op_type
    return OperationType.SELECT


def detect_language(target_files: List[str]) -> str:
    """Detect the target language from file extensions.

    Args:
        target_files: List of target file paths.

    Returns:
        Language identifier, defaults to "csharp".
    """
    for f in target_files:
        for ext, lang in _EXT_TO_LANGUAGE.items():
            if f.endswith(ext):
                return lang
    return "csharp"


def extract_tables(text: str) -> List[str]:
    """Extract table names mentioned in a description.

    Args:
        text: Feature description or query text.

    Returns:
        List of unique table names found.
    """
    matches = _TABLE_PATTERN.findall(text)
    # Deduplicate while preserving order
    seen: set[str] = set()
    tables: List[str] = []
    for m in matches:
        if m.lower() not in seen:
            seen.add(m.lower())
            tables.append(m)
    return tables


def extract_parameters(text: str) -> List[ParameterSpec]:
    """Extract likely parameter names from a description.

    Args:
        text: Feature description.

    Returns:
        List of ParameterSpec with detected parameter names.
    """
    matches = _PARAM_PATTERN.findall(text)
    seen: set[str] = set()
    params: List[ParameterSpec] = []
    for m in matches:
        if m.lower() not in seen:
            seen.add(m.lower())
            params.append(ParameterSpec(
                name=m,
                param_type="string",
                source="user_input",
                requires_parameterization=True,
            ))
    return params


def decompose_feature(
    feature_id: str,
    description: str,
    target_files: List[str],
    metadata: Optional[Dict[str, Any]] = None,
) -> List[QueryWorkItem]:
    """Decompose a Prime Contractor feature into query work items.

    Parses the feature's description and metadata to identify discrete
    query operations and produces individual QueryWorkItem objects.

    Args:
        feature_id: The feature identifier.
        description: Feature description text.
        target_files: Target file paths.
        metadata: Optional feature metadata dict.

    Returns:
        List of QueryWorkItem objects. May be empty if no database
        operations are detected.
    """
    metadata = metadata or {}

    # Detect database type
    full_text = description + " " + " ".join(
        str(v) for v in metadata.values() if isinstance(v, str)
    )
    database = detect_database_type(full_text)
    if database is None:
        return []  # Not a database-facing feature

    language = detect_language(target_files)
    tables = extract_tables(full_text)
    parameters = extract_parameters(full_text)
    framework = metadata.get("target_framework", "")

    # Split description into sentences/clauses to find distinct operations
    work_items: List[QueryWorkItem] = []

    # Try to detect multiple operations from the description
    # Split on common delimiters
    clauses = re.split(r'[;,\n•\-]|\band\b', description)

    for clause in clauses:
        clause = clause.strip()
        if not clause or len(clause) < 5:
            continue

        op_type = detect_operation_type(clause)
        clause_tables = extract_tables(clause) or tables[:1]
        clause_params = extract_parameters(clause) or parameters[:2]

        # Determine transaction boundary
        tx_boundary = TransactionBoundary.NONE
        if "transaction" in clause.lower():
            tx_boundary = TransactionBoundary.MULTI_STATEMENT
        elif op_type == OperationType.UPSERT:
            tx_boundary = TransactionBoundary.SINGLE_STATEMENT

        wi_id = f"qp-{feature_id}-{len(work_items):03d}"
        work_items.append(QueryWorkItem(
            id=wi_id,
            description=clause,
            database=database,
            operation_type=op_type,
            tables=clause_tables,
            parameters=clause_params,
            transaction_boundary=tx_boundary,
            target_language=language,
            target_framework=framework,
            file_path=target_files[0] if target_files else "",
        ))

    # If no clauses produced work items, create a single one from the whole description
    if not work_items:
        op_type = detect_operation_type(description)
        work_items.append(QueryWorkItem(
            id=f"qp-{feature_id}-000",
            description=description,
            database=database,
            operation_type=op_type,
            tables=tables[:4],
            parameters=parameters[:5],
            target_language=language,
            target_framework=framework,
            file_path=target_files[0] if target_files else "",
        ))

    logger.info(
        "Decomposed feature '%s' into %d query work items (database=%s)",
        feature_id, len(work_items), database.value,
    )
    return work_items
