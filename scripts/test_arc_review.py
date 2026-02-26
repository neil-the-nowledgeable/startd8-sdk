#!/usr/bin/env python3
"""Test Arc Review workflow on specified documents.

Usage:
  python scripts/test_arc_review.py [--mock] [doc1 doc2 ...]

Examples:
  python scripts/test_arc_review.py docs/design/CODE_MANIFEST_PHASE4_REQUIREMENTS.md
  python scripts/test_arc_review.py ~/.claude/plans/serene-zooming-crab.md
  python scripts/test_arc_review.py --mock docs/design/CODE_MANIFEST_PHASE4_REQUIREMENTS.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_DOCS = [
    "docs/design/CODE_MANIFEST_PHASE4_REQUIREMENTS.md",
    str(Path.home() / ".claude" / "plans" / "serene-zooming-crab.md"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Arc Review workflow")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use MockAgent (no API calls; validation may fail)",
    )
    parser.add_argument(
        "docs",
        nargs="*",
        default=DEFAULT_DOCS,
        help="Document paths to review (default: CODE_MANIFEST + serene-zooming-crab)",
    )
    args = parser.parse_args()

    from startd8.workflows.builtin import ArchitecturalReviewLogWorkflow
    from startd8.providers import ProviderRegistry

    if not args.mock:
        ProviderRegistry.discover()

    agents = None
    if args.mock:
        from startd8.agents import MockAgent

        agents = [MockAgent(name="mock", model="mock-model")]

    last_result = None
    for doc_str in args.docs:
        doc_path = Path(doc_str).expanduser().resolve()
        if not doc_path.exists():
            print(f"SKIP {doc_str}: not found")
            continue

        print(f"\n=== Arc Review: {doc_path.name} ===")
        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow.run(
            config={
                "document_path": str(doc_path),
                "reviewer_count": 1,
                "init_if_missing": True,
            },
            agents=agents,
            on_progress=lambda c, t, m: print(f"  [{c}/{t}] {m}"),
        )

        print(f"Success: {result.success}")
        if result.output:
            print(f"Rounds appended: {result.output.get('rounds_appended', 0)}")
        if result.metrics:
            print(f"Cost: ${result.metrics.total_cost:.4f}")
        if result.error:
            print(f"Error: {result.error[:300]}...")
        last_result = result

    if last_result is None:
        print("\nNo documents were processed.")
        return 1
    return 0 if last_result.success else 1


if __name__ == "__main__":
    sys.exit(main())
