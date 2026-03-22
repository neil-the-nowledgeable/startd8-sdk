"""Tests for security_prime.allowlist_audit — Phase 3."""

from __future__ import annotations

import pytest

from startd8.security_prime.allowlist import build_allowlist_metrics
from startd8.security_prime.allowlist_audit import (
    _STALE_RUN_THRESHOLD,
    detect_stale_entries,
    render_allowlist_audit,
)


class TestBuildAllowlistMetrics:
    def test_empty_allowlist(self):
        result = build_allowlist_metrics([], {})
        assert result["total_entries"] == 0
        assert result["hit_count"] == 0
        assert result["unhit_count"] == 0

    def test_all_hit(self):
        allowlist = [
            {"file_pattern": "**/*Store.cs", "check_id": "injection", "justification": "safe"},
        ]
        tracker = {"**/*Store.cs": ["src/CartStore.cs", "src/ProductStore.cs"]}
        result = build_allowlist_metrics(allowlist, tracker)
        assert result["hit_count"] == 1
        assert result["unhit_count"] == 0
        assert len(result["hit_entries"][0]["matched_files"]) == 2

    def test_mixed_hit_unhit(self):
        allowlist = [
            {"file_pattern": "**/*Store.cs", "check_id": "injection", "justification": ""},
            {"file_pattern": "**/*Cache.py", "check_id": "lifecycle", "justification": ""},
        ]
        tracker = {"**/*Store.cs": ["src/Store.cs"]}
        result = build_allowlist_metrics(allowlist, tracker)
        assert result["hit_count"] == 1
        assert result["unhit_count"] == 1


class TestDetectStaleEntries:
    def test_no_unhit(self):
        current = {"unhit_entries": []}
        stale = detect_stale_entries(current, [])
        assert stale == []

    def test_not_stale_yet(self):
        entry = {"file_pattern": "*.cs", "check_id": "injection"}
        current = {"unhit_entries": [entry]}
        # Only 2 prior runs
        archived = [{"unhit_entries": [entry]}] * 2
        stale = detect_stale_entries(current, archived)
        assert stale == []

    def test_stale_after_threshold(self):
        entry = {"file_pattern": "*.cs", "check_id": "injection"}
        current = {"unhit_entries": [entry]}
        archived = [{"unhit_entries": [entry]}] * (_STALE_RUN_THRESHOLD - 1)
        stale = detect_stale_entries(current, archived)
        assert len(stale) == 1
        assert stale[0]["runs_unhit"] == _STALE_RUN_THRESHOLD

    def test_break_in_consecutive(self):
        entry = {"file_pattern": "*.cs", "check_id": "injection"}
        current = {"unhit_entries": [entry]}
        # Recent runs are unhit, but older one was hit (empty unhit list)
        archived = [
            {"unhit_entries": [entry]},
            {"unhit_entries": []},  # Was hit in this run
            {"unhit_entries": [entry]},
            {"unhit_entries": [entry]},
        ]
        stale = detect_stale_entries(current, archived)
        # consecutive from newest: current(1) + archived[-1](2) = 2 < threshold
        assert stale == []


class TestRenderAllowlistAudit:
    def test_basic_rendering(self):
        metrics = {
            "total_entries": 2,
            "hit_count": 1,
            "unhit_count": 1,
            "hit_entries": [
                {"file_pattern": "*.cs", "check_id": "injection",
                 "matched_files": ["a.cs"]},
            ],
            "unhit_entries": [],
        }
        stale = [{"file_pattern": "*.py", "check_id": "lifecycle", "runs_unhit": 6}]
        md = render_allowlist_audit(metrics, stale)
        assert "Security Allowlist Audit" in md
        assert "*.cs" in md
        assert "Stale Entries" in md
        assert "6" in md

    def test_no_stale(self):
        metrics = {"total_entries": 1, "hit_count": 1, "unhit_count": 0,
                   "hit_entries": [], "unhit_entries": []}
        md = render_allowlist_audit(metrics, [])
        assert "Stale" not in md
