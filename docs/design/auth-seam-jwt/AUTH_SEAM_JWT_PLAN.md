# Auth Seam — JWT/Bearer Principal Contract (Tier 1.1) — Implementation Plan

**Version:** 1.0
**Date:** 2026-06-20
**Tracks:** `AUTH_SEAM_JWT_REQUIREMENTS.md` (v0.2)

---

## 1. Planning Discoveries (fed back into requirements §0)

| Requirements assumed (v0.1) | Code reality | Impact |
|---|---|---|
| FR-JWT-3: seam verifies the JWT signature | Generated `requirements.txt` (`derived.py:225-229`) bakes only fastapi/sqlmodel/jinja2/python-multipart/uvicorn — **no JWT lib**. Real verification needs PyJWT/jose + a JWKS/secret = a new always-on dep + runtime config. NR forbids a new baked dep. | **FR-JWT-3 reframed**: reference is **decode-only** (stdlib base64+json), trusting an upstream gateway that already verified the signature; it *documents* the verification swap-in (PyJWT+JWKS) for direct exposure. Verification-by-default is infeasible at $0 and is the gateway's job in the target topology. |
| OQ-2 trust model unknown | The whole motivation is "drops behind a gateway" — agentgateway/Gloo verify the JWT and forward it. | **Decode-only is the correct default**, not a compromise. New **FR-JWT-9** makes the trust model explicit + a machine-detectable `VERIFIED_UPSTREAM = False` posture. |
| OQ-1 dep question open | Same as above | **Resolved: no JWT lib baked.** New **FR-JWT-10** (no new always-on dep). |
| OQ-3 keep `X-Principal-Id` fallback? | A spoofable header alongside a Bearer contract is a privilege-escalation smell; nothing depends on the header name. | **Resolved: drop the silent header fallback.** Bearer is the single ingress. |
| FR-JWT-8 backward-compat (risk: high?) | `Principal.id` is consumed by M3 tenancy in `crud_generator.py:139-196` and `htmx_generator.py:661-768` (`obj.{owner} = principal.id`, scoped `select(...).where(... == principal.id)`). | **`sub` → `Principal.id` is mandatory and the field MUST stay named `id`.** Mapping fixed; no router changes. |
| OQ-5 tests may send `X-Principal-Id` and break | `grep` shows **no** test sends the header over HTTP; tenancy/route tests are string-presence assertions on rendered text (`test_tenant_scoping.py`), runtime cross-principal denial is a deferred PG integration test. | **Low test blast radius.** `test_auth_seam.py` asserts marker + `def get_principal(`/`def require_principal(` + FR-IDN-4 banner + drift — all survive a body change. Only new assertions are additive. |
| Drift may need to change | `auth.py` body is a constant; drift via `_renderers["python-auth-seam"]` (`drift.py:241`) + schema-sha staleness. | **No drift mechanism change.** Body stays constant; decode helper is pure stdlib → still deterministic. |

> ~50% of the v0.1 FRs were revised (FR-JWT-3 reframed; 1/2/3 clarified; +9/+10 added; 2 OQs flipped a
> design default). Past the 30% bar — v0.1 was appropriately premature; caught at doc cost.

## 2. Approach

Single-file change to `src/startd8/backend_codegen/auth_renderer.py` `_BODY`, plus additive tests.
No changes to `drift.py`, `assembler.py`, `crud_generator.py`, `htmx_generator.py`, or
`requirements.txt` rendering.

### Step 1 — Rewrite `_BODY` (auth_renderer.py)
- Add a stdlib `_decode_jwt_claims(token: str) -> dict` helper: split on `.`, base64url-decode the
  middle (payload) segment with padding fix, `json.loads`. Pure stdlib (`base64`, `json`). Returns
  `{}` on any malformed input (never raises out of the resolver).
- `get_principal` reads `Authorization: Bearer <token>` (FastAPI `Header(alias="Authorization")`),
  splits the scheme, decodes claims, enforces `exp` (stdlib `time.time()`), maps:
  - `sub` → `Principal.id` (mandatory; `None` principal if `sub` missing/empty)
  - `iss`, `aud`, `exp` → optional `Principal` fields
  - `scope` (space-delimited string) / `scopes` / `roles` / `groups` → `Principal.scopes: tuple[str,...]`
- `Principal` gains optional fields (`iss`, `aud`, `exp`, `scopes`) with defaults — `id` stays first
  and required so existing positional/`.id` usage is untouched.
- Markers: keep `REFERENCE_AUTH_SEAM = True`; add `VERIFIED_UPSTREAM = False` (FR-JWT-9) +
  `is_unverified_auth_seam()`-style detectability.
- Banner: keep FR-IDN-4 tenant banner; add a **DECODE-ONLY** banner — "this DECODES the JWT but does
  NOT verify its signature; safe ONLY behind a gateway/IdP that verified it. For direct exposure,
  replace `_decode_jwt_claims` with PyJWT + JWKS verification (add `pyjwt[crypto]` to requirements)."
- `require_principal` unchanged (still 401 on `None`).

### Step 2 — Detectability helper
- Add `is_verified_auth_seam(text) -> bool` (or extend the gate signal) returning `False` while
  `VERIFIED_UPSTREAM = False`, so wireframe/gates can advise "decode-only seam not hardened for direct
  exposure." Mirror `is_reference_auth_seam`.

### Step 3 — Tests (`tests/unit/backend_codegen/test_auth_seam.py`, additive)
- `Authorization`/`Bearer` present in body; `X-Principal-Id` absent.
- `_decode_jwt_claims` round-trips a hand-built unsigned JWT (header.payload.sig, stdlib base64url);
  `sub` → `Principal.id`; scopes parsed; malformed token → `{}`/`None` principal.
- `exp` in the past → 401 via `require_principal` path (construct a tiny ASGI app w/ TestClient, or
  unit-call `get_principal`).
- New markers present + detectability helpers; existing marker/drift/skip-hook tests still pass.
- Determinism: `render_auth_seam(SCHEMA) == render_auth_seam(SCHEMA)`; `owned_file_in_sync` True.

### Step 4 — Cross-doc note
- Append a forward-ref in `DEPLOYMENT_MODE_REQUIREMENTS.md` FR-IDN-2 pointing to this amendment
  (one line; the seam contract now = Bearer/JWT decode-only).

## 3. Validation

```bash
PYTHONPATH=$PWD/src .venv/bin/pytest tests/unit/backend_codegen/test_auth_seam.py \
  tests/unit/backend_codegen/test_tenant_scoping.py tests/unit/backend_codegen/test_tenancy.py -v
PYTHONPATH=$PWD/src .venv/bin/python -c "import ast; ast.parse(__import__('startd8.backend_codegen.auth_renderer', fromlist=['render_auth_seam']).render_auth_seam('model A { id String @id }'))"
```
- Generated `auth.py` must `ast.parse` clean (it's emitted code).
- `generate backend --check` on a deployed app stays `in_sync` (drift unchanged).

## 4. Risks

| Risk | Mitigation |
|---|---|
| Decode-only mistaken for verified | `VERIFIED_UPSTREAM = False` marker + loud DECODE-ONLY banner + wireframe/gate advisory |
| Emitted `auth.py` has a syntax error | `ast.parse` test on the rendered body |
| `Principal` field change breaks tenancy queries | `id` stays first/required; new fields are optional with defaults; run tenancy tests |
| base64url padding edge cases | helper pads to len%4; returns `{}` on any decode error |

## 5. Out of scope (deferred / operator)
- PyJWT/JWKS signature verification wiring (operator swaps in; we ship the documented seam).
- Token issuance / login / refresh / sessions.
- Tenant row-scoping (M3, shipped).
- Gateway-specific claim-forwarding header conventions (vendor-neutral Bearer only).
