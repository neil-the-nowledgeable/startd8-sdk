"""SQL injection detection — REQ-QP-600.

Two-pass approach:
1. Identify SQL construction sites (lines matching unsafe patterns)
2. Check if same or adjacent lines have safe parameterization patterns (suppression)

Comment-aware: skips // and /* */ comment lines.
"""

from __future__ import annotations

import hashlib
import re
from typing import List, Optional

from ..models import DatabaseType, SecurityCheckType, SecurityFinding
from ..patterns import DatabasePatternRegistry


# Comment patterns for supported languages
_LINE_COMMENT = re.compile(r'^\s*(?://|#)')
_BLOCK_COMMENT_START = re.compile(r'/\*')
_BLOCK_COMMENT_END = re.compile(r'\*/')

# SQL keywords that indicate a SQL construction site
_SQL_KEYWORDS = re.compile(
    r'\b(?:SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|TRUNCATE)\b',
    re.IGNORECASE,
)


def _is_comment_line(line: str) -> bool:
    """Check if a line is a single-line comment."""
    return bool(_LINE_COMMENT.match(line))


def detect_injection(
    source: str,
    database: DatabaseType | str,
    language: str,
    *,
    file_path: Optional[str] = None,
) -> List[SecurityFinding]:
    """Detect SQL injection vulnerabilities in source code.

    Args:
        source: Source code text.
        database: Database type for pattern lookup.
        language: Programming language for pattern lookup.
        file_path: Optional file path for finding attribution.

    Returns:
        List of SecurityFinding with check_type=INJECTION.
    """
    db_val = database.value if isinstance(database, DatabaseType) else database
    pattern = DatabasePatternRegistry.get(database, language)
    if pattern is None:
        return []

    findings: List[SecurityFinding] = []
    lines = source.splitlines()
    in_block_comment = False

    for line_no, line in enumerate(lines, start=1):
        # Track block comments
        if in_block_comment:
            if _BLOCK_COMMENT_END.search(line):
                in_block_comment = False
            continue
        if _BLOCK_COMMENT_START.search(line) and not _BLOCK_COMMENT_END.search(line):
            in_block_comment = True
            continue

        # Skip single-line comments
        if _is_comment_line(line):
            continue

        # Pass 1: Check for unsafe patterns on this line
        for unsafe_re in pattern.unsafe_patterns:
            if not unsafe_re.search(line):
                continue

            # Only flag lines that look like SQL construction sites
            if not _SQL_KEYWORDS.search(line):
                # Check adjacent lines for SQL context (within 3 lines)
                context_start = max(0, line_no - 4)
                context_end = min(len(lines), line_no + 2)
                context_lines = lines[context_start:context_end]
                if not any(_SQL_KEYWORDS.search(cl) for cl in context_lines):
                    continue

            # Pass 2: Check for safe parameterization on same or adjacent lines
            suppressed = False
            check_start = max(0, line_no - 2)
            check_end = min(len(lines), line_no + 2)
            for check_line in lines[check_start:check_end]:
                if any(safe_re.search(check_line) for safe_re in pattern.safe_patterns):
                    suppressed = True
                    break

            if not suppressed:
                pattern_hash = hashlib.sha256(
                    f"{line_no}:{line.strip()}".encode()
                ).hexdigest()[:12]
                findings.append(SecurityFinding(
                    check_type=SecurityCheckType.INJECTION,
                    severity="error",
                    message=(
                        f"Potential SQL injection: unsafe string construction "
                        f"without parameterized query on line {line_no}"
                    ),
                    line=line_no,
                    file_path=file_path,
                    database=db_val,
                    pattern_hash=pattern_hash,
                ))
                break  # One finding per line

    return findings
