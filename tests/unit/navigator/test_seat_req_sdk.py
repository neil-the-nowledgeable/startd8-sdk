"""Seat-req SDK slice — the two CRP-flagged fixes that live in src/startd8/navigator/ (FR-4 R1-F1 +
FR-6 R1-F4). The rest of the seat-req (Definer emit, roundtrip, req-health, CC a11y) is delegated to the
dev-os + ContextCore teams via handoff .md."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from startd8.cli import app
from startd8.navigator.sources_requirements import nodes_from_requirements

RUNNER = CliRunner()


def _doc(tmp_path, fr_lines):
    doc = tmp_path / "REQ-x.md"
    doc.write_text("# X — Requirements\n\n**Format:** det-req/0.1\n\n## Functional requirements\n\n"
                   + "\n".join(fr_lines) + "\n", encoding="utf-8")
    return doc


# ── FR-4 (R1-F1) — a mined Touches ref must NOT clear the done-claim evidence gate ─────────────────

def test_fr4_touches_mined_ref_does_not_clear_the_health_gate(tmp_path):
    # a done-claim FR (Verify (done): ...) with NO authored Lives but a real Touches path → its health
    # must stay `unknown` (the mined ref is derived, not authored evidence) — agreeing with the twins.
    real = "src/startd8/navigator/models.py"           # a path that exists on disk (mined into lives)
    doc = _doc(tmp_path, [
        f"- **FR-1 — Done thing.** does. Name: a done thing. Touches: `{real}`. "
        f"Verify (done): it works. Serves: O-1",
    ])
    n = nodes_from_requirements(doc, repo=tmp_path.parents[6] if False else None)[0]
    assert n.attributes["fr_health"] == "unknown"      # done-claim + only mined refs → unknown (R1-F1)

    # an FR with an AUTHORED strong git Lives clears it → on_track
    doc2 = _doc(tmp_path, [
        "- **FR-1 — Done.** does. Name: a done thing. "
        "Lives: code git:" + "a" * 40 + ":src/x.py. Verify (done): it works. Serves: O-1",
    ])
    assert nodes_from_requirements(doc2)[0].attributes["fr_health"] == "on_track"


# ── FR-6 (R1-F4) — the parse-loss floor: a dropped FR exits non-zero, not a silent short render ────

def test_fr6_parse_loss_floor_exits_nonzero_on_a_dropped_fr(tmp_path):
    # a `- **FR-...` bullet that does NOT parse as an FR (prose commentary, or a hard-wrap that broke the
    # `— Title.**` structure) → marker count > projected node count → non-zero exit with a named parse-loss.
    doc = _doc(tmp_path, [
        "- **FR-1 — Fine.** does. Name: a fine thing. Verify: ok. Serves: O-1",
        "- **FR-2's evidence gate is the point.** a prose bullet — a marker that doesn't parse as an FR.",
    ])
    res = RUNNER.invoke(app, ["navigator", "build", "--source", "requirements",
                              "--requirements", str(doc), "--format", "json"])
    assert res.exit_code != 0 and "parse-loss" in res.output

    # a clean source (every FR one physical line) builds fine
    clean = _doc(tmp_path, [
        "- **FR-1 — A.** does. Name: thing a. Verify: ok. Serves: O-1",
        "- **FR-2 — B.** does. Name: thing b. Verify: ok. Serves: O-1",
    ])
    res2 = RUNNER.invoke(app, ["navigator", "build", "--source", "requirements",
                               "--requirements", str(clean), "--format", "json"])
    assert res2.exit_code == 0 and len(json.loads(res2.stdout)["nodes"]) == 2
