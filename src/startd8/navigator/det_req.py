"""Vendored thin Lives / FR-health helpers — cited to det-req-kit (FR-6 vendor_thin).

Normative grammar: ``dev-os/det-req-kit/SCHEMA.md`` + ``extract.py`` EVIDENCE-1.
This module is a **minimal** port of Lives parse + ``fr_health`` so the SDK does
not require a sibling checkout of det-req-kit. Optional ``DET_REQ_KIT`` env may
point operators at the full kit later; unit tests must pass without it on path.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# --- cited from det-req-kit/extract.py (EVIDENCE-1) ---------------------------------

_FR = re.compile(r"^- \*\*(FR-[\w-]+)\s*[—-]\s*(.+?)\.\*\*\s*(.*)$")
_VERIFY_LABEL = re.compile(
    r"(?:\*\*)?\bVerify(?:\s*\((?P<ann>[^)]*)\))?:(?:\*\*)?\s*(?P<v>.*)$", re.DOTALL
)
_TOUCHES_LABEL = re.compile(r"(?:\*\*)?\bTouches(?:\s*\([^)]*\))?:(?:\*\*)?\s*")
_LIVES_LABEL = re.compile(r"(?:\*\*)?\bLives(?:\s*\([^)]*\))?:(?:\*\*)?\s*", re.IGNORECASE)
_LIVES_STOP = re.compile(
    r"(?:\*\*)?\b(?:Verify|Touches|Serves|Depends|Attrs|Lives)(?:\s*\([^)]*\))?:",
    re.IGNORECASE,
)
_GIT_REF = re.compile(r"^git:[0-9a-f]{40}:\S+")
_LIVES_SKIP_TYPES = frozenset({"owned_elsewhere", "declared_unimplemented"})
_DONEISH_RE = re.compile(r"^(?:already\s+true|met|done|delivered|closed)\b", re.IGNORECASE)
_SERVES = re.compile(
    r"(?:\*\*)?\bServes:(?:\*\*)?\s*((?:O-\d+)(?:\s*,\s*O-\d+)*)\.?", re.IGNORECASE
)


def _is_doneish_ann(ann: str | None) -> bool:
    return bool(ann and _DONEISH_RE.match(ann.strip()))


def parse_lives_body(body: str) -> List[Dict[str, str]]:
    body = body.strip().rstrip(".").strip()
    if not body:
        return []
    if re.search(r"(?:^|\s)-\s*type\s*:", body, re.IGNORECASE):
        entries: List[Dict[str, str]] = []
        for m in re.finditer(
            r"-\s*type\s*:\s*(\S+)\s+ref\s*:\s*(\S+)(?:\s+note\s*:\s*(.+?))?(?=\s*-\s*type\s*:|\Z)",
            body,
            re.IGNORECASE | re.DOTALL,
        ):
            e: Dict[str, str] = {"type": m.group(1), "ref": m.group(2).rstrip(".")}
            if m.group(3) and m.group(3).strip():
                e["note"] = m.group(3).strip().rstrip(".")
            entries.append(e)
        return entries
    parts = body.split(None, 1)
    if len(parts) == 1:
        return [{"type": parts[0], "ref": "-"}]
    return [{"type": parts[0], "ref": parts[1].strip()}]


def extract_lives(rest: str) -> Tuple[str, List[Dict[str, str]]]:
    lives: List[Dict[str, str]] = []
    chunks: List[str] = []
    pos = 0
    for m in _LIVES_LABEL.finditer(rest):
        chunks.append(rest[pos : m.start()])
        after = rest[m.end() :]
        stop = _LIVES_STOP.search(after)
        body = after[: stop.start()] if stop else after
        lives.extend(parse_lives_body(body))
        pos = m.end() + (stop.start() if stop else len(after))
    chunks.append(rest[pos:])
    cleaned = re.sub(r"\s+", " ", "".join(chunks)).strip()
    return cleaned, lives


# Writer-parity Approve prompts (kickoff navigator APPROVE? → signoff).
# Terminator = a *sentence-ending* period (followed by whitespace or end), so a decimal inside the
# prompt ("does 0.9 require…") does NOT prematurely truncate it — the earlier `\.\s*` did, because
# `\s*` allows zero spaces and matched the "." in "0.9" (dogfood FR-4 surfaced this).
_APPROVE = re.compile(
    r"(?:\*\*)?\bApprove\?:(?:\*\*)?\s*(?P<q>.+?)(?:\.(?=\s|$)|$)",
    re.IGNORECASE,
)
# NODE-SCHEMA: key is identity; Was: carries prior presentation aliases (rebrand notes).
_WAS = re.compile(
    r"(?:\*\*)?\bWas:(?:\*\*)?\s*(?P<body>.+?)(?:\.(?=\s|$)|$)",
    re.IGNORECASE,
)


def parse_approve_prompts(rest: str) -> Tuple[str, Tuple[str, ...]]:
    """Pull ``Approve?: q1 · q2`` (or semicolon / ' · ' separated) out of an FR rest."""
    m = _APPROVE.search(rest)
    if not m:
        return rest, ()
    raw = m.group("q").strip().rstrip(".")
    cleaned = (rest[: m.start()] + rest[m.end() :]).strip()
    parts = re.split(r"\s*[·|;]\s*", raw)
    prompts = tuple(p.strip(" []") for p in parts if p.strip(" []"))
    return cleaned, prompts


def parse_was_aliases(rest: str) -> Tuple[str, Tuple[str, ...]]:
    """Pull ``Was: old-name · other-alias`` out of an FR rest (NODE-SCHEMA alias notes)."""
    m = _WAS.search(rest)
    if not m:
        return rest, ()
    raw = m.group("body").strip().rstrip(".")
    cleaned = (rest[: m.start()] + rest[m.end() :]).strip()
    parts = re.split(r"\s*[·|,;]\s*", raw)
    aliases = tuple(p.strip(" []`") for p in parts if p.strip(" []`"))
    return cleaned, aliases


def split_fr_fields(rest: str) -> Tuple[str, List[str], str, List[str], List[Dict[str, str]], Optional[str], Tuple[str, ...], Tuple[str, ...]]:
    sm = _SERVES.search(rest)
    serves = [s.strip() for s in sm.group(1).split(",") if s.strip()] if sm else []
    rest = _SERVES.sub("", rest).strip()
    rest, approve_prompts = parse_approve_prompts(rest)
    rest, was_aliases = parse_was_aliases(rest)
    # Lives only before Verify: — Verify prose often cites `Lives: …` as an example
    # (dogfood REQ-01 FR-6); extracting after Verify invents false evidence.
    vm_pre = _VERIFY_LABEL.search(rest)
    pre_verify = rest[: vm_pre.start()] if vm_pre else rest
    post_verify = rest[vm_pre.start() :] if vm_pre else ""
    pre_verify, lives = extract_lives(pre_verify)
    rest = (pre_verify + (" " + post_verify if post_verify else "")).strip()
    vm = _VERIFY_LABEL.search(rest)
    verify_start = vm.start() if vm else len(rest)
    verify = vm.group("v").strip().rstrip(".") if vm else ""
    verify_ann = (vm.group("ann") or "").strip() or None if vm else None
    tmatches = [t for t in _TOUCHES_LABEL.finditer(rest) if t.start() < verify_start]
    if tmatches:
        last = tmatches[-1]
        behavior = rest[: last.start()].strip()
        touches_raw = rest[last.end() : verify_start].strip().rstrip(".")
        touches = [t.strip() for t in touches_raw.split(",") if t.strip()]
    else:
        behavior = rest[:verify_start].strip()
        touches = []
    return behavior, touches, verify, serves, lives, verify_ann, approve_prompts, was_aliases


def fr_health(fr: Dict[str, Any]) -> str:
    """done-claim without evidence → unknown; honest-skip → skipped; strong git → on_track."""
    ann = (fr.get("_verify_ann") or "").strip()
    lives = fr.get("lives") or []
    if not _is_doneish_ann(ann):
        return "n/a"
    if lives and all((e.get("type") or "") in _LIVES_SKIP_TYPES for e in lives):
        return "skipped"
    if not lives:
        return "unknown"
    if any(
        (e.get("type") or "") in _LIVES_SKIP_TYPES
        or _GIT_REF.match((e.get("ref") or "").strip())
        for e in lives
    ):
        return "on_track"
    return "unknown"


def parse_fr_lines(text: str) -> List[Dict[str, Any]]:
    """Minimal FR bullet parser (single-line det-req FR shape)."""
    frs: List[Dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        m = _FR.match(line)
        if not m:
            continue
        fid, title, rest = m.group(1), m.group(2).strip(), m.group(3).strip()
        (
            behavior,
            touches,
            verify,
            serves,
            lives,
            verify_ann,
            approve_prompts,
            was_aliases,
        ) = split_fr_fields(rest)
        fr: Dict[str, Any] = {
            "id": fid,
            "title": title,
            "behavior": behavior or title,
            "touches": touches,
            "verify": verify,
            "serves": serves,
            "lives": lives,
            "_verify_ann": verify_ann,
            "approve_prompts": list(approve_prompts),
            "was": list(was_aliases),
        }
        fr["fr_health"] = fr_health(fr)
        frs.append(fr)
    return frs


def det_req_kit_override() -> Optional[Path]:
    """Optional path to det-req-kit root (``DET_REQ_KIT``). Empty → vendor_thin only."""
    raw = os.environ.get("DET_REQ_KIT", "").strip()
    return Path(raw) if raw else None


def _frs_from_kit_doc(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Map kit ``functionalRequirements`` rows into the vendor_thin FR dict shape."""
    frs: List[Dict[str, Any]] = []
    for raw in doc.get("functionalRequirements") or []:
        if not isinstance(raw, dict):
            continue
        fr: Dict[str, Any] = {
            "id": str(raw.get("id", "")),
            "title": str(raw.get("title") or raw.get("behavior") or raw.get("id") or ""),
            "behavior": str(raw.get("behavior") or raw.get("title") or ""),
            "touches": list(raw.get("touches") or []),
            "verify": str(raw.get("verify") or ""),
            "serves": list(raw.get("serves") or []),
            "lives": list(raw.get("lives") or []),
            "_verify_ann": raw.get("_verify_ann"),
            "approve_prompts": list(raw.get("approve_prompts") or []),
            "was": list(raw.get("was") or []),
        }
        fr["fr_health"] = fr_health(fr)
        if fr["id"]:
            frs.append(fr)
    return frs


def parse_fr_lines_prefer_kit(text: str) -> List[Dict[str, Any]]:
    """Vendor_thin by default; when ``DET_REQ_KIT`` is set, prefer the kit's ``extract.parse``.

    Fail-loud if the env points at a missing/broken kit (opt-in must not silently no-op).
    Unit tests leave the env unset so CI never requires a sibling checkout.
    """
    kit = det_req_kit_override()
    if kit is None:
        return parse_fr_lines(text)
    extract_py = kit / "extract.py"
    if not extract_py.is_file():
        raise FileNotFoundError(
            f"DET_REQ_KIT={kit} has no extract.py — unset the env to use vendor_thin"
        )
    import importlib.util

    spec = importlib.util.spec_from_file_location("startd8_det_req_kit_extract", extract_py)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load det-req-kit extract from {extract_py}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    parse = getattr(mod, "parse", None)
    if not callable(parse):
        raise ImportError(f"{extract_py} has no callable parse()")
    doc = parse(text)
    if not isinstance(doc, dict):
        raise ValueError("det-req-kit parse() did not return a dict")
    frs = _frs_from_kit_doc(doc)
    if not frs:
        # Kit may ignore single-line fixtures without § headers — fall back, but loud.
        thin = parse_fr_lines(text)
        if thin:
            return thin
        raise ValueError("det-req-kit parse returned no functionalRequirements")
    return frs
