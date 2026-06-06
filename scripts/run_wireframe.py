#!/usr/bin/env python3
"""cap-dev-pipe wireframe shim (FR-W11) — read-only assembly visibility, never blocks.

Invoked from run-prime-contractor.sh / run-cap-delivery.sh when ``STARTD8_WIREFRAME=1``
(opt-in, FDE-style). Contract:

- **always exits 0** — a broken wireframe must never block the pipeline;
- on success: writes ``wireframe-plan.json`` + ``wireframe-summary.md`` under
  ``<output-dir>/wireframe/`` (artifact precedence R4-F3: the shim never touches
  ``.startd8/wireframe/``);
- on internal failure: still exits 0 but writes ``wireframe-error.json`` so operators can
  distinguish opted-off vs crashed vs empty-manifests (R5-F5/R5-S4).

Input discovery (R1-F4): ``--project-root`` (or ``PROJECT_ROOT`` env, the pipeline.env key),
then optional ``STARTD8_WIREFRAME_INPUTS`` (path-separator-delimited assembly-inputs YAMLs),
otherwise the FR-W8 convention defaults. Absent manifests are fine — the plan reports
``not_defined``/``defaults``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _write_error(out_dir: Path, exc: BaseException) -> None:
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "wireframe-error.json").write_text(
            json.dumps(
                {"error_type": type(exc).__name__, "message": str(exc)[:2000]},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass  # advisory all the way down


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, help="Pipeline run output dir ($OUTPUT_DIR).")
    parser.add_argument(
        "--project-root",
        default=os.environ.get("PROJECT_ROOT", "."),
        help="Project root (defaults to $PROJECT_ROOT from pipeline.env).",
    )
    parser.add_argument("--sdk-root", default=None, help="SDK root, prepended to sys.path if given.")
    parser.add_argument(
        "--from-run",
        default=None,
        help="Plan-ingestion run dir (FR-WPI-6): consume its manifests/ + add run_linkage. "
        "Defaults to --output-dir when that dir contains a manifests/ family.",
    )
    args = parser.parse_args()

    wf_dir = Path(args.output_dir) / "wireframe"
    try:
        if args.sdk_root:
            sys.path.insert(0, str(Path(args.sdk_root) / "src"))

        from startd8.wireframe import build_wireframe_plan, load_assembly_inputs
        from startd8.wireframe.render import persist_plan, run_linkage

        inputs_env = os.environ.get("STARTD8_WIREFRAME_INPUTS", "")
        yaml_paths = [Path(p) for p in inputs_env.split(os.pathsep) if p.strip()]

        # FR-WPI-6/10: post-ingestion invocations consume the run's extracted manifests.
        from_run = Path(args.from_run) if args.from_run else None
        if from_run is None and (Path(args.output_dir) / "manifests").is_dir():
            from_run = Path(args.output_dir)

        resolved = load_assembly_inputs(
            yaml_paths=yaml_paths, project_root=Path(args.project_root), from_run=from_run
        )
        plan = build_wireframe_plan(resolved)
        linkage = run_linkage(from_run) if from_run is not None else None
        written = persist_plan(
            plan, wf_dir, emit_context="pipeline", with_markdown=True, linkage=linkage
        )
        print(f"wireframe: plan written to {written.get('json') or wf_dir} (advisory, read-only)")
    except BaseException as exc:  # noqa: BLE001 — never block the pipeline (FR-W11)
        _write_error(wf_dir, exc)
        print(f"wireframe: failed ({type(exc).__name__}: {exc}) — error artifact written, continuing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
