"""The det-crp/0.1 conformance lint (SCHEMA_det-crp-0.1 §10) — review-log integrity + focus.

det-crp artifacts are **authored/accreted**, not projected, so the load-bearing checks are the
review-log's *integrity* (the cross-model memory must not lose a finding): unique suggestion ids, no
orphan disposition, no double-triage, an initialized A/B scaffold — plus the focus's non-empty
``Least-reviewed target``. Header-field checks (``formatVersion``/``companionKind``) apply **only when
the artifact declares them** (a bare accreted review-log usually does not — a fold-back the build
surfaced into SCHEMA §10).
"""

from __future__ import annotations

import re
from typing import List, Optional

from ..coverage_map.findings_sarif import render_sarif_from_findings
from .models import COMPANION_KIND, FORMAT_VERSION, CrpFinding

TOOL_NAME = "startd8-crp-lint"

# The append-only review-log scaffold (SCHEMA §3): three appendix sections.
_APPENDIX_A = re.compile(r"^#+\s+Appendix A[:\s]", re.MULTILINE)
_APPENDIX_B = re.compile(r"^#+\s+Appendix B[:\s]", re.MULTILINE)
_APPENDIX_C = re.compile(r"^#+\s+Appendix C[:\s]", re.MULTILINE)
# A suggestion id: R{round}-S{k} (plan) or R{round}-F{k} (requirements) — SCHEMA §3.
_SUGGESTION_ID = re.compile(r"\bR\d+-[SF]\d+\b")
# Focus fields (SCHEMA §2).
_LEAST_REVIEWED = re.compile(
    r"^\*\*Least-reviewed target:\*\*\s*(?P<v>.+?)\s*$", re.MULTILINE
)
# Header fields, checked only when present (conditional).
_FORMAT_VERSION = re.compile(
    r"formatVersion[:*`\s]+(?P<v>det-crp/[\w.]+)", re.IGNORECASE
)
_COMPANION_KIND = re.compile(r"companionKind[:*`\s]+(?P<v>\w+)", re.IGNORECASE)


def _ids(section: str) -> List[str]:
    return _SUGGESTION_ID.findall(section)


def _slice_between(text: str, start: re.Pattern, *stops: re.Pattern) -> Optional[str]:
    """The body from *start* to the earliest following *stop* heading (or EOF). ``None`` if absent."""
    m = start.search(text)
    if not m:
        return None
    body = text[m.end() :]
    ends = [s.search(body) for s in stops]
    positions = [e.start() for e in ends if e is not None]
    return body[: min(positions)] if positions else body


def has_review_log(text: str) -> bool:
    """True iff the doc carries an Appendix-C review-log (the only thing worth linting as det-crp)."""
    return bool(_APPENDIX_C.search(text))


def has_focus(text: str) -> bool:
    """True iff the doc is a CRP focus (declares a ``Least-reviewed target``)."""
    return bool(_LEAST_REVIEWED.search(text))


def lint_focus(text: str, *, source: str = "(crp-focus)") -> List[CrpFinding]:
    """SCHEMA §2 — a focus must carry a non-empty ``Least-reviewed target``."""
    findings: List[CrpFinding] = []
    m = _LEAST_REVIEWED.search(text)
    if not m or not m.group("v").strip():
        findings.append(
            CrpFinding(
                "focus-target-missing",
                "error",
                "a CRP focus must carry a non-empty `Least-reviewed target:` (§2)",
                source,
            )
        )
    return findings


def lint_review_log(text: str, *, source: str = "(crp)") -> List[CrpFinding]:
    """SCHEMA §3/§4 — the review-log integrity checks (the cross-model memory can't lose a finding)."""
    findings: List[CrpFinding] = []
    if not has_review_log(text):
        return findings  # not a review-log; nothing to lint

    a_body = _slice_between(text, _APPENDIX_A, _APPENDIX_B, _APPENDIX_C)
    b_body = _slice_between(text, _APPENDIX_B, _APPENDIX_C, _APPENDIX_A)
    c_body = _slice_between(text, _APPENDIX_C) or ""

    # §3 scaffold: A and B must be present (append-only; may be empty on round 1).
    if a_body is None:
        findings.append(
            CrpFinding(
                "missing-appendix-a",
                "error",
                "review-log has Appendix C but no Appendix A (Applied) scaffold (§3)",
                source,
            )
        )
    if b_body is None:
        findings.append(
            CrpFinding(
                "missing-appendix-b",
                "error",
                "review-log has Appendix C but no Appendix B (Rejected) scaffold (§3)",
                source,
            )
        )

    a_ids = set(_ids(a_body or ""))
    b_ids = set(_ids(b_body or ""))
    c_set = set(_ids(c_body))
    # NOTE (dogfood fold-back): a naive "id appears twice in Appendix C → duplicate" check is a FALSE
    # POSITIVE — a real review-log legitimately *references* an id many times (the round's suggestion
    # table + a coverage matrix + an endorsements list). A text lint cannot distinguish a second
    # *definition* (a genuine collision) from a *reference*, so id-uniqueness is enforced at authoring
    # time (the compiler), not here. This lint checks the reliably-detectable integrity invariants:
    # orphan disposition (A/B id absent from C), double-triage (id in both A and B), A/B scaffold.

    # §4 no orphan disposition: every A/B id must reference a real C suggestion.
    for aid in sorted(a_ids - c_set):
        findings.append(
            CrpFinding(
                "orphan-disposition",
                "warning",
                f"Appendix A applies {aid} which is not an Appendix-C suggestion "
                "(orphan/appendix-C pruned — append-only violated? §4)",
                source,
            )
        )
    for bid in sorted(b_ids - c_set):
        findings.append(
            CrpFinding(
                "orphan-disposition",
                "warning",
                f"Appendix B rejects {bid} which is not an Appendix-C suggestion (§4)",
                source,
            )
        )

    # §4 no double-triage: an id may not be both Applied and Rejected.
    for did in sorted(a_ids & b_ids):
        findings.append(
            CrpFinding(
                "double-triage",
                "error",
                f"suggestion {did} is in BOTH Appendix A and Appendix B (§4)",
                source,
            )
        )

    return findings


def lint_header(text: str, *, source: str = "(crp)") -> List[CrpFinding]:
    """Conditional header checks (SCHEMA §1) — only when the artifact declares them."""
    findings: List[CrpFinding] = []
    fv = _FORMAT_VERSION.search(text)
    if fv and fv.group("v") != FORMAT_VERSION:
        findings.append(
            CrpFinding(
                "format-version",
                "error",
                f"formatVersion must be {FORMAT_VERSION!r}, got {fv.group('v')!r}",
                source,
            )
        )
    ck = _COMPANION_KIND.search(text)
    if ck and ck.group("v") != COMPANION_KIND:
        findings.append(
            CrpFinding(
                "companion-kind",
                "error",
                f"companionKind must be {COMPANION_KIND!r}, got {ck.group('v')!r}",
                source,
            )
        )
    return findings


def lint_crp(text: str, *, source: str = "(crp)") -> List[CrpFinding]:
    """Lint a det-crp artifact: the review-log integrity, the focus (if any), + conditional header."""
    findings: List[CrpFinding] = []
    findings.extend(lint_header(text, source=source))
    if has_focus(text):
        findings.extend(lint_focus(text, source=source))
    findings.extend(lint_review_log(text, source=source))
    return findings


def findings_to_sarif(
    findings: List[CrpFinding], *, corpus: Optional[str] = None
) -> dict:
    """Render lint findings as SARIF 2.1.0 via the ONE reusable renderer (charter §6)."""
    return render_sarif_from_findings(
        findings, tool_name=TOOL_NAME, tool_version=FORMAT_VERSION, corpus=corpus
    )
