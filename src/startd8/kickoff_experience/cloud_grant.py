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

import json
import os
import secrets
import tempfile
import threading
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, Optional


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
    link_token: Optional[str] = None   # FR-E12: a one-time browser bearer that authorizes redeeming
    #                                    this grant via the human door (`--with-link`). None = no door.

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

    def __init__(self, audit: "Optional[Callable[[dict], None]]" = None,
                 metrics: "Optional[Callable[[str, Optional[str]], None]]" = None) -> None:
        self._grants: Dict[str, CloudGrant] = {}
        self._lock = threading.RLock()
        self._audit_cb = audit
        # FR-E4: optional OTel metrics sink, called (event, reason). Distinct from _audit: audit is
        # FAIL-CLOSED (an un-auditable elevation must not proceed); metrics are FAIL-OPEN (a telemetry
        # hiccup must NEVER affect a grant decision) — the two concerns must not be conflated.
        self._metrics_cb = metrics

    def _emit_metric(self, event: str, reason: "Optional[str]" = None) -> None:
        """FR-E4 — record a lifecycle metric. Fail-open by construction: any error is swallowed."""
        if self._metrics_cb is None:
            return
        try:
            self._metrics_cb(event, reason)
        except Exception:  # metrics must never break a grant decision
            pass

    def _denied(self, reason: "GrantDeny") -> "GrantDecision":
        """Emit a denial metric (by reason) and return the typed deny — a single choke point so every
        deny path is counted without rewriting each return."""
        self._emit_metric("deny", reason.value)
        return GrantDecision.deny(reason)

    # -- persistence seam (no-op for the in-memory reference; a file/db backend overrides) --
    def _persist(self, grant: CloudGrant) -> None:  # pragma: no cover - overridden by real backends
        """Durably write *grant*. Raise :class:`StoreUnavailable` if it cannot be written."""
        return None

    # -- op bracket (M4): every state op runs under the thread lock + an inter-process lock, and
    #    re-syncs from the durable backend first, so a CLI-issued grant is visible and consume is atomic
    #    across processes (the anti-replay guarantee holds for multi-instance, not just multi-thread). --
    def _interprocess_lock(self):  # pragma: no cover - overridden by the file backend
        return nullcontext()

    def _sync(self) -> None:  # pragma: no cover - overridden by the file backend
        """Reload the durable state (no-op for the in-memory reference)."""
        return None

    @contextmanager
    def _op(self):
        with self._lock, self._interprocess_lock():
            self._sync()
            yield

    def _audit(self, **event) -> None:
        """Record an audit event (FR-10). **Fail-closed:** if the callback raises, it propagates —
        issuance/consume/revoke must NOT proceed on an un-auditable elevation (R1-F7/R1-S6)."""
        if self._audit_cb is not None:
            self._audit_cb(dict(event))

    # -- issuance (M4 wires the human/operator surface; the primitive lives here) --
    def issue(
        self,
        target: GrantTarget,
        *,
        uses: int = 1,
        ttl_seconds: float,
        now: float,
        issued_by: str,
        link_token: "Optional[str]" = None,
    ) -> CloudGrant:
        """Mint a grant (default **1 use**, FR-2) expiring at ``now + ttl_seconds`` (FR-3). Persisted
        before it is observable; a persist failure raises (issuance fails closed, FR-10).

        *link_token* (FR-E12) binds a one-time browser bearer so the grant can be redeemed via the
        human door; omit it for the programmatic (api-key + Origin) path — behavior is unchanged."""
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
            link_token=link_token,
        )
        with self._op():
            # audit BEFORE persist — an un-auditable issuance must not create a grant (fail-closed).
            self._audit(event="issue", grant_id=grant.id, deployment_id=target.deployment_id,
                        project_id=target.project_id, capability=target.capability,
                        uses=int(uses), expires_at=grant.expires_at, issued_by=issued_by, at=now)
            self._persist(grant)           # fail-closed: no in-memory entry unless persisted
            self._grants[grant.id] = grant
        self._emit_metric("issue")         # FR-E4 (fail-open, after the grant is durable)
        return grant

    def revoke(self, grant_id: str) -> bool:
        """Immediately void a grant (FR-4). Returns False if unknown. Idempotent."""
        with self._op():
            g = self._grants.get(grant_id)
            if g is None:
                return False
            revoked = replace(g, revoked=True)
            self._audit(event="revoke", grant_id=grant_id, at_uses_remaining=g.uses_remaining)
            self._persist(revoked)
            self._grants[grant_id] = revoked
            self._emit_metric("revoke")    # FR-E4
            return True

    def get(self, grant_id: str) -> Optional[CloudGrant]:
        with self._op():
            return self._grants.get(grant_id)

    def _flush(self) -> None:  # pragma: no cover - overridden by the file backend
        """Durably write the WHOLE current grant set (used by :meth:`prune`, which removes records)."""
        return None

    def prune(self, now: float) -> int:
        """GC: drop expired / exhausted / revoked grants. Best-effort (a flush failure leaves the dead
        records on disk — harmless, they deny anyway). Returns the count removed."""
        with self._op():
            dead = [gid for gid, g in self._grants.items()
                    if g.revoked or g.uses_remaining <= 0 or now >= g.expires_at]
            for gid in dead:
                self._grants.pop(gid, None)
            if dead:
                self._flush()
            return len(dead)

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
            return self._denied(GrantDeny.CLOCK_UNTRUSTED)
        try:
            return self._resolve_and_consume(target, now)
        except StoreUnavailable:                        # a durable-backend read failure (`_sync`) → deny
            return self._denied(GrantDeny.STORE_UNAVAILABLE)

    def _resolve_and_consume(self, target: GrantTarget, now: float) -> GrantDecision:
        with self._op():
            grant = self._find_for_target(target)
            if grant is None:
                return self._denied(GrantDeny.ABSENT)
            live = grant.is_live(now)
            if live is not None:
                return self._denied(live)
            if grant.uses_remaining <= 0:
                return self._denied(GrantDeny.EXHAUSTED)
            consumed = replace(grant, uses_remaining=grant.uses_remaining - 1)
            try:
                # audit BEFORE persist; an un-auditable consume denies with no debit (R1-S6 fail-closed).
                self._audit(event="consume", grant_id=grant.id,
                            uses_remaining_after=consumed.uses_remaining, at=now)
                self._persist(consumed)                 # may raise StoreUnavailable
            except StoreUnavailable:
                return self._denied(GrantDeny.STORE_UNAVAILABLE)  # no debit — rollback
            self._grants[grant.id] = consumed           # commit only after persist
            self._emit_metric("consume")                # FR-E4 (one use spent, session created)
            return GrantDecision(
                True, grant_id=grant.id, uses_remaining_after=consumed.uses_remaining
            )

    # -- the human-door redemption (FR-E12): consume + BURN the one-time link token, atomically --
    def redeem_link(
        self,
        token: str,
        target: GrantTarget,
        *,
        now: float,
        clock_trusted: bool = True,
    ) -> GrantDecision:
        """Redeem a one-time link *token* for *target*: resolve the grant it is bound to, **consume one
        use AND burn the token** in a single locked critical section, and bind the returned ``grant_id``
        to the browser session (per-turn actions then REVALIDATE it, no re-consume). Every failure —
        unknown/burned token, wrong target, expired/revoked/exhausted grant — is a typed deny with **no
        debit and no token burn** (the caller shows one generic message; no existence oracle, FR-6)."""
        if not token or not clock_trusted:
            return self._denied(GrantDeny.CLOCK_UNTRUSTED if token else GrantDeny.ABSENT)
        try:
            return self._redeem_link(token, target, now)
        except StoreUnavailable:
            return self._denied(GrantDeny.STORE_UNAVAILABLE)

    def _redeem_link(self, token: str, target: GrantTarget, now: float) -> GrantDecision:
        with self._op():
            grant = self._find_by_link_token(token)
            if grant is None:
                return self._denied(GrantDeny.ABSENT)          # unknown or already-burned token
            if grant.target != target:
                return self._denied(GrantDeny.TARGET_MISMATCH)  # token for a different deployment/cap
            live = grant.is_live(now)
            if live is not None:
                return self._denied(live)
            if grant.uses_remaining <= 0:
                return self._denied(GrantDeny.EXHAUSTED)
            # consume one use AND burn the token together — the link is strictly one-time even if the
            # grant has uses left; a re-click finds no token (ABSENT), never a partially-applied state.
            redeemed = replace(grant, uses_remaining=grant.uses_remaining - 1, link_token=None)
            try:
                self._audit(event="redeem_link", grant_id=grant.id,
                            uses_remaining_after=redeemed.uses_remaining, at=now)
                self._persist(redeemed)                         # may raise StoreUnavailable
            except StoreUnavailable:
                return self._denied(GrantDeny.STORE_UNAVAILABLE)  # no debit, no burn — rollback
            self._grants[grant.id] = redeemed                   # commit only after persist
            self._emit_metric("consume")                        # FR-E4 (a session was created)
            return GrantDecision(
                True, grant_id=grant.id, uses_remaining_after=redeemed.uses_remaining
            )

    def _find_by_link_token(self, token: str) -> Optional[CloudGrant]:
        """The grant whose (unburned) link token equals *token*, compared in constant time to avoid a
        timing oracle. Returns None if none match (unknown or already-burned)."""
        match: Optional[CloudGrant] = None
        for g in self._grants.values():
            if g.link_token is not None and secrets.compare_digest(g.link_token, token):
                match = g
        return match

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
            return self._denied(GrantDeny.CLOCK_UNTRUSTED)
        try:
            return self._revalidate(grant_id, target, now)
        except StoreUnavailable:                        # a durable-backend read failure (`_sync`) → deny
            return self._denied(GrantDeny.STORE_UNAVAILABLE)

    def _revalidate(self, grant_id: str, target: GrantTarget, now: float) -> GrantDecision:
        with self._op():
            grant = self._grants.get(grant_id)
            if grant is None:
                return self._denied(GrantDeny.ABSENT)
            if grant.target != target:
                return self._denied(GrantDeny.TARGET_MISMATCH)
            live = grant.is_live(now)
            if live is not None:
                return self._denied(live)
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
        return store._denied(GrantDeny.API_KEY_INVALID)          # FR-E4: count the auth-layer deny too
    # (4) Origin/Host ∈ configured cloud origin.
    if not inputs.allowed_origins or inputs.origin_presented not in inputs.allowed_origins:
        return store._denied(GrantDeny.ORIGIN_REJECTED)
    # (2)(3) a live grant resolves for target+capability → consume one use (single-atomic).
    return store.resolve_and_consume(target, now=now, clock_trusted=clock_trusted)


# --------------------------------------------------------------------------- FR-E4 OTel metrics


class GrantMetrics:
    """FR-E4 — OTel counters for the cloud-grant lifecycle, usable as a :class:`GrantStore` ``metrics``
    sink (it is callable as ``(event, reason)``). Four counters:

    - ``startd8.cloud_grant.issued`` — grants minted (emitted by the issuance CLI process).
    - ``startd8.cloud_grant.consumed`` — uses spent at session creation (the served app).
    - ``startd8.cloud_grant.denied`` — write attempts denied, **labelled by ``reason``** (the
      :class:`GrantDeny` value): the panel's discriminating series (a spike in ``origin_rejected`` vs
      ``exhausted`` vs ``expired`` tells very different stories).
    - ``startd8.cloud_grant.revoked`` — grants voided by a human.

    **Fail-open by construction:** if OpenTelemetry isn't installed or no ``MeterProvider`` is
    configured, construction/record degrade to silent no-ops — a metrics gap never touches a grant."""

    def __init__(self, meter: object = None) -> None:
        self._ready = False
        try:
            if meter is None:
                from opentelemetry import metrics as _otel_metrics

                meter = _otel_metrics.get_meter("startd8.cloud_grant")
            self._issued = meter.create_counter(
                "startd8.cloud_grant.issued", description="Cloud grants issued")
            self._consumed = meter.create_counter(
                "startd8.cloud_grant.consumed", description="Cloud grant uses consumed (session creation)")
            self._denied = meter.create_counter(
                "startd8.cloud_grant.denied", description="Cloud grant write attempts denied, by reason")
            self._revoked = meter.create_counter(
                "startd8.cloud_grant.revoked", description="Cloud grants revoked")
            self._ready = True
        except Exception:  # OTel absent / no provider — degrade to a no-op sink
            self._ready = False

    def __call__(self, event: str, reason: "Optional[str]" = None) -> None:
        if not self._ready:
            return
        try:
            if event == "issue":
                self._issued.add(1)
            elif event == "consume":
                self._consumed.add(1)
            elif event == "revoke":
                self._revoked.add(1)
            elif event == "deny":
                self._denied.add(1, {"reason": reason or "unknown"})
        except Exception:  # never let a telemetry error escape into a grant path
            pass


# --------------------------------------------------------------------------- serialization (M4)


def _grant_to_dict(g: CloudGrant) -> dict:
    d = {
        "id": g.id,
        "deployment_id": g.target.deployment_id,
        "project_id": g.target.project_id,
        "capability": g.target.capability,
        "uses_remaining": g.uses_remaining,
        "expires_at": g.expires_at,
        "issued_by": g.issued_by,
        "issued_at": g.issued_at,
        "revoked": bool(g.revoked),
    }
    if g.link_token is not None:   # FR-E12: absent key ⇒ byte-identical to a pre-FR-E12 grant (FR-8)
        d["link_token"] = g.link_token
    return d


def _grant_from_dict(d: dict) -> CloudGrant:
    return CloudGrant(
        id=str(d["id"]),
        target=GrantTarget(str(d["deployment_id"]), str(d["project_id"]), str(d["capability"])),
        uses_remaining=int(d["uses_remaining"]),
        expires_at=float(d["expires_at"]),
        issued_by=str(d.get("issued_by", "")),
        issued_at=float(d.get("issued_at", 0.0)),
        revoked=bool(d.get("revoked", False)),
        link_token=(str(d["link_token"]) if d.get("link_token") is not None else None),
    )


# --------------------------------------------------------------------------- durable store + audit (M4)


class AuditLog:
    """Append-only JSONL audit sink (FR-10). Every issuance/consume/revoke is one line. **Fail-closed:**
    a write failure raises :class:`StoreUnavailable`, so the caller (the grant op) denies rather than
    perform an un-auditable elevation (R1-F7/R1-S6). No message text is recorded (FR-WM2-14a)."""

    def __init__(self, path: "str | os.PathLike") -> None:
        self._path = Path(path)

    def __call__(self, event: dict) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(event, sort_keys=True, ensure_ascii=False)
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        except OSError as exc:
            raise StoreUnavailable(f"audit write failed: {exc}") from exc


class FileGrantStore(GrantStore):
    """The out-of-band, **control-plane** grant store (OQ-4): a JSON file the operator's issuance CLI
    writes and the served app reads + consumes. Each op **reloads** the file (so a CLI-issued grant is
    visible) under an **inter-process flock** (so consume is atomic across app instances — the anti-replay
    guarantee, FR-7, holds multi-process). Persist is atomic (temp-then-rename + fsync).

    The served app should hold this **consume-only** (NR-6); issuance is the CLI. The
    issuance-vs-consumption *privilege* split is convention here (a shared file); a DB/service backend
    can enforce it (the app gets only a decrement capability).
    """

    def __init__(self, path: "str | os.PathLike", audit: "Optional[Callable[[dict], None]]" = None,
                 metrics: "Optional[Callable[[str, Optional[str]], None]]" = None) -> None:
        super().__init__(audit=audit, metrics=metrics)
        self._path = Path(path)
        self._lockpath = Path(str(self._path) + ".lock")
        self._sync()

    def _interprocess_lock(self):
        import fcntl
        from contextlib import contextmanager as _cm

        @_cm
        def _flock():
            self._lockpath.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(self._lockpath), os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)   # exclusive across processes for the whole op
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

        return _flock()

    def _sync(self) -> None:
        if not self._path.is_file():
            self._grants = {}
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise StoreUnavailable(f"grant store unreadable: {exc}") from exc
        if not isinstance(data, dict):
            raise StoreUnavailable("grant store is not a JSON object")
        self._grants = {gid: _grant_from_dict(g) for gid, g in data.items()}

    def _persist(self, grant: CloudGrant) -> None:
        self._write({**self._grants, grant.id: grant})

    def _flush(self) -> None:
        self._write(self._grants)               # prune removed records; write the whole current set

    def _write(self, grants: "Dict[str, CloudGrant]") -> None:
        payload = json.dumps({gid: _grant_to_dict(g) for gid, g in grants.items()}, sort_keys=True)
        d = self._path.parent
        d.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(d), prefix=".grants.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self._path)         # atomic on POSIX
        except OSError as exc:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise StoreUnavailable(f"grant store persist failed: {exc}") from exc

    def all_grants(self):
        """A read-only snapshot of all grants (for the CLI `list`). Reloads first."""
        with self._op():
            return list(self._grants.values())
