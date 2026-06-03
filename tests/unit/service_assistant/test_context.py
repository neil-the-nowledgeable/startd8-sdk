"""Project-context enrichment tests (FR-5), incl. the ContextManifest CRD shape."""

from startd8.service_assistant.context import _project_id_from_yaml, load_project_context


def test_contextmanifest_crd_shape():
    # The real .contextcore.yaml is a contextcore.io/v1alpha2 ContextManifest:
    # project id lives at spec.project.id (found via the run-026 real-world test).
    data = {
        "apiVersion": "contextcore.io/v1alpha2",
        "kind": "ContextManifest",
        "metadata": {"name": "startd8/run-026"},
        "spec": {"project": {"id": "startd8/run-026", "name": "Startd8 Run 026"}},
    }
    assert _project_id_from_yaml(data) == "startd8/run-026"


def test_flat_shapes_still_work():
    assert _project_id_from_yaml({"project": {"id": "p1"}}) == "p1"
    assert _project_id_from_yaml({"project_id": "p2"}) == "p2"
    assert _project_id_from_yaml({"project": "p3"}) == "p3"


def test_metadata_name_fallback():
    assert _project_id_from_yaml({"metadata": {"name": "p4"}}) == "p4"


def test_no_project_id():
    assert _project_id_from_yaml({"spec": {"business": {}}}) is None


def test_load_from_yaml_walks_up(tmp_path):
    run_dir = tmp_path / "run-001" / "plan-ingestion"
    run_dir.mkdir(parents=True)
    (run_dir.parent / ".contextcore.yaml").write_text(
        "apiVersion: contextcore.io/v1alpha2\nkind: ContextManifest\n"
        "spec:\n  project:\n    id: demo-proj\n",
        encoding="utf-8",
    )
    pc = load_project_context(run_dir)
    assert pc.project_id == "demo-proj"
    assert pc.source == "contextcore_yaml"  # no ~/.contextcore/state for this id


def test_no_yaml_degrades_to_none(tmp_path):
    run_dir = tmp_path / "run-002" / "plan-ingestion"
    run_dir.mkdir(parents=True)
    pc = load_project_context(run_dir)
    assert pc.source == "none"
    assert pc.project_id is None
