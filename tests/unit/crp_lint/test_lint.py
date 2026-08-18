"""Unit tests for the det-crp/0.1 conformance lint (SCHEMA_det-crp-0.1 §10).

Covers the review-log integrity checks (the load-bearing ones — the cross-model memory must not lose a
finding): unique ids, orphan disposition, double-triage, A/B scaffold presence; the focus check; the
conditional header check; and the SARIF-imports-not-vendors invariant.
"""

from __future__ import annotations

import pytest

from startd8.crp_lint import (
    findings_to_sarif,
    has_focus,
    has_review_log,
    lint_crp,
    lint_focus,
    lint_review_log,
)

pytestmark = pytest.mark.unit


CLEAN_LOG = """# PLAN

### Appendix A: Applied Suggestions
| ID | Suggestion | Date |
| R1-S1 | did it | 2026 |

### Appendix B: Rejected Suggestions (with Rationale)
| ID | Suggestion | Rationale | Date |
| R1-S2 | no | too costly | 2026 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)
#### Review Round R1
| ID | Area | Suggestion |
| R1-S1 | arch | do it |
| R1-S2 | perf | maybe |
| R1-S3 | docs | still pending |
"""

FOCUS = """# CRP focus — Widget

**Least-reviewed target:** the widget's error path.

**Do not re-litigate:**
- the API shape.
"""


# ── clean cases ──────────────────────────────────────────────────────────────────────────────────


def test_clean_review_log_has_no_findings():
    assert lint_review_log(CLEAN_LOG) == []


def test_pending_c_suggestion_is_not_a_finding():
    # R1-S3 is in C but neither A nor B → PENDING (allowed, §4), not flagged.
    assert not any(f.check == "orphan-disposition" for f in lint_review_log(CLEAN_LOG))


def test_focus_with_target_is_clean():
    assert lint_focus(FOCUS) == []
    assert has_focus(FOCUS) is True


# ── the integrity violations (§3/§4) ───────────────────────────────────────────────────────────────


def test_orphan_disposition_flagged():
    # Appendix A applies R1-S9 which never appears in Appendix C.
    bad = CLEAN_LOG.replace("| R1-S1 | did it | 2026 |", "| R1-S9 | orphan | 2026 |")
    checks = {f.check for f in lint_review_log(bad)}
    assert "orphan-disposition" in checks


def test_double_triage_flagged():
    # R1-S1 is Applied AND (now) Rejected.
    bad = CLEAN_LOG.replace(
        "| R1-S2 | no | too costly | 2026 |", "| R1-S1 | no | reversed | 2026 |"
    )
    findings = lint_review_log(bad)
    assert any(f.check == "double-triage" and f.severity == "error" for f in findings)


def test_repeated_id_reference_is_not_flagged():
    # Dogfood fold-back: an id REFERENCED again (a coverage matrix / endorsement row) is NOT a
    # duplicate — a text lint can't tell a reference from a second definition, so it never flags it.
    referenced_again = CLEAN_LOG + "\n\n### Coverage Matrix\n| R1-S1 | covered |\n"
    assert not any(
        f.check == "duplicate-suggestion-id" for f in lint_review_log(referenced_again)
    )
    # and a genuine double-triage IS still caught (the reliable integrity check remains)
    bad = CLEAN_LOG.replace(
        "| R1-S2 | no | too costly | 2026 |", "| R1-S1 | no | reversed | 2026 |"
    )
    assert any(f.check == "double-triage" for f in lint_review_log(bad))


def test_missing_ab_scaffold_flagged():
    # A review-log with an Appendix C but no A/B scaffold.
    bare = (
        "# PLAN\n\n### Appendix C: Incoming\n#### Review Round R1\n| ID |\n| R1-S1 |\n"
    )
    checks = {f.check for f in lint_review_log(bare)}
    assert "missing-appendix-a" in checks and "missing-appendix-b" in checks


def test_focus_missing_target_flagged():
    bad = FOCUS.replace("**Least-reviewed target:** the widget's error path.", "")
    assert any(f.check == "focus-target-missing" for f in lint_focus(bad))


# ── non-targets + header + SARIF ───────────────────────────────────────────────────────────────────


def test_non_review_log_yields_nothing():
    assert lint_review_log("# just a doc, no appendix") == []
    assert has_review_log("# just a doc") is False


def test_conditional_header_check():
    from startd8.crp_lint import lint_header

    assert lint_header("no header here") == []  # absent → skipped
    bad = "formatVersion: det-crp/9.9\ncompanionKind: PLAN\n"
    checks = {f.check for f in lint_header(bad)}
    assert "format-version" in checks and "companion-kind" in checks


def test_lint_crp_composes_all():
    doc = FOCUS + "\n" + CLEAN_LOG
    assert lint_crp(doc) == []


def test_sarif_imports_not_vendors():
    import startd8.crp_lint.lint as m

    assert (
        m.render_sarif_from_findings.__module__ == "startd8.coverage_map.findings_sarif"
    )
    bad = CLEAN_LOG.replace(
        "| R1-S2 | no | too costly | 2026 |", "| R1-S1 | no | reversed | 2026 |"
    )
    sarif = findings_to_sarif(lint_review_log(bad), corpus="test")
    assert sarif["version"] == "2.1.0"
    assert sarif["runs"][0]["tool"]["driver"]["name"] == "startd8-crp-lint"
