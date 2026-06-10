"""Deterministic Alembic migration generation — OQ-SCAF-2 fork B (FR-MG-2/3/6).

Diff a previous contract snapshot against the current one and emit additive-only ops
(create_table / add_column), never a drop; each revision embeds the schema it migrates to so the
chain is self-contained (OQ-SCAF-2c).
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from startd8.cli_generate import generate_app
from startd8.migration_codegen import latest_snapshot, next_revision, plan_migration, render_revision

pytestmark = pytest.mark.unit
runner = CliRunner()

_ENUM = "enum Status {\n  active\n  archived\n}\n\n"
V1 = _ENUM + (
    "model Job {\n"
    "  id String @id @default(cuid())\n"
    "  title String\n"
    "  status Status @default(active)\n"
    "}\n"
)
V2 = _ENUM + (
    "model Job {\n"
    "  id String @id @default(cuid())\n"
    "  title String\n"
    "  status Status @default(active)\n"
    "  appliedDate DateTime?\n"                       # new OPTIONAL field
    '  ownerName String @default("local")\n'          # new REQUIRED field WITH @default
    "}\n\n"
    "model Tag {\n"                                    # new MODEL
    "  id String @id @default(cuid())\n"
    "  label String\n"
    "}\n"
)


# --------------------------------------------------------------------------- #
# FR-MG-2 baseline
# --------------------------------------------------------------------------- #

def test_baseline_creates_all_tables():
    plan = plan_migration(V1, None)
    assert plan.is_baseline
    up = "\n".join(plan.upgrade_ops)
    assert "op.create_table(\n        'job'" in up
    assert "sa.Column('title', sa.String(), nullable=False)" in up
    # enum field → String column with a server_default from @default(active)
    assert "sa.Column('status', sa.String(), nullable=False, server_default=sa.text(\"'active'\"))" in up
    assert "op.drop_table('job')" in "\n".join(plan.downgrade_ops)


# --------------------------------------------------------------------------- #
# FR-MG-3 additive delta
# --------------------------------------------------------------------------- #

def test_delta_adds_columns_and_new_table():
    plan = plan_migration(V2, V1)
    assert not plan.is_baseline
    up = "\n".join(plan.upgrade_ops)
    assert "op.add_column('job', sa.Column('appliedDate', sa.DateTime(), nullable=True))" in up
    # required-with-default → NOT NULL add carrying the server_default (valid on existing rows)
    assert "op.add_column('job', sa.Column('ownerName', sa.String(), nullable=False, server_default=sa.text(\"'local'\"))" in up
    assert "op.create_table(\n        'tag'" in up                 # the new model
    down = "\n".join(plan.downgrade_ops)
    assert "op.drop_column('job', 'appliedDate')" in down
    assert "op.drop_table('tag')" in down


def test_required_field_without_default_softened_to_nullable_with_note():
    v3 = V1.replace("  title String\n", "  title String\n  city String\n")  # required, NO @default
    plan = plan_migration(v3, V1)
    up = "\n".join(plan.upgrade_ops)
    assert "op.add_column('job', sa.Column('city', sa.String(), nullable=True))" in up  # softened
    assert any("city: required field added as NULLABLE" in n for n in plan.notes)


def test_removals_and_type_changes_are_noted_never_dropped():
    plan = plan_migration(V1, V2)            # V2 → V1: Tag + two Job fields removed
    assert plan.empty or all("drop" not in op for op in plan.upgrade_ops)  # no destructive upgrade op
    joined = " ".join(plan.notes)
    assert "model Tag: removed from contract — NOT dropped" in joined
    assert "Job.appliedDate: removed from contract — NOT dropped" in joined


def test_no_changes_yields_empty_plan():
    assert plan_migration(V1, V1).empty


# --------------------------------------------------------------------------- #
# FR-MG: self-contained snapshot chain (OQ-SCAF-2c) + revision rendering
# --------------------------------------------------------------------------- #

def test_revision_renders_compiles_and_embeds_snapshot():
    plan = plan_migration(V1, None)
    text = render_revision(revision_id="0001", down_revision=None, message="baseline",
                           plan=plan, current_text=V1)
    compile(text, "<rev>", "exec")                       # valid Python
    assert "# startd8-schema-snapshot:" in text
    assert "revision = '0001'" in text and "down_revision = None" in text


def test_next_revision_chains_and_autodiscovers_previous(tmp_path):
    versions = tmp_path / "versions"
    versions.mkdir()
    # first call → baseline 0001
    fname1, text1, plan1 = next_revision(versions, V1, "baseline")
    assert fname1.startswith("0001_") and plan1.is_baseline
    (versions / fname1).write_text(text1, encoding="utf-8")
    # latest_snapshot reads V1 back out of the embedded snapshot
    prev, seq = latest_snapshot(versions)
    assert seq == 1 and prev == V1
    # second call auto-diffs V2 vs the embedded V1 → delta 0002, down_revision 0001
    fname2, text2, plan2 = next_revision(versions, V2, "add fields")
    assert fname2.startswith("0002_") and not plan2.is_baseline
    assert "down_revision = '0001'" in text2
    (versions / fname2).write_text(text2, encoding="utf-8")
    # third call with no change → nothing to do
    assert next_revision(versions, V2, "noop") is None


# --------------------------------------------------------------------------- #
# FR-MG-6 CLI (`startd8 generate migrate` / `--check`) — operator-applied, never touches a DB
# --------------------------------------------------------------------------- #

def test_cli_migrate_writes_baseline_then_check_is_up_to_date(tmp_path):
    contract = tmp_path / "schema.prisma"
    contract.write_text(V1, encoding="utf-8")
    versions = tmp_path / "alembic" / "versions"

    # --check before anything → pending (baseline), exit 1, writes nothing
    chk = runner.invoke(generate_app, ["migrate", "--contract", str(contract),
                                       "--versions", str(versions), "--check"])
    assert chk.exit_code == 1 and "pending" in chk.output
    assert not versions.exists() or not any(versions.glob("*.py"))

    # write the baseline
    res = runner.invoke(generate_app, ["migrate", "--contract", str(contract),
                                       "--versions", str(versions), "-m", "baseline"])
    assert res.exit_code == 0, res.output
    assert any(versions.glob("0001_*.py"))

    # --check again → up to date (the snapshot matches), exit 0
    chk2 = runner.invoke(generate_app, ["migrate", "--contract", str(contract),
                                        "--versions", str(versions), "--check"])
    assert chk2.exit_code == 0 and "up to date" in chk2.output
