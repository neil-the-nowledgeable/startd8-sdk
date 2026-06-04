"""REQ-CKG-524/527 — structural Prisma scoping in the injection seam (D4).

The acceptance the Phase-1 keyword gate failed: a feature that *uses* an entity
but whose name/files match no ``_MIRROR_NAMES`` stem (RUN-011 PI-001
``enrich-capabilities``) must still receive that entity's field set. Plus the
fallback that preserves the RUN-009 whole-model-mirror case.
"""

from __future__ import annotations

from types import SimpleNamespace

from startd8.contractors.prime_contractor import PrimeContractorWorkflow

_collect = PrimeContractorWorkflow._collect_upstream_interfaces
_mirrors = PrimeContractorWorkflow._feature_mirrors_data_model

SCHEMA = (
    "model Capability {\n id String @id\n name String\n score Float?\n}\n"
    "model Outcome {\n id String @id\n label String\n}\n"
)


def _stub(anchors, project_root):
    return SimpleNamespace(
        seed_upstream_anchors=anchors, project_root=str(project_root),
        queue=None, _feature_mirrors_data_model=_mirrors,
    )


def _feature(**kw):
    kw.setdefault("dependencies", [])
    kw.setdefault("target_files", [])
    kw.setdefault("description", "")
    kw.setdefault("name", "X")
    return SimpleNamespace(**kw)


def _project(tmp_path):
    (tmp_path / "prisma").mkdir()
    (tmp_path / "prisma" / "schema.prisma").write_text(SCHEMA)
    return tmp_path


class TestStructuralScoping:
    def test_pi001_style_gets_field_set_without_matching_heuristic(self, tmp_path):
        d = _project(tmp_path)
        feat = _feature(name="enrich-capabilities", target_files=["app/actions/enrich.ts"])
        # the OLD keyword gate would skip this (no _MIRROR_NAMES stem, no keyword)
        assert _mirrors(feat) is False
        out = _collect(_stub(["prisma/schema.prisma"], d), feat)
        # ...but structural reference resolution scopes it to Capability anyway
        assert "## Prisma data model" in out
        assert "`Capability`" in out

    def test_scopes_to_referenced_entity_only(self, tmp_path):
        d = _project(tmp_path)
        feat = _feature(name="enrich-capabilities", target_files=["app/actions/enrich.ts"])
        out = _collect(_stub(["prisma/schema.prisma"], d), feat)
        # Outcome is not referenced → not injected (no over-scoping, REQ-527)
        assert "`Outcome`" not in out

    def test_whole_model_mirror_fallback_injects_all(self, tmp_path):
        d = _project(tmp_path)
        # names no specific entity, but is a value-model mirror → inherit full set
        feat = _feature(name="data schemas", target_files=["lib/value-model.ts"])
        assert _mirrors(feat) is True
        out = _collect(_stub(["prisma/schema.prisma"], d), feat)
        assert "`Capability`" in out and "`Outcome`" in out

    def test_unrelated_feature_no_injection(self, tmp_path):
        d = _project(tmp_path)
        feat = _feature(name="render footer", target_files=["app/footer.tsx"])
        out = _collect(_stub(["prisma/schema.prisma"], d), feat)
        assert out == ""


class TestPerBatchArtifact:
    """REQ-CKG-500/NFR-2: the schema is parsed once per batch, reused per feature."""

    def test_uses_cached_artifact_without_rebuilding(self, monkeypatch):
        import startd8.contractors.prime_contractor as pc
        from startd8.contractors.project_knowledge import DraftModeProducer

        # the workflow built this once in run(); the seam must reuse it...
        cached = DraftModeProducer().build({"prisma/schema.prisma": SCHEMA}, "/x")
        # ...and must NOT re-parse per feature — guard by making a rebuild explode.
        def _boom(*a, **k):
            raise AssertionError("per-feature rebuild — the per-batch cache was bypassed")

        monkeypatch.setattr(pc, "_build_project_knowledge", _boom)

        stub = SimpleNamespace(
            seed_upstream_anchors=[], project_root="/x", queue=None,
            _feature_mirrors_data_model=_mirrors, _project_knowledge=cached,
        )
        out = _collect(stub, _feature(name="enrich-capabilities",
                                      target_files=["app/actions/enrich.ts"]))
        assert "`Capability`" in out  # rendered from the cached artifact, no rebuild

    def test_builds_inline_when_no_cache(self, tmp_path, monkeypatch):
        import startd8.contractors.prime_contractor as pc
        d = _project(tmp_path)
        called = {}
        real = pc._build_project_knowledge

        def _spy(anchors, root):
            called["hit"] = True
            return real(anchors, root)

        monkeypatch.setattr(pc, "_build_project_knowledge", _spy)
        # stub has no _project_knowledge → seam builds inline (single-feature path)
        out = _collect(_stub(["prisma/schema.prisma"], d),
                       _feature(name="enrich-capabilities", target_files=["x.ts"]))
        assert called.get("hit") is True
        assert "`Capability`" in out


_ENUM_SCHEMA = (
    "model Capability {\n id String @id\n name String\n tier Tier\n}\n"
    "model Outcome {\n id String @id\n label String\n}\n"
    "enum Tier {\n junior\n mid\n senior\n}\n"
)


def _enum_project(tmp_path):
    (tmp_path / "prisma").mkdir()
    (tmp_path / "prisma" / "schema.prisma").write_text(_ENUM_SCHEMA)
    return tmp_path


class TestEnumAuthoritySeam:
    """REQ-CKG-525: enum-value authority rides the per-feature scoping seam (step 2a)."""

    def test_enum_block_injected_alongside_scoped_field_set(self, tmp_path):
        d = _enum_project(tmp_path)
        feat = _feature(name="enrich-capabilities", target_files=["app/actions/enrich.ts"])
        out = _collect(_stub(["prisma/schema.prisma"], d), feat)
        assert "## Prisma data model" in out and "`Capability`" in out
        assert "## Enum values" in out
        assert "`Tier`: junior, mid, senior" in out

    def test_no_enum_block_when_feature_touches_no_data_model(self, tmp_path):
        d = _enum_project(tmp_path)
        feat = _feature(name="render footer", target_files=["app/footer.tsx"])
        out = _collect(_stub(["prisma/schema.prisma"], d), feat)
        assert "## Enum values" not in out  # no scoped field-set → no enum block either
