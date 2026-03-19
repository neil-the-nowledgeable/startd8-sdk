"""Tests for query_prime.security.credentials — credential leakage detection."""

import pytest

from startd8.query_prime.models import SecurityCheckType
from startd8.query_prime.security.credentials import detect_credential_leakage


class TestCredentialLeakage:
    """Credential leakage detection tests."""

    def test_qp_f3_console_writeline(self):
        """QP-F3 golden case: Console.WriteLine(connectionString) -> error."""
        source = '''
public void Connect(string connectionString)
{
    Console.WriteLine(connectionString);
    var conn = new NpgsqlConnection(connectionString);
}
'''
        findings = detect_credential_leakage(source, "csharp")
        assert len(findings) >= 1
        assert findings[0].check_type == SecurityCheckType.CREDENTIAL_LEAKAGE
        assert findings[0].severity == "error"

    def test_python_print_password(self):
        """print(password) is leakage."""
        source = '''
def connect(password):
    print(password)
    return create_connection(password)
'''
        findings = detect_credential_leakage(source, "python")
        assert len(findings) >= 1

    def test_python_logger_connstr(self):
        """logger.info with connection_string is leakage."""
        source = '''
def connect(connection_string):
    logger.info(connection_string)
'''
        findings = detect_credential_leakage(source, "python")
        assert len(findings) >= 1

    def test_safe_logging_no_credentials(self):
        """Logging without credential variables is safe."""
        source = '''
public void Process(string name)
{
    Console.WriteLine($"Processing {name}");
}
'''
        findings = detect_credential_leakage(source, "csharp")
        assert len(findings) == 0

    def test_nodejs_console_log(self):
        """console.log(password) is leakage."""
        source = '''
function connect(password) {
    console.log(password);
}
'''
        findings = detect_credential_leakage(source, "nodejs")
        assert len(findings) >= 1

    def test_comment_line_skipped(self):
        """Comments should not trigger findings."""
        source = '''
// Console.WriteLine(connectionString);
public void Safe() { }
'''
        findings = detect_credential_leakage(source, "csharp")
        assert len(findings) == 0

    def test_unknown_language_returns_empty(self):
        """Unknown language returns no findings."""
        findings = detect_credential_leakage("print(password)", "ruby")
        assert findings == []

    def test_api_key_detected(self):
        """apiKey in logging call is detected."""
        source = '''
public void Init(string apiKey)
{
    Console.WriteLine(apiKey);
}
'''
        findings = detect_credential_leakage(source, "csharp")
        assert len(findings) >= 1
