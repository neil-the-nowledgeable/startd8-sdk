"""FR-W14 golden cross-check — the anti-divergence gate (OQ-2).

On the named golden fixture (R3-S3, every conditional generator surface enabled — R6-S3), the
artifact paths the wireframe plan claims must equal the paths the generators actually emit,
**both directions**. If a generator's layout changes, this test fails and the wireframe's path
mirroring must be updated.

Kwarg trap (R6-S3): ``render_backend(manifest_text=…)`` is **ai_passes.yaml**, while scaffold's
``--manifest`` / ``render_scaffold(manifest_text)`` is **app.yaml**.
"""

from __future__ import annotations

from pathlib import Path

from startd8.backend_codegen.assembler import render_backend
from startd8.scaffold_codegen.renderers import render_scaffold
from startd8.view_codegen.renderers import render_views
from startd8.wireframe import build_wireframe_plan, load_assembly_inputs


def _generator_paths(root: Path) -> set:
    schema = (root / "prisma" / "schema.prisma").read_text(encoding="utf-8")
    backend = render_backend(
        schema,
        manifest_text=(root / "prisma" / "ai_passes.yaml").read_text(encoding="utf-8"),
        human_inputs_text=(root / "prisma" / "human_inputs.yaml").read_text(encoding="utf-8"),
        pages_text=(root / "prisma" / "pages.yaml").read_text(encoding="utf-8"),
        completeness_text=(root / "prisma" / "completeness.yaml").read_text(encoding="utf-8"),
        authoring=True,
        # pages_app_dir deliberately None: body fragments are untracked (R1-S4) and the
        # wireframe must not claim them.
    )
    scaffold = render_scaffold((root / "app.yaml").read_text(encoding="utf-8"))
    views = render_views(schema, (root / "prisma" / "views.yaml").read_text(encoding="utf-8"))
    return {p for p, _ in backend} | {p for p, _ in scaffold} | {p for p, _ in views}


def test_plan_paths_match_generator_paths_both_directions(golden_root: Path) -> None:
    plan = build_wireframe_plan(
        load_assembly_inputs(project_root=golden_root), authoring=True
    )
    claimed = set(plan.claimed_paths)
    emitted = _generator_paths(golden_root)

    missing_from_plan = sorted(emitted - claimed)
    overclaimed = sorted(claimed - emitted)
    assert not missing_from_plan, f"generators emit paths the plan does not claim: {missing_from_plan}"
    assert not overclaimed, f"plan claims paths the generators do not emit: {overclaimed}"


def test_conditional_surfaces_present(golden_root: Path) -> None:
    """R6-S3: the fixture must exercise the AI layer, authoring, and weighted completeness —
    otherwise the cross-check silently shrinks to the unconditional subset."""
    plan = build_wireframe_plan(
        load_assembly_inputs(project_root=golden_root), authoring=True
    )
    claimed = set(plan.claimed_paths)
    for must in (
        "app/server.py",            # AI layer (ai-server)
        "app/ai/routes.py",         # AI router
        "app/ai/suggest_notes.py",  # per-pass harness
        "app/pages_admin.py",       # authoring UI
        "app/completeness.py",      # weighted completeness
        "app/views/profile_dashboard.py",  # composite view
        "Dockerfile",               # scaffold container
    ):
        assert must in claimed, must


def test_openapi_contract_projects_golden_conditional_routes(golden_root: Path) -> None:
    """Role 1 FR-3: wireframe manifests → conditional routes in static contract."""
    from startd8.backend_codegen.openapi_contract_renderer import render_openapi_contract

    schema = (golden_root / "prisma" / "schema.prisma").read_text(encoding="utf-8")
    text = render_openapi_contract(
        schema,
        manifest_text=(golden_root / "prisma" / "ai_passes.yaml").read_text(encoding="utf-8"),
        pages_text=(golden_root / "prisma" / "pages.yaml").read_text(encoding="utf-8"),
        views_text=(golden_root / "prisma" / "views.yaml").read_text(encoding="utf-8"),
    )
    assert '("POST", "/ai/ai/suggest-notes")' in text
    assert '("GET", "/")' in text
