"""Inc 6 — engine end-to-end tests over run-012/013-shaped fixtures (FR-8/9/10/11/12)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from startd8.repair.retry.engine import RepairRetryEngine


def _report(ingestion: Path, features: list) -> Path:
    (ingestion).mkdir(parents=True, exist_ok=True)
    p = ingestion / "prime-postmortem-report.json"
    p.write_text(json.dumps({"features": features}), encoding="utf-8")
    return p


def _unres_issue(abs_path: str, specifier: str) -> dict:
    return {"category": "unresolvable_import", "severity": "error",
            "message": f"`{abs_path}` imports `{specifier}` which resolves to neither the generated batch nor an on-disk project file"}


@pytest.fixture
def run012(tmp_path):
    """A run-012-shaped tree: 1 rewrite (#4) + 3 cofile + 1 barrel."""
    ing = tmp_path / "plan-ingestion"
    gen = ing / "generated"
    (gen / "components" / "wizard" / "steps").mkdir(parents=True)
    (gen / "components" / "wizard" / "types.ts").write_text("export type W = {}\n")
    files = {
        "components/wizard/StepNav.tsx": "import s from './StepNav.module.css'\n",
        "components/ModeToggle.tsx": "import s from './ModeToggle.module.css'\n",
        "components/wizard/steps/ProofPointStep.tsx": (
            "export default function ProofPointStep(){return null}\n"
            "import s from './ProofPointStep.module.css'\n"
        ),
        "components/wizard/steps/EnrichStep.tsx": (
            "export default function EnrichStep(){return null}\n"
            "import { W } from '../../../types/wizard'\n"
        ),
        "components/wizard/WizardShell.tsx": "import { EnrichStep } from '@/components/wizard/steps'\n",
    }
    for rel, content in files.items():
        (gen / rel).write_text(content)
    g = str(gen) + "/"
    feats = [
        {"feature_id": "PI-007", "success": False, "disk_compliance": {
            "file_path": g + "components/wizard/StepNav.tsx",
            "semantic_issues": [_unres_issue(g + "components/wizard/StepNav.tsx", "./StepNav.module.css")]}},
        {"feature_id": "PI-005", "success": False, "disk_compliance": {
            "file_path": g + "components/ModeToggle.tsx",
            "semantic_issues": [_unres_issue(g + "components/ModeToggle.tsx", "./ModeToggle.module.css")]}},
        {"feature_id": "PI-011", "success": False, "disk_compliance": {
            "file_path": g + "components/wizard/steps/ProofPointStep.tsx",
            "semantic_issues": [_unres_issue(g + "components/wizard/steps/ProofPointStep.tsx", "./ProofPointStep.module.css")]}},
        {"feature_id": "PI-012", "success": False, "disk_compliance": {
            "file_path": g + "components/wizard/steps/EnrichStep.tsx",
            "semantic_issues": [_unres_issue(g + "components/wizard/steps/EnrichStep.tsx", "../../../types/wizard")]}},
        {"feature_id": "PI-008", "success": False, "disk_compliance": {
            "file_path": g + "components/wizard/WizardShell.tsx",
            "semantic_issues": [_unres_issue(g + "components/wizard/WizardShell.tsx", "@/components/wizard/steps")]}},
    ]
    _report(ing, feats)
    return ing


def test_run012_full_repair_with_scaffold(run012):
    rep = RepairRetryEngine(run012).run(scaffold=True)
    assert rep.rewritten == 1
    assert rep.scaffolded == 4  # 3 css + 1 barrel
    assert rep.needs_regen == 0
    assert rep.rolled_back == 0
    assert rep.resolution == "5/5 resolved"
    # the rewrite landed on disk:
    enrich = (run012 / "generated" / "components" / "wizard" / "steps" / "EnrichStep.tsx").read_text()
    assert "from '@/components/wizard/types'" in enrich
    # scaffolds exist:
    assert (run012 / "generated" / "components" / "wizard" / "StepNav.module.css").exists()
    assert (run012 / "generated" / "components" / "wizard" / "steps" / "index.ts").exists()


def test_run012_artifacts_written_under_run_dir(run012):
    rep = RepairRetryEngine(run012).run(scaffold=True)
    assert rep.report_path.parent == (run012 / "repair-retry").resolve()
    assert rep.report_path.is_file() and rep.worklist_path.is_file()
    data = json.loads(rep.report_path.read_text())
    assert "would_pass" not in data  # R1-S3
    assert json.loads(rep.worklist_path.read_text())["worklist"] == []  # all fixed


def test_no_scaffold_only_rewrites_then_worklists_assets(run012):
    rep = RepairRetryEngine(run012).run(scaffold=False)
    assert rep.rewritten == 1
    assert rep.scaffolded == 0
    # the 3 css + 1 barrel become residue (not silently passed)
    assert len(rep.worklist) >= 4
    assert any(w.get("reason") == "scaffold_disabled" for w in rep.worklist)


def test_second_pass_is_a_fixpoint(run012):
    """R4-S1: re-running over the repaired tree marks all already_resolved, exit-clean."""
    RepairRetryEngine(run012).run(scaffold=True)
    rep2 = RepairRetryEngine(run012).run(scaffold=True)
    assert rep2.already_resolved == 5
    assert rep2.rewritten == 0 and rep2.scaffolded == 0
    assert rep2.worklist == []
    assert rep2.resolution == "5/5 resolved"
