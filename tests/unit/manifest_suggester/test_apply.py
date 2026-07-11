# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Accumulation-aware apply seam tests (FR-MS-5/7, R2-S1) + the `startd8 screens` CLI."""

from __future__ import annotations

import yaml
from typer.testing import CliRunner

from startd8.cli_screens import screens_app
from startd8.manifest_suggester import (
    KIND_PAGE,
    KIND_VIEW,
    ScreenCandidate,
    accumulate,
    all_existing_slugs,
    apply_screen,
    baseline_views,
    read_authoring,
)

runner = CliRunner()

SCHEMA = """
model Order { id String @id
 items OrderItem[]
}
model Product { id String @id
 items OrderItem[]
}
model OrderItem { orderId String
 productId String
 order Order @relation(fields:[orderId],references:[id])
 product Product @relation(fields:[productId],references:[id])
 @@id([orderId, productId])
}
"""


def _project(tmp_path):
    # .resolve() so the macOS /tmp -> /private/tmp symlink doesn't trip the safe-write confinement guard.
    proj = tmp_path.resolve()
    (proj / "prisma").mkdir(parents=True, exist_ok=True)
    (proj / "prisma" / "schema.prisma").write_text(SCHEMA, encoding="utf-8")
    return proj


def _views(proj):
    return yaml.safe_load((proj / "prisma" / "views.yaml").read_text())["views"]


def _workspace(name):
    return ScreenCandidate(
        kind=KIND_VIEW,
        name=name,
        prose=f"### view: {name}\n- Kind: workspace\n- Root: Order\n",
        entities_referenced=("Order",),
    )


# ── accumulate() unit ─────────────────────────────────────────────────────────


def _page(name):
    slug = name.lower().replace(" ", "-")
    return ScreenCandidate(
        kind=KIND_PAGE,
        name=name,
        prose=f"## Pages\n\n| Page | Content file |\n| ---- | ---- |\n| {name} | {slug}.md |\n",
    )


def test_accumulate_adds_new_and_skips_duplicate():
    c = _workspace("Ops Console")
    doc, added = accumulate("", c)
    assert added and "### view: Ops Console" in doc
    doc2, added2 = accumulate(doc, c)  # same slug → not added
    assert added2 is False and doc2 == doc


def test_accumulate_merges_pages_into_one_table(tmp_path):
    # Pages share ONE `## Pages` table (extract_pages reads only the first) — accumulation MERGES rows.
    doc, _ = accumulate("", _page("Settings"))
    doc2, added = accumulate(doc, _page("About"))
    assert added
    assert doc2.count("## Pages") == 1  # one table, not two
    assert "| Settings | settings.md |" in doc2 and "| About | about.md |" in doc2
    # a duplicate page slug is not re-added
    doc3, added3 = accumulate(doc2, _page("Settings"))
    assert added3 is False and doc3 == doc2


def test_accumulate_mixes_views_and_pages(tmp_path):
    doc, _ = accumulate("", _workspace("Ops Console"))  # a view
    doc2, _ = accumulate(doc, _page("Settings"))  # a page merges into its own table
    assert "### view: Ops Console" in doc2 and "## Pages" in doc2


# ── apply_screen: first write, then R2-S1 accumulation ───────────────────────


def test_apply_writes_then_accumulates_without_clobber(tmp_path):
    proj = _project(tmp_path)
    r1 = apply_screen(proj, baseline_views(SCHEMA)[0])
    assert r1.applied and (proj / "prisma" / "views.yaml").is_file()
    assert [v["name"] for v in _views(proj)] == ["order_dashboard"]

    r2 = apply_screen(proj, _workspace("Ops Console"))
    assert r2.applied
    # R2-S1: the second approve preserves the first — BOTH views present.
    assert sorted(v["name"] for v in _views(proj)) == ["ops_console", "order_dashboard"]
    assert read_authoring(proj).count("### view:") == 2


def test_apply_pages_accumulate_into_pages_yaml(tmp_path):
    # FR-MS-2 + R2-S1 for pages: two approved pages both land in prisma/pages.yaml.
    proj = _project(tmp_path)
    assert apply_screen(proj, _page("Settings")).applied
    assert apply_screen(proj, _page("About")).applied
    pages = yaml.safe_load((proj / "prisma" / "pages.yaml").read_text())["pages"]
    assert sorted(p["title"] for p in pages) == ["About", "Settings"]


def test_apply_duplicate_is_idempotent(tmp_path):
    proj = _project(tmp_path)
    c = baseline_views(SCHEMA)[0]
    assert apply_screen(proj, c).applied
    again = apply_screen(proj, c)
    assert again.applied is False and again.code == "duplicate"


def test_apply_degrades_cleanly_when_apply_proposal_raises(tmp_path, monkeypatch):
    # A hard failure (e.g. safe-write on a symlinked root) must become a typed refusal, not a crash,
    # and must NOT persist the running authoring doc.
    proj = _project(tmp_path)

    def _boom(*a, **k):
        raise RuntimeError("safe-write refused")

    monkeypatch.setattr("startd8.kickoff_experience.proposals.apply_proposal", _boom)
    r = apply_screen(proj, baseline_views(SCHEMA)[0])
    assert r.applied is False and r.code == "apply_error" and "safe-write" in r.reason
    assert not (proj / "docs" / "kickoff" / "inputs" / "screens-authoring.md").exists()


def test_apply_refuses_to_clobber_hand_authored_manifest(tmp_path):
    proj = _project(tmp_path)
    # a pre-existing, non-suggester views.yaml (no running authoring doc) → first apply must not clobber.
    (proj / "prisma" / "views.yaml").write_text(
        yaml.safe_dump(
            {"views": [{"name": "hand_authored", "kind": "dashboard", "root": "Order"}]}
        ),
        encoding="utf-8",
    )
    r = apply_screen(proj, _workspace("Ops Console"))
    assert r.applied is False and r.code == "would_clobber"
    # the hand-authored file is untouched
    assert [v["name"] for v in _views(proj)] == ["hand_authored"]


def test_all_existing_slugs_reads_running_doc_and_live_manifest(tmp_path):
    proj = _project(tmp_path)
    apply_screen(
        proj, baseline_views(SCHEMA)[0]
    )  # → Order Dashboard in views.yaml + authoring doc
    slugs = all_existing_slugs(proj)
    # slugs are nfkd_kebab-normalized (hyphenated) — consistent across the running doc + live manifest.
    assert "order-dashboard" in slugs


# ── CLI: suggest → review → approve ──────────────────────────────────────────


def _sid(proj):
    d = proj / ".startd8" / "manifest-suggester" / "screens"
    return next(iter(d.glob("screens-*.json"))).name[len("screens-") : -len(".json")]


def test_cli_suggest_review_approve(tmp_path):
    proj = _project(tmp_path)
    s = runner.invoke(screens_app, ["suggest", "--project", str(proj)])
    assert s.exit_code == 0 and "staged 1" in s.stdout
    sid = _sid(proj)

    v = runner.invoke(screens_app, ["review", "--project", str(proj), "--session", sid])
    assert v.exit_code == 0
    assert "### view: Order Dashboard" in v.stdout
    assert "grounding: all staged screens resolve cleanly" in v.stdout

    a = runner.invoke(
        screens_app, ["approve", "--project", str(proj), "--session", sid, "--all"]
    )
    assert a.exit_code == 0 and "1/1 applied" in a.stdout
    assert [v["name"] for v in _views(proj)] == ["order_dashboard"]


def test_cli_suggest_dedupes_already_applied(tmp_path):
    proj = _project(tmp_path)
    # apply the baseline once, then a fresh suggest must dedupe it away (FR-MS-3).
    apply_screen(proj, baseline_views(SCHEMA)[0])
    s = runner.invoke(screens_app, ["suggest", "--project", str(proj)])
    assert s.exit_code == 0
    assert "staged 0 after dedupe" in s.stdout


def test_cli_approve_requires_name_or_all(tmp_path):
    proj = _project(tmp_path)
    runner.invoke(screens_app, ["suggest", "--project", str(proj)])
    sid = _sid(proj)
    r = runner.invoke(
        screens_app, ["approve", "--project", str(proj), "--session", sid]
    )
    assert r.exit_code == 2 and "--name" in r.stdout


def test_cli_reject_drops_staged_screen(tmp_path):
    # FR-MS-7: reject drops a staged screen (never applied) and writes nothing to the app.
    proj = _project(tmp_path)
    runner.invoke(screens_app, ["suggest", "--project", str(proj)])
    sid = _sid(proj)
    r = runner.invoke(
        screens_app,
        [
            "reject",
            "--project",
            str(proj),
            "--session",
            sid,
            "--name",
            "Order Dashboard",
        ],
    )
    assert r.exit_code == 0 and "rejected" in r.stdout
    # the session is now empty; review reports nothing staged; nothing was written to the app
    from startd8.manifest_suggester.store import ScreenCandidateStore

    assert ScreenCandidateStore(proj, sid).load() == []
    assert not (proj / "prisma" / "views.yaml").exists()


def test_cli_reject_unknown_name_errors(tmp_path):
    proj = _project(tmp_path)
    runner.invoke(screens_app, ["suggest", "--project", str(proj)])
    sid = _sid(proj)
    r = runner.invoke(
        screens_app,
        ["reject", "--project", str(proj), "--session", sid, "--name", "Nope"],
    )
    assert r.exit_code == 2 and "no staged screen matches" in r.stdout
