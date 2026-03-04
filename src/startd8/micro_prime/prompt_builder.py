"""Skeleton-First Prompt Construction (REQ-MP-200–205).

Builds focused prompts for local model body generation. The prompt includes
skeleton context (surrounding methods, class docstring, imports) and instructs
the model to output ONLY the function body.
"""

from __future__ import annotations

from typing import Optional

from startd8.forward_manifest import (
    ContractConfidence,
    ForwardElementSpec,
    ForwardFileSpec,
    InterfaceContract,
)
from startd8.logging_config import get_logger
from startd8.utils.code_manifest import ElementKind

logger = get_logger(__name__)


def build_body_prompt(
    element: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    contracts: list[InterfaceContract],
    skeleton: Optional[str] = None,
    few_shot_examples: Optional[list[str]] = None,
    token_budget: int = 1024,
    design_doc_sections: Optional[list[str]] = None,
) -> str:
    """Build a prompt for a local model to generate a single element body.

    Args:
        element: The target element to implement.
        file_spec: File spec containing imports and sibling elements.
        contracts: Binding constraints relevant to this element.
        skeleton: Optional skeleton file content for context.
        few_shot_examples: Optional list of completed sibling code.
        token_budget: Maximum input tokens (REQ-MP-205). Used for truncation.
        design_doc_sections: Optional design doc sections for implementation
            context (REQ-DDS-001). Rendered as ``# Implementation context:``.

    Returns:
        The constructed prompt string.
    """
    # REQ-MP-204: Route constants/variables to dedicated prompt
    if element.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE):
        return _build_constant_prompt(element, file_spec, few_shot_examples)

    prompt = _build_function_prompt(
        element, file_spec, contracts, skeleton, few_shot_examples,
        design_doc_sections=design_doc_sections,
    )
    return _truncate_to_budget(prompt, token_budget)


def _build_function_prompt(
    element: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    contracts: list[InterfaceContract],
    skeleton: Optional[str],
    few_shot_examples: Optional[list[str]],
    design_doc_sections: Optional[list[str]] = None,
) -> str:
    """Build prompt for function/method body generation (REQ-MP-200–203)."""
    stub = _build_element_stub(element)
    est_lines = _estimate_body_lines(element)

    # Render imports for context (REQ-MP-201)
    import_lines = _render_imports(file_spec)

    # Render sibling stubs for class context (REQ-MP-201)
    sibling_stubs = _render_sibling_stubs(element, file_spec)

    # Render binding constraints
    constraint_lines = _render_constraints(contracts)

    # Determine def keyword for format anchor
    def_keyword = "async def" if element.kind in (
        ElementKind.ASYNC_FUNCTION, ElementKind.ASYNC_METHOD,
    ) else "def"

    # ── Build prompt sections ──

    sections: list[str] = []

    # Method context header (REQ-MP-201)
    if element.parent_class:
        sections.append(
            f"# This is a method of class `{element.parent_class}`. "
            "Write it at the top level (no class wrapper)."
        )

    # Core instructions (REQ-MP-202)
    sections.extend([
        "# Task: Implement the function body below.",
        "# Replace `raise NotImplementedError` with a working implementation.",
        f"# The body should be approximately {est_lines} lines.",
        "# STOP after the function ends. Do NOT write additional functions, classes, or tests.",
        "# Output ONLY Python code. No markdown fences, no explanations, no comments before or after.",
        f"# Start directly with `{def_keyword} {element.name}(` on the first line.",
        "",
    ])

    # Available imports (REQ-MP-201)
    if import_lines:
        sections.append("# Available imports (ONLY use these — do NOT invent other APIs):")
        sections.extend(import_lines)
        sections.append("")

    # Implementation context from design doc sections (REQ-DDS-001)
    if design_doc_sections:
        sections.append("# Implementation context:")
        for ds in design_doc_sections:
            sections.append(f"# - {ds}")
        sections.append("")

    # Sibling context (REQ-MP-201)
    if sibling_stubs:
        sections.append("# Other methods in this class (for context, do not redefine):")
        sections.extend(sibling_stubs)
        sections.append("")

    # Constraints
    if constraint_lines:
        sections.append("# Constraints:")
        sections.extend(constraint_lines)
        sections.append("")

    # Few-shot examples (REQ-MP-203)
    if few_shot_examples:
        for i, ex in enumerate(few_shot_examples[:2]):
            label = "Example (completed)" if i == 0 else "Another example"
            sections.append(f"# {label}:")
            sections.append(ex)
            sections.append("")

    # Target element
    sections.append("# Now implement this:")
    sections.append(stub)

    return "\n".join(sections)


def _build_constant_prompt(
    element: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    few_shot_examples: Optional[list[str]],
) -> str:
    """Build prompt for constant/variable generation (REQ-MP-204)."""
    import_lines = _render_imports(file_spec)

    # Type annotation hint
    type_hint = ""
    if element.signature and element.signature.return_annotation:
        type_hint = f": {element.signature.return_annotation}"

    doc_hint = ""
    if element.docstring_hint:
        doc_hint = f"  # {element.docstring_hint}"

    sections = [
        "# Task: Define this module-level variable.",
        "# Output ONLY the assignment statement. 1-3 lines maximum.",
        "# Do NOT write functions, classes, decorators, or explanations.",
        "# Do NOT wrap output in markdown code fences.",
        f"# Start your output directly with `{element.name}`.",
        "",
    ]

    if import_lines:
        sections.append("# Available imports (use only these):")
        sections.extend(import_lines)
        sections.append("")

    if few_shot_examples:
        sections.append("# Example (completed):")
        sections.append(few_shot_examples[0])
        sections.append("")

    sections.append("# Define this:")
    sections.append(f"{element.name}{type_hint} = ...{doc_hint}")

    return "\n".join(sections)


def _build_element_stub(element: ForwardElementSpec) -> str:
    """Render an element as a Python stub at top-level indent."""
    lines: list[str] = []

    # Decorators
    for dec in element.decorators or []:
        lines.append(f"@{dec}")

    if element.kind == ElementKind.CLASS:
        bases = f"({', '.join(element.bases)})" if element.bases else ""
        lines.append(f"class {element.name}{bases}:")
    else:
        # Build signature
        prefix = "async def" if element.kind in (
            ElementKind.ASYNC_FUNCTION, ElementKind.ASYNC_METHOD,
        ) else "def"

        if element.kind == ElementKind.PROPERTY:
            prefix = "def"
            if "property" not in (element.decorators or []):
                lines.append("@property")

        params: list[str] = []
        if element.signature:
            for p in element.signature.params:
                s = p.name
                if p.annotation:
                    s += f": {p.annotation}"
                if p.default:
                    s += f" = {p.default}"
                params.append(s)

        sig = ", ".join(params)
        ret = ""
        if element.signature and element.signature.return_annotation:
            ret = f" -> {element.signature.return_annotation}"
        lines.append(f"{prefix} {element.name}({sig}){ret}:")

    # Docstring
    if element.docstring_hint:
        lines.append(f'    """{element.docstring_hint}"""')

    # Stub body
    lines.append("    raise NotImplementedError")

    return "\n".join(lines)


def _estimate_body_lines(element: ForwardElementSpec) -> str:
    """Heuristic line-count estimate for the length constraint hint."""
    if element.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE):
        return "1-2"
    if element.kind == ElementKind.PROPERTY:
        return "1-3"
    param_count = 0
    if element.signature:
        param_count = len([
            p for p in element.signature.params if p.name not in ("self", "cls")
        ])
    if param_count == 0:
        return "3-8"
    if param_count <= 2:
        return "5-12"
    return "8-15"


def _render_imports(file_spec: ForwardFileSpec) -> list[str]:
    """Render import lines from file spec."""
    lines: list[str] = []
    for imp in file_spec.imports:
        if imp.kind == "from":
            names = ", ".join(imp.names)
            lines.append(f"from {imp.module} import {names}")
        else:
            alias = f" as {imp.alias}" if imp.alias else ""
            lines.append(f"import {imp.module}{alias}")
    return lines


def _render_sibling_stubs(
    element: ForwardElementSpec, file_spec: ForwardFileSpec,
) -> list[str]:
    """Render stubs for sibling methods in the same class."""
    stubs: list[str] = []
    if not element.parent_class:
        return stubs
    for sib in file_spec.elements:
        if sib.parent_class == element.parent_class and sib.name != element.name:
            if sib.signature:
                params = ", ".join(
                    f"{p.name}: {p.annotation}" if p.annotation else p.name
                    for p in sib.signature.params
                )
                ret = f" -> {sib.signature.return_annotation}" if sib.signature.return_annotation else ""
                stubs.append(f"def {sib.name}({params}){ret}: ...")
    return stubs


def _render_constraints(contracts: list[InterfaceContract]) -> list[str]:
    """Render binding constraints for the prompt."""
    lines: list[str] = []
    for c in contracts:
        prefix = "[BINDING]" if c.confidence != ContractConfidence.TENTATIVE else "[ADVISORY]"
        lines.append(f"{prefix} {c.binding_text}")
    return lines


def find_few_shot_examples(
    element: ForwardElementSpec,
    file_path: str,
    completed_elements: list[dict],
    max_examples: int = 2,
) -> list[str]:
    """Find successfully-generated siblings for few-shot injection (REQ-MP-203).

    Priority (REQ-MP-205):
        1. Same class (matching parent_class)
        2. Same file (matching file_path)
        3. Same kind (matching ElementKind, across files)

    Args:
        element: Target element.
        file_path: Path of the target file.
        completed_elements: List of dicts with keys: element, file_path,
            code, syntax_valid. The element sub-dict may include ``kind``.
        max_examples: Maximum number of examples.

    Returns:
        List of code strings to use as few-shot examples.
    """
    examples: list[str] = []

    # Tier 1: Same class
    if element.parent_class:
        for ce in completed_elements:
            if len(examples) >= max_examples:
                break
            if (
                ce.get("syntax_valid")
                and ce.get("code")
                and ce.get("element", {}).get("parent_class") == element.parent_class
                and ce.get("element", {}).get("name") != element.name
            ):
                examples.append(ce["code"].strip())

    # Tier 2: Same file
    if len(examples) < max_examples:
        for ce in completed_elements:
            if len(examples) >= max_examples:
                break
            if (
                ce.get("syntax_valid")
                and ce.get("code")
                and ce.get("file_path") == file_path
                and ce.get("element", {}).get("name") != element.name
                and ce["code"].strip() not in examples
            ):
                examples.append(ce["code"].strip())

    # Tier 3: Same kind (across files)
    if len(examples) < max_examples:
        for ce in completed_elements:
            if len(examples) >= max_examples:
                break
            if (
                ce.get("syntax_valid")
                and ce.get("code")
                and ce.get("element", {}).get("kind") == element.kind
                and ce.get("element", {}).get("name") != element.name
                and ce["code"].strip() not in examples
            ):
                examples.append(ce["code"].strip())

    return examples


# ── Token budget enforcement (REQ-MP-205) ──


# Rough chars-per-token estimate for code prompts.
_CHARS_PER_TOKEN = 4


def _truncate_to_budget(prompt: str, token_budget: int) -> str:
    """Trim prompt sections to stay within *token_budget*.

    Removes sections in priority order (least valuable first):
    few-shot examples → sibling stubs → design-doc context.
    The core instructions and target element are never trimmed.
    """
    est_tokens = len(prompt) // _CHARS_PER_TOKEN
    if est_tokens <= token_budget:
        return prompt

    lines = prompt.splitlines()

    # Identify removable sections by their comment headers.
    # Each entry: (header, priority) — higher priority removed first.
    _REMOVABLE = [
        ("# Example (completed):", 1),
        ("# Another example:", 1),
        ("# Other methods in this class", 2),
        ("# Implementation context:", 3),
    ]

    for header, _ in _REMOVABLE:
        est_tokens = len(prompt) // _CHARS_PER_TOKEN
        if est_tokens <= token_budget:
            break

        # Remove from header line to next blank line (section boundary).
        new_lines: list[str] = []
        skipping = False
        for line in lines:
            if line.startswith(header):
                skipping = True
                continue
            if skipping and line.strip() == "":
                skipping = False
                continue
            if not skipping:
                new_lines.append(line)

        lines = new_lines
        prompt = "\n".join(lines)

    if len(prompt) // _CHARS_PER_TOKEN > token_budget:
        logger.debug(
            "Prompt still exceeds token budget after truncation "
            "(%d est. tokens > %d budget)",
            len(prompt) // _CHARS_PER_TOKEN,
            token_budget,
        )

    return prompt
