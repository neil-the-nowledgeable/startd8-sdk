"""Tests for the durable proven-content store (FR-9, plan I1)."""
from types import SimpleNamespace

from startd8.corpus import (
    Binding, ControlledCorpusRegistry, TermObservation,
    ContentStore, content_store_resolver, populate_from_run,
    DeterministicCorpusProvider,
)
from startd8.corpus.canonical import canonical_key
from startd8.corpus.models import term_id_for


def _corpus(target, n=3, req=1.0, surface="X"):
    r = ControlledCorpusRegistry()
    for i in range(n):
        r.merge_run(f"run-{i}", [TermObservation(
            kind="file", canonical_key=canonical_key("file", surface, target), surface_form=surface,
            bindings=[Binding("python", "file", target, "deterministic")],
            confidence="inferred", success=True, requirement_score=req)])
    return r


# ---- store round-trip (FR-9) ---------------------------------------------
def test_put_get_round_trip(tmp_path):
    store = ContentStore(tmp_path / "corpus-content")
    tid = term_id_for("file", "src/a.py")
    store.put(tid, "chk1", "print('x')\n")
    assert store.get(tid, "chk1") == "print('x')\n"
    assert store.has(tid, "chk1")


def test_checksum_miss_returns_none(tmp_path):
    """OQ-2 invalidation: content keyed by source_checksum; a changed checksum misses."""
    store = ContentStore(tmp_path / "cc")
    tid = term_id_for("file", "src/a.py")
    store.put(tid, "chk1", "v1\n")
    assert store.get(tid, "chk2") is None          # stale input → miss → LLM fallthrough
    assert store.get("file:other", "chk1") is None


def test_missing_store_returns_none(tmp_path):
    store = ContentStore(tmp_path / "absent")
    assert store.get(term_id_for("file", "src/a.py"), "chk1") is None


# ---- resolver binds corpus term -> store content -------------------------
def test_content_store_resolver(tmp_path):
    tf = "src/emailservice/logger.py"
    corpus = _corpus(tf)
    store = ContentStore(tmp_path / "cc")
    tid = corpus.find_by_canonical_key("file", tf).term_id
    store.put(tid, "chkA", "import logging\n")
    resolve = content_store_resolver(corpus, store, "chkA")
    assert resolve(tf) == "import logging\n"
    assert resolve("src/unknown.py") is None       # not in corpus
    assert content_store_resolver(corpus, store, "chkB")(tf) is None  # checksum mismatch


# ---- provider served from the durable store (FR-1..FR-3 over the store) ----
def test_provider_serves_from_store(tmp_path):
    tf = "src/loadgenerator/locustfile.py"
    corpus = _corpus(tf)
    store = ContentStore(tmp_path / "cc")
    store.put(corpus.find_by_canonical_key("file", tf).term_id, "chkA", "from locust import *\n")
    prov = DeterministicCorpusProvider(corpus, content_store_resolver(corpus, store, "chkA"))
    res = prov.generate(tf)
    assert res is not None and res.content == "from locust import *\n"


# ---- populate_from_run (standalone; not wired live in I1) -----------------
def test_populate_from_run(tmp_path):
    gen = tmp_path / "generated" / "src" / "a.py"
    gen.parent.mkdir(parents=True, exist_ok=True)
    gen.write_text("x = 1\n")
    report = SimpleNamespace(features=[
        SimpleNamespace(success=True, target_files=["src/a.py"], generated_files=[str(gen)]),
        SimpleNamespace(success=False, target_files=["src/b.py"], generated_files=[]),  # skipped
        SimpleNamespace(success=True, target_files=[], generated_files=[]),             # skipped
    ])
    store = ContentStore(tmp_path / "cc")
    n = populate_from_run(report, "chkA", store)
    assert n == 1
    assert store.get(term_id_for("file", "src/a.py"), "chkA") == "x = 1\n"
