"""Structural verification of generated code (AC-R4).

Pure functions extracted from engine.py — no engine state dependency.
Used by the MicroPrime engine to verify that generated code matches
the expected structure from the forward manifest.
"""

from __future__ import annotations

import ast
import textwrap
from collections.abc import Iterator
from typing import Optional

from startd8.forward_manifest import ForwardElementSpec
from startd8.utils.code_manifest import ElementKind


def structural_verify(
    code: str,
    element: ForwardElementSpec,
    language_id: str = "python",
) -> tuple[bool, str]:
    """Verify structural correctness of generated code.

    For Python: full AST-based checks (function exists, no stubs, return
    statements, self/cls parameter, factory returns, class body statements).

    For non-Python languages: syntax validation via the language's own
    parser (tree-sitter for C#, gofmt for Go, etc.).  Python-specific
    structural checks are skipped because they rely on ``ast`` module
    semantics that don't apply to other languages.

    Checks (Python only):
    - AST parses successfully
    - For functions: target function exists and body is non-empty
    - For constants: target assignment exists
    - No remaining NotImplementedError stubs
    - Return statements present when return annotation is non-None
    - Methods have ``self``/``cls`` as first parameter (unless @staticmethod)
    - Function body is not pass-only stub
    - Class body has no bare executable statements (splicer assembly defects)
    - Factory functions (create_*/make_*/build_*) return a value
    """
    if language_id != "python" and language_id:
        # Non-Python: validate syntax via language-aware parser, skip
        # Python-specific structural checks (function names, self param, etc.)
        from startd8.micro_prime.repair import _try_parse
        is_method = bool(element.parent_class)
        if _try_parse(code, is_method=is_method, language_id=language_id):
            return True, "structural checks passed (non-Python syntax valid)"
        return False, f"{language_id} syntax validation failed"
    is_method = bool(element.parent_class)

    def _render_def_line(target: ForwardElementSpec) -> Optional[str]:
        if target.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE, ElementKind.TYPE_ALIAS):
            return None
        if target.kind == ElementKind.CLASS:
            bases = f"({', '.join(target.bases)})" if target.bases else ""
            return f"class {target.name}{bases}:"
        prefix = "async def" if target.kind in (
            ElementKind.ASYNC_FUNCTION, ElementKind.ASYNC_METHOD,
        ) else "def"
        sig = "()"
        if target.signature:
            from startd8.utils.file_assembler import DeterministicFileAssembler

            assembler = DeterministicFileAssembler(element_registry=None)
            sig = assembler._render_signature(target.signature)
        ret = ""
        if target.signature and target.signature.return_annotation:
            ret = f" -> {target.signature.return_annotation}"
        return f"{prefix} {target.name}{sig}{ret}:"

    def _wrap_body(body: str, target: ForwardElementSpec) -> Optional[str]:
        def_line = _render_def_line(target)
        if def_line is None:
            return None
        wrapped = def_line + "\n" + textwrap.indent(body, "    ")
        if target.parent_class:
            wrapped = "class _Wrapper:\n" + textwrap.indent(wrapped, "    ")
        return wrapped

    # AST parse
    try:
        tree = ast.parse(code)
    except SyntaxError:
        wrapped = _wrap_body(code, element)
        if wrapped is None:
            return False, "ast.parse() failed"
        try:
            tree = ast.parse(wrapped)
        except SyntaxError:
            return False, "ast.parse() failed"

    # Check the target exists
    if element.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE):
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == element.name:
                        return True, "constant assignment found"
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id == element.name:
                    return True, "annotated assignment found"
        return False, "constant assignment not found"

    # For CLASS elements, verify the class name exists in the AST (R1-S3)
    if element.kind == ElementKind.CLASS:
        if code.strip() == "pass":
            return True, "class shell pass"
        # Reject any remaining NotImplementedError stubs in class body.
        for node in ast.walk(tree):
            if isinstance(node, ast.Raise) and _is_not_implemented(node):
                return False, "contains NotImplementedError"
        # Find the class node for semantic validation.
        class_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == element.name:
                class_node = node
                break
        if class_node is not None:
            issue = check_class_body_statements(class_node)
            if issue:
                return False, issue
            return True, "class definition found"
        return True, "class body passed syntax check"

    # For functions/methods: verify the target name exists in the AST.
    target_node = None
    if is_method and element.parent_class:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == element.parent_class:
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == element.name:
                        target_node = child
                        break
                if target_node is not None:
                    break
        if target_node is None:
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == element.name:
                    target_node = node
                    break
    else:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == element.name:
                target_node = node
                break

    if target_node is None:
        wrapped = _wrap_body(code, element)
        if wrapped is None:
            return False, "target function not found"
        try:
            tree = ast.parse(wrapped)
        except SyntaxError:
            return False, "target function not found"

        if element.parent_class:
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == "_Wrapper":
                    for child in node.body:
                        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == element.name:
                            target_node = child
                            break
                    if target_node is not None:
                        break
        else:
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == element.name:
                    target_node = node
                    break

        if target_node is None:
            return False, "target function not found"

    # Check for NotImplementedError stub — only direct body, not nested defs
    for node in _walk_body_only(target_node):
        if isinstance(node, ast.Raise) and _is_not_implemented(node):
            return False, "contains NotImplementedError"

    # Check return statements for non-None annotations — direct body only
    if element.signature and element.signature.return_annotation:
        ret_ann = element.signature.return_annotation
        if ret_ann not in ("None", "none"):
            has_return = any(
                isinstance(n, ast.Return) and n.value is not None
                for n in _walk_body_only(target_node)
            )
            if not has_return:
                return False, f"missing return for -> {ret_ann}"

    # Body must have at least one non-docstring statement
    body_stmts = []
    for stmt in target_node.body:
        if isinstance(stmt, ast.Expr) and isinstance(getattr(stmt, "value", None), ast.Constant):
            if isinstance(stmt.value.value, str):
                continue
        body_stmts.append(stmt)
    if not body_stmts:
        return False, "function body empty"

    # Reject pass-only bodies
    if all(isinstance(s, ast.Pass) for s in body_stmts):
        return False, "function body is pass-only stub"

    # Method must have self/cls as first parameter (unless @staticmethod).
    if is_method and not getattr(element, "is_static", False):
        args = target_node.args
        first_arg = args.args[0].arg if args.args else None
        expected = "cls" if getattr(element, "is_classmethod", False) else "self"
        if first_arg != expected:
            return False, f"method missing '{expected}' as first parameter"

    # Factory function return check
    _FACTORY_PREFIXES = ("create_", "make_", "build_", "get_")
    if (
        not is_method
        and any(element.name.startswith(p) for p in _FACTORY_PREFIXES)
        and element.signature
        and element.signature.return_annotation
        and element.signature.return_annotation not in ("None", "none")
    ):
        has_valued_return = any(
            isinstance(n, ast.Return) and n.value is not None
            for n in _walk_body_only(target_node)
        )
        if not has_valued_return:
            return False, (
                f"factory '{element.name}' has -> {element.signature.return_annotation} "
                "but no return with a value"
            )

    return True, "structural checks passed"


def ast_parse_valid(
    code: str,
    element: ForwardElementSpec,
    language_id: str = "python",
) -> bool:
    """Return True if the code parses as valid syntax.

    For Python: uses ``ast.parse()`` with class-wrapper fallback for methods.
    For other languages: delegates to ``repair._try_parse()`` which dispatches
    to the language's own syntax validator (tree-sitter for C#, gofmt for Go,
    etc.).
    """
    if language_id != "python" and language_id:
        # Non-Python: use the language-aware parser from the repair module
        from startd8.micro_prime.repair import _try_parse
        is_method = bool(element.parent_class)
        return _try_parse(code, is_method=is_method, language_id=language_id)

    # Python: AST-based with class-wrapper fallback for methods
    is_method = bool(element.parent_class)
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        if is_method:
            try:
                wrapped = "class _Wrapper:\n" + textwrap.indent(code, "    ")
                ast.parse(wrapped)
                return True
            except SyntaxError:
                return False
        return False


def check_class_body_statements(class_node: ast.ClassDef) -> Optional[str]:
    """Validate that a class body contains only valid class-level statements.

    Rejects bare executable expressions (e.g., ``print(...)`` at class body
    level) which are a common splicer assembly defect — method bodies leaking
    into class scope.

    Returns:
        Error description if invalid, ``None`` if the body is acceptable.
    """
    for stmt in class_node.body:
        if isinstance(stmt, (
            ast.FunctionDef, ast.AsyncFunctionDef,
            ast.ClassDef, ast.Assign, ast.AnnAssign,
            ast.Pass, ast.If, ast.Try,
        )):
            continue
        # Docstrings (string literal expressions)
        if isinstance(stmt, ast.Expr) and isinstance(
            getattr(stmt, "value", None), ast.Constant
        ):
            if isinstance(stmt.value.value, str):
                continue
        # Type alias assignment (3.12+)
        if hasattr(ast, "TypeAlias") and isinstance(stmt, ast.TypeAlias):
            continue
        # AugAssign (e.g., counter += 1) — unusual but valid at class level
        if isinstance(stmt, ast.AugAssign):
            continue
        # Everything else is suspect
        stmt_type = type(stmt).__name__
        if isinstance(stmt, ast.Expr):
            return (
                f"bare expression ({stmt_type}) at class body level "
                f"(line {getattr(stmt, 'lineno', '?')})"
            )
        if isinstance(stmt, ast.Return):
            return (
                f"return statement at class body level "
                f"(line {getattr(stmt, 'lineno', '?')})"
            )
    return None


def _walk_body_only(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Iterator[ast.AST]:
    """Walk all AST nodes inside *func_node* except nested function bodies.

    This prevents false positives when a generated function contains inner
    helper functions — e.g. a ``raise NotImplementedError`` in a nested stub
    should not flag the outer function as incomplete.
    """
    for child in ast.iter_child_nodes(func_node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield child
            continue
        yield child
        yield from ast.walk(child)


def _is_not_implemented(node: ast.Raise) -> bool:
    """Return True if a raise node corresponds to NotImplementedError."""
    if node.exc is None:
        return False
    exc = node.exc
    if isinstance(exc, ast.Call):
        func = exc.func
        if isinstance(func, ast.Name):
            return func.id == "NotImplementedError"
        if isinstance(func, ast.Attribute):
            return func.attr == "NotImplementedError"
    if isinstance(exc, ast.Name):
        return exc.id == "NotImplementedError"
    return False
