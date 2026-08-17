"""Sandboxed generated-app oracle runner (FR-1).

Given a det-req spec and a generated app root, extract each FR's runnable ``Verify:`` clause via the
**FR-2 parser** (``grammar.parse_spec`` — NOT ``verify_oracle.classify()``, which is verb-gated to
``startd8`` and would return ``assertion`` for a ``pytest``/``probe`` clause, R1-F2) and execute the
runnable ones **inside ``benchmark_matrix.sandbox``**:

  - one-shot (``pytest`` / ``python`` / console-script) → :func:`run_sandboxed` (rc 0 = pass).
  - service (``probe METHOD /path -> STATUS``) → a FIXED loopback httpx call rendered from the
    DATA-ONLY :class:`ProbeSpec` (never code from the clause). When the ORACLE rung supplies a
    ``live_port`` (the app the deploy harness already booted), the probe hits that loopback port
    directly; otherwise the runner boots the app via :func:`run_service_sandboxed`.

A ``SandboxResult``/``ServiceResult`` ``violation`` (env failure: never-ready / launch error /
client raised) maps to :data:`VERDICT_ERROR` (degrade), NEVER the model's ``fail`` — the same
"missing-key is infra_fail, not a catastrophic 0" rule the benchmark matrix encodes. A non-runnable
FR yields :data:`VERDICT_SKIP`.

This module does NOT import ``verify_oracle.evaluate``/``classify`` (navigator-locked) and never
touches the navigator allow-list (NR-2 / FR-9).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from ..benchmark_matrix.sandbox import (
    SandboxConfig,
    run_sandboxed,
    run_service_sandboxed,
)
from ..logging_config import get_logger
from . import (
    VERDICT_ERROR,
    VERDICT_FAIL,
    VERDICT_PASS,
    VERDICT_SKIP,
    OracleVerdict,
)
from .grammar import (
    KIND_ONESHOT,
    KIND_SERVICE,
    ParsedClause,
    ProbeSpec,
    parse_spec,
)

logger = get_logger("startd8.oracle_loop.runner")

# A conservative default timeout for a one-shot oracle command.
_ONESHOT_TIMEOUT_S = 120.0


def _probe_descriptor(p: ProbeSpec) -> str:
    body = f" body={p.body}" if p.body is not None else ""
    return f"{p.method} {p.path}{body} -> {p.expected_status}"


def _resolve_oneshot_cmd(clause: ParsedClause, app_root: Path) -> List[str]:
    """Resolve a one-shot clause's argv to a runnable command.

    A ``pytest`` / ``python`` verb runs as-is. A bare console-script token is resolved against the
    app's ``bin/`` (a prepared venv the deploy harness built) when present, else left as the bare
    token (the sandbox PATH resolves it). This is NOT a host-PATH lookup of arbitrary binaries — the
    grammar already constrained the first token to a bare name.
    """
    argv = list(clause.command_argv)
    if not argv:
        return argv
    if clause.is_console_script:
        candidate = app_root / "bin" / argv[0]
        if candidate.exists():
            argv = [str(candidate), *argv[1:]]
    return argv


def _make_probe_client(probe: ProbeSpec):
    """Build a FIXED loopback httpx client callback from a DATA-ONLY probe struct.

    The callback contains NO clause-derived code — only the parsed method/path/body/status. It
    returns ``(ok: bool, detail: str)``.
    """

    def _client(port: int):
        import httpx

        url = f"http://127.0.0.1:{port}{probe.path}"
        with httpx.Client(timeout=10.0) as c:
            resp = c.request(probe.method, url, json=probe.body)
        ok = resp.status_code == probe.expected_status
        return (ok, f"status={resp.status_code} expected={probe.expected_status}")

    return _client


def _probe_live(probe: ProbeSpec, live_port: int) -> OracleVerdict:
    """Run a service probe against an ALREADY-booted loopback app (the ORACLE-rung path)."""
    client = _make_probe_client(probe)
    try:
        ok, detail = client(live_port)
    except Exception as exc:  # noqa: BLE001 — a client/env failure degrades, never model fail
        return OracleVerdict(
            fr_id="",
            kind=KIND_SERVICE,
            verdict=VERDICT_ERROR,
            reason=f"probe client error: {type(exc).__name__}: {exc}",
            command_or_probe=_probe_descriptor(probe),
            isolation_level="live-loopback",
        )
    return OracleVerdict(
        fr_id="",
        kind=KIND_SERVICE,
        verdict=VERDICT_PASS if ok else VERDICT_FAIL,
        reason=detail,
        command_or_probe=_probe_descriptor(probe),
        isolation_level="live-loopback",
    )


def _run_oneshot(
    clause: ParsedClause, app_root: Path, cfg: SandboxConfig
) -> OracleVerdict:
    cmd = _resolve_oneshot_cmd(clause, app_root)
    local_cfg = SandboxConfig(**{**cfg.__dict__, "wall_timeout_s": max(cfg.wall_timeout_s, _ONESHOT_TIMEOUT_S)})
    result = run_sandboxed(cmd, app_root, local_cfg)
    descriptor = " ".join(cmd)
    if result.violation is not None:
        # Env outcome (timeout / resource kill / launch error) — degrade to error, not fail.
        return OracleVerdict(
            fr_id="",
            kind=KIND_ONESHOT,
            verdict=VERDICT_ERROR,
            reason=f"env: {result.violation}",
            command_or_probe=descriptor,
            isolation_level=result.isolation_level,
        )
    verdict = VERDICT_PASS if result.returncode == 0 else VERDICT_FAIL
    reason = "exit 0" if result.returncode == 0 else f"exit {result.returncode}"
    if verdict == VERDICT_FAIL and result.stderr:
        reason = f"{reason}: {result.stderr[-400:]}"
    return OracleVerdict(
        fr_id="",
        kind=KIND_ONESHOT,
        verdict=verdict,
        reason=reason,
        command_or_probe=descriptor,
        isolation_level=result.isolation_level,
    )


def _run_service_boot(
    clause: ParsedClause,
    app_root: Path,
    cfg: SandboxConfig,
    server_cmd: List[str],
    port: int,
    health_path: str,
) -> OracleVerdict:
    """Boot the app and probe it (used when no ``live_port`` is supplied)."""
    probe = clause.probe
    assert probe is not None
    client = _make_probe_client(probe)
    result = run_service_sandboxed(
        server_cmd,
        app_root,
        port,
        client,
        cfg,
        readiness_mode="http",
        health_path=health_path,
    )
    descriptor = _probe_descriptor(probe)
    if result.violation is not None or not result.ready:
        return OracleVerdict(
            fr_id="",
            kind=KIND_SERVICE,
            verdict=VERDICT_ERROR,
            reason=f"env: {result.violation or 'never ready'}",
            command_or_probe=descriptor,
            isolation_level=result.isolation_level,
        )
    ok, detail = result.client_outcome if result.client_outcome else (False, "no outcome")
    return OracleVerdict(
        fr_id="",
        kind=KIND_SERVICE,
        verdict=VERDICT_PASS if ok else VERDICT_FAIL,
        reason=detail,
        command_or_probe=descriptor,
        isolation_level=result.isolation_level,
    )


def run_oracle(
    spec_path: Path | str,
    app_root: Path | str,
    *,
    cfg: Optional[SandboxConfig] = None,
    live_port: Optional[int] = None,
    server_cmd: Optional[List[str]] = None,
    server_port: int = 8099,
    health_path: str = "/health",
) -> List[OracleVerdict]:
    """Run a generated app's runnable ``Verify:`` clauses as an oracle and return per-FR verdicts.

    ``live_port`` — when set (the ORACLE-rung path), service probes hit the already-booted loopback
    app directly; otherwise the runner boots the app via ``server_cmd`` under
    ``run_service_sandboxed``. One-shot clauses always run via ``run_sandboxed`` in ``app_root``.

    Every runnable clause runs through a ``benchmark_matrix.sandbox`` entry; a non-runnable clause
    (``assertion``/``manual``) yields ``skip`` carrying its ``assertion_text`` residue.
    """
    cfg = cfg or SandboxConfig()
    root = Path(app_root)
    clauses = parse_spec(spec_path)
    verdicts: List[OracleVerdict] = []
    for clause in clauses:
        if clause.kind == KIND_ONESHOT:
            v = _run_oneshot(clause, root, cfg)
        elif clause.kind == KIND_SERVICE:
            if live_port is not None:
                v = _probe_live(clause.probe, live_port)
            elif server_cmd is not None:
                v = _run_service_boot(
                    clause, root, cfg, server_cmd, server_port, health_path
                )
            else:
                v = OracleVerdict(
                    fr_id=clause.fr_id,
                    kind=KIND_SERVICE,
                    verdict=VERDICT_ERROR,
                    reason="no live_port or server_cmd to run the probe against",
                    command_or_probe=_probe_descriptor(clause.probe),
                    assertion_text=clause.assertion_text,
                )
                verdicts.append(v)
                continue
        else:
            # assertion / manual → non-runnable residue.
            verdicts.append(
                OracleVerdict(
                    fr_id=clause.fr_id,
                    kind=clause.kind,
                    verdict=VERDICT_SKIP,
                    reason=clause.reason,
                    assertion_text=clause.assertion_text,
                )
            )
            continue
        # Stamp the fr_id + residue onto the runnable verdict (the runners leave fr_id="").
        v = v.model_copy(
            update={"fr_id": clause.fr_id, "assertion_text": clause.assertion_text}
        )
        logger.debug(
            "oracle verdict fr=%s kind=%s verdict=%s isolation=%s",
            v.fr_id,
            v.kind,
            v.verdict,
            v.isolation_level,
            extra={"fr_id": v.fr_id, "verdict": v.verdict},
        )
        verdicts.append(v)
    return verdicts
