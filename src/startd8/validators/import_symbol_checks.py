"""Symbol-level import validation + referenced-template existence (F-6).

Closes the RUN-009/RUN-010 false-PASS class: an *unwired* generated module is
unfalsifiable — nothing imports it, so ``from starlette.responses import
TemplateResponse`` (a phantom symbol: the module exists, the name does not)
sails through module-level import resolution (L1) and every test stays green.

Two checks, both **fully static** — no generated code, and no third-party
code, is ever executed:

1. ``check_import_symbols`` — for each ``from M import name``, locate M's
   source file (project tree first, then the installed environment via a
   non-importing ``find_spec`` + path walk) and verify ``name`` is bound at
   module level of M's AST (def/class/assignment/import/``__all__``) or is a
   submodule on disk.  Modules with dynamic export surfaces (``import *``,
   module-level ``__getattr__``) are skipped — no claims, no false positives.
   Unlocatable modules are skipped too (module-level resolution is L1's job).

2. ``check_template_references`` — template names passed to
   ``TemplateResponse(...)`` / ``get_template(...)`` / ``render_template(...)``
   must exist on disk under a discoverable template root.  For f-string names
   (``f"wizard/{step}.html"``) the constant directory prefix is verified.
   When no template root exists at all the check makes no claims.

Why static over a runtime/subprocess import probe: importing arbitrary
generated code executes it (the gate must never run the thing it is judging),
and even a subprocess probe executes third-party module-level code and couples
the verdict to the validator venv's package versions.  AST parsing of the
resolved module source is side-effect-free, deterministic, and fast; the
conservative skip rules above absorb the dynamic-export cases where a static
reading would lie.

Issue dicts use the same shape as the other ``DiskComplianceResult``
``semantic_issues`` entries: ``category`` / ``severity`` / ``message`` /
``line`` / ``symbol``.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

__all__ = [
    "check_import_symbols",
    "check_template_references",
]

# ---------------------------------------------------------------------------
# Module binding-surface extraction (static)
# ---------------------------------------------------------------------------

# Cache of parsed module binding surfaces keyed by (path, mtime_ns).
# Third-party modules (e.g. starlette/responses.py) get parsed once per
# process instead of once per validated file.
_BINDINGS_CACHE: Dict[Tuple[str, int], Optional[frozenset]] = {}


def _collect_binding_names(tree: ast.Module) -> Optional[Set[str]]:
    """Collect names bound at module level of *tree*.

    Returns ``None`` when the module has a dynamic export surface that a
    static reading cannot enumerate (``from x import *`` or a module-level
    ``__getattr__``) — callers must then make no claims about the module.

    Walks through module-level ``if``/``try``/``for``/``while``/``with``
    blocks (conditional definitions still bind names on some path — counting
    them is the conservative, false-positive-avoiding direction).
    """
    names: Set[str] = set()

    def _walk(stmts) -> bool:
        """Returns False if a dynamic export surface was found."""
        for stmt in stmts:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if stmt.name == "__getattr__":
                    return False  # PEP 562 lazy exports — unverifiable
                names.add(stmt.name)
            elif isinstance(stmt, ast.ClassDef):
                names.add(stmt.name)
            elif isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    names.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(stmt, ast.ImportFrom):
                for alias in stmt.names:
                    if alias.name == "*":
                        return False  # re-export star — unverifiable
                    names.add(alias.asname or alias.name)
            elif isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    _add_target(target)
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        names.update(_string_elts(stmt.value))
            elif isinstance(stmt, ast.AugAssign):
                _add_target(stmt.target)
                if isinstance(stmt.target, ast.Name) and stmt.target.id == "__all__":
                    names.update(_string_elts(stmt.value))
            elif isinstance(stmt, ast.AnnAssign):
                _add_target(stmt.target)
            elif isinstance(stmt, ast.If):
                if not _walk(stmt.body) or not _walk(stmt.orelse):
                    return False
            elif isinstance(stmt, ast.Try):
                for block in (stmt.body, stmt.orelse, stmt.finalbody):
                    if not _walk(block):
                        return False
                for handler in stmt.handlers:
                    if not _walk(handler.body):
                        return False
            elif isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)):
                if isinstance(stmt, (ast.For, ast.AsyncFor)):
                    _add_target(stmt.target)
                if not _walk(stmt.body) or not _walk(stmt.orelse):
                    return False
            elif isinstance(stmt, (ast.With, ast.AsyncWith)):
                for item in stmt.items:
                    if item.optional_vars is not None:
                        _add_target(item.optional_vars)
                if not _walk(stmt.body):
                    return False
            elif isinstance(stmt, ast.Match):
                # Module-level match: case bodies bind like any block, and
                # capture patterns (`case X() as name:` / `case name:`) bind
                # names too — count both (conservative direction).
                for case in stmt.cases:
                    _add_pattern_names(case.pattern)
                    if not _walk(case.body):
                        return False
        return True

    def _add_pattern_names(pattern) -> None:
        if isinstance(pattern, ast.MatchAs) and pattern.name:
            names.add(pattern.name)
        if isinstance(pattern, ast.MatchStar) and pattern.name:
            names.add(pattern.name)
        if isinstance(pattern, ast.MatchMapping) and pattern.rest:
            names.add(pattern.rest)
        for child in ast.iter_child_nodes(pattern):
            if isinstance(child, ast.pattern):
                _add_pattern_names(child)

    def _add_target(target: ast.expr) -> None:
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                _add_target(elt)
        elif isinstance(target, ast.Starred):
            _add_target(target.value)

    def _string_elts(value: Optional[ast.expr]) -> Set[str]:
        out: Set[str] = set()
        if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
            for elt in value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    out.add(elt.value)
        return out

    if not _walk(getattr(tree, "body", [])):
        return None
    # Walrus bindings (`(x := ...)`) anywhere in the module. Deliberately
    # over-collects (function-local walruses too) — adding names is the
    # conservative direction: it can only suppress false positives.
    for node in ast.walk(tree):
        if isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _module_bindings(module_file: Path) -> Optional[frozenset]:
    """Parse *module_file* and return its module-level binding surface.

    Returns ``None`` when the module is dynamic or unreadable/unparseable
    (no claims).  Cached by (path, mtime).
    """
    try:
        key = (str(module_file), module_file.stat().st_mtime_ns)
    except OSError:
        return None
    if key in _BINDINGS_CACHE:
        return _BINDINGS_CACHE[key]
    result: Optional[frozenset] = None
    try:
        source = module_file.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
        collected = _collect_binding_names(tree)
        result = frozenset(collected) if collected is not None else None
    except (OSError, SyntaxError, ValueError):
        result = None
    _BINDINGS_CACHE[key] = result
    return result


# ---------------------------------------------------------------------------
# Module location (static — never imports the target)
# ---------------------------------------------------------------------------


def _locate_in_dir(base: Path, dotted: str) -> Tuple[Optional[Path], Optional[Path]]:
    """Resolve *dotted* under *base* dir → (module_source_file, package_dir).

    ``package_dir`` is set when the module is a package (its directory) so
    callers can verify submodule fallback (``from pkg import submodule``).
    """
    parts = dotted.split(".") if dotted else []
    cur = base
    for i, part in enumerate(parts):
        is_last = i == len(parts) - 1
        as_file = cur / f"{part}.py"
        as_dir = cur / part
        if is_last:
            if as_file.is_file():
                return as_file, None
            if as_dir.is_dir():
                init = as_dir / "__init__.py"
                # Namespace package (no __init__): empty binding surface,
                # but submodule fallback still applies.
                return (init if init.is_file() else None), as_dir
            return None, None
        if as_dir.is_dir():
            cur = as_dir
        else:
            return None, None
    # dotted == "" → base itself is the package dir (relative `from . import x`)
    init = cur / "__init__.py"
    return (init if init.is_file() else None), cur


def _locate_installed(dotted: str) -> Tuple[Optional[Path], Optional[Path], bool]:
    """Locate an installed module's source without importing it.

    Uses ``find_spec`` on the **top-level** name only (which consults the
    meta path without executing the module), then walks sub-segments on the
    filesystem.  Returns ``(module_file, package_dir, located)`` where
    ``located=False`` means the module could not be found/verified at all
    (not installed, builtin, frozen, or a compiled extension) — make no
    claims in that case.
    """
    top = dotted.split(".")[0]
    if top in sys.builtin_module_names:
        return None, None, False
    try:
        spec = importlib.util.find_spec(top)
    except (ImportError, ValueError, AttributeError):
        return None, None, False
    if spec is None:
        return None, None, False

    search_locations = list(spec.submodule_search_locations or [])
    rest = dotted.split(".")[1:]

    if not search_locations:
        # Single-file module (top-level .py or extension)
        origin = spec.origin or ""
        if rest:
            return None, None, False  # dotted path under a non-package
        if origin.endswith(".py") and Path(origin).is_file():
            return Path(origin), None, True
        return None, None, False  # builtin/frozen/extension — unverifiable

    if not rest:
        # Top-level package: __init__.py (or namespace pkg) + package dir
        for loc in search_locations:
            pkg_dir = Path(loc)
            init = pkg_dir / "__init__.py"
            if init.is_file():
                return init, pkg_dir, True
        if search_locations:
            return None, Path(search_locations[0]), True  # namespace pkg
        return None, None, False

    # Walk remaining segments across the search locations.
    for loc in search_locations:
        module_file, pkg_dir = _locate_in_dir(Path(loc), ".".join(rest))
        if module_file is not None or pkg_dir is not None:
            return module_file, pkg_dir, True
    return None, None, False


def _locate_module(
    node: ast.ImportFrom,
    abs_file: Path,
    project_root: Path,
) -> Tuple[Optional[Path], Optional[Path], bool]:
    """Locate the source of an ``ImportFrom`` target.

    Returns ``(module_file, package_dir, located)``.  ``located=False``
    means unverifiable (skip — module-level resolution is L1's concern).
    Resolution order: relative → project tree (root, then the file's own
    directory) → installed environment.
    """
    dotted = node.module or ""

    if node.level and node.level > 0:
        base = abs_file.parent
        for _ in range(node.level - 1):
            base = base.parent
        module_file, pkg_dir = _locate_in_dir(base, dotted)
        if module_file is not None or pkg_dir is not None:
            return module_file, pkg_dir, True
        return None, None, False  # broken relative import — L1 territory

    for base in (project_root, abs_file.parent):
        try:
            module_file, pkg_dir = _locate_in_dir(base, dotted)
        except OSError:
            continue
        if module_file is not None or pkg_dir is not None:
            return module_file, pkg_dir, True

    return _locate_installed(dotted)


# ---------------------------------------------------------------------------
# Check 1 — phantom symbols (F-6.1)
# ---------------------------------------------------------------------------


def check_import_symbols(
    tree: ast.AST,
    file_path: str,
    project_root: str,
) -> List[Dict[str, object]]:
    """Verify every ``from M import name`` names a symbol M actually binds.

    The RUN-009/RUN-010 phantom-import class: ``from starlette.responses
    import TemplateResponse`` — the module resolves (L1 passes) but the
    symbol does not exist, so the generated module can never import.

    Purely static: the target module's source is *parsed*, never executed.
    Emits ``phantom_symbol`` issues (severity ``error``).
    """
    issues: List[Dict[str, object]] = []
    root = Path(project_root)
    abs_file = Path(file_path)
    if not abs_file.is_absolute():
        abs_file = root / file_path

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if any(alias.name == "*" for alias in node.names):
            continue  # star import — nothing symbol-level to verify

        try:
            module_file, pkg_dir, located = _locate_module(node, abs_file, root)
        except Exception:
            continue
        if not located:
            continue  # unverifiable — no claims (L1 owns module-level)

        bindings: Optional[frozenset]
        if module_file is not None:
            if module_file.resolve() == abs_file.resolve():
                continue  # self-import edge case
            bindings = _module_bindings(module_file)
            if bindings is None:
                continue  # dynamic/unparseable module — no claims
        else:
            bindings = frozenset()  # namespace package: only submodules bind

        dotted = ("." * (node.level or 0)) + (node.module or "")
        for alias in node.names:
            name = alias.name
            if name in bindings:
                continue
            # Submodule fallback: `from pkg import sub` works when
            # pkg/sub.py or pkg/sub/ exists even if __init__ never binds it.
            if pkg_dir is not None and (
                (pkg_dir / f"{name}.py").is_file() or (pkg_dir / name).is_dir()
            ):
                continue
            location = str(module_file if module_file is not None else pkg_dir)
            issues.append({
                "category": "phantom_symbol",
                "severity": "error",
                "message": (
                    f"from '{dotted}' import '{name}' — symbol not found in "
                    f"the resolved module ({location}); this module cannot "
                    f"be imported (ImportError at load time)"
                ),
                "line": node.lineno,
                "symbol": f"{dotted}.{name}",
            })
    return issues


# ---------------------------------------------------------------------------
# Check 2 — referenced template assets (F-6.2)
# ---------------------------------------------------------------------------

_TEMPLATE_CALL_NAMES = frozenset({
    "TemplateResponse",   # Starlette/FastAPI
    "get_template",       # Jinja2 Environment / Jinja2Templates.env
    "select_template",    # Jinja2 Environment
    "render_template",    # Flask
})

# Calls whose string arguments declare a template *root* directory.
_TEMPLATE_ROOT_FACTORIES = frozenset({"Jinja2Templates", "FileSystemLoader"})

_SKIP_WALK_DIRS = frozenset({
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__",
    ".startd8", ".cap-dev-pipe", ".mypy_cache", ".ruff_cache", ".pytest_cache",
    "site-packages", "dist", "build", ".tox",
})
_MAX_WALK_DEPTH = 6
_MAX_WALK_DIRS = 4000


def _call_simple_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _discover_template_roots(tree: ast.AST, project_root: Path, abs_file: Path) -> List[Path]:
    """Find candidate template root directories.

    Union of (a) directories literally declared in this file via
    ``Jinja2Templates(directory=...)`` / ``FileSystemLoader(...)`` and
    (b) any directory named ``templates`` under the project root
    (bounded walk).  Returns only directories that exist.
    """
    roots: List[Path] = []

    # (a) declared in-file
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _call_simple_name(node.func) not in _TEMPLATE_ROOT_FACTORIES:
            continue
        candidates: List[str] = []
        for arg in node.args[:1]:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                candidates.append(arg.value)
        for kw in node.keywords:
            if kw.arg in ("directory", "searchpath") and isinstance(
                kw.value, ast.Constant
            ) and isinstance(kw.value.value, str):
                candidates.append(kw.value.value)
        for cand in candidates:
            for base in (project_root, abs_file.parent):
                p = (base / cand) if not Path(cand).is_absolute() else Path(cand)
                if p.is_dir() and p not in roots:
                    roots.append(p)

    # (b) bounded walk for dirs named "templates"
    visited = 0
    root_depth = len(project_root.parts)
    for dirpath, dirnames, _filenames in os.walk(project_root):
        visited += 1
        if visited > _MAX_WALK_DIRS:
            break
        depth = len(Path(dirpath).parts) - root_depth
        if depth >= _MAX_WALK_DEPTH:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in _SKIP_WALK_DIRS]
        for d in dirnames:
            if d == "templates":
                p = Path(dirpath) / d
                if p not in roots:
                    roots.append(p)
    return roots


def _template_name_candidates(node: ast.Call) -> List[ast.expr]:
    """Argument expressions that may carry the template name.

    Covers both Starlette signatures — ``TemplateResponse(name, ctx)`` and
    ``TemplateResponse(request, name, ctx)`` — plus ``name=`` /
    ``template_name=`` keywords, and single-arg ``get_template(name)``.
    """
    cands: List[ast.expr] = list(node.args[:2])
    for kw in node.keywords:
        if kw.arg in ("name", "template_name"):
            cands.append(kw.value)
    return cands


def check_template_references(
    tree: ast.AST,
    file_path: str,
    project_root: str,
) -> List[Dict[str, object]]:
    """Verify referenced templates exist on disk post-merge (F-6.2).

    RUN-009: ``templates.TemplateResponse(f"wizard/{step}.html", ...)`` with
    no ``app/templates/wizard/`` on disk — the cross-file contract only
    covered *named target files*, not referenced assets.

    Constant template names must exist under a template root; f-string names
    have their constant directory prefix verified.  When no template root
    can be discovered at all, no claims are made.
    Emits ``missing_template_asset`` issues (severity ``error``).
    """
    issues: List[Dict[str, object]] = []

    # Lazy root discovery — only pay the walk if the file references templates
    template_calls: List[ast.Call] = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _call_simple_name(node.func) in _TEMPLATE_CALL_NAMES
    ]
    if not template_calls:
        return issues

    root = Path(project_root)
    abs_file = Path(file_path)
    if not abs_file.is_absolute():
        abs_file = root / file_path

    roots = _discover_template_roots(tree, root, abs_file)
    if not roots:
        return issues  # no template root anywhere — unverifiable, no claims

    seen: Set[str] = set()
    for call in template_calls:
        for cand in _template_name_candidates(call):
            if isinstance(cand, ast.Constant) and isinstance(cand.value, str):
                name = cand.value
                if "." not in Path(name).name:
                    continue  # not template-shaped (e.g. a request variable)
                if name in seen:
                    break
                seen.add(name)
                if not any((r / name).is_file() for r in roots):
                    issues.append({
                        "category": "missing_template_asset",
                        "severity": "error",
                        "message": (
                            f"referenced template '{name}' not found under any "
                            f"template root "
                            f"({', '.join(str(r) for r in roots[:3])})"
                        ),
                        "line": call.lineno,
                        "symbol": name,
                    })
                break  # first string-bearing candidate wins
            if isinstance(cand, ast.JoinedStr):
                prefix = ""
                for part in cand.values:
                    if isinstance(part, ast.Constant) and isinstance(part.value, str):
                        prefix += part.value
                    else:
                        break
                if "/" not in prefix:
                    break  # dynamic name with no constant directory — no claims
                dir_prefix = prefix.rsplit("/", 1)[0]
                key = f"{dir_prefix}/*"
                if key in seen:
                    break
                seen.add(key)
                if not any((r / dir_prefix).is_dir() for r in roots):
                    issues.append({
                        "category": "missing_template_asset",
                        "severity": "error",
                        "message": (
                            f"templates referenced under directory "
                            f"'{dir_prefix}/' (dynamic name) but no such "
                            f"directory exists under any template root "
                            f"({', '.join(str(r) for r in roots[:3])})"
                        ),
                        "line": call.lineno,
                        "symbol": f"{dir_prefix}/",
                    })
                break
    return issues
