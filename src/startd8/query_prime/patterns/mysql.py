"""MySQL safe and unsafe patterns.

Covers MySqlConnector (C#), mysql-connector-python (Python).
"""

from __future__ import annotations

import re

from ..models import DatabaseType
from . import DatabasePattern, DatabasePatternRegistry

# ---------------------------------------------------------------------------
# C# — MySqlConnector
# ---------------------------------------------------------------------------

_mysql_csharp = DatabasePattern(
    database=DatabaseType.MYSQL,
    client_library="MySqlConnector",
    language="csharp",
    safe_param_syntax=(
        '@param with MySqlParameter',
        'cmd.Parameters.AddWithValue("@name", value)',
    ),
    safe_patterns=(
        re.compile(r'@\w+'),
        re.compile(r'MySqlParameter', re.IGNORECASE),
        re.compile(r'Parameters\.Add', re.IGNORECASE),
        re.compile(r'AddWithValue', re.IGNORECASE),
    ),
    unsafe_patterns=(
        re.compile(r'\$"[^"]*\{[^}]+\}[^"]*"'),
        re.compile(r'"[^"]*"\s*\+\s*\w+'),
        re.compile(r'String\.Format\s*\([^)]*(?:SELECT|INSERT|UPDATE|DELETE)', re.IGNORECASE),
    ),
    credential_variable_names=(
        "connectionString", "connStr", "password", "Password",
    ),
    resource_creation_patterns=(
        re.compile(r'new\s+MySqlConnection\s*\('),
    ),
    dispose_patterns=(
        re.compile(r'\busing\s*\('),
        re.compile(r'\bawait\s+using\b'),
        re.compile(r'\.Dispose\s*\('),
    ),
    health_check_query="SELECT 1",
)
DatabasePatternRegistry.register(_mysql_csharp)

# ---------------------------------------------------------------------------
# Python — mysql-connector-python
# ---------------------------------------------------------------------------

_mysql_python = DatabasePattern(
    database=DatabaseType.MYSQL,
    client_library="mysql-connector-python",
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
        "connection_string", "conn_str", "password",
    ),
    resource_creation_patterns=(
        re.compile(r'mysql\.connector\.connect\s*\('),
    ),
    dispose_patterns=(
        re.compile(r'\bwith\b'),
        re.compile(r'\.close\s*\('),
    ),
    health_check_query="SELECT 1",
)
DatabasePatternRegistry.register(_mysql_python)
