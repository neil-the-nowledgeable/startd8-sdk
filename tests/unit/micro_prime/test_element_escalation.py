"""Tests for element-level cloud escalation in Micro Prime (REQ-MP-505/512)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from startd8.micro_prime.models import (
    ElementResult,
    EscalationReason,
    EscalationResult,
    FileResult,
    TierClassification,
)
from startd8.micro_prime.prime_adapter import (
    MicroPrimeCodeGenerator,
    _extract_element_from_generated,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _make_ollama_mock():
    mock_response = MagicMock()
    mock_response.read.return_value = b'{"models": [{"name": "startd8-coder:latest"}]}'
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)
    return mock_response


def _make_partial_file_result(
    file_path: str,
    skeleton: str,
    success_names: list[str],
    escalated_names: list[str],
) -> FileResult:
    """Build a FileResult with some successes and some escalated elements."""
    fr = FileResult(file_path=file_path)
    for name in success_names:
        fr.element_results.append(
            ElementResult(
                element_name=name,
                file_path=file_path,
                tier=TierClassification.SIMPLE,
                success=True,
                code=f"return '{name}'",
            )
        )
    for name in escalated_names:
        fr.element_results.append(
            ElementResult(
                element_name=name,
                file_path=file_path,
                tier=TierClassification.MODERATE,
                success=False,
                escalation=EscalationResult(
                    reason=EscalationReason.TIER_TOO_HIGH,
                    detail="Too complex for local",
                ),
            )
        )
    fr.filled_skeleton = skeleton
    return fr


def _make_mock_cloud_agent(code_response: str = "return len(key)"):
    """Create a mock cloud agent that returns the given code."""
    mock_agent = MagicMock()
    mock_token_usage = MagicMock()
    mock_token_usage.input = 150
    mock_token_usage.output = 50
    mock_agent.generate.return_value = (code_response, 100, mock_token_usage)
    return mock_agent


# ── _extract_element_from_generated tests ────────────────────────────


class TestExtractElementFromGenerated:
    """Tests for the AST extraction helper."""

    def test_extract_function(self):
        source = (
            "import os\n\n"
            "def helper():\n"
            "    return 42\n\n"
            "def target_fn(x):\n"
            "    return x * 2\n"
        )
        result = _extract_element_from_generated(source, "target_fn", "function")
        assert result is not None
        assert "def target_fn(x):" in result
        assert "return x * 2" in result

    def test_extract_class(self):
        source = (
            "class MyFormatter:\n"
            "    def format(self, record):\n"
            "        return str(record)\n"
        )
        result = _extract_element_from_generated(source, "MyFormatter", "class")
        assert result is not None
        assert "class MyFormatter:" in result
        assert "def format" in result

    def test_extract_async_function(self):
        source = (
            "async def fetch(url):\n"
            "    return await get(url)\n"
        )
        result = _extract_element_from_generated(source, "fetch", "function")
        assert result is not None
        assert "async def fetch" in result

    def test_extract_method_as_function(self):
        """Methods are FunctionDef in AST — kind='function' should match."""
        source = (
            "class Foo:\n"
            "    def bar(self):\n"
            "        return 1\n"
        )
        result = _extract_element_from_generated(source, "bar", "function")
        assert result is not None
        assert "def bar(self):" in result

    def test_returns_none_for_missing_element(self):
        source = "def other():\n    pass\n"
        result = _extract_element_from_generated(source, "missing", "function")
        assert result is None

    def test_returns_none_for_syntax_error(self):
        source = "def broken(\n"
        result = _extract_element_from_generated(source, "broken", "function")
        assert result is None


# ── Element-level escalation integration tests ──────────────────────


class TestElementEscalation:
    """Tests for element-level cloud escalation in generate()."""

    def test_partial_file_triggers_element_escalation(
        self, tmp_path, sample_manifest, sample_skeleton,
    ):
        """File with 2 success + 1 escalated -> direct cloud call with prompt containing element name."""
        mock_agent = _make_mock_cloud_agent("return len(key)")

        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            cloud_agent_spec="anthropic:claude-haiku-4-5-20251001",
            output_dir=tmp_path,
        )

        partial = _make_partial_file_result(
            "src/mypackage/utils.py",
            sample_skeleton,
            success_names=["get_name"],
            escalated_names=["get_value"],
        )

        with patch.object(gen._engine, "process_file", return_value=partial), \
             patch("startd8.micro_prime.prime_adapter.urlopen",
                   return_value=_make_ollama_mock()), \
             patch(
                 "startd8.micro_prime.prime_adapter.MicroPrimeCodeGenerator._get_cloud_agent",
                 return_value=mock_agent,
             ):
            result = gen.generate(
                "Implement utils", {}, ["src/mypackage/utils.py"],
            )

        # Cloud agent should have been called for element escalation
        mock_agent.generate.assert_called_once()
        # The prompt should contain the element context
        call_args = mock_agent.generate.call_args
        prompt = call_args[0][0]
        assert "get_value" in prompt

    def test_escalation_context_includes_partial_skeleton(
        self, tmp_path, sample_manifest, sample_skeleton,
    ):
        """Cloud agent prompt includes skeleton content."""
        mock_agent = _make_mock_cloud_agent("return 42")

        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            cloud_agent_spec="anthropic:claude-haiku-4-5-20251001",
            output_dir=tmp_path,
        )

        partial = _make_partial_file_result(
            "src/mypackage/utils.py",
            sample_skeleton,
            success_names=["get_name"],
            escalated_names=["get_value"],
        )

        with patch.object(gen._engine, "process_file", return_value=partial), \
             patch("startd8.micro_prime.prime_adapter.urlopen",
                   return_value=_make_ollama_mock()), \
             patch(
                 "startd8.micro_prime.prime_adapter.MicroPrimeCodeGenerator._get_cloud_agent",
                 return_value=mock_agent,
             ):
            gen.generate("Implement", {}, ["src/mypackage/utils.py"])

        # The prompt should contain escalation context
        call_args = mock_agent.generate.call_args
        prompt = call_args[0][0]
        assert "get_value" in prompt
        # Escalation reason forwarded
        assert "tier_too_high" in prompt

    def test_splice_back_into_partial_skeleton(
        self, tmp_path, sample_manifest, sample_skeleton,
    ):
        """Output file contains both locally-filled and cloud-filled elements."""
        # Build a partial skeleton where get_name is filled but get_value has a stub
        filled_skeleton = sample_skeleton.replace(
            "        raise NotImplementedError\n\n    def get_value",
            "        return key.upper()\n\n    def get_value",
        )

        # Cloud agent returns the body for get_value
        mock_agent = _make_mock_cloud_agent("return len(key)")

        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            cloud_agent_spec="anthropic:claude-haiku-4-5-20251001",
            output_dir=tmp_path,
        )

        partial = _make_partial_file_result(
            "src/mypackage/utils.py",
            filled_skeleton,
            success_names=["get_name"],
            escalated_names=["get_value"],
        )

        with patch.object(gen._engine, "process_file", return_value=partial), \
             patch("startd8.micro_prime.prime_adapter.urlopen",
                   return_value=_make_ollama_mock()), \
             patch(
                 "startd8.micro_prime.prime_adapter.MicroPrimeCodeGenerator._get_cloud_agent",
                 return_value=mock_agent,
             ):
            result = gen.generate("Implement", {}, ["src/mypackage/utils.py"])

        # Read the final output and verify both elements are present
        output_path = tmp_path / "src/mypackage/utils.py"
        final_content = output_path.read_text(encoding="utf-8")
        assert "return key.upper()" in final_content  # locally filled
        assert "return len(key)" in final_content     # cloud filled

    def test_all_succeed_no_escalation(
        self, tmp_path, sample_manifest, sample_skeleton,
    ):
        """All elements succeed locally -> no cloud agent called."""
        mock_agent = _make_mock_cloud_agent()
        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            cloud_agent_spec="anthropic:claude-haiku-4-5-20251001",
            output_dir=tmp_path,
        )

        all_success = FileResult(file_path="src/mypackage/utils.py")
        all_success.element_results = [
            ElementResult(
                element_name="get_name",
                file_path="src/mypackage/utils.py",
                tier=TierClassification.SIMPLE,
                success=True,
                code="return 'name'",
            ),
            ElementResult(
                element_name="get_value",
                file_path="src/mypackage/utils.py",
                tier=TierClassification.SIMPLE,
                success=True,
                code="return 42",
            ),
        ]
        all_success.filled_skeleton = sample_skeleton

        with patch.object(gen._engine, "process_file", return_value=all_success), \
             patch("startd8.micro_prime.prime_adapter.urlopen",
                   return_value=_make_ollama_mock()), \
             patch(
                 "startd8.micro_prime.prime_adapter.MicroPrimeCodeGenerator._get_cloud_agent",
                 return_value=mock_agent,
             ):
            result = gen.generate("Implement", {}, ["src/mypackage/utils.py"])

        mock_agent.generate.assert_not_called()
        assert result.metadata.get("element_escalation_count") == 0

    def test_all_fail_uses_file_fallback(
        self, tmp_path, sample_manifest, sample_skeleton,
    ):
        """0 success -> existing file-level fallback path (unchanged)."""
        fallback = MagicMock()
        fallback.generate.return_value = MagicMock(
            success=True,
            generated_files=[tmp_path / "fb.py"],
            input_tokens=50,
            output_tokens=100,
            model="fallback",
            cost_usd=0.05,
        )

        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            fallback=fallback,
            output_dir=tmp_path,
        )

        all_fail = FileResult(file_path="src/mypackage/utils.py")
        all_fail.element_results = [
            ElementResult(
                element_name="get_name",
                file_path="src/mypackage/utils.py",
                tier=TierClassification.MODERATE,
                success=False,
                escalation=EscalationResult(
                    reason=EscalationReason.TIER_TOO_HIGH,
                    detail="complex",
                ),
            ),
        ]
        all_fail.filled_skeleton = sample_skeleton

        with patch.object(gen._engine, "process_file", return_value=all_fail), \
             patch("startd8.micro_prime.prime_adapter.urlopen",
                   return_value=_make_ollama_mock()):
            result = gen.generate("Implement", {}, ["src/mypackage/utils.py"])

        # File-level fallback called (not element-level)
        fallback.generate.assert_called_once()
        # Task should be the original task (not a targeted one)
        call_args = fallback.generate.call_args
        assert call_args[0][0] == "Implement"

    def test_fallback_failure_keeps_partial(
        self, tmp_path, sample_manifest, sample_skeleton,
    ):
        """Cloud agent returns empty -> partial skeleton preserved (Mottainai)."""
        # Cloud agent returns nothing useful
        mock_agent = _make_mock_cloud_agent("")

        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            cloud_agent_spec="anthropic:claude-haiku-4-5-20251001",
            output_dir=tmp_path,
        )

        partial = _make_partial_file_result(
            "src/mypackage/utils.py",
            sample_skeleton,
            success_names=["get_name"],
            escalated_names=["get_value"],
        )

        with patch.object(gen._engine, "process_file", return_value=partial), \
             patch("startd8.micro_prime.prime_adapter.urlopen",
                   return_value=_make_ollama_mock()), \
             patch(
                 "startd8.micro_prime.prime_adapter.MicroPrimeCodeGenerator._get_cloud_agent",
                 return_value=mock_agent,
             ):
            result = gen.generate("Implement", {}, ["src/mypackage/utils.py"])

        # Partial skeleton should still have been written (from the main loop)
        output_file = tmp_path / "src/mypackage/utils.py"
        assert output_file.exists()

    def test_cost_tracking(
        self, tmp_path, sample_manifest, sample_skeleton,
    ):
        """GenerationResult.cost_usd includes element escalation costs from PricingService."""
        mock_agent = _make_mock_cloud_agent("return len(key)")

        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            cloud_agent_spec="anthropic:claude-haiku-4-5-20251001",
            output_dir=tmp_path,
        )

        partial = _make_partial_file_result(
            "src/mypackage/utils.py",
            sample_skeleton,
            success_names=["get_name"],
            escalated_names=["get_value"],
        )

        with patch.object(gen._engine, "process_file", return_value=partial), \
             patch("startd8.micro_prime.prime_adapter.urlopen",
                   return_value=_make_ollama_mock()), \
             patch(
                 "startd8.micro_prime.prime_adapter.MicroPrimeCodeGenerator._get_cloud_agent",
                 return_value=mock_agent,
             ), \
             patch(
                 "startd8.costs.pricing.PricingService"
             ) as MockPricing:
            MockPricing.return_value.calculate_total_cost.return_value = 0.008
            result = gen.generate("Implement", {}, ["src/mypackage/utils.py"])

        assert result.cost_usd == 0.008
        assert result.metadata["element_escalation_cost_usd"] == 0.008
        assert result.metadata["element_escalation_count"] == 1
        assert result.metadata["micro_prime_only"] is False

    def test_no_fallback_skips_gracefully(
        self, tmp_path, sample_manifest, sample_skeleton,
    ):
        """No fallback and no cloud_agent_spec -> no crash, partial kept."""
        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            fallback=None,
            output_dir=tmp_path,
        )

        partial = _make_partial_file_result(
            "src/mypackage/utils.py",
            sample_skeleton,
            success_names=["get_name"],
            escalated_names=["get_value"],
        )

        with patch.object(gen._engine, "process_file", return_value=partial), \
             patch("startd8.micro_prime.prime_adapter.urlopen",
                   return_value=_make_ollama_mock()):
            result = gen.generate("Implement", {}, ["src/mypackage/utils.py"])

        # No crash, but stubs remain — success is false
        assert result.success is False
        assert result.metadata["element_escalation_count"] == 0
        assert result.cost_usd == 0.0


# ── New tests for direct cloud escalation ────────────────────────────


class TestResolveCloudAgentSpec:
    """Tests for _resolve_cloud_agent_spec() priority chain."""

    def test_explicit_cloud_agent_spec_takes_priority(self):
        """Constructor cloud_agent_spec takes priority over fallback."""
        fallback = MagicMock()
        fallback.drafter_agent = "anthropic:claude-sonnet-4-6"

        gen = MicroPrimeCodeGenerator(
            fallback=fallback,
            cloud_agent_spec="anthropic:claude-haiku-4-5-20251001",
        )
        assert gen._resolve_cloud_agent_spec() == "anthropic:claude-haiku-4-5-20251001"

    def test_fallback_drafter_agent_string(self):
        """Falls back to fallback.drafter_agent when no explicit spec."""
        fallback = MagicMock()
        fallback.drafter_agent = "anthropic:claude-sonnet-4-6"

        gen = MicroPrimeCodeGenerator(fallback=fallback)
        assert gen._resolve_cloud_agent_spec() == "anthropic:claude-sonnet-4-6"

    def test_default_to_haiku(self):
        """Falls back to DRAFT_MODEL_CLAUDE_HAIKU when no spec and no fallback."""
        gen = MicroPrimeCodeGenerator()
        spec = gen._resolve_cloud_agent_spec()
        assert "anthropic" in spec
        assert "haiku" in spec

    def test_fallback_without_drafter_agent(self):
        """Fallback without drafter_agent -> defaults to DRAFT_MODEL_CLAUDE_HAIKU."""
        fallback = MagicMock(spec=[])  # spec=[] means no attributes
        gen = MicroPrimeCodeGenerator(fallback=fallback)
        spec = gen._resolve_cloud_agent_spec()
        assert "haiku" in spec


class TestPerElementFailureContinues:
    """Tests for per-element error isolation during cloud escalation."""

    def test_per_element_failure_continues(
        self, tmp_path, sample_manifest, sample_skeleton,
    ):
        """One element's cloud call fails, others still splice."""
        # We need a manifest with two escalated elements.
        # Use two elements: get_name and get_value, both escalated
        partial = FileResult(file_path="src/mypackage/utils.py")
        partial.element_results = [
            ElementResult(
                element_name="get_name",
                file_path="src/mypackage/utils.py",
                tier=TierClassification.MODERATE,
                success=False,
                escalation=EscalationResult(
                    reason=EscalationReason.TIER_TOO_HIGH,
                    detail="complex",
                ),
            ),
            ElementResult(
                element_name="get_value",
                file_path="src/mypackage/utils.py",
                tier=TierClassification.MODERATE,
                success=False,
                escalation=EscalationResult(
                    reason=EscalationReason.TIER_TOO_HIGH,
                    detail="complex",
                ),
            ),
        ]
        # Mark one as local success so it's a partial file (not file-level fallback)
        partial.element_results.insert(
            0,
            ElementResult(
                element_name="DEFAULT_TIMEOUT",
                file_path="src/mypackage/utils.py",
                tier=TierClassification.TRIVIAL,
                success=True,
                code="30",
                template_used=True,
            ),
        )
        partial.filled_skeleton = sample_skeleton

        # Mock agent: first call raises, second call succeeds
        mock_agent = MagicMock()
        mock_token_usage = MagicMock()
        mock_token_usage.input = 100
        mock_token_usage.output = 50
        mock_agent.generate.side_effect = [
            RuntimeError("API timeout"),  # first element fails
            ("return len(key)", 100, mock_token_usage),  # second element succeeds
        ]

        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            cloud_agent_spec="anthropic:claude-haiku-4-5-20251001",
            output_dir=tmp_path,
        )

        with patch.object(gen._engine, "process_file", return_value=partial), \
             patch("startd8.micro_prime.prime_adapter.urlopen",
                   return_value=_make_ollama_mock()), \
             patch(
                 "startd8.micro_prime.prime_adapter.MicroPrimeCodeGenerator._get_cloud_agent",
                 return_value=mock_agent,
             ):
            result = gen.generate("Implement", {}, ["src/mypackage/utils.py"])

        # Should not crash, and should have processed at least one element
        assert result is not None
        assert mock_agent.generate.call_count == 2


class TestCloudAgentSpecFromCloud:
    """Tests for cloud_agent_spec enabling escalation without fallback."""

    def test_cloud_spec_without_fallback_enables_escalation(
        self, tmp_path, sample_manifest, sample_skeleton,
    ):
        """cloud_agent_spec alone (no fallback) enables element-level escalation."""
        mock_agent = _make_mock_cloud_agent("return len(key)")

        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            cloud_agent_spec="anthropic:claude-haiku-4-5-20251001",
            fallback=None,
            output_dir=tmp_path,
        )

        partial = _make_partial_file_result(
            "src/mypackage/utils.py",
            sample_skeleton,
            success_names=["get_name"],
            escalated_names=["get_value"],
        )

        with patch.object(gen._engine, "process_file", return_value=partial), \
             patch("startd8.micro_prime.prime_adapter.urlopen",
                   return_value=_make_ollama_mock()), \
             patch(
                 "startd8.micro_prime.prime_adapter.MicroPrimeCodeGenerator._get_cloud_agent",
                 return_value=mock_agent,
             ):
            result = gen.generate("Implement", {}, ["src/mypackage/utils.py"])

        # Cloud agent was called (not skipped due to no fallback)
        mock_agent.generate.assert_called_once()
        assert result.metadata["element_escalation_count"] == 1


class TestClassElementSkipped:
    """Tests that class-level elements are skipped during cloud escalation."""

    def test_class_element_not_sent_to_cloud(
        self, tmp_path, sample_manifest, sample_skeleton,
    ):
        """Class elements are skipped — their methods are handled individually."""
        from startd8.forward_manifest import ForwardElementSpec, ForwardFileSpec
        from startd8.utils.code_manifest import ElementKind, Signature

        # Build a manifest with a class element escalated
        class_element = ForwardElementSpec(
            kind=ElementKind.CLASS,
            name="MyClass",
            signature=Signature(params=[], return_annotation=""),
        )
        method_element = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="get_value",
            signature=Signature(
                params=[
                    {"name": "self"},
                    {"name": "key", "annotation": "str"},
                ],
                return_annotation="int",
            ),
            parent_class="MyClass",
        )
        file_spec = ForwardFileSpec(
            file="src/mypackage/utils.py",
            imports=[],
            elements=[class_element, method_element],
        )
        manifest = MagicMock()
        manifest.file_specs = {"src/mypackage/utils.py": file_spec}

        # Both elements escalated, one local success (constant) to trigger
        # element-level escalation path
        partial = FileResult(file_path="src/mypackage/utils.py")
        partial.element_results = [
            ElementResult(
                element_name="DEFAULT_TIMEOUT",
                file_path="src/mypackage/utils.py",
                tier=TierClassification.TRIVIAL,
                success=True,
                code="30",
                template_used=True,
            ),
            ElementResult(
                element_name="MyClass",
                file_path="src/mypackage/utils.py",
                tier=TierClassification.MODERATE,
                success=False,
                escalation=EscalationResult(
                    reason=EscalationReason.TIER_TOO_HIGH,
                    detail="Class element",
                ),
            ),
            ElementResult(
                element_name="get_value",
                file_path="src/mypackage/utils.py",
                tier=TierClassification.MODERATE,
                success=False,
                escalation=EscalationResult(
                    reason=EscalationReason.TIER_TOO_HIGH,
                    detail="complex method",
                ),
            ),
        ]
        partial.filled_skeleton = sample_skeleton

        mock_agent = _make_mock_cloud_agent("return len(key)")

        gen = MicroPrimeCodeGenerator(
            manifest=manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            cloud_agent_spec="anthropic:claude-haiku-4-5-20251001",
            output_dir=tmp_path,
        )

        with patch.object(gen._engine, "process_file", return_value=partial), \
             patch("startd8.micro_prime.prime_adapter.urlopen",
                   return_value=_make_ollama_mock()), \
             patch(
                 "startd8.micro_prime.prime_adapter.MicroPrimeCodeGenerator._get_cloud_agent",
                 return_value=mock_agent,
             ):
            result = gen.generate("Implement", {}, ["src/mypackage/utils.py"])

        # Cloud agent called only once — for get_value, NOT for MyClass
        mock_agent.generate.assert_called_once()
        prompt = mock_agent.generate.call_args[0][0]
        assert "get_value" in prompt
