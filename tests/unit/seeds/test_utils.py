"""Tests for startd8.seeds.utils — REQ-GPC-100."""

import pytest

from startd8.seeds.utils import is_omitted


class TestIsOmitted:
    """REQ-GPC-100: detect ContextCore profile-omitted markers."""

    def test_detects_source_profile_marker(self):
        assert is_omitted({"_omitted": "profile=source"}) is True

    def test_detects_observability_profile_marker(self):
        assert is_omitted({"_omitted": "profile=observability"}) is True

    def test_detects_marker_with_extra_keys(self):
        # Marker dicts may evolve to carry additional metadata
        assert is_omitted({"_omitted": "profile=source", "reason": "scoped"}) is True

    def test_rejects_normal_dict(self):
        assert is_omitted({"dashboard": {"uid": "abc"}}) is False

    def test_rejects_empty_dict(self):
        assert is_omitted({}) is False

    def test_rejects_none(self):
        assert is_omitted(None) is False

    def test_rejects_list(self):
        assert is_omitted([]) is False

    def test_rejects_string(self):
        assert is_omitted("_omitted") is False

    def test_rejects_int(self):
        assert is_omitted(42) is False

    def test_rejects_bool(self):
        assert is_omitted(True) is False
