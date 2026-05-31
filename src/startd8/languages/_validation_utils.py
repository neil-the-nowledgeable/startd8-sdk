"""Shared validation utilities for language profiles.

Centralizes contamination fingerprints, type mapping, and skeleton
config so that language-specific validators and assemblers can share
a single source of truth.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Contamination fingerprints
# ---------------------------------------------------------------------------

# Core Python fingerprints — if these appear in non-Python files, it's
# cross-language contamination.  Used as the base set for all languages.
PYTHON_FINGERPRINTS: tuple[str, ...] = (
    "def ", "import os", "from __future__", "print(", "self.",
    "#!/usr/bin/env python", "#!/usr/bin/python",
)

# Per-language fingerprint overrides.  Each tuple is the set of patterns
# to check for that specific target language.  Patterns that would
# false-positive on legitimate code in the target language are removed.
#
# Example: "print(" is removed from Go (matches builtin print() and
# fmt.Fprint), and "class " is removed from Node.js (JS has classes).
GO_CONTAMINATION_FINGERPRINTS: tuple[str, ...] = (
    "def ", "import os", "from __future__", "self.",
    "#!/usr/bin/env python", "#!/usr/bin/python",
    "class ",       # Python class definition (safe — Go has no class keyword)
    "raise ",       # Python exception raising
    "if __name__",  # Python main guard
)

JAVA_CONTAMINATION_FINGERPRINTS: tuple[str, ...] = (
    "def ", "import os", "from __future__", "self.",
    "#!/usr/bin/env python", "#!/usr/bin/python",
    "raise ",       # Python exception raising (Java uses "throw")
    "if __name__",  # Python main guard
    # Note: "print(" safe in Java — Java uses System.out.println()
    # Note: "class " NOT included — Java has classes
)

NODEJS_CONTAMINATION_FINGERPRINTS: tuple[str, ...] = (
    "def ", "import os", "from __future__", "self.",
    "#!/usr/bin/env python", "#!/usr/bin/python",
    "raise ",       # Python exception raising (JS uses "throw")
    "if __name__",  # Python main guard
    # Note: "print(" safe in Node — console.log() doesn't match, but
    #       print() is not a JS function so it IS a signal.  However,
    #       it false-positives on formatted template strings.
    # Note: "class " NOT included — JS has classes
)

# Registry: language_id → fingerprint tuple
CONTAMINATION_FINGERPRINTS: dict[str, tuple[str, ...]] = {
    "go": GO_CONTAMINATION_FINGERPRINTS,
    "java": JAVA_CONTAMINATION_FINGERPRINTS,
    "csharp": JAVA_CONTAMINATION_FINGERPRINTS,  # same set — C# has classes too
    "nodejs": NODEJS_CONTAMINATION_FINGERPRINTS,
}


def get_contamination_fingerprints(language_id: str) -> tuple[str, ...]:
    """Return the fingerprint tuple for a given language.

    Falls back to the base ``PYTHON_FINGERPRINTS`` for unknown languages.
    """
    return CONTAMINATION_FINGERPRINTS.get(language_id, PYTHON_FINGERPRINTS)


import re as _re

# Line-anchored matchers for the ambiguous fingerprints. A bare ``"self." in
# content`` substring scan false-flags valid non-Python code — ``window.self``
# / ``self.postMessage`` in JS, ``obj.self`` field access, an identifier named
# ``self``/``def``, or the literal text inside a string/comment. Anchoring to
# statement start eliminates those false positives (mirrors the precise logic in
# ``nodejs_semantic_checks._check_python_contamination``).
_SELF_DOT_RE = _re.compile(r"^\s*self\.\w")
_PY_DEF_RE = _re.compile(r"^\s*def\s+\w+\s*\(")
_PY_SHEBANGS = ("#!/usr/bin/env python", "#!/usr/bin/python")
# Comment/blank prefixes for the brace-delimited target languages (Go/Java/C#).
# ``#`` is included so C# preprocessor directives (``#region``/``#nullable``)
# and Python comments are skipped — skipping only risks a false *negative*.
_COMMENT_PREFIXES = ("//", "/*", "*", "#")


def detect_python_contamination(
    content: str, language_id: str,
) -> Optional[str]:
    """Return the offending Python fingerprint if *content* (a file in
    *language_id*, a NON-Python brace language) contains a strong, statement-
    anchored Python signal; else ``None``.

    Line-anchored and comment-aware — the correct replacement for the naive
    ``if fp in content`` substring scan that produced false positives on valid
    Go/Java/C#/Node code (audit finding F1).
    """
    fingerprints = get_contamination_fingerprints(language_id)
    for line in content.splitlines():
        stripped = line.strip()
        # Shebang check precedes the comment skip (a Python shebang starts ``#``).
        for sb in _PY_SHEBANGS:
            if stripped.startswith(sb):
                return sb
        if not stripped or stripped.startswith(_COMMENT_PREFIXES):
            continue
        if "self." in fingerprints and _SELF_DOT_RE.match(line):
            return "self."
        if "def " in fingerprints and _PY_DEF_RE.match(line):
            return "def "
        for fp in fingerprints:
            # ``self.``/``def `` handled above with anchored matchers; the rest
            # are matched at statement start (not anywhere in the line).
            if fp in ("self.", "def ") or fp in _PY_SHEBANGS:
                continue
            if stripped.startswith(fp):
                return fp
    return None


# ---------------------------------------------------------------------------
# Skeleton configuration (language-neutral DFA support)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SkeletonConfig:
    """Language-specific rendering rules for the polyglot file assembler.

    Captures the small set of differences between brace-delimited
    languages (Java, C#, Go, Node.js/TS) so that a single assembler
    can produce correct skeletons for all of them.
    """
    language_id: str
    stub_body: str
    sentinel: str = "// [STARTD8-SKELETON]"

    # Namespace / package
    namespace_template: str = ""       # e.g. "package {ns};" or "namespace {ns};"
    import_template: str = ""          # e.g. "import {mod};" or "using {mod};"
    stdlib_prefixes: Sequence[str] = ()  # for 2-tier import grouping

    # Type mapping (Python type str → target language type str)
    type_map: Dict[str, str] = field(default_factory=dict)
    default_type: str = "object"       # fallback for unknown types
    nullable_suffix: str = ""          # e.g. "?" for C#
    list_template: str = "List<{inner}>"
    dict_template: str = "Dictionary<{key}, {value}>"

    # Rendering
    has_properties: bool = False        # C# has { get; set; }
    indent: str = "    "
    comment_prefix: str = "//"


# Pre-built configs for each language
JAVA_SKELETON_CONFIG = SkeletonConfig(
    language_id="java",
    stub_body='throw new UnsupportedOperationException("TODO");',
    namespace_template="package {ns};",
    import_template="import {mod};",
    stdlib_prefixes=("java.", "javax."),
    type_map={
        "str": "String", "int": "int", "float": "double",
        "bool": "boolean", "None": "void", "bytes": "byte[]",
        "list": "List<Object>", "dict": "Map<String, Object>",
        "set": "Set<Object>", "tuple": "Object[]",
        "Any": "Object", "Optional": "Object",
    },
    default_type="Object",
    list_template="List<{inner}>",
    dict_template="Map<{key}, {value}>",
)

CSHARP_SKELETON_CONFIG = SkeletonConfig(
    language_id="csharp",
    stub_body="throw new NotImplementedException();",
    namespace_template="namespace {ns};",
    import_template="using {mod};",
    stdlib_prefixes=("System", "Microsoft"),
    type_map={
        "str": "string", "int": "int", "float": "double",
        "bool": "bool", "None": "void", "bytes": "byte[]",
        "list": "List<object>", "dict": "Dictionary<string, object>",
        "set": "HashSet<object>", "tuple": "object[]",
        "Any": "object", "Optional": "object",
    },
    default_type="object",
    nullable_suffix="?",
    has_properties=True,
    list_template="List<{inner}>",
    dict_template="Dictionary<{key}, {value}>",
)

GO_SKELETON_CONFIG = SkeletonConfig(
    language_id="go",
    stub_body='panic("not implemented")',
    namespace_template="package {ns}",
    import_template='"{mod}"',
    type_map={
        "str": "string", "int": "int", "float": "float64",
        "bool": "bool", "None": "", "bytes": "[]byte",
        "list": "[]interface{}", "dict": "map[string]interface{}",
        "Any": "interface{}",
    },
    default_type="interface{}",
    indent="\t",
)

NODEJS_SKELETON_CONFIG = SkeletonConfig(
    language_id="nodejs",
    stub_body='throw new Error("not implemented");',
    namespace_template="",  # JS has no package/namespace
    import_template="",     # handled per-format (CJS vs ESM)
    type_map={
        "str": "string", "int": "number", "float": "number",
        "bool": "boolean", "None": "void", "bytes": "Buffer",
        "list": "Array", "dict": "Object",
        "Any": "any",
    },
    default_type="any",
    indent="  ",  # JS convention: 2-space
)

SKELETON_CONFIGS: dict[str, SkeletonConfig] = {
    "java": JAVA_SKELETON_CONFIG,
    "csharp": CSHARP_SKELETON_CONFIG,
    "go": GO_SKELETON_CONFIG,
    "nodejs": NODEJS_SKELETON_CONFIG,
}


def get_skeleton_config(language_id: str) -> Optional[SkeletonConfig]:
    """Return skeleton config for a language, or None if not registered."""
    return SKELETON_CONFIGS.get(language_id)


def convert_python_type(type_str: str, config: SkeletonConfig) -> str:
    """Convert a Python type annotation to the target language type.

    Handles ``Optional[X]``, ``List[X]``, ``Dict[K, V]`` recursively.
    """
    if not type_str:
        return config.default_type

    # Optional[X] → nullable
    if type_str.startswith("Optional["):
        inner = type_str[len("Optional["):-1]
        inner_conv = convert_python_type(inner, config)
        if config.nullable_suffix:
            return f"{inner_conv}{config.nullable_suffix}"
        return inner_conv

    # List[X]
    if type_str.startswith(("List[", "list[")):
        inner = type_str[type_str.index("[") + 1:-1]
        inner_conv = convert_python_type(inner, config)
        return config.list_template.format(inner=inner_conv)

    # Dict[K, V]
    if type_str.startswith(("Dict[", "dict[")):
        inner = type_str[type_str.index("[") + 1:-1]
        parts = inner.split(",", 1)
        if len(parts) == 2:
            k = convert_python_type(parts[0].strip(), config)
            v = convert_python_type(parts[1].strip(), config)
            return config.dict_template.format(key=k, value=v)

    return config.type_map.get(type_str, type_str)


def check_balanced_braces(code: str) -> tuple[bool, str]:
    """Check that braces are balanced in source code.

    Used by Java and C# text-based validators.

    Returns:
        ``(True, '')`` if balanced, ``(False, error_message)`` otherwise.
    """
    depth = 0
    for ch in code:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return False, "unbalanced braces (extra closing brace)"
    if depth != 0:
        return False, f"unbalanced braces (depth={depth})"
    return True, ""
