"""Generic finding → SARIF 2.1.0 renderer — the reusable findings sink.

``coverage_map/engine.py::render_sarif`` renders a *coverage* report (which OTel §5 domains a
file touches) as SARIF. This module lifts the same 2.1.0 shape to a *generic finding*: any
producer of per-file findings — a rule id, a severity, a message, a file, an optional line —
can emit GitHub-code-scanning / IDE-consumable SARIF through one function, without knowing
anything about the coverage-map's crosswalk/pattern model.

Why this is nearly free: the SDK already has one near-universal finding shape —
``validators.semantic_checks.SemanticIssue`` (``check`` / ``severity`` / ``message`` / ``line`` /
``file_path``), emitted by all five language semantic validators. ``query_prime.models``'s
``SecurityFinding`` and ``security_prime.gate_models``'s ``GateFinding`` carry the same fields
under ``check_type``. This renderer **duck-types** them: it reads ``check`` *or* ``check_type``
(and ``file_path`` / ``file`` / ``source_file``), so it consumes every one of those producers —
plus plain dicts — with no per-producer adapter class.

Design note (Mottainai / anti-over-abstraction): coverage's ``render_sarif`` is a *merged, tested*
path and stays byte-for-byte as-is. This is its generic sibling, not a refactor of it. Folding
coverage onto this core is a behaviour-preserving follow-up gated by a parity test — see
``docs/design/SARIF-FINDINGS-REUSABILITY.md`` (the producer inventory + convergence plan).
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

#: The SARIF 2.1.0 JSON-schema URL (top-level ``$schema``; validators key on this + ``version``).
#: Kept identical to ``engine.SARIF_SCHEMA_URI`` so both renderers advertise the same schema.
SARIF_SCHEMA_URI = (
    "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"
)

_DEFAULT_INFO_URI = "https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html"

#: SARIF ``level`` is a closed vocabulary (none/note/warning/error). Map common severity strings
#: onto it; an unknown/absent severity degrades to ``warning`` (never crashes, never drops).
_SEVERITY_TO_LEVEL = {
    "error": "error", "err": "error", "critical": "error", "high": "error", "fatal": "error",
    "warning": "warning", "warn": "warning", "medium": "warning",
    "info": "note", "note": "note", "low": "note", "hint": "note", "none": "none",
}
_DEFAULT_LEVEL = "warning"


def _severity_to_level(severity: Any) -> str:
    return _SEVERITY_TO_LEVEL.get(str(severity or "").strip().lower(), _DEFAULT_LEVEL)


def _field(finding: Any, *names: str) -> Any:
    """First non-None value among *names*, read as an attribute then as a dict key."""
    for n in names:
        v = getattr(finding, n, None)
        if v is not None:
            return v
    if isinstance(finding, dict):
        for n in names:
            if finding.get(n) is not None:
                return finding[n]
    return None


def _rule_id(finding: Any) -> Optional[str]:
    """Rule id from a duck-typed finding: ``.check`` (SemanticIssue) or ``.check_type``
    (SecurityFinding/GateFinding). An enum ``check_type`` stringifies via ``.value`` → ``.name``
    → ``str()`` so ``SecurityCheckType.INJECTION`` becomes a stable ``ruleId``."""
    raw = _field(finding, "check", "check_type", "rule_id", "check_id", "category")
    if raw is None:
        return None
    for attr in ("value", "name"):
        v = getattr(raw, attr, None)
        if isinstance(v, str) and v:
            return v
    return str(raw)


def render_sarif_from_findings(
    findings: Iterable[Any],
    *,
    tool_name: str,
    tool_version: str = "unknown",
    information_uri: str = _DEFAULT_INFO_URI,
    rule_help_uris: Optional[dict[str, str]] = None,
    corpus: Optional[str] = None,
) -> dict[str, Any]:
    """Render an iterable of per-file findings as a SARIF 2.1.0 document.

    A *finding* is duck-typed — any object (or dict) exposing:

    * a **rule id** — ``.check`` or ``.check_type`` (enum accepted) or ``.rule_id`` / ``.check_id``
      / ``.category``;
    * ``.severity`` → SARIF ``level`` (error / warning / note; unknown or absent → ``warning``);
    * ``.message``;
    * a **file** — ``.file_path`` (or ``.file`` / ``.source_file`` / ``.uri``) → ``artifactLocation.uri``;
    * ``.line`` (optional, 1-based) → ``physicalLocation.region.startLine``.

    A finding lacking a rule id *or* a file uri cannot be represented in SARIF; it is **skipped**
    (never emitted invalid) and counted in ``runs[0].invocations[0].properties.skipped`` so the
    drop is honest, not silent. ``rules`` are emitted once per distinct id, in first-seen order.
    ``rule_help_uris`` optionally maps a rule id to a doc URL (else ``information_uri``).

    The document validates against the 2.1.0 shape: top-level ``$schema`` + ``version`` + a
    ``runs`` array, each run a ``tool.driver`` (with ``rules``) + ``invocations`` + ``results``.
    """
    rule_help_uris = rule_help_uris or {}
    results: list[dict[str, Any]] = []
    rule_ids: dict[str, None] = {}  # ordered set (first-seen)
    skipped = 0

    for f in findings:
        rid = _rule_id(f)
        uri = _field(f, "file_path", "file", "source_file", "uri")
        if not rid or not uri:
            skipped += 1
            continue
        rule_ids.setdefault(rid, None)

        physical: dict[str, Any] = {"artifactLocation": {"uri": str(uri)}}
        line = _field(f, "line")
        if isinstance(line, int) and line > 0:
            physical["region"] = {"startLine": line}

        results.append({
            "ruleId": rid,
            "level": _severity_to_level(_field(f, "severity")),
            "message": {"text": str(_field(f, "message") or rid)},
            "locations": [{"physicalLocation": physical}],
        })

    rules = [
        {
            "id": rid,
            "name": rid,
            "shortDescription": {"text": rid.replace("_", " ")},
            "helpUri": rule_help_uris.get(rid, information_uri),
        }
        for rid in rule_ids
    ]

    invocation: dict[str, Any] = {"executionSuccessful": True}
    props: dict[str, Any] = {}
    if corpus is not None:
        props["corpus"] = corpus
    if skipped:
        props["skipped"] = skipped
    if props:
        invocation["properties"] = props

    return {
        "$schema": SARIF_SCHEMA_URI,
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": tool_name,
                    "informationUri": information_uri,
                    "version": str(tool_version),
                    "rules": rules,
                },
            },
            "invocations": [invocation],
            "results": results,
        }],
    }
