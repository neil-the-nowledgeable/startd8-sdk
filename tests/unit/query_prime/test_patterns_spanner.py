"""Tests for Spanner patterns — QP-F2 false positive regression (critical)."""

import pytest

from startd8.query_prime.models import DatabaseType
from startd8.query_prime.patterns import DatabasePatternRegistry
from startd8.query_prime.security.injection import detect_injection


class TestSpannerPatterns:
    def test_spanner_csharp_registered(self):
        pattern = DatabasePatternRegistry.get(DatabaseType.SPANNER, "csharp")
        assert pattern is not None
        assert "Spanner" in pattern.client_library

    def test_spanner_go_registered(self):
        pattern = DatabasePatternRegistry.get(DatabaseType.SPANNER, "go")
        assert pattern is not None

    def test_spanner_java_registered(self):
        pattern = DatabasePatternRegistry.get(DatabaseType.SPANNER, "java")
        assert pattern is not None

    def test_at_param_safe_in_spanner(self):
        """@param syntax is SAFE in Spanner (QP-F2 regression guard)."""
        pattern = DatabasePatternRegistry.get(DatabaseType.SPANNER, "csharp")
        text = 'cmd.Parameters.Add("userId", SpannerDbType.String, userId);'
        assert any(p.search(text) for p in pattern.safe_patterns)

    def test_qp_f2_no_false_positive(self):
        """QP-F2 critical regression test: safe Spanner code must NOT flag."""
        source = '''
public async Task<CartItem> GetCartItemAsync(string userId)
{
    using var cmd = connection.CreateSelectCommand(
        "SELECT * FROM CartItems WHERE UserId = @userId");
    cmd.Parameters.Add("userId", SpannerDbType.String, userId);
    using var reader = await cmd.ExecuteReaderAsync();
    if (await reader.ReadAsync())
    {
        return new CartItem { UserId = reader.GetString(0) };
    }
    return null;
}
'''
        findings = detect_injection(source, DatabaseType.SPANNER, "csharp")
        assert len(findings) == 0, (
            f"QP-F2 REGRESSION: safe Spanner code flagged as injection! "
            f"Findings: {findings}"
        )

    def test_spanner_string_interpolation_detected(self):
        """String interpolation in Spanner query IS unsafe."""
        source = '''
public async Task DeleteAsync(string userId)
{
    using var cmd = connection.CreateDeleteCommand(
        $"DELETE FROM CartItems WHERE UserId = '{userId}'");
    await cmd.ExecuteNonQueryAsync();
}
'''
        findings = detect_injection(source, DatabaseType.SPANNER, "csharp")
        assert len(findings) >= 1

    def test_spanner_go_safe_statement(self):
        """Go spanner.Statement with Params is safe."""
        pattern = DatabasePatternRegistry.get(DatabaseType.SPANNER, "go")
        text = 'stmt := spanner.Statement{SQL: "SELECT * FROM t WHERE id = @id", Params: map[string]interface{}{"id": id}}'
        assert any(p.search(text) for p in pattern.safe_patterns)
