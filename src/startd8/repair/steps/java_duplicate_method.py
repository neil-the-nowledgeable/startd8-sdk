"""Remove duplicate method definitions in Java files (P4-1).

When the same method signature appears twice (same name + parameter types),
removes the second occurrence. Preserves the first definition.

Uses text-based detection (not AST) for robustness — matches method
declarations by name and parameter count. Only fires for .java files.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..models import ElementContext, RepairContext, RepairStepResult

# Match method declarations: captures access modifier + return type + name + params
_METHOD_DECL_RE = re.compile(
    r'^(\s+)'                           # indent
    r'(?:@\w+\s+)*'                     # optional annotations
    r'(?:public|protected|private)\s+'   # access modifier
    r'(?:static\s+)?'                   # optional static
    r'(?:final\s+)?'                    # optional final
    r'(?:synchronized\s+)?'             # optional synchronized
    r'(?:\w+(?:<[^>]+>)?\s+)'           # return type
    r'(\w+)'                            # method name (capture)
    r'\s*\(([^)]*)\)'                   # parameters (capture)
    r'\s*(?:throws\s+[\w,\s]+)?'        # optional throws
    r'\s*\{',                           # opening brace
)


def _param_signature(params: str) -> str:
    """Normalize parameter list to a comparable signature."""
    if not params.strip():
        return "()"
    # Extract type names only (strip parameter names and whitespace)
    parts = []
    for param in params.split(","):
        tokens = param.strip().split()
        if tokens:
            # Last token is the name; everything before is the type
            type_tokens = tokens[:-1] if len(tokens) > 1 else tokens
            parts.append(" ".join(type_tokens))
    return "(" + ",".join(parts) + ")"


class JavaDuplicateMethodStep:
    """Remove duplicate method definitions, keeping the first occurrence."""

    name: str = "java_duplicate_method_fix"

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
        # First pass: find all method declarations and their positions
        methods: dict[str, list[int]] = {}  # signature → [line indices]
        for i, line in enumerate(lines):
            match = _METHOD_DECL_RE.match(line)
            if match:
                name = match.group(2)
                params = match.group(3)
                sig = f"{name}{_param_signature(params)}"
                methods.setdefault(sig, []).append(i)

        # Find lines to remove (second+ occurrence of each duplicate)
        lines_to_remove: set[int] = set()
        for sig, positions in methods.items():
            if len(positions) > 1:
                # Keep first, mark rest for removal
                for pos in positions[1:]:
                    # Remove the method body (from declaration to matching close brace)
                    depth = 0
                    j = pos
                    while j < len(lines):
                        depth += lines[j].count("{") - lines[j].count("}")
                        lines_to_remove.add(j)
                        if depth <= 0:
                            break
                        j += 1
                    # Also remove preceding annotations/comments
                    k = pos - 1
                    while k >= 0:
                        stripped = lines[k].strip()
                        if stripped.startswith("@") or stripped.startswith("//") or stripped == "":
                            lines_to_remove.add(k)
                            k -= 1
                        else:
                            break

        if not lines_to_remove:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        result_lines = [
            line for i, line in enumerate(lines)
            if i not in lines_to_remove
        ]
        return RepairStepResult(
            step_name=self.name,
            modified=True,
            code="".join(result_lines),
            metrics={"methods_removed": len([
                sig for sig, pos in methods.items() if len(pos) > 1
            ])},
        )
