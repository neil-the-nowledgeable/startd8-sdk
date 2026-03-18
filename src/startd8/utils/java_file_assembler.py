"""Java Deterministic File Assembler (DFA).

Generates `.java` skeleton files from ``ForwardFileSpec`` entries in a
``ForwardManifest``.  Parallel to the Python ``DeterministicFileAssembler``
but exploits Java's rigid structure (one public class per file, mandatory
packages, fully typed signatures) for higher-fidelity skeletons.

Skeleton marker: ``// [STARTD8-SKELETON]``
Stub body: ``throw new UnsupportedOperationException("TODO");``
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional

from startd8.logging_config import get_logger

logger = get_logger(__name__)

JAVA_SKELETON_SENTINEL = "// [STARTD8-SKELETON]"
JAVA_STUB_BODY = 'throw new UnsupportedOperationException("TODO");'


def _derive_package(file_path: str) -> Optional[str]:
    """Derive Java package from file path.

    Strips ``src/main/java/`` or ``src/test/java/`` prefix, converts
    remaining directory path to dot-separated package name.
    """
    p = PurePosixPath(file_path)
    parts = list(p.parts)

    # Find src/main/java or src/test/java prefix
    for prefix in (
        ("src", "main", "java"),
        ("src", "test", "java"),
    ):
        plen = len(prefix)
        for i in range(len(parts) - plen):
            if tuple(parts[i : i + plen]) == prefix:
                # Package is everything between the prefix and the filename
                pkg_parts = parts[i + plen : -1]  # exclude filename
                if pkg_parts:
                    return ".".join(pkg_parts)
                return None

    # Non-standard layout: use directory path minus filename
    dir_parts = parts[:-1]
    if dir_parts:
        # Filter out common non-package directories
        skip = {"src", "main", "java", "test", "resources"}
        pkg = [part for part in dir_parts if part not in skip]
        if pkg:
            return ".".join(pkg)
    return None


def _derive_class_name(file_path: str) -> str:
    """Derive class name from file path (filename stem)."""
    return PurePosixPath(file_path).stem


def _render_imports(imports: List[str]) -> str:
    """Render import statements with 2-tier grouping.

    Tier 1: ``java.*`` / ``javax.*`` (standard library)
    Tier 2: Everything else (third-party / project imports)
    Separated by a blank line.
    """
    if not imports:
        return ""

    stdlib: list[str] = []
    other: list[str] = []
    seen: set[str] = set()

    for imp in imports:
        imp = imp.strip()
        if not imp:
            continue
        # Normalize: ensure it starts with "import "
        if not imp.startswith("import "):
            imp = f"import {imp};"
        if not imp.endswith(";"):
            imp = f"{imp};"
        if imp in seen:
            continue
        seen.add(imp)

        if any(imp.startswith(f"import {prefix}") for prefix in ("java.", "javax.")):
            stdlib.append(imp)
        else:
            other.append(imp)

    sections: list[str] = []
    if stdlib:
        sections.append("\n".join(sorted(stdlib)))
    if other:
        sections.append("\n".join(sorted(other)))

    return "\n\n".join(sections)


def _render_method_stub(
    name: str,
    return_type: str = "void",
    params: str = "",
    modifiers: str = "public",
    annotations: Optional[List[str]] = None,
    is_abstract: bool = False,
    indent: str = "    ",
) -> str:
    """Render a method stub with ``throw new UnsupportedOperationException``.

    Abstract methods get no body (just a semicolon).
    """
    lines: list[str] = []
    if annotations:
        for ann in annotations:
            if not ann.startswith("@"):
                ann = f"@{ann}"
            lines.append(f"{indent}{ann}")

    sig = f"{indent}{modifiers} {return_type} {name}({params})"

    if is_abstract:
        lines.append(f"{sig};")
    else:
        lines.append(f"{sig} {{")
        lines.append(f"{indent}    {JAVA_STUB_BODY}")
        lines.append(f"{indent}}}")

    return "\n".join(lines)


def _render_constructor_stub(
    class_name: str,
    params: str = "",
    modifiers: str = "public",
    indent: str = "    ",
) -> str:
    """Render a constructor stub."""
    lines = [
        f"{indent}{modifiers} {class_name}({params}) {{",
        f"{indent}    {JAVA_STUB_BODY}",
        f"{indent}}}",
    ]
    return "\n".join(lines)


def _render_field(
    name: str,
    field_type: str,
    modifiers: str = "private",
    annotations: Optional[List[str]] = None,
    indent: str = "    ",
) -> str:
    """Render a field declaration."""
    lines: list[str] = []
    if annotations:
        for ann in annotations:
            if not ann.startswith("@"):
                ann = f"@{ann}"
            lines.append(f"{indent}{ann}")
    lines.append(f"{indent}{modifiers} {field_type} {name};")
    return "\n".join(lines)


class JavaDeterministicFileAssembler:
    """Assembles Java skeleton files from ForwardManifest entries.

    Each rendered file contains:
    - Package declaration (derived from path)
    - Import block (2-tier: stdlib, then third-party)
    - Class/interface/enum with stub method bodies
    - ``// [STARTD8-SKELETON]`` marker
    """

    def render_specs(
        self,
        manifest: Any,
        output_dir: Optional[Path] = None,
    ) -> Dict[str, str]:
        """Render all .java files from a ForwardManifest.

        Args:
            manifest: ForwardManifest instance.
            output_dir: If provided, write files to disk.

        Returns:
            Dict mapping file paths to rendered content.
        """
        results: Dict[str, str] = {}
        for file_spec in manifest.files:
            if not file_spec.file.endswith(".java"):
                continue
            content = self.render_file(file_spec)
            if content:
                results[file_spec.file] = content
                if output_dir:
                    out_path = output_dir / file_spec.file
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(content, encoding="utf-8")
        return results

    def render_file(self, file_spec: Any) -> Optional[str]:
        """Render a single Java file from a ForwardFileSpec.

        Args:
            file_spec: ForwardFileSpec instance.

        Returns:
            Rendered Java source, or None if the file has no elements.
        """
        file_path = file_spec.file
        if not file_path.endswith(".java"):
            return None

        sections: list[str] = []

        # Skeleton marker
        sections.append(JAVA_SKELETON_SENTINEL)

        # Package declaration
        package = _derive_package(file_path)
        if package:
            sections.append(f"package {package};")

        # Imports
        import_strs: list[str] = []
        for imp in getattr(file_spec, "imports", []):
            if hasattr(imp, "names") and hasattr(imp, "module"):
                # ForwardImportSpec style
                if imp.module:
                    for name in imp.names:
                        import_strs.append(f"import {imp.module}.{name};")
            elif isinstance(imp, str):
                import_strs.append(imp)
        import_block = _render_imports(import_strs)
        if import_block:
            sections.append(import_block)

        # Derive class name
        class_name = _derive_class_name(file_path)

        # Group elements by parent
        elements = getattr(file_spec, "elements", [])
        type_elements = [e for e in elements if _is_type_element(e)]
        member_elements = [e for e in elements if not _is_type_element(e)]

        if not type_elements:
            # Default: create a public class with the file's class name
            class_body = self._render_members(member_elements, class_name)
            sections.append(f"public class {class_name} {{\n{class_body}\n}}")
        else:
            for te in type_elements:
                kind = _element_kind_to_java(te)
                name = te.name
                modifiers = "public"

                extends_str = ""
                if hasattr(te, "bases") and te.bases:
                    # First base is extends, rest are implements
                    extends_str = f" extends {te.bases[0]}"

                implements_str = ""
                if hasattr(te, "bases") and len(te.bases) > 1:
                    implements_str = f" implements {', '.join(te.bases[1:])}"

                # Annotations
                ann_lines = ""
                if hasattr(te, "decorators") and te.decorators:
                    ann_lines = "\n".join(
                        f"@{d}" if not d.startswith("@") else d
                        for d in te.decorators
                    ) + "\n"

                # Collect members belonging to this type
                members = [
                    e for e in member_elements
                    if getattr(e, "parent_class", None) == name
                ]
                body = self._render_members(members, name)

                if kind == "interface":
                    sections.append(
                        f"{ann_lines}{modifiers} {kind} {name}{extends_str} {{\n{body}\n}}"
                    )
                else:
                    sections.append(
                        f"{ann_lines}{modifiers} {kind} {name}{extends_str}{implements_str} {{\n{body}\n}}"
                    )

        content = "\n\n".join(sections) + "\n"

        # Validate via javalang if available
        content = self._validate_output(content, file_path)

        return content

    def _render_members(self, elements: list, class_name: str) -> str:
        """Render class members (fields, constructors, methods)."""
        lines: list[str] = []

        for elem in elements:
            kind = getattr(elem, "kind", None)
            kind_val = kind.value if hasattr(kind, "value") else str(kind)
            name = elem.name

            if kind_val in ("constant", "variable", "field"):
                ret_type = "Object"
                if hasattr(elem, "signature") and elem.signature:
                    ret_ann = getattr(elem.signature, "return_annotation", None)
                    if ret_ann:
                        ret_type = _python_type_to_java(ret_ann)
                modifiers = "private"
                if kind_val == "constant":
                    modifiers = "private static final"
                lines.append(_render_field(name, ret_type, modifiers=modifiers))
                lines.append("")

            elif name == class_name or kind_val == "constructor":
                # Constructor
                params = _render_java_params(elem)
                lines.append(_render_constructor_stub(class_name, params=params))
                lines.append("")

            elif kind_val in ("method", "async_method", "function", "async_function", "property"):
                ret_type = "void"
                if hasattr(elem, "signature") and elem.signature:
                    ret_ann = getattr(elem.signature, "return_annotation", None)
                    if ret_ann and ret_ann != "None":
                        ret_type = _python_type_to_java(ret_ann)
                params = _render_java_params(elem)
                modifiers = "public"
                annotations = None
                if hasattr(elem, "decorators") and elem.decorators:
                    annotations = [
                        d for d in elem.decorators
                        if d and (d.startswith("@") or d[0].isupper())
                    ]
                is_abstract = kind_val == "property"  # properties → abstract getters
                lines.append(_render_method_stub(
                    name, ret_type, params,
                    modifiers=modifiers,
                    annotations=annotations,
                    is_abstract=is_abstract,
                ))
                lines.append("")

        return "\n".join(lines).rstrip()

    def _validate_output(self, content: str, file_path: str) -> str:
        """Validate rendered output via javalang; return content unchanged on failure."""
        try:
            import javalang
            javalang.parse.parse(content)
        except ImportError:
            pass
        except Exception as exc:
            logger.warning(
                "Java DFA output validation failed for %s: %s", file_path, exc,
            )
        return content


def _is_type_element(elem: Any) -> bool:
    """Check if an element represents a type declaration."""
    kind = getattr(elem, "kind", None)
    kind_val = kind.value if hasattr(kind, "value") else str(kind)
    return kind_val == "class"


def _element_kind_to_java(elem: Any) -> str:
    """Map element metadata to Java type keyword.

    Checks decorators for interface hints; defaults to class.
    """
    if hasattr(elem, "decorators") and elem.decorators:
        for d in elem.decorators:
            if d and "interface" in d.lower():
                return "interface"
    return "class"


def _python_type_to_java(type_str: str) -> str:
    """Best-effort Python type → Java type conversion."""
    mapping = {
        "str": "String",
        "int": "int",
        "float": "double",
        "bool": "boolean",
        "None": "void",
        "bytes": "byte[]",
        "list": "List<Object>",
        "dict": "Map<String, Object>",
        "set": "Set<Object>",
        "tuple": "Object[]",
        "Any": "Object",
        "Optional": "Object",
    }
    # Handle Optional[X]
    if type_str.startswith("Optional["):
        inner = type_str[len("Optional["):-1]
        return _python_type_to_java(inner)
    # Handle List[X]
    if type_str.startswith(("List[", "list[")):
        inner = type_str[type_str.index("[") + 1:-1]
        return f"List<{_python_type_to_java(inner)}>"
    # Handle Dict[K, V]
    if type_str.startswith(("Dict[", "dict[")):
        inner = type_str[type_str.index("[") + 1:-1]
        parts = inner.split(",", 1)
        if len(parts) == 2:
            k = _python_type_to_java(parts[0].strip())
            v = _python_type_to_java(parts[1].strip())
            return f"Map<{k}, {v}>"
    return mapping.get(type_str, type_str)


def _render_java_params(elem: Any) -> str:
    """Render Java-style parameter list from a ForwardElementSpec."""
    if not hasattr(elem, "signature") or not elem.signature:
        return ""
    params: list[str] = []
    for p in elem.signature.params:
        if p.name in ("self", "cls"):
            continue
        java_type = _python_type_to_java(p.annotation) if p.annotation else "Object"
        params.append(f"{java_type} {p.name}")
    return ", ".join(params)
