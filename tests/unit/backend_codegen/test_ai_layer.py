"""M-C — owned AI-layer generation from a manifest.

Proves the run-021..026 glue-bug class is impossible by construction: imports come from the
generator's own symbol table (no `from ai.x`, no bare `import get_session`), the router is
single-prefixed, server.py mounts the owned app, and the edge schema omits human-only fields (C-4).
"""

import py_compile

import pytest

from startd8.backend_codegen import render_backend, check_drift
from startd8.backend_codegen.ai_layer import (
    parse_ai_passes,
    parse_human_inputs,
    render_ai_layer,
)

SCHEMA = """
model Profile {
  id   String @id @default(cuid())
  name String
}

model Metric {
  id        String  @id @default(cuid())
  name      String
  unit      String?
  value     Float?
  source    String?
  confirmed Boolean @default(false)
}
""".strip()

MANIFEST = """
passes:
  - name: extract_metrics
    input_entities: [Profile]
    output_entities: [Metric]
    route_path: /extract-metrics
    prompt: prompts/extract_metrics.md
""".strip()

HUMAN = "fields:\n  - target: Metric.value\n    authored_by: human\n    test_default: 42.0\n"


def _files(manifest=MANIFEST, human=HUMAN):
    return dict(render_ai_layer(SCHEMA, manifest, human))


# --------------------------------------------------------------------------- #
# Strict manifest parsing (FR-MA-5)
# --------------------------------------------------------------------------- #

def test_parse_valid_manifest():
    passes = parse_ai_passes(MANIFEST)
    assert len(passes) == 1
    assert passes[0].name == "extract_metrics"
    assert passes[0].output_entities == ("Metric",)
    assert passes[0].route_path == "/extract-metrics"


@pytest.mark.parametrize("bad", [
    "passes:\n  - name: x\n",  # missing required keys
    "passes:\n  - name: x\n    output_entities: [M]\n    route_path: nope\n    prompt: p",  # route no /
    "passes: []",  # no passes
    "{}",  # no passes key
    "passes:\n  - name: x\n    output_entities: [M]\n    route_path: /x\n    prompt: p\n    bogus: 1",  # unknown key
])
def test_parse_rejects_malformed(bad):
    with pytest.raises(ValueError):
        parse_ai_passes(bad)


def test_parse_rejects_duplicate_names():
    dup = MANIFEST + "\n  - name: extract_metrics\n    output_entities: [Metric]\n    route_path: /m2\n    prompt: p"
    with pytest.raises(ValueError):
        parse_ai_passes(dup)


def test_human_inputs_parse():
    hi = parse_human_inputs(HUMAN)
    assert ("Metric", "value") in hi.human_only_fields
    assert parse_human_inputs(None).human_only_fields == frozenset()


# --------------------------------------------------------------------------- #
# Edge schema projection (C-4 / FR-6)
# --------------------------------------------------------------------------- #

def test_edge_schema_omits_human_only_provenance_and_id():
    edge = _files()["app/ai/edge_schemas.py"]
    block = edge.split("class MetricEdge")[1].split("EDGE_SCHEMAS")[0]
    assert "value:" not in block          # human-only (FR-6) — the cardinal omission
    assert "source:" not in block         # provenance — harness-owned
    assert "confirmed:" not in block      # provenance — harness-owned
    assert "id:" not in block             # PK — DB-owned
    assert "name: str" in block           # ordinary scalar kept
    assert "unit: Optional[str]" in block


# --------------------------------------------------------------------------- #
# Correct imports by construction (the run-021..026 bug class, impossible)
# --------------------------------------------------------------------------- #

def test_router_imports_are_correct_single_prefixed():
    routes = _files()["app/ai/routes.py"]
    assert "from app.ai.extract_metrics import extract_metrics" in routes  # real pass, app.ai.* root
    assert "from app.db import get_session" in routes                      # owned sync session
    assert 'APIRouter(prefix="/ai"' in routes
    assert "'/extract-metrics'" in routes or '"/extract-metrics"' in routes
    assert "from ai." not in routes        # the run-023 wrong-root bug — impossible
    assert "/ai/extract-metrics" not in routes  # no double prefix (run-021)


def test_service_and_server_imports():
    f = _files()
    svc = f["app/ai/service.py"]
    assert "from app.tables import AiCall" in svc           # C-3: AiCall from tables, not models
    assert "from startd8.utils.agent_resolution import resolve_agent_spec" in svc  # B2
    assert "from app.db import get_session" in svc          # C-1 sync session
    assert "AsyncSession" not in svc                        # C-1
    server = f["app/server.py"]
    assert "from app.main import app" in server and "ai_router" in server
    assert "APIRouter" not in server                        # FR-MA-4: no routes of its own


def test_pass_harness_imports_no_wrong_root():
    pass_mod = _files()["app/ai/extract_metrics.py"]
    assert "from app.ai.service import call_ai_service" in pass_mod
    assert "from app.ai.edge_schemas import MetricEdge" in pass_mod
    assert "from app.tables import" in pass_mod
    assert "import get_session" not in pass_mod  # the run-025 bare-import bug — impossible
    assert "from ai." not in pass_mod


def test_everything_compiles(tmp_path):
    for rel, content in render_ai_layer(SCHEMA, MANIFEST, HUMAN):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        if rel.endswith(".py"):
            py_compile.compile(str(p), doraise=True)


# --------------------------------------------------------------------------- #
# Three-input drift + backward compatibility
# --------------------------------------------------------------------------- #

def test_ai_files_in_sync_and_stale_on_any_input_change():
    arts = render_backend(SCHEMA, manifest_text=MANIFEST, human_inputs_text=HUMAN)
    server = dict(arts)["app/server.py"]
    assert check_drift(SCHEMA, server, manifest_text=MANIFEST, human_inputs_text=HUMAN).status == "in_sync"
    # manifest change → stale
    m2 = MANIFEST + "\n    request_field: text\n"
    assert check_drift(SCHEMA, server, manifest_text=m2, human_inputs_text=HUMAN).status == "stale"
    # human-inputs change → stale
    assert check_drift(SCHEMA, server, manifest_text=MANIFEST, human_inputs_text="fields: []\n").status == "stale"


def test_spine_unaffected_by_manifest_change():
    arts = render_backend(SCHEMA, manifest_text=MANIFEST, human_inputs_text=HUMAN)
    models = dict(arts)["app/models.py"]
    m2 = MANIFEST + "\n    request_field: text\n"
    assert check_drift(SCHEMA, models, manifest_text=m2, human_inputs_text=HUMAN).status == "in_sync"


def test_no_manifest_means_no_ai_layer():
    arts = dict(render_backend(SCHEMA))
    assert not any(r.startswith("app/ai/") or r == "app/server.py" for r in arts)
