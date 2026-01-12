"""
Startd8 self-diagnostic workflow.

This module provides comprehensive diagnostics for the Startd8 SDK,
including health checks, agent-based analysis, and safe auto-fixes.

Main components:
- DiagnosticRunner: Orchestrates all health checks
- DiagnosticAnalyzer: Uses LLM agents to analyze failures
- AutoFixer: Applies safe, reversible fixes
- run_diagnostics: Convenience function for quick diagnostics

Example:
    from startd8.diagnostics import run_diagnostics, analyze_report

    # Run all diagnostics
    report = run_diagnostics()

    # Check for issues
    if report.has_failures():
        print(report.to_markdown())

        # Get AI-powered analysis
        analysis = analyze_report(report, agent=my_claude_agent)
        print(analysis)
"""

from .models import (
    HealthStatus,
    HealthCheck,
    CheckCategory,
    DiagnosticReport,
    CheckDefinition,
)
from .runner import (
    DiagnosticRunner,
    run_diagnostics,
)
from .analyzer import (
    DiagnosticAnalyzer,
    analyze_report,
)
from .auto_fix import (
    AutoFixer,
    apply_safe_fixes,
)

__all__ = [
    # Models
    "HealthStatus",
    "HealthCheck",
    "CheckCategory",
    "DiagnosticReport",
    "CheckDefinition",
    # Runner
    "DiagnosticRunner",
    "run_diagnostics",
    # Analyzer
    "DiagnosticAnalyzer",
    "analyze_report",
    # Auto-fix
    "AutoFixer",
    "apply_safe_fixes",
]
