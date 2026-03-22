"""C# convention repair step — deterministic fixes for common LLM generation defects.

Four repairs applied in order:
1. XML wrapper tag strip: ``<file path="...">`` / ``</file>`` removed from .sln files
2. Namespace PascalCase: ``namespace cartservice.cartstore`` → ``namespace Cartservice.Cartstore``
3. Block-scoped → file-scoped namespace: ``namespace X {`` → ``namespace X;`` (net8.0+)
4. Missing ``<Nullable>enable</Nullable>`` in .csproj files

All repairs are safe — they fix convention violations without changing semantics.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..models import ElementContext, RepairContext, RepairStepResult


class CSharpConventionFixStep:
    """Deterministic C# convention fixes for LLM-generated code."""

    name: str = "csharp_convention_fix"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        original = code
        repairs: list[str] = []

        suffix = file_path.suffix.lower()
        fname = file_path.name.lower()

        # 1. Strip XML wrapper tags from .sln files
        if suffix == ".sln" or fname.endswith(".sln"):
            code, stripped = _strip_file_wrapper_tag(code)
            if stripped:
                repairs.append("xml_wrapper_tag_stripped")

        # 2. Namespace PascalCase + block-to-file-scoped (for .cs files)
        if suffix == ".cs":
            code, ns_repairs = _fix_namespace_conventions(code, str(file_path))
            repairs.extend(ns_repairs)

        # 3. Missing <Nullable>enable</Nullable> in .csproj
        if suffix == ".csproj":
            code, nullable_added = _fix_missing_nullable(code)
            if nullable_added:
                repairs.append("nullable_enable_added")

        modified = code != original
        return RepairStepResult(
            step_name=self.name,
            modified=modified,
            code=code,
            metrics={"repairs": repairs, "repair_count": len(repairs)},
        )


def _strip_file_wrapper_tag(code: str) -> tuple[str, bool]:
    """Remove ``<file path="...">`` and ``</file>`` wrapper tags.

    LLMs sometimes wrap multi-file output in XML-like tags that
    are not part of the actual file content.
    """
    lines = code.splitlines(keepends=True)
    stripped = False

    # Strip leading <file ...> tag
    if lines and re.match(r'^\s*<file\s+', lines[0]):
        lines = lines[1:]
        stripped = True

    # Strip trailing </file> tag
    if lines and re.match(r'^\s*</file>\s*$', lines[-1]):
        lines = lines[:-1]
        stripped = True

    return "".join(lines) if stripped else code, stripped


def _fix_namespace_conventions(code: str, file_path: str) -> tuple[str, list[str]]:
    """Fix namespace case and style in C# source files.

    1. PascalCase the namespace to match _derive_namespace() output
    2. Convert block-scoped to file-scoped (net8.0+ convention)
    """
    repairs: list[str] = []

    # Find the namespace declaration
    ns_match = re.search(
        r'^(\s*)namespace\s+([\w.]+)\s*([;{])',
        code,
        re.MULTILINE,
    )
    if not ns_match:
        return code, repairs

    indent = ns_match.group(1).replace("\n", "").replace("\r", "")
    actual_ns = ns_match.group(2)
    terminator = ns_match.group(3)

    # Compute expected PascalCase namespace from file path
    try:
        from startd8.languages.csharp import _derive_namespace
        expected_ns = _derive_namespace(file_path)
    except ImportError:
        expected_ns = ""

    # 1. Fix case if mismatch and we have an expected value
    if expected_ns and actual_ns != expected_ns and actual_ns.lower() == expected_ns.lower():
        # Case-only mismatch — safe to fix
        code = code.replace(
            f"namespace {actual_ns}",
            f"namespace {expected_ns}",
            1,
        )
        # Also fix using directives that reference the old namespace
        # e.g., "using cartservice.cartstore;" → "using Cartservice.Cartstore;"
        for old_segment in _namespace_segments(actual_ns):
            new_segment = _namespace_segments(expected_ns)[
                _namespace_segments(actual_ns).index(old_segment)
            ] if old_segment in _namespace_segments(actual_ns) else old_segment
            # Only replace in using directives, not arbitrary code
            code = re.sub(
                rf'(using\s+(?:static\s+)?)({re.escape(actual_ns)})',
                rf'\g<1>{expected_ns}',
                code,
            )
        actual_ns = expected_ns
        repairs.append("namespace_pascalcase_fixed")

    # 2. Convert block-scoped to file-scoped
    if terminator == "{":
        code, converted = _block_to_file_scoped(code, actual_ns, indent)
        if converted:
            repairs.append("namespace_file_scoped_converted")

    return code, repairs


def _block_to_file_scoped(code: str, namespace: str, indent: str) -> tuple[str, bool]:
    """Convert ``namespace X {`` to ``namespace X;`` and remove the closing brace.

    This is only safe when the namespace block is the outermost scope
    (no code outside it except using directives and comments).
    """
    # Replace the opening: "namespace X {" → "namespace X;"
    pattern = re.escape(f"{indent}namespace {namespace}") + r'\s*\{'
    match = re.search(pattern, code)
    if not match:
        return code, False

    # Check that the namespace block wraps everything after usings
    # (safe to convert only if it's the outermost block)
    before_ns = code[:match.start()]
    after_ns = code[match.end():]

    # Before namespace should only have usings, comments, blank lines, attributes
    for line in before_ns.splitlines():
        stripped = line.strip()
        if stripped and not (
            stripped.startswith("using ")
            or stripped.startswith("//")
            or stripped.startswith("/*")
            or stripped.startswith("*")
            or stripped.startswith("#")
            or stripped.startswith("[")
            or stripped == ""
        ):
            return code, False  # Code before namespace — not safe to convert

    # Find and remove the matching closing brace (last } in file)
    # Trim one level of indentation from the body
    lines = code.splitlines(keepends=True)
    new_lines: list[str] = []
    ns_line_idx = None
    brace_line_idx = None  # The line with the opening {
    last_closing_brace_idx = None

    # Find namespace line — handles both K&R (same line) and Allman (next line)
    ns_pattern = re.escape(f"{indent}namespace {namespace}")
    for i, line in enumerate(lines):
        if re.match(ns_pattern + r'\s*$', line.rstrip()):
            # Allman style: brace on next line
            ns_line_idx = i
            if i + 1 < len(lines) and lines[i + 1].strip() == "{":
                brace_line_idx = i + 1
        elif re.match(ns_pattern + r'\s*\{', line.rstrip()):
            # K&R style: brace on same line
            ns_line_idx = i
            brace_line_idx = i
        if line.strip() == "}" and ns_line_idx is not None:
            last_closing_brace_idx = i

    if ns_line_idx is None or brace_line_idx is None or last_closing_brace_idx is None:
        return code, False

    for i, line in enumerate(lines):
        if i == ns_line_idx:
            # Replace block-scoped with file-scoped
            new_lines.append(f"{indent}namespace {namespace};\n")
        elif i == brace_line_idx and brace_line_idx != ns_line_idx:
            # Skip the separate opening brace line (Allman style)
            continue
        elif i == last_closing_brace_idx:
            # Skip the closing brace
            continue
        elif (brace_line_idx or ns_line_idx) < i < last_closing_brace_idx:
            # Dedent body by one level (4 spaces or 1 tab)
            if line.startswith("    "):
                new_lines.append(line[4:])
            elif line.startswith("\t"):
                new_lines.append(line[1:])
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    return "".join(new_lines), True


def _fix_missing_nullable(code: str) -> tuple[str, bool]:
    """Add ``<Nullable>enable</Nullable>`` to .csproj if missing."""
    if "<Nullable>" in code:
        return code, False  # Already present

    # Insert after <TargetFramework>
    match = re.search(r'([ \t]*<TargetFramework>[^<]+</TargetFramework>)', code)
    if not match:
        return code, False

    indent = re.match(r'(\s*)', match.group(1)).group(1)
    insertion = f"\n{indent}<Nullable>enable</Nullable>"
    code = code[:match.end()] + insertion + code[match.end():]
    return code, True


def _namespace_segments(ns: str) -> list[str]:
    """Split namespace into segments."""
    return ns.split(".")
