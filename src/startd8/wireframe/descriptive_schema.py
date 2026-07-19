"""FR-SHC — Self-Hosted Content: the descriptive content's own "data model" + coverage.

Dogfoods the way `startd8` treats a wireframed app's content, on OUR content (`descriptive.yaml`):
- **M-SHC-0** declares the record-TYPE schemas — the "data model" of our content (FR-SHC-2). The planning
  spike found **two types**: a per-section record and the one aggregate ``summary`` record, with different
  required fields per role.
- **M-SHC-1** computes audience-matrix coverage reusing the FR-WCI-2 ``CoverageStat`` (Mottainai) — the
  denominator is `required fields × roles-in-use` (OQ-SHC-2); fluency variants are *reported*, never counted
  (NR-2).

Right-sized Mieruka (FR-SHC-5): the surface is a report + a CI regression guard (see
``tests/unit/wireframe/test_descriptive_coverage.py``), NOT telemetry for a 10-section matrix.
"""
from __future__ import annotations

from typing import Optional

from .describe import _records
from .plan import CoverageStat

# --- M-SHC-0: the declared record-type schemas (FR-SHC-2) — single source for "what a record must carry".
# `architect` fields live at the record's top level; other roles under `audience.<role>`.
SECTION_SCHEMA = {
    "architect": {"required": ("what", "why", "do"), "optional": ("next",)},
    "end_user":  {"required": ("title", "what", "wont", "need"), "optional": ("do", "next")},
}
SUMMARY_SCHEMA = {
    "architect": {"required": ("what", "why", "do"), "optional": ()},
    "end_user":  {"required": ("headline", "lead", "steps", "closing"), "optional": ()},
}
ROLES = ("architect", "end_user")


def schema_for(record_key: str) -> dict:
    """The declared schema for a record — the aggregate ``summary`` is its own type (spike discovery)."""
    return SUMMARY_SCHEMA if record_key == "summary" else SECTION_SCHEMA


def _role_fields(record: dict, role: str) -> dict:
    """The authored fields for a role: architect = the base (top level); others = ``audience[role]``."""
    if role == "architect":
        return record
    return (record.get("audience") or {}).get(role) or {}


def _authored(fields: dict, name: str) -> bool:
    """A field counts as authored iff it has non-empty content (list ⇒ non-empty; str ⇒ non-blank)."""
    val = fields.get(name)
    if val is None:
        return False
    if isinstance(val, (list, tuple)):
        return len(val) > 0
    return bool(str(val).strip())


def matrix_coverage(records: Optional[dict] = None) -> dict:
    """Coverage of the audience matrix over the descriptive records (M-SHC-1, FR-SHC-3/4).

    Returns ``{"by_role": {role: CoverageStat}, "overall": CoverageStat, "gaps": [str], "fluency": {…}}``.
    ``gaps`` is the authoring to-do list — the ``key.role.field`` cells the schema requires but that are
    un-authored. ``fluency`` is informational (which sections carry depth variants), never counted.
    """
    records = _records() if records is None else records
    tally = {r: [0, 0] for r in ROLES}   # role → [authored, total]
    gaps: list[str] = []
    fluency: dict[str, list[str]] = {}

    for key, rec in records.items():
        schema = schema_for(key)
        for role in ROLES:
            fields = _role_fields(rec, role)
            for name in schema[role]["required"]:
                tally[role][1] += 1
                if _authored(fields, name):
                    tally[role][0] += 1
                else:
                    gaps.append(f"{key}.{role}.{name}")
        flu = ((rec.get("audience") or {}).get("end_user") or {}).get("fluency") or {}
        if flu:
            fluency[key] = sorted(flu)

    by_role = {r: CoverageStat(a, t) for r, (a, t) in tally.items()}
    overall = CoverageStat(sum(a for a, _ in tally.values()), sum(t for _, t in tally.values()))
    return {"by_role": by_role, "overall": overall, "gaps": gaps, "fluency": fluency}


def format_report(records: Optional[dict] = None) -> str:
    """A plain-text coverage report — the FR-WCI-2 content band, self-applied (the optional readout)."""
    cov = matrix_coverage(records)
    out = ["Self-hosted content coverage (FR-SHC) — descriptive.yaml audience matrix", ""]
    for role, stat in cov["by_role"].items():
        out.append(f"  {role:<9} {stat.authored}/{stat.total}  ({round(stat.ratio * 100)}%)")
    o = cov["overall"]
    out.append(f"  {'overall':<9} {o.authored}/{o.total}  ({round(o.ratio * 100)}%)")
    out.append("")
    if cov["gaps"]:
        out.append(f"  {len(cov['gaps'])} gap(s) — content to author:")
        out += [f"    - {g}" for g in cov["gaps"]]
    else:
        out.append("  ✓ no gaps — every required cell is authored")
    if cov["fluency"]:
        depth = ", ".join(f"{k} ({'/'.join(v)})" for k, v in cov["fluency"].items())
        out += ["", f"  fluency depth (informational, sparse): {depth}"]
    return "\n".join(out)


if __name__ == "__main__":  # optional readout: `python -m startd8.wireframe.descriptive_schema`
    print(format_report())
