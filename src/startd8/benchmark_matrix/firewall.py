"""Contamination-firewall verification for Jetson edge-cluster cells (FR-J5a / J6 / J6b / J8).

Pure, offline-testable verdict logic: given what a Jetson cell *requested* and what the server
*reported*, decide whether the result is admissible to the **general leaderboard** (clean),
belongs in the **fenced in-domain track**, or must be **invalidated** (not scored at all).

The live capture — the response's ``system_fingerprint`` (FR-J5a applied-adapter echo) and the
system prompt actually sent (FR-J6) — is wired by the runtime caller; this module only judges it.

Three vectors + the identity guard, per the requirements firewall:
- applied-adapter identity (FR-J5a): server-reported adapter MUST match the requested alias; a
  mismatch INVALIDATES the cell (a reachable-but-wrong-adapter 200-OK would otherwise be scored as
  the wrong contestant).
- system prompt (FR-J6): the prompt actually received MUST byte-equal the neutral prompt and contain
  no corpus/house-style tokens.
- determinism (FR-J6b): sampling params + quantization config MUST be recorded.
- "clean" (FR-J8): admissible to the general leaderboard iff base weights AND all vectors pass.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import re

from ..logging_config import get_logger

logger = get_logger(__name__)

# Tokens that betray the corpus-aware serving default (FR-J6). Lowercased substring match.
BANNED_CORPUS_TOKENS = (
    "microservices-demo",
    "online boutique",
    "house style",
    "json logger",
    "getjsonlogger",
    "opentelemetry",
    "otel",
    "grpc servicer",
    "apache",
)

# Server reports the applied adapter as ``served_adapter=<id>`` in the OpenAI system_fingerprint.
_FP_RE = re.compile(r"served_adapter=(?P<id>.+)\s*$")

# Server sentinel for "adapters disabled, base model served".
BASE_SENTINEL = "__base__"

TRACK_GENERAL = "general"
TRACK_IN_DOMAIN = "in-domain"
TRACK_INVALID = "invalid"


@dataclass
class VectorVerdict:
    name: str
    ok: bool
    detail: str


@dataclass
class FirewallVerdict:
    track: str                                   # general | in-domain | invalid
    clean: bool                                  # admissible to the GENERAL leaderboard
    invalidated: bool                            # cell must NOT be scored at all
    vectors: List[VectorVerdict] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)

    def as_provenance(self) -> Dict[str, Any]:
        """Flatten to a JSON-able dict for cells.json provenance (FR-J7)."""
        return {
            "track": self.track,
            "clean": self.clean,
            "invalidated": self.invalidated,
            "vectors": {v.name: {"ok": v.ok, "detail": v.detail} for v in self.vectors},
            "reasons": list(self.reasons),
        }


def parse_served_adapter(system_fingerprint: Optional[str]) -> Optional[str]:
    """Extract the server-reported applied adapter from ``served_adapter=<id>`` (FR-J5a echo)."""
    if not system_fingerprint:
        return None
    m = _FP_RE.search(system_fingerprint)
    return m.group("id").strip() if m else None


def verify_applied_adapter(
    system_fingerprint: Optional[str],
    expected_served_id: str,
    *,
    expect_base: bool,
) -> VectorVerdict:
    """FR-J5a: the server-reported adapter must match what was requested."""
    served = parse_served_adapter(system_fingerprint)
    if served is None:
        return VectorVerdict(
            "applied_adapter", False,
            "server did not report served_adapter (FR-J5a echo missing — old server?)",
        )
    want = BASE_SENTINEL if expect_base else expected_served_id
    ok = served == want
    return VectorVerdict("applied_adapter", ok, f"served={served!r} expected={want!r}")


def verify_system_prompt(sent_prompt: Optional[str], expected_neutral: str) -> VectorVerdict:
    """FR-J6: the prompt actually sent must byte-equal the neutral prompt and carry no corpus tokens."""
    if sent_prompt is None:
        return VectorVerdict("system_prompt", False, "no system prompt captured")
    if sent_prompt != expected_neutral:
        return VectorVerdict("system_prompt", False, "sent prompt != expected neutral prompt")
    low = sent_prompt.lower()
    hits = [t for t in BANNED_CORPUS_TOKENS if t in low]
    if hits:
        return VectorVerdict("system_prompt", False, f"banned corpus tokens present: {hits}")
    return VectorVerdict("system_prompt", True, "byte-equals neutral; no banned tokens")


def verify_determinism(sampling: Optional[Dict[str, Any]], quant: Optional[str]) -> VectorVerdict:
    """FR-J6b: sampling params + quant config must be RECORDED (cross-cell equality is the caller's
    job — comparing two cells; here we assert presence so an unrecorded run can't pass)."""
    missing = []
    if not sampling:
        missing.append("sampling")
    if not quant:
        missing.append("quant")
    ok = not missing
    return VectorVerdict("determinism", ok, "recorded" if ok else f"missing: {missing}")


def evaluate(
    *,
    contamination_label: str,
    expected_served_id: str,
    expect_base: bool,
    system_fingerprint: Optional[str],
    sent_prompt: Optional[str],
    expected_neutral: str,
    sampling: Optional[Dict[str, Any]] = None,
    quant: Optional[str] = None,
) -> FirewallVerdict:
    """Render the firewall verdict for a single Jetson cell.

    - applied-adapter mismatch ⇒ **invalidated** (track=invalid; never scored).
    - otherwise an in-domain model ⇒ fenced **in-domain** track (valid, but never a general peer).
    - a base ("clean"-labeled) model passing every vector ⇒ **general** (clean=True).
    """
    vectors = [
        verify_applied_adapter(system_fingerprint, expected_served_id, expect_base=expect_base),
        verify_system_prompt(sent_prompt, expected_neutral),
        verify_determinism(sampling, quant),
    ]
    reasons = [f"{v.name}: {v.detail}" for v in vectors if not v.ok]

    adapter_ok = vectors[0].ok
    invalidated = not adapter_ok  # FR-J5a: wrong/absent adapter echo invalidates the cell

    is_clean_label = contamination_label == "clean"
    clean = (not invalidated) and is_clean_label and all(v.ok for v in vectors)

    if invalidated:
        track = TRACK_INVALID
    elif is_clean_label:
        track = TRACK_GENERAL if clean else TRACK_INVALID  # clean-labeled but a vector failed ⇒ not admissible
    else:
        track = TRACK_IN_DOMAIN

    if invalidated or (is_clean_label and not clean):
        logger.warning("Jetson firewall: cell not admissible — %s", "; ".join(reasons) or "vector failure")

    return FirewallVerdict(track=track, clean=clean, invalidated=invalidated, vectors=vectors, reasons=reasons)


def evaluate_jetson_cell(
    *,
    requested_alias: str,
    system_fingerprint: Optional[str],
    sent_prompt: Optional[str],
    expected_neutral: str,
    sampling: Optional[Dict[str, Any]] = None,
    quant: Optional[str] = None,
) -> FirewallVerdict:
    """Convenience wrapper: resolve the expected served id / base-ness / contamination label from
    the ``JetsonProvider`` alias map, then ``evaluate`` (FR-J5a/J6/J6b/J8)."""
    from ..providers.jetson import JetsonProvider

    p = JetsonProvider()
    return evaluate(
        contamination_label=p.contamination_label(requested_alias),
        expected_served_id=p.served_id(requested_alias),
        expect_base=p.is_base(requested_alias),
        system_fingerprint=system_fingerprint,
        sent_prompt=sent_prompt,
        expected_neutral=expected_neutral,
        sampling=sampling,
        quant=quant,
    )
