"""I3a: postmortem content-store write — DEFAULT-OFF gate + on-path (FR-9)."""
import json
from types import SimpleNamespace

from startd8.corpus import ContentStore
from startd8.corpus.canonical import canonical_key
from startd8.corpus.models import term_id_for
from startd8.paths import corpus_content_dir


def _setup(tmp_path):
    out = tmp_path / "run-x" / "plan-ingestion"
    out.mkdir(parents=True)
    (out / "prime-context-seed.json").write_text(
        json.dumps({"source_checksum": "chkZ", "tasks": []}))
    gen = out / "generated" / "src" / "a.py"
    gen.parent.mkdir(parents=True)
    gen.write_text("x = 1\n")
    proj = tmp_path / "proj"
    proj.mkdir()
    report = SimpleNamespace(
        report_id="run-x", total_features=1,
        features=[SimpleNamespace(name="A", target_files=["src/a.py"], success=True,
                                  requirement_score=1.0, disk_quality_score=1.0,
                                  generated_files=[str(gen)])])
    return proj, out, report


def test_i3a_default_off_no_content_store(tmp_path, monkeypatch):
    """Default (flag unset): corpus accumulates but the content store is NOT written."""
    monkeypatch.delenv("STARTD8_CORPUS_CONTENT_STORE", raising=False)
    from startd8.contractors.prime_postmortem import PrimePostMortemEvaluator
    proj, out, report = _setup(tmp_path)
    PrimePostMortemEvaluator()._extract_corpus(report, str(proj), str(out))
    assert not corpus_content_dir(proj).exists()   # no content written by default


def test_i3a_flag_on_writes_content_keyed_by_checksum(tmp_path, monkeypatch):
    monkeypatch.setenv("STARTD8_CORPUS_CONTENT_STORE", "1")
    from startd8.contractors.prime_postmortem import PrimePostMortemEvaluator
    proj, out, report = _setup(tmp_path)
    PrimePostMortemEvaluator()._extract_corpus(report, str(proj), str(out))
    store = ContentStore(corpus_content_dir(proj))
    tid = term_id_for("file", canonical_key("file", "", "src/a.py"))
    assert store.get(tid, "chkZ") == "x = 1\n"      # persisted under the seed checksum
    assert store.get(tid, "other") is None          # checksum-keyed (OQ-2)
