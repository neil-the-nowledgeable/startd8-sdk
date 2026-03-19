"""Redis safe and unsafe patterns.

Redis is command-based (no SQL), so injection checks focus on
credential patterns and connection lifecycle.
"""

from __future__ import annotations

import re

from ..models import DatabaseType
from . import DatabasePattern, DatabasePatternRegistry

# ---------------------------------------------------------------------------
# C# — StackExchange.Redis
# ---------------------------------------------------------------------------

_redis_csharp = DatabasePattern(
    database=DatabaseType.REDIS,
    client_library="StackExchange.Redis",
    language="csharp",
    safe_param_syntax=(
        'db.StringGet(key) — command-based API, no SQL injection risk',
    ),
    safe_patterns=(
        re.compile(r'\.StringGet\s*\('),
        re.compile(r'\.StringSet\s*\('),
        re.compile(r'\.HashGet\s*\('),
        re.compile(r'\.HashSet\s*\('),
        re.compile(r'\.KeyDelete\s*\('),
    ),
    unsafe_patterns=(
        # Lua script injection via string interpolation
        re.compile(r'\$"[^"]*(?:EVAL|EVALSHA)[^"]*\{[^}]+\}[^"]*"', re.IGNORECASE),
    ),
    credential_variable_names=(
        "connectionString", "redisConnectionString", "password", "Password",
        "ConfigurationOptions",
    ),
    resource_creation_patterns=(
        re.compile(r'ConnectionMultiplexer\.Connect\s*\('),
    ),
    dispose_patterns=(
        re.compile(r'\busing\s*\('),
        re.compile(r'\.Dispose\s*\('),
        re.compile(r'\.Close\s*\('),
    ),
    health_check_query="PING",
)
DatabasePatternRegistry.register(_redis_csharp)

# ---------------------------------------------------------------------------
# Python — redis-py
# ---------------------------------------------------------------------------

_redis_python = DatabasePattern(
    database=DatabaseType.REDIS,
    client_library="redis",
    language="python",
    safe_param_syntax=(
        'r.get(key) — command-based API, no SQL injection risk',
    ),
    safe_patterns=(
        re.compile(r'\.get\s*\('),
        re.compile(r'\.set\s*\('),
        re.compile(r'\.hget\s*\('),
        re.compile(r'\.hset\s*\('),
        re.compile(r'\.delete\s*\('),
    ),
    unsafe_patterns=(
        re.compile(r'\.eval\s*\([^)]*f"', re.IGNORECASE),
        re.compile(r"\.eval\s*\([^)]*f'", re.IGNORECASE),
    ),
    credential_variable_names=(
        "redis_url", "password", "REDIS_URL",
    ),
    resource_creation_patterns=(
        re.compile(r'redis\.Redis\s*\('),
        re.compile(r'redis\.from_url\s*\('),
    ),
    dispose_patterns=(
        re.compile(r'\.close\s*\('),
        re.compile(r'\bwith\b'),
    ),
    health_check_query="PING",
)
DatabasePatternRegistry.register(_redis_python)

# ---------------------------------------------------------------------------
# Node.js — ioredis / redis
# ---------------------------------------------------------------------------

_redis_nodejs = DatabasePattern(
    database=DatabaseType.REDIS,
    client_library="ioredis",
    language="nodejs",
    safe_param_syntax=(
        'redis.get(key) — command-based API, no SQL injection risk',
    ),
    safe_patterns=(
        re.compile(r'\.get\s*\('),
        re.compile(r'\.set\s*\('),
        re.compile(r'\.hget\s*\('),
        re.compile(r'\.del\s*\('),
    ),
    unsafe_patterns=(
        re.compile(r'\.eval\s*\([^)]*`[^`]*\$\{', re.IGNORECASE),
    ),
    credential_variable_names=(
        "REDIS_URL", "password",
    ),
    resource_creation_patterns=(
        re.compile(r'new\s+Redis\s*\('),
        re.compile(r'createClient\s*\('),
    ),
    dispose_patterns=(
        re.compile(r'\.quit\s*\('),
        re.compile(r'\.disconnect\s*\('),
    ),
    health_check_query="PING",
)
DatabasePatternRegistry.register(_redis_nodejs)
