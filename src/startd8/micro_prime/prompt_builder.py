"""Skeleton-First Prompt Construction (REQ-MP-200–205).

Builds focused prompts for local model body generation. The prompt includes
rendered skeleton context and instructs the model to output ONLY the function
body (no ``def`` line, no class wrapper).
"""

from __future__ import annotations

import ast
import textwrap
from typing import Any, Optional

from startd8.forward_manifest import (
    ContractConfidence,
    ForwardElementSpec,
    ForwardFileSpec,
    InterfaceContract,
)
from startd8.logging_config import get_logger
from startd8.utils.code_manifest import ElementKind

logger = get_logger(__name__)


def build_full_function_prompt(
    element: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    contracts: list[InterfaceContract],
    skeleton: Optional[str] = None,
    few_shot_examples: Optional[list[str]] = None,
    token_budget: int = 1024,
    design_doc_sections: Optional[list[str]] = None,
    task_description: Optional[str] = None,
    domain_constraints: Optional[list[str]] = None,
    language_profile: Optional[Any] = None,
) -> str:
    """Build a prompt for a local model to generate a complete function.

    Unlike ``build_body_prompt`` which asks for body-only output, this asks
    the model to output the full function declaration + body.  The caller then
    extracts the body deterministically via AST (Python) or uses the output
    directly (non-Python, REQ-MPL-102).
    """
    if element.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE):
        return _build_constant_prompt(element, file_spec, few_shot_examples)

    prompt = _build_full_function_prompt_inner(
        element, file_spec, contracts, skeleton, few_shot_examples,
        design_doc_sections=design_doc_sections,
        task_description=task_description,
        domain_constraints=domain_constraints,
        language_profile=language_profile,
    )
    return _truncate_to_budget(prompt, token_budget)


def build_body_prompt(
    element: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    contracts: list[InterfaceContract],
    skeleton: Optional[str] = None,
    few_shot_examples: Optional[list[str]] = None,
    token_budget: int = 1024,
    design_doc_sections: Optional[list[str]] = None,
    task_description: Optional[str] = None,
    domain_constraints: Optional[list[str]] = None,
    language_profile: Optional[Any] = None,
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
        task_description: Optional feature-level task description forwarded
            from the seed (Mottainai Rule 2). Rendered as ``# Task context:``
            to convey intent (e.g. protocol, API style) that the skeleton
            and imports alone cannot express.
        domain_constraints: Optional domain-level constraints from plan
            ingestion (e.g. "must use async I/O", "no direct external API
            calls"). Rendered as ``# Domain constraints:``.

    Returns:
        The constructed prompt string.
    """
    # REQ-MP-204: Route constants/variables to dedicated prompt
    if element.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE):
        return _build_constant_prompt(element, file_spec, few_shot_examples)

    prompt = _build_function_prompt(
        element, file_spec, contracts, skeleton, few_shot_examples,
        design_doc_sections=design_doc_sections,
        task_description=task_description,
        domain_constraints=domain_constraints,
        language_profile=language_profile,
    )
    return _truncate_to_budget(prompt, token_budget)


def _build_function_prompt(
    element: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    contracts: list[InterfaceContract],
    skeleton: Optional[str],
    few_shot_examples: Optional[list[str]],
    design_doc_sections: Optional[list[str]] = None,
    task_description: Optional[str] = None,
    domain_constraints: Optional[list[str]] = None,
    language_profile: Optional[Any] = None,
) -> str:
    """Build prompt for function/method body generation (REQ-MP-200–203)."""
    return _build_element_prompt_core(
        element, file_spec, contracts, skeleton, few_shot_examples,
        design_doc_sections=design_doc_sections,
        task_description=task_description,
        domain_constraints=domain_constraints,
        full_function=False,
        language_profile=language_profile,
    )


def _build_full_function_prompt_inner(
    element: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    contracts: list[InterfaceContract],
    skeleton: Optional[str],
    few_shot_examples: Optional[list[str]],
    design_doc_sections: Optional[list[str]] = None,
    task_description: Optional[str] = None,
    domain_constraints: Optional[list[str]] = None,
    language_profile: Optional[Any] = None,
) -> str:
    """Build prompt asking the model to output a complete function declaration + body."""
    return _build_element_prompt_core(
        element, file_spec, contracts, skeleton, few_shot_examples,
        design_doc_sections=design_doc_sections,
        task_description=task_description,
        domain_constraints=domain_constraints,
        full_function=True,
        language_profile=language_profile,
    )


def _build_element_prompt_core(
    element: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    contracts: list[InterfaceContract],
    skeleton: Optional[str],
    few_shot_examples: Optional[list[str]],
    design_doc_sections: Optional[list[str]] = None,
    task_description: Optional[str] = None,
    domain_constraints: Optional[list[str]] = None,
    *,
    full_function: bool = False,
    language_profile: Optional[Any] = None,
) -> str:
    """Shared prompt builder for body-only and full-function modes.

    REQ-MPL-101: When *language_profile* is provided, instructions use
    language-specific stub markers, indentation rules, and declaration
    keywords from the profile (single source of truth — no parallel dict).

    The only differences between modes are:
    - Instructions (body-only vs complete function)
    - Few-shot formatting (indented body vs complete def+body)
    - Target label ("implement this" vs "implement this function")
    """
    stub = _build_element_stub(element)
    skeleton_context, indent_str, skeleton_siblings = _extract_element_context_from_skeleton(
        skeleton or "", element,
    )
    if not indent_str:
        indent_str = _fallback_indent(element)
    if skeleton_context:
        stub = skeleton_context

    import_lines = _render_imports(file_spec)
    sibling_stubs = skeleton_siblings or _render_sibling_stubs(element, file_spec)
    constraint_lines = _render_constraints(contracts)

    sections: list[str] = []

    # Class context (REQ-MP-201)
    if element.parent_class:
        bases_str = _lookup_parent_bases(element.parent_class, file_spec)
        if bases_str:
            sections.append(
                f"# This is a method of class `{element.parent_class}({bases_str})`."
            )
        else:
            sections.append(
                f"# This is a method of class `{element.parent_class}`."
            )
        init_hint = _lookup_init_context(element.parent_class, file_spec, skeleton or "")
        if init_hint:
            sections.append("# Constructor context (use `self.*` for instance state):")
            sections.append(init_hint)

    # REQ-MPL-101: Derive language-specific instruction fragments from profile.
    _decl_keyword = "def"
    _stub_marker = "raise NotImplementedError"
    _lang_id = ""
    if language_profile is not None:
        _lang_id = getattr(language_profile, "language_id", "")
        if hasattr(language_profile, "stub_marker_text"):
            _stub_marker = language_profile.stub_marker_text.strip("`")
        if _lang_id == "go":
            _decl_keyword = "func"
        elif _lang_id in ("java", "csharp"):
            _decl_keyword = "public/private"
        elif _lang_id == "nodejs":
            _decl_keyword = "function"

    # Mode-specific instructions
    if full_function:
        if element.parent_class:
            task_line = (
                f"# Task: Write the complete implementation of method `{element.name}` "
                f"for class `{element.parent_class}`."
            )
        else:
            task_line = f"# Task: Write the complete implementation of function `{element.name}`."
        sections.extend([
            task_line,
            f"# Output the full function: the `{_decl_keyword}` declaration and the function body.",
            "# Do NOT output import statements, class wrappers, or other functions.",
            "# Output ONLY the single function definition and NOTHING else.",
            "# Do NOT add comments, explanations, or markdown fences.",
            "# Do NOT wrap output in ```code blocks```. Output raw source code ONLY.",
            "",
        ])
    else:
        indent_spaces = len(indent_str or "")
        est_lines = _estimate_body_lines(element)
        def_line = None
        for line in _build_element_stub(element).splitlines():
            if line.strip().startswith("@"):
                continue
            def_line = line.strip()
            break

        if element.parent_class:
            body_framing = (
                f"# Task: Implement the body of method `{element.name}` "
                f"inside class `{element.parent_class}`."
            )
        else:
            body_framing = (
                f"# Task: Implement the body of function `{element.name}`."
            )
        # REQ-MPL-101: Language-aware indentation instruction
        if _lang_id == "go":
            _indent_instr = "# Use tab indentation (Go standard)."
        else:
            _indent_instr = f"# Indent every line with exactly {indent_spaces} spaces."

        sections.extend([
            body_framing,
            f"# Replace the `{_stub_marker}` line with a working implementation.",
            f"# The body MUST be {est_lines} lines. Do NOT exceed this.",
            "# Output ONLY the indented body lines that go INSIDE the function.",
            f"# Do NOT output a `{_decl_keyword}` line, class wrapper, docstring, or imports.",
            _indent_instr,
            "# Do NOT write standalone statements, helper functions, extra classes, main blocks, or tests.",
            "# Do NOT add comments, explanations, or markdown fences.",
            "# Output ONLY the function body and NOTHING else.",
            "",
        ])
        if def_line:
            sections.append(f"# Target signature: `{def_line}`")
            sections.append("")

    # Available imports (REQ-MP-201)
    if import_lines:
        sections.append("# Available imports (ONLY use these — do NOT invent other APIs):")
        sections.extend(import_lines)
        sections.append("")

    # Task context (Mottainai Rule 2)
    if task_description:
        sections.append(f"# Task context: {task_description}")
        sections.append("")

    # Domain constraints
    if domain_constraints:
        sections.append("# Domain constraints (MUST follow these):")
        for dc in domain_constraints:
            sections.append(f"# - {dc}")
        sections.append("")

    # Design doc context (REQ-DDS-001)
    if design_doc_sections:
        relevant, general = _partition_design_sections(
            design_doc_sections, element.name,
        )
        if relevant:
            sections.append(f"# What `{element.name}` must do:")
            for ds in relevant:
                sections.append(f"# - {ds}")
            sections.append("")
        if general:
            sections.append("# Implementation context (other parts of this feature):")
            for ds in general:
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
            if full_function:
                label = "Example (completed function)" if i == 0 else "Another example"
                sections.append(f"# {label}:")
                sections.append(ex)
            else:
                label = "Example (completed)" if i == 0 else "Another example"
                sections.append(f"# {label}:")
                sections.append(_format_example_body(ex, indent_str))
            sections.append("")

    # Target element
    if full_function:
        sections.append("# Now implement this function:")
    else:
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
        "# Output ONLY the assignment statement. 1 line maximum.",
        "# Do NOT write functions, classes, decorators, comments, or explanations.",
        "# Do NOT wrap output in markdown code fences.",
        f"# Start your output directly with `{element.name}` and STOP after the assignment.",
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
        return "1-2"
    param_count = 0
    if element.signature:
        param_count = len([
            p for p in element.signature.params if p.name not in ("self", "cls")
        ])
    if param_count == 0:
        return "3-6"
    if param_count <= 2:
        return "4-8"
    return "6-12"


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
    """Render stubs for sibling methods in the same class.

    Includes ``docstring_hint`` when available so the LLM can differentiate
    sibling methods by purpose (e.g. ``Check`` = health check vs.
    ``ListRecommendations`` = business logic).
    """
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
                hint = f"  # {sib.docstring_hint}" if sib.docstring_hint else ""
                stubs.append(f"def {sib.name}({params}){ret}: ...{hint}")
    return stubs


def _lookup_init_context(
    parent_class: str,
    file_spec: ForwardFileSpec,
    skeleton: str,
) -> Optional[str]:
    """Extract __init__ method context for a class to expose instance attributes.

    Prefers skeleton AST (has actual assignments like ``self._stub = stub``).
    Falls back to manifest __init__ signature (``def __init__(self, stub)``).
    Returns a comment-prefixed string or None.
    """
    # Try skeleton first — it has the actual __init__ body
    if skeleton:
        try:
            tree = ast.parse(skeleton)
            for node in tree.body:
                if isinstance(node, ast.ClassDef) and node.name == parent_class:
                    for child in node.body:
                        if isinstance(child, ast.FunctionDef) and child.name == "__init__":
                            lines = skeleton.splitlines()
                            start = child.lineno - 1
                            end = getattr(child, "end_lineno", None) or start + 1
                            init_lines = lines[start:end]
                            return "\n".join(f"# {line}" for line in init_lines if line.strip())
        except SyntaxError:
            pass

    # Fall back to manifest element spec for __init__
    for el in file_spec.elements:
        if el.parent_class == parent_class and el.name == "__init__" and el.signature:
            params = ", ".join(
                f"{p.name}: {p.annotation}" if p.annotation else p.name
                for p in el.signature.params
            )
            return f"# def __init__({params}): ..."

    return None


def _lookup_parent_bases(
    parent_class: str, file_spec: ForwardFileSpec,
) -> Optional[str]:
    """Find the base classes for *parent_class* from the file spec elements.

    Returns a comma-separated string like ``"demo_pb2_grpc.RecommendationServiceServicer"``
    or ``None`` if the class has no bases or isn't in the file spec.
    """
    for el in file_spec.elements:
        if el.kind == ElementKind.CLASS and el.name == parent_class and el.bases:
            return ", ".join(el.bases)
    return None


def _partition_design_sections(
    sections: list[str], element_name: str,
) -> tuple[list[str], list[str]]:
    """Split design-doc sections into element-relevant and general.

    A section is element-relevant if it mentions *element_name* (case-insensitive).
    This lets the prompt emphasize "what THIS method must do" vs. general context.
    """
    name_lower = element_name.lower()
    relevant: list[str] = []
    general: list[str] = []
    for s in sections:
        if name_lower in s.lower():
            relevant.append(s)
        else:
            general.append(s)
    return relevant, general


def _render_constraints(contracts: list[InterfaceContract]) -> list[str]:
    """Render binding constraints for the prompt."""
    lines: list[str] = []
    for c in contracts:
        prefix = "[BINDING]" if c.confidence != ContractConfidence.TENTATIVE else "[ADVISORY]"
        lines.append(f"{prefix} {c.binding_text}")
    return lines


def _is_usable_example(ce: dict) -> bool:
    """Return True if a completed element dict is safe to inject as few-shot."""
    if not ce.get("syntax_valid") or not ce.get("code"):
        return False
    # Re-validate: the syntax_valid flag may have been set before post-processing.
    try:
        ast.parse(ce["code"])
    except SyntaxError:
        return False
    return True


def _repair_sort_key(ce: dict) -> tuple[bool, int]:
    """Sort key preferring non-repaired examples, then fewer repair steps (E2: quality weighting).

    Tuple sort: non-repaired (False=0) sorts before repaired (True=1),
    then by step count ascending.
    """
    return (ce.get("repair_recovered", False), ce.get("repair_steps_count", 0))


def find_few_shot_examples(
    element: ForwardElementSpec,
    file_path: str,
    completed_elements: list[dict],
    max_examples: int = 2,
) -> list[str]:
    """Find successfully-generated siblings for few-shot injection (REQ-MP-205).

    Priority (REQ-MP-205):
        1. Same class (matching parent_class)
        2. Same file (matching file_path)
        3. Same kind (matching ElementKind, across files)

    Within each tier, candidates are sorted by repair_steps_count ascending
    so that cleaner examples are preferred (E2: quality weighting).

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
    seen: set[str] = set()

    def _add(code: str) -> bool:
        if code in seen:
            return False
        seen.add(code)
        examples.append(code)
        return True

    # Tier 1: Same class
    if element.parent_class:
        candidates = sorted(
            (ce for ce in completed_elements
             if _is_usable_example(ce)
             and ce.get("element", {}).get("parent_class") == element.parent_class
             and ce.get("element", {}).get("name") != element.name),
            key=_repair_sort_key,
        )
        for ce in candidates:
            if len(examples) >= max_examples:
                break
            _add(ce["code"].strip())

    # Tier 2: Same file
    if len(examples) < max_examples:
        candidates = sorted(
            (ce for ce in completed_elements
             if _is_usable_example(ce)
             and ce.get("file_path") == file_path
             and ce.get("element", {}).get("name") != element.name),
            key=_repair_sort_key,
        )
        for ce in candidates:
            if len(examples) >= max_examples:
                break
            _add(ce["code"].strip())

    # Tier 3: Same kind (across files)
    if len(examples) < max_examples:
        candidates = sorted(
            (ce for ce in completed_elements
             if _is_usable_example(ce)
             and ce.get("element", {}).get("kind") == element.kind
             and ce.get("element", {}).get("name") != element.name),
            key=_repair_sort_key,
        )
        for ce in candidates:
            if len(examples) >= max_examples:
                break
            _add(ce["code"].strip())

    return examples


# ── Skeleton context helpers (REQ-MP-200–203) ──────────────────────────────


def _fallback_indent(element: ForwardElementSpec) -> str:
    """Fallback indentation when skeleton context is unavailable."""
    depth = 2 if element.parent_class else 1
    return "    " * depth


def _node_start_line(node: ast.AST) -> int:
    """Return the starting line for a node, including decorators."""
    start = getattr(node, "lineno", 1)
    decorators = getattr(node, "decorator_list", None) or []
    for dec in decorators:
        dec_line = getattr(dec, "lineno", None)
        if dec_line is not None:
            start = min(start, dec_line)
    return start


def _is_not_implemented_raise(stmt: ast.stmt) -> bool:
    """Return True if the statement raises NotImplementedError."""
    if not isinstance(stmt, ast.Raise):
        return False
    exc = stmt.exc
    if isinstance(exc, ast.Name):
        return exc.id == "NotImplementedError"
    if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
        return exc.func.id == "NotImplementedError"
    return False


def _extract_docstring_lines(node: ast.AST, lines: list[str]) -> list[str]:
    """Extract docstring source lines for a ClassDef, if present."""
    body = getattr(node, "body", None)
    if not body:
        return []
    first = body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        start = getattr(first, "lineno", None)
        end = getattr(first, "end_lineno", None) or start
        if start is not None:
            return lines[start - 1: end]
    return []


def _extract_signature_lines(
    lines: list[str], def_lineno: int,
) -> list[str]:
    """Extract def signature lines starting at *def_lineno*."""
    if def_lineno <= 0 or def_lineno > len(lines):
        return []
    sig_lines: list[str] = []
    paren_depth = 0
    for line in lines[def_lineno - 1:]:
        sig_lines.append(line.rstrip())
        paren_depth += line.count("(") - line.count(")")
        if paren_depth <= 0 and line.rstrip().endswith(":"):
            break
    return sig_lines


def _signature_lines_to_stub(sig_lines: list[str]) -> Optional[str]:
    """Convert signature lines to a signature-only stub."""
    if not sig_lines:
        return None
    lines = list(sig_lines)
    last = lines[-1].rstrip()
    if last.endswith(":"):
        lines[-1] = f"{last} ..."
    else:
        lines.append(" ...")
    return textwrap.dedent("\n".join(lines))


def _extract_sibling_stubs_from_skeleton(
    lines: list[str],
    class_node: Optional[ast.ClassDef],
    element: ForwardElementSpec,
) -> list[str]:
    """Extract sibling method signature stubs from skeleton source."""
    if class_node is None:
        return []
    stubs: list[str] = []
    for child in class_node.body:
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if child.name == element.name:
            continue
        sig_lines = _extract_signature_lines(lines, child.lineno)
        stub = _signature_lines_to_stub(sig_lines)
        if stub:
            stubs.append(stub)
    return stubs


def _extract_element_context_from_skeleton(
    skeleton: str,
    element: ForwardElementSpec,
) -> tuple[Optional[str], Optional[str], list[str]]:
    """Extract the rendered element and indent level from a skeleton file."""
    if not skeleton:
        return None, None, []
    try:
        tree = ast.parse(skeleton)
    except SyntaxError:
        logger.debug("Skeleton parse failed for %s", element.name)
        return None, None, []

    lines = skeleton.splitlines()
    class_node = None
    target_node = None

    if element.parent_class:
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == element.parent_class:
                class_node = node
                break
        if class_node:
            for child in class_node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == element.name:
                    target_node = child
                    break
    else:
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == element.name:
                target_node = node
                break

    if target_node is None:
        return None, None, []

    # Extract the target element source lines (decorators -> end)
    start_line = _node_start_line(target_node)
    end_line = getattr(target_node, "end_lineno", None) or getattr(target_node, "lineno", None)
    if end_line is None:
        return None, None, []
    target_lines = lines[start_line - 1: end_line]

    # Determine indentation from the NotImplementedError stub in the skeleton
    indent_str = None
    for stmt in target_node.body:
        if _is_not_implemented_raise(stmt):
            stub_line = lines[stmt.lineno - 1]
            indent_str = stub_line[: len(stub_line) - len(stub_line.lstrip())]
            break

    # Include class header and optional class docstring for methods
    context_lines: list[str] = []
    if element.parent_class and class_node is not None:
        class_start = _node_start_line(class_node)
        context_lines.extend(lines[class_start - 1: class_node.lineno])
        context_lines.extend(_extract_docstring_lines(class_node, lines))

    context_lines.extend(target_lines)

    siblings = _extract_sibling_stubs_from_skeleton(lines, class_node, element)

    return "\n".join(context_lines), indent_str, siblings


def _strip_def_if_present(code: str) -> str:
    """Strip a leading def wrapper if the example contains one."""
    stripped = (code or "").strip()
    if not stripped:
        return ""

    lines = stripped.splitlines()
    first_code_idx = 0
    for i, line in enumerate(lines):
        lstripped = line.lstrip()
        if lstripped and not lstripped.startswith(("import ", "from ")):
            first_code_idx = i
            break

    first_line = lines[first_code_idx].lstrip() if first_code_idx < len(lines) else ""
    has_def = first_line.startswith(("def ", "async def "))

    if not has_def:
        return stripped

    if first_code_idx > 0:
        stripped = "\n".join(lines[first_code_idx:]).strip()

    try:
        tree = ast.parse(stripped)
    except SyntaxError:
        rest = stripped.splitlines()[1:]
        return "\n".join(rest)

    if not tree.body or not isinstance(tree.body[0], (ast.FunctionDef, ast.AsyncFunctionDef)):
        return stripped

    func = tree.body[0]
    all_lines = stripped.splitlines()
    body_start = func.body[0].lineno - 1 if func.body else 0
    if (
        func.body
        and isinstance(func.body[0], ast.Expr)
        and isinstance(func.body[0].value, ast.Constant)
        and isinstance(func.body[0].value.value, str)
        and len(func.body) > 1
    ):
        body_start = func.body[1].lineno - 1

    body_lines = all_lines[body_start:]
    return "\n".join(body_lines)


def _format_example_body(example: str, indent_str: str) -> str:
    """Normalize a few-shot example to body-only at the target indent."""
    body = _strip_def_if_present(example)
    if not body:
        return ""
    dedented = textwrap.dedent(body).splitlines()
    reindented = [
        indent_str + line if line.strip() else ""
        for line in dedented
    ]
    return "\n".join(reindented)

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
        ("# Implementation context (other parts", 3),
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
