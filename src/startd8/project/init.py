# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Deterministic ($0, no-LLM) project onboarding — ``startd8 project init``.

A thin orchestrator (bucket-1 applicational-completion) that turns a directory into a set-up StartD8
project by **composing already-shipped, already-confined functions** — it defines no new write
primitive. It:

1. **detects** the project shape (greenfield / brownfield_ready / brownfield_partial) from
   deterministic on-disk signals, folding in the read-only ``concierge`` survey/assess (FR-1/FR-2);
2. **establishes** the ``.startd8/`` role postings — VIPP always, FDE opt-in (FR-3);
3. makes the project **VIPP-inbox-*ready*** by standing up the inbox *mechanism* (``.gitignore`` +
   monotonic ``inbox-seq``) via the shared ``vipp_seam.ensure_inbox_scaffold`` (FR-4/FR-11);
4. optionally runs a **``$0`` non-interactive inbox *producer seam*** (closes issue #76) over
   explicitly-supplied (``--proposals``) or greenfield-auto-derived (``--instantiate``) proposals —
   it **never invents content** (FR-5/FR-12/FR-13/FR-14);
5. **reports** what it did + the next command (FR-9), and supports a read-only ``--check`` drift
   audit (FR-10).

The central design fact (requirements §0): **project ground-truth adjudicates, it does not
originate** proposals — so a healthy brownfield project is inbox-*ready*, not inbox-*produced*.
Production is always gated on a real, declared gap.

Every project-content write rides ``concierge.safe_write.apply_write_plan`` (FR-7). The postings'
``.startd8/*-context.json`` metadata is written by the SDK-owned ``ensure_posting`` atomic-metadata
path (a distinct, sanctioned boundary — it is SDK state, not project content).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ..logging_config import get_logger

if TYPE_CHECKING:  # type-only; the runtime import stays lazy to keep this module import-light
    from ..kickoff_experience.proposals import ProposalBuffer

logger = get_logger(__name__)

SCHEMA_VERSION = 1

# --- project shape verdicts -----------------------------------------------------------------------
SHAPE_GREENFIELD = "greenfield"
SHAPE_BROWNFIELD_READY = "brownfield_ready"
SHAPE_BROWNFIELD_PARTIAL = "brownfield_partial"

# The four kickoff input domains a complete brownfield project declares (mirrors
# concierge.core._assess_kickoff_inputs so the "ready vs partial" boundary stays aligned).
_KICKOFF_INPUT_DOMAINS = ("business-targets", "observability", "conventions", "build-preferences")

_CONTRACT_REL = "prisma/schema.prisma"


@dataclass
class ProjectShape:
    """Deterministic triage of a directory's project shape (FR-2). All signals are on-disk presence
    checks — no file contents are interpreted for the verdict."""

    verdict: str
    has_contract: bool
    has_app: bool
    kickoff_inputs_present: List[str] = field(default_factory=list)
    has_vipp_posting: bool = False
    has_fde_posting: bool = False

    @property
    def is_greenfield(self) -> bool:
        return self.verdict == SHAPE_GREENFIELD

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "has_contract": self.has_contract,
            "has_app": self.has_app,
            "kickoff_inputs_present": sorted(self.kickoff_inputs_present),
            "kickoff_inputs_expected": list(_KICKOFF_INPUT_DOMAINS),
            "has_vipp_posting": self.has_vipp_posting,
            "has_fde_posting": self.has_fde_posting,
        }


def detect_shape(project_root: Any) -> ProjectShape:
    """Classify a directory as greenfield / brownfield_ready / brownfield_partial (FR-2), $0/read-only.

    - **greenfield** — no contract, no ``app/`` package, no kickoff inputs (a bare directory).
    - **brownfield_ready** — a contract exists AND all four kickoff input domains are declared: a set-up
      app with nothing deterministic left to propose against (requirements OQ-4/D10).
    - **brownfield_partial** — an app-shaped directory (contract / ``app/`` / some kickoff inputs) that
      is not yet complete. A gap *may* exist, but production still requires authored content (§0).
    """
    root = Path(project_root)
    has_contract = (root / _CONTRACT_REL).is_file()
    has_app = (root / "app").is_dir()
    inputs_dir = root / "docs" / "kickoff" / "inputs"
    present = [d for d in _KICKOFF_INPUT_DOMAINS if (inputs_dir / f"{d}.yaml").is_file()]
    has_vipp = (root / ".startd8" / "vipp").is_dir()
    has_fde = (root / ".startd8" / "fde").is_dir()

    is_brownfield = has_contract or has_app or bool(present)
    if not is_brownfield:
        verdict = SHAPE_GREENFIELD
    elif has_contract and len(present) == len(_KICKOFF_INPUT_DOMAINS):
        verdict = SHAPE_BROWNFIELD_READY
    else:
        verdict = SHAPE_BROWNFIELD_PARTIAL

    return ProjectShape(
        verdict=verdict,
        has_contract=has_contract,
        has_app=has_app,
        kickoff_inputs_present=present,
        has_vipp_posting=has_vipp,
        has_fde_posting=has_fde,
    )


# --- M1: postings + inbox-ready -------------------------------------------------------------------


def establish_postings(
    project_root: Any, *, with_fde: bool = False, sdk_version: str
) -> Dict[str, str]:
    """Create the ``.startd8/`` role postings via the existing idempotent ``ensure_posting`` (FR-3).

    VIPP always; FDE only when ``with_fde`` (requirements OQ-2 — no Concierge posting exists, D4).
    Returns ``{role: context-file-path}``.

    FR-7 boundary: ``ensure_posting`` writes the SDK-owned ``.startd8/<role>/<role>-context.json``
    via its own atomic-metadata path (not ``apply_write_plan``). This is a *sanctioned* exception —
    that file is SDK state (it restamps ``updated_at`` / the SDK version each call), **not project
    content**. All *project-content* writes (the inbox scaffold, the produced inbox) ride
    ``apply_write_plan`` (via ``ensure_inbox_scaffold`` / ``serialize_buffer``).
    """
    from ..vipp import context as vipp_context

    root = Path(project_root)
    postings: Dict[str, str] = {}
    postings["vipp"] = str(vipp_context.ensure_posting(root, sdk_version=sdk_version))
    if with_fde:
        from ..fde import context as fde_context

        postings["fde"] = str(fde_context.ensure_posting(root, sdk_version=sdk_version))
    return postings


def ready_inbox(project_root: Any):
    """Stand up the inbox *mechanism* — not the inbox file (FR-4). Delegates to the shared
    ``ensure_inbox_scaffold`` (FR-11) so it can never drift from the producer path. No-clobber, so a
    re-run (or a mid-loop project) writes nothing and keeps any advanced ``inbox-seq``."""
    from ..kickoff_experience.vipp_seam import ensure_inbox_scaffold

    return ensure_inbox_scaffold(project_root)


# --- M2: the $0 non-interactive producer seam (closes #76) ----------------------------------------


class ProposalsFileError(ValueError):
    """The ``--proposals`` file is unreadable or structurally malformed (exit 2, nothing written)."""


def _rejection_detail(ack: str) -> str:
    """Pretty the propose-handler ack for an error message — used only for the *message*, never as
    the accept/reject decision (that comes from the buffer-length delta, so a change to the handler's
    ack wording can never silently turn a rejection into an acceptance)."""
    return ack[len("error:"):].strip() if ack.startswith("error:") else ack.strip()


def _load_proposals_file(path: Path) -> List[Dict[str, Any]]:
    """Parse an authored ``--proposals`` file into a list of ``{kind, ...params}`` entries (OQ-7).

    Accepts YAML or JSON; a top-level list, or a mapping with a ``proposals:`` list. Each entry must
    be a mapping carrying at least ``kind`` — ids are assigned by the producer, never trusted from the
    file. Parsing/shape errors raise :class:`ProposalsFileError` (never a half-read inbox, FR-12).
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProposalsFileError(f"cannot read proposals file {path}: {exc}") from exc

    data: Any
    try:
        import yaml  # PyYAML also parses JSON

        data = yaml.safe_load(raw)
    except Exception:
        try:
            data = json.loads(raw)
        except Exception as exc:
            raise ProposalsFileError(f"{path} is not valid YAML or JSON: {exc}") from exc

    if isinstance(data, dict) and "proposals" in data:
        data = data.get("proposals")
    if not isinstance(data, list):
        raise ProposalsFileError(
            f"{path} must be a list of proposals (or a mapping with a 'proposals:' list)"
        )
    entries: List[Dict[str, Any]] = []
    for i, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ProposalsFileError(f"{path}: proposal #{i} is not a mapping")
        if not str(entry.get("kind", "")).strip():
            raise ProposalsFileError(f"{path}: proposal #{i} is missing a 'kind'")
        entries.append(entry)
    return entries


def _buffer_from_entries(
    project_root: Any, entries: List[Dict[str, Any]]
) -> "ProposalBuffer":
    """Validate each authored entry through the **same per-kind validators the propose handler uses**
    (FR-12) and record it into a :class:`ProposalBuffer` — building each as a ``ProposedAction`` so the
    downstream ``serialize_buffer`` keeps envelope parity (FR-14). A rejected entry raises
    :class:`ProposalsFileError` before anything is serialized (exit 2, no half-written inbox).

    Accept/reject is decided by whether the handler **recorded into the buffer** (its actual contract),
    not by sniffing the ack string — so a reworded handler message can never silently admit a bad
    proposal."""
    from ..kickoff_experience.proposals import ProposalBuffer, make_propose_handler

    buffer = ProposalBuffer()
    handler = make_propose_handler(str(project_root), buffer)
    for i, entry in enumerate(entries):
        before = len(buffer)
        ack = handler(dict(entry))
        if len(buffer) == before:  # the handler records only on success — nothing recorded ⇒ rejected
            raise ProposalsFileError(
                f"proposal #{i} ({entry.get('kind')!r}) rejected — {_rejection_detail(ack)}"
            )
    return buffer


def produce_inbox(
    project_root: Any,
    shape: ProjectShape,
    *,
    proposals_file: Optional[Path] = None,
    instantiate: bool = False,
    posture: str = "prototype",
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """The gated ``$0`` producer (FR-5). Returns a structured result the caller folds into the report.

    Sources, in order (both never invent content — §0/NR-3):
    - ``proposals_file`` — an operator/agent-authored set, each entry validated per-kind (FR-12);
    - greenfield ``instantiate`` — the one deterministic ground-truth→proposal mapping (D8): a single
      ``instantiate`` ``ProposedAction`` whose bytes are the packaged templates.
    Otherwise nothing is produced — a ``brownfield_ready`` project is inbox-*ready* (OQ-4).

    Result ``status`` ∈ {``produced``, ``skipped_undrained``, ``no_gap``, ``not_greenfield``}.
    """
    from ..kickoff_experience.proposals import ProposalBuffer, make_propose_handler
    from ..kickoff_experience.vipp_seam import serialize_buffer

    root = Path(project_root)

    if proposals_file is not None:
        entries = _load_proposals_file(Path(proposals_file))
        buffer = _buffer_from_entries(root, entries)
        source = {"kind": "proposals-file", "path": str(proposals_file), "count": len(entries)}
    elif instantiate:
        if not shape.is_greenfield:
            # The instantiate mapping only applies to a greenfield dir with no kickoff package (D8).
            return {
                "status": "not_greenfield",
                "detail": (
                    "--instantiate is the greenfield-only deterministic proposal; this project is "
                    f"'{shape.verdict}'. Supply --proposals for an authored proposal set instead."
                ),
            }
        # Build via the propose handler so posture is validated by the same path (FR-12/FR-14).
        buffer = ProposalBuffer()
        handler = make_propose_handler(str(root), buffer)
        ack = handler({"kind": "instantiate", "posture": posture})
        if len(buffer) == 0:  # not recorded ⇒ rejected (buffer-delta, not string-sniffing)
            return {"status": "rejected", "detail": _rejection_detail(ack)}
        source = {"kind": "instantiate", "posture": posture}
    else:
        return {"status": "no_gap", "detail": "inbox-ready; no deterministic gap to propose against"}

    result = serialize_buffer(buffer, root, project_id=project_id or root.name)

    # FR-13: a no-clobber-of-undrained skip is a clean exit 0, not a failure.
    if result.skipped and not result.written:
        return {
            "status": "skipped_undrained",
            "detail": "an undrained inbox already exists — consume it first (`startd8 vipp negotiate` / `apply`)",
            "skipped": result.skipped,
        }
    if not result.ok:  # confinement / OS error → surfaced as a blocked write (exit 3)
        return {"status": "blocked", "detail": str(result.blocked + result.errors)}
    return {
        "status": "produced",
        "source": source,
        "written": sorted(result.written),
        "proposal_count": len(buffer),
    }


# --- M3 preview: read-only --check drift audit ----------------------------------------------------


def check_init(project_root: Any) -> Dict[str, Any]:
    """Read-only audit (FR-10): is the project init'd + in-sync? Writes nothing. The caller maps
    ``error`` → exit 2, ``in_sync`` → exit 0, drift → 1. A never-init'd project reports as drift
    (not initialized). An unreadable / non-directory root is an ``error`` (exit 2), mirroring
    ``cli_generate``'s cannot-read path."""
    root = Path(project_root)
    if not root.is_dir():
        return {
            "schema_version": SCHEMA_VERSION,
            "action": "init-check",
            "project_root": str(root),
            "error": f"project root is not a directory: {root}",
            "in_sync": False,
        }
    vipp_dir = root / ".startd8" / "vipp"
    checks = {
        "vipp_posting": (vipp_dir / "vipp-context.json").is_file(),
        "inbox_gitignore": (vipp_dir / ".gitignore").is_file(),
        "inbox_seq": (vipp_dir / "inbox-seq").is_file(),
    }
    drift = sorted(k for k, ok in checks.items() if not ok)
    initialized = checks["vipp_posting"]
    return {
        "schema_version": SCHEMA_VERSION,
        "action": "init-check",
        "project_root": str(root),
        "initialized": initialized,
        "in_sync": not drift,
        "checks": checks,
        "drift": drift,
    }


# --- top-level orchestrator ------------------------------------------------------------------------


def run_project_init(
    project_root: Any,
    *,
    with_fde: bool = False,
    instantiate: bool = False,
    proposals_file: Optional[Path] = None,
    posture: str = "prototype",
    check: bool = False,
    sdk_version: str = "0.0.0",
) -> Dict[str, Any]:
    """Orchestrate ``startd8 project init`` and return a schema-versioned summary (FR-1/FR-9).

    Deterministic, ``$0``, no LLM. In ``check`` mode it is read-only. Otherwise: establish postings →
    ready the inbox → (optionally) produce an inbox from a declared gap → summarize. Idempotent: a
    re-run on an init'd project writes nothing (FR-6).

    FR-7: the confined root is validated **up front** (before ``establish_postings``), so a
    symlinked / escaping root fails fast with ``SafeWriteError`` and init never writes *anything* —
    not even the SDK-owned posting metadata — outside the confined project root.
    """
    if check:
        audit = check_init(project_root)
        audit["shape"] = detect_shape(project_root).to_dict()
        return audit

    # Validate confinement before the first write (FR-7). Downstream writes operate on the resolved
    # real path; ``ensure_posting`` (which has no guard of its own) can no longer write through a
    # symlinked root because we would have raised here first.
    from ..concierge.safe_write import resolve_confined_root

    root = resolve_confined_root(project_root)

    # The two producer sources are mutually exclusive — fail loudly rather than silently ignore one.
    if proposals_file is not None and instantiate:
        raise ProposalsFileError(
            "choose one producer source: --proposals FILE or --instantiate, not both"
        )

    shape = detect_shape(root)

    summary: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "action": "init",
        "project_root": str(root),
        "shape": shape.to_dict(),
    }

    postings = establish_postings(root, with_fde=with_fde, sdk_version=sdk_version)
    summary["postings"] = postings

    inbox_result = ready_inbox(root)
    summary["inbox_ready"] = {
        "written": sorted(inbox_result.written),
        "already_present": [s.get("path") for s in inbox_result.skipped],
    }

    summary["producer"] = produce_inbox(
        root,
        shape,
        proposals_file=proposals_file,
        instantiate=instantiate,
        posture=posture,
    )
    summary["next"] = "startd8 vipp negotiate"
    return summary
