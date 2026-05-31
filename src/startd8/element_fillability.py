"""Positive fillability + empty-stem-artifact predicates — RUN-007 FR-0/FR-1/FR-5.

Shared by the skeleton-emission gate (`prime_adapter._generate_skeletons`, Step 2),
the complexity classifier (Step 5), the escalation post-check (Step 4), and the
disk validator (Step 6). Kept dependency-light (only ``ElementKind`` + stdlib) and
placed at the package top level — *not* under ``micro_prime/`` — so the disk
validator can import it without a ``forward_manifest_validator`` ⇄ ``micro_prime``
import cycle.

Background: the run-007 partial delivery shipped ``export class value-model {}``
stubs because ``seeds/element_deriver`` T0 unconditionally synthesises a
stem-named ``CLASS`` element (no members) when a feature declares no contracts.
The old ``kind != CLASS`` test treated empty ``STRUCT``/``INTERFACE``/``ENUM``/
``TYPE_ALIAS`` as implementable; FR-0 replaces it with a *positive* fillability
contract. See ``docs/design/RUN_007_REMEDIATION_REQUIREMENTS.md`` (FR-0).
"""
from __future__ import annotations

import re
from typing import Any, Iterable, List, Optional

from startd8.utils.code_manifest import ElementKind

__all__ = [
    "spec_fillable_elements",
    "is_fillable_spec",
    "is_empty_fillable_spec",
    "is_empty_stem_type_artifact",
]

# Kinds that carry behaviour or data on their own → always fillable.
_DIRECTLY_FILLABLE: frozenset = frozenset({
    ElementKind.FUNCTION, ElementKind.ASYNC_FUNCTION,
    ElementKind.METHOD, ElementKind.ASYNC_METHOD,
    ElementKind.PROPERTY, ElementKind.CONSTANT, ElementKind.VARIABLE,
    ElementKind.FIELD, ElementKind.DEFAULT_EXPORT,
})

# Structural type kinds: fillable ONLY if they carry members (FR-0).
_TYPE_KINDS: frozenset = frozenset({
    ElementKind.CLASS, ElementKind.STRUCT, ElementKind.INTERFACE,
    ElementKind.ENUM, ElementKind.RECORD,
})

# ``TYPE_ALIAS`` (and any unrecognised kind) is never fillable on its own.


def _kind_value(element: Any) -> str:
    """Return the element's kind as its enum *value* string ('class', 'function', …)."""
    k = element.get("kind") if isinstance(element, dict) else getattr(element, "kind", None)
    if k is None:
        return ""
    return k.value if hasattr(k, "value") else str(k)


def _attr(element: Any, name: str) -> Any:
    return element.get(name) if isinstance(element, dict) else getattr(element, name, None)


def _as_kind(value: str) -> Optional[ElementKind]:
    try:
        return ElementKind(value)
    except ValueError:
        return None


def spec_fillable_elements(elements: Iterable[Any]) -> List[Any]:
    """Return the subset of *elements* that are fillable (FR-0).

    A type element (CLASS/STRUCT/INTERFACE/ENUM/RECORD) is fillable only when a
    sibling element declares it as ``parent_class`` (i.e. it carries members);
    members are linked by ``parent_class`` in this model, not an inline list.
    """
    elements = list(elements)
    types_with_members = {
        _attr(e, "parent_class") for e in elements if _attr(e, "parent_class")
    }
    out: List[Any] = []
    for e in elements:
        kind = _as_kind(_kind_value(e))
        if kind is None:
            continue
        if kind in _DIRECTLY_FILLABLE:
            out.append(e)
        elif kind in _TYPE_KINDS and _attr(e, "name") in types_with_members:
            out.append(e)
    return out


def is_fillable_spec(elements: Iterable[Any]) -> bool:
    """True if the spec has at least one fillable element (FR-0)."""
    return len(spec_fillable_elements(elements)) > 0


def is_empty_fillable_spec(elements: Iterable[Any]) -> bool:
    """True if the spec has ZERO fillable elements — the empty-spec trigger (FR-1).

    The run-007 ``value-model.ts`` spec (a lone member-less ``CLASS``) is empty;
    a spec with any function/method/field/constant, a type-with-members, or a
    framework ``DEFAULT_EXPORT`` is not.
    """
    return not is_fillable_spec(elements)


# ---------------------------------------------------------------------------
# Empty-stem-type artifact detector (FR-5 / FR-2 shared predicate)
# ---------------------------------------------------------------------------
# Detects the *generated content* shape "a single empty top-level type whose
# name == the file stem, and nothing else" — the run-007 stub on disk. Used by
# the escalation post-check (Step 4) and the disk validator (Step 6). Step 6
# extends the false-positive exemption matrix (.d.ts / barrel / marker / enum /
# config). This module provides the core detector + a conservative baseline.

# Brace-language: `[export] [default] [public] [abstract] class|struct|interface|
# enum|record Name [extends/implements …] { }`  (empty body).
_BRACE_EMPTY_TYPE_RE = re.compile(
    r"(?:export\s+)?(?:default\s+)?"
    r"(?:public\s+|private\s+|internal\s+|protected\s+)?(?:abstract\s+)?"
    # Allow a hyphen in the captured name so the malformed run-007 stub
    # `class value-model {}` (an invalid JS identifier) is still detected.
    r"(?:class|struct|interface|enum|record)\s+([A-Za-z_$][\w$-]*)"
    r"[^{};]*\{\s*\}",
)
# Go: `type Name struct|interface { }` (empty body).
_GO_EMPTY_TYPE_RE = re.compile(
    r"type\s+([A-Za-z_]\w*)\s+(?:struct|interface)\s*\{\s*\}",
)
# Lines that are legal boilerplate around a stub (don't disqualify it).
_BOILERPLATE_LINE_RE = re.compile(
    r"^\s*(?:"
    r"import\b|export\s+(?:type\s+)?\{|export\s+\*|from\b|const\s+\w+\s*=\s*require\(|"
    r"'use strict'|\"use strict\"|package\s+\w+|module\.exports|using\s+|namespace\s+|"
    r"@?[\w./'\"-]+;?"  # bare directive-ish lines
    r")",
)


def _strip_code_comments(content: str) -> str:
    """Remove // line, /* */ block, and # line comments (string-naive but
    adequate for the empty-stub shape, which has no string literals)."""
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    content = re.sub(r"//[^\n]*", "", content)
    content = re.sub(r"(?m)^\s*#[^\n]*", "", content)
    return content


def _normalize_stem(name: str) -> str:
    """Lowercase + strip non-alphanumerics, so `value-model`, `ValueModel`, and
    `value_model` all compare equal (assemblers transform the stem differently:
    Node keeps the raw stem, Go PascalCases it)."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def is_empty_stem_type_artifact(
    file_path: str, content: str, language: Optional[str] = None,
) -> bool:
    """True if *content* is a single empty stem-named type and nothing else.

    This is the run-007 stub shape (``export class value-model {}``). The match
    requires: (1) exactly one empty type declaration, (2) its name matches the
    file stem (case/separator-insensitive), and (3) no other meaningful
    top-level code remains after removing comments, the matched type, and
    import/boilerplate lines.

    NOTE (Step 6 will extend): the false-positive exemption matrix
    (``.d.ts`` ambient, barrel ``export *``, marker interface, empty enum,
    config-object module) is layered on top of this core detector.
    """
    if not content or not content.strip():
        return False

    from pathlib import PurePosixPath
    stem = PurePosixPath(file_path).stem
    norm_stem = _normalize_stem(stem)

    stripped = _strip_code_comments(content)

    matches = list(_BRACE_EMPTY_TYPE_RE.finditer(stripped))
    matches += list(_GO_EMPTY_TYPE_RE.finditer(stripped))
    if len(matches) != 1:
        return False

    m = matches[0]
    if _normalize_stem(m.group(1)) != norm_stem:
        return False

    # Whatever remains after removing the matched empty type must be only
    # imports / boilerplate / blank lines — no functions, no other declarations.
    remainder = (stripped[: m.start()] + stripped[m.end():])
    for line in remainder.splitlines():
        s = line.strip()
        if not s:
            continue
        if not _BOILERPLATE_LINE_RE.match(s):
            return False
    return True
