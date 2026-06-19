"""Role 3 P2: context_integration must reach spec/draft prompts as a readable section."""

from startd8.implementation_engine.spec_builder import build_spec_prompt

AUTHORITY = (
    "## Outbound context clients (Role 3 — cross-process integration)\n"
    "| Producer | Factory | Client | contract-sha256 |\n"
    "| `catalog` | `get_catalog_client()` | `CatalogClient` | `abc123…` |\n"
)


def test_context_integration_rendered_as_readable_section():
    ctx = {"context_integration": AUTHORITY, "target_files": ["app/sync.py"]}
    prompt = build_spec_prompt("Sync notes from catalog", dict(ctx), None)

    assert "## Outbound context clients" in prompt
    assert "CatalogClient" in prompt
    assert "get_catalog_client" in prompt
    assert '"context_integration"' not in prompt


def test_absent_context_integration_is_noop():
    prompt = build_spec_prompt("Sync notes", {"target_files": ["app/sync.py"]}, None)
    assert "## Outbound context clients" not in prompt


def test_empty_context_integration_renders_no_section():
    ctx = {"context_integration": "   ", "target_files": ["app/sync.py"]}
    prompt = build_spec_prompt("Sync notes", dict(ctx), None)
    assert "## Outbound context clients" not in prompt
    assert '"context_integration"' not in prompt
