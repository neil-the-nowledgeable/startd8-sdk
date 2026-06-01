"""Bridge cross-file content-contract scan results into repair diagnostics (Inc 2, FR-4).

Mirrors ``repair/semantic_bridge.py``: it translates the detection-layer violation
objects (``PrismaUsageViolation`` / ``ImportViolation``) — which the integration
engine runs in the pre-merge path — into the typed ``Diagnostic`` subclasses the
repair routing table understands. The structured ``model`` field added to
``PrismaUsageViolation`` (R1-S3) is read directly, so no ``detail`` prose parsing
is needed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Sequence

from .models import Diagnostic, MisnamedFieldDiagnostic, WrongImportPathDiagnostic

if TYPE_CHECKING:  # avoid importing validators at module load
    from ..validators.cross_file_imports import ImportViolation
    from ..validators.prisma_usage import PrismaUsageViolation


def scan_results_to_diagnostics(
    prisma_violations: "Sequence[PrismaUsageViolation]",
    import_violations: "Sequence[ImportViolation]",
) -> List[Diagnostic]:
    """Translate content-contract scan results into routable diagnostics.

    Only the **invented-name** kinds are bridged into the rename pipeline:
    ``prisma_unknown_field`` (a field that is not on the model) and
    ``unresolvable_import`` (a specifier that resolves to nothing). The
    ``prisma_where_not_unique`` / ``prisma_invalid_compound_key`` /
    ``missing_dependency`` kinds are out of v1 scope (Non-Requirements §5) and
    are not bridged.
    """
    diagnostics: List[Diagnostic] = []

    for v in prisma_violations:
        if v.kind != "prisma_unknown_field":
            continue
        diagnostics.append(
            MisnamedFieldDiagnostic(
                category="content_contract",
                file=v.source_file,
                message=v.detail,
                field=v.field,
                model=v.model,
            )
        )

    for iv in import_violations:
        if iv.kind != "unresolvable_import":
            continue
        diagnostics.append(
            WrongImportPathDiagnostic(
                category="content_contract",
                file=iv.source_file,
                message=iv.detail,
                specifier=iv.specifier,
            )
        )

    return diagnostics
