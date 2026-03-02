"""
DashboardCreatorWorkflow — WorkflowBase subclass for dashboard generation (DC-200).
"""

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from startd8.dashboard_creator.compiler import CompilationError, compile_jsonnet_string
from startd8.dashboard_creator.config_merge import (
    hydrate_spec_defaults,
    merge_config_overrides,
    parse_config_libsonnet,
)
from startd8.dashboard_creator.discovery import discover_mixin, detect_toolchain
from startd8.dashboard_creator.generator import generate_dashboard_jsonnet
from startd8.dashboard_creator.json_validator import validate_dashboard_json
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
            if not config.get("grafana_url"):
                errors.append(
                    "Provisioning requires --grafana-url"
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
        self._emit_progress(on_progress, 2, 10, "Enforcing UID")
        try:
            spec = enforce_uid(spec)
        except ValidationError as exc:
            return WorkflowResult.from_error(
                self.metadata.workflow_id, f"UID enforcement failed: {exc}"
            )

        logger.info("Dashboard UID: %s", spec.uid)

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

        # 6. Generate Jsonnet
        self._emit_progress(on_progress, 5, 10, "Generating Jsonnet")
        gen_start = time.monotonic()
        jsonnet_source = generate_dashboard_jsonnet(spec)
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
        try:
            comp_result = compile_jsonnet_string(
                jsonnet_source, mixin, toolchain
            )
        except (CompilationError, TimeoutError, OSError) as exc:
            return WorkflowResult.from_error(
                self.metadata.workflow_id, f"Compilation failed: {exc}"
            )

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

        # 10. Provision to Grafana (DC-203)
        dashboard_url = None
        should_provision = config.get("provision", False) and not is_dry_run and not is_check
        if should_provision:
            self._emit_progress(on_progress, 9, 11, "Provisioning to Grafana")
            try:
                from startd8.dashboard_creator.grafana_client import GrafanaClient
                from startd8.dashboard_creator.provisioning import provision_dashboard

                grafana_url = config.get("grafana_url", "")
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
                    step_results.append(StepResult(
                        step_name="provision",
                        output=f"Provisioning failed: {prov_result.error}",
                    ))
            except (ConfigurationError, OSError) as exc:
                logger.warning("Provisioning error: %s", exc)
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
        """Parse spec from dict, YAML/JSON file path, or string."""
        if isinstance(spec_input, dict):
            return DashboardSpec(**spec_input)

        if isinstance(spec_input, DashboardSpec):
            return spec_input

        # Treat as file path
        path = Path(str(spec_input))
        if path.is_file():
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

    def _emit_progress(self, on_progress, current, total, message):
        """Safely emit progress callback."""
        if on_progress:
            try:
                on_progress(current, total, message)
            except Exception:
                logger.debug("Progress callback error at step %d/%d", current, total, exc_info=True)
