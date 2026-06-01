"""RUN-009 Approach-B classifier signatures 1-3 (toolchain-free)."""

from __future__ import annotations

from startd8.validators.cross_file_imports import scan_missing_dependencies
from startd8.validators.prisma_usage import scan_prisma_usage

PRISMA = """\
model Profile {
  id        String @id @default(cuid())
  ownerId   String @default("local")
  summary   String?
  yearsExp  Int?
}
model AiCall {
  id             String @id @default(cuid())
  promptTokens   Int?
  responseTokens Int?
}
"""


class TestMissingDependency:
    def test_undeclared_package_flagged(self, tmp_path):
        (tmp_path / "package.json").write_text('{"dependencies": {"next": "14", "zod": "3"}}')
        sources = {
            "lib/a.ts": "import pino from 'pino';\nimport { z } from 'zod';\n"
                        "import { NextResponse } from 'next/server';\nimport fs from 'node:fs';\n"
                        "import { x } from './local';\nimport { y } from '@/lib/db';\n",
        }
        v = scan_missing_dependencies(sources, str(tmp_path))
        specs = {x.specifier for x in v}
        assert "pino" in specs                 # undeclared → flagged
        assert "zod" not in specs              # declared
        assert "next/server" not in specs      # next is declared (package = next)
        assert "node:fs" not in specs          # node builtin
        assert "./local" not in specs and "@/lib/db" not in specs  # relative / alias
        assert all(x.kind == "missing_dependency" for x in v)

    def test_no_package_json_no_false_positives(self, tmp_path):
        assert scan_missing_dependencies({"a.ts": "import pino from 'pino';"}, str(tmp_path)) == []


class TestPrismaUsage:
    def _w(self, tmp_path):
        (tmp_path / "prisma").mkdir(exist_ok=True)
        (tmp_path / "prisma" / "schema.prisma").write_text(PRISMA)
        return str(tmp_path)

    def test_non_unique_where_flagged(self, tmp_path):
        root = self._w(tmp_path)
        sources = {"r.ts": "await db.profile.findUnique({ where: { ownerId: 'local' } });"}
        kinds = {(v.kind, v.field) for v in scan_prisma_usage(sources, root)}
        assert ("prisma_where_not_unique", "ownerId") in kinds

    def test_invalid_compound_key_flagged(self, tmp_path):
        root = self._w(tmp_path)
        sources = {"r.ts": "await db.profile.findUnique({ where: { id_ownerId: { id: 'x', ownerId: 'local' } } });"}
        kinds = {(v.kind, v.field) for v in scan_prisma_usage(sources, root)}
        assert ("prisma_invalid_compound_key", "id_ownerId") in kinds

    def test_unknown_data_field_flagged(self, tmp_path):
        root = self._w(tmp_path)
        sources = {"r.ts": "await db.aiCall.create({ data: { inputTokens: 1, outputTokens: 2 } });"}
        fields = {v.field for v in scan_prisma_usage(sources, root) if v.kind == "prisma_unknown_field"}
        assert "inputTokens" in fields and "outputTokens" in fields  # real fields are promptTokens/responseTokens

    def test_valid_usage_clean(self, tmp_path):
        root = self._w(tmp_path)
        sources = {"r.ts": "await db.profile.findUnique({ where: { id: 'x' } });\n"
                           "await db.profile.update({ where: { id: 'x' }, data: { summary: 's', yearsExp: 3 } });"}
        assert scan_prisma_usage(sources, root) == []

    def test_findFirst_allows_non_unique(self, tmp_path):
        root = self._w(tmp_path)
        sources = {"r.ts": "await db.profile.findFirst({ where: { ownerId: 'local' } });"}
        # findFirst is not a unique-where method → ownerId filter is fine
        assert [v for v in scan_prisma_usage(sources, root) if v.kind == "prisma_where_not_unique"] == []


class TestNoCommentFalsePositives:
    def test_comment_key_not_flagged(self, tmp_path):
        from startd8.validators.prisma_usage import scan_prisma_usage
        (tmp_path / "prisma").mkdir(exist_ok=True)
        (tmp_path / "prisma" / "schema.prisma").write_text(PRISMA)
        # a `// CRITICAL: ...` comment inside the data object must NOT be parsed as a key
        sources = {"r.ts": (
            "await db.aiCall.create({ data: {\n"
            "  // CRITICAL: value field is NEVER included\n"
            "  promptTokens: 1,\n"
            "} });"
        )}
        fields = {v.field for v in scan_prisma_usage(sources, str(tmp_path))}
        assert "CRITICAL" not in fields
        assert "promptTokens" not in fields  # real field → not flagged
