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
  id        String   @id @default(cuid())
  ownerId   String   @default("local")
  name      String
  unit      String?
  value     Float?
  source    String?
  confirmed Boolean  @default(false)
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
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


def test_plain_text_mode_multi_output_is_flagged_not_silently_dropped():
    # A plain text-mode pass (no input_entities / scope / source_binding) renders via
    # _render_pass_text, which persists only output_entities[0]. A second output entity
    # was silently DROPPED at generation; it must now raise a clear named error.
    multi = (
        "passes:\n"
        "  - name: extract_both\n"
        "    output_entities: [Capability, Outcome]\n"
        "    route_path: /extract-both\n"
        "    prompt: p\n"
    )
    with pytest.raises(ValueError, match=r"extract_both.*one output entity|one output entity"):
        parse_ai_passes(multi)


def test_read_mode_still_allows_multiple_output_entities():
    # Byte-parity anchor: a READ-mode pass (has input_entities) legitimately writes
    # multiple entities (the strtd8 multi-value Writes shape) — must NOT be rejected.
    read_multi = (
        "passes:\n"
        "  - name: suggest\n"
        "    input_entities: [ProofPoint]\n"
        "    output_entities: [Capability, Outcome]\n"
        "    route_path: /suggest\n"
        "    prompt: p\n"
    )
    passes = parse_ai_passes(read_multi)
    assert passes[0].output_entities == ("Capability", "Outcome")


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
    assert "ownerId" not in block         # ownership — DB-owned default (str → never AI-authored)
    assert "createdAt" not in block       # timestamp — DB-owned default; str→datetime would crash commit
    assert "updatedAt" not in block       # timestamp — DB-owned default
    assert "name: str" in block           # ordinary scalar kept
    assert "unit: Optional[str]" in block


def test_persist_helper_drops_server_managed_fields():
    """The generated _persist must never forward server-managed columns into a row (defense in
    depth to the edge-schema omission): str timestamps must not reach SQLModel datetime columns."""
    pass_mod = _files()["app/ai/extract_metrics.py"]
    assert "_server_managed" in pass_mod
    for f in ("createdAt", "updatedAt", "ownerId"):
        assert f in pass_mod.split("_server_managed")[1].split("\n")[0]  # named in the guard set
    assert "k not in _server_managed" in pass_mod


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


def test_ai_service_emits_startd8_cost_metrics():
    # Wiring fix: a deployed app's LLM usage must be QUERYABLE (startd8.cost.*), not only
    # AiCall DB rows. The emit must be present, guarded, and independent of DB logging.
    svc = _files()["app/ai/service.py"]
    assert "from startd8.costs.otel_metrics import CostMetrics" in svc   # reuse the SDK emitter
    assert "_COST_METRICS" in svc and "_COST_METRICS.record(" in svc     # actually emits
    assert "total_cost=" in svc and "output_tokens=" in svc             # the SLI-shaped fields
    # Guarded: absent OTel/startd8.costs ⇒ _COST_METRICS = None, no-op (app boots identically).
    assert "_COST_METRICS = None" in svc
    assert "if _COST_METRICS is not None:" in svc


def test_ai_service_cost_emit_survives_compile(tmp_path):
    # The generated cost-emit code must be valid Python (the wiring can't break the app).
    svc = _files()["app/ai/service.py"]
    p = tmp_path / "service.py"
    p.write_text(svc, encoding="utf-8")
    py_compile.compile(str(p), doraise=True)


_RENAMED_TS_SCHEMA = SCHEMA.replace(
    "updatedAt DateTime @updatedAt", "modifiedAt DateTime @updatedAt"
).replace(
    "createdAt DateTime @default(now())", "insertedAt DateTime @default(now())"
)


class TestServerManagedFieldsSchemaDerived:
    """#260: server-managed fields are dropped by SCHEMA ATTRIBUTE, not a hardcoded name list —
    a user-renamed @updatedAt / @default(now()) timestamp must not leak into the AI surface."""

    def _files_renamed(self):
        return dict(render_ai_layer(_RENAMED_TS_SCHEMA, MANIFEST, HUMAN))

    def test_renamed_timestamp_not_in_ai_edit_write_surface(self):
        # the edge (tool-input) schema is the write-gate — a renamed timestamp must NOT appear.
        edge = self._files_renamed()["app/ai/edge_schemas.py"]
        assert "modifiedAt" not in edge   # @updatedAt, renamed
        assert "insertedAt" not in edge   # @default(now()), renamed
        # a real content field is still writable.
        assert "unit" in edge

    def test_generated_helpers_bake_the_renamed_names(self):
        pass_mod = self._files_renamed()["app/ai/extract_metrics.py"]
        # the _summary/_persist skip set carries the ACTUAL renamed names, not just the convention.
        assert '"modifiedAt"' in pass_mod and '"insertedAt"' in pass_mod
        assert "__STARTD8_SERVER_MANAGED__" not in pass_mod  # placeholder fully substituted

    def test_default_convention_is_byte_identical(self):
        # a conventionally-named schema bakes the exact historical literal (no drift).
        pass_mod = _files()["app/ai/extract_metrics.py"]
        assert '{"id", "ownerId", "source", "confirmed", "createdAt", "updatedAt"}' in pass_mod


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


# --------------------------------------------------------------------------- #
# Harness modes (M-C polish): read-mode (DB-driven, multi-output) vs text-mode
# --------------------------------------------------------------------------- #

MULTI_MANIFEST = """
passes:
  - name: suggest_caps
    input_entities: [Profile]
    output_entities: [Capability, Outcome]
    route_path: /caps
    prompt: prompts/caps.md
""".strip()

CAP_SCHEMA = SCHEMA + """

model Capability {
  id        String  @id @default(cuid())
  name      String?
  category  String?
  source    String?
  confirmed Boolean @default(false)
}

model Outcome {
  id        String  @id @default(cuid())
  name      String?
  source    String?
  confirmed Boolean @default(false)
}
"""

TEXT_MANIFEST = """
passes:
  - name: extract_one
    output_entities: [Metric]
    route_path: /extract
    prompt: prompts/extract.md
""".strip()


def test_read_mode_harness_is_session_only_and_multi_output():
    files = dict(render_ai_layer(CAP_SCHEMA, MULTI_MANIFEST, ""))
    pass_mod = files["app/ai/suggest_caps.py"]
    assert "def suggest_caps(session: Session) -> dict[str, Any]:" in pass_mod
    assert "select(model).where(model.confirmed.is_(True))" in pass_mod   # reads confirmed inputs
    assert "class SuggestCapsResult" in pass_mod                          # combined result schema
    assert "capabilities: list[CapabilityEdge]" in pass_mod
    assert "outcomes: list[OutcomeEdge]" in pass_mod                      # multi-output
    assert 'row.source = "ai"' in pass_mod and "row.confirmed = False" in pass_mod
    # router route for a read-mode pass is body-less (no _Request)
    routes = files["app/ai/routes.py"]
    assert "def post_suggest_caps(session: Session = Depends(get_session))" in routes


def test_text_mode_harness_keeps_free_text_signature():
    files = dict(render_ai_layer(CAP_SCHEMA, TEXT_MANIFEST, ""))
    pass_mod = files["app/ai/extract_one.py"]
    assert "def extract_one(text: str, session: Session)" in pass_mod
    assert "call_ai_service('extract_one', full_prompt, MetricEdge, session)" in pass_mod
    routes = files["app/ai/routes.py"]
    assert "class _Request(BaseModel)" in routes      # text mode → request body
    assert "body: _Request" in routes


def test_read_mode_compiles(tmp_path):
    for rel, content in render_ai_layer(CAP_SCHEMA, MULTI_MANIFEST, ""):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        if rel.endswith(".py"):
            py_compile.compile(str(p), doraise=True)


def test_naming_helpers():
    from startd8.backend_codegen.ai_layer import _pascal, _plural_field, _snake

    assert _snake("ValueProp") == "value_prop"
    assert _pascal("suggest_caps") == "SuggestCaps"
    assert _plural_field("Capability") == "capabilities"
    assert _plural_field("Outcome") == "outcomes"
    assert _plural_field("ValueProp") == "value_props"


# ---------------------------------------------------------------------------
# Surface 3 / MODEL_CONFIG — configurable generated-app agent spec + drift
# ---------------------------------------------------------------------------

from startd8.backend_codegen.ai_layer import (  # noqa: E402
    render_ai_service,
    _DEFAULT_AI_AGENT_SPEC,
)


def test_default_agent_spec_baked_and_self_described():
    svc = render_ai_service(SCHEMA, MANIFEST, HUMAN)
    assert f'DEFAULT_AGENT_SPEC = "{_DEFAULT_AI_AGENT_SPEC}"' in svc
    assert f"# ai-agent-spec: {_DEFAULT_AI_AGENT_SPEC}" in svc
    assert "__AI_AGENT_SPEC__" not in svc  # placeholder fully substituted


def test_custom_agent_spec_baked_and_self_described():
    svc = render_ai_service(SCHEMA, MANIFEST, HUMAN, ai_agent_spec="gemini:gemini-2.5-pro")
    assert 'DEFAULT_AGENT_SPEC = "gemini:gemini-2.5-pro"' in svc
    assert "# ai-agent-spec: gemini:gemini-2.5-pro" in svc
    assert "anthropic:claude-opus-4-8" not in svc  # no leak of the default


def test_render_ai_layer_threads_agent_spec():
    files = dict(render_ai_layer(SCHEMA, MANIFEST, HUMAN, ai_agent_spec="openai:gpt-5.5"))
    assert 'DEFAULT_AGENT_SPEC = "openai:gpt-5.5"' in files["app/ai/service.py"]


def test_custom_spec_service_reads_in_sync():
    """The drift-hash fix: a service.py baked with a non-default provider must
    NOT read as drift — drift recovers the embedded spec and re-renders it."""
    svc = render_ai_service(SCHEMA, MANIFEST, HUMAN, ai_agent_spec="gemini:gemini-2.5-pro")
    result = check_drift(SCHEMA, svc, manifest_text=MANIFEST, human_inputs_text=HUMAN)
    assert result.status == "in_sync", result.detail


def test_tampered_custom_spec_service_detected():
    svc = render_ai_service(SCHEMA, MANIFEST, HUMAN, ai_agent_spec="gemini:gemini-2.5-pro")
    tampered = svc.replace("def call_ai_service", "def call_ai_service_HANDEDIT")
    result = check_drift(SCHEMA, tampered, manifest_text=MANIFEST, human_inputs_text=HUMAN)
    assert result.status != "in_sync"


def test_drift_fix_is_load_bearing():
    """Without spec recovery, the default re-render would differ from a custom-spec file."""
    gem = render_ai_service(SCHEMA, MANIFEST, HUMAN, ai_agent_spec="gemini:gemini-2.5-pro")
    anth = render_ai_service(SCHEMA, MANIFEST, HUMAN, ai_agent_spec="anthropic:claude-opus-4-8")
    assert gem != anth


# --------------------------------------------------------------------------- #
# Source-binding opt-out (`source_binding: none`) — the §7 convention-over-     #
# configuration escape hatch. Derivation auto-binds when a text-mode pass's     #
# single output entity carries a server-managed loose-ref field; `none` lets an #
# app whose entity matches that shape by coincidence stay unbound.              #
# --------------------------------------------------------------------------- #

from startd8.backend_codegen.ai_layer import effective_source_binding  # noqa: E402

# A schema whose ProofPoint entity carries a server-managed loose-ref field
# (optional String, not PK, human-owned) — the exact derivation shape.
_BIND_SCHEMA = """
model ProofPoint {
  id               String  @id @default(cuid())
  ownerId          String  @default("local")
  source           String  @default("user")
  confirmed        Boolean @default(false)
  title            String?
  sourceDocumentId String?
}
""".strip()

_BIND_HUMAN = (
    "fields:\n"
    "  - target: ProofPoint.sourceDocumentId\n"
    "    authored_by: human\n"
)


def _bind_manifest(extra: str = "") -> str:
    return (
        "passes:\n"
        "  - name: extract_points\n"
        "    output_entities: [ProofPoint]\n"
        "    route_path: /extract-points\n"
        "    prompt: prompts/extract_points.md\n"
        + extra
    )


def test_derivation_binds_without_opt_out():
    """Baseline: the loose-ref field is auto-derived as the provenance binding (zero config)."""
    ps = parse_ai_passes(_bind_manifest())[0]
    human = parse_human_inputs(_BIND_HUMAN)
    assert effective_source_binding(_BIND_SCHEMA, ps, human) == "sourceDocumentId"


def test_source_binding_none_disables_derivation():
    """`source_binding: none` returns None even though a loose-ref candidate exists (opt-out)."""
    ps = parse_ai_passes(_bind_manifest("    source_binding: none\n"))[0]
    human = parse_human_inputs(_BIND_HUMAN)
    assert effective_source_binding(_BIND_SCHEMA, ps, human) is None


@pytest.mark.parametrize("sentinel", ["none", "None", "NONE", "  none  "])
def test_source_binding_none_is_case_and_space_insensitive(sentinel):
    ps = parse_ai_passes(_bind_manifest(f"    source_binding: {sentinel!r}\n"))[0]
    human = parse_human_inputs(_BIND_HUMAN)
    assert effective_source_binding(_BIND_SCHEMA, ps, human) is None


def test_explicit_field_binding_still_wins():
    """A real field value still overrides derivation (the non-`none` override path is intact)."""
    ps = parse_ai_passes(_bind_manifest("    source_binding: sourceDocumentId\n"))[0]
    human = parse_human_inputs(_BIND_HUMAN)
    assert effective_source_binding(_BIND_SCHEMA, ps, human) == "sourceDocumentId"


def test_parse_accepts_none_on_read_mode_pass():
    """`none` is allowed regardless of the text-mode/single-output strictness (it only disables)."""
    manifest = (
        "passes:\n"
        "  - name: suggest\n"
        "    input_entities: [ProofPoint]\n"
        "    output_entities: [ProofPoint, Capability]\n"
        "    route_path: /suggest\n"
        "    prompt: prompts/suggest.md\n"
        "    source_binding: none\n"
    )
    passes = parse_ai_passes(manifest)
    assert passes[0].source_binding == "none"


def test_parse_still_rejects_real_binding_on_read_mode_pass():
    """A real `source_binding` field on a read-mode pass is still a loud failure (strictness kept)."""
    manifest = (
        "passes:\n"
        "  - name: suggest\n"
        "    input_entities: [ProofPoint]\n"
        "    output_entities: [ProofPoint]\n"
        "    route_path: /suggest\n"
        "    prompt: prompts/suggest.md\n"
        "    source_binding: sourceDocumentId\n"
    )
    with pytest.raises(ValueError):
        parse_ai_passes(manifest)


def test_opt_out_renders_byte_identical_to_unbound():
    """Opting out yields the exact unbound harness/router — the field is dropped from the emitted code."""
    bound_files = dict(render_ai_layer(_BIND_SCHEMA, _bind_manifest("    source_binding: none\n"), _BIND_HUMAN))
    # The same app with NO loose-ref field at all (genuinely unbound by absence).
    plain_schema = _BIND_SCHEMA.replace("  sourceDocumentId String?\n", "")
    plain_human = ""
    plain_files = dict(render_ai_layer(plain_schema, _bind_manifest(), plain_human))
    # Harness + router bodies (below the input-dependent three-hash header) must match exactly.
    for rel in ("app/ai/extract_points.py", "app/ai/routes.py"):
        bound_body = bound_files[rel].split("\n\n", 1)[1]
        plain_body = plain_files[rel].split("\n\n", 1)[1]
        assert bound_body == plain_body
        assert "source_id" not in bound_body  # no 3rd-arg / _Request.source_id leaked in
