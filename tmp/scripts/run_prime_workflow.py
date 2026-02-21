#!/usr/bin/env python3
"""Run the prime workflow with configurable modes and validation settings.

Supports --mode, --validate, --no-validate, --strict-validation, and
--force-regenerate flags with automatic conflict detection.
"""
from __future__ import annotations

import argparse
import dataclasses
import logging
import sys

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_MODES = ("generate", "validate", "full", "dry-run")

# ---------------------------------------------------------------------------
# Utility functions (defined before classes that reference them)
# ---------------------------------------------------------------------------


def setup_logging() -> logging.Logger:
    """Configure and return the module logger.

    Sets up a logger named "prime_workflow" with INFO level,
    outputting to stderr with a standard timestamp format.
    """
    logger = logging.getLogger("prime_workflow")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        )
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


def build_parser() -> argparse.ArgumentParser:
    """Construct and return the argument parser with all CLI flags.

    Returns:
        Configured ArgumentParser with --mode, --validate, --no-validate,
        --strict-validation, and --force-regenerate options.
    """
    parser = argparse.ArgumentParser(
        prog="run_prime_workflow",
        description="Run the prime workflow with configurable modes and validation settings.",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="full",
        choices=VALID_MODES,
        help="Workflow execution mode (default: full).",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        default=False,
        help="Enable validation (default behaviour).",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        default=False,
        dest="no_validate",
        help="Disable validation entirely.",
    )
    parser.add_argument(
        "--strict-validation",
        action="store_true",
        default=False,
        dest="strict_validation",
        help="Treat validation warnings as errors.",
    )
    parser.add_argument(
        "--force-regenerate",
        action="store_true",
        default=False,
        dest="force_regenerate",
        help="Force regeneration of all artifacts.",
    )
    return parser


def detect_conflicts(args: argparse.Namespace) -> list[str]:
    """Detect and return a list of human-readable conflict descriptions.

    Checks for mutually exclusive or contradictory flag combinations:
    - --validate and --no-validate together
    - --strict-validation and --no-validate together
    - --mode validate with --no-validate
    - --mode dry-run with --force-regenerate

    Args:
        args: Parsed command-line arguments.

    Returns:
        List of conflict error strings (empty if no conflicts detected).
    """
    conflicts: list[str] = []

    # Conflict 1: --validate and --no-validate both present
    if args.validate and args.no_validate:
        conflicts.append(
            "Conflicting flags: --validate and --no-validate cannot be used together."
        )

    # Conflict 2: --strict-validation requires validation to be enabled
    if args.strict_validation and args.no_validate:
        conflicts.append(
            "Conflicting flags: --strict-validation requires validation to be enabled, "
            "but --no-validate was specified."
        )

    # Conflict 3: --mode validate contradicts --no-validate
    if args.mode == "validate" and args.no_validate:
        conflicts.append(
            "Conflicting options: --mode=validate requires validation, "
            "but --no-validate was specified."
        )

    # Conflict 4: --mode dry-run contradicts --force-regenerate
    if args.mode == "dry-run" and args.force_regenerate:
        conflicts.append(
            "Conflicting options: --force-regenerate cannot be used with --mode=dry-run."
        )

    return conflicts


def resolve_config(args: argparse.Namespace) -> WorkflowConfig:
    """Convert raw parsed arguments into a resolved WorkflowConfig.

    Applies logical defaults (e.g., validation is on by default unless
    --no-validate is explicitly specified).

    Args:
        args: Parsed command-line arguments.

    Returns:
        WorkflowConfig with resolved settings.
    """
    return WorkflowConfig(
        mode=args.mode,
        validate=not args.no_validate,
        strict_validation=args.strict_validation,
        force_regenerate=args.force_regenerate,
    )


def run_workflow(config: WorkflowConfig) -> None:
    """Execute the prime workflow based on the resolved configuration.

    Currently a stub that logs the intended workflow actions.
    In a production system, this would orchestrate actual workflow steps.

    Args:
        config: The resolved WorkflowConfig to execute.
    """
    logger = logging.getLogger("prime_workflow")
    logger.info("Starting prime workflow in '%s' mode", config.mode)
    logger.info("Validation: %s", "enabled" if config.validate else "disabled")
    if config.strict_validation:
        logger.info("Strict validation: enabled")
    if config.force_regenerate:
        logger.info("Force regenerate: enabled")
    logger.info("Workflow execution complete.")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class WorkflowConfig:
    """Resolved runtime configuration for the prime workflow.

    Attributes:
        mode: The workflow execution mode (one of VALID_MODES).
        validate: Whether validation is enabled.
        strict_validation: Whether to treat validation warnings as errors.
        force_regenerate: Whether to force regeneration of all artifacts.
    """

    mode: str
    validate: bool
    strict_validation: bool
    force_regenerate: bool


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point: parse arguments, detect conflicts, run workflow.

    Flow:
    1. Set up logging
    2. Build argument parser
    3. Parse command-line arguments
    4. Detect any conflicts in flag combinations
    5. If conflicts exist, log them and exit with code 2
    6. Otherwise, resolve configuration and run the workflow
    7. Exit with code 0 on success
    """
    logger = setup_logging()
    parser = build_parser()
    args = parser.parse_args()

    # Detect conflicts before proceeding
    conflicts = detect_conflicts(args)
    if conflicts:
        for msg in conflicts:
            logger.error(msg)
        sys.exit(2)

    # Resolve configuration and execute workflow
    config = resolve_config(args)
    logger.info(
        "Resolved configuration: mode=%s, validate=%s, strict_validation=%s, force_regenerate=%s",
        config.mode,
        config.validate,
        config.strict_validation,
        config.force_regenerate,
    )
    run_workflow(config)
    sys.exit(0)


if __name__ == "__main__":
    main()