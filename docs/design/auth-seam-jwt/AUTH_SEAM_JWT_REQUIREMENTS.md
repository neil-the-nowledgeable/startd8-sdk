# Auth Seam — JWT/Bearer Principal Contract (Tier 1.1) — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-20
**Status:** Ready for CRP / implementation
**Owner:** StartD8 SDK / backend_codegen (bucket-1, $0 deterministic)
**Amends:** `docs/design/deployment-mode/DEPLOYMENT_MODE_REQUIREMENTS.md` FR-IDN-2/3/4
**Pilot surface:** `app/auth.py` (owned kind `python-auth-seam`) emitted in `deployment.mode: deployed`

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2 after planning against the real code
> (`auth_renderer.py`, `crud_generator.py`, `htmx_generator.py`, `derived.py`, `drift.py`,
> `test_auth_seam.py`, `test_tenant_scoping.py`). See `AUTH_SEAM_JWT_PLAN.md` §1. The central
> correction: **a reference seam cannot verify JWT signatures at $0, and in the target topology it
> shouldn't — the gateway already did.** Decode-only is the correct default, not a compromise.

| v0.1 assumption | Planning discovery | Impact |
|-----------------|--------------------|--------|
| FR-JWT-3: the seam verifies the JWT signature | Generated `requirements.txt` (`derived.py:225-229`) bakes no JWT lib; real verification needs PyJWT/jose + JWKS/secret = a new always-on dep + runtime config, forbidden by NR. | **FR-JWT-3 reframed** to decode-only-trusting-upstream; the seam *documents* the verification swap-in. |
| Trust model unknown (OQ-2) | The whole point is "drops behind a gateway" (agentgateway/Gloo verify + forward the JWT). | Decode-only is correct; **new FR-JWT-9** makes the trust model explicit + a `VERIFIED_UPSTREAM=False` marker. |
| Dep impact unknown (OQ-1) | Same — baking PyJWT into every app violates $0/no-new-dep. | **New FR-JWT-10**: no new always-on baked dependency. |
| Maybe keep `X-Principal-Id` as fallback (OQ-3) | A spoofable header beside a Bearer contract is a privilege-escalation smell; nothing depends on the header name. | Drop the silent fallback; Bearer is the **single** ingress. |
| FR-JWT-8 backward-compat risk | `Principal.id` is load-bearing across M3 tenancy (`crud_generator.py:139-196`, `htmx_generator.py:661-768`). | `sub` → `Principal.id` is **mandatory**; field stays named `id`, first/required; new claim fields are optional. No router changes. |
| Tests may send `X-Principal-Id` and break (OQ-5) | No test sends it over HTTP; tenancy tests assert on rendered text; runtime denial is a deferred PG test. | Low blast radius; existing `test_auth_seam.py` assertions survive a body change; new tests are additive. |

**Resolved open questions:**
- **OQ-1 → No JWT lib baked.** Decode-only uses stdlib (`base64`+`json`); see FR-JWT-10.
- **OQ-2 → Decode-only, trust upstream.** Default trust model is "gateway verified the token"; FR-JWT-9.
- **OQ-3 → Drop `X-Principal-Id`.** Single Bearer ingress; no spoofable fallback.
- **OQ-4 → Standalone amendment** (this doc) amending FR-IDN-2; one-line forward-ref added there.
- **OQ-5 → Low test impact.** Body-change-safe; additive tests only.

---

## 1. Problem Statement

The deployed-mode auth seam (`backend_codegen/auth_renderer.py`, FR-IDN-2) currently resolves the
caller from a bare **`X-Principal-Id` header**:

```python
def get_principal(x_principal_id: Optional[str] = Header(default=None, alias="X-Principal-Id")):
    return Principal(id=x_principal_id) if x_principal_id else None
```

This is a dev-only shortcut, not a recognizable identity contract. The motivation (Tier 1.1 of the
solo.io review) is that real deployments put a gateway (agentgateway / Gloo / any API gateway / IdP)
in front of the app, and that gateway speaks the **`Authorization: Bearer <JWT>`** standard. A bare
custom header means every operator hand-edits `get_principal` to read the real thing before the seam
is usable behind a gateway — defeating "drops cleanly behind any gateway without rework."

We want the reference seam to model the **industry-standard contract**: extract the principal from a
JWT presented as a Bearer token, mapping standard claims (`sub`, `iss`, `aud`, `exp`, scopes/roles)
onto `Principal`. It must remain a **mechanism-seam** (bucket-1): deterministic, `$0`, drift-checkable,
**not** a credential/session store, and clearly marked as reference-not-production.

### Gap table

| Aspect | Current state | Gap |
|--------|---------------|-----|
| Ingress contract | custom `X-Principal-Id` header | Not the gateway/IdP standard (`Authorization: Bearer`) |
| Token format | opaque string = principal id | No JWT awareness; no claims |
| Principal fields | `id` only | No `sub`/`iss`/`aud`/`scopes`/`roles` surfaced |
| Verification stance | none (trusts header) | No statement of trust model (gateway-verified vs direct) |
| Expiry | none | A reference that ignores `exp` models a footgun |
| Gateway-readiness | operator must rewrite resolver | Should be drop-in behind a standard gateway |

---

## 2. Requirements

- **FR-JWT-1 (Bearer ingress).** `get_principal` SHALL read the caller's token from the standard
  `Authorization: Bearer <token>` header.
- **FR-JWT-2 (Standard-claim mapping).** The seam SHALL parse the token as a JWT and map standard
  registered claims onto `Principal`: `sub` → `Principal.id`, plus `iss`, `aud`, `exp`, and
  scope/role claims (`scope`/`scopes`, `roles`/`groups`).
- **FR-JWT-3 (Verification stance — reframed v0.2).** The reference seam SHALL **decode** the JWT
  claims (stdlib base64url + JSON) and SHALL NOT itself cryptographically verify the signature by
  default — it trusts an upstream gateway/IdP to have verified the token (FR-JWT-9). It SHALL
  **document** the signature-verification swap-in (replace the decode helper with PyJWT/JWKS, add the
  dep) for direct-internet exposure. (Original "verify by default" was infeasible at $0 and is the
  gateway's job in the target topology — see §0.)
- **FR-JWT-4 (Expiry enforcement).** The seam SHALL reject expired tokens (`exp` in the past) with
  401, using **stdlib time only** (no library). Missing/unparseable `exp` SHALL fail closed (no
  principal) under the decode-only stance.
- **FR-JWT-5 (Mechanism-seam, not a store).** The seam SHALL remain a reference resolver — it issues
  no tokens, holds no sessions, and embeds no credentials. Token issuance / IdP config is operator
  content (bucket 4).
- **FR-JWT-6 (Reference marker preserved).** The machine-detectable `REFERENCE_AUTH_SEAM = True`
  marker (R1-F4) and `is_reference_auth_seam()` SHALL continue to work for gates/wireframe.
- **FR-JWT-7 (Determinism).** The rendered `app/auth.py` SHALL stay a constant body (no variance by
  schema content or mode value beyond existence-in-deployed), drift-checkable via the existing
  `_renderers` map and schema-sha staleness. No change to `drift.py`/`assembler.py` wiring.
- **FR-JWT-8 (Backward compatibility).** `sub` SHALL map to `Principal.id`, and `Principal.id` SHALL
  remain the first, required field, so M3 tenancy row-scoping (`crud_generator.py:139-196`,
  `htmx_generator.py:661-768`) and `require_principal` keep working unchanged. New claim fields
  (`iss`/`aud`/`exp`/`scopes`) are optional with defaults.
- **FR-JWT-9 (Explicit trust model — added v0.2).** The seam SHALL declare its trust posture with a
  machine-detectable `VERIFIED_UPSTREAM = False` marker and a loud **DECODE-ONLY** banner ("safe only
  behind a gateway/IdP that verified the signature"). Gates/wireframe SHOULD advise when a deployed
  build ships the decode-only seam unhardened for direct exposure.
- **FR-JWT-10 (No new baked dependency — added v0.2).** Implementing FR-JWT-1..4 SHALL NOT add any
  always-on third-party dependency to the generated `requirements.txt` (`derived.py`). Decode/expiry
  use stdlib only; PyJWT/JWKS is an operator opt-in documented in the seam.

## 3. Non-Requirements

- No token issuance, login routes, refresh, or session storage.
- No IdP/JWKS provisioning, key rotation policy, or secret management (operator / `secrets/`).
- No tenant row-scoping changes (that is FR-TEN-*/M3, already shipped separately).
- No change to `app/main.py` (seam stays a dependency module wired via `user_routers.py`).
- No new always-on third-party runtime dependency baked into generated `requirements.txt`.

## 4. Open Questions

*All v0.1 open questions resolved by the planning pass (see §0). Remaining for CRP:*

- **OQ-6 (new).** Should `aud`/`iss` mismatch be enforced (reject) by the reference, or only surfaced
  on `Principal`? Leaning surface-only (enforcement is operator policy, bucket 4) — confirm in CRP.

---

*v0.2 — Post-planning self-reflective update. 1 requirement reframed (FR-JWT-3), 4 clarified
(1/2/4/7/8), 2 added (FR-JWT-9/10), 5 open questions resolved, 1 new (OQ-6) raised for CRP.*
