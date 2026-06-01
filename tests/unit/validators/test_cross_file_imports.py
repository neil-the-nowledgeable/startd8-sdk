"""Tests for the toolchain-free unresolvable-import signature (RUN-009 Fix 3).

Reproduces the run-009 failure shape: a batch generated on a wiped foundation
(no Prisma, no node_modules) that imports invented module paths (`@/lib/prisma`)
must FAIL — the tsc gate can't run unprovisioned, so this pure-Python check is
the one that catches it.
"""

from __future__ import annotations

from pathlib import Path

from startd8.validators.cross_file_imports import scan_unresolvable_imports


class TestScan:
    def test_run009_shape(self):
        # F-104 service imports an invented @/lib/prisma + a real same-batch sibling
        sources = {
            "lib/value-model.ts": "import { z } from 'zod';\nexport const S = z.object({});",
            "lib/ai/service.ts": (
                "import prisma from '@/lib/prisma';\n"          # invented → unresolvable
                "import { S } from '@/lib/value-model';\n"      # same-batch sibling → resolves
                "import pino from 'pino';\n"                    # bare package → out of scope (not flagged)
            ),
        }
        v = scan_unresolvable_imports(sources, project_root="/nonexistent")
        specs = {x.specifier for x in v}
        assert "@/lib/prisma" in specs                 # the invented import is flagged
        assert "@/lib/value-model" not in specs        # resolved via the generated batch
        assert "pino" not in specs                     # bare package not handled here
        assert all(x.kind == "unresolvable_import" and x.severity == "error" for x in v)
        assert v[0].source_file == "lib/ai/service.ts"

    def test_wiped_prerequisite_flagged(self):
        # @/lib/db was the M1 anchor that --fresh wiped → now unresolvable
        sources = {"app/api/profile/route.ts": "import { db } from '@/lib/db';"}
        v = scan_unresolvable_imports(sources, project_root="/nonexistent")
        assert [x.specifier for x in v] == ["@/lib/db"]

    def test_resolves_against_on_disk_project_file(self, tmp_path):
        (tmp_path / "lib").mkdir()
        (tmp_path / "lib" / "db.ts").write_text("export const db = {};")
        sources = {"app/api/x/route.ts": "import { db } from '@/lib/db';"}
        # @/lib/db now exists on disk → resolved, no violation
        assert scan_unresolvable_imports(sources, str(tmp_path)) == []

    def test_relative_import_resolution(self, tmp_path):
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "helpers.ts").write_text("export const h = 1;")
        sources = {"app/route.ts": "import { h } from './helpers';\nimport { z } from './missing';"}
        v = scan_unresolvable_imports(sources, str(tmp_path))
        assert [x.specifier for x in v] == ["./missing"]

    def test_clean_batch_no_false_positives(self):
        sources = {
            "lib/a.ts": "export const a = 1;",
            "lib/b.ts": "import { a } from '@/lib/a';\nimport React from 'react';",
        }
        assert scan_unresolvable_imports(sources, "/nonexistent") == []


class TestPostmortemIntegration:
    def test_unresolvable_import_fails_feature_without_prisma(self, tmp_path):
        """Run-009 condition: no .prisma on disk, but an invented import → FAIL."""
        from startd8.contractors.prime_postmortem import (
            FeaturePostMortem, PrimePostMortemEvaluator, RootCause,
        )
        (tmp_path / "lib" / "ai").mkdir(parents=True)
        (tmp_path / "lib" / "ai" / "service.ts").write_text(
            "import prisma from '@/lib/prisma';\nexport const svc = {};\n"
        )
        feat = FeaturePostMortem(
            feature_id="PI-007", name="AI service", status="completed", success=True,
            verdict="PASS", generated_files=["lib/ai/service.ts"],
        )
        ev = PrimePostMortemEvaluator()
        ev._evaluate_cross_file_integrity([feat], project_root=str(tmp_path))

        assert feat.success is False
        assert feat.verdict == "FAIL:cross_file"
        assert feat.root_cause == RootCause.CROSS_FILE_CONTRACT
        cats = {i["category"] for i in feat.disk_compliance.semantic_issues}
        assert "unresolvable_import" in cats
