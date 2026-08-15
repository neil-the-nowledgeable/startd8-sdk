"""Deterministic name projections — the single source for a node's readable handle + canonical ref.

Per ``DETERMINISTIC_INTENT_DELIVERY_LANGUAGE`` §"How the naming works": a semantic name projects
deterministically to a compact readable handle (kebab slug + 8-hex digest) and a stable canonical ref.
One home so requirements, node-schema, and any future source derive the forms identically (no drift).
"""
from __future__ import annotations

import hashlib
import re


def slug(text: str, *, cap: int = 48) -> str:
    """Deterministic, compact kebab slug of a semantic name.

    Capped to stay recognizable; the 8-hex digest the handle appends preserves uniqueness even when
    two names share a truncated slug.
    """
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    if len(s) > cap:
        s = s[:cap].rsplit("-", 1)[0].strip("-")
    return s


def name_forms(name: str, key: str, *, initiative: str = "requirements", kind: str = "requirement") -> dict:
    """The deterministic projections for a semantic name: {name, handle, canonical}.

    - handle:    ``<kind>/<slug>-<8hex>`` — recognition + compact deterministic correlation
    - canonical: ``cc:intent:<initiative>:<kind>:<key>`` — stable machine identity, wording-independent
    """
    s = slug(name)
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:8]
    return {
        "name": name,
        "handle": f"{kind}/{s}-{digest}" if s else "",
        "canonical": f"cc:intent:{initiative}:{kind}:{key.lower()}",
    }
