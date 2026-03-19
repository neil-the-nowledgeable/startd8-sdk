"""Resource lifecycle issue detection — REQ-QP-602.

Detects per-request resource creation (connection pool exhaustion)
and missing dispose patterns.
"""

from __future__ import annotations

import hashlib
import re
from typing import List, Optional

from ..models import DatabaseType, SecurityCheckType, SecurityFinding
from ..patterns import DatabasePatternRegistry


# Comment patterns
_LINE_COMMENT = re.compile(r'^\s*(?://|#)')

# Scope-limiting patterns: using/with/defer indicate proper lifecycle
_SCOPE_PATTERNS = {
    "csharp": (
        re.compile(r'\busing\s*\('),
        re.compile(r'\bawait\s+using\b'),
    ),
    "python": (
        re.compile(r'\bwith\b'),
    ),
    "go": (
        re.compile(r'\bdefer\b'),
    ),
    "nodejs": (),  # Node.js typically uses .end()/.release() checked via dispose_patterns
    "java": (
        re.compile(r'\btry\s*\('),  # try-with-resources
    ),
}


def detect_lifecycle_issues(
    source: str,
    database: DatabaseType | str,
    language: str,
    *,
    file_path: Optional[str] = None,
) -> List[SecurityFinding]:
    """Detect resource lifecycle issues (connection pool exhaustion).

    Checks for resource creation patterns without corresponding
    dispose patterns in the surrounding context.

    Args:
        source: Source code text.
        database: Database type for pattern lookup.
        language: Programming language.
        file_path: Optional file path for finding attribution.

    Returns:
        List of SecurityFinding with check_type=LIFECYCLE.
    """
    pattern = DatabasePatternRegistry.get(database, language)
    if pattern is None:
        return []

    if not pattern.resource_creation_patterns:
        return []

    findings: List[SecurityFinding] = []
    lines = source.splitlines()

    for line_no, line in enumerate(lines, start=1):
        if _LINE_COMMENT.match(line):
            continue

        # Check if this line creates a resource
        for creation_re in pattern.resource_creation_patterns:
            if not creation_re.search(line):
                continue

            # Check surrounding context for dispose patterns
            context_start = max(0, line_no - 4)
            context_end = min(len(lines), line_no + 6)
            context_lines = lines[context_start:context_end]
            context_text = "\n".join(context_lines)

            has_dispose = False

            # Check language-specific scope patterns
            scope_patterns = _SCOPE_PATTERNS.get(language, ())
            for scope_re in scope_patterns:
                if scope_re.search(context_text):
                    has_dispose = True
                    break

            # Check database-specific dispose patterns
            if not has_dispose:
                for dispose_re in pattern.dispose_patterns:
                    if dispose_re.search(context_text):
                        has_dispose = True
                        break

            if not has_dispose:
                pattern_hash = hashlib.sha256(
                    f"{line_no}:{line.strip()}".encode()
                ).hexdigest()[:12]
                findings.append(SecurityFinding(
                    check_type=SecurityCheckType.LIFECYCLE,
                    severity="warning",
                    message=(
                        f"Resource lifecycle: resource creation without dispose "
                        f"pattern on line {line_no} — potential connection pool "
                        f"exhaustion"
                    ),
                    line=line_no,
                    file_path=file_path,
                    database=(
                        database.value if isinstance(database, DatabaseType) else database
                    ),
                    pattern_hash=pattern_hash,
                ))
                break  # One finding per creation site

    return findings
