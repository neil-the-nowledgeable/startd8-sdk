"""Add missing access modifiers to C# type declarations (P4-2).

When a class, struct, interface, or enum declaration lacks an explicit
access modifier, prefixes with ``public``. This is the most common
intended visibility for generated types.

Only fires for .cs files. Skips nested types (already inside a type block),
comments, and string literals.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..models import ElementContext, RepairContext, RepairStepResult

# Match type declarations without explicit access modifiers.
# Captures: optional modifiers (static, abstract, sealed, partial) + type keyword + name
_UNMODIFIED_TYPE_RE = re.compile(
    r'^(\s*)'                                    # leading indent (capture)
    r'(?!public\s|private\s|protected\s|internal\s)'  # no access modifier
    r'((?:static\s+|abstract\s+|sealed\s+|partial\s+)*)'  # optional other modifiers
    r'(class|struct|interface|enum|record)\s+'     # type keyword (capture)
    r'(\w+)',                                      # type name
)


class CSharpAccessModifierStep:
    """Add ``public`` access modifier to type declarations missing one."""

    name: str = "csharp_access_modifier_fix"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        if file_path.suffix.lower() != ".cs":
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        lines = code.splitlines(keepends=True)
        result_lines: list[str] = []
        count = 0
        depth = 0  # brace depth — only fix top-level types

        for line in lines:
            stripped = line.strip()

            # Track brace depth to skip nested types
            depth += stripped.count("{") - stripped.count("}")

            # Skip comments
            if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
                result_lines.append(line)
                continue

            # Only fix declarations at namespace level (depth <= 1)
            if depth <= 1:
                match = _UNMODIFIED_TYPE_RE.match(line)
                if match:
                    indent = match.group(1)
                    modifiers = match.group(2)
                    type_kw = match.group(3)
                    name = match.group(4)
                    # Reconstruct with public prefix
                    new_line = f"{indent}public {modifiers}{type_kw} {name}"
                    # Append everything after the name from the original line
                    after_name = line[match.end():]
                    new_line += after_name
                    if new_line != line:
                        count += 1
                        result_lines.append(new_line)
                        continue

            result_lines.append(line)

        return RepairStepResult(
            step_name=self.name,
            modified=count > 0,
            code="".join(result_lines),
            metrics={"modifiers_added": count},
        )
