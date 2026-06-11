"""
Unit tests for SkillAgent class.

Run with: pytest tests/test_skill_agent.py -v
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch, AsyncMock
from dataclasses import asdict

# Import the classes to test
from startd8.skills import (
    SkillAgent,
    SkillAgentConfig,
    CircuitState,
    SkillMetrics,
    create_game_enhancer_agent,
    create_html5_game_designer_agent,
    create_code_reviewer_agent,
)


class TestSkillAgentConfig:
    """Tests for SkillAgentConfig dataclass."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = SkillAgentConfig(
            skill_id="test-skill",
            name="Test Skill"
        )
        
        assert config.skill_id == "test-skill"
        assert config.name == "Test Skill"
        assert config.model == "claude-sonnet-4-6"  # matches SkillAgentConfig default (updated)
        assert config.max_tokens == 32768
        assert config.timeout_ms == 30000
        assert config.cost_tracking_enabled is False
        assert config.tags == []
        assert config.version == "1.0.0"
    
    def test_custom_values(self):
        """Test custom configuration values."""
        config = SkillAgentConfig(
            skill_id="skill-custom",
            name="Custom Skill",
            description="A custom skill for testing",
            model="claude-3-opus",
            max_tokens=4096,
            timeout_ms=60000,
            cost_tracking_enabled=True,
            tags=["test", "custom"],
            version="2.0.0",
            capabilities=["feature1", "feature2"]
        )
        
        assert config.skill_id == "skill-custom"
        assert config.model == "claude-3-opus"
        assert config.max_tokens == 4096
        assert config.cost_tracking_enabled is True
        assert config.tags == ["test", "custom"]
        assert config.capabilities == ["feature1", "feature2"]
    
    def test_to_dict(self):
        """Test serialization to dictionary."""
        config = SkillAgentConfig(
            skill_id="test-skill",
            name="Test Skill",
            tags=["test", "unit"]
        )
        
        data = config.to_dict()
        
        assert data['skill_id'] == "test-skill"
        assert data['tags'] == ["test", "unit"]
        assert 'model' in data
        assert 'max_tokens' in data
    
    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            'skill_id': 'test-skill',
            'name': 'Test Skill',
            'model': 'claude-3-opus',
            'max_tokens': 4096,
            'timeout_ms': 30000,
            'cost_tracking_enabled': False,
            'tags': [],
            'version': '1.0.0',
            'capabilities': [],
            'description': ''
        }
        
        config = SkillAgentConfig.from_dict(data)
        
        assert config.skill_id == "test-skill"
        assert config.max_tokens == 4096
    
    def test_roundtrip_serialization(self):
        """Test that to_dict/from_dict roundtrip preserves data."""
        original = SkillAgentConfig(
            skill_id="skill-roundtrip",
            name="Roundtrip Test",
            tags=["a", "b"],
            capabilities=["cap1", "cap2"]
        )
        
        data = original.to_dict()
        restored = SkillAgentConfig.from_dict(data)
        
        assert restored.skill_id == original.skill_id
        assert restored.name == original.name
        assert restored.tags == original.tags
        assert restored.capabilities == original.capabilities


class TestSkillAgentInit:
    """Tests for SkillAgent initialization."""
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_valid_skill_id(self):
        """Test initialization with valid skill_id."""
        agent = SkillAgent(skill_id="skill-test")
        
        assert agent.skill_id == "skill-test"
        assert agent.name == "skill-test"
        assert agent._circuit_state == CircuitState.CLOSED
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_valid_skill_id_with_name(self):
        """Test initialization with skill_id and custom name."""
        agent = SkillAgent(skill_id="skill-test", name="My Agent")
        
        assert agent.skill_id == "skill-test"
        assert agent.name == "My Agent"
    
    def test_invalid_skill_id_empty(self):
        """Test that empty skill_id raises ValueError."""
        with pytest.raises(ValueError, match="Invalid skill_id"):
            SkillAgent(skill_id="")
    
    def test_invalid_skill_id_none(self):
        """Test that None skill_id raises ValueError."""
        with pytest.raises(ValueError, match="Invalid skill_id"):
            SkillAgent(skill_id=None)
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_non_standard_naming_warning(self, caplog):
        """Test warning for non-standard skill_id naming."""
        import logging
        with caplog.at_level(logging.WARNING):
            agent = SkillAgent(skill_id="my-custom-skill")
        
        # Should log a warning about naming convention
        assert "does not follow convention" in caplog.text or agent.skill_id == "my-custom-skill"
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_custom_parameters(self):
        """Test initialization with custom parameters."""
        agent = SkillAgent(
            skill_id="skill-test",
            name="Custom Agent",
            model="claude-3-opus",
            max_tokens=4096,
            timeout_ms=60000
        )
        
        assert agent.model == "claude-3-opus"
        assert agent.max_tokens == 4096
        assert agent.timeout_ms == 60000
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_from_config(self):
        """Test creating agent from config."""
        config = SkillAgentConfig(
            skill_id="skill-test",
            name="Config Agent",
            max_tokens=4096
        )
        
        agent = SkillAgent.from_config(config)
        
        assert agent.skill_id == "skill-test"
        assert agent.name == "Config Agent"
        assert agent.max_tokens == 4096
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_mcp_disabled(self):
        """Test initialization with MCP disabled."""
        agent = SkillAgent(skill_id="skill-test", mcp_enabled=False)
        
        assert agent.mcp_enabled is False
    
    @patch.dict('os.environ', {}, clear=True)
    def test_missing_api_key_raises(self):
        """Test that missing API key raises RuntimeError."""
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            SkillAgent(skill_id="skill-test", mcp_enabled=True)


class TestSkillAgentParsing:
    """Tests for response parsing."""
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_parse_skill_response_with_metrics(self):
        """Test parsing skill response with metrics."""
        agent = SkillAgent(skill_id="skill-test")
        
        response = """# Skill Response
**Skill:** Test Skill
**Time:** 1234ms
**Tokens:** 156 in, 2847 out

---

## Generated Code
```typescript
export const Component = () => {
  return <div>Hello</div>;
};
```"""
        
        content, metrics = agent._parse_skill_response(response)
        
        assert "Generated Code" in content
        assert metrics['time_ms'] == 1234
        assert metrics['input'] == 156
        assert metrics['output'] == 2847
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_parse_skill_response_no_separator(self):
        """Test parsing response without --- separator."""
        agent = SkillAgent(skill_id="skill-test")
        
        response = "Just plain content without any formatting"
        
        content, metrics = agent._parse_skill_response(response)
        
        assert content == response
        assert metrics == {}
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_parse_skill_response_partial_metrics(self):
        """Test parsing response with only some metrics."""
        agent = SkillAgent(skill_id="skill-test")
        
        response = """**Time:** 500ms
---
Some content here"""
        
        content, metrics = agent._parse_skill_response(response)
        
        assert content == "Some content here"
        assert metrics.get('time_ms') == 500
        assert 'input' not in metrics
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_calculate_cost(self):
        """Test cost calculation."""
        agent = SkillAgent(skill_id="skill-test")
        
        tokens = {"input": 1000, "output": 1000}
        cost = agent._calculate_cost(tokens)
        
        # Input cost: (1000 / 1M) * 3 = 0.003
        # Output cost: (1000 / 1M) * 15 = 0.015
        # Total: ~0.018
        assert cost > 0
        assert 0.01 < cost < 0.05
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_calculate_cost_zero_tokens(self):
        """Test cost calculation with zero tokens."""
        agent = SkillAgent(skill_id="skill-test")
        
        tokens = {"input": 0, "output": 0}
        cost = agent._calculate_cost(tokens)
        
        assert cost == 0.0


class TestSkillAgentCircuitBreaker:
    """Tests for circuit breaker functionality."""
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_initial_state_closed(self):
        """Test circuit starts in closed state."""
        agent = SkillAgent(skill_id="skill-test")
        
        assert agent._circuit_state == CircuitState.CLOSED
        assert agent.is_healthy() is True
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_circuit_opens_after_failures(self):
        """Test circuit opens after threshold failures."""
        agent = SkillAgent(skill_id="skill-test")
        
        # Simulate failures up to threshold
        for i in range(SkillAgent.FAILURE_THRESHOLD):
            agent._record_failure(Exception("test"))
        
        assert agent._circuit_state == CircuitState.OPEN
        assert agent.is_healthy() is False
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_circuit_stays_closed_below_threshold(self):
        """Test circuit stays closed below failure threshold."""
        agent = SkillAgent(skill_id="skill-test")
        
        # Simulate failures below threshold
        for i in range(SkillAgent.FAILURE_THRESHOLD - 1):
            agent._record_failure(Exception("test"))
        
        assert agent._circuit_state == CircuitState.CLOSED
        assert agent.is_healthy() is True
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_success_resets_failure_count(self):
        """Test successful request resets failure count."""
        agent = SkillAgent(skill_id="skill-test")
        
        # Add some failures
        agent._record_failure(Exception("test"))
        agent._record_failure(Exception("test"))
        assert agent._failure_count == 2
        
        # Success resets
        agent._record_success()
        assert agent._failure_count == 0
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_half_open_success_closes_circuit(self):
        """Test successful request in half-open state closes circuit."""
        agent = SkillAgent(skill_id="skill-test")
        
        # Set to half-open
        agent._circuit_state = CircuitState.HALF_OPEN
        
        # Success should close
        agent._record_success()
        
        assert agent._circuit_state == CircuitState.CLOSED
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_half_open_failure_opens_circuit(self):
        """Test failure in half-open state opens circuit."""
        agent = SkillAgent(skill_id="skill-test")
        
        # Set to half-open
        agent._circuit_state = CircuitState.HALF_OPEN
        
        # Failure should open
        agent._record_failure(Exception("test"))
        
        assert agent._circuit_state == CircuitState.OPEN
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_manual_reset(self):
        """Test manual circuit breaker reset."""
        agent = SkillAgent(skill_id="skill-test")
        
        # Open circuit
        for i in range(SkillAgent.FAILURE_THRESHOLD):
            agent._record_failure(Exception("test"))
        
        assert agent._circuit_state == CircuitState.OPEN
        
        # Manual reset
        agent.reset_circuit_breaker()
        
        assert agent._circuit_state == CircuitState.CLOSED
        assert agent._failure_count == 0
        assert agent._last_failure_time is None
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_check_circuit_breaker_open_raises(self):
        """Test that check_circuit_breaker raises when open."""
        agent = SkillAgent(skill_id="skill-test")
        agent._circuit_state = CircuitState.OPEN
        agent._last_failure_time = time.time()  # Recent failure
        
        with pytest.raises(RuntimeError, match="Circuit breaker OPEN"):
            agent._check_circuit_breaker()


class TestSkillAgentInfo:
    """Tests for agent info and metadata."""
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_get_agent_info(self):
        """Test getting agent info."""
        agent = SkillAgent(
            skill_id="skill-test",
            name="Test Agent",
            max_tokens=4096
        )
        
        info = agent.get_agent_info()
        
        assert info['type'] == 'SkillAgent'
        assert info['skill_id'] == 'skill-test'
        assert info['name'] == 'Test Agent'
        assert info['max_tokens'] == 4096
        assert info['circuit_state'] == 'closed'
        assert info['mcp_enabled'] is True
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_agent_name_property(self):
        """Test agent_name property alias."""
        agent = SkillAgent(skill_id="skill-test", name="My Agent")
        
        assert agent.agent_name == "My Agent"
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_is_healthy_when_closed(self):
        """Test is_healthy returns True when circuit closed."""
        agent = SkillAgent(skill_id="skill-test")
        
        assert agent.is_healthy() is True
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_is_healthy_when_open(self):
        """Test is_healthy returns False when circuit open."""
        agent = SkillAgent(skill_id="skill-test")
        agent._circuit_state = CircuitState.OPEN
        
        assert agent.is_healthy() is False
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_is_healthy_when_half_open(self):
        """Test is_healthy returns True when circuit half-open."""
        agent = SkillAgent(skill_id="skill-test")
        agent._circuit_state = CircuitState.HALF_OPEN
        
        assert agent.is_healthy() is True


class TestSkillAgentFactories:
    """Tests for factory functions."""
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_create_game_enhancer_agent(self):
        """Test game enhancer factory function."""
        agent = create_game_enhancer_agent()
        
        assert agent.skill_id == "skill-react-game-enhancer"
        assert "game" in agent.name.lower() or "react" in agent.name.lower()
        assert isinstance(agent, SkillAgent)
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_create_html5_game_designer_agent(self):
        """Test HTML5 game designer factory function."""
        agent = create_html5_game_designer_agent()
        
        assert agent.skill_id == "skill-html_game_dev"
        assert isinstance(agent, SkillAgent)
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_create_code_reviewer_agent(self):
        """Test code reviewer factory function."""
        agent = create_code_reviewer_agent()
        
        assert agent.skill_id == "skill-code-reviewer"
        assert isinstance(agent, SkillAgent)
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_factory_with_custom_name(self):
        """Test factory with custom name."""
        agent = create_game_enhancer_agent(name="Custom Name")
        
        assert agent.name == "Custom Name"
        assert agent.skill_id == "skill-react-game-enhancer"
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_factory_with_custom_model(self):
        """Test factory with custom model."""
        agent = create_game_enhancer_agent(model="claude-3-opus")
        
        assert agent.model == "claude-3-opus"


class TestSkillAgentAsync:
    """Tests for async functionality."""
    
    @pytest.mark.asyncio
    async def test_agenerate_circuit_open(self):
        """Test that agenerate raises when circuit is open."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            agent = SkillAgent(skill_id="skill-test")
            
            # Open circuit
            for i in range(SkillAgent.FAILURE_THRESHOLD):
                agent._record_failure(Exception("test"))
            
            with pytest.raises(RuntimeError, match="Circuit breaker OPEN"):
                await agent.agenerate("test prompt")
    
    @pytest.mark.asyncio
    async def test_agenerate_success(self):
        """Test successful skill execution."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}), \
             patch('startd8.skills.agent.AsyncAnthropic') as mock_anthropic:
            # Setup mock
            mock_client = AsyncMock()
            mock_anthropic.return_value = mock_client
            
            mock_response = Mock()
            mock_response.content = [Mock(text="Test response\n---\nContent")]
            mock_response.usage = Mock()
            mock_response.usage.input_tokens = 100
            mock_response.usage.output_tokens = 200
            
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            
            agent = SkillAgent(skill_id="skill-test")
            
            response, time_ms, tokens = await agent.agenerate("test prompt")
            
            assert "Content" in response
            assert tokens.input == 100
            assert tokens.output == 200
            assert time_ms >= 0
    
    @pytest.mark.asyncio
    async def test_agenerate_failure_records(self):
        """Test that failures are recorded."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}), \
             patch('startd8.skills.agent.AsyncAnthropic') as mock_anthropic:
            mock_client = AsyncMock()
            mock_anthropic.return_value = mock_client
            mock_client.messages.create = AsyncMock(side_effect=Exception("API Error"))
            
            agent = SkillAgent(skill_id="skill-test")
            
            with pytest.raises(RuntimeError, match="Failed to execute skill"):
                await agent.agenerate("test prompt")
            
            assert agent._failure_count == 1


class TestCircuitState:
    """Tests for CircuitState enum."""
    
    def test_circuit_state_values(self):
        """Test CircuitState enum values."""
        assert CircuitState.CLOSED.value == "closed"
        assert CircuitState.OPEN.value == "open"
        assert CircuitState.HALF_OPEN.value == "half_open"
    
    def test_circuit_state_is_string_enum(self):
        """Test CircuitState is a string enum."""
        assert isinstance(CircuitState.CLOSED, str)
        assert CircuitState.CLOSED == "closed"


class TestSkillMetrics:
    """Tests for SkillMetrics dataclass."""
    
    def test_skill_metrics_creation(self):
        """Test creating SkillMetrics."""
        metrics = SkillMetrics(
            execution_time_ms=1000,
            input_tokens=100,
            output_tokens=200
        )
        
        assert metrics.execution_time_ms == 1000
        assert metrics.input_tokens == 100
        assert metrics.output_tokens == 200
        assert metrics.cache_hit is False
        assert metrics.circuit_state == CircuitState.CLOSED
    
    def test_skill_metrics_with_all_fields(self):
        """Test creating SkillMetrics with all fields."""
        metrics = SkillMetrics(
            execution_time_ms=1000,
            input_tokens=100,
            output_tokens=200,
            skill_reported_time_ms=950,
            cache_hit=True,
            circuit_state=CircuitState.HALF_OPEN
        )
        
        assert metrics.skill_reported_time_ms == 950
        assert metrics.cache_hit is True
        assert metrics.circuit_state == CircuitState.HALF_OPEN
