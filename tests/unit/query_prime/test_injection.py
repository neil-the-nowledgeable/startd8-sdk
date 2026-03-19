"""Tests for query_prime.security.injection — SQL injection detection."""

import pytest

from startd8.query_prime.models import DatabaseType, SecurityCheckType
from startd8.query_prime.security.injection import detect_injection


class TestInjectionDetection:
    """SQL injection detection tests."""

    def test_qp_f1_string_interpolation_csharp(self):
        """QP-F1 golden case: C# string interpolation -> INJECTION error."""
        source = '''
public async Task DeleteCartAsync(string userId)
{
    var cmd = new NpgsqlCommand(
        $"DELETE FROM cart_items WHERE userId = '{userId}'", conn);
    await cmd.ExecuteNonQueryAsync();
}
'''
        findings = detect_injection(source, DatabaseType.POSTGRESQL, "csharp")
        assert len(findings) >= 1
        assert findings[0].check_type == SecurityCheckType.INJECTION
        assert findings[0].severity == "error"

    def test_qp_f2_spanner_safe_parameterization(self):
        """QP-F2 golden case: Spanner @param is SAFE (no false positive)."""
        source = '''
public async Task<Cart> GetCartAsync(string userId)
{
    var cmd = connection.CreateSelectCommand(
        "SELECT * FROM CartItems WHERE UserId = @userId");
    cmd.Parameters.Add("userId", SpannerDbType.String, userId);
    using var reader = await cmd.ExecuteReaderAsync();
    return MapCart(reader);
}
'''
        findings = detect_injection(source, DatabaseType.SPANNER, "csharp")
        assert len(findings) == 0, f"False positive! Findings: {findings}"

    def test_safe_parameterized_postgresql_python(self):
        """psycopg2 %s parameterization is safe."""
        source = '''
def get_user(conn, user_id):
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        return cur.fetchone()
'''
        findings = detect_injection(source, DatabaseType.POSTGRESQL, "python")
        assert len(findings) == 0

    def test_unsafe_fstring_python(self):
        """Python f-string in SQL is unsafe."""
        source = '''
def delete_user(conn, user_id):
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM users WHERE id = '{user_id}'")
'''
        findings = detect_injection(source, DatabaseType.POSTGRESQL, "python")
        assert len(findings) >= 1
        assert findings[0].check_type == SecurityCheckType.INJECTION

    def test_safe_parameterized_nodejs(self):
        """Node.js $1 parameterization is safe."""
        source = '''
async function getUser(pool, userId) {
    const result = await pool.query(
        "SELECT * FROM users WHERE id = $1", [userId]
    );
    return result.rows[0];
}
'''
        findings = detect_injection(source, DatabaseType.POSTGRESQL, "nodejs")
        assert len(findings) == 0

    def test_unsafe_template_literal_nodejs(self):
        """Node.js template literal in SQL is unsafe."""
        source = '''
async function deleteUser(pool, userId) {
    await pool.query(`DELETE FROM users WHERE id = '${userId}'`);
}
'''
        findings = detect_injection(source, DatabaseType.POSTGRESQL, "nodejs")
        assert len(findings) >= 1

    def test_comment_lines_skipped(self):
        """Comments should not trigger findings."""
        source = '''
// $"DELETE FROM {table} WHERE id = '{id}'"
// This is just a comment about the old pattern
public async Task SafeDelete(string id)
{
    var cmd = new NpgsqlCommand("DELETE FROM items WHERE id = @id", conn);
    cmd.Parameters.AddWithValue("@id", id);
    await cmd.ExecuteNonQueryAsync();
}
'''
        findings = detect_injection(source, DatabaseType.POSTGRESQL, "csharp")
        assert len(findings) == 0

    def test_unknown_database_returns_empty(self):
        """Unknown database+language combo returns no findings."""
        findings = detect_injection("SELECT 1", "oracle", "ruby")
        assert findings == []

    def test_finding_has_pattern_hash(self):
        """Each finding should have a non-empty pattern hash."""
        source = '''
public void Run() {
    var cmd = new NpgsqlCommand($"SELECT * FROM t WHERE x = '{x}'", conn);
}
'''
        findings = detect_injection(source, DatabaseType.POSTGRESQL, "csharp")
        if findings:
            assert findings[0].pattern_hash != ""
