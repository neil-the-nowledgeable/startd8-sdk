"""Tests for REQ-MP-701: ForwardManifest deserialization + context forwarding."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from startd8.contractors.protocols import GenerationResult


# ── Helpers ──────────────────────────────────────────────────────────

_WORKFLOW_PREFIX = "startd8.contractors.prime_contractor.PrimeContractorWorkflow"


def _make_workflow(**kwargs):
    """Build a PrimeContractorWorkflow with a mock code_generator."""
    from startd8.contractors.prime_contractor import PrimeContractorWorkflow

    mock_gen = MagicMock()
    mock_gen.generate.return_value = GenerationResult(
        success=True,
        generated_files=[Path("out.py")],
        cost_usd=0.01,
        input_tokens=100,
        output_tokens=50,
        model="mock",
    )
    mock_gen.output_dir = Path("/tmp/generated")

    defaults = dict(
        project_root=Path("/tmp/test_project"),
        code_generator=mock_gen,
    )
    defaults.update(kwargs)
    wf = PrimeContractorWorkflow(**defaults)
    return wf, mock_gen


def _make_feature(name="test-feature", target_files=None, description="Implement foo", metadata=None):
    """Build a mock FeatureSpec."""
    from startd8.contractors.queue import FeatureSpec

    feat = MagicMock(spec=FeatureSpec)
    feat.name = name
    feat.id = f"F-{name}"
    feat.target_files = target_files or ["mod.py"]
    feat.description = description
    feat.metadata = metadata if metadata is not None else {}
    feat.status = None
    feat.generated_files = []
    feat.copy_source_task_id = None
    feat.copy_source_file = None
    feat.dependencies = []
    return feat


def _minimal_manifest_dict():
    """Return a minimal valid ForwardManifest dict."""
    return {
        "schema_version": "1.0.0",
        "contracts": [],
        "file_specs": {
            "mod.py": {
                "file": "mod.py",
                "elements": [],
                "imports": [],
            },
        },
        "stages_completed": [],
    }


# Shared patches for develop_feature internals
_DEVELOP_PATCHES = [
    patch(f"{_WORKFLOW_PREFIX}.pre_flight_validation", return_value=(True, {})),
    patch(f"{_WORKFLOW_PREFIX}._populate_existing_files"),
    patch(f"{_WORKFLOW_PREFIX}._save_queue_state_with_mode"),
    patch(f"{_WORKFLOW_PREFIX}._get_domain_enrichment", return_value=None),
    patch(f"{_WORKFLOW_PREFIX}._check_file_provenance", return_value={}),
]


def _apply_develop_patches(func):
    """Apply all develop_feature patches to a test method."""
    for p in reversed(_DEVELOP_PATCHES):
        func = p(func)
    return func


# ── load_seed_context deserialization ────────────────────────────────


class TestManifestDeserialization:
    """Test ForwardManifest deserialization in load_seed_context()."""

    def test_valid_manifest_deserialized(self):
        """A valid manifest dict is deserialized to ForwardManifest."""
        wf, _ = _make_workflow()
        seed_data = {"forward_manifest": _minimal_manifest_dict()}

        wf.load_seed_context(seed_data)

        assert wf._forward_manifest is not None
        assert hasattr(wf._forward_manifest, "file_specs")
        assert "mod.py" in wf._forward_manifest.file_specs

    def test_no_manifest_stays_none(self):
        """When no manifest in seed, _forward_manifest remains None."""
        wf, _ = _make_workflow()
        seed_data = {}

        wf.load_seed_context(seed_data)

        assert wf._forward_manifest is None

    def test_null_manifest_stays_none(self):
        """When manifest is None in seed, _forward_manifest remains None."""
        wf, _ = _make_workflow()
        seed_data = {"forward_manifest": None}

        wf.load_seed_context(seed_data)

        assert wf._forward_manifest is None

    def test_invalid_manifest_graceful_degradation(self):
        """Invalid manifest dict logs warning, _forward_manifest stays None."""
        wf, _ = _make_workflow()
        # Invalid: file_specs must be a dict, not a string
        seed_data = {"forward_manifest": {"file_specs": "not-a-dict"}}

        wf.load_seed_context(seed_data)

        assert wf._forward_manifest is None
        # Raw dict is still preserved for backward compat
        assert wf.seed_forward_manifest == {"file_specs": "not-a-dict"}

    def test_non_dict_manifest_ignored(self):
        """Non-dict manifest (e.g. a list) is ignored by the isinstance guard."""
        wf, _ = _make_workflow()
        seed_data = {"forward_manifest": ["not", "a", "dict"]}

        wf.load_seed_context(seed_data)

        assert wf._forward_manifest is None
        assert wf.seed_forward_manifest is None

    def test_manifest_with_contracts(self):
        """Manifest with contracts is deserialized with contract count logged."""
        wf, _ = _make_workflow()
        manifest_dict = _minimal_manifest_dict()
        manifest_dict["contracts"] = [
            {
                "contract_id": "C-001",
                "category": "function_name",
                "confidence": "explicit",
                "description": "Function create_user must exist",
                "binding_text": "MUST define function create_user",
            },
        ]
        seed_data = {"forward_manifest": manifest_dict}

        wf.load_seed_context(seed_data)

        assert wf._forward_manifest is not None
        assert len(wf._forward_manifest.contracts) == 1

    def test_raw_dict_preserved_for_backward_compat(self):
        """seed_forward_manifest (raw dict) is preserved alongside deserialized object."""
        wf, _ = _make_workflow()
        manifest_dict = _minimal_manifest_dict()
        seed_data = {"forward_manifest": manifest_dict}

        wf.load_seed_context(seed_data)

        assert wf.seed_forward_manifest == manifest_dict
        assert wf._forward_manifest is not None

    def test_forward_manifest_initialized_in_init(self):
        """_forward_manifest is initialized to None in __init__ before load_seed_context."""
        wf, _ = _make_workflow()
        assert wf._forward_manifest is None


# ── develop_feature context forwarding ───────────────────────────────


class TestManifestContextForwarding:
    """Test ForwardManifest forwarding into gen_context in develop_feature()."""

    @_apply_develop_patches
    def test_manifest_forwarded_in_gen_context(self, *_mocks):
        """When _forward_manifest is set, gen_context['manifest'] contains it."""
        wf, mock_gen = _make_workflow()
        wf._context_strategy = MagicMock()
        wf._context_strategy.resolve_task_context.return_value = {}
        wf._context_strategy.mode = "standalone"
        wf.queue.start_feature = MagicMock()

        # Deserialize manifest
        seed_data = {"forward_manifest": _minimal_manifest_dict()}
        wf.load_seed_context(seed_data)

        feature = _make_feature()
        wf.develop_feature(feature)

        # Verify gen_context passed to generate() includes manifest
        call_args = mock_gen.generate.call_args
        gen_context = call_args[1].get("context") or call_args[0][1]
        assert "manifest" in gen_context
        assert gen_context["manifest"] is wf._forward_manifest

    @_apply_develop_patches
    def test_no_manifest_not_in_gen_context(self, *_mocks):
        """When _forward_manifest is None, gen_context has no 'manifest' key."""
        wf, mock_gen = _make_workflow()
        wf._context_strategy = MagicMock()
        wf._context_strategy.resolve_task_context.return_value = {}
        wf._context_strategy.mode = "standalone"
        wf.queue.start_feature = MagicMock()

        feature = _make_feature()
        wf.develop_feature(feature)

        call_args = mock_gen.generate.call_args
        gen_context = call_args[1].get("context") or call_args[0][1]
        assert "manifest" not in gen_context

    @_apply_develop_patches
    def test_manifest_does_not_override_strategy_keys(self, *_mocks):
        """ForwardManifest forwarding does not clobber other gen_context keys."""
        wf, mock_gen = _make_workflow()
        wf._context_strategy = MagicMock()
        wf._context_strategy.resolve_task_context.return_value = {
            "feature_name": "test-feature",
            "target_file": "mod.py",
        }
        wf._context_strategy.mode = "standalone"
        wf.queue.start_feature = MagicMock()

        seed_data = {"forward_manifest": _minimal_manifest_dict()}
        wf.load_seed_context(seed_data)

        feature = _make_feature()
        wf.develop_feature(feature)

        call_args = mock_gen.generate.call_args
        gen_context = call_args[1].get("context") or call_args[0][1]
        assert gen_context["feature_name"] == "test-feature"
        assert gen_context["target_file"] == "mod.py"
        assert "manifest" in gen_context
