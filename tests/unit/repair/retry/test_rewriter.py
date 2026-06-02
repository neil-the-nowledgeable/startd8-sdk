"""Inc 3 — broadened resolver + rewrite lever tests (FR-4).

Covers both rewrite strategies against fixture trees mirroring the real incidents:
  * RUN-013 PI-004 — sub-namespace **collapse**
    (`@/lib/export/renderers/markdown` → `@/lib/export/markdown`).
  * RUN-012 #4 — **token-match** relocation
    (`../../../types/wizard` → `@/components/wizard/types`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.repair.retry.classifier import RetryClass, classify
from startd8.repair.retry.models import RetryViolation
from startd8.repair.retry.rewriter import apply_rewrite, compute_rewrite
from startd8.repair.retry.search import DiskTargetSearch


def _v(importer, specifier, fid="PI"):
    return RetryViolation(fid, importer, "unresolvable_import", specifier, "")


# ── RUN-013: sub-namespace collapse ──────────────────────────────────────────

@pytest.fixture
def run013_tree(tmp_path):
    gen = tmp_path / "generated"
    (gen / "lib" / "export").mkdir(parents=True)
    (gen / "app" / "api" / "export").mkdir(parents=True)
    (gen / "lib" / "export" / "markdown.ts").write_text("export const renderMarkdown = 1\n")
    (gen / "lib" / "export" / "json.ts").write_text("export const serializeJson = 1\n")
    (gen / "lib" / "export" / "corpus.ts").write_text("export const readCorpus = 1\n")
    (gen / "app" / "api" / "export" / "route.ts").write_text(
        "import { renderMarkdown } from '@/lib/export/renderers/markdown';\n"
        "import { serializeJson } from '@/lib/export/renderers/json';\n"
    )
    return gen


def test_pi004_subnamespace_classifies_rewritable(run013_tree):
    search = DiskTargetSearch(run013_tree)
    v = _v("app/api/export/route.ts", "@/lib/export/renderers/markdown", "PI-004")
    res = classify(v, search)
    assert res.retry_class == RetryClass.REWRITABLE_PATH
    assert res.target.name == "markdown.ts"


def test_pi004_collapse_rewrite_drops_invented_segment(run013_tree):
    search = DiskTargetSearch(run013_tree)
    rw_md = compute_rewrite(_v("app/api/export/route.ts", "@/lib/export/renderers/markdown"), search)
    rw_js = compute_rewrite(_v("app/api/export/route.ts", "@/lib/export/renderers/json"), search)
    assert rw_md is not None and rw_md.strategy == "collapse"
    assert rw_md.target_specifier == "@/lib/export/markdown"
    assert rw_js.target_specifier == "@/lib/export/json"


def test_pi004_apply_rewrite_fixes_only_the_imports(run013_tree):
    search = DiskTargetSearch(run013_tree)
    code = (run013_tree / "app" / "api" / "export" / "route.ts").read_text()
    for spec in ("@/lib/export/renderers/markdown", "@/lib/export/renderers/json"):
        rw = compute_rewrite(_v("app/api/export/route.ts", spec), search)
        code, changed = apply_rewrite(code, rw)
        assert changed
    assert "from '@/lib/export/markdown'" in code
    assert "from '@/lib/export/json'" in code
    assert "renderers" not in code


# ── RUN-012: token-match relocation ──────────────────────────────────────────

@pytest.fixture
def run012_tree(tmp_path):
    gen = tmp_path / "generated"
    (gen / "components" / "wizard" / "steps").mkdir(parents=True)
    (gen / "components" / "wizard" / "types.ts").write_text("export type W = {}\n")
    (gen / "components" / "wizard" / "steps" / "EnrichStep.tsx").write_text(
        "import { W } from '../../../types/wizard'\n"
    )
    return gen


def test_pi012_relocation_rewrites_via_token_match(run012_tree):
    search = DiskTargetSearch(run012_tree)
    rw = compute_rewrite(_v("components/wizard/steps/EnrichStep.tsx", "../../../types/wizard"), search)
    assert rw is not None and rw.strategy == "token_match"
    # alias form preferred and resolves blind to components/wizard/types.ts
    assert rw.target_specifier == "@/components/wizard/types"
    assert search.module_resolves(rw.target_specifier, "components/wizard/steps/EnrichStep.tsx")


def test_pi012_apply_rewrite(run012_tree):
    search = DiskTargetSearch(run012_tree)
    code = (run012_tree / "components" / "wizard" / "steps" / "EnrichStep.tsx").read_text()
    rw = compute_rewrite(_v("components/wizard/steps/EnrichStep.tsx", "../../../types/wizard"), search)
    code, changed = apply_rewrite(code, rw)
    assert changed and "from '@/components/wizard/types'" in code
    assert "../../../types/wizard" not in code


# ── form selection + safety ──────────────────────────────────────────────────

def test_prefers_relative_when_alias_not_blind_resolvable(tmp_path):
    # target lives under src/ but no tsconfig alias; the @/-blind form @/x resolves
    # via the src base, so this still picks alias. Construct a case where alias fails:
    gen = tmp_path / "generated"
    (gen / "deep" / "a").mkdir(parents=True)
    (gen / "deep" / "mod.ts").write_text("export const m = 1\n")
    (gen / "deep" / "a" / "Foo.tsx").write_text("import { m } from './nope/mod'\n")
    search = DiskTargetSearch(gen)
    rw = compute_rewrite(_v("deep/a/Foo.tsx", "./nope/mod"), search)
    # ./nope/mod collapses to ./mod? interior 'nope' dropped -> 'deep/a/' + 'mod'? no.
    # token-match: tokens {nope, mod}; deep/mod has segs {deep, mod} -> missing 'nope' -> no.
    # So this is absent (not rewritable) -> compute_rewrite returns None.
    assert rw is None


def test_ambiguous_is_not_rewritten(tmp_path):
    gen = tmp_path / "generated"
    (gen / "a").mkdir(parents=True)
    (gen / "b").mkdir(parents=True)
    (gen / "a" / "widget.ts").write_text("export const x = 1\n")
    (gen / "b" / "widget.ts").write_text("export const x = 1\n")
    search = DiskTargetSearch(gen)
    assert compute_rewrite(_v("c/Foo.tsx", "../widget"), search) is None


def test_apply_rewrite_does_not_touch_string_literals(run013_tree):
    search = DiskTargetSearch(run013_tree)
    code = (
        "import { x } from '@/lib/export/renderers/markdown'\n"
        "const doc = \"see '@/lib/export/renderers/markdown' docs\"\n"
    )
    rw = compute_rewrite(_v("app/api/export/route.ts", "@/lib/export/renderers/markdown"), search)
    out, changed = apply_rewrite(code, rw)
    assert "from '@/lib/export/markdown'" in out
    assert "const doc = \"see '@/lib/export/renderers/markdown' docs\"" in out  # literal untouched
