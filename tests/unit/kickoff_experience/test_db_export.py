"""DB → inputs/*.yaml exporter (the Option-B bridge)."""

from __future__ import annotations

import sqlite3
import textwrap
from pathlib import Path

import pytest

from startd8.kickoff_experience.db_export import FieldMapping, export_db_rows

CONVENTIONS = textwrap.dedent(
    """\
    # header — must survive
    domain: conventions
    provenance_default: authored
    language: python
    stack:
      framework: fastapi
    data_model:
      money: cents
      datetime: utc
    """
)


def _make_db(path: Path, **cols: str) -> None:
    con = sqlite3.connect(str(path))
    con.execute(
        "CREATE TABLE conventioninput "
        "(id TEXT, language TEXT, framework TEXT, money TEXT, tzPolicy TEXT, createdAt TEXT)"
    )
    con.execute(
        "INSERT INTO conventioninput VALUES (?,?,?,?,?,?)",
        ("c1", cols.get("language", "python"), cols.get("framework", "fastapi"),
         cols.get("money", "float"), cols.get("tzPolicy", "local"), "2026-01-01"),
    )
    con.commit()
    con.close()


@pytest.fixture
def project(tmp_path: Path) -> Path:
    inputs = tmp_path / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "conventions.yaml").write_text(CONVENTIONS, encoding="utf-8")
    return tmp_path


def test_export_writes_db_value_into_inputs_yaml(project: Path, tmp_path: Path) -> None:
    db = tmp_path / "wm.db"
    _make_db(db, money="float", tzPolicy="local")
    mapping = [
        FieldMapping("conventioninput", "money", "conventions.yaml#/data_model.money"),
        FieldMapping("conventioninput", "tzPolicy", "conventions.yaml#/data_model.datetime"),
    ]
    results = export_db_rows(project, db, mapping)
    assert all(r.ok for r in results), results
    on_disk = (project / "docs/kickoff/inputs/conventions.yaml").read_text()
    assert "money: float" in on_disk
    assert "datetime: local" in on_disk
    assert "# header — must survive" in on_disk  # M6 merge fidelity preserved


def test_export_reports_no_row_when_table_empty(project: Path, tmp_path: Path) -> None:
    db = tmp_path / "empty.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE conventioninput (id TEXT, money TEXT, createdAt TEXT)")
    con.commit()
    con.close()
    results = export_db_rows(
        project, db, [FieldMapping("conventioninput", "money", "conventions.yaml#/data_model.money")]
    )
    assert results[0].code == "no_row"


def test_export_records_capture_refusal_per_field(project: Path, tmp_path: Path) -> None:
    db = tmp_path / "wm.db"
    _make_db(db)
    # A value_path not in the M3 allow-list is refused by M6 and recorded, not raised.
    results = export_db_rows(
        project, db, [FieldMapping("conventioninput", "money", "conventions.yaml#/not_allowed")]
    )
    assert results[0].code == "value_path_not_allowed"
    assert not results[0].ok


def test_export_rejects_unsafe_identifiers(project: Path, tmp_path: Path) -> None:
    db = tmp_path / "wm.db"
    _make_db(db)
    with pytest.raises(ValueError):
        export_db_rows(
            project, db,
            [FieldMapping("conventioninput; DROP TABLE x", "money", "conventions.yaml#/data_model.money")],
        )
