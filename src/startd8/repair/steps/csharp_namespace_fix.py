"""Fix namespace-filepath alignment in C# files (P4-2).

When the namespace declaration doesn't match the directory structure,
rewrites it to match. For example, if the file is at
``src/cartservice/src/services/CartService.cs`` and declares
``namespace cartservice``, rewrites to ``namespace cartservice.services``.

Uses file-scoped namespace syntax (``namespace X.Y;``) for .NET 6+ projects.
Only fires for .cs files.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..models import ElementContext, RepairContext, RepairStepResult

# Match block-scoped: namespace Foo.Bar {
_BLOCK_NS_RE = re.compile(
    r'^(\s*)namespace\s+([\w.]+)\s*\{', re.MULTILINE,
)
# Match file-scoped: namespace Foo.Bar;
_FILE_NS_RE = re.compile(
    r'^(\s*)namespace\s+([\w.]+)\s*;', re.MULTILINE,
)


def _infer_namespace_from_path(file_path: Path) -> Optional[str]:
    """Infer expected namespace from directory structure.

    Looks for common root markers (src/, Services/, Models/) and builds
    a dotted namespace from the directory segments.
    """
    parts = file_path.parts
    # Find the 'src' directory as root anchor
    src_indices = [i for i, p in enumerate(parts) if p.lower() == "src"]
    if src_indices:
        start = src_indices[-1] + 1  # skip 'src' itself
    else:
        # Fallback: use last 2-3 directory segments
        start = max(0, len(parts) - 3)

    # Take directory segments (exclude filename)
    ns_parts = list(parts[start:-1])
    if not ns_parts:
        return None

    # PascalCase each segment
    return ".".join(
        seg[0].upper() + seg[1:] if seg else seg
        for seg in ns_parts
    )


class CSharpNamespaceFixStep:
    """Rewrite namespace declaration to match directory structure."""

    name: str = "csharp_namespace_fix"

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

        expected_ns = _infer_namespace_from_path(file_path)
        if not expected_ns:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        result = code
        modified = False

        # Try file-scoped first (preferred for .NET 6+)
        match = _FILE_NS_RE.search(result)
        if match:
            current_ns = match.group(2)
            if current_ns != expected_ns:
                result = result[:match.start(2)] + expected_ns + result[match.end(2):]
                modified = True
        else:
            # Try block-scoped
            match = _BLOCK_NS_RE.search(result)
            if match:
                current_ns = match.group(2)
                if current_ns != expected_ns:
                    result = result[:match.start(2)] + expected_ns + result[match.end(2):]
                    modified = True

        return RepairStepResult(
            step_name=self.name,
            modified=modified,
            code=result,
            metrics={"namespace_rewritten": 1 if modified else 0},
        )
