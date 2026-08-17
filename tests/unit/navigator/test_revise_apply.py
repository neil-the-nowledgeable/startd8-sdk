"""REQ-24 — the byte-identity revise applier (fills REQ-21's guard seam with a REAL guard).

The load-bearing guarantee: an edit auto-applies ONLY when regenerating the `$0` product proves its real
content unchanged (modulo the source-fingerprint stamp); a product-changing edit is caught by the guard
and downgraded to `human`, leaving the contract byte-identical. Enforce, don't declare.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

import pytest

from startd8.navigator.govern import Finding
from startd8.navigator.models import node_field_names
from startd8.navigator.revise_apply import apply_revise, byte_identity_guard
from startd8.navigator.revise_tier import (
    ReviseEdit,
    ReviseEditError,
    eligibility_of,
    parse_revise_edit,
)
from startd8.navigator.sources_retrospective import build_lesson_from_regression

_SCHEMA = """datasource db { provider = "sqlite"; url = "file:./dev.db" }
generator client { provider = "prisma-client-py" }

model Profile {
  id    Int    @id @default(autoincrement())
  name  String
}
"""

# empirically verified: a comment edit changes ONLY the schema-sha256 stamp (real content identical);
# a field rename changes 10 files of real content.
_IDENTICAL_EDIT = ReviseEdit("Profile", "schema.prisma", "model Profile {", "model Profile {  // a user profile")
_CHANGING_EDIT = ReviseEdit("Profile", "schema.prisma", "name  String", "title String")


def _lesson(confidence=0.95):
    lesson = build_lesson_from_regression(Finding("FR-6", "fail", "d", "regression", fr="Profile"))
    return dataclasses.replace(lesson, confidence=confidence)


# ── FR-1 — the concrete revise edit ─────────────────────────────────────────────────────────────────

def test_parse_revise_edit_validates():
    e = parse_revise_edit({"target": "Profile", "path": "s.prisma", "before": "x", "after": "y"})
    assert e.target == "Profile" and e.before == "x" and e.after == "y"
    for bad in ({"path": "s", "before": "x"}, {"target": "", "path": "s", "before": "x"},
                {"target": "t", "path": "s", "before": ""}):
        with pytest.raises(ReviseEditError):
            parse_revise_edit(bad)


# ── FR-2 — the real byte-identity guard (regenerate + hash-compare, modulo provenance) ─────────────

def test_guard_true_for_content_identical_edit_false_for_product_change():
    assert byte_identity_guard(_SCHEMA, _IDENTICAL_EDIT)() is True     # only the sha256 stamp moved
    assert byte_identity_guard(_SCHEMA, _CHANGING_EDIT)() is False     # real content changed → human


def test_guard_false_for_inapplicable_edit():
    """FR-2 fail-closed: an edit whose `before` isn't in the contract can't be proven → False."""
    assert byte_identity_guard(_SCHEMA, ReviseEdit("P", "s", "NOT PRESENT", "z"))() is False


# ── FR-3/FR-4 — apply through the seam, reversible ─────────────────────────────────────────────────

def test_content_identical_edit_auto_applies_and_writes_only_with_apply(tmp_path):
    schema = tmp_path / "schema.prisma"
    schema.write_text(_SCHEMA, encoding="utf-8")
    lesson = _lesson(0.95)
    elig = eligibility_of(lesson, byte_identical=True, effects=[])

    # dry-run: audit produced, but the contract is NOT written
    audit = apply_revise(schema, _IDENTICAL_EDIT, lesson, elig, timestamp="t", revert_ref="r", dry_run=True)
    assert audit is not None and audit.target == "Profile"
    assert schema.read_text(encoding="utf-8") == _SCHEMA               # FR-4: untouched in dry-run

    # --apply: the edit is committed to the contract (git-tracked, reversible)
    audit2 = apply_revise(schema, _IDENTICAL_EDIT, lesson, elig, timestamp="t", revert_ref="abc", dry_run=False)
    assert audit2 is not None and "// a user profile" in schema.read_text(encoding="utf-8")


def test_product_changing_edit_downgrades_to_human_and_leaves_contract_untouched(tmp_path):
    """FR-3/FR-4: a product-changing edit is caught by the guard → None (human) → contract byte-identical."""
    schema = tmp_path / "schema.prisma"
    schema.write_text(_SCHEMA, encoding="utf-8")
    lesson = _lesson(0.95)
    elig = eligibility_of(lesson, byte_identical=True, effects=[])
    audit = apply_revise(schema, _CHANGING_EDIT, lesson, elig, timestamp="t", revert_ref="r", dry_run=False)
    assert audit is None                                              # downgraded to human
    assert schema.read_text(encoding="utf-8") == _SCHEMA              # FR-4: contract left byte-identical


def test_below_floor_lesson_never_auto_applies_even_if_content_identical(tmp_path):
    schema = tmp_path / "schema.prisma"
    schema.write_text(_SCHEMA, encoding="utf-8")
    lesson = _lesson(0.2)                                             # below floor → human
    elig = eligibility_of(lesson, byte_identical=True, effects=[])
    assert apply_revise(schema, _IDENTICAL_EDIT, lesson, elig, timestamp="t", revert_ref="r", dry_run=False) is None
    assert schema.read_text(encoding="utf-8") == _SCHEMA


# ── FR-6 — firewall preserved (AST) ────────────────────────────────────────────────────────────────

def test_fr6_construction_coupling_quarantined_to_applier():
    nav = Path(__file__).parents[3] / "src" / "startd8" / "navigator"
    forbidden = ("backend_codegen", "contractors", "micro_prime")

    def _imports(mod):
        out = []
        for n in ast.walk(ast.parse((nav / mod).read_text())):
            if isinstance(n, ast.Import):
                out += [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom):
                out.append(n.module or "")
        return out

    # the applier MAY import backend_codegen (it regenerates the product)
    assert any("backend_codegen" in m for m in _imports("revise_apply.py"))
    # the navigator CORE must not
    for core in ("revise_tier.py", "realization.py", "realization_provenance.py", "sources_retrospective.py"):
        assert not [m for m in _imports(core) if any(f in m for f in forbidden)], f"{core} broke the firewall"


# ── FR-7 — additive, no new Node field ─────────────────────────────────────────────────────────────

def test_fr7_no_new_node_field():
    assert "verify" in node_field_names() and len(node_field_names()) == 19   # unchanged by REQ-24


# ── FR-5 — the CLI applier (dry-run default) ───────────────────────────────────────────────────────

def test_fr5_cli_revise_apply_dry_run(tmp_path):
    import dataclasses as _dc
    import json

    from typer.testing import CliRunner

    from startd8.cli import app
    from startd8.navigator.project import nodes_to_json

    schema = tmp_path / "schema.prisma"
    schema.write_text(_SCHEMA, encoding="utf-8")
    (tmp_path / "edit.json").write_text(json.dumps(_dc.asdict(_IDENTICAL_EDIT)))
    lesson = _lesson(0.95)
    (tmp_path / "lesson.json").write_text(json.dumps(nodes_to_json([lesson])[0]))

    res = CliRunner().invoke(app, ["navigator", "revise-apply", "--schema", str(schema),
                                   "--edit", str(tmp_path / "edit.json"), "--lesson", str(tmp_path / "lesson.json")])
    assert res.exit_code == 0, res.output
    assert "auto-eligible (dry-run)" in res.output               # content-identical edit → auto-eligible
    assert schema.read_text(encoding="utf-8") == _SCHEMA         # dry-run writes nothing

    # a product-changing edit reports human
    (tmp_path / "bad.json").write_text(json.dumps(_dc.asdict(_CHANGING_EDIT)))
    res2 = CliRunner().invoke(app, ["navigator", "revise-apply", "--schema", str(schema),
                                    "--edit", str(tmp_path / "bad.json"), "--lesson", str(tmp_path / "lesson.json")])
    assert res2.exit_code == 0 and "human" in res2.output
