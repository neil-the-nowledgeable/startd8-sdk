"""Manifest-Guided Repair Pipeline (REQ-MP-400–407).

An 8-step ordered pipeline that repairs LLM-generated code before splicing
into skeleton files. Each step is non-destructive: if it would break
previously valid code, its changes are reverted (REQ-MP-406).

Steps:
    1. Fence stripping — remove markdown code fences
    2. Over-generation trim — remove AST nodes not matching target FQN
    3. Bare statement wrapping — wrap body-only output in def/class
    4. Future import reorder — move ``from __future__`` to file top
    5. Indentation normalize — re-indent to 4-space
    6. Signature reconcile — restore canonical signature from manifest
    7. Import completion — add missing imports
    8. AST validation — final gate

Shared steps (1, 4, 5, 7, 8) delegate to ``startd8.repair.steps``.
Micro-prime-specific steps (2, 3, 6) remain local.
"""

from __future__ import annotations

import ast
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from startd8.forward_manifest import ForwardElementSpec, ForwardFileSpec, InterfaceContract
from startd8.logging_config import get_logger
from startd8.micro_prime.models import RepairAttribution, RepairStepResult
from startd8.repair.models import ElementContext, RepairContext
from startd8.repair.steps.duplicate_removal import DuplicateRemovalStep
from startd8.repair.steps.fence_strip import FenceStripStep
from startd8.repair.steps.future_import_reorder import FutureImportReorderStep
from startd8.repair.steps.import_completion import ManifestImportCompletion
from startd8.repair.steps.indent_normalize import IndentNormalizeStep
from startd8.utils.code_extraction import extract_code_from_response
from startd8.utils.code_manifest import ElementKind

logger = get_logger(__name__)

# Shared step instances
_shared_fence_strip = FenceStripStep()
_shared_future_import_reorder = FutureImportReorderStep()
_shared_indent_normalize = IndentNormalizeStep()
_shared_import_completion = ManifestImportCompletion()
_shared_duplicate_removal = DuplicateRemovalStep()


# ═══════════════════════════════════════════════════════════════════════════
# Repair step functions
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class RepairResult:
    """Result from running the manifest-guided repair pipeline (REQ-MP-400)."""

    code: str
    steps_applied: list[str]
    ast_valid: bool
    ast_valid_before: bool
    ast_valid_after: bool
    repair_recovered: bool
    metrics: dict[str, Any]
    step_results: list[RepairStepResult]
    last_error: Optional[str] = None


def _step_fence_strip(
    code: str,
    element: ForwardElementSpec,
    file_spec: Optional[ForwardFileSpec] = None,
    skeleton_source: Optional[str] = None,
) -> RepairStepResult:
    """Step 1: Strip markdown code fences (REQ-MP-400).

    Delegates to shared ``FenceStripStep``.
    """
    ctx = RepairContext()
    return _shared_fence_strip(code, ctx, Path("<element>"))


def _step_over_generation_trim(
    code: str,
    element: ForwardElementSpec,
    file_spec: Optional[ForwardFileSpec] = None,
    skeleton_source: Optional[str] = None,
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
    lines = code.splitlines()
    is_constant = element.kind in (
        ElementKind.CONSTANT, ElementKind.VARIABLE, ElementKind.TYPE_ALIAS,
    )

    target_node = None

    if is_constant:
        for node in tree.body:
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if node.target.id == target_name:
                    target_node = node
                    break
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == target_name:
                        target_node = node
                        break
            if target_node is not None:
                break
    elif element.kind == ElementKind.CLASS:
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == target_name:
                target_node = node
                break
    else:
        # Functions/methods: allow class wrapper containing target method
        if element.parent_class:
            for node in tree.body:
                if isinstance(node, ast.ClassDef) and node.name == element.parent_class:
                    for child in node.body:
                        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == target_name:
                            target_node = child
                            break
                if target_node is not None:
                    break
        if target_node is None:
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == target_name:
                    target_node = node
                    break
                if isinstance(node, ast.ClassDef):
                    for child in node.body:
                        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == target_name:
                            target_node = child
                            break
                if target_node is not None:
                    break

    if target_node is None:
        return RepairStepResult(
            step_name="over_generation_trim",
            modified=False,
            code=code,
            metrics={"target_not_found": True},
        )

    trimmed = _slice_source_for_node(lines, target_node)
    if trimmed and trimmed != code:
        return RepairStepResult(
            step_name="over_generation_trim",
            modified=True,
            code=trimmed,
            metrics={"nodes_removed": max(len(tree.body) - 1, 0)},
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
    skeleton_source: Optional[str] = None,
) -> RepairStepResult:
    """Step 3: Wrap body-only output in the manifest's def line (REQ-MP-407).

    Detects when the LLM returned only the function body (no def line) and
    wraps it in the canonical signature from the manifest.
    """
    if element.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE, ElementKind.TYPE_ALIAS):
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


def _step_future_import_reorder(
    code: str,
    element: ForwardElementSpec,
    file_spec: Optional[ForwardFileSpec] = None,
    skeleton_source: Optional[str] = None,
) -> RepairStepResult:
    """Step 4: Move ``from __future__`` imports to file top (REQ-RPL-107).

    Delegates to shared ``FutureImportReorderStep``.
    """
    ctx = RepairContext()
    return _shared_future_import_reorder(code, ctx, Path("<element>"))


def _step_indent_normalize(
    code: str,
    element: ForwardElementSpec,
    file_spec: Optional[ForwardFileSpec] = None,
    skeleton_source: Optional[str] = None,
) -> RepairStepResult:
    """Step 5: Normalize indentation to 4-space (REQ-MP-402).

    Delegates to shared ``IndentNormalizeStep``.
    """
    if skeleton_source:
        indent = _find_skeleton_indent(skeleton_source, element)
        if indent is not None and not _looks_like_definition(code):
            expanded = code.expandtabs(4)
            dedented = textwrap.dedent(expanded).strip()
            reindented = textwrap.indent(dedented, indent) if dedented else dedented
            if reindented != code:
                return RepairStepResult(
                    step_name="indent_normalize",
                    modified=True,
                    code=reindented,
                    metrics={"strategy": "skeleton"},
                )
            return RepairStepResult(
                step_name="indent_normalize",
                modified=False,
                code=code,
                metrics={"strategy": "skeleton", "no_change": True},
            )

    ec = ElementContext(parent_class=element.parent_class)
    ctx = RepairContext()
    return _shared_indent_normalize(code, ctx, Path("<element>"), ec)


def _step_signature_reconcile(
    code: str,
    element: ForwardElementSpec,
    file_spec: Optional[ForwardFileSpec] = None,
    skeleton_source: Optional[str] = None,
) -> RepairStepResult:
    """Step 6: Reconcile signature against manifest (REQ-MP-403).

    If the generated function has a different signature than the manifest
    specifies, replace it with the canonical signature.
    """
    if element.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE, ElementKind.TYPE_ALIAS):
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
                if paren_depth <= 0 and stripped.rstrip().endswith(":"):
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
    skeleton_source: Optional[str] = None,
) -> RepairStepResult:
    """Step 7: Add missing imports from manifest (REQ-MP-404).

    Delegates to shared ``ManifestImportCompletion``.
    """
    imports = file_spec.imports if file_spec else None
    ec = ElementContext(imports=imports)
    ctx = RepairContext()
    return _shared_import_completion(code, ctx, Path("<element>"), ec)


def _step_duplicate_removal(
    code: str,
    element: ForwardElementSpec,
    file_spec: Optional[ForwardFileSpec] = None,
    skeleton_source: Optional[str] = None,
) -> RepairStepResult:
    """Step 8: Remove duplicate imports (REQ-RPL-104).

    Delegates to shared ``DuplicateRemovalStep``.
    """
    ctx = RepairContext()
    return _shared_duplicate_removal(code, ctx, Path("<element>"))


def _step_ast_validate(
    code: str,
    element: ForwardElementSpec,
    file_spec: Optional[ForwardFileSpec] = None,
    skeleton_source: Optional[str] = None,
) -> RepairStepResult:
    """Step 9: Final AST validation gate (REQ-MP-405).

    Delegates to shared ``AstValidateStep``.
    """
    is_method = bool(element.parent_class)
    valid, error = _validate_ast_with_error(code, is_method)
    metrics = {"valid": valid}
    if error:
        metrics["error"] = error
    return RepairStepResult(
        step_name="ast_validate",
        modified=False,
        code=code,
        metrics=metrics,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Pipeline orchestration
# ═══════════════════════════════════════════════════════════════════════════

# Ordered list of repair steps
_REPAIR_STEPS = [
    _step_fence_strip,
    _step_over_generation_trim,
    _step_bare_statement_wrap,
    _step_future_import_reorder,
    _step_indent_normalize,
    _step_signature_reconcile,
    _step_import_completion,
    _step_duplicate_removal,
    _step_ast_validate,
]


def run_repair_pipeline(
    code: str,
    element: ForwardElementSpec,
    file_spec: Optional[ForwardFileSpec] = None,
    skeleton_source: Optional[str] = None,
) -> RepairResult:
    """Run the full 8-step repair pipeline.

    Non-destructive guarantee (REQ-MP-406): if a step breaks previously
    valid code, its changes are reverted.

    Args:
        code: Raw LLM-generated code.
        element: Target manifest element.
        file_spec: File spec for import context.
        skeleton_source: Optional skeleton source for indent normalization.

    Returns:
        RepairResult with repaired code and step metadata.
    """
    results: list[RepairStepResult] = []
    current = code
    is_method = bool(element.parent_class)
    ast_valid_before = _try_parse(current, is_method)

    for step_fn in _REPAIR_STEPS:
        was_valid_before = _try_parse(current, is_method)
        result = step_fn(current, element, file_spec, skeleton_source)
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

    # Determine AST validity + last error from ast_validate step
    ast_valid = _try_parse(current, is_method)
    last_error = None
    for r in results:
        if r.step_name == "ast_validate":
            ast_valid = bool(r.metrics.get("valid", ast_valid))
            last_error = r.metrics.get("error")
            break

    steps_applied = [r.step_name for r in results if r.modified]
    metrics = {r.step_name: r.metrics for r in results}
    ast_valid_after = ast_valid
    repair_recovered = (not ast_valid_before) and ast_valid_after

    return RepairResult(
        code=current,
        steps_applied=steps_applied,
        ast_valid=ast_valid,
        ast_valid_before=ast_valid_before,
        ast_valid_after=ast_valid_after,
        repair_recovered=repair_recovered,
        metrics=metrics,
        step_results=results,
        last_error=last_error,
    )


def repair(
    raw_output: str,
    target: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    contracts: list[InterfaceContract],
    skeleton_source: Optional[str] = None,
) -> RepairResult:
    """Run the full repair pipeline (REQ-MP-400 interface)."""
    _ = contracts  # Reserved for future steps; unused for now
    return run_repair_pipeline(
        raw_output,
        target,
        file_spec,
        skeleton_source=skeleton_source,
    )


def build_repair_attribution(
    step_results: list[RepairStepResult],
) -> RepairAttribution:
    """Build a ``RepairAttribution`` from a list of step results (REQ-MP-601).

    Maps each step's ``modified`` flag and ``metrics`` dict into the
    granular attribution fields.
    """
    attr = RepairAttribution()

    for r in step_results:
        if not r.modified:
            continue

        if r.step_name == "fence_strip":
            attr.fence_stripped = True

        elif r.step_name == "over_generation_trim":
            attr.trimmed = True
            attr.nodes_removed = r.metrics.get("nodes_removed", 0)

        elif r.step_name == "bare_statement_wrap":
            attr.bare_wrapped = True

        elif r.step_name == "indent_normalize":
            attr.indent_source = r.metrics.get("strategy", "unknown")

        elif r.step_name == "signature_reconcile":
            replaced_lines = r.metrics.get("replaced_def_lines", 0)
            attr.params_changed = replaced_lines
            attr.return_type_restored = replaced_lines > 0

        elif r.step_name == "import_completion":
            attr.imports_added = r.metrics.get("imports_added", 0)

        elif r.step_name == "duplicate_removal":
            attr.imports_removed = r.metrics.get("imports_removed", 0)

    return attr


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _build_def_line(element: ForwardElementSpec) -> Optional[str]:
    """Build a canonical def/async def line from the manifest element."""
    if element.kind == ElementKind.CLASS:
        bases = f"({', '.join(element.bases)})" if element.bases else ""
        return f"class {element.name}{bases}:"

    if element.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE, ElementKind.TYPE_ALIAS):
        return None

    # Build parameter list using DeterministicFileAssembler signature renderer
    sig = "()"
    if element.signature:
        from startd8.utils.file_assembler import DeterministicFileAssembler

        assembler = DeterministicFileAssembler()
        sig = assembler._render_signature(element.signature)

    ret = ""
    if element.signature and element.signature.return_annotation:
        ret = f" -> {element.signature.return_annotation}"

    prefix = "async def" if element.kind in (
        ElementKind.ASYNC_FUNCTION, ElementKind.ASYNC_METHOD,
    ) else "def"

    return f"{prefix} {element.name}{sig}{ret}:"


def _node_start_line(node: ast.AST) -> int:
    """Return starting line index including decorators."""
    start = getattr(node, "lineno", 1)
    decorators = getattr(node, "decorator_list", None) or []
    for dec in decorators:
        dec_line = getattr(dec, "lineno", None)
        if dec_line is not None:
            start = min(start, dec_line)
    return start


def _slice_source_for_node(lines: list[str], node: ast.AST) -> str:
    """Slice original source lines for a node (preserve exact text)."""
    start = _node_start_line(node)
    end = getattr(node, "end_lineno", None) or getattr(node, "lineno", None)
    if end is None:
        return ""
    return "\n".join(lines[start - 1: end])


def _looks_like_definition(code: str) -> bool:
    """Return True if code starts with def/async def/class/decorator."""
    stripped = (code or "").lstrip()
    return stripped.startswith(("def ", "async def ", "class ", "@"))


def _find_skeleton_indent(
    skeleton: str,
    element: ForwardElementSpec,
) -> Optional[str]:
    """Find indentation for the target element's stub in skeleton."""
    if not skeleton:
        return None
    try:
        tree = ast.parse(skeleton)
    except SyntaxError:
        return None

    lines = skeleton.splitlines()
    target = None

    if element.parent_class:
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == element.parent_class:
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == element.name:
                        target = child
                        break
            if target is not None:
                break
    else:
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == element.name:
                target = node
                break

    if target is None:
        return None

    for stmt in getattr(target, "body", []):
        if isinstance(stmt, ast.Raise):
            lineno = getattr(stmt, "lineno", None)
            if lineno is not None and 0 < lineno <= len(lines):
                line = lines[lineno - 1]
                return line[: len(line) - len(line.lstrip())]
    return None


def _validate_ast_with_error(code: str, is_method: bool = False) -> tuple[bool, Optional[str]]:
    """Validate code via ast.parse(), returning error details if invalid."""
    try:
        ast.parse(code)
        return True, None
    except SyntaxError as exc:
        err = exc

    if is_method:
        try:
            wrapped = "class _Wrapper:\n" + textwrap.indent(code, "    ")
            ast.parse(wrapped)
            return True, None
        except SyntaxError as exc:
            err = exc

    if err is None:
        return False, None

    detail = err.msg
    if err.lineno is not None:
        detail += f" (line {err.lineno}"
        if err.offset is not None:
            detail += f":{err.offset}"
        detail += ")"
    return False, detail


# Python keywords and builtins that are never valid import targets
_INVALID_IMPORT_MODULES = frozenset({
    "self", "cls", "True", "False", "None",
})


def _is_allowed_import(
    node: ast.Import | ast.ImportFrom,
    file_spec: Optional[ForwardFileSpec],
) -> bool:
    """Check if an import node is allowed by the manifest whitelist.

    Rejects:
    - ``from __future__`` imports (skeleton already has them).
    - Modules that are Python keywords/builtins (e.g. ``import self``).
    - Imports not present in ``file_spec.imports`` when a manifest is available.

    When no ``file_spec`` is provided, falls back to rejecting only
    ``__future__`` and obviously-invalid modules.
    """
    # Always reject __future__ — skeleton already has them at file level
    if isinstance(node, ast.ImportFrom) and node.module == "__future__":
        return False

    # Reject obviously-invalid module names
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name in _INVALID_IMPORT_MODULES:
                return False
    elif isinstance(node, ast.ImportFrom) and node.module:
        root = node.module.split(".")[0]
        if root in _INVALID_IMPORT_MODULES:
            return False

    # If no manifest, allow (best-effort — only reject obvious junk)
    if file_spec is None or not file_spec.imports:
        return True

    # Build a set of allowed (module, kind) pairs from the manifest
    allowed_modules: set[str] = set()
    for imp in file_spec.imports:
        allowed_modules.add(imp.module)
        # Also allow root package (e.g. "grpc" for "grpc_health.v1")
        root = imp.module.split(".")[0]
        allowed_modules.add(root)

    if isinstance(node, ast.Import):
        return all(
            alias.name.split(".")[0] in allowed_modules
            for alias in node.names
        )
    elif isinstance(node, ast.ImportFrom) and node.module:
        root = node.module.split(".")[0]
        return root in allowed_modules

    return True


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
