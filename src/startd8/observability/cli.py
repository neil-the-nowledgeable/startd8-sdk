# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

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
from typing import Optional

import typer

from .bind_and_verify import bind_and_verify
from .contrast import build_contrast, render_markdown
from .fidelity_scorecard import build_fidelity_scorecard
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
        help="Minimum binding_coverage (pass + bound_no_data) / replayed (FR-2/FR-10).",
    ),
    bind_window: str = typer.Option(
        "1h",
        "--bind-window",
        help="Wider range window used to re-probe an empty query before calling it a "
        "binding failure — tolerates stale-but-present data (FR-3).",
    ),
    exclude_kinds: str = typer.Option(
        "",
        "--exclude-kinds",
        help="Comma list of artifact kinds to exclude from replay (alert|slo|dashboard). "
        "Excluded queries are reported, not counted against binding_coverage (A1).",
    ),
    exclude_services: str = typer.Option(
        "",
        "--exclude-services",
        help="Comma list of services to exclude — for services intentionally not deployed "
        "to this backend (see the report's target_drift). Excluded, not counted as fail.",
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
        bind_window=bind_window,
        exclude_kinds={k.strip() for k in exclude_kinds.split(",") if k.strip()}
        or None,
        exclude_services={s.strip() for s in exclude_services.split(",") if s.strip()}
        or None,
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


@observability_app.command("bind-and-verify")
def bind_and_verify_cmd(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        "-m",
        help="ContextCore manifest (.contextcore.yaml) to export + generate from.",
    ),
    output: Path = typer.Option(
        ...,
        "--output",
        "-o",
        help="Output dir for export + generated artifacts (+ observability/ subdir).",
    ),
    prometheus: str = typer.Option(
        "http://localhost:9090",
        "--prometheus",
        help="Prometheus base URL (read for detection + replayed for verification).",
    ),
    freeze: bool = typer.Option(
        False,
        "--freeze",
        help="Persist the detected metricsProfile into the manifest (capture-then-"
        "freeze). Default: use it for this run only, mutating nothing on disk.",
    ),
    min_coverage: float = typer.Option(
        1.0,
        "--min-coverage",
        help="Minimum fraction of generated queries that must return live data.",
    ),
    allow_prod: bool = typer.Option(
        False,
        "--allow-prod",
        help="Opt in to a non-demo/non-localhost backend (passed to verify).",
    ),
    export_cmd: str = typer.Option(
        "contextcore manifest export --no-strict-quality",
        "--export-cmd",
        help="Command that runs ContextCore export (override if not on PATH). The "
        "default skips the strict-quality gate, which requires --task-mapping.",
    ),
    report: Path = typer.Option(
        None,
        "--report",
        help="Write the JSON bind-and-verify report here (default: stdout).",
    ),
) -> None:
    """Detect → reconcile → bind → export+generate → verify, in one command.

    Reads the live backend to detect the ``metricsProfile``, reconciles it against
    the manifest (an authored profile wins; detection cross-checks), binds it via
    capture-then-freeze, exports + generates the artifacts, then replays every
    generated query against the live backend and reports fidelity + the exact fix.

    Exit codes mirror the harness: 0 pass · 2 fidelity fail · 3 unknown (unreachable
    backend, export/generate failure, or zero queries replayed). Credentials come
    from the environment only and are redacted.
    """
    auth = Auth.from_env()
    result = bind_and_verify(
        manifest_path=manifest,
        prometheus_url=prometheus,
        output_dir=output,
        freeze=freeze,
        min_coverage=min_coverage,
        allow_prod=allow_prod,
        auth=auth,
        export_cmd=export_cmd.split(),
    )

    payload = redact(json.dumps(result.to_dict(), indent=2), auth.redactions())
    if report is not None:
        Path(report).write_text(payload + "\n")
        typer.echo(
            f"bind-and-verify report written to {report} (status={result.status})"
        )
    else:
        typer.echo(payload)

    raise typer.Exit(code=result.exit_code())


@observability_app.command("contrast")
def contrast_cmd(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        "-m",
        help="ContextCore manifest — generated ungoverned (bindings stripped) and governed.",
    ),
    output: Path = typer.Option(
        ...,
        "--output",
        "-o",
        help="Output dir (holds ungoverned/ + governed/ + before-after-contrast.md).",
    ),
    prometheus: str = typer.Option(
        "http://localhost:9090",
        "--prometheus",
        help="Prometheus base URL both variants are replayed against.",
    ),
    min_coverage: float = typer.Option(
        0.9,
        "--min-coverage",
        help="binding_coverage floor for each variant's gate status.",
    ),
    allow_prod: bool = typer.Option(
        False,
        "--allow-prod",
        help="Opt in to a non-demo/non-localhost backend.",
    ),
    export_cmd: str = typer.Option(
        "contextcore manifest export --no-strict-quality",
        "--export-cmd",
        help="Command that runs ContextCore export (override if not on PATH).",
    ),
) -> None:
    """Generate + replay the manifest two ways and write a before/after contrast artifact.

    Ungoverned = the manifest with its `metricsProfile` / `datasources` stripped (naive
    semconv defaults, unbound datasource). Governed = the manifest as authored. Both are
    replayed against the live backend, so the contrast is grounded in fidelity numbers.
    Writes `before-after-contrast.md` (+ the JSON report) to the output dir.
    """
    report = build_contrast(
        manifest_path=manifest,
        prometheus_url=prometheus,
        output_dir=output,
        min_coverage=min_coverage,
        allow_prod=allow_prod,
        auth=Auth.from_env(),
        export_cmd=export_cmd.split(),
    )
    md = render_markdown(report)
    md_path = Path(output) / "before-after-contrast.md"
    md_path.write_text(md + "\n")
    json_path = Path(output) / "before-after-contrast.json"
    json_path.write_text(json.dumps(report.to_dict(), indent=2) + "\n")
    typer.echo(
        f"contrast written to {md_path} "
        f"(ungoverned binds {report.ungoverned.binding_coverage:.0%} → "
        f"governed {report.governed.binding_coverage:.0%})"
    )


@observability_app.command("scorecard")
def scorecard_cmd(
    report: Path = typer.Option(
        ...,
        "--report",
        "-r",
        help="fidelity-report.json (from `validate-promql --report`) to render.",
    ),
    output: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Write the markdown scorecard here (default: stdout).",
    ),
) -> None:
    """Render a persisted fidelity report as an inverted-pyramid markdown scorecard (A2).

    Decoupled from running the harness, so a CI job can attach the scorecard as a build
    artifact next to the JSON report.
    """
    data = json.loads(Path(report).read_text())
    md = build_fidelity_scorecard(data)
    if output is not None:
        Path(output).write_text(md)
        typer.echo(f"scorecard written to {output} (status={data.get('status')})")
    else:
        typer.echo(md)


@observability_app.command("compare")
def compare_cmd(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        "-m",
        help="A generated observability-manifest.yaml (its fr_coverage block is read).",
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit the report as JSON."),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Exit 2 when any divergence class is non-empty (for a CI gate).",
    ),
) -> None:
    """Tier-A derived-vs-declared observability comparison — $0, offline.

    Reports where the generated artifacts can't be grounded against the subject's declared
    instrumentation surface (the manifest's ``fr_coverage``: suppressed / unverified base SLIs,
    unfulfilled FRs, ungrounded kinds, empty services). The live twin — replay the queries
    against real telemetry — is ``startd8 observability validate-promql``.

    Exit: 0 (advisory) · 2 (``--strict`` and divergence present).
    See docs/design/OBSERVABILITY_DERIVED_VS_EMITTED_COMPARISON.md.
    """
    from .compare import build_comparison_report, read_fr_coverage, render_report

    report = build_comparison_report(read_fr_coverage(manifest))
    typer.echo(
        json.dumps(report.to_dict(), indent=2) if as_json else render_report(report)
    )
    if strict and report.total_gaps:
        raise typer.Exit(code=2)


@observability_app.command("compare-live")
def compare_live_cmd(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        "-m",
        help="A generated observability-manifest.yaml (its fr_coverage block = Tier A).",
    ),
    artifacts_dir: Path = typer.Option(
        None,
        "--artifacts-dir",
        help="Generated observability output dir (the PromQL replayed for Tier B).",
    ),
    onboarding_metadata: Path = typer.Option(
        None,
        "--onboarding-metadata",
        help="ContextCore onboarding-metadata.json (reconstructs expected metric identity).",
    ),
    subject_image: str = typer.Option(
        None,
        "--subject-image",
        help="Single subject image to stand up + scrape (v1). Omit when using --prometheus.",
    ),
    subject_port: int = typer.Option(
        8080, "--subject-port", help="Subject /metrics port."
    ),
    metrics_path: str = typer.Option(
        "/metrics",
        "--metrics-path",
        help="Subject metrics path (e.g. /actuator/prometheus for Spring subjects).",
    ),
    prometheus: str = typer.Option(
        None,
        "--prometheus",
        help="Replay against an EXISTING backend instead of standing a subject up "
        "(the multi-container / Mastodon path).",
    ),
    min_coverage: float = typer.Option(
        1.0, "--min-coverage", help="Fidelity threshold."
    ),
    allow_prod: bool = typer.Option(
        False,
        "--allow-prod",
        help="Permit a non-loopback --prometheus backend (FR-8c). No-op on the "
        "--subject-image standup path (Prometheus is always loopback there).",
    ),
    keep_up: bool = typer.Option(
        False, "--keep-up", help="Skip teardown (debug); prints the docker rm commands."
    ),
    strict_tier_a: bool = typer.Option(
        False,
        "--strict-tier-a",
        help="Let Tier-A static gaps contribute a fail (default advisory).",
    ),
    baseline: Path = typer.Option(
        None,
        "--baseline",
        help="Accepted-fail baseline JSON; exit 2 only on a NEW fail (CI gate).",
    ),
    write_baseline: bool = typer.Option(
        False,
        "--write-baseline",
        help="Write current fail identities to --baseline (explicit re-baseline; never automatic).",
    ),
    as_json: bool = typer.Option(
        False, "--json", help="Emit the merged report as JSON."
    ),
    apply_profile_fix: bool = typer.Option(
        False, "--apply-profile-fix",
        help="Write the diagnosed metricsProfile fix into --manifest (explicit; regenerate after).",
    ),
) -> None:
    """Tier-B live derived-vs-emitted comparison — merges live fidelity with Tier-A gaps.

    Stands up ``--subject-image`` + Prometheus (or replays against ``--prometheus``), waits for a
    real scrape, replays the derived PromQL, and reports per-SLI which bind vs which are dead. A dead
    (``fail``) SLI is the #274/#275 bug class. With ``--baseline`` this is a CI gate: exit 2 on a NEW
    fail, 0 if clean/baselined, 3 if the live replay was inconclusive (standup/scrape failed).

    See docs/design/observability-compare/REQUIREMENTS.md.
    """
    from .compare_live import (
        EXIT_UNKNOWN,
        ci_gate,
        load_baseline,
        render_baseline,
        render_live_report,
        run_live_comparison,
    )

    auth = Auth.from_env()
    report = run_live_comparison(
        manifest=manifest,
        artifacts_dir=artifacts_dir,
        onboarding_metadata=onboarding_metadata,
        subject_image=subject_image,
        subject_port=subject_port,
        metrics_path=metrics_path,
        prometheus=prometheus,
        min_coverage=min_coverage,
        allow_prod=allow_prod,
        keep_up=keep_up,
        strict_tier_a=strict_tier_a,
        auth=auth,
    )

    # FR-8a: when gating (--baseline, not authoring), compute the new-vs-baseline regression set up
    # front so it reaches the operator in BOTH the --json payload and the human output — not just the
    # exit code. `ci_gate` returns (exit_code, new_fail_verdicts); it is already computed either way.
    gate = (
        ci_gate(report, load_baseline(baseline))
        if (baseline is not None and not write_baseline)
        else None
    )

    if as_json:
        doc = report.to_dict()
        if gate is not None:
            doc["new_fail_verdicts"] = gate[1]  # FR-8a: what regressed vs baseline
        payload = json.dumps(doc, indent=2)
    else:
        payload = render_live_report(report)
    typer.echo(redact(payload, auth.redactions()))

    # FR-8a: on a gate FAIL, name WHICH SLIs are new vs baseline — the regression this change
    # introduced — the discriminating signal a red gate exists to give (not just "something is dead").
    if gate is not None and gate[1] and not as_json:
        lines = [
            f"# {len(gate[1])} NEW dead SLI(s) vs baseline (introduced by this change):"
        ]
        lines += [
            f"#   ✗ {v.get('service', '?')}/{v.get('signal', '?')} — "
            f"{' '.join(str(v.get('expr', '')).split())}"
            for v in gate[1]
        ]
        typer.echo(redact("\n".join(lines), auth.redactions()))

    if keep_up and report.standup.get("subject_container"):
        typer.echo(
            "# --keep-up: tear down with:  "
            + (
                f"docker rm -f {report.standup['subject_container']} "
                f"{report.standup['prometheus_container']}; "
                f"docker network rm {report.standup['network']}"
            )
        )

    if apply_profile_fix:
        # FR-8b: apply the diagnosed one-line fix to the manifest — an EXPLICIT authoring action
        # (like --write-baseline), reusing the existing manifest-writer. It is the manifest half,
        # not a full fix: the operator must regenerate for the derived SLIs to change.
        if write_baseline:
            raise typer.BadParameter(
                "--apply-profile-fix and --write-baseline are separate authoring actions — run one at a time"
            )
        from .bind_and_verify import write_project_profile

        profile = (report.tier_b or {}).get("suggested_metrics_profile") or ""
        if not profile:
            typer.echo(
                "# no single metricsProfile fixes this run (none suggested — the fix may be a "
                "per-axis override); manifest left untouched. See the report detail."
            )
            raise typer.Exit(code=report.exit_code())
        write_project_profile(manifest, manifest, profile)
        typer.echo(f"# applied spec.observability.metricsProfile = {profile} -> {manifest}")
        typer.echo(
            "# NOTE: plain-YAML round-trip — comments are NOT preserved. Regenerate "
            "(startd8 generate observability / backend) for the derived SLIs to take effect."
        )
        raise typer.Exit(code=0)  # authoring is not a gate

    if write_baseline:
        if not baseline:
            raise typer.BadParameter("--write-baseline requires --baseline <path>")
        # NR-4 guard: a baseline may only be authored from a CONFIRMED-LIVE run. On an
        # ``unknown`` report (standup/scrape failed) ``fail_verdicts`` is empty, so writing
        # would silently zero the accepted set and self-heal the gate on the next run.
        if report.status == "unknown":
            typer.echo(
                f"# refusing --write-baseline: report is UNKNOWN ({report.reason}); "
                "would erase the baseline. Existing baseline left untouched."
            )
            raise typer.Exit(code=EXIT_UNKNOWN)
        Path(baseline).write_text(
            json.dumps(
                render_baseline(report, subject=subject_image or prometheus or ""),
                indent=2,
            ),
            encoding="utf-8",
        )
        typer.echo(
            f"# wrote baseline ({len(report.fail_verdicts)} accepted fails) -> {baseline}"
        )
        raise typer.Exit(
            code=0
        )  # authoring is not a gate — never red-X the baseline commit

    if gate is not None:
        raise typer.Exit(code=gate[0])
    raise typer.Exit(code=report.exit_code())


@observability_app.command("enrichment-parity")
def enrichment_parity_cmd(
    generated: Path = typer.Option(
        ...,
        "--generated",
        "-g",
        help="Generated collector-enrichment YAML "
        "(collector-enrichment/otelcol-business-enrichment.yaml from the artifact run).",
    ),
    reference: Optional[Path] = typer.Option(
        None,
        "--reference",
        "-r",
        help="The deployed / hand-written collector config FILE to compare against.",
    ),
    reference_cmd: Optional[str] = typer.Option(
        None,
        "--reference-cmd",
        help="Shell command whose stdout is the reference collector config — pull the LIVE deployed "
        "config from wherever it lives, e.g. "
        "\"kubectl get configmap otel-collector -o jsonpath='{.data.config\\.yaml}'\". "
        "Mutually exclusive with --reference.",
    ),
    as_json: bool = typer.Option(
        False, "--json", help="Emit the ParityResult as JSON instead of a text summary."
    ),
) -> None:
    """Semantic parity gate for the collector_enrichment cutover (REQ_COLLECTOR_ENRICHMENT FR-10a/11).

    Compares the generated ``transform/business`` processor against the deployed one on the resolved
    ``{service.name: {criticality?, owner?}}`` map — order- and grouping-insensitive, so a
    one-statement-per-service generator matches a value-grouped hand-written block. The reference is a
    FILE (``--reference``) or the stdout of a command that fetches the LIVE deployed config
    (``--reference-cmd``, e.g. a ``kubectl get configmap``). Run before deleting the mirror.
    Exit 0 = parity (safe to cut over), 1 = mismatch, 2 = unreadable/erroring input.
    """
    import subprocess

    from .collector_enrichment_parity import check_collector_enrichment_parity

    if (reference is None) == (reference_cmd is None):
        typer.echo(
            "error: provide exactly one of --reference <file> or --reference-cmd <shell>",
            err=True,
        )
        raise typer.Exit(code=2)

    try:
        gen_yaml = Path(generated).read_text()
        if reference_cmd is not None:
            # The operator's own command, on their own machine (same trust model as a shell alias) —
            # run it and use stdout as the reference. Non-zero exit / timeout ⇒ code 2, never a false pass.
            proc = subprocess.run(
                reference_cmd, shell=True, capture_output=True, text=True, timeout=60
            )
            if proc.returncode != 0:
                typer.echo(
                    f"error: --reference-cmd exited {proc.returncode}: "
                    f"{(proc.stderr or '').strip()[:500]}",
                    err=True,
                )
                raise typer.Exit(code=2)
            ref_yaml = proc.stdout
        else:
            ref_yaml = Path(reference).read_text()
    except OSError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2)
    except subprocess.TimeoutExpired:
        typer.echo("error: --reference-cmd timed out after 60s", err=True)
        raise typer.Exit(code=2)

    result = check_collector_enrichment_parity(gen_yaml, ref_yaml)

    if as_json:
        typer.echo(
            json.dumps(
                {
                    "matches": result.matches,
                    "only_in_generated": result.only_in_generated,
                    "only_in_reference": result.only_in_reference,
                    "value_mismatch": result.value_mismatch,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        typer.echo(result.summary())

    raise typer.Exit(code=0 if result.matches else 1)
