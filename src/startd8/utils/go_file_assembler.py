"""Go Deterministic File Assembler (DFA) — REQ-DFA-105.

Generates ``.go`` skeleton files from ``ForwardFileSpec`` entries.
Uses Go conventions: ``package`` declaration from directory name,
grouped imports, struct/interface declarations, ``panic("not implemented")``
stubs.

Skeleton marker: ``// [STARTD8-SKELETON]``
Stub body: ``panic("not implemented")``
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional

from startd8.logging_config import get_logger

logger = get_logger(__name__)

GO_SKELETON_SENTINEL = "// [STARTD8-SKELETON]"
GO_STUB_BODY = 'panic("not implemented")'

# Prefixes that identify Go stdlib imports (no dot in path).
_STDLIB_HEURISTIC = frozenset({
    "context", "crypto", "database", "encoding", "errors", "fmt",
    "io", "log", "math", "net", "os", "path", "reflect", "regexp",
    "runtime", "sort", "strconv", "strings", "sync", "testing",
    "time", "unicode",
})


def _derive_package(
    file_path: str,
    dir_packages: Optional[Dict[str, str]] = None,
) -> str:
    """Derive Go package name from file path.

    Go convention: package name = directory name (lowercase, single word).
    ``main.go`` in the root → ``package main``.

    REQ-KZ-GO-606: When *dir_packages* is provided, reuse the package name
    already assigned to sibling files in the same directory.  This ensures
    all ``.go`` files in a directory share the same ``package`` declaration.
    """
    p = PurePosixPath(file_path)
    parent_dir = str(p.parent)

    # REQ-KZ-GO-606: If a sibling already established the package, reuse it.
    if dir_packages and parent_dir in dir_packages:
        return dir_packages[parent_dir]

    name = p.stem  # e.g., "main" from "main.go"

    # Special case: main.go → package main
    if name == "main":
        return "main"

    # Use parent directory name
    parts = list(p.parts[:-1])
    # Strip common prefixes
    while parts and parts[0].lower() in ("src", "cmd", "internal", "pkg"):
        parts = parts[1:]

    if parts:
        return parts[-1].lower().replace("-", "").replace("_", "")
    return "main"


def _is_stdlib_import(imp: str) -> bool:
    """Heuristic: stdlib imports have no dots in the path."""
    imp = imp.strip().strip('"')
    first_segment = imp.split("/")[0]
    return first_segment in _STDLIB_HEURISTIC or "." not in first_segment


def _render_imports(imports: List[str]) -> str:
    """Render Go import block with stdlib/third-party grouping."""
    if not imports:
        return ""

    stdlib: list[str] = []
    other: list[str] = []
    seen: set[str] = set()

    for imp in imports:
        imp = imp.strip()
        if not imp:
            continue
        # Normalize: strip "import" keyword, quotes, aliases
        path = imp
        if path.startswith("import "):
            path = path[7:]
        path = path.strip().strip('"')
        if not path or path in seen:
            continue
        seen.add(path)

        if _is_stdlib_import(path):
            stdlib.append(f'\t"{path}"')
        else:
            other.append(f'\t"{path}"')

    if not stdlib and not other:
        return ""

    sections: list[str] = []
    if stdlib:
        sections.append("\n".join(sorted(stdlib)))
    if other:
        sections.append("\n".join(sorted(other)))

    inner = "\n\n".join(sections)
    return f"import (\n{inner}\n)"


def _render_func_stub(
    name: str,
    params: str = "",
    return_type: str = "",
    receiver: str = "",
    indent: str = "\t",
) -> str:
    """Render a Go function/method stub with panic body."""
    recv = f"({receiver}) " if receiver else ""
    ret = f" {return_type}" if return_type else ""
    return (
        f"func {recv}{name}({params}){ret} {{\n"
        f"{indent}{GO_STUB_BODY}\n"
        f"}}"
    )


class GoDeterministicFileAssembler:
    """Assembles Go skeleton files from ForwardManifest entries.

    Each rendered file contains:
    - ``// [STARTD8-SKELETON]`` marker
    - ``package`` declaration (derived from directory)
    - Import block (stdlib first, then third-party)
    - Struct/interface declarations with stub methods
    """

    def render_specs(
        self,
        manifest: Any,
        output_dir: Any = None,
    ) -> Dict[str, str]:
        """Render all .go files from a ForwardManifest."""
        results: Dict[str, str] = {}
        file_specs = manifest.file_specs if hasattr(manifest, "file_specs") else {}
        if isinstance(file_specs, dict):
            items = list(file_specs.items())
        else:
            items = [(getattr(fs, "file", ""), fs) for fs in file_specs]

        # REQ-KZ-GO-606: First pass — seed directory→package map from main.go
        # files so sibling files in the same directory get the same package.
        dir_packages: Dict[str, str] = {}
        for file_path, _ in items:
            if PurePosixPath(file_path).name == "main.go":
                dir_packages[str(PurePosixPath(file_path).parent)] = "main"

        for file_path, file_spec in items:
            if not file_path.endswith(".go"):
                continue
            content = self.render_file(file_spec, dir_packages=dir_packages)
            if content:
                results[file_path] = content
                # Record this file's package for later siblings
                pkg = _derive_package(file_path, dir_packages)
                parent_dir = str(PurePosixPath(file_path).parent)
                if parent_dir not in dir_packages:
                    dir_packages[parent_dir] = pkg
                if output_dir:
                    from pathlib import Path
                    out_path = Path(output_dir) / file_path
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(content, encoding="utf-8")
        return results

    def render_file(
        self,
        file_spec: Any,
        dir_packages: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """Render a single Go file from a ForwardFileSpec."""
        file_path = getattr(file_spec, "file", "")
        if not file_path.endswith(".go"):
            return None

        sections: list[str] = []

        # Skeleton marker
        sections.append(GO_SKELETON_SENTINEL)

        # Package declaration (REQ-KZ-GO-606: propagate from siblings)
        package = _derive_package(file_path, dir_packages)
        sections.append(f"package {package}")

        # Import block
        import_strs: list[str] = []
        for imp in getattr(file_spec, "imports", []):
            if hasattr(imp, "module") and imp.module:
                import_strs.append(imp.module)
            elif isinstance(imp, str):
                import_strs.append(imp)
        import_block = _render_imports(import_strs)
        if import_block:
            sections.append(import_block)

        # Elements
        elements = getattr(file_spec, "elements", [])

        # Separate type-level and function-level elements
        type_elements = [
            e for e in elements
            if getattr(e, "kind", None)
            and (
                getattr(e.kind, "value", str(e.kind)) == "class"
            )
        ]
        func_elements = [e for e in elements if e not in type_elements]

        class_name = PurePosixPath(file_path).stem
        # PascalCase the struct name
        if class_name and class_name[0].islower():
            class_name = class_name[0].upper() + class_name[1:]

        if not type_elements and not func_elements:
            # Default: empty struct with package-derived name
            if package != "main":
                sections.append(f"type {class_name} struct {{\n}}")

        for te in type_elements:
            name = te.name
            is_iface = getattr(te, "is_interface", False)
            if hasattr(te, "decorators") and te.decorators:
                if any("interface" in str(d).lower() for d in te.decorators):
                    is_iface = True

            if is_iface:
                sections.append(f"type {name} interface {{\n}}")
            else:
                # Struct with embedded types
                bases = getattr(te, "bases", []) or []
                body_lines = [f"\t{b}" for b in bases] if bases else []
                body = "\n".join(body_lines)
                sections.append(f"type {name} struct {{\n{body}\n}}")

        for fe in func_elements:
            name = fe.name
            parent = getattr(fe, "parent_class", None) or getattr(fe, "parent_type", None)
            receiver = f"s *{parent}" if parent else ""
            params = ""
            ret = ""
            if hasattr(fe, "signature") and fe.signature:
                sig = fe.signature
                p_parts = []
                for p in getattr(sig, "params", []):
                    if p.name in ("self", "cls"):
                        continue
                    ann = p.annotation or "interface{}"
                    p_parts.append(f"{p.name} {ann}")
                params = ", ".join(p_parts)
                ret = getattr(sig, "return_annotation", "") or ""

            sections.append(_render_func_stub(name, params, ret, receiver))

        # REQ-KZ-GO-604: Type-only files need at least one panic stub so that
        # _skeleton_has_stubs() returns True and the file-whole generation path
        # is eligible.  Without this, the skeleton passes through unchanged.
        if type_elements and not func_elements:
            sections.append(
                f"// placeholder — file-whole generation will replace this skeleton.\n"
                f"func init() {{\n"
                f"\t{GO_STUB_BODY}\n"
                f"}}"
            )

        return "\n\n".join(sections) + "\n"
