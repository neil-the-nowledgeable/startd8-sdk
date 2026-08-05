"""Single source of truth for RED-panel classification (RED = Rate / Errors / Duration).

Per ``docs/design/observability/RED_TAXONOMY_UNIFICATION_REQUIREMENTS.md`` (v0.4),
"what RED role does this panel play?" is answered ONCE here and every consumer derives
its question from that one classification, instead of the ~5 divergent substring
heuristics that used to drift and silently disagree.

Two orthogonal axes, previously tangled into every copy, are separated here:
  - **RED ROLE** of a panel — :class:`RedRole` ``{RATE, ERROR, DURATION, NONE}``.
  - **the QUESTION** asked — *covered?* (scoring), *present?* (generation),
    *protected?* (shrink) — all thin derivations over :func:`classify_red_role`.

The classifier has two tiers:
  - **descriptor-grounded** (preferred): keys on the resolved ``MetricDescriptor``'s
    REAL identities (``throughput_metric`` / ``error_selector`` /
    ``latency_bucket_metric``), never a ``_count`` / ``_total`` suffix guess — correct
    for the four ``_total``-throughput profiles by construction (FR-2), and null-safe on
    empty identities (FR-4a: ``"" in expr`` is always True, so empty is a NON-match).
  - **descriptor-free fallback** (``descriptor=None``): the union of the today-correct
    title/expr heuristics, for arbitrary on-disk dashboards the SDK did not generate
    (G4). The one place DURATION is unified to the stricter rule (B3): a duration/latency
    signal is required, never a bare ``histogram_quantile`` over a non-latency bucket.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, List, Mapping, Optional, Sequence


class RedRole(str, Enum):
    """The RED role a panel plays (FR-1). ``str``-valued for transparent serialization."""

    RATE = "rate"          # R — throughput
    ERROR = "error"        # E — errors / availability ratio
    DURATION = "duration"  # D — latency / duration
    NONE = "none"          # not a RED panel


#: The canonical RED triple — the single set the coverage math keys on (FR-1).
RED_ROLES = frozenset({RedRole.RATE, RedRole.ERROR, RedRole.DURATION})


# ---------------------------------------------------------------------------
# Panel expr/title extraction (targets-aware — D3)
# ---------------------------------------------------------------------------

def _panel_title(panel: Mapping[str, Any]) -> str:
    return str(panel.get("title") or "").strip().lower()


def _panel_exprs(panel: Mapping[str, Any]) -> List[str]:
    """All PromQL exprs a panel carries — ``expr`` AND every ``targets[].expr`` (D3)."""
    out: List[str] = []
    if panel.get("expr"):
        out.append(str(panel["expr"]))
    for t in panel.get("targets", []) or []:
        if isinstance(t, Mapping) and t.get("expr"):
            out.append(str(t["expr"]))
    return out


def _panel_has_expr(panel: Mapping[str, Any]) -> bool:
    return bool(_panel_exprs(panel))


# ---------------------------------------------------------------------------
# Descriptor-free tier — the union of the today-correct title/expr heuristics.
# DURATION is the one unified-to-stricter rule (B3): a duration/latency signal is
# required, never a bare histogram_quantile.  RATE / ERROR replicate the shipped
# broad `has_rate_panel` / `has_error_panel` exactly (byte-parity for the scorer).
# ---------------------------------------------------------------------------

_RATE_TITLES = ("request rate", "rate")
_ERROR_TITLES = ("error rate", "errors", "error")
_DURATION_TITLES = ("duration", "latency")


def _freeform_is_rate(panel: Mapping[str, Any]) -> bool:
    title = _panel_title(panel)
    if (title in _RATE_TITLES or title.endswith(" request rate")) and _panel_has_expr(panel):
        return True
    for expr in _panel_exprs(panel):
        e = expr.lower()
        if "rate(" not in e:
            continue
        if any(tok in e for tok in ("error", "failure", "fail", "status_code")):
            continue
        if "status" in e:
            continue
        if "_count" in e or "_total" in e:
            return True
    return False


def _freeform_is_error(panel: Mapping[str, Any]) -> bool:
    title = _panel_title(panel)
    if (title in _ERROR_TITLES or "error rate" in title) and _panel_has_expr(panel):
        return True
    for expr in _panel_exprs(panel):
        e = expr.lower()
        if any(
            tok in e
            for tok in ("error", "failure", "fail", "status_code", 'status_code!="ok"', "status!=")
        ):
            return True
    return False


def _freeform_is_duration(panel: Mapping[str, Any]) -> bool:
    title = _panel_title(panel)
    if (title in _DURATION_TITLES or "duration" in title or "latency" in title) and _panel_has_expr(panel):
        return True
    for expr in _panel_exprs(panel):
        e = expr.lower()
        # Stricter/unified DURATION (B3): a genuine duration/latency signal — NOT a
        # bare histogram_quantile over an arbitrary (e.g. size) bucket.
        if "duration" in e or "latency" in e or "delay_seconds" in e:
            return True
    return False


# ---------------------------------------------------------------------------
# Descriptor-grounded tier — keys on the descriptor's REAL identities.
# ---------------------------------------------------------------------------

def _references(exprs: Sequence[str], needle: str) -> bool:
    """True iff ``needle`` is non-empty AND a substring of some expr (FR-4a null-safe)."""
    if not needle:
        return False
    n = needle.lower()
    return any(n in e.lower() for e in exprs)


def _grounded_is_duration(panel: Mapping[str, Any], lb: str) -> bool:
    if _references(_panel_exprs(panel), lb):
        return True
    # Summary / name-scoped subjects (empty lb — harbor-core-http): title only, never a
    # false `"" in expr` bucket match (FR-4a).
    title = _panel_title(panel)
    return _panel_has_expr(panel) and (
        title in _DURATION_TITLES or "duration" in title or "latency" in title
    )


def _grounded_is_error(panel: Mapping[str, Any], es: str) -> bool:
    if _references(_panel_exprs(panel), es):
        return True
    title = _panel_title(panel)
    return _panel_has_expr(panel) and (title in _ERROR_TITLES or "error rate" in title)


def _grounded_is_rate(panel: Mapping[str, Any], tm: str, es: str) -> bool:
    exprs = _panel_exprs(panel)
    # References the real throughput series and is NOT the error ratio (which carries
    # the error_selector). FR-2a: a sibling _total/_count that is NOT tm never matches.
    if _references(exprs, tm) and not _references(exprs, es):
        return True
    title = _panel_title(panel)
    return _panel_has_expr(panel) and (title in _RATE_TITLES or title.endswith(" request rate"))


def _role_membership(
    panel: Mapping[str, Any], role: RedRole, descriptor: Optional[Any]
) -> bool:
    """Independent per-role predicate — a panel MAY satisfy more than one role (e.g. a
    rate panel over ``rpc_server_duration_count`` is both RATE and, by name, DURATION),
    exactly as the scorer's separate ``has_*_panel`` calls do. Coverage/presence key on
    this; :func:`classify_red_role` collapses it to one role for generation/dedup."""
    if descriptor is not None:
        if role is RedRole.DURATION:
            return _grounded_is_duration(panel, getattr(descriptor, "latency_bucket_metric", "") or "")
        if role is RedRole.ERROR:
            return _grounded_is_error(panel, getattr(descriptor, "error_selector", "") or "")
        if role is RedRole.RATE:
            return _grounded_is_rate(
                panel,
                getattr(descriptor, "throughput_metric", "") or "",
                getattr(descriptor, "error_selector", "") or "",
            )
        return False
    if role is RedRole.DURATION:
        return _freeform_is_duration(panel)
    if role is RedRole.ERROR:
        return _freeform_is_error(panel)
    if role is RedRole.RATE:
        return _freeform_is_rate(panel)
    return False


def classify_red_role(
    panel: Mapping[str, Any],
    descriptor: Optional[Any] = None,
) -> RedRole:
    """The one RED-role classifier (FR-2/3/4) — EXCLUSIVE single role, priority-ordered
    (DURATION > ERROR > RATE) so an error-ratio or duration panel is never mis-read as
    RATE. Used for generation/synthesis (one panel → one synthesized role) and, via
    ``!= NONE``, shrink protection. Coverage uses :func:`red_roles_present` (independent
    membership) instead — a panel can count toward multiple roles there.

    Descriptor-grounded when ``descriptor`` is provided (keys on the real metric
    identities, FR-4a null-safe), else the descriptor-free title/expr fallback. Reads
    the panel's full expr set (D3).
    """
    for role in (RedRole.DURATION, RedRole.ERROR, RedRole.RATE):
        if _role_membership(panel, role, descriptor):
            return role
    return RedRole.NONE


# ---------------------------------------------------------------------------
# The three derived questions (FR — coverage / presence / protection).
# ---------------------------------------------------------------------------

def red_roles_present(
    panels: Sequence[Mapping[str, Any]],
    descriptor: Optional[Any] = None,
) -> "frozenset[RedRole]":
    """The set of RED roles present across ``panels`` — **independent** membership: a
    single panel may contribute more than one role (matching the scorer's separate
    ``has_rate/has_error/has_duration`` calls), so this is NOT ``{classify(p)}``."""
    present = set()
    for p in panels:
        for role in RED_ROLES:
            if role not in present and _role_membership(p, role, descriptor):
                present.add(role)
    return frozenset(present)


def red_coverage(
    panels: Sequence[Mapping[str, Any]],
    descriptor: Optional[Any] = None,
) -> float:
    """RED coverage as a fraction of the {RATE, ERROR, DURATION} triple (scoring)."""
    return len(red_roles_present(panels, descriptor) & RED_ROLES) / 3.0


def has_red_role(
    role: RedRole,
    panels: Sequence[Mapping[str, Any]],
    descriptor: Optional[Any] = None,
) -> bool:
    """Is ``role`` already present (generation "present?" gate)."""
    return role in red_roles_present(panels, descriptor)


def is_red_protected(
    panel: Mapping[str, Any],
    descriptor: Optional[Any] = None,
) -> bool:
    """Would dropping this panel lose a RED role (shrink "protected?" gate).

    FR-7 precondition: the scored-⟺-protected invariant holds only when the scorer
    and the shrink path evaluate the SAME tier (both descriptor-free today). A
    mixed-tier call site voids it — callers must pass the same ``descriptor`` to both
    :func:`red_coverage` and this function.
    """
    return classify_red_role(panel, descriptor) is not RedRole.NONE


# ---------------------------------------------------------------------------
# The one deduping synthesizer (FR-9/FR-10).
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RedPanel:
    """A RED panel to synthesize, identified by ``(role, metric_identity)`` for dedup."""

    role: RedRole
    metric_identity: str
    title: str
    expr: str
    unit: str
    group: str


def synthesize_red_panels(
    existing: Sequence[Mapping[str, Any]],
    *,
    descriptor: Optional[Any],
    want_roles: "frozenset[RedRole]",
    candidates: Sequence[RedPanel],
) -> List[RedPanel]:
    """Emit at most one panel per wanted RED role, skipping roles already present.

    Dedup key = ``(RedRole, metric_identity)`` (FR-9/FR-10): a role already present in
    ``existing`` is skipped, and two candidates sharing a ``(role, metric_identity)``
    collapse to one — the structural kill for the double-emit (B2) and the
    two-writers case, regardless of whether the candidate came from the descriptor
    path or the locus path.
    """
    present = red_roles_present(existing, descriptor)
    out: List[RedPanel] = []
    seen: set = set()
    for c in candidates:
        if c.role not in want_roles or c.role in RED_ROLES and c.role in present:
            continue
        key = (c.role, c.metric_identity)
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out
