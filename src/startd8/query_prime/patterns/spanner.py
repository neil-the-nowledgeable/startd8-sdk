"""Cloud Spanner safe and unsafe patterns.

Critical: @param syntax via SpannerParameterCollection is SAFE (QP-F2 fix).
This was the source of false positives in C# Prime Contractor runs 078-079.
"""

from __future__ import annotations

import re

from ..models import DatabaseType
from . import DatabasePattern, DatabasePatternRegistry

# ---------------------------------------------------------------------------
# C# — Google.Cloud.Spanner.Data
# ---------------------------------------------------------------------------

_spanner_csharp = DatabasePattern(
    database=DatabaseType.SPANNER,
    client_library="Google.Cloud.Spanner.Data",
    language="csharp",
    safe_param_syntax=(
        '@param with SpannerParameterCollection',
        'cmd.Parameters.Add("userId", SpannerDbType.String, userId)',
    ),
    safe_patterns=(
        # @param inside SQL string literal (not bare C# @identifier)
        re.compile(r'["\'].*@\w+.*["\']'),
        re.compile(r'SpannerParameter', re.IGNORECASE),
        re.compile(r'SpannerParameterCollection', re.IGNORECASE),
        re.compile(r'Parameters\.Add\s*\(', re.IGNORECASE),
        re.compile(r'SpannerDbType\.\w+'),
    ),
    unsafe_patterns=(
        # String interpolation in SQL
        re.compile(r'\$"[^"]*\{[^}]+\}[^"]*"'),
        # String concatenation with SQL keywords
        re.compile(r'"[^"]*"\s*\+\s*\w+'),
        re.compile(r'String\.Format\s*\([^)]*(?:SELECT|INSERT|UPDATE|DELETE)', re.IGNORECASE),
    ),
    credential_variable_names=(
        "connectionString", "connStr", "SpannerConnectionStringBuilder",
        "ProjectId", "InstanceId",
    ),
    resource_creation_patterns=(
        re.compile(r'new\s+SpannerConnection\s*\('),
        re.compile(r'SpannerConnection\s*\.\s*CreateCommand'),
    ),
    dispose_patterns=(
        re.compile(r'\busing\s*\('),
        re.compile(r'\bawait\s+using\b'),
        re.compile(r'\busing\s+var\b'),              # C# 8+ declaration form
        re.compile(r'\bawait\s+using\s+var\b'),       # C# 8+ async declaration form
        re.compile(r'\.Dispose\s*\('),
        re.compile(r'\.Close\s*\('),
    ),
    health_check_query="SELECT 1",
)
DatabasePatternRegistry.register(_spanner_csharp)

# ---------------------------------------------------------------------------
# Go — cloud.google.com/go/spanner
# ---------------------------------------------------------------------------

_spanner_go = DatabasePattern(
    database=DatabaseType.SPANNER,
    client_library="cloud.google.com/go/spanner",
    language="go",
    safe_param_syntax=(
        '@param with spanner.Statement{SQL, Params}',
        'spanner.Statement{SQL: "SELECT * FROM t WHERE id = @id", Params: map[string]interface{}{"id": id}}',
    ),
    safe_patterns=(
        # @param inside Go string literal (not bare identifier)
        re.compile(r'["`].*@\w+.*["`]'),
        re.compile(r'spanner\.Statement'),
        re.compile(r'Params:\s*map'),
    ),
    unsafe_patterns=(
        re.compile(r'fmt\.Sprintf\s*\([^)]*(?:SELECT|INSERT|UPDATE|DELETE)', re.IGNORECASE),
        re.compile(r'"[^"]*"\s*\+\s*\w+'),
    ),
    credential_variable_names=(
        "connectionString", "projectID", "instanceID",
    ),
    resource_creation_patterns=(
        re.compile(r'spanner\.NewClient\s*\('),
    ),
    dispose_patterns=(
        re.compile(r'defer\s+\w+\.Close\s*\('),
        re.compile(r'\.Close\s*\('),
    ),
    health_check_query="SELECT 1",
)
DatabasePatternRegistry.register(_spanner_go)

# ---------------------------------------------------------------------------
# Java — com.google.cloud.spanner
# ---------------------------------------------------------------------------

_spanner_java = DatabasePattern(
    database=DatabaseType.SPANNER,
    client_library="com.google.cloud.spanner",
    language="java",
    safe_param_syntax=(
        '@param with Statement.newBuilder().bind()',
        'Statement.newBuilder("SELECT * FROM t WHERE id = @id").bind("id").to(id).build()',
    ),
    safe_patterns=(
        # @param inside Java string literal
        re.compile(r'".*@\w+.*"'),
        re.compile(r'Statement\.newBuilder'),
        re.compile(r'\.bind\s*\('),
    ),
    unsafe_patterns=(
        re.compile(r'String\.format\s*\([^)]*(?:SELECT|INSERT|UPDATE|DELETE)', re.IGNORECASE),
        re.compile(r'"[^"]*"\s*\+\s*\w+'),
    ),
    credential_variable_names=(
        "connectionString", "projectId", "instanceId",
    ),
    resource_creation_patterns=(
        re.compile(r'Spanner\.service\s*\('),
        re.compile(r'SpannerOptions\.newBuilder'),
    ),
    dispose_patterns=(
        re.compile(r'try\s*\('),  # try-with-resources
        re.compile(r'\.close\s*\('),
    ),
    health_check_query="SELECT 1",
)
DatabasePatternRegistry.register(_spanner_java)
