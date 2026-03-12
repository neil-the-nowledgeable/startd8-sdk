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
