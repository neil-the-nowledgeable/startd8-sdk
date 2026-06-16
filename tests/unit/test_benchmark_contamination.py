"""CodeBLEU contamination/memorization probe (FR-47). Pure-logic tests + skip-guarded scoring."""
from __future__ import annotations

import pytest

from startd8.benchmark_matrix.contamination import (
    OB_SERVICE_LANG,
    codebleu_available,
    codebleu_lang,
    resolve_main_source,
    score_pair,
    score_run,
    _is_impl_file,
)
from pathlib import Path


# --- pure logic (no codebleu needed) -----------------------------------------

def test_codebleu_lang_maps_sdk_ids_and_extensions():
    assert codebleu_lang("nodejs") == "javascript"
    assert codebleu_lang("csharp") == "c_sharp"
    assert codebleu_lang(".go") == "go"
    assert codebleu_lang("a.py") == "python"
    assert codebleu_lang("rust") is None


def test_is_impl_file_excludes_generated_and_tests(tmp_path):
    assert _is_impl_file(Path("src/currencyservice/server.js"))
    assert not _is_impl_file(Path("src/currencyservice/client.js"))      # client
    assert not _is_impl_file(Path("src/x/node_modules/foo.js"))          # dep dir
    assert not _is_impl_file(Path("build/generated/AdServiceGrpc.java")) # generated + grpc
    assert not _is_impl_file(Path("src/AdServiceTest.java"))             # test
    assert not _is_impl_file(Path("recommendation_server.py.backup"))    # backup


def test_is_impl_file_does_not_misfire_on_latest_substring(tmp_path):
    """Regression: 'microservices-demo-latest' contains 'test' (la-TEST). Segment/name matching
    must NOT exclude a real source file just because an ancestor dir is named '…-latest'."""
    f = tmp_path / "microservices-demo-latest" / "src" / "currencyservice" / "server.js"
    f.parent.mkdir(parents=True)
    f.write_text("function x(){return 1}\n")
    assert _is_impl_file(f)
    assert resolve_main_source(f.parent, ".js") == f


def test_resolve_main_source_picks_largest_impl(tmp_path):
    d = tmp_path / "svc"
    d.mkdir()
    (d / "small.go").write_text("package m\n")
    (d / "main.go").write_text("package m\n" + "// x\n" * 50)
    (d / "main_test.go").write_text("package m\n" + "// y\n" * 200)  # excluded despite size
    assert resolve_main_source(d, ".go").name == "main.go"


def test_score_pair_degrades_on_missing_files(tmp_path):
    sc = score_pair(tmp_path / "nope.py", tmp_path / "also_nope.py", "python")
    assert sc.available is False
    assert sc.codebleu is None
    assert "missing" in sc.detail


def test_score_pair_degrades_on_unknown_language(tmp_path):
    f = tmp_path / "a.rs"
    f.write_text("fn main(){}")
    sc = score_pair(f, f, "rust")
    assert sc.available is False and "no CodeBLEU language" in sc.detail


def test_score_run_empty_when_no_sandboxes(tmp_path):
    rep = score_run(tmp_path, tmp_path)
    assert rep["n_cells"] == 0 and rep["n_scored"] == 0
    assert rep["model_mean_codebleu"] == {}


def test_ob_service_lang_covers_nine_services():
    assert len(OB_SERVICE_LANG) == 9
    assert OB_SERVICE_LANG["cartservice"] == ("csharp", ".cs")


# --- real scoring (needs codebleu + parsers) ---------------------------------

requires_codebleu = pytest.mark.skipif(not codebleu_available(), reason="codebleu not installed")


@requires_codebleu
def test_score_pair_identical_is_high(tmp_path):
    a = tmp_path / "a.py"
    a.write_text("def add(x, y):\n    return x + y\n")
    sc = score_pair(a, a, "python")
    if not sc.available:                      # tree-sitter parser/ABI gap on this interpreter
        pytest.skip(f"codebleu degraded: {sc.detail}")
    assert sc.codebleu is not None and sc.codebleu > 0.9   # identical code ⇒ near-1.0


@requires_codebleu
def test_score_pair_dissimilar_is_lower(tmp_path):
    ref = tmp_path / "r.py"
    cand = tmp_path / "c.py"
    ref.write_text("def add(x, y):\n    return x + y\n")
    cand.write_text("class Z:\n    def __init__(s):\n        s.v = [i*i for i in range(9)]\n")
    a, b = score_pair(ref, ref, "python"), score_pair(ref, cand, "python")
    if not (a.available and b.available):
        pytest.skip("codebleu degraded on this interpreter")
    assert b.codebleu < a.codebleu            # dissimilar scores below identical


def test_score_run_resolves_k2_k3_sandboxes_via_cells_json(tmp_path):
    """Review fix: with cells.json present, score_run resolves K2 (-lev-on) and K3
    (-lead-…_drafter-…) sandboxes via sandbox_dir_name + the recorded coordinate — not fragile
    dir-name parsing — and attributes the correct model."""
    import json as _json

    from startd8.benchmark_matrix.runner import sandbox_dir_name

    run = tmp_path / "run"
    (run / "sandboxes").mkdir(parents=True)
    ref_root = tmp_path / "ob"
    (ref_root / "currencyservice").mkdir(parents=True)
    (ref_root / "currencyservice" / "server.js").write_text("function convert(){ return 1; }\n")

    model, target = "anthropic:claude-opus-4-8", "src/currencyservice/server.js"
    meta = []

    def place(leverage, lead, drafter):
        sb = run / "sandboxes" / sandbox_dir_name(
            "currencyservice", model, 0, leverage=leverage, lead=lead, drafter=drafter)
        (sb / target).parent.mkdir(parents=True, exist_ok=True)
        (sb / target).write_text("function convert(){ return 2; }\n")
        meta.append({"service": "currencyservice", "model": model, "repetition": 0,
                     "status": "ok", "leverage": leverage, "lead": lead, "drafter": drafter})

    place("on", None, None)                          # K2 on-cell → ...-lev-on
    place("off", model, "gemini:gemini-2.5-pro")     # K3 off-diagonal → ...-lead-…_drafter-…
    (run / "cells.json").write_text(_json.dumps(meta))

    rep = score_run(run, ref_root)
    assert rep["n_cells"] == 2
    # both sandboxes resolved (gen+ref found — not "missing"); model attributed from cells.json
    assert all("missing" not in c["detail"] for c in rep["cells"]), [c["detail"] for c in rep["cells"]]
    assert all(c["service"] == "currencyservice" and c["model"] == model for c in rep["cells"])
