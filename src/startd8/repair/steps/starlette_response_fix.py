"""Starlette ``TemplateResponse`` safe-fix step.

Deterministically repairs the recurring LLM-authored Starlette mistakes the strtd8 pilot
observed on three consecutive construction runs (008/009/010) — the model reproduces them
even against an explicit contract rule, so the lesson belongs in machinery:

1. **Phantom import** — ``from starlette.responses import TemplateResponse`` does not exist
   (it lives on a ``Jinja2Templates`` instance / ``starlette.templating``). The name is
   removed from the import (the line is dropped when it becomes empty). Always wrong, so
   always safe.
2. **Bare call repoint** — bare ``TemplateResponse(...)`` → ``templates.TemplateResponse(...)``
   — only when the module already binds a ``templates`` instance (e.g. ``from .web import
   templates``), so the rewrite never invents a name.
3. **Request-first reorder** — ``templates.TemplateResponse('name.html', {...})`` →
   ``templates.TemplateResponse(request, 'name.html', {...})`` — only when the first argument
   is a (f-)string literal AND ``request`` appears among the remaining arguments (proof the
   name is in scope). The deprecated name-first form crashes the jinja cache on current
   Starlette (unhashable key); the same lesson was fixed in the SDK's own emitters
   (dd15e7ca, 52f2601e) — this step extends it to LLM-authored files.

Anything not matching these exact shapes is left for escalation, never guessed at.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from ..models import ElementContext, RepairContext, RepairStepResult

# `from starlette.responses import A, TemplateResponse, B` (the phantom import)
_PHANTOM_IMPORT_RE = re.compile(
    r"^(\s*)from\s+starlette\.responses\s+import\s+(.+?)\s*$", re.MULTILINE
)

# A `templates` binding in scope (import or assignment) — gate for the bare-call repoint.
_TEMPLATES_BINDING_RE = re.compile(
    r"(^\s*from\s+[\w.]+\s+import\s+.*\btemplates\b)|(^\s*templates\s*=)", re.MULTILINE
)

# Bare `TemplateResponse(` not preceded by a dot (so `templates.TemplateResponse` is untouched).
_BARE_CALL_RE = re.compile(r"(?<![\w.])TemplateResponse\(")

# `templates.TemplateResponse(<str-or-fstr literal>` — candidate for request-first insertion.
_NAME_FIRST_RE = re.compile(r"(\btemplates\.TemplateResponse\(\s*)(f?['\"])")


class StarletteResponseFixStep:
    """Deterministic fixer for phantom/name-first Starlette TemplateResponse usage."""

    name: str = "starlette_response_fix"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        if not str(file_path).endswith(".py"):
            return RepairStepResult(step_name=self.name, modified=False, code=code)

        fixed = code
        fixes = 0
        rules: List[str] = []

        # (1) Phantom import: strip TemplateResponse from starlette.responses imports.
        def _strip_phantom(m: re.Match) -> str:
            indent, names = m.group(1), m.group(2)
            kept = [n.strip() for n in names.split(",") if n.strip() and
                    n.strip().split(" as ")[0].strip() != "TemplateResponse"]
            if len(kept) == len([n for n in names.split(",") if n.strip()]):
                return m.group(0)  # TemplateResponse wasn't among them
            nonlocal fixes
            fixes += 1
            if not kept:
                return f"{indent}# repaired: phantom TemplateResponse import removed (starlette_response_fix)"
            return f"{indent}from starlette.responses import {', '.join(kept)}"

        new = _PHANTOM_IMPORT_RE.sub(_strip_phantom, fixed)
        if new != fixed:
            fixed = new
            rules.append("phantom_import_strip")

        # (2) Bare-call repoint — only when a `templates` binding exists in the module.
        if _BARE_CALL_RE.search(fixed) and _TEMPLATES_BINDING_RE.search(fixed):
            fixed, n = _BARE_CALL_RE.subn("templates.TemplateResponse(", fixed)
            if n:
                fixes += n
                rules.append("bare_call_repoint")

        # (3) Request-first: insert `request, ` when first arg is a string literal and
        # `request` provably appears later in the same call line (name is in scope).
        out_lines = []
        reordered = 0
        for line in fixed.splitlines(keepends=True):
            m = _NAME_FIRST_RE.search(line)
            if m and re.search(r"[,(]\s*\{?['\"]?request\b", line[m.end():]):
                line = line[: m.end(1)] + "request, " + line[m.end(1):]
                reordered += 1
            out_lines.append(line)
        if reordered:
            fixed = "".join(out_lines)
            fixes += reordered
            rules.append("request_first_reorder")

        if not fixes:
            return RepairStepResult(step_name=self.name, modified=False, code=code)
        return RepairStepResult(
            step_name=self.name,
            modified=True,
            code=fixed,
            metrics={"fixes": fixes, "rules": rules},
        )
