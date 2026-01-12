"""
Diagnostic analyzer that uses startd8 agents to analyze failures.

The DiagnosticAnalyzer takes a DiagnosticReport with failures and uses
an LLM agent to perform root cause analysis and generate recommendations.
"""

from typing import Any, List, Optional

from .models import DiagnosticReport, HealthCheck, HealthStatus


# Analysis prompt template
ANALYSIS_PROMPT_TEMPLATE = """You are analyzing diagnostic results for the Startd8 SDK.

## Diagnostic Report
Generated: {timestamp}
Summary: {healthy} healthy, {warning} warnings, {critical} critical, {unknown} unknown

## Failed Checks
{formatted_failures}

## Task
Analyze these diagnostic failures and provide:
1. Root cause analysis for each failure
2. Determine if any failures are related
3. Specific fix steps for each issue
4. Suggestions to prevent these issues in the future

## Output Format

### Root Cause Analysis
[For each failure, explain the likely root cause]

### Related Issues
[If any failures are related, explain how]

### Recommended Fixes
[Numbered list of specific fix steps]

### Prevention Measures
[How to prevent these issues in the future]
"""


class DiagnosticAnalyzer:
    """
    Uses startd8 agents to analyze diagnostic failures.

    The analyzer takes a DiagnosticReport and uses an LLM agent to provide
    semantic analysis, root cause identification, and fix recommendations.

    Example:
        from startd8.agents import MockAgent, ClaudeAgent

        # Use mock for testing
        analyzer = DiagnosticAnalyzer()  # Uses MockAgent by default
        analysis = analyzer.analyze_failures(report)

        # Use real agent for production
        analyzer = DiagnosticAnalyzer(agent=ClaudeAgent(name="diagnostic-analyzer"))
        analysis = analyzer.analyze_failures(report)
    """

    def __init__(self, agent: Optional[Any] = None):
        """
        Initialize the diagnostic analyzer.

        Args:
            agent: Agent to use for analysis. Defaults to MockAgent for safety.
        """
        if agent is None:
            # Default to MockAgent for safe self-testing
            from startd8.agents import MockAgent
            self.agent = MockAgent(name="diagnostic-analyzer")
        else:
            self.agent = agent

    def analyze_failures(self, report: DiagnosticReport) -> str:
        """
        Analyze diagnostic failures using the configured agent.

        Args:
            report: DiagnosticReport containing failures to analyze

        Returns:
            Analysis text with root cause, fixes, and recommendations
        """
        failures = report.get_failures()
        if not failures:
            return "No failures to analyze. All diagnostics passed."

        prompt = self._build_analysis_prompt(report, failures)
        response, _, _ = self.agent.generate(prompt)

        # Store analysis in report
        report.analysis = response
        report.recommendations = self._extract_recommendations(response)

        return response

    def _build_analysis_prompt(
        self,
        report: DiagnosticReport,
        failures: List[HealthCheck],
    ) -> str:
        """
        Build the analysis prompt from the diagnostic report.

        Args:
            report: Full diagnostic report
            failures: List of failed checks

        Returns:
            Formatted prompt string
        """
        summary = report.summary

        # Format failures
        failure_lines = []
        for check in failures:
            status_icon = {
                HealthStatus.WARNING: "WARNING",
                HealthStatus.CRITICAL: "CRITICAL",
                HealthStatus.UNKNOWN: "UNKNOWN",
            }.get(check.status, "ISSUE")

            failure_lines.append(f"### [{status_icon}] {check.name}")
            failure_lines.append(f"Category: {check.category.value}")
            failure_lines.append(f"Message: {check.message}")

            if check.details:
                failure_lines.append("Details:")
                for key, value in check.details.items():
                    failure_lines.append(f"  - {key}: {value}")

            if check.fix_hint:
                failure_lines.append(f"Fix hint: {check.fix_hint}")

            failure_lines.append("")

        formatted_failures = "\n".join(failure_lines)

        return ANALYSIS_PROMPT_TEMPLATE.format(
            timestamp=report.generated_at.strftime("%Y-%m-%d %H:%M:%S"),
            healthy=summary.get("healthy", 0),
            warning=summary.get("warning", 0),
            critical=summary.get("critical", 0),
            unknown=summary.get("unknown", 0),
            formatted_failures=formatted_failures,
        )

    def _extract_recommendations(self, analysis: str) -> List[str]:
        """
        Extract actionable recommendations from the analysis text.

        Args:
            analysis: Agent's analysis response

        Returns:
            List of recommendation strings
        """
        recommendations = []

        # Look for numbered lists in the "Recommended Fixes" section
        in_fixes_section = False
        for line in analysis.split("\n"):
            line = line.strip()

            if "recommended fix" in line.lower() or "fix steps" in line.lower():
                in_fixes_section = True
                continue

            if in_fixes_section:
                # Stop at next section
                if line.startswith("###") or line.startswith("##"):
                    in_fixes_section = False
                    continue

                # Extract numbered items
                if line and (line[0].isdigit() or line.startswith("-")):
                    # Clean up the line
                    clean_line = line.lstrip("0123456789.-) ").strip()
                    if clean_line:
                        recommendations.append(clean_line)

        return recommendations


def analyze_report(
    report: DiagnosticReport,
    agent: Optional[Any] = None,
) -> str:
    """
    Convenience function to analyze a diagnostic report.

    Args:
        report: DiagnosticReport to analyze
        agent: Optional agent to use (defaults to MockAgent)

    Returns:
        Analysis text with recommendations

    Example:
        report = run_diagnostics()
        if report.has_failures():
            analysis = analyze_report(report, agent=my_claude_agent)
            print(analysis)
    """
    analyzer = DiagnosticAnalyzer(agent=agent)
    return analyzer.analyze_failures(report)
