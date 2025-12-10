# StartDate SDK

**Version 0.2.0**

A comprehensive Python SDK for managing multi-LLM agent workflows, benchmarking, and prompt version control in the StartDate project.

## Features

- 🤖 **Multi-Agent Support**: Built-in support for Claude, GPT-4, and Gemini
- 📝 **Prompt Version Control**: Track and manage prompts with semantic versioning
- ⏱️ **Response Tracking**: Record responses with timing and token usage
- 📊 **Benchmarking**: Compare multiple LLMs on the same prompts
- 💰 **Cost Tracking**: Automatic cost estimation based on token usage
- 🎯 **CLI Tools**: Command-line interface for easy management
- 💾 **Flexible Storage**: JSON-based file system storage (extensible to other backends)

## Installation

### Recommended: pipx (Isolated Environment)

**Best for:** Most users who want a clean, isolated installation

```bash
# Install pipx (one-time setup)
brew install pipx  # macOS
# or: pip install --user pipx
pipx ensurepath    # Add to PATH

# Install startd8 in isolated environment
pipx install startd8

# Or install from local source (for development)
pipx install -e /path/to/startd8-sdk-project

# Update startd8
pipx upgrade startd8

# Uninstall
pipx uninstall startd8
```

**Why pipx?** 
- ✅ Complete isolation from your system Python
- ✅ No dependency conflicts
- ✅ Easy updates and uninstalls
- ✅ Standard tool used by `black`, `pytest`, `poetry`

### Alternative: Standard pip Installation

**Best for:** Developers who want to import startd8 as a library

```bash
cd startd8-sdk-project
pip install -e .

# With development dependencies
pip install -e ".[dev]"
```

**Note:** This installs into your current Python environment and may conflict with other packages.

## Quick Start

### Python API

```python
from startdate import AgentFramework, ClaudeAgent, GPT4Agent
from startdate.benchmark import BenchmarkRunner

# Initialize framework
framework = AgentFramework()

# Create a versioned prompt
prompt = framework.create_prompt(
    content="Implement a user authentication system with JWT tokens",
    version="1.0.0",
    tags=["auth", "backend", "security"]
)

# Set up agents
claude = ClaudeAgent()
gpt4 = GPT4Agent()

# Run benchmark
runner = BenchmarkRunner(framework)
results = runner.run_benchmark(
    prompt_content=prompt.content,
    agents=[claude, gpt4],
    benchmark_name="Auth System Comparison"
)

# Compare responses
comparison = framework.compare_responses(prompt.id)
print(f"Average response time: {comparison['avg_response_time_ms']}ms")
print(f"Total tokens used: {comparison['total_tokens']}")
```

### Command Line Interface

```bash
# Initialize framework
startdate init

# Create a prompt
startdate create-prompt "Write a REST API for user registration" \
    --version 1.0.0 \
    --tag api --tag backend

# List prompts
startdate list-prompts

# Run a benchmark (using mock agents for testing)
startdate run-benchmark <prompt-id> \
    --name "User Registration API" \
    --agent mock

# Compare responses
startdate compare <prompt-id>

# Generate markdown report
startdate compare <prompt-id> --output report.md

# Show statistics
startdate stats
```

## Architecture

### Core Components

1. **AgentFramework**: Main orchestrator for prompts, responses, and benchmarks
2. **Agents**: Abstract base class and implementations for different LLM providers
3. **Storage**: Pluggable storage backends (currently file system)
4. **Benchmark**: Tools for running and comparing multi-agent tests
5. **CLI**: Command-line interface for interactive use

### Data Models

```python
from startdate.models import (
    Prompt,           # Versioned prompt with tags and metadata
    AgentResponse,    # Agent response with timing and tokens
    Benchmark,        # Benchmark definition and status
    TokenUsage,       # Token usage statistics
    ComparisonMetrics # Comparison metrics across agents
)
```

## Configuration

### Environment Variables

```bash
# API Keys
export ANTHROPIC_API_KEY="your-claude-api-key"
export OPENAI_API_KEY="your-openai-api-key"
export GOOGLE_API_KEY="your-gemini-api-key"

# Storage location
export STARTDATE_DATA_DIR="$HOME/.startdate"
```

### Storage Structure

```
.startdate/
├── prompts/
│   ├── prompt-abc123.json
│   └── prompt-def456.json
├── responses/
│   ├── response-ghi789.json
│   └── response-jkl012.json
└── benchmarks/
    └── benchmark-mno345.json
```

## Usage Examples

### Example 1: Compare Three Models

```python
from startdate import AgentFramework, ClaudeAgent, GPT4Agent, MockAgent
from pathlib import Path

# Initialize
framework = AgentFramework(Path("./.startdate"))

# Create prompt
prompt = framework.create_prompt(
    content="Design a database schema for an e-commerce platform",
    version="1.0.0",
    tags=["database", "design", "ecommerce"]
)

# Initialize agents
agents = [
    ClaudeAgent(name="claude-sonnet"),
    GPT4Agent(name="gpt4-turbo"),
    MockAgent(name="baseline")  # For testing
]

# Get responses
for agent in agents:
    try:
        response = agent.create_response(
            prompt_id=prompt.id,
            prompt=prompt.content
        )
        framework.storage.save_response(response)
        print(f"✓ {agent.name}: {response.response_time_ms}ms")
    except Exception as e:
        print(f"✗ {agent.name}: {e}")

# Compare
comparison = framework.compare_responses(prompt.id)

print("\n🏆 Rankings:")
print("By Speed:", comparison['rankings']['by_speed'])
print("By Efficiency:", comparison['rankings']['by_token_efficiency'])
```

### Example 2: Track Development Across Branches

```python
from startdate import AgentFramework
import subprocess

framework = AgentFramework()

# Create feature prompt
prompt = framework.create_prompt(
    content="Implement password reset functionality",
    version="1.0.0",
    tags=["feature", "auth", "password-reset"]
)

# Assign to different model branches
models = {
    "claude": "feature/password-reset-claude",
    "gpt4": "feature/password-reset-gpt4",
    "gemini": "feature/password-reset-gemini"
}

for model, branch in models.items():
    # Create git branch
    subprocess.run(["git", "checkout", "-b", branch])
    
    # Record metadata
    prompt.metadata[model] = {
        "branch": branch,
        "status": "in_progress"
    }

framework.storage.save_prompt(prompt)
```

### Example 3: Generate Comparison Reports

```python
from startdate import AgentFramework
from startdate.benchmark import ComparisonReport
from pathlib import Path

framework = AgentFramework()
report_gen = ComparisonReport(framework)

# Generate markdown report
report = report_gen.generate_markdown_report(
    prompt_id="prompt-abc123",
    output_file=Path("./reports/comparison.md")
)

# Generate metrics
metrics = report_gen.generate_metrics("prompt-abc123")

print(f"Total responses: {metrics.total_responses}")
print(f"Fastest agent: {metrics.fastest_agent}")
print(f"Most efficient: {metrics.most_efficient_agent}")
print(f"Cheapest: {metrics.cheapest_agent}")
print(f"Total cost: ${metrics.total_cost_estimate:.2f}")
```

## Integration with StartDate Workflow

### Recommended Workflow

1. **Create Feature Prompt**
   ```bash
   startdate create-prompt "Feature description" --tag feature-name
   ```

2. **Create Model Branches**
   ```bash
   git checkout -b feature/name-claude
   git checkout -b feature/name-gpt4
   git checkout -b feature/name-gemini
   ```

3. **Implement on Each Branch**
   - Let each AI agent implement the feature on its branch
   - Record responses and timing data

4. **Compare Implementations**
   ```bash
   startdate compare <prompt-id> --output comparison.md
   ```

5. **Review and Merge**
   - Review comparison report
   - Select best implementation or combine approaches
   - Merge to main branch

## API Reference

### AgentFramework

```python
framework = AgentFramework(storage_dir: Optional[Path] = None)

# Prompt management
prompt = framework.create_prompt(content, version, tags, metadata)
prompt = framework.get_prompt(prompt_id)
prompts = framework.list_prompts(tags)

# Response management
response = framework.record_response(prompt_id, agent_name, model, response, response_time_ms, token_usage, metadata)
response = framework.get_response(response_id)
responses = framework.list_responses(prompt_id, agent_name)

# Benchmarking
benchmark = framework.create_benchmark(name, prompt_id, metadata)
benchmark = framework.complete_benchmark(benchmark_id, summary)
benchmark = framework.get_benchmark(benchmark_id)

# Comparison
comparison = framework.compare_responses(prompt_id)
report = framework.export_benchmark_report(benchmark_id, output_file)
```

### Agents

```python
# Claude
agent = ClaudeAgent(
    name="claude",
    model="claude-3-5-sonnet-20241022",
    api_key=None,  # Uses ANTHROPIC_API_KEY
    max_tokens=4096
)

# GPT-4
agent = GPT4Agent(
    name="gpt4",
    model="gpt-4-turbo-preview",
    api_key=None,  # Uses OPENAI_API_KEY
    max_tokens=4096
)

# Generate response
response = agent.create_response(prompt_id, prompt, metadata)
```

## Development

### For Contributors

```bash
# Clone the repository
git clone <repository-url>
cd startd8-sdk-project

# Create a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black src/

# Lint
ruff check src/

# Type check
mypy src/
```

### Testing pipx Installation

```bash
# Test pipx installation from local source
pipx install -e /path/to/startd8-sdk-project

# Verify it works
startd8 --help
startd8 tui
```

## Contributing

Contributions are welcome! This project is part of the StartDate initiative to benchmark LLM-driven development.

## License

MIT License - See LICENSE file for details

## Related Projects

- **MCP Agent Framework**: Model Context Protocol server for Claude Desktop integration
- **StartDate CLI**: Command-line tools for project management
- **StartDate Web**: Web interface for visualization and comparison

## Support

For issues, questions, or contributions, please visit:
- GitHub Issues: [startdate/issues](https://github.com/startdate/startdate-oss/issues)
- Documentation: [docs.startdate.dev](https://docs.startdate.dev)
- Discord: [StartDate Community](https://discord.gg/startdate)

