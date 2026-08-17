"""REQ-19 FR-2 live-wiring — `generate backend --emit-realization-provenance` writes the artifact."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from startd8.cli import app
from startd8.navigator.realization_contract import parse_record

RUNNER = CliRunner()

_SCHEMA = """
datasource db { provider = "sqlite"; url = "file:./dev.db" }
generator client { provider = "prisma-client-py" }

model Profile {
  id    Int    @id @default(autoincrement())
  name  String
}
"""


def test_generate_backend_emits_realization_provenance(tmp_path):
    schema = tmp_path / "schema.prisma"
    schema.write_text(_SCHEMA, encoding="utf-8")
    out = tmp_path / "gen"
    res = RUNNER.invoke(app, ["generate", "backend", "--schema", str(schema), "--out", str(out),
                             "--emit-realization-provenance"])
    assert res.exit_code == 0, res.output
    prov = out / "realization-provenance.json"
    assert prov.exists(), "the provenance artifact was not written"
    data = json.loads(prov.read_text())
    recs = data["records"]
    assert recs and all(r["regime"] == "deterministic" and r["source_confidence"] == 1.0 for r in recs)
    for r in recs:                     # every emitted record conforms to the contract
        parse_record(r)
    # off by default → no artifact (additive, zero effect on existing runs)
    out2 = tmp_path / "gen2"
    RUNNER.invoke(app, ["generate", "backend", "--schema", str(schema), "--out", str(out2)])
    assert not (out2 / "realization-provenance.json").exists()
