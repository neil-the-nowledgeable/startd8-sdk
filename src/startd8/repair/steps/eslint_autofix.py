"""ESLint auto-fix composite repair step (REQ-KZ-ND-402d Phase 3).

Runs ``eslint --fix`` with ``no-var`` + ``prefer-const`` rules for
smarter ``var`` → ``const``/``let`` conversion than the regex-based
``VarToConstStep``.  Falls back to Phase 2 text-based steps when
ESLint is not installed.

ESLint v10+ requires a flat config file — the step writes a temporary
``eslint.config.mjs`` alongside the target file and cleans up after.

**What ESLint handles better than Phase 2:**
- ``var`` → ``const`` only when the binding is never reassigned
- ``var`` → ``let`` when reassignment is detected (regex can't do this)

**What ESLint does NOT auto-fix (Phase 2 still needed internally):**
- ``no-duplicate-imports`` reports but doesn't fix — ``DedupRequireStep``
  handles this as a fallback
- Python contamination — ``ContaminationStripJsStep`` is separate

Only fires for JS/TS files.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from ..models import ElementContext, RepairContext, RepairStepResult
from ..vue_sfc_repair import (
    VueScriptRepairSlice,
    merge_script_back,
    synthetic_script_path,
    vue_script_slice,
)

_JS_EXTENSIONS = frozenset({".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"})

# Minimal ESLint flat config for auto-fix.
# no-var:       flags var declarations (auto-fixable → let)
# prefer-const: promotes let → const when never reassigned (auto-fixable)
_ESLINT_CONFIG = """\
export default [{ rules: { "no-var": "error", "prefer-const": "error" } }];
"""


class EslintAutoFixStep:
    """Run ``eslint --fix`` with fallback to Phase 2 text-based steps."""

    name: str = "eslint_autofix"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        sl = vue_script_slice(code, file_path)
        eff_code = sl.script if sl is not None else code
        eff_path = (
            synthetic_script_path(file_path, sl.inner_suffix)
            if sl is not None
            else file_path
        )
        if file_path.suffix.lower() not in _JS_EXTENSIONS and sl is None:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        # Try ESLint first
        if shutil.which("eslint") is not None:
            result = _run_eslint_fix(eff_code, eff_path.suffix)
            if result is not None:
                fixed_code, eslint_modified = result
                # Chain: run dedup_require after eslint (eslint can't fix it)
                final_code, dedup_modified = _run_dedup_fallback(
                    fixed_code, eff_path,
                )
                modified = eslint_modified or dedup_modified
                merged = merge_script_back(sl, code, final_code, modified)
                return RepairStepResult(
                    step_name=self.name,
                    modified=merged != code,
                    code=merged,
                    metrics={
                        "engine": "eslint",
                        "eslint_modified": eslint_modified,
                        "dedup_fallback": dedup_modified,
                    },
                )
            # ESLint failed (config error, timeout, etc.) — fall through

        # Fallback: Phase 2 text-based steps
        return _run_phase2_fallback(
            eff_code, context, eff_path, element_context, sl, code,
        )


def _run_eslint_fix(code: str, suffix: str) -> Optional[tuple[str, bool]]:
    """Run eslint --fix on code via temp file.

    Returns (fixed_code, was_modified) or None on failure.
    """
    tmpdir = None
    try:
        tmpdir = tempfile.mkdtemp(prefix="eslint_repair_")
        # Write the source file
        src_path = os.path.join(tmpdir, f"repair{suffix}")
        with open(src_path, "w", encoding="utf-8") as f:
            f.write(code)

        # Write the ESLint config
        config_path = os.path.join(tmpdir, "eslint.config.mjs")
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(_ESLINT_CONFIG)

        # Run eslint --fix — config auto-discovered from cwd (flat config).
        # Do NOT use --config with absolute path — ESLint v10 treats the
        # file as "outside of base path" and ignores it.
        subprocess.run(
            ["eslint", "--fix", src_path],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=tmpdir,
        )

        # Read back the (potentially) fixed file
        with open(src_path, encoding="utf-8") as f:
            fixed = f.read()

        modified = fixed != code
        return fixed, modified

    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    finally:
        if tmpdir:
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except OSError:
                pass


def _run_dedup_fallback(
    code: str,
    file_path: Path,
) -> tuple[str, bool]:
    """Run DedupRequireStep on code (ESLint can't auto-fix duplicate imports)."""
    from .dedup_require import DedupRequireStep

    step = DedupRequireStep()
    result = step(code, RepairContext(), file_path)
    return result.code, result.modified


def _run_phase2_fallback(
    code: str,
    context: RepairContext,
    file_path: Path,
    element_context: Optional[ElementContext],
    sl: VueScriptRepairSlice | None,
    original_full: str,
) -> RepairStepResult:
    """Run Phase 2 text-based steps sequentially as ESLint fallback."""
    from .dedup_require import DedupRequireStep
    from .var_to_const import VarToConstStep

    any_modified = False
    current = code

    for step_cls in (VarToConstStep, DedupRequireStep):
        step = step_cls()
        result = step(current, context, file_path, element_context)
        if result.modified:
            any_modified = True
            current = result.code

    merged = merge_script_back(sl, original_full, current, any_modified)
    return RepairStepResult(
        step_name="eslint_autofix",
        modified=merged != original_full,
        code=merged,
        metrics={"engine": "phase2_fallback"},
    )
