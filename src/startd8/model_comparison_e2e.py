"""End-to-end Cap-Dev-Pipe multi-model comparison — module foundation + preflight.

Round 1 of a benchmark tournament: run the SAME frozen seed (plan + requirements) through the full
Cap-Dev-Pipe (shared contextcore preamble once, then per-model plan-ingestion → prime → postmortem)
once per model under test, each in a fully isolated project tree, then score and rank.

This module currently implements STEP S0 only — the module skeleton, the FR-5 stage-status enum, the
forward-looking orchestration dataclasses (`StageResult` / `ModelResult`) that later steps (S1–S6)
populate, the FR-17 preflight, and the FR-19 secret redaction. Orchestration (S1–S4), the manifest
(FR-16), the model-pin assertion (FR-14), and the CLI command (S7) are intentionally NOT implemented
here.

Reuses the proven spine in ``startd8.model_comparison`` (``slug()`` and the ``validate_inputs``
pattern) and the provider-validation pattern (``ProviderRegistry``).

Design:
- docs/design/E2E_PIPELINE_MODEL_COMPARISON_REQUIREMENTS.md (v0.3) — §3 FR-5, FR-14, FR-16,
  FR-17, FR-19.
- docs/design/E2E_PIPELINE_MODEL_COMPARISON_PLAN.md (v1.1) — "Step-by-step" S0.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from startd8.logging_config import get_logger
from startd8.model_comparison import (
    SDK_ROOT,
    _fmt,
    _load_json,
    build_command,
    cost_from_db,
    extract_metrics,
    materialize_sandbox,
    run_command,
    slug,
)
from startd8.providers import ProviderRegistry

# Symlinked cap-dev-pipe scripts live under the repo's ``.cap-dev-pipe/`` dir (see CLAUDE.md).
CAP_DEV_PIPE_DIR = SDK_ROOT / ".cap-dev-pipe"
RUN_CAP_DELIVERY = CAP_DEV_PIPE_DIR / "run-cap-delivery.sh"
RUN_PLAN_INGESTION = CAP_DEV_PIPE_DIR / "run-plan-ingestion.sh"

# Stage names (stable identifiers used in StageResult.stage and dry-run plans).
STAGE_SHARED_PREAMBLE = "shared-preamble"
STAGE_PLAN_INGESTION = "plan-ingestion"
STAGE_PRIME = "prime"

logger = get_logger(__name__)


# --------------------------------------------------------------------------- stage status (FR-5)


class StageStatus:
    """Fixed stage-status enum (FR-5).

    A model+stage records exactly one of these. ``skipped_shared`` marks a stage handled once by
    the shared preamble rather than per model; ``invalid_comparison`` marks batch-integrity failures
    (FR-15, e.g. two models collapsing to an identical seed hash).
    """

    NOT_STARTED = "not_started"
    SKIPPED_SHARED = "skipped_shared"
    SUCCESS = "success"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    INVALID_MODEL = "invalid_model"
    BUDGET_EXCEEDED = "budget_exceeded"
    ARTIFACT_MISSING = "artifact_missing"
    INVALID_COMPARISON = "invalid_comparison"

    #: All valid status values, for validation/iteration.
    ALL: frozenset[str] = frozenset(
        {
            NOT_STARTED,
            SKIPPED_SHARED,
            SUCCESS,
            FAILED,
            TIMED_OUT,
            INVALID_MODEL,
            BUDGET_EXCEEDED,
            ARTIFACT_MISSING,
            INVALID_COMPARISON,
        }
    )


#: Default comparison mode stamped into the report/manifest header (FR-9, FR-16). The shared
#: manifest preamble is generated once and reused across models, so the comparison is "frozen"
#: against that single manifest version.
MANIFEST_FROZEN_V1 = "manifest_frozen_v1"


# --------------------------------------------------------------------------- data structures


@dataclass
class StageResult:
    """Outcome of one model-controllable pipeline stage (S1–S4 populate this).

    Forward-looking: ``cost_source``/``cost_confidence`` carry the truth-in-labeling provenance
    (FR-9, FR-16) so a downstream report can disclose whether a cost figure is measured, allocated,
    or unknown rather than silently presenting an estimate as fact.
    """

    stage: str
    status: str = StageStatus.NOT_STARTED
    duration_s: Optional[float] = None
    cost_usd: Optional[float] = None
    cost_source: Optional[str] = None  # e.g. "prime-result.json", "allocated", "unknown"
    cost_confidence: Optional[str] = None  # e.g. "measured" | "allocated" | "unknown"
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "status": self.status,
            "duration_s": self.duration_s,
            "cost_usd": self.cost_usd,
            "cost_source": self.cost_source,
            "cost_confidence": self.cost_confidence,
            "error": self.error,
        }


@dataclass
class ModelResult:
    """Per-model aggregate of the full E2E run (S1–S6 populate this).

    ``resolved_agents`` holds the FR-14 model-pin evidence (assessor/transformer/lead/drafter specs
    actually resolved by each stage); ``seed_hash`` holds the post-ingestion seed hash used for the
    FR-15 batch-integrity check; ``advanced`` is a placeholder flag for tournament progression
    (whether this model advances past Round 1).
    """

    model: str
    slug: str = ""
    stages: list[StageResult] = field(default_factory=list)
    resolved_agents: dict[str, Any] = field(default_factory=dict)  # FR-14 evidence
    seed_hash: Optional[str] = None  # FR-15 batch-integrity check
    advanced: bool = False  # FR-21 tournament Round-1 advancement verdict (set by apply_advancement)
    advancement: Optional[dict[str, Any]] = None  # FR-21 full verdict: {advanced, reason, checks}
    error: Optional[str] = None
    # S5 (FR-9): the three cost fields + capability score breakdown. Populated by ``score_batch``;
    # ``None`` until scored. S6/FR-21 read these (rank on cost_fields["cost_attributable_usd"];
    # gate on capability["score"] / capability["capability_prime_only"]).
    cost_fields: Optional[dict[str, Any]] = None
    capability: Optional[dict[str, Any]] = None

    def __post_init__(self) -> None:
        if not self.slug:
            self.slug = slug(self.model)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "slug": self.slug,
            "stages": [s.to_dict() for s in self.stages],
            "resolved_agents": self.resolved_agents,
            "seed_hash": self.seed_hash,
            "advanced": self.advanced,
            "advancement": self.advancement,
            "error": self.error,
            "cost_fields": self.cost_fields,
            "capability": self.capability,
        }


# --------------------------------------------------------------------------- preflight (FR-17)


def _validate_model_spec(spec: str) -> Optional[str]:
    """Validate one ``provider:model`` spec. Return an error string, or None if valid.

    Checks the spec parses, the provider is registered, and ``provider.validate_config({})`` passes
    (the same gate used elsewhere in the SDK before creating agents).
    """
    if ":" not in spec:
        return f"invalid spec (expected 'provider:model'): {spec!r}"
    provider_name, model = spec.split(":", 1)
    if not provider_name or not model:
        return f"invalid spec (empty provider or model): {spec!r}"

    provider = ProviderRegistry.get_provider(provider_name)
    if provider is None:
        available = ", ".join(sorted(ProviderRegistry.list_providers()))
        return f"unknown provider {provider_name!r} in {spec!r} (available: {available})"

    try:
        ok = provider.validate_config({})
    except Exception as e:  # noqa: BLE001 — validation failure must surface as a preflight error
        return f"provider {provider_name!r} failed validation for {spec!r}: {e}"
    if not ok:
        return (
            f"provider {provider_name!r} config invalid for {spec!r} "
            f"(check credentials / required env vars)"
        )
    return None


def preflight(
    models: list[str],
    plan_paths: list[Path],
    requirements_paths: list[Path],
    source_root: Path,
    batch_root: Path,
) -> list[str]:
    """Fail-fast preflight before any paid work (FR-17).

    Returns a list of human-readable error strings; an **empty list means OK**. Checks:

    - every model is a valid ``provider:model`` spec (provider registered + ``validate_config``);
    - at least **two distinct valid** models;
    - no filesystem **slug collisions** after normalization (two specs whose ``slug()`` collide);
    - every plan and requirements input file exists;
    - ``batch_root`` is not the same path as ``source_root`` (would clobber the source tree).
    """
    errors: list[str] = []

    # 1. Per-spec validity (collect the valid set for distinctness/collision checks).
    valid_models: list[str] = []
    for spec in models:
        err = _validate_model_spec(spec)
        if err is None:
            valid_models.append(spec)
        else:
            errors.append(err)

    # 2. Require >= 2 DISTINCT valid models.
    distinct_valid = list(dict.fromkeys(valid_models))  # preserve order, drop dupes
    if len(distinct_valid) < 2:
        errors.append(
            f"need >=2 distinct valid models; got {len(distinct_valid)} "
            f"({', '.join(distinct_valid) or 'none'})"
        )

    # 3. Reject filesystem slug collisions after normalization (checked across all valid distinct
    #    specs — two different specs that normalize to the same on-disk slug would overwrite).
    slug_map: dict[str, list[str]] = {}
    for spec in distinct_valid:
        slug_map.setdefault(slug(spec), []).append(spec)
    for normalized, specs in sorted(slug_map.items()):
        if len(specs) > 1:
            errors.append(
                f"slug collision: {', '.join(sorted(specs))} all normalize to "
                f"{normalized!r} (would share a batch directory)"
            )

    # 4. Input files must exist.
    if not plan_paths:
        errors.append("no plan paths provided")
    for p in plan_paths:
        if not Path(p).is_file():
            errors.append(f"plan file not found: {p}")
    if not requirements_paths:
        errors.append("no requirements paths provided")
    for p in requirements_paths:
        if not Path(p).is_file():
            errors.append(f"requirements file not found: {p}")

    # 5. batch_root must not equal source_root.
    try:
        if Path(batch_root).resolve() == Path(source_root).resolve():
            errors.append(
                f"batch root must not equal source root: {Path(source_root).resolve()}"
            )
    except OSError as e:
        errors.append(f"could not resolve batch/source roots: {e}")

    if errors:
        logger.warning("preflight found %d issue(s)", len(errors))
    return errors


# --------------------------------------------------------------------------- redaction (FR-19)

# Known secret env var names whose live values (if set) must be masked in any persisted text.
_SECRET_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "MISTRAL_API_KEY",
    "DEEPSEEK_API_KEY",
)

_REDACTED = "[REDACTED]"

# Generic secret patterns: provider-style keys (sk-..., sk-ant-...) and bearer tokens.
_GENERIC_PATTERNS: tuple[re.Pattern[str], ...] = (
    # `Bearer <token>` (Authorization headers).
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]+"),
    # OpenAI/Anthropic-style `sk-...` keys (incl. sk-ant-...). >=16 trailing chars to avoid
    # masking ordinary "sk-" prefixes in prose.
    re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_\-]{16,}"),
    # `KEY=value` / `KEY: value` where the key name ends in TOKEN/SECRET/API_KEY/APIKEY/PASSWORD.
    re.compile(
        r"(?i)\b([A-Z0-9_]*(?:TOKEN|SECRET|API[_-]?KEY|APIKEY|PASSWORD))\b\s*[=:]\s*"
        r"['\"]?[^\s'\"]+",
    ),
)


def redact_secrets(text: str) -> str:
    """Redact API keys / tokens / known secret env values from ``text`` (FR-19).

    Replaces, with ``[REDACTED]``: the live values of known secret env vars (if present in the
    environment and the text), provider-style ``sk-...`` keys, ``Bearer <token>`` headers, and
    ``<NAME_WITH_TOKEN/SECRET/API_KEY/PASSWORD>=<value>`` assignments. Idempotent and safe on text
    with no secrets. Used to sanitize persisted stdout/stderr, command lines, and config snapshots.
    """
    if not text:
        return text
    redacted = text

    # 1. Mask live secret env values verbatim first (most specific).
    for name in _SECRET_ENV_VARS:
        value = os.environ.get(name)
        if value and value in redacted:
            redacted = redacted.replace(value, _REDACTED)

    # 2. Generic patterns. The KEY=value pattern keeps the key name and masks only the value.
    redacted = _GENERIC_PATTERNS[0].sub(_REDACTED, redacted)
    redacted = _GENERIC_PATTERNS[1].sub(_REDACTED, redacted)
    redacted = _GENERIC_PATTERNS[2].sub(
        lambda m: f"{m.group(1)}={_REDACTED}", redacted
    )
    return redacted


# --------------------------------------------------------------------------- model-pin (S3 stub)


def _normalize_spec(spec: Any) -> str:
    """Normalize a resolved agent spec for comparison.

    Accepts either a ``provider:model`` string or a bare model id. The plan-ingestion diagnostic
    records the resolved spec verbatim (e.g. ``anthropic:claude-...``); we compare on the model id
    so a ``mock:mock-model`` request matches a resolved ``mock:mock-model`` (or bare ``mock-model``).
    """
    s = str(spec).strip()
    return s.split(":", 1)[1] if ":" in s else s


def assert_model_pin(
    resolved_agents: dict[str, Any],
    model_under_test: str,
) -> Optional[str]:
    """Assert the resolved ingestion agents match the model under test (FR-14 / OQ-11).

    ``resolved_agents`` is the ``totals.models`` block read from the plan-ingestion diagnostic
    (keys ``assessor`` / ``transformer`` / ``default_provider``). This guards the silent
    ``Models.CLAUDE_SONNET_LATEST`` fallback in ``_resolve_assessor_agent`` /
    ``_resolve_transformer_agent``: if either the resolved assessor or transformer does NOT equal
    ``model_under_test``, the comparison would secretly run on Sonnet for that model.

    Returns a human-readable error string on mismatch (or when the evidence is missing), else None.
    """
    if not resolved_agents:
        return (
            f"model-pin: no resolved-agent evidence for {model_under_test!r} "
            f"(diagnostic missing totals.models — cannot confirm the model was honored)"
        )
    want = _normalize_spec(model_under_test)
    mismatches: list[str] = []
    for role in ("assessor", "transformer"):
        if role not in resolved_agents:
            mismatches.append(f"{role}=<missing>")
            continue
        got = _normalize_spec(resolved_agents[role])
        if got != want:
            mismatches.append(f"{role}={resolved_agents[role]!r}")
    if mismatches:
        return (
            f"model-pin mismatch for {model_under_test!r}: expected assessor+transformer == "
            f"{model_under_test!r}, got {', '.join(mismatches)} "
            f"(silent Sonnet fallback — FR-14)"
        )
    return None


# --------------------------------------------------------------------------- S1: shared preamble


def run_shared_preamble(
    plan_paths: list[Path],
    requirements_paths: list[Path],
    shared_dir: Path,
    *,
    project: str = "compare-models-e2e",
    name: str = "shared",
    runner: Callable[..., dict[str, Any]] = run_command,
    timeout: Optional[float] = None,
    dry_run: bool = False,
) -> StageResult:
    """S1 — run ``run-cap-delivery.sh`` ONCE into ``batch/_shared/`` (model-independent, FR-7).

    The contextcore manifest/polish preamble has no per-model knob, so it runs exactly once for the
    whole batch (R1-S6). On failure the caller aborts the batch (FR-5): nothing downstream can run.

    Cost is recorded as a *shared* line item (``cost_source="shared"``); contextcore does not emit a
    per-run cost today, so ``cost_usd`` is typically None with ``cost_confidence="missing"``.
    Returns a single ``StageResult`` (never raises).
    """
    cmd = build_shared_preamble_command(plan_paths, requirements_paths, shared_dir, project, name)
    if dry_run:
        return StageResult(stage=STAGE_SHARED_PREAMBLE, status=StageStatus.NOT_STARTED)

    shared_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    rec = runner(cmd, CAP_DEV_PIPE_DIR, timeout=timeout)
    duration = rec.get("duration_seconds", time.monotonic() - started)
    if rec.get("timed_out"):
        return StageResult(
            stage=STAGE_SHARED_PREAMBLE,
            status=StageStatus.TIMED_OUT,
            duration_s=duration,
            cost_source="shared",
            cost_confidence="missing",
            error=redact_secrets(rec.get("stderr_tail") or "shared preamble timed out"),
        )
    if rec.get("returncode") != 0:
        return StageResult(
            stage=STAGE_SHARED_PREAMBLE,
            status=StageStatus.FAILED,
            duration_s=duration,
            cost_source="shared",
            cost_confidence="missing",
            error=redact_secrets(
                (rec.get("stderr_tail") or rec.get("stdout_tail") or "")
                or f"cap-delivery exited {rec.get('returncode')}"
            ),
        )
    return StageResult(
        stage=STAGE_SHARED_PREAMBLE,
        status=StageStatus.SUCCESS,
        duration_s=duration,
        cost_source="shared",
        cost_confidence="missing",
    )


def build_shared_preamble_command(
    plan_paths: list[Path],
    requirements_paths: list[Path],
    shared_dir: Path,
    project: str = "compare-models-e2e",
    name: str = "shared",
) -> list[str]:
    """The ``run-cap-delivery.sh`` invocation for the shared preamble (single plan + N reqs)."""
    cmd: list[str] = [
        "bash",
        str(RUN_CAP_DELIVERY),
        "--plan",
        str(plan_paths[0]),  # cap-delivery takes one --plan
        "--project",
        project,
        "--name",
        name,
        "--output-dir",
        str(shared_dir),
    ]
    for req in requirements_paths:
        cmd += ["--requirements", str(req)]
    return cmd


# --------------------------------------------------------------------------- S2: per-model sandbox


def prepare_model_sandbox(
    source_root: Path,
    model: str,
    batch_root: Path,
    shared_dir: Optional[Path] = None,
    *,
    isolation: str = "copy",
) -> tuple[Path, Path]:
    """S2 — materialize ``batch/<slug>/{workdir,output}`` for one model (FR-4).

    Reuses ``materialize_sandbox(..., batch_root=batch_root)`` so the H1 ignore also excludes
    ``batch/_shared`` and sibling model outputs from the workdir copy (R1-S2). The shared provenance
    (``run-provenance.json`` + manifest artifacts) is copied **read-only** into the per-model output
    so plan-ingestion can consume it without mutating the shared dir.
    """
    model_root = batch_root / slug(model)
    workdir = model_root / "workdir"
    output = model_root / "output"
    output.mkdir(parents=True, exist_ok=True)
    # Verbatim-model sidecar so downstream tooling joins by the true id, not the lossy slug.
    (model_root / ".model").write_text(model, encoding="utf-8")

    materialize_sandbox(source_root, workdir, isolation, batch_root=batch_root)
    _copy_shared_provenance(shared_dir, output)
    return workdir, output


def _copy_shared_provenance(shared_dir: Optional[Path], output: Path) -> None:
    """Copy the shared preamble's provenance + manifest artifacts (read-only) into ``output``.

    Best-effort: missing files are skipped (the smoke path stubs a subset). Never mutates
    ``shared_dir``.
    """
    if shared_dir is None or not Path(shared_dir).is_dir():
        return
    dest = output / "_shared"
    dest.mkdir(parents=True, exist_ok=True)
    for item in sorted(Path(shared_dir).glob("*")):
        if item.is_file():
            shutil.copy2(item, dest / item.name)


# --------------------------------------------------------------------------- S3: plan-ingestion


def build_ingestion_config(
    model: str,
    workdir: Path,
    output: Path,
    shared_dir: Optional[Path],
) -> dict[str, Any]:
    """Per-model plan-ingestion config pinning ``assessor_agent`` + ``transformer_agent`` (OQ-11).

    Mirrors the post-resolve config-injection pattern in ``run-plan-ingestion.sh`` (which patches
    ``EFFECTIVE_CONFIG`` for ``--providers`` etc.): we set the assessor/transformer roles to the
    model under test so ``_resolve_ingestion_agent_spec`` honors them instead of defaulting to
    Sonnet. ``output_dir`` / ``project_root`` drive where the seed + diagnostic land.
    """
    cfg: dict[str, Any] = {
        "assessor_agent": model,
        "transformer_agent": model,
        "output_dir": str(output),
        "project_root": str(workdir),
        "force_regenerate": True,
        "review_rounds": 0,
    }
    prov_seed = _shared_provenance_path(shared_dir, output)
    if prov_seed is not None:
        cfg["provenance"] = str(prov_seed)
    return cfg


def _shared_provenance_path(shared_dir: Optional[Path], output: Path) -> Optional[Path]:
    """Locate the copied-in shared ``run-provenance.json`` (preferred) or the original."""
    candidates = [
        output / "_shared" / "run-provenance.json",
    ]
    if shared_dir is not None:
        candidates.append(Path(shared_dir) / "run-provenance.json")
    for c in candidates:
        if c.is_file():
            return c
    return None


def run_plan_ingestion(
    model: str,
    workdir: Path,
    output: Path,
    shared_dir: Optional[Path],
    *,
    runner: Callable[..., dict[str, Any]] = run_command,
    timeout: Optional[float] = None,
    dry_run: bool = False,
) -> tuple[StageResult, dict[str, Any], Optional[str]]:
    """S3 — per-model plan-ingestion with the model pinned (FR-2 narrowed, FR-14, FR-15).

    Writes a pinned config to ``output/ingestion-config.json``, invokes ``run-plan-ingestion.sh``
    via ``runner``, then reads back:

    - ``resolved_agents`` from ``plan-ingestion-diagnostic.json`` → ``totals.models``
      (keys ``assessor`` / ``transformer`` / ``default_provider``); empty if the diagnostic is
      missing;
    - ``seed_hash`` = sha256 of the produced ``prime-context-seed.json`` (FR-15 integrity);

    and runs ``assert_model_pin`` (FR-14). Returns ``(StageResult, resolved_agents, seed_hash)``.
    On a model-pin mismatch the stage is marked ``invalid_model`` with the pin error; on a missing
    seed it is ``artifact_missing``. Never raises.
    """
    cfg = build_ingestion_config(model, workdir, output, shared_dir)
    config_path = output / "ingestion-config.json"

    if dry_run:
        return (
            StageResult(stage=STAGE_PLAN_INGESTION, status=StageStatus.NOT_STARTED),
            {},
            None,
        )

    output.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    cmd = build_ingestion_command(config_path)

    rec = runner(cmd, CAP_DEV_PIPE_DIR, timeout=timeout)
    duration = rec.get("duration_seconds")

    # Read evidence regardless of exit code (partial artifacts still inform the report).
    resolved_agents = read_resolved_agents(output)
    seed_hash = compute_seed_hash(output)

    if rec.get("timed_out"):
        return (
            StageResult(
                stage=STAGE_PLAN_INGESTION,
                status=StageStatus.TIMED_OUT,
                duration_s=duration,
                error=redact_secrets(rec.get("stderr_tail") or "plan-ingestion timed out"),
            ),
            resolved_agents,
            seed_hash,
        )
    if rec.get("returncode") != 0:
        return (
            StageResult(
                stage=STAGE_PLAN_INGESTION,
                status=StageStatus.FAILED,
                duration_s=duration,
                error=redact_secrets(
                    (rec.get("stderr_tail") or rec.get("stdout_tail") or "")
                    or f"plan-ingestion exited {rec.get('returncode')}"
                ),
            ),
            resolved_agents,
            seed_hash,
        )

    # FR-14: model-pin verification (guards silent Sonnet fallback).
    pin_error = assert_model_pin(resolved_agents, model)
    if pin_error is not None:
        return (
            StageResult(
                stage=STAGE_PLAN_INGESTION,
                status=StageStatus.INVALID_MODEL,
                duration_s=duration,
                error=pin_error,
            ),
            resolved_agents,
            seed_hash,
        )

    # Seed must exist for prime to run.
    if seed_hash is None:
        return (
            StageResult(
                stage=STAGE_PLAN_INGESTION,
                status=StageStatus.ARTIFACT_MISSING,
                duration_s=duration,
                error="prime-context-seed.json not produced by plan-ingestion",
            ),
            resolved_agents,
            seed_hash,
        )

    return (
        StageResult(
            stage=STAGE_PLAN_INGESTION,
            status=StageStatus.SUCCESS,
            duration_s=duration,
        ),
        resolved_agents,
        seed_hash,
    )


def build_ingestion_command(config_path: Path) -> list[str]:
    """The ``run-plan-ingestion.sh --config <pinned>`` invocation (config carries the model pin)."""
    return [
        "bash",
        str(RUN_PLAN_INGESTION),
        "--config",
        str(config_path),
    ]


def seed_path(output: Path) -> Path:
    """The plan-ingestion seed consumed by prime."""
    return output / "prime-context-seed.json"


def compute_seed_hash(output: Path) -> Optional[str]:
    """sha256 of the produced ``prime-context-seed.json`` (FR-15), or None if absent."""
    path = seed_path(output)
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_resolved_agents(output: Path) -> dict[str, Any]:
    """Read ``totals.models`` (resolved assessor/transformer/default_provider) from the diagnostic.

    The plan-ingestion workflow records each resolved ingestion model into
    ``plan-ingestion-diagnostic.json`` under ``totals.models`` (see
    ``plan_ingestion_workflow._record_ingestion_model``). Returns an empty dict when the diagnostic
    or the block is missing — callers treat that as "no evidence" (FR-14 fails closed).
    """
    diag = output / "plan-ingestion-diagnostic.json"
    if not diag.is_file():
        return {}
    try:
        data = json.loads(diag.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    models = (data.get("totals") or {}).get("models") or {}
    return dict(models) if isinstance(models, dict) else {}


# --------------------------------------------------------------------------- S4: prime


def run_prime(
    model: str,
    seed: Path,
    workdir: Path,
    output: Path,
    cost_budget: Optional[float],
    *,
    runner: Callable[..., dict[str, Any]] = run_command,
    timeout: Optional[float] = None,
    dry_run: bool = False,
) -> StageResult:
    """S4 — per-model prime with the model pinned on both generation paths (proven path).

    Reuses ``model_comparison.build_command`` (``--lead-agent``/``--drafter-agent`` == model,
    ``--force-regenerate``) + ``runner``. This records success/failure/duration only — capability
    + cost extraction from ``prime-result.json`` is S5's job (``extract_metrics``), not done here.
    Never raises.
    """
    cmd = build_command(seed, workdir, output, model, cost_budget)
    if dry_run:
        return StageResult(stage=STAGE_PRIME, status=StageStatus.NOT_STARTED)

    rec = runner(cmd, SDK_ROOT, timeout=timeout)
    duration = rec.get("duration_seconds")
    if rec.get("timed_out"):
        return StageResult(
            stage=STAGE_PRIME,
            status=StageStatus.TIMED_OUT,
            duration_s=duration,
            error=redact_secrets(rec.get("stderr_tail") or "prime timed out"),
        )
    if rec.get("returncode") != 0:
        return StageResult(
            stage=STAGE_PRIME,
            status=StageStatus.FAILED,
            duration_s=duration,
            error=redact_secrets(
                (rec.get("stderr_tail") or rec.get("stdout_tail") or "")
                or f"prime exited {rec.get('returncode')}"
            ),
        )
    return StageResult(stage=STAGE_PRIME, status=StageStatus.SUCCESS, duration_s=duration)


# --------------------------------------------------------------------------- orchestration (FR-6)


@dataclass
class E2EBatchResult:
    """Outcome of one orchestrated E2E batch (the structures S5/S6 consume).

    ``shared`` is the single S1 ``StageResult``; ``models`` is the per-model list; ``invalid``
    flags an FR-15 seed-hash collision (two models collapsing to an identical seed). ``aborted``
    is True when the shared preamble failed and no per-model work ran (FR-5).
    """

    shared: StageResult
    models: list[ModelResult] = field(default_factory=list)
    invalid_comparison: bool = False
    aborted: bool = False
    preflight_errors: list[str] = field(default_factory=list)
    #: The batch root the per-model trees live under; lets score_batch derive the per-model output
    #: dir safely (its default formerly pointed at SDK_ROOT/batch — a silent all-N/A footgun).
    batch_root: Optional[Path] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "shared": self.shared.to_dict(),
            "models": [m.to_dict() for m in self.models],
            "invalid_comparison": self.invalid_comparison,
            "aborted": self.aborted,
            "preflight_errors": list(self.preflight_errors),
            "batch_root": str(self.batch_root) if self.batch_root else None,
        }


def plan_e2e(
    models: list[str],
    plan_paths: list[Path],
    requirements_paths: list[Path],
    source_root: Path,
    batch_root: Path,
    cost_budget: Optional[float] = None,
) -> list[dict[str, Any]]:
    """Dry-run plan: the per-model/per-stage command sequence WITHOUT executing (FR-12, R1-S6).

    Returns an ordered list of ``{"stage", "scope", "model"?, "cmd"}`` entries. The shared
    cap-delivery command appears **exactly once** (first entry, ``scope="batch"``); each model then
    contributes its plan-ingestion + prime commands (``scope="model"``). No filesystem mutation.
    """
    shared_dir = batch_root / "_shared"
    plan: list[dict[str, Any]] = [
        {
            "stage": STAGE_SHARED_PREAMBLE,
            "scope": "batch",
            "cmd": build_shared_preamble_command(plan_paths, requirements_paths, shared_dir),
        }
    ]
    seen: set[str] = set()
    for model in models:
        if model in seen:
            continue
        seen.add(model)
        model_root = batch_root / slug(model)
        workdir = model_root / "workdir"
        output = model_root / "output"
        config_path = output / "ingestion-config.json"
        plan.append(
            {
                "stage": STAGE_PLAN_INGESTION,
                "scope": "model",
                "model": model,
                "cmd": build_ingestion_command(config_path),
            }
        )
        plan.append(
            {
                "stage": STAGE_PRIME,
                "scope": "model",
                "model": model,
                "cmd": build_command(seed_path(output), workdir, output, model, cost_budget),
            }
        )
    return plan


def orchestrate_e2e(
    models: list[str],
    plan_paths: list[Path],
    requirements_paths: list[Path],
    source_root: Path,
    batch_root: Path,
    *,
    cost_budget: Optional[float] = None,
    isolation: str = "copy",
    per_stage_timeout: Optional[float] = None,
    runner: Callable[..., dict[str, Any]] = run_command,
    dry_run: bool = False,
    log: Callable[[str], None] = logger.info,
) -> E2EBatchResult:
    """Serial E2E driver (FR-6): preflight → S1 shared preamble → per-model S2→S3→S4.

    Order of operations:

    1. **Preflight (FR-17).** Validate specs / inputs / roots; abort (no work) on any error.
    2. **S1 shared preamble.** Runs cap-delivery once into ``batch/_shared/``. If it FAILS, the
       whole batch aborts (FR-5) — nothing downstream can run.
    3. **Per model, serially (FR-6).** S2 sandbox → S3 plan-ingestion (pins the model, records
       ``resolved_agents`` + ``seed_hash``, FR-14/15) → S4 prime. A per-model stage failure records
       the status and **continues** to the next model (FR-5). A model only advances stages while the
       prior stage succeeded.
    4. **FR-15 batch integrity.** After all models, if two share an identical ``seed_hash`` the batch
       is flagged ``invalid_comparison`` (each colliding model gets an ``invalid_comparison`` stage).

    Returns an :class:`E2EBatchResult` (shared StageResult + per-model ``ModelResult`` list). Does
    NOT build the manifest (S6) or capability score (S5) — only populates the structures.

    The ``runner`` parameter is the single injectable subprocess seam (default = the real
    ``run_command``); the S8 smoke test substitutes a fake to exercise this path with zero spend.
    """
    # 1. Preflight (FR-17) — before any paid work.
    errors = preflight(models, plan_paths, requirements_paths, source_root, batch_root)
    if errors:
        for e in errors:
            log(f"preflight: {e}")
        return E2EBatchResult(
            shared=StageResult(stage=STAGE_SHARED_PREAMBLE, status=StageStatus.NOT_STARTED),
            aborted=True,
            preflight_errors=errors,
        )

    distinct_models = list(dict.fromkeys(models))
    shared_dir = batch_root / "_shared"

    if dry_run:
        # Plan only — no execution; cap-delivery shown exactly once (R1-S6).
        for entry in plan_e2e(
            distinct_models, plan_paths, requirements_paths, source_root, batch_root, cost_budget
        ):
            scope = entry["scope"]
            who = entry.get("model", "")
            log(f"[{scope}] {entry['stage']} {who}: {' '.join(entry['cmd'])}")
        return E2EBatchResult(
            shared=StageResult(stage=STAGE_SHARED_PREAMBLE, status=StageStatus.NOT_STARTED),
        )

    # 2. S1 — shared preamble (once). Abort the whole batch on failure (FR-5).
    log("=== S1: shared cap-delivery preamble (once) ===")
    shared = run_shared_preamble(
        plan_paths,
        requirements_paths,
        shared_dir,
        runner=runner,
        timeout=per_stage_timeout,
    )
    if shared.status != StageStatus.SUCCESS:
        log(f"shared preamble {shared.status} — aborting batch (FR-5): {shared.error}")
        return E2EBatchResult(shared=shared, aborted=True)

    # 3. Per-model serial loop (FR-6). A per-model failure CONTINUES to the next (FR-5).
    results: list[ModelResult] = []
    for model in distinct_models:
        log(f"=== model {model} ===")
        mr = ModelResult(model=model)
        results.append(mr)
        try:
            _run_one_model(
                mr,
                model,
                source_root,
                batch_root,
                shared_dir,
                cost_budget=cost_budget,
                isolation=isolation,
                per_stage_timeout=per_stage_timeout,
                runner=runner,
                log=log,
            )
        except Exception as exc:  # noqa: BLE001 — one bad model must not kill the batch (FR-5)
            mr.error = redact_secrets(str(exc))
            mr.stages.append(
                StageResult(
                    stage=STAGE_PLAN_INGESTION,
                    status=StageStatus.FAILED,
                    error=mr.error,
                )
            )
            log(f"  model {model} errored: {mr.error}")

    # 4. FR-15 — batch integrity: flag identical seed hashes across models.
    invalid = _flag_seed_collisions(results, log)
    return E2EBatchResult(
        shared=shared, models=results, invalid_comparison=invalid, batch_root=batch_root
    )


def _run_one_model(
    mr: ModelResult,
    model: str,
    source_root: Path,
    batch_root: Path,
    shared_dir: Path,
    *,
    cost_budget: Optional[float],
    isolation: str,
    per_stage_timeout: Optional[float],
    runner: Callable[..., dict[str, Any]],
    log: Callable[[str], None],
) -> None:
    """S2→S3→S4 for one model, populating ``mr`` in place. Stops at the first failed stage."""
    # S2 — isolated sandbox.
    workdir, output = prepare_model_sandbox(
        source_root, model, batch_root, shared_dir, isolation=isolation
    )

    # S3 — plan-ingestion (pins model, records resolved_agents + seed_hash).
    ing_stage, resolved_agents, seed_hash = run_plan_ingestion(
        model, workdir, output, shared_dir, runner=runner, timeout=per_stage_timeout
    )
    mr.stages.append(ing_stage)
    mr.resolved_agents = resolved_agents
    mr.seed_hash = seed_hash
    if ing_stage.status != StageStatus.SUCCESS:
        mr.error = ing_stage.error
        # Record prime as not-started so the report shows the full stage set.
        mr.stages.append(StageResult(stage=STAGE_PRIME, status=StageStatus.NOT_STARTED))
        log(f"  plan-ingestion {ing_stage.status}: {ing_stage.error}")
        return

    # S4 — prime.
    prime_stage = run_prime(
        model,
        seed_path(output),
        workdir,
        output,
        cost_budget,
        runner=runner,
        timeout=per_stage_timeout,
    )
    mr.stages.append(prime_stage)
    if prime_stage.status != StageStatus.SUCCESS:
        mr.error = prime_stage.error
        log(f"  prime {prime_stage.status}: {prime_stage.error}")


def _flag_seed_collisions(
    results: list[ModelResult], log: Callable[[str], None]
) -> bool:
    """FR-15: if ≥2 models share an identical non-null ``seed_hash``, flag the batch invalid.

    Each colliding model gets an appended ``invalid_comparison`` stage so the per-model report row
    surfaces it. Returns True when any collision was found.
    """
    by_hash: dict[str, list[ModelResult]] = {}
    for mr in results:
        if mr.seed_hash:
            by_hash.setdefault(mr.seed_hash, []).append(mr)
    invalid = False
    for seed_hash, colliding in by_hash.items():
        if len(colliding) > 1:
            invalid = True
            names = ", ".join(m.model for m in colliding)
            msg = (
                f"identical seed hash {seed_hash[:12]}… across models [{names}] — "
                f"comparison collapsed (model pin failure or shared-state bug, FR-15)"
            )
            log(f"  INVALID COMPARISON: {msg}")
            for mr in colliding:
                mr.stages.append(
                    StageResult(
                        stage=STAGE_PLAN_INGESTION,
                        status=StageStatus.INVALID_COMPARISON,
                        error=msg,
                    )
                )
    return invalid


# --------------------------------------------------------------------------- S5: extraction + score

# Cost-source / cost-confidence enum (R2-S3). Each cost figure is tagged with where it came from and
# how much to trust it, so a report can disclose provenance instead of presenting an estimate as fact.
COST_SOURCE_PRIME_RESULT = "prime_result"  # measured from prime-result.json total_cost_usd
COST_SOURCE_DIAGNOSTIC = "diagnostic"  # measured from plan-ingestion-diagnostic.json totals.cost_usd
COST_SOURCE_COST_DB_WINDOW = "cost_db_window"  # time-window fallback against the shared cost DB
COST_SOURCE_SHARED = "shared"  # allocated from the shared preamble (model-independent)
COST_SOURCE_MISSING = "missing"  # no cost figure available

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_MISSING = "missing"

# Worst-to-best ordering of confidence tiers; ``_worst_confidence`` folds component tiers to the
# weakest one so an aggregate cost never advertises more certainty than its weakest input.
_CONFIDENCE_RANK = {CONFIDENCE_MISSING: 0, CONFIDENCE_MEDIUM: 1, CONFIDENCE_HIGH: 2}

# Capability-score weights (FR-9 / R1-S4). Documented + summing to 1.0. ``capability_score`` =
# W_INGESTION * norm(ingestion_signal) + W_PRIME * norm(prime_gate + feature_completion). Prime is
# weighted more heavily because it produces the deliverable; ingestion gates whether the seed that
# prime consumes is sound (an invalid seed caps end-to-end quality regardless of prime skill).
W_INGESTION = 0.3
W_PRIME = 0.7

# Within the prime component, split between the cross-file gate score and feature completion rate.
_PRIME_GATE_WEIGHT = 0.5
_PRIME_COMPLETION_WEIGHT = 0.5


def _stage(model_result: ModelResult, stage_name: str) -> Optional[StageResult]:
    """Return the (first) StageResult with ``stage == stage_name``, or None."""
    for s in model_result.stages:
        if s.stage == stage_name:
            return s
    return None


def _clamp01(value: Optional[float]) -> Optional[float]:
    """Clamp a numeric to [0, 1]; pass through None."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, v))


def _worst_confidence(confidences: list[Optional[str]]) -> str:
    """Fold a list of confidence tiers to the weakest present (R1-S3 worst-case rule).

    Components with ``None`` confidence are treated as ``missing``. An empty list -> ``missing``.
    """
    ranks = [_CONFIDENCE_RANK.get(c or CONFIDENCE_MISSING, 0) for c in confidences]
    if not ranks:
        return CONFIDENCE_MISSING
    worst = min(ranks)
    for name, rank in _CONFIDENCE_RANK.items():
        if rank == worst:
            return name
    return CONFIDENCE_MISSING


def _read_ingestion_diagnostic(output_dir: Path) -> dict[str, Any]:
    """Read ``plan-ingestion-diagnostic.json`` (or {} if absent/unparseable)."""
    return _load_json(output_dir / "plan-ingestion-diagnostic.json") or {}


def extract_stage_costs(
    model_result: ModelResult,
    output_dir: Path,
    run_record: Optional[dict[str, Any]] = None,
) -> None:
    """Populate ``cost_usd`` / ``cost_source`` / ``cost_confidence`` on the per-model stages (FR-9).

    Mutates ``model_result`` in place. Reuses ``model_comparison.extract_metrics`` (prime) and
    ``cost_from_db`` (time-window fallback) — does NOT re-implement gate/cost parsing (FR-10).

    - **Prime stage:** ``extract_metrics(output_dir)`` → if ``total_cost`` is present, tag
      ``prime_result`` / ``high``; else fall back to ``cost_from_db(start, end)`` → ``cost_db_window``
      / ``medium``; else ``missing`` / ``missing``.
    - **Plan-ingestion stage:** the diagnostic's ``totals.cost_usd`` if present → ``diagnostic`` /
      ``high``; else the cost-DB time window → ``cost_db_window`` / ``medium``; else ``missing``.

    ``run_record`` is the runner dict (``start_ts`` / ``end_ts`` datetimes) used to scope the cost-DB
    window fallback; when absent (or lacking timestamps) the DB fallback is skipped.
    """
    start_ts = (run_record or {}).get("start_ts")
    end_ts = (run_record or {}).get("end_ts")

    # ---- prime stage ----
    prime_stage = _stage(model_result, STAGE_PRIME)
    if prime_stage is not None:
        metrics = extract_metrics(output_dir)
        total = metrics.get("total_cost")
        if total is not None:
            prime_stage.cost_usd = float(total)
            prime_stage.cost_source = COST_SOURCE_PRIME_RESULT
            prime_stage.cost_confidence = CONFIDENCE_HIGH
        else:
            db_cost = (
                cost_from_db(start_ts, end_ts)
                if start_ts is not None and end_ts is not None
                else None
            )
            if db_cost is not None:
                prime_stage.cost_usd = float(db_cost)
                prime_stage.cost_source = COST_SOURCE_COST_DB_WINDOW
                prime_stage.cost_confidence = CONFIDENCE_MEDIUM
            else:
                prime_stage.cost_usd = None
                prime_stage.cost_source = COST_SOURCE_MISSING
                prime_stage.cost_confidence = CONFIDENCE_MISSING

    # ---- plan-ingestion stage ----
    ing_stage = _stage(model_result, STAGE_PLAN_INGESTION)
    if ing_stage is not None:
        diag = _read_ingestion_diagnostic(output_dir)
        diag_cost = (diag.get("totals") or {}).get("cost_usd")
        if diag_cost is not None:
            ing_stage.cost_usd = float(diag_cost)
            ing_stage.cost_source = COST_SOURCE_DIAGNOSTIC
            ing_stage.cost_confidence = CONFIDENCE_HIGH
        else:
            db_cost = (
                cost_from_db(start_ts, end_ts)
                if start_ts is not None and end_ts is not None
                else None
            )
            if db_cost is not None:
                ing_stage.cost_usd = float(db_cost)
                ing_stage.cost_source = COST_SOURCE_COST_DB_WINDOW
                ing_stage.cost_confidence = CONFIDENCE_MEDIUM
            else:
                ing_stage.cost_usd = None
                ing_stage.cost_source = COST_SOURCE_MISSING
                ing_stage.cost_confidence = CONFIDENCE_MISSING


def compute_cost_fields(
    model_result: ModelResult,
    shared_stage: Optional[StageResult] = None,
) -> dict[str, Any]:
    """The THREE cost fields per model (FR-9). Run ``extract_stage_costs`` first.

    - ``cost_attributable_usd`` = ingestion + prime — the model-varied, comparable number.
      **Ranking uses this field** (the shared preamble is model-independent, so loading it onto each
      model would skew ``$ / capability`` by model count).
    - ``cost_shared_preamble_usd`` = the shared preamble cost allocated to this model (or ``None``;
      contextcore does not emit a per-run cost today, so this is typically ``None``).
    - ``cost_total_loaded_usd`` = attributable + shared (fully-loaded; a report footnote, not the
      ranking key).

    Each field carries the **worst-case** ``cost_confidence`` across its components, so an aggregate
    never overstates certainty. A field is ``None`` only when *all* its components are missing.
    """
    ing = _stage(model_result, STAGE_PLAN_INGESTION)
    prime = _stage(model_result, STAGE_PRIME)

    attributable_parts = [s for s in (ing, prime) if s is not None]
    attributable_costs = [s.cost_usd for s in attributable_parts if s.cost_usd is not None]
    attributable = sum(attributable_costs) if attributable_costs else None
    attributable_conf = _worst_confidence([s.cost_confidence for s in attributable_parts])

    shared_cost = shared_stage.cost_usd if shared_stage is not None else None
    shared_conf = shared_stage.cost_confidence if shared_stage is not None else CONFIDENCE_MISSING

    # Total loaded = attributable + shared (each may be None; sum present components).
    total_parts = [c for c in (attributable, shared_cost) if c is not None]
    total_loaded = sum(total_parts) if total_parts else None
    total_conf = _worst_confidence([attributable_conf, shared_conf])

    return {
        # The comparable number — RANKING USES THIS (cost_attributable_usd).
        "cost_attributable_usd": attributable,
        "cost_attributable_confidence": attributable_conf,
        "cost_shared_preamble_usd": shared_cost,
        "cost_shared_preamble_confidence": shared_conf,
        "cost_total_loaded_usd": total_loaded,
        "cost_total_loaded_confidence": total_conf,
        "ranking_field": "cost_attributable_usd",
    }


def _ingestion_signal(output_dir: Path) -> tuple[Optional[float], Optional[str]]:
    """The ingestion capability signal in [0,1] + its source artifact path.

    Uses ``plan-ingestion-diagnostic.json``'s top-level ``seed_quality_score`` (the workflow's own
    [0,1] quality measure). Returns (None, None) when the diagnostic / score is absent.
    """
    diag_path = output_dir / "plan-ingestion-diagnostic.json"
    diag = _load_json(diag_path) or {}
    score = diag.get("seed_quality_score")
    if score is None:
        return None, None
    return _clamp01(score), str(diag_path)


def _prime_signal(
    output_dir: Path, prime_metrics: Optional[dict[str, Any]]
) -> tuple[Optional[float], Optional[float], Optional[float], Optional[str], Optional[str]]:
    """The prime capability sub-signals: (combined, gate_norm, completion, gate_verdict, source).

    ``combined`` = gate * _PRIME_GATE_WEIGHT + completion * _PRIME_COMPLETION_WEIGHT over whichever
    sub-signals are present (re-normalized across present parts). Reuses ``extract_metrics`` output
    (passed in to avoid re-reading): ``gate_score`` (cross_file_gate score, [0,1]) and
    ``completion_rate`` (succeeded / processed). ``gate_verdict`` (cross_file_gate verdict string,
    e.g. ``"pass"``) is carried through for the FR-21 advancement gate. Returns (None, ...) for
    absent sub-signals.
    """
    metrics = prime_metrics if prime_metrics is not None else extract_metrics(output_dir)
    gate_norm = _clamp01(metrics.get("gate_score"))
    completion = _clamp01(metrics.get("completion_rate"))
    gate_verdict = metrics.get("gate_verdict")

    parts: list[tuple[float, float]] = []
    if gate_norm is not None:
        parts.append((_PRIME_GATE_WEIGHT, gate_norm))
    if completion is not None:
        parts.append((_PRIME_COMPLETION_WEIGHT, completion))
    if not parts:
        combined = None
    else:
        weight_sum = sum(w for w, _ in parts)
        combined = sum(w * v for w, v in parts) / weight_sum if weight_sum else None

    src = str(_prime_result_path(output_dir)) if metrics.get("artifacts_found") else None
    return combined, gate_norm, completion, gate_verdict, src


def _prime_result_path(output_dir: Path) -> Path:
    """Best-effort path to the prime-result artifact (for score-breakdown provenance)."""
    from startd8.model_comparison import _latest_match

    match = _latest_match(output_dir, "prime-result*.json")
    return match if match is not None else (output_dir / "prime-result.json")


def compute_capability(
    model_result: ModelResult,
    prime_metrics: Optional[dict[str, Any]] = None,
    output_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Capability score with an explicit, documented ``score_breakdown`` (FR-9 / R1-S4).

    ``score`` = ``W_INGESTION * norm(ingestion_signal) + W_PRIME * norm(prime_gate + completion)``,
    weights documented as module constants (W_INGESTION + W_PRIME == 1.0). A **missing component
    contributes 0** to the weighted sum and is **recorded as a penalty** (the lost weight), not
    silently dropped. Also produces ``capability_prime_only`` — the prime component alone,
    re-normalized to [0,1] — the apples-to-apples control against ``compare-models``.

    ``output_dir`` defaults to the per-model output (``batch/<slug>/output``) when not given so the
    function can read the ingestion diagnostic + prime artifacts; ``prime_metrics`` (an
    ``extract_metrics`` dict) is reused when supplied to avoid re-reading prime-result.json.
    """
    if output_dir is None:
        output_dir = SDK_ROOT / "batch" / model_result.slug / "output"

    ingestion_signal, ingestion_src = _ingestion_signal(output_dir)
    prime_combined, gate_norm, completion, gate_verdict, prime_src = _prime_signal(
        output_dir, prime_metrics
    )

    components: dict[str, Any] = {
        "ingestion": {
            "weight": W_INGESTION,
            "value": ingestion_signal,
            "source": ingestion_src,
        },
        "prime": {
            "weight": W_PRIME,
            "value": prime_combined,
            "gate_score": gate_norm,
            "gate_verdict": gate_verdict,  # FR-21: cross_file_gate pass/fail string
            "completion_rate": completion,
            "source": prime_src,
        },
    }

    penalties: list[dict[str, Any]] = []
    score = 0.0
    for name, comp in components.items():
        weight = comp["weight"]
        value = comp["value"]
        if value is None:
            # Missing component contributes 0 and is RECORDED as a penalty (FR-9), not dropped.
            penalties.append(
                {
                    "component": name,
                    "lost_weight": weight,
                    "reason": f"{name} signal missing (contributes 0)",
                }
            )
        else:
            score += weight * value

    # capability_prime_only: the prime component alone, re-normalized to [0,1] (control vs
    # compare-models which has no ingestion stage). None when the prime signal is absent.
    capability_prime_only = prime_combined

    return {
        "score": round(score, 6),
        "score_breakdown": {
            "formula": "W_INGESTION*norm(ingestion) + W_PRIME*norm(gate+completion)",
            "weights": {"W_INGESTION": W_INGESTION, "W_PRIME": W_PRIME},
            "components": components,
            "penalties": penalties,
        },
        "capability_prime_only": capability_prime_only,
    }


def sanitize_run_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a runner/metrics dict with all string text passed through ``redact_secrets``.

    FR-19: any persisted stdout/stderr/command/config text must be redacted before storage. Walks
    the dict recursively; strings are redacted, lists/dicts recursed, other scalars passed through.
    The ``command`` list (argv) is redacted element-wise.
    """
    return _sanitize(record)  # type: ignore[return-value]


def _sanitize(obj: Any) -> Any:
    if isinstance(obj, str):
        return redact_secrets(obj)
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return type(obj)(_sanitize(v) for v in obj)
    return obj


def score_batch(
    batch: E2EBatchResult,
    output_dir_for: Optional[Callable[[ModelResult], Path]] = None,
    run_record_for: Optional[Callable[[ModelResult], dict[str, Any]]] = None,
) -> E2EBatchResult:
    """Run S5 extraction + scoring for every model, attaching results to each ``ModelResult`` (FR-9).

    For each model: ``extract_stage_costs`` → ``compute_cost_fields`` (with the shared preamble
    stage) → ``compute_capability``, writing ``ModelResult.cost_fields`` and ``ModelResult.capability``.
    Pure-ish: mutates the passed ``batch`` in place and also returns it. Reuses
    ``model_comparison`` extractors throughout (FR-10) — no gate/cost re-parsing here.

    - ``output_dir_for(mr)`` resolves the per-model output dir (default ``batch/<slug>/output``).
    - ``run_record_for(mr)`` supplies the runner dict (``start_ts`` / ``end_ts``) for the cost-DB
      window fallback; default returns ``{}`` (DB fallback skipped — relies on artifact costs).
    """
    if output_dir_for is None:
        # Derive from the batch's own root (set by orchestrate_e2e) so scoring reads where the
        # orchestrator actually wrote. Falls back to SDK_ROOT/batch only if batch_root is unset.
        _root = batch.batch_root if batch.batch_root is not None else (SDK_ROOT / "batch")

        def output_dir_for(mr: ModelResult) -> Path:  # noqa: E306
            return _root / mr.slug / "output"

    for mr in batch.models:
        out = output_dir_for(mr)
        run_record = run_record_for(mr) if run_record_for is not None else {}
        extract_stage_costs(mr, out, run_record)
        mr.cost_fields = compute_cost_fields(mr, batch.shared)
        prime_metrics = extract_metrics(out)
        mr.capability = compute_capability(mr, prime_metrics, output_dir=out)
    return batch


# --------------------------------------------------------------------------- FR-21: advancement

#: Default tournament roster (the flagship set). Round 1 runs this roster; a non-flagship model is
#: gated identically (the gate is roster-agnostic — membership here only documents the default field).
#: Ids mirror the canonical ``benchmark_matrix.scorecard.FLAGSHIP_MODELS`` (Fable 5 excluded — access-
#: gated) so the tournament's roster matches the scorecard's headline set.
FLAGSHIP_MODELS: tuple[str, ...] = (
    "anthropic:claude-opus-4-8",
    "openai:gpt-5.5",
    "gemini:gemini-2.5-pro",
)

# Advancement reason vocabulary (stable strings a downstream tournament orchestrator can switch on).
REASON_ADVANCED = "advanced"
REASON_INPUTS_MISSING = "inputs_missing"
REASON_BELOW_CAPABILITY = "below_capability_threshold"
REASON_PRIME_GATE_FAILED = "prime_gate_failed"
REASON_INGESTION_FAILED = "ingestion_failed"
REASON_INVALID_COMPARISON = "invalid_comparison"

# Prime cross_file_gate verdict strings that count as a PASS for FR-21 (case-insensitive).
_GATE_PASS_VERDICTS = frozenset({"pass", "passed", "ok"})


@dataclass(frozen=True)
class AdvancementGate:
    """An explicit, documented **per-round** advancement bar (FR-21).

    Each round of the tournament instantiates its OWN gate (the user's "different bars" decision):
    this dataclass is the **Round-1** bar. Round 2/3 build their own ``AdvancementGate`` with a higher
    ``min_capability`` and/or additional required criteria — nothing here is hardcoded into the verdict
    logic, so a stricter round is a new instance, not a code change.

    Criteria are evaluated over signals the run **already produces** (no new stage work, NR-4/NR-5):

    - ``min_capability`` — the configurable ``--advance-threshold``; a model's
      ``capability["score"]`` (the FR-9 dual-weighted [0,1] score) must be ``>=`` this.
    - ``require_prime_gate_pass`` — the prime ``cross_file_gate`` verdict must be a pass
      (``pass``/``passed``/``ok``); guards advancing a model whose generated code failed integrity.
    - ``require_ingestion_success`` — the plan-ingestion stage status must be ``SUCCESS`` (a sound
      seed is a precondition for trusting the prime output).
    - ``require_valid_comparison`` — the batch must NOT be ``invalid_comparison`` (FR-15 seed
      collision) and this model must not be errored; a collapsed comparison advances no one.

    Disabling a ``require_*`` flag drops that criterion from the gate (it is neither evaluated nor
    able to fail advancement) — useful for a relaxed early round.
    """

    min_capability: float = 0.6
    require_prime_gate_pass: bool = True
    require_ingestion_success: bool = True
    require_valid_comparison: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "round": "round_1",
            "min_capability": self.min_capability,
            "require_prime_gate_pass": self.require_prime_gate_pass,
            "require_ingestion_success": self.require_ingestion_success,
            "require_valid_comparison": self.require_valid_comparison,
        }

    def describe(self) -> str:
        """One-line human description of the Round-1 bar (for the report header)."""
        parts = [f"capability ≥ {self.min_capability:g}"]
        if self.require_prime_gate_pass:
            parts.append("prime cross_file_gate = pass")
        if self.require_ingestion_success:
            parts.append("plan-ingestion = success")
        if self.require_valid_comparison:
            parts.append("comparison valid (not collapsed/errored)")
        return "; ".join(parts)


#: The default Round-1 gate (threshold 0.6, all criteria required). The CLI's ``--advance-threshold``
#: overrides ``min_capability`` by constructing a new gate; Round 2/3 instantiate their own.
DEFAULT_ROUND1_GATE = AdvancementGate()


def _gate_verdict_for(model_result: ModelResult) -> Optional[str]:
    """The prime ``cross_file_gate`` verdict string for this model, or None if unavailable.

    Reads the value threaded into the capability breakdown by ``compute_capability`` (S5) — no
    re-parsing of prime-result.json (FR-10).
    """
    cap = model_result.capability or {}
    prime = ((cap.get("score_breakdown") or {}).get("components") or {}).get("prime") or {}
    verdict = prime.get("gate_verdict")
    return str(verdict) if verdict is not None else None


def evaluate_advancement(
    model_result: ModelResult,
    gate: AdvancementGate,
    *,
    batch_invalid_comparison: bool,
) -> dict[str, Any]:
    """Compute the per-model Round-1 advancement verdict against ``gate`` (FR-21).

    Returns ``{advanced: bool, reason: str, checks: {...}}``. **Degrade-honest:** if required gate
    inputs are missing — no capability score, or no prime stage result — the model is
    ``advanced: False`` with reason ``inputs_missing``; a missing input NEVER advances a model.

    Otherwise each ENABLED criterion is evaluated:

    - ``capability``: ``capability["score"] >= gate.min_capability``;
    - ``prime_gate`` (if ``require_prime_gate_pass``): prime cross_file_gate verdict is a pass;
    - ``ingestion`` (if ``require_ingestion_success``): plan-ingestion stage status == SUCCESS;
    - ``valid_comparison`` (if ``require_valid_comparison``): batch not invalid AND model not errored.

    ``advanced`` is True iff every enabled criterion passes. ``reason`` is ``advanced`` on success,
    else the first failing criterion's reason (``below_capability_threshold`` / ``prime_gate_failed``
    / ``ingestion_failed`` / ``invalid_comparison``). ``checks`` records, per criterion, whether it
    was enabled, whether it passed, and the observed value — for transparency in the manifest/report.
    """
    cap = model_result.capability or {}
    score = cap.get("score")
    prime_stage = _stage(model_result, STAGE_PRIME)
    ing_stage = _stage(model_result, STAGE_PLAN_INGESTION)

    # Degrade-honest: required inputs absent -> never advance.
    if not isinstance(score, (int, float)) or prime_stage is None:
        return {
            "advanced": False,
            "reason": REASON_INPUTS_MISSING,
            "checks": {
                "capability": {
                    "enabled": True,
                    "passed": False,
                    "observed": score if isinstance(score, (int, float)) else None,
                    "threshold": gate.min_capability,
                },
                "prime_gate": {
                    "enabled": gate.require_prime_gate_pass,
                    "passed": False,
                    "observed": _gate_verdict_for(model_result),
                },
                "ingestion": {
                    "enabled": gate.require_ingestion_success,
                    "passed": False,
                    "observed": ing_stage.status if ing_stage is not None else None,
                },
                "valid_comparison": {
                    "enabled": gate.require_valid_comparison,
                    "passed": False,
                    "observed": None,
                },
            },
        }

    checks: dict[str, Any] = {}

    # 1. Capability >= threshold (always enabled).
    cap_pass = float(score) >= gate.min_capability
    checks["capability"] = {
        "enabled": True,
        "passed": cap_pass,
        "observed": float(score),
        "threshold": gate.min_capability,
    }

    # 2. Prime cross_file_gate pass.
    gate_verdict = _gate_verdict_for(model_result)
    gate_pass = (
        gate_verdict is not None and gate_verdict.strip().lower() in _GATE_PASS_VERDICTS
    )
    checks["prime_gate"] = {
        "enabled": gate.require_prime_gate_pass,
        "passed": gate_pass,
        "observed": gate_verdict,
    }

    # 3. Plan-ingestion success.
    ing_pass = ing_stage is not None and ing_stage.status == StageStatus.SUCCESS
    checks["ingestion"] = {
        "enabled": gate.require_ingestion_success,
        "passed": ing_pass,
        "observed": ing_stage.status if ing_stage is not None else None,
    }

    # 4. Valid comparison (batch not collapsed AND model not errored/flagged invalid).
    valid_pass = (
        not batch_invalid_comparison
        and not model_result.error
        and not _model_invalid(model_result)
    )
    checks["valid_comparison"] = {
        "enabled": gate.require_valid_comparison,
        "passed": valid_pass,
        "observed": valid_pass,
    }

    # Evaluate enabled criteria in priority order; first failure names the reason.
    ordered: list[tuple[str, bool, str]] = [
        ("valid_comparison", gate.require_valid_comparison, REASON_INVALID_COMPARISON),
        ("ingestion", gate.require_ingestion_success, REASON_INGESTION_FAILED),
        ("prime_gate", gate.require_prime_gate_pass, REASON_PRIME_GATE_FAILED),
        ("capability", True, REASON_BELOW_CAPABILITY),
    ]
    reason = REASON_ADVANCED
    advanced = True
    for key, enabled, fail_reason in ordered:
        if enabled and not checks[key]["passed"]:
            advanced = False
            reason = fail_reason
            break

    return {"advanced": advanced, "reason": reason, "checks": checks}


def apply_advancement(batch: E2EBatchResult, gate: AdvancementGate) -> None:
    """Compute + stash the Round-1 advancement verdict on every model in ``batch`` (FR-21).

    Mutates each ``ModelResult`` in place: sets ``advanced`` and stashes the full verdict dict on
    ``advancement``. Call AFTER ``score_batch`` (the gate reads ``capability``) and before
    ``build_manifest`` so the verdict is persisted. Idempotent.
    """
    for mr in batch.models:
        verdict = evaluate_advancement(
            mr, gate, batch_invalid_comparison=batch.invalid_comparison
        )
        mr.advancement = verdict
        mr.advanced = bool(verdict["advanced"])


# --------------------------------------------------------------------------- S6: manifest + report

#: Schema version of ``batch-run-manifest.json`` (FR-16). Bump on any breaking key change so
#: downstream tooling (FR-21 advancement, S7 CLI) can detect an incompatible manifest.
MANIFEST_SCHEMA_VERSION = "1.0"

#: Canonical output filenames written into ``batch_root`` (FR-16 / FR-9).
MANIFEST_FILENAME = "batch-run-manifest.json"
REPORT_JSON_FILENAME = "comparison-report.json"
REPORT_MD_FILENAME = "comparison-report.md"
INPUTS_DIRNAME = "_inputs"
SHARED_DIRNAME = "_shared"

_UNKNOWN = "unknown"
_NA = "N/A"


def _sha256_file(path: Path) -> str:
    """sha256 hex digest of a file's bytes."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_inputs_archive(
    plan_paths: list[Path],
    requirements_paths: list[Path],
    batch_root: Path,
) -> dict[str, str]:
    """Copy the exact frozen inputs into ``batch/_inputs/`` and return ``{archived_path: sha256}``.

    FR-16 (folds R3-F2): the comparison's auditability requires the inputs to be frozen *and*
    checksummed at run time, so a later edit to the original source file cannot silently change what
    the run claims it consumed. Copies each plan + requirements file (deduping by basename with an
    index suffix on collision) into ``batch_root/_inputs/`` and hashes the **archived copy** (the
    immutable artifact the report points at). Returns a mapping of archived absolute path → digest.
    """
    inputs_dir = Path(batch_root) / INPUTS_DIRNAME
    inputs_dir.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    used: set[str] = set()
    for src in [*plan_paths, *requirements_paths]:
        src = Path(src)
        name = src.name
        if name in used:  # basename collision across plan/reqs — disambiguate, never overwrite.
            stem, suffix = src.stem, src.suffix
            i = 1
            while f"{stem}.{i}{suffix}" in used:
                i += 1
            name = f"{stem}.{i}{suffix}"
        used.add(name)
        dest = inputs_dir / name
        shutil.copy2(src, dest)
        hashes[str(dest)] = _sha256_file(dest)
    return hashes


def hash_shared_artifacts(shared_dir: Optional[Path]) -> dict[str, str]:
    """``{relpath: sha256}`` for every file under ``shared_dir`` (best-effort, recursive).

    FR-16: the shared preamble produces the model-independent manifest/polish artifacts; hashing them
    lets a reader confirm every model truly consumed the *same* frozen manifest (R4-S7 reuse
    precondition). Returns ``{}`` when the dir is missing — degrade-honest, never raises.
    """
    if shared_dir is None:
        return {}
    root = Path(shared_dir)
    if not root.is_dir():
        return {}
    hashes: dict[str, str] = {}
    for item in sorted(root.rglob("*")):
        if item.is_file():
            try:
                hashes[str(item.relative_to(root))] = _sha256_file(item)
            except OSError:  # unreadable file — skip rather than abort the manifest.
                continue
    return hashes


def collect_versions() -> dict[str, Any]:
    """Tool/SDK version metadata for the manifest (FR-39 / R4-F8).

    Records: the installed ``startd8`` version (``importlib.metadata``), the contextcore CLI version
    if discoverable (best-effort), and the SDK checkout's git SHA + dirty flag. Every field degrades
    to ``"unknown"`` rather than raising — a non-git checkout or missing dependency must not break
    manifest emission. Version metadata is what lets two runs over time be compared honestly when the
    *harness itself* changed (a ranking shift may be the tool, not the model).
    """
    try:
        startd8_version = importlib.metadata.version("startd8")
    except Exception:  # noqa: BLE001 — best-effort metadata, must not raise
        startd8_version = _UNKNOWN

    contextcore_version = _UNKNOWN
    try:
        contextcore_version = importlib.metadata.version("contextcore")
    except Exception:  # noqa: BLE001 — not installed as a dist; try the CLI below
        try:
            proc = subprocess.run(
                ["contextcore", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(SDK_ROOT),
            )
            if proc.returncode == 0 and proc.stdout.strip():
                contextcore_version = proc.stdout.strip()
        except Exception:  # noqa: BLE001 — no CLI / not on PATH
            contextcore_version = _UNKNOWN

    git_sha = _UNKNOWN
    git_dirty: Optional[bool] = None
    try:
        sha_proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(SDK_ROOT),
        )
        if sha_proc.returncode == 0 and sha_proc.stdout.strip():
            git_sha = sha_proc.stdout.strip()
            status_proc = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(SDK_ROOT),
            )
            if status_proc.returncode == 0:
                git_dirty = bool(status_proc.stdout.strip())
    except Exception:  # noqa: BLE001 — non-git checkout / git unavailable
        git_sha = _UNKNOWN
        git_dirty = None

    return {
        "startd8": startd8_version,
        "contextcore": contextcore_version,
        "git_sha": git_sha,
        "git_dirty": git_dirty,
    }


def _model_invalid(mr: ModelResult) -> bool:
    """True when any stage on this model carries the ``invalid_comparison`` status (FR-15)."""
    return any(s.status == StageStatus.INVALID_COMPARISON for s in mr.stages)


def _model_manifest_entry(mr: ModelResult) -> dict[str, Any]:
    """One per-model block of the manifest (FR-16). All embedded text is redacted (FR-19)."""
    return {
        "model": mr.model,
        "slug": mr.slug,
        "resolved_agents": _sanitize(mr.resolved_agents),  # FR-14 evidence
        "seed_hash": mr.seed_hash,  # FR-15 integrity
        "advanced": mr.advanced,  # FR-21 verdict (mirrors advancement.advanced)
        "advancement": mr.advancement,  # FR-21 full per-model verdict {advanced, reason, checks}
        "invalid_comparison": _model_invalid(mr),
        "stages": [_sanitize(s.to_dict()) for s in mr.stages],
        "cost_fields": mr.cost_fields,
        "capability": mr.capability,
        "error": redact_secrets(mr.error) if mr.error else None,
    }


def _advancement_block(batch: E2EBatchResult, gate: AdvancementGate) -> dict[str, Any]:
    """The top-level FR-21 ``advancement`` block: the gate + per-model verdicts.

    Reads each model's stashed ``advancement`` verdict (from ``apply_advancement``); a model that was
    never evaluated degrades to ``advanced: False`` / ``inputs_missing`` rather than being omitted.
    """
    models: dict[str, Any] = {}
    for mr in batch.models:
        verdict = mr.advancement or {
            "advanced": False,
            "reason": REASON_INPUTS_MISSING,
            "checks": {},
        }
        models[mr.model] = {
            "advanced": bool(verdict.get("advanced")),
            "reason": verdict.get("reason", REASON_INPUTS_MISSING),
            "checks": verdict.get("checks", {}),
        }
    return {
        "round": "round_1",
        "gate": gate.to_dict(),
        "gate_description": gate.describe(),
        "models": models,
    }


def build_manifest(
    batch: E2EBatchResult,
    *,
    comparison_mode: str,
    input_hashes: dict[str, str],
    shared_artifact_hashes: dict[str, str],
    versions: dict[str, Any],
    batch_root: Path,
    gate: AdvancementGate = DEFAULT_ROUND1_GATE,
) -> dict[str, Any]:
    """The authoritative ``batch-run-manifest.json`` payload (FR-16) — the report derives from it.

    Top-level keys: ``schema_version``, ``comparison_mode``, ``generated_at`` (UTC iso), ``inputs``
    (frozen-input hashes), ``shared_preamble`` (status + artifact hashes + cost), ``models`` (each
    with FR-14 ``resolved_agents``, FR-15 ``seed_hash``, per-stage status/duration/cost(+source/
    confidence), the three ``cost_fields``, ``capability`` + ``score_breakdown``, ``error``),
    ``invalid_comparison``, ``aborted``, ``preflight_errors``, ``versions``, and ``report_paths``.

    All embedded free text (stage errors, model errors, resolved-agent values) is passed through
    ``redact_secrets`` (FR-19) before it lands in the manifest. This is the *contract*: any report or
    downstream consumer (FR-21 advancement, S7 CLI) reads this, not the raw artifacts.
    """
    shared = batch.shared
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "comparison_mode": comparison_mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "batch_root": str(batch_root),
        "inputs": dict(input_hashes),
        "shared_preamble": {
            "status": shared.status,
            "duration_s": shared.duration_s,
            "cost_usd": shared.cost_usd,
            "cost_source": shared.cost_source,
            "cost_confidence": shared.cost_confidence,
            "error": redact_secrets(shared.error) if shared.error else None,
            "artifact_hashes": dict(shared_artifact_hashes),
        },
        "models": [_model_manifest_entry(mr) for mr in batch.models],
        "advancement": _advancement_block(batch, gate),  # FR-21 tournament verdict
        "invalid_comparison": batch.invalid_comparison,
        "aborted": batch.aborted,
        "preflight_errors": [redact_secrets(e) for e in batch.preflight_errors],
        "versions": dict(versions),
        "report_paths": {
            "manifest": str(Path(batch_root) / MANIFEST_FILENAME),
            "report_json": str(Path(batch_root) / REPORT_JSON_FILENAME),
            "report_md": str(Path(batch_root) / REPORT_MD_FILENAME),
        },
    }


def _rank_models_from_manifest(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank manifest model blocks: capability score desc, then ``cost_attributable_usd`` asc (FR-9).

    Mirrors the spirit of ``model_comparison.rank_models``: a present, higher capability wins; ties
    break on cheaper attributable cost. Missing capability sorts last (treated as -inf); missing cost
    sorts last among ties (treated as +inf). Invalid-comparison / errored models are NOT dropped —
    they still appear, just ranked to the bottom by their (absent) signals.
    """

    def key(m: dict[str, Any]):
        cap = (m.get("capability") or {}).get("score")
        cost = (m.get("cost_fields") or {}).get("cost_attributable_usd")
        # invalid/errored models sort to the bottom regardless of any stray signal.
        invalid = m.get("invalid_comparison") or bool(m.get("error"))
        return (
            1 if invalid else 0,
            -(cap if isinstance(cap, (int, float)) else float("-inf")),
            cost if isinstance(cost, (int, float)) else float("inf"),
        )

    return sorted(models, key=key)


def _stage_status_in(model: dict[str, Any], stage_name: str) -> str:
    """The status string for ``stage_name`` in a manifest model block, or ``"—"`` if absent."""
    for s in model.get("stages", []):
        if s.get("stage") == stage_name:
            return s.get("status") or _NA
    return "—"


def _fmt_cost(value: Any, confidence: Optional[str] = None) -> str:
    """Format a cost field as ``$X.XXXX`` (+ a confidence tag), or ``N/A`` when missing."""
    if not isinstance(value, (int, float)):
        return _NA
    base = f"${_fmt(float(value), 4)}"
    if confidence and confidence != CONFIDENCE_HIGH:
        return f"{base} ({confidence})"
    return base


def _fmt_score(value: Any) -> str:
    """Format a [0,1] capability score, or ``N/A``."""
    return _fmt(float(value), 4) if isinstance(value, (int, float)) else _NA


def build_report_markdown(manifest: dict[str, Any]) -> str:
    """Human-readable ranked report derived from the manifest (FR-9).

    Header block states ``comparison_mode``, the FR-1 framing (frozen inputs + shared manifest;
    divergence begins at plan-ingestion), the single-run/INDICATIVE caveat (NR-3), the
    shared-manifest disclaimer, and a pointer to ``compare-models`` as the prime-only control. The
    per-model table is **ranked by capability score desc then ``cost_attributable_usd`` asc**, with
    columns: model | per-stage status | capability | capability_prime_only | cost_attributable |
    cost_total_loaded (footnote) | seed_hash (short). Missing values render ``N/A``; models flagged
    ``invalid_comparison`` / degraded are visibly marked, never silently dropped.
    """
    mode = manifest.get("comparison_mode", _UNKNOWN)
    versions = manifest.get("versions") or {}
    models = _rank_models_from_manifest(manifest.get("models") or [])
    advancement = manifest.get("advancement") or {}

    lines: list[str] = [
        "# End-to-End Pipeline Multi-Model Comparison",
        "",
        f"- Comparison mode: `{mode}`",
        f"- Generated (UTC): `{manifest.get('generated_at', _UNKNOWN)}`",
        f"- Models: {len(models)} | Execution: serial",
        f"- Versions: startd8 `{versions.get('startd8', _UNKNOWN)}` · "
        f"contextcore `{versions.get('contextcore', _UNKNOWN)}` · "
        f"git `{(versions.get('git_sha') or _UNKNOWN)[:12]}`"
        + (" (dirty)" if versions.get("git_dirty") else ""),
        "",
        "> **Framing (FR-1).** All models share **frozen inputs** and a single **shared manifest** "
        "(one contextcore preamble feeds every model). Divergence begins at **plan-ingestion**: each "
        "model produces its own enriched seed and its own generated code. This is NOT byte-identical "
        "prompts at every stage, and NOT per-model polished plans.",
        "",
        "> **Single-run, indicative — not statistical.** LLM sampling makes one run per model noisy; "
        "treat rankings as directional, not as production model selection.",
        "",
        "> **Shared-manifest disclaimer.** The contextcore preamble (polish/analyze/init) ran "
        "**once, shared, model-independent**; its cost is reported separately and is **excluded from "
        "the ranking key** (ranking uses `cost_attributable_usd` = plan-ingestion + prime).",
        "",
        "> **Prime-only control.** For an apples-to-apples generation-only comparison (no ingestion "
        "stage), see the `capability_prime_only` column and the `compare-models` command.",
        "",
        "> **Round-1 gate (FR-21).** "
        + (advancement.get("gate_description") or "not evaluated")
        + ". Models clearing this bar advance to the next tournament round; degrade-honest — a model "
        "with missing gate inputs does **not** advance (`inputs_missing`).",
        "",
    ]

    if manifest.get("aborted"):
        lines += [
            "> ⚠️ **Batch aborted** (shared preamble failed — no per-model work ran).",
            "",
        ]
    if manifest.get("invalid_comparison"):
        lines += [
            "> ⚠️ **INVALID COMPARISON** — two or more models collapsed to an identical seed hash "
            "(FR-15); affected rows are marked below.",
            "",
        ]
    preflight_errors = manifest.get("preflight_errors") or []
    if preflight_errors:
        lines.append("> ⚠️ **Preflight errors:** " + "; ".join(preflight_errors))
        lines.append("")

    lines += [
        "## Ranked comparison (best first: capability ↓, then attributable cost ↑)",
        "",
        "| Model | Ingestion | Prime | Capability | Capability (prime-only) | "
        "Cost (attributable) | Cost (total-loaded) † | Advanced | Seed |",
        "|---|---|---|---:|---:|---:|---:|:---:|---|",
    ]
    adv_models = advancement.get("models") or {}
    for m in models:
        cf = m.get("cost_fields") or {}
        cap = m.get("capability") or {}
        seed = m.get("seed_hash")
        seed_short = f"`{seed[:12]}`" if isinstance(seed, str) and seed else _NA
        adv_verdict = adv_models.get(m.get("model")) or {}
        if adv_verdict.get("advanced"):
            adv_cell = "✓"
        elif adv_verdict.get("reason") == REASON_INPUTS_MISSING:
            adv_cell = "✗ (inputs_missing)"
        else:
            adv_cell = "✗"
        marks = []
        if m.get("invalid_comparison"):
            marks.append("⚠️ invalid")
        if m.get("error"):
            marks.append("⚠️ degraded")
        label = m.get("model", _UNKNOWN)
        if marks:
            label = f"{label} ({', '.join(marks)})"
        lines.append(
            "| "
            + " | ".join(
                [
                    label,
                    _stage_status_in(m, STAGE_PLAN_INGESTION),
                    _stage_status_in(m, STAGE_PRIME),
                    _fmt_score(cap.get("score")),
                    _fmt_score(cap.get("capability_prime_only")),
                    _fmt_cost(
                        cf.get("cost_attributable_usd"),
                        cf.get("cost_attributable_confidence"),
                    ),
                    _fmt_cost(
                        cf.get("cost_total_loaded_usd"),
                        cf.get("cost_total_loaded_confidence"),
                    ),
                    adv_cell,
                    seed_short,
                ]
            )
            + " |"
        )

    lines += [
        "",
        "† **Total-loaded** = attributable + the shared preamble cost allocated to this model. It is "
        "a footnote, **not** the ranking key (the shared preamble is model-independent, so loading it "
        "onto each model would skew `$ / capability` by model count).",
        "",
    ]

    # FR-21: which models cleared the Round-1 gate (in ranked order; degrade-honest).
    advancing = [
        m.get("model")
        for m in models
        if (adv_models.get(m.get("model")) or {}).get("advanced")
    ]
    lines += [
        "**Advancing to next round:** "
        + (", ".join(f"`{name}`" for name in advancing) if advancing else "_none_")
        + ".",
        "",
    ]

    if not models:
        lines += ["_No model results to report._", ""]
    else:
        winner = models[0]
        if not (winner.get("invalid_comparison") or winner.get("error")):
            wcap = (winner.get("capability") or {}).get("score")
            wcost = (winner.get("cost_fields") or {}).get("cost_attributable_usd")
            lines += [
                "## Verdict",
                "",
                f"**Top-ranked: `{winner.get('model')}`** — capability {_fmt_score(wcap)}, "
                f"attributable cost {_fmt_cost(wcost)} (single-run, indicative).",
                "",
            ]

    return "\n".join(lines) + "\n"


def write_batch_outputs(
    batch: E2EBatchResult,
    batch_root: Path,
    *,
    comparison_mode: str = MANIFEST_FROZEN_V1,
    plan_paths: list[Path],
    requirements_paths: list[Path],
    shared_dir: Optional[Path] = None,
    gate: AdvancementGate = DEFAULT_ROUND1_GATE,
) -> dict[str, str]:
    """Orchestrate S6: freeze inputs → hash shared artifacts → build manifest → write report (FR-16/9).

    Writes, into ``batch_root``:

    - ``batch-run-manifest.json`` — the authoritative FR-16 contract;
    - ``comparison-report.json`` — the same manifest payload (the report's machine form);
    - ``comparison-report.md`` — the human ranked report derived from the manifest.

    Also archives the frozen inputs into ``batch/_inputs/`` (FR-16 / R3-F2) and computes the FR-21
    Round-1 advancement verdict (via ``apply_advancement(batch, gate)``) so it is persisted in the
    manifest's ``advancement`` block and surfaced in the report. ``gate`` defaults to
    ``DEFAULT_ROUND1_GATE``; a caller (the S7 CLI) passes a gate built from ``--advance-threshold``.
    Returns a mapping of logical name → written path (``manifest`` / ``report_json`` / ``report_md`` /
    ``inputs_dir``). This is what the S7 CLI calls after ``score_batch``.
    """
    batch_root = Path(batch_root)
    batch_root.mkdir(parents=True, exist_ok=True)
    if shared_dir is None:
        shared_dir = batch_root / SHARED_DIRNAME

    input_hashes = write_inputs_archive(plan_paths, requirements_paths, batch_root)
    shared_artifact_hashes = hash_shared_artifacts(shared_dir)
    versions = collect_versions()

    # FR-21: compute + stash the Round-1 advancement verdict before building the manifest so the
    # verdict (and per-model ``advanced``) is persisted.
    apply_advancement(batch, gate)

    manifest = build_manifest(
        batch,
        comparison_mode=comparison_mode,
        input_hashes=input_hashes,
        shared_artifact_hashes=shared_artifact_hashes,
        versions=versions,
        batch_root=batch_root,
        gate=gate,
    )

    manifest_path = batch_root / MANIFEST_FILENAME
    report_json_path = batch_root / REPORT_JSON_FILENAME
    report_md_path = batch_root / REPORT_MD_FILENAME

    manifest_text = json.dumps(manifest, indent=2)
    manifest_path.write_text(manifest_text, encoding="utf-8")
    # comparison-report.json IS the manifest payload (the report's machine form).
    report_json_path.write_text(manifest_text, encoding="utf-8")
    report_md_path.write_text(build_report_markdown(manifest), encoding="utf-8")

    logger.info(
        "wrote batch outputs to %s (%d model(s), mode=%s)",
        batch_root,
        len(batch.models),
        comparison_mode,
    )
    return {
        "manifest": str(manifest_path),
        "report_json": str(report_json_path),
        "report_md": str(report_md_path),
        "inputs_dir": str(batch_root / INPUTS_DIRNAME),
    }
