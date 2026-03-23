"""Node.js Deterministic File Assembler (DFA).

Generates ``.js`` and ``.ts`` skeleton files from ``ForwardFileSpec``
entries in a ``ForwardManifest``.  Supports both CommonJS and ESM
module formats based on file extension and hints in the file spec.

Skeleton marker: ``// [STARTD8-SKELETON]``
Stub body: ``throw new Error("not implemented");``
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional

from startd8.languages._validation_utils import (
    NODEJS_SKELETON_CONFIG,
    convert_python_type,
)
from startd8.logging_config import get_logger

logger = get_logger(__name__)

NODEJS_SKELETON_SENTINEL = "// [STARTD8-SKELETON]"
NODEJS_STUB_BODY = NODEJS_SKELETON_CONFIG.stub_body

_JS_EXTENSIONS = frozenset({".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"})


def _is_esm(file_path: str, file_spec: Any = None) -> bool:
    """Determine if a file should use ESM (import/export) or CJS (require/module.exports).

    ESM when: ``.mjs``, ``.ts``, ``.tsx``, or file_spec metadata hints ESM.
    CJS when: ``.cjs``.
    Default (``.js``): ESM (modern Node.js convention).
    """
    suffix = PurePosixPath(file_path).suffix.lower()
    if suffix in (".mjs", ".ts", ".tsx", ".jsx"):
        return True
    if suffix == ".cjs":
        return False
    # .js: check metadata for "type": "module" hint
    if file_spec and hasattr(file_spec, "metadata"):
        meta = file_spec.metadata if isinstance(file_spec.metadata, dict) else {}
        if meta.get("module_type") == "esm":
            return True
    # Default: ESM (modern)
    return True


def _derive_module_name(file_path: str) -> str:
    """Derive module/class name from file path."""
    return PurePosixPath(file_path).stem


def _render_imports(imports: List[str], esm: bool) -> str:
    """Render import statements in ESM or CJS format."""
    if not imports:
        return ""

    seen: set[str] = set()
    lines: list[str] = []

    for imp in imports:
        imp = imp.strip()
        if not imp or imp in seen:
            continue
        seen.add(imp)

        # If already a full statement, use as-is
        if imp.startswith("import ") or imp.startswith("const ") or imp.startswith("require("):
            lines.append(imp if imp.endswith(";") else f"{imp};")
            continue

        # Normalize: module path → import/require statement
        if esm:
            lines.append(f"import {{ /* TODO */ }} from '{imp}';")
        else:
            # CJS: derive variable name from last path segment
            var_name = imp.rsplit("/", 1)[-1].replace("-", "_").replace("@", "")
            lines.append(f"const {var_name} = require('{imp}');")

    return "\n".join(lines)


def _python_type_to_js(type_str: str) -> str:
    """Convert Python type annotation to JSDoc/TypeScript type."""
    return convert_python_type(type_str, NODEJS_SKELETON_CONFIG)


def _render_js_params(elem: Any) -> str:
    """Render JS parameter list from a ForwardElementSpec."""
    if not hasattr(elem, "signature") or not elem.signature:
        return ""
    params: list[str] = []
    for p in elem.signature.params:
        if p.name in ("self", "cls"):
            continue
        params.append(p.name)
    return ", ".join(params)


def _render_function_stub(
    name: str,
    params: str = "",
    is_async: bool = False,
    esm: bool = True,
    indent: str = "",
) -> str:
    """Render a function stub."""
    async_prefix = "async " if is_async else ""
    export_prefix = "export " if esm else ""
    lines = [
        f"{indent}{export_prefix}{async_prefix}function {name}({params}) {{",
        f"{indent}  {NODEJS_STUB_BODY}",
        f"{indent}}}",
    ]
    return "\n".join(lines)


def _render_method_stub(
    name: str,
    params: str = "",
    is_async: bool = False,
    indent: str = "  ",
) -> str:
    """Render a class method stub."""
    async_prefix = "async " if is_async else ""
    lines = [
        f"{indent}{async_prefix}{name}({params}) {{",
        f"{indent}  {NODEJS_STUB_BODY}",
        f"{indent}}}",
    ]
    return "\n".join(lines)


def _render_constructor_stub(
    params: str = "",
    indent: str = "  ",
) -> str:
    """Render a constructor stub."""
    lines = [
        f"{indent}constructor({params}) {{",
        f"{indent}  {NODEJS_STUB_BODY}",
        f"{indent}}}",
    ]
    return "\n".join(lines)


def _is_type_element(elem: Any) -> bool:
    """Check if an element represents a class declaration."""
    kind = getattr(elem, "kind", None)
    kind_val = kind.value if hasattr(kind, "value") else str(kind)
    return kind_val == "class"


class NodejsDeterministicFileAssembler:
    """Assembles Node.js/TypeScript skeleton files from ForwardManifest entries.

    Each rendered file contains:
    - ``// [STARTD8-SKELETON]`` marker
    - Import statements (ESM or CJS)
    - Class/function stubs with ``throw new Error("not implemented")`` bodies
    - Module exports (CJS) or export keywords (ESM)
    """

    def render_specs(
        self,
        manifest: Any,
        output_dir: Any = None,
    ) -> Dict[str, str]:
        """Render all JS/TS files from a ForwardManifest."""
        results: Dict[str, str] = {}
        for file_spec in manifest.files:
            suffix = PurePosixPath(file_spec.file).suffix.lower()
            if suffix not in _JS_EXTENSIONS:
                continue
            content = self.render_file(file_spec)
            if content:
                results[file_spec.file] = content
                if output_dir:
                    from pathlib import Path
                    out_path = Path(output_dir) / file_spec.file
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(content, encoding="utf-8")
        return results

    def render_file(self, file_spec: Any) -> Optional[str]:
        """Render a single JS/TS file from a ForwardFileSpec."""
        file_path = file_spec.file
        suffix = PurePosixPath(file_path).suffix.lower()
        if suffix not in _JS_EXTENSIONS:
            return None

        esm = _is_esm(file_path, file_spec)
        sections: list[str] = []

        # Skeleton marker
        sections.append(NODEJS_SKELETON_SENTINEL)

        # 'use strict' for CJS
        if not esm:
            sections.append("'use strict';")

        # Imports
        import_strs: list[str] = []
        for imp in getattr(file_spec, "imports", []):
            if hasattr(imp, "names") and hasattr(imp, "module"):
                if imp.module:
                    import_strs.append(imp.module)
            elif isinstance(imp, str):
                import_strs.append(imp)
        import_block = _render_imports(import_strs, esm)
        if import_block:
            sections.append(import_block)

        # Elements
        elements = getattr(file_spec, "elements", [])
        type_elements = [e for e in elements if _is_type_element(e)]
        member_elements = [e for e in elements if not _is_type_element(e)]

        if type_elements:
            for te in type_elements:
                name = te.name
                extends_str = ""
                if hasattr(te, "bases") and te.bases:
                    extends_str = f" extends {te.bases[0]}"

                members = [
                    e for e in member_elements
                    if getattr(e, "parent_class", None) == name
                ]

                export_kw = "export " if esm else ""
                class_lines = [f"{export_kw}class {name}{extends_str} {{"]
                class_lines.append(self._render_members(members, name))
                class_lines.append("}")
                sections.append("\n".join(class_lines))

                if not esm:
                    sections.append(f"module.exports = {{ {name} }};")
        else:
            # Standalone functions
            func_lines: list[str] = []
            export_names: list[str] = []
            for elem in member_elements:
                kind = getattr(elem, "kind", None)
                kind_val = kind.value if hasattr(kind, "value") else str(kind)
                name = elem.name
                params = _render_js_params(elem)
                is_async = kind_val.startswith("async") if kind_val else False

                func_lines.append(_render_function_stub(
                    name, params, is_async=is_async, esm=esm,
                ))
                func_lines.append("")
                if not esm:
                    export_names.append(name)

            if func_lines:
                sections.append("\n".join(func_lines).rstrip())
            if not esm and export_names:
                exports = ", ".join(export_names)
                sections.append(f"module.exports = {{ {exports} }};")

        content = "\n\n".join(sections) + "\n"
        return content

    def _render_members(self, elements: list, class_name: str) -> str:
        """Render class members (constructor, methods)."""
        lines: list[str] = []

        for elem in elements:
            kind = getattr(elem, "kind", None)
            kind_val = kind.value if hasattr(kind, "value") else str(kind)
            name = elem.name
            params = _render_js_params(elem)

            if name == class_name or kind_val == "constructor":
                lines.append(_render_constructor_stub(params=params))
                lines.append("")
            elif kind_val in ("method", "async_method", "function", "async_function"):
                is_async = kind_val.startswith("async") if kind_val else False
                lines.append(_render_method_stub(
                    name, params, is_async=is_async,
                ))
                lines.append("")

        return "\n".join(lines).rstrip()
