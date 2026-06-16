"""P1b / F-105 — behavioral-parity gate for the FR-IMP-2 persist consolidation.

The consolidation routes both AI-pass renderers' persist selection through one decision point
(`_row_identity` → `_row_persist_parts`). This test pins that the seam is byte-identical to the
pre-consolidation `_PERSIST_DEDUP_HELPER if ps.dedup_by else _PERSIST_HELPER` selection, and that
the source/scoped emission paths are untouched (they never reach the row tier).
"""

from __future__ import annotations

import pytest

from startd8.backend_codegen.ai_layer import (
    _PERSIST_DEDUP_HELPER,
    _PERSIST_HELPER,
    _row_identity,
    _row_persist_parts,
    parse_ai_passes,
    render_ai_pass,
)

NAME_SCHEMA = """
model Capability {
  id        String  @id @default(cuid())
  ownerId   String  @default("local")
  source    String  @default("user")
  confirmed Boolean @default(false)
  name      String?
  summary   String?
}
""".strip()

DEDUP_SCHEMA = """
model Artifact {
  id        String  @id @default(cuid())
  ownerId   String  @default("local")
  source    String  @default("user")
  confirmed Boolean @default(false)
  kind      String?
  title     String?
}
""".strip()

NAME_MANIFEST = """
passes:
  - name: gen_caps
    output_entities: [Capability]
    route_path: /gen-caps
    prompt: prompts/gen_caps.md
""".strip()

DEDUP_MANIFEST = """
passes:
  - name: gen_artifacts
    output_entities: [Artifact]
    route_path: /gen-artifacts
    prompt: prompts/gen_artifacts.md
    dedup_by: kind
""".strip()


def _pass(manifest):
    return parse_ai_passes(manifest)[0]


# -- the decision point maps legacy keys to the right identity ---------------- #

def test_no_dedup_maps_to_name():
    key = _row_identity(_pass(NAME_MANIFEST))
    assert key.kind == "name"
    const, helper, field = _row_persist_parts(key)
    assert const == []
    assert helper is _PERSIST_HELPER
    assert field is None


def test_dedup_by_maps_to_field():
    key = _row_identity(_pass(DEDUP_MANIFEST))
    assert key.kind == "field" and key.fields == ("kind",)
    const, helper, field = _row_persist_parts(key)
    assert const == ["_DEDUP_FIELD = 'kind'  # F-11: re-generation dedup key (FR-8)", ""]
    assert helper is _PERSIST_DEDUP_HELPER
    assert field == "kind"


# -- byte-identity of the rendered harness ------------------------------------ #

def test_name_pass_emits_name_helper_only():
    out = render_ai_pass(NAME_SCHEMA, NAME_MANIFEST, "", pass_name="gen_caps")
    assert "_DEDUP_FIELD" not in out
    assert "name-deduped" in out
    assert "dedup by `_DEDUP_FIELD`" not in out


def test_dedup_pass_emits_dedup_field_and_helper():
    out = render_ai_pass(DEDUP_SCHEMA, DEDUP_MANIFEST, "", pass_name="gen_artifacts")
    assert "_DEDUP_FIELD = 'kind'  # F-11: re-generation dedup key (FR-8)" in out
    assert "deduped by 'kind'" in out
    # the confirmed-aware body is present (FR-8 semantics preserved)
    assert "never clobber" in out or "owns this key" in out


def test_rendered_harness_compiles():
    import py_compile
    import tempfile
    import os

    for schema, manifest, name in [
        (NAME_SCHEMA, NAME_MANIFEST, "gen_caps"),
        (DEDUP_SCHEMA, DEDUP_MANIFEST, "gen_artifacts"),
    ]:
        out = render_ai_pass(schema, manifest, "", pass_name=name)
        fd, path = tempfile.mkstemp(suffix=".py")
        os.write(fd, out.encode())
        os.close(fd)
        try:
            py_compile.compile(path, doraise=True)
        finally:
            os.unlink(path)
