"""Inc 8b — owned-file skip decision helpers (the C2-safe pipeline-hook predicate).

The prime-contractor hook skips an owned generated file ONLY when it is currently in-sync
with the schema. These pure helpers encode that decision; header presence alone never
qualifies (a stale / hand-edited / header-only file must fall through to the LLM).
"""

from __future__ import annotations

import pytest

from startd8.frontend_codegen import (
    embedded_source_file,
    is_owned_generated_file,
    owned_file_in_sync,
    render_zod_schema,
)

pytestmark = pytest.mark.unit

SCHEMA = "model M {\n  id String @id\n  name String\n}"
SCHEMA_V2 = "model M {\n  id String @id\n  name String\n  extra String?\n}"


def test_is_owned_generated_file():
    gen = render_zod_schema(SCHEMA).text
    assert is_owned_generated_file(gen) is True
    assert is_owned_generated_file("export const MSchema = z.object({});") is False
    assert is_owned_generated_file("") is False


def test_embedded_source_file_recovered_from_header():
    gen = render_zod_schema(SCHEMA, source_file="db/schema.prisma").text
    assert embedded_source_file(gen) == "db/schema.prisma"
    assert embedded_source_file("no header") is None


def test_in_sync_true_for_fresh_render():
    gen = render_zod_schema(SCHEMA).text
    assert owned_file_in_sync(SCHEMA, gen) is True


def test_in_sync_uses_embedded_label_so_nondefault_label_still_matches():
    # Recovering the label from the header avoids a false "tampered" (audit M3).
    gen = render_zod_schema(SCHEMA, source_file="custom/path/schema.prisma").text
    assert owned_file_in_sync(SCHEMA, gen) is True


def test_in_sync_false_when_schema_changed():
    gen = render_zod_schema(SCHEMA).text  # generated from v1
    assert owned_file_in_sync(SCHEMA_V2, gen) is False  # schema is now v2 → stale


def test_in_sync_false_when_body_tampered():
    gen = render_zod_schema(SCHEMA).text
    tampered = gen.replace("name: z.string(),", "name: z.number(),", 1)
    assert owned_file_in_sync(SCHEMA, tampered) is False


def test_in_sync_false_without_header():
    assert owned_file_in_sync(SCHEMA, "export const MSchema = z.object({});") is False


def test_in_sync_false_for_header_only_truncated_body():
    # A crash-truncated file: header present, body missing → must NOT be treated as provided.
    gen = render_zod_schema(SCHEMA).text
    header_only = gen.split("export const")[0]  # keep header + import, drop all schemas
    assert is_owned_generated_file(header_only) is True  # header is there...
    assert owned_file_in_sync(SCHEMA, header_only) is False  # ...but not in-sync
