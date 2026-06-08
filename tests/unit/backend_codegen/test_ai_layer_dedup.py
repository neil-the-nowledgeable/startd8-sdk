"""F-11 — per-pass dedup key for nameless output entities + confirmed-aware re-synthesis.

The generated AI-pass harness `_persist` dedups by `name`. An output entity with no `name` column
(e.g. `Artifact` → only `kind`/`title`/`dataJson`) never trips that guard, so a second run appends
duplicates and clobbers nothing — violating FR-8 ("never clobber a `confirmed:true` row; only add new
unconfirmed"). The fix: `ai_passes.yaml` may declare `dedup_by: <field>`; the generated `_persist`
then dedups by that field with FR-8 semantics — supersede a stale *unconfirmed* row of the key, never
touch a `confirmed:true` one (add alongside).

Two test layers:
- TEXT: assert the generated harness carries the confirmed-aware dedup-by-key logic, and that a pass
  with no `dedup_by` renders byte-identical to today (name-based).
- RUNTIME (importorskip sqlmodel): run the generated `_persist` twice against an in-memory SQLModel
  and check the row counts + confirmed survival (the 4→4 not 8 acceptance).
"""

import py_compile

import pytest

from startd8.backend_codegen import check_drift
from startd8.backend_codegen.ai_layer import (
    parse_ai_passes,
    render_ai_pass,
    render_ai_layer,
)

# `Artifact` is nameless: kind/title/dataJson, plus the provenance columns. A text-mode pass that
# synthesizes Artifacts (F-306 shape). dedup_by: kind — the per-pass re-generation key.
ARTIFACT_SCHEMA = """
model Artifact {
  id        String  @id @default(cuid())
  ownerId   String  @default("local")
  source    String  @default("user")
  confirmed Boolean @default(false)
  kind      String?
  title     String?
  dataJson  String?
}
""".strip()

ARTIFACT_MANIFEST = """
passes:
  - name: generate_artifacts
    output_entities: [Artifact]
    route_path: /generate-artifacts
    prompt: prompts/generate_artifacts.md
    dedup_by: kind
""".strip()

# A name-bearing pass with NO dedup_by — must stay byte-identical to today.
NAMED_SCHEMA = """
model Capability {
  id        String  @id @default(cuid())
  ownerId   String  @default("local")
  source    String  @default("user")
  confirmed Boolean @default(false)
  name      String?
  category  String?
}
""".strip()

NAMED_MANIFEST = """
passes:
  - name: suggest_caps
    output_entities: [Capability]
    route_path: /suggest-caps
    prompt: prompts/suggest_caps.md
""".strip()


# --------------------------------------------------------------------------- #
# Parse
# --------------------------------------------------------------------------- #

def test_parse_dedup_by():
    p = parse_ai_passes(ARTIFACT_MANIFEST)[0]
    assert p.dedup_by == "kind"


def test_parse_dedup_by_default_none():
    assert parse_ai_passes(NAMED_MANIFEST)[0].dedup_by is None


def test_parse_dedup_by_empty_rejected():
    bad = ARTIFACT_MANIFEST.replace("dedup_by: kind", 'dedup_by: ""')
    with pytest.raises(ValueError, match="dedup_by"):
        parse_ai_passes(bad)


def test_parse_dedup_by_unknown_key_still_rejected():
    bad = NAMED_MANIFEST + "\n    dedupby: kind\n"  # typo'd key
    with pytest.raises(ValueError, match="unknown keys"):
        parse_ai_passes(bad)


# --------------------------------------------------------------------------- #
# Generated harness text — confirmed-aware dedup-by-key
# --------------------------------------------------------------------------- #

def test_dedup_harness_carries_confirmed_aware_logic():
    mod = render_ai_pass(ARTIFACT_SCHEMA, ARTIFACT_MANIFEST, "", pass_name="generate_artifacts")
    assert '_DEDUP_FIELD = \'kind\'' in mod or '_DEDUP_FIELD = "kind"' in mod
    # dedups by the declared field, not by name
    assert "getattr(model, _DEDUP_FIELD) == key" in mod
    # FR-8: never touch a confirmed row; supersede stale unconfirmed
    assert 'getattr(r, "confirmed", False)' in mod
    assert "session.delete(stale)" in mod
    # the name-based guard is NOT what this harness uses
    assert "model.name == name" not in mod


def test_dedup_harness_compiles(tmp_path):
    mod = render_ai_pass(ARTIFACT_SCHEMA, ARTIFACT_MANIFEST, "", pass_name="generate_artifacts")
    p = tmp_path / "generate_artifacts.py"
    p.write_text(mod, encoding="utf-8")
    py_compile.compile(str(p), doraise=True)


def test_no_dedup_by_is_byte_identical_name_based():
    """A pass without dedup_by renders exactly the legacy name-based harness (no F-11 leakage)."""
    mod = render_ai_pass(NAMED_SCHEMA, NAMED_MANIFEST, "", pass_name="suggest_caps")
    assert "_DEDUP_FIELD" not in mod
    assert "name-deduped" in mod
    assert "if name and hasattr(model, \"name\"):" in mod
    assert "model.name == name" in mod


def test_dedup_layer_in_sync():
    """The generated dedup harness round-trips through drift cleanly (deterministic by construction)."""
    arts = dict(render_ai_layer(ARTIFACT_SCHEMA, ARTIFACT_MANIFEST, ""))
    mod = arts["app/ai/generate_artifacts.py"]
    assert check_drift(
        ARTIFACT_SCHEMA, mod, manifest_text=ARTIFACT_MANIFEST, human_inputs_text=""
    ).status == "in_sync"


def test_dedup_by_change_is_drift():
    """Changing dedup_by re-renders the harness — a stored copy goes stale (manifest is hashed)."""
    arts = dict(render_ai_layer(ARTIFACT_SCHEMA, ARTIFACT_MANIFEST, ""))
    mod = arts["app/ai/generate_artifacts.py"]
    m2 = ARTIFACT_MANIFEST.replace("dedup_by: kind", "dedup_by: title")
    assert check_drift(ARTIFACT_SCHEMA, mod, manifest_text=m2, human_inputs_text="").status == "stale"


# --------------------------------------------------------------------------- #
# Runtime — the 4→4 (not 8) + confirmed-survival acceptance
# --------------------------------------------------------------------------- #

def test_dedup_persist_runtime_resynthesis(tmp_path):
    """Drive the generated `_persist` twice against a real in-memory SQLModel (FR-8 acceptance)."""
    pytest.importorskip("sqlmodel")
    from sqlmodel import Session, SQLModel, create_engine, select

    # Generate + load the harness module standalone (it imports app.* — patch those symbols in).
    import sys

    arts = dict(render_ai_layer(ARTIFACT_SCHEMA, ARTIFACT_MANIFEST, ""))
    tables_src = dict(__import__("startd8.backend_codegen", fromlist=["render_backend"]).render_backend(
        ARTIFACT_SCHEMA, manifest_text=ARTIFACT_MANIFEST, human_inputs_text=""
    ))["app/tables.py"]

    # Build a minimal `app` package on disk and import the real generated tables + harness.
    pkg = tmp_path / "app"
    (pkg / "ai").mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "ai" / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "tables.py").write_text(tables_src, encoding="utf-8")
    # service + edge_schemas are imported by the harness at module load; provide the real ones.
    (pkg / "ai" / "edge_schemas.py").write_text(arts["app/ai/edge_schemas.py"], encoding="utf-8")
    # the harness imports `from app.ai.service import call_ai_service` at module top — stub it.
    (pkg / "ai" / "service.py").write_text(
        "def call_ai_service(*a, **k):\n    raise RuntimeError('not called in this test')\n",
        encoding="utf-8",
    )
    (pkg / "db.py").write_text("def get_session():\n    raise RuntimeError('unused')\n", encoding="utf-8")
    (pkg / "ai" / "generate_artifacts.py").write_text(
        arts["app/ai/generate_artifacts.py"], encoding="utf-8"
    )

    sys.path.insert(0, str(tmp_path))
    _purge = [m for m in sys.modules if m == "app" or m.startswith("app.")]
    for m in _purge:
        del sys.modules[m]
    # Drop any leftover SQLModel table for Artifact from the shared metadata.
    md = SQLModel.metadata
    if md.tables.get("artifact") is not None:
        md.remove(md.tables["artifact"])
    try:
        tables = __import__("app.tables", fromlist=["Artifact"])
        mod = __import__("app.ai.generate_artifacts", fromlist=["_persist"])
        from app.ai.edge_schemas import ArtifactEdge  # noqa: E402

        engine = create_engine(f"sqlite:///{tmp_path}/dedup.db")
        SQLModel.metadata.create_all(engine)

        kinds = ["value-summary", "pitch-10s", "pitch-30s", "pitch-60s"]

        def _run_pass(session):
            for k in kinds:
                edge = ArtifactEdge(kind=k, title=f"{k} title", dataJson="{}")
                mod._persist(session, tables.Artifact, edge)
            session.commit()

        # First run → 4 unconfirmed Artifacts.
        with Session(engine) as s:
            _run_pass(s)
        with Session(engine) as s:
            rows = s.exec(select(tables.Artifact)).all()
        assert len(rows) == 4, f"first run should create 4, got {len(rows)}"

        # User confirms ONE of them (value-summary) — and edits its title to a curated value.
        with Session(engine) as s:
            vs = s.exec(
                select(tables.Artifact).where(tables.Artifact.kind == "value-summary")
            ).one()
            vs.confirmed = True
            vs.title = "USER CURATED SUMMARY"
            s.add(vs)
            s.commit()
            confirmed_id = vs.id

        # Second run → the 3 unconfirmed kinds are SUPERSEDED (replaced, not duplicated); the
        # confirmed value-summary survives AND a fresh value-summary proposal is added alongside it.
        with Session(engine) as s:
            _run_pass(s)
        with Session(engine) as s:
            rows = s.exec(select(tables.Artifact)).all()
            by_kind = {}
            for r in rows:
                by_kind.setdefault(r.kind, []).append(r)
            # the confirmed row survived byte-identical
            survivor = s.exec(
                select(tables.Artifact).where(tables.Artifact.id == confirmed_id)
            ).one()

        # 3 unconfirmed kinds stayed singletons (no duplication: 4 stays 4 for those).
        for k in ["pitch-10s", "pitch-30s", "pitch-60s"]:
            assert len(by_kind[k]) == 1, f"{k} should not duplicate, got {len(by_kind[k])}"
        # the confirmed row is untouched and a new unconfirmed proposal sits alongside it
        assert survivor.confirmed is True
        assert survivor.title == "USER CURATED SUMMARY"
        assert len(by_kind["value-summary"]) == 2  # confirmed survivor + fresh proposal
        new_vs = [r for r in by_kind["value-summary"] if r.id != confirmed_id]
        assert len(new_vs) == 1 and new_vs[0].confirmed is False
        # total: 3 (singletons) + 2 (confirmed + new) = 5 — never 8 (no blind append)
        assert len(rows) == 5
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))
        for m in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
            del sys.modules[m]
        if md.tables.get("artifact") is not None:
            md.remove(md.tables["artifact"])
