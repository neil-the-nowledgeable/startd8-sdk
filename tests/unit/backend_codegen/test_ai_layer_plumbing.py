"""M-B — AI-layer plumbing: shared header, three-hash drift core, manifest/human-inputs reads.

Plumbing only (FR-MA-5 / C-5). The AI-layer *renderers* land in M-C; here we verify the reusable
substrate they'll sit on, and — critically — that the shared-header refactor is **byte-identical** to
the old per-module copies so existing owned files don't drift.
"""

from startd8.backend_codegen import _headers, derived
from startd8.backend_codegen import crud_generator
from startd8.backend_codegen import drift
from startd8.backend_codegen.provider import PydanticSQLModelProvider
from startd8.contractors.deterministic_providers import ProviderContext
from startd8.frontend_codegen.schema_renderer import schema_sha256

SHA = "a" * 64
PSHA = "b" * 64
HSHA = "c" * 64


# --------------------------------------------------------------------------- #
# Shared header — byte-identity (the refactor must not change a single byte)
# --------------------------------------------------------------------------- #

def test_header_standard_is_byte_identical_to_legacy():
    expected = (
        "# GENERATED from prisma/schema.prisma — do not edit by hand; "
        "regenerate via `startd8 generate backend`.\n"
        "# startd8-artifact: pydantic-models\n"
        "# Source of truth: the Prisma schema.\n"
        f"# schema-sha256: {SHA}"
    )
    assert _headers.header_standard("prisma/schema.prisma", SHA, "pydantic-models") == expected


def test_both_renderers_use_the_one_shared_header():
    # Re-point check: crud_generator._header and derived._header are the shared function.
    assert crud_generator._header is _headers.header_standard
    assert derived._header is _headers.header_standard


def test_header_ai_layer_carries_three_hashes():
    out = _headers.header_ai_layer("prisma/schema.prisma", SHA, PSHA, HSHA, "ai-service")
    assert "# startd8-artifact: ai-service" in out
    assert f"# schema-sha256: {SHA}" in out
    assert f"# passes-sha256: {PSHA}" in out
    assert f"# human-inputs-sha256: {HSHA}" in out


# --------------------------------------------------------------------------- #
# Header parsing helpers
# --------------------------------------------------------------------------- #

def test_embedded_passes_and_human_sha_roundtrip():
    out = _headers.header_ai_layer("prisma/schema.prisma", SHA, PSHA, HSHA, "ai-service")
    assert drift.embedded_schema_sha(out) == SHA
    assert drift.embedded_passes_sha(out) == PSHA
    assert drift.embedded_human_sha(out) == HSHA


def test_standard_header_has_no_ai_hashes():
    out = _headers.header_standard("prisma/schema.prisma", SHA, "pydantic-models")
    assert drift.embedded_passes_sha(out) is None
    assert drift.embedded_human_sha(out) is None


# --------------------------------------------------------------------------- #
# Three-hash drift core (the de-risked "ripple")
# --------------------------------------------------------------------------- #

def test_ai_layer_in_sync_when_all_three_match():
    out = _headers.header_ai_layer("prisma/schema.prisma", SHA, PSHA, HSHA, "ai-service")
    assert drift.ai_layer_stale_reason(out, schema_sha=SHA, passes_sha=PSHA, human_sha=HSHA) is None


def test_ai_layer_stale_on_any_single_input_change():
    out = _headers.header_ai_layer("prisma/schema.prisma", SHA, PSHA, HSHA, "ai-service")
    assert "schema changed" in drift.ai_layer_stale_reason(
        out, schema_sha="d" * 64, passes_sha=PSHA, human_sha=HSHA
    )
    assert "ai_passes changed" in drift.ai_layer_stale_reason(
        out, schema_sha=SHA, passes_sha="d" * 64, human_sha=HSHA
    )
    assert "human_inputs changed" in drift.ai_layer_stale_reason(
        out, schema_sha=SHA, passes_sha=PSHA, human_sha="d" * 64
    )


def test_ai_layer_stale_when_hash_header_missing():
    out = _headers.header_standard("prisma/schema.prisma", SHA, "pydantic-models")  # no ai hashes
    reason = drift.ai_layer_stale_reason(out, schema_sha=SHA, passes_sha=PSHA, human_sha=HSHA)
    assert reason is not None and "ai_passes-sha256" in reason


# --------------------------------------------------------------------------- #
# Provider reads — second/third inputs
# --------------------------------------------------------------------------- #

def test_provider_reads_manifest_and_human_inputs_conventional(tmp_path):
    (tmp_path / "prisma").mkdir()
    (tmp_path / "prisma" / "ai_passes.yaml").write_text("passes: []\n", encoding="utf-8")
    (tmp_path / "prisma" / "human_inputs.yaml").write_text("config: {}\n", encoding="utf-8")
    ctx = ProviderContext(project_root=str(tmp_path), source_anchors=())
    assert PydanticSQLModelProvider._read_manifest(ctx) == "passes: []\n"
    assert PydanticSQLModelProvider._read_human_inputs(ctx) == "config: {}\n"


def test_provider_reads_manifest_from_anchor(tmp_path):
    custom = tmp_path / "cfg"
    custom.mkdir()
    (custom / "ai_passes.yaml").write_text("passes: [x]\n", encoding="utf-8")
    ctx = ProviderContext(project_root=str(tmp_path), source_anchors=("cfg/ai_passes.yaml",))
    assert PydanticSQLModelProvider._read_manifest(ctx) == "passes: [x]\n"


def test_provider_returns_none_when_inputs_absent(tmp_path):
    ctx = ProviderContext(project_root=str(tmp_path), source_anchors=())
    assert PydanticSQLModelProvider._read_manifest(ctx) is None
    assert PydanticSQLModelProvider._read_human_inputs(ctx) is None


# --------------------------------------------------------------------------- #
# Regression: spine generation is byte-unchanged (no AI hashes leak in)
# --------------------------------------------------------------------------- #

SCHEMA = """
model Profile {
  id   String @id @default(cuid())
  name String
}
""".strip()


def test_spine_headers_unchanged_no_ai_hashes():
    from startd8.backend_codegen import render_backend

    files = dict(render_backend(SCHEMA))
    models = files["app/models.py"]
    assert "# startd8-artifact: pydantic-models" in models
    assert f"# schema-sha256: {schema_sha256(SCHEMA)}" in models
    # the spine must NOT carry the AI-layer hash lines
    assert "passes-sha256" not in models
    assert "human-inputs-sha256" not in models
    # and it stays in-sync under the existing single-input drift check
    assert drift.check_drift(SCHEMA, models).status == "in_sync"
