#!/usr/bin/env python3
"""Mine golden corpus entries from a ForwardManifest + on-disk source code.

Pairs manifest element specs with their actual implementations to produce
corpus entries for the Micro Prime evaluation harness.

Usage:
  # Preview what would be added (dry run)
  python3 scripts/mine_corpus_from_manifest.py \
      --seed path/to/prime-context-seed.json \
      --project-root path/to/target/project \
      --dry-run

  # Generate and append to corpus
  python3 scripts/mine_corpus_from_manifest.py \
      --seed path/to/prime-context-seed.json \
      --project-root path/to/target/project

  # With custom corpus path
  python3 scripts/mine_corpus_from_manifest.py \
      --seed path/to/prime-context-seed.json \
      --project-root path/to/target/project \
      --corpus path/to/corpus.json

How it works:
  1. Loads ForwardManifest from the seed JSON
  2. For each Python file_spec with on-disk source:
     a. Builds a skeleton (stubs with raise NotImplementedError)
     b. Reads the actual source as the reference implementation
     c. Validates the reference passes AST parsing
     d. Creates a corpus entry per file (file_whole mode) or per element
  3. Deduplicates against existing corpus entries by file path
  4. Appends new entries to corpus.json

Requirements:
  - The target project must have working source code on disk
  - The seed must contain a forward_manifest with file_specs
  - Only Python files are supported (non-Python files are skipped)
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import textwrap
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

CORPUS_PATH = (
    Path(__file__).resolve().parent.parent
    / "tests"
    / "evaluation"
    / "golden_corpus"
    / "corpus.json"
)


def _derive_archetype(fpath: str, elements: list[dict]) -> str:
    """Derive a human-readable archetype from file path and element mix."""
    stem = Path(fpath).stem
    kinds = {e.get("kind", "unknown") for e in elements}

    # Name-based archetypes
    if "logger" in stem:
        return "logging_module"
    if "server" in stem or "service" in stem:
        if any(e.get("kind") == "class" for e in elements):
            return "grpc_service_module"
        return "server_lifecycle"
    if "client" in stem:
        return "grpc_client"
    if "locust" in stem or "load" in stem:
        return "load_test_module"
    if "config" in stem:
        return "config_module"

    # Kind-based fallbacks
    if "class" in kinds and len(elements) > 3:
        return "class_module"
    if len(elements) > 5:
        return "utility_module"
    if len(elements) <= 2:
        return "simple_module"
    return "mixed_module"


def _build_skeleton(source: str, elements: list[dict]) -> str | None:
    """Build a skeleton from source by replacing function/method bodies
    with raise NotImplementedError.

    Returns None if the source doesn't parse.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    lines = source.splitlines(keepends=True)
    # Collect (start_line, end_line) for function/method bodies
    replacements: list[tuple[int, int, int]] = []  # (start, end, indent)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Find the body start (first statement in body)
            if not node.body:
                continue
            body_start = node.body[0].lineno  # 1-indexed
            body_end = node.body[-1].end_lineno or node.body[-1].lineno

            # Calculate indent from the def line
            def_line = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
            indent = len(def_line) - len(def_line.lstrip()) + 4

            # Skip if body is already just a docstring (keep it) + raise
            replacements.append((body_start, body_end, indent))

    if not replacements:
        return None

    # Sort by line number descending so replacements don't shift indices
    replacements.sort(key=lambda x: x[0], reverse=True)

    result_lines = list(lines)
    for body_start, body_end, indent in replacements:
        # Preserve docstring if present
        stub = " " * indent + "raise NotImplementedError\n"
        # Check if first body line is a docstring
        first_body = result_lines[body_start - 1].strip() if body_start <= len(result_lines) else ""
        if first_body.startswith('"""') or first_body.startswith("'''"):
            # Find end of docstring
            doc_end = body_start
            for i in range(body_start - 1, min(body_end, len(result_lines))):
                line = result_lines[i].strip()
                if (line.endswith('"""') or line.endswith("'''")) and i > body_start - 1:
                    doc_end = i + 1  # 0-indexed, so +1 for 1-indexed
                    break
                if line.count('"""') >= 2 or line.count("'''") >= 2:
                    doc_end = body_start
                    break
            # Replace lines after docstring through body_end
            result_lines[doc_end:body_end] = [stub]
        else:
            # Replace entire body
            result_lines[body_start - 1:body_end] = [stub]

    return "".join(result_lines)


def _file_spec_to_dict(fspec: Any) -> dict:
    """Convert ForwardFileSpec to corpus-compatible dict."""
    elements = []
    for el in fspec.elements:
        el_dict: dict[str, Any] = {
            "kind": el.kind.value,
            "name": el.name,
        }
        if el.parent_class:
            el_dict["parent_class"] = el.parent_class
        if el.signature:
            sig: dict[str, Any] = {}
            if el.signature.params:
                sig["params"] = [
                    {k: v for k, v in {
                        "name": p.name,
                        "annotation": p.annotation,
                        "default": p.default,
                    }.items() if v is not None}
                    for p in el.signature.params
                ]
            if el.signature.return_annotation:
                sig["return_annotation"] = el.signature.return_annotation
            if sig:
                el_dict["signature"] = sig
        elements.append(el_dict)

    imports = []
    for imp in (fspec.imports or []):
        imp_dict: dict[str, str] = {"kind": imp.kind if isinstance(imp.kind, str) else imp.kind.value}
        if hasattr(imp, "module") and imp.module:
            imp_dict["module"] = imp.module
        if hasattr(imp, "name") and imp.name:
            imp_dict["name"] = imp.name
        imports.append(imp_dict)

    return {
        "file": fspec.file,
        "imports": imports,
        "elements": elements,
    }


def mine_entries(
    seed_path: str,
    project_root: str,
    mode: str = "file_whole",
) -> list[dict]:
    """Mine corpus entries from seed manifest + on-disk source."""
    from startd8.forward_manifest import ForwardManifest

    seed = json.loads(Path(seed_path).read_text(encoding="utf-8"))
    fm_dict = seed.get("forward_manifest")
    if not fm_dict:
        print("ERROR: seed has no forward_manifest key", file=sys.stderr)
        return []

    fm = ForwardManifest.model_validate(fm_dict)
    root = Path(project_root)
    entries: list[dict] = []
    next_id = 100  # Start high to avoid collisions with existing gc-xxx IDs

    for fpath, fspec in fm.file_specs.items():
        # Only Python files with elements
        if not fpath.endswith(".py"):
            continue
        if not fspec.elements:
            continue

        source_file = root / fpath
        if not source_file.is_file():
            print(f"  SKIP {fpath}: source file not found on disk", file=sys.stderr)
            continue

        source = source_file.read_text(encoding="utf-8")

        # Validate source parses
        try:
            ast.parse(source)
        except SyntaxError as e:
            print(f"  SKIP {fpath}: SyntaxError in source: {e}", file=sys.stderr)
            continue

        # Build skeleton
        skeleton = _build_skeleton(source, [{"kind": el.kind.value} for el in fspec.elements])
        if skeleton is None:
            print(f"  SKIP {fpath}: could not build skeleton", file=sys.stderr)
            continue

        # Validate skeleton parses
        try:
            ast.parse(skeleton)
        except SyntaxError:
            print(f"  SKIP {fpath}: skeleton doesn't parse (skeleton generation bug)", file=sys.stderr)
            continue

        # Count stubs in skeleton
        stub_count = skeleton.count("raise NotImplementedError")
        if stub_count == 0:
            print(f"  SKIP {fpath}: no stubs in skeleton", file=sys.stderr)
            continue

        archetype = _derive_archetype(fpath, [{"kind": el.kind.value, "name": el.name} for el in fspec.elements])
        n_elements = len(fspec.elements)
        loc = len(source.splitlines())

        entry: dict[str, Any] = {
            "id": f"gc-{next_id:03d}",
            "description": f"{archetype} ({n_elements} elements, {loc} LOC)",
            "archetype": archetype,
            "file": _file_spec_to_dict(fspec),
            "skeleton": skeleton,
            "reference": source,
            "expected_tier": "simple" if loc <= 150 else "moderate",
            "mode": "file_whole",
            "source_project": "online-boutique",
        }
        entries.append(entry)
        next_id += 1
        print(f"  MINED {fpath}: {archetype}, {n_elements} elements, {loc} LOC, {stub_count} stubs")

    return entries


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mine golden corpus entries from manifest + source code",
    )
    parser.add_argument(
        "--seed", required=True,
        help="Path to prime-context-seed.json",
    )
    parser.add_argument(
        "--project-root", required=True,
        help="Path to the target project root (where source files live)",
    )
    parser.add_argument(
        "--corpus", default=str(CORPUS_PATH),
        help=f"Path to corpus.json (default: {CORPUS_PATH})",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview entries without writing to corpus",
    )
    parser.add_argument(
        "--mode", choices=["file_whole", "element"], default="file_whole",
        help="Generation mode for corpus entries (default: file_whole)",
    )
    args = parser.parse_args()

    print(f"\nMining corpus entries from: {args.seed}")
    print(f"Project root: {args.project_root}\n")

    entries = mine_entries(args.seed, args.project_root, mode=args.mode)

    if not entries:
        print("\nNo entries mined. Check stderr for skip reasons.")
        return 1

    # Load existing corpus for dedup
    corpus_path = Path(args.corpus)
    if corpus_path.exists():
        corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    else:
        corpus = {"schema_version": "1.0.0", "description": "Golden corpus", "corpus": []}

    existing_files = {e.get("file", {}).get("file", "") for e in corpus["corpus"]}

    # Dedup
    new_entries = [e for e in entries if e["file"]["file"] not in existing_files]
    dupes = len(entries) - len(new_entries)
    if dupes:
        print(f"\n  {dupes} entries already in corpus (skipped)")

    if not new_entries:
        print("\nAll mined entries already exist in corpus. Nothing to add.")
        return 0

    print(f"\n{'Would add' if args.dry_run else 'Adding'} {len(new_entries)} new entries to corpus:")
    for e in new_entries:
        print(f"  {e['id']}: {e['description']}")

    if args.dry_run:
        print("\n  --dry-run: no changes written")
        return 0

    # Re-number IDs to follow existing corpus
    max_existing = 0
    for e in corpus["corpus"]:
        eid = e.get("id", "")
        if eid.startswith("gc-"):
            try:
                max_existing = max(max_existing, int(eid[3:]))
            except ValueError:
                pass
    for i, e in enumerate(new_entries):
        e["id"] = f"gc-{max_existing + i + 1:03d}"

    corpus["corpus"].extend(new_entries)

    corpus_path.write_text(
        json.dumps(corpus, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"\n  Wrote {len(new_entries)} entries to {corpus_path}")
    print(f"  Corpus now has {len(corpus['corpus'])} total entries")

    return 0


if __name__ == "__main__":
    sys.exit(main())
