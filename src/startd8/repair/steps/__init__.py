"""Repair step implementations.

Each step implements the ``RepairStep`` protocol from ``repair.protocol``.
"""

from .ast_validate import AstValidateStep
from .bracket_balance import BracketBalanceStep
from .class_body_dedup import ClassBodyDeduplicationStep
from .definition_order_fix import DefinitionOrderFixStep
from .dunder_all_fix import DunderAllFixStep
from .duplicate_removal import DuplicateRemovalStep
from .extended_lint_fix import ExtendedLintFixStep
from .fence_strip import FenceStripStep
from .future_import_reorder import FutureImportReorderStep
from .import_completion import ErrorDrivenImportCompletion, ManifestImportCompletion
from .indent_normalize import IndentNormalizeStep
from .semantic_import_fix import SemanticImportFixStep
from .semantic_method_fix import SemanticMethodFixStep
from .semantic_method_resolution_fix import SemanticMethodResolutionFixStep
from .unused_variable_removal import UnusedVariableRemovalStep
from .variable_initialization import VariableInitializationStep

__all__ = [
    "AstValidateStep",
    "BracketBalanceStep",
    "ClassBodyDeduplicationStep",
    "DefinitionOrderFixStep",
    "DunderAllFixStep",
    "DuplicateRemovalStep",
    "ExtendedLintFixStep",
    "FenceStripStep",
    "FutureImportReorderStep",
    "ErrorDrivenImportCompletion",
    "IndentNormalizeStep",
    "ManifestImportCompletion",
    "SemanticImportFixStep",
    "SemanticMethodFixStep",
    "SemanticMethodResolutionFixStep",
    "UnusedVariableRemovalStep",
    "VariableInitializationStep",
]
