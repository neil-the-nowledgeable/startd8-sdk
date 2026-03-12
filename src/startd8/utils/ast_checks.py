"""Shared AST-based code validation utilities.

Used by MicroPrime engine, prime_adapter, checkpoint, and skeleton_spec_extractor
to avoid duplicate implementations of the same checks at different fidelity levels.
"""

from __future__ import annotations

import ast
from typing import List


def is_stub_only_body(body: List[ast.stmt]) -> bool:
    """Return True if a function/method body is solely a NotImplementedError stub.

    Matches bodies that are exactly one statement: ``raise NotImplementedError``
    or ``raise NotImplementedError()``, optionally preceded by a docstring.
    Bodies with any other statements (assignments, returns, calls, etc.) are
    considered real implementations — even if they also contain
    ``raise NotImplementedError`` in a branch.
    """
    stmts = list(body)
    # Strip leading docstring
    if (
        stmts
        and isinstance(stmts[0], ast.Expr)
        and isinstance(getattr(stmts[0], "value", None), ast.Constant)
        and isinstance(stmts[0].value.value, str)
    ):
        stmts = stmts[1:]
    if len(stmts) != 1:
        return False
    stmt = stmts[0]
    if not isinstance(stmt, ast.Raise):
        return False
    exc = stmt.exc
    if exc is None:
        return False
    # raise NotImplementedError
    if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
        return True
    # raise NotImplementedError()
    if (
        isinstance(exc, ast.Call)
        and isinstance(exc.func, ast.Name)
        and exc.func.id == "NotImplementedError"
    ):
        return True
    return False


def is_stub_body(body: List[ast.stmt]) -> bool:
    """Return True if a function body is a stub (pass, ..., or raise NotImplementedError).

    Broader than :func:`is_stub_only_body` — also matches ``pass``, ``...``
    (Ellipsis), and empty bodies.  Used by integration checkpoint validation
    where any kind of stub indicates incomplete code.
    """
    if not body:
        return True
    # Strip leading docstring
    stmts = list(body)
    if (
        stmts
        and isinstance(stmts[0], ast.Expr)
        and isinstance(stmts[0].value, ast.Constant)
        and isinstance(stmts[0].value.value, str)
    ):
        stmts = stmts[1:]
    if not stmts:
        return True
    if len(stmts) != 1:
        return False
    stmt = stmts[0]
    # pass
    if isinstance(stmt, ast.Pass):
        return True
    # ... (Ellipsis)
    if (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and stmt.value.value is ...
    ):
        return True
    # raise NotImplementedError — delegate to narrow check
    return is_stub_only_body(body)
