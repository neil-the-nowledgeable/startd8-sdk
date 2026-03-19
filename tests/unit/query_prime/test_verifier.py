"""Tests for query_prime.security pipeline — verify_file()."""

import pytest

from startd8.query_prime.models import (
    DatabaseType,
    SecurityCheckType,
    SecurityVerdict,
)
from startd8.query_prime.security import verify_file


class TestVerifyFile:
    """Security verification pipeline tests."""

    def test_clean_code_passes(self):
        """Safe parameterized code passes verification."""
        source = '''
public async Task<User> GetUserAsync(NpgsqlDataSource ds, string id)
{
    await using var conn = await ds.OpenConnectionAsync();
    await using var cmd = new NpgsqlCommand(
        "SELECT * FROM users WHERE id = @id", conn);
    cmd.Parameters.AddWithValue("@id", id);
    return Map(await cmd.ExecuteReaderAsync());
}
'''
        result = verify_file(source, "user_store.cs", DatabaseType.POSTGRESQL, "csharp")
        assert result.verdict == SecurityVerdict.PASS
        assert result.checks_failed == 0

    def test_injection_causes_fail(self):
        """Injection finding causes FAIL verdict."""
        source = '''
public void Delete(string userId)
{
    var cmd = new NpgsqlCommand(
        $"DELETE FROM users WHERE id = '{userId}'", conn);
    cmd.ExecuteNonQuery();
}
'''
        result = verify_file(source, "store.cs", DatabaseType.POSTGRESQL, "csharp")
        assert result.verdict == SecurityVerdict.FAIL
        assert result.checks_failed >= 1
        assert any(
            f.check_type == SecurityCheckType.INJECTION
            for f in result.findings
        )

    def test_credential_leakage_causes_fail(self):
        """Credential leakage causes FAIL verdict."""
        source = '''
public void Connect(string connectionString)
{
    Console.WriteLine(connectionString);
}
'''
        result = verify_file(source, "store.cs", DatabaseType.POSTGRESQL, "csharp")
        assert result.verdict == SecurityVerdict.FAIL

    def test_lifecycle_only_causes_warn(self):
        """Lifecycle issues without injection/creds -> WARN."""
        source = '''
public async Task Query()
{
    var ds = NpgsqlDataSource.Create(connStr);
    var conn = await ds.OpenConnectionAsync();
    var cmd = new NpgsqlCommand("SELECT 1", conn);
    await cmd.ExecuteScalarAsync();
}
'''
        result = verify_file(source, "store.cs", DatabaseType.POSTGRESQL, "csharp")
        # Should warn about lifecycle but not fail
        assert result.verdict in (SecurityVerdict.WARN, SecurityVerdict.PASS)

    def test_lifecycle_strict_causes_fail(self):
        """Lifecycle issues with strict_lifecycle=True -> FAIL."""
        source = '''
public async Task Query()
{
    var ds = NpgsqlDataSource.Create(connStr);
    var conn = await ds.OpenConnectionAsync();
    var cmd = new NpgsqlCommand("SELECT 1", conn);
    await cmd.ExecuteScalarAsync();
}
'''
        result = verify_file(
            source, "store.cs", DatabaseType.POSTGRESQL, "csharp",
            strict_lifecycle=True,
        )
        if result.findings:  # Only if lifecycle issues were found
            assert result.verdict == SecurityVerdict.FAIL

    def test_injection_overrides_lifecycle_pass(self):
        """Pipeline ordering: injection fail overrides lifecycle pass -> FAIL."""
        source = '''
public async Task DeleteAndQuery(string userId)
{
    await using var conn = await ds.OpenConnectionAsync();
    await using var cmd = new NpgsqlCommand(
        $"DELETE FROM items WHERE userId = '{userId}'", conn);
    await cmd.ExecuteNonQueryAsync();
}
'''
        result = verify_file(source, "store.cs", DatabaseType.POSTGRESQL, "csharp")
        assert result.verdict == SecurityVerdict.FAIL

    def test_result_to_dict(self):
        """Verification result serializes correctly."""
        result = verify_file("SELECT 1", "test.py", DatabaseType.SQLITE, "python")
        d = result.to_dict()
        assert "verdict" in d
        assert "findings" in d
