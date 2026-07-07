# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Config-driven facilitation context (FR-6/FR-7).

Resolves the panel's run context — ``desc`` / ``objective`` / ``strategy`` — from the project's own
kickoff inputs and/or a requirements doc, instead of a baked demo domain (which historically leaked
the "Blue Planet Adventures" retail demo into every un-parameterised run). Resolution order per field:

1. **Explicit override** — a value passed by the caller (CLI ``--objective`` etc.) always wins.
2. **Kickoff input** — ``docs/kickoff/inputs/business-targets.yaml``: an explicit ``objective`` /
   ``strategy`` / ``description`` field if the author wrote one, else a value *derived* from the
   structured ``goals`` (targets → objective, metrics → strategy).
3. **Requirements doc** — the overview paragraph of a requirements markdown (for ``desc``), if a path
   is given or a conventional one is found.
4. **Neutral default** — a domain-neutral placeholder that defers to the live project artifact (which
   the facilitator loads via ``_gather_artifact``). Recorded in ``missing`` so the fallback is visible.

Deterministic and ``$0`` — pure parsing, no LLM. The result reports, per field, *where the value came
from* (``sources``) and which fields fell back to the neutral default (``missing``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except Exception:  # pragma: no cover - yaml is a hard dep of the SDK; defensive only
    yaml = None  # type: ignore

# Neutral placeholders (mirror facilitation.DEFAULT_*): NO project domain — defer to the artifact.
NEUTRAL_DESC = (
    "the project described by the artifact and kickoff inputs below "
    "(no domain provided — see the grounded context)"
)
NEUTRAL_OBJECTIVE = (
    "deliver the project's stated goals as described in its requirements and kickoff inputs below"
)
NEUTRAL_STRATEGY = (
    "follow the approach implied by the project's requirements and kickoff inputs below"
)

_BUSINESS_TARGETS_REL = "docs/kickoff/inputs/business-targets.yaml"
# Conventional requirements-doc names to look for when no path is given (first match wins).
_REQUIREMENTS_GLOBS = ("REQUIREMENTS.md", "docs/*REQUIREMENTS*.md", "docs/**/*REQUIREMENTS*.md")


@dataclass(frozen=True)
class ResolvedContext:
    """The facilitation context resolved from project inputs (FR-7)."""

    desc: str
    objective: str
    strategy: str
    sources: Dict[str, str] = field(default_factory=dict)  # field -> origin label
    missing: List[str] = field(default_factory=list)  # fields that fell back to neutral

    def summary_line(self) -> str:
        """One-line human note of where context came from (for the runner banner)."""
        parts = [f"{k}={v}" for k, v in self.sources.items()]
        note = "context: " + ", ".join(parts)
        if self.missing:
            note += f"  (neutral fallback: {', '.join(self.missing)})"
        return note


def _load_yaml(path: Path) -> Optional[Dict[str, Any]]:
    if yaml is None or not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text())
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _goals(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    g = data.get("goals")
    return [row for row in g if isinstance(row, dict)] if isinstance(g, list) else []


def _objective_from_targets(data: Dict[str, Any]) -> Optional[str]:
    """Explicit ``objective`` field, else synthesize from ``goals`` targets."""
    explicit = data.get("objective")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    targets = [str(g["target"]).strip() for g in _goals(data) if str(g.get("target", "")).strip()]
    if targets:
        return "Deliver the project's business targets: " + "; ".join(targets) + "."
    return None


def _strategy_from_targets(data: Dict[str, Any]) -> Optional[str]:
    """Explicit ``strategy`` field, else synthesize from the tracked ``goals`` metrics."""
    explicit = data.get("strategy")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    metrics = [str(g["metric"]).strip() for g in _goals(data) if str(g.get("metric", "")).strip()]
    if metrics:
        return "Advance the tracked metrics: " + ", ".join(metrics) + "."
    return None


def _desc_from_business_targets(data: Dict[str, Any]) -> Optional[str]:
    for key in ("description", "summary", "desc"):
        v = data.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _find_requirements(project_root: Path, explicit: Optional[Path]) -> Optional[Path]:
    if explicit is not None:
        return explicit if explicit.is_file() else None
    for pattern in _REQUIREMENTS_GLOBS:
        matches = sorted(project_root.glob(pattern))
        if matches:
            return matches[0]
    return None


def _overview_from_requirements(path: Path) -> Optional[str]:
    """The first substantive prose paragraph of a requirements markdown (thin, per OQ-5).

    Skips the title/metadata; prefers the paragraph under a Problem Statement / Overview heading, else
    the first non-heading, non-metadata paragraph. Returns a bounded single line.
    """
    try:
        lines = path.read_text().splitlines()
    except Exception:
        return None

    def _clean(block: List[str]) -> str:
        text = " ".join(s.strip() for s in block).strip()
        text = re.sub(r"\s+", " ", text)
        return text[:400].rstrip()

    # Pass 1: paragraph under an Overview / Problem Statement heading.
    heading_re = re.compile(r"^#{1,4}\s+.*(problem statement|overview|summary)", re.I)
    for i, ln in enumerate(lines):
        if heading_re.match(ln):
            para: List[str] = []
            for nxt in lines[i + 1 :]:
                s = nxt.strip()
                if not s and para:
                    break
                if s.startswith("#"):
                    break
                if s and not s.startswith(("**", ">", "|", "-", "*", "!")):
                    para.append(s)
            if para:
                return _clean(para)
    # Pass 2: first plain prose paragraph anywhere.
    para = []
    for ln in lines:
        s = ln.strip()
        if s.startswith("#") or s.startswith(("**", ">", "|", "-", "*", "!", "---")) or not s:
            if para:
                break
            continue
        para.append(s)
    return _clean(para) if para else None


def resolve_context(
    project_root: Any,
    *,
    desc: Optional[str] = None,
    objective: Optional[str] = None,
    strategy: Optional[str] = None,
    requirements_path: Optional[Any] = None,
) -> ResolvedContext:
    """Resolve facilitation context from inputs (FR-7). Explicit args override; neutral is last resort."""
    root = Path(project_root).expanduser()
    bt = _load_yaml(root / _BUSINESS_TARGETS_REL) or {}
    sources: Dict[str, str] = {}
    missing: List[str] = []

    def _pick(field_name: str, override: Optional[str], derived: Optional[str], neutral: str) -> str:
        if isinstance(override, str) and override.strip():
            sources[field_name] = "override"
            return override.strip()
        if derived:
            sources[field_name] = "business-targets.yaml"
            return derived
        return neutral  # source/missing recorded by caller for desc's requirements path

    resolved_objective = _pick("objective", objective, _objective_from_targets(bt), NEUTRAL_OBJECTIVE)
    if "objective" not in sources:
        sources["objective"] = "default-neutral"
        missing.append("objective")

    resolved_strategy = _pick("strategy", strategy, _strategy_from_targets(bt), NEUTRAL_STRATEGY)
    if "strategy" not in sources:
        sources["strategy"] = "default-neutral"
        missing.append("strategy")

    # desc: override -> business-targets prose -> requirements overview -> neutral
    resolved_desc = NEUTRAL_DESC
    if isinstance(desc, str) and desc.strip():
        resolved_desc, sources["desc"] = desc.strip(), "override"
    else:
        bt_desc = _desc_from_business_targets(bt)
        if bt_desc:
            resolved_desc, sources["desc"] = bt_desc, "business-targets.yaml"
        else:
            req = _find_requirements(root, Path(requirements_path).expanduser() if requirements_path else None)
            overview = _overview_from_requirements(req) if req else None
            if overview:
                resolved_desc, sources["desc"] = overview, f"requirements:{req.name}"
            else:
                sources["desc"] = "default-neutral"
                missing.append("desc")

    return ResolvedContext(
        desc=resolved_desc,
        objective=resolved_objective,
        strategy=resolved_strategy,
        sources=sources,
        missing=missing,
    )
