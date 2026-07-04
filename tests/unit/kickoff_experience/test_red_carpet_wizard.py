"""Tests for the Red Carpet wizard-driver + asset-chaining + completion model (FR-WD + CRP R1)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

from startd8.kickoff_experience import wizard
from startd8.kickoff_experience.manifest import default_config
from startd8.kickoff_experience.proposals import PROPOSAL_KINDS
from startd8.kickoff_experience.red_carpet import RedCarpetStage, RedCarpetState, build_red_carpet_state
from startd8.kickoff_experience.red_carpet_completion import build_completion
from startd8.kickoff_experience.wizard import (
    WizardAction,
    run_red_carpet_driver,
    wizard_inventory,
    wizard_prepopulate,
)


def _state(*, schema=False, app=False, pages=False, views=False):
    gates = {"schema": schema, "app": app, "pages": pages, "views": views}
    unmet = tuple(k for k in ("schema", "app", "pages", "views") if not gates[k])
    stages = (RedCarpetStage("data_model", "done" if schema else "pending", ""),)
    return RedCarpetState(stages=stages, next_stage=None if not unmet else "data_model",
                          cascade_offerable=not unmet, unmet_gates=unmet, readiness_score=None)


def _write_all_fields(root: Path):
    inputs = root / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    by_file: dict = {}
    for f in default_config().writable_fields():
        wt = f.write_target
        node = by_file.setdefault(wt.file, {})
        cur = node
        parts = wt.key.split(".")
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = "x"
    for fname, data in by_file.items():
        (inputs / fname).write_text(yaml.safe_dump(data), encoding="utf-8")


# ── FR-WD-2: completion model ─────────────────────────────────────────────────────────────────────

def test_completion_greenfield_zero(tmp_path):
    c = build_completion(tmp_path, _state()).to_dict()
    assert c["overall_pct"] == 0
    # CRP R1-F1: content/run are NOT in the denominator.
    assert {s["stage"] for s in c["stages"]} == {"data_model", "manifests", "value_inputs"}


def test_completion_all_present_is_100(tmp_path):
    _write_all_fields(tmp_path)
    c = build_completion(tmp_path, _state(schema=True, app=True, pages=True, views=True)).to_dict()
    assert c["overall_pct"] == 100  # CRP R1-F1 — reachable


def test_completion_stage_equal_weighting(tmp_path):
    # schema met (data_model 1/1), manifests 0/3, value_inputs 0/N → (1 + 0 + 0)/3 = 33%.
    c = build_completion(tmp_path, _state(schema=True)).to_dict()
    assert c["overall_pct"] == 33


def test_completion_invalid_domain_unfilled(tmp_path):
    _write_all_fields(tmp_path)
    # mark 'conventions' invalid in assess → its fields count as unfilled (CRP R1-F7).
    assess = {"kickoff_inputs": {"domains": {"conventions": {"status": "invalid"}}}}
    c = build_completion(tmp_path, _state(schema=True, app=True, pages=True, views=True), assess)
    vi = next(s for s in c.stages if s.stage == "value_inputs")
    assert vi.filled < vi.total  # conventions fields excluded


def test_completion_counts_defaulted_distinctly(tmp_path):
    _write_all_fields(tmp_path)
    c = build_completion(tmp_path, _state(schema=True, app=True, pages=True, views=True))
    assert c.n_defaulted >= 1  # estimate/config-default fields counted distinctly


def test_completion_in_to_dict(tmp_path):
    d = build_red_carpet_state(tmp_path).to_dict()
    assert "completion" in d and "overall_pct" in d["completion"]


# ── CRP R1-S1: structural anti-import guard (the no-import property is structural, not just behavioral)
# GE-M2: the wizard + completion code now lives in the `orchestrator` conductor (wizard /
# red_carpet_completion are compat shims). The guard scans the conductor — the real code's home — so
# the NR-4a property stays enforced on the actual implementation, not the shim.

_FORBIDDEN = ("introspect_models", "resolve_models", "build_derivation", "importlib")


@pytest.mark.parametrize("mod", [__import__(
    "startd8.kickoff_experience.orchestrator", fromlist=["x"])])
def test_wizard_modules_never_reference_import_machinery(mod):
    # Structural (AST) guard — code references only; the docstring may name the prohibition.
    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [n.name for n in node.names] + ([node.module] if isinstance(node, ast.ImportFrom) else [])
            for n in names:
                assert not any(bad in (n or "") for bad in _FORBIDDEN), f"{mod.__file__} imports {n}"
        elif isinstance(node, ast.Name):
            assert node.id not in _FORBIDDEN, f"{mod.__file__} references {node.id}"
        elif isinstance(node, ast.Attribute):
            assert node.attr not in _FORBIDDEN, f"{mod.__file__} references .{node.attr}"


# ── FR-WD-5 / CRP R1-F4/S5: discriminating no-untrusted-import proof ──────────────────────────────

def test_wizard_proposes_derive_command_without_importing(tmp_path):
    # A model file whose IMPORT writes a sentinel. The wizard must survey it + propose the derive
    # command NAMING it, and MUST NOT trigger the sentinel (it never imports).
    sentinel = tmp_path / "SENTINEL_IMPORTED"
    app = tmp_path / "app"
    app.mkdir()
    (app / "models.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(sentinel)!r}).write_text('imported')\n"   # import-time side effect
        "from pydantic import BaseModel\n"
        "class User(BaseModel):\n    id: str\n",
        encoding="utf-8")
    inv = wizard_inventory(tmp_path)
    assert "app/models.py" in inv["model_files"]                     # positive: surveyed the model
    acts = wizard_prepopulate(tmp_path, inv, _state())
    dm = [a for a in acts if a.stage == "data_model"]
    assert dm and dm[0].action_kind == "command"                    # positive: proposed the command
    assert "derive-contract" in (dm[0].command or "")
    assert not sentinel.exists()                                     # negative: never imported


# ── FR-WD-6 / CRP R1-F6: re-drive self-reference guard ────────────────────────────────────────────

def test_inventory_excludes_the_brief_output(tmp_path):
    docs = tmp_path / "docs" / "kickoff"
    docs.mkdir(parents=True)
    (docs / "REQUIREMENTS.md").write_text("## Entities\n", encoding="utf-8")
    inv = wizard_inventory(tmp_path)
    assert all(d.get("path") != "docs/kickoff/REQUIREMENTS.md" for d in inv["requirement_docs"])


# ── FR-WD-7: instantiate-first + template-seeded keys ─────────────────────────────────────────────

def test_prepopulate_instantiate_first_when_no_package(tmp_path):
    acts = wizard_prepopulate(tmp_path, {"model_files": [], "requirement_docs": []}, _state(schema=True))
    vi = [a for a in acts if a.stage == "value_inputs"]
    assert vi and vi[0].action_kind == "instantiate"  # capture cannot create the package


# ── FR-WD-3 / CRP R1-F8: action kind ∈ PROPOSAL_KINDS ∪ {command} ─────────────────────────────────

def test_action_kinds_are_bound(tmp_path):
    app = tmp_path / "app"; app.mkdir()
    (app / "m.py").write_text("from pydantic import BaseModel\nclass A(BaseModel):\n id:str\n", encoding="utf-8")
    acts = wizard_prepopulate(tmp_path, wizard_inventory(tmp_path), _state())
    for a in acts:
        assert a.action_kind in set(PROPOSAL_KINDS) | {"command"}


# ── FR-WD-1 / CRP R1-S3: driver loop advance mapping ──────────────────────────────────────────────

class _Outcome:
    def __init__(self, ok, retriable=False, code="ok"):
        self._ok = ok; self._retriable = retriable; self.code = code; self.detail = ""
    @property
    def ok(self): return self._ok
    @property
    def retriable(self): return self._retriable


def test_driver_advances_on_ok_then_completes():
    # state flips to complete after one confirmed proposal.
    calls = {"n": 0}
    def build_state():
        calls["n"] += 1
        done = calls["n"] > 1
        return _state(schema=done, app=done, pages=done, views=done)  # 2nd call: fully complete
    lines = []
    steps = run_red_carpet_driver(
        banner="B", build_state=build_state,
        prepopulate=lambda s: [WizardAction("data_model", "f", "n", "brief", proposal=object())],
        read_input=lambda p: "",
        emit_line=lines.append,
        on_proposal=lambda a: _Outcome(ok=True),
    )
    assert steps >= 1
    assert any("complete" in ln for ln in lines)


def test_driver_retriable_retains_without_stalling():
    def build_state():
        return _state(schema=False)   # never completes
    lines = []
    steps = run_red_carpet_driver(
        banner="B", build_state=build_state,
        prepopulate=lambda s: [WizardAction("data_model", "f", "n", "brief", proposal=object())],
        read_input=lambda p: "",
        emit_line=lines.append,
        on_proposal=lambda a: _Outcome(ok=False, retriable=True, code="PARTIAL"),
        no_progress_limit=2, max_steps=3,
    )
    # retriable never trips the no-progress friction message
    assert not any("stuck on" in ln for ln in lines)


def test_driver_no_progress_guard_offers_friction():
    lines = []
    run_red_carpet_driver(
        banner="B", build_state=lambda: _state(schema=False),
        prepopulate=lambda s: [WizardAction("data_model", "f", "n", "brief", proposal=object())],
        read_input=lambda p: "",
        emit_line=lines.append,
        on_proposal=lambda a: None,   # declined every time
        no_progress_limit=2, max_steps=5,
    )
    assert any("stuck on" in ln for ln in lines)
