"""Extended lint fix repair step (REQ-RPL-105).

Applies ``ruff check --fix`` for checkpoint-identified lint violations.
Subprocess hardening: ``shell=False``, argv-based paths, sanitized
environment (strips ``*_API_KEY``, ``*_SECRET``, ``*_TOKEN``).
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from ...logging_config import get_logger
from ..models import ElementContext, LintDiagnostic, RepairContext, RepairStepResult

logger = get_logger(__name__)

# Env var patterns to strip for subprocess hardening.
_SECRET_KEY_RE = re.compile(
    r"(API_KEY|SECRET|TOKEN)$",
    re.IGNORECASE,
)


class ExtendedLintFixStep:
    """Apply ruff --fix for lint violations identified in diagnostics."""

    name: str = "extended_lint_fix"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        # Collect fixable lint rule codes from diagnostics.
        fixable_codes: list[str] = []
        for diag in context.diagnostics:
            if isinstance(diag, LintDiagnostic) and diag.fixable and diag.rule:
                fixable_codes.append(diag.rule)

        if not fixable_codes:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        # Deduplicate while preserving order.
        seen: set[str] = set()
        unique_codes: list[str] = []
        for c in fixable_codes:
            if c not in seen:
                seen.add(c)
                unique_codes.append(c)

        select_arg = ",".join(unique_codes)

        # Write code to a temp file, run ruff on it, read back.
        tmp_path: Optional[Path] = None
        try:
            fd, tmp_str = tempfile.mkstemp(suffix=".py", prefix="rpl_lint_")
            tmp_path = Path(tmp_str)
            os.close(fd)
            tmp_path.write_text(code, encoding="utf-8")

            env = _sanitized_env()

            cmd = [
                "ruff", "check",
                "--fix",
                "--select", select_arg,
                "--no-cache",
                str(tmp_path),
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                env=env,
            )

            fixed_code = tmp_path.read_text(encoding="utf-8")

            if fixed_code == code:
                return RepairStepResult(
                    step_name=self.name,
                    modified=False,
                    code=code,
                    metrics={
                        "rules_targeted": unique_codes,
                        "ruff_returncode": result.returncode,
                    },
                )

            logger.debug(
                "ruff --fix applied %d rule(s) to %s",
                len(unique_codes), file_path,
            )

            return RepairStepResult(
                step_name=self.name,
                modified=True,
                code=fixed_code,
                metrics={
                    "rules_targeted": unique_codes,
                    "ruff_returncode": result.returncode,
                    "ruff_stdout": result.stdout[:500] if result.stdout else "",
                    "ruff_stderr": result.stderr[:500] if result.stderr else "",
                },
            )

        except FileNotFoundError:
            # ruff binary not installed — skip gracefully.
            logger.warning("ruff not found; skipping extended lint fix")
            return RepairStepResult(
                step_name=self.name,
                modified=False,
                code=code,
                metrics={"error": "ruff_not_found"},
            )
        except subprocess.TimeoutExpired:
            logger.warning("ruff timed out on %s", file_path)
            return RepairStepResult(
                step_name=self.name,
                modified=False,
                code=code,
                metrics={"error": "timeout"},
            )
        except OSError as exc:
            logger.warning("ruff subprocess error: %s", exc)
            return RepairStepResult(
                step_name=self.name,
                modified=False,
                code=code,
                metrics={"error": str(exc)},
            )
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass


def _sanitized_env() -> dict[str, str]:
    """Return a copy of ``os.environ`` with secret-bearing vars removed."""
    env: dict[str, str] = {}
    for key, val in os.environ.items():
        if _SECRET_KEY_RE.search(key):
            continue
        env[key] = val
    return env
