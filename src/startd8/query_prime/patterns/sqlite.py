"""SQLite safe and unsafe patterns.

Covers sqlite3 (Python) — the most common SQLite client.
"""

from __future__ import annotations

import re

from ..models import DatabaseType
from . import DatabasePattern, DatabasePatternRegistry

# ---------------------------------------------------------------------------
# Python — sqlite3
# ---------------------------------------------------------------------------

_sqlite_python = DatabasePattern(
    database=DatabaseType.SQLITE,
    client_library="sqlite3",
    language="python",
    safe_param_syntax=(
        '? with tuple: cursor.execute("SELECT * FROM t WHERE id = ?", (id,))',
    ),
    safe_patterns=(
        re.compile(r'\?'),
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
        "db_path", "database_path",
    ),
    resource_creation_patterns=(
        re.compile(r'sqlite3\.connect\s*\('),
    ),
    dispose_patterns=(
        re.compile(r'\bwith\b'),
        re.compile(r'\.close\s*\('),
    ),
    health_check_query="SELECT 1",
)
DatabasePatternRegistry.register(_sqlite_python)

# ---------------------------------------------------------------------------
# C# — Microsoft.Data.Sqlite
# ---------------------------------------------------------------------------

_sqlite_csharp = DatabasePattern(
    database=DatabaseType.SQLITE,
    client_library="Microsoft.Data.Sqlite",
    language="csharp",
    safe_param_syntax=(
        '@param with SqliteParameter',
        'cmd.Parameters.AddWithValue("@name", value)',
    ),
    safe_patterns=(
        # @param inside SQL string literal (not bare C# @identifier)
        re.compile(r'["\'].*@\w+.*["\']'),
        re.compile(r'SqliteParameter', re.IGNORECASE),
        re.compile(r'Parameters\.Add', re.IGNORECASE),
        re.compile(r'AddWithValue', re.IGNORECASE),
    ),
    unsafe_patterns=(
        re.compile(r'\$"[^"]*\{[^}]+\}[^"]*"'),
        re.compile(r'"[^"]*"\s*\+\s*\w+'),
    ),
    credential_variable_names=(
        "connectionString", "connStr",
    ),
    resource_creation_patterns=(
        re.compile(r'new\s+SqliteConnection\s*\('),
    ),
    dispose_patterns=(
        re.compile(r'\busing\s*\('),
        re.compile(r'\.Dispose\s*\('),
    ),
    health_check_query="SELECT 1",
)
DatabasePatternRegistry.register(_sqlite_csharp)

# ---------------------------------------------------------------------------
# Node.js — better-sqlite3
# ---------------------------------------------------------------------------

_sqlite_nodejs = DatabasePattern(
    database=DatabaseType.SQLITE,
    client_library="better-sqlite3",
    language="nodejs",
    safe_param_syntax=(
        '? with args: stmt.run(value)',
        'db.prepare("SELECT * FROM t WHERE id = ?").get(id)',
    ),
    safe_patterns=(
        re.compile(r'\?'),
        re.compile(r'\.prepare\s*\('),
        re.compile(r'\.run\s*\('),
        re.compile(r'\.get\s*\('),
        re.compile(r'\.all\s*\('),
    ),
    unsafe_patterns=(
        re.compile(r'`[^`]*\$\{[^}]+\}[^`]*`'),
        re.compile(r'"[^"]*"\s*\+\s*\w+'),
        re.compile(r"'[^']*'\s*\+\s*\w+"),
    ),
    credential_variable_names=(
        "dbPath", "databasePath",
    ),
    resource_creation_patterns=(
        re.compile(r'new\s+Database\s*\('),
    ),
    dispose_patterns=(
        re.compile(r'\.close\s*\('),
    ),
    health_check_query="SELECT 1",
)
DatabasePatternRegistry.register(_sqlite_nodejs)
