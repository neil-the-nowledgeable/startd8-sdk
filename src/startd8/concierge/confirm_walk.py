# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Guided multi-field confirm walk — the interactive layer over value-input confirmation.

A **new dedicated, pure-of-IO** loop (NOT the deprecated red-carpet driver): it walks the *awaiting*
confirmable fields one at a time, shows each field's label + why (its domain's one-line question) +
grammar + current default, and dispatches one line of input — a value (`set`), ``a`` (`as-is`), Enter
(skip), or ``q`` (quit) — to the **unchanged** ``build_confirm_plan``/``apply_confirm``. Each
confirmation persists immediately, so quitting mid-walk keeps progress and a re-run only re-offers the
still-awaiting fields. IO is injected (``read_input``/``emit_line``) so the loop is unit-testable with
a scripted reader. See ``docs/design/kickoff/GUIDED_CONFIRM_FLOW_{REQUIREMENTS,PLAN}.md``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from startd8.logging_config import get_logger

from .confirmation import (
    ConfirmError,
    apply_confirm,
    build_confirm_plan,
    confirmable_fields,
    confirmed_value_paths,
    field_current_value,
)

logger = get_logger(__name__)

#: Reserved input tokens (no collision with the 3 current confirmable fields' valid values — a field
#: that legitimately needs these as values uses the scriptable single-shot `kickoff confirm <vp>`).
WALK_QUIT = frozenset({"q", "quit", "exit", ":q"})
WALK_AS_IS = "a"
_LEGEND = "  [value] type a value · [a] confirm as-is · [Enter] skip · [q] quit"

ReadInput = Callable[[str], Optional[str]]
EmitLine = Callable[[str], None]


def _domain_ordinal(slug: str) -> int:
    from .core import KICKOFF_INPUT_REGISTRY

    meta = KICKOFF_INPUT_REGISTRY.get(slug)
    return meta.ordinal if meta is not None else 99


def awaiting_fields(project_root: str | Path, config: Optional[Any] = None) -> List[dict]:
    """Confirmable fields not yet in the ledger, ordered by domain ordinal then declaration order."""
    confirmed = confirmed_value_paths(project_root)
    pending = [f for f in confirmable_fields(config) if f["value_path"] not in confirmed]
    return sorted(pending, key=lambda f: _domain_ordinal(f["domain"]))   # stable ⇒ declaration order kept


def _domain_question(slug: str, cache: Dict[str, str]) -> str:
    if slug in cache:
        return cache[slug]
    try:
        from .core import explain_input_domain

        cache[slug] = explain_input_domain(slug).get("question", "") or ""
    except Exception:   # unknown slug / unreadable explainer → no why-line, never fatal
        cache[slug] = ""
    return cache[slug]


def field_prompt_lines(
    project_root: str | Path, field: dict, config: Any, qcache: Dict[str, str]
) -> List[str]:
    """The per-field context block — label + current default, the domain 'why', grammar, and choices.
    Reuses the registry `question` + `FieldDef.grammar_help` verbatim (no new prose)."""
    from ..kickoff_experience.manifest import default_config

    cfg = config or default_config()
    fdef = cfg.field_by_value_path(field["value_path"])
    current = field_current_value(project_root, field["value_path"], config=cfg)
    head = field["label"] if current is None else f"{field['label']} (currently {current!r})"
    lines = [head]
    why = _domain_question(field["domain"], qcache)
    if why:
        lines.append(f"  why: {why}")
    if fdef is not None and fdef.grammar_help:
        lines.append(f"  {fdef.grammar_help}")
    if field.get("choices"):
        lines.append(f"  choices: {', '.join(field['choices'])}")
    return lines


def run_confirm_walk(
    project_root: str | Path,
    *,
    read_input: ReadInput,
    emit_line: EmitLine,
    timestamp: Optional[str] = None,
    config: Optional[Any] = None,
) -> Dict[str, Any]:
    """Walk the awaiting fields interactively (pure-of-IO). Returns a session summary
    ``{confirmed: [...], skipped: [...], quit: bool, remaining: int}``. $0, no LLM."""
    from ..kickoff_experience.manifest import default_config

    cfg = config or default_config()
    fields = awaiting_fields(project_root, cfg)   # snapshot at start (R2 — stable set)
    confirmed_now: List[str] = []
    skipped: List[str] = []
    quit_flag = False
    qcache: Dict[str, str] = {}

    for field in fields:
        vp = field["value_path"]
        while True:   # re-prompt this field on a validation error
            for line in field_prompt_lines(project_root, field, cfg, qcache):
                emit_line(line)
            emit_line(_LEGEND)
            raw = read_input(f"  ▸ {field['label']}: ")
            if raw is None or raw.strip().lower() in WALK_QUIT:
                quit_flag = True
                break
            token = raw.strip()
            if token == "":
                skipped.append(vp)
                break
            mode = "as-is" if token.lower() == WALK_AS_IS else "set"
            try:
                plan = build_confirm_plan(
                    project_root, vp, None if mode == "as-is" else token,
                    mode=mode, timestamp=timestamp, config=cfg,
                )
                apply_confirm(project_root, plan)
            except ConfirmError as exc:
                emit_line(f"  ✗ {exc}")
                if exc.code in ("bad_value", "capture_failed", "missing_value"):
                    continue   # bad input → re-prompt the same field (FR-6)
                break          # other failure → leave awaiting, advance (FR-4)
            confirmed_now.append(vp)
            emit_line(f"  ✓ confirmed ({mode})")
            break
        if quit_flag:
            break

    remaining = len(awaiting_fields(project_root, cfg))
    return {"confirmed": confirmed_now, "skipped": skipped, "quit": quit_flag, "remaining": remaining}
