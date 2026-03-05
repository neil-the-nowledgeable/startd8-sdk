"""Prime Contractor CodeGenerator Adapter (REQ-MP-504).

Implements the ``CodeGenerator`` protocol, wrapping the Micro Prime engine
for use in PrimeContractorWorkflow. Elements that can't be handled locally
are delegated to a fallback ``CodeGenerator``.
"""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import URLError
from urllib.request import urlopen

from startd8.contractors.protocols import CodeGenerator, GenerationResult
from startd8.forward_manifest import ForwardManifest
from startd8.logging_config import get_logger
from startd8.micro_prime.classifier import classify_element
from startd8.micro_prime.engine import MicroPrimeEngine
from startd8.micro_prime.models import MicroPrimeConfig, TierClassification

logger = get_logger(__name__)

# OTel metrics (REQ-MP-705) — optional dependency
try:
    from opentelemetry import metrics as otel_metrics
    _meter = otel_metrics.get_meter("startd8.micro_prime")
    _elements_local_counter = _meter.create_counter(
        "micro_prime.elements_local",
        description="Elements processed locally by Micro Prime",
    )
    _elements_escalated_counter = _meter.create_counter(
        "micro_prime.elements_escalated",
        description="Elements escalated to fallback generator",
    )
    _template_hits_counter = _meter.create_counter(
        "micro_prime.template_hits",
        description="Elements resolved by template registry",
    )
except ImportError:
    _elements_local_counter = None
    _elements_escalated_counter = None
    _template_hits_counter = None


# Size-regression threshold: if filled skeleton is below this ratio of the
# existing target file, escalate to the fallback generator.  Matches the
# integration engine's _INTEGRATION_SIZE_REGRESSION_THRESHOLD.
_SIZE_REGRESSION_THRESHOLD = 0.60
_MIN_EXISTING_LINES = 50


def _serialize_file_result(fr: Any) -> dict:
    """Serialize a FileResult dataclass to dict, truncating code to avoid bloat."""
    result = dataclasses.asdict(fr)
    for er in result.get("element_results", []):
        code = er.get("code")
        if code and len(code) > 500:
            er["code"] = code[:500] + "... [truncated]"
    # Drop filled_skeleton from serialization — too large for metadata
    result.pop("filled_skeleton", None)
    return result


def _sanitize_for_json(value: Any) -> Any:
    """Recursively convert Pydantic models to dicts for JSON compatibility."""
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {k: _sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_for_json(v) for v in value]
    return value


class MicroPrimeCodeGenerator:
    """``CodeGenerator`` implementation using the Micro Prime engine.

    Processes TRIVIAL and SIMPLE elements locally, delegating MODERATE and
    COMPLEX elements to a fallback ``CodeGenerator`` (typically the
    LeadContractor pattern).

    Args:
        config: Micro Prime engine configuration.
        fallback: Fallback code generator for elements beyond local capability.
        manifest: Forward manifest for element metadata.
        skeletons: Dict of file path -> skeleton content.
        output_dir: Directory for writing generated files.  Defaults to cwd.
    """

    def __init__(
        self,
        config: Optional[MicroPrimeConfig] = None,
        fallback: Optional[CodeGenerator] = None,
        manifest: Optional[ForwardManifest] = None,
        skeletons: Optional[dict[str, str]] = None,
        output_dir: Optional[Path] = None,
    ) -> None:
        self._config = config or MicroPrimeConfig()
        self._fallback = fallback
        self._manifest = manifest
        self._skeletons = skeletons or {}
        self._output_dir = output_dir or Path(".")
        self._engine = MicroPrimeEngine(config=self._config)
        self._ollama_available: Optional[bool] = None

    def generate(
        self,
        task: str,
        context: Dict[str, Any],
        target_files: List[str],
    ) -> GenerationResult:
        """Generate code for the given task.

        Attempts local generation first. For elements that require cloud
        processing, delegates to the fallback generator if available.

        Args:
            task: Description of what to implement.
            context: Additional context (existing code, requirements, etc.).
            target_files: Expected output file paths.

        Returns:
            GenerationResult with success status and generated file paths.
        """
        manifest = context.get("manifest") or self._manifest
        skeletons = context.get("skeletons") or self._skeletons

        # REQ-MP-702: Auto-generate skeletons from manifest when missing.
        # Prime Contractor has no SCAFFOLD phase, so stubs are produced on
        # demand using DeterministicFileAssembler.
        if manifest is not None and not skeletons:
            skeletons = self._generate_skeletons(manifest, target_files)

        if manifest is None:
            logger.warning(
                "MicroPrimeCodeGenerator: no manifest, delegating to fallback",
            )
            return self._delegate_to_fallback(task, context, target_files)

        # REQ-MP-711: Ollama availability guard — check once per instance
        ollama_ok = self._check_ollama_available()

        if self._config.dry_run:
            return self._dry_run_classify(manifest, skeletons, target_files, ollama_ok)

        if not ollama_ok:
            logger.info("Ollama unavailable — delegating all to fallback")
            return self._delegate_to_fallback(task, context, target_files)

        # Existing target files for size-regression escalation guard
        existing_files: Dict[str, str] = context.get("existing_files") or {}

        # Process target files through the engine
        all_file_results: list = []
        generated_files: list[Path] = []
        written_file_paths: set[str] = set()  # relative paths that were successfully written
        total_input = 0
        total_output = 0
        escalated_files: list[str] = []
        local_element_count = 0
        template_count = 0
        ollama_count = 0
        escalated_element_count = 0

        for file_path in target_files:
            file_spec = manifest.file_specs.get(file_path)
            skeleton = skeletons.get(file_path, "")

            if file_spec is None or not skeleton:
                escalated_files.append(file_path)
                continue

            # REQ-DDS-002: Thread design_doc_sections to engine
            _dds = context.get("design_doc_sections") or []
            file_result = self._engine.process_file(
                file_spec, manifest, skeleton,
                design_doc_sections=_dds if _dds else None,
            )
            all_file_results.append(file_result)

            if file_result.filled_skeleton:
                # Size-regression escalation guard: if the filled skeleton is
                # significantly smaller than the existing target file, escalate
                # to the fallback generator instead of writing a tiny skeleton.
                existing_content = existing_files.get(file_path, "")
                if existing_content:
                    filled_lines = file_result.filled_skeleton.count("\n") + 1
                    existing_lines = existing_content.count("\n") + 1
                    ratio = filled_lines / existing_lines if existing_lines > 0 else 1.0
                    if ratio < _SIZE_REGRESSION_THRESHOLD and existing_lines >= _MIN_EXISTING_LINES:
                        logger.warning(
                            "Micro Prime size-regression guard: %s has %d lines "
                            "vs %d existing (%.0f%%) — escalating to fallback",
                            file_path, filled_lines, existing_lines, ratio * 100,
                        )
                        escalated_files.append(file_path)
                        continue

                # REQ-MP-703: Write filled skeleton to disk
                output_path = self._output_dir / file_path
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(
                    file_result.filled_skeleton, encoding="utf-8",
                )
                generated_files.append(output_path)
                written_file_paths.add(file_path)
                logger.info(
                    "Micro Prime wrote %s (%d lines, %d elements filled)",
                    file_path,
                    file_result.filled_skeleton.count("\n") + 1,
                    sum(1 for er in file_result.element_results if er.success),
                )

            # Track tokens and element counts
            for er in file_result.element_results:
                total_input += er.input_tokens
                total_output += er.output_tokens
                if er.success:
                    local_element_count += 1
                    if er.template_used:
                        template_count += 1
                    else:
                        ollama_count += 1
                if er.escalation is not None:
                    escalated_element_count += 1

            # OTel metrics (REQ-MP-705)
            if _elements_local_counter is not None:
                for er in file_result.element_results:
                    if er.success:
                        _elements_local_counter.add(
                            1, {"tier": er.tier.value, "file_path": file_path},
                        )
                        if er.template_used and _template_hits_counter is not None:
                            _template_hits_counter.add(
                                1, {"file_path": file_path},
                            )
                    if er.escalation is not None and _elements_escalated_counter is not None:
                        _elements_escalated_counter.add(
                            1,
                            {"reason": er.escalation.reason.value, "file_path": file_path},
                        )

            # Element-level escalation: only delegate the whole file to
            # fallback when ZERO elements succeeded locally.  When some
            # elements were filled successfully, keep the partial skeleton
            # (Mottainai — don't waste locally-produced assets).
            if file_result.escalated_count > 0 and file_result.success_count == 0:
                escalated_files.append(file_path)

        local_file_count = len(generated_files)

        partial_files = sum(
            1 for fp in target_files
            if fp not in escalated_files and fp not in written_file_paths
        )
        logger.info(
            "Micro Prime: %d elements local (%d files), %d escalated "
            "(%d files to fallback, %d partial kept)",
            local_element_count,
            local_file_count,
            escalated_element_count,
            len(escalated_files),
            partial_files,
        )

        # Mottainai: only delegate files that had escalations to the fallback.
        # Files where all elements were handled locally are kept as-is.
        if escalated_files and self._fallback is not None:
            fallback_result = self._delegate_to_fallback(
                task, context, escalated_files,
            )
            generated_files.extend(fallback_result.generated_files)
            total_input += fallback_result.input_tokens
            total_output += fallback_result.output_tokens
            return GenerationResult(
                success=fallback_result.success,
                generated_files=generated_files,
                input_tokens=total_input,
                output_tokens=total_output,
                cost_usd=fallback_result.cost_usd,
                model=f"micro-prime+{fallback_result.model}",
                metadata={
                    "micro_prime_files_written": local_file_count,
                    "fallback_files_delegated": len(escalated_files),
                    "fallback_files_written": len(fallback_result.generated_files),
                    "micro_prime_elements": local_element_count,
                    "micro_prime_template_hits": template_count,
                    "micro_prime_ollama_generations": ollama_count,
                    "fallback_elements": escalated_element_count,
                    "micro_prime_cost_usd": 0.0,
                    "fallback_cost_usd": fallback_result.cost_usd,
                    "micro_prime_file_results": [
                        _serialize_file_result(fr) for fr in all_file_results
                    ],
                },
            )

        return GenerationResult(
            success=local_file_count > 0,
            generated_files=generated_files,
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=0.0,
            model=f"{self._config.provider}:{self._config.model}",
            metadata={
                "micro_prime_only": True,
                "micro_prime_files_written": local_file_count,
                "micro_prime_elements": local_element_count,
                "micro_prime_template_hits": template_count,
                "micro_prime_ollama_generations": ollama_count,
                "micro_prime_cost_usd": 0.0,
                "micro_prime_file_results": [
                    _serialize_file_result(fr) for fr in all_file_results
                ],
            },
        )

    def _dry_run_classify(
        self,
        manifest: ForwardManifest,
        skeletons: dict[str, str],
        target_files: List[str],
        ollama_available: bool,
    ) -> GenerationResult:
        """Run classification on all elements and print a report without generating code.

        Iterates every target file's elements through ``classify_element()`` and
        the template registry, collecting tier counts and per-file summaries.
        Prints a formatted console report and returns a zero-cost result with
        classification metadata.
        """
        base_url = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        model_name = self._config.model
        templates = self._engine._templates if self._config.templates_enabled else None

        per_file: list[dict[str, Any]] = []
        tier_totals = {t: 0 for t in TierClassification}
        total_elements = 0
        total_local = 0
        total_escalated = 0

        for file_path in target_files:
            file_spec = manifest.file_specs.get(file_path)
            skeleton = skeletons.get(file_path, "")
            if file_spec is None:
                per_file.append({
                    "file": file_path,
                    "skipped": True,
                    "reason": "no file_spec in manifest",
                })
                continue
            if not skeleton:
                per_file.append({
                    "file": file_path,
                    "skipped": True,
                    "reason": "no skeleton generated",
                })
                continue

            skeleton_lines = skeleton.count("\n") + 1
            elements_info: list[dict[str, str]] = []
            file_local = 0
            file_escalated = 0

            for element in file_spec.elements:
                contracts = self._engine._get_element_contracts(
                    element, file_spec, manifest,
                )
                tier, reason = classify_element(
                    element, file_spec, contracts,
                    template_registry=templates,
                    config=self._config,
                )
                tier_totals[tier] += 1
                total_elements += 1

                template_hit = templates.match(element, file_spec) is not None if templates else False

                # Routing: TRIVIAL with template works without Ollama;
                # SIMPLE requires Ollama; MODERATE/COMPLEX always escalate.
                if tier == TierClassification.TRIVIAL and template_hit:
                    file_local += 1
                    total_local += 1
                elif tier in (TierClassification.TRIVIAL, TierClassification.SIMPLE) and ollama_available:
                    file_local += 1
                    total_local += 1
                else:
                    file_escalated += 1
                    total_escalated += 1

                elements_info.append({
                    "name": element.name,
                    "tier": tier.value.upper(),
                    "reason": reason,
                    "template_hit": template_hit,
                })

            per_file.append({
                "file": file_path,
                "element_count": len(file_spec.elements),
                "skeleton_lines": skeleton_lines,
                "elements": elements_info,
                "local": file_local,
                "escalated": file_escalated,
            })

        # Print bypasses log-level filtering — this is a user-facing report.
        report = self._format_dry_run_report(
            per_file, tier_totals, total_elements, total_local,
            ollama_available, model_name, base_url,
        )
        print(report)

        return GenerationResult(
            success=True,
            generated_files=[],
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            model="micro-prime-dry-run",
            metadata={
                "dry_run": True,
                "ollama_available": ollama_available,
                "total_elements": total_elements,
                "total_local": total_local,
                "total_escalated": total_escalated,
                "tier_totals": {t.value: c for t, c in tier_totals.items()},
                "per_file": per_file,
            },
        )

    @staticmethod
    def _format_dry_run_report(
        per_file: list[dict[str, Any]],
        tier_totals: dict[TierClassification, int],
        total_elements: int,
        total_local: int,
        ollama_available: bool,
        model_name: str,
        base_url: str,
    ) -> str:
        """Format the dry-run classification report as a box-drawing string."""
        local_pct = (total_local / total_elements * 100) if total_elements else 0
        ollama_status = (
            f"available ({model_name} @ {base_url})"
            if ollama_available
            else f"unavailable ({base_url})"
        )

        lines = [
            "",
            "\u2554" + "\u2550" * 62 + "\u2557",
            "\u2551  Micro Prime \u2014 Dry Run Classification Report" + " " * 17 + "\u2551",
            "\u255a" + "\u2550" * 62 + "\u255d",
            "",
            f"  Ollama: {ollama_status}",
            "",
        ]

        for pf in per_file:
            if pf.get("skipped"):
                lines.append(f"  {pf['file']}  [SKIPPED: {pf['reason']}]")
                lines.append("")
                continue

            lines.append(
                f"  {pf['file']} ({pf['element_count']} elements, "
                f"skeleton: {pf['skeleton_lines']} lines)"
            )
            for el in pf.get("elements", []):
                line = f"    {el['tier']:<10} {el['name']:<35} {el['reason']}"
                if el["template_hit"]:
                    line += "  [template]"
                lines.append(line)
            lines.append(
                f"    -> {pf['local']} local, "
                f"{pf['escalated']} escalated"
            )
            lines.append("")

        file_count = sum(1 for p in per_file if not p.get("skipped"))
        lines.append("  " + "-" * 60)
        lines.append(f"  Summary: {file_count} files, {total_elements} elements")
        lines.append(
            f"    TRIVIAL:  {tier_totals[TierClassification.TRIVIAL]:>3}  (template match)"
        )
        lines.append(
            f"    SIMPLE:   {tier_totals[TierClassification.SIMPLE]:>3}  (Ollama local)"
        )
        lines.append(
            f"    MODERATE: {tier_totals[TierClassification.MODERATE]:>3}  (cloud fallback)"
        )
        lines.append(
            f"    COMPLEX:  {tier_totals[TierClassification.COMPLEX]:>3}  (cloud fallback)"
        )
        lines.append("")
        lines.append(
            f"  Local generation: {total_local}/{total_elements} elements "
            f"({local_pct:.0f}%)"
        )
        lines.append("")
        return "\n".join(lines)

    def _generate_skeletons(
        self,
        manifest: ForwardManifest,
        target_files: List[str],
    ) -> dict[str, str]:
        """Generate stub skeletons from manifest for target files only.

        Uses ``DeterministicFileAssembler`` to render ``ForwardFileSpec``
        elements into Python source with ``raise NotImplementedError`` stubs.
        Only the current feature's target files are rendered (not the entire
        manifest).  Per-file failures are logged and skipped — they do not
        block other files.

        Returns:
            Dict mapping file path to skeleton source text.
        """
        from startd8.utils.file_assembler import DeterministicFileAssembler

        assembler = DeterministicFileAssembler()
        skeletons: dict[str, str] = {}

        for file_path in target_files:
            file_spec = manifest.file_specs.get(file_path)
            if file_spec is None:
                logger.debug("No file_spec for %s, skipping skeleton", file_path)
                continue
            try:
                source = assembler.render_file(file_spec)
                skeletons[file_path] = source
                logger.debug(
                    "Generated skeleton for %s (%d lines)",
                    file_path,
                    source.count("\n") + 1,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to generate skeleton for %s: %s", file_path, exc,
                )

        return skeletons

    def _check_ollama_available(self) -> bool:
        """Check if Ollama is reachable and the configured model is pulled.

        Result is cached on ``self._ollama_available`` so the HTTP check
        only fires once per adapter instance.  Uses a 5-second timeout to
        avoid blocking generation (REQ-MP-711).
        """
        if self._ollama_available is not None:
            return self._ollama_available

        base_url = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        url = f"{base_url}/api/tags"
        model_name = self._config.model

        try:
            with urlopen(url, timeout=5) as response:
                data = json.loads(response.read().decode())

            model_names: list[str] = []
            for m in data.get("models", []):
                if not isinstance(m, dict):
                    continue
                name = m.get("name", "")
                model_names.append(name)
                if ":" in name:
                    model_names.append(name.split(":")[0])

            model_base = model_name.split(":")[0]
            if model_name in model_names or model_base in model_names:
                self._ollama_available = True
                return True

            logger.warning(
                "Ollama model '%s' not found (available: %s)",
                model_name,
                sorted(set(model_names)),
            )
            self._ollama_available = False
            return False

        except (ConnectionRefusedError, TimeoutError, URLError, OSError) as exc:
            logger.warning("Ollama not reachable at %s: %s", base_url, exc)
            self._ollama_available = False
            return False

    def _delegate_to_fallback(
        self,
        task: str,
        context: Dict[str, Any],
        target_files: List[str],
    ) -> GenerationResult:
        """Delegate to the fallback code generator.

        Sanitizes the context dict before delegation: Pydantic models
        (e.g. ForwardManifest) are converted to dicts so downstream
        ``json.dumps(context)`` calls in the spec builder don't crash.
        """
        if self._fallback is None:
            return GenerationResult(
                success=False,
                error="No fallback generator configured and elements need cloud processing",
            )
        # Sanitize: recursively convert Pydantic models to dicts for JSON compatibility
        clean_context = _sanitize_for_json(context)
        return self._fallback.generate(task, clean_context, target_files)
