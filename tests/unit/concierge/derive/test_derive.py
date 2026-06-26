"""Tests for derive-contract orchestration — Step 3 (preview+provenance), Step 4 (exclusion/
orphans), Step 5 (drift + ratified-flagged suppression). Core paths use in-process facts for
speed; a navig8 contained smoke covers the full subprocess path."""

from __future__ import annotations

import enum
from typing import Dict, List, Optional

import pytest
from pydantic import BaseModel, Field

from startd8.concierge.derive.derive import (
    PROVENANCE_HEADER,
    _assemble,
    _check,
    build_derivation,
)
from startd8.concierge.derive.introspect import introspect_models


class Bites(str, enum.Enum):
    AT_FORMATION = "at-formation"
    DONE = "done"


class Child(BaseModel):
    id: str
    name: str


class Parent(BaseModel):
    id: str
    tags: List[str] = []                 # unmarked list[str] → flagged
    bites: Bites = Bites.DONE
    children: List[Child] = []


class Artifact(BaseModel):               # a pipeline artifact to exclude (Step 4)
    id: str
    blob: str


def _facts(*models):
    return introspect_models(list(models))


# ── Step 3 — preview + provenance ────────────────────────────────────────────

def test_provenance_header_and_unratified():
    d, _ = _assemble(_facts(Parent, Child))
    assert d.contract_text.startswith(PROVENANCE_HEADER)
    assert "unratified" in d.contract_text
    assert "model Parent" in d.contract_text and d.errors == []


def test_report_and_shape():
    d, report = _assemble(_facts(Parent, Child))
    assert d.shape["entities"] == 2 and d.shape["enums"] == 1
    assert any(t["rule"] == "enum-hyphen-normalize" for t in report.transforms)


# ── Step 4 — exclusion sidecar + orphan/dangling detection ───────────────────

def test_exclude_model_drops_and_records():
    d, _ = _assemble(_facts(Parent, Child, Artifact), exclude_models=["Artifact"])
    assert "model Artifact" not in d.contract_text
    assert any(fl.get("kind") == "sidecar-exclude" and fl.get("entity") == "Artifact"
               for fl in d.report["flags"])


def test_orphan_exclusion_flagged():
    d, _ = _assemble(_facts(Parent, Child), exclude_models=["DoesNotExist"])
    assert any(fl.get("kind") == "orphan-exclusion" for fl in d.report["flags"])


def test_dangling_reference_flagged():
    """Excluding a model that a kept entity references is flagged (relation would dangle)."""
    class Ref(BaseModel):
        id: str

    class Holder(BaseModel):
        id: str
        ref: Optional[Ref] = None

    d, _ = _assemble(_facts(Holder, Ref), exclude_models=["Ref"])
    assert any(fl.get("kind") == "dangling-reference" and fl.get("field") == "ref"
               for fl in d.report["flags"])


# ── Step 5 — drift + ratified-flagged suppression ───────────────────────────

def test_drift_in_sync_against_own_output():
    d, _ = _assemble(_facts(Parent, Child))
    body = d.contract_text[len(PROVENANCE_HEADER):]      # parity compares schema bodies
    drift = _check(_facts(Parent, Child), body)
    assert drift.verdict == "in_sync" and drift.drift == []


def test_drift_detects_a_real_change():
    d, _ = _assemble(_facts(Parent, Child))
    live = d.contract_text[len(PROVENANCE_HEADER):].replace("prompt String", "prompt String")
    # remove the Child model from live → drift
    live_missing_child = "\n".join(
        ln for ln in live.splitlines() if "Child" not in ln
    )
    drift = _check(_facts(Parent, Child), live_missing_child)
    assert drift.verdict == "drifted" and drift.drift


def test_ratified_flagged_field_suppressed():
    """FR-DC-11: a flagged field (unmarked list[str] `tags`) the human ratified away from the live
    contract must NOT read as drift — it lands in excluded_flagged, not drift."""
    d, _ = _assemble(_facts(Parent, Child))
    body = d.contract_text[len(PROVENANCE_HEADER):]
    # simulate ratification: the human turned `tags` into something else → it's absent from live.
    live = "\n".join(ln for ln in body.splitlines() if "tags" not in ln)
    drift = _check(_facts(Parent, Child), live)
    assert any("Parent.tags" in line for line in drift.excluded_flagged)
    assert not any("Parent.tags" in line for line in drift.drift)
    assert drift.verdict == "in_sync"   # the only difference was the ratified flagged field


# ── navig8 contained smoke (full subprocess path) ───────────────────────────

def test_navig8_build_derivation_contained():
    work = "/Users/neilyashinsky/Documents/dev/startd8-work/src"
    from pathlib import Path
    if not Path(work, "startd8_work", "legal", "tree_models.py").is_file():
        pytest.skip("startd8_work not present")
    d = build_derivation(
        ["startd8_work.legal.tree_models", "startd8_work.legal.models"],
        project_pythonpath=work,
        model_names=["DecisionTree", "TreeNode", "Perspective", "Citation"],
    )
    assert d.contract_text.startswith(PROVENANCE_HEADER)
    assert d.errors == []
    assert "model TreeNode" in d.contract_text and "model Citation" in d.contract_text
    assert d.shape["entities"] == 4
