# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""``startd8 observability`` — live-validation harness CLI (FR-8a).

Single canonical entrypoint for the live-replay fidelity harness
(REQ_TARGET_METRIC_BINDING.md Group C). ContextCore CI invokes
``startd8 observability validate-promql`` — no second repo checkout. Lives
inside the ``observability`` package (co-located with the generator and the
``prometheus_query`` primitive) and is wired into the top-level app in
``startd8/cli.py`` via ``app.add_typer(observability_app, name="observability")``.

Credentials (FR-8b) come ONLY from the environment (``PROMETHEUS_BEARER_TOKEN``,
``PROMETHEUS_ORG_ID`` / ``X_SCOPE_ORGID``) — never a CLI flag or manifest — and
are redacted from all output.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from .metric_descriptor import match_profiles, profile_signatures
from .prometheus_query import Auth, list_metric_names
from .validate_promql import redact, run_validation

observability_app = typer.Typer(
    help="Observability harnesses (live PromQL fidelity validation, FR-8..10)."
)


@observability_app.callback()
def _observability_callback() -> None:
    """Presence of a callback keeps this a command *group*."""


@observability_app.command("validate-promql")
def validate_promql(
    artifacts_dir: Path = typer.Option(
        ...,
        "--artifacts-dir",
        help="Generated observability output (alerts/ slos/ dashboards/).",
    ),
    onboarding_metadata: Path = typer.Option(
        ...,
        "--onboarding-metadata",
        help="ContextCore onboarding-metadata.json (per-service convention_profile "
        "+ transport). Expected identity is reconstructed from this, NOT re-parsed "
        "from PromQL (FR-8/Mottainai).",
    ),
    prometheus: str = typer.Option(
        "http://localhost:9090",
        "--prometheus",
        help="Prometheus base URL (read-only /api/v1/query).",
    ),
    min_coverage: float = typer.Option(
        1.0,
        "--min-coverage",
        help="Minimum fraction of expressions that must return live data (FR-10).",
    ),
    allow_prod: bool = typer.Option(
        False,
        "--allow-prod",
        help="Opt in to a non-demo/non-localhost backend (FR-8c). Default refuses.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print the query count / estimated series and exit without querying (FR-8c).",
    ),
    report: Path = typer.Option(
        None,
        "--report",
        help="Write the JSON fidelity report here (default: stdout).",
    ),
) -> None:
    """Replay every generated PromQL against a live Prometheus and gate on fidelity.

    Exit codes (FR-10): 0 pass · 2 fail-below-coverage · 3 unknown (zero queries
    replayed or backend unreachable — never conflated with pass).

    Credentials are read from the environment only (FR-8b) and redacted here.
    """
    auth = Auth.from_env()
    result = run_validation(
        artifacts_dir=artifacts_dir,
        onboarding_metadata=onboarding_metadata,
        prometheus_url=prometheus,
        min_coverage=min_coverage,
        allow_prod=allow_prod,
        dry_run=dry_run,
        auth=auth,
    )

    payload = json.dumps(result.to_dict(), indent=2)
    payload = redact(payload, auth.redactions())  # FR-8b: never leak secrets.

    if report is not None:
        Path(report).write_text(payload + "\n")
        typer.echo(f"fidelity report written to {report} (status={result.status})")
    else:
        typer.echo(payload)

    raise typer.Exit(code=result.exit_code())


@observability_app.command("detect-profile")
def detect_profile(
    prometheus: str = typer.Option(
        "http://localhost:9090",
        "--prometheus",
        help="Prometheus base URL (read-only /api/v1/label/__name__/values).",
    ),
    report: Path = typer.Option(
        None,
        "--report",
        help="Write the JSON detection result here (default: stdout).",
    ),
) -> None:
    """Read a live backend's metric names and report which ``metricsProfile`` it matches.

    A scoped, read-only authoring aid (quick-win #2): it inspects the running
    Prometheus so you don't have to guess which convention your target emits, then
    prints the ``metricsProfile`` to set in the manifest. It touches only
    ``/api/v1/label/__name__/values`` and never influences generation — no
    determinism risk.

    Exit codes mirror the harness: ``0`` a profile matches · ``2`` metrics exist but
    no built-in profile matches (declare a per-axis ``metrics`` override) · ``3``
    the backend was unreachable or exposes no metrics (fail-loud, never a silent
    empty match). Credentials come from the environment only (FR-8b) and are redacted.
    """
    auth = Auth.from_env()
    try:
        live_names = list_metric_names(prometheus, auth=auth)
    except Exception as exc:  # unreachable backend ⇒ distinct non-pass (FR-10 parity)
        msg = redact(f"backend unreachable at {prometheus}: {exc}", auth.redactions())
        typer.echo(json.dumps({"status": "unknown", "reason": msg}, indent=2))
        raise typer.Exit(code=3)

    matched = match_profiles(live_names)
    signatures = profile_signatures()
    live_set = set(live_names)
    # Per-profile signature presence — shows *why* a profile did/didn't match.
    profile_detail = {
        name: {
            "throughput_metric": {"name": thru, "present": thru in live_set},
            "latency_bucket_metric": {"name": bucket, "present": bucket in live_set},
            "matches": name in matched,
        }
        for name, (thru, bucket) in signatures.items()
    }

    if not live_names:
        status, reason, code = (
            "unknown",
            "backend exposes zero metric names — nothing to match against",
            3,
        )
    elif matched:
        status, reason, code = (
            "matched",
            f"live backend matches metricsProfile {matched[0]!r}",
            0,
        )
    else:
        status, reason, code = (
            "no-match",
            "metrics exist but no built-in profile's signature is fully present — "
            "declare a per-axis `spec.targets[].metrics` override",
            2,
        )

    payload = {
        "status": status,
        "reason": reason,
        "prometheus": prometheus,
        "metric_name_count": len(live_names),
        "suggested_metrics_profile": matched[0] if matched else "",
        "matched_profiles": matched,
        "profiles": profile_detail,
    }
    out = redact(json.dumps(payload, indent=2), auth.redactions())

    if report is not None:
        Path(report).write_text(out + "\n")
        typer.echo(f"detection result written to {report} (status={status})")
    else:
        typer.echo(out)

    raise typer.Exit(code=code)
