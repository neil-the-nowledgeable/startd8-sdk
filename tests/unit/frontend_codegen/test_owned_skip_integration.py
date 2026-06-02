"""Inc 8b — integration test for the prime-contractor owned-file skip hook.

Exercises ``PrimeContractorWorkflow._try_deterministic_file_shortcut`` directly via a stub
``self``. The core now consults the language-agnostic ``DeterministicFileProvider`` registry;
this test registers the Prisma→Zod provider explicitly (the entry point activates on install).
Verifies: an owned in-sync file is skipped ($0.00 GENERATED); stale/tampered/non-owned/
absent targets fall through to the LLM; and build files keep their prior behavior.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

# Importable now that the protobuf-runtime mismatch is fixed; skip if a leaner env can't.
prime = pytest.importorskip("startd8.contractors.prime_contractor")

from startd8.contractors import deterministic_providers  # noqa: E402
from startd8.frontend_codegen import render_zod_schema  # noqa: E402
from startd8.frontend_codegen.provider import PrismaZodFileProvider  # noqa: E402

pytestmark = pytest.mark.unit

PCW = prime.PrimeContractorWorkflow
FeatureStatus = prime.FeatureStatus


@pytest.fixture(autouse=True)
def _register_provider():
    """Register the Prisma→Zod provider (entry-point discovery needs an install)."""
    deterministic_providers.clear_providers()
    deterministic_providers.register_provider(PrismaZodFileProvider())
    deterministic_providers._DISCOVERED = True  # skip entry-point discovery in-test
    yield
    deterministic_providers.clear_providers()

SCHEMA = "model M {\n  id String @id\n  name String\n}\n"
SCHEMA_V2 = "model M {\n  id String @id\n  name String\n  extra String?\n}\n"


def _write(tmp_path, rel, text):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _stub_self(tmp_path):
    return SimpleNamespace(
        project_root=tmp_path,
        seed_upstream_anchors=["prisma/schema.prisma"],
        _DETERMINISTIC_BUILD_NAMES=PCW._DETERMINISTIC_BUILD_NAMES,
        _DETERMINISTIC_BUILD_EXTENSIONS=PCW._DETERMINISTIC_BUILD_EXTENSIONS,
        _resolve_output_dir=lambda: tmp_path,
        _save_queue_state_with_mode=lambda: None,
    )


def _feature(target_files):
    return SimpleNamespace(
        name="f", target_files=target_files, generated_files=None, status=None
    )


def _run(tmp_path, feature, schema=SCHEMA):
    _write(tmp_path, "prisma/schema.prisma", schema)
    return PCW._try_deterministic_file_shortcut(_stub_self(tmp_path), feature)


def test_owned_in_sync_file_is_skipped_at_zero_cost(tmp_path):
    _write(tmp_path, "lib/value-model.ts", render_zod_schema(SCHEMA).text)
    f = _feature(["lib/value-model.ts"])
    assert _run(tmp_path, f) is True
    assert f.status == FeatureStatus.GENERATED
    assert f.generated_files  # resolved path recorded


def test_owned_but_stale_falls_through_to_llm(tmp_path):
    _write(tmp_path, "lib/value-model.ts", render_zod_schema(SCHEMA).text)
    f = _feature(["lib/value-model.ts"])
    # Anchor is now V2 → the on-disk owned file is stale → must NOT be skipped.
    assert _run(tmp_path, f, schema=SCHEMA_V2) is None


def test_owned_but_tampered_falls_through_to_llm(tmp_path):
    tampered = render_zod_schema(SCHEMA).text.replace(
        "name: z.string(),", "name: z.number(),", 1
    )
    _write(tmp_path, "lib/value-model.ts", tampered)
    f = _feature(["lib/value-model.ts"])
    assert _run(tmp_path, f) is None


def test_non_owned_ts_falls_through_to_llm(tmp_path):
    _write(
        tmp_path, "lib/value-model.ts", "export const x = 1;\n"
    )  # no GENERATED header
    f = _feature(["lib/value-model.ts"])
    assert _run(tmp_path, f) is None


def test_absent_target_falls_through_to_llm(tmp_path):
    f = _feature(["lib/value-model.ts"])  # never written
    assert _run(tmp_path, f) is None


def test_build_file_still_skipped_without_content_check(tmp_path):
    _write(tmp_path, "package.json", '{"name":"x"}\n')
    f = _feature(["package.json"])
    assert _run(tmp_path, f) is True
    assert f.status == FeatureStatus.GENERATED


def test_mixed_owned_and_absent_build_file_falls_through(tmp_path):
    # One owned in-sync file + one missing build file → not all provided → LLM.
    _write(tmp_path, "lib/value-model.ts", render_zod_schema(SCHEMA).text)
    f = _feature(["lib/value-model.ts", "package.json"])  # package.json absent
    assert _run(tmp_path, f) is None
