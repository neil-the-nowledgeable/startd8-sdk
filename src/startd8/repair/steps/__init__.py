"""Repair step implementations.

Each step implements the ``RepairStep`` protocol from ``repair.protocol``.
"""

from .ast_validate import AstValidateStep
from .bracket_balance import BracketBalanceStep
from .csharp_convention_fix import CSharpConventionFixStep
from .csharp_syntax_validate import CSharpSyntaxValidateStep
from .go_contamination_strip import GoPythonContaminationStripStep
from .go_dot_import_cleanup import GoDotImportCleanupStep
from .go_syntax_validate import GoSyntaxValidateStep
from .go_unchecked_error import GoUncheckedErrorFixStep
from .java_import_sort import JavaImportSortStep
from .java_sql_parameterize import JavaSqlParameterizeStep
from .java_syntax_validate import JavaSyntaxValidateStep
from .js_syntax_validate import JsSyntaxValidateStep
from .contamination_strip_js import ContaminationStripJsStep
from .dedup_require import DedupRequireStep
from .eslint_autofix import EslintAutoFixStep
from .shebang_strip import ShebangStripStep
from .var_to_const import VarToConstStep
from .class_body_dedup import ClassBodyDeduplicationStep
from .definition_order_fix import DefinitionOrderFixStep
from .dunder_all_fix import DunderAllFixStep
from .duplicate_removal import DuplicateRemovalStep
from .extended_lint_fix import ExtendedLintFixStep
from .fence_strip import FenceStripStep
from .future_import_reorder import FutureImportReorderStep
from .import_completion import ErrorDrivenImportCompletion, ManifestImportCompletion
from .indent_normalize import IndentNormalizeStep
from .semantic_discarded_return_fix import SemanticDiscardedReturnFixStep
from .semantic_duplicate_main_fix import SemanticDuplicateMainFixStep
from .semantic_import_fix import SemanticImportFixStep
from .semantic_method_fix import SemanticMethodFixStep
from .semantic_method_resolution_fix import SemanticMethodResolutionFixStep
from .sql_parameterize import SqlParameterizeStep
from .todo_uncomment import TodoUncommentStep
from .unused_variable_removal import UnusedVariableRemovalStep
from .variable_initialization import VariableInitializationStep

__all__ = [
    "AstValidateStep",
    "BracketBalanceStep",
    "CSharpConventionFixStep",
    "CSharpSyntaxValidateStep",
    "GoPythonContaminationStripStep",
    "GoDotImportCleanupStep",
    "GoSyntaxValidateStep",
    "GoUncheckedErrorFixStep",
    "JavaImportSortStep",
    "JavaSqlParameterizeStep",
    "JavaSyntaxValidateStep",
    "JsSyntaxValidateStep",
    "ContaminationStripJsStep",
    "DedupRequireStep",
    "EslintAutoFixStep",
    "ShebangStripStep",
    "VarToConstStep",
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
    "SemanticDiscardedReturnFixStep",
    "SemanticDuplicateMainFixStep",
    "SemanticImportFixStep",
    "SemanticMethodFixStep",
    "SemanticMethodResolutionFixStep",
    "SqlParameterizeStep",
    "TodoUncommentStep",
    "UnusedVariableRemovalStep",
    "VariableInitializationStep",
]
