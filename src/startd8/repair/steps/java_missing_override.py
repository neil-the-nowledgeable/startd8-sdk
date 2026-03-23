"""Insert @Override annotations on methods that override superclass methods (P4-1).

Detects methods that match common override signatures (toString, equals,
hashCode, close, run, compareTo, iterator, hasNext, next) without an
existing @Override annotation. Inserts ``@Override`` on the line before
the method declaration.

Only fires for .java files. Conservative: only annotates well-known
override candidates to avoid false positives.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..models import ElementContext, RepairContext, RepairStepResult

# Well-known method names that are almost always overrides when present
_OVERRIDE_CANDIDATES = frozenset({
    "toString", "equals", "hashCode", "close", "run",
    "compareTo", "iterator", "hasNext", "next", "clone",
    "finalize", "onStart", "onStop", "onCreate", "onDestroy",
})

# Match method declarations for override candidates (not constructors, not static)
_METHOD_RE = re.compile(
    r'^(\s+)'                           # leading whitespace (capture indent)
    r'(?:public|protected)\s+'          # access modifier (required for overrides)
    r'(?!static\s)'                     # NOT static
    r'(?:\w+(?:<[^>]+>)?\s+)?'          # optional return type
    r'(' + '|'.join(_OVERRIDE_CANDIDATES) + r')'  # method name
    r'\s*\(',                           # opening paren
)


class JavaMissingOverrideStep:
    """Insert @Override before methods that override superclass methods."""

    name: str = "java_missing_override"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        if file_path.suffix.lower() != ".java":
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        lines = code.splitlines(keepends=True)
        result_lines: list[str] = []
        count = 0

        for i, line in enumerate(lines):
            match = _METHOD_RE.match(line)
            if match:
                indent = match.group(1)
                # Check if previous non-blank line already has @Override
                prev_idx = len(result_lines) - 1
                while prev_idx >= 0 and not result_lines[prev_idx].strip():
                    prev_idx -= 1
                already_annotated = (
                    prev_idx >= 0
                    and "@Override" in result_lines[prev_idx]
                )
                if not already_annotated:
                    result_lines.append(f"{indent}@Override\n")
                    count += 1
            result_lines.append(line)

        return RepairStepResult(
            step_name=self.name,
            modified=count > 0,
            code="".join(result_lines),
            metrics={"overrides_added": count},
        )
