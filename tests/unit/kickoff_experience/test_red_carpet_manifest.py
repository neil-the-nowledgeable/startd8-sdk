"""Red Carpet Treatment N1 — the `manifest` proposal kind: prose → confined project-tree manifest.

The proposal supplies authoring PROSE, never a path. The server extracts (round-trip-gated), maps each
yielded manifest to its server-derived `CONVENTION_PATHS` destination (R1-F2), refuses to clobber by
default (R1-F3), and overwrites only on `replace`. These tests pin the security-critical invariants.
"""

from __future__ import annotations

from pathlib import Path

from startd8.kickoff_experience.proposals import (
    ProposalBuffer,
    ProposedAction,
    apply_proposal,
    make_propose_handler,
)

# §2.2 Pages — extracts to pages.yaml (→ prisma/pages.yaml), needs no schema.
_PAGES = """## Pages

| Page | Purpose | Content file |
|------|---------|--------------|
| Home | the landing page | home.md |
| About | about the project | about.md |
"""


def _manifest(source: str, **params) -> ProposedAction:
    return ProposedAction(kind="manifest", params={"source": source, **params}, id="m1")


def test_manifest_materializes_to_server_derived_dest(tmp_path: Path) -> None:
    out = apply_proposal(tmp_path, _manifest(_PAGES))
    assert out.ok, out
    dest = tmp_path / "prisma" / "pages.yaml"          # the CONVENTION_PATHS["pages"] destination
    assert dest.is_file() and "Home" in dest.read_text()


def test_manifest_missing_source_rejected(tmp_path: Path) -> None:
    out = apply_proposal(tmp_path, _manifest("   "))
    assert out.code == "missing_source" and not out.ok
    assert not (tmp_path / "prisma").exists()


def test_manifest_no_clobber_then_replace(tmp_path: Path) -> None:
    assert apply_proposal(tmp_path, _manifest(_PAGES)).ok
    dest = tmp_path / "prisma" / "pages.yaml"
    dest.write_text("# hand-edited — do not lose\n")    # simulate a hand edit between stages
    blocked = apply_proposal(tmp_path, _manifest(_PAGES))
    assert blocked.code == "would_clobber" and not blocked.ok
    assert dest.read_text() == "# hand-edited — do not lose\n"   # unchanged (no-clobber)
    ok = apply_proposal(tmp_path, _manifest(_PAGES, replace=True))
    assert ok.ok and "Home" in dest.read_text()         # replace overwrites


def test_manifest_dest_is_server_derived_not_from_payload(tmp_path: Path) -> None:
    # R1-F2: a payload-supplied path/dest is IGNORED — the writer derives the dest from the extracted
    # manifest + CONVENTION_PATHS, so a traversal attempt in params cannot escape the project tree.
    out = apply_proposal(tmp_path, _manifest(
        _PAGES, dest="../../etc/evil.yaml", path="/etc/evil.yaml"))
    assert out.ok
    assert (tmp_path / "prisma" / "pages.yaml").is_file()         # went to the convention dest
    assert not (tmp_path.parent / "etc").exists()                # no escape outside the root


def test_propose_handler_records_manifest(tmp_path: Path) -> None:
    buf = ProposalBuffer()
    handler = make_propose_handler(tmp_path, buf)
    ack = handler({"kind": "manifest", "source": _PAGES, "source_label": "pages.md"})
    assert "recorded" in ack.lower()
    assert len(buf.pending()) == 1 and buf.pending()[0].kind == "manifest"
    err = handler({"kind": "manifest", "source": ""})
    assert err.startswith("error:") and len(buf.pending()) == 1   # empty prose rejected at propose
