"""Tests for the corpus-driven deterministic provider (DETERMINISTIC_PROVIDER_REQUIREMENTS)."""
from startd8.corpus import (
    Binding, ControlledCorpusRegistry, TermObservation,
    DeterministicCorpusProvider, dict_content_resolver,
)
from startd8.corpus.canonical import canonical_key


def _obs(target, success, req, surface="X"):
    return TermObservation(
        kind="file", canonical_key=canonical_key("file", surface, target), surface_form=surface,
        bindings=[Binding("python", "file", target, "deterministic")],
        confidence="inferred", success=success, requirement_score=req)


def _corpus(target, results, surface="X"):
    r = ControlledCorpusRegistry()
    for i, (s, q) in enumerate(results):
        r.merge_run(f"run-{i}", [_obs(target, s, q, surface)])
    return r


# ---- routing (FR-1) -------------------------------------------------------
def test_routes_deterministic_candidate():
    tf = "src/loadgenerator/locustfile.py"
    prov = DeterministicCorpusProvider(_corpus(tf, [(True, 1.0)] * 3),
                                       dict_content_resolver({tf: "print('x')\n"}))
    assert prov.route(tf).eligible is True


def test_never_routes_false_pass_risk():
    tf = "src/shoppingassistantservice/shoppingassistantservice.py"
    prov = DeterministicCorpusProvider(_corpus(tf, [(True, 0.5)] * 3),
                                       dict_content_resolver({tf: "x = 1\n"}))
    d = prov.route(tf)
    assert d.eligible is False and d.reason == "refused:false_pass_risk"
    assert prov.generate(tf) is None  # never served deterministically


def test_ineligible_when_not_in_corpus():
    prov = DeterministicCorpusProvider(ControlledCorpusRegistry(), dict_content_resolver({}))
    d = prov.route("src/unknown.py")
    assert d.eligible is False and d.reason == "not_in_corpus"


def test_ineligible_when_immature():
    tf = "src/a.py"
    prov = DeterministicCorpusProvider(_corpus(tf, [(True, 1.0), (True, 1.0)]),  # L2, not L3
                                       dict_content_resolver({tf: "x\n"}), min_maturity=3)
    assert prov.route(tf).eligible is False


# ---- emission (FR-3/4/5) --------------------------------------------------
def test_emits_proven_content_no_llm():
    tf = "src/emailservice/logger.py"
    content = "import logging\n\ndef get_logger(name):\n    return logging.getLogger(name)\n"
    prov = DeterministicCorpusProvider(_corpus(tf, [(True, 1.0)] * 3),
                                       dict_content_resolver({tf: content}))
    res = prov.generate(tf)
    assert res is not None
    assert res.content == content                 # byte-identical
    assert res.fill_source == "corpus_deterministic"


def test_falls_through_when_no_content():
    tf = "src/a.py"
    prov = DeterministicCorpusProvider(_corpus(tf, [(True, 1.0)] * 3),
                                       dict_content_resolver({}))  # eligible but no content
    assert prov.generate(tf) is None              # → LLM path unchanged


def test_validation_gate_falls_through_on_bad_content():
    tf = "src/a.py"
    prov = DeterministicCorpusProvider(
        _corpus(tf, [(True, 1.0)] * 3),
        dict_content_resolver({tf: "def broken(:\n"}),          # invalid python
        validator=lambda t, c: _is_valid_py(c))
    assert prov.generate(tf) is None              # corrupted content not emitted


def _is_valid_py(src: str) -> bool:
    import ast
    try:
        ast.parse(src); return True
    except SyntaxError:
        return False


def test_emit_is_deterministic():
    tf = "src/a.py"
    prov = DeterministicCorpusProvider(_corpus(tf, [(True, 1.0)] * 3),
                                       dict_content_resolver({tf: "x = 1\n"}))
    assert prov.generate(tf).content == prov.generate(tf).content
