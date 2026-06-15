# CLAUDE.md

This file provides guidance to Claude Code for the StartDate (startd8) SDK repository.

## Project Overview

StartD8 is a Python SDK and CLI tool for managing multi-LLM agent workflows, benchmarking different models (Anthropic, OpenAI, Gemini, Mistral, Ollama), and prompt version control. It provides a unified interface for comparing LLM responses, tracking costs, and orchestrating multi-phase code generation (Artisan Contractor 8-phase pipeline, PrimeContractor batch workflows). Includes ContextCore integration for project observability and OTel-based telemetry.

## Generation Scope & Priority — READ FIRST (the bucket separation)

> **The recurring failure mode this prevents:** conflating *building the application* with
> *generating the real content that fills it*. They are different jobs with different owners. Keep
> these four buckets separate, and prioritize strictly in this order. The SDK's job ends at bucket 3.

| # | Bucket | What it is | Owner / cost | Priority |
|---|--------|-----------|--------------|----------|
| **1** | **APPLICATION** ("applicational completion") | the data model (`schema.prisma` contract), pages, forms, fields, CRUD, composite views — the structural skeleton | **SDK, deterministic, $0 LLM** (`backend_codegen` shipped; scaffold gen `REQ-SCAF`; view gen `REQ-VIEW`). ~89% of an app. | **FIRST — always** |
| **2** | **PLACEHOLDER CONTENT + STATIC TEST DATA** | basic placeholder user-facing copy + static integration-test fixtures/seed data | **SDK, minimal/throwaway** | second |
| **3** | **INTEGRATION** | the LLM-generated glue/wiring that integrates the deterministic pieces into a working whole, proven end-to-end | **SDK, the ONE in-scope LLM-generation aspect** | third |
| **4** | **END-USER / COMPANY CONTENT** | the *real* value content (StartDate: real value summaries/pitches/tailored assets; any app: the company's real copy + data) | **USER / COMMISSIONING COMPANY — NOT the SDK** | out of scope |

**Rules going forward:**
- **Prioritize applicational completion first.** Build the working application skeleton before any content.
- **Bucket 2 is ~zero importance** except to prove the application works. Generate minimal placeholders + static test data; do **not** invest in making this content good.
- **The SDK's LLM-generation scope ends at INTEGRATION (bucket 3).** Everything past integration — the real user-facing value content — is **provided by the user or the company requesting the app.** The SDK builds the application that *produces/holds* content; it does not author the real content.
- **Determinism story = the APPLICATION bucket only.** The "~60–75%→~89% deterministic" / "two (now three) classes of determinism" framing describes bucket 1. Never cite it as if the SDK generates content (bucket 4).
- **cap-dev-pipe passes** for a full app ≈ **~4 LLM passes**, and even those are **integration-focused** (bucket 3), not real-content generation. The deterministic cascade (`generate backend` + `generate scaffold` + `generate views`) is **$0 CLI calls, not pipeline passes**.

**The two human design bookends** (`docs/design-princples/DATA_MODEL_AND_RETROSPECTIVE.md`): as
implementation automates, human leverage concentrates at **DATA MODEL** (front — designing the
contract bucket-1 derives from) and **RETROSPECTIVE** (back — reflecting after each increment and
feeding lessons back to the data model/requirements/plan). Bracket every cap-dev-pipe pass with both.

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
# Activate virtual environment
source .venv/bin/activate

# Install in development mode
pip install -e ".[dev]"

# Install with all providers
pip install -e ".[all,dev]"

# Run tests
pytest

# Run specific test file
pytest tests/unit/test_agents.py -v

# Run with coverage
pytest --cov=startd8 --cov-report=term-missing

# Lint and format
ruff check src/
black src/

# Type checking
mypy src/

# Run CLI
startd8 --help
startd8 tui          # Launch interactive TUI
startd8 init         # Initialize framework in current dir
startd8 run-benchmark --help
startd8 compare-models --help   # same seed → N models, isolated, ranked capability+cost report
startd8 wireframe    # Pre-generation summary of what the $0 cascade will build ($0, read-only,
                     #   advisory; --inputs <assembly-inputs.yaml> repeatable; --json for CI)

# Summer 2026 model benchmark — Track 2 behavioral scoring (measures model skill; deterministic+micro-prime OFF)
doppler run -p startd8 -c dev -- python3 scripts/run_behavioral_pilot.py   # --dry-run default; --run spends
python3 scripts/rescore_behavioral.py <batch-root>   # $0 re-score of persisted servers (no regen)

# Deterministic $0 generation cascade (bucket 1 — no LLM)
startd8 generate frontend   # Render Prisma→Zod schema file deterministically
startd8 generate backend    # Full all-Python backend (Pydantic + SQLModel + FastAPI + HTMX + derived)
startd8 generate scaffold   # Project plumbing (pyproject/logging/alembic/Dockerfile) from app.yaml
startd8 generate views      # Composite/relational views (dashboard/board/workspace) from views.yaml

# Presentation polish (Tier 1 — deterministic $0 design system)
startd8 polish apply        # Apply accessible design theme (writes stylesheet + static mount)
startd8 polish check        # Audit polish drift (exit 0=in-sync, 1=drift, 2=error)
startd8 polish themes       # List curated themes
```

## Project Structure

Top-level layout (`src/startd8/`). Use `ls`/`grep` for the full file listing — only key files are called out below.

```
src/startd8/
├── cli.py, framework.py, benchmark.py, orchestration.py   # CLI + core AgentFramework/BenchmarkRunner/Pipeline
├── models.py, config*.py, model_catalog.py                # Pydantic models, config, centralized model defaults
├── truncation_detection.py, security.py, otel.py          # Code-aware truncation, security utils, OTel
├── logging_config.py (get_logger), logging_otel.py        # Logging + OTel log bridge (see Must Do)
├── forward_manifest*.py                                   # Design-time contract forwarding + disk validation
│
├── frontend_codegen/     # $0 Prisma→Zod schema render (PrismaZodFileProvider)
├── backend_codegen/      # $0 deterministic all-Python app gen (bucket 1): pydantic/sqlmodel renderers,
│                   #   crud/htmx/pages/test emitters, assembler, drift, gates; ai_layer.py = source-bound AI passes
├── scaffold_codegen/     # $0 project plumbing gen (pyproject/logging/alembic/Dockerfile) — ScaffoldFileProvider
├── view_codegen/         # $0 composite/relational views (dashboard/board/workspace) — CompositeViewProvider
├── presentation_polish/  # $0 deterministic Tier-1 design system (CSS restyle): css, themes, tokens, engine, provider
├── agents/         # Per-provider agents (claude/openai/gemini/mock) + pool, tracked wrapper; base.py = BaseAgent
├── providers/      # Provider abstraction: protocol.py, registry.py (ProviderRegistry), 1 file per provider
├── costs/          # Cost tracking: tracker, pricing, budget, analytics, otel_metrics, usage_limits
├── model_comparison.py     # `startd8 compare-models`: same seed → N models, isolated, ranked (see Architecture)
├── benchmark_matrix/       # Summer 2026 model benchmark (service×model×repetition): run_spec, budget,
│                   #   runner, aggregate (median/IQR/pass-rate + consistency), scoring (compile gate +
│                   #   functional term), sandbox (untrusted exec); behavioral/ = Track 2 executed scoring
├── contractors/    # Multi-phase orchestration — see Architecture. Key: prime_contractor.py, integration_engine.py,
│                   #   context_seed/ (phase handlers + compat wrapper context_seed_handlers.py), prime_postmortem.py,
│                   #   queue.py (cycle detection), gate_contracts.py, checkpoint.py; artisan_*/ (ON HOLD)
├── security_prime/ # Security gate orchestration (~550 lines): contract, enrichment, scorer, gate_models
├── query_prime/    # Secure DB query gen by tier: engine, classifier, generator; security/ (verify_file), patterns/
├── exemplars/      # Proven Exemplar Pipeline: extractor, registry, structural_extractor, template_promoter
├── complexity/     # Tier routing: classifier (classify_tier), router, signals
├── micro_prime/    # Element-level local generation: engine, decomposer, splicer, prime_adapter, repair
├── repair/         # ~45 post-gen repair steps (orchestrator, diagnostics, routing, staging) — steps/ by language
├── languages/      # 5 LanguageProfiles (python/go/nodejs/java/csharp) + registry, resolution; go_/csharp_ parser+splicer
├── validators/     # Per-language *_semantic_checks.py, todo_scanner, observability_artifact_*
├── implementation_engine/  # spec→draft→review prompt construction: spec_builder, drafter, budget, prompts/ (YAML)
├── workflows/      # WorkflowBase + registry + builtin/ (lead/primary contractor, plan_ingestion, *_review, etc.)
├── dashboard_creator/      # Grafana dashboard gen: workflow, compiler, generator, models
├── seeds/, project/        # Seed task builder/derivation; project scaffolding
├── observability/  # OTel manifest/collector + artifact_generator (Dashboard/Alert/SLO)
├── integrations/   # ContextCore workflow adapter + task runner
├── diagnostics/, evaluation/, storage/, events/, mcp/, skills/, prompt_builder/,
├── ratelimit/, resilience/, server/ (Starlette REST), testing/, help_content/
│
scripts/   # ~52 runner/utility scripts (run_prime_workflow.py, run_contextcore_workflow.py, run_artisan_* [ON HOLD], …)
tests/     # ~523 files — unit/ (contractors ~2744, micro_prime ~355, …), integration/, e2e/, contract_validation/
docs/, examples/
```

## Architecture

### Provider Pattern

The SDK uses a provider abstraction to support multiple LLM backends:

```python
# Discover and use providers
from startd8.providers import ProviderRegistry

ProviderRegistry.discover()
provider = ProviderRegistry.get_provider("anthropic")
provider.validate_config({})
agent = provider.create_agent("claude-sonnet-4-20250514")
```

### Deterministic App Generation (`backend_codegen`) — bucket 1, $0 LLM

The active **applicational-completion** path: projects one `schema.prisma` contract into a working
all-Python app (FastAPI + Pydantic + SQLModel + HTMX + Jinja2) with **zero LLM cost**. Drives the
`startd8 generate {frontend,backend,scaffold,views}` cascade.
- `pydantic_renderer.py` / `sqlmodel_renderer.py` — models + tables (FK, `Relationship()` back_populates,
  `@default` translation, reserved-name guard, compound `@@id` PKs)
- `crud_generator.py`, `htmx_generator.py`, `pages_generator.py`, `pages_authoring.py` — CRUD + HTMX UI + pages
- `assembler.py`, `derived.py`, `forms_manifest.py` — assembly, derived artifacts, form manifests
- `drift.py`, `gates.py`, `test_emitter.py` — `--check` idempotency drift, quality gates, generated test suites
- `provider.py` — `PydanticSQLModelProvider`, registered under the `startd8.contractors.deterministic_providers`
  entry-point group the prime-contractor skip-hook consults (~12 owned `$0.00-skip` kinds). Sibling $0 codegen
  modules register the same way: `frontend_codegen` (`PrismaZodFileProvider`), `scaffold_codegen`
  (`ScaffoldFileProvider`), `view_codegen` (`CompositeViewProvider`).
- `ai_layer.py` — the ONE in-scope LLM aspect (bucket 3 integration): **source-bound extraction** passes
  (FR-SBE-1..6 / FR-IMP-4/5) where the harness threads `source_id` and server-stamps a provenance
  `binding`, so an AI pass cannot silently invent values not traceable to source.

### Presentation Polish (`presentation_polish`) — bucket 1, $0 LLM, Tier 1

Post-build presentation-layer capability: CSS-only restyle of an already-generated bare all-Python app
into an accessible, themed UI — **deterministic, $0**. Drives `startd8 polish {apply,check,themes}`.
- `css.py`, `tokens.py`, `themes.py` — design-system stylesheet, design tokens, curated accessible themes
- `engine.py` — apply/check orchestration (idempotent; `check` exits 0=in-sync/1=drift/2=error)
- `provider.py` — `PresentationPolishFileProvider` (coexists with backend_codegen's provider)
- FR-25 integration: small static-mount hook in generated `main.py` + base.html `<link>` (additive)
- Tier 2 (LLM bespoke design) is **deferred**; Tier 1 ships CSS restyle only.

### Artisan Contractor (8-Phase Orchestrator) — ON HOLD

> **ON HOLD (2026-03-12).** Prime Contractor is the only active construction path. Artisan code
> remains for reference and is not deleted, but don't invest new work here. Routing between Prime
> and Artisan is vestigial. See `docs/ARTISAN_WORKFLOW_GUIDE.md` for full details.

8 phases, split into a design half (PLAN→SCAFFOLD→DESIGN) and implementation half
(IMPLEMENT→INTEGRATE→TEST→REVIEW→FINALIZE) joined by a handoff file. Phase handlers live in
`context_seed/core.py` (re-exported via `context_seed_handlers.py` compat wrapper). Patterns reused
by Prime: per-phase checkpoint/crash recovery (`checkpoint.py`), resume caching to `.startd8/state/`
with 3-layer validation (schema version → source checksum → per-task file hash), contract validation
(`artisan-pipeline.contract.yaml` + `gate_contracts.py`), and per-task error guards.

### Model Benchmark Matrix + Track 2 Behavioral Scoring

Benchmarks measure *model skill* (deterministic cascade + micro-prime OFF), distinct from the $0 codegen path.
- `model_comparison.py` — `startd8 compare-models`: one seed → N models, each in an isolated sandbox, ranked
  (disk-quality, tie-break cost-per-feature). The reusable core the matrix builds on.
- `benchmark_matrix/` — Summer 2026 grid (service×model×repetition):
  - `run_spec.py` `BenchmarkRunSpec` (immutable, content-hashed) · `budget.py` fail-closed preflight + cumulative abort.
  - `runner.py` `SubprocessCellExecutor` (drives `run_prime_workflow.py --benchmark-mode`); **infra-fail classification**
    excludes env failures (dead/missing key, 401/404/rate-limit) from scores — a **missing key is `infra_fail`, never the
    model's catastrophic 0** (`is_infra_error`).
  - `aggregate.py` distribution-appropriate: **median + IQR + pass-rate + catastrophic** (not mean); `rank_models_by_quality`
    (peak) + `rank_models_by_consistency` (reliability — K1).
  - `scoring.py` composite = structural gated by a **compile floor** (COMPILE_FLOOR) + optional **behavioral functional term**
    (`FUNCTIONAL_WEIGHT`); gates floor first; missing terms degrade (FR-32), never 0.
  - `behavioral/` (**Track 2 executed functional-correctness**): `run_service_sandboxed` (long-lived server + loopback
    client + guaranteed process-group kill; loopback-allowed/egress-denied), `StartupContract`+`resolve_serve_command`
    (seed `startup` block + Node serve hook), `node_runtime/` vendored offline closure (grpc-js+proto-loader+**pino+uuid**),
    `prepare_node_workdir` (proto at all conventional + service-relative paths), `charge_suite.py` SDK-authored
    `PaymentService.Charge` ground truth. Env failure → degrade with the missing module/proto path named.
- **Persist-then-rescore (Mottainai):** runs write a durable batch (`cells.json`+`report.md`); `scripts/rescore_behavioral.py`
  re-scores persisted servers for **$0** as the harness improves (generate once, re-score free). Pilot:
  `scripts/run_behavioral_pilot.py` (`--dry-run` default, `--run` spends; run under `doppler run -p startd8 -c dev`).
- Design: `docs/design/benchmark-scoring/` (FUNCTIONAL_CORRECTNESS_* incl. Track 2 v0.2), `docs/design/PRIME_MODEL_COMPARISON_*`.

### Key Classes

- `AgentFramework` - Core orchestration, manages prompts/responses/storage
- `BenchmarkRunner` - Run comparisons across multiple agents
- `Pipeline` - Sequential workflow execution
- `ProviderRegistry` - Dynamic provider discovery via entry points
- `CostTracker` - Track API costs across providers
- `ArtisanContractorWorkflow` - 8-phase code generation orchestrator (ON HOLD)
- `PrimeContractorWorkflow` - Multi-feature batch code generation (active construction path)
- `PrimePostMortemEvaluator` - Post-mortem evaluation with disk quality scoring
- `SecurityScoreResult` / `GateVerdictReport` - Security Prime scoring and gate decisions
- `QueryPrimeEngine` - Secure database query generation by tier
- `ExemplarRegistry` - Proven exemplar lookup and promotion
- `LanguageRegistry` - Multi-language profile discovery and resolution (5 languages)
- `WorkflowBase` - Base class for registered workflows
- `ModelCatalogEntry` - Centralized model defaults with `.agent_spec` property

### ContextCore Integration

`integrations/contextcore.py` provides unified project observability and task tracking:
- `ContextCoreConfig` - Configuration for project/task/sprint IDs
- `ContextCoreWorkflowAdapter` - Wraps workflows with OTel span tracking
- `ContextCoreTaskRunner` - Multi-task runner with dependency resolution
- `ContextCoreTaskSource` - Loads tasks from `~/.contextcore/state/{project}/` (single-project only)
- OTel semantic conventions: `CONTEXTCORE_PROJECT_ID`, `CONTEXTCORE_TASK_ID`, etc.

**SpanState v2 compliance** (when emitting ContextCore state files via `task_tracking_emitter`):
- Top-level `status` field is **required**: `"OK"` / `"ERROR"` / `"UNSET"` (distinct from `task.status` attribute)
- `task.status` must use ContextCore canonical enum: `backlog|todo|in_progress|in_review|blocked|done|cancelled` — NOT `"pending"`
- `task.type` must use canonical enum: `epic|story|task|subtask|bug|spike|incident` — custom classifiers go in `task.labels`
- `task.percent_complete` attribute required for Grafana gauge panels
- Zero-point `task.created` event with `percent_complete: 0` required for burndown charts
- See `ContextCore/docs/plans/WEAVER_CROSS_REPO_ALIGNMENT_REQUIREMENTS.md` (REQ-8) for cross-repo dashboard alignment

### Complexity Classification and Micro Prime

The SDK routes code generation tasks by complexity tier:
- `complexity/classifier.py` — `classify_tier()` assigns TRIVIAL/SIMPLE/MODERATE/COMPLEX
- `complexity/router.py` — Routes tasks to the appropriate generator
- `micro_prime/engine.py` — `MicroPrimeEngine` handles SIMPLE/MODERATE tasks locally (no LLM calls for trivial)
- `micro_prime/decomposer.py` — Breaks MODERATE elements into SIMPLE sub-elements (Class/Function strategies)
- `micro_prime/splicer.py` — Splices generated code into existing files
- `micro_prime/prime_adapter.py` — Bridges PrimeContractor ↔ MicroPrime

### Multi-Language Support

The SDK supports code generation for multiple languages via a Protocol-based abstraction:

```python
from startd8.languages import LanguageProfile, LanguageRegistry, resolve_language

LanguageRegistry.discover()  # loads from entry points
profile = resolve_language(["src/main.go", "src/util.go"])  # -> GoLanguageProfile
```

| Language | ID | Capabilities | MicroPrime | Semantic Checks |
|----------|-----|-------------|------------|-----------------|
| **Python** | `python` | AST repair, Ruff lint, pytest, pip | Full (AST splicer) | 4 checks (dupe main, dupe defs, bare except, phantom imports) |
| **Go** | `go` | goimports/gofmt, text-based stub detection, body splicing, go.mod gen | Full (text-based splicer) | unchecked error, dot import, contamination, package dir |
| **Node.js** | `nodejs` | Node syntax check, npm test, CommonJS+ESM, package.json gen | Full | require/import style, var usage, console.log |
| **Java** | `java` | Gradle compile, text-based stub detection, build.gradle gen | Full | empty catch, wildcard import, raw types, @Override, contamination |
| **C#** | `csharp` | .NET build, csproj gen, namespace validation, file-scoped namespaces | Full | namespace alignment, SQL injection, credential leakage, console output |

Key patterns:
- **LanguageProfile protocol**: 15 properties/methods covering syntax check, lint, test, stub detection, dependency file gen, Docker images, merge strategy
- **Multi-language MicroPrime**: All 5 languages support MicroPrime element-level generation. Python uses AST-based splicer; Go uses text-based splicer with brace matching; C#/Node.js/Java use file-whole generation with element-level decomposition.
- **Per-language semantic validators**: Each language has a dedicated `*_semantic_checks.py` module with language-specific quality checks
- **Per-language repair steps**: ~45 repair steps organized by language (Go: 5, Java: 5, C#: 4, Node.js: 3, Python: core, cross-language: 2)
- **resolve_language()**: Counts file extensions across target files, returns dominant language profile, falls back to Python
- **Go-specific tooling**: `go_parser.py` (regex-based structure extraction), `go_splicer.py` (text-based body splicing with brace matching)

### Kaizen Quality System

Cross-run quality measurement and improvement feedback loop (Phases A-E):

- **Phase A — Registry Enrichment**: `engine.py` emits generation metadata (strategy, model, timing, AST validity) per element
- **Phase B — Disk Validation**: `forward_manifest_validator.py:validate_disk_compliance()` → `DiskComplianceResult` (AST valid, stubs remaining, import completeness, contract compliance, semantic issues)
- **Phase C — Feedback Loop**: `prime_postmortem.py:CAUSE_TO_SUGGESTION` (25 root cause mappings) → `generate_kaizen_suggestions()` → kaizen hints injected as P1 sections in spec/draft prompts
- **Phase D — Semantic Validation**: `validators/semantic_checks.py` — 4 AST checks (duplicate main guards, duplicate definitions, bare except:pass, phantom imports). Wired into `integration_engine.py` as non-blocking warnings.
- **Phase E — Dual Scoring**: `compute_disk_quality_score()` = (contract_compliance × 0.4) + (import_completeness × 0.2) + (stub_penalty × 0.2) + (semantic_penalty × 0.2). `assembly_delta` = requirement_score - disk_quality_score.

Post-mortem artifacts per run:
- `prime-postmortem-report.json` — per-feature scores, disk compliance, semantic issues
- `prime-postmortem-summary.md` — human-readable summary
- `kaizen-metrics.json` — aggregate metrics (success rate, cost, assembly delta, semantic breakdown)
- `kaizen-suggestions.json` — actionable improvement suggestions
- `batch-postmortem-report.json` — cross-run progression tracking
- `kaizen-trends.json/md` — success rate slope, cost slope, failure patterns across runs
- `kaizen-correlation.json/md` — prompt feature ↔ outcome Spearman correlations

### Security Prime

Security validation orchestration wired into the prime contractor pipeline:
- `security_prime/contract.py` — `derive_security_contract()` extracts security context from seed tasks
- `security_prime/enrichment.py` — `enrich_security_fields()` injects security context into spec/draft prompts
- `security_prime/scorer.py` — `compute_security_score()` → `SecurityScoreResult` (injection, credentials, lifecycle)
- `security_prime/gate_models.py` — `GateVerdictReport` for Anzen gate pass/fail decisions
- Wired via `integration_engine.py` → `verify_file()` from `query_prime/security/`
- Kaizen integration: `update_query_security_metrics()` writes `query_security` section to kaizen-metrics.json

### Query Prime

Secure database query generation engine:
- `query_prime/engine.py` — `QueryPrimeEngine` orchestrates query generation by tier (T1=template, T2=Haiku, T3=Sonnet)
- `query_prime/classifier.py` — `classify_query_tier()` routes queries to appropriate model
- `query_prime/security/` — `verify_file()` checks for injection, credential leakage, lifecycle issues
- `query_prime/patterns/` — DB-specific patterns (Redis, MySQL, SQLite, Spanner, PostgreSQL)
- Integrated into plan ingestion via query-informed enrichment (REQ-QPI)

### Proven Exemplar Pipeline (PEP)

Mines perfect-score features from prior runs to use as templates:
- `exemplars/extractor.py` — `extract_exemplars_from_run()` identifies features scoring 1.00
- `exemplars/registry.py` — `ExemplarRegistry` with fingerprint-based lookup
- `exemplars/structural_extractor.py` — AST-based structural fingerprinting (`ConfigFingerprint`)
- `exemplars/template_promoter.py` — Promotes mature exemplars to MicroPrime templates
- Exemplar data persisted to `exemplar-registry.json` per run

### Keiyaku A2A Contracts (Micro Prime)

Agent-to-agent boundaries in Micro Prime use typed contracts per the [Keiyaku Design Principle](docs/design-princples/KEIYAKU_DESIGN_PRINCIPLE.md):
- `ClassificationResult` — carries `TaskComplexitySignals` from classifier to decomposer (K-10)
- `EscalationHandoff` — structured JSON handoff replacing prose escalation context (K-6)
- `EscalationRepairOutcome` — structured repair diagnostics at escalation boundary (K-9)
- `SemanticVerificationResult` — pre-defined contract for LLM semantic verification (K-7)

See `docs/design/micro-prime/KEIYAKU_GAP_ANALYSIS.md` for the full boundary inventory.

### Repair Pipeline

Post-generation repair for syntax, lint, and import errors:
- `repair/orchestrator.py` — `run_file_repair()`, `run_element_repair()` orchestrators
- `repair/diagnostics.py` — Checkpoint diagnostic parsing and failure classification
- `repair/routing.py` — Routes failures to appropriate repair steps
- `repair/staging.py` — Atomic staging for safe repair operations
- Integration: `IntegrationEngine._attempt_pre_merge_repair()` (pre-merge) and `_attempt_repair()` (post-merge)

### Implementation Engine (Prompt Pipeline)

The `implementation_engine/` module handles spec→draft→review prompt construction:
- **Consolidated prompts**: All templates in `contractor_prompts.yaml` (single source of truth). Fallback strings in `prompts/__init__.py` ensure the engine works without the YAML file.
- **Budget enforcement**: `enforce_prompt_budget()` uses P0-P3 priority-ordered section removal. `TOTAL_SPEC_BUDGET_TOKENS` (4096) and `TOTAL_DRAFT_BUDGET_TOKENS` (8192) hard caps.
- **Primary Contractor**: The `LeadContractorWorkflow` is now also exported as `PrimaryContractorWorkflow` (alias). Comments/docstrings use "Primary Contractor" terminology; the `lead_contractor_*` filenames and class names are preserved for backward compatibility.

### Forward Manifest

Design-time contract forwarding for review-time validation:
- `forward_manifest.py` — `ForwardManifest`, `InterfaceContract` models
- `forward_manifest_extractor.py` — Extracts contracts from source code AST
- `forward_manifest_validator.py` — Validates generated code against contracts, produces `ContractViolation` list; also provides `DiskComplianceResult` + `validate_disk_compliance()` for post-assembly disk validation (10 validation layers: imports, stubs, duplicates, factory returns, discarded returns, service identity, method resolution, reachability, contract compliance, semantic issues)
- Consumed by `ReviewPhaseHandler` to enforce structural compliance and by `PrimePostMortemEvaluator` for disk quality scoring

### Context Seed Compat Wrapper Pattern

`context_seed_handlers.py` is a **compatibility wrapper** that re-exports all symbols from the `context_seed/` subpackage. This preserves the legacy import path (`from startd8.contractors.context_seed_handlers import X`) while allowing the implementation to live in organized submodules. **When modifying context_seed/, always verify that new public symbols are re-exported in the wrapper and that test `mock.patch` targets reference `context_seed.core`, not `context_seed_handlers`.**

### Session Tracking

`session_tracking.py` provides session lifecycle management:
- `SessionTracker` / `get_session_tracker()` - Track session state, metrics, and context usage
- `SessionMetrics`, `SessionState`, `ContextUsage` - Session data models

### Entry Points

The SDK uses `pyproject.toml` entry points for plugin discovery:
```toml
# Providers (6 registered)
[project.entry-points."startd8.providers"]
anthropic, openai, ollama, gemini, mistral, mock

# Workflows (16 registered)
[project.entry-points."startd8.workflows"]
pipeline, doc-enhancement, iterative-dev, design-polish,
critical-review, convergent-review, lead-contractor,
lead-contractor-contextcore, primary-contractor,
primary-contractor-contextcore, architectural-review-log,
policy-analysis, plain-language, plan-ingestion,
domain-preflight, dashboard-create

# Language profiles (5 registered)
[project.entry-points."startd8.languages"]
python, go, nodejs, java, csharp

# Deterministic-file providers (5 registered) — the prime-contractor skip-hook consults these
# to decide a file is $0 deterministically-owned (no LLM)
[project.entry-points."startd8.contractors.deterministic_providers"]
prisma-zod, pydantic-sqlmodel, scaffold, composite-view, presentation-polish

# Contractor plugins
[project.entry-points."startd8.contractors.instrumentors"]
[project.entry-points."startd8.contractors.size_estimators"]
[project.entry-points."startd8.contractors.merge_strategies"]

# Third-party preflight rules
[project.entry-points."startd8.preflight_rules"]
```

## Conventions

### Naming
- **Files:** snake_case.py (e.g., `document_enhancement.py`)
- **Classes:** PascalCase (e.g., `BenchmarkRunner`)
- **Functions:** snake_case (e.g., `run_benchmark`)
- **Constants:** UPPER_SNAKE_CASE

### Code Style
- Type hints on all public functions
- Pydantic models for data structures
- Async support via `async/await` (many methods have sync + async variants)
- Rich console output for CLI commands

### Agent Specs
Agents are specified as `provider:model` strings:
- `anthropic:claude-sonnet-4-20250514`
- `openai:gpt-4-turbo-preview`
- `gemini:gemini-1.5-pro`
- `mistral:mistral-large-latest`
- `ollama:llama2`
- `mock:mock-model`

### Storage
- Default storage: `.startd8/` directory in project root
- JSON-based file storage (prompts, responses, benchmarks)
- Configurable via `AgentFramework(storage_dir=...)`

## Important Context

### Must Do
- Always call `ProviderRegistry.discover()` before using providers
- Call `provider.validate_config({})` before creating agents
- Use `BaseAgent` as the type hint for agents (not specific implementations)
- Run tests with `pytest` before committing changes
- Preserve existing exception handling patterns in `exceptions.py`
- Use `from startd8.logging_config import get_logger` for logging in SDK modules (NOT `logging.getLogger()`) — ensures OTel log bridge attachment for Loki visibility
- Use `ModelCatalogEntry.agent_spec` for model defaults — don't scatter hardcoded model strings
- When modifying `context_seed/` subpackage, verify new symbols are re-exported in `context_seed_handlers.py` compat wrapper
- When splitting modules, run `grep -rn 'from old_module import\|patch.*old_module' tests/` to find all symbols and patch targets that need forwarding
- When adding new LLM-calling boundaries in `micro_prime/`, define JSON input/output contracts before implementation (REQ-MP-1010, Keiyaku compliance gate)
- Call `LanguageRegistry.discover()` before using language profiles (same pattern as ProviderRegistry)
- All 5 languages (Python, Go, Node.js, Java, C#) support MicroPrime element-level generation — file-whole bypass is no longer the default for non-Python tasks

### Must Avoid
- Don't hardcode API keys - they come from environment variables
- Don't skip provider validation - it checks for required config
- Don't use blocking calls in async code paths
- Don't modify the `__all__` exports without updating tests
- Don't use `logging.getLogger()` directly in `contractors/` or other SDK modules — logs silently miss Loki
- Don't hardcode model version strings — use `model_catalog.py` centralized defaults
- Don't use ad-hoc status strings in `task_tracking_emitter` — use ContextCore's canonical `TaskStatus` enum values from `contracts/types.py` (`todo`, not `pending`)
- Don't omit the top-level `status` field when creating ContextCore state files — SpanState v2 requires it (`UNSET`/`OK`/`ERROR`)
- Don't patch `context_seed_handlers.X` in tests when the code under test imports from `context_seed.core` — patch where the symbol is **looked up**, not where it's re-exported
- Don't split a module without updating the logger acquisition policy test allowlist (`test_logger_acquisition_policy.py`) for any new files using string logger names

### Environment Variables
```bash
ANTHROPIC_API_KEY    # For Claude models
OPENAI_API_KEY       # For GPT models
GOOGLE_API_KEY       # For Gemini models
MISTRAL_API_KEY      # For Mistral models
OLLAMA_HOST          # Ollama server URL (optional)
```

### Infrastructure Config (repo root)
- `pytest.ini` - Test markers and asyncio config
- `docker-compose.loki-stack.yml` - Loki/Grafana observability stack
- `promtail-config.yml` - Log shipping to Loki
- `.contextcore.yaml` - ContextCore project/task configuration

### Known Issues
- Response ID tracking has edge cases in concurrent scenarios
- Gemini provider requires separate google-genai package
- Cost tracking assumes standard pricing (may differ for enterprise)

## Version

Current version: **0.4.0** (defined in pyproject.toml)

Pre-1.0 SemVer: breaking changes may occur in MINOR versions.

## Documentation

Key docs in `docs/`:
- `SDK_ARCHITECTURE_v1.md` - Architecture overview
- `API_REFERENCE_v1.md` - API reference
- `ARTISAN_WORKFLOW_GUIDE.md` - Artisan contractor workflow guide (phases, handoff, scripts)
- `COST_TRACKING_USER_GUIDE.md` - Cost tracking guide
- `PIPELINE_WORKFLOWS_v1.md` - Pipeline workflows
- `PRIME_CONTRACTOR_WORKFLOW_GUIDE.md` - Prime contractor pattern guide
- `TUI_USER_GUIDE_v1.md` - TUI usage guide
- `DOWNSTREAM_WORKAROUND_CATALOG.md` - Downstream project workaround tracking
- `ITERATIVE_DEV_WORKFLOW.md` - Iterative development workflow
- `FEATURE_WORKFLOW_GUIDE.md` - Feature workflow guide
- `LOKI_SETUP_GUIDE.md` - Observability/Loki setup
- `PATTERN-truncation-detection.md` - Code-aware truncation detection pattern
- `PATTERN-silent-telemetry-loss.md` - OTel log bridge init gap pattern
- `ARTISAN_WORKFLOW_ISSUES_CATALOG.md` - Known artisan pipeline issues and fixes
- `docs/design/` - Design documents for major features
- `docs/design/micro-prime/` - Micro Prime engine requirements and plans
- `docs/design/prime/` - Prime Contractor requirements, Kaizen convergent review
- `docs/design/kaizen/` - Kaizen quality system requirements, validation reports, phase plans
  - Per-language: `KAIZEN_PYTHON_REQUIREMENTS.md`, `KAIZEN_CSHARP_REQUIREMENTS.md`, `KAIZEN_GO_REQUIREMENTS.md`, `KAIZEN_JAVA_REQUIREMENTS.md`, `KAIZEN_NODEJS_REQUIREMENTS.md`
  - Observability: `KAIZEN_OBSERVABILITY_ARTIFACT_REQUIREMENTS.md`
- `docs/design/security-prime/` - Security Prime requirements (7 docs)
- `docs/design/query-prime/` - Query Prime requirements + query-informed plan ingestion (7 docs)
- `docs/design-princples/` - Cross-cutting design principles:
  - `MOTTAINAI_DESIGN_PRINCIPLE.md` - Don't discard artifacts (within a run)
  - `KAIZEN_DESIGN_PRINCIPLE.md` - Don't discard lessons (across runs)
  - `WARM_UP_DESIGN_PRINCIPLE.md` - Don't discard context (across toolchain transitions)
  - `HAYAI_DESIGN_PRINCIPLE.md` - Don't defer enforcement (across pipeline stages)
  - `SOTTO_DESIGN_PRINCIPLE.md` - Don't disturb what exists (authored content rides the deterministic skeleton via a hash-exempt, presence-gated seam → byte-identical-when-absent)
- `docs/capability-index/` - Capability tracking across versions (benefits, capabilities, functional requirements, agent card, MCP tools)

## Embedded Pipeline (`.cap-dev-pipe/`)

This project embeds the **Capability Delivery Pipeline** via symlinks to the canonical source at `~/Documents/dev/cap-dev-pipe/`. The `.cap-dev-pipe/` directory contains:

- **Symlinked scripts** — `run-cap-delivery.sh`, `run-plan-ingestion.sh`, `run-prime-contractor.sh`, `run-artisan.sh`, `resolve-provenance.py`
- **`pipeline.env`** — project-specific config (tracked in git)
- **`pipeline-output/`** — runtime artifacts (gitignored)

Run pipeline commands from `.cap-dev-pipe/`:
```bash
cd .cap-dev-pipe
./run-cap-delivery.sh --plan /path/to/plan.md --requirements /path/to/reqs.md --project startd8 --name my-run
./run-plan-ingestion.sh --provenance pipeline-output/my-run/run-provenance.json
./run-prime-contractor.sh --provenance pipeline-output/my-run/run-provenance.json --list
```

## Lessons Learned

See `SDK_developer_LESSONS_LEARNED.md` at `/Users/neilyashinsky/Documents/craft/Lessons_Learned/sdk/` for accumulated development wisdom.
