"""RUN-036 (convention half): the Python house-style authority (FastAPI/SQLModel, `app.tables`
module-source, `session.exec` not `session.query`) reaches the lead/cloud SPEC and DRAFT prompts.

Test features and 0-element features route to the lead/cloud path and were inventing the wrong
module/ORM. This threads the same 8b authority micro-prime already gets into spec_builder + drafter.
"""

from startd8.implementation_engine.drafter import build_supplementary_sections
from startd8.implementation_engine.spec_builder import build_spec_prompt

CG = (
    "House style — the generated app uses these conventions; follow them exactly:\n"
    "- DB access: SQLModel — `session.exec(select(Model)...)`. Never `session.query(...)`.\n"
    "- Imports: SQLModel tables come from `app.tables`; `app.models` is Pydantic *Schema only."
)


def test_convention_guidance_rendered_in_spec():
    sp = build_spec_prompt(
        "implement the jobs router",
        {"convention_guidance": CG, "target_files": ["app/jobs.py"]},
        None,
    )
    assert "House style" in sp
    assert "app.tables" in sp
    # popped → rendered as a dedicated section, NOT JSON-escaped into the `## Context` dump
    assert '"convention_guidance"' not in sp


def test_convention_guidance_rendered_in_draft():
    out = build_supplementary_sections({"convention_guidance": CG})
    assert "House style" in out
    assert "session.exec" in out


def test_absent_convention_guidance_is_noop():
    sp = build_spec_prompt("implement", {"target_files": ["app/jobs.py"]}, None)
    assert "House style" not in sp
    assert build_supplementary_sections({}).find("House style") == -1
