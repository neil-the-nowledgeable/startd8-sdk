"""
Unit tests for Document Enhancement Chain
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from startd8.document_enhancement import (
    DocumentEnhancementChain,
    DocumentExtractionError,
    AgentFailureError,
    InvalidDocumentError,
    ENHANCEMENT_PROMPT_TEMPLATE
)
from startd8.models import (
    DocumentEnhancementConfig,
    EnhancementAgentConfig,
    ErrorHandling,
    TokenUsage
)
from startd8.agents import MockAgent


class TestPromptBuilding:
    """Test prompt building logic"""
    
    def test_build_prompt_with_instructions(self, tmp_path):
        """Test prompt building with user instructions"""
        # Create test document
        doc_path = tmp_path / "test.md"
        doc_path.write_text("# Test Document\n\nContent here.")
        
        config = DocumentEnhancementConfig(
            source_document=doc_path,
            enhancement_instructions="Add examples",
            agents=[
                EnhancementAgentConfig(
                    agent_name="mock",
                    agent_instance=MockAgent(),
                    step_name="mock-step",
                    order=0
                )
            ]
        )
        
        chain = DocumentEnhancementChain(config)
        
        prompt = chain._build_prompt(
            document_content="# Test\nContent",
            instructions="Add examples",
            step_number=0
        )
        
        assert "# Test\nContent" in prompt
        assert "Add examples" in prompt
        assert "enhanced version" in prompt.lower()
    
    def test_build_prompt_without_instructions(self, tmp_path):
        """Test prompt building without instructions"""
        doc_path = tmp_path / "test.md"
        doc_path.write_text("# Test")
        
        config = DocumentEnhancementConfig(
            source_document=doc_path,
            agents=[
                EnhancementAgentConfig(
                    agent_name="mock",
                    agent_instance=MockAgent(),
                    step_name="mock-step",
                    order=0
                )
            ]
        )
        
        chain = DocumentEnhancementChain(config)
        
        prompt = chain._build_prompt(
            document_content="# Test",
            instructions=None,
            step_number=0
        )
        
        assert "# Test" in prompt
        assert "expertise" in prompt.lower()
    
    def test_build_prompt_with_step_context(self, tmp_path):
        """Test prompt building includes step context for non-first steps"""
        doc_path = tmp_path / "test.md"
        doc_path.write_text("# Test")
        
        config = DocumentEnhancementConfig(
            source_document=doc_path,
            agents=[
                EnhancementAgentConfig(
                    agent_name="mock",
                    agent_instance=MockAgent(),
                    step_name="mock-step",
                    order=0
                )
            ]
        )
        
        chain = DocumentEnhancementChain(config)
        
        prompt = chain._build_prompt(
            document_content="# Test",
            instructions="Improve",
            step_number=2,
            previous_agent="gpt4"
        )
        
        assert "gpt4" in prompt
        assert "already been enhanced" in prompt.lower()


class TestDocumentExtraction:
    """Test document extraction from agent responses"""
    
    def test_extract_from_markdown_code_block(self, tmp_path):
        """Test extraction from markdown code block"""
        doc_path = tmp_path / "test.md"
        doc_path.write_text("# Original")
        
        config = DocumentEnhancementConfig(
            source_document=doc_path,
            agents=[
                EnhancementAgentConfig(
                    agent_name="mock",
                    agent_instance=MockAgent(),
                    step_name="mock-step",
                    order=0
                )
            ]
        )
        
        chain = DocumentEnhancementChain(config)
        
        response = """Here is the enhanced document:

```markdown
# Enhanced Document

This is the improved version.
```

Hope this helps!
"""
        
        extracted = chain._extract_document_from_response(response, "# Original")
        
        assert "# Enhanced Document" in extracted
        assert "improved version" in extracted
        assert "Hope this helps" not in extracted
    
    def test_extract_from_md_code_block(self, tmp_path):
        """Test extraction from ```md code block"""
        doc_path = tmp_path / "test.md"
        doc_path.write_text("# Original")
        
        config = DocumentEnhancementConfig(
            source_document=doc_path,
            agents=[
                EnhancementAgentConfig(
                    agent_name="mock",
                    agent_instance=MockAgent(),
                    step_name="mock-step",
                    order=0
                )
            ]
        )
        
        chain = DocumentEnhancementChain(config)
        
        response = """```md
# Enhanced Document

Content here.
```"""
        
        extracted = chain._extract_document_from_response(response, "# Original")
        
        assert "# Enhanced Document" in extracted
        assert "Content here" in extracted
    
    def test_extract_from_plain_markdown(self, tmp_path):
        """Test extraction when response is plain markdown"""
        doc_path = tmp_path / "test.md"
        doc_path.write_text("# Original")
        
        config = DocumentEnhancementConfig(
            source_document=doc_path,
            agents=[
                EnhancementAgentConfig(
                    agent_name="mock",
                    agent_instance=MockAgent(),
                    step_name="mock-step",
                    order=0
                )
            ]
        )
        
        chain = DocumentEnhancementChain(config)
        
        response = """# Enhanced Document

## Section 1

Content here.

## Section 2

More content.
"""
        
        extracted = chain._extract_document_from_response(response, "# Original")
        
        assert "# Enhanced Document" in extracted
        assert "## Section 1" in extracted
        assert "## Section 2" in extracted
    
    def test_extract_fallback_to_full_response(self, tmp_path):
        """Test fallback to using full response"""
        doc_path = tmp_path / "test.md"
        doc_path.write_text("# Original")
        
        config = DocumentEnhancementConfig(
            source_document=doc_path,
            agents=[
                EnhancementAgentConfig(
                    agent_name="mock",
                    agent_instance=MockAgent(),
                    step_name="mock-step",
                    order=0
                )
            ]
        )
        
        chain = DocumentEnhancementChain(config)
        
        response = "Some text without markdown headers or code blocks."
        
        extracted = chain._extract_document_from_response(response, "# Original")
        
        # Should return the response as-is
        assert extracted == response.strip()
    
    def test_extract_empty_response_raises_error(self, tmp_path):
        """Test that empty response raises error"""
        doc_path = tmp_path / "test.md"
        doc_path.write_text("# Original")
        
        config = DocumentEnhancementConfig(
            source_document=doc_path,
            agents=[
                EnhancementAgentConfig(
                    agent_name="mock",
                    agent_instance=MockAgent(),
                    step_name="mock-step",
                    order=0
                )
            ]
        )
        
        chain = DocumentEnhancementChain(config)
        
        with pytest.raises(DocumentExtractionError):
            chain._extract_document_from_response("", "# Original")


class TestChainExecution:
    """Test chain execution logic"""
    
    def test_single_agent_chain(self, tmp_path):
        """Test chain with single agent"""
        doc_path = tmp_path / "test.md"
        doc_path.write_text("# Original Document\n\nContent here.")
        
        mock_agent = MockAgent()
        
        config = DocumentEnhancementConfig(
            source_document=doc_path,
            enhancement_instructions="Add examples",
            agents=[
                EnhancementAgentConfig(
                    agent_name="mock",
                    agent_instance=mock_agent,
                    step_name="mock-enhancement",
                    order=0
                )
            ]
        )
        
        chain = DocumentEnhancementChain(config)
        result = chain.run()
        
        assert result.success
        assert len(result.steps) == 1
        assert result.steps[0].agent_name == "mock"
        assert result.steps[0].success
        assert result.output_path is not None
        assert result.output_path.exists()
    
    def test_multi_agent_chain(self, tmp_path):
        """Test chain with multiple agents"""
        doc_path = tmp_path / "test.md"
        doc_path.write_text("# Original\n\nContent.")
        
        config = DocumentEnhancementConfig(
            source_document=doc_path,
            agents=[
                EnhancementAgentConfig(
                    agent_name="mock1",
                    agent_instance=MockAgent(name="mock1"),
                    step_name="step1",
                    order=0
                ),
                EnhancementAgentConfig(
                    agent_name="mock2",
                    agent_instance=MockAgent(name="mock2"),
                    step_name="step2",
                    order=1
                ),
                EnhancementAgentConfig(
                    agent_name="mock3",
                    agent_instance=MockAgent(name="mock3"),
                    step_name="step3",
                    order=2
                )
            ]
        )
        
        chain = DocumentEnhancementChain(config)
        result = chain.run()
        
        assert result.success
        assert len(result.steps) == 3
        assert result.steps[0].agent_name == "mock1"
        assert result.steps[1].agent_name == "mock2"
        assert result.steps[2].agent_name == "mock3"
        assert all(step.success for step in result.steps)
    
    def test_agents_run_in_correct_order(self, tmp_path):
        """Test agents run in specified order"""
        doc_path = tmp_path / "test.md"
        doc_path.write_text("# Original")
        
        # Create agents with specific order (not sequential)
        config = DocumentEnhancementConfig(
            source_document=doc_path,
            agents=[
                EnhancementAgentConfig(
                    agent_name="third",
                    agent_instance=MockAgent(name="third"),
                    step_name="step3",
                    order=2
                ),
                EnhancementAgentConfig(
                    agent_name="first",
                    agent_instance=MockAgent(name="first"),
                    step_name="step1",
                    order=0
                ),
                EnhancementAgentConfig(
                    agent_name="second",
                    agent_instance=MockAgent(name="second"),
                    step_name="step2",
                    order=1
                )
            ]
        )
        
        chain = DocumentEnhancementChain(config)
        result = chain.run()
        
        # Check execution order
        assert result.steps[0].agent_name == "first"
        assert result.steps[1].agent_name == "second"
        assert result.steps[2].agent_name == "third"
    
    def test_intermediate_results_saved(self, tmp_path):
        """Test intermediate results are saved when configured"""
        doc_path = tmp_path / "test.md"
        doc_path.write_text("# Original")
        
        config = DocumentEnhancementConfig(
            source_document=doc_path,
            agents=[
                EnhancementAgentConfig(
                    agent_name="mock1",
                    agent_instance=MockAgent(name="mock1"),
                    step_name="step1",
                    order=0
                ),
                EnhancementAgentConfig(
                    agent_name="mock2",
                    agent_instance=MockAgent(name="mock2"),
                    step_name="step2",
                    order=1
                )
            ],
            save_intermediate=True
        )
        
        chain = DocumentEnhancementChain(config)
        result = chain.run()
        
        # Check intermediate paths exist
        for step in result.steps:
            if step.success:
                assert step.intermediate_path is not None
                assert step.intermediate_path.exists()
    
    def test_callbacks_invoked(self, tmp_path):
        """Test callbacks are invoked during execution"""
        doc_path = tmp_path / "test.md"
        doc_path.write_text("# Original")
        
        config = DocumentEnhancementConfig(
            source_document=doc_path,
            agents=[
                EnhancementAgentConfig(
                    agent_name="mock",
                    agent_instance=MockAgent(),
                    step_name="step1",
                    order=0
                )
            ]
        )
        
        chain = DocumentEnhancementChain(config)
        
        start_calls = []
        complete_calls = []
        progress_calls = []
        
        def on_start(step, total, agent):
            start_calls.append((step, total, agent))
        
        def on_complete(step, total, agent, result):
            complete_calls.append((step, total, agent))
        
        def on_progress(current, total):
            progress_calls.append((current, total))
        
        result = chain.run(
            on_step_start=on_start,
            on_step_complete=on_complete,
            on_progress=on_progress
        )
        
        assert len(start_calls) == 1
        assert len(complete_calls) == 1
        assert len(progress_calls) == 1


class TestErrorHandling:
    """Test error handling scenarios"""
    
    def test_stop_on_error(self, tmp_path):
        """Test STOP error handling stops chain immediately"""
        doc_path = tmp_path / "test.md"
        doc_path.write_text("# Original")
        
        # Create failing agent
        failing_agent = Mock(spec=MockAgent)
        failing_agent.name = "failing"
        failing_agent.model = "mock-model"
        failing_agent.generate.side_effect = Exception("Agent failed")
        
        config = DocumentEnhancementConfig(
            source_document=doc_path,
            agents=[
                EnhancementAgentConfig(
                    agent_name="mock1",
                    agent_instance=MockAgent(name="mock1"),
                    step_name="step1",
                    order=0
                ),
                EnhancementAgentConfig(
                    agent_name="failing",
                    agent_instance=failing_agent,
                    step_name="step2",
                    order=1
                ),
                EnhancementAgentConfig(
                    agent_name="mock3",
                    agent_instance=MockAgent(name="mock3"),
                    step_name="step3",
                    order=2
                )
            ],
            on_error=ErrorHandling.STOP
        )
        
        chain = DocumentEnhancementChain(config)
        result = chain.run()
        
        # Should have 2 steps: 1 success, 1 failure
        assert len(result.steps) == 2
        assert result.steps[0].success
        assert not result.steps[1].success
        assert not result.success
    
    def test_skip_on_error(self, tmp_path):
        """Test SKIP error handling continues past failures"""
        doc_path = tmp_path / "test.md"
        doc_path.write_text("# Original")
        
        # Create failing agent
        failing_agent = Mock(spec=MockAgent)
        failing_agent.name = "failing"
        failing_agent.model = "mock-model"
        failing_agent.generate.side_effect = Exception("Agent failed")
        
        config = DocumentEnhancementConfig(
            source_document=doc_path,
            agents=[
                EnhancementAgentConfig(
                    agent_name="mock1",
                    agent_instance=MockAgent(name="mock1"),
                    step_name="step1",
                    order=0
                ),
                EnhancementAgentConfig(
                    agent_name="failing",
                    agent_instance=failing_agent,
                    step_name="step2",
                    order=1
                ),
                EnhancementAgentConfig(
                    agent_name="mock3",
                    agent_instance=MockAgent(name="mock3"),
                    step_name="step3",
                    order=2
                )
            ],
            on_error=ErrorHandling.SKIP
        )
        
        chain = DocumentEnhancementChain(config)
        result = chain.run()
        
        # Should have all 3 steps
        assert len(result.steps) == 3
        assert result.steps[0].success
        assert not result.steps[1].success
        assert result.steps[2].success
    
    def test_invalid_document_path(self, tmp_path):
        """Test handling of invalid document path"""
        doc_path = tmp_path / "nonexistent.md"
        
        with pytest.raises(ValueError, match="does not exist"):
            config = DocumentEnhancementConfig(
                source_document=doc_path,
                agents=[
                    EnhancementAgentConfig(
                        agent_name="mock",
                        agent_instance=MockAgent(),
                        step_name="step1",
                        order=0
                    )
                ]
            )


class TestMetricsTracking:
    """Test metrics tracking"""
    
    def test_token_usage_tracked(self, tmp_path):
        """Test token usage is tracked"""
        doc_path = tmp_path / "test.md"
        doc_path.write_text("# Original")
        
        config = DocumentEnhancementConfig(
            source_document=doc_path,
            agents=[
                EnhancementAgentConfig(
                    agent_name="mock",
                    agent_instance=MockAgent(),
                    step_name="step1",
                    order=0
                )
            ]
        )
        
        chain = DocumentEnhancementChain(config)
        result = chain.run()
        
        assert result.total_tokens > 0
        assert result.total_cost >= 0
        assert result.total_time_ms > 0
    
    def test_chain_id_unique(self, tmp_path):
        """Test each chain has unique ID"""
        doc_path = tmp_path / "test.md"
        doc_path.write_text("# Original")
        
        config = DocumentEnhancementConfig(
            source_document=doc_path,
            agents=[
                EnhancementAgentConfig(
                    agent_name="mock",
                    agent_instance=MockAgent(),
                    step_name="step1",
                    order=0
                )
            ]
        )
        
        chain1 = DocumentEnhancementChain(config)
        chain2 = DocumentEnhancementChain(config)
        
        assert chain1.chain_id != chain2.chain_id
        assert chain1.chain_id.startswith("chain-")


class TestOutputGeneration:
    """Test output file generation"""
    
    def test_final_document_saved(self, tmp_path):
        """Test final document is saved"""
        doc_path = tmp_path / "test.md"
        doc_path.write_text("# Original")
        
        config = DocumentEnhancementConfig(
            source_document=doc_path,
            agents=[
                EnhancementAgentConfig(
                    agent_name="mock",
                    agent_instance=MockAgent(),
                    step_name="step1",
                    order=0
                )
            ]
        )
        
        chain = DocumentEnhancementChain(config)
        result = chain.run()
        
        assert result.output_path is not None
        assert result.output_path.exists()
        assert result.output_path.name == "enhanced_final.md"
        
        # Read and verify content
        content = result.output_path.read_text()
        assert len(content) > 0
    
    def test_output_directory_structure(self, tmp_path):
        """Test output directory has correct structure"""
        doc_path = tmp_path / "test.md"
        doc_path.write_text("# Original")
        
        config = DocumentEnhancementConfig(
            source_document=doc_path,
            agents=[
                EnhancementAgentConfig(
                    agent_name="mock",
                    agent_instance=MockAgent(),
                    step_name="step1",
                    order=0
                )
            ],
            save_intermediate=True
        )
        
        chain = DocumentEnhancementChain(config)
        result = chain.run()
        
        output_dir = result.output_path.parent
        
        # Check directory name format (YYYYMMDD_HHMM)
        assert len(output_dir.name) == 13  # YYYYMMDD_HHMM
        assert "_" in output_dir.name
        
        # Check final file exists
        assert (output_dir / "enhanced_final.md").exists()
        
        # Check intermediate directories exist
        assert (output_dir / "step1_mock").exists()











