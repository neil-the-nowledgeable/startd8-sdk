"""Method-alignment pre-step for the combined scoreboard (M2 — CS-15, CS-7, CS-16).

`merge_runs` (M1) only merges cells scored under the **same** method signature (CS-5): a run whose
``parity_key`` differs from the anchor is silently *excluded*. That is safe but lossy — a run that is
merely **behind** the target (an older `sdk_version`, scored before a gate-fix landed) carries the same
on-disk artifacts and could be *brought current* by re-scoring (`rescore_run`, $0, no LLM). M2 runs
**before** merge and decides, per input run, whether it is:

  - ``already_current``        — its ``parity_key`` already equals the target → use as-is.
  - ``aligned``                — BEHIND the target within the same method-class AND it has a
                                 ``sandboxes/`` dir → rescore it to the current scoring layer and use
                                 the **in-memory** rescored cells (the source dir is never mutated).
  - ``excluded:no_sandboxes``  — behind the target but no ``sandboxes/`` → cannot be re-scored → drop.
  - ``excluded:calibration``   — a genuinely **different method-class** (e.g. ``naive``), not a version
                                 lag → drop. You cannot rescore a naive run into an expose run: expose
                                 requires the defect ledger, which re-scoring old artifacts may not
                                 reproduce. Treat method-class differences as exclusions, conservatively.

**Non-destructive (hard requirement).** Alignment never writes to the input dirs. ``rescore_run`` has a
preview mode (``write=False``, the default) that returns the rescored ``CellResult`` objects in
``RescoreReport.cells`` *without* persisting — so M2 uses that and hands the in-memory cells to M3. No
temp-copy is needed (see ``align_runs`` docstring).

**Fairness is preserved (CS-7).** Re-scoring only touches ``status == "ok"`` cells (``rescore_run``
leaves ``deps_missing`` / ``infra_fail`` / ``failed`` / ``timeout`` cells untouched), so the persisted
fairness classification is never recomputed or overridden here.

**Conservative when unsure.** Anything that is not an unambiguous version-lag within the same
method-class is excluded with a clear reason rather than silently aligned — a false exclusion is safe
(the run just doesn't contribute), a false alignment is a silently-wrong consolidated board.

The surviving inputs are returned as :class:`AlignedInput` records — each carries EITHER the original
``run_dir`` (for ``already_current`` runs M3 can read from disk) OR an in-memory ``cells`` list (for
``aligned`` runs, so the merge consumes the re-scored cells without re-reading the unmutated source).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .method import MethodSignature, method_signature
from .rescore import SANDBOXES_DIR, rescore_run
from .runner import CellResult

# Action tags (also used as the `action` field value).
ACTION_ALREADY_CURRENT = "already_current"
ACTION_ALIGNED = "aligned"
ACTION_EXCLUDED_NO_SANDBOXES = "excluded:no_sandboxes"
ACTION_EXCLUDED_CALIBRATION = "excluded:calibration"
ACTION_EXCLUDED_ERROR = "excluded:rescore_error"

# The method-class of a signature, used to decide version-lag (alignable) vs different method (exclude).
# Within a class, only the version/formula may differ; across classes, never align.
#   expose-class:  expose, shadow+expose  (the defect-ledger family — the current canonical board)
#   raw-class:     raw, shadow            (no defect ledger, repair posture only)
#   naive-class:   naive                  (apply + no expose — the pre-stamp default; calibration)
#   unknown:       unknown                (unresolvable — never alignable)
_METHOD_CLASS = {
    "expose": "expose",
    "shadow+expose": "expose",
    "raw": "raw",
    "shadow": "raw",
    "naive": "naive",
    "unknown": "unknown",
}


def _method_class(sig: MethodSignature) -> str:
    return _METHOD_CLASS.get(sig.scoring_method, "unknown")


@dataclass
class AlignmentAction:
    """The alignment decision (and its evidence) for one input run."""
    run: str                                    # the run dir's name (provenance)
    action: str                                 # already_current | aligned | excluded:*
    reason: str
    signature_before: MethodSignature
    signature_after: Optional[MethodSignature] = None  # post-rescore signature (aligned only)

    @property
    def included(self) -> bool:
        return self.action in (ACTION_ALREADY_CURRENT, ACTION_ALIGNED)


@dataclass
class AlignedInput:
    """A surviving input M3 can feed to ``merge_runs``. Carries EITHER the original ``run_dir`` (read
    from disk) OR an in-memory ``cells`` list (re-scored, source dir untouched). Exactly one is set."""
    run_dir: Path
    action: str
    cells: Optional[List[CellResult]] = None    # set for `aligned`; None ⇒ read run_dir from disk

    @property
    def is_rescored(self) -> bool:
        return self.cells is not None


@dataclass
class AlignmentResult:
    """The M2 verdict over a list of input runs (CS-15)."""
    target: MethodSignature
    actions: List[AlignmentAction] = field(default_factory=list)
    inputs: List[AlignedInput] = field(default_factory=list)  # the survivors, anchor-first order
    warnings: List[str] = field(default_factory=list)

    @property
    def aligned_run_dirs(self) -> List[Path]:
        """The surviving run dirs, in priority order — a convenience for callers that merge from disk.

        NOTE: for ``aligned`` inputs this is the *unmutated* source dir; its on-disk cells are STALE
        (still pre-rescore). Prefer :attr:`inputs` (which carries the in-memory re-scored cells) when
        feeding ``merge_runs`` so the aligned scores are the ones that merge. Provided for callers that
        only need the surviving set (e.g. logging / provenance)."""
        return [i.run_dir for i in self.inputs]

    @property
    def included_actions(self) -> List[AlignmentAction]:
        return [a for a in self.actions if a.included]

    @property
    def excluded_actions(self) -> List[AlignmentAction]:
        return [a for a in self.actions if not a.included]


def _has_sandboxes(run_dir: Path) -> bool:
    sb = run_dir / SANDBOXES_DIR
    try:
        return sb.is_dir() and any(sb.iterdir())
    except OSError:  # CS-16: an unreadable dir is a degrade, not a crash
        return False


def align_runs(
    run_dirs,
    seeds_dir,
    *,
    target: Optional[MethodSignature] = None,
    **rescore_kwargs,
) -> AlignmentResult:
    """Classify + (where possible) re-score each input run to a single target method (CS-15).

    Args:
        run_dirs: input benchmark run dirs, **anchor (most-canonical) first**. The first run's
            signature is the default target (the mergeable group all survivors share).
        seeds_dir: the OB seeds dir — required by ``rescore_run`` to resolve each service's primary
            file when re-scoring an ``aligned`` run. (Unused for ``already_current`` / excluded runs.)
        target: override the target method signature (default: the anchor run's signature).
        **rescore_kwargs: forwarded verbatim to ``rescore_run`` for ``aligned`` runs (e.g. ``cfg``,
            ``pass_threshold``, ``run_lint``). ``write`` is FORCED to ``False`` — alignment is
            non-destructive (the input dirs are never mutated); any caller-supplied ``write`` is ignored.

    Returns an :class:`AlignmentResult`. **Pure / $0** — ``rescore_run`` invokes no model, and this
    function never writes to ``run_dirs`` (it uses ``rescore_run``'s preview mode, ``write=False``, and
    consumes the in-memory ``RescoreReport.cells``). Never raises on a partial/missing input (CS-16).
    """
    dirs = [Path(d) for d in run_dirs]
    seeds_dir = Path(seeds_dir)
    # `write` is non-negotiable here regardless of what the caller passed.
    rescore_kwargs.pop("write", None)

    if not dirs:
        unknown = MethodSignature("unknown", False, None, None, "none")
        return AlignmentResult(target=unknown, warnings=["no run dirs given"])

    sigs = [method_signature(d) for d in dirs]
    target_sig = target if target is not None else sigs[0]
    target_class = _method_class(target_sig)

    result = AlignmentResult(target=target_sig)
    if target_class in ("naive", "unknown"):
        result.warnings.append(
            f"target method is {target_sig.scoring_method!r} (class {target_class}) — "
            "list the canonical scored run first, or pass an explicit target?"
        )

    for d, sig in zip(dirs, sigs):
        name = d.name

        # 1. Already at the target parity → use as-is.
        if sig.parity_key == target_sig.parity_key:
            result.actions.append(AlignmentAction(
                name, ACTION_ALREADY_CURRENT, "parity_key matches target",
                signature_before=sig, signature_after=sig,
            ))
            result.inputs.append(AlignedInput(d, ACTION_ALREADY_CURRENT, cells=None))
            continue

        # 2. Different method-CLASS (e.g. naive vs expose) → calibration, never alignable.
        if _method_class(sig) != target_class:
            result.actions.append(AlignmentAction(
                name, ACTION_EXCLUDED_CALIBRATION,
                f"method-class {_method_class(sig)} ({sig.scoring_method}) != target class "
                f"{target_class} ({target_sig.scoring_method}) — different method, not a version lag",
                signature_before=sig,
            ))
            continue

        # 3. Same method-class but behind the target (version/formula lag). Alignable IFF artifacts exist.
        if not _has_sandboxes(d):
            result.actions.append(AlignmentAction(
                name, ACTION_EXCLUDED_NO_SANDBOXES,
                "behind target but no sandboxes/ — nothing on disk to re-score",
                signature_before=sig,
            ))
            continue

        # 3a. Re-score the artifacts to the current scoring layer — in memory, source dir untouched.
        try:
            report = rescore_run(d, seeds_dir, write=False, **rescore_kwargs)
        except Exception as exc:  # noqa: BLE001 - CS-16: a rescore failure degrades to exclude, never crashes
            result.actions.append(AlignmentAction(
                name, ACTION_EXCLUDED_ERROR,
                f"rescore failed: {type(exc).__name__}: {exc}",
                signature_before=sig,
            ))
            continue

        # The artifacts are unchanged, so the run's *identity* doesn't move (sdk_version/formula live in
        # run-spec.json, which we don't rewrite). The alignment is in the recomputed compile/lint terms
        # carried by the in-memory cells. We stamp signature_after with the target so M3 treats these
        # cells as target-method without re-reading the (unmutated, still-behind) run-spec.
        result.actions.append(AlignmentAction(
            name, ACTION_ALIGNED,
            f"behind target (was {sig.scoring_method} sdk={sig.sdk_version}); re-scored "
            f"{report.cells_rescored} ok cell(s) to current scoring layer",
            signature_before=sig, signature_after=target_sig,
        ))
        result.inputs.append(AlignedInput(d, ACTION_ALIGNED, cells=report.cells))

    return result
