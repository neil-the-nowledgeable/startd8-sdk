"""PostgreSQL/AlloyDB safe and unsafe patterns.

Covers Npgsql (C#), psycopg2 (Python), node-postgres (Node.js), asyncpg (Python).
"""

from __future__ import annotations

import re

from ..models import DatabaseType
from . import DatabasePattern, DatabasePatternRegistry

# ---------------------------------------------------------------------------
# C# — Npgsql
# ---------------------------------------------------------------------------

_npgsql = DatabasePattern(
    database=DatabaseType.POSTGRESQL,
    client_library="Npgsql",
    language="csharp",
    safe_param_syntax=(
        '@param with NpgsqlParameter',
        'cmd.Parameters.AddWithValue("@name", value)',
        'new NpgsqlParameter("@name", value)',
    ),
    safe_patterns=(
        # Parameterized: @param inside a SQL string literal (not bare @identifier)
        re.compile(r'["\'].*@\w+.*["\']'),
        re.compile(r'NpgsqlParameter', re.IGNORECASE),
        re.compile(r'Parameters\.Add', re.IGNORECASE),
        re.compile(r'AddWithValue', re.IGNORECASE),
    ),
    unsafe_patterns=(
        # String interpolation in SQL: $"...{var}..."
        re.compile(r'\$"[^"]*\{[^}]+\}[^"]*"'),
        # String concatenation: "..." + var + "..."
        re.compile(r'"[^"]*"\s*\+\s*\w+'),
        # String.Format with SQL keywords
        re.compile(r'String\.Format\s*\([^)]*(?:SELECT|INSERT|UPDATE|DELETE)', re.IGNORECASE),
    ),
    credential_variable_names=(
        "connectionString", "connStr", "password", "Password",
        "NpgsqlConnectionStringBuilder",
    ),
    resource_creation_patterns=(
        re.compile(r'NpgsqlDataSource\.Create\s*\('),
        re.compile(r'new\s+NpgsqlConnection\s*\('),
    ),
    dispose_patterns=(
        re.compile(r'\busing\s*\('),
        re.compile(r'\bawait\s+using\b'),
        re.compile(r'\.Dispose\s*\('),
    ),
    health_check_query="SELECT 1",
)
DatabasePatternRegistry.register(_npgsql)

# ---------------------------------------------------------------------------
# Python — psycopg2
# ---------------------------------------------------------------------------

_psycopg2 = DatabasePattern(
    database=DatabaseType.POSTGRESQL,
    client_library="psycopg2",
    language="python",
    safe_param_syntax=(
        '%s with tuple: cursor.execute("SELECT * FROM t WHERE id = %s", (id,))',
    ),
    safe_patterns=(
        re.compile(r'%s'),
        re.compile(r'execute\s*\([^,]+,\s*\('),
        re.compile(r'execute\s*\([^,]+,\s*\['),
    ),
    unsafe_patterns=(
        re.compile(r'f"[^"]*\{[^}]+\}[^"]*"'),
        re.compile(r'f\'[^\']*\{[^}]+\}[^\']*\''),
        re.compile(r'"[^"]*"\s*%\s*\('),
        re.compile(r'"[^"]*"\s*\.format\s*\('),
    ),
    credential_variable_names=(
        "connection_string", "conn_str", "password", "dsn",
    ),
    resource_creation_patterns=(
        re.compile(r'psycopg2\.connect\s*\('),
    ),
    dispose_patterns=(
        re.compile(r'\bwith\b'),
        re.compile(r'\.close\s*\('),
    ),
    health_check_query="SELECT 1",
)
DatabasePatternRegistry.register(_psycopg2)

# ---------------------------------------------------------------------------
# Node.js — node-postgres (pg)
# ---------------------------------------------------------------------------

_node_pg = DatabasePattern(
    database=DatabaseType.POSTGRESQL,
    client_library="pg",
    language="nodejs",
    safe_param_syntax=(
        '$1 with array: client.query("SELECT * FROM t WHERE id = $1", [id])',
    ),
    safe_patterns=(
        re.compile(r'\$\d+'),
        re.compile(r'\.query\s*\([^,]+,\s*\['),
    ),
    unsafe_patterns=(
        re.compile(r'`[^`]*\$\{[^}]+\}[^`]*`'),
        re.compile(r'"[^"]*"\s*\+\s*\w+'),
        re.compile(r"'[^']*'\s*\+\s*\w+"),
    ),
    credential_variable_names=(
        "connectionString", "password", "DATABASE_URL",
    ),
    resource_creation_patterns=(
        re.compile(r'new\s+Pool\s*\('),
        re.compile(r'new\s+Client\s*\('),
    ),
    dispose_patterns=(
        re.compile(r'\.end\s*\('),
        re.compile(r'\.release\s*\('),
    ),
    health_check_query="SELECT 1",
)
DatabasePatternRegistry.register(_node_pg)
