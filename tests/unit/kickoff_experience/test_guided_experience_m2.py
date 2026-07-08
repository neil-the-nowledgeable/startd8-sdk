# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""GE-M2 — concierge/conductor detangle: consolidation invariants.

These tests are the M2 exit gate (FR-GE-7's reframed metric): they enforce the *surface / vocabulary
/ write-path* properties, not a module count. Two CI-enforceable invariants (plan R1-S6 / R2-S6):

  * **Write-audit (FR-GE-13):** no experience module performs a direct filesystem write — every byte
    the guided experience writes rides `concierge/safe_write.py` (via `apply_write_plan`). A repo-wide
    AST gate, not a manual claim.
  * **No-new-engine (FR-GE-6):** the merged conductor + view REUSE the existing advisor / readiness
    projections; the detangle introduced no second readiness/advisor implementation. The 3→1 merge is
    the highest-risk window for accidental engine introduction, so this is asserted structurally.

Plus a thin structural check that the three merges landed as compat re-exports (one vocabulary /
one write path preserved across the legacy import paths).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import startd8.kickoff_experience as ke_pkg

_PKG_DIR = Path(ke_pkg.__file__).parent

# The experience modules whose writes must ride the safe-write floor. (The floor itself,
# `concierge/safe_write.py`, lives in a different package and is intentionally out of scope.)
#
# FR-GE-13 governs GUIDED-EXPERIENCE writes to the project **source of record** (docs/kickoff/…). A few
# modules living in this package are NOT guided-experience write surfaces — they own their own
# **endpoint / spend-safety state** under `.startd8/` (atomic tmpfile+rename, plus an fcntl lock file),
# intentionally outside the concierge floor. Exempt them by name, with the reason, rather than let the
# glob mis-scope the audit onto server/endpoint code.
_ENDPOINT_STATE_MODULES = {
    # Phase-2 stakeholder-run HTTP endpoint: writes the run idempotency/crash-marker ledger + an fcntl
    # lock file under .startd8/stakeholder-run/ (spend-safety state, not kickoff source-of-record).
    "stakeholder_run.py",
}
_EXPERIENCE_MODULES = sorted(
    p
    for p in _PKG_DIR.glob("*.py")
    if p.name != "__init__.py" and p.name not in _ENDPOINT_STATE_MODULES
)

_WRITE_METHODS = {"write_text", "write_bytes", "writelines"}
_WRITE_MODE_CHARS = set("wax+")


def _open_has_write_mode(call: ast.Call) -> bool:
    """True iff a builtin ``open(...)`` call names a write/append/create mode (positional or `mode=`)."""
    mode_node = None
    if len(call.args) >= 2:
        mode_node = call.args[1]
    for kw in call.keywords:
        if kw.arg == "mode":
            mode_node = kw.value
    if isinstance(mode_node, ast.Constant) and isinstance(mode_node.value, str):
        return bool(set(mode_node.value) & _WRITE_MODE_CHARS)
    return False


def _direct_write_calls(source: str) -> list[str]:
    """Return a description of any direct filesystem-write call in *source* (AST, not regex)."""
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # `.write_text(...)` / `.write_bytes(...)` / `.writelines(...)` on any object
        if isinstance(func, ast.Attribute) and func.attr in _WRITE_METHODS:
            offenders.append(f"{func.attr}() @ line {node.lineno}")
        # `os.write(fd, data)`
        elif (isinstance(func, ast.Attribute) and func.attr == "write"
              and isinstance(func.value, ast.Name) and func.value.id == "os"):
            offenders.append(f"os.write() @ line {node.lineno}")
        # builtin `open(path, 'w'|'a'|'x'|...)`
        elif isinstance(func, ast.Name) and func.id == "open" and _open_has_write_mode(node):
            offenders.append(f"open(..., write-mode) @ line {node.lineno}")
    return offenders


@pytest.mark.parametrize("module_path", _EXPERIENCE_MODULES, ids=lambda p: p.name)
def test_no_experience_module_writes_outside_the_safe_write_floor(module_path):
    """FR-GE-13 write-audit: no kickoff-experience module bypasses the safe-write floor."""
    offenders = _direct_write_calls(module_path.read_text(encoding="utf-8"))
    assert not offenders, (
        f"{module_path.name} performs a direct filesystem write {offenders} — route it through "
        f"`concierge/safe_write.py` (apply_write_plan). Every guided-experience write rides the "
        f"safe-write floor (FR-GE-13)."
    )


def test_conductor_reuses_the_existing_advisor_not_a_reimplementation():
    """FR-GE-6 no-new-engine: the conductor PROJECTS the existing advisor output; it does not define
    a competing readiness/advisor computation."""
    src = (_PKG_DIR / "orchestrator.py").read_text(encoding="utf-8")
    # It imports and drives the existing advisor projection…
    assert "build_red_carpet_state" in src
    assert "red_carpet_advisor" in src, "conductor must import the existing advisor, not reinvent it"
    tree = ast.parse(src)
    defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    # …and must NOT REDEFINE any of the existing engine entry points (only import/reuse them).
    forbidden = {"build_red_carpet_state", "build_readiness", "derive_advisories", "build_assess"}
    clash = defined & forbidden
    assert not clash, f"conductor redefines an existing engine entry point {clash} (FR-GE-6 violation)"


def test_merged_view_reuses_readiness_not_a_reimplementation():
    """FR-GE-6: the merged view+apply module reuses `build_readiness`; it does not re-derive it."""
    src = (_PKG_DIR / "concierge_view.py").read_text(encoding="utf-8")
    assert "build_readiness" in src
    tree = ast.parse(src)
    defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    forbidden = {"build_readiness", "build_assess", "build_survey"}
    clash = defined & forbidden
    assert not clash, f"view redefines an existing engine entry point {clash} (FR-GE-6 violation)"


def test_legacy_module_names_still_import_after_the_detangle():
    """One vocabulary / one write path preserved: the retired module names re-export from the
    canonical merge targets (compat window coupled to the M1 alias retirement)."""
    # Quartet → concierge_view
    from startd8.kickoff_experience import concierge_view
    from startd8.kickoff_experience.concierge_agent import resolve_concierge_agent_spec
    from startd8.kickoff_experience.concierge_apply import ConciergeWriteCode, apply_concierge_plan
    from startd8.kickoff_experience.tui_concierge import run_concierge

    assert resolve_concierge_agent_spec is concierge_view.resolve_concierge_agent_spec
    assert apply_concierge_plan is concierge_view.apply_concierge_plan
    assert ConciergeWriteCode is concierge_view.ConciergeWriteCode
    assert run_concierge is concierge_view.run_concierge

    # The surviving projections re-export from orchestrator (the conductor). The red-carpet wizard
    # (run_red_carpet_driver / wizard_prepopulate / the `wizard` shim) was retired — see
    # ADR_RETIRE_RED_CARPET_WIZARD.
    from startd8.kickoff_experience import orchestrator
    from startd8.kickoff_experience.red_carpet_completion import build_completion

    assert build_completion is orchestrator.build_completion


def test_chat_constructors_collapse_to_one_parametrized_factory():
    """The three chat constructors are thin wrappers over one parametrized factory (R2-S2: a single
    3-valued mode, no dead flag combination)."""
    from startd8.kickoff_experience import chat

    assert set(chat._CHAT_MODE_SPEC) == {
        chat.CHAT_MODE_READ, chat.CHAT_MODE_AGENTIC, chat.CHAT_MODE_RED_CARPET
    }
    # red_carpet implies agentic (the dead corner — red_carpet without propose — is foreclosed).
    agentic, red_carpet, _ = chat._CHAT_MODE_SPEC[chat.CHAT_MODE_RED_CARPET]
    assert agentic and red_carpet
    with pytest.raises(ValueError):
        chat.build_kickoff_chat(object(), "/tmp/x", mode="not-a-mode")
