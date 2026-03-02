# Dashboard Creator (dbrd-cr8r) — Implementation Plan

**Version:** 0.1.0
**Created:** 2026-03-01
**Status:** DRAFT
**Requirements:** [`DBRD_CR8R_REQUIREMENTS.md`](DBRD_CR8R_REQUIREMENTS.md)

## 1. Overview

This plan implements the 36 requirements from `DBRD_CR8R_REQUIREMENTS.md` in 4 delivery phases. Each phase is self-contained and shippable. The plan follows the SDK's established patterns: `WorkflowBase` subclass, Pydantic v2 models, Typer CLI, OTel spans, and entry-point registration.

## 2. Module Layout

```
src/startd8/dashboard_creator/
├── __init__.py                # Public API exports
├── models.py                  # DashboardSpec, PanelSpec, VariableSpec, TargetSpec
├── discovery.py               # MixinContext, ToolchainInfo
├── config_merge.py            # Config override merge + default hydration
├── validation.py              # UID enforcement + cross-field spec validation
├── generator.py               # Jsonnet template engine + panel/variable mapping
├── compiler.py                # Jsonnet compilation (binary + Python fallback)
├── json_validator.py          # Compiled JSON validation
├── output.py                  # Output persistence (deterministic JSON)
├── layout.py                  # Row auto-grouping + gridPos auto-layout
├── batch.py                   # Multi-dashboard batch + dry-run + check mode
├── grafana_client.py          # Minimal httpx Grafana API client
├── provisioning.py            # Opt-in dashboard push to Grafana
├── manifest_sync.py           # DashboardRef upsert into ObservabilityManifest
├── mixin_update.py            # mixin.libsonnet auto-update
├── workflow.py                # DashboardCreatorWorkflow (WorkflowBase subclass)
└── templates/                 # Pre-built YAML spec templates (Phase 4)

tests/unit/dashboard_creator/
├── __init__.py
├── conftest.py                # Shared fixtures (sample specs, mock mixin dir)
├── test_models.py
├── test_discovery.py
├── test_config_merge.py
├── test_validation.py
├── test_generator.py
├── test_compiler.py
├── test_json_validator.py
├── test_output.py
├── test_layout.py
├── test_batch.py
├── test_grafana_client.py
├── test_provisioning.py
├── test_manifest_sync.py
├── test_mixin_update.py
└── test_workflow.py

tests/integration/
└── test_dashboard_creator_e2e.py

docs/schemas/
└── dashboard-spec.schema.json    # Generated from DashboardSpec.model_json_schema()
```

**Files modified (not new):**
- `src/startd8/cli.py` — add `dashboard` subcommand group
- `pyproject.toml` — add `dashboard-create` entry point + `docs/schemas/` inclusion

## 3. Delivery Phases

### Phase 1: MVP (Layer 0 + Core Generation + Registration)

**Goal:** Single dashboard generates + compiles from a YAML spec. Workflow registered and callable via `WorkflowRegistry`.

**Requirements:** DC-000 through DC-007, DC-100 through DC-107, DC-200

**Entry criteria:** `startd8-mixin/` exists with `vendor/` dependencies installed.

**Exit criteria:** `pytest tests/unit/dashboard_creator/ -v` passes. A sample YAML spec produces a valid Grafana dashboard JSON file at `.startd8/dashboards/{uid}.json`.

---

### Phase 2: Provisioning (CLI + Grafana API)

**Goal:** Dashboard pushed to Grafana via `startd8 dashboard create --provision`.

**Requirements:** DC-202, DC-203, DC-206, DC-208

**Entry criteria:** Phase 1 complete.

**Exit criteria:** `startd8 dashboard create spec.yaml` works end-to-end. `startd8 dashboard create --provision` pushes to a running Grafana instance. `startd8 dashboard delete <uid>` removes from Grafana + local files.

---

### Phase 3: Polish (Batch, Layout, Observability)

**Goal:** Batch mode, auto-layout, row grouping, manifest sync, OTel spans.

**Requirements:** DC-108 through DC-111, DC-201, DC-204, DC-205, DC-207

**Entry criteria:** Phase 2 complete.

**Exit criteria:** Batch mode processes a directory of specs with per-dashboard error isolation. `dashboard-create-report.json` emitted. OTel spans visible in Tempo.

---

### Phase 4: Advanced (Deferred — not required for v1)

**Goal:** LLM-assisted generation, alert/recording rule co-generation, template library.

**Requirements:** DC-300 through DC-306

**Entry criteria:** Phase 3 complete.

**Exit criteria:** Deferred. Tracked in requirements doc for future planning.

---

## 4. Task Breakdown

### Phase 1: MVP

#### Task 1.1: Pydantic Models (DC-001, DC-002, DC-003)
**File:** `src/startd8/dashboard_creator/models.py`
**Test:** `tests/unit/dashboard_creator/test_models.py`
**Depends on:** Nothing

Create the core data models:

```python
# models.py

from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

class PanelType(str, Enum):
    STAT = "stat"
    GAUGE = "gauge"
    TIMESERIES = "timeseries"
    TABLE = "table"
    BARCHART = "barchart"
    BAR_GAUGE = "barGauge"
    PIECHART = "piechart"
    HISTOGRAM = "histogram"
    LOGS = "logs"
    ROW = "row"
    TRACEQL_STAT = "traceqlStat"
    TRACEQL_TABLE = "traceqlTable"
    TRACEQL_TIMESERIES = "traceqlTimeseries"
    TRACEQL_GAUGE = "traceqlGauge"
    TRACES = "traces"
    TEXT = "text"

class VariableType(str, Enum):
    PROMETHEUS_DATASOURCE = "prometheusDatasource"
    TEMPO_DATASOURCE = "tempoDatasource"
    LOKI_DATASOURCE = "lokiDatasource"
    SERVICE_NAME = "serviceNameVariable"
    MODEL = "modelVariable"
    AGENT = "agentVariable"
    PROJECT = "projectVariable"
    CUSTOM = "customVariable"
    CONSTANT = "constantVariable"

class GridPos(BaseModel):
    h: int = 8
    w: int = 12
    x: int = 0
    y: int = 0

class TargetSpec(BaseModel):
    expr: str
    legendFormat: str = ""
    # TraceQL targets
    query: Optional[str] = None

class ThresholdStep(BaseModel):
    value: Optional[float] = None
    color: str = "green"

class PanelSpec(BaseModel):
    type: PanelType
    title: str
    # Single-target panels (stat, gauge, barGauge, logs, traceqlStat, etc.)
    expr: Optional[str] = None
    query: Optional[str] = None  # TraceQL
    # Multi-target panels (timeseries, table, barchart, piechart, histogram, etc.)
    targets: Optional[List[TargetSpec]] = None
    # Layout
    gridPos: Optional[GridPos] = None
    group: Optional[str] = None  # Row grouping (DC-108)
    # Common options
    unit: str = ""
    thresholds: List[ThresholdStep] = Field(default_factory=list)
    overrides: List[Dict[str, Any]] = Field(default_factory=list)
    # Panel-specific options (forwarded to constructor)
    options: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_target_source(self) -> "PanelSpec":
        """Panels need either expr, query, targets, or content (text)."""
        if self.type == PanelType.ROW:
            return self  # Rows don't need targets
        if self.type == PanelType.TEXT:
            if "content" not in self.options:
                raise ValueError("Text panels require options.content")
            return self
        has_single = self.expr is not None or self.query is not None
        has_multi = self.targets is not None and len(self.targets) > 0
        if not has_single and not has_multi:
            raise ValueError(
                f"Panel '{self.title}' ({self.type.value}) requires "
                f"'expr', 'query', or 'targets'"
            )
        return self

class VariableSpec(BaseModel):
    type: VariableType
    name: str
    label: str = ""
    # For metric-based variables (model, agent, project)
    metric: Optional[str] = None
    # For custom variables
    query: Optional[str] = None
    multi: bool = False
    # For constant variables
    value: Optional[str] = None

    @model_validator(mode="after")
    def validate_variable_params(self) -> "VariableSpec":
        metric_types = {
            VariableType.MODEL, VariableType.AGENT, VariableType.PROJECT
        }
        if self.type in metric_types and not self.metric:
            raise ValueError(
                f"Variable '{self.name}' ({self.type.value}) requires 'metric'"
            )
        if self.type == VariableType.CUSTOM and not self.query:
            raise ValueError(
                f"Variable '{self.name}' (customVariable) requires 'query'"
            )
        if self.type == VariableType.CONSTANT and not self.value:
            raise ValueError(
                f"Variable '{self.name}' (constantVariable) requires 'value'"
            )
        return self

class DashboardSpec(BaseModel):
    title: str
    uid: Optional[str] = None  # Auto-generated if omitted (DC-006)
    description: str = ""
    tags: List[str] = Field(default_factory=list)
    panels: List[PanelSpec] = Field(min_length=1)
    variables: List[VariableSpec] = Field(default_factory=list)
    datasources: Dict[str, str] = Field(default_factory=dict)
    refresh: Optional[str] = None     # Hydrated from config (DC-005)
    timezone: Optional[str] = None    # Hydrated from config (DC-005)
    time_from: Optional[str] = None   # Hydrated from config (DC-005)
    time_to: Optional[str] = None     # Hydrated from config (DC-005)
    config_overrides: Dict[str, Any] = Field(default_factory=dict)
```

**Tests:**
- Valid spec round-trips through YAML parse → model → `.model_dump()`
- `panels` must be non-empty (min_length=1)
- PanelSpec validator rejects panels without `expr`/`query`/`targets`
- VariableSpec validator rejects metric types without `metric` field
- All 16 `PanelType` enum values are accepted
- All 9 `VariableType` enum values are accepted

**Schema export:** After model creation, run `DashboardSpec.model_json_schema()` and write to `docs/schemas/dashboard-spec.schema.json`. Add a one-time script or pytest fixture that regenerates on model changes.

**Estimated size:** ~180 lines (models.py) + ~200 lines (test_models.py)

---

#### Task 1.2: Mixin Discovery + Toolchain Detection (DC-000, DC-004)
**File:** `src/startd8/dashboard_creator/discovery.py`
**Test:** `tests/unit/dashboard_creator/test_discovery.py`
**Depends on:** Nothing

```python
# discovery.py

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional
import shutil

from startd8.exceptions import ConfigurationError

@dataclass
class MixinContext:
    mixin_dir: Path
    panels_path: Path
    variables_path: Path
    config_path: Path
    dashboards_dir: Path
    vendor_dir: Path
    mixin_libsonnet: Path

@dataclass
class ToolchainInfo:
    backend: Literal["binary", "python"]
    version: str
    binary_path: Optional[str] = None  # For binary backend

def discover_mixin(search_paths: Optional[list[Path]] = None) -> MixinContext:
    """DC-000: Locate and validate startd8-mixin/ directory.

    Search order:
    1. Explicit search_paths (if provided)
    2. SDK package root (Path(__file__).parents[3] / "startd8-mixin")
    3. Current working directory / "startd8-mixin"

    Raises ConfigurationError if:
    - Mixin directory not found
    - Required files missing (panels.libsonnet, variables.libsonnet, config.libsonnet)
    - vendor/ directory missing or empty
    """

def detect_toolchain() -> ToolchainInfo:
    """DC-004: Detect jsonnet compilation toolchain.

    Check order:
    1. jsonnet binary on $PATH (shutil.which("jsonnet"))
    2. _gojsonnet Python package (import _gojsonnet)

    Raises ConfigurationError with installation instructions if neither found.
    """
```

**Tests:**
- Discovery finds mixin in SDK root
- Discovery raises `ConfigurationError` when mixin dir missing
- Discovery raises `ConfigurationError` when vendor/ missing (with "run 'jb install'" message)
- Discovery raises `ConfigurationError` when required `.libsonnet` files missing
- Toolchain detects binary when on PATH (mock `shutil.which`)
- Toolchain falls back to `_gojsonnet` when binary missing (mock import)
- Toolchain raises `ConfigurationError` with install instructions when neither available

**Estimated size:** ~100 lines (discovery.py) + ~150 lines (test_discovery.py)

---

#### Task 1.3: Config Override + Default Hydration (DC-005)
**File:** `src/startd8/dashboard_creator/config_merge.py`
**Test:** `tests/unit/dashboard_creator/test_config_merge.py`
**Depends on:** Task 1.1, Task 1.2

```python
# config_merge.py

from pathlib import Path
from typing import Any, Dict

from startd8.dashboard_creator.models import DashboardSpec
from startd8.dashboard_creator.discovery import MixinContext
from startd8.exceptions import ValidationError

# Known top-level config keys for validation
_VALID_CONFIG_SECTIONS = {
    "datasources", "dashboardTags", "dashboardRefresh",
    "dashboardTimeFrom", "dashboardTimeTo", "serviceName",
    "metrics", "spans", "artisanMetrics", "alertThresholds", "selectors",
}

def parse_config_libsonnet(config_path: Path) -> Dict[str, Any]:
    """Parse config.libsonnet into a Python dict.

    Uses regex extraction for the known structure rather than
    full Jsonnet evaluation (avoids toolchain dependency for config reads).
    Falls back to a hardcoded default map matching the current config.libsonnet.
    """

def merge_config_overrides(
    base_config: Dict[str, Any],
    overrides: Dict[str, Any],
) -> Dict[str, Any]:
    """Deep-merge user overrides into base config.

    Raises ValidationError for unknown override keys.
    """

def hydrate_spec_defaults(
    spec: DashboardSpec,
    config: Dict[str, Any],
) -> DashboardSpec:
    """DC-005: Fill missing optional spec fields from config defaults.

    - refresh → config.dashboardRefresh (default "30s")
    - timezone → "browser"
    - time_from → config.dashboardTimeFrom (default "now-6h")
    - time_to → config.dashboardTimeTo (default "now")
    - datasources → config.datasources UIDs

    Returns a new DashboardSpec (does not mutate input).
    """

def write_config_overlay(
    merged_config: Dict[str, Any],
    output_path: Path,
) -> Path:
    """Write merged config as a temporary .libsonnet file for the compiler.

    Returns the path to the written file.
    """
```

**Tests:**
- Deep-merge overrides leaf values correctly
- Deep-merge preserves unmodified base values
- Unknown override keys raise `ValidationError`
- Hydration fills `refresh` from config when spec.refresh is None
- Hydration fills `timezone` to "browser" when spec.timezone is None
- Hydration fills datasource UIDs from config when spec.datasources is empty
- Hydration does NOT overwrite explicitly-set spec fields

**Estimated size:** ~120 lines (config_merge.py) + ~150 lines (test_config_merge.py)

---

#### Task 1.4: UID Enforcement + Spec Validation (DC-006, DC-007)
**File:** `src/startd8/dashboard_creator/validation.py`
**Test:** `tests/unit/dashboard_creator/test_validation.py`
**Depends on:** Task 1.1, Task 1.3

```python
# validation.py

import re
from typing import Any, Dict, List

from startd8.dashboard_creator.models import DashboardSpec
from startd8.exceptions import ValidationError

_UID_PATTERN = re.compile(r"^cc-[a-z0-9]+-[a-z0-9-]+$")
_UID_MAX_LENGTH = 40
_METRIC_REF_PATTERN = re.compile(r"\$\{metrics\.(\w+)\}")
_SELECTOR_REF_PATTERN = re.compile(r"\$\{selectors\.(\w+)\}")

# Maps PanelType → panels.libsonnet constructor name
PANEL_CONSTRUCTORS: Dict[str, str] = { ... }  # All 16

# Maps VariableType → variables.libsonnet builder name
VARIABLE_BUILDERS: Dict[str, str] = { ... }  # All 9

def enforce_uid(spec: DashboardSpec) -> DashboardSpec:
    """DC-006: Enforce cc-{pack}-{kebab-name} UID convention.

    - If uid is None, auto-generate from title.
    - If uid is set but non-conforming, raise ValidationError with suggestion.
    - Truncate to 40 characters.

    Returns new DashboardSpec with resolved uid.
    """

def generate_uid_from_title(title: str, pack: str = "startd8") -> str:
    """Generate a conforming UID from a dashboard title.

    "My Dashboard" → "cc-startd8-my-dashboard"
    """

def validate_spec(
    spec: DashboardSpec,
    config_keys: Dict[str, Any],
) -> List[str]:
    """DC-007: Cross-field validation.

    Checks:
    1. All PanelSpec.type values have matching constructors
    2. All VariableSpec.type values have matching builders
    3. ${metrics.*} references resolve to config.metrics keys
    4. ${selectors.*} references resolve to config.selectors keys
    5. Panels with targets have at least one; panels with expr are non-empty
    6. No duplicate panel titles

    Returns list of error strings (empty = valid).
    """
```

**Tests:**
- Auto-generate UID: "My Dashboard" → "cc-startd8-my-dashboard"
- Auto-generate handles special characters, spaces, underscores
- Auto-generate truncates to 40 characters
- Conforming UID passes validation
- Non-conforming UID raises `ValidationError` with suggestion
- Unresolvable `${metrics.unknown}` detected
- Unresolvable `${selectors.unknown}` detected
- Duplicate panel titles detected
- Empty `targets` list detected
- Valid spec returns empty error list

**Estimated size:** ~130 lines (validation.py) + ~200 lines (test_validation.py)

---

#### Task 1.5: Jsonnet Template Engine (DC-100, DC-101, DC-102, DC-103, DC-104)
**File:** `src/startd8/dashboard_creator/generator.py`
**Test:** `tests/unit/dashboard_creator/test_generator.py`
**Depends on:** Task 1.1, Task 1.3, Task 1.4

This is the largest single task. The generator transforms a validated `DashboardSpec` into a `.libsonnet` string that follows the mixin composition pattern.

```python
# generator.py

from typing import Any, Dict, List

from startd8.dashboard_creator.models import (
    DashboardSpec, PanelSpec, PanelType, VariableSpec, VariableType, TargetSpec,
)

def generate_dashboard_jsonnet(
    spec: DashboardSpec,
    config_overrides: Dict[str, Any] | None = None,
) -> str:
    """DC-100: Transform DashboardSpec into a .libsonnet string.

    Generated Jsonnet follows the overview.libsonnet pattern:
    1. Import config, dashboards, panels, variables
    2. Extract local m = config.metrics, ds = config.datasources, sel = config.selectors
    3. Create baseDashboard via dashboards.dashboard()
    4. Add templating list from variables
    5. Call dashboards.withPanels(baseDashboard, [...])

    Returns the Jsonnet source as a string.
    """

def _render_panel(panel: PanelSpec) -> str:
    """DC-101: Render a PanelSpec as a panels.*() constructor call."""

def _render_variable(variable: VariableSpec) -> str:
    """DC-102: Render a VariableSpec as a variables.*() builder call."""

def _resolve_metric_refs(expr: str) -> str:
    """DC-103: Replace ${metrics.X} with m.X in expression strings."""

def _resolve_selector_refs(expr: str) -> str:
    """DC-104: Replace ${selectors.X} with sel.X in expression strings."""

def _render_expression(expr: str) -> str:
    """Render an expression string as a Jsonnet string literal.

    Handles metric/selector refs by splitting the string into
    literal parts and variable references:

    'rate(${metrics.requestsTotal}[5m])' →
    'rate(' + m.requestsTotal + '[5m])'
    """

def _render_targets(targets: List[TargetSpec]) -> str:
    """Render a list of TargetSpec as a Jsonnet array of objects."""
```

**Key design decisions:**
- Metric references (`${metrics.X}`) are rendered as Jsonnet string concatenation, not string interpolation, because they need to resolve to `config.metrics.*` Jsonnet values.
- Example: `'rate(${metrics.requestsTotal}[5m])'` → `'rate(' + m.requestsTotal + '[5m])'`
- Literal `$` (e.g., `$__rate_interval`) is preserved unchanged.
- The generator is stateless and pure — no side effects, no file I/O.

**Generated output pattern:**
```jsonnet
local config = (import '../config.libsonnet')._config;
local dashboards = import '../lib/dashboards.libsonnet';
local panels = import '../lib/panels.libsonnet';
local variables = import '../lib/variables.libsonnet';

local m = config.metrics;
local ds = config.datasources;
local sel = config.selectors;

local mimirDatasource = { type: 'prometheus', uid: '${datasource}' };

local baseDashboard = dashboards.dashboard(
  'Agent Performance Overview',
  'cc-startd8-agent-perf',
  description='Agent request latency and session health',
  tags=['startd8', 'agents'],
) {
  templating: {
    list: [
      variables.prometheusDatasource(name='datasource', label='Prometheus'),
      variables.modelVariable(m.requestsTotal, name='model', label='Model'),
    ],
  },
};

dashboards.withPanels(baseDashboard, [
  panels.timeseries(
    'Request Latency P99',
    targets=[
      { expr: 'histogram_quantile(0.99, rate(' + m.responseTimeMs + '[$__rate_interval]))', legendFormat: 'p99' },
    ],
    datasource=mimirDatasource,
    unit='ms',
  ),
  panels.stat(
    'Active Sessions',
    m.activeSessions,
    datasource=mimirDatasource,
    unit='short',
  ),
])
```

**Tests:**
- Generates valid Jsonnet for a minimal spec (1 stat panel)
- Generates correct `dashboards.dashboard()` call with title, uid, description, tags
- Generates correct `panels.*()` calls for each of the 16 panel types
- Generates correct `variables.*()` calls for each of the 9 variable types
- Metric references (`${metrics.X}`) become `m.X` in Jsonnet
- Selector references (`${selectors.X}`) become `sel.X` in Jsonnet
- Literal `$__rate_interval` is preserved
- Multi-target panels render as array of target objects
- Config override import path is correct when overrides present

**Estimated size:** ~350 lines (generator.py) + ~300 lines (test_generator.py)

---

#### Task 1.6: Jsonnet Compilation (DC-105)
**File:** `src/startd8/dashboard_creator/compiler.py`
**Test:** `tests/unit/dashboard_creator/test_compiler.py`
**Depends on:** Task 1.2

```python
# compiler.py

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from startd8.dashboard_creator.discovery import MixinContext, ToolchainInfo
from startd8.exceptions import Startd8Error

class CompilationError(Startd8Error):
    """Jsonnet compilation failed."""
    def __init__(self, message: str, source_path: str = "", line: int = 0):
        self.source_path = source_path
        self.line = line
        super().__init__(message)

@dataclass
class CompilationResult:
    json_str: str
    duration_ms: int
    backend: str  # "binary" or "python"

def compile_jsonnet(
    source_path: Path,
    mixin: MixinContext,
    toolchain: ToolchainInfo,
    timeout_seconds: int = 30,
) -> CompilationResult:
    """DC-105: Compile .libsonnet to JSON.

    Binary backend:
      jsonnet -J vendor/ -J lib/ <source_path>

    Python backend:
      _gojsonnet.evaluate_file(str(source_path), jpathdir=[...])

    Raises:
      CompilationError — Jsonnet syntax/semantic error
      TimeoutError — Compilation exceeded timeout
    """

def compile_jsonnet_string(
    source: str,
    mixin: MixinContext,
    toolchain: ToolchainInfo,
    timeout_seconds: int = 30,
) -> CompilationResult:
    """Compile Jsonnet from a string (writes to tempfile, compiles, cleans up)."""
```

**Tests:**
- Binary backend invokes `subprocess.run` with correct `-J` flags
- Python backend calls `_gojsonnet.evaluate_file` with correct jpathdir
- Compilation error captures Jsonnet error message and line number
- Timeout raises `TimeoutError`
- Result includes `duration_ms` and `backend`
- Output is valid JSON (parseable by `json.loads`)

**Note:** Unit tests mock subprocess/import. Integration test (Task 1.10) exercises real compilation.

**Estimated size:** ~100 lines (compiler.py) + ~120 lines (test_compiler.py)

---

#### Task 1.7: JSON Validation (DC-106)
**File:** `src/startd8/dashboard_creator/json_validator.py`
**Test:** `tests/unit/dashboard_creator/test_json_validator.py`
**Depends on:** Nothing

```python
# json_validator.py

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List

@dataclass
class JsonValidationResult:
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    dashboard_json: Dict[str, Any] = field(default_factory=dict)

_REQUIRED_KEYS = {"title", "uid", "panels", "templating", "schemaVersion"}
_SUPPORTED_SCHEMA_VERSIONS = range(36, 42)  # 36–41; pinned to grafonnet

def validate_dashboard_json(
    json_str: str,
    expected_uid: str,
) -> JsonValidationResult:
    """DC-106: Validate compiled JSON against Grafana dashboard requirements.

    Checks:
    1. Required top-level keys present
    2. uid matches expected_uid
    3. schemaVersion in supported range
    4. panels is a list
    """
```

**Tests:**
- Valid JSON passes all checks
- Missing required key detected
- UID mismatch detected
- Unsupported schemaVersion detected
- Malformed JSON (not parseable) detected

**Estimated size:** ~60 lines (json_validator.py) + ~80 lines (test_json_validator.py)

---

#### Task 1.8: Output Persistence (DC-107)
**File:** `src/startd8/dashboard_creator/output.py`
**Test:** `tests/unit/dashboard_creator/test_output.py`
**Depends on:** Nothing

```python
# output.py

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

@dataclass
class PersistenceResult:
    json_path: Path
    libsonnet_path: Optional[Path] = None

def persist_dashboard(
    dashboard_json: dict,
    uid: str,
    output_dir: Path | None = None,
    libsonnet_source: str | None = None,
    libsonnet_dir: Path | None = None,
) -> PersistenceResult:
    """DC-107: Write dashboard JSON + optional .libsonnet source.

    - JSON → {output_dir}/{uid}.json  (default: .startd8/dashboards/)
    - Libsonnet → {libsonnet_dir}/{name}.libsonnet  (default: startd8-mixin/dashboards/)
    - Deterministic: json.dumps(sort_keys=True, indent=2) + trailing newline
    - Creates parent dirs if needed
    - Upsert semantics (overwrites existing)
    """
```

**Tests:**
- JSON written to correct path with correct content
- Deterministic output: two identical inputs produce byte-identical files
- Trailing newline present
- Parent directories created
- Existing file overwritten
- Libsonnet source written when `persist_source=True`
- Libsonnet source NOT written when `persist_source=False`

**Estimated size:** ~50 lines (output.py) + ~80 lines (test_output.py)

---

#### Task 1.9: Workflow Registration (DC-200)
**File:** `src/startd8/dashboard_creator/workflow.py`
**File:** `src/startd8/dashboard_creator/__init__.py`
**Test:** `tests/unit/dashboard_creator/test_workflow.py`
**Depends on:** Tasks 1.1–1.8

Wire all Phase 1 components into a `WorkflowBase` subclass.

```python
# workflow.py

from startd8.workflows.base import WorkflowBase
from startd8.workflows.models import (
    WorkflowMetadata, WorkflowInput, WorkflowResult, WorkflowMetrics,
    StepResult, ValidationResult,
)

class DashboardCreatorWorkflow(WorkflowBase):

    @property
    def metadata(self) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_id="dashboard-create",
            name="Dashboard Creator",
            description="Generate Grafana dashboards from declarative YAML specs using startd8-mixin",
            version="0.1.0",
            capabilities=["dashboard-generation", "jsonnet", "grafana"],
            tags=["dashboards", "grafana", "monitoring", "observability"],
            requires_agents=False,
            agent_count=AgentCount.NONE,
            min_agents=0,
            inputs=[
                WorkflowInput(name="spec", type="object", required=True,
                              description="DashboardSpec dict or path to YAML/JSON file"),
                WorkflowInput(name="persist_source", type="boolean", required=False,
                              default=False, description="Write .libsonnet to mixin dir"),
                WorkflowInput(name="output_dir", type="string", required=False,
                              description="Override output directory"),
                WorkflowInput(name="dry_run", type="boolean", required=False,
                              default=False, description="Generate without writing"),
                WorkflowInput(name="check", type="boolean", required=False,
                              default=False, description="Validate + compile, no write"),
                # Phase 2 inputs (provision, grafana_url, etc.) added later
            ],
        )

    def _custom_validate(self, config: dict) -> list[str]:
        """DC-007: Delegate to validation.validate_spec()."""

    def _execute(self, config, agents, on_progress) -> WorkflowResult:
        """
        Pipeline:
        1. Parse spec (from dict or file path)
        2. Discover mixin + toolchain
        3. Enforce UID (DC-006)
        4. Merge config overrides + hydrate defaults (DC-005)
        5. Validate spec (DC-007)
        6. Generate Jsonnet (DC-100–DC-104)
        7. Compile Jsonnet (DC-105)
        8. Validate JSON (DC-106)
        9. Persist output (DC-107) — unless dry_run/check
        10. Return WorkflowResult with artifacts
        """
```

**Entry point registration (pyproject.toml):**
```toml
[project.entry-points."startd8.workflows"]
# ... existing entries ...
dashboard-create = "startd8.dashboard_creator.workflow:DashboardCreatorWorkflow"
```

**`__init__.py` exports:**
```python
from startd8.dashboard_creator.models import (
    DashboardSpec, PanelSpec, VariableSpec, TargetSpec,
    PanelType, VariableType, GridPos,
)
from startd8.dashboard_creator.workflow import DashboardCreatorWorkflow

__all__ = [
    "DashboardSpec", "PanelSpec", "VariableSpec", "TargetSpec",
    "PanelType", "VariableType", "GridPos",
    "DashboardCreatorWorkflow",
]
```

**Tests:**
- Workflow discoverable via `WorkflowRegistry.discover()` + `WorkflowRegistry.get("dashboard-create")`
- `metadata.workflow_id == "dashboard-create"`
- `validate_config({})` returns errors for missing required `spec`
- `validate_config({"spec": valid_dict})` returns success
- `run(config, dry_run=True)` returns Jsonnet source in artifacts without writing files
- `run(config)` produces a JSON file at the expected output path
- `run(config, check=True)` validates + compiles but writes nothing
- `dry_run` + `check` together raises `ConfigurationError`

**Estimated size:** ~200 lines (workflow.py) + ~50 lines (__init__.py) + ~250 lines (test_workflow.py)

---

#### Task 1.10: Integration Test + Schema Export
**File:** `tests/integration/test_dashboard_creator_e2e.py`
**File:** `docs/schemas/dashboard-spec.schema.json`
**File:** `tests/unit/dashboard_creator/conftest.py`
**Depends on:** Tasks 1.1–1.9

```python
# conftest.py — shared fixtures

import pytest
from pathlib import Path

@pytest.fixture
def sample_spec_dict():
    """Minimal valid DashboardSpec as a dict."""
    return {
        "title": "Test Dashboard",
        "panels": [
            {"type": "stat", "title": "Test Metric", "expr": "up"}
        ],
    }

@pytest.fixture
def sample_spec_yaml(tmp_path, sample_spec_dict):
    """Write sample spec to a YAML file and return path."""
    import yaml
    spec_path = tmp_path / "test-spec.yaml"
    spec_path.write_text(yaml.dump(sample_spec_dict))
    return spec_path

@pytest.fixture
def mock_mixin_dir(tmp_path):
    """Create a minimal mixin directory structure for testing."""
    mixin = tmp_path / "startd8-mixin"
    (mixin / "lib").mkdir(parents=True)
    (mixin / "dashboards").mkdir()
    (mixin / "vendor").mkdir()
    # Write minimal .libsonnet files
    (mixin / "config.libsonnet").write_text("{ _config+:: {} }")
    (mixin / "lib" / "panels.libsonnet").write_text("{ stat(title, expr):: {} }")
    (mixin / "lib" / "variables.libsonnet").write_text("{ }")
    (mixin / "lib" / "dashboards.libsonnet").write_text(
        "{ dashboard(t, u, description='', tags=[]):: {}, "
        "withPanels(d, p):: d { panels: p } }"
    )
    (mixin / "mixin.libsonnet").write_text("{ grafanaDashboards+:: {} }")
    return mixin
```

**Integration test (`test_dashboard_creator_e2e.py`):**
- Marked `@pytest.mark.integration`
- Requires `jsonnet` binary or `_gojsonnet` on the system
- Full pipeline: YAML spec → DashboardSpec → generate Jsonnet → compile → validate → persist
- Asserts: output JSON has correct uid, title, panels count, schemaVersion

**Schema export:**
- Script or test fixture that runs `DashboardSpec.model_json_schema()` and writes to `docs/schemas/dashboard-spec.schema.json`
- Committed as a checked-in artifact for editor/CI validation

**Estimated size:** ~80 lines (conftest.py) + ~100 lines (e2e test) + JSON schema (auto-generated)

---

### Phase 2: Provisioning

#### Task 2.1: Grafana API Client (DC-202)
**File:** `src/startd8/dashboard_creator/grafana_client.py`
**Test:** `tests/unit/dashboard_creator/test_grafana_client.py`
**Depends on:** Phase 1

```python
# grafana_client.py

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from startd8.exceptions import ConfigurationError, APIError
from startd8.logging_config import get_logger

logger = get_logger(__name__)

_GRAFANA_TOKEN_ENV = "GRAFANA_API_TOKEN"
_GRAFANA_URL_ENV = "GRAFANA_URL"
_MIN_API_VERSION = 9

@dataclass
class GrafanaResponse:
    success: bool
    status_code: int
    data: Dict[str, Any]
    error: Optional[str] = None

class GrafanaClient:
    """Minimal httpx-based Grafana HTTP API client.

    Security:
    - Token from GRAFANA_API_TOKEN env var ONLY
    - Token never logged, stored in spec files, or included in errors
    - HTTPS required by default; --allow-insecure for local dev only
    """

    def __init__(
        self,
        grafana_url: Optional[str] = None,
        allow_insecure: bool = False,
    ):
        self.grafana_url = grafana_url or os.environ.get(_GRAFANA_URL_ENV, "")
        self._token = os.environ.get(_GRAFANA_TOKEN_ENV, "")
        self._allow_insecure = allow_insecure
        self._validate_endpoint()
        self._validate_token()

    def _validate_endpoint(self):
        """Enforce HTTPS unless allow_insecure=True."""

    def _validate_token(self):
        """Raise ConfigurationError if token empty."""

    def check_version(self) -> int:
        """GET /api/health — extract version, raise if < v9."""

    def upsert_dashboard(self, dashboard_json: Dict[str, Any]) -> GrafanaResponse:
        """POST /api/dashboards/db — create or update."""

    def get_dashboard(self, uid: str) -> GrafanaResponse:
        """GET /api/dashboards/uid/{uid}."""

    def search_dashboards(self, query: str = "") -> List[Dict[str, Any]]:
        """GET /api/search?query={query}&type=dash-db."""

    def delete_dashboard(self, uid: str) -> GrafanaResponse:
        """DELETE /api/dashboards/uid/{uid}."""
```

**Tests (all use `httpx` mock/respx):**
- Token loaded from env var only
- HTTPS enforced by default; HTTP rejected with error
- HTTP allowed when `allow_insecure=True` (with warning log)
- 401/403 produces descriptive error about token permissions
- `upsert_dashboard` sends correct payload
- `get_dashboard` returns parsed response
- `delete_dashboard` sends DELETE request
- Version check rejects Grafana < v9
- Connection timeout after 10s
- Token never appears in log output (mock logger, assert no token in calls)

**Estimated size:** ~150 lines (grafana_client.py) + ~200 lines (test_grafana_client.py)

---

#### Task 2.2: Dashboard Provisioning (DC-203)
**File:** `src/startd8/dashboard_creator/provisioning.py`
**Test:** `tests/unit/dashboard_creator/test_provisioning.py`
**Depends on:** Task 2.1

```python
# provisioning.py

from dataclasses import dataclass
from typing import Any, Dict, Optional

from startd8.dashboard_creator.grafana_client import GrafanaClient, GrafanaResponse
from startd8.logging_config import get_logger

logger = get_logger(__name__)

@dataclass
class ProvisioningResult:
    success: bool
    uid: str
    grafana_url: Optional[str] = None  # Clickable URL on success
    error: Optional[str] = None
    status_code: Optional[int] = None

def provision_dashboard(
    dashboard_json: Dict[str, Any],
    client: GrafanaClient,
) -> ProvisioningResult:
    """DC-203: Push compiled dashboard JSON to Grafana.

    On success: returns ProvisioningResult with clickable URL ({grafana_url}/d/{uid}).
    On failure: returns ProvisioningResult with error (compiled JSON preserved locally).
    """

def deprovision_dashboard(
    uid: str,
    client: GrafanaClient,
) -> ProvisioningResult:
    """DC-208: Remove dashboard from Grafana."""
```

**Tests:**
- Successful provision returns clickable URL
- Failed provision returns error with status code
- Token never appears in ProvisioningResult or logs
- Deprovision sends DELETE and returns result
- 404 on deprovision logs warning (dashboard already gone)

**Estimated size:** ~60 lines (provisioning.py) + ~80 lines (test_provisioning.py)

---

#### Task 2.3: CLI Command (DC-206)
**File:** `src/startd8/cli.py` (modify existing)
**Test:** Tests via Typer `CliRunner` in `tests/unit/dashboard_creator/test_cli.py`
**Depends on:** Task 2.2, Phase 1

Add a `dashboard` subcommand group to the existing CLI:

```python
# In cli.py — add near existing command registrations

dashboard_app = typer.Typer(help="Dashboard management commands")
app.add_typer(dashboard_app, name="dashboard")

@dashboard_app.command("create")
def dashboard_create(
    spec_file: Path = typer.Argument(..., help="Path to DashboardSpec YAML/JSON file, or directory for batch"),
    provision: bool = typer.Option(False, "--provision", help="Push to Grafana after compilation"),
    grafana_url: Optional[str] = typer.Option(None, "--grafana-url", help="Grafana instance URL"),
    allow_insecure: bool = typer.Option(False, "--allow-insecure", help="Allow HTTP Grafana endpoints"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Generate Jsonnet without writing"),
    check: bool = typer.Option(False, "--check", help="Validate + compile, no write/provision"),
    persist_source: bool = typer.Option(False, "--persist-source", help="Write .libsonnet to mixin dir"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", help="Override output directory"),
    config_path: Optional[Path] = typer.Option(None, "--config", help="Config override file"),
    print_template: bool = typer.Option(False, "--print-template", help="Print YAML spec skeleton and exit"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
):
    """Generate Grafana dashboards from declarative YAML/JSON specs."""

@dashboard_app.command("delete")
def dashboard_delete(
    uid: str = typer.Argument(..., help="Dashboard UID to delete"),
    grafana_url: Optional[str] = typer.Option(None, "--grafana-url"),
    allow_insecure: bool = typer.Option(False, "--allow-insecure"),
    remove_source: bool = typer.Option(False, "--remove-source", help="Also remove .libsonnet source"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Remove a dashboard from Grafana and local files."""
```

**Tests:**
- `startd8 dashboard create --help` shows all flags
- `startd8 dashboard create --print-template` outputs valid YAML
- `startd8 dashboard create spec.yaml` invokes workflow with correct config
- `--dry-run` and `--check` together exits with error
- `--provision` without `GRAFANA_API_TOKEN` exits with error
- Exit codes: 0 (success), 1 (failure), 2 (partial in batch mode)
- `startd8 dashboard delete <uid> --yes` invokes deletion

**Estimated size:** ~150 lines (cli additions) + ~150 lines (test_cli.py)

---

#### Task 2.4: Wire Provisioning into Workflow
**File:** `src/startd8/dashboard_creator/workflow.py` (modify)
**Depends on:** Tasks 2.1–2.3

Add provisioning inputs to `metadata.inputs` and provisioning step to `_execute()`:

- New inputs: `provision`, `grafana_url`, `allow_insecure`
- After persist step: if `provision=True`, create `GrafanaClient` and call `provision_dashboard()`
- Add `StepResult` for provisioning step
- Print clickable URL to console on success

**Estimated size:** ~40 lines added to workflow.py

---

### Phase 3: Polish

#### Task 3.1: Row Auto-Grouping (DC-108)
**File:** `src/startd8/dashboard_creator/layout.py`
**Test:** `tests/unit/dashboard_creator/test_layout.py`
**Depends on:** Phase 1

```python
# layout.py

from typing import List
from startd8.dashboard_creator.models import PanelSpec, PanelType, GridPos

def auto_group_panels(panels: List[PanelSpec]) -> List[PanelSpec]:
    """DC-108: Insert row panels for grouped panels.

    - Panels without group come first (ungrouped)
    - For each unique group, insert a row panel before group members
    - Groups emitted in order of first appearance
    - Group starting with "+" renders as collapsed=true
    """

def auto_layout_panels(panels: List[PanelSpec]) -> List[PanelSpec]:
    """DC-109: Calculate gridPos for panels without explicit positioning.

    - 24-column grid, 2-column layout (12 units each)
    - Default panel: h=8, w=12
    - Rows: w=24, reset Y cursor
    - Explicit gridPos panels placed first; auto-layout fills around them
    """
```

**Tests:**
- Ungrouped panels come before grouped panels
- Row panels inserted before each group
- "+" prefix → collapsed=true
- Auto-layout: 2 panels → side by side (x=0 and x=12)
- Auto-layout: 3 panels → 2 on first row, 1 on second
- Row panels span full width (w=24)
- Explicit gridPos preserved

**Estimated size:** ~100 lines (layout.py) + ~120 lines (test_layout.py)

---

#### Task 3.2: Dry-Run + Check Mode (DC-110)
**File:** `src/startd8/dashboard_creator/workflow.py` (modify)
**Depends on:** Phase 1

Already stubbed in Phase 1 (`_execute` checks `dry_run` and `check` config flags). This task ensures:
- `dry_run=True`: returns Jsonnet source in `WorkflowResult.output["jsonnet_source"]` without file writes
- `check=True`: runs validation + compilation, returns pass/fail, no file writes or provisioning
- Mutual exclusivity enforced in `_custom_validate`

**Estimated size:** ~30 lines modified in workflow.py (logic already scaffolded in Phase 1)

---

#### Task 3.3: Multi-Dashboard Batch (DC-111)
**File:** `src/startd8/dashboard_creator/batch.py`
**Test:** `tests/unit/dashboard_creator/test_batch.py`
**Depends on:** Phase 1, Task 3.1

```python
# batch.py

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

@dataclass
class BatchDashboardEntry:
    uid: str
    status: str  # "success" or "failure"
    duration_ms: int
    output_path: Optional[str] = None
    error: Optional[str] = None

@dataclass
class BatchReport:
    timestamp: str
    total: int
    succeeded: int
    failed: int
    dashboards: List[BatchDashboardEntry] = field(default_factory=list)

    def exit_code(self) -> int:
        """0 = all success, 2 = partial, 1 = all failed."""

def load_specs_from_directory(dir_path: Path) -> List[dict]:
    """Load all .yaml/.yml/.json spec files from a directory."""

def run_batch(
    specs: List[dict],
    execute_fn: Callable,
    on_progress: Optional[Callable] = None,
) -> BatchReport:
    """DC-111: Process specs with per-dashboard error isolation.

    Each spec is processed independently. Failures are captured in the report
    but do not abort other dashboards.
    """

def persist_batch_report(report: BatchReport, output_dir: Path) -> Path:
    """Write report to .startd8/reports/dashboard-create-report.json."""
```

**Tests:**
- Directory loading finds .yaml, .yml, .json files
- Per-dashboard error isolation: 1 failure doesn't abort others
- Report has correct succeeded/failed counts
- Exit code: 0 (all success), 2 (partial), 1 (all failed)
- Report persisted to correct path
- Progress callback emits per-dashboard updates

**Estimated size:** ~100 lines (batch.py) + ~120 lines (test_batch.py)

---

#### Task 3.4: Manifest Sync (DC-201)
**File:** `src/startd8/dashboard_creator/manifest_sync.py`
**Test:** `tests/unit/dashboard_creator/test_manifest_sync.py`
**Depends on:** Phase 1

```python
# manifest_sync.py

from pathlib import Path
from typing import Any, Dict, List, Optional

from startd8.observability.manifest import DashboardRef, ObservabilityManifest

def sync_dashboard_ref(
    uid: str,
    title: str,
    file_path: str,
    tags: List[str],
    metrics_used: List[str],
    manifest_path: Path,
) -> Optional[DashboardRef]:
    """DC-201: Create/update DashboardRef in ObservabilityManifest.

    - Upsert by UID (no duplicates)
    - Propagate tags to DashboardRef
    - Skip if manifest file doesn't exist (no error)
    - Extract metrics_used from ${metrics.*} references
    """

def remove_dashboard_ref(uid: str, manifest_path: Path) -> bool:
    """DC-208 (partial): Remove DashboardRef from manifest."""
```

**Tests:**
- New DashboardRef appended to manifest
- Existing DashboardRef updated (upsert by UID)
- Tags propagated correctly
- metrics_used populated from metric references
- Missing manifest file → skip without error
- Remove deletes entry, returns True; missing entry returns False

**Estimated size:** ~70 lines (manifest_sync.py) + ~100 lines (test_manifest_sync.py)

---

#### Task 3.5: Mixin Auto-Update (DC-204)
**File:** `src/startd8/dashboard_creator/mixin_update.py`
**Test:** `tests/unit/dashboard_creator/test_mixin_update.py`
**Depends on:** Phase 1

```python
# mixin_update.py

from pathlib import Path

def update_mixin_aggregator(
    dashboard_name: str,
    mixin_libsonnet_path: Path,
) -> bool:
    """DC-204: Add dashboard import to mixin.libsonnet.

    Adds: '{name}.json': (import 'dashboards/{name}.libsonnet'),
    to the grafanaDashboards+:: block.

    - No-op if entry already exists
    - Preserves existing formatting
    """
```

**Tests:**
- New entry added to `grafanaDashboards+::` block
- Duplicate entry not added
- Existing formatting preserved

**Estimated size:** ~50 lines (mixin_update.py) + ~60 lines (test_mixin_update.py)

---

#### Task 3.6: OTel Span Emission (DC-205)
**File:** `src/startd8/dashboard_creator/workflow.py` (modify)
**Depends on:** Phase 1

Add child spans inside `_execute()`:

```python
# Inside _execute():
with self._create_workflow_span(config) as root_span:
    if root_span:
        root_span.set_attribute("dashboard.uid", uid)
        root_span.set_attribute("dashboard.title", spec.title)
        root_span.set_attribute("dashboard.panel_count", len(spec.panels))

    # ... generation step ...
    # Child span: dashboard_creator.generate (duration, panel_count)

    # ... compilation step ...
    # Child span: dashboard_creator.compile (duration_ms, backend)

    # ... provisioning step (if applicable) ...
    # Child span: dashboard_creator.provision (success, status_code)
```

**Estimated size:** ~30 lines added to workflow.py

---

#### Task 3.7: ContextCore Project Context (DC-207)
**File:** `src/startd8/dashboard_creator/workflow.py` (modify)
**Depends on:** Phase 1

Already partially handled by `WorkflowBase._extract_project_context()` and `_enrich_span_with_project_context()`. This task adds:
- Read `.contextcore.yaml` if it exists to extract `project.id` and `project.name`
- Set `CONTEXTCORE_PROJECT_ID` and `CONTEXTCORE_PROJECT_NAME` span attributes
- Include `project_id` in `DashboardRef` metadata
- Graceful degradation when `.contextcore.yaml` absent

**Estimated size:** ~20 lines added to workflow.py

---

#### Task 3.8: Wire Phase 3 into Workflow
**File:** `src/startd8/dashboard_creator/workflow.py` (modify)
**Depends on:** Tasks 3.1–3.7

Update `_execute()` to:
1. Call `auto_group_panels()` before generation (if any panel has `group`)
2. Call `auto_layout_panels()` before generation (for panels without `gridPos`)
3. Call `sync_dashboard_ref()` after successful compilation
4. Call `update_mixin_aggregator()` after writing `.libsonnet` (when `persist_source=True`)
5. Support batch mode: if spec_file is a directory, delegate to `run_batch()`
6. Persist batch report when in batch mode

**Estimated size:** ~60 lines added to workflow.py

---

### Phase 4: Advanced (Deferred)

Not implemented in this plan. Requirements DC-300 through DC-306 are tracked in the requirements document for future cycles. Key dependencies:

- DC-300 (Manifest-driven): Needs DC-201 (manifest sync) from Phase 3
- DC-301 (LLM-assisted): Needs `resolve_agent_spec()` integration + panel signature context
- DC-302/DC-303 (Alert/Recording rules): Needs `alerts.libsonnet` and `rules.libsonnet` parsing
- DC-304 (Templates): Needs Phase 1 models + a `templates/` directory with YAML files
- DC-305 (Incremental update): Needs DC-107 (output persistence) + JSON diff logic
- DC-306 (Smoke tests): Needs DC-107 + Jsonnet test generation

---

## 5. Implementation Order (Dependency-Sorted)

```
Phase 1: MVP
  1.1  models.py              (no deps)
  1.2  discovery.py            (no deps)
  1.7  json_validator.py       (no deps)
  1.8  output.py               (no deps)
  1.6  compiler.py             (1.2)
  1.3  config_merge.py         (1.1, 1.2)
  1.4  validation.py           (1.1, 1.3)
  1.5  generator.py            (1.1, 1.3, 1.4)
  1.9  workflow.py             (1.1–1.8)
  1.10 e2e test + schema       (1.1–1.9)

Phase 2: Provisioning
  2.1  grafana_client.py       (Phase 1)
  2.2  provisioning.py         (2.1)
  2.3  cli.py                  (2.2, Phase 1)
  2.4  wire provisioning       (2.1–2.3)

Phase 3: Polish
  3.1  layout.py               (Phase 1)
  3.2  dry-run/check mode      (Phase 1)
  3.3  batch.py                (Phase 1, 3.1)
  3.4  manifest_sync.py        (Phase 1)
  3.5  mixin_update.py         (Phase 1)
  3.6  OTel spans              (Phase 1)
  3.7  ContextCore context     (Phase 1)
  3.8  wire Phase 3            (3.1–3.7)
```

**Parallelizable within each phase:**
- Phase 1: Tasks 1.1, 1.2, 1.7, 1.8 can all be built in parallel
- Phase 2: Task 2.1 is independent; 2.2 and 2.3 depend on it
- Phase 3: Tasks 3.1, 3.2, 3.4, 3.5, 3.6, 3.7 can all be built in parallel

## 6. Files Modified (Existing)

| File | Change | Phase |
|------|--------|-------|
| `pyproject.toml` | Add `dashboard-create` workflow entry point | 1 |
| `src/startd8/cli.py` | Add `dashboard` subcommand group (`create`, `delete`) | 2 |

## 7. Files Created (New)

| File | Phase | Lines (est.) |
|------|-------|-------------|
| `src/startd8/dashboard_creator/__init__.py` | 1 | 50 |
| `src/startd8/dashboard_creator/models.py` | 1 | 180 |
| `src/startd8/dashboard_creator/discovery.py` | 1 | 100 |
| `src/startd8/dashboard_creator/config_merge.py` | 1 | 120 |
| `src/startd8/dashboard_creator/validation.py` | 1 | 130 |
| `src/startd8/dashboard_creator/generator.py` | 1 | 350 |
| `src/startd8/dashboard_creator/compiler.py` | 1 | 100 |
| `src/startd8/dashboard_creator/json_validator.py` | 1 | 60 |
| `src/startd8/dashboard_creator/output.py` | 1 | 50 |
| `src/startd8/dashboard_creator/workflow.py` | 1 | 200 |
| `src/startd8/dashboard_creator/grafana_client.py` | 2 | 150 |
| `src/startd8/dashboard_creator/provisioning.py` | 2 | 60 |
| `src/startd8/dashboard_creator/layout.py` | 3 | 100 |
| `src/startd8/dashboard_creator/batch.py` | 3 | 100 |
| `src/startd8/dashboard_creator/manifest_sync.py` | 3 | 70 |
| `src/startd8/dashboard_creator/mixin_update.py` | 3 | 50 |
| `docs/schemas/dashboard-spec.schema.json` | 1 | auto |
| `tests/unit/dashboard_creator/conftest.py` | 1 | 80 |
| `tests/unit/dashboard_creator/test_models.py` | 1 | 200 |
| `tests/unit/dashboard_creator/test_discovery.py` | 1 | 150 |
| `tests/unit/dashboard_creator/test_config_merge.py` | 1 | 150 |
| `tests/unit/dashboard_creator/test_validation.py` | 1 | 200 |
| `tests/unit/dashboard_creator/test_generator.py` | 1 | 300 |
| `tests/unit/dashboard_creator/test_compiler.py` | 1 | 120 |
| `tests/unit/dashboard_creator/test_json_validator.py` | 1 | 80 |
| `tests/unit/dashboard_creator/test_output.py` | 1 | 80 |
| `tests/unit/dashboard_creator/test_workflow.py` | 1 | 250 |
| `tests/unit/dashboard_creator/test_grafana_client.py` | 2 | 200 |
| `tests/unit/dashboard_creator/test_provisioning.py` | 2 | 80 |
| `tests/unit/dashboard_creator/test_cli.py` | 2 | 150 |
| `tests/unit/dashboard_creator/test_layout.py` | 3 | 120 |
| `tests/unit/dashboard_creator/test_batch.py` | 3 | 120 |
| `tests/unit/dashboard_creator/test_manifest_sync.py` | 3 | 100 |
| `tests/unit/dashboard_creator/test_mixin_update.py` | 3 | 60 |
| `tests/integration/test_dashboard_creator_e2e.py` | 1 | 100 |
| **Total** | | **~4,330** |

## 8. Risk Mitigations

| Risk | Mitigation | Task |
|------|-----------|------|
| Jsonnet string generation is error-prone | Extensive test coverage per panel type; integration test compiles real Jsonnet | 1.5, 1.10 |
| `_gojsonnet` Python package API differs from binary | Abstract behind `compile_jsonnet()` with backend-specific branches | 1.6 |
| Config override deep-merge is subtle | Explicit tests for leaf override, nested override, unknown key rejection | 1.3 |
| Metric reference resolution edge cases | Test `$__rate_interval` preservation, nested refs, partial refs | 1.5 |
| Grafana API version drift | Version check on client init; pin to v9+ | 2.1 |
| Token leakage in logs/errors | Logger mock tests asserting token never appears; `get_logger()` used (not `logging.getLogger()`) | 2.1 |

## 9. Testing Strategy

| Layer | Count (est.) | Markers | What's Tested |
|-------|-------------|---------|--------------|
| Unit | ~30 test files | `@pytest.mark.unit` | Individual functions, model validation, error handling |
| Integration | 1 test file | `@pytest.mark.integration` | Full pipeline: YAML → Jsonnet → JSON |
| CLI | 1 test file | `@pytest.mark.unit` | Typer command invocation via `CliRunner` |

All tests run with `pytest tests/unit/dashboard_creator/ -v`. Integration tests gated behind `@pytest.mark.integration` (require `jsonnet` toolchain).

## 10. Conventions Followed

- `from startd8.logging_config import get_logger` — not `logging.getLogger()`
- `from startd8.exceptions import ConfigurationError, ValidationError` — SDK exceptions
- Pydantic v2 `BaseModel` with `Field()`, `field_validator`, `model_validator`
- `WorkflowBase` subclass with `metadata`, `_custom_validate`, `_execute`
- Entry point in `pyproject.toml` under `startd8.workflows`
- Type hints on all public functions
- `json.dumps(sort_keys=True, indent=2)` for deterministic output

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: codex (gpt-5)
- **Date**: 2026-03-01 23:41:38 UTC
- **Scope**: Implementation-plan review for deterministic outputs, robust provisioning behavior, and secure filesystem operations

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | Add an explicit version-conflict strategy for provisioning (`412`/revision mismatch): define one deterministic policy (`retry with overwrite` or `fail-fast with remediation`) and wire it into client + workflow flow control. | The plan specifies upsert provisioning but not conflict resolution behavior, creating ambiguity under concurrent edits and making outcomes non-reproducible. | Phase 2: `grafana_client.py` and `provisioning.py` task specs | Integration tests with concurrent dashboard updates must assert deterministic and documented conflict behavior. |
| R1-S2 | Interfaces | medium | Introduce a shared configuration-resolution helper that enforces precedence across CLI flags, env vars, spec fields, and defaults. | Configuration sources are distributed across tasks and can diverge without a single resolver contract. | Phase 1 `workflow.py` + Phase 2 `cli.py` (new helper in `dashboard_creator/config.py` or `workflow.py`) | Table-driven unit tests should cover every overlapping field and prove stable precedence. |
| R1-S3 | Data | medium | Define a typed, versioned batch report model (`schema_version`, required keys, enumerated status/error codes) instead of emitting ad-hoc dicts. | DC-111 requires a structured report, but the implementation plan does not pin a formal schema, which risks downstream parser breakage. | Phase 3 Task 3.3 (`batch.py`) + tests (`test_batch.py`) | Validate emitted reports against a JSON schema and add compatibility tests for schema evolution. |
| R1-S4 | Risks | high | Add bounded retry/backoff/jitter policy for transient Grafana API failures (`429`, `5xx`, timeout) with explicit non-retry cases (`401/403`). | The plan covers timeouts/auth checks but lacks resilience behavior for transient outages/rate limits, a major operational risk. | Phase 2 Task 2.1 (`grafana_client.py`) and Task 2.2 (`provisioning.py`) | Unit tests with mocked responses should verify retry classification, attempt bounds, and backoff timing behavior. |
| R1-S5 | Validation | medium | Add deterministic panel-ID assignment as a first-class implementation step and regression tests for byte-identical output across repeated runs. | Deterministic JSON output is a core requirement, but the plan does not define how panel identifiers remain stable across generation/layout paths. | Phase 1 Task 1.5 (`generator.py`) and Task 1.10 tests | Repeat generation with identical input and assert byte-for-byte output equivalence including panel IDs. |
| R1-S6 | Ops | medium | Implement atomic persistence primitives for JSON/libsonnet/report outputs (temp file + fsync + rename) and require them in all write paths. | Direct overwrite writes can leave partial artifacts on interruption, causing flaky follow-up runs and corrupted CI state. | Phase 1 Task 1.8 (`output.py`) + Phase 3 Task 3.3 (`batch.py`) | Fault-injection tests should verify no partial files are observable after simulated interruption. |
| R1-S7 | Security | high | Add strict path-boundary guards for write/delete operations to prevent traversal or symlink-escape via `uid`, `name`, or user-supplied directories. | The plan writes and deletes files in multiple locations; without normalized boundary checks, malformed inputs can target unintended paths. | Phase 1 (`output.py`) and Phase 2 delete flow (`cli.py`, `workflow.py`, `manifest_sync.py`) | Security tests should cover `../` traversal, absolute-path injection, and symlink escape attempts with hard-fail behavior. |

#### Review Round R2

- **Reviewer**: codex (gpt-5)
- **Date**: 2026-03-01 23:50:58 UTC
- **Scope**: Extra-high pass for deterministic behavior, batch safety, and operational robustness

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Architecture | high | Add Grafana folder targeting to the implementation plan (spec field plus provisioning and CLI wiring), with defined precedence and default root behavior. | Requirements need folder placement to avoid manual dashboard organization; the plan has no model or provisioning hook for it. | Phase 1 Task 1.1 (`models.py`), Phase 2 Task 2.2 (`provisioning.py`), Phase 2 Task 2.3 (`cli.py`) | Provision with a folder set and assert the dashboard is created in that folder; default should land in root. |
| R2-S2 | Interfaces | medium | Implement an escape syntax for literal `${metrics.*}` and `${selectors.*}` tokens in `_resolve_metric_refs`/`_resolve_selector_refs`. | Without escaping, users cannot render literal tokens in labels/annotations and substitution can be surprising. | Phase 1 Task 1.5 (`generator.py`) | Unit tests verify escaped tokens remain literal and unescaped tokens are replaced. |
| R2-S3 | Data | medium | Define list/array merge semantics in `merge_config_overrides` (replace vs concat) and encode them in tests. | Current deep-merge logic is undefined for lists, leading to nondeterministic behavior and divergent expectations. | Phase 1 Task 1.3 (`config_merge.py`) | Table-driven tests for list overrides assert deterministic merge behavior. |
| R2-S4 | Risks | high | Add duplicate UID preflight detection in batch mode (including auto-generated UIDs) and fail before any write/provisioning. | Duplicate UIDs will silently overwrite outputs or dashboards, a high-impact failure mode in batch runs. | Phase 3 Task 3.3 (`batch.py`) and Phase 1 validation hooks | Batch tests with duplicate UIDs must fail fast with a clear error. |
| R2-S5 | Validation | medium | Enforce deterministic batch processing order (sorted paths) and deterministic ordering in the batch report. | Filesystem iteration order varies by platform and breaks reproducibility in CI reports. | Phase 3 Task 3.3 (`batch.py`) | Re-run batch on the same directory and assert report ordering is identical. |
| R2-S6 | Ops | medium | Define explicit error handling for invalid or read-only `observability-manifest.yaml` (warn and continue vs fail-fast) and implement it. | Current plan only addresses the missing-manifest case; invalid manifests are common during early adoption and need predictable behavior. | Phase 3 Task 3.4 (`manifest_sync.py`) | Tests for invalid YAML and permission errors assert documented behavior. |
| R2-S7 | Security | medium | Sanitize Grafana URLs with embedded credentials in logs/errors and ensure the sanitized form is used in all outputs. | URLs can include basic-auth credentials or query tokens and should not leak into logs or reports. | Phase 2 Task 2.1 (`grafana_client.py`) and Task 2.2 (`provisioning.py`) | Tests inject a credentialed URL and assert logs/errors redact secrets. |

#### Requirements Coverage

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| DC-000 Mixin Library Discovery | Task 1.2 (`discovery.py`) | Full | — |
| DC-001 DashboardSpec Model | Task 1.1 (`models.py`) | Full | — |
| DC-002 PanelSpec Model | Task 1.1 (`models.py`) | Full | — |
| DC-003 VariableSpec Model | Task 1.1 (`models.py`) | Full | — |
| DC-004 Jsonnet Toolchain Detection | Task 1.2 (`discovery.py`) | Full | — |
| DC-005 Config Libsonnet Override | Task 1.3 (`config_merge.py`) | Full | — |
| DC-006 UID Convention Enforcement | Task 1.4 (`validation.py`) | Full | — |
| DC-007 Spec Validation | Task 1.4 (`validation.py`) | Full | — |
| DC-100 Jsonnet Template Engine | Task 1.5 (`generator.py`) | Full | — |
| DC-101 Panel Mapping | Task 1.5 (`generator.py`) | Full | — |
| DC-102 Variable Wiring | Task 1.5 (`generator.py`) | Full | — |
| DC-103 Metric Reference Injection | Task 1.5 (`generator.py`) | Full | — |
| DC-104 Selector Reference Injection | Task 1.5 (`generator.py`) | Full | — |
| DC-105 Jsonnet Compilation | Task 1.6 (`compiler.py`) | Full | — |
| DC-106 JSON Validation | Task 1.7 (`json_validator.py`) | Full | — |
| DC-107 Output Persistence | Task 1.8 (`output.py`) | Full | — |
| DC-108 Row Auto-Grouping | Task 3.1 (`layout.py`) | Full | — |
| DC-109 GridPos Auto-Layout | Task 3.1 (`layout.py`) | Full | — |
| DC-110 Dry-Run Mode | Task 3.2 (`dry-run/check`) | Full | — |
| DC-111 Multi-Dashboard Batch | Task 3.3 (`batch.py`) | Full | — |
| DC-200 WorkflowBase Registration | Task 1.9 (`workflow.py`, entry point) | Full | — |
| DC-201 ObservabilityManifest Sync | Task 3.4 (`manifest_sync.py`) | Full | — |
| DC-202 Grafana API Client | Task 2.1 (`grafana_client.py`) | Full | — |
| DC-203 Dashboard Provisioning | Task 2.2 (`provisioning.py`) + Task 2.4 (workflow wiring) | Full | — |
| DC-204 Mixin.libsonnet Auto-Update | Task 3.5 (`mixin_update.py`) | Full | — |
| DC-205 OTel Span Emission | Task 3.6 (`workflow.py` spans) | Full | — |
| DC-206 CLI Command | Task 2.3 (`cli.py`) | Full | — |
| DC-207 ContextCore Project Context | Task 3.7 (`workflow.py`) | Full | — |
| DC-208 Dashboard Deletion/Retirement | Task 2.2 (`provisioning.py`) + Task 2.3 (`cli.py`) | Full | — |
| DC-300 Manifest-Driven Dashboard Generation | Phase 4 (Deferred) | Partial | Deferred; no task breakdown or tests defined in the plan. |
| DC-301 LLM-Assisted Spec Generation | Phase 4 (Deferred) | Partial | Deferred; no implementation steps or validation plan defined. |
| DC-302 Alert Rule Co-Generation | Phase 4 (Deferred) | Partial | Deferred; no task breakdown or acceptance validation in the plan. |
| DC-303 Recording Rule Co-Generation | Phase 4 (Deferred) | Partial | Deferred; no task breakdown or acceptance validation in the plan. |
| DC-304 Template Library | Phase 4 (Deferred) | Partial | Deferred; no task breakdown or validation plan defined. |
| DC-305 Incremental Update | Phase 4 (Deferred) | Partial | Deferred; no task breakdown or validation plan defined. |
| DC-306 Smoke Test Generation | Phase 4 (Deferred) | Partial | Deferred; no task breakdown or validation plan defined. |
