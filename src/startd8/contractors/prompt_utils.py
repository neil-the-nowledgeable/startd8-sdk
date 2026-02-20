"""Shared prompt utilities used by both artisan and prime contractor routes."""

from __future__ import annotations

_BINDING_PREFIX = "[BINDING] "
_STRUCTURAL_PREFIX = "[STRUCTURAL] "
_ADVISORY_PREFIX = "[ADVISORY] "


def format_constraints(constraints: list[str]) -> str:
    """Group constraints by ``[BINDING]``/``[STRUCTURAL]``/``[ADVISORY]`` prefix.

    Tagged constraints are stripped of their prefix and grouped under markdown
    ``###`` headers.  Untagged constraints are rendered as a flat bullet list
    after the tagged groups.

    Args:
        constraints: Constraint strings, optionally prefixed with a priority
            tag (e.g. ``"[BINDING] Must use X"``).

    Returns:
        Markdown string with grouped sections, or ``""`` if *constraints*
        is empty.  Example output::

            ### Binding (must not violate)
            - Must use X
            ### Advisory (prefer but not blocking)
            - Prefer stdlib
    """
    if not constraints:
        return ""

    groups: dict[str, list[str]] = {
        "binding": [],
        "structural": [],
        "advisory": [],
        "other": [],
    }
    for c in constraints:
        if c.startswith(_BINDING_PREFIX):
            groups["binding"].append(c.removeprefix(_BINDING_PREFIX))
        elif c.startswith(_STRUCTURAL_PREFIX):
            groups["structural"].append(c.removeprefix(_STRUCTURAL_PREFIX))
        elif c.startswith(_ADVISORY_PREFIX):
            groups["advisory"].append(c.removeprefix(_ADVISORY_PREFIX))
        else:
            groups["other"].append(c)

    parts: list[str] = []
    if groups["binding"]:
        parts.append("### Binding (must not violate)")
        parts.extend(f"- {c}" for c in groups["binding"])
    if groups["structural"]:
        parts.append("### Structural (code organization)")
        parts.extend(f"- {c}" for c in groups["structural"])
    if groups["advisory"]:
        parts.append("### Advisory (prefer but not blocking)")
        parts.extend(f"- {c}" for c in groups["advisory"])
    if groups["other"]:
        parts.extend(f"- {c}" for c in groups["other"])
    return "\n".join(parts)


def find_missing_parameters(
    text: str,
    resolved_parameters: list[dict],
) -> list[dict]:
    """Return resolved parameters whose ``key_value`` is not found in *text*.

    Args:
        text: The document text to search (e.g. a design document).
        resolved_parameters: List of parameter dicts, each expected to
            contain a ``"key_value"`` key.

    Returns:
        Subset of *resolved_parameters* whose ``key_value`` does not appear
        as a substring of *text*.  Empty list if all are present.
    """
    missing = []
    for param in resolved_parameters:
        key_value = param.get("key_value", "")
        if key_value and key_value not in text:
            missing.append(param)
    return missing
