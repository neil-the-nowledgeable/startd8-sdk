# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""CRP Appendix A/B/C scaffold — owned by WLQ, matching ``new-cnvrg-rvw-prmpt``.

The Capability-Delivery Loop generator
(``~/Documents/dev/cap-dev-pipe/new-cnvrg-rvw-prmpt.sh``) initializes the
``## Appendix: Iterative Review Log`` scaffold idempotently before building a
review prompt. WLQ does the same on render/drain so reviewers **only append**
a ``#### Review Round`` under Appendix C — never create the scaffold,
including when a project ``agent_template_path`` bypasses the shell renderer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from ...logging_config import get_logger

logger = get_logger(__name__)

#: Detection key shared with ``new-cnvrg-rvw-prmpt.sh`` (``SCAFFOLD_MARKER``).
SCAFFOLD_MARKER = "## Appendix: Iterative Review Log"

#: Canonical empty A/B/C scaffold body (keep in sync with the shell script).
REVIEW_LOG_SCAFFOLD = """\
---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)
"""


def has_review_log_scaffold(path: Path) -> bool:
    """True when *path* already contains the Iterative Review Log marker."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return False
    return SCAFFOLD_MARKER in text


def ensure_review_log_scaffold(path: Path) -> bool:
    """Append the canonical empty A/B/C scaffold when absent (idempotent).

    Returns ``True`` when the scaffold was written, ``False`` when already
    present. Raises ``FileNotFoundError`` if *path* does not exist.
    """
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(f"CRP source document missing: {target}")
    if has_review_log_scaffold(target):
        return False
    with target.open("a", encoding="utf-8") as handle:
        if target.stat().st_size > 0:
            handle.write("\n")
        handle.write(REVIEW_LOG_SCAFFOLD)
        if not REVIEW_LOG_SCAFFOLD.endswith("\n"):
            handle.write("\n")
    logger.info("Initialized CRP review-log scaffold in %s", target.resolve())
    return True


def ensure_source_scaffolds(paths: Iterable[Path]) -> List[Path]:
    """Ensure A/B/C scaffolds for every source path; return paths newly scaffolded."""
    initialized: List[Path] = []
    for path in paths:
        if ensure_review_log_scaffold(Path(path)):
            initialized.append(Path(path).resolve())
    return initialized
