"""
Unit tests for data models and validation
"""

import pytest
from datetime import datetime, timezone

from startd8.models import Prompt, AgentResponse, TokenUsage, Benchmark
from pydantic import ValidationError


class TestPrompt:
    """Test Prompt model validation"""
    
    def test_valid_prompt(self):
        """Test creating a valid prompt"""
        prompt = Prompt(
            id="test-123",
            content="Valid content",
            version="1.0.0"
        )
        assert prompt.content == "Valid content"
        assert prompt.version == "1.0.0"
    
    def test_empty_content_rejected(self):
        """Test that empty content is rejected"""
        with pytest.raises(ValidationError):
            Prompt(
                id="test-123",
                content="",
                version="1.0.0"
            )
    
    def test_whitespace_only_content_rejected(self):
        """Test that whitespace-only content is rejected"""
        with pytest.raises(ValidationError):
            Prompt(
                id="test-123",
                content="   \n\t  ",
                version="1.0.0"
            )
    
    def test_content_too_long_rejected(self):
        """Test that content exceeding limit is rejected"""
        with pytest.raises(ValidationError):
            Prompt(
                id="test-123",
                content="x" * 1_000_001,
                version="1.0.0"
            )
    
    def test_invalid_version_format(self):
        """Test that invalid version format is rejected"""
        with pytest.raises(ValidationError):
            Prompt(
                id="test-123",
                content="Valid content",
                version="invalid"
            )
    
    def test_valid_semver_versions(self):
        """Test that valid semver formats are accepted"""
        valid_versions = ["1.0.0", "1.0.0-alpha", "1.0.0+build", "1.0.0-alpha+build"]
        
        for version in valid_versions:
            prompt = Prompt(
                id="test-123",
                content="Valid content",
                version=version
            )
            assert prompt.version == version
    
    def test_content_stripped(self):
        """Test that content is stripped of leading/trailing whitespace"""
        prompt = Prompt(
            id="test-123",
            content="  Valid content  ",
            version="1.0.0"
        )
        assert prompt.content == "Valid content"


class TestTokenUsage:
    """Test TokenUsage model validation"""
    
    def test_valid_token_usage(self):
        """Test creating valid token usage"""
        usage = TokenUsage(input=100, output=200, total=300)
        assert usage.input == 100
        assert usage.output == 200
        assert usage.total == 300
    
    def test_negative_tokens_rejected(self):
        """Test that negative token counts are rejected"""
        with pytest.raises(ValidationError):
            TokenUsage(input=-1, output=100, total=100)
    
    def test_total_must_equal_sum(self):
        """Test that total must equal input + output"""
        with pytest.raises(ValidationError):
            TokenUsage(input=100, output=200, total=250)
    
    def test_cost_estimate(self):
        """Test cost estimation"""
        usage = TokenUsage(input=1_000_000, output=1_000_000, total=2_000_000)
        cost = usage.cost_estimate
        # Should be approximately $3 + $15 = $18
        assert 17.5 < cost < 18.5


class TestAgentResponse:
    """Test AgentResponse model validation"""
    
    def test_valid_response(self):
        """Test creating a valid response"""
        response = AgentResponse(
            id="test-123",
            prompt_id="prompt-123",
            agent_name="test-agent",
            model="test-model",
            response="Test response",
            response_time_ms=100
        )
        assert response.response_time_ms == 100
    
    def test_negative_response_time_rejected(self):
        """Test that negative response time is rejected"""
        with pytest.raises(ValidationError):
            AgentResponse(
                id="test-123",
                prompt_id="prompt-123",
                agent_name="test",
                model="test",
                response="Test",
                response_time_ms=-1
            )
    
    def test_excessive_response_time_rejected(self):
        """Test that excessive response time is rejected"""
        with pytest.raises(ValidationError):
            AgentResponse(
                id="test-123",
                prompt_id="prompt-123",
                agent_name="test",
                model="test",
                response="Test",
                response_time_ms=100_000_000  # > 24 hours
            )
    
    def test_response_time_seconds_property(self):
        """Test response_time_seconds property"""
        response = AgentResponse(
            id="test-123",
            prompt_id="prompt-123",
            agent_name="test",
            model="test",
            response="Test",
            response_time_ms=1500
        )
        assert response.response_time_seconds == 1.5
    
    def test_tokens_per_second_property(self):
        """Test tokens_per_second property"""
        response = AgentResponse(
            id="test-123",
            prompt_id="prompt-123",
            agent_name="test",
            model="test",
            response="Test",
            response_time_ms=1000,
            token_usage=TokenUsage(input=100, output=200, total=300)
        )
        # Should be 200 output tokens / 1 second = 200 tokens/sec
        assert response.tokens_per_second == 200.0









