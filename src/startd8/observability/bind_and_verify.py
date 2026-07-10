# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""``bind-and-verify`` — the one-command close-the-loop flow.

Composes the five observability primitives into a single flow so "1.0 fidelity
score against zero live data" is structurally impossible:

1. **detect**   — read the live backend's metric names, match a ``metricsProfile``
   (``list_metric_names`` + ``match_profiles``; the same primitive ``detect-profile``
   uses).
2. **reconcile**— compare the detected profile against what the manifest declares.
   An **authored profile always wins** (Genchi Genbutsu: the human's intent is
   authoritative); detection then becomes a cross-check that flags a mismatch.
3. **bind**     — feed the profile into export. *Capture-then-freeze* (BPI Q1):
   by default nothing on disk is mutated — the profile is injected into a throwaway
   sibling copy of the manifest for this run only. ``--freeze`` persists it into the
   real manifest so subsequent deterministic exports carry it.
4. **export + generate** — ``contextcore manifest export`` (CLI-only, subprocessed)
   then ``generate_observability_artifacts`` (imported) produce the PromQL artifacts.
5. **verify**   — ``run_validation`` replays every generated query against the live
   backend and returns the fidelity report, which already names the exact one-line
   fix for any failure (quick-win #1).

Every external effect (metric-name read, export subprocess, generate, validate) is
injectable so the orchestration + reconciliation logic is unit-testable without a
network, a subprocess, or a real Prometheus — mirroring ``run_validation``'s
``query_fn`` pattern.

Exit codes mirror the harness: ``0`` pass · ``2`` fidelity fail · ``3`` unknown
(backend unreachable, export/generate failed, or zero queries replayed — never
conflated with pass).
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from .metric_descriptor import match_profiles
from .prometheus_query import Auth, list_metric_names

logger = logging.getLogger(__name__)

EXIT_PASS = 0
EXIT_FAIL = 2
EXIT_UNKNOWN = 3

#: Default output subdir the generated artifacts land in (validate reads the same).
_ARTIFACTS_SUBDIR = "observability"
_ONBOARDING_FILENAME = "onboarding-metadata.json"


# ─────────────────────────────── report model ──────────────────────────────


@dataclass
class BindVerifyReport:
    """The end-to-end result of a bind-and-verify run (JSON-serializable)."""

    status: str  # "pass" | "fail" | "unknown"
    reason: str
    detection: Dict[str, Any] = field(default_factory=dict)
    reconciliation: Dict[str, Any] = field(default_factory=dict)
    export: Dict[str, Any] = field(default_factory=dict)
    generation: Dict[str, Any] = field(default_factory=dict)
    fidelity: Optional[Dict[str, Any]] = None
    #: The one-line profile fix, surfaced to the top level for humans. Sourced
    #: from the fidelity report (a fidelity fail) or from detection-vs-authored
    #: mismatch when the pipeline never got far enough to replay.
    suggested_metrics_profile: str = ""

    def exit_code(self) -> int:
        return {"pass": EXIT_PASS, "fail": EXIT_FAIL}.get(self.status, EXIT_UNKNOWN)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ─────────────────────────── manifest profile I/O ──────────────────────────


def read_manifest_profiles(manifest_path: Path) -> Dict[str, Any]:
    """The profiles a manifest currently declares, read from raw YAML.

    Returns ``{"project": <str|None>, "targets": {name: profile}}``. Raw YAML (not
    the Pydantic model) so this never fails on an otherwise-valid manifest and never
    rewrites unrelated content.
    """
    data = yaml.safe_load(Path(manifest_path).read_text(encoding="utf-8")) or {}
    spec = data.get("spec") or {}
    observability = spec.get("observability") or {}
    project = observability.get("metricsProfile")
    targets: Dict[str, Any] = {}
    for t in spec.get("targets") or []:
        if isinstance(t, dict) and t.get("metricsProfile"):
            targets[t.get("name", "<target>")] = t.get("metricsProfile")
    return {"project": project, "targets": targets}


def write_project_profile(src: Path, dst: Path, profile: str) -> None:
    """Copy *src* manifest to *dst* with ``spec.observability.metricsProfile`` set.

    Sets a single nested key on a raw-YAML round-trip; every other field is
    preserved verbatim. Comments are not preserved (plain ``yaml``) — the caller
    is responsible for warning when *dst* is the user's real manifest (``--freeze``).
    """
    data = yaml.safe_load(Path(src).read_text(encoding="utf-8")) or {}
    spec = data.setdefault("spec", {})
    observability = spec.setdefault("observability", {})
    observability["metricsProfile"] = profile
    Path(dst).write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


# ──────────────────────────── default effects ──────────────────────────────


def _default_export(manifest_path: Path, output_dir: Path, export_cmd: List[str]) -> Dict[str, Any]:
    """Subprocess ``contextcore manifest export`` (the only CLI-only step).

    Returns ``{"ok": bool, "returncode": int, "stderr_tail": str, "cmd": [...]}``.
    A missing ``contextcore`` binary is reported as a clear, actionable failure
    rather than an opaque traceback.
    """
    cmd = [
        *export_cmd,
        "--path", str(manifest_path),
        "--output-dir", str(output_dir),
        "--emit-onboarding",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return {
            "ok": False,
            "returncode": 127,
            "stderr_tail": (
                f"'{export_cmd[0]}' not found on PATH — install ContextCore "
                "(`pip install -e .` in the ContextCore repo) or pass --export-cmd."
            ),
            "cmd": cmd,
        }
    tail = "\n".join((proc.stderr or "").strip().splitlines()[-8:])
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stderr_tail": tail,
        "cmd": cmd,
    }


def _default_generate(onboarding: Path, artifacts_dir: Path, manifest_path: Path) -> Dict[str, Any]:
    """Call the canonical generator and summarize its report."""
    from .artifact_generator import generate_observability_artifacts

    report = generate_observability_artifacts(
        onboarding_metadata_path=onboarding,
        output_dir=artifacts_dir,
        manifest_path=manifest_path,
    )
    by_status: Dict[str, int] = {}
    errors: List[str] = []
    for a in report.artifacts:
        by_status[a.status] = by_status.get(a.status, 0) + 1
        if a.status == "error":
            errors.append(f"{a.service_id}/{a.artifact_type}: {a.error_message or 'error'}")
    return {
        "ok": not errors,
        "project_id": report.project_id,
        "services_processed": report.services_processed,
        "services_skipped": report.services_skipped,
        "artifacts_by_status": by_status,
        "errors": errors,
    }


# ──────────────────────────── the orchestrator ─────────────────────────────


def bind_and_verify(
    *,
    manifest_path: Path,
    prometheus_url: str,
    output_dir: Path,
    freeze: bool = False,
    min_coverage: float = 1.0,
    allow_prod: bool = False,
    auth: Optional[Auth] = None,
    export_cmd: Optional[List[str]] = None,
    # Injectable effects (default to the real ones); enable network-free tests.
    list_names_fn: Optional[Callable[..., List[str]]] = None,
    export_fn: Optional[Callable[[Path, Path, List[str]], Dict[str, Any]]] = None,
    generate_fn: Optional[Callable[[Path, Path, Path], Dict[str, Any]]] = None,
    validate_fn: Optional[Callable[..., Any]] = None,
) -> BindVerifyReport:
    """Run detect → reconcile → bind → export+generate → verify and return the report."""
    manifest_path = Path(manifest_path)
    output_dir = Path(output_dir)
    auth = auth or Auth()
    # bind-and-verify runs the *fidelity* workflow, not the traceability one, so the
    # default export skips the strict-quality gate (which otherwise demands
    # --task-mapping). Override --export-cmd to supply your own base + flags.
    export_cmd = export_cmd or ["contextcore", "manifest", "export", "--no-strict-quality"]
    list_names_fn = list_names_fn or list_metric_names
    export_fn = export_fn or (lambda m, o, c=export_cmd: _default_export(m, o, c))
    generate_fn = generate_fn or _default_generate
    if validate_fn is None:
        from .validate_promql import run_validation as validate_fn  # type: ignore

    # ── Step 1: detect ──────────────────────────────────────────────────────
    try:
        live_names = list(list_names_fn(prometheus_url, auth=auth))
    except Exception as exc:  # unreachable backend ⇒ distinct non-pass (never green)
        return BindVerifyReport(
            status="unknown",
            reason=f"backend unreachable at {prometheus_url}: {exc}",
            detection={"reachable": False},
        )
    matched = match_profiles(live_names)
    detected = matched[0] if matched else ""
    detection = {
        "reachable": True,
        "metric_name_count": len(live_names),
        "matched_profiles": matched,
        "detected_profile": detected,
    }
    if not live_names:
        return BindVerifyReport(
            status="unknown",
            reason="backend exposes zero metric names — nothing to bind against",
            detection=detection,
        )

    # ── Step 2: reconcile against the authored manifest ─────────────────────
    declared = read_manifest_profiles(manifest_path)
    authored = declared["project"] or (next(iter(declared["targets"].values()), None))
    reconciliation: Dict[str, Any] = {
        "manifest_project_profile": declared["project"],
        "manifest_target_profiles": declared["targets"],
        "detected_profile": detected,
    }

    manifest_for_export = manifest_path
    tmp_manifest: Optional[Path] = None
    if authored:
        # Authored-wins (Genchi Genbutsu). Detection is a cross-check only.
        mismatch = bool(detected) and detected != authored
        reconciliation["action"] = "authored"
        reconciliation["mismatch"] = mismatch
        if mismatch:
            reconciliation["note"] = (
                f"manifest declares {authored!r} but the live backend matches "
                f"{detected!r} — the authored profile was used; verify below will "
                "show whether it resolves against live data."
            )
    elif detected:
        if freeze:
            # Capture-then-freeze: persist into the real manifest.
            write_project_profile(manifest_path, manifest_path, detected)
            reconciliation["action"] = "frozen"
            reconciliation["note"] = (
                f"wrote spec.observability.metricsProfile: {detected} into "
                f"{manifest_path} (comments not preserved)."
            )
        else:
            # Non-mutating: inject into a throwaway sibling copy for this run only.
            tmp_manifest = manifest_path.with_suffix(manifest_path.suffix + ".bindverify.tmp")
            write_project_profile(manifest_path, tmp_manifest, detected)
            manifest_for_export = tmp_manifest
            reconciliation["action"] = "detected-applied"
            reconciliation["note"] = (
                f"used detected profile {detected!r} for this run only; re-run with "
                "--freeze to persist it into the manifest."
            )
    else:
        reconciliation["action"] = "none"
        reconciliation["note"] = (
            "no authored profile and no built-in profile matched the live backend; "
            "the generator default was used — see the fidelity remediation for the fix."
        )

    try:
        # ── Step 3+4: export then generate ──────────────────────────────────
        output_dir.mkdir(parents=True, exist_ok=True)
        export_result = export_fn(manifest_for_export, output_dir, export_cmd)
        if not export_result.get("ok"):
            return BindVerifyReport(
                status="unknown",
                reason="export failed — see export.stderr_tail",
                detection=detection,
                reconciliation=reconciliation,
                export=export_result,
            )

        onboarding = output_dir / _ONBOARDING_FILENAME
        if not onboarding.exists():
            return BindVerifyReport(
                status="unknown",
                reason=f"export produced no {_ONBOARDING_FILENAME} (needed by generate/verify)",
                detection=detection,
                reconciliation=reconciliation,
                export=export_result,
            )

        artifacts_dir = output_dir / _ARTIFACTS_SUBDIR
        generation = generate_fn(onboarding, artifacts_dir, manifest_for_export)
        if not generation.get("ok"):
            return BindVerifyReport(
                status="unknown",
                reason="generation reported errors — see generation.errors",
                detection=detection,
                reconciliation=reconciliation,
                export=export_result,
                generation=generation,
            )

        # ── Step 5: verify ──────────────────────────────────────────────────
        fidelity = validate_fn(
            artifacts_dir=artifacts_dir,
            onboarding_metadata=onboarding,
            prometheus_url=prometheus_url,
            min_coverage=min_coverage,
            allow_prod=allow_prod,
            auth=auth,
        )
    finally:
        if tmp_manifest is not None:
            tmp_manifest.unlink(missing_ok=True)

    fidelity_dict = fidelity.to_dict()
    return BindVerifyReport(
        status=fidelity.status,
        reason=f"bind-and-verify complete — fidelity {fidelity.status}: {fidelity.reason}",
        detection=detection,
        reconciliation=reconciliation,
        export=export_result,
        generation=generation,
        fidelity=fidelity_dict,
        suggested_metrics_profile=fidelity_dict.get("suggested_metrics_profile", ""),
    )
