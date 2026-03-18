"""C# body splicing — splice generated method bodies into skeleton files.

Uses tree-sitter-c-sharp for precise byte-offset splicing — no line
counting, no brace-matching heuristics.  The most precise splicer of
any language in the pipeline.

Architecture:
1. Parse skeleton with tree-sitter → locate stub methods by name
2. For each stub, extract ``body.start_byte`` / ``body.end_byte``
3. Parse generated code → extract the corresponding method body
4. Replace bytes in the skeleton buffer
5. Re-parse result to validate syntax
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from startd8.logging_config import get_logger

logger = get_logger(__name__)

# Stub patterns for C# skeleton files
CSHARP_STUB_PATTERNS = [
    re.compile(r'throw\s+new\s+NotImplementedException\s*\('),
    re.compile(r'throw\s+new\s+NotSupportedException\s*\('),
    re.compile(r'^\s*//\s*TODO\b', re.MULTILINE),
]


@dataclass
class CSharpSpliceResult:
    """Result of a C# body splice operation."""

    code: Optional[str] = None
    methods_spliced: int = 0
    methods_skipped: int = 0
    warnings: List[str] = field(default_factory=list)
    has_syntax_error: bool = False


def _is_stub_body(body_text: str) -> bool:
    """Check if a method body is a stub (not yet implemented)."""
    stripped = body_text.strip().strip("{}")
    if not stripped.strip():
        return True
    for pattern in CSHARP_STUB_PATTERNS:
        if pattern.search(stripped):
            return True
    return False


def _extract_method_bodies_ts(source: str) -> Dict[str, tuple[int, int, str]]:
    """Extract method/constructor bodies from C# source using tree-sitter.

    Returns dict mapping method_name -> (body_start_byte, body_end_byte, body_text).
    """
    from .csharp_parser import parse_csharp

    result = parse_csharp(source)
    if result.parser_used != "tree_sitter":
        return {}

    source_bytes = source.encode("utf-8")
    bodies: Dict[str, tuple[int, int, str]] = {}

    for elem in result.elements:
        if elem.kind not in ("method", "constructor"):
            continue
        if elem.body_start_byte is None or elem.body_end_byte is None:
            continue
        if elem.name in bodies:
            # Duplicate method name (overload or partial class) — keep first
            logger.debug("Duplicate method '%s' in source — keeping first", elem.name)
            continue
        body_text = source_bytes[elem.body_start_byte:elem.body_end_byte].decode(
            "utf-8", errors="replace",
        )
        bodies[elem.name] = (elem.body_start_byte, elem.body_end_byte, body_text)

    return bodies


def splice_csharp_bodies(
    skeleton: str,
    generated_bodies: Dict[str, str],
) -> CSharpSpliceResult:
    """Splice generated method bodies into a C# skeleton file.

    Uses tree-sitter byte offsets for precise body replacement — no
    line counting or brace matching needed.

    Args:
        skeleton: Skeleton file content with stub methods.
        generated_bodies: Dict mapping method names to generated code
            containing the full method (including signature and body).

    Returns:
        CSharpSpliceResult with spliced code and statistics.
    """
    result = CSharpSpliceResult()

    # Parse skeleton to find stub methods
    skeleton_bodies = _extract_method_bodies_ts(skeleton)
    if not skeleton_bodies:
        result.warnings.append("tree-sitter not available or no methods found in skeleton")
        result.code = skeleton
        return result

    # Build replacement plan — collect all replacements sorted by position
    # (reverse order so byte offsets remain valid after each replacement)
    replacements: List[tuple[int, int, str]] = []  # (start, end, new_body)

    for method_name, gen_code in generated_bodies.items():
        if method_name not in skeleton_bodies:
            result.warnings.append(
                f"Method '{method_name}' not found in skeleton"
            )
            result.methods_skipped += 1
            continue

        skel_start, skel_end, skel_body = skeleton_bodies[method_name]

        if not _is_stub_body(skel_body):
            result.warnings.append(
                f"'{method_name}' body is not a stub — skipping"
            )
            result.methods_skipped += 1
            continue

        # Extract new body from generated code
        gen_bodies = _extract_method_bodies_ts(gen_code)
        if method_name not in gen_bodies:
            result.warnings.append(
                f"Could not extract body for '{method_name}' from generated code"
            )
            result.methods_skipped += 1
            continue

        _, _, new_body_text = gen_bodies[method_name]
        replacements.append((skel_start, skel_end, new_body_text))
        result.methods_spliced += 1

    if not replacements:
        result.code = skeleton
        return result

    # Apply replacements in reverse byte order to preserve offsets
    skeleton_bytes = skeleton.encode("utf-8")
    replacements.sort(key=lambda r: r[0], reverse=True)
    for start, end, new_body in replacements:
        new_body_bytes = new_body.encode("utf-8")
        skeleton_bytes = skeleton_bytes[:start] + new_body_bytes + skeleton_bytes[end:]

    result.code = skeleton_bytes.decode("utf-8", errors="replace")

    # Validate result with tree-sitter
    from .csharp_parser import validate_csharp_syntax
    valid, msg = validate_csharp_syntax(result.code)
    result.has_syntax_error = not valid
    if not valid:
        result.warnings.append(f"post-splice syntax error: {msg}")

    return result


def check_using_coverage(
    cs_content: str,
    csproj_content: str,
) -> List[Dict[str, str]]:
    """Cross-check using directives against .csproj PackageReferences (REQ-CS-502).

    Returns a list of advisory issues (missing package references).
    Stdlib namespaces (System.*, Microsoft.*) are not flagged.
    """
    from .csharp_parser import parse_csharp
    import xml.etree.ElementTree as ET

    issues: List[Dict[str, str]] = []

    # Extract usings from C# source
    parse_result = parse_csharp(cs_content)
    usings = parse_result.usings

    # Extract PackageReferences from .csproj
    pkg_names: set[str] = set()
    try:
        root = ET.fromstring(csproj_content)
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "PackageReference":
                inc = elem.get("Include", "")
                if inc:
                    pkg_names.add(inc.lower())
    except ET.ParseError:
        return []  # can't parse csproj — skip

    # Check each using against known stdlib prefixes and package refs
    _STDLIB = ("System", "Microsoft")
    for ns in usings:
        # Skip stdlib
        if any(ns.startswith(prefix) for prefix in _STDLIB):
            continue
        # Skip project-internal namespaces (lowercase first segment heuristic)
        first_segment = ns.split(".")[0]
        if first_segment and first_segment[0].islower():
            continue
        # Check if any package reference matches the using's root namespace.
        # NuGet packages often share a root with their namespaces:
        #   PackageReference "Grpc.AspNetCore" covers using "Grpc.Core"
        #   (shared root "Grpc" / "grpc")
        ns_lower = ns.lower()
        ns_root = ns.split(".")[0].lower()
        if not any(
            pkg == ns_lower
            or pkg == ns_root
            or ns_lower.startswith(pkg + ".")
            or pkg.startswith(ns_root + ".")  # Grpc.AspNetCore starts with Grpc.
            for pkg in pkg_names
        ):
            issues.append({
                "category": "csharp_dependency",
                "severity": "advisory",
                "message": f"using '{ns}' has no matching PackageReference in .csproj",
                "symbol": ns,
            })

    return issues
