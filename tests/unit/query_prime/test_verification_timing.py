"""Tests for verification timing instrumentation in verify_file()."""

from __future__ import annotations

from startd8.query_prime.models import SecurityVerdict
from startd8.query_prime.security import verify_file


class TestVerificationTiming:
    """Verify that verify_file() populates timing data."""

    def test_timing_populated_on_clean_file(self):
        source = 'var x = cmd.Parameters.AddWithValue("@id", id);'
        result = verify_file(source, "test.cs", "postgresql", "csharp")
        assert result.verification_timing_ms is not None
        assert "injection_ms" in result.verification_timing_ms
        assert "credential_ms" in result.verification_timing_ms
        assert "lifecycle_ms" in result.verification_timing_ms

    def test_timing_values_are_non_negative(self):
        source = "SELECT 1;"
        result = verify_file(source, "test.cs", "postgresql", "csharp")
        assert result.verification_timing_ms is not None
        for key, value in result.verification_timing_ms.items():
            assert value >= 0.0, f"{key} has negative timing"

    def test_timing_included_in_to_dict(self):
        source = "SELECT 1;"
        result = verify_file(source, "test.cs", "postgresql", "csharp")
        d = result.to_dict()
        assert "verification_timing_ms" in d
        assert isinstance(d["verification_timing_ms"], dict)
