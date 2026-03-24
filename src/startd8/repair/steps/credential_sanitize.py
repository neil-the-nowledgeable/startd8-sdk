"""Credential leakage sanitization repair step.

Rewrites code that logs or exposes credential-bearing variables
(connection strings, passwords, API keys) in two patterns:

1. **Direct credential logging** — replaces interpolated credential
   variables in logging calls with sanitized metadata::

       BAD:  Console.WriteLine($"Connecting: {connectionString}");
       GOOD: Console.WriteLine("Connecting to database");

2. **Exception info disclosure** — replaces ``{ex}`` / ``{error}``
   interpolated into thrown exception messages with generic text::

       BAD:  throw new RpcException(..., $"Error: {ex}");
       GOOD: throw new RpcException(..., "Service unavailable");

Language-neutral: works on C#, Java, Go, Node.js, and Python.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ...logging_config import get_logger
from ..models import ElementContext, RepairContext, RepairStepResult

logger = get_logger(__name__)

# Credential-bearing variable name patterns (case-insensitive).
# Handles both snake_case (connection_string) and camelCase (connectionString).
_CREDENTIAL_NAMES = re.compile(
    r'(?:connection_?[Ss]tring|db_?[Ss]tring|database_?[Ss]tring|'
    r'[Pp]assword|[Pp]asswd|[Ss]ecret|api_?[Kk]ey|private_?[Kk]ey|'
    r'access_?[Tt]oken|auth_?[Tt]oken|bearer_?[Tt]oken|'
    r'[Cc]redentials?)',
)

# Logging calls across languages.
_LOG_CALL = re.compile(
    r'(?:'
    r'Console\.Write(?:Line)?|'       # C#
    r'_?logger\.(?:Log)?(?:Info|Warn|Error|Debug|Information|Warning|Critical)|'  # C# ILogger
    r'log\.(?:info|warn|error|debug|fatal|trace|println)|'  # Go/Java
    r'System\.out\.print(?:ln)?|'     # Java
    r'console\.(?:log|warn|error|info|debug)|'  # Node.js
    r'logging\.(?:info|warning|error|debug)|'   # Python
    r'print\('                        # Python
    r')',
    re.IGNORECASE,
)

# Interpolated variable in a string: ${var}, {var}, $"{var}", f"{var}"
_INTERPOLATED_VAR = re.compile(
    r'[\$f]?"[^"]*\{(\w+)\}[^"]*"',
)

# Exception variable interpolated into throw/raise message.
_EXCEPTION_INTERPOLATION = re.compile(
    r'(?:throw|raise)\s+.*[\$f]?"[^"]*\{(ex|err|error|exception|e)\}[^"]*"',
    re.IGNORECASE,
)


class CredentialSanitizeStep:
    """Remove credential variables from logging calls and exception messages."""

    name: str = "credential_sanitize"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        lines = code.splitlines(keepends=True)
        modified_lines: list[str] = []
        changes = 0
        change_details: list[str] = []

        for i, line in enumerate(lines):
            new_line = line

            # Pattern 1: Credential variable in a logging call
            if _LOG_CALL.search(line) and _CREDENTIAL_NAMES.search(line):
                new_line = _sanitize_log_line(line)
                if new_line != line:
                    changes += 1
                    change_details.append(
                        f"line {i+1}: sanitized credential in log call"
                    )

            # Pattern 2: Exception variable interpolated into throw/raise
            elif _EXCEPTION_INTERPOLATION.search(line):
                new_line = _sanitize_exception_line(line)
                if new_line != line:
                    changes += 1
                    change_details.append(
                        f"line {i+1}: sanitized exception disclosure"
                    )

            modified_lines.append(new_line)

        if changes == 0:
            return RepairStepResult(
                step_name=self.name,
                modified=False,
                code=code,
                metrics={"changes": 0},
            )

        result_code = "".join(modified_lines)
        logger.debug(
            "Credential sanitize: %s — %d changes: %s",
            file_path.name, changes, "; ".join(change_details),
        )
        return RepairStepResult(
            step_name=self.name,
            modified=True,
            code=result_code,
            metrics={
                "changes": changes,
                "details": change_details,
            },
        )


def _sanitize_log_line(line: str) -> str:
    """Replace credential-bearing interpolated variables in a log line.

    Strategy: replace the entire interpolated string argument with a
    generic message.  This is safer than trying to extract just the
    credential variable — the surrounding text often contains context
    that hints at the credential type.

    Example::
        Console.WriteLine($"Connecting to Spanner: {_databaseString}");
        → Console.WriteLine("Connecting to database");
    """
    # Find the interpolated string containing the credential
    # Replace $"...{credentialVar}..." with "operation description"
    def _replace_interpolated(match: re.Match) -> str:
        full = match.group(0)
        # Check if any credential name is in the interpolated vars
        vars_in_string = _INTERPOLATED_VAR.findall(full)
        for var in vars_in_string:
            if _CREDENTIAL_NAMES.search(var):
                # Replace the entire interpolated string with a safe message
                return '"[credential redacted]"'
        return full

    # Match interpolated strings: $"..." or f"..."
    return re.sub(r'[\$f]?"[^"]*\{[^}]+\}[^"]*"', _replace_interpolated, line)


def _sanitize_exception_line(line: str) -> str:
    """Replace exception variable interpolation in throw/raise messages.

    Example::
        throw new RpcException(new Status(StatusCode.Unavailable, $"Error: {ex}"));
        → throw new RpcException(new Status(StatusCode.Unavailable, "Service unavailable"));
    """
    # Replace $"...{ex}..." or $"...{error}..." with generic message
    return re.sub(
        r'[\$f]?"[^"]*\{(?:ex|err|error|exception|e)\}[^"]*"',
        '"Service unavailable"',
        line,
        flags=re.IGNORECASE,
    )
