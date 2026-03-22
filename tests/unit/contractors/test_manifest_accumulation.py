"""Tests for within-run forward manifest accumulation (Layer 3)."""

import pytest
from unittest.mock import MagicMock, patch
from startd8.forward_manifest import (
    ContractCategory,
    ContractConfidence,
    ForwardManifest,
    InterfaceContract,
)


def _make_manifest(binding_text="Convert(from_code, to_code, amount: Money) -> Money"):
    """Create a ForwardManifest with one explicit contract."""
    return ForwardManifest(
        contracts=[
            InterfaceContract(
                contract_id="c-001",
                category=ContractCategory.FUNCTION_NAME,
                confidence=ContractConfidence.EXPLICIT,
                description="Convert currency",
                binding_text=binding_text,
            ),
        ],
        file_specs={},
    )


def _make_feature(feature_id="f-001", name="currency-service", deps=None, score=1.0, manifest=None):
    """Create a mock FeatureSpec with metadata."""
    feature = MagicMock()
    feature.id = feature_id
    feature.name = name
    feature.dependencies = deps or []
    feature.metadata = {
        "_disk_quality_score": score,
        "_forward_manifest": manifest or _make_manifest(),
    }
    return feature


class TestAccumulateManifest:
    """Test _accumulate_manifest on PrimeContractorWorkflow."""

    def test_accumulates_high_score(self):
        """Feature with score >= 0.9 gets accumulated."""
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow

        wf = MagicMock(spec=PrimeContractorWorkflow)
        wf._accumulated_manifests = {}

        feature = _make_feature()
        PrimeContractorWorkflow._accumulate_manifest(wf, feature)
        assert "f-001" in wf._accumulated_manifests

    def test_skips_low_score(self):
        """Feature with score < 0.9 is not accumulated."""
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow

        wf = MagicMock(spec=PrimeContractorWorkflow)
        wf._accumulated_manifests = {}

        feature = _make_feature(score=0.7)
        PrimeContractorWorkflow._accumulate_manifest(wf, feature)
        assert len(wf._accumulated_manifests) == 0

    def test_skips_no_manifest(self):
        """Feature with no manifest metadata is silently skipped."""
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow

        wf = MagicMock(spec=PrimeContractorWorkflow)
        wf._accumulated_manifests = {}

        feature = MagicMock()
        feature.id = "f-002"
        feature.name = "no-manifest"
        feature.metadata = {"_disk_quality_score": 1.0}
        PrimeContractorWorkflow._accumulate_manifest(wf, feature)
        assert len(wf._accumulated_manifests) == 0

    def test_accumulates_dict_manifest(self):
        """Feature with dict manifest (not Pydantic instance) is deserialized."""
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow

        wf = MagicMock(spec=PrimeContractorWorkflow)
        wf._accumulated_manifests = {}

        manifest_dict = _make_manifest().model_dump()
        feature = _make_feature(manifest=manifest_dict)
        PrimeContractorWorkflow._accumulate_manifest(wf, feature)
        assert "f-001" in wf._accumulated_manifests
        assert isinstance(wf._accumulated_manifests["f-001"], ForwardManifest)

    def test_exception_is_non_fatal(self):
        """Exception during accumulation is caught silently."""
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow

        wf = MagicMock(spec=PrimeContractorWorkflow)
        wf._accumulated_manifests = {}

        feature = MagicMock()
        feature.id = "f-003"
        feature.name = "bad-manifest"
        feature.metadata = {"_disk_quality_score": 1.0, "_forward_manifest": "not-valid"}
        # Should not raise
        PrimeContractorWorkflow._accumulate_manifest(wf, feature)
        assert len(wf._accumulated_manifests) == 0


class TestGetUpstreamContracts:
    """Test _get_upstream_contracts on PrimeContractorWorkflow."""

    def test_upstream_contracts_found(self):
        """Dependent feature returns upstream contracts."""
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow

        manifest = _make_manifest()

        wf = MagicMock(spec=PrimeContractorWorkflow)
        wf._accumulated_manifests = {"dep-001": manifest}
        wf.queue = MagicMock()
        wf.queue.get_feature.return_value = None

        feature = _make_feature(deps=["dep-001"])
        result = PrimeContractorWorkflow._get_upstream_contracts(wf, feature)
        assert len(result) == 1
        assert result[0]["feature_id"] == "dep-001"
        assert len(result[0]["contracts"]) == 1
        assert result[0]["contracts"][0]["confidence"] == "explicit"

    def test_no_deps_empty_list(self):
        """Feature with no dependencies returns empty list."""
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow

        wf = MagicMock(spec=PrimeContractorWorkflow)
        wf._accumulated_manifests = {"dep-001": MagicMock()}

        feature = _make_feature(deps=[])
        result = PrimeContractorWorkflow._get_upstream_contracts(wf, feature)
        assert result == []

    def test_no_accumulated_manifests(self):
        """Empty accumulated manifests returns empty list."""
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow

        wf = MagicMock(spec=PrimeContractorWorkflow)
        wf._accumulated_manifests = {}

        feature = _make_feature(deps=["dep-001"])
        result = PrimeContractorWorkflow._get_upstream_contracts(wf, feature)
        assert result == []

    def test_name_based_lookup(self):
        """Dependencies by name (not ID) are resolved via queue lookup."""
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow

        manifest = _make_manifest()

        wf = MagicMock(spec=PrimeContractorWorkflow)
        wf._accumulated_manifests = {"actual-id-001": manifest}

        dep_feature = MagicMock()
        dep_feature.name = "currency-service"
        wf.queue = MagicMock()
        wf.queue.get_feature.side_effect = lambda fid: dep_feature if fid == "actual-id-001" else None

        feature = _make_feature(deps=["currency-service"])
        result = PrimeContractorWorkflow._get_upstream_contracts(wf, feature)
        assert len(result) == 1
        assert result[0]["feature_name"] == "currency-service"

    def test_skips_non_explicit_contracts(self):
        """Only explicit-confidence contracts are returned."""
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow

        manifest = ForwardManifest(
            contracts=[
                InterfaceContract(
                    contract_id="c-001",
                    category=ContractCategory.FUNCTION_NAME,
                    confidence=ContractConfidence.INFERRED,
                    description="Inferred function",
                    binding_text="some_func()",
                ),
            ],
            file_specs={},
        )

        wf = MagicMock(spec=PrimeContractorWorkflow)
        wf._accumulated_manifests = {"dep-001": manifest}
        wf.queue = MagicMock()
        wf.queue.get_feature.return_value = None

        feature = _make_feature(deps=["dep-001"])
        result = PrimeContractorWorkflow._get_upstream_contracts(wf, feature)
        assert result == []

    def test_multiple_deps(self):
        """Multiple dependencies each contribute contracts."""
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow

        m1 = _make_manifest("ServiceA.run()")
        m2 = _make_manifest("ServiceB.start()")

        wf = MagicMock(spec=PrimeContractorWorkflow)
        wf._accumulated_manifests = {"dep-001": m1, "dep-002": m2}
        wf.queue = MagicMock()
        wf.queue.get_feature.return_value = None

        feature = _make_feature(deps=["dep-001", "dep-002"])
        result = PrimeContractorWorkflow._get_upstream_contracts(wf, feature)
        assert len(result) == 2


class TestAccumulatedContractsSection:
    """Test _build_accumulated_contracts_section in spec_builder."""

    def test_builds_section(self):
        from startd8.implementation_engine.spec_builder import _build_accumulated_contracts_section

        ctx = {
            "upstream_contracts": [
                {
                    "feature_name": "currency-service",
                    "feature_id": "dep-001",
                    "language": "go",
                    "contracts": [
                        {
                            "name": "Convert",
                            "binding_text": "Convert(from_code, to_code, amount: Money) -> Money",
                            "confidence": "explicit",
                        },
                    ],
                }
            ]
        }
        section = _build_accumulated_contracts_section(ctx)
        assert "Upstream API Contracts" in section
        assert "currency-service" in section
        assert "Convert" in section
        assert "(go)" in section

    def test_empty_context(self):
        from startd8.implementation_engine.spec_builder import _build_accumulated_contracts_section

        assert _build_accumulated_contracts_section({}) == ""

    def test_none_upstream(self):
        from startd8.implementation_engine.spec_builder import _build_accumulated_contracts_section

        assert _build_accumulated_contracts_section({"upstream_contracts": None}) == ""

    def test_empty_list(self):
        from startd8.implementation_engine.spec_builder import _build_accumulated_contracts_section

        assert _build_accumulated_contracts_section({"upstream_contracts": []}) == ""

    def test_no_language_suffix(self):
        from startd8.implementation_engine.spec_builder import _build_accumulated_contracts_section

        ctx = {
            "upstream_contracts": [
                {
                    "feature_name": "svc",
                    "feature_id": "dep-001",
                    "language": "unknown",
                    "contracts": [{"binding_text": "foo()", "confidence": "explicit"}],
                }
            ]
        }
        section = _build_accumulated_contracts_section(ctx)
        assert "(unknown)" not in section
        assert "### svc\n" in section

    def test_truncation(self):
        from startd8.implementation_engine.spec_builder import _build_accumulated_contracts_section

        # Create a very large contracts section
        contracts = []
        for i in range(100):
            contracts.append({
                "name": f"Function_{i}",
                "binding_text": f"function_{i}(arg1, arg2, arg3, arg4, arg5) -> ReturnType_{i}",
                "confidence": "explicit",
            })

        ctx = {
            "upstream_contracts": [
                {
                    "feature_name": "big-service",
                    "feature_id": "dep-001",
                    "language": "python",
                    "contracts": contracts,
                }
            ]
        }
        section = _build_accumulated_contracts_section(ctx)
        assert len(section) <= 2_400


class TestDrafterUpstreamContracts:
    """Test upstream contracts in drafter's build_supplementary_sections."""

    def test_upstream_in_supplementary(self):
        from startd8.implementation_engine.drafter import build_supplementary_sections

        ctx = {
            "upstream_contracts": [
                {
                    "feature_name": "auth-service",
                    "contracts": [
                        {"binding_text": "authenticate(token: str) -> User"},
                    ],
                }
            ]
        }
        result = build_supplementary_sections(ctx)
        assert "Upstream API Contracts" in result
        assert "auth-service" in result
        assert "authenticate" in result

    def test_no_upstream_no_section(self):
        from startd8.implementation_engine.drafter import build_supplementary_sections

        ctx = {"forward_contracts": "some contract"}
        result = build_supplementary_sections(ctx)
        assert "Upstream API Contracts" not in result
