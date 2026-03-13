#!/usr/bin/env python3
"""Evaluation harness for Micro Prime Ollama output quality.

Runs the golden corpus through MicroPrimeEngine, scores each element
against its reference implementation, and produces a quality report.

Usage:
  # Default run (startd8-coder model)
  python3 scripts/run_eval_ollama.py

  # Compare models
  python3 scripts/run_eval_ollama.py --model qwen2.5-coder:14b

  # Repeat for statistical significance
  python3 scripts/run_eval_ollama.py --repeat 5

  # File-whole entries only (Section 3 research)
  python3 scripts/run_eval_ollama.py --mode file_whole

  # Element-level entries only
  python3 scripts/run_eval_ollama.py --mode element

  # Dry run (score reference against itself, validates harness)
  python3 scripts/run_eval_ollama.py --dry-run

  # Output JSON report
  python3 scripts/run_eval_ollama.py --output results/eval-001.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

# Add src to path for development
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardImportSpec,
    ForwardManifest,
    InterfaceContract,
)
from startd8.micro_prime.engine import MicroPrimeEngine
from startd8.micro_prime.eval_scoring import (
    CorpusReport,
    ElementScore,
    FileScore,
    score_element,
    score_fill_rate,
)
from startd8.micro_prime.metrics import MetricsCollector
from startd8.micro_prime.models import MicroPrimeConfig
from startd8.micro_prime.templates import TemplateRegistry
from startd8.utils.code_manifest import ElementKind, Param, ParamKind, Signature


# ── Corpus Loading ─────────────────────────────────────────────────────

CORPUS_PATH = Path(__file__).resolve().parent.parent / "tests" / "evaluation" / "golden_corpus" / "corpus.json"


def load_corpus(
    path: Path = CORPUS_PATH,
    mode_filter: Optional[str] = None,
) -> list[dict]:
    """Load golden corpus entries, optionally filtering by mode."""
    with open(path) as f:
        data = json.load(f)

    entries = data["corpus"]
    if mode_filter == "file_whole":
        entries = [e for e in entries if e.get("mode") == "file_whole"]
    elif mode_filter == "element":
        entries = [e for e in entries if e.get("mode") != "file_whole"]
    return entries


def _build_param(p: dict) -> Param:
    """Build a Param from corpus JSON."""
    return Param(
        name=p["name"],
        annotation=p.get("annotation"),
        default=p.get("default"),
    )


def _build_signature(sig: dict | None) -> Signature | None:
    """Build a Signature from corpus JSON."""
    if sig is None:
        return None
    return Signature(
        params=[_build_param(p) for p in sig.get("params", [])],
        return_annotation=sig.get("return_annotation"),
    )


def _build_element(elem: dict) -> ForwardElementSpec:
    """Build a ForwardElementSpec from corpus JSON."""
    return ForwardElementSpec(
        kind=ElementKind(elem["kind"]),
        name=elem["name"],
        signature=_build_signature(elem.get("signature")),
        bases=elem.get("bases", []),
        parent_class=elem.get("parent_class"),
        type_annotation=elem.get("type_annotation"),
        value_repr=elem.get("value_repr"),
    )


def _build_file_spec(file_data: dict) -> ForwardFileSpec:
    """Build a ForwardFileSpec from corpus JSON."""
    imports = [
        ForwardImportSpec(
            kind=imp["kind"],
            module=imp["module"],
            names=imp.get("names", []),
        )
        for imp in file_data.get("imports", [])
    ]
    elements = [_build_element(e) for e in file_data.get("elements", [])]
    return ForwardFileSpec(
        file=file_data["file"],
        imports=imports,
        elements=elements,
    )


def _expected_import_modules(file_data: dict) -> list[str]:
    """Extract expected import module names from corpus file data."""
    modules = []
    for imp in file_data.get("imports", []):
        modules.append(imp["module"])
    return modules


# ── Engine Setup ───────────────────────────────────────────────────────


def create_engine(
    model: str = "startd8-coder",
    temperature: float = 0.1,
) -> tuple[MicroPrimeEngine, MicroPrimeConfig, MetricsCollector]:
    """Create a configured MicroPrimeEngine for evaluation."""
    config = MicroPrimeConfig(
        model=model,
        provider="ollama",
        temperature=temperature,
        templates_enabled=True,
        repair_enabled=True,
        few_shot_enabled=False,  # Disable few-shot for clean evaluation
        file_ollama_whole_enabled=True,
    )
    metrics = MetricsCollector()
    templates = TemplateRegistry(enabled=True)
    engine = MicroPrimeEngine(
        config=config,
        template_registry=templates,
        metrics_collector=metrics,
    )
    return engine, config, metrics


# ── Evaluation Runner ──────────────────────────────────────────────────


def evaluate_element_entry(
    entry: dict,
    engine: MicroPrimeEngine,
    dry_run: bool = False,
) -> list[ElementScore]:
    """Evaluate a single corpus entry (element-level generation)."""
    file_spec = _build_file_spec(entry["file"])
    skeleton = entry["skeleton"]
    reference = entry["reference"]
    expected_imports = _expected_import_modules(entry["file"])
    scores: list[ElementScore] = []

    manifest = ForwardManifest(
        file_specs={file_spec.file: file_spec},
    )

    for element in file_spec.elements:
        if dry_run:
            # Score reference against itself (harness validation)
            score = score_element(
                generated_code=reference,
                reference_code=reference,
                element_name=element.name,
                file_path=file_spec.file,
                tier=entry.get("expected_tier", "simple"),
                expected_imports=expected_imports,
            )
            scores.append(score)
            continue

        start_ms = time.time() * 1000
        try:
            result = engine.process_element(
                element=element,
                file_spec=file_spec,
                skeleton=skeleton,
            )
            elapsed_ms = time.time() * 1000 - start_ms

            generated = result.code or ""

            score = score_element(
                generated_code=generated,
                reference_code=reference,
                element_name=element.name,
                file_path=file_spec.file,
                tier=result.tier.value if result.tier else entry.get("expected_tier", "simple"),
                expected_imports=expected_imports,
                repair_steps=result.repair_steps_applied,
                repair_recovered=result.repair_recovered,
                generation_time_ms=elapsed_ms,
            )
        except Exception as exc:
            elapsed_ms = time.time() * 1000 - start_ms
            score = ElementScore(
                element_name=element.name,
                file_path=file_spec.file,
                tier=entry.get("expected_tier", "simple"),
                generation_time_ms=elapsed_ms,
                error=str(exc),
            )
        scores.append(score)
    return scores


def evaluate_file_whole_entry(
    entry: dict,
    engine: MicroPrimeEngine,
    dry_run: bool = False,
) -> tuple[list[ElementScore], FileScore]:
    """Evaluate a file-whole corpus entry."""
    file_spec = _build_file_spec(entry["file"])
    skeleton = entry["skeleton"]
    reference = entry["reference"]
    expected_imports = _expected_import_modules(entry["file"])
    total_stubs = skeleton.count("raise NotImplementedError")

    manifest = ForwardManifest(
        file_specs={file_spec.file: file_spec},
    )

    if dry_run:
        generated = reference
        element_scores = []
        for element in file_spec.elements:
            s = score_element(
                generated_code=reference,
                reference_code=reference,
                element_name=element.name,
                file_path=file_spec.file,
                tier=entry.get("expected_tier", "simple"),
                expected_imports=expected_imports,
            )
            element_scores.append(s)
        fill = score_fill_rate(reference, total_stubs)
        file_score = FileScore(
            file_path=file_spec.file,
            element_scores=element_scores,
            fill_rate=fill,
            total_elements=len(file_spec.elements),
            filled_elements=int(fill * total_stubs),
        )
        return element_scores, file_score

    start_ms = time.time() * 1000
    try:
        result = engine.process_file(
            file_spec=file_spec,
            manifest=manifest,
            skeleton=skeleton,
            ollama_available=True,
        )
        elapsed_ms = time.time() * 1000 - start_ms

        generated = result.filled_skeleton or ""
        fill = score_fill_rate(generated, total_stubs)

        element_scores = []
        for er in result.element_results:
            s = score_element(
                generated_code=er.code or "",
                reference_code=reference,
                element_name=er.element_name,
                file_path=er.file_path,
                tier=er.tier.value if er.tier else entry.get("expected_tier", "simple"),
                expected_imports=expected_imports,
                repair_steps=er.repair_steps_applied,
                repair_recovered=er.repair_recovered,
                generation_time_ms=elapsed_ms / max(len(result.element_results), 1),
            )
            element_scores.append(s)

        # If file-whole succeeded but we don't have per-element results,
        # score the whole file as a single unit
        if not element_scores and generated:
            for element in file_spec.elements:
                s = score_element(
                    generated_code=generated,
                    reference_code=reference,
                    element_name=element.name,
                    file_path=file_spec.file,
                    tier=entry.get("expected_tier", "simple"),
                    expected_imports=expected_imports,
                    generation_time_ms=elapsed_ms / max(len(file_spec.elements), 1),
                )
                element_scores.append(s)

        file_score = FileScore(
            file_path=file_spec.file,
            element_scores=element_scores,
            fill_rate=fill,
            total_elements=len(file_spec.elements),
            filled_elements=int(fill * total_stubs),
        )

    except Exception as exc:
        elapsed_ms = time.time() * 1000 - start_ms
        element_scores = [
            ElementScore(
                element_name=e.name,
                file_path=file_spec.file,
                tier=entry.get("expected_tier", "simple"),
                generation_time_ms=elapsed_ms / max(len(file_spec.elements), 1),
                error=str(exc),
            )
            for e in file_spec.elements
        ]
        file_score = FileScore(
            file_path=file_spec.file,
            element_scores=element_scores,
            fill_rate=0.0,
            total_elements=len(file_spec.elements),
            filled_elements=0,
        )

    return element_scores, file_score


def run_evaluation(
    model: str = "startd8-coder",
    mode_filter: Optional[str] = None,
    dry_run: bool = False,
    temperature: float = 0.1,
) -> CorpusReport:
    """Run a full evaluation pass over the golden corpus."""
    entries = load_corpus(mode_filter=mode_filter)
    engine, config, metrics = create_engine(model=model, temperature=temperature)
    run_id = f"eval-{uuid.uuid4().hex[:8]}"

    report = CorpusReport(run_id=run_id, model=model)

    print(f"\n{'=' * 60}")
    print(f"  Micro Prime Evaluation — {model}")
    print(f"  Run ID: {run_id}")
    print(f"  Corpus: {len(entries)} entries, mode={mode_filter or 'all'}")
    print(f"  Dry run: {dry_run}")
    print(f"{'=' * 60}\n")

    for i, entry in enumerate(entries, 1):
        entry_id = entry["id"]
        desc = entry["description"]
        is_file_whole = entry.get("mode") == "file_whole"
        mode_label = "file-whole" if is_file_whole else "element"

        print(f"  [{i}/{len(entries)}] {entry_id}: {desc} ({mode_label})", end="")
        sys.stdout.flush()

        if is_file_whole:
            elem_scores, file_score = evaluate_file_whole_entry(entry, engine, dry_run)
            report.element_scores.extend(elem_scores)
            report.file_scores.append(file_score)
            avg = file_score.composite_score
            print(f" — fill={file_score.fill_rate:.0%}, score={avg:.2f}")
        else:
            elem_scores = evaluate_element_entry(entry, engine, dry_run)
            report.element_scores.extend(elem_scores)
            # Print first element inline, rest on new indented lines
            for j, s in enumerate(elem_scores):
                status = "PASS" if s.pass_threshold else "FAIL"
                detail = f"{status} {s.element_name} (syn={s.syntax} imp={s.imports} lint={s.lint} sem={s.semantic})"
                if j == 0:
                    print(f" — {detail}")
                else:
                    print(f"    {'':>{len(str(len(entries)))*2+5}}{detail}")

    _print_summary(report)
    return report


# ── Reporting ──────────────────────────────────────────────────────────


def _print_summary(report: CorpusReport) -> None:
    """Print a summary table to console."""
    print(f"\n{'=' * 60}")
    print(f"  SUMMARY — {report.model} (run {report.run_id})")
    print(f"{'=' * 60}")
    print(f"  Elements evaluated: {report.total_elements}")
    print(f"  Syntax rate:        {report.syntax_rate:.1%}")
    print(f"  Import rate:        {report.import_rate:.1%}")
    print(f"  Lint rate:          {report.lint_rate:.1%}")
    print(f"  Mean semantic:      {report.mean_semantic:.2f} / 3.00")
    print(f"  Mean composite:     {report.mean_composite:.3f}")
    print(f"  Pass rate:          {report.pass_rate:.1%}")
    print(f"  Repair rate:        {report.repair_rate:.1%}")

    if report.file_scores:
        mean_fill = sum(f.fill_rate for f in report.file_scores) / len(report.file_scores)
        print(f"\n  File-whole fill rate (mean): {mean_fill:.1%}")
        for fs in report.file_scores:
            print(f"    {fs.file_path}: fill={fs.fill_rate:.0%} ({fs.filled_elements}/{fs.total_elements} elements)")

    # Per-tier breakdown
    tiers: dict[str, list[ElementScore]] = {}
    for s in report.element_scores:
        tiers.setdefault(s.tier, []).append(s)

    if len(tiers) > 1:
        print(f"\n  Per-tier breakdown:")
        for tier_name in ["trivial", "simple", "moderate", "complex"]:
            tier_scores = tiers.get(tier_name, [])
            if not tier_scores:
                continue
            n = len(tier_scores)
            syn = sum(s.syntax for s in tier_scores) / n
            sem = sum(s.semantic for s in tier_scores) / n
            comp = sum(s.composite_score for s in tier_scores) / n
            pr = sum(1 for s in tier_scores if s.pass_threshold) / n
            print(f"    {tier_name:10s}: n={n:3d}  syn={syn:.0%}  sem={sem:.1f}  comp={comp:.3f}  pass={pr:.0%}")

    # Failures detail
    failures = [s for s in report.element_scores if not s.pass_threshold]
    if failures:
        print(f"\n  Failures ({len(failures)}):")
        for s in failures:
            reason = s.error or f"syn={s.syntax} sem={s.semantic}"
            print(f"    {s.element_name} ({s.file_path}): {reason}")

    print(f"{'=' * 60}\n")


# ── CLI ────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate Micro Prime Ollama output quality against golden corpus",
    )
    parser.add_argument(
        "--model", default="startd8-coder",
        help="Ollama model name (default: startd8-coder)",
    )
    parser.add_argument(
        "--mode", choices=["element", "file_whole"],
        help="Filter corpus by mode (element or file_whole)",
    )
    parser.add_argument(
        "--repeat", type=int, default=1,
        help="Number of evaluation passes for statistical significance",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Score reference against itself (validates harness, no Ollama calls)",
    )
    parser.add_argument(
        "--temperature", type=float, default=0.1,
        help="Sampling temperature (default: 0.1)",
    )
    parser.add_argument(
        "--output", type=str,
        help="Write JSON report to file",
    )
    parser.add_argument(
        "--corpus", type=str,
        help="Path to golden corpus JSON (default: tests/evaluation/golden_corpus/corpus.json)",
    )
    args = parser.parse_args()

    if args.corpus:
        global CORPUS_PATH
        CORPUS_PATH = Path(args.corpus)

    all_reports: list[dict] = []

    for run_num in range(1, args.repeat + 1):
        if args.repeat > 1:
            print(f"\n{'#' * 60}")
            print(f"  Run {run_num} / {args.repeat}")
            print(f"{'#' * 60}")

        report = run_evaluation(
            model=args.model,
            mode_filter=args.mode,
            dry_run=args.dry_run,
            temperature=args.temperature,
        )
        all_reports.append(report.to_dict())

    # Multi-run summary
    if args.repeat > 1:
        print(f"\n{'=' * 60}")
        print(f"  MULTI-RUN SUMMARY ({args.repeat} runs)")
        print(f"{'=' * 60}")
        syntax_rates = [r["syntax_rate"] for r in all_reports]
        pass_rates = [r["pass_rate"] for r in all_reports]
        composites = [r["mean_composite"] for r in all_reports]
        semantics = [r["mean_semantic"] for r in all_reports]

        def _stats(values: list[float]) -> str:
            avg = sum(values) / len(values)
            if len(values) > 1:
                variance = sum((v - avg) ** 2 for v in values) / (len(values) - 1)
                std = variance ** 0.5
                return f"{avg:.3f} ± {std:.3f}"
            return f"{avg:.3f}"

        print(f"  Syntax rate:    {_stats(syntax_rates)}")
        print(f"  Pass rate:      {_stats(pass_rates)}")
        print(f"  Mean composite: {_stats(composites)}")
        print(f"  Mean semantic:  {_stats(semantics)}")
        print(f"{'=' * 60}\n")

    # Write output
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_data = {
            "schema_version": "1.0.0",
            "model": args.model,
            "temperature": args.temperature,
            "repeat": args.repeat,
            "mode_filter": args.mode,
            "runs": all_reports,
        }
        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"Report written to {output_path}")


if __name__ == "__main__":
    main()
