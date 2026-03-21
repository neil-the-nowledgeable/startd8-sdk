"""Credential leakage detection — REQ-QP-601.

Detects logging calls that include credential-named variables.
False-positive suppression: allows host, port, database individually.
"""

from __future__ import annotations

import hashlib
import re
from typing import List, Optional

from ..models import SecurityCheckType, SecurityFinding


# Credential-bearing variable name patterns
_CREDENTIAL_NAMES = re.compile(
    r'_?(?:connectionString|connStr|conn_str|connection_string|'
    r'databaseString|dbString|db_string|'
    r'password|Password|secret|Secret|credential|Credential|'
    r'apiKey|api_key|ApiKey|'
    r'private_key|privateKey|PrivateKey|'
    r'access_token|accessToken|AccessToken)\b'
)

# Logging/output call patterns per language
_LOG_PATTERNS = {
    "csharp": re.compile(
        r'(?:Console\.Write(?:Line)?|Debug\.Write(?:Line)?|'
        r'Trace\.Write(?:Line)?|'
        r'_?logger\.(?:Log|Info|Warn|Error|Debug|Trace|Fatal|Critical)|'
        r'Log(?:ger)?\.(?:Info|Warn|Error|Debug|Trace|Fatal|Critical))\s*\(',
        re.IGNORECASE,
    ),
    "python": re.compile(
        r'(?:print|logging\.(?:info|warning|error|debug|critical)|'
        r'logger\.(?:info|warning|error|debug|critical)|'
        r'log\.(?:info|warning|error|debug|critical))\s*\(',
        re.IGNORECASE,
    ),
    "nodejs": re.compile(
        r'(?:console\.(?:log|warn|error|debug|info)|'
        r'logger\.(?:info|warn|error|debug))\s*\(',
        re.IGNORECASE,
    ),
    "go": re.compile(
        r'(?:fmt\.Print(?:f|ln)?|log\.Print(?:f|ln)?|'
        r'logger\.(?:Info|Warn|Error|Debug))\s*\(',
        re.IGNORECASE,
    ),
    "java": re.compile(
        r'(?:System\.out\.print(?:ln)?|System\.err\.print(?:ln)?|'
        r'logger\.(?:info|warn|error|debug|trace)|'
        r'log\.(?:info|warn|error|debug|trace))\s*\(',
        re.IGNORECASE,
    ),
}

# Comment patterns
_LINE_COMMENT = re.compile(r'^\s*(?://|#)')

# Exception info disclosure: interpolating exception objects into
# throw/raise statements exposes stack traces and potentially
# connection strings to external callers (gRPC clients, HTTP responses).
_EXCEPTION_INTERPOLATION = re.compile(
    r'(?:throw\s+new\s+\w*Exception|raise\s+\w*Error)\s*\([^)]*'
    r'\{(?:ex|exc|e|error|err)\}',
)


def detect_credential_leakage(
    source: str,
    language: str,
    *,
    file_path: Optional[str] = None,
) -> List[SecurityFinding]:
    """Detect credential leakage via logging calls.

    Args:
        source: Source code text.
        language: Programming language.
        file_path: Optional file path for finding attribution.

    Returns:
        List of SecurityFinding with check_type=CREDENTIAL_LEAKAGE.
    """
    log_pattern = _LOG_PATTERNS.get(language)
    if log_pattern is None:
        return []

    findings: List[SecurityFinding] = []
    lines = source.splitlines()

    for line_no, line in enumerate(lines, start=1):
        if _LINE_COMMENT.match(line):
            continue

        # Check if line has a logging call
        if not log_pattern.search(line):
            continue

        # Check if credential-named variables appear on the same line
        if not _CREDENTIAL_NAMES.search(line):
            continue

        pattern_hash = hashlib.sha256(
            f"{line_no}:{line.strip()}".encode()
        ).hexdigest()[:12]
        findings.append(SecurityFinding(
            check_type=SecurityCheckType.CREDENTIAL_LEAKAGE,
            severity="error",
            message=(
                f"Credential leakage: logging call includes credential-bearing "
                f"variable on line {line_no}"
            ),
            line=line_no,
            file_path=file_path,
            pattern_hash=pattern_hash,
        ))

    # Pass 2: Exception info disclosure — interpolating exception objects
    # into throw/raise exposes internals to external callers.
    # Check both single-line and multiline throw patterns.
    in_throw = False
    throw_start = 0
    for line_no, line in enumerate(lines, start=1):
        if _LINE_COMMENT.match(line):
            continue
        stripped = line.strip()

        # Track multiline throw context (within 3 lines of throw/raise)
        if re.search(r'throw\s+new\s+\w*Exception|raise\s+\w*Error', stripped):
            in_throw = True
            throw_start = line_no

        if in_throw and line_no - throw_start > 3:
            in_throw = False

        # Check for exception interpolation on this line or in throw context
        has_exc_interp = re.search(r'\{(?:ex|exc|e|error|err)\}', stripped)
        if has_exc_interp and (in_throw or _EXCEPTION_INTERPOLATION.search(stripped)):
            pattern_hash = hashlib.sha256(
                f"exc:{line_no}:{stripped}".encode()
            ).hexdigest()[:12]
            findings.append(SecurityFinding(
                check_type=SecurityCheckType.CREDENTIAL_LEAKAGE,
                severity="warning",
                message=(
                    f"Exception info disclosure: exception object interpolated "
                    f"into thrown exception on line {line_no} — may expose "
                    f"stack traces or connection strings to external callers"
                ),
                line=line_no,
                file_path=file_path,
                pattern_hash=pattern_hash,
            ))
            in_throw = False  # Don't double-report same throw

    return findings
