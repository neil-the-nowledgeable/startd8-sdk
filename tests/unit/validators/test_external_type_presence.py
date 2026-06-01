"""Inc-1: signature (f) external-type-presence (REQ-CKG-610) — import-form matrix.

The synthetic ScipReader holds the members the TS compiler *resolved* (valid exports);
`scan()` flags referenced members absent from that set. This models reality: valid refs
appear in the index, hallucinated ones don't.
"""

from __future__ import annotations

import pytest

pytest.importorskip("google.protobuf")  # reader needs the [code-observability] extra

from startd8.code_observability import scip_pb2  # noqa: E402
from startd8.code_observability.scip_reader import ScipReader  # noqa: E402
from startd8.validators.external_type_presence import scan  # noqa: E402

_READ = scip_pb2.SymbolRole.ReadAccess

# What scip-typescript resolved (valid external exports actually used in the project).
_RESOLVED = [
    "scip-typescript npm next 14.0.0 `server.d.ts`/NextResponse#",
    "scip-typescript npm @anthropic-ai/sdk 0.24.0 `index.d.ts`/TextBlockParam#",
    "scip-typescript npm zod 3.25.0 `index.d.cts`/z.",
    "scip-typescript npm zod 3.25.0 v3/`types.d.cts`/ZodObject#extend().",
]


def _reader(resolved=_RESOLVED) -> ScipReader:
    idx = scip_pb2.Index()
    idx.metadata.tool_info.name = "scip-typescript"
    d = idx.documents.add()
    d.relative_path = "lib/_resolved.ts"
    for sym in resolved:
        o = d.occurrences.add()
        o.symbol = sym
        o.symbol_roles = _READ
    return ScipReader.from_bytes(idx.SerializeToString())


def _specifiers(sources):
    return {v.specifier for v in scan(sources, _reader())}


# --- the two RUN_009 failures this check exists to catch ---

def test_named_import_hallucinated_export_flagged():  # #4
    s = {"next.config.ts": "import { defineConfig } from 'next';\n"}
    assert _specifiers(s) == {"next.defineConfig"}


def test_namespace_member_hallucinated_flagged():  # #11
    s = {"lib/ai/service.ts":
         "import * as Anthropic from '@anthropic-ai/sdk';\n"
         "const b: Anthropic.ContentBlockParam = x;\n"}
    assert _specifiers(s) == {"@anthropic-ai/sdk.ContentBlockParam"}


def test_default_import_member_hallucinated_flagged():
    s = {"lib/ai/service.ts":
         "import Anthropic from '@anthropic-ai/sdk';\nAnthropic.ContentBlockParam;\n"}
    assert _specifiers(s) == {"@anthropic-ai/sdk.ContentBlockParam"}


# --- valid forms must NOT be flagged (false-positive guards) ---

def test_named_import_real_export_clean():
    assert _specifiers({"r.ts": "import { NextResponse } from 'next/server';\n"}) == set()


def test_namespace_member_real_export_clean():
    s = {"r.ts": "import * as Anthropic from '@anthropic-ai/sdk';\nconst t = Anthropic.TextBlockParam;\n"}
    assert _specifiers(s) == set()


def test_import_type_real_export_clean():
    assert _specifiers({"r.ts": "import type { TextBlockParam } from '@anthropic-ai/sdk';\n"}) == set()


def test_relative_and_alias_imports_ignored():
    s = {"r.ts": "import { foo } from './local';\nimport { bar } from '@/lib/db';\nfoo; bar;\n"}
    assert _specifiers(s) == set()


def test_subpath_member_hallucinated_flagged():
    # 'next/server' maps to package 'next'; 'nope' is not a resolved next export.
    assert _specifiers({"r.ts": "import { nope } from 'next/server';\n"}) == {"next.nope"}


def test_unresolved_package_skipped_no_false_positive():
    # pino has zero resolved members -> can't conclude membership -> skip (missing-dep's job).
    s = {"r.ts": "import pino from 'pino';\npino.whatever();\n"}
    assert _specifiers(s) == set()


def test_advisory_when_scip_none():
    assert scan({"r.ts": "import { defineConfig } from 'next';\n"}, None) == []


def test_only_ts_sources_considered():
    # A .prisma or .md path is not TS source — never scanned.
    assert _specifiers({"schema.prisma": "import { defineConfig } from 'next';\n"}) == set()


# --- honest strategy-(a) boundary (documented, tracked) ---

@pytest.mark.xfail(
    strict=True,
    reason="strategy-(a) limitation: a package with ZERO resolved members is skipped by the "
           "FP guard, so a hallucination is missed when it's the package's only reference. "
           "Closing this needs strategy-(b) .d.ts indexing (deferred). XPASS => gap closed.",
)
def test_hallucination_is_only_reference_to_package():
    # Reader has NO @anthropic-ai/sdk members resolved; the bad ref is the only mention.
    reader = _reader(resolved=["scip-typescript npm next 14.0.0 `server.d.ts`/NextResponse#"])
    s = {"r.ts": "import Anthropic from '@anthropic-ai/sdk';\nAnthropic.ContentBlockParam;\n"}
    specs = {v.specifier for v in scan(s, reader)}
    assert "@anthropic-ai/sdk.ContentBlockParam" in specs
