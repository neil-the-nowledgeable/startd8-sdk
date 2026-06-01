"""Unified cross-file Verifier registry (CKG Phase 1, REQ-CKG-600/235).

One surface that runs the cross-file checks and returns a **typed batch result**
(findings + per-check availability) the caller consumes for its verdict (R3-S4). This is
the extraction the 690a regression-lock guards: `_evaluate_cross_file_integrity` becomes a
thin caller (Inc-4b) and the 5 shipped signatures' output must be byte-equivalent.

Checks (REQ-CKG-235 finding contract; all `scope="cross_file"`):
  toolchain-free (always run):
    - zod_symmetry           prisma_zod_symmetry.evaluate_cross_file_integrity   (d, #7/#13)
    - unresolvable_import    cross_file_imports.scan_unresolvable_imports        (a, #1/#2)
    - missing_dependency     cross_file_imports.scan_missing_dependencies        (b, #3)
    - prisma_usage           prisma_usage.scan_prisma_usage                      (c/e, #8/#12)
    - tsconfig_paths         tsconfig_paths.scan                                 (Inc-2, #5)
  SCIP-gated (skipped_unavailable when no index, REQ-CKG-230):
    - external_type_presence external_type_presence.scan                        (f, #4/#11)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from startd8.code_observability.scip_reader import ScipReader
from startd8.validators import (
    cross_file_imports,
    external_type_presence,
    prisma_usage,
    prisma_zod_symmetry,
    tsconfig_paths,
)

# Remediation hint per finding kind (REQ-CKG-235 remediation-grade messages).
_REMEDIATION = {
    "unresolvable_import": "Fix the import path or create the missing module.",
    "missing_dependency": "Add the package to package.json dependencies (or remove the import).",
    "prisma_unknown_field": "Use a field that exists on the Prisma model (check schema.prisma).",
    "prisma_where_not_unique": "Use @id/@unique field(s) in a unique-where, or switch to findFirst.",
    "prisma_invalid_compound_key": "Reference a declared @@unique/@@id compound key, or use scalar where.",
    "field_missing_in_prisma": "Remove the field from the Zod schema or add it to the Prisma model.",
    "field_type_mismatch": "Align the Zod field type-class with the Prisma column type.",
    "fk_invented": "Remove the invented relation field, or add the relation to the Prisma model.",
    "tsconfig_alias_unresolved": "Point the tsconfig path alias at an existing directory/file.",
    "external_type_unresolved": "Use a real exported member of the package (check its .d.ts / docs).",
}


@dataclass(frozen=True)
class Finding:
    """Normalized cross-file finding (REQ-CKG-235)."""

    check_id: str
    kind: str
    source_file: str
    locus: str            # field or specifier
    severity: str         # "error" | "warning"
    scope: str            # "cross_file"
    message: str
    remediation: str


@dataclass
class CrossFileResult:
    findings: List[Finding] = field(default_factory=list)
    availability: Dict[str, str] = field(default_factory=dict)  # check_id -> ran|skipped_unavailable

    @property
    def errors(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def has_error(self) -> bool:
        return any(f.severity == "error" for f in self.findings)


def _locus(raw: Any) -> str:
    return getattr(raw, "field", None) or getattr(raw, "specifier", None) or ""


def _to_finding(check_id: str, raw: Any) -> Finding:
    kind = getattr(raw, "kind", check_id)
    return Finding(
        check_id=check_id,
        kind=kind,
        source_file=getattr(raw, "source_file", "") or "",
        locus=_locus(raw),
        severity=getattr(raw, "severity", "error"),
        scope="cross_file",
        message=getattr(raw, "detail", "") or "",
        remediation=_REMEDIATION.get(kind, "Review the cross-file contract violation."),
    )


def run_checks(
    sources: Dict[str, str],
    project_root: str,
    *,
    scip: Optional[ScipReader] = None,
) -> CrossFileResult:
    """Run all cross-file checks; return findings + per-check availability.

    ``sources`` maps repo-relative path -> content (the materialized batch). ``scip`` is the
    per-batch index (None -> the SCIP-backed checks report ``skipped_unavailable``, never PASS).
    """
    result = CrossFileResult()

    # Toolchain-free checks (always run).
    for raw in prisma_zod_symmetry.evaluate_cross_file_integrity(sources):
        result.findings.append(_to_finding("zod_symmetry", raw))
    result.availability["zod_symmetry"] = "ran"

    for raw in cross_file_imports.scan_unresolvable_imports(sources, project_root):
        result.findings.append(_to_finding("unresolvable_import", raw))
    result.availability["unresolvable_import"] = "ran"

    for raw in cross_file_imports.scan_missing_dependencies(sources, project_root):
        result.findings.append(_to_finding("missing_dependency", raw))
    result.availability["missing_dependency"] = "ran"

    for raw in prisma_usage.scan_prisma_usage(sources, project_root):
        result.findings.append(_to_finding("prisma_usage", raw))
    result.availability["prisma_usage"] = "ran"

    for raw in tsconfig_paths.scan(project_root):
        result.findings.append(_to_finding("tsconfig_paths", raw))
    result.availability["tsconfig_paths"] = "ran"

    # SCIP-gated check (REQ-CKG-230/610).
    if scip is not None:
        for raw in external_type_presence.scan(sources, scip):
            result.findings.append(_to_finding("external_type_presence", raw))
        result.availability["external_type_presence"] = "ran"
    else:
        result.availability["external_type_presence"] = "skipped_unavailable"

    return result
