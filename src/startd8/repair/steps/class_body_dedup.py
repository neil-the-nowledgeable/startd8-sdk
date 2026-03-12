"""Class body deduplication repair step (REQ-RPL-105).

Strips bare method-body statements (return, try/except with return) that
Ollama sometimes generates at class body level without an enclosing ``def``.

Example of the pattern this fixes::

    class JsonFormatter(logging.Formatter):
        import json
        log_entry = { ... }
        try:
            return json.dumps(log_entry)   # ← SyntaxError: return outside function
        except (TypeError, ValueError):
            return json.dumps(...)         # ← SyntaxError
        def format(self, record) -> str:   # ← actual method (kept)
            log_entry = { ... }
            try:
                return json.dumps(log_entry)
            except ...:
                return json.dumps(...)

After repair the bare block (lines with ``return`` at class level) is removed,
leaving only the proper method definition.

This step runs before AST-dependent steps (``duplicate_removal``,
``ast_validate``) because the SyntaxError prevents ``ast.parse()``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ...logging_config import get_logger
from ..models import ElementContext, RepairContext, RepairStepResult

logger = get_logger(__name__)

_CLASS_RE = re.compile(r"^(\s*)class\s+\w+")
_DEF_RE = re.compile(r"^\s*(?:async\s+)?def\s+")
_RETURN_RE = re.compile(r"^\s*return(?:\s|$)")


class ClassBodyDeduplicationStep:
    """Remove bare method-body blocks from class bodies."""

    name: str = "class_body_dedup"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        fixed, count = _strip_bare_return_blocks(code)
        return RepairStepResult(
            step_name=self.name,
            modified=count > 0,
            code=fixed,
            metrics={"bare_blocks_removed": count},
        )


def _strip_bare_return_blocks(code: str) -> tuple[str, int]:
    """Remove class-body zones that contain bare ``return`` statements.

    Scans each class body and divides it into *zones* separated by
    method definitions (``def`` at body indent).  If a zone contains a
    ``return`` statement (at any depth within the zone), the entire zone
    is removed — it's a duplicated method body that Ollama emitted at
    class level without the enclosing ``def``.

    Zones that don't contain ``return`` (class variables, decorators,
    nested classes) are left untouched.

    Returns ``(fixed_code, blocks_removed)``.
    """
    lines = code.splitlines(keepends=True)
    n = len(lines)
    removals: set[int] = set()
    blocks_removed = 0

    i = 0
    while i < n:
        m = _CLASS_RE.match(lines[i].rstrip())
        if not m:
            i += 1
            continue

        class_indent = len(m.group(1))

        # Detect body indent from next non-blank, non-comment line.
        body_indent = class_indent + 4
        for k in range(i + 1, min(i + 10, n)):
            ks = lines[k].rstrip()
            if ks and not ks.lstrip().startswith("#"):
                body_indent = len(ks) - len(ks.lstrip())
                break

        # Walk the class body, collecting non-method "zones".
        j = i + 1
        zone: list[int] = []
        zone_has_return = False

        while j < n:
            s = lines[j].rstrip()

            # Blank line — part of current zone.
            if not s:
                zone.append(j)
                j += 1
                continue

            indent = len(s) - len(s.lstrip())

            # End of class body (back to class indent or above).
            if indent <= class_indent:
                break

            content = s.strip()

            # Method definition at body indent → flush previous zone.
            if indent == body_indent and _DEF_RE.match(s):
                if zone_has_return and zone:
                    removals.update(zone)
                    blocks_removed += 1
                zone = []
                zone_has_return = False
                # Skip past the method body.
                j += 1
                while j < n:
                    ms = lines[j].rstrip()
                    if not ms:
                        j += 1
                        continue
                    mi = len(ms) - len(ms.lstrip())
                    if mi <= body_indent:
                        break
                    j += 1
                continue

            # Non-method line in class body.
            zone.append(j)
            if _RETURN_RE.match(content):
                zone_has_return = True

            j += 1

        # Flush trailing zone.
        if zone_has_return and zone:
            removals.update(zone)
            blocks_removed += 1

        i = j if j > i else i + 1

    if not removals:
        return code, 0

    new_lines = [line for idx, line in enumerate(lines) if idx not in removals]
    result = "".join(new_lines)
    # Collapse runs of 3+ blank lines.
    result = re.sub(r"\n{3,}", "\n\n", result)

    if blocks_removed:
        logger.debug(
            "Removed %d bare method-body block(s) from class bodies", blocks_removed,
        )

    return result, blocks_removed
