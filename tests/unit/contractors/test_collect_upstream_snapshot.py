"""REQ-CKG-540 — characterization snapshot of ``_collect_upstream_interfaces``.

Captured BEFORE the CKG Phase-2 refactor that replaces the
``_feature_mirrors_data_model`` keyword gate with structural relevance scoping
(REQ-CKG-524/527). These golden strings lock the seam's current byte-output on
the at-risk branches so the refactor can prove behaviour parity — the same
discipline as the Phase-1 690a regression lock. "Keep the Mode-A/B tests green"
is necessary but not sufficient; those tests assert substrings, not exact output
on the empty/warning branches.

If a later step intentionally changes this output, update the golden here in the
same commit, with the reason — never silently.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from startd8.contractors.prime_contractor import PrimeContractorWorkflow

_collect = PrimeContractorWorkflow._collect_upstream_interfaces
_mirrors = PrimeContractorWorkflow._feature_mirrors_data_model

# --- golden output (captured from current behaviour, 2026-06-01) ----------------

GOLDEN_TS = (
    "## Upstream module interfaces (already generated — import EXACTLY these)\n"
    "Import from these real module paths and use ONLY these exported symbols. "
    "Do not invent module names or export names.\n"
    "- `lib/db.ts` exports: db, prisma"
)

GOLDEN_PRISMA = (
    "## Prisma data model — mirror these field names/types EXACTLY\n"
    "Zod/TypeScript schemas MUST use these exact field names and compatible types. "
    "Do NOT invent fields (no `bio` when Prisma declares `summary`) or foreign keys "
    "the model does not declare.\n"
    "- `Capability`: id: String, name: String, score: Float?\n"
    "- `Outcome`: id: String, label: String"
)

# REQ-CKG-522 (added in the Phase-2 seam refactor, 2026-06-01): features that
# import real upstream modules now also receive explicit module-path negatives.
# This is an INTENTIONAL change to S1/S3 (they gained this section); the edge and
# Prisma branches (S2/S4/S5/S6/S7) remain byte-identical, proving the refactor
# only changed what it meant to. Seeds are filtered to the project's real modules
# (here `@/lib/db` exists → the AI-service negative is dropped).
GOLDEN_NEGATIVES = (
    "## Do NOT use these invented module paths\n"
    "- `@/lib/prisma` is not a module path — use `@/lib/db` (the Prisma client)\n"
    "- `@/lib/db/` is not a module path — use `@/lib/db` (no per-model sub-paths)"
)

GOLDEN_TS_WITH_NEGATIVES = GOLDEN_TS + "\n\n" + GOLDEN_NEGATIVES
GOLDEN_COMBINED = GOLDEN_TS + "\n\n" + GOLDEN_NEGATIVES + "\n\n" + GOLDEN_PRISMA

_PRISMA_SCHEMA = (
    "model Capability {\n id String @id @default(cuid())\n name String\n"
    " score Float?\n outcomes Outcome[]\n}\n"
    "model Outcome {\n id String @id\n label String\n}\n"
)


def _stub(anchors, project_root, queue=None):
    return SimpleNamespace(
        seed_upstream_anchors=anchors, project_root=str(project_root),
        queue=queue, _feature_mirrors_data_model=_mirrors,
    )


def _feature(**kw):
    kw.setdefault("dependencies", [])
    kw.setdefault("target_files", [])
    kw.setdefault("description", "")
    kw.setdefault("name", "X")
    return SimpleNamespace(**kw)


def _project(tmp_path, *, ts=False, prisma=False):
    if ts:
        (tmp_path / "lib").mkdir(exist_ok=True)
        (tmp_path / "lib" / "db.ts").write_text(
            "export const db = {};\nexport const prisma = db;\n"
        )
    if prisma:
        (tmp_path / "prisma").mkdir(exist_ok=True)
        (tmp_path / "prisma" / "schema.prisma").write_text(_PRISMA_SCHEMA)
    return tmp_path


class TestCharacterizationSnapshot:
    def test_s1_mode_b_ts_anchor_inherited(self, tmp_path):
        d = _project(tmp_path, ts=True)
        out = _collect(
            _stub(["lib/db.ts"], d),
            _feature(name="Cap API", target_files=["app/api/cap.ts"]),
        )
        assert out == GOLDEN_TS_WITH_NEGATIVES

    def test_s2_prisma_branch_fires(self, tmp_path):
        d = _project(tmp_path, prisma=True)
        out = _collect(
            _stub(["prisma/schema.prisma"], d),
            _feature(name="cap schema", target_files=["lib/value-model.ts"],
                     description="zod schema mirror"),
        )
        assert out == GOLDEN_PRISMA

    def test_s3_combined_ts_and_prisma(self, tmp_path):
        d = _project(tmp_path, ts=True, prisma=True)
        out = _collect(
            _stub(["lib/db.ts", "prisma/schema.prisma"], d),
            _feature(name="cap schema", target_files=["lib/schemas.ts"]),
        )
        assert out == GOLDEN_COMBINED

    def test_s4_no_anchors_empty(self, tmp_path):
        assert _collect(_stub([], tmp_path), _feature()) == ""

    def test_s5_absent_anchor_warning_path_empty(self, tmp_path):
        # declared anchor not on disk → FR-4 warning branch, empty render
        assert _collect(_stub(["lib/missing.ts"], tmp_path), _feature()) == ""

    def test_s6_prisma_present_but_feature_not_mirror_empty(self, tmp_path):
        # the keyword gate currently SKIPS this (the likely Gap-A miss the
        # refactor fixes) — locked so the change is visible, not silent.
        d = _project(tmp_path, prisma=True)
        out = _collect(
            _stub(["prisma/schema.prisma"], d),
            _feature(target_files=["app/page.tsx"], name="ui page"),
        )
        assert out == ""

    def test_s7_mode_a_producer_not_on_disk_empty(self, tmp_path):
        dep = _feature(name="producer", target_files=["lib/gen.ts"])  # not written
        queue = SimpleNamespace(
            get_feature=lambda fid: dep if fid == "DEP" else None
        )
        stub = SimpleNamespace(
            seed_upstream_anchors=[], project_root=str(tmp_path), queue=queue,
            _feature_mirrors_data_model=_mirrors,
        )
        out = _collect(stub, _feature(name="consumer", dependencies=["DEP"]))
        assert out == ""
