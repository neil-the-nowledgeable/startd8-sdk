"""
Deterministic File Assembler — renders skeleton ``.py`` files from
``ForwardManifest.file_specs`` without LLM calls.

Converts IMPLEMENT from "generate entire files" to "fill in function bodies"
by deterministically producing Python source with correct signatures, imports,
class structure, and ``raise NotImplementedError`` stubs.

Two modes of operation:

- **render_specs** — pure computation, returns ``{filepath: source_text}``
  with ``ast.parse()`` validation.  No disk I/O.
- **materialize** — writes validated specs to disk via atomic writes,
  creating ``__init__.py`` chains for intermediate packages.

Mottainai rules addressed:

- Rule 2: Forward, don't regenerate
- Rule 4: Register what you produce
- Rule 5: Prefer deterministic over stochastic
"""

from __future__ import annotations

import ast
import hashlib
import keyword
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, NamedTuple, Optional, Set

from startd8.logging_config import get_logger

# Identifier scanner + the typing exports a skeleton may reference in annotations. Used to
# complete the `from typing import …` line from signatures so `-> List[Dict]` doesn't render
# with undefined names (which fails type-check and breaks FastAPI/SQLModel get_type_hints).
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_TYPING_EXPORTS: frozenset = frozenset({
    "Any", "Dict", "List", "Optional", "Tuple", "Set", "FrozenSet", "Union", "Callable",
    "Iterable", "Iterator", "Mapping", "MutableMapping", "Sequence", "MutableSequence",
    "Type", "Deque", "DefaultDict", "Counter", "OrderedDict", "Awaitable", "Coroutine",
    "AsyncIterator", "AsyncIterable", "AsyncGenerator", "Generator", "ClassVar", "Final",
    "Literal", "Annotated", "TypedDict", "Protocol", "NamedTuple", "NewType", "TypeVar",
    "NoReturn", "Hashable", "Text", "IO", "BinaryIO", "TextIO", "Pattern", "Match",
})
from startd8.utils.code_manifest import (
    ElementKind,
    ParamKind,
    Signature,
    Visibility,
)

if TYPE_CHECKING:
    from startd8.contractors.context_schema import FileStubResult
    from startd8.forward_manifest import (
        ForwardDependencies,
        ForwardElementSpec,
        ForwardFileSpec,
        ForwardImportSpec,
        ForwardManifest,
    )

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SKELETON_SENTINEL = "# [STARTD8-SKELETON]"
"""First line of every generated skeleton file.  Used by downstream phases
(PriorArtModule, IMPLEMENT drift detection) to identify assembler output."""

# Stdlib detection — reuse the canonical set from code_manifest
try:
    from startd8.utils.code_manifest import _STDLIB_MODULES
except ImportError:  # pragma: no cover
    _STDLIB_MODULES: set[str] = getattr(sys, "stdlib_module_names", None) or set()
    logger.debug(
        "Could not import _STDLIB_MODULES from code_manifest; "
        "falling back to sys.stdlib_module_names (%d modules)",
        len(_STDLIB_MODULES),
    )

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class StubManifestEntry(NamedTuple):
    """Compact metadata for seed embedding (~100 bytes per file)."""

    file_path: str
    sha256: str
    elements_count: int
    imports_count: int
    validated: bool


class RenderResult(NamedTuple):
    """Output of ``render_specs()``."""

    specs: Dict[str, str]
    """Mapping of filepath → validated source text."""
    failures: list
    """``FileStubResult`` instances for render failures (phase="render")."""
    metadata: List[StubManifestEntry]
    """Compact entries for seed embedding."""


# ---------------------------------------------------------------------------
# Assembler
# ---------------------------------------------------------------------------


class DeterministicFileAssembler:
    """Renders skeleton ``.py`` files from ``ForwardManifest.file_specs``.

    Parameters
    ----------
    module_inventory:
        Optional set/list of importable package names discovered during
        SCAFFOLD.  Used for import classification (local vs external).
    """

    def __init__(
        self,
        module_inventory: Optional[list[str]] = None,
        element_registry: Optional[Any] = None,
    ) -> None:
        self._module_inventory: set[str] = set(module_inventory or [])
        self._element_registry = element_registry

    # ── Public API ────────────────────────────────────────────────────────

    def render_specs(self, manifest: ForwardManifest) -> RenderResult:
        """Pure computation: render all file_specs, validate via ``ast.parse``.

        Returns a ``RenderResult`` with validated source texts, render failures,
        and compact metadata entries.
        """
        from startd8.contractors.context_schema import FileStubResult

        specs: Dict[str, str] = {}
        failures: list[FileStubResult] = []
        metadata: List[StubManifestEntry] = []

        if not manifest.file_specs:
            return RenderResult(specs=specs, failures=failures, metadata=metadata)

        # Deterministic ordering: sort by file path
        for file_path in sorted(manifest.file_specs.keys()):
            file_spec = manifest.file_specs[file_path]

            # Skip non-Python files — render_file() produces Python skeletons
            # and ast.parse() only validates Python.  Non-Python targets
            # (Dockerfiles, HTML, YAML, etc.) are handled by direct-copy in
            # the integration engine.
            lang = getattr(file_spec, "language", None)
            if lang and lang != "python":
                logger.debug(
                    "Skipping non-Python file %s (language=%s)", file_path, lang,
                )
                continue
            if not file_path.endswith(".py"):
                logger.debug(
                    "Skipping non-Python file %s (extension check)", file_path,
                )
                continue

            try:
                source = self.render_file(file_spec)
                # Validate via ast.parse
                ast.parse(source, filename=file_path)
                specs[file_path] = source
                metadata.append(
                    StubManifestEntry(
                        file_path=file_path,
                        sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
                        elements_count=len(file_spec.elements),
                        imports_count=len(file_spec.imports),
                        validated=True,
                    )
                )
            except Exception as exc:
                logger.warning(
                    "Render failure for %s: %s", file_path, exc,
                    exc_info=True,
                )
                failures.append(
                    FileStubResult(
                        file_path=file_path,
                        elements_count=len(file_spec.elements),
                        imports_count=len(file_spec.imports),
                        status="syntax_error",
                        phase="render",
                        error=str(exc),
                    )
                )

        return RenderResult(specs=specs, failures=failures, metadata=metadata)

    def materialize(
        self,
        specs: Dict[str, str],
        project_root: Path,
        dry_run: bool = False,
    ) -> list[FileStubResult]:
        """Write validated specs to disk.  Skip existing files.

        All paths are validated via ``sanitize_path`` before write.
        All writes use ``atomic_write`` for crash safety.

        Returns a list of ``FileStubResult`` instances (all phase="materialize").
        """
        from startd8.contractors.context_schema import FileStubResult
        from startd8.security import sanitize_path
        from startd8.utils.file_operations import atomic_write

        def _result(
            fp: str, status: str, error: Optional[str] = None,
        ) -> FileStubResult:
            return FileStubResult(
                file_path=fp,
                elements_count=0,
                imports_count=0,
                status=status,
                phase="materialize",
                error=error,
            )

        results: list[FileStubResult] = []
        project_root = Path(project_root).resolve()

        for file_path in sorted(specs.keys()):
            source = specs[file_path]
            try:
                safe_path = sanitize_path(file_path, base_dir=project_root)
            except Exception as exc:
                logger.warning(
                    "Path safety rejection for %s: %s", file_path, exc,
                    exc_info=True,
                )
                results.append(_result(
                    file_path, "syntax_error",
                    error=f"Path safety: {exc}",
                ))
                continue

            if safe_path.exists():
                status = "would_skip_exists" if dry_run else "skipped_exists"
                results.append(_result(file_path, status))
                continue

            if dry_run:
                results.append(_result(file_path, "would_create"))
                continue

            # Ensure __init__.py chain for intermediate packages
            init_results = self._ensure_init_chain(
                safe_path, project_root, dry_run=False,
            )
            results.extend(init_results)

            try:
                safe_path.parent.mkdir(parents=True, exist_ok=True)
                content_bytes = source.encode("utf-8")
                atomic_write(safe_path, content_bytes)
                results.append(_result(file_path, "created"))
            except Exception as exc:
                logger.warning(
                    "Materialize write failure for %s: %s", file_path, exc,
                    exc_info=True,
                )
                results.append(_result(
                    file_path, "syntax_error",
                    error=f"Write error: {exc}",
                ))

        return results

    # ── File rendering ────────────────────────────────────────────────────

    def render_file(self, file_spec: ForwardFileSpec) -> str:
        """Render a single ``ForwardFileSpec`` into Python source text."""
        lines: list[str] = []

        # 1. Sentinel
        lines.append(SKELETON_SENTINEL)

        # 2. from __future__ import annotations
        lines.append("")
        lines.append("from __future__ import annotations")

        # 3. Imports — completed with the typing names the signatures reference (see
        # _complete_typing_imports): a skeleton declaring `-> List[Dict]` must import List/Dict,
        # else the file fails type-check AND breaks FastAPI/SQLModel at runtime (they evaluate
        # annotations via get_type_hints despite `from __future__ import annotations`).
        import_block = self._render_imports(
            self._complete_typing_imports(file_spec), file_spec.dependencies
        )
        if import_block:
            lines.append("")
            lines.append(import_block)

        # 4. Validate identifiers
        self._validate_identifiers(file_spec.elements)

        # 5. Check for duplicate public symbols
        self._check_duplicate_symbols(file_spec.elements)

        # 6. Group elements: separate classes from top-level, attach methods
        class_groups, top_level = self._group_elements(file_spec.elements)

        # 7. Render top-level elements and class groups (PEP 8: 2 blank lines between top-level defs)
        for item in self._ordered_render_items(class_groups, top_level, file_spec.elements):
            lines.append("")
            lines.append("")
            if isinstance(item, tuple):
                class_elem, methods = item
                lines.append(self._render_class(class_elem, methods))
            else:
                lines.append(self._render_element(item, indent=""))

        # 8. __all__
        all_list = self._build_all_list(file_spec.elements)
        if all_list:
            lines.append("")
            lines.append("")
            items = ", ".join(f'"{name}"' for name in all_list)
            lines.append(f"__all__ = [{items}]")

        # Trailing newline
        lines.append("")
        return "\n".join(lines)

    # ── Import rendering ──────────────────────────────────────────────────

    def _typing_names_in_signatures(self, elements: list) -> Set[str]:
        """Collect ``typing`` names referenced in element annotations (params/return/assign).

        Conservative: only matches identifiers in the known ``typing`` export set, so a local
        class is never mistaken for ``typing.List``. Subscripts/qualified names are ignored
        (``app.tables.Job`` won't match; ``List`` and ``Dict`` in ``List[Dict]`` will).
        """
        names: Set[str] = set()
        for elem in elements:
            anns: list[str] = []
            sig = getattr(elem, "signature", None)
            if sig is not None:
                for p in getattr(sig, "params", []) or []:
                    if getattr(p, "annotation", None):
                        anns.append(str(p.annotation))
                if getattr(sig, "return_annotation", None):
                    anns.append(str(sig.return_annotation))
            if getattr(elem, "type_annotation", None):
                anns.append(str(elem.type_annotation))
            for ann in anns:
                for tok in _IDENT_RE.findall(ann):
                    if tok in _TYPING_EXPORTS:
                        names.add(tok)
        return names

    def _complete_typing_imports(self, file_spec: "ForwardFileSpec") -> list:
        """Return ``file_spec.imports`` with the ``typing`` import completed from signatures.

        Merges any existing ``from typing import …`` with the names the signatures use, so the
        rendered skeleton is self-consistent (no undefined ``Dict``/``List``). Non-typing imports
        are preserved verbatim and ordering is otherwise unchanged. Never mutates the frozen spec.
        """
        used = self._typing_names_in_signatures(file_spec.elements)
        if not used:
            return list(file_spec.imports)

        # Never shadow a name already imported from another module: a domain `Match` from
        # `app.tables` must NOT become `from typing import Match`. Only complete the genuinely
        # missing typing names.
        imported_elsewhere: Set[str] = set()
        for imp in file_spec.imports:
            if not (getattr(imp, "kind", None) == "from" and getattr(imp, "module", None) == "typing"):
                imported_elsewhere.update(getattr(imp, "names", None) or [])
        used = used - imported_elsewhere
        if not used:
            return list(file_spec.imports)

        from startd8.forward_manifest import ForwardImportSpec

        out: list = []
        existing: Set[str] = set()
        for imp in file_spec.imports:
            if getattr(imp, "kind", None) == "from" and getattr(imp, "module", None) == "typing":
                existing.update(imp.names or [])
                continue  # collapse all typing-from imports into one merged spec below
            out.append(imp)
        out.append(ForwardImportSpec(kind="from", module="typing", names=sorted(existing | used)))
        return out

    def _render_imports(
        self,
        imports: list[ForwardImportSpec],
        dependencies: Optional[ForwardDependencies],
    ) -> str:
        """Render imports in 6-tier precedence order.

        Tier ordering:
        1. ``__future__`` (skipped — always emitted by ``render_file``)
        2. Explicit stdlib (from ``ForwardDependencies.stdlib``)
        3. Explicit external (from ``ForwardDependencies.external``)
        4. ``_STDLIB_MODULES`` table (``sys.stdlib_module_names``)
        5. ``module_inventory`` (project-local packages from SCAFFOLD)
        6. External fallback (anything not matched above)
        """
        # Classify each import
        future: list[str] = []
        stdlib: list[str] = []
        external: list[str] = []
        local: list[str] = []

        # Collect explicit stdlib/external from ForwardDependencies
        explicit_stdlib: Set[str] = set()
        explicit_external: Set[str] = set()
        if dependencies is not None:
            explicit_stdlib = set(getattr(dependencies, "stdlib", []))
            explicit_external = set(getattr(dependencies, "external", []))

        for imp in imports:
            rendered = self._render_single_import(imp)
            if not rendered:
                continue
            module_root = imp.module.split(".")[0]

            if module_root == "__future__":
                # Skip — we always emit from __future__ import annotations
                continue
            elif module_root in explicit_stdlib:
                stdlib.append(rendered)
            elif module_root in explicit_external:
                external.append(rendered)
            elif module_root in _STDLIB_MODULES:
                stdlib.append(rendered)
            elif module_root in self._module_inventory:
                local.append(rendered)
            else:
                external.append(rendered)

        # Build sections with blank-line separators
        sections: list[str] = []
        for group in [future, stdlib, external, local]:
            if group:
                sections.append("\n".join(sorted(group)))

        return "\n\n".join(sections)

    def _render_single_import(self, imp: ForwardImportSpec) -> Optional[str]:
        """Render a single ForwardImportSpec to a source line.

        Returns ``None`` for malformed imports (e.g. ``from X import``
        with no names), which the caller skips.
        """
        if imp.kind == "from":
            if not imp.names:
                return None
            line = f"from {imp.module} import {', '.join(imp.names)}"
        else:
            line = f"import {imp.module}"
            if imp.alias:
                line += f" as {imp.alias}"
        return line

    # ── Element rendering ─────────────────────────────────────────────────

    def _render_element(self, elem: ForwardElementSpec, indent: str) -> str:
        """Render a single element (function, constant, etc.)."""
        lines: list[str] = []
        kind = elem.kind

        if kind in (ElementKind.CONSTANT, ElementKind.VARIABLE, ElementKind.TYPE_ALIAS):
            return self._render_constant(elem, indent)

        # Decorators
        for dec in elem.decorators:
            lines.append(f"{indent}@{dec}")

        # def / async def
        is_async = kind in (ElementKind.ASYNC_FUNCTION, ElementKind.ASYNC_METHOD)
        is_property = kind == ElementKind.PROPERTY
        prefix = "async def" if is_async else "def"

        if is_property and "property" not in elem.decorators:
            lines.append(f"{indent}@property")

        sig_str = self._render_signature(elem.signature) if elem.signature else "()"
        ret = ""
        if elem.signature and elem.signature.return_annotation:
            ret = f" -> {elem.signature.return_annotation}"

        lines.append(f"{indent}{prefix} {elem.name}{sig_str}{ret}:")

        # Docstring
        body_indent = indent + "    "
        if elem.docstring_hint:
            lines.append(f'{body_indent}"""')
            for doc_line in elem.docstring_hint.split("\n"):
                lines.append(f"{body_indent}{doc_line}")
            lines.append(f'{body_indent}"""')

        # Body — check element registry for pre-existing validated code (REQ-MP-1106)
        element_id = getattr(elem, "source_contract_id", None)
        registry_code = self._lookup_registry_code(elem)
        if registry_code is not None and element_id:
            lines.append(f"{body_indent}# [ELEMENT-REGISTRY: {element_id}]")
            for code_line in registry_code.splitlines():
                lines.append(f"{body_indent}{code_line}")
        else:
            lines.append(f"{body_indent}raise NotImplementedError")

        return "\n".join(lines)

    def _lookup_registry_code(self, elem: ForwardElementSpec) -> Optional[str]:
        """Look up pre-existing validated code from the element registry (REQ-MP-1106).

        Returns the code body (without leading indent) if found, non-empty,
        and passing ``ast.parse()`` validation in a synthetic function context.
        Returns ``None`` to fall back to the ``raise NotImplementedError`` stub.

        Non-fatal: registry errors log a warning and fall back to stub.
        """
        if self._element_registry is None:
            return None
        element_id = getattr(elem, "source_contract_id", None)
        if not element_id:
            return None
        try:
            entry = self._element_registry.get(element_id)
            if entry is not None:
                code = entry.extra.get("code")
                if code and isinstance(code, str):
                    # Validate cached code parses in a function context
                    if not self._validate_registry_code(code, element_id):
                        logger.warning(
                            "SCAFFOLD registry code for %s (%s) failed "
                            "ast.parse validation; falling back to stub",
                            elem.name, element_id,
                        )
                        return None
                    logger.debug(
                        "SCAFFOLD registry pre-fill for %s (%s)",
                        elem.name, element_id,
                    )
                    return code
        except Exception as exc:
            logger.warning(
                "SCAFFOLD registry lookup failed for %s: %s", element_id, exc,
            )
        return None

    @staticmethod
    def _validate_registry_code(code: str, element_id: str) -> bool:
        """Validate that cached code is syntactically valid Python.

        Wraps the code in a synthetic function body and runs ``ast.parse()``.
        Returns ``True`` if valid, ``False`` otherwise.
        """
        # Indent the code as if it were inside a function body
        indented = "\n".join(f"    {line}" for line in code.splitlines())
        wrapper = f"def _validate_wrapper_():\n{indented}\n"
        try:
            ast.parse(wrapper)
            return True
        except SyntaxError:
            return False

    def _render_constant(self, elem: ForwardElementSpec, indent: str) -> str:
        """Render a constant/variable/type_alias stub."""
        annotation = ""
        if elem.signature and elem.signature.return_annotation:
            annotation = f": {elem.signature.return_annotation}"
        elif getattr(elem, "type_annotation", None):
            annotation = f": {elem.type_annotation}"

        # Use value_repr if available, otherwise ... as placeholder
        value = getattr(elem, "value_repr", None) or "..."
        return f"{indent}{elem.name}{annotation} = {value}"

    def _render_signature(self, sig: Signature) -> str:
        """Render a Signature model to a parameter string."""
        parts: list[str] = []
        saw_positional_only = False
        saw_keyword_only = False

        for param in sig.params:
            rendered = param.name
            if param.annotation:
                rendered += f": {param.annotation}"
            if param.default is not None:
                rendered += f" = {param.default}"

            if param.kind == ParamKind.POSITIONAL_ONLY:
                saw_positional_only = True
                parts.append(rendered)
            elif param.kind == ParamKind.VAR_POSITIONAL:
                if saw_positional_only:
                    parts.append("/")
                    saw_positional_only = False
                parts.append(f"*{rendered}")
                saw_keyword_only = True
            elif param.kind == ParamKind.KEYWORD_ONLY:
                if saw_positional_only:
                    parts.append("/")
                    saw_positional_only = False
                if not saw_keyword_only:
                    parts.append("*")
                    saw_keyword_only = True
                parts.append(rendered)
            elif param.kind == ParamKind.VAR_KEYWORD:
                if saw_positional_only:
                    parts.append("/")
                    saw_positional_only = False
                parts.append(f"**{rendered}")
            else:
                # POSITIONAL or KEYWORD
                if saw_positional_only:
                    parts.append("/")
                    saw_positional_only = False
                parts.append(rendered)

        if saw_positional_only:
            parts.append("/")

        return f"({', '.join(parts)})"

    # ── Class rendering ───────────────────────────────────────────────────

    def _render_class(
        self, class_elem: ForwardElementSpec, methods: list[ForwardElementSpec],
    ) -> str:
        """Render a class with its nested methods."""
        lines: list[str] = []

        # Decorators
        for dec in class_elem.decorators:
            lines.append(f"@{dec}")

        # Class definition
        bases = ", ".join(class_elem.bases) if class_elem.bases else ""
        if bases:
            lines.append(f"class {class_elem.name}({bases}):")
        else:
            lines.append(f"class {class_elem.name}:")

        indent = "    "

        # Class docstring
        if class_elem.docstring_hint:
            lines.append(f'{indent}"""')
            for doc_line in class_elem.docstring_hint.split("\n"):
                lines.append(f"{indent}{doc_line}")
            lines.append(f'{indent}"""')

        if not methods:
            lines.append(f"{indent}pass")
            return "\n".join(lines)

        # Sort methods: __init__ first, then manifest order
        ordered = self._order_methods(methods)

        first_method = True
        for method in ordered:
            if not first_method:
                lines.append("")  # 1 blank line between methods
            lines.append(self._render_element(method, indent=indent))
            first_method = False

        return "\n".join(lines)

    def _order_methods(self, methods: list) -> list:
        """Order methods: __init__ hoisted first, rest in manifest order."""
        init_methods = [m for m in methods if m.name == "__init__"]
        other_methods = [m for m in methods if m.name != "__init__"]
        return init_methods + other_methods

    # ── Grouping & ordering ───────────────────────────────────────────────

    def _group_elements(
        self, elements: list[ForwardElementSpec],
    ) -> tuple[dict[str, list[ForwardElementSpec]], list[ForwardElementSpec]]:
        """Group elements by parent_class.

        Returns (class_methods, top_level):
        - class_methods: {class_name: [method_elements]}
        - top_level: elements without parent_class and not CLASS kind with
          methods (those become class groups)
        """
        class_methods: dict[str, list] = {}
        top_level: list = []
        class_names: set[str] = set()

        # First pass: identify classes
        for elem in elements:
            if elem.kind == ElementKind.CLASS:
                class_names.add(elem.name)

        # Second pass: group methods, collect top-level
        for elem in elements:
            parent = getattr(elem, "parent_class", None)
            if parent:
                class_methods.setdefault(parent, []).append(elem)
            elif elem.kind != ElementKind.CLASS:
                top_level.append(elem)

        return class_methods, top_level

    def _ordered_render_items(
        self,
        class_groups: dict[str, list[ForwardElementSpec]],
        top_level: list[ForwardElementSpec],
        elements: list[ForwardElementSpec],
    ) -> list:
        """Produce a deterministic render order.

        Sort by: (is_class desc, name asc) for top-level grouping.
        Classes include their methods; orphan methods (parent_class set
        but no matching CLASS element) get a synthetic class wrapper.
        """
        from startd8.forward_manifest import ForwardElementSpec as _FES

        rendered_classes: set[str] = set()
        class_elems: dict[str, ForwardElementSpec] = {}
        for elem in elements:
            if elem.kind == ElementKind.CLASS:
                class_elems[elem.name] = elem

        # (sort_key, name, render_item)
        all_items: list[tuple[int, str, Any]] = []

        for elem in elements:
            if elem.kind == ElementKind.CLASS and elem.name not in rendered_classes:
                rendered_classes.add(elem.name)
                methods = class_groups.get(elem.name, [])
                all_items.append((0, elem.name, (elem, methods)))
            elif getattr(elem, "parent_class", None) is None and elem.kind != ElementKind.CLASS:
                all_items.append((1, elem.name, elem))

        # Orphan methods — parent_class doesn't match any CLASS element
        for parent_name, methods in sorted(class_groups.items()):
            if parent_name not in class_elems and parent_name not in rendered_classes:
                rendered_classes.add(parent_name)
                synthetic_class = _FES(kind=ElementKind.CLASS, name=parent_name)
                all_items.append((0, parent_name, (synthetic_class, methods)))

        all_items.sort(key=lambda x: (x[0], x[1]))
        return [item[2] for item in all_items]

    # ── __all__ list ──────────────────────────────────────────────────────

    def _build_all_list(self, elements: list[ForwardElementSpec]) -> list[str]:
        """Build __all__ from public, top-level symbols only."""
        names: list[str] = []
        method_kinds = {ElementKind.METHOD, ElementKind.ASYNC_METHOD, ElementKind.PROPERTY}

        for elem in elements:
            if elem.visibility != Visibility.PUBLIC:
                continue
            if elem.kind in method_kinds:
                continue
            if getattr(elem, "parent_class", None) is not None:
                continue
            names.append(elem.name)

        return sorted(names)

    # ── Validation helpers ────────────────────────────────────────────────

    def _validate_identifiers(self, elements: list[ForwardElementSpec]) -> None:
        """Fail fast on invalid Python identifiers."""
        for elem in elements:
            name = elem.name
            if not name.isidentifier():
                raise ValueError(
                    f"Invalid Python identifier: {name!r} "
                    f"(element kind={elem.kind.value})"
                )
            if keyword.iskeyword(name):
                raise ValueError(
                    f"Python keyword cannot be used as identifier: {name!r} "
                    f"(element kind={elem.kind.value})"
                )

    def _check_duplicate_symbols(self, elements: list[ForwardElementSpec]) -> None:
        """Hard error on duplicate public top-level symbols; warn on private."""
        seen_public: dict[str, int] = {}
        seen_private: dict[str, int] = {}
        method_kinds = {ElementKind.METHOD, ElementKind.ASYNC_METHOD, ElementKind.PROPERTY}

        for elem in elements:
            if elem.kind in method_kinds or getattr(elem, "parent_class", None):
                continue

            name = elem.name
            if elem.visibility == Visibility.PUBLIC:
                if name in seen_public:
                    raise ValueError(
                        f"Duplicate public top-level symbol: {name!r} — "
                        f"contract defect in ForwardManifest"
                    )
                seen_public[name] = 1
            else:
                if name in seen_private:
                    logger.warning(
                        "Duplicate private top-level symbol %r — keeping first",
                        name,
                    )
                seen_private[name] = 1

    # ── __init__.py chain ─────────────────────────────────────────────────

    def _ensure_init_chain(
        self,
        target_path: Path,
        project_root: Path,
        dry_run: bool,
    ) -> list[FileStubResult]:
        """Create missing ``__init__.py`` files for intermediate packages."""
        from startd8.contractors.context_schema import FileStubResult
        from startd8.utils.file_operations import atomic_write

        results: list[FileStubResult] = []
        try:
            rel = target_path.relative_to(project_root)
        except ValueError:
            return results

        # Walk parent directories from project_root down to target's parent
        parts = list(rel.parent.parts)
        current = project_root
        for part in parts:
            current = current / part
            init_path = current / "__init__.py"
            if not init_path.exists():
                rel_path = str(init_path.relative_to(project_root))
                if dry_run:
                    results.append(
                        FileStubResult(
                            file_path=rel_path,
                            elements_count=0,
                            imports_count=0,
                            status="would_create",
                            phase="materialize",
                        )
                    )
                else:
                    try:
                        init_path.parent.mkdir(parents=True, exist_ok=True)
                        atomic_write(init_path, b"")
                        results.append(
                            FileStubResult(
                                file_path=rel_path,
                                elements_count=0,
                                imports_count=0,
                                status="created",
                                phase="materialize",
                            )
                        )
                    except Exception as exc:
                        logger.warning(
                            "Failed to create __init__.py at %s: %s",
                            init_path, exc, exc_info=True,
                        )
                        results.append(
                            FileStubResult(
                                file_path=rel_path,
                                elements_count=0,
                                imports_count=0,
                                status="syntax_error",
                                phase="materialize",
                                error=f"__init__.py write error: {exc}",
                            )
                        )
        return results


__all__ = [
    "SKELETON_SENTINEL",
    "StubManifestEntry",
    "RenderResult",
    "DeterministicFileAssembler",
]
