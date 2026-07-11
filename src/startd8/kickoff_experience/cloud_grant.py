"""M0 — the CloudGrant primitive: a human-issued, use-limited, expiring, revocable, server-side
authorization that temporarily lets a **cloud** kickoff deployment perform an otherwise cloud-denied
capability (the agentic chat-write path). This module is the **primitive only** — the web-serve wiring
(the ``_cloud_capability`` seam, the trust chain, the CLI issuance surface) is M1–M5.

Design contract — ``CLOUD_MIRROR_GRANT_REQUIREMENTS.md`` v0.4:

- **FR-7 (single-atomic consume, no replay):** :meth:`GrantStore.resolve_and_consume` resolves + decrements
  in **one atomic op** under a lock. **Consume-before-act**; the store never refunds (a refund is a
  replay vector) — so a use is **forfeit** if the caller's action then fails. A **store failure during
  consume ⇒ deny with no use debited** (the decrement is committed to memory only after ``_persist``).
  Mirrors the ``consultation/serve.py`` consume-before-act/anti-replay nonce pattern (FR-SRV-5) — a
  server-side counter, never a signed claim.
- **FR-8 (least-privilege, target-bound):** scope is the normative ``GrantTarget{deployment_id,
  project_id, capability}``; a grant for one target can never satisfy a request for another (mismatch → deny).
- **FR-5 (fail-closed):** every one of {absent, expired, exhausted, revoked, store-unavailable,
  clock-untrusted} is an independent, typed **deny** (:class:`GrantDeny`).
- **FR-15 / OQ-7 (per-action re-validation):** :meth:`GrantStore.revalidate` re-checks a grant's liveness
  **without consuming** — a session consumes ONE use at creation, then re-validates (not re-consumes)
  every turn/apply, so a session created just before expiry is denied on its next action.

The clock is **injected** (`now: float`, epoch seconds) so expiry is testable; a caller that cannot
trust its clock passes ``clock_trusted=False`` → deny (FR-5).
"""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass, replace
from enum import Enum
from typing import Dict, Optional


# --------------------------------------------------------------------------- scope + record


@dataclass(frozen=True)
class GrantTarget:
    """The normative least-privilege scope a grant is bound to (FR-8). Equality is the match rule:
    a grant satisfies a request iff the requesting target equals the grant's target."""

    deployment_id: str
    project_id: str
    capability: str


@dataclass(frozen=True)
class CloudGrant:
    """A single temporary authorization. Immutable — consumption/revocation produce a new record so a
    partially-applied mutation can never be observed (the store swaps the reference atomically)."""

    id: str
    target: GrantTarget
    uses_remaining: int
    expires_at: float          # absolute epoch seconds (trusted server clock)
    issued_by: str             # issuer label (FR-6/FR-10) — attributable to the credential holder
    issued_at: float
    revoked: bool = False

    def is_live(self, now: float) -> Optional["GrantDeny"]:
        """None if live; otherwise the specific deny reason (FR-5). Does not consider uses."""
        if self.revoked:
            return GrantDeny.REVOKED
        if now >= self.expires_at:
            return GrantDeny.EXPIRED
        return None


# --------------------------------------------------------------------------- decision


class GrantDeny(str, Enum):
    """The typed, independent deny reasons (FR-5). ``str`` so it serializes to a stable audit token."""

    ABSENT = "absent"                     # no grant for this target+capability
    EXPIRED = "expired"
    EXHAUSTED = "exhausted"               # uses_remaining == 0
    REVOKED = "revoked"
    TARGET_MISMATCH = "target_mismatch"   # a grant id was presented but bound to a different target
    STORE_UNAVAILABLE = "store_unavailable"
    CLOCK_UNTRUSTED = "clock_untrusted"
    # M2 trust-chain factors that fail BEFORE the grant is touched (FR-14):
    API_KEY_INVALID = "api_key_invalid"   # (1) consumer --api-key absent/mismatched
    ORIGIN_REJECTED = "origin_rejected"   # (4) Host/Origin not in the configured cloud origin


@dataclass(frozen=True)
class GrantDecision:
    """The typed result of a resolve/revalidate — allow, or a specific deny reason. Mirrors the seam's
    ``Decision`` (FR-13) so the caller never re-derives posture."""

    allowed: bool
    reason: Optional[GrantDeny] = None
    grant_id: Optional[str] = None
    uses_remaining_after: Optional[int] = None

    @staticmethod
    def deny(reason: GrantDeny) -> "GrantDecision":
        return GrantDecision(False, reason=reason)


class StoreUnavailable(Exception):
    """Raised by a persistence backend when it cannot read/write. Caught by the store → deny, no debit."""


# --------------------------------------------------------------------------- store


class GrantStore:
    """In-memory, thread-safe grant store — the reference implementation + test double.

    A persistence backend overrides :meth:`_persist` (write one grant durably). The base keeps grants in
    a dict guarded by a re-entrant lock; the **resolve+decrement critical section is fully serialized**,
    so N concurrent redemptions of a 1-use grant yield **exactly one** allow (FR-7). The decrement is
    committed to the in-memory map **only after** ``_persist`` succeeds, so a persist failure rolls back
    with no use debited (FR-7 store-unavailable-mid-consume).
    """

    def __init__(self) -> None:
        self._grants: Dict[str, CloudGrant] = {}
        self._lock = threading.Lock()

    # -- persistence seam (no-op for the in-memory reference; a file/db backend overrides) --
    def _persist(self, grant: CloudGrant) -> None:  # pragma: no cover - overridden by real backends
        """Durably write *grant*. Raise :class:`StoreUnavailable` if it cannot be written."""
        return None

    # -- issuance (M4 wires the human/operator surface; the primitive lives here) --
    def issue(
        self,
        target: GrantTarget,
        *,
        uses: int = 1,
        ttl_seconds: float,
        now: float,
        issued_by: str,
    ) -> CloudGrant:
        """Mint a grant (default **1 use**, FR-2) expiring at ``now + ttl_seconds`` (FR-3). Persisted
        before it is observable; a persist failure raises (issuance fails closed, FR-10)."""
        if uses < 1:
            raise ValueError("a grant must have at least 1 use")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        grant = CloudGrant(
            id=secrets.token_urlsafe(16),
            target=target,
            uses_remaining=int(uses),
            expires_at=now + ttl_seconds,
            issued_by=issued_by,
            issued_at=now,
        )
        with self._lock:
            self._persist(grant)           # fail-closed: no in-memory entry unless persisted
            self._grants[grant.id] = grant
        return grant

    def revoke(self, grant_id: str) -> bool:
        """Immediately void a grant (FR-4). Returns False if unknown. Idempotent."""
        with self._lock:
            g = self._grants.get(grant_id)
            if g is None:
                return False
            revoked = replace(g, revoked=True)
            self._persist(revoked)
            self._grants[grant_id] = revoked
            return True

    def get(self, grant_id: str) -> Optional[CloudGrant]:
        with self._lock:
            return self._grants.get(grant_id)

    # -- the atomic resolve+consume (session creation, FR-7/FR-15) --
    def resolve_and_consume(
        self,
        target: GrantTarget,
        *,
        now: float,
        clock_trusted: bool = True,
    ) -> GrantDecision:
        """Atomically resolve a live grant for *target* and **consume one use**. One allow per use;
        every failure mode is a typed deny with **no debit** (FR-5/FR-7)."""
        if not clock_trusted:
            return GrantDecision.deny(GrantDeny.CLOCK_UNTRUSTED)
        with self._lock:
            grant = self._find_for_target(target)
            if grant is None:
                return GrantDecision.deny(GrantDeny.ABSENT)
            live = grant.is_live(now)
            if live is not None:
                return GrantDecision.deny(live)
            if grant.uses_remaining <= 0:
                return GrantDecision.deny(GrantDeny.EXHAUSTED)
            consumed = replace(grant, uses_remaining=grant.uses_remaining - 1)
            try:
                self._persist(consumed)                 # may raise StoreUnavailable
            except StoreUnavailable:
                return GrantDecision.deny(GrantDeny.STORE_UNAVAILABLE)  # no debit — rollback
            self._grants[grant.id] = consumed           # commit only after persist
            return GrantDecision(
                True, grant_id=grant.id, uses_remaining_after=consumed.uses_remaining
            )

    # -- per-action re-validation (per-turn/apply; NO consume, FR-15/OQ-7) --
    def revalidate(
        self,
        grant_id: str,
        target: GrantTarget,
        *,
        now: float,
        clock_trusted: bool = True,
    ) -> GrantDecision:
        """Re-check that the session's grant is still live for *target* **without consuming** — so a
        session created just before expiry/revocation is denied on its next action, without spending a
        second use. Also enforces target binding (a grant id bound to a different target → deny, FR-8)."""
        if not clock_trusted:
            return GrantDecision.deny(GrantDeny.CLOCK_UNTRUSTED)
        with self._lock:
            grant = self._grants.get(grant_id)
            if grant is None:
                return GrantDecision.deny(GrantDeny.ABSENT)
            if grant.target != target:
                return GrantDecision.deny(GrantDeny.TARGET_MISMATCH)
            live = grant.is_live(now)
            if live is not None:
                return GrantDecision.deny(live)
            return GrantDecision(
                True, grant_id=grant.id, uses_remaining_after=grant.uses_remaining
            )

    # -- internal --
    def _find_for_target(self, target: GrantTarget) -> Optional[CloudGrant]:
        """The newest grant bound to exactly *target* (FR-8 match rule). A grant for a different
        deployment/project/capability is never returned — mismatch denies by construction."""
        best: Optional[CloudGrant] = None
        for g in self._grants.values():
            if g.target == target and (best is None or g.issued_at > best.issued_at):
                best = g
        return best


# --------------------------------------------------------------------------- FR-14 trust chain (M2)


@dataclass(frozen=True)
class TrustChainInputs:
    """The per-request factors of the cloud-write trust chain (FR-14). Assembled from the request +
    the served app's config; the grant is a separate factor resolved from the store."""

    api_key_expected: Optional[str]     # the served app's configured consumer --api-key
    api_key_presented: Optional[str]    # the request's X-API-Key
    allowed_origins: frozenset          # the configured cloud origin(s)
    origin_presented: Optional[str]     # the request's Origin/Host


def evaluate_trust_chain(
    store: Optional[GrantStore],
    target: GrantTarget,
    inputs: TrustChainInputs,
    *,
    now: float,
    clock_trusted: bool = True,
) -> GrantDecision:
    """The **ordered AND-gate** (FR-14, R1-F1): a cloud write is honored **iff ALL of** —
    (1) api-key valid **AND** (4) Origin ∈ configured **AND** (2)(3) a live grant resolves — and the
    grant is **consumed** (this is the session-creation trust chain). Absence/failure of **any** factor
    ⇒ a typed deny with **no consume** (factors 1 & 4 short-circuit before the grant is touched).

    Note the ordering: api-key and Origin are checked **before** the store so a bad-key / bad-Origin
    request never spends a use (and never even probes the grant store — no existence oracle).
    """
    if store is None:
        return GrantDecision.deny(GrantDeny.ABSENT)              # not grant-capable → deny
    # (1) consumer api-key — required and matched.
    if not inputs.api_key_expected or inputs.api_key_presented != inputs.api_key_expected:
        return GrantDecision.deny(GrantDeny.API_KEY_INVALID)
    # (4) Origin/Host ∈ configured cloud origin.
    if not inputs.allowed_origins or inputs.origin_presented not in inputs.allowed_origins:
        return GrantDecision.deny(GrantDeny.ORIGIN_REJECTED)
    # (2)(3) a live grant resolves for target+capability → consume one use (single-atomic).
    return store.resolve_and_consume(target, now=now, clock_trusted=clock_trusted)
