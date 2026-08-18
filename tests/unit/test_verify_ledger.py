"""Fixture-driven tests for the done-census verifier (``scripts/verify_ledger.py``).

These do NOT depend on the live ledger's content (which changes). Pure functions
(``extract_shas``/``extract_paths``/``classify_path``/``parse_implemented_rows``) are unit-tested
directly; the one git-touching path (LANDED) is exercised with a real ancestor sha via
``git rev-parse HEAD`` and gated on a repo being present.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

# Load the standalone script as a module (it lives in scripts/, not on the package path).
_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_ledger.py"
_spec = importlib.util.spec_from_file_location("verify_ledger", _SCRIPT)
vl = importlib.util.module_from_spec(_spec)
# Register in sys.modules BEFORE exec so @dataclass can resolve annotations (Python 3.14).
sys.modules["verify_ledger"] = vl
_spec.loader.exec_module(vl)


# ── extract_shas: the classification guards ─────────────────────────────────────────────────


def test_extract_shas_basic():
    text = "REQ delivered (`d416fc38`) and also `bbf97542`."
    assert vl.extract_shas(text) == ["d416fc38", "bbf97542"]


def test_extract_shas_ignores_color_hex():
    # `#3a6a94` is a CSS color, not a commit sha.
    text = "renders `--accent:#3a6a94` vs `#1b545f`"
    assert vl.extract_shas(text) == []


def test_extract_shas_ignores_sha256_field():
    # a content digest field, not a commit sha.
    text = "carries a `sha256:deadbeefcafef00d` provenance header"
    assert vl.extract_shas(text) == []


def test_extract_shas_ignores_flags():
    text = "run `--renderer` and `--semantic-only` with `--full-graph`"
    assert vl.extract_shas(text) == []


def test_extract_shas_dedupes():
    text = "landed `aaaaaaa` then again `aaaaaaa`"
    assert vl.extract_shas(text) == ["aaaaaaa"]


def test_extract_shas_rejects_too_short_or_nonhex():
    # 6 hex is below the floor; a word with non-hex letters is not captured.
    text = "`abcde` `zzzzzzz` `hello`"
    assert vl.extract_shas(text) == []


# ── extract_paths ───────────────────────────────────────────────────────────────────────────


def test_extract_paths_slash_and_ext():
    text = (
        "see `render_tree.py`, `plan_codegen/`, `src/startd8/navigator/realization.py`"
    )
    paths = vl.extract_paths(text)
    assert "render_tree.py" in paths
    assert "plan_codegen/" in paths
    assert "src/startd8/navigator/realization.py" in paths


def test_extract_paths_skips_shas_and_flags_and_colors():
    text = "`d416fc38` `--flag` `#3a6a94` `plain prose here`"
    assert vl.extract_paths(text) == []


def test_extract_paths_skips_scheme_refs():
    text = "`cc:intent:req-01` and `sha256:abc`"
    assert vl.extract_paths(text) == []


def test_extract_paths_skips_non_path_prose_tokens():
    # elided branch names, HTML fragments, slash-commands, prose arrows, version + dotted-attr refs
    # are all NOT filesystem paths and must not be flagged PHANTOM.
    text = (
        "`feature/…-theme-ee3af56c` `</head>` `/code-review` "
        "`proposed→accepted/rejected` `det-plan/0.1` "
        "`backend_codegen/realization_emit.deterministic_records`"
    )
    assert vl.extract_paths(text) == []


def test_extract_paths_skips_bare_extension_suffix():
    # ".projected.md" is a filename SUFFIX written in prose, not a real file (empty stem).
    text = "each REQ gets a `.projected.md` sibling"
    assert vl.extract_paths(text) == []


def test_extract_paths_keeps_real_module_path():
    # a genuine module path with a real extension is still a path.
    text = "`src/startd8/navigator/realization.py` and bare `govern.py`"
    paths = vl.extract_paths(text)
    assert "src/startd8/navigator/realization.py" in paths
    assert "govern.py" in paths


# ── classify_path: presence≠liveness ────────────────────────────────────────────────────────


def test_classify_path_existing_relative(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "startd8").mkdir()
    target = tmp_path / "src" / "startd8" / "thing.py"
    target.write_text("x = 1\n")
    res = vl.classify_path(tmp_path, "src/startd8/thing.py")
    assert res.live is True


def test_classify_path_phantom(tmp_path):
    res = vl.classify_path(tmp_path, "does/not/exist.py")
    assert res.live is False


def test_classify_path_bare_filename_found_anywhere(tmp_path):
    src = tmp_path / "src" / "pkg"
    src.mkdir(parents=True)
    (src / "render_tree.py").write_text("# tree\n")
    res = vl.classify_path(tmp_path, "render_tree.py")
    assert res.live is True


def test_classify_path_bare_dirname(tmp_path):
    d = tmp_path / "src" / "startd8" / "plan_codegen"
    d.mkdir(parents=True)
    res = vl.classify_path(tmp_path, "plan_codegen/")
    assert res.live is True


def test_classify_path_bare_filename_absent(tmp_path):
    (tmp_path / "src").mkdir()
    res = vl.classify_path(tmp_path, "ghost.py")
    assert res.live is False


# ── parse_implemented_rows ──────────────────────────────────────────────────────────────────


_LEDGER = """# Ledger

## ✅ Implemented (built + landed)

| Artifact | What | State |
|---|---|---|
| **REQ-clean** | `render_tree.py` shipped (`{sha}`) | built |
| **REQ-phantom** | `does/not/exist.py` gone (`{sha}`) | built |
| **REQ-unverifiable** | prose only, no sha no path | built |

---

## Next
"""


def test_parse_skips_header_and_separator():
    rows = vl.parse_implemented_rows(_LEDGER.format(sha="deadbeef"))
    labels = [r.label for r in rows]
    assert labels == ["REQ-clean", "REQ-phantom", "REQ-unverifiable"]


def test_parse_stops_at_next_section():
    text = _LEDGER.format(sha="deadbeef") + "\n| not-a-row | in | next |\n"
    rows = vl.parse_implemented_rows(text)
    # the trailing table is after the "## Next" heading → excluded
    assert all(r.label != "not-a-row" for r in rows)


# ── verify_row / verify_ledger: fixture ledger against a REAL ancestor sha ───────────────────


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _has_git_repo() -> bool:
    root = _repo_root()
    return (
        subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--git-dir"],
            capture_output=True,
        ).returncode
        == 0
    )


def _head_sha() -> str:
    root = _repo_root()
    out = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()


@pytest.mark.skipif(
    not _has_git_repo(), reason="requires a git repo for the LANDED check"
)
def test_verify_ledger_end_to_end(tmp_path):
    root = _repo_root()
    head = _head_sha()
    # a real path that exists under the repo (this very test file's package dir)
    real_path = "tests/unit/test_verify_ledger.py"
    ledger = tmp_path / "ledger.md"
    ledger.write_text(
        "## ✅ Implemented (built + landed)\n\n"
        "| Artifact | What | State |\n"
        "|---|---|---|\n"
        f"| **REQ-clean** | `{real_path}` at (`{head}`) | built |\n"
        "| **REQ-phantom** | `does/not/exist.py` gone | built |\n"
        "| **REQ-unverifiable** | prose only | built |\n"
        "\n---\n"
    )
    report = vl.verify_ledger(ledger, root, ref=head)

    by_label = {r.label: r for r in report.rows}

    clean = by_label["REQ-clean"]
    assert clean.verdict == vl.VERDICT_LIVE
    assert clean.findings == []
    assert head in clean.checked_shas

    phantom = by_label["REQ-phantom"]
    assert phantom.verdict == vl.VERDICT_DRIFT
    assert any(f.startswith("PHANTOM:does/not/exist.py") for f in phantom.findings)

    unver = by_label["REQ-unverifiable"]
    assert unver.verdict == vl.VERDICT_UNVERIFIABLE

    assert report.clean == 1
    assert report.drift == 1
    assert report.unverifiable == 1
    assert report.has_drift is True


@pytest.mark.skipif(
    not _has_git_repo(), reason="requires a git repo for the LANDED check"
)
def test_unlanded_sha_is_drift(tmp_path):
    """A real object that is NOT an ancestor of the chosen ref → UNLANDED (authored≠propagated).

    We fabricate the drift by choosing a ref that HEAD is not an ancestor of: use an empty-tree
    style impossible ancestor. Simpler: pick ref = a KNOWN older commit and sha = HEAD (HEAD is not
    an ancestor of an older commit).
    """
    root = _repo_root()
    head = _head_sha()
    # the parent of HEAD is an older commit; HEAD is NOT an ancestor of HEAD~1.
    parent = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD~1"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not parent:
        pytest.skip("no parent commit available")
    ledger = tmp_path / "ledger.md"
    ledger.write_text(
        "## ✅ Implemented (built + landed)\n\n"
        "| Artifact | What | State |\n"
        "|---|---|---|\n"
        f"| **REQ-unlanded** | claimed at (`{head}`) | built |\n"
        "\n---\n"
    )
    # ref = parent → HEAD is NOT an ancestor of parent → UNLANDED
    report = vl.verify_ledger(ledger, root, ref=parent)
    row = report.rows[0]
    assert row.verdict == vl.VERDICT_DRIFT
    assert any(f == f"UNLANDED:{head}" for f in row.findings)


def test_classify_absence_cross_repo_and_runtime():
    """Enhancement: a benign absence (sibling-repo / runtime artifact) is NOT genuine PHANTOM drift."""
    from scripts.verify_ledger import classify_absence

    assert classify_absence("dev-os/NODE-SCHEMA.md") == "CROSS-REPO"
    assert classify_absence("ContextCore/foo.py") == "CROSS-REPO"
    assert classify_absence("realization-provenance.json") == "RUNTIME"
    assert classify_absence("openapi.json") == "RUNTIME"
    # a genuinely-absent in-repo source path is NOT benign → stays PHANTOM (None here)
    assert classify_absence("HANDOFF_landing-work-onto-reconciled-main.md") is None
    assert classify_absence("src/startd8/real_thing.py") is None
