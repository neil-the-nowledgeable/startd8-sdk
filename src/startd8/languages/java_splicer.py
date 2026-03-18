"""Java body splicing — splice generated method bodies into skeleton files.

Uses text-based brace matching (same approach as ``go_splicer.py``). Java's
brace-delimited syntax makes this reliable:
1. Find method declaration by name
2. Locate opening ``{``
3. Match closing ``}`` via depth counting
4. Replace body lines with new implementation
5. Optionally validate via ``javalang.parse.parse()``

Handles:
- Instance methods: ``public ReturnType methodName(...)``
- Static methods: ``public static ReturnType methodName(...)``
- Annotations on preceding lines (e.g. ``@Override``)
- Generic return types (e.g. ``List<String>``)
- Constructors
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from startd8.logging_config import get_logger

logger = get_logger(__name__)


JAVA_SKELETON_SENTINEL = "// [STARTD8-SKELETON]"

JAVA_STUB_PATTERNS = [
    re.compile(r'throw\s+new\s+UnsupportedOperationException\s*\('),
    re.compile(r'throw\s+new\s+RuntimeException\s*\(\s*"not implemented'),
    re.compile(r'throw\s+new\s+RuntimeException\s*\(\s*"TODO'),
]

# Method declaration pattern: [modifiers] [generics] ReturnType methodName(
_METHOD_DECL_RE = re.compile(
    r"^\s*(?:(?:public|private|protected|abstract|static|final|default|"
    r"synchronized|native|strictfp)\s+)*"
    r"(?:<[^>]+>\s+)?"  # optional generics
    r"[\w.<>,\[\]?]+\s+"  # return type
    r"(?P<name>\w+)\s*\(",
)

# Constructor pattern: [modifiers] ClassName(
_CONSTRUCTOR_DECL_RE = re.compile(
    r"^\s*(?:(?:public|private|protected)\s+)?"
    r"(?P<name>[A-Z]\w*)\s*\(",
)


@dataclass
class JavaSpliceResult:
    """Result of a Java body splice operation."""

    code: Optional[str] = None
    methods_spliced: int = 0
    methods_skipped: int = 0
    warnings: List[str] = field(default_factory=list)


def _find_method_declaration(
    lines: List[str],
    method_name: str,
) -> Optional[int]:
    """Find the line index of a method/constructor declaration by name.

    Handles annotations on preceding lines and generic return types.
    """
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Skip annotations, blank lines, comments
        if stripped.startswith("@") or stripped.startswith("//") or not stripped:
            continue

        # Try method pattern
        m = _METHOD_DECL_RE.match(line)
        if m and m.group("name") == method_name:
            return i

        # Try constructor pattern
        m = _CONSTRUCTOR_DECL_RE.match(line)
        if m and m.group("name") == method_name:
            return i

    return None


def _find_body_range(
    lines: List[str],
    decl_line: int,
) -> Optional[tuple[int, int]]:
    """Find the body range (open brace line, close brace line) of a method.

    Handles multi-line signatures by scanning forward from decl_line.
    """
    # Find the opening brace
    open_line = None
    for i in range(decl_line, min(decl_line + 15, len(lines))):
        if "{" in lines[i]:
            open_line = i
            break

    if open_line is None:
        return None

    # Count braces to find matching close
    depth = 0
    for i in range(open_line, len(lines)):
        depth += lines[i].count("{") - lines[i].count("}")
        if depth == 0:
            return (open_line, i)

    return None


def _is_stub_body(body_lines: List[str]) -> bool:
    """Check if method body lines are a stub."""
    body_text = "\n".join(body_lines)

    # Empty body
    if not body_text.strip():
        return True

    for pattern in JAVA_STUB_PATTERNS:
        if pattern.search(body_text):
            return True

    return False


def _extract_body_from_generated(
    generated_code: str,
    method_name: str,
) -> Optional[str]:
    """Extract a method body from generated code.

    Finds the method by name, extracts the body between braces.
    """
    lines = generated_code.splitlines()
    decl = _find_method_declaration(lines, method_name)
    if decl is None:
        return None

    body_range = _find_body_range(lines, decl)
    if body_range is None:
        return None

    open_line, close_line = body_range

    # Extract body lines (between { and })
    body_lines = []
    first_line = lines[open_line]
    brace_pos = first_line.find("{")
    if brace_pos == -1:
        return None
    after_brace = first_line[brace_pos + 1:].strip()
    if after_brace and after_brace != "}":
        body_lines.append(after_brace)

    for i in range(open_line + 1, close_line):
        body_lines.append(lines[i])

    return "\n".join(body_lines)


def _reindent_body(body: str, indent: str) -> str:
    """Dedent body to zero and re-indent to target level."""
    dedented = textwrap.dedent(body)
    result_lines = []
    for line in dedented.splitlines():
        if line.strip():
            result_lines.append(indent + line.lstrip())
        else:
            result_lines.append("")
    return "\n".join(result_lines)


def splice_java_bodies(
    skeleton: str,
    generated_bodies: Dict[str, str],
) -> JavaSpliceResult:
    """Splice generated method bodies into a Java skeleton file.

    Args:
        skeleton: Skeleton file content with stub methods.
        generated_bodies: Dict mapping method names to generated code
            containing the full method (including signature and body).

    Returns:
        JavaSpliceResult with spliced code and statistics.
    """
    result = JavaSpliceResult()
    lines = skeleton.splitlines()
    spliced = 0
    skipped = 0

    # Each splice replaces `lines` with a new list — forward indices shift,
    # but we re-scan from the top each iteration so this is safe.
    for method_name, gen_code in generated_bodies.items():
        decl = _find_method_declaration(lines, method_name)
        if decl is None:
            result.warnings.append(
                f"Method '{method_name}' not found in skeleton"
            )
            skipped += 1
            continue

        body_range = _find_body_range(lines, decl)
        if body_range is None:
            result.warnings.append(
                f"Could not find body braces for '{method_name}'"
            )
            skipped += 1
            continue

        open_line, close_line = body_range

        # Check if the existing body is a stub
        body_lines = lines[open_line + 1: close_line]
        if not _is_stub_body(body_lines):
            result.warnings.append(
                f"'{method_name}' body is not a stub — skipping"
            )
            skipped += 1
            continue

        # Extract new body from generated code
        new_body = _extract_body_from_generated(gen_code, method_name)
        if new_body is None:
            result.warnings.append(
                f"Could not extract body for '{method_name}' from generated code"
            )
            skipped += 1
            continue

        # Determine indentation from the skeleton
        indent = "        "  # Java convention: 2 levels (class + method)
        for bl in body_lines:
            if bl.strip():
                indent = bl[: len(bl) - len(bl.lstrip())]
                break

        # Reindent the new body
        reindented = _reindent_body(new_body, indent)

        # Replace the body lines
        new_lines = (
            lines[: open_line + 1]
            + reindented.splitlines()
            + lines[close_line:]
        )
        lines = new_lines
        spliced += 1

    result.code = "\n".join(lines) + "\n"
    result.methods_spliced = spliced
    result.methods_skipped = skipped

    # Post-splice validation
    _validate_spliced(result)

    return result


def _validate_spliced(result: JavaSpliceResult) -> None:
    """Validate spliced output via javalang if available."""
    if result.code is None:
        return
    try:
        import javalang
        javalang.parse.parse(result.code)
    except ImportError:
        pass
    except Exception as exc:
        result.warnings.append(f"Post-splice validation failed: {exc}")
