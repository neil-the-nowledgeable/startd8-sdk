## startd8 SDK - Provider Plugin System Guide

**Last Updated:** 2026-06-08  
**Version:** 0.4.0

---

## Overview

The startd8 SDK provider plugin system allows you to add new LLM providers without modifying core SDK code. Providers are discovered automatically via Python entry points, making it easy to create and distribute custom provider packages.

### Key Features

- ✅ **Plugin Architecture** - Add providers without touching core code
- ✅ **Auto-Discovery** - Providers registered via entry points
- ✅ **8 Built-in Providers** - Anthropic, OpenAI, Gemini, Mistral, Ollama, NIM, OpenAI-compatible, Mock
- ✅ **Cloud, edge/local & self-hosted** - via Ollama, NIM, and any OpenAI-compatible endpoint
- ✅ **Easy Custom Providers** - Simple protocol to implement
- ✅ **Model Metadata** - Cost tracking, context windows, capabilities
- ✅ **Backward Compatible** - Existing code works unchanged

---

## Quick Start

### Using Built-in Providers

```python
from startd8.providers import ProviderRegistry

# Auto-discover all providers
ProviderRegistry.discover()

# List available providers
providers = ProviderRegistry.list_providers()
# ['anthropic', 'openai', 'gemini', 'mistral', 'ollama', 'nim', 'openai-compatible', 'mock']

# Create an agent from a provider
provider = ProviderRegistry.get_provider("anthropic")
provider.validate_config({"api_key": "your-api-key"})  # or set ANTHROPIC_API_KEY
agent = provider.create_agent(
    model="claude-sonnet-4-20250514",
    name="anthropic:claude-sonnet-4-20250514",
    api_key="your-api-key",
)

# Use the agent
response = await agent.agenerate("Hello!")
```

### Using AgentRegistry (Simplified)

```python
from startd8.job_queue import AgentRegistry

registry = AgentRegistry()

# Get agent by explicit provider:model
agent = registry.get_agent("openai:gpt-4o")

# List all available
available = registry.list_available()
```

---

## Built-in Providers

### 1. Anthropic Claude

```python
from startd8.providers import AnthropicProvider

provider = AnthropicProvider()

# Create agent
agent = provider.create_agent(
    model="claude-sonnet-4-20250514",
    api_key="your-key",  # or use ANTHROPIC_API_KEY env var
    max_tokens=4096
)

# Get model metadata (used by cost tracking)
info = provider.get_model_info("claude-sonnet-4-20250514")
# { 'name': ..., 'context_window': 200000, 'max_output_tokens': ...,
#   'cost_per_1m_input': ..., 'cost_per_1m_output': ... }
```

> Don't hardcode model strings across your code — use `model_catalog.py` centralized defaults
> (`ModelCatalogEntry.agent_spec`).

### 2. OpenAI GPT

```python
from startd8.providers import OpenAIProvider

provider = OpenAIProvider()
agent = provider.create_agent(
    model="gpt-4o",
    api_key="your-key",  # or use OPENAI_API_KEY env var
    max_tokens=4096
)
```

### 3. Google Gemini

```python
from startd8.providers import GeminiProvider

provider = GeminiProvider()
agent = provider.create_agent(
    model="gemini-2.0-flash",
    api_key="your-key"  # or use GOOGLE_API_KEY env var
)
```

> Gemini requires the separate `google-genai` package to be installed.

### 4. Mistral

```python
from startd8.providers import MistralProvider

provider = MistralProvider()
agent = provider.create_agent(
    model="mistral-large-latest",
    api_key="your-key"  # or use MISTRAL_API_KEY env var
)
```

### 5. Ollama (edge / local LLMs)

```python
from startd8.providers import OllamaProvider

provider = OllamaProvider()
agent = provider.create_agent(
    model="llama3",
    base_url="http://localhost:11434/v1"  # default; or set OLLAMA_HOST
)
# Common models: llama3, mistral, mixtral, codellama, phi
```

### 6. NVIDIA NIM & OpenAI-compatible (self-hosted / any endpoint)

```python
from startd8.providers import ProviderRegistry

ProviderRegistry.discover()

# NVIDIA NIM (self-hosted inference)
nim = ProviderRegistry.get_provider("nim")

# Any OpenAI-compatible endpoint (vLLM, LM Studio, gateways, etc.)
compat = ProviderRegistry.get_provider("openai-compatible")
agent = compat.create_agent(model="my-model", base_url="https://my-endpoint/v1")
```

### 7. Mock Provider (Testing)

```python
from startd8.providers import MockProvider

provider = MockProvider()
agent = provider.create_agent(model="mock-model")
```

---

## Creating Custom Providers

### Step 1: Implement the Provider

Create a class that implements the `AgentProvider` protocol:

```python
# my_provider.py
from typing import List, Dict, Any, Optional
from startd8.providers import AgentProvider
from startd8.agents import BaseAgent
from startd8.exceptions import ConfigurationError

class MyCustomProvider:
    """My custom LLM provider"""
    
    @property
    def name(self) -> str:
        """Unique provider identifier"""
        return "my-provider"
    
    @property
    def display_name(self) -> str:
        """Human-readable name"""
        return "My Custom Provider"
    
    @property
    def supported_models(self) -> List[str]:
        """List of supported model IDs"""
        return ["model-v1", "model-v2", "model-v3"]
    
    def create_agent(
        self, 
        model: str, 
        name: Optional[str] = None,
        **config
    ) -> BaseAgent:
        """Create an agent instance"""
        if model not in self.supported_models:
            raise ValueError(f"Model {model} not supported")
        
        # Create your custom agent here
        from my_package.agents import MyCustomAgent
        return MyCustomAgent(
            name=name or model,
            model=model,
            **config
        )
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate configuration"""
        # Check for required config
        if 'api_key' not in config:
            raise ConfigurationError("api_key required")
        return True
    
    def get_required_env_vars(self) -> List[str]:
        """Required environment variables"""
        return ['MY_PROVIDER_API_KEY']
    
    def get_model_info(self, model: str) -> Optional[Dict[str, Any]]:
        """Model metadata (optional)"""
        return {
            "name": model,
            "context_window": 8192,
            "cost_per_1m_input": 1.00,
            "cost_per_1m_output": 2.00
        }
    
    def supports_streaming(self) -> bool:
        """Whether streaming is supported (optional)"""
        return True
    
    def get_capabilities(self) -> List[str]:
        """Provider capabilities (optional)"""
        return ['text-generation', 'function-calling']
```

### Step 2: Register via Entry Points

In your package's `pyproject.toml`:

```toml
[project.entry-points."startd8.providers"]
my-provider = "my_package.providers:MyCustomProvider"
```

Or in `setup.py`:

```python
setup(
    name="my-startd8-provider",
    entry_points={
        "startd8.providers": [
            "my-provider = my_package.providers:MyCustomProvider",
        ],
    },
)
```

### Step 3: Use Your Provider

After installing your package:

```python
from startd8.providers import ProviderRegistry

# Auto-discover will find your provider
ProviderRegistry.discover()

# Now it's available
agent = ProviderRegistry.create_agent(
    provider_name="my-provider",
    model="model-v1",
    api_key="..."
)
```

---

## Provider Discovery

### Automatic Discovery

Providers are discovered automatically when you:

```python
from startd8.providers import ProviderRegistry

# Triggers auto-discovery
ProviderRegistry.discover()

# Or use any registry method (triggers discovery internally)
providers = ProviderRegistry.list_providers()
```

### Manual Registration

For testing or runtime registration:

```python
from startd8.providers import ProviderRegistry

# Register a provider instance
provider = MyCustomProvider()
ProviderRegistry.register(provider)
```

### Forced Re-Discovery

```python
# Force re-scan of entry points
ProviderRegistry.discover(force=True)
```

---

## Advanced Usage

### Finding Providers for Models

```python
from startd8.providers import ProviderRegistry

# Find which provider supports a model
provider = ProviderRegistry.find_provider_for_model("gpt-4")
print(provider.name)  # 'openai'

# Get all models from all providers
all_models = ProviderRegistry.list_all_models()
# {
#     'anthropic': ['claude-sonnet-4-20250514', ...],
#     'openai': ['gpt-4o', 'gpt-4', ...],
#     ...
# }
```

### Getting Provider Information

```python
# Get detailed provider info
info = ProviderRegistry.get_provider_info("anthropic")
# {
#     'name': 'anthropic',
#     'display_name': 'Anthropic Claude',
#     'models': [...],
#     'env_vars': ['ANTHROPIC_API_KEY'],
#     'capabilities': ['text-generation', 'vision', ...],
#     'streaming': True
# }
```

### Using with Cost Tracking

```python
from startd8.costs import CostTracker, BudgetManager

# Create cost tracking components
cost_tracker = CostTracker()
budget_manager = BudgetManager()

# Create agent with cost tracking
agent = ProviderRegistry.create_agent(
    provider_name="anthropic",
    model="claude-sonnet-4-20250514",
    cost_tracker=cost_tracker,
    budget_manager=budget_manager
)

# Costs are tracked automatically
response = await agent.agenerate("Hello!")
```

---

## Provider Capabilities

### Capability Identifiers

Providers can declare their capabilities:

- `text-generation` - Basic text generation
- `function-calling` - Function/tool calling
- `vision` - Image understanding
- `json-mode` - JSON output mode
- `streaming` - Streaming responses
- `long-context` - Extended context windows
- `ultra-long-context` - Million+ token context (Gemini 1.5)
- `local-execution` - Runs locally (Ollama)
- `testing` - Mock/testing only

### Checking Capabilities

```python
provider = ProviderRegistry.get_provider("anthropic")

# Check if provider supports a capability
if 'vision' in provider.get_capabilities():
    print("This provider supports vision!")

# Check streaming support
if provider.supports_streaming():
    print("Streaming is available")
```

---

## Model Metadata

### Available Metadata

Providers can supply model metadata:

```python
info = provider.get_model_info("claude-sonnet-4-20250514")

# Common fields:
# - name: Human-readable model name
# - context_window: Maximum context length (tokens)
# - max_output_tokens: Maximum output length
# - cost_per_1m_input: Cost per 1M input tokens
# - cost_per_1m_output: Cost per 1M output tokens
# - latency_ms: Expected latency (for mocks)
```

### Using Metadata for Cost Tracking

The cost metadata is used automatically by the cost tracking system:

```python
from startd8.costs import CostTracker

tracker = CostTracker()

# Create agent with cost tracking
agent = ProviderRegistry.create_agent(
    provider_name="anthropic",
    model="claude-sonnet-4-20250514",
    cost_tracker=tracker
)

# Costs are calculated using model metadata
response = await agent.agenerate("Hello!")
print(f"Cost: ${tracker.get_total_cost():.4f}")
```

### Metadata Drives Generation Tiering & Budgets

The `cost_per_1m_input` / `cost_per_1m_output` metadata isn't just for reporting — it feeds the
deterministic-codegen side of the SDK:

- **Tier routing**: the complexity classifier/router and Prime Contractor use per-model cost to
  route work to the cheapest capable tier (template → Haiku → Sonnet), keeping the LLM
  integration passes cheap while the deterministic cascade stays $0.
- **Budget gates**: a run's remaining `$` budget is threaded into the generation context, so
  under-specified targets are refused (not endlessly escalated) once a cap is reached.

A custom provider that supplies accurate cost metadata participates in this routing automatically.

---

## Best Practices

### 1. Use Provider Registry

```python
# ✅ Good - Uses plugin system
from startd8.providers import ProviderRegistry
agent = ProviderRegistry.create_agent("anthropic", "claude-sonnet-4-20250514")

# ❌ Avoid - hardcoding provider wiring in your code
from startd8.providers.anthropic import AnthropicProvider
agent = AnthropicProvider().create_agent("claude-sonnet-4-20250514")
```

### 2. Handle Provider Availability

```python
# Check if provider is available
provider = ProviderRegistry.get_provider("anthropic")
if provider is None:
    print("Anthropic provider not available")
    # Fall back to another provider
    provider = ProviderRegistry.get_provider("mock")
```

### 3. Validate Configuration

```python
try:
    agent = ProviderRegistry.create_agent(
        provider_name="anthropic",
        model="claude-sonnet-4-20250514"
    )
except ConfigurationError as e:
    print(f"Configuration error: {e}")
    # Handle missing API key, etc.
```

### 4. Use Model Metadata

```python
# Get model info before using
info = provider.get_model_info(model)
if info and info['context_window'] < 100000:
    print("Warning: Small context window")
```

---

## Testing with Custom Providers

### Mock Provider for Tests

```python
import pytest
from startd8.providers import ProviderRegistry, MockProvider

class TestMyFeature:
    def setup_method(self):
        # Clear registry and use only mock
        ProviderRegistry.clear()
        ProviderRegistry.register(MockProvider())
    
    def teardown_method(self):
        ProviderRegistry.clear()
    
    @pytest.mark.asyncio
    async def test_feature(self):
        agent = ProviderRegistry.create_agent("mock", "mock-model")
        response = await agent.agenerate("Test")
        assert response is not None
```

### Custom Test Provider

```python
class TestProvider:
    """Provider for testing with specific behaviors"""
    
    @property
    def name(self) -> str:
        return "test"
    
    @property
    def display_name(self) -> str:
        return "Test Provider"
    
    @property
    def supported_models(self) -> List[str]:
        return ["test-fast", "test-slow", "test-error"]
    
    def create_agent(self, model: str, **config) -> BaseAgent:
        # Return agent with specific test behavior
        if model == "test-error":
            return ErrorThrowingAgent()
        elif model == "test-slow":
            return SlowAgent(delay=5.0)
        else:
            return MockAgent(name=model, model=model)
```

---

## Distributing Custom Providers

### Creating a Provider Package

```
my-startd8-provider/
├── pyproject.toml
├── README.md
├── src/
│   └── my_provider/
│       ├── __init__.py
│       ├── provider.py
│       └── agents.py
└── tests/
    └── test_provider.py
```

**pyproject.toml:**

```toml
[project]
name = "my-startd8-provider"
version = "0.1.0"
dependencies = [
    "startd8>=0.4.0",
]

[project.entry-points."startd8.providers"]
my-provider = "my_provider.provider:MyProvider"
```

### Publishing

```bash
# Build package
python -m build

# Upload to PyPI
python -m twine upload dist/*

# Users can install
pip install my-startd8-provider
```

### Users Automatically Get Your Provider

```python
# After installing your package, users get your provider automatically
from startd8.providers import ProviderRegistry

# Your provider is discovered
assert "my-provider" in ProviderRegistry.list_providers()

# And can be used immediately
agent = ProviderRegistry.create_agent("my-provider", "model-v1")
```

---

## Troubleshooting

### Provider Not Found

**Problem:** `ConfigurationError: Unknown provider: my-provider`

**Solutions:**
1. Check the provider package is installed: `pip list | grep provider`
2. Verify entry points are registered: `pip show my-provider`
3. Force re-discovery: `ProviderRegistry.discover(force=True)`

### Import Errors

**Problem:** Provider fails to load with import error

**Solutions:**
1. Check optional dependencies are installed (e.g., `pip install anthropic`)
2. Check Python version compatibility
3. Review provider logs: `logging.getLogger('startd8.providers').setLevel(logging.DEBUG)`

### API Key Issues

**Problem:** `ConfigurationError: API key required`

**Solutions:**
1. Set environment variable: `export ANTHROPIC_API_KEY=...`
2. Pass in config: `create_agent(..., api_key="...")`
3. Check required env vars: `provider.get_required_env_vars()`

---

## Examples

See `examples/provider_examples.py` for complete working examples.

---

## Further Reading

- [SDK Architecture](docs/SDK_ARCHITECTURE_v1.md)
- [API Reference](docs/API_REFERENCE_v1.md)
- [Cost Tracking User Guide](docs/COST_TRACKING_USER_GUIDE.md)
- [Provider System Tests](tests/unit/test_providers.py)

---

**Happy provider development! 🚀**
