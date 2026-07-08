#!/usr/bin/env python3
"""Phase 2 M4 pilot — exercise the REAL stakeholder-run endpoint end-to-end (bounded live spend).

Bounds: cap=1 persona, Haiku (default, cheapest), a $1 DAILY blocking budget as a hard backstop.
Validates: dry-run (no spend) → confirm (real spend, run_key echoed) → transcript persists → the run
does NOT touch kickoff inputs → status endpoint. Throwaway temp project (no writes to household).

Run under doppler so ANTHROPIC_API_KEY is injected:
  doppler run -p startd8 -c dev -- env PYTHONPATH=src .venv/bin/python docs/design/kickoff-portal/pilot/run_m4_pilot.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "src")

from starlette.testclient import TestClient

from startd8.costs.budget import BudgetManager
from startd8.costs.store import CostStore
from startd8.kickoff_experience.stakeholder_run import ensure_daily_ceiling
from startd8.kickoff_experience.stakeholder_run_server import RunServerConfig, build_stakeholder_run_app
from startd8.stakeholder_panel.models import PROTOCOL_VERSION

TOKEN = "pilot-token"
HDR = {"Authorization": f"Bearer {TOKEN}"}


def _write_roster(root: Path) -> None:
    inputs = root / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    roster = {
        "protocol_version": PROTOCOL_VERSION,
        "domain": "stakeholders",
        "provenance_default": "authored",
        "personas": [
            {
                "role_id": "budget-owner",
                "display_name": "Household Budget Owner",
                "goals": ["keep every bill paid before its due date", "avoid all late fees"],
                "constraints": ["fixed monthly income"],
                "answers_for": ["business-targets"],
            },
            {
                "role_id": "caregiver",
                "display_name": "Household Caregiver",
                "goals": ["never miss a medication refill"],
                "answers_for": ["observability"],
            },
        ],
    }
    import yaml

    (inputs / "stakeholders.yaml").write_text(yaml.safe_dump(roster, sort_keys=False))


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="m4-pilot-"))
    print(f"pilot project: {root}")
    _write_roster(root)

    # Fail-closed: a $1 DAILY blocking budget (the hard spend backstop).
    manager = BudgetManager(CostStore(root / ".startd8" / "costs.db"))
    ensure_daily_ceiling(manager, limit_usd=1.0)

    cfg = RunServerConfig(project_root=root, token=TOKEN, model="anthropic:claude-haiku-4-5-20251001",
                          budget_manager=manager)  # panel_factory=None → REAL LLM
    client = TestClient(build_stakeholder_run_app(cfg))

    question = "In one sentence, what is the single most important thing to get right?"

    # 1. dry-run — NO spend
    dr = client.post("/stakeholders/run", json={"question": question, "cap": 1, "dry_run": True}, headers=HDR)
    print(f"\n[1] dry-run  HTTP {dr.status_code}: {json.dumps(dr.json())}")
    assert dr.status_code == 200, dr.text
    run_key = dr.json()["run_key"]

    # 2. confirm — REAL spend (cap=1, Haiku), run_key echoed
    print(f"\n[2] confirm  (cap=1, Haiku, run_key={run_key[:8]}…) — spending…")
    cr = client.post("/stakeholders/run", json={"question": question, "cap": 1, "run_key": run_key}, headers=HDR)
    print(f"    HTTP {cr.status_code}")
    assert cr.status_code == 200, cr.text
    body = cr.json()
    print(f"    status={body['status']} session={body['session_id']}")
    for a in body["answers"]:
        print(f"    • {a['role_id']} ({a['grounding']}): {a['text'][:200]}")

    # 3. status endpoint
    st = client.get(f"/stakeholders/run/{body['session_id']}", headers=HDR)
    print(f"\n[3] status   HTTP {st.status_code}: count={st.json().get('count')}")

    # 4. idempotent replay — same run_key → deduped, NOT re-charged
    rep = client.post("/stakeholders/run", json={"question": question, "cap": 1, "run_key": run_key}, headers=HDR)
    print(f"\n[4] replay   status={rep.json().get('status')} (expect 'deduped' — no second charge)")

    # 5. invariants
    transcript = list((root / ".startd8" / "stakeholder-panel").glob("*.json"))
    kickoff_inputs = list((root / "docs" / "kickoff" / "inputs").glob("*.yaml"))
    print("\n[5] invariants:")
    print(f"    transcript persisted: {len(transcript)} file(s)")
    print(f"    kickoff inputs present: {[p.name for p in kickoff_inputs]} (only the roster we wrote — run did NOT create inputs)")
    print(f"\nPILOT PROJECT (inspect / rm): {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
