"""RUN-036 #2: field-set/entity authority must reach the SPEC prompt as a readable section.

The `Match` name-invention originated in the spec artifact: the real entities
(JobMatch/TailoredMatch in app.tables) were buried — JSON-escaped — inside the generic
`## Context` dump, so the spec invented a non-existent `Match` from `app.models`. The draft
prompt already rendered `upstream_interfaces` prominently; the spec did not. The fix pops it
and renders it as a dedicated P0 section (like the drafter).
"""

from startd8.implementation_engine.spec_builder import build_spec_prompt

AUTHORITY = (
    "## Prisma data model — mirror these field names/types EXACTLY\n"
    "- `JobMatch`: id: Int, jd_id: Int, score: Float\n"
    "- `TailoredMatch`: id: Int, content: String\n"
)


def test_upstream_interfaces_rendered_as_readable_section():
    ctx = {"upstream_interfaces": AUTHORITY, "target_files": ["app/jobs.py"]}
    prompt = build_spec_prompt("Implement the jobs router", dict(ctx), None)

    # Surfaced as readable markdown (the real entities are visible to the model)...
    assert "## Prisma data model — mirror these field names/types EXACTLY" in prompt
    assert "JobMatch" in prompt
    assert "TailoredMatch" in prompt
    # ...and POPPED, so it is NOT left to be JSON-escaped into the `## Context` dump
    # (the JSON key would appear verbatim if it had not been popped).
    assert '"upstream_interfaces"' not in prompt


def test_absent_upstream_interfaces_is_noop():
    prompt = build_spec_prompt("Implement the jobs router", {"target_files": ["app/jobs.py"]}, None)
    assert "## Prisma data model" not in prompt


def test_empty_upstream_interfaces_renders_no_section():
    ctx = {"upstream_interfaces": "   ", "target_files": ["app/jobs.py"]}
    prompt = build_spec_prompt("Implement the jobs router", dict(ctx), None)
    assert "## Prisma data model" not in prompt
    assert '"upstream_interfaces"' not in prompt  # still popped (no spurious JSON key)
