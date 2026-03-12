"""Repair step implementations.

Each step implements the ``RepairStep`` protocol from ``repair.protocol``.
"""

from .ast_validate import AstValidateStep
from .bracket_balance import BracketBalanceStep
from .class_body_dedup import ClassBodyDeduplicationStep
from .duplicate_removal import DuplicateRemovalStep
from .extended_lint_fix import ExtendedLintFixStep
from .fence_strip import FenceStripStep
from .future_import_reorder import FutureImportReorderStep
from .import_completion import ErrorDrivenImportCompletion, ManifestImportCompletion
from .indent_normalize import IndentNormalizeStep

__all__ = [
    "AstValidateStep",
    "BracketBalanceStep",
    "ClassBodyDeduplicationStep",
    "DuplicateRemovalStep",
    "ExtendedLintFixStep",
    "FenceStripStep",
    "FutureImportReorderStep",
    "ErrorDrivenImportCompletion",
    "IndentNormalizeStep",
    "ManifestImportCompletion",
]
