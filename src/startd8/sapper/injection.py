"""FR-SAP-12 finding injection — populate a generation context with per-file Sapper warnings.

The survey writes ``sapper-friction-report.json``; this module is what a generation run calls to
fold the per-file findings into the prompt context, so the generator is *warned* before it
reproduces a misalignment (the advisory → prevention step). It sets two keys consumed downstream:

- ``gen_context["sapper_guidance"]`` → micro-prime prompt (``MicroPrimeContext.from_prime``);
- ``gen_context["sapper_alignment"]`` → lead/drafter spec prompt (``spec_builder``, P0 section).

Guarded + no-op by default: with no report path (arg or ``STARTD8_SAPPER_REPORT`` env) it does
nothing, so it is safe to call unconditionally in the generation path. Never raises into the
caller — a malformed report degrades to "no injection", never a broken run.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Iterable, Optional

from startd8.logging_config import get_logger

logger = get_logger(__name__)

REPORT_ENV = "STARTD8_SAPPER_REPORT"

# Cache parsed per-file blocks by (path, mtime) so a multi-feature run reads the report once.
_CACHE: Dict[tuple, Dict[str, str]] = {}


def _resolve_report_path(report_path: Optional[str]) -> Optional[Path]:
    p = report_path or os.environ.get(REPORT_ENV, "").strip()
    if not p:
        return None
    path = Path(p)
    return path if path.is_file() else None


def _load_blocks(path: Path) -> Dict[str, str]:
    try:
        key = (str(path), path.stat().st_mtime)
    except OSError:
        return {}
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    try:
        from .report import file_blocks_from_json

        blocks = file_blocks_from_json(path.read_text(encoding="utf-8"))
    except Exception as exc:  # malformed/partial report → no injection, never break the run
        logger.info("sapper report unreadable (%s); skipping finding injection", exc)
        blocks = {}
    _CACHE[key] = blocks
    return blocks


def populate_gen_context(
    gen_context: dict,
    target_files: Iterable[str],
    *,
    report_path: Optional[str] = None,
) -> bool:
    """Set the Sapper guidance keys on ``gen_context`` for ``target_files``. Returns True if injected.

    Concatenates the per-file blocks for the given target files. No-op (returns False) when no
    report is configured or none of the files have findings.
    """
    path = _resolve_report_path(report_path)
    if path is None:
        return False
    blocks = _load_blocks(path)
    if not blocks:
        return False
    selected = [blocks[f] for f in target_files if f in blocks]
    if not selected:
        return False
    combined = "\n\n".join(selected)
    gen_context["sapper_guidance"] = combined     # → micro-prime (engine appends to constraints)
    gen_context["sapper_alignment"] = combined    # → lead/drafter spec (spec_builder P0 section)
    logger.debug("sapper: injected findings for %d/%d target file(s)", len(selected), len(list(target_files)))
    return True
