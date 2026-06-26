"""FR-WCI-2 — the unified words/content coverage rollup.

Aggregates the author→approve surfaces the wireframe tracks per-item — page bodies, view copy, AI
prompts, and form help (FR-FH-9) — into a `ContentCoverageStats` on the plan and a
`content_completeness` block in the `--json` body (schema_version 3). Visibility only (bucket 2/4).

Golden fixture: `about.md` present + `home.md` missing → page bodies 1/2; one AI prompt present →
1/1; one view (`profile_dashboard`) with no `view_prose.yaml` → view copy 0/1; 8 writable form fields
with no `form_prose.yaml` → form help 0/8 → overall 2/12.
"""

from __future__ import annotations

import json
from pathlib import Path

from startd8.wireframe import (
    CoverageStat,
    build_wireframe_plan,
    load_assembly_inputs,
)
from startd8.wireframe.render import SCHEMA_VERSION, canonical_json


def _plan(root: Path, **kw):
    return build_wireframe_plan(load_assembly_inputs(project_root=root), **kw)


def test_rollup_aggregates_the_surfaces(golden_root: Path) -> None:
    cov = _plan(golden_root, authoring=True).content_coverage
    assert cov.page_bodies == CoverageStat(1, 2)   # about.md authored, home.md missing
    assert cov.ai_prompts == CoverageStat(1, 1)    # suggest_notes prompt present
    assert cov.view_copy == CoverageStat(0, 1)     # profile_dashboard, no view_prose.yaml
    assert cov.form_help == CoverageStat(0, 8)     # FR-FH-9: 8 writable form fields, no form_prose.yaml
    assert cov.overall == CoverageStat(2, 12)


def test_rollup_is_independent_of_authoring_flag(golden_root: Path) -> None:
    # Content coverage is bucket-2/4 visibility — the `authoring` toggle (pages section) must not move it.
    assert _plan(golden_root).content_coverage == _plan(golden_root, authoring=True).content_coverage


def test_ratio_is_vacuously_complete_when_total_zero(tmp_path: Path) -> None:
    cov = _plan(tmp_path).content_coverage   # empty project — no manifests at all
    assert cov.overall == CoverageStat(0, 0)
    assert cov.overall.ratio == 1.0          # 0/0 ⇒ 1.0, never a ZeroDivisionError
    assert cov.view_copy.ratio == 1.0


def test_authoring_view_copy_moves_the_rollup(golden_copy: Path) -> None:
    assert _plan(golden_copy).content_coverage.view_copy == CoverageStat(0, 1)
    (golden_copy / "prisma" / "view_prose.yaml").write_text(
        'profile_dashboard:\n  title: "Your profile"\n', encoding="utf-8"
    )
    after = _plan(golden_copy).content_coverage
    assert after.view_copy == CoverageStat(1, 1)
    assert after.overall == CoverageStat(3, 12)   # the one extra authored surface rolls up


def test_authoring_a_missing_page_body_moves_the_rollup(golden_copy: Path) -> None:
    assert _plan(golden_copy).content_coverage.page_bodies == CoverageStat(1, 2)
    (golden_copy / "app" / "pages" / "home.md").write_text("# Home\n\nReal content.\n", encoding="utf-8")
    assert _plan(golden_copy).content_coverage.page_bodies == CoverageStat(2, 2)


def test_json_carries_content_completeness_block(golden_root: Path) -> None:
    body = json.loads(canonical_json(_plan(golden_root, authoring=True)))
    assert body["schema_version"] == SCHEMA_VERSION == 3
    cc = body["content_completeness"]
    assert set(cc) == {"page_bodies", "view_copy", "ai_prompts", "form_help", "overall"}
    assert cc["overall"] == {"authored": 2, "total": 12, "ratio": 0.1667}
    assert cc["page_bodies"] == {"authored": 1, "total": 2, "ratio": 0.5}
    assert cc["view_copy"] == {"authored": 0, "total": 1, "ratio": 0.0}
    assert cc["ai_prompts"] == {"authored": 1, "total": 1, "ratio": 1.0}
    assert cc["form_help"] == {"authored": 0, "total": 8, "ratio": 0.0}


def test_content_completeness_participates_in_byte_identity(golden_root: Path) -> None:
    # The rollup is deterministic for identical inputs (FR-W2) — it joins the canonical body.
    assert canonical_json(_plan(golden_root)) == canonical_json(_plan(golden_root))
