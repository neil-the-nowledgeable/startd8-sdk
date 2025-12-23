"""Document Enhancement Chain - Usage Examples

This example demonstrates how to use the Document Enhancement Chain
with ProviderRegistry-backed agents (provider:model) and mock agents.
"""

from __future__ import annotations

from pathlib import Path

from startd8.document_enhancement import DocumentEnhancementChain
from startd8.framework import AgentFramework
from startd8.models import AgentConfig, DocumentEnhancementConfig, ErrorHandling
from startd8.providers import ProviderRegistry


def _framework() -> AgentFramework:
    # Store outputs under the user config directory by default for examples.
    return AgentFramework(Path.home() / ".startd8")


def example_1_basic_enhancement():
    """Example 1: Basic document enhancement with two agents."""
    print("=" * 60)
    print("Example 1: Basic Document Enhancement (provider:model)")
    print("=" * 60)

    # Create a sample document
    doc_path = Path("sample_design.md")
    doc_path.write_text(
        """# Feature Design: User Authentication

## Overview
Basic login functionality.

## Requirements
- User can log in with email/password
- Passwords are hashed

## Implementation
TBD
""",
        encoding="utf-8",
    )

    ProviderRegistry.discover()
    openai = ProviderRegistry.get_provider("openai")
    anthropic = ProviderRegistry.get_provider("anthropic")
    if not openai or not anthropic:
        raise RuntimeError("Required providers not available")
    openai.validate_config({})
    anthropic.validate_config({})

    openai_agent = openai.create_agent("gpt-4-turbo-preview", name="openai-structure")
    anthropic_agent = anthropic.create_agent("claude-3-5-sonnet-20241022", name="anthropic-refine")

    config = DocumentEnhancementConfig(
        source_document=doc_path,
        enhancement_instructions="Add security considerations and API design sections",
        agents=[
            AgentConfig(
                agent_name="openai:gpt-4-turbo-preview",
                agent_instance=openai_agent,
                step_name="structure",
                order=0,
            ),
            AgentConfig(
                agent_name="anthropic:claude-3-5-sonnet-20241022",
                agent_instance=anthropic_agent,
                step_name="refinement",
                order=1,
            ),
        ],
        save_intermediate=True,
        on_error=ErrorHandling.STOP,
    )

    chain = DocumentEnhancementChain(config, _framework())

    print("\nExecuting enhancement chain...")
    result = chain.run(
        on_step_start=lambda step, total, agent: print(f"  Starting step {step}/{total}: {agent}"),
        on_step_complete=lambda step, total, agent, res: print(
            f"  Completed step {step}/{total}: {agent} - {'✓' if res.success else '✗'}"
        ),
    )

    print("\n" + "=" * 60)
    print("Results:")
    print("=" * 60)
    print(f"Success: {result.success}")
    print(f"Total steps: {len(result.steps)}")
    print(f"Successful: {result.steps_completed}")
    print(f"Failed: {result.steps_failed}")
    print(f"Total time: {result.total_time_ms}ms")
    print(f"Total tokens: {result.total_tokens:,}")
    print(f"Total cost: ${result.total_cost:.4f}")
    print(f"Output saved to: {result.output_path}")

    doc_path.unlink(missing_ok=True)


def example_2_three_agent_chain():
    """Example 2: Three-agent enhancement chain."""
    print("\n" + "=" * 60)
    print("Example 2: Three-Agent Chain")
    print("=" * 60)

    doc_path = Path("api_design.md")
    doc_path.write_text(
        """# API Design

## Endpoints
- /users
- /posts

## Authentication
JWT tokens
""",
        encoding="utf-8",
    )

    ProviderRegistry.discover()
    openai = ProviderRegistry.get_provider("openai")
    anthropic = ProviderRegistry.get_provider("anthropic")
    if not openai or not anthropic:
        raise RuntimeError("Required providers not available")
    openai.validate_config({})
    anthropic.validate_config({})

    agent_a = openai.create_agent("gpt-4-turbo-preview", name="openai-structure")
    agent_b = anthropic.create_agent("claude-3-5-sonnet-20241022", name="anthropic-content")
    agent_c = openai.create_agent("gpt-4-turbo-preview", name="openai-polish")

    config = DocumentEnhancementConfig(
        source_document=doc_path,
        enhancement_instructions=(
            "1. Add detailed endpoint specifications\n"
            "2. Add request/response examples\n"
            "3. Add error handling documentation\n"
            "4. Polish and format consistently"
        ),
        agents=[
            AgentConfig(
                agent_name="openai:gpt-4-turbo-preview",
                agent_instance=agent_a,
                step_name="structure",
                order=0,
            ),
            AgentConfig(
                agent_name="anthropic:claude-3-5-sonnet-20241022",
                agent_instance=agent_b,
                step_name="content",
                order=1,
            ),
            AgentConfig(
                agent_name="openai:gpt-4-turbo-preview",
                agent_instance=agent_c,
                step_name="polish",
                order=2,
            ),
        ],
        save_intermediate=True,
        on_error=ErrorHandling.RETRY,
    )

    chain = DocumentEnhancementChain(config, _framework())

    print("\nEnhancement chain: OpenAI → Anthropic → OpenAI")
    result = chain.run()

    print(f"\nCompleted {result.steps_completed}/{len(result.steps)} steps")
    print(f"Output: {result.output_path}")

    doc_path.unlink(missing_ok=True)


def example_3_error_handling():
    """Example 3: Demonstrating error handling with SKIP mode (mock provider)."""
    print("\n" + "=" * 60)
    print("Example 3: Error Handling (SKIP mode)")
    print("=" * 60)

    doc_path = Path("test_doc.md")
    doc_path.write_text("# Test Document\n\nBasic content.", encoding="utf-8")

    ProviderRegistry.discover()
    mock = ProviderRegistry.get_provider("mock")
    if not mock:
        raise RuntimeError("Mock provider not available")

    config = DocumentEnhancementConfig(
        source_document=doc_path,
        enhancement_instructions="Enhance this document",
        agents=[
            AgentConfig(
                agent_name="mock:mock-model",
                agent_instance=mock.create_agent("mock-model", name="mock1"),
                step_name="step1",
                order=0,
            ),
            AgentConfig(
                agent_name="mock:mock-model",
                agent_instance=mock.create_agent("mock-model", name="mock2"),
                step_name="step2",
                order=1,
            ),
            AgentConfig(
                agent_name="mock:mock-model",
                agent_instance=mock.create_agent("mock-model", name="mock3"),
                step_name="step3",
                order=2,
            ),
        ],
        save_intermediate=True,
        on_error=ErrorHandling.SKIP,
    )

    chain = DocumentEnhancementChain(config, _framework())
    result = chain.run()

    print("\nAll steps completed despite any failures")
    print(f"Successful: {result.steps_completed}/{len(result.steps)}")
    print(f"Output: {result.output_path}")

    doc_path.unlink(missing_ok=True)


def example_4_minimal_config():
    """Example 4: Minimal configuration with no instructions."""
    print("\n" + "=" * 60)
    print("Example 4: Minimal Configuration")
    print("=" * 60)

    doc_path = Path("minimal_doc.md")
    doc_path.write_text("# Project\n\nSome initial notes.", encoding="utf-8")

    ProviderRegistry.discover()
    anthropic = ProviderRegistry.get_provider("anthropic")
    if not anthropic:
        raise RuntimeError("Anthropic provider not available")
    anthropic.validate_config({})

    config = DocumentEnhancementConfig(
        source_document=doc_path,
        agents=[
            AgentConfig(
                agent_name="anthropic:claude-3-5-sonnet-20241022",
                agent_instance=anthropic.create_agent("claude-3-5-sonnet-20241022"),
                step_name="enhance",
                order=0,
            )
        ],
        # No instructions -> agent uses its own judgment
        save_intermediate=False,
        on_error=ErrorHandling.STOP,
    )

    chain = DocumentEnhancementChain(config, _framework())
    result = chain.run()

    print("\nEnhancement complete!")
    print(f"Cost: ${result.total_cost:.4f}")
    print(f"Output: {result.output_path}")

    doc_path.unlink(missing_ok=True)


def example_5_custom_callbacks():
    """Example 5: Using custom callbacks for progress tracking (mock provider)."""
    print("\n" + "=" * 60)
    print("Example 5: Custom Progress Callbacks")
    print("=" * 60)

    doc_path = Path("callback_test.md")
    doc_path.write_text("# Document\n\nContent to enhance.", encoding="utf-8")

    ProviderRegistry.discover()
    mock = ProviderRegistry.get_provider("mock")
    if not mock:
        raise RuntimeError("Mock provider not available")

    config = DocumentEnhancementConfig(
        source_document=doc_path,
        agents=[
            AgentConfig(
                agent_name="mock:mock-model",
                agent_instance=mock.create_agent("mock-model", name="mock1"),
                step_name="step1",
                order=0,
            ),
            AgentConfig(
                agent_name="mock:mock-model",
                agent_instance=mock.create_agent("mock-model", name="mock2"),
                step_name="step2",
                order=1,
            ),
        ],
    )

    chain = DocumentEnhancementChain(config, _framework())

    def on_step_start(step_num, total, agent_name):
        print(f"\n→ Starting step {step_num}/{total}: {agent_name}")
        print("  Processing...")

    def on_step_complete(step_num, total, agent_name, result):
        if result.success:
            tokens = result.token_usage.total if result.token_usage else 0
            print(f"  ✓ Complete! ({result.response_time_ms}ms, {tokens:,} tokens)")
        else:
            print(f"  ✗ Failed: {result.error}")

    def on_progress(current, total):
        percent = (current / total) * 100
        print(f"  Progress: {percent:.0f}%")

    result = chain.run(
        on_step_start=on_step_start,
        on_step_complete=on_step_complete,
        on_progress=on_progress,
    )

    print(f"\n{'=' * 60}")
    print(f"Chain complete: {result.chain_id}")

    doc_path.unlink(missing_ok=True)


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Document Enhancement Chain - Examples")
    print("=" * 60)
    print("\nNote: Some examples use real providers (OpenAI/Anthropic).")
    print("Make sure you have API keys configured before running.")
    print("Mock examples run without API keys.")
    print()

    # Uncomment examples to run
    # example_1_basic_enhancement()
    # example_2_three_agent_chain()
    example_3_error_handling()
    # example_4_minimal_config()
    example_5_custom_callbacks()
