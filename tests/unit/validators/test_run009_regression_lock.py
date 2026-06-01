"""CKG Phase 1 — REQ-CKG-690a regression lock + Zod composition audit.

This is the *safety net* that must land BEFORE `_evaluate_cross_file_integrity`
(prime_postmortem.py:1660) is refactored/extracted in Inc-4 (REQ-CKG-600). It freezes
the current behaviour of the cross-file *check-composition layer* — the union of
error-severity findings the surface produces from its four entry points
(`prisma_zod_symmetry.evaluate_cross_file_integrity` + `scan_unresolvable_imports` +
`scan_missing_dependencies` + `scan_prisma_usage`, the "5 shipped signatures").

`_run_cross_file_checks()` mirrors exactly what the surface composes. When Inc-4 extracts
that orchestration into `validators/cross_file_verifier.py`, repoint this helper at the new
function: same corpus → identical finding set proves the extraction is byte-equivalent.

Part 2 (`TestZodCompositionAudit`) answers the CRP's "is Phase 1 under-scoped?" (R1-F5/S3):
it records — as `xfail(strict=True)` — that the regex Zod extractor in `prisma_zod_symmetry`
detects drift only in *flat* top-level `z.object`, and misses every composition form. Each
xfail is a tracked, named gap whose downstream gate is the project-level `tsc --noEmit`
(`_evaluate_ts_toolchain`, FR-4) until a SCIP-resolved-types check (Inc-0/Inc-1) supersedes it;
`strict=True` makes pytest flag XPASS the moment a later increment closes the gap.
"""

from __future__ import annotations

import json
from typing import Dict, Set, Tuple

import pytest

from startd8.validators.cross_file_imports import (
    scan_missing_dependencies,
    scan_unresolvable_imports,
)
from startd8.validators.prisma_usage import scan_prisma_usage
from startd8.validators.prisma_zod_symmetry import evaluate_cross_file_integrity

# --- Faithful run-009 schema (real strtd8 field shapes: the #12/#13 drift sources) ---
PRISMA = """\
model Profile {
  id       String @id @default(cuid())
  ownerId  String @default("local")
  summary  String?
  yearsExp Int?
}
model ProofPoint {
  id      String @id @default(cuid())
  ownerId String @default("local")
  title   String?
}
model AiCall {
  id             String @id @default(cuid())
  promptTokens   Int?
  responseTokens Int?
}
"""

# A finding = (signature, kind, locus, source_file). `locus` is specifier or field.
Finding = Tuple[str, str, str, str]


def _run_cross_file_checks(sources: Dict[str, str], project_root: str) -> Set[Finding]:
    """Mirror of `_evaluate_cross_file_integrity`'s check composition (error-only).

    SINGLE SEAM: Inc-4 repoints this to `cross_file_verifier.run(...)` and the locked
    sets below must not change.
    """
    out: Set[Finding] = set()
    for f in evaluate_cross_file_integrity(sources):
        if f.severity == "error":
            out.add(("zod_symmetry", f.kind, f.field or "", f.source_file or ""))
    for scan in (scan_unresolvable_imports, scan_missing_dependencies):
        for f in scan(sources, project_root):
            if f.severity == "error":
                out.add((scan.__name__, f.kind, f.specifier or "", f.source_file or ""))
    for f in scan_prisma_usage(sources, project_root):
        if f.severity == "error":
            out.add(("prisma_usage", f.kind, f.field or "", f.source_file or ""))
    return out


@pytest.fixture()
def project_root(tmp_path) -> str:
    """A tmp project with the run-009 schema on disk + a package.json (pino undeclared)."""
    (tmp_path / "prisma").mkdir()
    (tmp_path / "prisma" / "schema.prisma").write_text(PRISMA)
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"next": "14", "zod": "3",
                                     "@prisma/client": "5", "@anthropic-ai/sdk": "0.24"}})
    )
    return str(tmp_path)


# Each generated file reproduces ≥1 RUN_009 failure category.
DIRTY_SOURCES: Dict[str, str] = {
    "prisma/schema.prisma": PRISMA,
    # #1 module-path: @/lib/prisma is invented (real path is @/lib/db) ; #3 dep: pino undeclared
    "app/api/profile/route.ts": "import { prisma } from '@/lib/prisma';\nimport pino from 'pino';\n",
    # #12 canonical-schema: AiCall has promptTokens/responseTokens, not input/output
    "lib/ai/service.ts": "await db.aiCall.create({ data: { inputTokens: 1, outputTokens: 2 } });\n",
    # #8 compound-key: id_ownerId is not a unique constraint on ProofPoint
    "app/api/pp/route.ts":
        "await db.proofPoint.findUnique({ where: { id_ownerId: { proofPointId: 'x', capabilityId: 'y' } } });\n",
    # #13 zod-field-not-in-prisma (claim/category) ; #7 type-class mismatch (yearsExp Int vs z.string)
    "lib/schemas.ts":
        "import { z } from 'zod';\n"
        "export const ProofPointSchema = z.object({ id: z.string(), claim: z.string(), category: z.string() });\n"
        "export const ProfileSchema = z.object({ id: z.string(), yearsExp: z.string() });\n",
}

# FROZEN current behaviour — captured 2026-06-01 against the shipped 5 signatures.
# Any change here means the verifier surface changed; Inc-4 must reproduce this exactly.
EXPECTED_DIRTY: Set[Finding] = {
    ("scan_unresolvable_imports", "unresolvable_import", "@/lib/prisma", "app/api/profile/route.ts"),
    ("scan_missing_dependencies", "missing_dependency", "pino", "app/api/profile/route.ts"),
    ("prisma_usage", "prisma_unknown_field", "inputTokens", "lib/ai/service.ts"),
    ("prisma_usage", "prisma_unknown_field", "outputTokens", "lib/ai/service.ts"),
    ("prisma_usage", "prisma_invalid_compound_key", "id_ownerId", "app/api/pp/route.ts"),
    ("zod_symmetry", "field_missing_in_prisma", "claim", "lib/schemas.ts"),
    ("zod_symmetry", "field_missing_in_prisma", "category", "lib/schemas.ts"),
    ("zod_symmetry", "field_type_mismatch", "yearsExp", "lib/schemas.ts"),
}

# A coherent batch: imports resolve, deps declared, valid Prisma usage, Zod mirrors Prisma.
CLEAN_SOURCES: Dict[str, str] = {
    "prisma/schema.prisma": PRISMA,
    "lib/db.ts": "export const db = {};\n",  # makes @/lib/db resolvable
    "app/api/profile/route.ts":
        "import { db } from '@/lib/db';\nimport { z } from 'zod';\n"
        "await db.profile.findUnique({ where: { id: 'x' } });\n",
    "lib/schemas.ts":
        "import { z } from 'zod';\n"
        "export const ProfileSchema = z.object({ id: z.string(), summary: z.string().optional(), "
        "yearsExp: z.number().optional() });\n",
}


class TestRun009RegressionLock:
    """REQ-CKG-690a: freeze the 5-signature check-composition layer before Inc-4 refactors it."""

    def test_locked_error_finding_set(self, project_root):
        assert _run_cross_file_checks(DIRTY_SOURCES, project_root) == EXPECTED_DIRTY

    @pytest.mark.parametrize(
        "category, predicate",
        [
            ("#1 module-path (unresolvable @/ import)",
             lambda fs: ("scan_unresolvable_imports", "unresolvable_import", "@/lib/prisma", "app/api/profile/route.ts") in fs),
            ("#3 dependency-availability (undeclared pino)",
             lambda fs: any(k == "missing_dependency" and loc == "pino" for _, k, loc, _ in fs)),
            ("#7 type-class mismatch (yearsExp)",
             lambda fs: any(k == "field_type_mismatch" and loc == "yearsExp" for _, k, loc, _ in fs)),
            ("#8 invalid compound key (id_ownerId)",
             lambda fs: any(k == "prisma_invalid_compound_key" and loc == "id_ownerId" for _, k, loc, _ in fs)),
            ("#12 unknown Prisma field (input/outputTokens)",
             lambda fs: {loc for _, k, loc, _ in fs if k == "prisma_unknown_field"} >= {"inputTokens", "outputTokens"}),
            ("#13 Zod field absent from Prisma (claim/category)",
             lambda fs: {loc for _, k, loc, _ in fs if k == "field_missing_in_prisma"} >= {"claim", "category"}),
        ],
    )
    def test_each_category_caught(self, project_root, category, predicate):
        assert predicate(_run_cross_file_checks(DIRTY_SOURCES, project_root)), f"regressed: {category}"

    def test_clean_corpus_no_false_positives(self, project_root):
        # The false-PASS guard's inverse: a coherent batch yields zero error findings.
        assert _run_cross_file_checks(CLEAN_SOURCES, project_root) == set()


# --- Part 2: Zod composition audit (REQ-CKG-690a Zod audit / R1-F5/S3) ---

_AUDIT_PRISMA = "model Widget {\n  id   String @id\n  size Int?\n}\n"


def _drift_detected(zod_src: str) -> bool:
    """True iff the invented `bogus` field is flagged field_missing_in_prisma."""
    sources = {"prisma/schema.prisma": _AUDIT_PRISMA, "lib/s.ts": "import { z } from 'zod';\n" + zod_src}
    return any(
        f.kind == "field_missing_in_prisma" and f.field == "bogus" and f.severity == "error"
        for f in evaluate_cross_file_integrity(sources)
    )


# (name, zod source inventing a `bogus` field not present on the Widget model)
_COMPOSITION_FORMS = {
    "extend": "export const WidgetSchema = z.object({ id: z.string() }).extend({ bogus: z.string() });",
    "merge": "const Base = z.object({ id: z.string() });\n"
             "export const WidgetSchema = Base.merge(z.object({ bogus: z.string() }));",
    "nested": "export const WidgetSchema = z.object({ id: z.string(), nested: z.object({ bogus: z.string() }) });",
    "union": "export const WidgetSchema = z.union([z.object({ id: z.string() }), z.object({ bogus: z.string() })]);",
    "discriminated_union":
        "export const WidgetSchema = z.discriminatedUnion('t', [z.object({ t: z.literal('a'), bogus: z.string() })]);",
    "lazy": "export const WidgetSchema = z.lazy(() => z.object({ id: z.string(), bogus: z.string() }));",
    "spread_var": "const fields = { id: z.string(), bogus: z.string() };\n"
                  "export const WidgetSchema = z.object(fields);",
}


class TestZodCompositionAudit:
    """Empirical coverage map for the regex Zod extractor (answers 'is Phase 1 under-scoped?')."""

    def test_flat_object_drift_detected(self):
        # Baseline: flat top-level z.object IS covered today.
        assert _drift_detected("export const WidgetSchema = z.object({ id: z.string(), bogus: z.string() });")

    @pytest.mark.parametrize(
        "form",
        [
            pytest.param(
                name,
                marks=pytest.mark.xfail(
                    strict=True,
                    reason=f"KNOWN GAP: regex Zod extractor misses drift in z.object {name!r}; "
                           "downstream gate = tsc --noEmit (FR-4), to be superseded by SCIP-resolved "
                           "types (CKG Inc-0/Inc-1). XPASS here means the gap closed — remove the marker.",
                ),
            )
            for name in _COMPOSITION_FORMS
        ],
    )
    def test_composition_form_drift(self, form):
        # We ASSERT detection (the desired end state); currently xfails for every composition form.
        assert _drift_detected(_COMPOSITION_FORMS[form])
