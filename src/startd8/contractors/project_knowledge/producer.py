"""CKG Phase 2 — ProjectKnowledge producer (REQ-CKG-520/521/523).

The producer is a **view over the Phase-1 resolver** (CROSS_FILE §11): it calls
the same ``parse_prisma_schema`` / ``upstream_interface`` functions the Verifier
uses — no bespoke scanner. Its ``build`` signature mirrors
``cross_file_verifier.run_checks(sources, project_root, *, scip=None)`` so
detection and prevention consume identical inputs (REQ-CKG-520 convergence).

``DraftModeProducer`` is the v1 backend (stdlib/regex, partial-code-tolerant). A
future ``ScipProducer`` drops in via the ``scip`` parameter when a SCIP index
exists — without changing this seam (OQ-4 resolved).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable

from ...languages.prisma_parser import parse_prisma_schema
from ..upstream_interface import build_upstream_interfaces
from .models import EnumAuthority, FieldSetAuthority, FieldSpec, ProjectKnowledge
from .negatives import relevant_negatives

__all__ = ["ProjectKnowledgeProducer", "DraftModeProducer", "canonical_specifier"]

_TSJS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
_PRISMA_OMISSION = "Prisma schema unavailable — do not assume a field set or invent fields."


@runtime_checkable
class ProjectKnowledgeProducer(Protocol):
    """Swappable backend protocol (draft-mode now; SCIP-backed later)."""

    def build(
        self,
        sources: Dict[str, str],
        project_root: str,
        *,
        scip: Optional[Any] = None,
    ) -> ProjectKnowledge:
        ...


def canonical_specifier(module_path: str) -> str:
    """A project module path → its canonical ``@/``-alias import specifier.

    ``lib/db.ts`` → ``@/lib/db``. Matches the ``@/`` convention the codebase uses
    (and that ``resolve_specifier_to_paths`` resolves by default).
    """
    stem = module_path
    for ext in _TSJS:
        if stem.endswith(ext):
            stem = stem[: -len(ext)]
            break
    return "@/" + stem.lstrip("/")


class DraftModeProducer:
    """v1 producer over the stdlib/regex Phase-1 extractors."""

    def build(
        self,
        sources: Dict[str, str],
        project_root: str,
        *,
        scip: Optional[Any] = None,
    ) -> ProjectKnowledge:
        omissions: List[str] = []

        # --- Prisma field-set authority (REQ-521) ---------------------------
        prisma_path, prisma_text = self._find_prisma(sources, project_root)
        field_sets: Tuple[FieldSetAuthority, ...] = ()
        if prisma_text is None:
            omissions.append(_PRISMA_OMISSION)
        else:
            field_sets = self._field_sets(prisma_text, prisma_path or "schema.prisma")
            if not field_sets:
                # schema present but no models parsed → state it, don't claim authority
                omissions.append(_PRISMA_OMISSION)

        # --- TS/JS module interfaces (positive module-path authority) -------
        ts_paths = [p for p in sources if str(p).endswith(_TSJS)]
        interfaces = tuple(build_upstream_interfaces(
            producer_files=ts_paths,
            project_root=project_root,
            require_present=False,
            read_fn=sources.get,
        ))

        # --- Explicit negatives (REQ-522, D2) -------------------------------
        canonical_modules = [canonical_specifier(i.module_path) for i in interfaces]
        negatives = tuple(relevant_negatives(canonical_modules))

        # --- Enum-value authority (REQ-525) ---------------------------------
        enums: Tuple[EnumAuthority, ...] = ()
        if prisma_text is not None:
            enums = self._enums(prisma_text, prisma_path or "schema.prisma")

        return ProjectKnowledge(
            project_root=project_root,
            field_sets=field_sets,
            interfaces=interfaces,
            negatives=negatives,
            enums=enums,
            omissions=tuple(omissions),
        )

    @staticmethod
    def _enums(prisma_text: str, source_file: str) -> Tuple[EnumAuthority, ...]:
        """Enum-value authority from the contract (REQ-525). Reuses the shared
        parser's already-extracted ``enums`` — no new parsing."""
        schema = parse_prisma_schema(prisma_text or "")
        return tuple(
            EnumAuthority(name=name, values=tuple(values), source_file=source_file)
            for name, values in sorted(schema.enums.items())
            if values
        )

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _find_prisma(
        sources: Dict[str, str], project_root: str,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Locate the schema: prefer in-batch ``sources``, else on disk."""
        for path, text in sources.items():
            if str(path).endswith(".prisma"):
                return path, text
        # fall back to the conventional location on disk
        disk = Path(project_root) / "prisma" / "schema.prisma"
        try:
            if disk.is_file():
                return "prisma/schema.prisma", disk.read_text(encoding="utf-8")
        except OSError:
            pass
        return None, None

    @staticmethod
    def _field_sets(prisma_text: str, source_file: str) -> Tuple[FieldSetAuthority, ...]:
        schema = parse_prisma_schema(prisma_text or "")
        out: List[FieldSetAuthority] = []
        for name in sorted(schema.models):
            scalars = schema.scalar_fields(name)  # relations/list-relations excluded
            if not scalars:
                continue
            specs = tuple(
                FieldSpec(name=f.name, type=f.type, optional=f.is_optional, is_list=f.is_list)
                for f in scalars
            )
            out.append(FieldSetAuthority(entity=name, fields=specs, source_file=source_file))
        return tuple(out)
