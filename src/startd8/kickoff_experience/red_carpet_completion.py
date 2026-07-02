"""Red Carpet completion model (FR-WD-2) — a `$0` filled/total meter over the user-fillable surface.

Distinct from the coarse ``readiness_score`` (a ready-*stage* fraction): this counts real units the user
fills. Denominator = **user-fillable units only** (CRP R1-F1): the cascade gates
(``schema``/``app``/``pages``/``views``) ∪ the writable value-input fields
(``default_config().writable_fields()``). The always-pending ``content`` and derived ``run`` stages are
**excluded**, so a fully-filled project reads **100%**.

Weighting (CRP R1-F2): **stage-equal, then field-equal within a stage** — each stage contributes an equal
share of the overall %; within a stage its units split evenly. So one whole-schema gate is not
equal-weighted against one scalar field.

Filled semantics (CRP R1-F7): a value-input field is "filled" only if **present AND its domain is not
invalid** — a present-but-invalid value never masks a blocked build. ``defaulted`` values (provenance
``estimate``/``config-default``) are counted **distinctly** (``n_defaulted`` — "N to review"), not as done.

Pure / read-only / no-LLM. Never imports project code (NR-4a).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple

_MANIFEST_GATES: Tuple[str, ...] = ("app", "pages", "views")
_DEFAULTED_PROVENANCE = ("estimate", "config-default")


@dataclass(frozen=True)
class StageCompletion:
    stage: str
    filled: int
    total: int

    @property
    def fraction(self) -> float:
        return (self.filled / self.total) if self.total else 0.0

    def to_dict(self) -> dict:
        return {"stage": self.stage, "filled": self.filled, "total": self.total,
                "pct": round(100 * self.fraction)}


@dataclass(frozen=True)
class Completion:
    """The user-fillable completion meter — per-stage + overall %, with a distinct defaulted count."""

    stages: Tuple[StageCompletion, ...]
    overall_pct: int          # 0..100, stage-equal mean of the fillable stages
    n_defaulted: int          # present value-input fields whose provenance is a default/estimate

    def to_dict(self) -> dict:
        return {
            "overall_pct": self.overall_pct,
            "n_defaulted": self.n_defaulted,
            "stages": [s.to_dict() for s in self.stages],
        }


def _field_present(root: Path, file: str, dotted_key: str) -> bool:
    """True iff the value-input field's dotted key exists (non-null) in its on-disk YAML. Read-only;
    a parse failure → False (the domain-invalid check zeroes it out anyway)."""
    import yaml

    p = root / "docs" / "kickoff" / "inputs" / file
    if not p.is_file():
        return False
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return False
    cur: Any = data
    for part in dotted_key.split("."):
        if not isinstance(cur, Mapping) or part not in cur:
            return False
        cur = cur[part]
    return cur is not None


def build_completion(
    project_root: str | Path,
    state: Any,
    assess: Optional[Mapping[str, Any]] = None,
) -> Completion:
    """Compute the user-fillable completion meter (FR-WD-2). ``state`` supplies the cascade gates via
    ``unmet_gates``; ``assess`` supplies per-domain validity (an invalid domain → its fields unfilled)."""
    root = Path(project_root)
    unmet = set(getattr(state, "unmet_gates", ()) or ())

    # data_model — one unit: the schema gate.
    dm = StageCompletion("data_model", 0 if "schema" in unmet else 1, 1)

    # manifests — three units: app / pages / views.
    mf_filled = sum(1 for g in _MANIFEST_GATES if g not in unmet)
    mf = StageCompletion("manifests", mf_filled, len(_MANIFEST_GATES))

    # value_inputs — the writable fields; filled = present AND domain not invalid.
    from .manifest import default_config

    domains_status = ((assess or {}).get("kickoff_inputs") or {}).get("domains") or {}
    fields = [f for f in default_config().writable_fields() if f.write_target is not None]
    filled = 0
    n_defaulted = 0
    for f in fields:
        wt = f.write_target
        domain = wt.file[:-5] if wt.file.endswith(".yaml") else wt.file
        domain_invalid = (domains_status.get(domain) or {}).get("status") == "invalid"
        if not domain_invalid and _field_present(root, wt.file, wt.key):
            filled += 1
            if f.provenance_default in _DEFAULTED_PROVENANCE:
                n_defaulted += 1
    vi = StageCompletion("value_inputs", filled, len(fields))

    stages = (dm, mf, vi)
    fracs = [s.fraction for s in stages if s.total]
    overall = round(100 * (sum(fracs) / len(fracs))) if fracs else 0
    return Completion(stages=stages, overall_pct=overall, n_defaulted=n_defaulted)
