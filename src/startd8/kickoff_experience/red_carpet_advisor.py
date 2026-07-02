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

from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Mapping, Optional, Tuple

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
ADVISOR_COMMANDS: Tuple[str, ...] = (
    CMD_GENERATE_CONTRACT_PROMOTE, CMD_RED_CARPET_AGENT, CMD_WIREFRAME, CMD_GENERATE_BACKEND,
)

# The value-input domains diagnosed by the generic loop — EXCLUDES `stakeholders` (CRP R1-F1: it has a
# different shape/status set and is handled by a dedicated clause).
_VALUE_DOMAINS: Tuple[str, ...] = ("business-targets", "observability", "conventions", "build-preferences")

_MAX_DETAIL = 200


def _bound(text: Any, limit: int = _MAX_DETAIL) -> str:
    """Collapse whitespace/newlines and length-cap — bounded, leak-free (P4)."""
    s = " ".join(str(text or "").split())
    return s if len(s) <= limit else s[: limit - 1] + "…"


@dataclass(frozen=True)
class Advisory:
    """One derived insight / readiness diagnosis. Advisory only — never a gate (P3)."""

    kind: str
    severity: str
    title: str
    detail: str        # the *why*
    action: str        # the *what to do*
    command: Optional[str] = None  # the exact CLI invocation (relative paths only), where one exists

    def sort_key(self) -> Tuple[int, int, str, str]:
        # CRP R1-F4: byte-stable (severity, curated-kind-priority, kind, title) — no `stage` on Advisory.
        return (_SEVERITY_RANK.get(self.severity, 9), _KIND_ORDER.get(self.kind, 9), self.kind, self.title)

    def to_dict(self) -> dict:
        d = {"kind": self.kind, "severity": self.severity, "title": self.title,
             "detail": self.detail, "action": self.action}
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

def _schema_advisories(state: Any, schema_text: Optional[str]) -> List[Advisory]:
    # Emptiness (CRP R1-F5): "schema present" == the data-model gate (`_present`, size>0), surfaced as
    # the `data_model` stage being done. A zero-byte schema reads as "no schema yet", never "unparseable".
    if not _stage_done(state, "data_model") or not schema_text or not schema_text.strip():
        return [Advisory(
            KIND_SCHEMA_SHAPE, SEVERITY_INFO, "No data model yet",
            "The schema.prisma contract is the front bookend everything derives from; it is not present yet.",
            "Start with the data model: interview → requirements brief → promote the contract.",
            CMD_RED_CARPET_AGENT,
        )]
    try:
        from ..languages.prisma_parser import parse_prisma_schema
        schema = parse_prisma_schema(schema_text)
    except Exception:
        return [Advisory(
            KIND_SCHEMA_SHAPE, SEVERITY_INFO, "Schema not parseable at $0",
            "The schema is present but the $0 parser could not read it; the cascade's own gate is authoritative.",
            "Review prisma/schema.prisma if the cascade later reports a schema error.",
        )]
    models = schema.models
    n = len(models)
    if n == 0:
        return [Advisory(
            KIND_SCHEMA_SHAPE, SEVERITY_WARN, "Schema declares no models",
            "prisma/schema.prisma parsed but contains no `model` blocks.",
            "Add at least one entity, then re-promote the contract.",
            CMD_GENERATE_CONTRACT_PROMOTE,
        )]
    out: List[Advisory] = [Advisory(
        KIND_SCHEMA_SHAPE, SEVERITY_INFO, f"Data model: {n} {'entity' if n == 1 else 'entities'}",
        f"The contract declares {n} model(s) — a project-scale signal.",
        "No action needed — informational.",
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
                CMD_GENERATE_CONTRACT_PROMOTE,
            ))
    return out


# ── Per-input readiness diagnosis (FR-RCA-6) ──────────────────────────────────────────────────────

def _input_advisories(assess: Mapping[str, Any]) -> List[Advisory]:
    domains = dict(((assess.get("kickoff_inputs") or {}).get("domains")) or {})
    out: List[Advisory] = []
    for name in _VALUE_DOMAINS:
        d = domains.get(name)
        if not d:
            continue  # domain not assessed at all
        status = d.get("status")
        if status == "absent":
            out.append(Advisory(
                KIND_INPUT_GAP, SEVERITY_WARN, f"Value input missing: {name}",
                f"The '{name}' value input is not authored yet.",
                f"Author {name} — drive the Red Carpet interview to capture it.",
                CMD_RED_CARPET_AGENT,
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
    if any(k in s for k in ("page", "view", "app", "manifest", "form", "flow")):
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


# ── Ranked playbook (FR-RCA-8) ────────────────────────────────────────────────────────────────────

_GATE_LABEL = {"app": "app manifest", "pages": "at least one page", "views": "at least one view"}


def build_playbook(
    project_root: str | Path,
    state: Any,
    advisories: Tuple[Advisory, ...],
    *,
    cap: int = 7,
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
    # 2 — unmet cascade gates in canonical app → pages → views order.
    for g in ("app", "pages", "views"):
        if g in unmet:
            add("manifests", f"Add {_GATE_LABEL[g]}",
                f"The '{g}' cascade gate is unmet; author it from the schema.",
                CMD_RED_CARPET_AGENT)
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
        add("run", "Run the $0 cascade",
            "Generate the app deterministically (no LLM).", CMD_GENERATE_BACKEND)
    return tuple(steps[:cap])
