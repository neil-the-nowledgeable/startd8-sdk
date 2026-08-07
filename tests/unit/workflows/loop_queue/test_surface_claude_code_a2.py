# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""A2 (code-asks 2026-08-04): claude-code is a registered SDK surface.

Guards the fix for the gap the Istio smoke test caught — `wloop list-surfaces` did not include
`claude-code`, so an `enqueue` with `surface_id=claude-code` was refused unless the job declared inline
`surface_conformance`, even though the dev-os VJO in-agent adapter (drain-claude.py) was shipped + armed.
"""
from __future__ import annotations

from startd8.workflows.loop_queue.surfaces import is_known_surface, list_surfaces


def test_claude_code_is_a_known_surface():
    assert is_known_surface("claude-code") is True


def test_claude_code_appears_in_list_surfaces():
    ids = {s.surface_id for s in list_surfaces()}
    # the four rostered surfaces (registry is advisory/open — FR-22 — but these are the shipped/known set)
    assert {"cursor", "codex", "antigravity", "claude-code"} <= ids


def test_claude_code_metadata_names_the_dev_os_adapter():
    cc = next(s for s in list_surfaces() if s.surface_id == "claude-code")
    assert cc.display_name == "Claude Code"
    assert "dev-os" in cc.ownership  # the VJO in-agent adapter owns it
