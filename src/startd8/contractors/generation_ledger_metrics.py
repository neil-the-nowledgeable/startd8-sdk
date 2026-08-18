"""Export the Prime generation-ledger portfolio as Prometheus textfile metrics ($0/offline).

Mirrors ``benchmark_matrix.metrics_export``: the ledger is static JSON under
``~/.startd8/generation-ledger/``, but Grafana queries Prometheus. This bridges the gap **without a
live stack** — it writes a Prometheus **textfile exposition** (``.prom``) whose metric names + labels
match the portfolio dashboard's PromQL. Point a Prometheus *textfile collector* (or the local
docker-compose stack) at the file and the dashboard renders real numbers. Re-run it after any
``prime-ledger record`` / auto-record; scrape it periodically for the time-series panels.

Metrics:
  gen_ledger_portfolio_cost_usd            (gauge)  total LLM cost across all Prime projects
  gen_ledger_portfolio_projects            (gauge)  number of projects Prime has worked on
  gen_ledger_project_cost_usd{project}     (gauge)  cumulative LLM cost per project
  gen_ledger_project_runs{project}         (gauge)  recorded runs per project
  gen_ledger_project_features_passed{...}  (gauge)  features passed per project
  gen_ledger_run_cost_usd{project,run}     (gauge)  per-run LLM cost
  gen_ledger_run_local_ratio{project,run}  (gauge)  share of features generated $0 on Ollama/Micro Prime
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from ..logging_config import get_logger
from . import generation_ledger as gl

logger = get_logger(__name__)


def _metric(name: str, labels: Dict[str, str], value: float) -> str:
    if labels:
        lbl = ",".join(f'{k}="{v}"' for k, v in labels.items())
        return f"{name}{{{lbl}}} {value}"
    return f"{name} {value}"


def export_ledger_metrics(home: Optional[str] = None) -> str:
    """Build the Prometheus exposition text for the whole ledger portfolio (pure)."""
    index = gl.load_index(home)
    lines: List[str] = [
        "# Prime generation-ledger portfolio metrics ($0 textfile export)"
    ]

    # --- portfolio-level ---------------------------------------------------
    total_cost = sum(p.get("cumulative_cost_usd", 0.0) for p in index.projects)
    lines += [
        "# HELP gen_ledger_portfolio_cost_usd Total LLM cost across all Prime projects",
        "# TYPE gen_ledger_portfolio_cost_usd gauge",
        _metric("gen_ledger_portfolio_cost_usd", {}, round(total_cost, 6)),
        "# HELP gen_ledger_portfolio_projects Number of projects Prime has worked on",
        "# TYPE gen_ledger_portfolio_projects gauge",
        _metric("gen_ledger_portfolio_projects", {}, len(index.projects)),
    ]

    # --- per-project gauges ------------------------------------------------
    for name, help_text, key in [
        (
            "gen_ledger_project_cost_usd",
            "Cumulative LLM cost per project",
            "cumulative_cost_usd",
        ),
        ("gen_ledger_project_runs", "Recorded runs per project", "runs"),
        (
            "gen_ledger_project_features_passed",
            "Features passed per project",
            "features_passed",
        ),
    ]:
        lines += [f"# HELP {name} {help_text}", f"# TYPE {name} gauge"]
        for p in index.projects:
            val = p.get(key, 0)
            lines.append(
                _metric(
                    name,
                    {"project": p.get("project_id", "")},
                    round(val, 6) if isinstance(val, float) else val,
                )
            )

    # --- per-run gauges (the micro-prime cost-efficiency signal) -----------
    ratio_lines: List[str] = []
    cost_lines: List[str] = []
    for p in index.projects:
        ledger = gl.load_project_ledger(p.get("project_id", ""), home=home)
        for s in gl.project_trends(ledger)["runs"]:
            labels = {"project": p.get("project_id", ""), "run": s["run_id"]}
            ratio_lines.append(
                _metric(
                    "gen_ledger_run_local_ratio", labels, round(s["local_ratio"], 4)
                )
            )
            cost_lines.append(
                _metric("gen_ledger_run_cost_usd", labels, round(s["cost_usd"], 6))
            )
    lines += [
        "# HELP gen_ledger_run_local_ratio Share of features generated $0 on Ollama/Micro Prime",
        "# TYPE gen_ledger_run_local_ratio gauge",
        *ratio_lines,
        "# HELP gen_ledger_run_cost_usd Per-run LLM cost in USD",
        "# TYPE gen_ledger_run_cost_usd gauge",
        *cost_lines,
    ]
    return "\n".join(lines) + "\n"


def write_ledger_metrics(
    output_path: str, home: Optional[str] = None
) -> Dict[str, Any]:
    """Write the portfolio Prometheus textfile to *output_path* (``.prom``)."""
    text = export_ledger_metrics(home)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    n = sum(1 for ln in text.splitlines() if ln and not ln.startswith("#"))
    logger.info("Wrote %d generation-ledger metric series → %s", n, path)
    return {"path": str(path), "series": n}


def _ledger_observations(home: Optional[str]) -> Dict[str, Any]:
    """Gather the portfolio into (value, attributes) lists for the OTLP gauges (pure)."""
    index = gl.load_index(home)
    proj = index.projects
    run_ratio: List[Any] = []
    run_cost: List[Any] = []
    for p in proj:
        ledger = gl.load_project_ledger(p.get("project_id", ""), home=home)
        for s in gl.project_trends(ledger)["runs"]:
            attrs = {"project": p.get("project_id", ""), "run": s["run_id"]}
            run_ratio.append((s["local_ratio"], attrs))
            run_cost.append((s["cost_usd"], attrs))
    return {
        "portfolio_cost": sum(p.get("cumulative_cost_usd", 0.0) for p in proj),
        "portfolio_projects": len(proj),
        "project_cost": [
            (p.get("cumulative_cost_usd", 0.0), {"project": p.get("project_id", "")})
            for p in proj
        ],
        "project_runs": [
            (p.get("runs", 0), {"project": p.get("project_id", "")}) for p in proj
        ],
        "project_features": [
            (p.get("features_passed", 0), {"project": p.get("project_id", "")})
            for p in proj
        ],
        "run_ratio": run_ratio,
        "run_cost": run_cost,
    }


def push_ledger_metrics_otlp(
    home: Optional[str] = None, endpoint: str = "localhost:4317"
) -> Dict[str, Any]:
    """Push the portfolio as OTLP gauges → Alloy → Mimir (the live datasource path).

    The same metric names/labels as the textfile export, emitted as OTLP observable gauges so a live
    Grafana dashboard (Mimir datasource) renders real numbers. Endpoint defaults to the SDK's standard
    Alloy OTLP receiver (``localhost:4317``, insecure). Integration-verified against a live stack.
    """
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
        OTLPMetricExporter,
    )
    from opentelemetry.metrics import Observation
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource

    obs = _ledger_observations(home)

    def _multi(pairs):
        return lambda _options: [Observation(v, a) for v, a in pairs]

    exporter = OTLPMetricExporter(endpoint=endpoint, insecure=True)
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=60000)
    provider = MeterProvider(
        resource=Resource.create({"service.name": "startd8.generation-ledger"}),
        metric_readers=[reader],
    )
    meter = provider.get_meter("startd8.generation_ledger")
    meter.create_observable_gauge(
        "gen_ledger_portfolio_cost_usd",
        callbacks=[lambda _o: [Observation(obs["portfolio_cost"])]],
    )
    meter.create_observable_gauge(
        "gen_ledger_portfolio_projects",
        callbacks=[lambda _o: [Observation(obs["portfolio_projects"])]],
    )
    meter.create_observable_gauge(
        "gen_ledger_project_cost_usd", callbacks=[_multi(obs["project_cost"])]
    )
    meter.create_observable_gauge(
        "gen_ledger_project_runs", callbacks=[_multi(obs["project_runs"])]
    )
    meter.create_observable_gauge(
        "gen_ledger_project_features_passed",
        callbacks=[_multi(obs["project_features"])],
    )
    meter.create_observable_gauge(
        "gen_ledger_run_local_ratio", callbacks=[_multi(obs["run_ratio"])]
    )
    meter.create_observable_gauge(
        "gen_ledger_run_cost_usd", callbacks=[_multi(obs["run_cost"])]
    )

    provider.force_flush()
    provider.shutdown()
    series = 2 + len(obs["project_cost"]) * 3 + len(obs["run_ratio"]) * 2
    logger.info(
        "Pushed %d generation-ledger gauge series via OTLP → %s", series, endpoint
    )
    return {"series": series, "endpoint": endpoint}
