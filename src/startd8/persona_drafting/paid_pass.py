# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Shared paid-pass runner (FR-KO-4 — extracted from the sibling CLIs).

Both `startd8 requirements elicit --roles` and `startd8 screens suggest --roles` duplicated the same
boilerplate: locate + validate the roster, build a live `StakeholderPanel`, run an async pass, and
always `close()` the panel. This is that boilerplate, once — the sibling CLIs pass an async callable
that receives the live panel. Raises a typed :class:`PaidPassError` so each CLI maps the failure kind to
its own exit code (no behavior change).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

__all__ = ["PaidPassError", "run_paid_pass"]


class PaidPassError(Exception):
    """A paid pass could not run. ``kind`` ∈ {``no_roster``, ``invalid_roster``, ``failed``}."""

    def __init__(self, message: str, kind: str) -> None:
        super().__init__(message)
        self.kind = kind


def run_paid_pass(
    project_root: Path | str,
    *,
    roster_rel: Path,
    run: Callable[[Any], Awaitable[Any]],
    model: Optional[str] = None,
) -> Any:
    """Load+validate the roster, build a live panel, ``await run(panel)``, always close. Returns run's result.

    ``run`` is an async callable given the live :class:`StakeholderPanel` (the CLI closes over the brief /
    schema / cap / session_id it needs). Any provider/auth/budget failure surfaces as
    ``PaidPassError(kind="failed")``; a missing/invalid roster as ``no_roster``/``invalid_roster``.
    """
    root = Path(project_root)
    roster_path = root / roster_rel
    if not roster_path.is_file():
        raise PaidPassError(
            f"no roster at {roster_path} — run `startd8 requirements init-roster` to write a default",
            "no_roster",
        )
    from startd8.stakeholder_panel import RosterError, load_roster, validate_roster
    from startd8.stakeholder_panel.panel import DEFAULT_MODEL_SPEC, StakeholderPanel

    try:
        roster = load_roster(roster_path)
    except RosterError as exc:
        raise PaidPassError(str(exc), "invalid_roster")
    if validate_roster(roster):
        raise PaidPassError(
            "roster is invalid (run `startd8 panel` to inspect)", "invalid_roster"
        )

    panel = StakeholderPanel(
        roster, project_root=root, model_spec=model or DEFAULT_MODEL_SPEC
    )
    try:
        return asyncio.run(run(panel))
    except (
        Exception
    ) as exc:  # provider/auth/budget failure — clean, typed message (never a traceback)
        raise PaidPassError(f"paid pass failed: {exc}", "failed")
    finally:
        panel.close()
