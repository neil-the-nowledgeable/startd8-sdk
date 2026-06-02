"""Inc 8 — drift / staleness checking (FR-11).

Two-stage check with the exit-code contract: in-sync (0), stale vs tampered vs missing (1).
"""

from __future__ import annotations

import pytest

from startd8.frontend_codegen import check_drift, embedded_schema_sha, render_zod_schema
from startd8.frontend_codegen.drift import DRIFT, IN_SYNC

pytestmark = pytest.mark.unit

SCHEMA = "model M {\n  id String @id\n  name String\n}"
SCHEMA_V2 = "model M {\n  id String @id\n  name String\n  extra String?\n}"
SRC = "prisma/schema.prisma"


def _generated(schema=SCHEMA):
    return render_zod_schema(schema, source_file=SRC).text


def test_in_sync():
    ondisk = _generated()
    result = check_drift(SCHEMA, ondisk, source_file=SRC)
    assert result.status == "in_sync"
    assert result.exit_code == IN_SYNC


def test_missing_file_is_drift():
    result = check_drift(SCHEMA, None, source_file=SRC)
    assert result.status == "missing"
    assert result.exit_code == DRIFT


def test_stale_when_schema_changed():
    ondisk = _generated(SCHEMA)  # generated from v1
    result = check_drift(SCHEMA_V2, ondisk, source_file=SRC)  # schema is now v2
    assert result.status == "stale"
    assert result.exit_code == DRIFT


def test_tampered_when_body_hand_edited():
    ondisk = _generated(SCHEMA)
    # Edit the body but not the schema → header sha still matches current, content differs.
    tampered = ondisk.replace("name: z.string(),", "name: z.number(),", 1)
    assert tampered != ondisk
    result = check_drift(SCHEMA, tampered, source_file=SRC)
    assert result.status == "tampered"
    assert result.exit_code == DRIFT


def test_tampered_when_no_header():
    ondisk = "export const MSchema = z.object({\n  id: z.string(),\n});\n"
    result = check_drift(SCHEMA, ondisk, source_file=SRC)
    assert result.status == "tampered"
    assert result.exit_code == DRIFT


def test_embedded_schema_sha_extraction():
    ondisk = _generated()
    sha = embedded_schema_sha(ondisk)
    assert sha is not None and len(sha) == 64
    assert embedded_schema_sha("no header here") is None
