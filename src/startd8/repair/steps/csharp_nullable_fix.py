"""Insert <Nullable>enable</Nullable> into .csproj files (P4-2).

When a .csproj file has a <PropertyGroup> but no <Nullable> element,
inserts ``<Nullable>enable</Nullable>`` after the first <PropertyGroup> tag.

Only fires for .csproj files.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..models import ElementContext, RepairContext, RepairStepResult

_PROPERTY_GROUP_RE = re.compile(r'(<PropertyGroup[^>]*>)', re.IGNORECASE)
_NULLABLE_RE = re.compile(r'<Nullable>', re.IGNORECASE)


class CSharpNullableFixStep:
    """Insert <Nullable>enable</Nullable> in .csproj PropertyGroup."""

    name: str = "csharp_nullable_fix"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        if file_path.suffix.lower() != ".csproj":
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        # Already has Nullable element
        if _NULLABLE_RE.search(code):
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        # Find first PropertyGroup and insert after it
        match = _PROPERTY_GROUP_RE.search(code)
        if not match:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        # Detect indentation from the PropertyGroup line
        line_start = code.rfind("\n", 0, match.start()) + 1
        indent = ""
        for ch in code[line_start:match.start()]:
            if ch in (" ", "\t"):
                indent += ch
            else:
                break
        child_indent = indent + "    "

        insert_pos = match.end()
        insert_text = f"\n{child_indent}<Nullable>enable</Nullable>"
        result = code[:insert_pos] + insert_text + code[insert_pos:]

        return RepairStepResult(
            step_name=self.name,
            modified=True,
            code=result,
            metrics={"nullable_inserted": 1},
        )
