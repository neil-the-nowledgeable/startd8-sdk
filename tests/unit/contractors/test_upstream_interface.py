"""Tests for intra-batch inter-feature contract propagation (RUN-008 FR-1/2/3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.exceptions import MissingUpstreamArtifact
from startd8.contractors.upstream_interface import (
    build_upstream_interfaces,
    extract_import_specifiers,
    extract_ts_exports,
    render_upstream_interfaces,
    resolve_specifier_to_paths,
)

ZOD = Path(__file__).parents[1] / "validators" / "fixtures" / "run008_value_model.ts"

# the real run-008 consumer (broken import) shape
ROUTE_ASIS = """\
import { db } from '@/lib/db';
import { ProfileSchema } from '@/lib/schemas';
import { z } from 'zod';
"""


class TestExportExtraction:
    def test_extracts_real_run008_exports(self):
        exports = extract_ts_exports(ZOD.read_text())
        # the producer's REAL interface — what the consumer should import
        assert "ProfileSchema" in exports
        assert "ProofPointSchema" in exports
        assert "MetricSchema" in exports
        # `export type Profile = z.infer<...>` style type exports too
        assert "Profile" in exports

    def test_export_list_and_default(self):
        src = "export { foo, bar as baz };\nexport default function App() {}"
        ex = extract_ts_exports(src)
        assert {"foo", "baz", "default"} <= ex
        assert "bar" not in ex  # aliased — only the visible name


class TestImportResolution:
    def test_extract_specifiers(self):
        specs = extract_import_specifiers(ROUTE_ASIS)
        assert "@/lib/db" in specs
        assert "@/lib/schemas" in specs
        assert "zod" in specs

    def test_resolve_alias_to_producer(self):
        candidates = ["lib/value-model.ts", "lib/db.ts", "app/page.tsx"]
        # the CORRECT specifier resolves to the producer file
        assert resolve_specifier_to_paths("@/lib/value-model", candidates) == ["lib/value-model.ts"]
        # the run-008 BUG: '@/lib/schemas' resolves to nothing (no such producer)
        assert resolve_specifier_to_paths("@/lib/schemas", candidates) == []
        # bare package import is not a sibling
        assert resolve_specifier_to_paths("zod", candidates) == []

    def test_resolve_relative(self):
        candidates = ["app/api/profile/helpers.ts", "lib/db.ts"]
        got = resolve_specifier_to_paths(
            "./helpers", candidates, importer_path="app/api/profile/route.ts"
        )
        assert got == ["app/api/profile/helpers.ts"]


class TestUpstreamAssembly:
    def test_present_producer_yields_real_exports(self, tmp_path):
        (tmp_path / "lib").mkdir()
        (tmp_path / "lib" / "value-model.ts").write_text(ZOD.read_text())
        ifaces = build_upstream_interfaces(
            producer_files=["lib/value-model.ts"],
            project_root=str(tmp_path),
            import_specifiers={"lib/value-model.ts": "@/lib/value-model"},
        )
        assert len(ifaces) == 1
        assert "ProfileSchema" in ifaces[0].exports
        assert ifaces[0].import_specifier == "@/lib/value-model"

    def test_missing_declared_producer_blocks_loudly(self, tmp_path):
        # FR-2: a declared upstream that isn't on disk must raise, not be invented
        with pytest.raises(MissingUpstreamArtifact) as ei:
            build_upstream_interfaces(
                producer_files=["lib/value-model.ts"],
                project_root=str(tmp_path),
                require_present=True,
            )
        assert ei.value.missing_path == "lib/value-model.ts"
        assert ei.value.root_cause == "cross_file_contract"

    def test_missing_optional_producer_skipped(self, tmp_path):
        ifaces = build_upstream_interfaces(
            producer_files=["lib/value-model.ts"],
            project_root=str(tmp_path),
            require_present=False,
        )
        assert ifaces == []

    def test_render(self, tmp_path):
        (tmp_path / "lib").mkdir()
        (tmp_path / "lib" / "value-model.ts").write_text("export const ProfileSchema = 1;\n")
        ifaces = build_upstream_interfaces(
            producer_files=["lib/value-model.ts"], project_root=str(tmp_path),
        )
        out = render_upstream_interfaces(ifaces)
        assert "lib/value-model.ts" in out
        assert "ProfileSchema" in out
        assert "import EXACTLY these" in out
        assert render_upstream_interfaces([]) == ""
