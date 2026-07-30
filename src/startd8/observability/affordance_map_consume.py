"""AffordanceMap consume — load, plan, apply, merge, sidecar (REQ Affordance-Map Generator Consume).

Shipped WP-B0–B3: deterministic planner, targeted live ``gen.*`` repairs (RED / triplet /
shrink / enrich_runbook retrofit), FR-B5-aligned runbooks (elsewhere), FR-B7
``affordance_actions.json`` sidecar. Does **not** import contextcore (NR-G1 / AC-G7).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
)

import yaml

from startd8.logging_config import get_logger

logger = get_logger(__name__)

# ---- Exit codes (FR-B1) ------------------------------------------------------

EXIT_OK = 0
EXIT_MALFORMED = 2
EXIT_ALL_SKIPPED = 3

# ---- Known gen set (FR-AFF-1 snapshot; NR-G5 no rename) -----------------------

GEN_EMIT_RED = "gen.emit_red_panels"
GEN_COMPLETE_TRIPLET = "gen.complete_triplet"
GEN_IMPROVE_COVERAGE = "gen.improve_metric_coverage"
GEN_ENRICH_RUNBOOK = "gen.enrich_runbook"
GEN_SHRINK = "gen.shrink_dashboard_lines"

KNOWN_GEN_AFFORDANCES: frozenset = frozenset(
    {
        GEN_EMIT_RED,
        GEN_COMPLETE_TRIPLET,
        GEN_IMPROVE_COVERAGE,
        GEN_ENRICH_RUNBOOK,
        GEN_SHRINK,
    }
)

# Live = real repair branch; advisory skip honestly (R2-F1).
# gen.enrich_runbook is LIVE: FR-B5 fixed *new* emit; map-mode retrofits
# pre-FR-B5 trees (Service summary / First response → Overview / Procedures + Risks).
ADVISORY_GEN: frozenset = frozenset({GEN_IMPROVE_COVERAGE})
UNREACHABLE_GEN: frozenset = frozenset()  # kept for API; empty after enrich LIVE
LIVE_GEN: frozenset = frozenset(KNOWN_GEN_AFFORDANCES - ADVISORY_GEN - UNREACHABLE_GEN)

AFFORDANCE_PRIORITY: Tuple[str, ...] = (
    GEN_EMIT_RED,
    GEN_COMPLETE_TRIPLET,
    GEN_IMPROVE_COVERAGE,
    GEN_ENRICH_RUNBOOK,
    GEN_SHRINK,
)

_PRIORITY_INDEX = {a: i for i, a in enumerate(AFFORDANCE_PRIORITY)}

_ENV_FORM = re.compile(r"^[A-Z][A-Z0-9_]*(?:_SERVICE)?$")

_ARTIFACT_TYPES: Dict[str, List[str]] = {
    GEN_EMIT_RED: ["dashboard_spec", "dashboard"],
    GEN_COMPLETE_TRIPLET: ["alert_rule", "dashboard_spec", "slo_definition"],
    GEN_IMPROVE_COVERAGE: ["dashboard_spec"],
    GEN_ENRICH_RUNBOOK: ["runbook"],
    GEN_SHRINK: ["dashboard_spec", "dashboard"],
}


class ActionOutcome(str, Enum):
    PLANNED = "planned"
    APPLIED = "applied"
    APPLIED_NO_CHANGE = "applied_no_change"
    SKIPPED = "skipped"



def signal_kind_for(family_or_signal: str) -> str:
    """Classify locus signal (metric | transport | component)."""
    s = family_or_signal or ""
    if s.startswith("transport:"):
        return "transport"
    if s.startswith("component:"):
        return "component"
    return "metric"

def _coerce_confidence(raw: Any) -> Optional[float]:
    """Soft-coerce map confidence; bad values → None (do not fail the whole load)."""
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        logger.warning("ignoring non-numeric AffordanceMap confidence=%r", raw)
        return None

@dataclass
class AffordanceMapEntry:
    """One row from CC affordance_map (plain JSON; Keiyaku boundary)."""

    element_id: str
    gap_code: str = ""
    affordance_ids: List[str] = field(default_factory=list)
    confidence: Optional[float] = None
    provenance: Optional[str] = None
    unmapped_reason: Optional[str] = None
    locus_status: Optional[str] = None
    source_loci: List[Dict[str, Any]] = field(default_factory=list)
    locus_reason: Optional[str] = None

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "AffordanceMapEntry":
        ids = raw.get("affordance_ids") or []
        if not isinstance(ids, list):
            ids = []
        loci_raw = raw.get("source_loci") or []
        loci: List[Dict[str, Any]] = []
        if isinstance(loci_raw, list):
            for loc in loci_raw:
                if isinstance(loc, Mapping):
                    row = dict(loc)
                    fos = str(row.get("family_or_signal") or "")
                    row["signal_kind"] = row.get("signal_kind") or signal_kind_for(fos)
                    loci.append(row)
        return cls(
            element_id=str(raw.get("element_id") or ""),
            gap_code=str(raw.get("gap_code") or ""),
            affordance_ids=[str(x) for x in ids],
            confidence=_coerce_confidence(raw.get("confidence")),
            provenance=str(raw["provenance"]) if raw.get("provenance") is not None else None,
            unmapped_reason=(
                str(raw["unmapped_reason"])
                if raw.get("unmapped_reason") is not None
                else None
            ),
            locus_status=(
                str(raw["locus_status"]) if raw.get("locus_status") is not None else None
            ),
            source_loci=loci,
            locus_reason=(
                str(raw["locus_reason"]) if raw.get("locus_reason") is not None else None
            ),
        )


@dataclass
class ActionPlanEntry:
    """Typed plan/apply row (FR-B2b)."""

    service_id: str
    affordance_id: str
    artifact_types: List[str]
    reason: str
    gap_code: str = ""
    confidence: Optional[float] = None
    legs: Optional[List[str]] = None
    outcome: ActionOutcome = ActionOutcome.PLANNED
    unmapped_reason: Optional[str] = None
    content_hash_before: Optional[str] = None
    content_hash_after: Optional[str] = None
    rendered_hash_before: Optional[str] = None
    rendered_hash_after: Optional[str] = None
    loci_used: Optional[List[Dict[str, Any]]] = None
    locus_skip_reason: Optional[str] = None
    locus_status: Optional[str] = None
    # True/False once a shrink attempt has checked for an on-disk rendered
    # artifact; None (default) means "not applicable" — distinguishes a
    # substantive refusal from render_unavailable (plan Step 3).
    render_available: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["outcome"] = self.outcome.value
        return d


@dataclass
class LoadResult:
    """Result of loading an AffordanceMap file or dict."""

    entries: List[AffordanceMapEntry]
    source_truncated: bool = False
    source_shape: str = "array"  # array | scorecard
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class PlanResult:
    """Planner output + skip accounting for exit codes."""

    actions: List[ActionPlanEntry]
    skips: List[ActionPlanEntry] = field(default_factory=list)

    @property
    def all_entries(self) -> List[ActionPlanEntry]:
        return list(self.actions) + list(self.skips)

    @property
    def has_live_planned(self) -> bool:
        return any(
            e.affordance_id in LIVE_GEN and e.outcome == ActionOutcome.PLANNED
            for e in self.actions
        )

    @property
    def all_skipped(self) -> bool:
        return bool(self.all_entries) and not self.actions


# ---- Normalize + match ladder (FR-B6a) ---------------------------------------


def normalize_element_id(raw: str) -> str:
    """Local mirror of ContextCore ``catalog_service_id`` / ``normalize_service``.

    ENV_FORM: strip trailing ``_SERVICE``, delete underscores, lowercase, append
    ``service`` when the slug does not already end with it.
    Otherwise: lowercase.
    """
    s = (raw or "").strip()
    if not s:
        return ""
    if _ENV_FORM.fullmatch(s):
        base = re.sub(r"_SERVICE$", "", s)
        slug = base.replace("_", "").lower()
        return slug if slug.endswith("service") else slug + "service"
    return s.lower()


def _service_equivalent(a: str, b: str) -> bool:
    """(?:service)?$ -insensitive equivalence after lowercasing."""
    a_l, b_l = a.lower(), b.lower()
    if a_l == b_l:
        return True

    def stem(x: str) -> str:
        return x[:-7] if x.endswith("service") else x

    return stem(a_l) == stem(b_l)


def match_service_id(
    element_id: str,
    known_service_ids: Sequence[str],
) -> Optional[str]:
    """Match ladder: exact → normalized → (?:service)?$ equivalence.

    Returns the canonical ``ServiceHints.service_id`` spelling on success.
    """
    if not element_id:
        return None
    known = list(known_service_ids)
    # (1) exact
    if element_id in known:
        return element_id
    # (2) normalized equals a hint id
    norm = normalize_element_id(element_id)
    for sid in known:
        if norm == sid or norm == normalize_element_id(sid):
            return sid
    # (3) service-suffix-insensitive
    for sid in known:
        if _service_equivalent(norm, sid) or _service_equivalent(
            normalize_element_id(element_id), normalize_element_id(sid)
        ):
            return sid
    return None


# ---- Locus helpers (REQ locus-grounded generate) -----------------------------

_LOCUS_BLOCKING = frozenset(
    {"no_source_locus", "unverifiable", "locus_unavailable"}
)
_ARTIFACT_SHAPE_GEN = frozenset({GEN_ENRICH_RUNBOOK, GEN_SHRINK})
_RED_RATE_RE = re.compile(
    r"(request|handled|started|received|http|grpc).*(total|count)|_(requests|ops|operations)_total$",
    re.I,
)
_RED_ERR_RE = re.compile(r"error|fail|drop|reject|5xx|failed", re.I)
# FR-1b: duration selection is two-tier — a STRONG signal (duration/latency/delay
# in the name) MUST win over the WEAK bare-`_seconds$`/`_bucket$` shape, and a
# `*_timestamp_seconds` gauge (a point-in-time marker, not a measured duration)
# MUST never be picked as a duration family at either tier.
_RED_DUR_STRONG_RE = re.compile(r"duration|latency|delay", re.I)
_RED_DUR_WEAK_RE = re.compile(r"_seconds$|_bucket$", re.I)
_RED_TIMESTAMP_RE = re.compile(r"_timestamp_seconds$", re.I)


def metric_loci(entry: AffordanceMapEntry) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for loc in entry.source_loci or []:
        fos = str(loc.get("family_or_signal") or "")
        kind = str(loc.get("signal_kind") or signal_kind_for(fos))
        if kind == "metric" and fos and not fos.startswith(("transport:", "component:")):
            row = dict(loc)
            row["signal_kind"] = "metric"
            out.append(row)
    return out


def is_transport_or_component_only(entry: AffordanceMapEntry) -> bool:
    """True when loci exist but none are metric families (FR-G2b)."""
    if not entry.source_loci:
        return False
    return not metric_loci(entry)


def merge_needed_where_into_entries(
    entries: Sequence[AffordanceMapEntry],
    needed_where: Union[Path, str, Mapping[str, Any]],
) -> List[AffordanceMapEntry]:
    """Transitional merge. AffordanceMap-native loci win on conflict (FR-G1)."""
    if isinstance(needed_where, (str, Path)):
        path = Path(needed_where)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("needed-where unreadable: %s", exc)
            return list(entries)
    else:
        data = needed_where
    if not isinstance(data, Mapping):
        return list(entries)
    rows = data.get("needed_where") or data.get("affordance_map") or []
    idx: Dict[Tuple[str, str], Mapping[str, Any]] = {}
    if isinstance(rows, list):
        for r in rows:
            if isinstance(r, Mapping):
                idx[(str(r.get("element_id") or ""), str(r.get("gap_code") or ""))] = r
    out: List[AffordanceMapEntry] = []
    for e in entries:
        if e.locus_status or e.source_loci:
            out.append(e)
            continue
        nw = idx.get((e.element_id, e.gap_code))
        if not nw:
            out.append(e)
            continue
        loci: List[Dict[str, Any]] = []
        for loc in nw.get("source_loci") or []:
            if isinstance(loc, Mapping):
                row = dict(loc)
                fos = str(row.get("family_or_signal") or "")
                row["signal_kind"] = row.get("signal_kind") or signal_kind_for(fos)
                loci.append(row)
        out.append(
            AffordanceMapEntry(
                element_id=e.element_id,
                gap_code=e.gap_code,
                affordance_ids=list(e.affordance_ids),
                confidence=e.confidence,
                provenance=e.provenance,
                unmapped_reason=e.unmapped_reason,
                locus_status=str(nw.get("status") or "") or None,
                source_loci=loci,
                locus_reason=str(nw["reason"]) if nw.get("reason") is not None else None,
            )
        )
    return out


def _pick_red_families(loci: Sequence[Mapping[str, Any]]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Distinct-family RED family selection (FR-1b, R1-F1/R1-F2).

    No two of the three returned families are ever the same name: each slot is
    filled only from names not already claimed by an earlier slot, and a slot
    with no distinct candidate is left ``None`` (omitted) rather than filled by
    a duplicate fallback. Order of assignment is error → duration → rate, so
    the duration slot's timestamp exclusion and strong/weak preference apply
    before rate's catch-all fallback claims a family duration would have used.
    """
    names = [str(l.get("family_or_signal")) for l in loci if l.get("family_or_signal")]

    err: Optional[str] = None
    for n in names:
        if _RED_ERR_RE.search(n):
            err = n
            break

    dur: Optional[str] = None
    for n in names:
        if n == err or _RED_TIMESTAMP_RE.search(n):
            continue
        if _RED_DUR_STRONG_RE.search(n):
            dur = n
            break
    if dur is None:
        for n in names:
            if n == err or _RED_TIMESTAMP_RE.search(n):
                continue
            if _RED_DUR_WEAK_RE.search(n):
                dur = n
                break

    rate: Optional[str] = None
    for n in names:
        if n in (err, dur):
            continue
        if _RED_RATE_RE.search(n):
            rate = n
            break
    if rate is None:
        for n in names:
            if n not in (err, dur):
                rate = n
                break

    return rate, err, dur


# ---- Load (FR-B1) ------------------------------------------------------------


class AffordanceMapError(ValueError):
    """Malformed or unreadable AffordanceMap."""


def load_affordance_map(
    source: Union[Path, str, Mapping[str, Any], Sequence[Any]],
) -> LoadResult:
    """Load AffordanceMap from path, dict (scorecard), or raw array.

    Detects history truncation when ``history.trimmed`` is set or the map is
    capped while ``gaps`` is longer (FR-B1 / AC-G11).
    """
    data: Any
    path_hint: Optional[Path] = None

    if isinstance(source, (str, Path)):
        path_hint = Path(source)
        try:
            text = path_hint.read_text(encoding="utf-8")
        except OSError as exc:
            return LoadResult(entries=[], error=f"unreadable: {exc}")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            return LoadResult(entries=[], error=f"malformed JSON: {exc}")
    else:
        data = source

    truncated = False
    shape = "array"
    rows: List[Any]

    if isinstance(data, list):
        rows = data
        shape = "array"
    elif isinstance(data, dict):
        shape = "scorecard"
        amap = data.get("affordance_map")
        if amap is None:
            return LoadResult(
                entries=[],
                error="scorecard object missing affordance_map",
                source_shape=shape,
            )
        if not isinstance(amap, list):
            return LoadResult(
                entries=[],
                error="affordance_map must be a list",
                source_shape=shape,
            )
        rows = amap
        history = data.get("history") or {}
        if isinstance(history, dict) and history.get("trimmed"):
            truncated = True
        gaps = data.get("gaps")
        if (
            isinstance(gaps, list)
            and len(rows) > 0
            and len(gaps) > len(rows)
            and len(rows) <= 15
        ):
            # HISTORY_AFFORDANCE_CAP = 15 — silent trim looks like success.
            truncated = True
    else:
        return LoadResult(entries=[], error="root must be array or object")

    entries: List[AffordanceMapEntry] = []
    for i, row in enumerate(rows):
        if not isinstance(row, Mapping):
            return LoadResult(
                entries=[],
                error=f"affordance_map[{i}] is not an object",
                source_shape=shape,
                source_truncated=truncated,
            )
        entries.append(AffordanceMapEntry.from_dict(row))

    if truncated:
        logger.warning(
            "AffordanceMap appears history-truncated (source_truncated=true)%s",
            f" path={path_hint}" if path_hint else "",
        )

    return LoadResult(
        entries=entries,
        source_truncated=truncated,
        source_shape=shape,
    )


# ---- Plan (FR-B2) ------------------------------------------------------------


def plan_affordance_actions(
    entries: Sequence[AffordanceMapEntry],
    known_service_ids: Sequence[str],
    *,
    service_filter: Optional[Sequence[str]] = None,
) -> PlanResult:
    """Build ordered action plan; unknown ids/services → skips (FR-B2, B6, B8 + locus)."""
    known = list(known_service_ids)
    filter_set: Optional[Set[str]] = set(service_filter) if service_filter else None

    if filter_set is not None:
        known = [s for s in known if s in filter_set]
        if not known:
            logger.info("AffordanceMap ∩ --services is empty; no-op")
            return PlanResult(actions=[], skips=[])

    planned: List[ActionPlanEntry] = []
    skips: List[ActionPlanEntry] = []
    # key -> (locus_rank, entry) for preference: source_backed (0) over partial (1)
    best: Dict[Tuple[str, str, str], Tuple[int, ActionPlanEntry]] = {}

    def _locus_rank(status: Optional[str]) -> int:
        if status == "source_backed":
            return 0
        if status == "partial":
            return 1
        return 2

    def _remember(entry: ActionPlanEntry, locus_status: Optional[str]) -> None:
        key = (entry.service_id, entry.gap_code, entry.affordance_id)
        rank = _locus_rank(locus_status)
        prev = best.get(key)
        if prev is None or rank < prev[0]:
            best[key] = (rank, entry)

    for entry in entries:
        matched = match_service_id(entry.element_id, known)
        if matched is None:
            skips.append(
                ActionPlanEntry(
                    service_id=entry.element_id or "(empty)",
                    affordance_id="(unresolved)",
                    artifact_types=[],
                    reason=f"unknown_element_id:{entry.element_id!r}",
                    gap_code=entry.gap_code,
                    confidence=entry.confidence,
                    outcome=ActionOutcome.SKIPPED,
                    unmapped_reason=entry.unmapped_reason,
                    locus_status=entry.locus_status,
                    locus_skip_reason=entry.locus_reason,
                )
            )
            continue

        ids = list(entry.affordance_ids)
        if not ids and entry.unmapped_reason:
            skips.append(
                ActionPlanEntry(
                    service_id=matched,
                    affordance_id="(unmapped)",
                    artifact_types=[],
                    reason=f"unmapped:{entry.unmapped_reason}",
                    gap_code=entry.gap_code,
                    confidence=entry.confidence,
                    outcome=ActionOutcome.SKIPPED,
                    unmapped_reason=entry.unmapped_reason,
                    locus_status=entry.locus_status,
                    locus_skip_reason=entry.locus_reason,
                    loci_used=list(entry.source_loci) if entry.source_loci else None,
                )
            )
            continue

        blocking = (entry.locus_status or "") in _LOCUS_BLOCKING
        transport_only = is_transport_or_component_only(entry)
        m_loci = metric_loci(entry)

        for aid in ids:
            if not aid.startswith("gen."):
                skips.append(
                    ActionPlanEntry(
                        service_id=matched,
                        affordance_id=aid,
                        artifact_types=[],
                        reason="non_gen_affordance",
                        gap_code=entry.gap_code,
                        confidence=entry.confidence,
                        outcome=ActionOutcome.SKIPPED,
                        unmapped_reason=entry.unmapped_reason,
                        locus_status=entry.locus_status,
                    )
                )
                continue
            if aid not in KNOWN_GEN_AFFORDANCES:
                skips.append(
                    ActionPlanEntry(
                        service_id=matched,
                        affordance_id=aid,
                        artifact_types=[],
                        reason=f"unknown_gen_affordance:{aid}",
                        gap_code=entry.gap_code,
                        confidence=entry.confidence,
                        outcome=ActionOutcome.SKIPPED,
                        unmapped_reason=entry.unmapped_reason,
                        locus_status=entry.locus_status,
                    )
                )
                continue

            if blocking and aid not in _ARTIFACT_SHAPE_GEN:
                skips.append(
                    ActionPlanEntry(
                        service_id=matched,
                        affordance_id=aid,
                        artifact_types=list(_ARTIFACT_TYPES.get(aid, [])),
                        reason=f"locus_blocked:{entry.locus_status}",
                        gap_code=entry.gap_code,
                        confidence=entry.confidence,
                        outcome=ActionOutcome.SKIPPED,
                        locus_status=entry.locus_status,
                        locus_skip_reason=entry.locus_reason or entry.locus_status,
                    )
                )
                continue

            if aid == GEN_EMIT_RED and transport_only:
                skips.append(
                    ActionPlanEntry(
                        service_id=matched,
                        affordance_id=aid,
                        artifact_types=list(_ARTIFACT_TYPES.get(aid, [])),
                        reason="transport_only_loci",
                        gap_code=entry.gap_code,
                        confidence=entry.confidence,
                        outcome=ActionOutcome.SKIPPED,
                        locus_status=entry.locus_status,
                        locus_skip_reason="transport_only_loci",
                        loci_used=list(entry.source_loci),
                    )
                )
                continue

            # Coverage: live when source_backed metric loci exist; else advisory skip
            if aid in ADVISORY_GEN:
                if entry.locus_status == "source_backed" and m_loci:
                    pe = ActionPlanEntry(
                        service_id=matched,
                        affordance_id=aid,
                        artifact_types=list(_ARTIFACT_TYPES.get(aid, [])),
                        reason=f"gap:{entry.gap_code or 'unspecified'}:locus_bind",
                        gap_code=entry.gap_code,
                        confidence=entry.confidence,
                        outcome=ActionOutcome.PLANNED,
                        locus_status=entry.locus_status,
                        loci_used=list(m_loci),
                    )
                    _remember(pe, entry.locus_status)
                    continue
                skips.append(
                    ActionPlanEntry(
                        service_id=matched,
                        affordance_id=aid,
                        artifact_types=list(_ARTIFACT_TYPES.get(aid, [])),
                        reason="no_deterministic_lever",
                        gap_code=entry.gap_code,
                        confidence=entry.confidence,
                        outcome=ActionOutcome.SKIPPED,
                        locus_status=entry.locus_status,
                        locus_skip_reason=entry.locus_reason,
                    )
                )
                continue

            pe = ActionPlanEntry(
                service_id=matched,
                affordance_id=aid,
                artifact_types=list(_ARTIFACT_TYPES.get(aid, [])),
                reason=f"gap:{entry.gap_code or 'unspecified'}",
                gap_code=entry.gap_code,
                confidence=entry.confidence,
                outcome=ActionOutcome.PLANNED,
                locus_status=entry.locus_status,
                loci_used=list(m_loci) if m_loci else (list(entry.source_loci) if entry.source_loci else None),
            )
            _remember(pe, entry.locus_status)

    planned = [v[1] for v in best.values()]
    planned.sort(
        key=lambda e: (_PRIORITY_INDEX.get(e.affordance_id, 99), e.service_id)
    )
    return PlanResult(actions=planned, skips=skips)


def exit_code_for_plan(
    load: LoadResult,
    plan: PlanResult,
    *,
    empty_intersection: bool = False,
) -> int:
    """FR-B1 exit table."""
    if load.error:
        return EXIT_MALFORMED
    if empty_intersection:
        return EXIT_OK
    if not load.entries:
        return EXIT_OK
    if plan.all_skipped or (not plan.actions and plan.skips):
        return EXIT_ALL_SKIPPED
    if not plan.actions and not plan.skips:
        return EXIT_OK
    return EXIT_OK


def format_plan_for_dry_run(plan: PlanResult) -> str:
    """Human-readable dry-run plan print."""
    lines = ["AffordanceMap action plan:"]
    if not plan.all_entries:
        lines.append("  (empty — nothing to do)")
        return "\n".join(lines)
    for e in plan.actions:
        lines.append(
            f"  + {e.service_id}  {e.affordance_id}  "
            f"artifacts={e.artifact_types}  reason={e.reason}"
        )
    for e in plan.skips:
        lines.append(
            f"  ~ SKIP  {e.service_id}  {e.affordance_id}  reason={e.reason}"
        )
    return "\n".join(lines)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def collect_source_provenance(load: LoadResult) -> List[str]:
    """Unique provenance strings from map entries (FR-B7 / R1-F3)."""
    return sorted({e.provenance for e in load.entries if e.provenance})


# Top-level keys required on every written affordance_actions.json (FR-B7).
SIDECAR_REQUIRED_KEYS: frozenset = frozenset(
    {
        "schema_version",
        "dry_run",
        "source_truncated",
        "source_shape",
        "source_provenance",
        "all_skipped",
        "summary",
        "planned",
        "applied",
        "applied_no_change",
        "skipped",
        "written_paths",
    }
)


def build_affordance_actions_payload(
    *,
    load: LoadResult,
    planned: Sequence[ActionPlanEntry],
    applied: Sequence[ActionPlanEntry],
    applied_no_change: Sequence[ActionPlanEntry],
    skipped: Sequence[ActionPlanEntry],
    dry_run: bool = False,
    written_paths: Optional[Sequence[str]] = None,
    all_skipped: Optional[bool] = None,
) -> Dict[str, Any]:
    """Build the FR-B7 sidecar document (shared by plan-only and apply writers)."""
    if all_skipped is None:
        all_skipped = (
            bool(load.entries)
            and not planned
            and not applied
            and not applied_no_change
        )
    return {
        "schema_version": 1,
        "dry_run": dry_run,
        "source_truncated": load.source_truncated,
        "source_shape": load.source_shape,
        "source_provenance": collect_source_provenance(load),
        "all_skipped": bool(all_skipped),
        "summary": {
            "planned": len(planned),
            "applied": len(applied),
            "applied_no_change": len(applied_no_change),
            "skipped": len(skipped),
        },
        "planned": [e.to_dict() for e in planned],
        "applied": [e.to_dict() for e in applied],
        "applied_no_change": [e.to_dict() for e in applied_no_change],
        "skipped": [e.to_dict() for e in skipped],
        "written_paths": list(written_paths or []),
    }


def write_affordance_actions_report(
    output_dir: Path,
    *,
    plan: PlanResult,
    load: LoadResult,
    dry_run: bool = False,
) -> Path:
    """Write affordance_actions.json from a plan (no-op / empty-intersect path).

    When ``dry_run=True``, returns the destination path but writes **zero** files
    (FR-B2a).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / "affordance_actions.json"
    payload = build_affordance_actions_payload(
        load=load,
        planned=plan.actions,
        applied=[],
        applied_no_change=[],
        skipped=plan.skips,
        dry_run=dry_run,
        written_paths=[],
        all_skipped=plan.all_skipped
        or (bool(load.entries) and not plan.actions),
    )
    if not dry_run:
        dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return dest


# ---- Merge helpers (FR-B3a / R1-S1) — WP-B0.5 --------------------------------


def merge_quality_services(
    prior: Mapping[str, Any],
    touched: Mapping[str, Any],
) -> Dict[str, Any]:
    """Merge touched per-service quality blocks into a prior quality JSON."""
    out: Dict[str, Any] = dict(prior)
    prior_services = dict(prior.get("services") or {})
    for svc_id, block in touched.items():
        prior_services[svc_id] = block
    out["services"] = prior_services
    if "aggregate" in prior and isinstance(prior["aggregate"], dict):
        composites = [
            v.get("composite_score")
            for v in prior_services.values()
            if isinstance(v, dict) and "composite_score" in v
        ]
        agg = dict(prior["aggregate"])
        if composites:
            agg["avg_composite_score"] = round(
                sum(float(c) for c in composites) / len(composites), 4
            )
            agg["services_scored"] = len(composites)
        out["aggregate"] = agg
    return out


def merge_manifest_artifacts(
    prior: Mapping[str, Any],
    touched_artifacts: Sequence[Mapping[str, Any]],
    *,
    touched_service_ids: Iterable[str] = (),  # noqa: ARG001 — API compat only
) -> Dict[str, Any]:
    """Upsert touched artifact rows by ``(type, service)``; keep siblings intact.

    Replacing *all* rows for a touched service (legacy behavior) wiped alert/SLO
    rows when only a dashboard was repaired — FR-B3a requires those to survive.
    ``touched_service_ids`` is retained for call-site compatibility but is not a
    wipe key (upsert key is ``(type, service)``).
    """
    _ = touched_service_ids
    out: Dict[str, Any] = dict(prior)
    prior_arts = list(prior.get("artifacts") or [])
    replace_keys = {
        (a.get("type"), a.get("service"))
        for a in touched_artifacts
        if isinstance(a, Mapping)
    }
    kept = [
        a
        for a in prior_arts
        if not (
            isinstance(a, dict)
            and (a.get("type"), a.get("service")) in replace_keys
        )
    ]
    out["artifacts"] = kept + [dict(a) for a in touched_artifacts]
    return out


def load_json_file(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load_yaml_file(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — merge is best-effort fail-soft
        logger.debug("failed to parse YAML %s: %s", path, exc)
        return None
    return data if isinstance(data, dict) else None




# ---- Shrink (WP-B2 / FR-B4) --------------------------------------------------


@dataclass
class ShrinkResult:
    """Outcome of a dashboard shrink attempt."""

    ok: bool
    spec: Dict[str, Any]
    rendered_json: Optional[str] = None
    reason: str = ""
    panels_dropped: int = 0
    lines_before: int = 0
    lines_after: int = 0
    # Evidence carrier for a "would_delete_metric_coverage" refusal (R1-F3):
    # the selector names that would have been lost by the refused drop.
    lost_selectors: Optional[List[str]] = None


def resolve_dashboard_max_lines(
    contracts: Optional[Mapping[str, Any]] = None,
    *,
    default: int = 300,
) -> int:
    """Resolve max_lines from expected_output_contracts.dashboard (FR-B4)."""
    if not contracts:
        return default
    dash = contracts.get("dashboard") if isinstance(contracts, Mapping) else None
    if isinstance(dash, Mapping):
        ml = dash.get("max_lines")
        if isinstance(ml, int) and ml > 0:
            return ml
    return default


def line_count(text: str) -> int:
    if not text:
        return 0
    return text.count("\n") + 1


# ---- Metric selector identity (FR-1 input; plan Step 1 / R1-S5, R2-S1, R2-S2) -

# PromQL keywords/operators that never name a metric.
_PROMQL_KEYWORDS: frozenset = frozenset(
    {
        "by", "without", "on", "ignoring", "group_left", "group_right",
        "offset", "bool", "and", "or", "unless", "atan2",
    }
)

# PromQL functions — always followed by "(" and never a metric selector, even
# though several (histogram_quantile, sum_over_time, label_replace, …) contain
# underscores like real Thanos series names.
_PROMQL_FUNCTIONS: frozenset = frozenset(
    {
        "rate", "irate", "increase", "delta", "idelta", "deriv", "predict_linear",
        "sum", "avg", "min", "max", "count", "count_values", "stddev", "stdvar",
        "topk", "bottomk", "quantile", "histogram_quantile", "abs", "ceil",
        "floor", "round", "exp", "ln", "log2", "log10", "sqrt", "clamp",
        "clamp_max", "clamp_min", "absent", "absent_over_time", "changes",
        "resets", "sort", "sort_desc", "vector", "scalar", "time", "timestamp",
        "label_replace", "label_join", "day_of_month", "day_of_week",
        "days_in_month", "hour", "minute", "month", "year", "sum_over_time",
        "avg_over_time", "min_over_time", "max_over_time", "count_over_time",
        "quantile_over_time", "stddev_over_time", "stdvar_over_time",
        "last_over_time", "present_over_time", "holt_winters",
    }
)

_METRIC_TOKEN_RE = re.compile(r"[A-Za-z_:][A-Za-z0-9_:]*")
_LABEL_MATCHER_RE = re.compile(
    r'([A-Za-z_][A-Za-z0-9_]*)\s*(=~|!~|!=|=)\s*"((?:[^"\\]|\\.)*)"'
)
# A genuine histogram always exposes these three legs under one base name.
_HIST_SUFFIXES: Tuple[str, ...] = ("_bucket", "_count", "_sum")
# PromQL duration-literal units (``5m``, ``1h30m``, ``30s``, …) — a bare unit
# letter immediately after a digit is a duration suffix, never a metric name.
_DURATION_UNITS: frozenset = frozenset({"ms", "s", "m", "h", "d", "w", "y"})


class SelectorParseError(ValueError):
    """A PromQL expression could not be parsed for selector identity.

    Raised rather than swallowed (R1-F2): a parse failure must never look like
    "this query touches zero metrics" to the FR-1 subset check, or a real
    deletion could satisfy the invariant vacuously.
    """


def _normalize_label_matchers(
    label_block: str, *, drop: frozenset = frozenset()
) -> Tuple[Tuple[str, str, str], ...]:
    """Sorted ``(name, op, value)`` triples — full matcher identity (R2-S2).

    Distinct label matchers on the same metric name are distinct selectors;
    only ``drop`` (used for the histogram ``le`` bucket label) is elided.
    """
    pairs = [
        (k, op, v)
        for k, op, v in _LABEL_MATCHER_RE.findall(label_block or "")
        if k not in drop
    ]
    return tuple(sorted(pairs))


def _extract_raw_selectors(expr: str) -> List[Tuple[str, str]]:
    """Scan a PromQL expression for ``(metric_name, label_block)`` pairs.

    Fail-closed on an unbalanced ``{`` — raises :class:`SelectorParseError`
    instead of returning a partial/empty result for that expression.
    """
    out: List[Tuple[str, str]] = []
    i, n = 0, len(expr)
    while i < n:
        c = expr[i]
        if c == "[":
            # Range-vector / subquery duration span, e.g. "[5m]" or "[1h:5m]"
            # — never contains a metric selector, only durations.
            depth, j = 0, i
            while j < n:
                if expr[j] == "[":
                    depth += 1
                elif expr[j] == "]":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
            i = j if j > i else i + 1
            continue
        m = _METRIC_TOKEN_RE.match(expr, i)
        if not m:
            i += 1
            continue
        tok = m.group(0)
        start = m.start()
        i = m.end()
        low = tok.lower()
        if low in _DURATION_UNITS and start > 0 and expr[start - 1].isdigit():
            # "offset 5m" / "1h30m" outside a "[...]" span.
            continue
        if low in ("by", "without"):
            # "sum by (le, job) (...)" / "... without (instance) (...)" — the
            # parenthesized list is label names, never metric selectors.
            k = i
            while k < n and expr[k] in " \t":
                k += 1
            if k < n and expr[k] == "(":
                depth, j = 0, k
                while j < n:
                    if expr[j] == "(":
                        depth += 1
                    elif expr[j] == ")":
                        depth -= 1
                        if depth == 0:
                            j += 1
                            break
                    j += 1
                else:
                    raise SelectorParseError(
                        f"unbalanced by/without parens in expr: {expr!r}"
                    )
                i = j
            continue
        if low in _PROMQL_KEYWORDS or low in _PROMQL_FUNCTIONS:
            continue
        if i < n and expr[i] == "(" and "_" not in tok:
            # Bare identifier(...) call with no metric-shaped name — treat as
            # an unknown function rather than a selector.
            continue
        label_block = ""
        if i < n and expr[i] == "{":
            depth, j = 0, i
            while j < n:
                if expr[j] == "{":
                    depth += 1
                elif expr[j] == "}":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
            else:
                raise SelectorParseError(
                    f"unbalanced selector brace in expr: {expr!r}"
                )
            label_block = expr[i:j]
            i = j
        out.append((tok, label_block))
    return out


def dashboard_metric_selectors(spec_or_rendered: Mapping[str, Any]) -> frozenset:
    """Selector-identity set for a dashboard spec or rendered Grafana JSON.

    Reads ``panels[].expr`` (spec shape) and ``panels[].targets[].expr``
    (rendered shape), recursing into Grafana row panels' nested ``panels[]``
    (R2-S1). Histogram ``_bucket``/``_count``/``_sum`` legs of the *same*
    base name + label set collapse to one selector **only when at least two
    of the legs actually co-occur** — a lone ``..._count`` metric that merely
    shares a suffix with no sibling ``_bucket`` is not merged into a family
    it may not belong to (R1-S5: cardinality is the property FR-1 must not
    let a normalizer quietly erase). Distinct label matchers on the same
    metric name remain distinct selectors (R2-S2); only the bucket ``le``
    label is elided when collapsing a confirmed histogram family.

    Raises :class:`SelectorParseError` (fail-closed, R1-F2) rather than
    silently contributing an empty selector set for an unparseable query.
    """
    families: Dict[Tuple[str, Tuple[Tuple[str, str, str], ...]], Set[str]] = {}

    def visit(panel: Mapping[str, Any]) -> None:
        exprs: List[str] = []
        if panel.get("expr"):
            exprs.append(str(panel["expr"]))
        for t in panel.get("targets") or []:
            if isinstance(t, Mapping) and t.get("expr"):
                exprs.append(str(t["expr"]))
        for expr in exprs:
            for name, label_block in _extract_raw_selectors(expr):
                base = name
                is_hist_leg = False
                for suf in _HIST_SUFFIXES:
                    if name.endswith(suf):
                        base = name[: -len(suf)]
                        is_hist_leg = True
                        break
                drop = frozenset({"le"}) if is_hist_leg else frozenset()
                labels = _normalize_label_matchers(label_block, drop=drop)
                key = (base, labels) if is_hist_leg else (name, labels)
                families.setdefault(key, set()).add(name)
        for child in panel.get("panels") or []:
            if isinstance(child, Mapping):
                visit(child)

    for p in spec_or_rendered.get("panels") or []:
        if isinstance(p, Mapping):
            visit(p)

    selectors: Set[str] = set()
    for (base_or_name, labels), names in families.items():
        label_str = ",".join(f'{k}{op}"{v}"' for k, op, v in labels)
        has_bucket = any(nm.endswith("_bucket") for nm in names)
        if has_bucket and len(names) > 1:
            selectors.add(f"{base_or_name}{{{label_str}}}")
        else:
            for nm in names:
                selectors.add(f"{nm}{{{label_str}}}")
    return frozenset(selectors)


def try_render_grafana_json(spec_dict: Mapping[str, Any]) -> Optional[str]:
    """Render a dashboard spec to Grafana JSON; None if toolchain unavailable."""
    try:
        from startd8.dashboard_creator.workflow import DashboardCreatorWorkflow
    except ImportError:
        return None
    import tempfile

    try:
        workflow = DashboardCreatorWorkflow()
        with tempfile.TemporaryDirectory() as staging:
            result = workflow.run(
                {
                    "spec": dict(spec_dict),
                    "output_dir": staging,
                    "enforce_uid": False,
                }
            )
            if not getattr(result, "success", False):
                return None
            uid = spec_dict.get("uid", "obs-dashboard")
            produced = Path(staging) / f"{uid}.json"
            if produced.is_file():
                return produced.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001 — shrink must refuse, not crash
        logger.exception("Grafana JSON render failed during shrink")
    return None


def _panel_is_red_protected(panel: Mapping[str, Any]) -> bool:
    """True if dropping this panel would risk OBS-200a Rate/Errors/Duration."""
    title = str(panel.get("title") or "").lower()
    group = str(panel.get("group") or "").lower()
    expr = str(panel.get("expr") or "").lower()
    if group in ("throughput", "errors", "latency") or title in (
        "request rate",
        "error rate",
    ):
        return True
    if "duration" in title or "latency" in title:
        return True
    if "rate(" in expr and ("_count" in expr or "_total" in expr):
        if "status" not in expr and "error" not in expr:
            return True  # Rate leg
        if "error" in expr or "status" in expr:
            return True  # Errors leg
    if "histogram_quantile" in expr and (
        "duration" in expr or "latency" in expr
    ):
        return True
    return False


def _red_coverage_ok(panels: Sequence[Mapping[str, Any]]) -> bool:
    try:
        from startd8.validators.observability_artifact_checks import (
            _compute_red_coverage,
        )

        return _compute_red_coverage(list(panels)) >= (2.0 / 3.0)
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "RED coverage scorer unavailable (%s); using protected-panel fallback",
            exc,
        )
        protected = sum(1 for p in panels if _panel_is_red_protected(p))
        return protected >= 2


def _reflow_gridpos(panels: List[Dict[str, Any]]) -> None:
    """Re-assign a 2-column grid and unique ids after drops (FR-B4)."""
    w, h = 12, 8
    for i, panel in enumerate(panels):
        panel["gridPos"] = {"h": h, "w": w, "x": (i % 2) * 12, "y": (i // 2) * h}
        panel["id"] = i + 1


def _drop_priority(panel: Mapping[str, Any]) -> int:
    """Higher = drop sooner. Prefer verbose / non-RED / duplicate-looking."""
    if _panel_is_red_protected(panel):
        return -1000
    title = str(panel.get("title") or "").lower()
    group = str(panel.get("group") or "").lower()
    score = 0
    if group in ("cost & tokens", "sessions", "progress", "health"):
        score += 20
    if "p50" in title or "p95" in title:
        score += 15
    if "body.size" in title or "size" in title:
        score += 10
    return score


RenderFn = Callable[[Mapping[str, Any]], Optional[str]]


def shrink_dashboard_lines(
    spec_dict: Mapping[str, Any],
    *,
    max_lines: int,
    preserve_red: bool = True,  # noqa: ARG001 — kept for call-site compat (FR-2)
    render_fn: Optional[RenderFn] = None,
) -> ShrinkResult:
    """Shrink a dashboard **spec** until rendered JSON <= max_lines, refusing
    honestly rather than deleting Thanos metric coverage (FR-B4 / FR-1..FR-3).

    Refusal precedence ladder inside the drop loop (R1-S1), checked freshly
    each iteration against the *current* top-priority candidate:

      1. ``no_drop_signal`` — every remaining candidate has the same
         ``_drop_priority`` score (no ordering signal at all; a stable sort
         would delete-by-list-position, not by judgement). FR-3.
      2. ``would_delete_metric_coverage`` — the top-priority candidate is the
         only carrier of one or more metric selectors; dropping it would
         shrink the dashboard's selector set below what it started with.
         FR-1. This subsumes the old RED-regression gate: a RED panel that
         is a real metric's only carrier is refused for the same reason a
         non-RED one would be; a panel that is *not* uniquely load-bearing
         (a duplicate view, a decorative/non-metric panel) may be dropped
         even if it happens to look RED-shaped, because nothing is lost.

    ``preserve_red``/``_red_coverage_ok`` are no longer an in-loop gate
    (FR-2 — the gate was inert on every real subject dashboard: RED coverage
    never reached 2/3 on any of them, so it could never fire) — RED-looking
    panels still sort last via ``_drop_priority``'s -1000, which is now
    ordering input only, not a second, redundant safety mechanism (PRE-6).

    On refuse, ``spec`` is left unchanged from the last successful drop
    (candidate drops are staged before being accepted).
    """
    render: RenderFn = render_fn or try_render_grafana_json
    spec: Dict[str, Any] = json.loads(json.dumps(spec_dict))  # deep copy via JSON
    panels: List[Dict[str, Any]] = list(spec.get("panels") or [])
    _reflow_gridpos(panels)
    spec["panels"] = panels

    try:
        pre_selectors = dashboard_metric_selectors(spec)
    except SelectorParseError:
        return ShrinkResult(
            ok=False, spec=spec, reason="selector_parse_failed", panels_dropped=0
        )

    rendered = render(spec)
    if rendered is None:
        return ShrinkResult(
            ok=False,
            spec=spec,
            reason="render_unavailable",
            panels_dropped=0,
        )
    before_lines = line_count(rendered)
    if before_lines <= max_lines:
        return ShrinkResult(
            ok=True,
            spec=spec,
            rendered_json=rendered,
            reason="already_under_budget",
            panels_dropped=0,
            lines_before=before_lines,
            lines_after=before_lines,
        )

    dropped = 0
    while line_count(rendered) > max_lines:
        candidates = list(enumerate(panels))
        if not candidates:
            return ShrinkResult(
                ok=False,
                spec=spec,
                rendered_json=rendered,
                reason="panel_graph_integrity",
                panels_dropped=dropped,
                lines_before=before_lines,
                lines_after=line_count(rendered),
            )
        scores = [_drop_priority(p) for _, p in candidates]
        if len(set(scores)) <= 1:
            # Global tie: no candidate is distinguishable from any other, so
            # any pick is "deleted by list position, not judgement" (FR-3).
            return ShrinkResult(
                ok=False,
                spec=spec,
                rendered_json=rendered,
                reason="no_drop_signal",
                panels_dropped=dropped,
                lines_before=before_lines,
                lines_after=line_count(rendered),
            )
        candidates.sort(key=lambda ip: _drop_priority(ip[1]), reverse=True)
        drop_i, _victim = candidates[0]
        staged: List[Dict[str, Any]] = json.loads(json.dumps(panels))
        staged.pop(drop_i)
        _reflow_gridpos(staged)
        staged_spec = dict(spec)
        staged_spec["panels"] = staged
        try:
            post_selectors = dashboard_metric_selectors(staged_spec)
        except SelectorParseError:
            return ShrinkResult(
                ok=False,
                spec=spec,
                rendered_json=rendered,
                reason="selector_parse_failed",
                panels_dropped=dropped,
                lines_before=before_lines,
                lines_after=line_count(rendered),
            )
        if not (pre_selectors <= post_selectors):
            return ShrinkResult(
                ok=False,
                spec=spec,
                rendered_json=rendered,
                reason="would_delete_metric_coverage",
                panels_dropped=dropped,
                lines_before=before_lines,
                lines_after=line_count(rendered),
                lost_selectors=sorted(pre_selectors - post_selectors),
            )
        panels = staged
        spec["panels"] = panels
        dropped += 1
        rendered = render(spec)
        if rendered is None:
            return ShrinkResult(
                ok=False,
                spec=spec,
                reason="render_unavailable",
                panels_dropped=dropped,
                lines_before=before_lines,
            )

    for p in panels:
        if "expr" not in p and "targets" not in p:
            return ShrinkResult(
                ok=False,
                spec=spec,
                rendered_json=rendered,
                reason="panel_graph_integrity",
                panels_dropped=dropped,
                lines_before=before_lines,
                lines_after=line_count(rendered),
            )

    return ShrinkResult(
        ok=True,
        spec=spec,
        rendered_json=rendered,
        reason="shrunk",
        panels_dropped=dropped,
        lines_before=before_lines,
        lines_after=line_count(rendered),
    )

# ---- Apply (WP-B1) -----------------------------------------------------------


@dataclass
class ApplyResult:
    """Outcomes from applying a plan to disk."""

    entries: List[ActionPlanEntry]
    written_paths: List[str] = field(default_factory=list)
    touched_service_ids: List[str] = field(default_factory=list)
    quality_touched: Dict[str, Any] = field(default_factory=dict)
    manifest_touched: List[Dict[str, Any]] = field(default_factory=list)


def _triplet_legs_needed(
    output_dir: Path,
    service_id: str,
) -> Tuple[List[str], str]:
    """Return (legs_to_regen, reason). Absent quality → all three."""
    all_legs = ["alert_rule", "dashboard_spec", "slo_definition"]
    quality = load_json_file(output_dir / "observability-quality.json")
    if quality is None:
        return list(all_legs), "leg_signal_unavailable"
    svc = (quality.get("services") or {}).get(service_id) or {}
    needed: List[str] = []
    for leg in all_legs:
        block = svc.get(leg)
        if not isinstance(block, dict) or "score" not in block:
            needed.append(leg)
        elif float(block.get("score") or 0.0) == 0.0:
            needed.append(leg)
    if not needed:
        # Map asked for complete_triplet but legs look fine — still no-op.
        return [], "legs_already_complete"
    return needed, f"gap:triplet_incomplete:{','.join(needed)}"


def _artifact_quality_block(artifact: Any) -> Dict[str, Any]:
    """Project ArtifactResult.quality into the quality-JSON leg shape."""
    q = getattr(artifact, "quality", None) or {}
    return {
        "score": q.get("score", 0.0),
        "checks_passed": q.get("checks_passed", 0),
        "checks_total": q.get("checks_total", 0),
        "issues": q.get("issues", []),
        "repairs_applied": q.get("repairs_applied", []),
    }


def _confined_dest(output_dir: Path, relative: str) -> Optional[Path]:
    """Resolve ``relative`` under ``output_dir``; None if it escapes the root."""
    if not relative or Path(relative).is_absolute():
        logger.warning("refusing absolute or empty artifact path: %r", relative)
        return None
    root = output_dir.resolve()
    dest = (output_dir / relative).resolve()
    if not dest.is_relative_to(root):
        logger.warning(
            "refusing path escape: %s is outside output_dir %s", dest, root
        )
        return None
    return dest


def _write_one(output_dir: Path, artifact: Any) -> Optional[str]:
    """Write a generated artifact under ``output_dir`` (path-confined).

    Returns the relative ``output_path`` on success, or None when status/content
    is missing or the path would escape ``output_dir``.
    """
    if getattr(artifact, "status", None) != "generated" or not getattr(
        artifact, "content", None
    ):
        return None
    rel = str(getattr(artifact, "output_path", "") or "")
    dest = _confined_dest(output_dir, rel)
    if dest is None:
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(artifact.content, encoding="utf-8")
    return rel


_HEADING_RENAMES: Tuple[Tuple[re.Pattern, str], ...] = (
    (re.compile(r"^##\s+Service summary\s*$", re.MULTILINE), "## Overview"),
    (re.compile(r"^##\s+First response\s*$", re.MULTILINE), "## Procedures"),
)

def _risks_section_body(service: Any, business: Any) -> str:
    """Deterministic Risks bullets (same sources as FR-B5 ``generate_runbook``)."""
    avail = getattr(business, "availability", None) or "—"
    crit = getattr(business, "criticality", None) or "medium"
    bits = [
        f"- Criticality is **{crit}**; availability target **{avail}**.",
    ]
    kinds = list(getattr(service, "kinds", None) or [])
    if kinds:
        bits.append(
            f"- Declared kinds ({', '.join(kinds)}) drive which RED/SLI panels apply — "
            "missing throughput/availability kinds leave Rate/Error coverage incomplete."
        )
    else:
        bits.append(
            "- No service kinds declared — RED completeness depends on transport defaults; "
            "verify OBS-200a after regenerate."
        )
    return "\n".join(bits)


def _section_span(text: str, heading: str) -> Optional[Tuple[int, int]]:
    """Return ``[start, end)`` of the body after ``heading`` until the next ``##``."""
    m = re.search(rf"^{re.escape(heading)}\s*$", text, re.MULTILINE)
    if not m:
        return None
    start = m.end()
    nxt = re.search(r"^##\s+", text[start:], re.MULTILINE)
    end = start + nxt.start() if nxt else len(text)
    return start, end


def _insert_before_heading_or_append(text: str, heading: str, block: str) -> str:
    m = re.search(rf"^{re.escape(heading)}\s*$", text, re.MULTILINE)
    if m:
        return text[: m.start()] + block + text[m.start() :]
    return text.rstrip() + "\n\n" + block


def _insert_after_section(text: str, heading: str, block: str) -> str:
    span = _section_span(text, heading)
    if span is None:
        return text.rstrip() + "\n\n" + block
    _, end = span
    return text[:end] + block + text[end:]


def _ensure_risks_nonempty(text: str, service: Any, business: Any) -> str:
    span = _section_span(text, "## Risks")
    if span is None:
        return text
    start, end = span
    body = text[start:end]
    has_content = any(
        ln.strip() and not ln.strip().startswith("#") for ln in body.splitlines()
    )
    if has_content:
        return text
    fill = "\n\n" + _risks_section_body(service, business) + "\n\n"
    return text[:start] + fill + text[end:]


def enrich_runbook_markdown(
    content: str,
    *,
    service: Any,
    business: Any,
) -> str:
    """Idempotent retrofit: old FR-B5-pre headings → contract markers + Risks body.

    Renames ``Service summary``→``Overview``, ``First response``→``Procedures``;
    injects missing Overview/Risks/Procedures/Escalation; fills hollow Risks.
    Keeps Escalation (and other sections) intact.
    """
    text = content or ""
    for pat, repl in _HEADING_RENAMES:
        text = pat.sub(repl, text)

    sid = getattr(service, "service_id", None) or "service"
    if "## Overview" not in text:
        overview = (
            f"## Overview\n\n"
            f"- **Service:** {sid}\n"
            f"- **Transport:** {getattr(service, 'transport', None) or 'unknown'}\n\n"
        )
        # After title / blockquote preamble when present
        m = re.search(r"^#\s+.+$", text, re.MULTILINE)
        if m:
            rest = text[m.end() :]
            # skip blank + optional blockquote lines
            pos = 0
            lines = rest.splitlines(keepends=True)
            i = 0
            while i < len(lines) and not lines[i].strip():
                i += 1
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            pos = m.end() + sum(len(lines[j]) for j in range(i))
            text = text[:pos] + overview + text[pos:]
        else:
            text = overview + text

    if "## Risks" not in text:
        risks = f"## Risks\n\n{_risks_section_body(service, business)}\n\n"
        text = _insert_after_section(text, "## Overview", risks)

    if "## Procedures" not in text:
        procedures = (
            "## Procedures\n\n"
            "1. Open the service dashboard; check the RED panels (rate, errors, duration).\n"
            "2. Correlate with recent deploys and the error-rate panel.\n"
            "3. Check logs for error spikes.\n\n"
        )
        if "## Escalation" in text:
            text = _insert_before_heading_or_append(text, "## Escalation", procedures)
        else:
            text = text.rstrip() + "\n\n" + procedures

    if "## Escalation" not in text:
        text = (
            text.rstrip()
            + "\n\n## Escalation\n\n- Notify the owning team.\n"
        )

    text = _ensure_risks_nonempty(text, service, business)
    if not text.endswith("\n"):
        text += "\n"
    return text


def _apply_enrich_runbook(
    entry: ActionPlanEntry,
    *,
    service: Any,
    business: Any,
    output_dir: Path,
    result: ApplyResult,
) -> None:
    """Live apply for ``gen.enrich_runbook`` — retrofit on-disk runbook markdown.

    Retrofit-only by contract: a missing runbook is ``no_runbook``, never a
    synthesized file. Neither ``quality_touched`` nor ``manifest_touched`` is
    populated — the runbook leg has no disk re-score path, so writing a leg score
    would move ``avg_composite_score`` while leaving ``avg_runbook_score`` stale.
    The ``affordance_actions.json`` sidecar is the whole evidence surface, which
    keeps ``observability-quality.json`` / ``observability-manifest.yaml``
    byte-identical for a runbook-only map.
    """
    rel = f"runbooks/{service.service_id}-runbook.md"
    dest = _confined_dest(output_dir, rel)
    if dest is None:
        entry.outcome = ActionOutcome.SKIPPED
        entry.reason = "path_escape"
        result.entries.append(entry)
        return

    before = dest.read_text(encoding="utf-8") if dest.is_file() else ""
    entry.content_hash_before = content_hash(before) if before else None

    if not before.strip():
        entry.outcome = ActionOutcome.SKIPPED
        entry.reason = "no_runbook"
        result.entries.append(entry)
        return

    after = enrich_runbook_markdown(before, service=service, business=business)
    entry.content_hash_after = content_hash(after)
    if after == before:
        entry.outcome = ActionOutcome.APPLIED_NO_CHANGE
        entry.reason = "runbook_markers_already_present"
        entry.content_hash_after = entry.content_hash_before
        result.entries.append(entry)
        return

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(after, encoding="utf-8")
    result.written_paths.append(rel)
    entry.outcome = ActionOutcome.APPLIED
    entry.reason = "enrich_runbook"
    result.touched_service_ids.append(service.service_id)
    result.entries.append(entry)


def _apply_shrink(
    entry: ActionPlanEntry,
    *,
    service: Any,
    business: Any,
    descriptor: Any,
    output_dir: Path,
    result: ApplyResult,
    contracts: Optional[Mapping[str, Any]],
    max_lines: Optional[int],
    render_fn: Optional[RenderFn],
    generate_dashboard_spec: Any,
    repair_and_validate: Any,
) -> None:
    """Apply ``gen.shrink_dashboard_lines`` for one service."""
    dash_rel = f"dashboards/{service.service_id}-dashboard-spec.yaml"
    dash_path = output_dir / dash_rel
    if not dash_path.is_file():
        art = generate_dashboard_spec(service, business, descriptor)
        art = repair_and_validate(art, business, transport=service.transport)
        if art.status != "generated" or not art.content:
            entry.outcome = ActionOutcome.SKIPPED
            entry.reason = "no_dashboard_spec"
            result.entries.append(entry)
            return
        written = _write_one(output_dir, art)
        if written:
            # R1-F5: this write happens before any FR-1/FR-3/FR-4 precondition
            # can fire — a later refusal must not silently omit it from the
            # sidecar's written_paths accounting.
            result.written_paths.append(written)
    before = dash_path.read_text(encoding="utf-8")
    entry.content_hash_before = content_hash(before)
    gj_rel = f"grafana/dashboards/{service.service_id}-dashboard.json"
    gj_path = output_dir / gj_rel
    if gj_path.is_file():
        entry.rendered_hash_before = content_hash(
            gj_path.read_text(encoding="utf-8")
        )
    try:
        spec_dict = yaml.safe_load(before)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "dashboard spec unparseable for shrink service=%s path=%s: %s",
            service.service_id,
            dash_path,
            exc,
            exc_info=True,
        )
        entry.outcome = ActionOutcome.SKIPPED
        entry.reason = "dashboard_spec_unparseable"
        result.entries.append(entry)
        return
    if not isinstance(spec_dict, dict):
        entry.outcome = ActionOutcome.SKIPPED
        entry.reason = "dashboard_spec_unparseable"
        result.entries.append(entry)
        return

    ml = max_lines if max_lines is not None else resolve_dashboard_max_lines(contracts)

    # ---- Spec<->render coherence precondition (FR-4/FR-6, plan Step 3) ----
    # A fresh re-render is always spec-derived and can never drift from the
    # spec's own selectors; the drift this guards against is between the
    # spec and whatever rendered artifact *already exists on disk* (e.g. an
    # earlier, differently-templated generation). Checked symmetrically
    # (R3-S1): either direction of divergence is a coherence failure.
    try:
        spec_selectors = dashboard_metric_selectors(spec_dict)
    except SelectorParseError:
        entry.outcome = ActionOutcome.SKIPPED
        entry.reason = "selector_parse_failed"
        entry.content_hash_after = entry.content_hash_before
        entry.rendered_hash_after = entry.rendered_hash_before
        result.entries.append(entry)
        return

    entry.render_available = gj_path.is_file()
    scored_lines: Optional[int] = None
    if entry.render_available:
        rendered_text = gj_path.read_text(encoding="utf-8")
        try:
            rendered_dict = json.loads(rendered_text)
            render_selectors = dashboard_metric_selectors(rendered_dict)
        except (json.JSONDecodeError, SelectorParseError):
            render_selectors = None
        if render_selectors is not None:
            spec_only = spec_selectors - render_selectors
            render_only = render_selectors - spec_selectors
            if spec_only or render_only:
                entry.outcome = ActionOutcome.SKIPPED
                entry.reason = "spec_render_drift"
                entry.content_hash_after = entry.content_hash_before
                entry.rendered_hash_after = entry.rendered_hash_before
                entry.legs = sorted(spec_only) + [f"+{s}" for s in sorted(render_only)]
                result.entries.append(entry)
                return
            scored_lines = line_count(rendered_text)

    shrink = shrink_dashboard_lines(
        spec_dict,
        max_lines=ml,
        preserve_red=True,
        render_fn=render_fn,
    )
    if not shrink.ok:
        entry.outcome = ActionOutcome.SKIPPED
        entry.reason = shrink.reason
        entry.content_hash_after = entry.content_hash_before
        entry.rendered_hash_after = entry.rendered_hash_before
        if shrink.lost_selectors:
            entry.legs = shrink.lost_selectors
        result.entries.append(entry)
        return

    if shrink.panels_dropped == 0 and shrink.reason == "already_under_budget":
        # FR-4/FR-6: the spec being under budget is not sufficient when the
        # already-scored artifact on disk is still over — that would be a
        # false APPLIED_NO_CHANGE (the row-level fix; the class-level
        # exit_code_for_apply residual is out of scope, see R1-S3).
        if scored_lines is not None and scored_lines > ml:
            entry.outcome = ActionOutcome.SKIPPED
            entry.reason = "scored_artifact_over_budget"
            entry.content_hash_after = entry.content_hash_before
            entry.rendered_hash_after = entry.rendered_hash_before
            result.entries.append(entry)
            return
        entry.outcome = ActionOutcome.APPLIED_NO_CHANGE
        entry.reason = "already_under_budget"
        entry.content_hash_after = entry.content_hash_before
        entry.rendered_hash_after = entry.rendered_hash_before
        result.entries.append(entry)
        return

    header = (
        "# DashboardSpec — generated by startd8 observability artifact generator\n"
        f"# service: {service.service_id}\n\n"
    )
    new_content = header + yaml.safe_dump(
        shrink.spec, sort_keys=False, default_flow_style=False
    )
    entry.content_hash_after = content_hash(new_content)
    confined = _confined_dest(output_dir, dash_rel)
    if confined is None:
        entry.outcome = ActionOutcome.SKIPPED
        entry.reason = "path_escape"
        result.entries.append(entry)
        return
    confined.write_text(new_content, encoding="utf-8")
    result.written_paths.append(dash_rel)
    if shrink.rendered_json:
        gj_dest = _confined_dest(output_dir, gj_rel)
        if gj_dest is not None:
            gj_dest.parent.mkdir(parents=True, exist_ok=True)
            gj_dest.write_text(shrink.rendered_json, encoding="utf-8")
            result.written_paths.append(gj_rel)
            entry.rendered_hash_after = content_hash(shrink.rendered_json)
    entry.outcome = ActionOutcome.APPLIED
    entry.reason = (
        f"shrunk lines {shrink.lines_before}->{shrink.lines_after} "
        f"dropped={shrink.panels_dropped}"
    )
    result.touched_service_ids.append(service.service_id)
    result.manifest_touched.append(
        {
            "type": "dashboard_spec",
            "service": service.service_id,
            "path": dash_rel,
            "status": "generated",
        }
    )
    result.entries.append(entry)


def _locus_red_dashboard_yaml(
    service_id: str,
    loci: Sequence[Mapping[str, Any]],
) -> str:
    """Minimal dashboard_spec YAML using only cited metric families (FR-G2/G3)."""
    rate, err, dur = _pick_red_families(loci)
    panels: List[Dict[str, Any]] = []
    used: List[str] = []
    if rate:
        panels.append(
            {
                "type": "timeseries",
                "title": "Request Rate",
                "expr": f"sum(rate({rate}[$__rate_interval]))",
                "unit": "reqps",
                "group": "Throughput",
            }
        )
        used.append(rate)
    if err:
        panels.append(
            {
                "type": "timeseries",
                "title": "Error Rate",
                "expr": f"sum(rate({err}[$__rate_interval]))",
                "unit": "reqps",
                "group": "Errors",
            }
        )
        used.append(err)
    if dur:
        panels.append(
            {
                "type": "timeseries",
                "title": "Duration",
                "expr": f"histogram_quantile(0.99, sum(rate({dur}[$__rate_interval])) by (le))"
                if dur.endswith("_bucket")
                else f"sum(rate({dur}[$__rate_interval]))",
                "unit": "s",
                "group": "Latency",
            }
        )
        used.append(dur)
    if not panels:
        return ""
    spec = {
        "apiVersion": "grafana.observability/v1alpha1",
        "kind": "DashboardSpec",
        "metadata": {"name": f"{service_id}-locus-red"},
        "spec": {
            "title": f"{service_id} RED (locus-grounded)",
            "panels": panels,
            "locus_families": used,
        },
    }
    return yaml.safe_dump(spec, sort_keys=False)


def _apply_emit_red(
    entry: ActionPlanEntry,
    *,
    service: Any,
    business: Any,
    descriptor: Any,
    output_dir: Path,
    result: ApplyResult,
    generate_dashboard_spec: Any,
    repair_and_validate: Any,
    service_sli_kinds: Any,
) -> None:
    """Apply ``gen.emit_red_panels`` for one service (locus-biased when loci present)."""
    sli = service_sli_kinds(service, business)
    dash_path = output_dir / f"dashboards/{service.service_id}-dashboard-spec.yaml"
    before = dash_path.read_text(encoding="utf-8") if dash_path.is_file() else ""
    entry.content_hash_before = content_hash(before) if before else None

    loci = list(entry.loci_used or [])
    metric_only = [
        l
        for l in loci
        if str(l.get("signal_kind") or signal_kind_for(str(l.get("family_or_signal") or "")))
        == "metric"
    ]

    if metric_only:
        after = _locus_red_dashboard_yaml(service.service_id, metric_only)
        if not after:
            entry.outcome = ActionOutcome.SKIPPED
            entry.reason = "locus_families_unusable"
            entry.locus_skip_reason = "locus_families_unusable"
            result.entries.append(entry)
            return
        entry.content_hash_after = content_hash(after)
        if before and content_hash(before) == entry.content_hash_after:
            entry.outcome = ActionOutcome.APPLIED_NO_CHANGE
            entry.reason = "red_already_complete_locus"
            result.entries.append(entry)
            return
        dash_rel = f"dashboards/{service.service_id}-dashboard-spec.yaml"
        dest = _confined_dest(output_dir, dash_rel)
        if dest is None:
            entry.outcome = ActionOutcome.SKIPPED
            entry.reason = "path_escape"
            result.entries.append(entry)
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(after, encoding="utf-8")
        # Use planned relative path — do not dest.relative_to(output_dir):
        # macOS /tmp → /private/tmp breaks Path.relative_to on unresolved roots.
        result.written_paths.append(dash_rel)
        entry.outcome = ActionOutcome.APPLIED
        entry.reason = "emit_red_panels_locus"
        entry.loci_used = metric_only
        result.touched_service_ids.append(service.service_id)
        result.quality_touched.setdefault(service.service_id, {})["dashboard_spec"] = {
            "score": 1.0,
            "status": "generated",
            "locus_grounded": True,
        }
        result.manifest_touched.append(
            {
                "type": "dashboard_spec",
                "service": service.service_id,
                "path": f"dashboards/{service.service_id}-dashboard-spec.yaml",
                "status": "generated",
            }
        )
        result.entries.append(entry)
        return

    if "throughput" not in sli and "availability" not in sli:
        entry.outcome = ActionOutcome.APPLIED_NO_CHANGE
        entry.reason = f"sli_kinds_no_red:{sorted(sli) if sli else []}"
        entry.content_hash_after = entry.content_hash_before
        result.entries.append(entry)
        return

    art = generate_dashboard_spec(service, business, descriptor)
    art = repair_and_validate(art, business, transport=service.transport)
    after = art.content or ""
    entry.content_hash_after = content_hash(after) if after else None
    if art.status != "generated" or not after:
        entry.outcome = ActionOutcome.SKIPPED
        entry.reason = art.error_message or "dashboard_not_generated"
        result.entries.append(entry)
        return

    already_complete = False
    if before:
        try:
            already_complete = yaml.safe_load(before) == yaml.safe_load(after)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "YAML compare failed for emit_red service=%s: %s",
                service.service_id,
                exc,
                exc_info=True,
            )
            already_complete = False
    if already_complete:
        entry.outcome = ActionOutcome.APPLIED_NO_CHANGE
        entry.reason = "red_already_complete"
        entry.content_hash_after = entry.content_hash_before
        result.entries.append(entry)
        return

    path = _write_one(output_dir, art)
    if path:
        result.written_paths.append(path)
    entry.outcome = ActionOutcome.APPLIED
    entry.reason = "emit_red_panels"
    result.touched_service_ids.append(service.service_id)
    result.quality_touched.setdefault(service.service_id, {})[
        "dashboard_spec"
    ] = _artifact_quality_block(art)
    result.manifest_touched.append(
        {
            "type": art.artifact_type,
            "service": art.service_id,
            "path": art.output_path,
            "status": art.status,
            "quality_score": (art.quality or {}).get("score"),
        }
    )
    result.entries.append(entry)


def _apply_improve_coverage(
    entry: ActionPlanEntry,
    *,
    service: Any,
    output_dir: Path,
    result: ApplyResult,
) -> None:
    """Bind ≥1 PromQL panel to a cited metric family (FR-G4) — no second scorer."""
    loci = list(entry.loci_used or [])
    metric_only = [
        l
        for l in loci
        if str(l.get("signal_kind") or signal_kind_for(str(l.get("family_or_signal") or "")))
        == "metric"
    ]
    if not metric_only:
        entry.outcome = ActionOutcome.SKIPPED
        entry.reason = "no_deterministic_lever"
        entry.locus_skip_reason = "no_metric_loci"
        result.entries.append(entry)
        return

    family = str(metric_only[0].get("family_or_signal") or "")
    dash_rel = f"dashboards/{service.service_id}-dashboard-spec.yaml"
    dash_path = output_dir / dash_rel
    before = dash_path.read_text(encoding="utf-8") if dash_path.is_file() else ""
    entry.content_hash_before = content_hash(before) if before else None

    panel = {
        "type": "timeseries",
        "title": f"Coverage bind: {family}",
        "expr": f"sum(rate({family}[$__rate_interval]))",
        "unit": "ops",
        "group": "Coverage",
    }
    if before:
        try:
            doc = yaml.safe_load(before) or {}
        except Exception:  # noqa: BLE001
            doc = {}
    else:
        doc = {
            "apiVersion": "grafana.observability/v1alpha1",
            "kind": "DashboardSpec",
            "metadata": {"name": f"{service.service_id}-coverage"},
            "spec": {"title": f"{service.service_id} coverage", "panels": []},
        }
    if not isinstance(doc, dict):
        doc = {}
    spec = doc.setdefault("spec", {})
    if not isinstance(spec, dict):
        spec = {}
        doc["spec"] = spec
    panels = spec.setdefault("panels", [])
    if not isinstance(panels, list):
        panels = []
        spec["panels"] = panels
    # Idempotent: skip if family already referenced
    already = any(family in str(p.get("expr") or "") for p in panels if isinstance(p, dict))
    if already:
        entry.outcome = ActionOutcome.APPLIED_NO_CHANGE
        entry.reason = "coverage_family_already_bound"
        entry.content_hash_after = entry.content_hash_before
        entry.loci_used = metric_only[:1]
        result.entries.append(entry)
        return
    panels.append(panel)
    after = yaml.safe_dump(doc, sort_keys=False)
    entry.content_hash_after = content_hash(after)
    dest = _confined_dest(output_dir, dash_rel)
    if dest is None:
        entry.outcome = ActionOutcome.SKIPPED
        entry.reason = "path_escape"
        result.entries.append(entry)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(after, encoding="utf-8")
    result.written_paths.append(dash_rel)
    entry.outcome = ActionOutcome.APPLIED
    entry.reason = "improve_metric_coverage_locus_bind"
    entry.loci_used = metric_only[:1]
    result.touched_service_ids.append(service.service_id)
    result.quality_touched.setdefault(service.service_id, {})["dashboard_spec"] = {
        "score": 1.0,
        "status": "generated",
        "locus_grounded": True,
        "coverage_family": family,
    }
    result.manifest_touched.append(
        {
            "type": "dashboard_spec",
            "service": service.service_id,
            "path": dash_rel,
            "status": "generated",
        }
    )
    result.entries.append(entry)


def _apply_complete_triplet(
    entry: ActionPlanEntry,
    *,
    service: Any,
    business: Any,
    descriptor: Any,
    output_dir: Path,
    result: ApplyResult,
    generate_alert_rules: Any,
    generate_dashboard_spec: Any,
    generate_slo_definitions: Any,
    generate_declared_base_slos: Any,
    repair_and_validate: Any,
) -> None:
    """Apply ``gen.complete_triplet`` for one service."""
    legs, leg_reason = _triplet_legs_needed(output_dir, service.service_id)
    entry.legs = list(legs)
    entry.reason = leg_reason
    if not legs:
        entry.outcome = ActionOutcome.APPLIED_NO_CHANGE
        result.entries.append(entry)
        return

    gens = {
        "alert_rule": lambda: generate_alert_rules(service, business, descriptor),
        "dashboard_spec": lambda: generate_dashboard_spec(
            service, business, descriptor
        ),
        "slo_definition": lambda: generate_slo_definitions(
            service, business, descriptor
        ),
    }
    wrote_any = False
    for leg in legs:
        art = gens[leg]()
        art = repair_and_validate(art, business, transport=service.transport)
        if art.status == "generated" and art.content:
            path = _write_one(output_dir, art)
            if path:
                result.written_paths.append(path)
                wrote_any = True
            result.quality_touched.setdefault(service.service_id, {})[
                leg
            ] = _artifact_quality_block(art)
            result.manifest_touched.append(
                {
                    "type": art.artifact_type,
                    "service": art.service_id,
                    "path": art.output_path,
                    "status": art.status,
                    "quality_score": (art.quality or {}).get("score"),
                }
            )
            if leg == "slo_definition":
                try:
                    decl = generate_declared_base_slos(
                        service, business, descriptor
                    )
                    decl = repair_and_validate(
                        decl, business, transport=service.transport
                    )
                    if decl.status == "generated" and decl.content:
                        p = _write_one(output_dir, decl)
                        if p:
                            result.written_paths.append(p)
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "declared_base_slos failed for %s", service.service_id
                    )
        else:
            logger.warning(
                "triplet leg %s for %s not generated: %s",
                leg,
                service.service_id,
                getattr(art, "error_message", None),
            )
    if wrote_any:
        result.touched_service_ids.append(service.service_id)
        entry.outcome = ActionOutcome.APPLIED
    else:
        entry.outcome = ActionOutcome.APPLIED_NO_CHANGE
    result.entries.append(entry)


def apply_affordance_actions(
    plan: PlanResult,
    *,
    services: Sequence[Any],
    business: Any,
    output_dir: Path,
    descriptors: Optional[Mapping[str, Any]] = None,
    contracts: Optional[Mapping[str, Any]] = None,
    max_lines: Optional[int] = None,
    render_fn: Optional[RenderFn] = None,
) -> ApplyResult:
    """Apply live plan actions; advisory remain planner skips."""
    from startd8.observability.artifact_generator import _repair_and_validate
    from startd8.observability.artifact_generator_generators import (
        _service_sli_kinds,
        generate_alert_rules,
        generate_dashboard_spec,
        generate_declared_base_slos,
        generate_slo_definitions,
    )
    from startd8.observability.metric_descriptor import resolve_descriptor

    by_id = {s.service_id: s for s in services}
    desc_map: Dict[str, Any] = dict(descriptors or {})
    result = ApplyResult(entries=[])
    result.entries.extend(plan.skips)

    for action in plan.actions:
        entry = ActionPlanEntry(
            service_id=action.service_id,
            affordance_id=action.affordance_id,
            artifact_types=list(action.artifact_types),
            reason=action.reason,
            gap_code=action.gap_code,
            confidence=action.confidence,
            legs=action.legs,
            outcome=ActionOutcome.PLANNED,
            loci_used=list(action.loci_used) if action.loci_used else None,
            locus_status=action.locus_status,
            locus_skip_reason=action.locus_skip_reason,
        )
        service = by_id.get(action.service_id)
        if service is None:
            entry.outcome = ActionOutcome.SKIPPED
            entry.reason = f"unknown_element_id:{action.service_id!r}"
            result.entries.append(entry)
            continue

        if action.service_id not in desc_map:
            desc_map[action.service_id] = resolve_descriptor(
                profile=getattr(service, "metric_profile", None) or None,
                kinds=getattr(service, "kinds", None),
                transport=getattr(service, "transport", "http") or "http",
                overrides=getattr(service, "descriptor_overrides", None),
            )
        descriptor = desc_map[action.service_id]

        if action.affordance_id == GEN_SHRINK:
            _apply_shrink(
                entry,
                service=service,
                business=business,
                descriptor=descriptor,
                output_dir=output_dir,
                result=result,
                contracts=contracts,
                max_lines=max_lines,
                render_fn=render_fn,
                generate_dashboard_spec=generate_dashboard_spec,
                repair_and_validate=_repair_and_validate,
            )
            continue

        if action.affordance_id == GEN_EMIT_RED:
            _apply_emit_red(
                entry,
                service=service,
                business=business,
                descriptor=descriptor,
                output_dir=output_dir,
                result=result,
                generate_dashboard_spec=generate_dashboard_spec,
                repair_and_validate=_repair_and_validate,
                service_sli_kinds=_service_sli_kinds,
            )
            continue

        if action.affordance_id == GEN_IMPROVE_COVERAGE:
            _apply_improve_coverage(
                entry,
                service=service,
                output_dir=output_dir,
                result=result,
            )
            continue

        if action.affordance_id == GEN_COMPLETE_TRIPLET:
            _apply_complete_triplet(
                entry,
                service=service,
                business=business,
                descriptor=descriptor,
                output_dir=output_dir,
                result=result,
                generate_alert_rules=generate_alert_rules,
                generate_dashboard_spec=generate_dashboard_spec,
                generate_slo_definitions=generate_slo_definitions,
                generate_declared_base_slos=generate_declared_base_slos,
                repair_and_validate=_repair_and_validate,
            )
            continue

        if action.affordance_id == GEN_ENRICH_RUNBOOK:
            _apply_enrich_runbook(
                entry,
                service=service,
                business=business,
                output_dir=output_dir,
                result=result,
            )
            continue

        entry.outcome = ActionOutcome.SKIPPED
        entry.reason = f"unhandled_affordance:{action.affordance_id}"
        result.entries.append(entry)

    result.touched_service_ids = sorted(set(result.touched_service_ids))
    return result



def merge_and_write_reports(
    output_dir: Path,
    apply: ApplyResult,
) -> None:
    """Merge touched quality/manifest rows into prior files on disk."""
    # Gate on real upserts — touched_service_ids alone used to wipe sibling
    # manifest rows when quality/manifest payloads were empty.
    if not apply.quality_touched and not apply.manifest_touched:
        return

    qpath = output_dir / "observability-quality.json"
    prior_q = load_json_file(qpath) or {"services": {}, "aggregate": {}}
    # Fold quality_touched into per-service composite shells
    touched_services: Dict[str, Any] = {}
    for svc_id, legs in apply.quality_touched.items():
        block = dict((prior_q.get("services") or {}).get(svc_id) or {})
        block.update(legs)
        scores = [
            float(v["score"])
            for v in block.values()
            if isinstance(v, dict) and "score" in v
        ]
        if scores:
            block["composite_score"] = round(sum(scores) / len(scores), 4)
        touched_services[svc_id] = block
    merged_q = merge_quality_services(prior_q, touched_services)
    qpath.write_text(json.dumps(merged_q, indent=2) + "\n", encoding="utf-8")

    mpath = output_dir / "observability-manifest.yaml"
    prior_m = load_yaml_file(mpath) or {"artifacts": []}
    merged_m = merge_manifest_artifacts(
        prior_m,
        apply.manifest_touched,
        touched_service_ids=apply.touched_service_ids
        or {a.get("service") for a in apply.manifest_touched if a.get("service")},
    )
    header = (
        "# observability-manifest.yaml\n"
        "# Merged by startd8 affordance-map consume (targeted repair)\n\n"
    )
    mpath.write_text(
        header + yaml.safe_dump(merged_m, sort_keys=False), encoding="utf-8"
    )


def write_apply_actions_report(
    output_dir: Path,
    *,
    load: LoadResult,
    apply: ApplyResult,
) -> Path:
    """Write affordance_actions.json from apply outcomes (FR-B7)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / "affordance_actions.json"
    planned = [
        e for e in apply.entries if e.outcome == ActionOutcome.PLANNED
    ]
    applied = [
        e for e in apply.entries if e.outcome == ActionOutcome.APPLIED
    ]
    no_change = [
        e for e in apply.entries if e.outcome == ActionOutcome.APPLIED_NO_CHANGE
    ]
    skipped = [
        e for e in apply.entries if e.outcome == ActionOutcome.SKIPPED
    ]
    payload = build_affordance_actions_payload(
        load=load,
        planned=planned,
        applied=applied,
        applied_no_change=no_change,
        skipped=skipped,
        dry_run=False,
        written_paths=apply.written_paths,
        all_skipped=bool(apply.entries)
        and not applied
        and not no_change
        and not planned,
    )
    dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return dest


def exit_code_for_apply(load: LoadResult, apply: ApplyResult) -> int:
    """Exit codes after apply (FR-B1)."""
    if load.error:
        return EXIT_MALFORMED
    if not load.entries:
        return EXIT_OK
    applied_like = [
        e
        for e in apply.entries
        if e.outcome
        in (ActionOutcome.APPLIED, ActionOutcome.APPLIED_NO_CHANGE)
    ]
    if applied_like:
        return EXIT_OK
    # Only skips (or empty) after a non-empty map
    if apply.entries:
        return EXIT_ALL_SKIPPED
    return EXIT_OK


__all__ = [
    "EXIT_OK",
    "EXIT_MALFORMED",
    "EXIT_ALL_SKIPPED",
    "KNOWN_GEN_AFFORDANCES",
    "LIVE_GEN",
    "ADVISORY_GEN",
    "UNREACHABLE_GEN",
    "AFFORDANCE_PRIORITY",
    "GEN_EMIT_RED",
    "GEN_COMPLETE_TRIPLET",
    "GEN_SHRINK",
    "GEN_ENRICH_RUNBOOK",
    "ActionOutcome",
    "AffordanceMapEntry",
    "ActionPlanEntry",
    "LoadResult",
    "PlanResult",
    "ApplyResult",
    "AffordanceMapError",
    "normalize_element_id",
    "match_service_id",
    "load_affordance_map",
    "enrich_runbook_markdown",
    "merge_needed_where_into_entries",
    "signal_kind_for",
    "metric_loci",
    "plan_affordance_actions",
    "exit_code_for_plan",
    "exit_code_for_apply",
    "format_plan_for_dry_run",
    "content_hash",
    "collect_source_provenance",
    "SIDECAR_REQUIRED_KEYS",
    "build_affordance_actions_payload",
    "write_affordance_actions_report",
    "write_apply_actions_report",
    "apply_affordance_actions",
    "shrink_dashboard_lines",
    "ShrinkResult",
    "resolve_dashboard_max_lines",
    "try_render_grafana_json",
    "line_count",
    "RenderFn",
    "merge_and_write_reports",
    "merge_quality_services",
    "merge_manifest_artifacts",
    "load_json_file",
    "load_yaml_file",
]
