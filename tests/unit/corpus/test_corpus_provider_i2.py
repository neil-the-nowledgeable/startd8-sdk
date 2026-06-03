"""I2: provider on the durable store + default validation gate (FR-5)."""
from startd8.corpus import (
    Binding, ControlledCorpusRegistry, TermObservation,
    ContentStore, build_corpus_provider, default_content_validator,
)
from startd8.corpus.canonical import canonical_key


def _corpus(target, n=3, req=1.0, surface="X"):
    r = ControlledCorpusRegistry()
    for i in range(n):
        r.merge_run(f"run-{i}", [TermObservation(
            kind="file", canonical_key=canonical_key("file", surface, target), surface_form=surface,
            bindings=[Binding("python", "file", target, "deterministic")],
            confidence="inferred", success=True, requirement_score=req)])
    return r


# ---- default validator (FR-5) --------------------------------------------
def test_validator_rejects_empty():
    assert default_content_validator("src/a.py", "") is False
    assert default_content_validator("src/a.py", "   \n") is False


def test_validator_python_ast():
    assert default_content_validator("src/a.py", "def f():\n    return 1\n") is True
    assert default_content_validator("src/a.py", "def f(:\n") is False  # syntax error


def test_validator_non_python_accepts_nonempty():
    assert default_content_validator("src/go.mod", "module x\n") is True
    assert default_content_validator("src/app.json", "{not valid json but nonempty}") is True


# ---- factory: store + validator wired (FR-1/2/3/5) -----------------------
def test_factory_serves_valid_content(tmp_path):
    tf = "src/emailservice/logger.py"
    corpus = _corpus(tf)
    store = ContentStore(tmp_path / "cc")
    tid = corpus.find_by_canonical_key("file", tf).term_id
    store.put(tid, "chkA", "import logging\n")
    prov = build_corpus_provider(corpus, store, "chkA")
    res = prov.generate(tf)
    assert res is not None and res.content == "import logging\n"


def test_factory_rejects_invalid_python_falls_through(tmp_path):
    tf = "src/a.py"
    corpus = _corpus(tf)
    store = ContentStore(tmp_path / "cc")
    store.put(corpus.find_by_canonical_key("file", tf).term_id, "chkA", "def broken(:\n")
    prov = build_corpus_provider(corpus, store, "chkA")
    assert prov.generate(tf) is None  # FR-5: bad content not emitted → LLM fallthrough


def test_factory_checksum_mismatch_falls_through(tmp_path):
    tf = "src/a.py"
    corpus = _corpus(tf)
    store = ContentStore(tmp_path / "cc")
    store.put(corpus.find_by_canonical_key("file", tf).term_id, "chkA", "x = 1\n")
    prov = build_corpus_provider(corpus, store, "chkB")  # different checksum
    assert prov.generate(tf) is None


def test_factory_refuses_false_pass_risk(tmp_path):
    tf = "src/rag.py"
    corpus = _corpus(tf, req=0.5)  # stable build, low req → false_pass_risk
    store = ContentStore(tmp_path / "cc")
    store.put(corpus.find_by_canonical_key("file", tf).term_id, "chkA", "x = 1\n")
    prov = build_corpus_provider(corpus, store, "chkA")
    assert prov.route(tf).reason == "refused:false_pass_risk"
    assert prov.generate(tf) is None
