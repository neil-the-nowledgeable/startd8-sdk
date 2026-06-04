"""Convention-aware repair — Python house-style authority + detection (Phase A, advisory).

The single source of truth for the Python house style is **derived from the generators** (FR-CAR-0),
with provenance split per rule-kind (CRP R1-F1):

- ``module_source`` is derived from the **declarative** ``backend_codegen.CANONICAL_LAYOUT`` (SQLModel
  tables live in ``app.tables``; ``app.models`` holds Pydantic ``*Schema`` only) — clean to consume.
- ``framework`` / ``orm_idiom`` / ``template_idiom`` come from a **small declarative manifest**
  (``_IDIOM_RULES``) co-located here, **asserted-equal to renderer output by the parity test** rather than
  parsed out of the f-string renderers.

Phase A is **detect-only / advisory** (FR-CAR-3): :func:`detect_conventions` emits
:class:`~startd8.repair.models.ConventionDiagnostic` items; there is no fixing, no escalation, and no
verdict change here (those are Phase B). Detectors run on any tier; the authority-governed-scope guard that
gates *fixing* (FR-CAR-4, R1-F6) lands with the Phase-B fixers, not here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Pattern, Tuple

from .models import ConventionDiagnostic


@dataclass(frozen=True)
class IdiomRule:
    """One declarative house-style rule (framework / orm_idiom / template_idiom)."""

    kind: str
    regex: Pattern[str]
    symbol: str
    expected: str
    safe_fixable: bool = False


# The declarative idiom manifest (FR-CAR-0). Asserted-equal-to-generator-output by the parity test:
# `backend_codegen` emits FastAPI + SQLModel + Jinja2Templates and never Flask/SQLAlchemy-query/render_template.
_IDIOM_RULES: Tuple[IdiomRule, ...] = (
    IdiomRule(
        "framework",
        re.compile(r"^\s*(?:from\s+flask\b|import\s+flask\b)"),
        "flask",
        "FastAPI (APIRouter / Depends / HTMLResponse) — there is no Flask in a generated app",
        safe_fixable=False,  # wholesale framework swap → escalate (Phase B)
    ),
    IdiomRule(
        "framework",
        re.compile(r"@\w+\.route\s*\("),
        "@app.route",
        "@router.get/.post(...) on an APIRouter, not Flask's @app.route",
        safe_fixable=False,
    ),
    IdiomRule(
        "template_idiom",
        re.compile(r"\brender_template\s*\("),
        "render_template",
        "Jinja2Templates + TemplateResponse (the value_map.py / htmx pattern)",
        safe_fixable=False,
    ),
    IdiomRule(
        "orm_idiom",
        re.compile(r"\.query\s*\(\s*\w+\s*\)\s*\.get\s*\("),
        "session.query(...).get(...)",
        "session.get(Model, id) or session.exec(select(...)).first()",
        safe_fixable=True,  # unambiguous deterministic rewrite (Phase B)
    ),
    IdiomRule(
        "orm_idiom",
        re.compile(r"\.query\s*\("),
        "session.query(...)",
        "session.exec(select(Model)...) — SQLModel/SQLAlchemy-2.0 style",
        safe_fixable=False,
    ),
)

# `from app.models import X` — flag imports of non-Schema names (tables belong in app.tables).
_MODELS_IMPORT_RE = re.compile(r"^\s*from\s+([\w.]+)\s+import\s+(.+)$")


@dataclass(frozen=True)
class PythonConventionAuthority:
    """The generator-derived Python house-style authority consumed by the detectors."""

    tables_module: str           # canonical module for SQLModel tables (e.g. "app.tables")
    schemas_module: str          # canonical module for Pydantic *Schema (e.g. "app.models")
    idiom_rules: Tuple[IdiomRule, ...]


def _path_to_module(rel_path: str) -> str:
    """`app/tables.py` → `app.tables`."""
    return rel_path[:-3].replace("/", ".") if rel_path.endswith(".py") else rel_path.replace("/", ".")


def build_python_convention_authority() -> PythonConventionAuthority:
    """Derive the authority from the generators: module-source from the declarative ``CANONICAL_LAYOUT``."""
    from ..backend_codegen.crud_generator import CANONICAL_LAYOUT

    return PythonConventionAuthority(
        tables_module=_path_to_module(CANONICAL_LAYOUT["sqlmodel-tables"]),
        schemas_module=_path_to_module(CANONICAL_LAYOUT["pydantic-models"]),
        idiom_rules=_IDIOM_RULES,
    )


def _is_comment(line: str) -> bool:
    return line.lstrip().startswith("#")


def _split_imports(spec: str) -> List[str]:
    """Parse the imported-names portion of a ``from X import a, b`` line."""
    spec = spec.split("#", 1)[0].replace("(", "").replace(")", "").strip().rstrip(",")
    return [n.split(" as ")[0].strip() for n in spec.split(",") if n.strip()]


def detect_conventions(
    code: str, authority: Optional[PythonConventionAuthority] = None, *, file: str = ""
) -> List[ConventionDiagnostic]:
    """Detect Python house-style violations in *code* (Phase A, advisory — no fixing).

    Returns one :class:`ConventionDiagnostic` per violation, with ``convention_kind``, ``symbol``, the
    canonical ``expected`` form, the 1-based ``line``, and ``safe_fixable`` (the Phase-B fix hint).
    """
    auth = authority or build_python_convention_authority()
    out: List[ConventionDiagnostic] = []

    for i, raw in enumerate(code.splitlines(), 1):
        if _is_comment(raw):
            continue

        # framework / orm_idiom / template_idiom — declarative idiom rules
        for rule in auth.idiom_rules:
            if rule.regex.search(raw):
                out.append(
                    ConventionDiagnostic(
                        category="convention",
                        file=file,
                        message=f"{rule.symbol}: use {rule.expected}",
                        convention_kind=rule.kind,
                        symbol=rule.symbol,
                        expected=rule.expected,
                        line=i,
                        safe_fixable=rule.safe_fixable,
                    )
                )

        # module_source — a SQLModel table imported from the schemas module (app.models)
        m = _MODELS_IMPORT_RE.match(raw)
        if m and m.group(1) == auth.schemas_module:
            offenders = [
                n for n in _split_imports(m.group(2))
                if n != "*" and not n.endswith(("Schema", "Config"))
            ]
            if offenders:
                out.append(
                    ConventionDiagnostic(
                        category="convention",
                        file=file,
                        message=(
                            f"{', '.join(offenders)} imported from {auth.schemas_module}; "
                            f"SQLModel tables live in {auth.tables_module}"
                        ),
                        convention_kind="module_source",
                        symbol=f"from {auth.schemas_module} import {', '.join(offenders)}",
                        expected=f"import tables from {auth.tables_module} ({auth.schemas_module} = Pydantic *Schema only)",
                        line=i,
                        safe_fixable=True,  # deterministic module repoint (Phase B, with shadow check)
                    )
                )

    return out


def unrepaired_convention_residual(paths, authority=None) -> List[ConventionDiagnostic]:
    """Convention violations remaining in the given Python files — the residual to escalate (FR-CAR-6).

    Reads each ``.py`` path's **final** content and re-detects. Used to surface convention residue WHERE
    the repair pipeline would otherwise drop it (R1-F9: the post-generation path only runs syntax+lint, so
    a lint-clean wrong-framework file leaves no diagnostic without this).
    """
    from pathlib import Path

    auth = authority or build_python_convention_authority()
    out: List[ConventionDiagnostic] = []
    for raw in paths:
        p = Path(raw)
        if p.suffix == ".py" and p.is_file():
            try:
                out.extend(detect_conventions(p.read_text(encoding="utf-8"), auth, file=str(p)))
            except OSError:
                continue
    return out


__all__ = [
    "IdiomRule",
    "PythonConventionAuthority",
    "build_python_convention_authority",
    "detect_conventions",
    "unrepaired_convention_residual",
]
