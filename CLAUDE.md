# CLAUDE.md

This file provides guidance to Claude Code for the StartDate (startd8) SDK repository.

## Project Overview

StartD8 is a Python SDK and CLI tool for managing multi-LLM agent workflows, benchmarking different models (Anthropic, OpenAI, Gemini, Mistral, Ollama), and prompt version control. It provides a unified interface for comparing LLM responses, tracking costs, and orchestrating multi-phase code generation (PrimeContractor batch workflows, Artisan Contractor 8-phase pipeline ON HOLD). Includes ContextCore integration for project observability and OTel-based telemetry.

## Tech Stack

- **Language:** Python 3.9+ (venv uses 3.14)
- **CLI Framework:** Typer with Rich for terminal output
- **Data Models:** Pydantic v2
- **HTTP Client:** httpx (async support)
- **Build System:** setuptools with pyproject.toml
- **Testing:** pytest with pytest-asyncio (markers: unit, integration, slow, asyncio, evaluation)
- **Observability:** OpenTelemetry (traces, metrics, logs) with Loki/Grafana stack

## Commands

```bash
source .venv/bin/activate
pip install -e ".[dev]"          # Dev mode
pip install -e ".[all,dev]"      # All providers
pytest                            # Run tests
pytest tests/unit/test_agents.py -v
pytest --cov=startd8 --cov-report=term-missing
ruff check src/ && black src/    # Lint/format
mypy src/                        # Type check
startd8 --help                   # CLI
```

## Project Structure (high-level)

```
src/startd8/              # Main package
├── agents/               # Agent implementations (base, claude, openai, gemini, mock, pool, tracked)
├── providers/            # Provider abstraction (protocol, registry, anthropic, openai, gemini, mistral, mock)
├── costs/                # Cost tracking (tracker, pricing, budget, analytics, OTel metrics)
├── contractors/          # Multi-phase workflow orchestration
│   ├── prime_contractor.py       # PrimeContractorWorkflow (active construction path)
│   ├── artisan_contractor.py     # ArtisanContractorWorkflow (ON HOLD)
│   ├── context_seed/             # Phase handler implementations
│   ├── context_seed_handlers.py  # Compat wrapper — re-exports from context_seed/
│   ├── artisan_phases/           # 12 individual phase implementations
│   ├── generators/               # Code generators (PrimaryContractor)
│   └── prime_postmortem.py       # Post-mortem evaluation + Kaizen
├── micro_prime/          # Local code generation engine (element-level, 6 host profiles)
├── complexity/           # Complexity classification (TRIVIAL/SIMPLE/MODERATE/COMPLEX) + tier routing
├── languages/            # Multi-language support (python, go, nodejs, vue, java, csharp)
├── repair/               # Post-generation repair pipeline (~45 steps, per-language)
├── validators/           # Per-language semantic checks + observability artifact validation
├── implementation_engine/ # Spec→draft→review prompt pipeline (YAML templates + budget enforcement)
├── security_prime/       # Security validation orchestration (~550 lines)
├── query_prime/          # Secure database query generation by tier (T1/T2/T3)
├── exemplars/            # Proven Exemplar Pipeline (PEP) — mine/reuse perfect-score features
├── workflows/builtin/    # 16 registered workflows (primary-contractor, plan-ingestion, etc.)
├── forward_manifest*.py  # Design-time contract forwarding + disk compliance validation
├── integrations/         # ContextCore workflow adapter and task runner
├── model_catalog.py      # Centralized model defaults with .agent_spec property
├── logging_config.py     # Logging configuration (get_logger)
└── logging_otel.py       # OpenTelemetry log bridge

scripts/                  # Runner and utility scripts (~52 files)
tests/                    # Test suite (~523 files, ~3000+ tests)
docs/                     # Documentation (~40 files) + design/ + design-princples/
```

## Architecture

### Key Classes

- `PrimeContractorWorkflow` — Multi-feature batch code generation (active construction path)
- `ArtisanContractorWorkflow` — 8-phase code generation orchestrator (ON HOLD)
- `ProviderRegistry` / `LanguageRegistry` — Dynamic discovery via entry points (call `.discover()` first)
- `MicroPrimeEngine` — Element-level code generation (Python, Go, Node.js, Vue SFC, Java, C#)
- `ModelCatalogEntry` — Centralized model defaults with `.agent_spec` property
- `WorkflowBase` — Base class for registered workflows

### Artisan 8-Phase Pipeline (ON HOLD)

PLAN → SCAFFOLD → DESIGN → IMPLEMENT → INTEGRATE → TEST → REVIEW → FINALIZE

Key patterns: design/impl handoff split, context seed handlers in `context_seed/core.py` (re-exported via compat wrapper), checkpoint/resume, per-task error guards, contract validation via `gate_contracts.py`.

### Multi-Language Support (6 language profiles)

Python, Go, Node.js, Vue 3 (``.vue`` SFC), Java, and C# support MicroPrime element-level generation. Vue reuses the Node.js host with dialect ``vue_sfc``; the engine splices inside the primary ``<script>`` / ``<script setup>`` block. Profiles load via setuptools entry points (``startd8_languages``); call ``LanguageRegistry.discover()`` before ``get_by_extension`` / ``resolve_language``. Protocol-based via `LanguageProfile` (15 methods). Use `resolve_language(target_files)` to auto-detect.

### Kaizen Quality System

Cross-run quality feedback loop: Registry enrichment → Disk validation → Feedback loop (25 root cause mappings) → Semantic validation → Dual scoring. Post-mortem artifacts: `prime-postmortem-report.json`, `kaizen-metrics.json`, `kaizen-suggestions.json`, `batch-postmortem-report.json`.

### Implementation Engine (Prompt Pipeline)

All templates in `contractor_prompts.yaml` (single source of truth) with fallback strings. Budget enforcement via `enforce_prompt_budget()` with P0-P3 priority sections. `PrimaryContractorWorkflow` is the single-task lead/drafter workflow (canonical name).

### SpanState v2 Compliance (ContextCore)

When emitting ContextCore state files:
- Top-level `status` is **required**: `"OK"` / `"ERROR"` / `"UNSET"`
- `task.status`: canonical enum (`todo`, NOT `pending`)
- `task.type`: canonical enum — custom classifiers go in `task.labels`
- `task.percent_complete` + zero-point `task.created` event required for dashboards

## Conventions

### Naming
- **Files:** snake_case.py — **Classes:** PascalCase — **Functions:** snake_case — **Constants:** UPPER_SNAKE_CASE

### Agent Specs
`provider:model` strings: `anthropic:claude-sonnet-4-20250514`, `openai:gpt-4-turbo-preview`, `gemini:gemini-1.5-pro`, `mistral:mistral-large-latest`, `ollama:llama2`, `mock:mock-model`

### Storage
Default `.startd8/` directory in project root. JSON-based. Configurable via `AgentFramework(storage_dir=...)`.

## Important Context

### Must Do
- Always call `ProviderRegistry.discover()` / `LanguageRegistry.discover()` before using providers/languages
- Call `provider.validate_config({})` before creating agents
- Use `BaseAgent` as the type hint for agents (not specific implementations)
- Run tests with `pytest` before committing changes
- Use `from startd8.logging_config import get_logger` for logging (NOT `logging.getLogger()`) — ensures OTel/Loki visibility
- Use `ModelCatalogEntry.agent_spec` for model defaults — don't scatter hardcoded model strings
- When modifying `context_seed/`, verify new symbols re-exported in `context_seed_handlers.py` compat wrapper
- When splitting modules, `grep -rn 'from old_module import\|patch.*old_module' tests/` to find all patch targets needing forwarding
- When adding LLM-calling boundaries in `micro_prime/`, define JSON contracts before implementation (Keiyaku compliance)

### Must Avoid
- Don't hardcode API keys — they come from environment variables
- Don't skip provider validation
- Don't use blocking calls in async code paths
- Don't modify `__all__` exports without updating tests
- Don't use `logging.getLogger()` in `contractors/` or SDK modules — logs silently miss Loki
- Don't hardcode model version strings — use `model_catalog.py`
- Don't use ad-hoc status strings in `task_tracking_emitter` — use ContextCore canonical enums
- Don't omit top-level `status` field in ContextCore state files
- Don't patch `context_seed_handlers.X` in tests — patch where the symbol is **looked up** (`context_seed.core`)
- Don't split a module without updating `test_logger_acquisition_policy.py` allowlist

### Environment Variables
```bash
ANTHROPIC_API_KEY    # Claude
OPENAI_API_KEY       # GPT
GOOGLE_API_KEY       # Gemini
MISTRAL_API_KEY      # Mistral
OLLAMA_HOST          # Ollama (optional)
# Vue SFC (optional; see docs/design/languages/VUE_SFC_MICROPRIME.md)
STARTD8_VUE_SYNTAX_CHECK       # default on: vue-tsc in checkpoints; set 0 to skip subprocess
STARTD8_VUE_FILE_OLLAMA_WHOLE  # default off: set 1 to allow file-level Ollama-whole for .vue (REQ-VUE-P-016)
```

### Known Issues
- Response ID tracking has edge cases in concurrent scenarios
- Gemini provider requires separate google-genai package
- Cost tracking assumes standard pricing (may differ for enterprise)

## Version

Current version: **0.4.0** (defined in pyproject.toml). Pre-1.0 SemVer.

## Embedded Pipeline (`.cap-dev-pipe/`)

Symlinks to `~/Documents/dev/cap-dev-pipe/`. Run pipeline commands from `.cap-dev-pipe/`:
```bash
./run-cap-delivery.sh --plan /path/to/plan.md --requirements /path/to/reqs.md --project startd8 --name my-run
./run-plan-ingestion.sh --provenance pipeline-output/my-run/run-provenance.json
./run-prime-contractor.sh --provenance pipeline-output/my-run/run-provenance.json --list
```

## Lessons Learned

See `SDK_developer_LESSONS_LEARNED.md` at `/Users/neilyashinsky/Documents/craft/Lessons_Learned/sdk/` for accumulated development wisdom (275 lessons across 14 topics).
