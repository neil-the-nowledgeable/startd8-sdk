"""I3b: live Phase 0.7 _try_corpus_shortcut — DEFAULT-OFF gate + emission + guardrails."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from startd8.contractors.prime_contractor import PrimeContractorWorkflow
from startd8.contractors.queue import FeatureStatus
from startd8.corpus import (
    Binding, ControlledCorpusRegistry, TermObservation, ContentStore,
)
from startd8.corpus.canonical import canonical_key
from startd8.corpus.models import term_id_for
from startd8.paths import controlled_corpus_path, corpus_content_dir


def _fixture(tmp_path, target="src/a.py", content="x = 1\n", req=1.0, checksum="chkZ"):
    """Build a project with a corpus (target at L3) + content store + seed on disk."""
    proj = tmp_path / "proj"; proj.mkdir()
    out = tmp_path / "out"; out.mkdir()
    # corpus: 3 runs → L3 deterministic_candidate (or false_pass if req low)
    reg = ControlledCorpusRegistry()
    for i in range(3):
        reg.merge_run(f"run-{i}", [TermObservation(
            kind="file", canonical_key=canonical_key("file", "A", target), surface_form="A",
            bindings=[Binding("python", "file", target, "deterministic")],
            confidence="inferred", success=True, requirement_score=req)])
    reg.save(controlled_corpus_path(proj))
    # content store keyed by (term_id, checksum)
    ContentStore(corpus_content_dir(proj)).put(
        term_id_for("file", canonical_key("file", "", target)), checksum, content)
    # seed with source_checksum
    seed = proj / "prime-context-seed.json"
    seed.write_text(json.dumps({"source_checksum": checksum, "tasks": []}))
    # bare workflow with only the attributes the method touches
    wf = PrimeContractorWorkflow.__new__(PrimeContractorWorkflow)
    wf.project_root = proj
    wf._seed_path = str(seed)
    wf._resolve_output_dir = lambda: out
    wf._save_queue_state_with_mode = lambda: None
    feature = SimpleNamespace(name="A", target_files=[target], generated_files=[], status=None)
    return wf, feature, out


def test_i3b_default_off_is_noop(tmp_path, monkeypatch):
    """Flag unset (default): shortcut is a no-op → LLM path unchanged (regression-safe)."""
    monkeypatch.delenv("STARTD8_CORPUS_DETERMINISTIC", raising=False)
    wf, feature, out = _fixture(tmp_path)
    assert wf._try_corpus_shortcut(feature) is None
    assert feature.status is None                       # untouched
    assert not (out / "src" / "a.py").exists()          # nothing written


def test_i3b_flag_on_emits_content(tmp_path, monkeypatch):
    monkeypatch.setenv("STARTD8_CORPUS_DETERMINISTIC", "1")
    wf, feature, out = _fixture(tmp_path, content="print('served')\n")
    assert wf._try_corpus_shortcut(feature) is True
    written = out / "src" / "a.py"
    assert written.read_text() == "print('served')\n"   # emitted, no LLM
    assert feature.status == FeatureStatus.GENERATED
    assert feature.generated_files == [str(written)]


def test_i3b_refuses_false_pass(tmp_path, monkeypatch):
    monkeypatch.setenv("STARTD8_CORPUS_DETERMINISTIC", "1")
    wf, feature, out = _fixture(tmp_path, req=0.5)        # → false_pass_risk
    assert wf._try_corpus_shortcut(feature) is None       # never served
    assert not (out / "src" / "a.py").exists()


def test_i3b_checksum_mismatch_falls_through(tmp_path, monkeypatch):
    monkeypatch.setenv("STARTD8_CORPUS_DETERMINISTIC", "1")
    wf, feature, out = _fixture(tmp_path, checksum="chkZ")
    # seed now declares a DIFFERENT checksum than the stored content
    Path(wf._seed_path).write_text(json.dumps({"source_checksum": "chkOTHER"}))
    assert wf._try_corpus_shortcut(feature) is None
    assert not (out / "src" / "a.py").exists()


def test_i3b_no_corpus_file_falls_through(tmp_path, monkeypatch):
    monkeypatch.setenv("STARTD8_CORPUS_DETERMINISTIC", "1")
    wf, feature, out = _fixture(tmp_path)
    controlled_corpus_path(wf.project_root).unlink()      # no corpus
    assert wf._try_corpus_shortcut(feature) is None
