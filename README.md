# startd8-SDK

**Version 0.4.0**

A **software-engineering harness and development toolkit for Language-Model-assisted
development.** startd8 turns a requirements document into working software through a
**Requirements → Capabilities delivery pipeline**, and gives you **multi-LLM benchmarking
plus cloud and edge/local model evaluation** to choose the right model for each job.

The throughline is a deliberate one: **maximize what is generated deterministically (at $0
LLM cost) and use language models only where they add real value** — a bridge toward
deterministic, auditable generation for **production and enterprise applications.**

> The original benchmarking framework is still here and fully supported (see
> [Benchmarking & model evaluation](#benchmarking--model-evaluation)). It is now one half of a
> larger toolkit whose other half is deterministic code delivery.

---

## The idea in one screen

Building an application and *generating the content that fills it* are different jobs. startd8
keeps four buckets separate and prioritizes them strictly — and the SDK's generation scope
**ends at integration**:

| # | Bucket | What it is | Owner / cost |
|---|--------|-----------|--------------|
| **1** | **Application** | data model, pages, forms, CRUD, composite views — the structural skeleton | **SDK, deterministic, $0 LLM** (≈89% of an app) |
| **2** | **Placeholder content + static test data** | throwaway copy + fixtures that prove the app runs | SDK, minimal |
| **3** | **Integration** | the LLM-generated glue that wires the deterministic pieces into a working whole | **SDK — the one in-scope LLM aspect** |
| **4** | **Real end-user / company content** | the actual value content | **You / the commissioning company — out of scope** |

This is why a full app needs only **~4 LLM passes** (all integration-focused): the deterministic
cascade (`generate backend` + `generate scaffold` + `generate views`) is **$0, no API calls**.

---

## Installation

### Recommended: pipx (isolated environment)

```bash
# one-time setup
brew install pipx            # macOS  (or: pip install --user pipx)
pipx ensurepath

# install
pipx install startd8

# from local source (development)
pipx install -e /path/to/startd8-sdk

startd8 --help
```

### Alternative: pip (use as a library)

```bash
cd startd8-sdk
pip install -e ".[dev]"        # with dev dependencies
pip install -e ".[all,dev]"    # with all optional providers
```

See [INSTALL.md](INSTALL.md) and [INSTALL_PIPX.md](INSTALL_PIPX.md) for details.

---

## Quick start

### A. Deterministic code generation ($0, no LLM)

The deterministic cascade projects **one Prisma data-model contract** into a working
all-Python application (Pydantic + SQLModel + FastAPI + HTMX), runtime-verified end to end.

```bash
# 1. See exactly what the $0 cascade WILL build before you run it (read-only, advisory)
startd8 wireframe --inputs assembly-inputs.yaml

# 2. Generate the full backend from the Prisma contract
startd8 generate backend --schema schema.prisma --out ./app

# 3. Emit project plumbing (pyproject / logging / alembic / Dockerfile) from app.yaml
startd8 generate scaffold --inputs app.yaml --out ./app

# 4. Emit composite/relational views (dashboard / board / workspace) from views.yaml
startd8 generate views --inputs views.yaml --out ./app

# Bonus: apply an accessible design theme to the built app ($0)
startd8 polish ./app
```

`startd8 generate --help` lists all four targets (`frontend`, `backend`, `scaffold`, `views`).

### B. Benchmarking & model evaluation

```bash
# Initialize storage
startd8 init

# Run the SAME seed through Prime Contractor across 2+ models in isolated
# sandboxes, then rank — cloud and edge/local side by side
startd8 compare-models --seed seed.json \
    --model anthropic:claude-sonnet-4-20250514 \
    --model ollama:llama3 \
    --model gemini:gemini-2.0-flash

# Classic prompt benchmarking
startd8 create-prompt "Implement JWT auth" --version 1.0.0 --tag auth
startd8 run-benchmark <prompt-id> --name "Auth comparison" --agent mock:mock-model
startd8 compare <prompt-id> --output report.md
startd8 stats
```

### Python API

```python
from startd8 import AgentFramework
from startd8.benchmark import BenchmarkRunner
from startd8.providers import ProviderRegistry

ProviderRegistry.discover()                      # always discover first
anthropic = ProviderRegistry.get_provider("anthropic")
anthropic.validate_config({})                    # always validate before use
agent = anthropic.create_agent("claude-sonnet-4-20250514")

framework = AgentFramework()
runner = BenchmarkRunner(framework)
results = runner.run_benchmark(
    prompt_content="Design a schema for an e-commerce platform",
    agents=[agent],
    benchmark_name="Schema design",
)
print(results["comparison"]["avg_response_time_ms"])
```

---

## The Requirements → Capabilities delivery pipeline

The **Capability Delivery Pipeline** (`cap-dev-pipe`) carries a requirements doc + plan through
ingestion, deterministic assembly, and LLM-assisted integration. It is embedded in this repo via
symlinks to the canonical source and driven from `.cap-dev-pipe/`:

```bash
cd .cap-dev-pipe
./run-cap-delivery.sh   --plan plan.md --requirements reqs.md --project myapp --name run-1
./run-plan-ingestion.sh --provenance pipeline-output/run-1/run-provenance.json
./run-prime-contractor.sh --provenance pipeline-output/run-1/run-provenance.json --list
```

Bracket every pass with the two human design bookends — **DATA MODEL** (front: design the
contract bucket 1 derives from) and **RETROSPECTIVE** (back: feed lessons back into
requirements/plan). The deterministic `generate` cascade is **$0 and not a pipeline pass**; the
LLM passes are integration-focused.

Guides: [PRIME_CONTRACTOR_WORKFLOW_GUIDE](docs/PRIME_CONTRACTOR_WORKFLOW_GUIDE.md) ·
[FEATURE_WORKFLOW_GUIDE](docs/FEATURE_WORKFLOW_GUIDE.md) ·
[ITERATIVE_DEV_WORKFLOW](docs/ITERATIVE_DEV_WORKFLOW.md)

---

## Command surface

`startd8 <command>` — run `startd8 --help` or `startd8 <command> --help` for full options.

| Area | Commands |
|------|----------|
| **Deterministic codegen** | `wireframe`, `generate` (frontend/backend/scaffold/views), `polish`, `repair`, `manifest` |
| **Pipeline & contractors** | `workflow`, `project`, `queue`, `compare-models`, `assist`, `fde`, `sapper`, `element-registry` |
| **Benchmarking & prompts** | `init`, `create-prompt`, `list-prompts`, `show-prompt`, `run-benchmark`, `compare`, `list-responses`, `show-response`, `stats`, `templates`, `build-prompt` |
| **Pipelines & serving** | `pipeline`, `serve`, `dashboard` |
| **Interactive & ops** | `tui`, `otel-status`, `otel-configure` |

---

## Architecture

- **Provider abstraction** — 8 providers via entry points: `anthropic`, `openai`, `gemini`,
  `mistral`, `ollama`, `nim`, `openai-compatible`, `mock`. Edge/local and self-hosted models
  run through `ollama`, `nim`, and any OpenAI-compatible endpoint.
- **Multi-language code generation** — 7 language profiles: `python` (strongest — AST repair,
  splicing), `go`, `nodejs`, `java`, `csharp`, `vue`, `prisma`. Python is the deterministic
  backend target.
- **Prime Contractor** — the active multi-feature construction path (tier-routed: template →
  Haiku → Sonnet), with checkpoint/resume, per-language repair (~45 steps), and Kaizen
  cross-run quality feedback.
- **Backend codegen** — `src/startd8/backend_codegen/` projects one `.prisma` contract into
  models / tables / CRUD / HTMX UI / export / AI-schemas / completeness, all $0-deterministic.
- **Observability** — OpenTelemetry traces/metrics/logs with a Loki/Grafana stack; cost
  tracking across all providers.

Deeper reference: [SDK_ARCHITECTURE_v1](docs/SDK_ARCHITECTURE_v1.md) ·
[API_REFERENCE_v1](docs/API_REFERENCE_v1.md) ·
[PROVIDER_PLUGIN_GUIDE](PROVIDER_PLUGIN_GUIDE.md) ·
[COST_TRACKING_USER_GUIDE](docs/COST_TRACKING_USER_GUIDE.md)

---

## Configuration

```bash
# API keys (read from environment; never hardcode)
export ANTHROPIC_API_KEY="..."
export OPENAI_API_KEY="..."
export GOOGLE_API_KEY="..."      # Gemini
export MISTRAL_API_KEY="..."
export OLLAMA_HOST="http://localhost:11434"   # optional, for edge/local
```

Default storage is a `.startd8/` directory in the project root (JSON file storage; configurable
via `AgentFramework(storage_dir=...)` or `--dir` on the CLI).

Observability setup: [LOKI_SETUP_GUIDE](docs/LOKI_SETUP_GUIDE.md) ·
[OTEL_INTEGRATION_GUIDE](OTEL_INTEGRATION_GUIDE.md).

---

## Development

```bash
git clone https://github.com/neil-the-nowledgeable/startd8.git
cd startd8
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pytest                 # run tests
ruff check src/        # lint
black src/             # format
mypy src/              # type-check
```

See [TESTING.md](TESTING.md) and [CLAUDE.md](CLAUDE.md) (repository conventions and
architecture map).

---

## License

This software is licensed under the **Equitable Use License v1.0** (see [LICENSE.md](LICENSE.md)).

Free for individuals, small businesses (<$1M revenue), non-profits, educational institutions,
worker cooperatives, open-source projects, and founders from historically excluded communities
(Restorative Access). Large corporations and for-profit healthcare pay an equitable fee
(5–15% of documented value); government agencies, fossil-fuel companies, military contractors,
private-prison operators, investment banks, and lobbyists pay the maximum fee permissible.

The license also requires that efficiency gains from automation benefit workers (50% of
documented savings to affected workers, 25% to retraining); using this software to eliminate
jobs violates the license. Prohibited uses include fascism, genocide, weapons, and surveillance.
Full terms in [LICENSE.md](LICENSE.md).

---

## Support

- **Issues:** https://github.com/neil-the-nowledgeable/startd8/issues
- **Repository conventions & architecture:** [CLAUDE.md](CLAUDE.md)
- **Changelog:** [CHANGELOG.md](CHANGELOG.md)
