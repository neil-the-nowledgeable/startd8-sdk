"""Deployment-mode coherence guard — the FR-CFG-5 normative ERROR/WARN/OK matrix.

Evaluates the declared deployment mode against what is **knowable at build time** from ``app.yaml``:
persistence DSN (``persistence.path``), migrations posture (``migrations.enabled``), and — when the
caller knows them — the auth-seam/tenant facts. Incoherent ERROR combinations fail the build; WARN
combinations proceed loudly. Pure/deterministic; consumed by ``generate backend`` and ``wireframe``.

The bind and auth/tenant rows are structurally present but **dormant** until those inputs exist
(auth seam = M2/A6; ``deployment.tenant`` = Tier B/M3) — callers pass ``has_auth_seam``/``has_tenant``
once those land. See DEPLOYMENT_MODE_REQUIREMENTS.md §3.A FR-CFG-5.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from .manifest import AppManifest

ERROR = "ERROR"
WARN = "WARN"

# Severity TIER (orthogonal to ERROR/WARN) — tagged at source so the cap-dev-pipe deploy-coherence
# gate can collapse to HARD/SOFT/warn (REQ-CDP-DEPLOY-7/10, cloud-native FR-CND-30). The 3-value
# taxonomy is richer-at-source and future-proofs the OQ-6 deployability trend at no extra cost.
#   security    → a security-critical posture (auth bypass, isolation gap). ERROR+security ⇒ HARD.
#   operational → a correctness/ops posture (data loss, concurrency, missing migrations). ERROR ⇒ SOFT.
#   advisory    → informational only.
SECURITY = "security"
OPERATIONAL = "operational"
ADVISORY = "advisory"

# Verdict + exit-code contract consumed by `scripts/check_deploy_coherence.py --json` and, downstream,
# the cap-dev-pipe gate. Exit codes mirror `check_seed_quality.py`'s convention, extended with `3`.
VERDICT_OK = "ok"      # exit 0 — no blocking deploy finding
VERDICT_SOFT = "soft"  # exit 1 — operational ERROR (overridable downstream)
VERDICT_SKIP = "skip"  # exit 2 — not a deployed posture (deploy gate N/A)
VERDICT_HARD = "hard"  # exit 3 — security-critical ERROR (NON-overridable downstream)

_VERDICT_EXIT = {VERDICT_OK: 0, VERDICT_SOFT: 1, VERDICT_SKIP: 2, VERDICT_HARD: 3}

# DSN scheme prefixes that denote a shared/server database (vs a single-writer SQLite file).
_SHARED_SCHEMES = (
    "postgres://", "postgresql://", "postgresql+", "mysql://", "mysql+",
    "mariadb://", "cockroachdb://", "cockroach://",
)


@dataclass(frozen=True)
class CoherenceFinding:
    severity: str  # "ERROR" | "WARN"
    code: str
    message: str
    severity_tier: str = OPERATIONAL  # "security" | "operational" | "advisory" (REQ-CDP-DEPLOY-7)


def _persistence_kind(db_path: str) -> str:
    """Classify the declared persistence DSN: ``shared`` | ``sqlite-memory`` | ``sqlite-file``."""
    s = (db_path or "").strip().lower()
    if s.startswith(_SHARED_SCHEMES):
        return "shared"
    if ":memory:" in s or s == "sqlite://":
        return "sqlite-memory"
    return "sqlite-file"


def evaluate_coherence(
    manifest: AppManifest, *, has_auth_seam: bool = False, has_tenant: bool = False
) -> Tuple[CoherenceFinding, ...]:
    """The FR-CFG-5 matrix over the build-time-knowable axes (mode × persistence × migrations × auth)."""
    findings = []
    mode = manifest.deployment_mode
    kind = _persistence_kind(manifest.db_path)

    if mode == "deployed":
        if kind == "sqlite-file":
            findings.append(CoherenceFinding(
                ERROR, "deployed-sqlite-file",
                f"deployed mode declares a single-writer SQLite file persistence ({manifest.db_path!r}); "
                "under shared concurrency this corrupts/loses writes. Declare a shared DSN "
                "(e.g. persistence.path: postgresql://…).",
                severity_tier=OPERATIONAL,
            ))
        elif kind == "sqlite-memory":
            findings.append(CoherenceFinding(
                WARN, "deployed-sqlite-memory",
                "deployed mode with an in-memory SQLite persistence — acceptable only for "
                "ephemeral/test runs; a real deployment needs a shared database.",
                severity_tier=OPERATIONAL,
            ))
        if not manifest.migrations:
            findings.append(CoherenceFinding(
                ERROR, "deployed-no-migrations",
                "deployed mode with migrations disabled: a shared DB must not auto-create_all "
                "(FR-PER-3). Enable migrations (migrations.enabled: true).",
                severity_tier=OPERATIONAL,
            ))
        if has_auth_seam and not manifest.deploy_trust_gateway:
            findings.append(CoherenceFinding(
                ERROR, "deployed-decode-only-no-gateway-ack",
                "deployed mode emits the DECODE-ONLY auth seam (it does not verify JWT signatures), "
                "but `deploy.trust_gateway` is not acknowledged and no gateway-fronting network guard "
                "is declared: direct exposure is an AUTH BYPASS — any attacker-minted token is trusted. "
                "Set `deploy.trust_gateway: true` (a verifying gateway/agentgateway fronts the app) or "
                "emit the ClusterIP + NetworkPolicy guard (FR-CND-6).",
                severity_tier=SECURITY,
            ))
        # M3: per-env secrets-scope consistency. If SOME environments pin a secrets_config and others
        # don't, the unpinned ones fall back to the shared base SecretStore ref — so e.g. prod could
        # silently share dev's secret scope. Flag the gap (FR-ENV-7 / R1-S6).
        specs = manifest.deploy_environment_specs
        if specs:
            pinned = [s.name for s in specs if s.secrets_config]
            unpinned = [s.name for s in specs if not s.secrets_config]
            if pinned and unpinned:
                findings.append(CoherenceFinding(
                    WARN, "env-inconsistent-secrets-scope",
                    "some environments pin `deploy.environments.<env>.secrets_config` but these do not: "
                    f"{sorted(unpinned)} — they fall back to the shared base secret scope, which can "
                    "leak one environment's secrets into another. Pin a per-env secrets_config for each.",
                    severity_tier=SECURITY,
                ))
        if has_auth_seam and not has_tenant:
            findings.append(CoherenceFinding(
                WARN, "deployed-auth-no-tenant",
                "deployed mode emits the auth seam but no deployment.tenant is declared: "
                "AUTHENTICATED BUT NOT TENANT-ISOLATED — every principal can read all rows "
                "(legal only for a single-owner / shared-read-only app).",
                severity_tier=SECURITY,
            ))
    elif mode == "installed":
        if kind == "shared":
            findings.append(CoherenceFinding(
                ERROR, "installed-shared-dsn",
                f"installed (single-user) mode declares a shared-DB persistence ({manifest.db_path!r}); "
                "installed apps have no pool/isolation posture. Use deployed mode for a shared database.",
                severity_tier=OPERATIONAL,
            ))
        if has_auth_seam or has_tenant:
            findings.append(CoherenceFinding(
                ERROR, "installed-auth-requested",
                "installed (single-user) mode with auth/tenancy requested — installed apps are "
                "single-owner by definition (NR-3). Use deployed mode.",
                severity_tier=OPERATIONAL,
            ))
        if manifest.deploy_environments:
            findings.append(CoherenceFinding(
                ERROR, "installed-with-environments",
                "installed (single-user) mode declares `deploy.environments` — environments are a "
                "deployed-only concern (one local environment for installed). Use deployed mode or "
                "remove the environments block (FR-ENV-2).",
                severity_tier=OPERATIONAL,
            ))
    return tuple(findings)


def has_errors(findings: Tuple[CoherenceFinding, ...]) -> bool:
    return any(f.severity == ERROR for f in findings)


def deploy_coherence_verdict(
    findings: Tuple[CoherenceFinding, ...], *, mode: str
) -> Tuple[str, int]:
    """Collapse findings to a (verdict, exit_code) for the deploy-coherence gate.

    Only ``deployed`` postures are gated (installed has no ``deploy/`` tree → skip). A
    **security-tier ERROR** is HARD (non-overridable downstream); any other ERROR is SOFT;
    WARN/advisory never block. The mapping — not the raw severity — is the cross-repo Keiyaku
    contract (REQ-CDP-DEPLOY-6/7/10, FR-CND-30).
    """
    if mode != "deployed":
        return VERDICT_SKIP, _VERDICT_EXIT[VERDICT_SKIP]
    if any(f.severity == ERROR and f.severity_tier == SECURITY for f in findings):
        return VERDICT_HARD, _VERDICT_EXIT[VERDICT_HARD]
    if any(f.severity == ERROR for f in findings):
        return VERDICT_SOFT, _VERDICT_EXIT[VERDICT_SOFT]
    return VERDICT_OK, _VERDICT_EXIT[VERDICT_OK]


def finding_to_dict(f: CoherenceFinding) -> dict:
    """Serialize a finding for the ``--json`` verdict (``severity_tier`` is always present)."""
    return {
        "severity": f.severity,
        "severity_tier": f.severity_tier,
        "code": f.code,
        "message": f.message,
    }
