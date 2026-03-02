"""Manifest-Guided Repair Pipeline (REQ-MP-400–407).

A 7-step ordered pipeline that repairs LLM-generated code before splicing
into skeleton files. Each step is non-destructive: if it would break
previously valid code, its changes are reverted (REQ-MP-406).

Steps:
    1. Fence stripping — remove markdown code fences
    2. Over-generation trim — remove AST nodes not matching target FQN
    3. Bare statement wrapping — wrap body-only output in def/class
    4. Indentation normalize — re-indent to 4-space
    5. Signature reconcile — restore canonical signature from manifest
    6. Import completion — add missing imports
    7. AST validation — final gate
"""

from __future__ import annotations

import ast
import textwrap
from typing import Optional

from startd8.forward_manifest import ForwardElementSpec, ForwardFileSpec
from startd8.logging_config import get_logger
from startd8.micro_prime.models import RepairStepResult
from startd8.utils.code_extraction import extract_code_from_response
from startd8.utils.code_manifest import ElementKind

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Repair step functions
# ═══════════════════════════════════════════════════════════════════════════


def _step_fence_strip(
    code: str,
    element: ForwardElementSpec,
    file_spec: Optional[ForwardFileSpec] = None,
) -> RepairStepResult:
    """Step 1: Strip markdown code fences (REQ-MP-400).

    Delegates to the existing ``extract_code_from_response()`` utility.
    """
    stripped = extract_code_from_response(code)
    modified = stripped != code
    return RepairStepResult(
        step_name="fence_strip",
        modified=modified,
        code=stripped,
        metrics={"had_fences": modified},
    )


def _step_over_generation_trim(
    code: str,
    element: ForwardElementSpec,
    file_spec: Optional[ForwardFileSpec] = None,
) -> RepairStepResult:
    """Step 2: Remove AST nodes not matching the target element (REQ-MP-401).

    If the LLM generated extra functions, classes, or statements beyond the
    target element, trim them. Only applies when the code parses successfully.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return RepairStepResult(
            step_name="over_generation_trim",
            modified=False,
            code=code,
            metrics={"parse_failed": True},
        )

    target_name = element.name
    is_constant = element.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE)

    if is_constant:
        # For constants, keep only assignment to the target name
        kept_nodes: list[ast.stmt] = []
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    if node.target.id == target_name:
                        kept_nodes.append(node)
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == target_name:
                            kept_nodes.append(node)
                            break
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                kept_nodes.append(node)
        if kept_nodes and len(kept_nodes) < len(tree.body):
            tree.body = kept_nodes
            trimmed = ast.unparse(tree)
            return RepairStepResult(
                step_name="over_generation_trim",
                modified=True,
                code=trimmed,
                metrics={"nodes_removed": len(tree.body) - len(kept_nodes)},
            )
    else:
        # For functions/methods, keep only the target definition
        kept_nodes = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == target_name:
                    kept_nodes.append(node)
            elif isinstance(node, ast.ClassDef):
                if node.name == target_name:
                    kept_nodes.append(node)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                kept_nodes.append(node)
        if kept_nodes and len(kept_nodes) < len(tree.body):
            tree.body = kept_nodes
            trimmed = ast.unparse(tree)
            return RepairStepResult(
                step_name="over_generation_trim",
                modified=True,
                code=trimmed,
                metrics={"nodes_removed": len(tree.body) - len(kept_nodes)},
            )

    return RepairStepResult(
        step_name="over_generation_trim",
        modified=False,
        code=code,
    )


def _step_bare_statement_wrap(
    code: str,
    element: ForwardElementSpec,
    file_spec: Optional[ForwardFileSpec] = None,
) -> RepairStepResult:
    """Step 3: Wrap body-only output in the manifest's def line (REQ-MP-407).

    Detects when the LLM returned only the function body (no def line) and
    wraps it in the canonical signature from the manifest.
    """
    if element.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE):
        return RepairStepResult(
            step_name="bare_statement_wrap", modified=False, code=code,
        )

    # Check if the code already starts with def/async def/class
    stripped = code.lstrip()
    if stripped.startswith(("def ", "async def ", "class ")):
        return RepairStepResult(
            step_name="bare_statement_wrap", modified=False, code=code,
        )

    # Also check if it starts with a decorator
    if stripped.startswith("@"):
        return RepairStepResult(
            step_name="bare_statement_wrap", modified=False, code=code,
        )

    # Looks like body-only output — wrap it
    sig_line = _build_def_line(element)
    if sig_line is None:
        return RepairStepResult(
            step_name="bare_statement_wrap", modified=False, code=code,
        )

    # Indent body under the def
    body_lines = code.splitlines()
    indented = "\n".join(f"    {line}" if line.strip() else "" for line in body_lines)
    wrapped = f"{sig_line}\n{indented}"

    return RepairStepResult(
        step_name="bare_statement_wrap",
        modified=True,
        code=wrapped,
        metrics={"wrapped_body_lines": len(body_lines)},
    )


def _step_indent_normalize(
    code: str,
    element: ForwardElementSpec,
    file_spec: Optional[ForwardFileSpec] = None,
) -> RepairStepResult:
    """Step 4: Normalize indentation to 4-space (REQ-MP-402).

    Applies multiple strategies from the experiment script:
    1. textwrap.dedent
    2. Strip first line + dedent
    3. Strip last line + dedent
    4. Strip both + dedent
    5. Tab-to-spaces + dedent
    """
    is_method = bool(element.parent_class)

    # If already valid, skip
    if _try_parse(code, is_method):
        return RepairStepResult(
            step_name="indent_normalize", modified=False, code=code,
        )

    strategies: list[tuple[str, str]] = []
    lines = code.split("\n")

    # Strategy 1: Straight dedent
    dedented = textwrap.dedent(code).strip()
    strategies.append(("dedent", dedented))

    # Strategy 2: Strip first line + dedent
    if len(lines) > 2:
        without_first = "\n".join(lines[1:])
        strategies.append(("strip_first+dedent", textwrap.dedent(without_first).strip()))

    # Strategy 3: Strip last line + dedent
    if len(lines) > 2:
        without_last = "\n".join(lines[:-1])
        strategies.append(("strip_last+dedent", textwrap.dedent(without_last).strip()))

    # Strategy 4: Strip both + dedent
    if len(lines) > 3:
        middle = "\n".join(lines[1:-1])
        strategies.append(("strip_both+dedent", textwrap.dedent(middle).strip()))

    # Strategy 5: Tab → 4 spaces + dedent
    if "\t" in code:
        tab_fixed = code.expandtabs(4)
        strategies.append(("tabs_to_spaces+dedent", textwrap.dedent(tab_fixed).strip()))

    for name, candidate in strategies:
        if not candidate:
            continue
        if _try_parse(candidate, is_method):
            return RepairStepResult(
                step_name="indent_normalize",
                modified=True,
                code=candidate,
                metrics={"strategy": name},
            )

    return RepairStepResult(
        step_name="indent_normalize",
        modified=False,
        code=code,
        metrics={"all_strategies_failed": True},
    )


def _step_signature_reconcile(
    code: str,
    element: ForwardElementSpec,
    file_spec: Optional[ForwardFileSpec] = None,
) -> RepairStepResult:
    """Step 5: Reconcile signature against manifest (REQ-MP-403).

    If the generated function has a different signature than the manifest
    specifies, replace it with the canonical signature.
    """
    if element.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE):
        return RepairStepResult(
            step_name="signature_reconcile", modified=False, code=code,
        )
    if not element.signature:
        return RepairStepResult(
            step_name="signature_reconcile", modified=False, code=code,
        )

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return RepairStepResult(
            step_name="signature_reconcile", modified=False, code=code,
        )

    # Find the target function/class
    target_node = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == element.name:
                target_node = node
                break

    if target_node is None:
        return RepairStepResult(
            step_name="signature_reconcile", modified=False, code=code,
        )

    # Build the canonical def line from manifest
    canonical_def = _build_def_line(element)
    if canonical_def is None:
        return RepairStepResult(
            step_name="signature_reconcile", modified=False, code=code,
        )

    # Extract current def line from source
    lines = code.splitlines()
    # Find the def line (may span multiple lines with parens)
    def_start = None
    def_end = None
    paren_depth = 0
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if def_start is None:
            if stripped.startswith(("def ", "async def ")):
                def_start = i
                paren_depth += line.count("(") - line.count(")")
                if paren_depth <= 0 and ":" in line.split(")")[-1]:
                    def_end = i
                    break
        else:
            paren_depth += line.count("(") - line.count(")")
            if paren_depth <= 0:
                def_end = i
                break

    if def_start is None or def_end is None:
        return RepairStepResult(
            step_name="signature_reconcile", modified=False, code=code,
        )

    # Get the indentation of the original def line
    original_indent = lines[def_start][: len(lines[def_start]) - len(lines[def_start].lstrip())]

    # Replace the def line(s) with canonical
    new_lines = lines[:def_start] + [original_indent + canonical_def] + lines[def_end + 1 :]
    new_code = "\n".join(new_lines)

    if new_code == code:
        return RepairStepResult(
            step_name="signature_reconcile", modified=False, code=code,
        )

    return RepairStepResult(
        step_name="signature_reconcile",
        modified=True,
        code=new_code,
        metrics={"replaced_def_lines": def_end - def_start + 1},
    )


def _step_import_completion(
    code: str,
    element: ForwardElementSpec,
    file_spec: Optional[ForwardFileSpec] = None,
) -> RepairStepResult:
    """Step 6: Add missing imports from manifest (REQ-MP-404).

    Checks for names used in the code that correspond to manifest imports
    and adds any missing import statements at the top.
    """
    if file_spec is None:
        return RepairStepResult(
            step_name="import_completion", modified=False, code=code,
        )

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return RepairStepResult(
            step_name="import_completion", modified=False, code=code,
        )

    # Collect existing import names
    existing_imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                existing_imports.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                existing_imports.add(alias.asname or alias.name)

    # Collect all Name references in code
    used_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used_names.add(node.id)
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            used_names.add(node.value.id)

    # Find manifest imports that provide used names but are missing
    missing_imports: list[str] = []
    for imp in file_spec.imports:
        if imp.kind == "from":
            for name in imp.names:
                if name in used_names and name not in existing_imports:
                    names_str = ", ".join(imp.names)
                    missing_imports.append(f"from {imp.module} import {names_str}")
                    existing_imports.update(imp.names)
                    break
        else:
            mod_base = imp.module.split(".")[0]
            effective_name = imp.alias or mod_base
            if effective_name in used_names and effective_name not in existing_imports:
                alias_str = f" as {imp.alias}" if imp.alias else ""
                missing_imports.append(f"import {imp.module}{alias_str}")
                existing_imports.add(effective_name)

    if not missing_imports:
        return RepairStepResult(
            step_name="import_completion", modified=False, code=code,
        )

    # Prepend missing imports
    import_block = "\n".join(missing_imports)
    new_code = import_block + "\n\n" + code

    return RepairStepResult(
        step_name="import_completion",
        modified=True,
        code=new_code,
        metrics={"imports_added": len(missing_imports)},
    )


def _step_ast_validate(
    code: str,
    element: ForwardElementSpec,
    file_spec: Optional[ForwardFileSpec] = None,
) -> RepairStepResult:
    """Step 7: Final AST validation gate (REQ-MP-405)."""
    is_method = bool(element.parent_class)
    valid = _try_parse(code, is_method)
    return RepairStepResult(
        step_name="ast_validate",
        modified=False,
        code=code,
        metrics={"valid": valid},
    )


# ═══════════════════════════════════════════════════════════════════════════
# Pipeline orchestration
# ═══════════════════════════════════════════════════════════════════════════

# Ordered list of repair steps
_REPAIR_STEPS = [
    _step_fence_strip,
    _step_over_generation_trim,
    _step_bare_statement_wrap,
    _step_indent_normalize,
    _step_signature_reconcile,
    _step_import_completion,
    _step_ast_validate,
]


def run_repair_pipeline(
    code: str,
    element: ForwardElementSpec,
    file_spec: Optional[ForwardFileSpec] = None,
) -> tuple[str, list[RepairStepResult]]:
    """Run the full 7-step repair pipeline.

    Non-destructive guarantee (REQ-MP-406): if a step breaks previously
    valid code, its changes are reverted.

    Args:
        code: Raw LLM-generated code.
        element: Target manifest element.
        file_spec: File spec for import context.

    Returns:
        Tuple of (repaired code, list of step results).
    """
    results: list[RepairStepResult] = []
    current = code
    is_method = bool(element.parent_class)

    for step_fn in _REPAIR_STEPS:
        was_valid_before = _try_parse(current, is_method)
        result = step_fn(current, element, file_spec)
        results.append(result)

        if result.modified:
            # REQ-MP-406: Non-destructive guarantee
            is_valid_after = _try_parse(result.code, is_method)
            if was_valid_before and not is_valid_after:
                # Revert — this step broke valid code
                logger.debug(
                    "Repair step '%s' broke valid code for %s, reverting",
                    result.step_name,
                    element.name,
                )
                result.modified = False
                result.code = current
                result.metrics["reverted"] = True
            else:
                current = result.code

    return current, results


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _build_def_line(element: ForwardElementSpec) -> Optional[str]:
    """Build a canonical def/async def line from the manifest element."""
    if element.kind == ElementKind.CLASS:
        bases = f"({', '.join(element.bases)})" if element.bases else ""
        return f"class {element.name}{bases}:"

    if element.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE):
        return None

    # Build parameter list
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

    prefix = "async def" if element.kind in (
        ElementKind.ASYNC_FUNCTION, ElementKind.ASYNC_METHOD,
    ) else "def"

    return f"{prefix} {element.name}({sig}){ret}:"


def _try_parse(code: str, is_method: bool = False) -> bool:
    """Try ast.parse(), with class-wrapper fallback for methods."""
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        pass
    if is_method:
        try:
            wrapped = "class _Wrapper:\n" + textwrap.indent(code, "    ")
            ast.parse(wrapped)
            return True
        except SyntaxError:
            pass
    return False
