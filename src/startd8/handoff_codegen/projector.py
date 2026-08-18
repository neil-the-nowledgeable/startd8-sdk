"""The ``$0`` REQ+ledger → det-handoff/0.1 projector.

The **second projector** in the det-doc-kit family, built against
``STANDARD_det-doc-kit-projector-pattern.md`` (the real ``/reflective-adoption`` gate). Mirrors
``plan_codegen``: a pure, LLM-free function of two authored inputs — the **REQ** (FRs → build order +
exit criteria, Touches → prerequisites/pointers, Objectives → hand-back) and the **ledger** (delivery
state → the solo-vs-gap gate + the ``base`` sha). The Gotchas / session framing are **human-residue**
(``SCHEMA_det-handoff-0.1.md §5``) — the projector emits placeholders, never invented content.

Reuse (Mottainai): ``navigator.det_req.parse_fr_lines`` (FRs), ``navigator.req_header`` (the shared
header parsing — extracted from plan_codegen for this second projector), ``navigator.naming.name_forms``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

from ..navigator import req_header as H
from ..navigator.det_req import parse_fr_lines
from ..navigator.naming import name_forms
from .models import (
    COMPANION_KIND,
    FORMAT_VERSION,
    PROJECTED_MATURITY,
    BuildStep,
    Handoff,
    Prerequisite,
)

# An Objective line: ``- **O-1:** <text>`` (the hand-back deliverables).
_OBJECTIVE = re.compile(r"^-\s*\*\*(O-\d+):\*\*\s*(?P<t>.+?)\s*$", re.MULTILINE)
# A ledger row marking a REQ delivered (built/landed/shipped) — the solo-vs-gap state signal.
_DELIVERED_WORDS = ("built", "landed", "shipped")
_OPEN_WORDS = ("follow-on", "follow-ons", "open", "pending", "deferred")


class NotHandoffOwedError(ValueError):
    """Raised when the projector is asked to hand off a REQ that owes no handoff (§5 solo-vs-gap).

    A REQ with no FRs (nothing to build) or one the ledger marks fully delivered with no open
    follow-ons owes no handoff — the honest gate; do not manufacture a brief for ceremony.
    """


def _req_num(req_text: str, req_path: Optional[Path]) -> str:
    """The ``REQ-NN`` token for this req (from the canonical key ``…:req-29`` → ``REQ-29``)."""
    key = H.req_key(req_text, req_path)  # e.g. "req-29"
    m = re.search(r"req-([\w-]+)", key, re.IGNORECASE)
    return f"REQ-{m.group(1)}".upper() if m else key.upper()


def is_handoff_owed(
    req_text: str, *, req_path: Optional[Path] = None, ledger_text: Optional[str] = None
) -> bool:
    """§5 solo-vs-gap gate: does this REQ *owe* a handoff (is there work to hand off)?

    Owed iff the REQ declares FRs **and** the ledger does not mark it fully delivered-with-no-open-
    follow-ons. Absent a ledger, a spec with FRs is presumptively owed (unbuilt). *(Adoption finding:
    unlike det-plan — whose gate is a REQ **marker** — det-handoff's gate is a **ledger state**; the
    signal is doc-type-specific.)*
    """
    if not parse_fr_lines(req_text):
        return False
    if not ledger_text:
        return True
    req_num = _req_num(req_text, req_path).lower()
    for line in ledger_text.splitlines():
        low = line.lower()
        if req_num in low and any(w in low for w in _DELIVERED_WORDS):
            # Delivered — owed only if the row still names an open follow-on.
            return any(w in low for w in _OPEN_WORDS)
    return True


def _base_from_ledger(ledger_text: Optional[str], base_sha: Optional[str]) -> str:
    """The git base (``main @ <sha>``). Explicit ``base_sha`` wins; else unresolved (honest)."""
    if base_sha:
        return f"main @ {base_sha}"
    return "main @ (unresolved — pass --base <sha>)"


def _build_order(frs: List[dict]) -> Tuple[BuildStep, ...]:
    """The ordered build list — each FR + its Verify: clause as the exit criterion (§2)."""
    return tuple(
        BuildStep(
            fr=fr["id"],
            name=(fr.get("name") or fr.get("title") or fr["id"]).strip(),
            verify=(fr.get("verify") or "").strip(),
        )
        for fr in frs
    )


def _prerequisites(
    frs: List[dict], req_path: Optional[Path]
) -> Tuple[Prerequisite, ...]:
    """The §2 prerequisite/reuse audit — each authored Touches/code-Lives ref resolved on disk."""
    root = H.repo_root(req_path)
    seen: List[str] = []
    out: List[Prerequisite] = []
    refs: List[str] = []
    for fr in frs:
        for f in fr.get("touches") or []:
            refs.append(f.strip().strip("`"))
        for e in fr.get("lives") or []:
            if (e.get("type") or "").lower() == "code":
                refs.append((e.get("ref") or "").strip().strip("`"))
    for ref in refs:
        if not ref or ref in seen:
            continue
        seen.append(ref)
        out.append(Prerequisite(ref=ref, resolved=bool(root) and (root / ref).exists()))
    return tuple(out)


def _pointers(frs: List[dict]) -> Tuple[str, ...]:
    """Where to look — the union of the FRs' Touches refs (deduped, sorted)."""
    seen: List[str] = []
    for fr in frs:
        for f in fr.get("touches") or []:
            key = f.strip().strip("`")
            if key and key not in seen:
                seen.append(key)
    return tuple(sorted(seen))


def _hand_back(req_text: str) -> Tuple[str, ...]:
    """What the receiving session returns — the REQ's Objectives (``O-N``)."""
    return tuple(
        f"{m.group(1)}: {m.group('t').strip()}" for m in _OBJECTIVE.finditer(req_text)
    )


def _spec_ref(req_text: str, req_path: Optional[Path]) -> str:
    """The spec line — the REQ ref + its Format:/Governs (from the REQ header)."""
    num = _req_num(req_text, req_path)
    fmt = H.format_ref(req_text)
    parts = [f"`{req_path.name}`" if req_path is not None else num]
    if fmt:
        parts.append(f"Format: {fmt}")
    return " · ".join(parts)


def project_handoff(
    req_text: str,
    *,
    req_path: Optional[Path] = None,
    ledger_text: Optional[str] = None,
    base_sha: Optional[str] = None,
) -> Handoff:
    """Project a REQ (+ optional ledger) into a :class:`Handoff` — the pure ``$0`` function.

    Raises :class:`NotHandoffOwedError` for a REQ that owes no handoff (§5). Makes no network/LLM call.
    """
    if not is_handoff_owed(req_text, req_path=req_path, ledger_text=ledger_text):
        raise NotHandoffOwedError(
            "requirement owes no handoff — it declares no FRs, or the ledger marks it fully "
            "delivered with no open follow-ons (§5 solo-vs-gap)"
        )
    frs = parse_fr_lines(req_text)

    name = H.semantic_name(req_text) or H.title(req_text) or "projected handoff"
    forms = name_forms(
        name,
        H.req_key(req_text, req_path),
        initiative="requirements-visualization",
        kind="handoff",
    )
    return Handoff(
        version="0.1",
        format_version=FORMAT_VERSION,
        pairs_with=req_path.name if req_path is not None else "(source req)",
        base=_base_from_ledger(ledger_text, base_sha),
        companion_kind=COMPANION_KIND,
        maturity=PROJECTED_MATURITY,
        name=forms["name"],
        handle=forms["handle"],
        ref=forms["canonical"],
        spec=_spec_ref(req_text, req_path),
        build_order=_build_order(frs),
        prerequisites=_prerequisites(frs, req_path),
        pointers=_pointers(frs),
        hand_back=_hand_back(req_text),
    )
