"""Fix raw type usage in Java — add generic type parameters (P4-1).

Replaces bare collection types with parameterized versions:
  List → List<Object>
  Map → Map<String, Object>
  Set → Set<Object>
  Collection → Collection<Object>
  Iterator → Iterator<Object>

Conservative: only fixes declarations (field, local, parameter, return type),
NOT usages in expressions. Skips lines inside comments or strings.
Only fires for .java files.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..models import ElementContext, RepairContext, RepairStepResult

# Raw types that should have generic parameters
_RAW_TYPES = {
    "List": "List<Object>",
    "ArrayList": "ArrayList<Object>",
    "LinkedList": "LinkedList<Object>",
    "Map": "Map<String, Object>",
    "HashMap": "HashMap<String, Object>",
    "TreeMap": "TreeMap<String, Object>",
    "Set": "Set<Object>",
    "HashSet": "HashSet<Object>",
    "TreeSet": "TreeSet<Object>",
    "Collection": "Collection<Object>",
    "Iterator": "Iterator<Object>",
    "Iterable": "Iterable<Object>",
}

# Match raw type in declaration context: preceded by whitespace/modifier,
# followed by whitespace + identifier (field/param name) or > (nested generic).
# Negative lookahead ensures we don't match already-parameterized types.
_RAW_TYPE_RE = re.compile(
    r'\b(' + '|'.join(re.escape(t) for t in _RAW_TYPES) + r')'
    r'(?!<)'           # not already parameterized
    r'(?=\s+\w|\s*\>)' # followed by space+identifier or > (nested)
)


class JavaRawTypeFixStep:
    """Replace raw collection types with parameterized versions."""

    name: str = "java_raw_type_fix"

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
        in_block_comment = False

        for line in lines:
            stripped = line.strip()

            # Track block comments
            if "/*" in stripped and "*/" not in stripped:
                in_block_comment = True
            if "*/" in stripped:
                in_block_comment = False

            # Skip comment and annotation lines
            if in_block_comment or stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("@"):
                result_lines.append(line)
                continue

            # Skip import statements (raw types in imports are valid)
            if stripped.startswith("import "):
                result_lines.append(line)
                continue

            new_line = line
            for raw_type, parameterized in _RAW_TYPES.items():
                # Use word boundary match to avoid partial replacements
                pattern = re.compile(
                    r'\b' + re.escape(raw_type) + r'\b(?!<)(?=\s+\w|\s*\>)',
                )
                new_line = pattern.sub(parameterized, new_line)

            if new_line != line:
                count += 1
            result_lines.append(new_line)

        return RepairStepResult(
            step_name=self.name,
            modified=count > 0,
            code="".join(result_lines),
            metrics={"raw_types_fixed": count},
        )
