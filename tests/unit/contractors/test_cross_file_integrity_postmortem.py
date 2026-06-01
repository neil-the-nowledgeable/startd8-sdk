"""RUN-008 FR-10 — cross-file integrity wired into the postmortem.

Two layers:
- the pure batch function ``evaluate_cross_file_integrity`` (detector-regression
  lock per FR-11 — fed the run-008 sources directly), and
- the postmortem integration: a feature that ships a Zod schema diverging from
  the Prisma model is flipped to FAIL with the cross-file root cause/stage.
"""

from __future__ import annotations

from pathlib import Path

from startd8.contractors.prime_postmortem import (
    FeaturePostMortem,
    PipelineStage,
    PrimePostMortemEvaluator,
    RootCause,
)
from startd8.validators.prisma_zod_symmetry import evaluate_cross_file_integrity

FIX = Path(__file__).parents[1] / "validators" / "fixtures"
PRISMA = FIX / "run008_schema.prisma"
ZOD = FIX / "run008_value_model.ts"


class TestBatchFunction:
    def test_run008_sources_flag_errors_with_source_file(self):
        sources = {
            "prisma/schema.prisma": PRISMA.read_text(),
            "lib/value-model.ts": ZOD.read_text(),
        }
        findings = evaluate_cross_file_integrity(sources)
        errors = [f for f in findings if f.severity == "error"]
        assert errors, "run-008 sources must produce cross-file errors"
        assert any(f.kind == "fk_invented" and f.field == "profileId" for f in errors)
        assert any(f.kind == "field_type_mismatch" and f.field == "value" for f in errors)
        # every finding is attributed to the Zod file that declared it
        assert all(f.source_file == "lib/value-model.ts" for f in errors)

    def test_no_prisma_means_no_findings(self):
        # a Python-only (or Zod-only) batch must incur zero findings
        assert evaluate_cross_file_integrity({"app/main.py": "print('hi')"}) == []
        assert evaluate_cross_file_integrity(
            {"lib/value-model.ts": ZOD.read_text()}
        ) == []  # zod present but no prisma → skip

    def test_coherent_batch_clean(self):
        sources = {
            "prisma/schema.prisma": "model Widget {\n id String @id @default(cuid())\n name String\n}\n",
            "lib/schemas.ts": "export const WidgetSchema = z.object({ id: z.string(), name: z.string() });",
        }
        assert [f for f in evaluate_cross_file_integrity(sources) if f.severity == "error"] == []


class TestPostmortemIntegration:
    def _features(self):
        prisma_feat = FeaturePostMortem(
            feature_id="PI-010", name="prisma schema", status="completed", success=True,
            generated_files=[str(PRISMA)], verdict="PASS", requirement_score=1.0,
        )
        zod_feat = FeaturePostMortem(
            feature_id="PI-011", name="zod value-model", status="completed", success=True,
            generated_files=[str(ZOD)], verdict="PASS", requirement_score=1.0,
        )
        return prisma_feat, zod_feat

    def test_zod_feature_flipped_to_fail(self):
        prisma_feat, zod_feat = self._features()
        ev = PrimePostMortemEvaluator()
        ev._evaluate_cross_file_integrity([prisma_feat, zod_feat], project_root=str(FIX))

        # the Zod-owning feature is now an honest failure
        assert zod_feat.success is False
        assert zod_feat.verdict == "FAIL:cross_file"
        assert zod_feat.disk_quality_score == 0.0
        assert zod_feat.root_cause == RootCause.CROSS_FILE_CONTRACT
        assert zod_feat.pipeline_stage == PipelineStage.CROSS_FEATURE_CONTRACT
        assert zod_feat.semantic_error_count > 0
        assert zod_feat.error_message
        kinds = {i["category"] for i in zod_feat.disk_compliance.semantic_issues}
        assert "fk_invented" in kinds or "field_missing_in_prisma" in kinds

        # the Prisma producer feature is untouched (divergence attributed to consumer)
        assert prisma_feat.success is True

    def test_clean_batch_does_not_flip(self, tmp_path):
        (tmp_path / "prisma").mkdir()
        (tmp_path / "prisma" / "schema.prisma").write_text(
            "model Widget {\n id String @id @default(cuid())\n name String\n}\n"
        )
        (tmp_path / "schemas.ts").write_text(
            "export const WidgetSchema = z.object({ id: z.string(), name: z.string() });"
        )
        feat = FeaturePostMortem(
            feature_id="W", name="widget", status="completed", success=True,
            generated_files=["schemas.ts", "prisma/schema.prisma"], verdict="PASS",
        )
        ev = PrimePostMortemEvaluator()
        ev._evaluate_cross_file_integrity([feat], project_root=str(tmp_path))
        assert feat.success is True
        assert feat.verdict == "PASS"
