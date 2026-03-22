#!/usr/bin/env python3
"""Enrich a context seed with per-task quality hints from a prior postmortem.

REQ-RFL-320: Closes the cross-run feedback loop at the seed level.

Usage:
    python3 scripts/enrich_seed_from_postmortem.py \
        --seed seed.json \
        --postmortem previous-run/kaizen-suggestions.json \
        --output enriched-seed.json

The enrichment is idempotent — re-running with the same postmortem
produces identical output.
"""

import argparse
import json
import sys
from pathlib import Path

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def _load_suggestions(path: Path) -> list:
    """Load kaizen suggestions from postmortem or kaizen-suggestions.json."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(
            f"ERROR: cannot parse {path}: {exc}",
            file=sys.stderr,
        )
        return []
    # kaizen-suggestions.json is a list directly
    if isinstance(data, list):
        return data
    # postmortem report has suggestions nested
    if isinstance(data, dict):
        return data.get("kaizen_suggestions", data.get("suggestions", []))
    return []


def _match_suggestion_to_task(suggestion: dict, task_context: dict) -> bool:
    """Check if a suggestion is relevant to a task by domain/file overlap."""
    hint = suggestion.get("hint", "")
    pattern = suggestion.get("pattern_type", "")
    observed = suggestion.get("observed_context", "")

    domain = task_context.get("domain", "")
    target_files = task_context.get("target_files", [])

    if domain and domain in observed:
        return True
    if any(tf in observed for tf in target_files if isinstance(tf, str) and tf):
        return True
    if pattern and pattern in str(task_context):
        return True
    return False


def enrich_seed(seed: dict, suggestions: list) -> dict:
    """Enrich seed tasks with per-task quality hints.

    Returns:
        The modified seed dict (mutated in place).
    """
    tasks = seed.get("tasks", [])
    if not tasks or not suggestions:
        return seed

    for task in tasks:
        config = task.get("config", {})
        context = config.get("context", {})
        existing_hints = list(context.get("quality_hints", []))

        matched = []
        unmatched = []

        for suggestion in suggestions:
            hint_text = suggestion.get("hint", "")
            if not hint_text or hint_text in existing_hints:
                continue
            if _match_suggestion_to_task(suggestion, context):
                matched.append(hint_text)
            else:
                unmatched.append(hint_text)

        # Matched first, then unmatched (run-level), cap at 3
        for h in matched + unmatched:
            if h not in existing_hints and len(existing_hints) < 3:
                existing_hints.append(h)

        context["quality_hints"] = existing_hints

    return seed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich context seed with quality hints from postmortem",
    )
    parser.add_argument(
        "--seed", required=True, type=Path,
        help="Path to the context seed JSON",
    )
    parser.add_argument(
        "--postmortem", required=True, type=Path,
        help="Path to kaizen-suggestions.json or postmortem report",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Output path (default: overwrite input seed)",
    )
    args = parser.parse_args()

    if not args.seed.exists():
        print(f"ERROR: seed not found: {args.seed}", file=sys.stderr)
        sys.exit(1)
    if not args.postmortem.exists():
        print(f"ERROR: postmortem not found: {args.postmortem}", file=sys.stderr)
        sys.exit(1)

    seed = json.loads(args.seed.read_text(encoding="utf-8"))
    suggestions = _load_suggestions(args.postmortem)

    if not suggestions:
        print("No suggestions found in postmortem — seed unchanged.")
        output = args.output or args.seed
        output.write_text(
            json.dumps(seed, indent=2), encoding="utf-8",
        )
        sys.exit(0)

    enriched = enrich_seed(seed, suggestions)
    enriched["authoring_mode"] = "hybrid"  # REQ-SU-300: pipeline + post-enrichment

    output = args.output or args.seed
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(enriched, indent=2), encoding="utf-8")

    task_count = len(enriched.get("tasks", []))
    hints_count = sum(
        len(t.get("config", {}).get("context", {}).get("quality_hints", []))
        for t in enriched.get("tasks", [])
    )
    print(
        f"Enriched {task_count} tasks with {hints_count} quality hints "
        f"from {len(suggestions)} suggestions → {output}",
    )


if __name__ == "__main__":
    main()
