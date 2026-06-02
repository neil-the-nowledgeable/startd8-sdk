"""Data models for the repair-retry pass (Inc 1, FR-2).

A ``RetryViolation`` is the normalized form of one cross-file contract violation
extracted from a run's ``prime-postmortem-report.json``. ``RetryDisposition`` is
the per-violation outcome the engine assigns later (Inc 6).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RetryDisposition(str, Enum):
    """Per-violation outcome of a repair-retry pass.

    ``str`` mixin so the value serializes cleanly into the report JSON (FR-10).
    """

    REWRITTEN = "rewritten"  # rewritable-path → import_path_rename (FR-4)
    SCAFFOLDED = "scaffolded"  # missing target created (FR-5/FR-6)
    ROLLED_BACK = "rolled_back"  # fix applied then reverted by re-validation (FR-7)
    NEEDS_REGEN = (
        "needs_regen"  # feature-level residue, has a task_filter_token (FR-8, R2-F5)
    )
    UNSCAFFOLDED_ASSET = (
        "unscaffolded_asset"  # non-feature co-file left missing, no token (FR-8, R2-F5)
    )
    ALREADY_RESOLVED = "already_resolved"  # live-state pre-filter: already fixed on disk (FR-11, R4-F1)


@dataclass(frozen=True)
class RetryViolation:
    """One normalized cross-file contract violation from the postmortem report.

    Attributes:
        feature_id: The owning feature (e.g. ``"PI-012"``).
        file_path: The importing file, as ``disk_compliance.file_path`` (the
            run-relative path the on-disk artifacts live under).
        category: The semantic-issue category (v1 acts on ``"unresolvable_import"``).
        specifier: The parsed import specifier (e.g. ``"./StepNav.module.css"``);
            ``""`` when the message could not be parsed (``parse_ok`` is then False).
        message: The raw structured message (kept verbatim for the report + debugging).
        parse_ok: False when no specifier could be parsed from ``message`` — the
            violation is **not** dropped (R1-F1); a downstream consumer routes it to
            a ``needs_regen`` worklist entry with ``reason="unparseable_message"``.
    """

    feature_id: str
    file_path: str
    category: str
    specifier: str
    message: str
    parse_ok: bool = True
