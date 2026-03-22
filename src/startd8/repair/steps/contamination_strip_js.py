"""JavaScript contamination strip repair step (REQ-KZ-ND-402d Phase 2).

Removes lines containing Python fingerprints from JavaScript/TypeScript
source files.  Reuses the fingerprint patterns from
``nodejs_semantic_checks._check_python_contamination()``.

Context-aware: ``self.`` is only matched at statement level (line-start
anchor) to avoid false positives in string literals like ``"yourself."``.
Comment lines are skipped.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..models import ElementContext, RepairContext, RepairStepResult

_JS_EXTENSIONS = frozenset({".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"})

# Python fingerprints — same set as nodejs_semantic_checks.py
_PY_FINGERPRINTS = (
    "def ", "import os", "from __future__",
    "#!/usr/bin/env python",
)

# self. requires line-start anchor (QW-1 — avoids "yourself." FP)
_SELF_DOT_RE = re.compile(r'^\s*self\.')

# def at statement level
_DEF_RE = re.compile(r'^\s*def\s+\w+\s*\(')


class ContaminationStripJsStep:
    """Remove Python fingerprint lines from JS/TS files."""

    name: str = "contamination_strip_js"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        if file_path.suffix.lower() not in _JS_EXTENSIONS:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        lines = code.splitlines(keepends=True)
        keep: list[str] = []
        removed_count = 0
        patterns_found: set[str] = set()

        for line in lines:
            stripped = line.strip()

            # Skip comment lines — don't remove them even if they
            # happen to contain a fingerprint substring
            if stripped.startswith("//") or stripped.startswith("/*"):
                keep.append(line)
                continue

            matched = False

            # Check self. with line-start anchor
            if _SELF_DOT_RE.match(line):
                patterns_found.add("self.")
                matched = True

            # Check def at statement level
            if not matched and _DEF_RE.match(line):
                patterns_found.add("def ")
                matched = True

            # Check other fingerprints at line start
            if not matched:
                for fp in _PY_FINGERPRINTS:
                    if fp == "def ":
                        continue  # handled above
                    if stripped.startswith(fp):
                        patterns_found.add(fp)
                        matched = True
                        break

            if matched:
                removed_count += 1
            else:
                keep.append(line)

        if removed_count == 0:
            return RepairStepResult(
                step_name=self.name,
                modified=False,
                code=code,
                metrics={"lines_removed": 0, "patterns_matched": []},
            )

        return RepairStepResult(
            step_name=self.name,
            modified=True,
            code="".join(keep),
            metrics={
                "lines_removed": removed_count,
                "patterns_matched": sorted(patterns_found),
            },
        )
