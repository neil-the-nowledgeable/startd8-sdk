"""REQ-CKG-530 — adherence harness scaffold: measurement, rate, threshold, prompt.

No API cost: exercises the harness logic with a deterministic MockBackend.
"""

from __future__ import annotations

from startd8.contractors.project_knowledge.adherence import (
    RUN011_CASES,
    AdherenceCase,
    MockBackend,
    build_spec_prompt,
    measure_adherence,
    measure_adherence_structural,
    run_case,
    run_suite,
)

CASE_A = next(c for c in RUN011_CASES if c.case_id == "PI-001")
CASE_B = next(c for c in RUN011_CASES if c.case_id == "PI-002")


class TestPromptBuilding:
    def test_injection_adds_authority_section(self):
        base = build_spec_prompt(CASE_A, inject=False)
        injected = build_spec_prompt(CASE_A, inject=True)
        assert "## Prisma data model" not in base
        assert "## Prisma data model" in injected
        # scoped to the referenced entity (Capability), not the whole schema
        assert "`Capability`" in injected

    def test_injection_includes_negatives_for_path_case(self):
        injected = build_spec_prompt(CASE_B, inject=True)
        # Gap-B case references Capability + the prisma client → field set present;
        # negatives only render with a concrete TS interface, which the artifact
        # has none of here, so assert at least the field authority landed.
        assert "`Capability`" in injected

    def test_case_marker_present_for_routing(self):
        assert "[case:PI-001]" in build_spec_prompt(CASE_A, inject=False)


class TestMeasurement:
    def test_adherent_when_no_forbidden_token(self):
        assert measure_adherence("const x = { id, name, summary }", CASE_A) is True

    def test_not_adherent_when_invention_present(self):
        assert measure_adherence("const x = { id, aiRefId }", CASE_A) is False
        assert measure_adherence("import x from '@/lib/prisma'", CASE_B) is False


class TestStructuralScoring:
    # --- Gap A (Prisma field invention via db.<model> usage) ---
    def test_gapA_real_fields_adherent(self):
        code = "const c = await db.capability.update({ where: { id }, data: { score: 5 } })"
        assert measure_adherence_structural(code, CASE_A) is True

    def test_gapA_denylisted_invention_caught(self):
        code = "await db.capability.create({ data: { aiRefId: 1, name: 'x' } })"
        assert measure_adherence_structural(code, CASE_A) is False

    def test_gapA_novel_invention_caught_where_denylist_false_passes(self):
        # `bogusField` is NOT on CASE_A.forbidden → denylist FALSE-PASSES it...
        code = "await db.capability.create({ data: { bogusField: 1 } })"
        assert measure_adherence(code, CASE_A) is True          # denylist misses it
        assert measure_adherence_structural(code, CASE_A) is False  # structural catches it

    # --- Gap B (module-path invention) ---
    def test_gapB_real_module_adherent(self):
        assert measure_adherence_structural("import { db } from '@/lib/db'", CASE_B) is True

    def test_gapB_denylisted_path_caught(self):
        assert measure_adherence_structural("import { prisma } from '@/lib/prisma'", CASE_B) is False

    def test_gapB_novel_path_caught_where_denylist_false_passes(self):
        # `@/lib/database` is NOT on CASE_B.forbidden → denylist FALSE-PASSES it...
        code = "import x from '@/lib/database'"
        assert measure_adherence(code, CASE_B) is True            # denylist misses it
        assert measure_adherence_structural(code, CASE_B) is False  # structural catches it

    def test_gapB_bare_package_import_ignored(self):
        # bare npm packages are not project modules → never flagged
        assert measure_adherence_structural("import { z } from 'zod'\nimport { db } from '@/lib/db'", CASE_B) is True


class TestRateAndThreshold:
    def test_rate_computation_over_seeds(self):
        # 4 of 5 outputs clean → rate 0.8
        outs = [
            "ok id name",          # adherent
            "ok id name summary",  # adherent
            "bad aiRefId",         # not
            "ok id",               # adherent
            "ok name",             # adherent
        ]
        backend = MockBackend(outputs_by_case={"PI-001": outs})
        res = run_case(CASE_A, backend, inject=False, n_seeds=5)
        assert res.adherent == 4 and res.rate == 0.8

    def test_suite_per_gap_and_threshold_gate(self):
        backend = MockBackend(
            outputs_by_case={
                "PI-001": ["ok id name"],          # GapA clean
                "PI-004": ["ok id summary"],        # GapA clean
                "PI-002": ["import '@/lib/prisma'"],  # GapB dirty
                "PI-007": ["import '@/lib/prisma'"],  # GapB dirty
            },
        )
        report = run_suite(RUN011_CASES, backend, inject=False, n_seeds=3, threshold=0.9)
        rates = report.rate_by_gap()
        assert rates["A"] == 1.0
        assert rates["B"] == 0.0
        assert report.passes() is False  # Gap B below threshold

    def test_all_pass_when_above_threshold(self):
        backend = MockBackend(default="clean output id name summary")
        report = run_suite(RUN011_CASES, backend, inject=True, n_seeds=5, threshold=0.9)
        assert report.passes() is True


def test_run011_cases_cover_both_gaps():
    gaps = {c.gap for c in RUN011_CASES}
    assert gaps == {"A", "B"}
    assert all(c.forbidden for c in RUN011_CASES)  # every case has invention tokens
