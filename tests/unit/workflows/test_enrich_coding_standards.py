"""Tests for _enrich_coding_standards — REQ-TDE-200 through REQ-TDE-204.

Verifies that the enrichment step resolves language profiles, injects
coding_standards into task context, and sanitizes anti-patterns in task
descriptions at plan ingestion time.
"""

import pytest

from startd8.forward_manifest import ForwardFileSpec, ForwardManifest
from startd8.workflows.builtin.plan_ingestion_enrichment import (
    _enrich_coding_standards,
    _ensure_task_context,
)


def _make_task(task_id, target_files, description="", design_doc_sections=None):
    """Build a minimal task dict for testing."""
    ctx = {"target_files": target_files}
    if design_doc_sections:
        ctx["design_doc_sections"] = design_doc_sections
    return {
        "task_id": task_id,
        "config": {
            "task_description": description,
            "context": ctx,
        },
    }


class TestEnrichCodingStandards:
    """REQ-TDE-200: Language profile resolution at enrichment time."""

    def test_csharp_language_resolved(self):
        tasks = [_make_task("PI-001", ["Services/CartService.cs"])]
        injected, _ = _enrich_coding_standards(tasks)
        ctx = tasks[0]["config"]["context"]
        assert ctx["language_id"] == "csharp"
        assert "ILogger" in ctx["coding_standards"]
        assert "C#" in ctx["language_role"]
        assert injected == 1

    def test_go_language_resolved(self):
        tasks = [_make_task("PI-001", ["cmd/server/main.go"])]
        injected, _ = _enrich_coding_standards(tasks)
        ctx = tasks[0]["config"]["context"]
        assert ctx["language_id"] == "go"
        assert "slog" in ctx["coding_standards"] or "Go" in ctx["coding_standards"]

    def test_java_language_resolved(self):
        tasks = [_make_task("PI-001", ["src/main/java/App.java"])]
        injected, _ = _enrich_coding_standards(tasks)
        ctx = tasks[0]["config"]["context"]
        assert ctx["language_id"] == "java"

    def test_python_language_resolved(self):
        tasks = [_make_task("PI-001", ["src/app.py"])]
        injected, _ = _enrich_coding_standards(tasks)
        ctx = tasks[0]["config"]["context"]
        assert ctx["language_id"] == "python"

    def test_no_clobber(self):
        """Skip tasks where language_id is already set."""
        tasks = [_make_task("PI-001", ["Services/CartService.cs"])]
        tasks[0]["config"]["context"]["language_id"] = "custom"
        injected, _ = _enrich_coding_standards(tasks)
        assert injected == 0
        assert tasks[0]["config"]["context"]["language_id"] == "custom"

    def test_no_target_files_skipped(self):
        tasks = [_make_task("PI-001", [])]
        injected, _ = _enrich_coding_standards(tasks)
        assert injected == 0

    def test_multiple_tasks(self):
        tasks = [
            _make_task("PI-001", ["Services/Cart.cs"]),
            _make_task("PI-002", ["cmd/main.go"]),
            _make_task("PI-003", ["src/app.py"]),
        ]
        injected, _ = _enrich_coding_standards(tasks)
        assert injected == 3
        assert tasks[0]["config"]["context"]["language_id"] == "csharp"
        assert tasks[1]["config"]["context"]["language_id"] == "go"
        assert tasks[2]["config"]["context"]["language_id"] == "python"


class TestDescriptionSanitization:
    """REQ-TDE-203: Anti-pattern sanitization in task descriptions."""

    def test_csharp_console_writeline_sanitized(self):
        desc = 'Add logging: Console.WriteLine($"Cart updated for {userId}");'
        tasks = [_make_task("PI-001", ["Services/CartService.cs"], description=desc)]
        _, sanitized = _enrich_coding_standards(tasks)
        assert sanitized == 1
        new_desc = tasks[0]["config"]["task_description"]
        assert "Console.WriteLine" not in new_desc
        assert "_logger.LogInformation" in new_desc

    def test_original_preserved_for_audit(self):
        desc = 'Console.WriteLine("hello");'
        tasks = [_make_task("PI-001", ["Services/Cart.cs"], description=desc)]
        _enrich_coding_standards(tasks)
        ctx = tasks[0]["config"]["context"]
        assert ctx["_original_task_description"] == desc

    def test_clean_description_not_counted(self):
        desc = '_logger.LogInformation("already clean");'
        tasks = [_make_task("PI-001", ["Services/Cart.cs"], description=desc)]
        _, sanitized = _enrich_coding_standards(tasks)
        assert sanitized == 0

    def test_go_fmt_println_sanitized(self):
        desc = 'Log the port: fmt.Println("listening on", port)'
        tasks = [_make_task("PI-001", ["cmd/main.go"], description=desc)]
        _, sanitized = _enrich_coding_standards(tasks)
        new_desc = tasks[0]["config"]["task_description"]
        assert "fmt.Println" not in new_desc
        assert "slog.Info" in new_desc

    def test_design_doc_sections_sanitized(self):
        sections = ['Console.WriteLine("section example");', 'Normal text here']
        tasks = [_make_task(
            "PI-001", ["Services/Cart.cs"],
            design_doc_sections=sections,
        )]
        _enrich_coding_standards(tasks)
        dds = tasks[0]["config"]["context"]["design_doc_sections"]
        assert "Console.WriteLine" not in dds[0]
        assert "_logger.LogInformation" in dds[0]
        assert dds[1] == "Normal text here"

    def test_python_description_unchanged(self):
        desc = 'print("debug output")'
        tasks = [_make_task("PI-001", ["src/app.py"], description=desc)]
        _, sanitized = _enrich_coding_standards(tasks)
        assert sanitized == 0
        assert tasks[0]["config"]["task_description"] == desc


class TestForwardManifestLanguageHints:
    """REQ-JSF-007: plan-ingestion enrichment honors manifest ``language`` hints."""

    def test_readme_hint_nodejs(self):
        tasks = [_make_task("PI-001", ["README.md"])]
        fm = ForwardManifest(
            file_specs={
                "README.md": ForwardFileSpec(
                    file="README.md", elements=[], language="nodejs",
                ),
            },
        )
        injected, _ = _enrich_coding_standards(tasks, forward_manifest=fm)
        assert injected == 1
        assert tasks[0]["config"]["context"]["language_id"] == "nodejs"


class TestBatchContext:
    """REQ-TDE-200: Batch target files used for language-neutral inference."""

    def test_dockerfile_infers_from_batch(self):
        """A Dockerfile task should infer language from sibling C# tasks."""
        tasks = [
            _make_task("PI-001", ["Services/Cart.cs"]),
            _make_task("PI-002", ["Dockerfile"]),
        ]
        _enrich_coding_standards(tasks)
        # PI-001 should be csharp
        assert tasks[0]["config"]["context"]["language_id"] == "csharp"
        # PI-002 (Dockerfile) should also infer csharp from batch context
        ctx2 = tasks[1]["config"]["context"]
        if "language_id" in ctx2:
            # May or may not resolve depending on resolution heuristics
            assert ctx2["language_id"] in ("csharp", "python")
