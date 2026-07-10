"""Digital Project Workbook build+provision helper (FR-1/FR-10).

Post-M4 convergence: the Workbook is the pure-Python **v2 cockpit** — ``build_workbook_v2_and_maybe_
provision`` (per project) and ``build_index`` (the portfolio dashlist), both emitting Grafana v2 JSON
with **no jsonnet toolchain**. The classic Era-1 board + its jsonnet compile path were retired. Every
helper degrades to a :class:`PortalResult` with a ``skipped_reason`` rather than raising (FR-6/FR-7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from ..logging_config import get_logger
from .paths import DASHBOARDS, startd8_dir
from .portal_spec import INDEX_UID

logger = get_logger(__name__)


@dataclass
class PortalResult:
    """Outcome of a Workbook generate(+provision). ``skipped_reason`` set ⇒ nothing was generated."""

    uid: str = ""
    json_path: Optional[str] = None
    provisioned_url: Optional[str] = None
    summary: Dict[str, Any] = field(default_factory=dict)
    skipped_reason: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.skipped_reason is None and self.json_path is not None

    def message(self) -> str:
        """The single, entry-point-agnostic human line (FR-10 anti-drift for messaging, CRP R1-S7)."""
        if self.skipped_reason:
            return f"Workbook: skipped — {self.skipped_reason}"
        line = f"Workbook: {self.json_path}"
        if self.provisioned_url:
            line += f"  →  {self.provisioned_url}"
        return line



# ------------------------------------------------- the Digital Project Workbook (v2 cockpit) — default
# The audience-personalized v2 cockpit (`kickoff portal`, default post-M4). Pure-Python v2 emit (no
# jsonnet toolchain), then optional provision via `provision_v2` (version-gated + collision-guarded).


def build_workbook_v2_and_maybe_provision(
    project_root: Path,
    project: Optional[str] = None,
    *,
    out_dir: Optional[Path] = None,
    provision_url: Optional[str] = None,
) -> PortalResult:
    """Generate (and optionally provision) the **v2 dynamic** Workbook. Never raises — degrades to a
    :class:`PortalResult` with a ``skipped_reason`` (mirrors the classic helper)."""
    root = Path(project_root).expanduser()
    name = project or root.resolve().name
    from .portal_spec_v2 import build_workbook_v2, workbook_v2_uid

    uid = workbook_v2_uid(name)
    if not (root / "docs" / "kickoff").is_dir():
        return PortalResult(
            uid=uid,
            skipped_reason="no kickoff package — run `startd8 kickoff instantiate` first",
        )
    try:
        from ..concierge.audience import resolve_audience_preference
        from ..concierge.confirmation import load_ledger
        from ..dashboard_creator.v2 import persist_v2_dashboard, provision_v2
        from .state import resolve_kickoff_state

        # empty pre-authoring → skeleton board (FR-4)
        state = resolve_kickoff_state(root)
        audience = resolve_audience_preference(root).value
        provenance = load_ledger(root)
        # Agentic cockpit read-model (M2): fold the FR-1 session snapshot + VIPP inbox so the
        # Assistant/Proposals tabs mirror the real session. Best-effort — a broken view degrades to
        # honest empty-state tabs (FR-10), never a failed build.
        try:
            from .agentic_view import build_agentic_view

            view = build_agentic_view(root)
        except Exception:  # pragma: no cover - the cockpit view is never load-bearing
            view = None
        board = build_workbook_v2(
            state, name, audience=audience, provenance=provenance, view=view
        )
        # Emit a progress point (readiness/cost/proposals) so the cockpit's burndown accrues over
        # time (roadmap Tier 3). Best-effort — a no-op without a metrics collector.
        try:
            from .metrics import record_from_view

            record_from_view(view, name)
        except Exception:  # pragma: no cover - metrics never break the build
            pass

        dest = (
            Path(out_dir).expanduser()
            if out_dir
            else (startd8_dir(root) / DASHBOARDS)
        )
        pres = persist_v2_dashboard(board, output_dir=dest)
        summary: Dict[str, Any] = {
            "schema": "kickoff.portal.v2",
            "uid": uid,
            "dynamic": True,
            "audience": audience.value,
            "fields": len(state.fields),
            "snapshot": (view.snapshot_status if view is not None else "absent"),
            "proposals": (len(view.proposals) if view is not None else 0),
        }

        provisioned_url: Optional[str] = None
        if provision_url:
            from ..dashboard_creator.grafana_client import GrafanaClient

            client = GrafanaClient(
                provision_url, allow_insecure=provision_url.startswith("http://")
            )
            r = provision_v2(client, board)
            if not r.success:
                return PortalResult(
                    uid=uid,
                    json_path=str(pres.json_path),
                    summary=summary,
                    skipped_reason=r.skipped_reason or r.error,
                )
            provisioned_url = f"{provision_url.rstrip('/')}/d/{uid}"
        return PortalResult(
            uid=uid,
            json_path=str(pres.json_path),
            provisioned_url=provisioned_url,
            summary=summary,
        )
    except (
        Exception
    ) as exc:  # noqa: BLE001 — degrade, never propagate (mirrors the classic path)
        logger.warning("Dynamic Workbook (v2) generation failed: %s", exc)
        return PortalResult(uid=uid, skipped_reason=f"generation failed: {exc}")


# --------------------------------------------------------------------------- portfolio index (FR-11)


def _is_loopback(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "::1", "")


def build_index(
    project_root: Path,
    *,
    out_dir: Optional[Path] = None,
    provision_url: Optional[str] = None,
    confirm_shared: bool = False,
) -> PortalResult:
    """Build the portfolio-index dashboard (FR-11). NR-6: provisioning to a NON-loopback URL requires
    ``confirm_shared=True`` (the index is a global singleton — higher blast radius). Never raises.
    """
    root = Path(project_root).expanduser()
    if provision_url and not _is_loopback(provision_url) and not confirm_shared:
        return PortalResult(
            uid=INDEX_UID,
            skipped_reason=(
                f"index provisioning to a shared instance ({provision_url}) needs explicit confirmation "
                "(--yes) — the portfolio index is global (NR-6)"
            ),
        )
    # Convergence M4: the index is now a pure-Python v2 dashlist (no jsonnet toolchain).
    try:
        from ..dashboard_creator.v2 import persist_v2_dashboard, provision_v2
        from .portal_spec_v2 import build_index_v2

        board = build_index_v2()
        dest = (
            Path(out_dir).expanduser()
            if out_dir
            else (startd8_dir(root) / DASHBOARDS)
        )
        pres = persist_v2_dashboard(board, output_dir=dest)
        summary: Dict[str, Any] = {"schema": "kickoff.portal-index.v2", "uid": INDEX_UID}
        provisioned_url: Optional[str] = None
        if provision_url:
            from ..dashboard_creator.grafana_client import GrafanaClient

            client = GrafanaClient(
                provision_url, allow_insecure=provision_url.startswith("http://")
            )
            r = provision_v2(client, board)
            if not r.success:
                return PortalResult(
                    uid=INDEX_UID,
                    json_path=str(pres.json_path),
                    summary=summary,
                    skipped_reason=r.skipped_reason or r.error,
                )
            provisioned_url = f"{provision_url.rstrip('/')}/d/{INDEX_UID}"
        return PortalResult(
            uid=INDEX_UID,
            json_path=str(pres.json_path),
            provisioned_url=provisioned_url,
            summary=summary,
        )
    except Exception as exc:  # pragma: no cover - degrade
        logger.warning("Workbook index generation failed: %s", exc)
        return PortalResult(uid=INDEX_UID, skipped_reason=f"generation failed: {exc}")
