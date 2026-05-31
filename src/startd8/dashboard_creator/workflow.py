"""
DashboardCreatorWorkflow — WorkflowBase subclass for dashboard generation (DC-200).
"""

import json
import os
import time
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from startd8.dashboard_creator.compiler import CompilationError, compile_jsonnet_string
from startd8.dashboard_creator.config_merge import (
    hydrate_spec_defaults,
    merge_config_overrides,
    parse_config_libsonnet,
    write_config_overlay,
)
from startd8.dashboard_creator.discovery import discover_mixin, detect_toolchain
from startd8.dashboard_creator.generator import generate_dashboard_jsonnet
from startd8.dashboard_creator.json_validator import validate_dashboard_json
from startd8.dashboard_creator.layout import apply_layout
from startd8.dashboard_creator.manifest_sync import sync_manifest
from startd8.dashboard_creator.mixin_update import derive_mixin_entry, update_mixin_imports
from startd8.dashboard_creator.models import DashboardSpec, PanelType
from startd8.dashboard_creator.output import persist_dashboard
from startd8.dashboard_creator.validation import enforce_uid, validate_spec
from startd8.exceptions import ConfigurationError, ValidationError
from startd8.logging_config import get_logger
from startd8.workflows.base import WorkflowBase
from startd8.workflows.models import (
    AgentCount,
    StepResult,
    ValidationResult,
    WorkflowInput,
    WorkflowMetadata,
    WorkflowMetrics,
    WorkflowResult,
)

logger = get_logger(__name__)

_OVERLAY_FILENAME = "_dc_config_overlay.libsonnet"

# Graceful OTel import — child spans under WorkflowBase's root span (DC-205)
try:
    from opentelemetry import trace as _otel_trace

    _tracer = _otel_trace.get_tracer("startd8.dashboard_creator")
except ImportError:
    _otel_trace = None  # type: ignore[assignment]
    _tracer = None


class DashboardCreatorWorkflow(WorkflowBase):
    """Generate Grafana dashboards from declarative YAML/JSON specs."""

    @property
    def metadata(self) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_id="dashboard-create",
            name="Dashboard Creator",
            description=(
                "Generate Grafana dashboards from declarative YAML specs "
                "using startd8-mixin"
            ),
            version="0.1.0",
            capabilities=["dashboard-generation", "jsonnet", "grafana"],
            tags=["dashboards", "grafana", "monitoring", "observability"],
            requires_agents=False,
            agent_count=AgentCount.NONE,
            min_agents=0,
            inputs=[
                WorkflowInput(
                    name="spec",
                    type="string",
                    required=True,
                    description="DashboardSpec dict or path to YAML/JSON file",
                ),
                WorkflowInput(
                    name="persist_source",
                    type="boolean",
                    required=False,
                    default=False,
                    description="Write .libsonnet to mixin dir",
                ),
                WorkflowInput(
                    name="output_dir",
                    type="string",
                    required=False,
                    description="Override output directory",
                ),
                WorkflowInput(
                    name="dry_run",
                    type="boolean",
                    required=False,
                    default=False,
                    description="Generate without writing",
                ),
                WorkflowInput(
                    name="check",
                    type="boolean",
                    required=False,
                    default=False,
                    description="Validate + compile, no write",
                ),
                WorkflowInput(
                    name="provision",
                    type="boolean",
                    required=False,
                    default=False,
                    description="Push dashboard to Grafana after generation",
                ),
                WorkflowInput(
                    name="grafana_url",
                    type="string",
                    required=False,
                    description="Grafana instance URL for provisioning",
                ),
                WorkflowInput(
                    name="allow_insecure",
                    type="boolean",
                    required=False,
                    default=False,
                    description="Allow plain HTTP connections to Grafana",
                ),
                WorkflowInput(
                    name="manifest_path",
                    type="string",
                    required=False,
                    description="Path to observability-manifest.yaml for sync",
                ),
            ],
        )

    def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        """Override base validation for polymorphic 'spec' input (accepts dict, str, or DashboardSpec)."""
        errors: List[str] = []
        meta = self.metadata

        # Required-field presence check
        for inp in meta.inputs:
            if inp.required and inp.name not in config:
                errors.append(f"Missing required input: {inp.name}")

        # Type check non-spec inputs using base _TYPE_MAP
        for inp in meta.inputs:
            if inp.name == "spec" or inp.name not in config:
                continue
            val = config[inp.name]
            if val is None and not inp.required:
                continue
            expected = self._TYPE_MAP.get(inp.type)
            if expected and not isinstance(val, expected):
                errors.append(
                    f"Input '{inp.name}': expected {inp.type}, "
                    f"got {type(val).__name__}"
                )

        # Custom validation
        errors.extend(self._custom_validate(config))

        if errors:
            return ValidationResult.failure(errors)
        return ValidationResult.success()

    def _custom_validate(self, config: Dict[str, Any]) -> List[str]:
        """DC-007: Validate spec-specific constraints."""
        errors: List[str] = []

        if config.get("dry_run") and config.get("check"):
            errors.append("Cannot use both --dry-run and --check together")

        if config.get("provision"):
            if not os.environ.get("GRAFANA_API_TOKEN"):
                errors.append(
                    "Provisioning requires GRAFANA_API_TOKEN environment variable"
                )
            if not config.get("grafana_url") and not os.environ.get("GRAFANA_URL"):
                errors.append(
                    "Provisioning requires --grafana-url or GRAFANA_URL environment variable"
                )

        spec_input = config.get("spec")
        if spec_input is None:
            # Already caught by required-field check in validate_config
            return errors

        # Try to parse the spec to catch validation errors early
        try:
            self._parse_spec(spec_input)
        except (ValueError, ConfigurationError, yaml.YAMLError) as exc:
            errors.append(f"Invalid spec: {exc}")

        return errors

    def _execute(
        self,
        config: Dict[str, Any],
        agents: Optional[List[Any]],
        on_progress: Optional[Any],
    ) -> WorkflowResult:
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
        10. Provision to Grafana (DC-203) — if provision=True
        11. Return WorkflowResult with artifacts
        """
        started_at_ns = time.monotonic()
        step_results: List[StepResult] = []
        is_dry_run = config.get("dry_run", False)
        is_check = config.get("check", False)

        self._emit_progress(on_progress, 0, 10, "Parsing spec")

        # 1. Parse spec
        try:
            spec = self._parse_spec(config["spec"])
        except (ConfigurationError, ValueError, yaml.YAMLError, json.JSONDecodeError) as exc:
            return WorkflowResult.from_error(
                self.metadata.workflow_id, f"Spec parsing failed: {exc}"
            )

        # 2. Discover mixin + toolchain
        self._emit_progress(on_progress, 1, 10, "Discovering mixin")
        try:
            mixin = discover_mixin()
            toolchain = detect_toolchain()
        except ConfigurationError as exc:
            return WorkflowResult.from_error(
                self.metadata.workflow_id, str(exc)
            )

        step_results.append(StepResult(
            step_name="discover",
            output=f"Mixin: {mixin.mixin_dir}, Toolchain: {toolchain.backend} ({toolchain.version})",
        ))

        # 3. Enforce UID
        # Callers with their own uid convention (e.g. the observability artifact
        # generator, which standardizes on obs-{service} and wires that uid into
        # alert/SLO dashboard_url links) can opt out via enforce_uid=False. A None
        # uid is still auto-generated so the dashboard always has one.
        if config.get("enforce_uid", True):
            self._emit_progress(on_progress, 2, 10, "Enforcing UID")
            try:
                spec = enforce_uid(spec)
            except ValidationError as exc:
                return WorkflowResult.from_error(
                    self.metadata.workflow_id, f"UID enforcement failed: {exc}"
                )
        elif spec.uid is None:
            from startd8.dashboard_creator.validation import generate_uid_from_title
            spec = spec.model_copy(update={"uid": generate_uid_from_title(spec.title)})

        logger.info("Dashboard UID: %s", spec.uid)

        # Set root span attributes + ContextCore enrichment (DC-205, DC-207)
        self._set_root_span_attrs(spec)
        self._enrich_span_with_contextcore()

        # 4. Merge config + hydrate defaults
        self._emit_progress(on_progress, 3, 10, "Merging config")
        base_config = parse_config_libsonnet(mixin.config_path)
        if spec.config_overrides:
            try:
                merged_config = merge_config_overrides(base_config, spec.config_overrides)
            except (ValidationError, KeyError, TypeError) as exc:
                return WorkflowResult.from_error(
                    self.metadata.workflow_id, f"Config merge failed: {exc}"
                )
        else:
            merged_config = base_config

        spec = hydrate_spec_defaults(spec, merged_config)

        # 4.5 Write config overlay for the compiler (DC-005 AC3)
        config_overlay_filename = None
        if spec.config_overrides:
            try:
                overlay_path = mixin.mixin_dir / _OVERLAY_FILENAME
                write_config_overlay(merged_config, overlay_path)
                config_overlay_filename = _OVERLAY_FILENAME
            except OSError as exc:
                return WorkflowResult.from_error(
                    self.metadata.workflow_id,
                    f"Failed to write config overlay: {exc}. "
                    f"Config overrides will not take effect.",
                )

        # 5. Validate spec
        self._emit_progress(on_progress, 4, 10, "Validating spec")
        validation_errors = validate_spec(spec, merged_config)
        if validation_errors:
            return WorkflowResult.from_error(
                self.metadata.workflow_id,
                f"Spec validation failed: {'; '.join(validation_errors)}",
            )

        step_results.append(StepResult(
            step_name="validate",
            output="Spec validation passed",
        ))

        # 5.5 Apply layout (DC-108, DC-109) — group rows + auto-position
        has_groups = any(p.group is not None for p in spec.panels)
        has_missing_gridpos = any(
            p.gridPos is None and p.type != PanelType.ROW for p in spec.panels
        )
        if has_groups or has_missing_gridpos:
            spec = apply_layout(spec)
            step_results.append(StepResult(
                step_name="layout",
                output=f"Applied layout ({len(spec.panels)} panels)",
            ))

        # 6. Generate Jsonnet
        # Overlay cleanup is consolidated in a single finally block covering
        # both the dry-run early return and the compile path.
        try:
            self._emit_progress(on_progress, 5, 10, "Generating Jsonnet")
            gen_start = time.monotonic()
            with self._child_span("generate", panel_count=len(spec.panels)):
                jsonnet_source = generate_dashboard_jsonnet(
                    spec, config_overlay_filename=config_overlay_filename
                )
            gen_ms = int((time.monotonic() - gen_start) * 1000)

            step_results.append(StepResult(
                step_name="generate",
                output=f"Generated {len(jsonnet_source)} chars of Jsonnet",
                time_ms=gen_ms,
            ))

            if is_dry_run:
                self._emit_progress(on_progress, 10, 10, "Dry run complete")
                return WorkflowResult(
                    workflow_id=self.metadata.workflow_id,
                    success=True,
                    output={"jsonnet_source": jsonnet_source, "uid": spec.uid},
                    steps=step_results,
                    metrics=WorkflowMetrics(
                        total_time_ms=int((time.monotonic() - started_at_ns) * 1000),
                        step_count=len(step_results),
                    ),
                )

            # 7. Compile Jsonnet
            self._emit_progress(on_progress, 6, 10, "Compiling Jsonnet")
            with self._child_span("compile") as compile_span:
                try:
                    comp_result = compile_jsonnet_string(
                        jsonnet_source, mixin, toolchain
                    )
                    if compile_span:
                        compile_span.set_attribute("compilation.duration_ms", comp_result.duration_ms)
                        compile_span.set_attribute("compilation.backend", comp_result.backend)
                except (CompilationError, TimeoutError, OSError) as exc:
                    if compile_span and _otel_trace:
                        compile_span.set_status(_otel_trace.StatusCode.ERROR, str(exc))
                        compile_span.record_exception(exc)
                    return WorkflowResult.from_error(
                        self.metadata.workflow_id, f"Compilation failed: {exc}"
                    )
        finally:
            # Clean up temp config overlay (DC-005 AC3)
            if config_overlay_filename:
                (mixin.mixin_dir / config_overlay_filename).unlink(missing_ok=True)

        step_results.append(StepResult(
            step_name="compile",
            output=f"Compiled in {comp_result.duration_ms}ms ({comp_result.backend})",
            time_ms=comp_result.duration_ms,
        ))

        # 8. Validate JSON
        self._emit_progress(on_progress, 7, 10, "Validating JSON")
        expected_panel_count = sum(
            1 for p in spec.panels if p.type != PanelType.ROW
        )
        json_result = validate_dashboard_json(
            comp_result.json_str, spec.uid, expected_panel_count
        )
        if not json_result.valid:
            return WorkflowResult.from_error(
                self.metadata.workflow_id,
                f"JSON validation failed: {'; '.join(json_result.errors)}",
            )

        for warning in json_result.warnings:
            logger.warning("JSON validation warning: %s", warning)

        step_results.append(StepResult(
            step_name="validate_json",
            output="JSON validation passed",
        ))

        if is_check:
            self._emit_progress(on_progress, 10, 10, "Check complete")
            return WorkflowResult(
                workflow_id=self.metadata.workflow_id,
                success=True,
                output={"uid": spec.uid, "check": "passed"},
                steps=step_results,
                metrics=WorkflowMetrics(
                    total_time_ms=int((time.monotonic() - started_at_ns) * 1000),
                    step_count=len(step_results),
                ),
            )

        # 9. Persist output
        self._emit_progress(on_progress, 8, 10, "Writing output")
        output_dir = Path(config["output_dir"]) if config.get("output_dir") else None
        persist_source = config.get("persist_source", False)

        with self._child_span("persist"):
            persist_result = persist_dashboard(
                dashboard_json=json_result.dashboard_json,
                uid=spec.uid,
                output_dir=output_dir,
                libsonnet_source=jsonnet_source if persist_source else None,
                libsonnet_dir=mixin.dashboards_dir if persist_source else None,
            )

        step_results.append(StepResult(
            step_name="persist",
            output=f"Written to {persist_result.json_path}",
        ))

        # 9.5 Manifest sync (DC-201) — non-fatal
        manifest_path_str = config.get("manifest_path")
        if manifest_path_str:
            try:
                manifest_path = Path(manifest_path_str)
                synced = sync_manifest(spec, persist_result.json_path, manifest_path)
                if synced:
                    step_results.append(StepResult(
                        step_name="manifest_sync",
                        output=f"Synced to {manifest_path}",
                    ))
            except Exception as exc:
                logger.warning("Manifest sync failed (non-fatal): %s", exc)

        # 9.6 Mixin auto-update (DC-204) — non-fatal, only when persist_source=True
        if persist_source and mixin.mixin_libsonnet:
            try:
                json_fn, libsonnet_rel = derive_mixin_entry(spec.uid or "")
                updated = update_mixin_imports(
                    mixin.mixin_libsonnet, json_fn, libsonnet_rel
                )
                if updated:
                    step_results.append(StepResult(
                        step_name="mixin_update",
                        output=f"Added {json_fn} to mixin.libsonnet",
                    ))
            except Exception as exc:
                logger.warning("Mixin update failed (non-fatal): %s", exc)

        # 10. Provision to Grafana (DC-203)
        dashboard_url = None
        should_provision = config.get("provision", False) and not is_dry_run and not is_check
        if should_provision:
            self._emit_progress(on_progress, 9, 11, "Provisioning to Grafana")
            with self._child_span("provision") as prov_span:
                try:
                    from startd8.dashboard_creator.grafana_client import GrafanaClient
                    from startd8.dashboard_creator.provisioning import provision_dashboard

                    grafana_url = config.get("grafana_url") or os.environ.get("GRAFANA_URL", "")
                    allow_insecure = config.get("allow_insecure", False)
                    client = GrafanaClient(grafana_url, allow_insecure=allow_insecure)
                    prov_result = provision_dashboard(json_result.dashboard_json, client)

                    if prov_result.success:
                        dashboard_url = prov_result.dashboard_url
                        step_results.append(StepResult(
                            step_name="provision",
                            output=f"Provisioned: {dashboard_url}",
                        ))
                    else:
                        logger.warning("Provisioning failed: %s", prov_result.error)
                        if prov_span and _otel_trace:
                            prov_span.set_status(
                                _otel_trace.StatusCode.ERROR,
                                prov_result.error or "unknown",
                            )
                        step_results.append(StepResult(
                            step_name="provision",
                            output=f"Provisioning failed: {prov_result.error}",
                        ))
                except Exception as exc:
                    logger.warning("Provisioning error: %s", exc, exc_info=True)
                    if prov_span and _otel_trace:
                        prov_span.set_status(_otel_trace.StatusCode.ERROR, str(exc))
                        prov_span.record_exception(exc)
                    step_results.append(StepResult(
                        step_name="provision",
                        output=f"Provisioning error: {exc}",
                    ))

        self._emit_progress(on_progress, 11, 11, "Complete")

        panel_count = sum(1 for p in spec.panels if p.type != PanelType.ROW)
        total_ms = int((time.monotonic() - started_at_ns) * 1000)
        return WorkflowResult(
            workflow_id=self.metadata.workflow_id,
            success=True,
            output={
                "uid": spec.uid,
                "json_path": str(persist_result.json_path),
                "libsonnet_path": (
                    str(persist_result.libsonnet_path)
                    if persist_result.libsonnet_path
                    else None
                ),
                "jsonnet_source": jsonnet_source,
                "dashboard_url": dashboard_url,
                "panel_count": panel_count,
            },
            steps=step_results,
            metrics=WorkflowMetrics(
                total_time_ms=total_ms,
                step_count=len(step_results),
            ),
        )

    def _parse_spec(self, spec_input: Any) -> DashboardSpec:
        """Parse spec from dict, YAML/JSON file path, markdown requirements, or string."""
        if isinstance(spec_input, dict):
            return DashboardSpec(**spec_input)

        if isinstance(spec_input, DashboardSpec):
            return spec_input

        # Treat as file path
        path = Path(str(spec_input))
        if path.is_file():
            if path.suffix == ".md":
                from startd8.dashboard_creator.requirements_parser import parse_requirements
                return parse_requirements(path)  # may raise ConfigurationError
            content = path.read_text(encoding="utf-8")
            if path.suffix in {".yaml", ".yml"}:
                data = yaml.safe_load(content)
            else:
                data = json.loads(content)
            return DashboardSpec(**data)

        # Try as YAML string
        try:
            data = yaml.safe_load(str(spec_input))
            if isinstance(data, dict):
                return DashboardSpec(**data)
        except yaml.YAMLError:
            pass

        raise ConfigurationError(
            f"Cannot parse spec: expected a dict, file path, or YAML string, "
            f"got {type(spec_input).__name__}"
        )

    def _child_span(self, name: str, **attrs: Any):
        """Create a child span under the current OTel context (DC-205).

        Returns a context manager yielding the span, or ``nullcontext(None)``
        when OTel is not installed.  Callers **must** guard span method calls
        with ``if span:`` since the yielded value is ``None`` without OTel.
        """
        if not _tracer:
            return nullcontext(None)
        return _tracer.start_as_current_span(
            f"dashboard_creator.{name}",
            attributes={f"dashboard_creator.{k}": v for k, v in attrs.items()},
        )

    def _set_root_span_attrs(self, spec: DashboardSpec) -> None:
        """Set dashboard-specific attributes on the current root span (DC-205)."""
        if not _otel_trace:
            return
        span = _otel_trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute("dashboard.uid", spec.uid or "")
            span.set_attribute("dashboard.title", spec.title)
            span.set_attribute("dashboard.panel_count", len(spec.panels))

    @staticmethod
    def _load_contextcore_context() -> Optional[Dict[str, str]]:
        """DC-207: Load project context from ``.contextcore.yaml``.

        Walks up to 3 parent directories from CWD looking for the file.
        Returns a dict with ``project.id`` and ``project.name`` keys,
        or None if the file is absent or malformed.
        """
        search = Path.cwd()
        for _ in range(4):  # cwd + 3 parents
            candidate = search / ".contextcore.yaml"
            if candidate.is_file():
                try:
                    data = yaml.safe_load(candidate.read_text(encoding="utf-8"))
                    if not isinstance(data, dict):
                        return None
                    spec_block = data.get("spec", {})
                    project = spec_block.get("project", {})
                    pid = project.get("id")
                    pname = project.get("name")
                    if pid or pname:
                        ctx: Dict[str, str] = {}
                        if pid:
                            ctx["project.id"] = str(pid)
                        if pname:
                            ctx["project.name"] = str(pname)
                        return ctx
                except Exception:
                    logger.debug("Failed to parse %s", candidate, exc_info=True)
                return None
            parent = search.parent
            if parent == search:
                break
            search = parent
        return None

    def _enrich_span_with_contextcore(self) -> None:
        """DC-207: Set ContextCore attributes on the current span."""
        if not _otel_trace:
            return
        ctx = self._load_contextcore_context()
        if not ctx:
            return
        span = _otel_trace.get_current_span()
        if span and span.is_recording():
            for key, value in ctx.items():
                span.set_attribute(f"io.contextcore.{key}", value)

    def _emit_progress(self, on_progress, current, total, message):
        """Safely emit progress callback."""
        if on_progress:
            try:
                on_progress(current, total, message)
            except Exception:
                logger.debug("Progress callback error at step %d/%d", current, total, exc_info=True)
