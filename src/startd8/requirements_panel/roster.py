# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Default requirements-elicitation roster (FR-RP-10 — resolves OQ-RP-7).

The paid pass (``elicit --roles``) needs a Stakeholder-Panel roster; a greenfield user has none, so it
fails for exactly the people it should help. This ships a **curated default** whose personas are
``answers_for``-keyed on the ``RequirementDomain`` areas (and whose ``role_id``s match the default
owning roles in :mod:`~startd8.requirements_panel.domains`), plus an installer that writes it without
clobbering an existing roster. It is a valid ``domain: stakeholders`` roster (no new grammar, NR-RP-3).
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Optional

__all__ = [
    "ROSTER_REL",
    "TEMPLATE_NAME",
    "default_roster_text",
    "install_default_roster",
    "InstallResult",
]

# The conventional roster location the Stakeholder Panel / this CLI read (parity with cli_panel).
ROSTER_REL = Path("docs") / "kickoff" / "inputs" / "stakeholders.yaml"
TEMPLATE_NAME = "requirements_stakeholders.yaml"


def default_roster_text() -> str:
    """The packaged default roster YAML (works from a wheel via importlib.resources).

    Navigates from the parent package so ``templates/`` needs no ``__init__.py``.
    """
    root = resources.files("startd8.requirements_panel")
    return (root / "templates" / TEMPLATE_NAME).read_text(encoding="utf-8")


@dataclass
class InstallResult:
    written: bool
    path: Path
    reason: str = ""


def install_default_roster(
    project_root: Path | str, *, dest: Optional[Path] = None, force: bool = False
) -> InstallResult:
    """Write the default roster to ``docs/kickoff/inputs/stakeholders.yaml`` (refuses to clobber).

    A roster is a human-owned authoring artifact; regenerating over an edited one would be data loss, so
    the default is written only when absent (unless *force*).
    """
    target = (
        Path(dest) if dest is not None else Path(project_root).expanduser() / ROSTER_REL
    )
    if target.exists() and not force:
        return InstallResult(
            written=False,
            path=target,
            reason=f"{target} already exists — edit it in place (use --force to overwrite)",
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(default_roster_text(), encoding="utf-8")
    return InstallResult(written=True, path=target)
