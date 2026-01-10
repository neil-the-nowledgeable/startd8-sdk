# TASK-006: Evaluation Reporter Tool

**Status:** OPEN  
**Priority:** Medium  
**Category:** Eval  
**Created:** 2025-12-09  
**Assigned To:** Unassigned  
**Dependencies:** TASK-003  

---

## Objective

Create a reporting tool that generates human-readable reports from evaluation results, supporting multiple output formats.

## Acceptance Criteria

- [ ] Generate Markdown reports from JSON results
- [ ] Include summary statistics
- [ ] Include per-test-case details
- [ ] Support comparison mode (multiple runs)
- [ ] CLI interface
- [ ] Optional HTML output

## Context

The evaluation framework (TASK-003) produces JSON results. This task creates tools to transform those results into readable reports for humans and for sharing.

## Implementation Notes

### Report Sections

1. **Executive Summary**
   - Total tests run
   - Pass/fail counts
   - Average metrics

2. **Skill Comparison** (if multiple skills)
   - Side-by-side metrics table
   - Winner per metric

3. **Test Case Details**
   - Individual results
   - Metrics breakdown
   - Any errors or issues

4. **Recommendations**
   - Based on metrics analysis

### Example Markdown Output

```markdown
# Evaluation Report: game-skills-v1

**Run Date:** 2025-12-09  
**Skills Tested:** 2  
**Total Tests:** 8  

## Summary

| Metric | html5-game-designer-pro | mcp-builder |
|--------|------------------------|-------------|
| Avg Latency | 2,500 ms | 3,200 ms |
| Avg Tokens | 5,678 | 4,890 |
| Success Rate | 100% | 95% |

## Winner: html5-game-designer-pro

Better latency and 100% success rate.

## Test Case Details

### TC001: Simple Tower Defense

| Skill | Status | Latency | Tokens |
|-------|--------|---------|--------|
| html5-game-designer-pro | ✅ Pass | 2,100 ms | 5,234 |
| mcp-builder | ✅ Pass | 2,900 ms | 4,567 |

...
```

### CLI Interface

```bash
# Generate Markdown report
python reporter.py results/2025-12-09_run1.json -o report.md

# Generate HTML report
python reporter.py results/2025-12-09_run1.json -f html -o report.html

# Compare two runs
python reporter.py compare run1.json run2.json -o comparison.md
```

---

## Work Log

*No work started yet*

---

## Blockers

- **Depends on TASK-003** — Need evaluation results to report on

---

## Completion Notes

*Task not yet complete*
