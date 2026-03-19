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
    r'\b(?:connectionString|connStr|conn_str|connection_string|'
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

    return findings
