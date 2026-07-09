"""v2 dashboard provisioning (dynamic-dashboards M5, FR-6).

Publishes a v2 board to Grafana with the **version gate** (refuse < 13.1, FR-11/R1-F1) and a **UID
collision guard** (refuse if the UID already belongs to a *different-titled* board — a different project
slugging to the same UID, incl. a classic one; R1-S8/FR-5) in front of an idempotent upsert. The endpoint
is recorded in the result (``provision_api``, R1-F3).

Per the M0 decision matrix (outcome 1, verdict GO): the **legacy** ``POST /api/dashboards/db`` accepts a
v2 payload on 13.1 with full round-trip fidelity and clean ``overwrite`` upsert semantics, so it is the
provision path (the resource API is native but needs resourceVersion juggling for updates). The existing
``GrafanaClient.upsert_dashboard`` is reused unchanged — the classic path is untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .version import version_gate_reason

_LEGACY_PROVISION_API = "/api/dashboards/db"


@dataclass
class V2ProvisionResult:
    """Outcome of a v2 provision. ``skipped_reason`` set ⇒ nothing was published (fail-loud, not broken)."""

    success: bool
    uid: str
    provision_api: Optional[str] = None
    skipped_reason: Optional[str] = None
    error: Optional[str] = None


def provision_v2(
    client: Any,
    board: Dict[str, Any],
    *,
    force: bool = False,
) -> V2ProvisionResult:
    """Version-gate + collision-guard + idempotent upsert a v2 ``board`` via ``client``.

    ``client`` is a ``GrafanaClient`` (duck-typed: ``check_version``/``get_dashboard``/``upsert_dashboard``).
    Returns a :class:`V2ProvisionResult`; never raises for a gate/collision/API failure — it degrades to a
    ``skipped_reason``/``error`` so the caller decides how loud to be (mirrors the classic portal path).
    ``force=True`` overrides the UID-collision guard.
    """
    uid = (board.get("metadata") or {}).get("name")
    if not uid:
        return V2ProvisionResult(
            False, uid="", skipped_reason="v2 board has no metadata.name"
        )

    # 1. Version gate (FR-11 / R1-F1) — minor-aware; refuse a target that can't render v2.
    vr = client.check_version()
    version_str = (getattr(vr, "data", None) or {}).get("version", "")
    if not getattr(vr, "success", False):
        return V2ProvisionResult(
            False,
            uid=uid,
            skipped_reason=f"cannot verify Grafana version: {getattr(vr, 'error', '?')}",
        )
    reason = version_gate_reason(version_str)
    if reason:
        return V2ProvisionResult(False, uid=uid, skipped_reason=reason)

    # 2. UID collision guard (R1-S8 + FR-5) — refuse if the UID already belongs to a *different* board
    #    (a different project slugging to the same UID, incl. a classic board). Idempotency: our OWN board
    #    (same title) re-provisions cleanly. Title comparison is used, not a schema sniff, because the
    #    legacy GET returns a classic-shaped representation even for a v2-stored board (so `apiVersion`
    #    absence is NOT a reliable "classic" signal — that caused a false self-collision).
    our_title = (board.get("spec") or {}).get("title")
    existing = client.get_dashboard(uid)
    if getattr(existing, "success", False) and isinstance(
        getattr(existing, "data", None), dict
    ):
        stored = existing.data.get("dashboard") or {}
        existing_title = stored.get("title") if isinstance(stored, dict) else None
        if existing_title and our_title and existing_title != our_title and not force:
            return V2ProvisionResult(
                False,
                uid=uid,
                skipped_reason=(
                    f"UID {uid!r} already belongs to a different dashboard {existing_title!r} — refusing "
                    "to overwrite it (rename the project/board, or pass force=True to override)"
                ),
            )

    # 3. Idempotent upsert via the legacy endpoint (M0 outcome 1 — accepts v2 with fidelity).
    resp = client.upsert_dashboard(board)
    if not getattr(resp, "success", False):
        return V2ProvisionResult(
            False,
            uid=uid,
            provision_api=_LEGACY_PROVISION_API,
            error=getattr(resp, "error", "upsert failed"),
        )
    return V2ProvisionResult(True, uid=uid, provision_api=_LEGACY_PROVISION_API)
