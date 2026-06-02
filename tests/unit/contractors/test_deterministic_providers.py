"""DeterministicFileProvider registry + the Prisma→Zod provider (the core-decoupling seam).

The prime-contractor skip-hook asks the registry "is this file deterministically provided +
in-sync?" without importing any stack. Tests the registry mechanics and that the Prisma/Zod
logic now lives behind the protocol (not in the core).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.contractors import deterministic_providers as dp
from startd8.contractors.deterministic_providers import (
    ProviderContext,
    is_deterministically_provided,
)
from startd8.frontend_codegen import render_zod_schema
from startd8.frontend_codegen.provider import PrismaZodFileProvider

pytestmark = pytest.mark.unit

SCHEMA = "model M {\n  id String @id\n  name String\n}\n"


@pytest.fixture(autouse=True)
def _clean_registry():
    dp.clear_providers()
    dp._DISCOVERED = True  # don't pull entry points during unit tests
    yield
    dp.clear_providers()


def _ctx(tmp_path):
    return ProviderContext(
        project_root=tmp_path, source_anchors=("prisma/schema.prisma",)
    )


def _write_schema(tmp_path):
    p = tmp_path / "prisma" / "schema.prisma"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(SCHEMA, encoding="utf-8")


# --------------------------------------------------------------------------- #
# Registry mechanics (stack-agnostic)
# --------------------------------------------------------------------------- #


def test_no_providers_means_not_provided(tmp_path):
    assert (
        is_deterministically_provided(tmp_path / "x.ts", "anything", _ctx(tmp_path))
        is False
    )


def test_registry_gates_on_owns_and_in_sync(tmp_path):
    class Dummy:
        name = "dummy"

        def __init__(self, owns, in_sync):
            self._owns, self._in_sync = owns, in_sync

        def owns(self, path, content):
            return self._owns

        def is_in_sync(self, path, content, context):
            return self._in_sync

    p = tmp_path / "x.ts"
    # owns but not in-sync → not provided
    dp.clear_providers()
    dp._DISCOVERED = True
    dp.register_provider(Dummy(owns=True, in_sync=False))
    assert is_deterministically_provided(p, "c", _ctx(tmp_path)) is False
    # owns and in-sync → provided
    dp.clear_providers()
    dp._DISCOVERED = True
    dp.register_provider(Dummy(owns=True, in_sync=True))
    assert is_deterministically_provided(p, "c", _ctx(tmp_path)) is True
    # doesn't own → not provided (even if it would be in-sync)
    dp.clear_providers()
    dp._DISCOVERED = True
    dp.register_provider(Dummy(owns=False, in_sync=True))
    assert is_deterministically_provided(p, "c", _ctx(tmp_path)) is False


def test_a_throwing_provider_never_causes_a_false_skip(tmp_path):
    class Boom:
        name = "boom"

        def owns(self, path, content):
            raise RuntimeError("kaboom")

        def is_in_sync(self, path, content, context):
            return True

    dp.register_provider(Boom())
    # The error is swallowed → not provided (safe: falls through to the LLM, never skips).
    assert (
        is_deterministically_provided(tmp_path / "x.ts", "c", _ctx(tmp_path)) is False
    )


# --------------------------------------------------------------------------- #
# PrismaZodFileProvider (the TS/Prisma logic, now behind the protocol)
# --------------------------------------------------------------------------- #


def test_prisma_provider_owns_only_generated_files():
    prov = PrismaZodFileProvider()
    gen = render_zod_schema(SCHEMA).text
    assert prov.owns(Path("lib/value-model.ts"), gen) is True
    assert prov.owns(Path("lib/value-model.ts"), "export const x = 1;") is False


def test_prisma_provider_in_sync_true_for_fresh_render(tmp_path):
    _write_schema(tmp_path)
    prov = PrismaZodFileProvider()
    gen = render_zod_schema(SCHEMA, source_file="prisma/schema.prisma").text
    assert prov.is_in_sync(tmp_path / "lib/value-model.ts", gen, _ctx(tmp_path)) is True


def test_prisma_provider_not_in_sync_when_no_schema(tmp_path):
    # No schema on disk → cannot verify → not in-sync (safe).
    prov = PrismaZodFileProvider()
    gen = render_zod_schema(SCHEMA).text
    assert (
        prov.is_in_sync(tmp_path / "lib/value-model.ts", gen, _ctx(tmp_path)) is False
    )


def test_end_to_end_via_registry(tmp_path):
    _write_schema(tmp_path)
    dp.register_provider(PrismaZodFileProvider())
    gen = render_zod_schema(SCHEMA, source_file="prisma/schema.prisma").text
    out = tmp_path / "lib" / "value-model.ts"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(gen, encoding="utf-8")
    assert is_deterministically_provided(out, gen, _ctx(tmp_path)) is True
    # tamper → not provided
    assert (
        is_deterministically_provided(
            out,
            gen.replace("name: z.string(),", "name: z.number(),", 1),
            _ctx(tmp_path),
        )
        is False
    )


def test_core_no_longer_imports_frontend_codegen():
    """The decoupling guarantee: prime_contractor must not import frontend_codegen at module
    level (it goes through the registry). Source-level check."""
    import startd8.contractors.prime_contractor as pc

    src = Path(pc.__file__).read_text(encoding="utf-8")
    # the only frontend reference should be gone; the skip-hook uses deterministic_providers
    assert "from ..frontend_codegen" not in src
    assert "deterministic_providers" in src
