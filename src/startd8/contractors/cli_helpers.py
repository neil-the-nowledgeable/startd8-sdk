"""
CLI helpers for PrimeContractorWorkflow scripts.

Provides ``add_workflow_args()`` and ``apply_workflow_args()`` so downstream
scripts can wire common flags (--reset-state, --retry-failed, --clean,
--continue-on-failure, --dry-run) without reimplementing them each time.

Example::

    import argparse
    from startd8.contractors.cli_helpers import add_workflow_args, apply_workflow_args

    parser = argparse.ArgumentParser()
    add_workflow_args(parser)
    args = parser.parse_args()

    workflow = PrimeContractorWorkflow(project_root=root, dry_run=args.dry_run)
    # ... add features ...
    apply_workflow_args(workflow, args)
    result = workflow.run(stop_on_failure=not args.continue_on_failure)
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .prime_contractor import PrimeContractorWorkflow


def add_workflow_args(parser: argparse.ArgumentParser) -> None:
    """
    Register common PrimeContractorWorkflow CLI flags on *parser*.

    Flags added:
    - ``--dry-run``
    - ``--reset-state``
    - ``--retry-failed``
    - ``--continue-on-failure``
    - ``--clean``
    - ``--clean-all``  (includes target files)
    """
    group = parser.add_argument_group("Workflow control")
    group.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview changes without executing code generation or integration",
    )
    group.add_argument(
        "--reset-state",
        action="store_true",
        default=False,
        help="Delete state file and clean workspace artifacts before running",
    )
    group.add_argument(
        "--retry-failed",
        action="store_true",
        default=False,
        help="Reset failed/blocked features to their last good status and resume",
    )
    group.add_argument(
        "--continue-on-failure",
        action="store_true",
        default=False,
        help="Skip failed features and continue with independent ones",
    )
    group.add_argument(
        "--clean",
        action="store_true",
        default=False,
        help="Clean workspace artifacts (generated/, .backup, __pycache__) before running",
    )
    group.add_argument(
        "--clean-all",
        action="store_true",
        default=False,
        help="Like --clean but also removes target files listed in the feature queue",
    )


def apply_workflow_args(
    workflow: PrimeContractorWorkflow,
    args: argparse.Namespace,
) -> None:
    """
    Apply parsed CLI flags to *workflow* before ``run()``.

    Call this **after** adding features to the queue so that
    ``--retry-failed`` and ``--reset-state`` operate on the full queue.

    Order of operations:
    1. ``--reset-state`` → ``workflow.full_reset()`` (clears state + artifacts)
    2. ``--clean`` / ``--clean-all`` → ``workflow.clean_workspace(...)``
    3. ``--retry-failed`` → ``workflow.reset_failed_features()``
    """
    if getattr(args, "reset_state", False):
        print("Resetting workflow state and cleaning workspace...")
        workflow.full_reset(include_targets=getattr(args, "clean_all", False))
        return  # full_reset already cleaned; skip redundant clean

    if getattr(args, "clean_all", False):
        print("Cleaning workspace (including target files)...")
        workflow.clean_workspace(include_targets=True)
    elif getattr(args, "clean", False):
        print("Cleaning workspace artifacts...")
        workflow.clean_workspace(include_targets=False)

    if getattr(args, "retry_failed", False):
        print("Resetting failed/blocked features for retry...")
        workflow.reset_failed_features()
