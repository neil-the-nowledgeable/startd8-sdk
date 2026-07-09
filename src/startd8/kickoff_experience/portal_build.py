"""Shared Digital Project Workbook build+provision helper (FR-1/FR-10).

ONE path for both `startd8 kickoff portal` and `kickoff instantiate --portal`, so the two entry points
cannot drift. Deterministic ($0) generation via the startd8-mixin jsonnet pipeline; provisioning is
opt-in. The helper never raises for an absent/broken toolchain or a provision failure — it returns a
:class:`PortalResult` with a ``skipped_reason`` so callers can degrade non-fatally (FR-6/FR-7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from ..logging_config import get_logger
from .portal_spec import (
    INDEX_UID,
    WorkbookSlugError,
    build_kickoff_portal_spec,
    build_workbook_index_spec,
    workbook_uid,
)

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


# --------------------------------------------------------------------------- toolchain gate (FR-6)


def _toolchain_reason() -> Optional[str]:
    """Return None if the jsonnet toolchain is available, else a concise, actionable skip reason."""
    try:
        from ..dashboard_creator.discovery import detect_toolchain

        detect_toolchain()
        return None
    except Exception:  # ConfigurationError (absent) — degrade, never raise (FR-6a)
        return (
            "no jsonnet toolchain — install jsonnet or `pip install gojsonnet`, "
            "then run `startd8 kickoff portal`"
        )


# --------------------------------------------------------------------------- best-effort loaders


def _load_panel_run(
    project_root: Path, session_id: Optional[str] = None
) -> Optional[List[dict]]:
    """Latest (or a specific) stakeholder-panel run's answers for the Workbook. None on any absence."""
    try:
        from ..stakeholder_panel.transcript import TranscriptStore

        if session_id:
            return [
                a.to_dict() for a in TranscriptStore(project_root, session_id).load()
            ] or None
        tdir = project_root / ".startd8" / "stakeholder-panel"
        if not tdir.is_dir():
            return None
        sessions = sorted(
            (p for p in tdir.glob("*.json") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not sessions:
            return None
        return [
            a.to_dict() for a in TranscriptStore(project_root, sessions[0].stem).load()
        ] or None
    except (
        Exception
    ):  # pragma: no cover - never let transcript loading break the portal
        return None


def _load_pipeline_state(project_root: Path) -> Optional[dict]:
    """Assemble the panel→bridge→VIPP funnel for the Workbook (best-effort, $0). None if no activity."""
    try:
        staged: List[dict] = []
        pdir = project_root / ".startd8" / "stakeholder-panel" / "proposals"
        if pdir.is_dir():
            from ..stakeholder_panel.proposals import ProposalStore

            for f in sorted(pdir.glob("proposals-*.json")):
                sid = f.stem[len("proposals-") :]
                staged.extend(
                    r.to_dict() for r in ProposalStore(project_root, sid).load()
                )

        inbox: Dict[str, Any] = {"present": False}
        inbox_path = project_root / ".startd8" / "vipp" / "proposals-inbox.json"
        if inbox_path.is_file() and not inbox_path.is_symlink():
            from ..vipp.models import ProposalEnvelope

            env = ProposalEnvelope.from_json(inbox_path.read_text(encoding="utf-8"))
            inbox = {
                "present": True,
                "count": len(env.proposals),
                "envelope_seq": env.envelope_seq,
            }

        dispositions: Dict[str, Any] = {"present": False}
        disp_path = project_root / ".startd8" / "vipp" / "dispositions.json"
        if disp_path.is_file() and not disp_path.is_symlink():
            from ..vipp.models import VippReport

            rep = VippReport.from_json(disp_path.read_text(encoding="utf-8"))
            dispositions = {
                "present": True,
                "counts": rep.counts(),
                "evidence_available": rep.evidence_available,
                "items": [
                    {
                        "proposal_id": d.proposal_id,
                        "decision": getattr(d.decision, "value", str(d.decision)),
                        "reason": d.reason,
                    }
                    for d in rep.dispositions
                ],
                "advisories": list(rep.panel_advisories or []),
            }
        if not staged and not inbox["present"] and not dispositions["present"]:
            return None
        return {"staged": staged, "inbox": inbox, "dispositions": dispositions}
    except Exception:  # pragma: no cover - never let pipeline loading break the portal
        return None


def _roster(project_root: Path) -> Any:
    try:
        from ..stakeholder_panel import load_roster

        rp = project_root / "docs" / "kickoff" / "inputs" / "stakeholders.yaml"
        return load_roster(rp) if rp.is_file() else None
    except Exception:  # pragma: no cover
        return None


# --------------------------------------------------------------------------- generation


def _provision_collision_reason(
    provision_url: str, uid: str, title: str
) -> Optional[str]:
    """FR-5 provision-time collision guard: return a refusal reason if ``uid`` already belongs to a
    DIFFERENT project on the target Grafana, else None. Best-effort — a check that cannot run (network,
    auth) does not block; the provision itself surfaces real connectivity/auth errors. Only a positive
    hit (a same-UID board with a *different* title) refuses, so two distinct projects that slugify to
    the same UID never silently clobber each other on a shared instance.
    """
    try:
        from ..dashboard_creator.grafana_client import GrafanaClient

        client = GrafanaClient(
            provision_url, allow_insecure=provision_url.startswith("http://")
        )
        resp = client.get_dashboard(uid)
    except (
        Exception
    ):  # pragma: no cover - can't check → don't block (provision surfaces real errors)
        return None
    if getattr(resp, "success", False):
        existing = ((resp.data or {}).get("dashboard") or {}).get("title", "")
        if existing and existing != title:
            return (
                f"UID {uid} already belongs to {existing!r} on {provision_url} — refusing to overwrite "
                f"a different project's Workbook (FR-5). Rename this project or its board."
            )
    return None


def _run_workflow(
    spec: Dict[str, Any], out_dir: Path, provision_url: Optional[str]
) -> Any:
    from ..dashboard_creator.workflow import DashboardCreatorWorkflow

    config: Dict[str, Any] = {"spec": spec, "output_dir": str(out_dir)}
    if provision_url:
        config.update(
            provision=True,
            grafana_url=provision_url,
            allow_insecure=provision_url.startswith("http://"),
        )
    return DashboardCreatorWorkflow().run(config)


def _persist(
    result: Any, provision_url: Optional[str], summary: Dict[str, Any]
) -> PortalResult:
    """Turn a workflow result into a PortalResult; a compile/provision failure degrades (FR-6b/FR-7)."""
    if not getattr(result, "success", False):
        reason = (
            f"generation failed: {getattr(result, 'error', None) or 'unknown error'}"
        )
        logger.warning("Workbook %s", reason)
        return PortalResult(
            uid=summary.get("uid", ""), summary=summary, skipped_reason=reason
        )
    output = result.output if isinstance(result.output, dict) else {}
    json_path = output.get("json_path")
    # NB: the dashboard JSON is written by DashboardCreatorWorkflow (a derived artifact under
    # .startd8/dashboards/, NOT the kickoff source-of-record). This module performs no direct
    # filesystem write itself — it must not (FR-GE-13 guided-experience write-audit).
    summary = {
        **summary,
        "json_path": json_path,
        "dashboard_url": output.get("dashboard_url"),
        "provisioned": bool(provision_url),
    }
    return PortalResult(
        uid=summary.get("uid", ""),
        json_path=json_path,
        provisioned_url=output.get("dashboard_url"),
        summary=summary,
    )


def build_and_maybe_provision(
    project_root: Path,
    project: Optional[str] = None,
    *,
    out_dir: Optional[Path] = None,
    provision_url: Optional[str] = None,
    session: Optional[str] = None,
) -> PortalResult:
    """Build the project's Workbook dashboard JSON (optionally provision). Never raises (FR-6/FR-7).

    Returns a :class:`PortalResult`. A missing kickoff package, absent/broken toolchain, slug collision,
    or compile/provision failure all degrade to ``skipped_reason`` — the caller decides how loud to be.
    """
    root = Path(project_root).expanduser()
    name = project or root.resolve().name

    try:
        uid = workbook_uid(name)
    except WorkbookSlugError as exc:  # FR-5 reserved/empty slug
        logger.warning("Workbook slug rejected: %s", exc)
        return PortalResult(skipped_reason=str(exc))

    if (reason := _toolchain_reason()) is not None:
        return PortalResult(uid=uid, skipped_reason=reason)

    # FR-4: the Workbook is generated from the moment the kickoff PACKAGE exists, even before any
    # authoring — a fresh project yields an empty *skeleton* board (0 fields) that fills in as the human
    # authors + confirms. We skip only when there is no kickoff package at all (nothing to show).
    if not (root / "docs" / "kickoff").is_dir():
        return PortalResult(
            uid=uid,
            skipped_reason="no kickoff package — run `startd8 kickoff instantiate` first",
        )

    try:
        from .docs import live_schema_text, load_kickoff_docs
        from .state import build_kickoff_state

        docs = load_kickoff_docs(
            root
        )  # may be empty pre-authoring → an empty skeleton board (FR-4)
        state = build_kickoff_state(docs, live_schema_text=live_schema_text(root))
        spec = build_kickoff_portal_spec(
            state,
            name,
            roster=_roster(root),
            panel_results=_load_panel_run(root, session_id=session),
            pipeline=_load_pipeline_state(root),
        )
        dest = (
            Path(out_dir).expanduser()
            if out_dir
            else (root / ".startd8" / "dashboards")
        )
        ac = state.attention_counts
        summary = {
            "schema": "kickoff.portal.v1",
            "uid": spec["uid"],
            "panels": len(spec["panels"]),
            "fields": len(state.fields),
            "confirmed": ac.get("ok", 0),
            "gaps": ac.get("blocked", 0),
        }
        # FR-5: before pushing to a shared Grafana, refuse if this UID already belongs to a *different*
        # project (two names slugging to the same UID) — never silently clobber. Disk-only gen can't
        # collide (each project owns its own file), so the guard is provision-path only.
        if provision_url and (
            reason := _provision_collision_reason(
                provision_url, spec["uid"], spec["title"]
            )
        ):
            return PortalResult(uid=uid, summary=summary, skipped_reason=reason)
        result = _run_workflow(spec, dest, provision_url)
    except (
        Exception
    ) as exc:  # broken toolchain / unexpected — degrade, never propagate (FR-6b/FR-7)
        logger.warning("Workbook generation failed: %s", exc)
        return PortalResult(uid=uid, skipped_reason=f"generation failed: {exc}")

    return _persist(result, provision_url, summary)


# ------------------------------------------------- dynamic (v2) Workbook — dynamic-dashboards M6/CLI
# The audience-personalized v2 dynamic board (`kickoff portal --dynamic`). Additive + SEPARATE from the
# classic path above (its own `-v2` UID; coexists, R2-F5): pure-Python v2 emit (no jsonnet toolchain
# needed), then optional provision via `provision_v2` (version-gated + collision-guarded).


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
        from .docs import live_schema_text, load_kickoff_docs
        from .state import build_kickoff_state

        docs = load_kickoff_docs(root)  # empty pre-authoring → skeleton board (FR-4)
        state = build_kickoff_state(docs, live_schema_text=live_schema_text(root))
        audience = resolve_audience_preference(root).value
        provenance = load_ledger(root)
        board = build_workbook_v2(state, name, audience=audience, provenance=provenance)

        dest = (
            Path(out_dir).expanduser()
            if out_dir
            else (root / ".startd8" / "dashboards")
        )
        pres = persist_v2_dashboard(board, output_dir=dest)
        summary: Dict[str, Any] = {
            "schema": "kickoff.portal.v2",
            "uid": uid,
            "dynamic": True,
            "audience": audience.value,
            "fields": len(state.fields),
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
    if (reason := _toolchain_reason()) is not None:
        return PortalResult(uid=INDEX_UID, skipped_reason=reason)
    try:
        spec = build_workbook_index_spec()
        dest = (
            Path(out_dir).expanduser()
            if out_dir
            else (root / ".startd8" / "dashboards")
        )
        result = _run_workflow(spec, dest, provision_url)
    except Exception as exc:  # pragma: no cover - degrade
        logger.warning("Workbook index generation failed: %s", exc)
        return PortalResult(uid=INDEX_UID, skipped_reason=f"generation failed: {exc}")
    return _persist(
        result, provision_url, {"schema": "kickoff.portal-index.v1", "uid": INDEX_UID}
    )
