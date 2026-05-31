"""Tests for upstream-contract forwarding in the drafter's supplementary sections.

NOTE (2026-05-31): This file previously also held TestAccumulateManifest,
TestGetUpstreamContracts, and TestAccumulatedContractsSection, which targeted
``PrimeContractorWorkflow._accumulate_manifest`` / ``._get_upstream_contracts`` and
``spec_builder._build_accumulated_contracts_section``. Those symbols were
**intentionally removed** in commit d356def8 (REQ-ICD-106), which replaced the
per-feature manifest-accumulation mechanism with the seed-based
``security_contract`` flow — its coverage now lives in
``tests/unit/test_security_contract_wiring.py``. The orphaned tests (which could
never pass against the deleted API) were removed here; the still-valid drafter
upstream-contract tests below are retained.
"""


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
