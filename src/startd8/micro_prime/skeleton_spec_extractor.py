"""
Skeleton AST Spec Extractor — REQ-MP-1104.

When a feature has zero ForwardElementSpecs after plan ingestion AND a skeleton
or generated file exists on disk, this module parses its AST and creates
ForwardElementSpec entries for each ``def``/``class`` containing
``raise NotImplementedError``.

ID format: ``flcm-skel-{relpath}:{line}:{name}``

Precedence: below ``source-ast`` — must not overwrite specs from
higher-precedence sources (deterministic, human-yaml, proto).
"""

from __future__ import annotations

import ast
from typing import Optional

from startd8.forward_manifest import ForwardElementSpec
from startd8.logging_config import get_logger
from startd8.utils.code_manifest import ElementKind, Param, ParamKind, Signature

logger = get_logger(__name__)


from startd8.utils.ast_checks import is_stub_only_body as _is_stub_body  # noqa: E402


def _make_spec_id(file_path: str, line: int, name: str) -> str:
    """Build the skeleton spec ID: ``flcm-skel-{relpath}:{line}:{name}``."""
    return f"flcm-skel-{file_path}:{line}:{name}"


def _extract_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> Signature:
    """Extract a Signature from an AST function definition."""
    params: list[Param] = []
    args = node.args

    # Positional-only params
    for arg in args.posonlyargs:
        params.append(
            Param(
                name=arg.arg,
                annotation=ast.unparse(arg.annotation) if arg.annotation else None,
                kind=ParamKind.POSITIONAL_ONLY,
            )
        )

    # Regular positional params
    # defaults align to the end of args.args
    num_args = len(args.args)
    num_defaults = len(args.defaults)
    for i, arg in enumerate(args.args):
        default_index = i - (num_args - num_defaults)
        default = (
            ast.unparse(args.defaults[default_index])
            if default_index >= 0
            else None
        )
        params.append(
            Param(
                name=arg.arg,
                annotation=ast.unparse(arg.annotation) if arg.annotation else None,
                default=default,
                kind=ParamKind.POSITIONAL,
            )
        )

    # *args
    if args.vararg:
        params.append(
            Param(
                name=args.vararg.arg,
                annotation=(
                    ast.unparse(args.vararg.annotation)
                    if args.vararg.annotation
                    else None
                ),
                kind=ParamKind.VAR_POSITIONAL,
            )
        )

    # keyword-only
    for i, arg in enumerate(args.kwonlyargs):
        kw_default = args.kw_defaults[i] if i < len(args.kw_defaults) else None
        params.append(
            Param(
                name=arg.arg,
                annotation=ast.unparse(arg.annotation) if arg.annotation else None,
                default=ast.unparse(kw_default) if kw_default else None,
                kind=ParamKind.KEYWORD_ONLY,
            )
        )

    # **kwargs
    if args.kwarg:
        params.append(
            Param(
                name=args.kwarg.arg,
                annotation=(
                    ast.unparse(args.kwarg.annotation)
                    if args.kwarg.annotation
                    else None
                ),
                kind=ParamKind.VAR_KEYWORD,
            )
        )

    return_annotation = ast.unparse(node.returns) if node.returns else None
    return Signature(params=params, return_annotation=return_annotation)


def _func_to_spec(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    file_path: str,
    parent_class: Optional[str] = None,
) -> Optional[ForwardElementSpec]:
    """Convert a stub function/method AST node to a ForwardElementSpec."""
    if not _is_stub_body(node.body):
        return None

    is_async = isinstance(node, ast.AsyncFunctionDef)

    if parent_class is not None:
        kind = ElementKind.ASYNC_METHOD if is_async else ElementKind.METHOD
    else:
        kind = ElementKind.ASYNC_FUNCTION if is_async else ElementKind.FUNCTION

    decorator_names = []
    is_static = False
    is_classmethod = False
    is_abstract = False
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name):
            decorator_names.append(dec.id)
            if dec.id == "staticmethod":
                is_static = True
            elif dec.id == "classmethod":
                is_classmethod = True
            elif dec.id == "abstractmethod":
                is_abstract = True
        elif isinstance(dec, ast.Attribute):
            attr_name = ast.unparse(dec)
            decorator_names.append(attr_name)
            if attr_name == "abc.abstractmethod":
                is_abstract = True

    signature = _extract_signature(node)
    spec_id = _make_spec_id(file_path, node.lineno, node.name)

    return ForwardElementSpec(
        kind=kind,
        name=node.name,
        signature=signature,
        parent_class=parent_class,
        source_contract_id=spec_id,
        decorators=decorator_names,
        is_static=is_static,
        is_classmethod=is_classmethod,
        is_abstract=is_abstract,
    )


def extract_skeleton_specs(
    source_code: str,
    file_path: str,
) -> list[ForwardElementSpec]:
    """Parse source code AST and create ForwardElementSpecs for stub elements.

    Only creates specs for functions/methods whose body is solely
    ``raise NotImplementedError`` (with an optional docstring).

    Args:
        source_code: Python source code to parse.
        file_path: Relative file path used in spec IDs.

    Returns:
        List of ForwardElementSpec entries for stub elements.
        Empty list on syntax errors or empty files.
    """
    if not source_code or not source_code.strip():
        return []

    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        logger.warning(
            "Failed to parse skeleton file; returning empty specs",
            extra={"file_path": file_path},
        )
        return []

    specs: list[ForwardElementSpec] = []

    for node in ast.iter_child_nodes(tree):
        # Top-level functions
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            spec = _func_to_spec(node, file_path)
            if spec is not None:
                specs.append(spec)

        # Classes: extract stub methods
        elif isinstance(node, ast.ClassDef):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    spec = _func_to_spec(child, file_path, parent_class=node.name)
                    if spec is not None:
                        specs.append(spec)

    if specs:
        logger.debug(
            "Extracted skeleton specs",
            extra={"file_path": file_path, "count": len(specs)},
        )

    return specs


# ═══════════════════════════════════════════════════════════════════════════
# Go skeleton spec extraction — REQ-GO-MP-700
# ═══════════════════════════════════════════════════════════════════════════


def extract_go_skeleton_specs(
    source_code: str,
    file_path: str,
) -> list[ForwardElementSpec]:
    """Parse Go source and create ForwardElementSpecs for stub functions.

    Creates specs for functions/methods whose body matches Go stub patterns
    (``panic("not implemented")``, ``// TODO``, empty body).

    Uses ``go_parser.parse_go_source()`` for structural extraction and
    ``GoLanguageProfile.stub_patterns`` for stub detection.

    Args:
        source_code: Go source code to parse.
        file_path: Relative file path used in spec IDs.

    Returns:
        List of ForwardElementSpec entries for stub elements.
        Empty list on parse errors or empty files.
    """
    if not source_code or not source_code.strip():
        return []

    try:
        from startd8.languages.go_parser import parse_go_source
        from startd8.languages.registry import LanguageRegistry
    except ImportError:
        logger.debug("Go parser not available for skeleton extraction")
        return []

    elements = parse_go_source(source_code)
    if not elements:
        return []

    # Get stub patterns from Go profile
    LanguageRegistry.discover()
    go_profile = LanguageRegistry.get("go")
    stub_regexes = []
    if go_profile and hasattr(go_profile, "stub_patterns"):
        import re as _re
        stub_regexes = [_re.compile(p) for p in go_profile.stub_patterns]

    # Detect stubs by finding the function body (brace-matched) and
    # checking if it matches a stub pattern.
    source_lines = source_code.splitlines()

    # Import splicer helpers for precise body range detection
    try:
        from startd8.languages.go_splicer import _find_func_declaration, _find_body_range
        _has_splicer = True
    except ImportError:
        _has_splicer = False

    specs: list[ForwardElementSpec] = []
    for elem in elements:
        if elem.kind not in ("function", "method"):
            continue

        # Find the function body precisely via brace matching
        is_stub = False
        if _has_splicer:
            decl_line = _find_func_declaration(source_lines, elem.name)
            if decl_line is not None:
                body_range = _find_body_range(source_lines, decl_line)
                if body_range:
                    open_line, close_line = body_range
                    body_text = "\n".join(source_lines[open_line + 1:close_line])
                    for pat in stub_regexes:
                        if pat.search(body_text):
                            is_stub = True
                            break
        else:
            # Fallback: check 3 lines after declaration (less precise)
            start_line = elem.line_number  # 1-based
            for i in range(start_line, min(start_line + 3, len(source_lines))):
                line = source_lines[i] if i < len(source_lines) else ""
                for pat in stub_regexes:
                    if pat.search(line):
                        is_stub = True
                        break
                if is_stub:
                    break

        if not is_stub:
            continue

        # Build spec
        kind = ElementKind.METHOD if elem.parent_type else ElementKind.FUNCTION
        spec_id = _make_spec_id(file_path, elem.line_number, elem.name)
        sig = Signature(params=[], return_annotation=elem.return_type)

        specs.append(ForwardElementSpec(
            name=elem.name,
            kind=kind,
            signature=sig,
            parent_class=elem.parent_type,
            decomposition_source=spec_id,
        ))

    if specs:
        logger.debug(
            "Extracted Go skeleton specs",
            extra={"file_path": file_path, "count": len(specs)},
        )

    return specs
