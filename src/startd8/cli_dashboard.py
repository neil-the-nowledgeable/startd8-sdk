# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""dashboard CLI command group (extracted from cli.py, Pass E)."""

from .exceptions import ConfigurationError
from typing import Optional, List
from pathlib import Path
import os
import typer
from .cli_shared import console


dashboard_app = typer.Typer(
    name="dashboard",
    help="Dashboard management commands"
)


_DASHBOARD_TEMPLATE = """\
# Dashboard spec template — see docs/design/dashboard-creator/ for full reference
title: "My Dashboard"
description: "What this dashboard monitors"
tags:
  - startd8
  - observability
panels:
  - type: stat
    title: "Request Rate"
    expr: 'rate(http_requests_total{job="my-service"}[5m])'
    unit: reqps
  - type: timeseries
    title: "Latency"
    targets:
      - expr: 'histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))'
        legendFormat: "p99"
      - expr: 'histogram_quantile(0.50, rate(http_request_duration_seconds_bucket[5m]))'
        legendFormat: "p50"
    unit: s
variables:
  - type: prometheusDatasource
    name: datasource
    label: "Data Source"
"""


def _print_dashboard_template() -> None:
    """Print a YAML dashboard spec skeleton to stdout."""
    console.print(_DASHBOARD_TEMPLATE)


@dashboard_app.command("create")
def dashboard_create(
    spec_file: Optional[Path] = typer.Argument(
        None, help="Path to dashboard spec YAML/JSON file"
    ),
    provision: bool = typer.Option(
        False, "--provision", help="Push dashboard to Grafana after generation"
    ),
    grafana_url: Optional[str] = typer.Option(
        None, "--grafana-url", help="Grafana instance URL"
    ),
    allow_insecure: bool = typer.Option(
        False, "--allow-insecure", help="Allow plain HTTP connections to Grafana"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Generate Jsonnet without writing files"
    ),
    check: bool = typer.Option(
        False, "--check", help="Validate and compile only, no write"
    ),
    persist_source: bool = typer.Option(
        False, "--persist-source", help="Write .libsonnet to mixin dir"
    ),
    output_dir: Optional[Path] = typer.Option(
        None, "--output-dir", help="Override output directory"
    ),
    config: Optional[Path] = typer.Option(
        None, "--config", help="Path to config overrides YAML"
    ),
    print_template: bool = typer.Option(
        False, "--print-template", help="Print a YAML spec template and exit"
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Verbose output"),
):
    """Generate a Grafana dashboard from a declarative YAML/JSON spec.

    Examples:

        startd8 dashboard create my-spec.yaml

        startd8 dashboard create my-spec.yaml --provision --grafana-url https://grafana.local

        startd8 dashboard create --print-template > my-spec.yaml
    """
    if print_template:
        _print_dashboard_template()
        return

    if spec_file is None:
        console.print(
            "[red]Error: SPEC_FILE argument is required.[/red]\n"
            "Usage: startd8 dashboard create [OPTIONS] SPEC_FILE\n"
            "       startd8 dashboard create --print-template"
        )
        raise typer.Exit(1)

    if not spec_file.is_file():
        console.print(f"[red]Error: spec file not found: {spec_file}[/red]")
        raise typer.Exit(1)

    # Lazy import to avoid circular / heavy imports at CLI startup
    from .dashboard_creator.workflow import DashboardCreatorWorkflow

    workflow = DashboardCreatorWorkflow()

    wf_config: dict = {
        "spec": str(spec_file),
        "dry_run": dry_run,
        "check": check,
        "persist_source": persist_source,
    }
    if output_dir:
        wf_config["output_dir"] = str(output_dir)
    if provision:
        wf_config["provision"] = True
    if grafana_url:
        wf_config["grafana_url"] = grafana_url
    elif os.environ.get("GRAFANA_URL"):
        wf_config["grafana_url"] = os.environ["GRAFANA_URL"]
    if allow_insecure:
        wf_config["allow_insecure"] = True

    if verbose:
        def _on_progress(current, total, message):
            console.print(f"  [{current}/{total}] {message}")
    else:
        _on_progress = None

    result = workflow.run(wf_config, on_progress=_on_progress)

    if not result.success:
        console.print(f"[red]Dashboard creation failed: {result.error}[/red]")
        raise typer.Exit(1)

    output = result.output or {}
    uid = output.get("uid", "unknown")
    panel_count = output.get("panel_count")

    if dry_run:
        console.print(f"[green]Dry run complete — UID: {uid}[/green]")
    elif check:
        console.print(f"[green]Check passed — UID: {uid}[/green]")
    else:
        json_path = output.get("json_path", "")
        console.print(f"[green]Dashboard created — UID: {uid}[/green]")
        if json_path:
            console.print(f"  Output: {json_path}")
        if panel_count is not None:
            console.print(f"  Panels: {panel_count}")

    dashboard_url = output.get("dashboard_url")
    if dashboard_url:
        console.print(f"  URL: [link={dashboard_url}]{dashboard_url}[/link]")


@dashboard_app.command("from-requirements")
def dashboard_from_requirements(
    path: Path = typer.Argument(..., help="Path to requirements markdown file"),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output YAML file path"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print YAML to stdout without writing"
    ),
    no_uid_transform: bool = typer.Option(
        False, "--no-uid-transform", help="Keep original UID without cc-govbudget- prefix"
    ),
):
    """Parse a requirements markdown document into a DashboardSpec YAML.

    Examples:

        startd8 dashboard from-requirements design/intro-requirements.md --dry-run

        startd8 dashboard from-requirements design/intro-requirements.md -o dashboards/intro.spec.yaml
    """
    if not path.is_file():
        console.print(f"[red]Error: file not found: {path}[/red]")
        raise typer.Exit(1)

    from .dashboard_creator.requirements_parser import (
        parse_requirements,
        _spec_to_dict,
    )

    spec = parse_requirements(path)

    if no_uid_transform and spec.uid:
        # Restore original UID from the requirements doc header
        import re as _re

        header_text = path.read_text(encoding="utf-8")
        uid_m = _re.search(r"\*\*Dashboard UID\*\*:\s*`([^`]+)`", header_text)
        if uid_m:
            spec = spec.model_copy(update={"uid": uid_m.group(1).strip()})

    import yaml as _yaml

    data = _spec_to_dict(spec)
    yaml_str = _yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)

    panel_count = len(spec.panels)
    var_count = len(spec.variables)

    if dry_run:
        console.print(yaml_str)
        console.print(
            f"\n[green]Parsed: {panel_count} panels, {var_count} variables "
            f"— UID: {spec.uid}[/green]"
        )
        return

    out_path = output or path.with_suffix(".spec.yaml")
    out_path.write_text(yaml_str, encoding="utf-8")
    console.print(
        f"[green]Wrote {out_path} — {panel_count} panels, {var_count} variables "
        f"— UID: {spec.uid}[/green]"
    )


@dashboard_app.command("delete")
def dashboard_delete(
    uid: str = typer.Argument(..., help="Dashboard UID to delete"),
    grafana_url: Optional[str] = typer.Option(
        None, "--grafana-url", help="Grafana instance URL"
    ),
    allow_insecure: bool = typer.Option(
        False, "--allow-insecure", help="Allow plain HTTP connections"
    ),
    remove_source: bool = typer.Option(
        False, "--remove-source", help="Also delete .libsonnet source file"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Delete a dashboard from Grafana and/or local files.

    Examples:

        startd8 dashboard delete cc-startd8-my-dashboard

        startd8 dashboard delete cc-startd8-my-dashboard --grafana-url https://grafana.local --yes
    """
    if not yes:
        confirm = typer.confirm(f"Delete dashboard '{uid}'?")
        if not confirm:
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    # Best-effort Grafana deletion
    if grafana_url:
        try:
            from .dashboard_creator.grafana_client import GrafanaClient
            from .dashboard_creator.provisioning import deprovision_dashboard

            client = GrafanaClient(grafana_url, allow_insecure=allow_insecure)
            result = deprovision_dashboard(uid, client)
            if result.success:
                console.print(f"[green]Deleted from Grafana: {uid}[/green]")
            else:
                console.print(
                    f"[yellow]Warning: Grafana deletion failed: {result.error}[/yellow]"
                )
        except (ConfigurationError, OSError) as exc:
            console.print(
                f"[yellow]Warning: Could not connect to Grafana: {exc}[/yellow]"
            )

    # Local cleanup always proceeds
    from .dashboard_creator.provisioning import delete_local_artifacts

    artifacts = delete_local_artifacts(uid, remove_source=remove_source)

    deleted_items = [name for name, ok in artifacts.items() if ok]
    if deleted_items:
        console.print(f"[green]Deleted local artifacts: {', '.join(deleted_items)}[/green]")
    else:
        console.print("[dim]No local artifacts found to delete.[/dim]")
