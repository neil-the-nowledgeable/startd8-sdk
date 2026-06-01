"""Intra-batch inter-feature contract propagation — RUN-008 FR-1/2/3.

The run-008 root cause (G1): each feature designs its cross-file contract in
isolation. A consumer importing a sibling-produced module never sees the
producer's *actual* emitted interface, so it invents the module name, the
export names, and the field shape (PI-012 imported ``@/lib/schemas`` while
PI-011 emitted ``lib/value-model.ts`` exporting ``ProfileSchema``).

This module supplies the producer's **real, on-disk** interface so the consumer
can be grounded in what was actually generated (FR-1, disk-authoritative per
OQ-1), resolves which producer files a consumer imports from (FR-3), and blocks
loudly when a declared producer output is absent rather than inventing it (FR-2,
:class:`~startd8.exceptions.MissingUpstreamArtifact`).

Export extraction is toolchain-free (regex over the emitted source) so it works
without Node — consistent with the rest of the RUN-008 verification path. The
``.d.ts``-based extraction (FR-8) is a future refinement when the Track-B
toolchain is provisioned; the export set it would yield is the same shape this
returns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

from ..exceptions import MissingUpstreamArtifact

# export const/let/var/function/class/interface/type/enum NAME
_EXPORT_DECL_RE = re.compile(
    r"\bexport\s+(?:default\s+)?(?:async\s+)?"
    r"(?:const|let|var|function|class|interface|type|enum)\s+([A-Za-z_$][\w$]*)"
)
# export { A, B as C }  (optionally `from '...'`)
_EXPORT_LIST_RE = re.compile(r"\bexport\s*\{([^}]*)\}")
_EXPORT_DEFAULT_RE = re.compile(r"\bexport\s+default\b")
# import ... from '<module>'   /   export ... from '<module>'
_IMPORT_FROM_RE = re.compile(r"""\b(?:import|export)\b[^;\n]*?\bfrom\s*['"]([^'"]+)['"]""")
_BARE_IMPORT_RE = re.compile(r"""\bimport\s*['"]([^'"]+)['"]""")


@dataclass(frozen=True)
class UpstreamInterface:
    """The real emitted interface of one producer file a consumer imports from."""

    module_path: str            # e.g. "lib/value-model.ts"
    import_specifier: str       # how the consumer referenced it, e.g. "@/lib/value-model"
    exports: Set[str] = field(default_factory=set)


def extract_ts_exports(source: str) -> Set[str]:
    """Extract the public export names from TypeScript/JS *source* (toolchain-free)."""
    exports: Set[str] = set()
    for m in _EXPORT_DECL_RE.finditer(source or ""):
        exports.add(m.group(1))
    for m in _EXPORT_LIST_RE.finditer(source or ""):
        for part in m.group(1).split(","):
            part = part.strip()
            if not part:
                continue
            # `A as B` re-exports as B (the visible name)
            name = part.split(" as ")[-1].strip() if " as " in part else part
            name = name.lstrip("*").strip()
            if re.fullmatch(r"[A-Za-z_$][\w$]*", name):
                exports.add(name)
    if _EXPORT_DEFAULT_RE.search(source or ""):
        exports.add("default")
    return exports


def extract_exports(source: str, path: str) -> Set[str]:
    """Dispatch export extraction by file extension. TS/JS today; extensible."""
    suffix = Path(path).suffix.lower()
    if suffix in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
        return extract_ts_exports(source)
    return set()


def extract_import_specifiers(source: str) -> List[str]:
    """Return the module specifiers a TS/JS file imports from (incl. bare imports)."""
    specs: List[str] = []
    for m in _IMPORT_FROM_RE.finditer(source or ""):
        specs.append(m.group(1))
    for m in _BARE_IMPORT_RE.finditer(source or ""):
        specs.append(m.group(1))
    return specs


def resolve_specifier_to_paths(
    specifier: str,
    candidate_paths: List[str],
    *,
    alias_prefixes: Optional[Dict[str, str]] = None,
    importer_path: str = "",
) -> List[str]:
    """Resolve an import *specifier* to matching producer file paths.

    Handles ``@/``-style aliases (``alias_prefixes`` maps ``"@/"`` → base dir,
    default ``""`` i.e. project root) and relative (``./`` / ``../``) imports.
    Bare package imports (``zod``, ``next/server``) resolve to nothing — they
    are not sibling-produced. Matching is by path stem to tolerate the missing
    extension in the specifier.
    """
    alias_prefixes = alias_prefixes or {"@/": ""}
    if specifier.startswith("."):
        base = Path(importer_path).parent if importer_path else Path("")
        target = (base / specifier).as_posix()
    else:
        matched_alias = next((a for a in alias_prefixes if specifier.startswith(a)), None)
        if matched_alias is None:
            return []  # bare package import — not a sibling
        rest = specifier[len(matched_alias):]
        prefix = alias_prefixes[matched_alias]
        target = f"{prefix.rstrip('/')}/{rest}" if prefix else rest
    target_stem = re.sub(r"\.(ts|tsx|js|jsx|mjs|cjs)$", "", Path(target).as_posix())
    target_stem = target_stem.lstrip("/")
    out: List[str] = []
    for cand in candidate_paths:
        cand_stem = re.sub(r"\.(ts|tsx|js|jsx|mjs|cjs)$", "", Path(cand).as_posix())
        if cand_stem.endswith(target_stem) or cand_stem == target_stem:
            out.append(cand)
    return out


def build_upstream_interfaces(
    *,
    producer_files: List[str],
    project_root: str,
    import_specifiers: Optional[Dict[str, str]] = None,
    require_present: bool = True,
    read_fn: Optional[Callable[[str], Optional[str]]] = None,
) -> List[UpstreamInterface]:
    """Assemble the real interfaces of a consumer's *producer_files* (FR-1).

    Reads each producer file on disk and extracts its real exports. When
    *require_present* (the feature explicitly ``depends_on`` the producer), a
    missing producer file raises :class:`MissingUpstreamArtifact` (FR-2) rather
    than silently omitting it. *import_specifiers* maps producer path → how the
    consumer referenced it (for the prompt); optional.
    """
    import_specifiers = import_specifiers or {}

    def _default_read(p: str) -> Optional[str]:
        candidate = Path(p) if Path(p).is_absolute() else Path(project_root) / p
        try:
            return candidate.read_text(encoding="utf-8") if candidate.is_file() else None
        except OSError:
            return None

    read = read_fn or _default_read
    interfaces: List[UpstreamInterface] = []
    for pf in producer_files:
        source = read(pf)
        if source is None:
            if require_present:
                raise MissingUpstreamArtifact(
                    f"Upstream producer artifact not found on disk: {pf}",
                    missing_path=pf,
                )
            continue
        interfaces.append(UpstreamInterface(
            module_path=pf,
            import_specifier=import_specifiers.get(pf, pf),
            exports=extract_exports(source, pf),
        ))
    return interfaces


def render_upstream_interfaces(interfaces: List[UpstreamInterface]) -> str:
    """Render interfaces as a prompt section grounding the consumer in real exports."""
    if not interfaces:
        return ""
    lines = [
        "## Upstream module interfaces (already generated — import EXACTLY these)",
        "Import from these real module paths and use ONLY these exported symbols. "
        "Do not invent module names or export names.",
    ]
    for iface in sorted(interfaces, key=lambda i: i.module_path):
        exports = ", ".join(sorted(iface.exports)) if iface.exports else "(no named exports)"
        lines.append(f"- `{iface.module_path}` exports: {exports}")
    return "\n".join(lines)
