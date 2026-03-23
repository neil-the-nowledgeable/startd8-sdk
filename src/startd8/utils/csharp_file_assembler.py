"""C# Deterministic File Assembler (DFA).

Generates ``.cs`` skeleton files from ``ForwardFileSpec`` entries in a
``ForwardManifest``.  Parallel to the Java ``JavaDeterministicFileAssembler``
but uses C#-specific conventions: file-scoped namespaces, ``using`` directives,
``NotImplementedException`` stubs, and property syntax.

Skeleton marker: ``// [STARTD8-SKELETON]``
Stub body: ``throw new NotImplementedException();``
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional

from startd8.logging_config import get_logger

logger = get_logger(__name__)

CSHARP_SKELETON_SENTINEL = "// [STARTD8-SKELETON]"
CSHARP_STUB_BODY = "throw new NotImplementedException();"

# Prefixes for system/framework usings (tier 1).
# Everything else is tier 2 (third-party / project).
_STDLIB_PREFIXES = ("System", "Microsoft")


def _derive_namespace(file_path: str) -> Optional[str]:
    """Derive C# namespace from file path.

    Delegates to ``CSharpLanguageProfile._derive_namespace`` when available.
    Falls back to PascalCase conversion of the directory path.
    """
    try:
        from startd8.languages.csharp import CSharpLanguageProfile
        profile = CSharpLanguageProfile()
        ns = profile._derive_namespace(file_path)
        if ns:
            return ns
    except (ImportError, Exception):
        pass

    # Inline fallback: strip src/ prefix, PascalCase directory segments
    p = PurePosixPath(file_path)
    parts = list(p.parts[:-1])  # exclude filename
    # Strip leading "src" if present
    if parts and parts[0].lower() == "src":
        parts = parts[1:]
    if not parts:
        return None
    return ".".join(_pascalcase(seg) for seg in parts)


def _pascalcase(s: str) -> str:
    """Convert a string to PascalCase (best-effort)."""
    if not s:
        return s
    # Already PascalCase
    if s[0].isupper() and "_" not in s and "-" not in s:
        return s
    return "".join(word.capitalize() for word in s.replace("-", "_").split("_"))


def _derive_class_name(file_path: str) -> str:
    """Derive class name from file path (filename stem)."""
    return PurePosixPath(file_path).stem


def _render_usings(imports: List[str]) -> str:
    """Render using directives with 2-tier grouping.

    Tier 1: ``System.*`` / ``Microsoft.*`` (framework)
    Tier 2: Everything else (third-party / project)
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
        # Normalize: strip "using " prefix and trailing ";"
        ns = imp
        if ns.startswith("using "):
            ns = ns[6:]
        if ns.endswith(";"):
            ns = ns[:-1]
        ns = ns.strip()
        if not ns:
            continue

        directive = f"using {ns};"
        if directive in seen:
            continue
        seen.add(directive)

        if any(ns.startswith(prefix) for prefix in _STDLIB_PREFIXES):
            stdlib.append(directive)
        else:
            other.append(directive)

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
    attributes: Optional[List[str]] = None,
    is_abstract: bool = False,
    is_override: bool = False,
    is_async: bool = False,
    indent: str = "    ",
) -> str:
    """Render a method stub with ``throw new NotImplementedException()``.

    Abstract/interface methods get no body (just a semicolon).
    """
    lines: list[str] = []
    if attributes:
        for attr in attributes:
            if not attr.startswith("["):
                attr = f"[{attr}]"
            lines.append(f"{indent}{attr}")

    mod_parts = [modifiers]
    if is_override:
        mod_parts.append("override")
    if is_async:
        mod_parts.append("async")
    mod_str = " ".join(mod_parts)

    sig = f"{indent}{mod_str} {return_type} {name}({params})"

    if is_abstract:
        lines.append(f"{sig};")
    else:
        lines.append(f"{sig}")
        lines.append(f"{indent}{{")
        lines.append(f"{indent}    {CSHARP_STUB_BODY}")
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
        f"{indent}{modifiers} {class_name}({params})",
        f"{indent}{{",
        f"{indent}    {CSHARP_STUB_BODY}",
        f"{indent}}}",
    ]
    return "\n".join(lines)


def _render_property_stub(
    name: str,
    prop_type: str = "object",
    modifiers: str = "public",
    attributes: Optional[List[str]] = None,
    indent: str = "    ",
) -> str:
    """Render a property with auto-getter/setter."""
    lines: list[str] = []
    if attributes:
        for attr in attributes:
            if not attr.startswith("["):
                attr = f"[{attr}]"
            lines.append(f"{indent}{attr}")
    lines.append(f"{indent}{modifiers} {prop_type} {name} {{ get; set; }}")
    return "\n".join(lines)


def _render_field(
    name: str,
    field_type: str,
    modifiers: str = "private",
    indent: str = "    ",
) -> str:
    """Render a field declaration."""
    return f"{indent}{modifiers} {field_type} {name};"


def _python_type_to_csharp(type_str: str) -> str:
    """Best-effort Python type → C# type conversion."""
    mapping = {
        "str": "string",
        "int": "int",
        "float": "double",
        "bool": "bool",
        "None": "void",
        "bytes": "byte[]",
        "list": "List<object>",
        "dict": "Dictionary<string, object>",
        "set": "HashSet<object>",
        "tuple": "object[]",
        "Any": "object",
        "Optional": "object",
    }
    # Handle Optional[X] → X?
    if type_str.startswith("Optional["):
        inner = type_str[len("Optional["):-1]
        inner_cs = _python_type_to_csharp(inner)
        return f"{inner_cs}?"
    # Handle List[X]
    if type_str.startswith(("List[", "list[")):
        inner = type_str[type_str.index("[") + 1:-1]
        return f"List<{_python_type_to_csharp(inner)}>"
    # Handle Dict[K, V]
    if type_str.startswith(("Dict[", "dict[")):
        inner = type_str[type_str.index("[") + 1:-1]
        parts = inner.split(",", 1)
        if len(parts) == 2:
            k = _python_type_to_csharp(parts[0].strip())
            v = _python_type_to_csharp(parts[1].strip())
            return f"Dictionary<{k}, {v}>"
    return mapping.get(type_str, type_str)


def _render_csharp_params(elem: Any) -> str:
    """Render C#-style parameter list from a ForwardElementSpec."""
    if not hasattr(elem, "signature") or not elem.signature:
        return ""
    params: list[str] = []
    for p in elem.signature.params:
        if p.name in ("self", "cls"):
            continue
        cs_type = _python_type_to_csharp(p.annotation) if p.annotation else "object"
        params.append(f"{cs_type} {p.name}")
    return ", ".join(params)


def _is_type_element(elem: Any) -> bool:
    """Check if an element represents a type declaration."""
    kind = getattr(elem, "kind", None)
    kind_val = kind.value if hasattr(kind, "value") else str(kind)
    return kind_val == "class"


def _element_kind_to_csharp(elem: Any) -> str:
    """Map element metadata to C# type keyword.

    Checks decorators for interface/struct/record/enum hints.
    """
    if hasattr(elem, "decorators") and elem.decorators:
        for d in elem.decorators:
            if not d:
                continue
            dl = d.lower()
            if "interface" in dl:
                return "interface"
            if "struct" in dl:
                return "struct"
            if "record" in dl:
                return "record"
            if "enum" in dl:
                return "enum"
    return "class"


class CSharpDeterministicFileAssembler:
    """Assembles C# skeleton files from ForwardManifest entries.

    Each rendered file contains:
    - ``// [STARTD8-SKELETON]`` marker
    - Using directives (2-tier: System/Microsoft, then third-party)
    - File-scoped namespace declaration
    - Class/interface/struct/record with stub method bodies
    """

    def render_specs(
        self,
        manifest: Any,
        output_dir: Any = None,
    ) -> Dict[str, str]:
        """Render all .cs files from a ForwardManifest."""
        results: Dict[str, str] = {}
        for file_spec in manifest.files:
            if not file_spec.file.endswith(".cs"):
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
        """Render a single C# file from a ForwardFileSpec.

        Returns:
            Rendered C# source, or None if the file has no elements.
        """
        file_path = file_spec.file
        if not file_path.endswith(".cs"):
            return None

        sections: list[str] = []

        # Skeleton marker
        sections.append(CSHARP_SKELETON_SENTINEL)

        # Using directives
        import_strs: list[str] = []
        for imp in getattr(file_spec, "imports", []):
            if hasattr(imp, "names") and hasattr(imp, "module"):
                # ForwardImportSpec: "using Module.Name;"
                if imp.module:
                    import_strs.append(imp.module)
            elif isinstance(imp, str):
                import_strs.append(imp)
        using_block = _render_usings(import_strs)
        if using_block:
            sections.append(using_block)

        # File-scoped namespace (always — never block-scoped)
        namespace = _derive_namespace(file_path)
        if namespace:
            sections.append(f"namespace {namespace};")

        # Derive class name
        class_name = _derive_class_name(file_path)

        # Group elements
        elements = getattr(file_spec, "elements", [])
        type_elements = [e for e in elements if _is_type_element(e)]
        member_elements = [e for e in elements if not _is_type_element(e)]

        if not type_elements:
            # Default: create a public class with the file's class name
            class_body = self._render_members(member_elements, class_name)
            sections.append(f"public class {class_name}\n{{\n{class_body}\n}}")
        else:
            for te in type_elements:
                kind = _element_kind_to_csharp(te)
                name = te.name
                modifiers = "public"

                # Base class / interfaces
                bases_str = ""
                if hasattr(te, "bases") and te.bases:
                    bases_str = f" : {', '.join(te.bases)}"

                # Attributes
                attr_lines = ""
                if hasattr(te, "decorators") and te.decorators:
                    attrs = [
                        d for d in te.decorators
                        if d and not any(kw in d.lower() for kw in
                                         ("interface", "struct", "record", "enum"))
                    ]
                    if attrs:
                        attr_lines = "\n".join(
                            f"[{a}]" if not a.startswith("[") else a
                            for a in attrs
                        ) + "\n"

                # Collect members belonging to this type
                members = [
                    e for e in member_elements
                    if getattr(e, "parent_class", None) == name
                ]
                body = self._render_members(members, name)

                sections.append(
                    f"{attr_lines}{modifiers} {kind} {name}{bases_str}\n"
                    f"{{\n{body}\n}}"
                )

        content = "\n\n".join(sections) + "\n"

        # Validate via tree-sitter if available
        content = self._validate_output(content, file_path)

        return content

    def _render_members(self, elements: list, class_name: str) -> str:
        """Render class members (fields, constructors, methods, properties)."""
        lines: list[str] = []

        for elem in elements:
            kind = getattr(elem, "kind", None)
            kind_val = kind.value if hasattr(kind, "value") else str(kind)
            name = elem.name

            if kind_val in ("constant", "variable", "field"):
                ret_type = "object"
                if hasattr(elem, "signature") and elem.signature:
                    ret_ann = getattr(elem.signature, "return_annotation", None)
                    if ret_ann:
                        ret_type = _python_type_to_csharp(ret_ann)
                elif hasattr(elem, "type_annotation") and elem.type_annotation:
                    ret_type = _python_type_to_csharp(elem.type_annotation)
                modifiers = "private readonly" if kind_val == "constant" else "private"
                lines.append(_render_field(name, ret_type, modifiers=modifiers))
                lines.append("")

            elif name == class_name or kind_val == "constructor":
                params = _render_csharp_params(elem)
                lines.append(_render_constructor_stub(class_name, params=params))
                lines.append("")

            elif kind_val == "property":
                ret_type = "object"
                if hasattr(elem, "signature") and elem.signature:
                    ret_ann = getattr(elem.signature, "return_annotation", None)
                    if ret_ann and ret_ann != "None":
                        ret_type = _python_type_to_csharp(ret_ann)
                elif hasattr(elem, "type_annotation") and elem.type_annotation:
                    ret_type = _python_type_to_csharp(elem.type_annotation)
                attributes = None
                if hasattr(elem, "decorators") and elem.decorators:
                    attributes = [
                        d for d in elem.decorators
                        if d and (d.startswith("[") or d[0].isupper())
                    ]
                lines.append(_render_property_stub(
                    name, ret_type, attributes=attributes,
                ))
                lines.append("")

            elif kind_val in ("method", "async_method", "function", "async_function"):
                ret_type = "void"
                if hasattr(elem, "signature") and elem.signature:
                    ret_ann = getattr(elem.signature, "return_annotation", None)
                    if ret_ann and ret_ann != "None":
                        ret_type = _python_type_to_csharp(ret_ann)
                params = _render_csharp_params(elem)
                modifiers = "public"
                is_abstract = getattr(elem, "is_abstract", False)
                is_override = False
                is_async = kind_val.startswith("async")
                attributes = None
                if hasattr(elem, "decorators") and elem.decorators:
                    attrs = [
                        d for d in elem.decorators
                        if d and (d.startswith("[") or d[0].isupper())
                    ]
                    if attrs:
                        attributes = attrs
                    # Check for override hint
                    if any("override" in d.lower() for d in elem.decorators if d):
                        is_override = True
                lines.append(_render_method_stub(
                    name, ret_type, params,
                    modifiers=modifiers,
                    attributes=attributes,
                    is_abstract=is_abstract,
                    is_override=is_override,
                    is_async=is_async,
                ))
                lines.append("")

        return "\n".join(lines).rstrip()

    def _validate_output(self, content: str, file_path: str) -> str:
        """Validate rendered output via tree-sitter; return content unchanged on failure."""
        try:
            from startd8.languages.csharp_parser import validate_csharp_syntax
            valid, error = validate_csharp_syntax(content)
            if not valid:
                logger.warning(
                    "C# DFA output validation warning for %s: %s",
                    file_path, error,
                )
        except ImportError:
            pass
        except Exception as exc:
            logger.warning(
                "C# DFA output validation failed for %s: %s", file_path, exc,
            )
        return content
