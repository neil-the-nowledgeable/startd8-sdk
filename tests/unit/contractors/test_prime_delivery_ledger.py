"""Tests for prime → delivery-ledger projection (REQ-PRIME-DELIVERY-LEDGER)."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from startd8.contractors.prime_delivery_ledger import (
    default_output_path,
    emit_delivery_ledger,
    main,
)

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "prime_delivery_ledger"


def _git_project(tmp_path: Path) -> tuple[Path, str]:
    """Copy fixture sources into a real git repo; return (root, merge_sha)."""
    root = tmp_path / "project"
    shutil.copytree(FIXTURE / "generated", root)
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "fixture@example.com"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "fixture"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "fixture generated sources"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return root, sha


def test_emit_builds_work_items_and_content_addressed_evidence(tmp_path: Path):
    root, sha = _git_project(tmp_path)
    out = tmp_path / "delivery-ledger.yaml"
    result = emit_delivery_ledger(
        postmortem=FIXTURE / "prime-postmortem-report.json",
        traceability=FIXTURE / "ingestion-traceability.json",
        project_root=root,
        merge_sha=sha,
        output_path=out,
    )
    assert out.is_file()
    assert result.work_item_count == 3
    assert result.evidence_count == 3
    delivery = result.ledger["delivery"]
    by_id = {w["id"]: w for w in delivery["work_items"]}
    assert set(by_id) == {"PI-001a", "PI-001b", "PI-001c"}
    # auto-satisfied REQ-CDP-INT-001 must not appear
    all_satisfies = {s for w in delivery["work_items"] for s in w["satisfies"]}
    assert "REQ-CDP-INT-001" not in all_satisfies
    assert "FR-11" in by_id["PI-001a"]["satisfies"]

    evidence = {e["id"]: e for e in delivery["evidence"]}
    wizard = next(e for e in evidence.values() if e["locator"].endswith(":app/wizard.py"))
    blob = subprocess.run(
        ["git", "cat-file", "blob", f"{sha}:app/wizard.py"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    assert wizard["sha256"] == hashlib.sha256(blob).hexdigest()
    assert wizard["locator"] == f"git:{sha}:app/wizard.py"
    assert wizard["id"] in by_id["PI-001c"]["evidence"]

    # Reconciler-shaped load
    doc = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert doc["delivery"]["evidence"] and doc["delivery"]["work_items"]


def test_unknown_merge_sha_skips_evidence_without_inventing_locators(tmp_path: Path):
    root, _ = _git_project(tmp_path)
    result = emit_delivery_ledger(
        postmortem=FIXTURE / "prime-postmortem-report.json",
        traceability=FIXTURE / "ingestion-traceability.json",
        project_root=root,
        merge_sha="unknown",
        output_path=tmp_path / "skip-ledger.yaml",
    )
    assert result.evidence_count == 0
    assert result.work_item_count == 3
    assert any("merge_sha" in s.reason for s in result.skips)
    for e in result.ledger["delivery"]["evidence"]:
        assert False, f"invented evidence: {e}"


def test_disk_pass_alone_does_not_create_evidence_without_blob(tmp_path: Path):
    """FR-3: PASS / disk_quality must not mint evidence when blob absent."""
    root = tmp_path / "empty-git"
    root.mkdir()
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "fixture@example.com"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "fixture"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    (root / "README").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "README"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "empty"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    result = emit_delivery_ledger(
        postmortem=FIXTURE / "prime-postmortem-report.json",
        traceability=FIXTURE / "ingestion-traceability.json",
        project_root=root,
        merge_sha=sha,
        output_path=tmp_path / "no-blob.yaml",
    )
    assert result.evidence_count == 0
    assert any("blob missing" in s.reason for s in result.skips)


def test_refuses_to_overwrite_dossier_yaml(tmp_path: Path):
    root, sha = _git_project(tmp_path)
    with pytest.raises(ValueError, match="dossier.yaml"):
        emit_delivery_ledger(
            postmortem=FIXTURE / "prime-postmortem-report.json",
            traceability=FIXTURE / "ingestion-traceability.json",
            project_root=root,
            merge_sha=sha,
            output_path=tmp_path / "dossier.yaml",
        )


def test_default_output_path_and_cli(tmp_path: Path):
    root, sha = _git_project(tmp_path)
    assert default_output_path(root) == root / ".startd8" / "delivery-ledger.yaml"
    rc = main(
        [
            "--postmortem",
            str(FIXTURE / "prime-postmortem-report.json"),
            "--traceability",
            str(FIXTURE / "ingestion-traceability.json"),
            "--project-root",
            str(root),
            "--merge-sha",
            sha,
        ]
    )
    assert rc == 0
    assert (root / ".startd8" / "delivery-ledger.yaml").is_file()


def test_reconciler_dry_run_fr_missing_lives(tmp_path: Path):
    """Iter-2 dogfood: stub Book A → fr-missing-lives proves Book B loadable."""
    import sys

    root, sha = _git_project(tmp_path)
    ledger = tmp_path / "delivery-ledger.yaml"
    emit_delivery_ledger(
        postmortem=FIXTURE / "prime-postmortem-report.json",
        traceability=FIXTURE / "ingestion-traceability.json",
        project_root=root,
        merge_sha=sha,
        output_path=ledger,
    )
    stub_req = tmp_path / "REQ-stub.md"
    stub_req.write_text(
        """# Requirements: Fixture Stub

**Project:** fixture   **Criticality:** low
**Version:** 0.1.0   **Date:** 2026-08-14
**Format:** det-req/0.1
**Backend:** spike-component

## Overview
Stub book A — FR ids only, no Lives.

## Objectives
- O-1: Prove ledger loads.

## Risks
| Type | Description | Mitigation | Priority |
|---|---|---|---|
| quality | none | n/a | low |

## Profile
Declared profile: **internal**

## Functional requirements
- **FR-11 — Wizard done.** Touches: X. Verify: y. Serves: O-1
- **FR-6 — Wizard step.** Touches: X. Verify: y. Serves: O-1
- **FR-8 — Wizard py.** Touches: X. Verify: y. Serves: O-1

## Non-goals
- Lives fuel.

## Owned fields
Only humans enter: nothing.

## Contract projection
- **Backend:** spike-component
""",
        encoding="utf-8",
    )
    sys.path.insert(0, str(Path("/Users/neilyashinsky/Documents/dev/dev-os/scripts")))
    from reconcile_lives_evidence import reconcile

    report = reconcile(stub_req, ledger, root)
    assert report["schema"].startswith("dev-os.lives-evidence-reconcile/")
    statuses = {
        m["requirement_id"]: m["status"] for m in report["requirement_mappings"]
    }
    assert statuses.get("FR-11") == "fr-missing-lives"
    assert statuses.get("FR-6") == "fr-missing-lives"
    assert statuses.get("FR-8") == "fr-missing-lives"


def test_reconciler_agree_when_lives_match_emitted_locators(tmp_path: Path):
    """Iter-2 altitude 2: fueled Book A → at least one agree (FR-6)."""
    import sys

    root, sha = _git_project(tmp_path)
    ledger = tmp_path / "delivery-ledger.yaml"
    result = emit_delivery_ledger(
        postmortem=FIXTURE / "prime-postmortem-report.json",
        traceability=FIXTURE / "ingestion-traceability.json",
        project_root=root,
        merge_sha=sha,
        output_path=ledger,
    )
    by_path = {
        e["locator"].split(":", 2)[-1]: e for e in result.ledger["delivery"]["evidence"]
    }
    done = by_path["app/templates/wizard/done.html"]
    step = by_path["app/templates/wizard/step.html"]
    wizard = by_path["app/wizard.py"]

    fueled = tmp_path / "REQ-fueled.md"
    fueled.write_text(
        f"""# Requirements: Fixture Fueled

**Project:** fixture   **Criticality:** low
**Version:** 0.1.0   **Date:** 2026-08-14
**Format:** det-req/0.1
**Backend:** spike-component

## Overview
Book A with Lives matching emitted evidence.

## Objectives
- O-1: Agree.

## Risks
| Type | Description | Mitigation | Priority |
|---|---|---|---|
| quality | none | n/a | low |

## Profile
Declared profile: **internal**

## Functional requirements
- **FR-11 — Wizard done.** Touches: X. Lives: code {done["locator"]}. Verify: y. Serves: O-1
- **FR-6 — Wizard step.** Touches: X. Lives: code {step["locator"]}. Verify: y. Serves: O-1
- **FR-8 — Wizard py.** Touches: X. Lives: code {wizard["locator"]}. Verify: y. Serves: O-1

## Non-goals
- Sync conductor.

## Owned fields
Only humans enter: Lives.

## Contract projection
- **Backend:** spike-component
""",
        encoding="utf-8",
    )
    sys.path.insert(0, str(Path("/Users/neilyashinsky/Documents/dev/dev-os/scripts")))
    from reconcile_lives_evidence import reconcile

    report = reconcile(fueled, ledger, root)
    statuses = {
        m["requirement_id"]: m["status"] for m in report["requirement_mappings"]
    }
    assert statuses.get("FR-11") == "agree"
    assert statuses.get("FR-6") == "agree"
    assert statuses.get("FR-8") == "agree"


def test_postmortem_hook_emits_when_merge_sha_supplied(tmp_path: Path):
    """Iter-1 optional hook: _write_outputs emits ledger only with merge_sha."""
    from startd8.contractors.prime_postmortem import PrimePostMortemEvaluator

    root, sha = _git_project(tmp_path)
    out = tmp_path / "pipeline-out"
    out.mkdir()
    # Minimal postmortem already on disk (hook reads these paths)
    import json
    import shutil

    shutil.copy(FIXTURE / "prime-postmortem-report.json", out / "prime-postmortem-report.json")
    shutil.copy(FIXTURE / "ingestion-traceability.json", out / "ingestion-traceability.json")

    ev = PrimePostMortemEvaluator()
    ev._project_root = str(root)
    ev._result_dict = {}
    ev._maybe_emit_delivery_ledger(str(out))
    assert not (root / ".startd8" / "delivery-ledger.yaml").exists()

    ev._result_dict = {"delivery_merge_sha": sha}
    ev._maybe_emit_delivery_ledger(str(out))
    ledger = root / ".startd8" / "delivery-ledger.yaml"
    assert ledger.is_file()
    doc = yaml.safe_load(ledger.read_text(encoding="utf-8"))
    assert len(doc["delivery"]["evidence"]) == 3
