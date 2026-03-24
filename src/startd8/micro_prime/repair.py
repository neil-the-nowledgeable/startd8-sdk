"""Manifest-Guided Repair Pipeline (REQ-MP-400–408).

A 10-step ordered pipeline that repairs LLM-generated code before splicing
into skeleton files. Each step is non-destructive: if it would break
previously valid code, its changes are reverted (REQ-MP-406).

Steps:
    1. Fence stripping — remove markdown code fences
    2. Octal literal fix — convert Py2 octal ``0NNN`` → Py3 ``0oNNN``
    3. Over-generation trim — remove AST nodes not matching target FQN
    4. Bare statement wrapping — wrap body-only output in def/class
    5. Future import reorder — move ``from __future__`` to file top
    6. Indentation normalize — re-indent to 4-space
    7. Signature reconcile — restore canonical signature from manifest
    8. Import completion — add missing imports
    9. Duplicate removal — remove duplicate imports
   10. AST validation — final gate

Shared steps (1, 5, 6, 8, 9, 10) delegate to ``startd8.repair.steps``.
Micro-prime-specific steps (2, 3, 4, 7) remain local.

Structured logging and OTel metrics are emitted per run for repair
analysis (OLLAMA_QUALITY_RESEARCH_AGENDA Section 7).
"""

from __future__ import annotations

import ast
import re
import time
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from startd8.forward_manifest import ForwardElementSpec, ForwardFileSpec, InterfaceContract
from startd8.logging_config import get_logger
from startd8.micro_prime._ast_utils import find_element_node
from startd8.micro_prime.models import RepairAttribution, RepairStepResult
from startd8.repair.models import Diagnostic, ElementContext, RepairContext
from startd8.repair.steps.definition_order_fix import DefinitionOrderFixStep
from startd8.repair.steps.duplicate_removal import DuplicateRemovalStep
from startd8.repair.steps.fence_strip import FenceStripStep
from startd8.repair.steps.future_import_reorder import FutureImportReorderStep
from startd8.repair.steps.import_completion import ManifestImportCompletion
from startd8.repair.steps.indent_normalize import IndentNormalizeStep
from startd8.utils.code_extraction import extract_code_from_response
from startd8.utils.code_manifest import ElementKind

logger = get_logger(__name__)

# OTel instrumentation (graceful degradation when unavailable)
try:
    from opentelemetry import metrics as _otel_metrics
    _MP_REPAIR_METER = _otel_metrics.get_meter("startd8.micro_prime.repair")
    _mp_repair_attempts = _MP_REPAIR_METER.create_counter(
        "micro_prime.repair.attempts_total",
        description="Total micro-prime repair pipeline runs",
    )
    _mp_repair_recovered = _MP_REPAIR_METER.create_counter(
        "micro_prime.repair.recovered_total",
        description="Repairs that recovered invalid code to valid AST",
    )
    _mp_repair_step_applied = _MP_REPAIR_METER.create_counter(
        "micro_prime.repair.step_applied",
        description="Per-step application count",
    )
    _mp_repair_wall_clock = _MP_REPAIR_METER.create_histogram(
        "micro_prime.repair.wall_clock_ms",
        description="Wall-clock time per repair pipeline run",
    )
    _HAS_OTEL = True
except Exception:
    _mp_repair_attempts = _mp_repair_recovered = _mp_repair_step_applied = _mp_repair_wall_clock = None
    _HAS_OTEL = False

# Shared step instances
_shared_fence_strip = FenceStripStep()
_shared_future_import_reorder = FutureImportReorderStep()
_shared_indent_normalize = IndentNormalizeStep()
_shared_import_completion = ManifestImportCompletion()
_shared_duplicate_removal = DuplicateRemovalStep()
_shared_definition_order_fix = DefinitionOrderFixStep()


# ═══════════════════════════════════════════════════════════════════════════
# Repair step functions
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class RepairResult:
    """Result from running the manifest-guided repair pipeline (REQ-MP-400)."""

    code: str
    steps_applied: list[str]
    ast_valid: bool
    ast_valid_before: bool
    ast_valid_after: bool
    repair_recovered: bool
    metrics: dict[str, Any]
    step_results: list[RepairStepResult]
    last_error: Optional[str] = None


def _step_fence_strip(
    code: str,
    element: ForwardElementSpec,
    file_spec: Optional[ForwardFileSpec] = None,
    skeleton_source: Optional[str] = None,
) -> RepairStepResult:
    """Step 1: Strip markdown code fences (REQ-MP-400).

    Delegates to shared ``FenceStripStep``.
    """
    ctx = RepairContext()
    return _shared_fence_strip(code, ctx, Path("<element>"))


_LEADING_ZERO_INT_RE = re.compile(
    r"""
    (?<![.\w])   # not preceded by dot (float) or word char (identifier/hex/bin)
    0(\d+)       # leading zero followed by any digits
    (?!\w)       # not followed by word char (e.g. 0x, 0b, 0o, variable)
    """,
    re.VERBOSE,
)


def _leading_zero_replacer(match: re.Match) -> str:
    """Replace leading-zero integer: octal digits → 0o prefix, else strip zero."""
    digits = match.group(1)
    # All zeros (00, 000) → just 0
    stripped = digits.lstrip("0")
    if not stripped:
        return "0"
    if all(c in "01234567" for c in digits):
        # Pure octal digits (e.g. 0755) → 0o755
        return f"0o{digits}"
    # Contains 8 or 9 (e.g. 09, 0855) → strip leading zero (decimal intent)
    return stripped


def _step_octal_literal_fix(
    code: str,
    element: ForwardElementSpec,
    file_spec: Optional[ForwardFileSpec] = None,
    skeleton_source: Optional[str] = None,
) -> RepairStepResult:
    """Step 2: Fix leading-zero integer literals (REQ-MP-408).

    Python 3 rejects ALL leading-zero integer literals with
    ``SyntaxError: leading zeros in decimal integer literals``.
    Ollama models generate these in two forms:

    - Python 2-style octals: ``0755``, ``0644`` → converted to ``0o755``, ``0o644``
    - Decimal with stray leading zero: ``09``, ``0855`` → stripped to ``9``, ``855``

    This step runs before any AST-dependent steps.
    """
    fixed, count = _LEADING_ZERO_INT_RE.subn(_leading_zero_replacer, code)
    return RepairStepResult(
        step_name="octal_literal_fix",
        modified=count > 0,
        code=fixed,
        metrics={"octal_literals_fixed": count},
    )


def _step_over_generation_trim(
    code: str,
    element: ForwardElementSpec,
    file_spec: Optional[ForwardFileSpec] = None,
    skeleton_source: Optional[str] = None,
) -> RepairStepResult:
    """Step 3: Remove AST nodes not matching the target element (REQ-MP-401).

    If the LLM generated extra functions, classes, or statements beyond the
    target element, trim them. Only applies when the code parses successfully.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return RepairStepResult(
            step_name="over_generation_trim",
            modified=False,
            code=code,
            metrics={"parse_failed": True},
        )

    lines = code.splitlines()
    target_node = find_element_node(tree, element, search_all_classes=True)

    if target_node is None:
        return RepairStepResult(
            step_name="over_generation_trim",
            modified=False,
            code=code,
            metrics={"target_not_found": True},
        )

    trimmed = _slice_source_for_node(lines, target_node)
    # Preserve leading non-future imports.
    import_lines: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            import_lines.append(_slice_source_for_node(lines, node))
        elif isinstance(node, ast.ImportFrom):
            if node.module == "__future__":
                continue
            import_lines.append(_slice_source_for_node(lines, node))
    if import_lines:
        trimmed = "\n".join([l for l in import_lines if l] + [trimmed])

    if trimmed and trimmed.strip() != code.strip():
        return RepairStepResult(
            step_name="over_generation_trim",
            modified=True,
            code=trimmed,
            metrics={"nodes_removed": max(len(tree.body) - 1, 0)},
        )

    return RepairStepResult(
        step_name="over_generation_trim",
        modified=False,
        code=code,
    )


# Line-anchored pattern for markdown fence markers.  The old ``"```" in s``
# test matched backtick sequences inside string literals, producing false
# positives.  This regex requires the fence to be at the start of a line
# (with optional whitespace) followed by an optional language tag.
_FENCE_LINE_RE = re.compile(r"^\s*```[\w]*\s*$", re.MULTILINE)


def _detect_definition_line(code: str) -> bool:
    """Return True if *code* already starts with a def/class/decorator."""
    stripped = code.lstrip()
    return stripped.startswith(("def ", "async def ", "class ", "@"))


def _strip_residual_fences(code: str) -> tuple[str, bool]:
    """Strip residual markdown fences that survived fence_strip.

    Returns ``(cleaned_code, was_modified)``.  If fences are found they are
    removed via ``extract_code_from_response``; otherwise the input is
    returned unchanged.  (run-019/022 defence)
    """
    if not _FENCE_LINE_RE.search(code):
        return code, False
    cleaned = extract_code_from_response(code)
    if cleaned != code:
        logger.debug(
            "bare_statement_wrap: stripped residual fences from body (%d→%d chars)",
            len(code), len(cleaned),
        )
        return cleaned, True
    return code, False


def _hoist_leading_imports(
    raw_lines: list[str],
    file_spec: Optional[ForwardFileSpec],
) -> tuple[list[str], list[str]]:
    """Separate leading import lines from body lines.

    Returns ``(hoisted_imports, body_lines)`` where *hoisted_imports* are
    module-level imports to place above the def line and *body_lines* is the
    remaining code.  Imports that reference symbols defined in the same file
    (per *file_spec*) are dropped to avoid F811.  (run-014, run-017)
    """
    hoisted: list[str] = []
    first_body_idx = 0
    for i, line in enumerate(raw_lines):
        lstripped = line.lstrip()
        if not lstripped:
            continue
        if lstripped.startswith(("import ", "from ")):
            hoisted.append(lstripped)
            first_body_idx = i + 1
        else:
            break

    # Drop imports referencing symbols defined in the same file.
    if hoisted and file_spec is not None:
        local_names = {el.name for el in file_spec.elements}
        filtered: list[str] = []
        for imp in hoisted:
            if imp.startswith("from ") and " import " in imp:
                imported_part = imp.split(" import ", 1)[1]
                imported_names = [
                    n.strip().split(" as ")[0].strip() for n in imported_part.split(",")
                ]
                if all(n in local_names for n in imported_names):
                    logger.debug(
                        "Dropping hoisted import %r — all names defined locally", imp,
                    )
                    continue
            filtered.append(imp)
        hoisted = filtered

    body_lines = raw_lines[first_body_idx:]
    # Strip leading blank lines so indent calculation starts at real code.
    while body_lines and not body_lines[0].strip():
        body_lines = body_lines[1:]

    return hoisted, body_lines if body_lines else ["pass"]


def _normalize_body_indentation(body_lines: list[str]) -> list[str]:
    """Normalise body lines to zero indent before re-indenting under the def.

    Handles two Ollama patterns:
    1. All lines share a non-zero minimum indent — strip it uniformly.
    2. First line at column 0, rest carry spurious indent — strip common
       indent of lines 2+ *unless* line 1 ends with ``:`` (genuine block).
    """
    indents = [
        len(line) - len(line.lstrip())
        for line in body_lines
        if line.strip()
    ]
    if not indents:
        return body_lines

    min_indent = min(indents)
    if min_indent > 0:
        return [
            line[min_indent:] if line.strip() else ""
            for line in body_lines
        ]

    if len(indents) >= 2 and indents[0] == 0:
        first_content = body_lines[0].strip()
        is_block_start = first_content.endswith(":")
        rest_indents = [i for i in indents[1:] if i > 0]
        if rest_indents and not is_block_start:
            strip = min(rest_indents)
            return [body_lines[0]] + [
                line[strip:] if line.strip() else ""
                for line in body_lines[1:]
            ]

    return body_lines


def _wrap_body_in_def(
    sig_line: str,
    body_lines: list[str],
    hoisted_imports: list[str],
) -> str:
    """Indent *body_lines* under *sig_line* and prepend hoisted imports."""
    indented = "\n".join(
        f"    {line}" if line.strip() else "" for line in body_lines
    )
    wrapped = f"{sig_line}\n{indented}"
    if hoisted_imports:
        wrapped = "\n".join(hoisted_imports) + "\n\n" + wrapped
    return wrapped


def _step_bare_statement_wrap(
    code: str,
    element: ForwardElementSpec,
    file_spec: Optional[ForwardFileSpec] = None,
    skeleton_source: Optional[str] = None,
) -> RepairStepResult:
    """Step 3: Wrap body-only output in the manifest's def line (REQ-MP-407).

    Detects when the LLM returned only the function body (no def line) and
    wraps it in the canonical signature from the manifest.
    """
    if element.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE, ElementKind.TYPE_ALIAS):
        return RepairStepResult(
            step_name="bare_statement_wrap", modified=False, code=code,
        )

    if _detect_definition_line(code):
        return RepairStepResult(
            step_name="bare_statement_wrap", modified=False, code=code,
        )

    # Strip residual fences that survived fence_strip (run-019/022).
    code, fences_stripped = _strip_residual_fences(code)
    if fences_stripped and _detect_definition_line(code):
        return RepairStepResult(
            step_name="bare_statement_wrap", modified=True, code=code,
        )

    sig_line = _build_def_line(element)
    if sig_line is None:
        return RepairStepResult(
            step_name="bare_statement_wrap", modified=False, code=code,
        )

    hoisted_imports, body_lines = _hoist_leading_imports(
        code.splitlines(), file_spec,
    )

    # After hoisting, if the body already starts with def/class/decorator,
    # don't wrap — just reassemble with hoisted imports (run-016 pattern).
    first_body_stripped = body_lines[0].lstrip() if body_lines else ""
    if first_body_stripped.startswith(("def ", "async def ", "class ", "@")):
        reassembled = "\n".join(body_lines)
        if hoisted_imports:
            reassembled = "\n".join(hoisted_imports) + "\n\n" + reassembled
        return RepairStepResult(
            step_name="bare_statement_wrap",
            modified=bool(hoisted_imports),
            code=reassembled,
            metrics={"hoisted_imports": len(hoisted_imports), "already_wrapped": True},
        )

    body_lines = _normalize_body_indentation(body_lines)
    wrapped = _wrap_body_in_def(sig_line, body_lines, hoisted_imports)

    return RepairStepResult(
        step_name="bare_statement_wrap",
        modified=True,
        code=wrapped,
        metrics={
            "wrapped_body_lines": len(body_lines),
            "hoisted_imports": len(hoisted_imports),
        },
    )


def _step_future_import_reorder(
    code: str,
    element: ForwardElementSpec,
    file_spec: Optional[ForwardFileSpec] = None,
    skeleton_source: Optional[str] = None,
) -> RepairStepResult:
    """Step 4: Move ``from __future__`` imports to file top (REQ-RPL-107).

    Delegates to shared ``FutureImportReorderStep``.
    """
    ctx = RepairContext()
    return _shared_future_import_reorder(code, ctx, Path("<element>"))


def _step_indent_normalize(
    code: str,
    element: ForwardElementSpec,
    file_spec: Optional[ForwardFileSpec] = None,
    skeleton_source: Optional[str] = None,
) -> RepairStepResult:
    """Step 5: Normalize indentation to 4-space (REQ-MP-402).

    Delegates to shared ``IndentNormalizeStep``.
    """
    if skeleton_source:
        indent = _find_skeleton_indent(skeleton_source, element)
        if indent is not None and not _looks_like_definition(code):
            expanded = code.expandtabs(4)
            dedented = textwrap.dedent(expanded).strip()
            reindented = textwrap.indent(dedented, indent) if dedented else dedented
            if reindented != code:
                return RepairStepResult(
                    step_name="indent_normalize",
                    modified=True,
                    code=reindented,
                    metrics={"strategy": "skeleton"},
                )
            return RepairStepResult(
                step_name="indent_normalize",
                modified=False,
                code=code,
                metrics={"strategy": "skeleton", "no_change": True},
            )

    ec = ElementContext(parent_class=element.parent_class)
    ctx = RepairContext()
    return _shared_indent_normalize(code, ctx, Path("<element>"), ec)


def _step_signature_reconcile(
    code: str,
    element: ForwardElementSpec,
    file_spec: Optional[ForwardFileSpec] = None,
    skeleton_source: Optional[str] = None,
) -> RepairStepResult:
    """Step 6: Reconcile signature against manifest (REQ-MP-403).

    If the generated function has a different signature than the manifest
    specifies, replace it with the canonical signature.
    """
    if element.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE, ElementKind.TYPE_ALIAS):
        return RepairStepResult(
            step_name="signature_reconcile", modified=False, code=code,
        )
    if not element.signature:
        return RepairStepResult(
            step_name="signature_reconcile", modified=False, code=code,
        )

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return RepairStepResult(
            step_name="signature_reconcile", modified=False, code=code,
        )

    target_node = find_element_node(tree, element)

    if target_node is None:
        return RepairStepResult(
            step_name="signature_reconcile", modified=False, code=code,
        )

    # Build the canonical def line from manifest
    canonical_def = _build_def_line(element)
    if canonical_def is None:
        return RepairStepResult(
            step_name="signature_reconcile", modified=False, code=code,
        )

    # Extract current def line from source
    lines = code.splitlines()
    # Find the def line (may span multiple lines with parens)
    def_start = None
    def_end = None
    paren_depth = 0
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if def_start is None:
            if stripped.startswith(("def ", "async def ")):
                def_start = i
                paren_depth += line.count("(") - line.count(")")
                if paren_depth <= 0 and stripped.rstrip().endswith(":"):
                    def_end = i
                    break
        else:
            paren_depth += line.count("(") - line.count(")")
            if paren_depth <= 0:
                def_end = i
                break

    if def_start is None or def_end is None:
        return RepairStepResult(
            step_name="signature_reconcile", modified=False, code=code,
        )

    # Get the indentation of the original def line
    original_indent = lines[def_start][: len(lines[def_start]) - len(lines[def_start].lstrip())]

    # Replace the def line(s) with canonical
    new_lines = lines[:def_start] + [original_indent + canonical_def] + lines[def_end + 1 :]
    new_code = "\n".join(new_lines)

    if new_code == code:
        return RepairStepResult(
            step_name="signature_reconcile", modified=False, code=code,
        )

    return RepairStepResult(
        step_name="signature_reconcile",
        modified=True,
        code=new_code,
        metrics={"replaced_def_lines": def_end - def_start + 1},
    )


def _step_import_completion(
    code: str,
    element: ForwardElementSpec,
    file_spec: Optional[ForwardFileSpec] = None,
    skeleton_source: Optional[str] = None,
) -> RepairStepResult:
    """Step 7: Add missing imports from manifest (REQ-MP-404).

    Delegates to shared ``ManifestImportCompletion``.
    """
    imports = file_spec.imports if file_spec else None
    ec = ElementContext(imports=imports)
    ctx = RepairContext()
    return _shared_import_completion(code, ctx, Path("<element>"), ec)


def _step_duplicate_removal(
    code: str,
    element: ForwardElementSpec,
    file_spec: Optional[ForwardFileSpec] = None,
    skeleton_source: Optional[str] = None,
) -> RepairStepResult:
    """Step 8: Remove duplicate imports (REQ-RPL-104).

    Delegates to shared ``DuplicateRemovalStep``.
    """
    ctx = RepairContext()
    return _shared_duplicate_removal(code, ctx, Path("<element>"))


def _step_definition_order_fix(
    code: str,
    element: ForwardElementSpec,
    file_spec: Optional[ForwardFileSpec] = None,
    skeleton_source: Optional[str] = None,
) -> RepairStepResult:
    """Step 9: Reorder top-level definitions to resolve forward references.

    Fixes F821 errors from model emitting classes that reference functions
    defined later in the file.  File-whole only — element bodies have a
    single definition so ordering is irrelevant.
    """
    ctx = RepairContext()
    return _shared_definition_order_fix(code, ctx, Path("<file>"))


def _step_ast_validate(
    code: str,
    element: ForwardElementSpec,
    file_spec: Optional[ForwardFileSpec] = None,
    skeleton_source: Optional[str] = None,
) -> RepairStepResult:
    """Step 10: Final AST validation gate (REQ-MP-405).

    Delegates to shared ``AstValidateStep``.
    """
    is_method = bool(element.parent_class)
    valid, error = _validate_ast_with_error(code, is_method)
    metrics = {"valid": valid}
    if error:
        metrics["error"] = error
    return RepairStepResult(
        step_name="ast_validate",
        modified=False,
        code=code,
        metrics=metrics,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Pipeline orchestration
# ═══════════════════════════════════════════════════════════════════════════

# AC-R25: Step applicability metadata — single source of truth for which
# repair steps apply to element-body vs file-whole modes.
_STEP_APPLICABILITY: dict[str, frozenset[str]] = {
    "fence_strip":          frozenset({"element", "file"}),
    "octal_literal_fix":    frozenset({"element", "file"}),
    "over_generation_trim": frozenset({"element"}),
    "bare_statement_wrap":  frozenset({"element"}),
    "future_import_reorder": frozenset({"element"}),
    "indent_normalize":     frozenset({"element"}),
    "signature_reconcile":  frozenset({"element"}),
    "import_completion":    frozenset({"element"}),
    "duplicate_removal":       frozenset({"element", "file"}),
    "definition_order_fix":    frozenset({"file"}),
    "ast_validate":            frozenset({"element", "file"}),
}

# Ordered list of all repair steps (with step name for registry lookup)
_ALL_STEPS = [
    ("fence_strip", _step_fence_strip),
    ("octal_literal_fix", _step_octal_literal_fix),
    ("over_generation_trim", _step_over_generation_trim),
    ("bare_statement_wrap", _step_bare_statement_wrap),
    ("future_import_reorder", _step_future_import_reorder),
    ("indent_normalize", _step_indent_normalize),
    ("signature_reconcile", _step_signature_reconcile),
    ("import_completion", _step_import_completion),
    ("duplicate_removal", _step_duplicate_removal),
    ("definition_order_fix", _step_definition_order_fix),
    ("ast_validate", _step_ast_validate),
]

# Ordered list of element-body repair steps
_REPAIR_STEPS = [fn for _name, fn in _ALL_STEPS]


def _emit_repair_telemetry(
    result: "RepairResult",
    pipeline_mode: str,
    element_name: Optional[str] = None,
    file_path: Optional[str] = None,
    wall_clock_ms: float = 0,
) -> None:
    """Emit structured logging and OTel metrics for repair pipeline runs.

    Supports OLLAMA_QUALITY_RESEARCH_AGENDA Section 7 (repair pipeline analysis).
    """
    steps_applied = result.steps_applied
    log_extra = {
        "repair": {
            "pipeline_mode": pipeline_mode,
            "ast_valid_before": result.ast_valid_before,
            "ast_valid_after": result.ast_valid_after,
            "repair_recovered": result.repair_recovered,
            "steps_applied": steps_applied,
            "steps_count": len(steps_applied),
            "wall_clock_ms": round(wall_clock_ms, 1),
        }
    }
    if element_name:
        log_extra["repair"]["element_name"] = element_name
    if file_path:
        log_extra["repair"]["file_path"] = file_path
    logger.info(
        "micro_prime.repair.complete %s recovered=%s steps=%s",
        pipeline_mode,
        result.repair_recovered,
        steps_applied,
        extra=log_extra,
    )
    if _HAS_OTEL and _mp_repair_attempts is not None:
        try:
            _mp_repair_attempts.add(1, {"pipeline_mode": pipeline_mode})
            if result.repair_recovered:
                _mp_repair_recovered.add(1, {"pipeline_mode": pipeline_mode})
            for step in steps_applied:
                _mp_repair_step_applied.add(1, {"step": step, "pipeline_mode": pipeline_mode})
            if wall_clock_ms > 0 and _mp_repair_wall_clock is not None:
                _mp_repair_wall_clock.record(wall_clock_ms, {"pipeline_mode": pipeline_mode})
        except Exception:
            pass


def run_repair_pipeline(
    code: str,
    element: ForwardElementSpec,
    file_spec: Optional[ForwardFileSpec] = None,
    skeleton_source: Optional[str] = None,
    language_id: str = "python",
) -> RepairResult:
    """Run the full 8-step repair pipeline.

    Non-destructive guarantee (REQ-MP-406): if a step breaks previously
    valid code, its changes are reverted.

    Args:
        code: Raw LLM-generated code.
        element: Target manifest element.
        file_spec: File spec for import context.
        skeleton_source: Optional skeleton source for indent normalization.
        language_id: Target language for syntax validation dispatch.

    Returns:
        RepairResult with repaired code and step metadata.
    """
    start = time.monotonic()
    results: list[RepairStepResult] = []
    current = code
    is_method = bool(element.parent_class)
    ast_valid_before = _try_parse(current, is_method, language_id)

    for step_fn in _REPAIR_STEPS:
        was_valid_before = _try_parse(current, is_method, language_id)
        result = step_fn(current, element, file_spec, skeleton_source)
        results.append(result)

        if result.modified:
            # REQ-MP-406: Non-destructive guarantee
            is_valid_after = _try_parse(result.code, is_method, language_id)
            if was_valid_before and not is_valid_after:
                # Revert — this step broke valid code
                logger.debug(
                    "Repair step '%s' broke valid code for %s, reverting",
                    result.step_name,
                    element.name,
                )
                result.modified = False
                result.code = current
                result.metrics["reverted"] = True
            else:
                current = result.code

    # Determine AST validity + last error from ast_validate step
    ast_valid = _try_parse(current, is_method, language_id)
    last_error = None
    for r in results:
        if r.step_name == "ast_validate":
            ast_valid = bool(r.metrics.get("valid", ast_valid))
            last_error = r.metrics.get("error")
            break

    steps_applied = [r.step_name for r in results if r.modified]
    metrics = {r.step_name: r.metrics for r in results}
    ast_valid_after = ast_valid
    repair_recovered = (not ast_valid_before) and ast_valid_after

    result = RepairResult(
        code=current,
        steps_applied=steps_applied,
        ast_valid=ast_valid,
        ast_valid_before=ast_valid_before,
        ast_valid_after=ast_valid_after,
        repair_recovered=repair_recovered,
        metrics=metrics,
        step_results=results,
        last_error=last_error,
    )
    wall_clock_ms = (time.monotonic() - start) * 1000
    _emit_repair_telemetry(
        result,
        pipeline_mode="element",
        element_name=element.name,
        file_path=file_spec.file if file_spec else None,
        wall_clock_ms=wall_clock_ms,
    )
    return result


# ── AC-R18/R25: File-whole repair steps (derived from applicability registry) ──
# File-whole output is a complete Python file, not a body-only fragment.
# Body-only steps are excluded automatically via the "file" tag.
_FILE_REPAIR_STEPS = [
    fn for name, fn in _ALL_STEPS
    if "file" in _STEP_APPLICABILITY.get(name, frozenset())
]


def run_file_repair_pipeline(
    code: str,
    file_spec: Optional[ForwardFileSpec] = None,
    language_id: str = "python",
) -> RepairResult:
    """Run the file-whole repair pipeline (AC-R18).

    Uses only the repair steps that are safe for complete-file output.
    Body-only steps (over-generation trim, bare statement wrap, indent
    normalize, signature reconcile) are skipped because they assume
    single-element body fragments and can damage multi-element files.

    Args:
        code: Raw LLM-generated complete file.
        file_spec: File spec for import context.
        language_id: Target language for syntax validation dispatch.

    Returns:
        RepairResult with repaired code and step metadata.
    """
    start = time.monotonic()
    results: list[RepairStepResult] = []
    current = code
    # File-whole output is never a method body — always a complete file.
    is_method = False
    ast_valid_before = _try_parse(current, is_method, language_id)

    # Use a synthetic element for the step API (steps require an element
    # argument even though file-level steps don't use element-specific
    # fields like parent_class or signature).
    from startd8.utils.code_manifest import Signature
    synthetic_element = ForwardElementSpec(
        name="__file_whole__",
        kind=ElementKind.FUNCTION,
        signature=Signature(params=[], return_annotation=None),
    )

    for step_fn in _FILE_REPAIR_STEPS:
        was_valid_before = _try_parse(current, is_method, language_id)
        result = step_fn(current, synthetic_element, file_spec, None)
        results.append(result)

        if result.modified:
            is_valid_after = _try_parse(result.code, is_method, language_id)
            if was_valid_before and not is_valid_after:
                logger.debug(
                    "File repair step '%s' broke valid code, reverting",
                    result.step_name,
                )
                result.modified = False
                result.code = current
                result.metrics["reverted"] = True
            else:
                current = result.code

    ast_valid = _try_parse(current, is_method, language_id)
    last_error = None
    for r in results:
        if r.step_name == "ast_validate":
            ast_valid = bool(r.metrics.get("valid", ast_valid))
            last_error = r.metrics.get("error")
            break

    steps_applied = [r.step_name for r in results if r.modified]
    metrics = {r.step_name: r.metrics for r in results}
    ast_valid_after = ast_valid
    repair_recovered = (not ast_valid_before) and ast_valid_after

    result = RepairResult(
        code=current,
        steps_applied=steps_applied,
        ast_valid=ast_valid,
        ast_valid_before=ast_valid_before,
        ast_valid_after=ast_valid_after,
        repair_recovered=repair_recovered,
        metrics=metrics,
        step_results=results,
        last_error=last_error,
    )
    wall_clock_ms = (time.monotonic() - start) * 1000
    _emit_repair_telemetry(
        result,
        pipeline_mode="file",
        file_path=file_spec.file if file_spec else None,
        wall_clock_ms=wall_clock_ms,
    )
    return result


def to_escalation_repair_outcome(
    element_fqn: str,
    raw_code: str,
    result: RepairResult,
) -> "EscalationRepairOutcome":
    """Convert internal RepairResult to Keiyaku boundary contract (K-9).

    Translates the internal repair pipeline result into a structured
    ``EscalationRepairOutcome`` suitable for escalation handoffs and
    observability, preserving machine-readable diagnostics.

    Args:
        element_fqn: Fully-qualified element name (e.g. "MyClass.my_method").
        raw_code: The original code before any repair steps.
        result: The RepairResult from ``run_repair_pipeline``.

    Returns:
        An ``EscalationRepairOutcome`` with structured step records.
    """
    from startd8.micro_prime.models import (
        EscalationRepairOutcome,
        RepairStepOutcome,
    )

    step_outcomes = []
    for sr in result.step_results:
        # Derive a human-readable detail from step metrics
        detail_parts = []
        if sr.modified:
            detail_parts.append(f"{sr.step_name} modified code")
        if sr.metrics.get("reverted"):
            detail_parts.append("reverted (broke valid code)")
        if sr.metrics.get("nodes_removed"):
            detail_parts.append(
                f"removed {sr.metrics['nodes_removed']} node(s)"
            )
        if sr.metrics.get("wrapped_body_lines"):
            detail_parts.append(
                f"wrapped {sr.metrics['wrapped_body_lines']} body line(s)"
            )
        if sr.metrics.get("replaced_def_lines"):
            detail_parts.append(
                f"replaced {sr.metrics['replaced_def_lines']} def line(s)"
            )
        if sr.metrics.get("imports_added"):
            detail_parts.append(
                f"added {sr.metrics['imports_added']} import(s)"
            )
        if sr.metrics.get("imports_removed"):
            detail_parts.append(
                f"removed {sr.metrics['imports_removed']} duplicate import(s)"
            )
        detail = "; ".join(detail_parts) if detail_parts else "no change"

        # Determine AST validity after this step — use metrics if available
        ast_valid = sr.metrics.get("valid", None)
        if ast_valid is None:
            # For non-ast_validate steps, infer from result validity
            ast_valid = result.ast_valid_after

        step_outcomes.append(RepairStepOutcome(
            step=sr.step_name,
            modified=sr.modified,
            ast_valid_after=bool(ast_valid),
            detail=detail,
        ))

    # Determine final verdict
    if result.repair_recovered:
        verdict = "recovered"
    elif result.ast_valid_before == result.ast_valid_after and not result.steps_applied:
        verdict = "unchanged"
    elif not result.ast_valid_after:
        verdict = "failed"
    else:
        verdict = "recovered" if result.steps_applied else "unchanged"

    return EscalationRepairOutcome(
        element_fqn=element_fqn,
        ast_valid_before=result.ast_valid_before,
        ast_valid_after=result.ast_valid_after,
        steps=step_outcomes,
        final_verdict=verdict,
        lines_before=len(raw_code.splitlines()) if raw_code else 0,
        lines_after=len(result.code.splitlines()) if result.code else 0,
    )


def repair(
    raw_output: str,
    target: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    contracts: list[InterfaceContract],
    skeleton_source: Optional[str] = None,
) -> RepairResult:
    """Run the full repair pipeline (REQ-MP-400 interface)."""
    _ = contracts  # Reserved for future steps; unused for now
    return run_repair_pipeline(
        raw_output,
        target,
        file_spec,
        skeleton_source=skeleton_source,
    )


def build_repair_attribution(
    step_results: list[RepairStepResult],
) -> RepairAttribution:
    """Build a ``RepairAttribution`` from a list of step results (REQ-MP-601).

    Maps each step's ``modified`` flag and ``metrics`` dict into the
    granular attribution fields.
    """
    attr = RepairAttribution()

    for r in step_results:
        if not r.modified:
            continue

        if r.step_name == "fence_strip":
            attr.fence_stripped = True

        elif r.step_name == "over_generation_trim":
            attr.trimmed = True
            attr.nodes_removed = r.metrics.get("nodes_removed", 0)

        elif r.step_name == "bare_statement_wrap":
            attr.bare_wrapped = True

        elif r.step_name == "indent_normalize":
            attr.indent_source = r.metrics.get("strategy", "unknown")

        elif r.step_name == "signature_reconcile":
            replaced_lines = r.metrics.get("replaced_def_lines", 0)
            attr.params_changed = replaced_lines
            attr.return_type_restored = replaced_lines > 0

        elif r.step_name == "import_completion":
            attr.imports_added = r.metrics.get("imports_added", 0)
            import_names = r.metrics.get("import_names", []) or []
            for name in import_names:
                if name not in attr.import_names:
                    attr.import_names.append(name)

        elif r.step_name == "duplicate_removal":
            attr.imports_removed = r.metrics.get("imports_removed", 0)

    return attr


# ═══════════════════════════════════════════════════════════════════════════
# File-whole contractor repair bridge (tier 2)
# ═══════════════════════════════════════════════════════════════════════════


def _translate_validation_failure(
    reason: str,
    file_path: str,
) -> list[Diagnostic]:
    """Translate a ``_validate_file_whole_result`` reason into diagnostics.

    Maps the failure reason string to ``Diagnostic`` objects with the
    appropriate category so the contractor routing table selects the
    right repair steps.
    """
    if not reason or reason == "empty output":
        return []

    if reason.startswith("ast.parse() failed"):
        return [Diagnostic(category="syntax", file=file_path, message=reason)]

    if reason.startswith("nested duplicate function"):
        return [Diagnostic(category="syntax", file=file_path, message=reason)]

    if reason == "contains skeleton markers":
        return [Diagnostic(category="lint", file=file_path, message=reason)]

    # Stub-only or missing elements — semantic category
    if "stub" in reason.lower() or "missing" in reason.lower():
        return [Diagnostic(category="semantic", file=file_path, message=reason)]

    # Fallback: treat as syntax (most broadly routed category)
    return [Diagnostic(category="syntax", file=file_path, message=reason)]


def run_file_whole_contractor_repair(
    code: str,
    reason: str,
    file_path: str,
) -> RepairResult:
    """Escalate file-whole repair to the full contractor pipeline.

    Bridges micro prime's file-whole path to the contractor repair
    orchestrator (12 steps with routing, circuit breaker, OTel).
    Called as tier 2 when ``run_file_repair_pipeline`` (4 steps) fails.

    Args:
        code: Raw LLM-generated complete file.
        reason: Failure reason from ``_validate_file_whole_result``.
        file_path: Relative file path for diagnostics.

    Returns:
        RepairResult translated from the contractor's RepairOutcome.
    """
    diagnostics = _translate_validation_failure(reason, file_path)
    if not diagnostics:
        return RepairResult(
            code=code,
            steps_applied=[],
            ast_valid=_try_parse(code),
            ast_valid_before=_try_parse(code),
            ast_valid_after=_try_parse(code),
            repair_recovered=False,
            metrics={},
            step_results=[],
        )

    # Lazy import to avoid circular dependency
    from startd8.repair.config import RepairConfig as ContractorRepairConfig
    from startd8.repair.orchestrator import run_file_repair

    path_key = Path(file_path)
    config = ContractorRepairConfig()
    outcome = run_file_repair(
        files={path_key: code},
        diagnostics=diagnostics,
        config=config,
        project_root=Path("."),
    )

    # Extract single-file result
    repaired_code = outcome.repaired_files.get(path_key, code)
    ast_valid_before = _try_parse(code)
    ast_valid_after = _try_parse(repaired_code)

    # Collect step results from the file result (if present)
    step_results: list[RepairStepResult] = []
    if outcome.file_results:
        fr = outcome.file_results[0]
        step_results = [
            RepairStepResult(
                step_name=sr.step_name,
                modified=sr.modified,
                code=sr.code,
                metrics=sr.metrics,
            )
            for sr in fr.step_results
        ]

    return RepairResult(
        code=repaired_code,
        steps_applied=outcome.steps_applied,
        ast_valid=ast_valid_after,
        ast_valid_before=ast_valid_before,
        ast_valid_after=ast_valid_after,
        repair_recovered=(not ast_valid_before) and ast_valid_after,
        metrics={r.step_name: r.metrics for r in step_results},
        step_results=step_results,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _build_def_line(element: ForwardElementSpec) -> Optional[str]:
    """Build a canonical def/async def line from the manifest element.

    AC-R12: Delegates to the single canonical renderer in models.py.
    """
    from startd8.micro_prime.models import render_def_line
    return render_def_line(element)


def _node_start_line(node: ast.AST) -> int:
    """Return starting line index including decorators."""
    start = getattr(node, "lineno", 1)
    decorators = getattr(node, "decorator_list", None) or []
    for dec in decorators:
        dec_line = getattr(dec, "lineno", None)
        if dec_line is not None:
            start = min(start, dec_line)
    return start


def _slice_source_for_node(lines: list[str], node: ast.AST) -> str:
    """Slice original source lines for a node (preserve exact text)."""
    start = _node_start_line(node)
    end = getattr(node, "end_lineno", None) or getattr(node, "lineno", None)
    if end is None:
        return ""
    return "\n".join(lines[start - 1: end])


def _looks_like_definition(code: str) -> bool:
    """Return True if code starts with def/async def/class/decorator."""
    stripped = (code or "").lstrip()
    return stripped.startswith(("def ", "async def ", "class ", "@"))


def _find_skeleton_indent(
    skeleton: str,
    element: ForwardElementSpec,
) -> Optional[str]:
    """Find indentation for the target element's stub in skeleton."""
    if not skeleton:
        return None
    try:
        tree = ast.parse(skeleton)
    except SyntaxError:
        return None

    lines = skeleton.splitlines()
    target = find_element_node(tree, element)

    if target is None:
        return None

    for stmt in getattr(target, "body", []):
        if isinstance(stmt, ast.Raise):
            lineno = getattr(stmt, "lineno", None)
            if lineno is not None and 0 < lineno <= len(lines):
                line = lines[lineno - 1]
                return line[: len(line) - len(line.lstrip())]
    return None


def _validate_ast_with_error(code: str, is_method: bool = False) -> tuple[bool, Optional[str]]:
    """Validate code via ast.parse(), returning error details if invalid."""
    try:
        ast.parse(code)
        return True, None
    except SyntaxError as exc:
        err = exc

    if is_method:
        try:
            wrapped = "class _Wrapper:\n" + textwrap.indent(code, "    ")
            ast.parse(wrapped)
            return True, None
        except SyntaxError as exc:
            err = exc

    if err is None:
        return False, None

    detail = err.msg
    if err.lineno is not None:
        detail += f" (line {err.lineno}"
        if err.offset is not None:
            detail += f":{err.offset}"
        detail += ")"
    return False, detail


# Python keywords and builtins that are never valid import targets
_INVALID_IMPORT_MODULES = frozenset({
    "self", "cls", "True", "False", "None",
})


def _is_allowed_import(
    node: ast.Import | ast.ImportFrom,
    file_spec: Optional[ForwardFileSpec],
) -> bool:
    """Check if an import node is allowed by the manifest allow list.

    Rejects:
    - ``from __future__`` imports (skeleton already has them).
    - Modules that are Python keywords/builtins (e.g. ``import self``).
    - Imports not present in ``file_spec.imports`` when a manifest is available.

    When no ``file_spec`` is provided, falls back to rejecting only
    ``__future__`` and obviously-invalid modules.
    """
    # Always reject __future__ — skeleton already has them at file level
    if isinstance(node, ast.ImportFrom) and node.module == "__future__":
        return False

    # Reject obviously-invalid module names
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name in _INVALID_IMPORT_MODULES:
                return False
    elif isinstance(node, ast.ImportFrom) and node.module:
        root = node.module.split(".")[0]
        if root in _INVALID_IMPORT_MODULES:
            return False

    # If no manifest, allow (best-effort — only reject obvious junk)
    if file_spec is None or not file_spec.imports:
        return True

    # Build a set of allowed (module, kind) pairs from the manifest
    allowed_modules: set[str] = set()
    for imp in file_spec.imports:
        allowed_modules.add(imp.module)
        # Also allow root package (e.g. "grpc" for "grpc_health.v1")
        root = imp.module.split(".")[0]
        allowed_modules.add(root)

    if isinstance(node, ast.Import):
        return all(
            alias.name.split(".")[0] in allowed_modules
            for alias in node.names
        )
    elif isinstance(node, ast.ImportFrom) and node.module:
        root = node.module.split(".")[0]
        return root in allowed_modules

    return True


def _try_parse(
    code: str,
    is_method: bool = False,
    language_id: str = "python",
) -> bool:
    """Validate code syntax, dispatching by language.

    Python: ``ast.parse()`` with class-wrapper fallback for methods.
    C#: tree-sitter via ``csharp_parser.validate_csharp_syntax()`` if
        available, else assume valid (the C# repair steps validate
        independently).
    Go/Java/Node.js: language-specific syntax check or assume valid.
    """
    if language_id == "python" or not language_id:
        try:
            ast.parse(code)
            return True
        except SyntaxError:
            pass
        if is_method:
            try:
                wrapped = "class _Wrapper:\n" + textwrap.indent(code, "    ")
                ast.parse(wrapped)
                return True
            except SyntaxError:
                pass
        return False

    if language_id == "csharp":
        try:
            from startd8.languages.csharp_parser import validate_csharp_syntax
            valid, _ = validate_csharp_syntax(code)
            return valid
        except ImportError:
            return True  # tree-sitter unavailable — assume valid

    if language_id == "go":
        try:
            from startd8.repair.steps._go_tool_runner import run_go_tool
            result = run_go_tool(code, ["gofmt", "-e"])
            return result.returncode == 0 if result.tool_found else True
        except ImportError:
            return True

    if language_id in ("java", "nodejs"):
        # No in-process parser available — assume valid.
        # Validation happens via the language's own syntax validate step.
        return True

    # Unknown language — assume valid to avoid false escalation
    return True
