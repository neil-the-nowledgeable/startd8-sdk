"""Negative regression guard for the Concierge read-only/preview floor over MCP.

Spec: Welcome Mat Concierge-mode plan M-CM6 / R1-S5 / R1-S9 and RCT R1-F1 — "propose-only" and the
read-only MCP floor are today enforced only by the *absence* of an apply/write tool, which a future
addition could silently widen. This test pins the floor so a regression fails loudly.

It asserts, across BOTH MCP server modules:
  1. the MCP `startd8_concierge` action set is exactly the reconciled read/preview floor
     {survey, assess, instantiate, instantiate-kickoff, log-friction} — the canonical
     `instantiate` plus its deprecated `instantiate-kickoff` alias (FR-10), no `derive-contract`
     (CLI-only, FR-C8 spec-deferral), no apply/commit/promote/cascade action;
  2. the MCP concierge input carries no `apply` param and no derive-contract fields;
  3. the `startd8_concierge` tool is annotated read-only (readOnlyHint=True, destructiveHint=False);
  4. the agentic-loop registries (`build_concierge_registry` / `build_kickoff_registry`) expose only
     read tools ⊆ {survey, assess, field_states} and allow only the `read` effect class;
  5. the MCP `survey` returns the bare `build_survey` shape, NOT the write-affordance-carrying
     `build_concierge_view` (R1-S9) — no instantiate_offer / friction_form / next_action leaks.
"""
from __future__ import annotations

import pytest

import startd8_mcp

# Both MCP server modules must honor the same floor (FR-C14 mirror).
_SERVERS = [("startd8_mcp", startd8_mcp.ConciergeAction, startd8_mcp.ConciergeInput)]
try:
    from startd8_mcp_server import server as _srv2

    _SERVERS.append(("startd8_mcp_server.server", _srv2.ConciergeAction, _srv2.ConciergeInput))
except Exception:  # pragma: no cover - second server optional in some layouts
    pass

# The read/preview floor: reads + preview-only writes. NO derive-contract, NO apply.
# FR-10: canonical `instantiate` + its deprecated `instantiate-kickoff` alias both live on the floor.
READ_PREVIEW_ACTIONS = {"survey", "assess", "instantiate", "instantiate-kickoff", "log-friction"}
# Core read actions that must always remain in the loop allow-list (it may grow with new READ tools).
LOOP_READ_ACTIONS = {"survey", "assess", "field_states"}
_WRITE_MARKERS = ("apply", "commit", "delete", "promote", "cascade")
# Loop-tool names that would signal a write/apply capability sneaking onto the read-only floor.
_LOOP_WRITE_MARKERS = ("apply", "commit", "delete", "promote", "cascade", "instantiate", "friction", "write", "confirm", "derive")


@pytest.mark.parametrize("modname,action_enum,_input", _SERVERS)
def test_mcp_concierge_action_set_is_the_readonly_preview_floor(modname, action_enum, _input):
    values = {a.value for a in action_enum}
    assert "derive-contract" not in values, f"{modname}: derive-contract must stay CLI-only (FR-C8)"
    assert values == READ_PREVIEW_ACTIONS, f"{modname}: unexpected MCP concierge actions: {values}"
    for v in values:
        assert not any(m in v for m in _WRITE_MARKERS), f"{modname}: write-style action leaked: {v}"


@pytest.mark.parametrize("modname,_action,input_model", _SERVERS)
def test_mcp_concierge_input_has_no_apply_or_derive_fields(modname, _action, input_model):
    fields = set(input_model.model_fields)
    assert "apply" not in fields, f"{modname}: MCP tool must expose no `apply` param (FR-C3)"
    for f in ("models", "pythonpath", "model_names", "exclude_models", "check"):
        assert f not in fields, f"{modname}: derive-contract field `{f}` must be absent from MCP input"


def test_mcp_concierge_tool_is_annotated_read_only():
    tools = {t.name: t for t in startd8_mcp.mcp._tool_manager.list_tools()}
    tool = tools.get("startd8_concierge")
    assert tool is not None, "startd8_concierge tool not registered"
    ann = getattr(tool, "annotations", None)
    assert ann is not None, "startd8_concierge missing annotations"

    def _get(a, key):
        return a.get(key) if isinstance(a, dict) else getattr(a, key, None)

    assert _get(ann, "readOnlyHint") is True, "startd8_concierge must be readOnlyHint=True"
    assert _get(ann, "destructiveHint") is False, "startd8_concierge must be destructiveHint=False"


def test_agentic_loop_registries_are_read_only(tmp_path):
    from startd8.concierge.chat import build_concierge_registry
    from startd8.kickoff_experience.chat import KICKOFF_READ_ACTIONS, build_kickoff_registry

    # The read allow-list MAY grow with new *read* tools (e.g. RCT's `red_carpet_state`), but must
    # never gain a write/apply action. We enforce the durable invariant (no write tool), which is
    # stronger and more future-proof than a literal {survey,assess,field_states} name subset.
    assert LOOP_READ_ACTIONS <= set(KICKOFF_READ_ACTIONS), "a core read action disappeared"
    for a in KICKOFF_READ_ACTIONS:
        assert not any(m in a for m in _LOOP_WRITE_MARKERS), f"write-style action in read allow-list: {a}"

    for reg in (build_concierge_registry(tmp_path), build_kickoff_registry(tmp_path)):
        # Hard gate: the registry only permits the `read` effect class, so a mis-registered write
        # tool cannot be invoked at all.
        assert set(reg.allow_effect_classes) == {"read"}, f"loop registry allows non-read: {reg.allow_effect_classes}"
        # And no individual tool is a write or named like one.
        for tool_name, spec in reg._tools.items():
            assert spec.effect_class == "read", f"non-read loop tool {tool_name}: {spec.effect_class}"
            assert not any(m in tool_name for m in _LOOP_WRITE_MARKERS), f"write-style loop tool: {tool_name}"
        assert {"survey", "assess"} <= reg.names(), "core read tools missing from loop registry"


def test_mcp_survey_returns_build_survey_not_concierge_view(tmp_path):
    from startd8.concierge.core import build_survey, handle_concierge_tool

    got = handle_concierge_tool("survey", tmp_path)
    expected = build_survey(tmp_path)
    assert set(got) == set(expected), "MCP survey must return the bare build_survey shape"
    # Write-affordance keys that only build_concierge_view carries must NOT reach the read-only floor.
    for leaked in ("instantiate_offer", "friction_form", "next_action"):
        assert leaked not in got, f"survey leaked concierge_view write-affordance key: {leaked}"
