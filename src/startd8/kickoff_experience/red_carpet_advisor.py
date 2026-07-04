"""Red Carpet Prescriptive Advisor (FR-RCA) — the deterministic ``$0`` insight + playbook layer.

Pure, read-only, **no-LLM**. Projects already-computed state (the ``build_assess`` result, the on-disk
``schema.prisma``, the RCT stage map) into two prescriptive outputs:

- **advisories** — derived insights + per-input readiness *diagnosis* (the *why* + *what to do*):
  schema-shape observations, value-input gaps/invalidity, defaulted-value reviews, cascade blockers,
  and the stakeholder roster.
- **next_steps** — a ranked, command-bearing playbook: each step names its stage and, where one exists,
  the exact CLI command that advances it.

Boundaries (inherited): never writes, **never a gate** (P3 — removing this layer does not change
``cascade_offerable``). Output is bounded/leak-free — collapsed whitespace, length-capped `detail`
strings, no absolute host paths — so it is safe to emit over telemetry, the web rail (HTML-escaped
downstream, FR-RCA-11), and MCP (read-only, FR-RCA-12).

Advisory ordering (P5 / CRP R1-F4): byte-stable key ``(severity_rank, kind, title)``. ``Advisory`` has
**no** ``stage`` field — only :class:`NextStep` does. Dedupe (OQ-C): keyed by ``(kind-family, subject)``;
a ``cascade-blocker`` beats a value-input gap on the same subject (higher leverage, matches ``ranking``
Tier 1).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

# The canonical kickoff/value-input domain set (single source of truth; kept under the local
# `_VALUE_DOMAINS` name below so this module's vocabulary is unchanged).
from ..concierge.core import KICKOFF_INPUT_DOMAINS

# ── Severity ─────────────────────────────────────────────────────────────────────────────────────
SEVERITY_INFO = "info"
SEVERITY_WARN = "warn"
SEVERITY_ERROR = "error"
_SEVERITY_RANK = {SEVERITY_ERROR: 0, SEVERITY_WARN: 1, SEVERITY_INFO: 2}

# ── Advisory kinds — a CLOSED set (CRP R1-F3: no `bucket-boundary`; no derivation emits it) ─────────
KIND_SCHEMA_SHAPE = "schema-shape"
KIND_INPUT_GAP = "input-gap"
KIND_INPUT_INVALID = "input-invalid"
KIND_CASCADE_BLOCKER = "cascade-blocker"
KIND_PROVENANCE_REVIEW = "provenance-review"
KIND_STAKEHOLDER = "stakeholder"
ADVISORY_KINDS: Tuple[str, ...] = (
    KIND_SCHEMA_SHAPE, KIND_INPUT_GAP, KIND_INPUT_INVALID,
    KIND_CASCADE_BLOCKER, KIND_PROVENANCE_REVIEW, KIND_STAKEHOLDER,
)

# Curated secondary sort priority within a severity tier (CRP R1-F4 byte-stable key). Cascade blockers
# are highest-leverage (they block the build); the schema-shape insight ranks next so the headline
# "missing FKs" observation is not crowded out of the top-N cap by lower-value gaps.
_KIND_ORDER = {
    KIND_CASCADE_BLOCKER: 0, KIND_SCHEMA_SHAPE: 1, KIND_INPUT_INVALID: 2,
    KIND_INPUT_GAP: 3, KIND_PROVENANCE_REVIEW: 4, KIND_STAKEHOLDER: 5,
}

# ── Command constants (CRP R1-S6) — one source of truth for the playbook, reflection, and the
#    command-drift validation test. No bare `startd8 …` literal should live outside this module. ─────
CMD_GENERATE_CONTRACT_PROMOTE = "startd8 generate contract --promote"
CMD_RED_CARPET_AGENT = "startd8 kickoff red-carpet --agent"
CMD_WIREFRAME = "startd8 wireframe"
CMD_GENERATE_BACKEND = "startd8 generate backend"
# FR-MS-8 — the Manifest Suggester is the guided way to fill the "which screens?" gap (pages/views),
# so the advisor points at it at the moment of need rather than the generic interview.
CMD_SCREENS_SUGGEST = "startd8 screens suggest"
ADVISOR_COMMANDS: Tuple[str, ...] = (
    CMD_GENERATE_CONTRACT_PROMOTE, CMD_RED_CARPET_AGENT, CMD_WIREFRAME, CMD_GENERATE_BACKEND,
    CMD_SCREENS_SUGGEST,
)

# The value-input domains diagnosed by the generic loop — EXCLUDES `stakeholders` (CRP R1-F1: it has a
# different shape/status set and is handled by a dedicated clause).
_VALUE_DOMAINS: Tuple[str, ...] = KICKOFF_INPUT_DOMAINS

_MAX_DETAIL = 200


def _bound(text: Any, limit: int = _MAX_DETAIL) -> str:
    """Collapse whitespace/newlines and length-cap — bounded, leak-free (P4)."""
    s = " ".join(str(text or "").split())
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _slug(text: str) -> str:
    """A stable, bounded slug for advisory codes / anchors (lowercase, hyphenated)."""
    out = "".join(c if c.isalnum() else "-" for c in str(text).strip().lower())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")[:48]


@dataclass(frozen=True)
class Advisory:
    """One derived insight / readiness diagnosis. Advisory only — never a gate (P3)."""

    kind: str
    severity: str
    title: str
    detail: str        # the *why*
    action: str        # the *what to do*
    command: Optional[str] = None  # the exact CLI invocation (relative paths only), where one exists
    code: str = ""     # FR-RCA-17 — stable id for telemetry/anchoring; auto-derived from kind+subject

    def __post_init__(self) -> None:
        # Frozen-safe derive: `kind:slug(subject-after-the-colon)` when no explicit code was given.
        if not self.code:
            subject = self.title.split(":", 1)[-1]
            object.__setattr__(self, "code", f"{self.kind}:{_slug(subject)}")

    def sort_key(self) -> Tuple[int, int, str, str]:
        # CRP R1-F4: byte-stable (severity, curated-kind-priority, kind, title) — no `stage` on Advisory.
        return (_SEVERITY_RANK.get(self.severity, 9), _KIND_ORDER.get(self.kind, 9), self.kind, self.title)

    def to_dict(self) -> dict:
        d = {"kind": self.kind, "severity": self.severity, "title": self.title,
             "detail": self.detail, "action": self.action, "code": self.code}
        if self.command is not None:
            d["command"] = self.command
        return d


@dataclass(frozen=True)
class NextStep:
    """One ranked, command-bearing playbook step."""

    rank: int
    stage: str
    title: str
    detail: str
    command: Optional[str] = None

    def to_dict(self) -> dict:
        d = {"rank": self.rank, "stage": self.stage, "title": self.title, "detail": self.detail}
        if self.command is not None:
            d["command"] = self.command
        return d


def _stage_done(state: Any, key: str) -> bool:
    return any(getattr(s, "key", None) == key and getattr(s, "status", None) == "done"
               for s in getattr(state, "stages", ()))


# ── Schema-shape insights (FR-RCA-5) ───────────────────────────────────────────────────────────────

_FK_SUFFIX_RE = re.compile(r"^(?P<stem>.+?)(?:Id|_id|_fk)$")


def _model_has_pk(model: Any) -> bool:
    return (any(f.is_id for f in model.fields)
            or any(str(a).startswith("@@id") for a in model.block_attributes))


def _likely_fk_advisories(schema: Any) -> List[Advisory]:
    """A scalar `<name>Id` whose `<name>` names a model, with no relation to it → probable missing FK."""
    model_by_lower = {name.lower(): name for name in schema.models}
    out: List[Advisory] = []
    for mname, m in schema.models.items():
        rel_types = {f.type for f in m.fields if schema.is_relation_field(f)}
        for f in m.fields:
            if f.is_id or schema.is_relation_field(f):
                continue
            match = _FK_SUFFIX_RE.match(f.name)
            if not match:
                continue
            target = model_by_lower.get(match.group("stem").lower())
            if target and target not in rel_types:
                out.append(Advisory(
                    KIND_SCHEMA_SHAPE, SEVERITY_WARN, f"Possible missing relation: {mname}.{f.name}",
                    _bound(f"`{mname}.{f.name}` looks like a foreign key to `{target}` but no @relation links them."),
                    f"Add a `{target}` relation field with @relation, then re-promote the contract.",
                    CMD_GENERATE_CONTRACT_PROMOTE, code=f"schema-shape:likely-fk:{_slug(mname + '-' + f.name)}",
                ))
    return out


def _schema_advisories(state: Any, schema_text: Optional[str]) -> List[Advisory]:
    # Emptiness (CRP R1-F5): "schema present" == the data-model gate (`_present`, size>0), surfaced as
    # the `data_model` stage being done. A zero-byte schema reads as "no schema yet", never "unparseable".
    if not _stage_done(state, "data_model") or not schema_text or not schema_text.strip():
        return [Advisory(
            KIND_SCHEMA_SHAPE, SEVERITY_INFO, "No data model yet",
            "The schema.prisma contract is the front bookend everything derives from; it is not present yet.",
            "Start with the data model: interview → requirements brief → promote the contract.",
            CMD_RED_CARPET_AGENT, code="schema-shape:none",
        )]
    try:
        from ..languages.prisma_parser import parse_prisma_schema
        schema = parse_prisma_schema(schema_text)
    except Exception:
        return [Advisory(
            KIND_SCHEMA_SHAPE, SEVERITY_INFO, "Schema not parseable at $0",
            "The schema is present but the $0 parser could not read it; the cascade's own gate is authoritative.",
            "Review prisma/schema.prisma if the cascade later reports a schema error.",
            code="schema-shape:unparseable",
        )]
    models = schema.models
    n = len(models)
    if n == 0:
        return [Advisory(
            KIND_SCHEMA_SHAPE, SEVERITY_WARN, "Schema declares no models",
            "prisma/schema.prisma parsed but contains no `model` blocks.",
            "Add at least one entity, then re-promote the contract.",
            CMD_GENERATE_CONTRACT_PROMOTE, code="schema-shape:no-models",
        )]
    out: List[Advisory] = [Advisory(
        KIND_SCHEMA_SHAPE, SEVERITY_INFO, f"Data model: {n} {'entity' if n == 1 else 'entities'}",
        f"The contract declares {n} model(s) — a project-scale signal.",
        "No action needed — informational.", code="schema-shape:count",
    )]
    # Relation islands (OQ-D false-positive guard): only when >1 model AND ≥1 has zero relation fields.
    if n > 1:
        islands = sorted(
            name for name, m in models.items()
            if not any(schema.is_relation_field(f) for f in m.fields)
        )
        if islands:
            shown = ", ".join(islands[:8]) + ("…" if len(islands) > 8 else "")
            out.append(Advisory(
                KIND_SCHEMA_SHAPE, SEVERITY_WARN, f"{len(islands)} of {n} models are unlinked",
                _bound(f"Models with no relation fields: {shown}. Likely missing foreign keys / relations."),
                "Add relations (e.g. a foreign-key field + @relation) then re-promote the contract.",
                CMD_GENERATE_CONTRACT_PROMOTE, code="schema-shape:islands",
            ))
    # FR-RCA-14 — expanded diagnostics (all reuse the parsed schema; info/warn only, never a gate).
    # No primary key (per model).
    for mname, m in models.items():
        if not _model_has_pk(m):
            out.append(Advisory(
                KIND_SCHEMA_SHAPE, SEVERITY_WARN, f"Model has no primary key: {mname}",
                f"`{mname}` declares neither an @id field nor an @@id block key.",
                "Add an @id (or @@id) so the cascade can generate CRUD + findUnique.",
                CMD_GENERATE_CONTRACT_PROMOTE, code=f"schema-shape:no-pk:{_slug(mname)}",
            ))
    # Likely foreign key with no relation.
    out.extend(_likely_fk_advisories(schema))
    # Empty enum.
    for ename, variants in (schema.enums or {}).items():
        if not variants:
            out.append(Advisory(
                KIND_SCHEMA_SHAPE, SEVERITY_WARN, f"Empty enum: {ename}",
                f"enum `{ename}` declares no variants.",
                "Add variants or remove the enum, then re-promote the contract.",
                CMD_GENERATE_CONTRACT_PROMOTE, code=f"schema-shape:empty-enum:{_slug(ename)}",
            ))
    return out


# ── Per-input readiness diagnosis (FR-RCA-6) ──────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _domain_fields() -> Dict[str, Tuple[str, ...]]:
    """FR-RCA-18 — the writable value-input field keys per domain, from the seeded kickoff config.

    Grouped by the file stem of each field's ``value_path`` (``<domain>.yaml#/<key>``). Degrades to
    ``{}`` if the config is unavailable so remediation falls back to the domain-level message.
    """
    try:
        from .manifest import default_config

        grouped: Dict[str, List[str]] = {}
        for f in default_config().writable_fields():
            vp = str(getattr(f, "value_path", "") or "")
            file = vp.split("#", 1)[0]
            domain = file[:-5] if file.endswith(".yaml") else file
            grouped.setdefault(domain, []).append(str(getattr(f, "key", "") or getattr(f, "label", "")))
        return {k: tuple(v) for k, v in grouped.items()}
    except Exception:
        return {}


def _input_advisories(assess: Mapping[str, Any]) -> List[Advisory]:
    domains = dict(((assess.get("kickoff_inputs") or {}).get("domains")) or {})
    domain_fields = _domain_fields()
    out: List[Advisory] = []
    for name in _VALUE_DOMAINS:
        d = domains.get(name)
        if not d:
            continue  # domain not assessed at all
        status = d.get("status")
        if status == "absent":
            # FR-RCA-18 — name the specific fields to fill, not just "author it".
            fields = domain_fields.get(name) or ()
            if fields:
                shown = ", ".join(fields[:4]) + (f" +{len(fields) - 4} more" if len(fields) > 4 else "")
                detail = _bound(f"The '{name}' value input is not authored yet. Fields to fill: {shown}.")
                action = _bound(f"Author {name} — fill: {shown}.")
            else:
                detail = f"The '{name}' value input is not authored yet."
                action = f"Author {name} — drive the Red Carpet interview to capture it."
            out.append(Advisory(
                KIND_INPUT_GAP, SEVERITY_WARN, f"Value input missing: {name}",
                detail, action, CMD_RED_CARPET_AGENT,
            ))
        elif status == "invalid":
            out.append(Advisory(
                KIND_INPUT_INVALID, SEVERITY_ERROR, f"Value input invalid: {name}",
                _bound(f"'{name}' failed to parse: {d.get('error', '')}"),
                f"Fix docs/kickoff/inputs/{name}.yaml (see the parse error).",
            ))
        elif status == "present":
            prov = d.get("provenance_default")
            if prov in ("estimate", "config-default"):
                out.append(Advisory(
                    KIND_PROVENANCE_REVIEW, SEVERITY_INFO, f"Defaulted value: {name}",
                    f"'{name}' is present but its provenance is '{prov}' (a default/estimate, not confirmed).",
                    "Confirm or change the value so it reflects a real decision.",
                ))
    # Stakeholders carve-out (CRP R1-F1): different shape (authored/consumable/note) + wider status set.
    st = domains.get("stakeholders")
    if st:
        out.extend(_stakeholder_advisories(st))
    return out


def _stakeholder_advisories(st: Mapping[str, Any]) -> List[Advisory]:
    """Stakeholders NEVER map to an `input-invalid` error (CRP R1-F1) — always a `stakeholder` advisory."""
    status = st.get("status")
    if status == "present":
        if st.get("authored") and not st.get("consumable"):
            return [Advisory(
                KIND_STAKEHOLDER, SEVERITY_INFO, "Stakeholder roster authored",
                _bound(st.get("note") or "Roster authored; the live Stakeholder Panel ships in a later increment."),
                "No action needed — the live panel consumes it in a later increment.",
            )]
        return []  # authored + consumable → nothing to advise
    if status == "invalid":
        return [Advisory(
            KIND_STAKEHOLDER, SEVERITY_WARN, "Stakeholder roster invalid",
            _bound(f"stakeholders.yaml did not validate: {st.get('error', '')}"),
            "Fix docs/kickoff/inputs/stakeholders.yaml if you intend to use the panel (optional).",
        )]
    if status == "unavailable":
        return [Advisory(
            KIND_STAKEHOLDER, SEVERITY_INFO, "Stakeholder panel unavailable",
            _bound(st.get("error") or "the stakeholder_panel package is not importable"),
            "Optional — no action needed for the $0 cascade.",
        )]
    return []  # absent → stakeholders are optional; no advisory


# ── Cascade-blocker translation (FR-RCA-7) ────────────────────────────────────────────────────────

def _blocker_command(section: str) -> Optional[str]:
    s = section.lower()
    if any(k in s for k in ("schema", "data model", "contract")):
        return CMD_GENERATE_CONTRACT_PROMOTE
    # FR-MS-8 — the "screens" gap (pages/views) routes to the Manifest Suggester, the guided way to
    # decide *which* screens the product needs. Broader app/manifest/form/flow gaps stay the interview.
    if any(k in s for k in ("page", "view", "screen")):
        return CMD_SCREENS_SUGGEST
    if any(k in s for k in ("app", "manifest", "form", "flow")):
        return CMD_RED_CARPET_AGENT
    return None


def _cascade_advisories(assess: Mapping[str, Any]) -> List[Advisory]:
    cascade = dict(assess.get("cascade") or {})
    # Degraded state (CRP R1-S2): inputs_error has NO `blockers` key — still emit one bounded advisory.
    if cascade.get("status") == "inputs_error":
        return [Advisory(
            KIND_CASCADE_BLOCKER, SEVERITY_ERROR, "Assembly inputs did not resolve",
            _bound(f"The cascade inputs failed to load: {cascade.get('error', '')}"),
            "Fix the assembly inputs (docs/ASSEMBLY_INPUTS.yaml or the convention manifests) so readiness can be computed.",
        )]
    out: List[Advisory] = []
    for b in cascade.get("blockers", []):  # `.get` — key absent on non-ok states
        section = (str(b.get("section", "")).strip() or "unknown")
        out.append(Advisory(
            KIND_CASCADE_BLOCKER, SEVERITY_WARN, f"Cascade blocker: {section}",
            _bound(b.get("consequence") or b.get("status") or ""),
            "Resolve this section so the cascade can assemble the app.",
            _blocker_command(section),
        ))
    return out


def _subject(a: Advisory) -> str:
    """The dedupe subject — the text after the first ':' in the title, lowercased."""
    return a.title.split(":", 1)[-1].strip().lower()


def _dedupe(advs: List[Advisory]) -> List[Advisory]:
    """Dedupe advisories:

    - OQ-C: a cascade-blocker beats a value-input gap on the same subject.
    - Cascade-blockers that share the **same consequence** (e.g. the "no contract → …" family that a
      missing schema fans out across every downstream section) collapse to the first — they are one root
      cause surfaced under different section names; showing all of them is noise, not signal.
    - Exact ``(kind, title)`` duplicates are dropped.
    """
    cascade_subjects = {_subject(a) for a in advs if a.kind == KIND_CASCADE_BLOCKER}
    seen: set = set()
    seen_cascade_detail: set = set()
    out: List[Advisory] = []
    for a in advs:
        if a.kind == KIND_INPUT_GAP and _subject(a) in cascade_subjects:
            continue  # higher-leverage cascade blocker already covers this subject
        if a.kind == KIND_CASCADE_BLOCKER:
            if a.detail in seen_cascade_detail:
                continue  # same root-cause consequence already shown
            seen_cascade_detail.add(a.detail)
        key = (a.kind, a.title)
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out


def derive_advisories(
    project_root: str | Path,
    state: Any,
    assess: Mapping[str, Any],
    schema_text: Optional[str],
) -> Tuple[Advisory, ...]:
    """Pure ``$0`` insight derivation. ``project_root`` is accepted for symmetry/future use."""
    advs: List[Advisory] = []
    advs.extend(_schema_advisories(state, schema_text))
    advs.extend(_input_advisories(assess or {}))
    advs.extend(_cascade_advisories(assess or {}))
    advs = _dedupe(advs)
    advs.sort(key=lambda a: a.sort_key())
    return tuple(advs)


def cap_advisories(advisories: Tuple[Advisory, ...], cap: int) -> Tuple[Advisory, ...]:
    """Cap to top-N (OQ-E) but **reserve one slot for the headline schema insight** (FR-RCA-19).

    Input must be pre-sorted. If the cap would drop every `schema-shape` advisory (e.g. a greenfield
    wall of cascade-blockers), swap the top schema-shape advisory into the last kept slot so the
    front-bookend insight is never buried. Deterministic / byte-stable.
    """
    advs = list(advisories)
    if len(advs) <= cap or cap <= 0:
        return tuple(advs[:cap] if cap >= 0 else advs)
    kept = advs[:cap]
    if not any(a.kind == KIND_SCHEMA_SHAPE for a in kept):
        top_schema = next((a for a in advs if a.kind == KIND_SCHEMA_SHAPE), None)
        if top_schema is not None:
            kept = kept[: cap - 1] + [top_schema]
    return tuple(kept)


# ── Ranked playbook (FR-RCA-8) ────────────────────────────────────────────────────────────────────

_GATE_LABEL = {"app": "app manifest", "pages": "at least one page", "views": "at least one view"}


def build_playbook(
    project_root: str | Path,
    state: Any,
    advisories: Tuple[Advisory, ...],
    *,
    cap: int = 7,
    preview: Optional[Mapping[str, Any]] = None,
) -> Tuple[NextStep, ...]:
    """Assemble the ranked, command-bearing playbook in canonical dependency order (FR-RCA-8)."""
    steps: List[NextStep] = []
    unmet = set(getattr(state, "unmet_gates", ()) or ())

    def add(stage: str, title: str, detail: str, command: Optional[str] = None) -> None:
        steps.append(NextStep(len(steps) + 1, stage, title, _bound(detail), command))

    # 1 — the data-model gate (front bookend).
    if "schema" in unmet:
        add("data_model", "Author the data-model contract",
            "Interview → requirements brief → promote prisma/schema.prisma (the front bookend).",
            CMD_RED_CARPET_AGENT)
    # 2 — unmet cascade gates in canonical app → pages → views order. The screens gaps (pages/views)
    #     point at the Manifest Suggester (FR-MS-8); the app manifest stays the interview.
    for g in ("app", "pages", "views"):
        if g in unmet:
            cmd = CMD_SCREENS_SUGGEST if g in ("pages", "views") else CMD_RED_CARPET_AGENT
            add("manifests", f"Add {_GATE_LABEL[g]}",
                f"The '{g}' cascade gate is unmet; author it from the schema.",
                cmd)
    # 3 — value-input gaps / invalidity.
    for a in advisories:
        if a.kind in (KIND_INPUT_GAP, KIND_INPUT_INVALID):
            add("value_inputs", a.title, a.detail, a.command)
    # 4 — defaulted values to review.
    for a in advisories:
        if a.kind == KIND_PROVENANCE_REVIEW:
            add("value_inputs", a.title, a.detail, a.command)
    # 5 — offerable ⇒ wireframe checkpoint, then the $0 cascade.
    if getattr(state, "cascade_offerable", False):
        add("run", "Review the wireframe",
            "Preview what the $0 cascade will build before running it.", CMD_WIREFRAME)
        # FR-RCA-20 — weave the (already-fetched) wireframe preview into the run step for a concrete go/no-go.
        run_detail = "Generate the app deterministically (no LLM)."
        if preview:
            shape = preview.get("shape")
            counts = preview.get("counts")
            if shape:
                run_detail += f" Planned shape: {shape}."
            if counts:
                run_detail += f" Sections: {counts}."
        add("run", "Run the $0 cascade", run_detail, CMD_GENERATE_BACKEND)
    return tuple(steps[:cap])
