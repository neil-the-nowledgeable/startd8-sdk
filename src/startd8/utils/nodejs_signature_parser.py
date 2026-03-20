"""Node.js / TypeScript signature string parser for plan ingestion element extraction.

Parses LLM-extracted ``api_signatures`` strings into ``ForwardElementSpec`` objects
so that MicroPrime can perform element-level code generation for Node.js targets.

Handles the common 80% of JS/TS signature patterns (functions, classes, arrow
functions, interfaces, type aliases). Exotic patterns are skipped with a debug log.

REQ-EE-103
"""

from __future__ import annotations

import re
from typing import Optional

from startd8.forward_manifest import ForwardElementSpec, Visibility
from startd8.logging_config import get_logger
from startd8.utils.code_manifest import ElementKind, Param, Signature

logger = get_logger(__name__)

# --- Skip patterns (export declarations, not element definitions) -----------
_SKIP_RE = re.compile(r"^\s*(module\.exports|exports\.)\b")

# --- Class / interface / type -----------------------------------------------
_CLASS_RE = re.compile(
    r"^(?:export\s+)?(?:default\s+)?(?:abstract\s+)?"
    r"(class|interface|type)\s+"
    r"(\w+)"
    r"(?:\s+extends\s+([\w.]+))?"
)

# --- Function declaration ---------------------------------------------------
_FUNC_RE = re.compile(
    r"^(?:export\s+)?(?:default\s+)?"
    r"(async\s+)?function\s+"
    r"(\w+)"
    r"\s*\(([^)]*)\)"
    r"(?:\s*:\s*(\S+))?"
)

# --- Arrow / function-expression assignment ---------------------------------
_ARROW_RE = re.compile(
    r"^(?:export\s+)?(?:const|let|var)\s+"
    r"(\w+)"
    r"\s*=\s*(async\s+)?"
    r"(?:\([^)]*\)\s*=>|function\s*\()"
)


def _extract_params(raw: str) -> list[Param]:
    """Extract parameter names from a raw parameter string."""
    params: list[Param] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        # Strip TS type annotations: "name: Type" -> "name"
        name = part.split(":")[0].split("=")[0].strip()
        # Strip destructuring / rest operator
        name = name.lstrip(".")  # ...rest -> rest
        if name.startswith("..."):
            name = name[3:]
        if name and name.isidentifier():
            annotation: Optional[str] = None
            if ":" in part:
                annotation = part.split(":", 1)[1].split("=")[0].strip() or None
            params.append(Param(name=name, annotation=annotation))
    return params


def _has_export(sig: str) -> bool:
    return sig.lstrip().startswith("export")


def parse_nodejs_signatures(
    api_signatures: list[str],
    target_file: str,
) -> list[ForwardElementSpec]:
    """Parse Node.js/TypeScript signature strings into ForwardElementSpec objects.

    Args:
        api_signatures: Raw signature strings extracted by the LLM during plan
            ingestion (e.g. ``"export function processPayment(request)"``).
        target_file: The target file path for the generated elements (unused in
            parsing but required by the caller contract).

    Returns:
        List of ``ForwardElementSpec`` objects. Unparseable signatures are
        skipped with a debug log.
    """
    specs: list[ForwardElementSpec] = []

    for sig in api_signatures:
        sig_stripped = sig.strip()
        if not sig_stripped:
            continue

        # Skip module.exports / exports.X declarations
        if _SKIP_RE.match(sig_stripped):
            logger.debug("Skipping export declaration: %s", sig_stripped)
            continue

        visibility = Visibility.PUBLIC if _has_export(sig_stripped) else Visibility.PUBLIC
        exported = _has_export(sig_stripped)

        # --- Class / interface / type ---
        m = _CLASS_RE.match(sig_stripped)
        if m:
            keyword, name, base = m.group(1), m.group(2), m.group(3)
            is_abstract = keyword == "interface" or "abstract" in sig_stripped.split(keyword)[0]
            kind = ElementKind.CLASS
            bases = [base] if base else []
            specs.append(
                ForwardElementSpec(
                    kind=kind,
                    name=name,
                    bases=bases,
                    visibility=Visibility.PUBLIC,
                    is_abstract=is_abstract,
                    decomposition_source="parse-llm",
                )
            )
            continue

        # --- Function declaration ---
        m = _FUNC_RE.match(sig_stripped)
        if m:
            is_async = bool(m.group(1))
            name = m.group(2)
            raw_params = m.group(3)
            return_type = m.group(4)
            params = _extract_params(raw_params)
            specs.append(
                ForwardElementSpec(
                    kind=ElementKind.FUNCTION,
                    name=name,
                    signature=Signature(params=params, return_annotation=return_type),
                    visibility=Visibility.PUBLIC,
                    decomposition_source="parse-llm",
                )
            )
            continue

        # --- Arrow function / function expression assignment ---
        m = _ARROW_RE.match(sig_stripped)
        if m:
            name = m.group(1)
            specs.append(
                ForwardElementSpec(
                    kind=ElementKind.FUNCTION,
                    name=name,
                    signature=Signature(params=[]),
                    visibility=Visibility.PUBLIC,
                    decomposition_source="parse-llm",
                )
            )
            continue

        logger.debug("Skipping unparseable Node.js signature: %s", sig_stripped)

    return specs
