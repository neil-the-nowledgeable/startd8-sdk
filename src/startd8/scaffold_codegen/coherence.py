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
            ))
        elif kind == "sqlite-memory":
            findings.append(CoherenceFinding(
                WARN, "deployed-sqlite-memory",
                "deployed mode with an in-memory SQLite persistence — acceptable only for "
                "ephemeral/test runs; a real deployment needs a shared database.",
            ))
        if not manifest.migrations:
            findings.append(CoherenceFinding(
                ERROR, "deployed-no-migrations",
                "deployed mode with migrations disabled: a shared DB must not auto-create_all "
                "(FR-PER-3). Enable migrations (migrations.enabled: true).",
            ))
        if has_auth_seam and not has_tenant:
            findings.append(CoherenceFinding(
                WARN, "deployed-auth-no-tenant",
                "deployed mode emits the auth seam but no deployment.tenant is declared: "
                "AUTHENTICATED BUT NOT TENANT-ISOLATED — every principal can read all rows "
                "(legal only for a single-owner / shared-read-only app).",
            ))
    elif mode == "installed":
        if kind == "shared":
            findings.append(CoherenceFinding(
                ERROR, "installed-shared-dsn",
                f"installed (single-user) mode declares a shared-DB persistence ({manifest.db_path!r}); "
                "installed apps have no pool/isolation posture. Use deployed mode for a shared database.",
            ))
        if has_auth_seam or has_tenant:
            findings.append(CoherenceFinding(
                ERROR, "installed-auth-requested",
                "installed (single-user) mode with auth/tenancy requested — installed apps are "
                "single-owner by definition (NR-3). Use deployed mode.",
            ))
    return tuple(findings)


def has_errors(findings: Tuple[CoherenceFinding, ...]) -> bool:
    return any(f.severity == ERROR for f in findings)
