"""
Unit tests for AgentFramework
"""

import pytest

from startd8 import AgentFramework
from startd8.models import TokenUsage
from startd8.exceptions import ValidationError
from startd8.agents import MockAgent


class TestAgentFramework:
    """Test AgentFramework operations"""
    
    def test_create_prompt(self, framework: AgentFramework):
        """Test creating a prompt"""
        prompt = framework.create_prompt(
            content="Test content",
            version="1.0.0",
            tags=["test"]
        )
        
        assert prompt.id is not None
        assert prompt.content == "Test content"
        assert prompt.version == "1.0.0"
        assert "test" in prompt.tags
    
    def test_create_prompt_validation_empty_content(self, framework: AgentFramework):
        """Test that empty content is rejected"""
        with pytest.raises(ValidationError):
            framework.create_prompt(
                content="",
                version="1.0.0"
            )
    
    def test_create_prompt_validation_invalid_version(self, framework: AgentFramework):
        """Test that invalid version format is rejected"""
        with pytest.raises(ValidationError):
            framework.create_prompt(
                content="Test",
                version="invalid-version"
            )
    
    def test_get_prompt(self, framework: AgentFramework):
        """Test retrieving a prompt"""
        prompt = framework.create_prompt(
            content="Test",
            version="1.0.0"
        )
        
        retrieved = framework.get_prompt(prompt.id)
        assert retrieved is not None
        assert retrieved.id == prompt.id
    
    def test_list_prompts(self, framework: AgentFramework):
        """Test listing prompts"""
        framework.create_prompt(content="Test 1", version="1.0.0", tags=["tag1"])
        framework.create_prompt(content="Test 2", version="1.0.0", tags=["tag2"])
        framework.create_prompt(content="Test 3", version="1.0.0", tags=["tag1"])
        
        all_prompts = framework.list_prompts()
        assert len(all_prompts) == 3
        
        filtered = framework.list_prompts(tags=["tag1"])
        assert len(filtered) == 2
    
    def test_record_response(self, framework: AgentFramework, sample_prompt: Prompt):
        """Test recording a response"""
        # Save prompt first
        framework.storage.save_prompt(sample_prompt)
        
        token_usage = TokenUsage(input=100, output=200, total=300)
        response = framework.record_response(
            prompt_id=sample_prompt.id,
            agent_name="test-agent",
            model="test-model",
            response="Test response",
            response_time_ms=150,
            token_usage=token_usage
        )
        
        assert response.id is not None
        assert response.prompt_id == sample_prompt.id
        assert response.agent_name == "test-agent"
    
    def test_record_response_validation_negative_time(self, framework: AgentFramework, sample_prompt: Prompt):
        """Test that negative response time is rejected"""
        framework.storage.save_prompt(sample_prompt)
        
        with pytest.raises(ValidationError):
            framework.record_response(
                prompt_id=sample_prompt.id,
                agent_name="test",
                model="test",
                response="Test",
                response_time_ms=-1
            )
    
    def test_list_responses(self, framework: AgentFramework, sample_prompt: Prompt):
        """Test listing responses"""
        framework.storage.save_prompt(sample_prompt)
        
        framework.record_response(
            prompt_id=sample_prompt.id,
            agent_name="agent1",
            model="model1",
            response="Response 1",
            response_time_ms=100
        )
        
        framework.record_response(
            prompt_id=sample_prompt.id,
            agent_name="agent2",
            model="model2",
            response="Response 2",
            response_time_ms=200
        )
        
        all_responses = framework.list_responses()
        assert len(all_responses) == 2
        
        filtered = framework.list_responses(prompt_id=sample_prompt.id)
        assert len(filtered) == 2
        
        agent_filtered = framework.list_responses(agent_name="agent1")
        assert len(agent_filtered) == 1
    
    def test_create_benchmark(self, framework: AgentFramework, sample_prompt: Prompt):
        """Test creating a benchmark"""
        framework.storage.save_prompt(sample_prompt)
        
        benchmark = framework.create_benchmark(
            name="Test Benchmark",
            prompt_id=sample_prompt.id
        )
        
        assert benchmark.id is not None
        assert benchmark.name == "Test Benchmark"
        assert benchmark.prompt_id == sample_prompt.id
    
    def test_complete_benchmark(self, framework: AgentFramework, sample_prompt: Prompt):
        """Test completing a benchmark"""
        framework.storage.save_prompt(sample_prompt)
        
        benchmark = framework.create_benchmark(
            name="Test",
            prompt_id=sample_prompt.id
        )
        
        # Add some responses
        framework.record_response(
            prompt_id=sample_prompt.id,
            agent_name="agent1",
            model="model1",
            response="Response",
            response_time_ms=100
        )
        
        completed = framework.complete_benchmark(
            benchmark.id,
            summary="Test summary"
        )
        
        assert completed.status == "completed"
        assert completed.summary == "Test summary"
        assert completed.completed_at is not None
        assert len(completed.response_ids) > 0
    
    def test_compare_responses(self, framework: AgentFramework, sample_prompt: Prompt):
        """Test comparing responses"""
        framework.storage.save_prompt(sample_prompt)
        
        # Add multiple responses
        for i in range(3):
            framework.record_response(
                prompt_id=sample_prompt.id,
                agent_name=f"agent{i}",
                model=f"model{i}",
                response=f"Response {i}",
                response_time_ms=100 + i * 50,
                token_usage=TokenUsage(input=50, output=50, total=100)
            )
        
        comparison = framework.compare_responses(sample_prompt.id)
        
        assert comparison['total_responses'] == 3
        assert comparison['avg_response_time_ms'] > 0
        assert len(comparison['rankings']['by_speed']) == 3









