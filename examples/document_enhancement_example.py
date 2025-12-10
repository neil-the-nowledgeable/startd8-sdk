"""
Document Enhancement Chain - Usage Examples

This example demonstrates how to use the Document Enhancement Chain
to sequentially enhance documents using multiple AI agents.
"""

from pathlib import Path
from startd8.document_enhancement import DocumentEnhancementChain
from startd8.models import (
    DocumentEnhancementConfig,
    AgentConfig,
    ErrorHandling
)
from startd8.agents import GPT4Agent, ClaudeAgent, ComposerAgent, MockAgent
from startd8.framework import AgentFramework


def example_1_basic_enhancement():
    """
    Example 1: Basic document enhancement with two agents.
    
    This example chains GPT-4 and Claude to enhance a design document.
    """
    print("=" * 60)
    print("Example 1: Basic Document Enhancement")
    print("=" * 60)
    
    # Create a sample document
    doc_path = Path("sample_design.md")
    doc_path.write_text("""# Feature Design: User Authentication

## Overview
Basic login functionality.

## Requirements
- User can log in with email/password
- Passwords are hashed

## Implementation
TBD
""")
    
    # Configure enhancement chain
    config = DocumentEnhancementConfig(
        source_document=doc_path,
        enhancement_instructions="Add security considerations and API design sections",
        agents=[
            AgentConfig(
                agent_name="gpt4",
                agent_instance=GPT4Agent(),
                step_name="gpt4-enhancement",
                order=0
            ),
            AgentConfig(
                agent_name="claude",
                agent_instance=ClaudeAgent(),
                step_name="claude-refinement",
                order=1
            )
        ],
        save_intermediate=True,
        on_error=ErrorHandling.STOP
    )
    
    # Create framework for storage
    framework = AgentFramework(Path.home() / ".startd8")
    
    # Execute enhancement chain
    chain = DocumentEnhancementChain(config, framework)
    
    print("\nExecuting enhancement chain...")
    result = chain.run(
        on_step_start=lambda step, total, agent: print(f"  Starting step {step}/{total}: {agent}"),
        on_step_complete=lambda step, total, agent, res: print(f"  Completed step {step}/{total}: {agent} - {'✓' if res.success else '✗'}"),
    )
    
    # Display results
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
    
    # Cleanup
    doc_path.unlink()


def example_2_three_agent_chain():
    """
    Example 2: Three-agent enhancement chain.
    
    This example uses GPT-4 for structure, Claude for content, 
    and Composer for final polish.
    """
    print("\n" + "=" * 60)
    print("Example 2: Three-Agent Chain")
    print("=" * 60)
    
    doc_path = Path("api_design.md")
    doc_path.write_text("""# API Design

## Endpoints
- /users
- /posts

## Authentication
JWT tokens
""")
    
    config = DocumentEnhancementConfig(
        source_document=doc_path,
        enhancement_instructions="""
        1. Add detailed endpoint specifications
        2. Add request/response examples
        3. Add error handling documentation
        4. Polish and format consistently
        """,
        agents=[
            AgentConfig(
                agent_name="gpt4",
                agent_instance=GPT4Agent(),
                step_name="structure",
                order=0
            ),
            AgentConfig(
                agent_name="claude",
                agent_instance=ClaudeAgent(),
                step_name="content",
                order=1
            ),
            AgentConfig(
                agent_name="composer",
                agent_instance=ComposerAgent(),
                step_name="polish",
                order=2
            )
        ],
        save_intermediate=True,
        on_error=ErrorHandling.RETRY
    )
    
    framework = AgentFramework(Path.home() / ".startd8")
    chain = DocumentEnhancementChain(config, framework)
    
    print("\nEnhancement chain: GPT-4 → Claude → Composer")
    result = chain.run()
    
    print(f"\nCompleted {result.steps_completed}/{len(result.steps)} steps")
    print(f"Output: {result.output_path}")
    
    # Cleanup
    doc_path.unlink()


def example_3_error_handling():
    """
    Example 3: Demonstrating error handling with SKIP mode.
    
    This example shows how the chain continues even if one agent fails.
    """
    print("\n" + "=" * 60)
    print("Example 3: Error Handling (SKIP mode)")
    print("=" * 60)
    
    doc_path = Path("test_doc.md")
    doc_path.write_text("# Test Document\n\nBasic content.")
    
    # Use Mock agents for reliable testing
    config = DocumentEnhancementConfig(
        source_document=doc_path,
        enhancement_instructions="Enhance this document",
        agents=[
            AgentConfig(
                agent_name="mock1",
                agent_instance=MockAgent(name="mock1"),
                step_name="step1",
                order=0
            ),
            AgentConfig(
                agent_name="mock2",
                agent_instance=MockAgent(name="mock2"),
                step_name="step2",
                order=1
            ),
            AgentConfig(
                agent_name="mock3",
                agent_instance=MockAgent(name="mock3"),
                step_name="step3",
                order=2
            )
        ],
        save_intermediate=True,
        on_error=ErrorHandling.SKIP  # Continue even if agents fail
    )
    
    framework = AgentFramework(Path.home() / ".startd8")
    chain = DocumentEnhancementChain(config, framework)
    
    result = chain.run()
    
    print(f"\nAll steps completed despite any failures")
    print(f"Successful: {result.steps_completed}/{len(result.steps)}")
    print(f"Output: {result.output_path}")
    
    # Cleanup
    doc_path.unlink()


def example_4_minimal_config():
    """
    Example 4: Minimal configuration with no instructions.
    
    This lets agents use their own judgment for enhancement.
    """
    print("\n" + "=" * 60)
    print("Example 4: Minimal Configuration")
    print("=" * 60)
    
    doc_path = Path("minimal_doc.md")
    doc_path.write_text("# Project\n\nSome initial notes.")
    
    # Minimal config - no instructions, default error handling
    config = DocumentEnhancementConfig(
        source_document=doc_path,
        agents=[
            AgentConfig(
                agent_name="claude",
                agent_instance=ClaudeAgent(),
                step_name="enhance",
                order=0
            )
        ]
        # No instructions - agent uses own judgment
        # save_intermediate defaults to False
        # on_error defaults to STOP
    )
    
    framework = AgentFramework(Path.home() / ".startd8")
    chain = DocumentEnhancementChain(config, framework)
    
    result = chain.run()
    
    print(f"\nEnhancement complete!")
    print(f"Cost: ${result.total_cost:.4f}")
    print(f"Output: {result.output_path}")
    
    # Cleanup
    doc_path.unlink()


def example_5_custom_callbacks():
    """
    Example 5: Using custom callbacks for progress tracking.
    
    This demonstrates how to track progress with custom callbacks.
    """
    print("\n" + "=" * 60)
    print("Example 5: Custom Progress Callbacks")
    print("=" * 60)
    
    doc_path = Path("callback_test.md")
    doc_path.write_text("# Document\n\nContent to enhance.")
    
    config = DocumentEnhancementConfig(
        source_document=doc_path,
        agents=[
            AgentConfig(
                agent_name="mock1",
                agent_instance=MockAgent(name="mock1"),
                step_name="step1",
                order=0
            ),
            AgentConfig(
                agent_name="mock2",
                agent_instance=MockAgent(name="mock2"),
                step_name="step2",
                order=1
            )
        ]
    )
    
    framework = AgentFramework(Path.home() / ".startd8")
    chain = DocumentEnhancementChain(config, framework)
    
    # Custom callbacks
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
        on_progress=on_progress
    )
    
    print(f"\n{'=' * 60}")
    print(f"Chain complete: {result.chain_id}")
    
    # Cleanup
    doc_path.unlink()


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Document Enhancement Chain - Examples")
    print("=" * 60)
    print("\nNote: These examples use real AI agents (GPT-4, Claude, Composer).")
    print("Make sure you have API keys configured before running.")
    print("You can use Mock agents for testing without API keys.")
    print()
    
    # Uncomment the examples you want to run:
    
    # Example 1: Basic two-agent enhancement
    # example_1_basic_enhancement()
    
    # Example 2: Three-agent chain
    # example_2_three_agent_chain()
    
    # Example 3: Error handling with SKIP
    example_3_error_handling()
    
    # Example 4: Minimal configuration
    # example_4_minimal_config()
    
    # Example 5: Custom callbacks
    example_5_custom_callbacks()
    
    print("\n" + "=" * 60)
    print("Examples complete!")
    print("=" * 60)





