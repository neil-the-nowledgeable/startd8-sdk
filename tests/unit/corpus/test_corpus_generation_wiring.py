"""R4-S2: Controlled Corpus authorities wired into the spec prompt (FR-9)."""
from startd8.corpus import Binding, ControlledCorpusRegistry, TermObservation
from startd8.corpus.canonical import canonical_key
from startd8.implementation_engine.spec_builder import (
    _build_corpus_authorities_section,
    build_spec_prompt,
)


def _mature_registry():
    r = ControlledCorpusRegistry()
    obs = lambda: [TermObservation(
        kind="file", canonical_key=canonical_key("file", "Logger", "src/emailservice/logger.py"),
        surface_form="Logger",
        bindings=[Binding("python", "file", "src/emailservice/logger.py", "deterministic")],
        confidence="inferred", success=True, requirement_score=1.0)]
    r.merge_run("run-001", obs())
    r.merge_run("run-002", obs())  # -> maturity 2, deterministic_candidate
    return r


# ---- helper-level ---------------------------------------------------------
def test_section_rendered_from_injected_registry():
    s = _build_corpus_authorities_section({"_corpus_registry": _mature_registry()})
    assert "Established project vocabulary" in s
    assert "src/emailservice/logger.py" in s


def test_section_empty_when_disabled():
    s = _build_corpus_authorities_section(
        {"_corpus_registry": _mature_registry(), "corpus_authorities_enabled": False})
    assert s == ""


def test_section_empty_when_env_off(monkeypatch):
    monkeypatch.setenv("STARTD8_CORPUS_AUTHORITIES", "0")
    s = _build_corpus_authorities_section({"_corpus_registry": _mature_registry()})
    assert s == ""


def test_section_empty_when_no_corpus(tmp_path):
    # no registry, no file at the given path -> empty (no crash)
    s = _build_corpus_authorities_section({"corpus_path": str(tmp_path / "absent.json")})
    assert s == ""


def test_helper_pops_its_context_keys():
    ctx = {"_corpus_registry": _mature_registry(), "corpus_authorities_enabled": True,
           "corpus_path": "x"}
    _build_corpus_authorities_section(ctx)
    # keys consumed so they don't leak into the JSON general-context dump
    assert "_corpus_registry" not in ctx
    assert "corpus_authorities_enabled" not in ctx
    assert "corpus_path" not in ctx


# ---- end-to-end through build_spec_prompt ---------------------------------
def test_authorities_land_in_spec_prompt():
    ctx = {"_corpus_registry": _mature_registry(), "target_files": ["src/new.py"]}
    prompt = build_spec_prompt("Implement a new thing", ctx, None)
    assert "Established project vocabulary" in prompt
    assert "src/emailservice/logger.py" in prompt


def test_no_authorities_when_disabled_in_spec_prompt():
    ctx = {"_corpus_registry": _mature_registry(), "corpus_authorities_enabled": False,
           "target_files": ["src/new.py"]}
    prompt = build_spec_prompt("Implement a new thing", ctx, None)
    assert "Established project vocabulary" not in prompt


def test_project_root_resolves_on_disk_corpus(tmp_path):
    """The R4-S2 read path resolves <project_root>/.startd8/controlled-corpus.json
    (the same location the postmortem write path uses)."""
    from startd8.paths import controlled_corpus_path
    cp = controlled_corpus_path(tmp_path)
    cp.parent.mkdir(parents=True, exist_ok=True)
    _mature_registry().save(cp)
    section = _build_corpus_authorities_section({"project_root": str(tmp_path)})
    assert "Established project vocabulary" in section
    assert "src/emailservice/logger.py" in section
