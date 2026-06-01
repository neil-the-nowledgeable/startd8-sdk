"""SCIP index reader (CKG Phase 1, REQ-CKG-210/220).

Parses a scip-typescript index (protobuf, via the vendored :mod:`scip_pb2`) into the
typed accessors the cross-file checks consume. There is **no separate fact-normalizer
model** (REQ-CKG-220 collapsed here): the reader's accessors *are* the fact surface.

Key fact verified by the SG-2 spike: scip-typescript 0.4.0 leaves the top-level
``Index.external_symbols`` table **empty** — external symbols appear as **occurrence
symbols** on each document. So everything here reads ``Document.occurrences``.

SCIP global symbol grammar (space-separated):
    ``<scheme> <manager> <package-name> <version> <descriptor...>``
e.g. ``scip-typescript npm zod 3.25.76 v3/`types.d.cts`/ZodObject#extend().``
Locals are ``local <id>`` and carry no package.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from startd8.logging_config import get_logger

try:  # protobuf is the only pip dep, carried by the optional [code-observability] extra
    from . import scip_pb2
except ImportError:  # keep the package import-safe (NFR-1 / REQ-CKG-710)
    scip_pb2 = None  # type: ignore[assignment]

logger = get_logger(__name__)

# SCIP SymbolRole.Definition is the literal 1 (kept as a fallback so module import never
# requires protobuf); the live enum value is used when scip_pb2 is available.
_DEFINITION = scip_pb2.SymbolRole.Definition if scip_pb2 is not None else 1


def _require_pb2() -> None:
    if scip_pb2 is None:
        raise RuntimeError(
            "SCIP reading requires protobuf. Install the extra: "
            'pip install -e ".[code-observability]"'
        )


@dataclass(frozen=True)
class ParsedSymbol:
    scheme: str
    manager: str
    package: str
    version: str
    descriptor: str  # member path within the package, e.g. "…/ZodObject#extend()."


@dataclass(frozen=True)
class ExternalRef:
    """A reference, resolved by the TS compiler, into an external package member."""

    package: str
    version: str
    descriptor: str
    source_file: str
    symbol: str


@dataclass(frozen=True)
class CrossFileEdge:
    """A project symbol defined in one file and referenced from another."""

    symbol: str
    def_file: str
    ref_file: str


def parse_symbol(symbol: str) -> Optional[ParsedSymbol]:
    """Parse a SCIP global symbol. Returns ``None`` for locals / malformed symbols."""
    if not symbol or symbol.startswith("local"):
        return None
    parts = symbol.split(" ")
    if len(parts) < 5:
        return None  # not a fully-qualified global package symbol
    scheme, manager, package, version = parts[0], parts[1], parts[2], parts[3]
    descriptor = " ".join(parts[4:])
    if not package or not descriptor:
        return None
    return ParsedSymbol(scheme, manager, package, version, descriptor)


# Next.js app-router handler files (best-effort; Inc-3 derives shapes from these).
_ROUTE_SUFFIXES = ("/route.ts", "/route.tsx")


class ScipReader:
    """Typed accessors over a parsed SCIP index."""

    def __init__(self, index: "scip_pb2.Index") -> None:
        self._index = index

    @classmethod
    def from_path(cls, path: str | Path) -> "ScipReader":
        _require_pb2()
        idx = scip_pb2.Index()
        idx.ParseFromString(Path(path).read_bytes())
        return cls(idx)

    @classmethod
    def from_bytes(cls, data: bytes) -> "ScipReader":
        _require_pb2()
        idx = scip_pb2.Index()
        idx.ParseFromString(data)
        return cls(idx)

    # -- basic --
    def documents(self) -> List[str]:
        return [d.relative_path for d in self._index.documents]

    def tool(self) -> Tuple[str, str]:
        ti = self._index.metadata.tool_info
        return (ti.name, ti.version)

    def _defined_symbols(self) -> Set[str]:
        """Symbols with a Definition occurrence anywhere in the index (i.e. project-owned)."""
        defined: Set[str] = set()
        for doc in self._index.documents:
            for occ in doc.occurrences:
                if occ.symbol and not occ.symbol.startswith("local") and (occ.symbol_roles & _DEFINITION):
                    defined.add(occ.symbol)
        return defined

    # -- external-package resolution (signature f, REQ-CKG-610) --
    def external_member_refs(self) -> List[ExternalRef]:
        """Occurrences resolving into an *external* package member.

        The project itself is also an npm package, so a symbol is external only when it
        is npm-managed AND never defined in the indexed set (externals live in
        node_modules and are not indexed, so they have no Definition occurrence).
        """
        defined = self._defined_symbols()
        refs: List[ExternalRef] = []
        for doc in self._index.documents:
            for occ in doc.occurrences:
                ps = parse_symbol(occ.symbol)
                if ps is None or ps.manager != "npm" or occ.symbol in defined:
                    continue
                refs.append(
                    ExternalRef(ps.package, ps.version, ps.descriptor, doc.relative_path, occ.symbol)
                )
        return refs

    def external_symbols_by_package(self) -> Dict[str, Set[str]]:
        """package -> set of referenced member descriptors (the strategy-(a) resolved set)."""
        out: Dict[str, Set[str]] = {}
        for ref in self.external_member_refs():
            out.setdefault(ref.package, set()).add(ref.descriptor)
        return out

    # -- cross-file resolution --
    def cross_file_edges(self) -> List[CrossFileEdge]:
        """Project symbols defined in one file and referenced from another.

        External symbols have no Definition occurrence in the indexed set, so they
        never produce edges — no need to identify the project package explicitly.
        """
        def_file: Dict[str, str] = {}
        ref_files: Dict[str, Set[str]] = {}
        for doc in self._index.documents:
            for occ in doc.occurrences:
                sym = occ.symbol
                if not sym or sym.startswith("local"):
                    continue
                if occ.symbol_roles & _DEFINITION:
                    def_file.setdefault(sym, doc.relative_path)
                else:
                    ref_files.setdefault(sym, set()).add(doc.relative_path)
        edges: List[CrossFileEdge] = []
        for sym, dfile in def_file.items():
            for rfile in ref_files.get(sym, ()):  # noqa: B007
                if rfile != dfile:
                    edges.append(CrossFileEdge(sym, dfile, rfile))
        return edges

    # -- routes (best-effort; Inc-3 derives shapes) --
    def routes(self) -> List[str]:
        return [
            d.relative_path
            for d in self._index.documents
            if d.relative_path.endswith(_ROUTE_SUFFIXES)
        ]
