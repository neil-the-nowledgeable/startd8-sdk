"""
element_id — Deterministic element ID generation for the startd8 package.

ID Format
---------
Every ID has the form::

    {readable_prefix}-{hash12}

where ``readable_prefix`` encodes the kind and human-readable scope,
and ``hash12`` is the first 12 hex characters of the SHA-256 digest of the
fully-qualified composite key (ensuring collision resistance).

Readable Prefix Structure
~~~~~~~~~~~~~~~~~~~~~~~~~
    {kind}/{file_dot_path}.{parent}.{name}{@line}

Components that are absent are simply omitted (no placeholder dot is emitted).

Examples::

    function/my_func-3f9a1c004b2e
    function/src.startd8.engine.my_func-3f9a1c004b2e
    method/src.startd8.engine.myclass.do_thing@0042-3f9a1c004b2e

Normalization Rules
~~~~~~~~~~~~~~~~~~~
- ``kind``, ``name``, ``parent_class``: lowercased, whitespace stripped,
  non-``[a-z0-9_]`` characters replaced with ``_``.
- ``file_path``: os.path.normpath → forward slashes → strip leading ``./``
  or ``/`` → strip ``.py`` suffix → lowercase.
- ``line``: formatted as 4-digit zero-padded integer (e.g., ``0042``).

Composite Key (input to hash)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    "{kind}::{file}::{parent}::{name}::{line}"

Missing optional fields contribute an empty string segment so that the
presence/absence of each field affects the hash independently.
"""

from __future__ import annotations

import hashlib
import os
import re

__all__ = ["make_element_id", "parse_element_id"]

# ---------------------------------------------------------------------------
# Module-level compiled regexes (compiled once at import time)
# ---------------------------------------------------------------------------

# Matches any character NOT in [a-z0-9_] — used for token normalization.
_UNSAFE_CHARS_RE: re.Pattern[str] = re.compile(r"[^a-z0-9_]")

# Parses a well-formed element ID: {kind}/{scope}-{12-hex-hash}
_ID_PATTERN: re.Pattern[str] = re.compile(r"^([a-z0-9_]+/.+)-([0-9a-f]{12})$")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalize_token(value: str) -> str:
    """
    Normalize a token (kind, name, or parent_class) for use in an element ID.

    Steps applied in order:

    1. Strip leading and trailing whitespace.
    2. Convert to lowercase.
    3. Replace any character not matching ``[a-z0-9_]`` with a single
       underscore.

    Parameters
    ----------
    value : str
        The raw token to normalize.

    Returns
    -------
    str
        The normalized token.  May be an empty string if *value* consisted
        entirely of whitespace.
    """
    stripped = value.strip().lower()
    return _UNSAFE_CHARS_RE.sub("_", stripped)


def _normalize_file_path(file_path: str) -> str:
    """
    Normalize a file path for stable inclusion in an element ID.

    Steps applied in order:

    1. ``os.path.normpath`` — resolves ``.``, ``..``, duplicate separators.
    2. Replace OS path separators (backslashes on Windows) with forward
       slashes so IDs are platform-independent.
    3. Strip a leading ``./`` prefix that ``normpath`` may leave on
       relative paths.
    4. Strip a leading ``/`` to convert absolute paths to relative form.
    5. Strip a trailing ``.py`` suffix (case-insensitive).
    6. Lowercase the entire result.

    Parameters
    ----------
    file_path : str
        The raw file path to normalize.

    Returns
    -------
    str
        The normalized path.  May be an empty string if the path normalizes
        to nothing meaningful.
    """
    normalized = os.path.normpath(file_path)
    # Guarantee forward slashes regardless of the host OS.
    normalized = normalized.replace("\\", "/")
    # normpath on a './foo' input yields './foo' on some platforms.
    if normalized.startswith("./"):
        normalized = normalized[2:]
    # Make absolute paths relative so IDs are portable across machines.
    normalized = normalized.lstrip("/")
    # Drop the .py extension — we care about the module, not the file type.
    if normalized.lower().endswith(".py"):
        normalized = normalized[:-3]
    return normalized.lower()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def make_element_id(
    kind: str,
    name: str,
    file_path: str | None = None,
    parent_class: str | None = None,
    line: int | None = None,
) -> str:
    """
    Generate a deterministic, stable element ID.

    The returned ID encodes a kind, name, and optional scoping dimensions
    (file path, parent class, line number) in a human-readable prefix, with
    a 12-character SHA-256 hash suffix for collision resistance.  The ID is
    fully deterministic: identical inputs always produce identical output.

    Parameters
    ----------
    kind : str
        Element kind label (e.g., ``'function'``, ``'class'``, ``'method'``,
        ``'variable'``).  Normalized before use.
    name : str
        Element name as it appears in source (e.g., the function or class
        name).  Normalized before use.
    file_path : str | None, optional
        Path to the source file containing the element.  Normalized before
        use.  When ``None`` the file dimension is omitted from the readable
        prefix but still contributes an empty string segment to the composite
        key used for hashing.
    parent_class : str | None, optional
        Name of the enclosing class for methods or nested elements.
        Normalized before use.  When ``None``, omitted from the readable
        prefix.
    line : int | None, optional
        Source line number.  Provides disambiguation for overloaded or
        duplicate names within the same scope.  Must be ``>= 0`` when
        provided.  Formatted as a 4-digit zero-padded integer (e.g.,
        ``0042``).

    Returns
    -------
    str
        Deterministic ID of the form ``{readable_prefix}-{hash12}``.

    Raises
    ------
    ValueError
        If *line* is provided and is negative.

    Examples
    --------
    >>> make_element_id("function", "my_func")  # doctest: +SKIP
    'function/my_func-3f9a1c004b2e'

    >>> make_element_id(
    ...     "method", "do_thing",
    ...     file_path="src/engine.py",
    ...     parent_class="MyClass",
    ...     line=42,
    ... )  # doctest: +SKIP
    'method/src.engine.myclass.do_thing@0042-a1b2c3d4e5f6'
    """
    if line is not None and line < 0:
        raise ValueError(
            f"line must be a non-negative integer, got {line!r}"
        )

    # ------------------------------------------------------------------
    # Normalize all inputs
    # ------------------------------------------------------------------
    kind_norm   = _normalize_token(kind)
    name_norm   = _normalize_token(name)
    file_norm   = _normalize_file_path(file_path) if file_path is not None else ""
    parent_norm = _normalize_token(parent_class) if parent_class is not None else ""
    line_str    = f"{line:04d}" if line is not None else ""

    # ------------------------------------------------------------------
    # Build composite key → SHA-256 → first 12 hex chars
    #
    # All five segments are always present (absent optionals → "").
    # The "::" separator is not a valid output of any normalization step,
    # so segments can never bleed into one another.
    # ------------------------------------------------------------------
    composite_key = "::".join([
        kind_norm,
        file_norm,
        parent_norm,
        name_norm,
        line_str,
    ])
    hash12 = hashlib.sha256(composite_key.encode("utf-8")).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Build human-readable prefix
    #
    # Format: {kind}/{dot_joined_scope_parts}
    #
    # Scope parts (in order, present only when non-empty):
    #   1. file_norm  — path separators converted to dots
    #   2. parent_norm
    #   3. name_norm[@line_str]  — always appended
    # ------------------------------------------------------------------
    scope_parts: list[str] = []

    if file_norm:
        scope_parts.append(file_norm.replace("/", "."))

    if parent_norm:
        scope_parts.append(parent_norm)

    name_with_line = name_norm + (f"@{line_str}" if line_str else "")
    scope_parts.append(name_with_line)

    readable_prefix = kind_norm + "/" + ".".join(scope_parts)

    return f"{readable_prefix}-{hash12}"


def parse_element_id(element_id: str) -> dict[str, str]:
    """
    Decompose an element ID produced by :func:`make_element_id` into its
    labeled structural parts.

    This is a best-effort *structural* parse of the ID string.  It does
    **not** reverse-engineer the original ``file_path``, ``parent_class``,
    or ``line`` arguments — that information is encoded in the readable
    prefix but is not fully recoverable without the original inputs.

    Parameters
    ----------
    element_id : str
        An ID string previously produced by :func:`make_element_id`.

    Returns
    -------
    dict[str, str]
        A dictionary with the following keys:

        ``'kind'``
            The element kind (the segment before the first ``/``).
        ``'readable_prefix'``
            The full human-readable prefix (everything before the trailing
            ``-{hash}`` suffix).
        ``'hash'``
            The 12-character lowercase hexadecimal hash suffix.

    Raises
    ------
    ValueError
        If *element_id* does not match the expected structural format
        ``{kind}/{scope}-{12-hex-hash}``.

    Examples
    --------
    >>> parsed = parse_element_id("function/my_func-3f9a1c004b2e")
    >>> parsed['kind']
    'function'
    >>> parsed['hash']
    '3f9a1c004b2e'
    >>> len(parsed['hash'])
    12
    """
    match = _ID_PATTERN.match(element_id)
    if not match:
        raise ValueError(
            f"element_id {element_id!r} does not match the expected format "
            f"'{{kind}}/{{scope}}-{{12-hex-chars}}'. "
            f"Ensure the ID was produced by make_element_id()."
        )
    readable_prefix = match.group(1)
    hash_suffix     = match.group(2)
    kind            = readable_prefix.split("/", 1)[0]

    return {
        "kind":            kind,
        "readable_prefix": readable_prefix,
        "hash":            hash_suffix,
    }