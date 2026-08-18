"""REQ-prime-project-generation-ledger — I1–I3 pins (FR-1 identity, FR-2 registry, FR-3 auto-derive).

The load-bearing test (FR-3) reproduces the portal-v2 row from its REAL copied manifests — the
concrete first cell the /reflective-instantiation loop realized.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from startd8.contractors import generation_ledger as gl
from startd8.contractors.batch_postmortem import resolve_project_identity

pytestmark = pytest.mark.unit

_FIXTURE = Path(__file__).parent / "fixtures" / "portal_v2"


def _install_portal_v2(tmp_path: Path) -> Path:
    """Copy the real portal-v2 manifests into a project root named ``portal-v2`` (so dir-name identity
    resolves), returning the root."""
    root = tmp_path / "portal-v2"
    shutil.copytree(_FIXTURE, root)
    return root


def _mini_project(root: Path, *, cost: float, run_id: str, batch_id: str) -> Path:
    """A minimal second Prime-generated project (one paid feature) for the cross-project index test."""
    (root / ".startd8").mkdir(parents=True)
    (root / ".cap-dev-pipe" / "pipeline-output").mkdir(parents=True)
    (root / ".startd8" / "generation-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.1.0",
                "generated_at": "2026-08-14T10:00:00+00:00",
                "features": {
                    "F-1": {
                        "name": "thing",
                        "success": True,
                        "cost_usd": cost,
                        "model": "claude-sonnet-4-6",
                        "provider": "anthropic",
                    }
                },
                "total_cost_usd": cost,
                "total_input_tokens": 10,
                "total_output_tokens": 5,
                "total_model_time_ms": 100.0,
            }
        ),
        encoding="utf-8",
    )
    (root / ".cap-dev-pipe" / "pipeline-output" / "batch-ledger.json").write_text(
        json.dumps(
            {
                "batch_id": batch_id,
                "seed_path": "s.json",
                "seed_checksum": batch_id[-6:],
                "total_tasks": 1,
                "created_at": "",
                "updated_at": "",
                "tasks": {},
                "runs": [
                    {
                        "run_id": run_id,
                        "timestamp": "2026-08-14T10:00:00+00:00",
                        "tasks_attempted": 1,
                        "tasks_passed": 1,
                        "tasks_failed": 0,
                        "cumulative_passed": 1,
                        "remaining": 0,
                        "force_regenerated_count": 0,
                        "cost_usd": cost,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return root


# ── FR-3: auto-derive reproduces the portal-v2 row exactly ─────────────────────────────────────────


def test_fr3_reproduces_portal_v2_row(tmp_path):
    root = _install_portal_v2(tmp_path)
    home = str(tmp_path / "home")
    ledger = gl.record_run(str(root), home=home)

    assert ledger.project_id == "portal-v2"
    cum = ledger.cumulative()
    assert cum["total_cost_usd"] == 2.9375809999999993
    assert cum["features_passed"] == 16
    assert cum["features_total_in_batch"] == 21
    assert cum["status"] == "IN_PROGRESS"

    run = ledger.batches[0]["runs"][0]
    assert run["run_id"] == "portal-v2-preview"
    assert ledger.batches[0]["batch_id"] == "batch-4e94a4edc329"
    assert run["features_attempted"] == 16 and run["features_failed"] == 0
    assert run["remaining_in_batch"] == 5 and run["verdict"] == "PASS"
    assert run["model_mix"] == {"claude-sonnet-4-6": 5, "startd8-coder": 11}
    assert round(run["cost_by_provider"]["anthropic"], 6) == 2.937581
    assert run["cost_by_provider"]["ollama"] == 0.0
    # 10 non-null artifact paths (+ delivery_ledger reserved null)
    non_null = {k: v for k, v in run["artifacts"].items() if v is not None}
    assert len(non_null) == 10 and run["artifacts"]["delivery_ledger"] is None


def test_fr3_persists_project_file_and_index(tmp_path):
    root = _install_portal_v2(tmp_path)
    home = str(tmp_path / "home")
    gl.record_run(str(root), home=home)

    pfile = gl.project_ledger_path("portal-v2", home)
    idx = gl.index_path(home)
    assert pfile.is_file() and idx.is_file()
    data = json.loads(pfile.read_text())
    assert data["schema"] == gl.SCHEMA
    assert data["project"]["project_id"] == "portal-v2"
    assert data["trust_model"].startswith("auto-derived")


# ── FR-2: cross-project registry (two projects → two files + one index) ────────────────────────────


def test_fr2_two_projects_yield_two_files_and_one_index(tmp_path):
    home = str(tmp_path / "home")
    gl.record_run(str(_install_portal_v2(tmp_path)), home=home)
    gl.record_run(
        str(
            _mini_project(
                tmp_path / "other-app",
                cost=0.5,
                run_id="other-run",
                batch_id="batch-oth123",
            )
        ),
        home=home,
    )

    projects_dir = gl.ledger_dir(home) / "projects"
    files = sorted(p.name for p in projects_dir.glob("*.json"))
    assert files == ["other-app.json", "portal-v2.json"]

    index = gl.load_index(home)
    ids = sorted(p["project_id"] for p in index.projects)
    assert ids == ["other-app", "portal-v2"]
    pv = next(p for p in index.projects if p["project_id"] == "portal-v2")
    assert pv["cumulative_cost_usd"] == 2.9375809999999993
    assert pv["status"] == "IN_PROGRESS" and pv["features_passed"] == 16


def test_fr2_home_env_override(tmp_path, monkeypatch):
    # $STARTD8_HOME redirects the registry — the test never writes to the real HOME.
    monkeypatch.setenv("STARTD8_HOME", str(tmp_path / "envhome"))
    gl.record_run(str(_install_portal_v2(tmp_path)))
    assert (
        tmp_path / "envhome" / "generation-ledger" / "projects" / "portal-v2.json"
    ).is_file()


def test_record_run_idempotent(tmp_path):
    root = _install_portal_v2(tmp_path)
    home = str(tmp_path / "home")
    gl.record_run(str(root), home=home)
    ledger = gl.record_run(str(root), home=home)  # same run again
    assert (
        len(ledger.batches) == 1 and len(ledger.batches[0]["runs"]) == 1
    )  # no duplicate row


def test_record_run_missing_manifest_raises(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(FileNotFoundError):
        gl.record_run(str(tmp_path / "empty"), home=str(tmp_path / "home"))


# ── FR-1: project identity resolver ────────────────────────────────────────────────────────────────


def test_fr1_identity_from_dir_name(tmp_path):
    root = tmp_path / "my-cool-app"
    root.mkdir()
    pid, ppath = resolve_project_identity(str(root))
    assert pid == "my-cool-app" and ppath == str(root.resolve())


def test_fr1_identity_prefers_project_context_yaml(tmp_path):
    root = tmp_path / "dirname-not-id"
    root.mkdir()
    (root / "project-context.yaml").write_text(
        "spec:\n  project:\n    id: canonical-id\n", encoding="utf-8"
    )
    pid, _ = resolve_project_identity(str(root))
    assert pid == "canonical-id"


# ── I6 (FR-5 helper): find_project_root walks up to the generated project ──────────────────────────


def test_find_project_root_walks_up(tmp_path):
    root = _install_portal_v2(tmp_path)  # has .startd8/generation-manifest.json
    deep = root / ".cap-dev-pipe" / "pipeline-output" / "portal-v2-preview"
    deep.mkdir(parents=True)
    assert gl.find_project_root(str(deep)) == root.resolve()
    assert gl.find_project_root(str(tmp_path / "nowhere")) is None


# ── I4 (FR-6): the liveness oracle — PHANTOM / DRIFT / clean ────────────────────────────────────────


def _complete_artifacts(root: Path, run_id: str) -> None:
    """Materialize every conventional artifact the run row cites, so verify is clean."""
    for rel in [
        ".startd8/prime-postmortem-report.json",
        ".startd8/prime-postmortem-summary.md",
        ".startd8/kaizen-metrics.json",
        ".startd8/forward-manifest.json",
        f".cap-dev-pipe/pipeline-output/{run_id}/run-provenance.json",
        f".cap-dev-pipe/pipeline-output/{run_id}/{run_id}-artifact-manifest.yaml",
        f".cap-dev-pipe/pipeline-output/{run_id}/project-context.yaml",
    ]:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}", encoding="utf-8")


def test_fr6_pristine_project_verifies_clean(tmp_path):
    root = _install_portal_v2(tmp_path)
    _complete_artifacts(root, "portal-v2-preview")
    home = str(tmp_path / "home")
    ledger = gl.record_run(str(root), home=home)
    assert gl.verify_project(ledger) == []


def test_fr6_missing_artifact_is_phantom(tmp_path):
    root = _install_portal_v2(tmp_path)
    _complete_artifacts(root, "portal-v2-preview")
    home = str(tmp_path / "home")
    gl.record_run(str(root), home=home)
    (root / ".startd8" / "kaizen-metrics.json").unlink()  # remove a cited artifact
    findings = gl.verify_project(gl.load_project_ledger("portal-v2", home=home))
    assert any(f.kind == "PHANTOM" and "kaizen_metrics" in f.detail for f in findings)


def test_fr6_edited_cost_is_drift(tmp_path):
    root = _install_portal_v2(tmp_path)
    _complete_artifacts(root, "portal-v2-preview")
    home = str(tmp_path / "home")
    gl.record_run(str(root), home=home)
    # tamper the recorded cost in the persisted ledger → drift vs the manifest
    pfile = gl.project_ledger_path("portal-v2", home)
    data = json.loads(pfile.read_text())
    data["batches"][0]["runs"][0]["cost_usd"] = 999.99
    pfile.write_text(json.dumps(data), encoding="utf-8")
    findings = gl.verify_project(gl.load_project_ledger("portal-v2", home=home))
    assert any(f.kind == "DRIFT" for f in findings)


def test_fr6_verify_all_spans_projects(tmp_path):
    home = str(tmp_path / "home")
    r1 = _install_portal_v2(tmp_path)
    _complete_artifacts(r1, "portal-v2-preview")
    gl.record_run(str(r1), home=home)
    gl.record_run(
        str(
            _mini_project(
                tmp_path / "other-app",
                cost=0.5,
                run_id="other-run",
                batch_id="batch-oth123",
            )
        ),
        home=home,
    )
    # other-app cites artifacts that don't exist → verify_all surfaces its phantoms
    findings = gl.verify_all(home)
    assert any(f.project_id == "other-app" for f in findings)


# ── #4: per-project trends ─────────────────────────────────────────────────────────────────────────


def test_project_trends_computes_slopes():
    led = gl.ProjectGenerationLedger(project_id="p", project_path="/p")
    # run1: cost 2.0, 1/2 local; run2: cost 1.0, 2/2 local — cost falling + local rising (decouple win)
    led.upsert_run(
        {"batch_id": "b1"},
        {
            "run_id": "r1",
            "generated_at": "2026-01-01",
            "cost_usd": 2.0,
            "features_passed": 2,
            "features": [{"cost_usd": 0.0}, {"cost_usd": 2.0}],
        },
    )
    led.upsert_run(
        {"batch_id": "b1"},
        {
            "run_id": "r2",
            "generated_at": "2026-01-02",
            "cost_usd": 1.0,
            "features_passed": 2,
            "features": [{"cost_usd": 0.0}, {"cost_usd": 0.0}],
        },
    )
    t = gl.project_trends(led)
    assert [s["run_id"] for s in t["runs"]] == ["r1", "r2"]  # chronological
    assert t["runs"][0]["local_ratio"] == 0.5 and t["runs"][1]["local_ratio"] == 1.0
    assert t["cost_slope"] < 0  # cost trending down
    assert t["local_ratio_slope"] > 0  # $0-local (micro-prime) trending up


def test_project_trends_single_run_has_no_slope():
    led = gl.ProjectGenerationLedger(project_id="p", project_path="/p")
    led.upsert_run(
        {"batch_id": "b1"},
        {
            "run_id": "r1",
            "generated_at": "2026-01-01",
            "cost_usd": 1.0,
            "features_passed": 1,
            "features": [{"cost_usd": 0.0}],
        },
    )
    t = gl.project_trends(led)
    assert len(t["runs"]) == 1
    assert t["cost_slope"] is None and t["local_ratio_slope"] is None
