# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""CLI wiring tests for `startd8 requirements` (backlog #8) — elicit/synthesize/review/approve/init-roster.

Exercises the Typer commands end to end against a temp project (no LLM — the `$0` baseline path only),
including the new `--target` lifecycle guard (FR-RP-6 elicit-half, R2-S4).
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from startd8.cli_requirements import requirements_app

runner = CliRunner()

SCHEMA = "model User { id String @id\n name String\n}\nmodel Order { id String @id\n userId String\n}"


def _project(tmp_path: Path) -> Path:
    (tmp_path / "prisma").mkdir(parents=True, exist_ok=True)
    (tmp_path / "prisma" / "schema.prisma").write_text(SCHEMA, encoding="utf-8")
    return tmp_path


def _session_id(project: Path) -> str:
    d = project / ".startd8" / "requirements-panel" / "candidates"
    files = list(d.glob("candidates-*.json"))
    assert files, "elicit did not stage a session"
    return files[0].name[len("candidates-") : -len(".json")]


# ── init-roster ───────────────────────────────────────────────────────────────


def test_cli_init_roster_writes_then_refuses(tmp_path):
    proj = _project(tmp_path)
    r1 = runner.invoke(requirements_app, ["init-roster", "--project", str(proj)])
    assert r1.exit_code == 0
    assert (proj / "docs" / "kickoff" / "inputs" / "stakeholders.yaml").is_file()
    r2 = runner.invoke(requirements_app, ["init-roster", "--project", str(proj)])
    assert r2.exit_code == 5  # _EXIT_CLOBBER
    assert "already exists" in r2.stdout


# ── elicit ($0 baseline) → synthesize → review ───────────────────────────────


def test_cli_elicit_baseline_synthesize_review(tmp_path):
    proj = _project(tmp_path)
    e = runner.invoke(requirements_app, ["elicit", "--project", str(proj)])
    assert e.exit_code == 0
    assert "baseline stubs: 2" in e.stdout
    sid = _session_id(proj)

    s = runner.invoke(
        requirements_app, ["synthesize", "--project", str(proj), "--session", sid]
    )
    assert s.exit_code == 0
    assert "synthesized 2 FRs" in s.stdout

    v = runner.invoke(
        requirements_app, ["review", "--project", str(proj), "--session", sid]
    )
    assert v.exit_code == 0
    # review shows the literal doc, out-of-band provenance, advisory coverage, and the blocking gate
    assert "## Requirements" in v.stdout
    assert "coverage:" in v.stdout
    assert "readiness: BLOCKED" in v.stdout  # baseline stubs are unowned


# ── approve: readiness-blocked, then a clean doc writes + refuses regeneration ─


def test_cli_approve_blocked_on_unowned_baseline(tmp_path):
    proj = _project(tmp_path)
    runner.invoke(requirements_app, ["elicit", "--project", str(proj)])
    sid = _session_id(proj)
    out = proj / "REQ.md"
    r = runner.invoke(
        requirements_app,
        ["approve", str(out), "--project", str(proj), "--session", sid],
    )
    assert r.exit_code == 6  # _EXIT_BLOCKED (unowned <needs-owner> stubs)
    assert not out.exists()


def test_cli_approve_writes_then_refuses_regeneration(tmp_path, monkeypatch):
    # Stage a clean (owned, no-stub) candidate directly so approve can pass the readiness gate.
    proj = _project(tmp_path)
    from startd8.requirements_panel import PROV_ESTIMATE, RequirementCandidate
    from startd8.requirements_panel.store import CandidateStore

    CandidateStore(proj, "elicit-clean").save(
        [
            RequirementCandidate(
                area="security",
                title="RBAC",
                body="The system MUST enforce RBAC.",
                role_id="sec",
                provenance=PROV_ESTIMATE,
            )
        ]
    )
    out = proj / "docs" / "REQ.md"
    r1 = runner.invoke(
        requirements_app,
        ["approve", str(out), "--project", str(proj), "--session", "elicit-clean"],
    )
    assert r1.exit_code == 0 and out.is_file()
    first = out.read_bytes()
    r2 = runner.invoke(
        requirements_app,
        ["approve", str(out), "--project", str(proj), "--session", "elicit-clean"],
    )
    assert r2.exit_code == 5  # _EXIT_CLOBBER — never regenerates over an existing doc
    assert out.read_bytes() == first


# ── the new --target lifecycle guard (FR-RP-6 elicit-half, R2-S4) ─────────────


def test_cli_elicit_target_guard_refuses_before_spend(tmp_path):
    proj = _project(tmp_path)
    existing = proj / "docs" / "EXISTING_REQUIREMENTS.md"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("# already here\n", encoding="utf-8")
    r = runner.invoke(
        requirements_app,
        ["elicit", "--project", str(proj), "--target", str(existing)],
    )
    assert r.exit_code == 5  # refused BEFORE staging/spend
    assert "already exists" in r.stdout
    # no session was staged (the guard fired first)
    assert not (proj / ".startd8" / "requirements-panel" / "candidates").exists()


def test_cli_elicit_target_absent_proceeds(tmp_path):
    proj = _project(tmp_path)
    r = runner.invoke(
        requirements_app,
        ["elicit", "--project", str(proj), "--target", str(proj / "NEW.md")],
    )
    assert r.exit_code == 0
    assert "baseline stubs: 2" in r.stdout
