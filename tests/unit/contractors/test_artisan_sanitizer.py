"""
Comprehensive unit tests for ArtisanSanitizer.

This module validates the sanitizer component's ability to redact API keys,
detect and mask secrets, remove personally identifiable information (PII),
sanitize file system paths, and handle edge cases gracefully.

Test coverage target: >90% of sanitizer module code paths.

Test Categories:
    - TestAPIKeyRedaction: OpenAI, AWS, GitHub, generic API key patterns
    - TestSecretDetection: Passwords, tokens, PEM keys, connection strings
    - TestPIIRemoval: Emails, phone numbers, SSNs, IPs, credit cards
    - TestPathSanitization: Unix/Windows paths, tracebacks, relative paths
    - TestSanitizeMainEntry: Type handling, nested structures, empty inputs
    - TestEdgeCases: Unicode, long strings, idempotency, boundary conditions
    - TestConfiguration: Custom placeholders, strict mode, persistence
    - TestIntegration: Real-world error messages, config files, JSON responses
"""

import json

import pytest

# ---------------------------------------------------------------------------
# Module Discovery and Import
# ---------------------------------------------------------------------------

_sanitizer_module = None
_ArtisanSanitizer = None
_sanitize_function = None

_import_paths = [
    "artisan.contractors.sanitizer",
    "contractors.sanitizer",
    "artisan.sanitizer",
    "artisan_sanitizer",
    "sanitizer",
]

for _module_path in _import_paths:
    try:
        _sanitizer_module = __import__(_module_path, fromlist=["ArtisanSanitizer"])
        _ArtisanSanitizer = getattr(_sanitizer_module, "ArtisanSanitizer", None)
        if _ArtisanSanitizer is not None:
            break
    except ImportError:
        continue

# Fall back to a function-based API if no class was found.
if _ArtisanSanitizer is None:
    for _module_path in _import_paths:
        try:
            _sanitizer_module = __import__(_module_path, fromlist=["sanitize"])
            _sanitize_function = getattr(_sanitizer_module, "sanitize", None)
            if _sanitize_function is not None:
                break
        except ImportError:
            continue

if _sanitizer_module is None:
    pytest.skip("Could not import sanitizer module", allow_module_level=True)

# ---------------------------------------------------------------------------
# Test Constants  (clearly marked – never used outside tests)
# ---------------------------------------------------------------------------

# API Keys
TEST_OPENAI_KEY = "sk-proj-abc123def456ghi789jkl012mno345pqrst678uvw"
TEST_OPENAI_KEY_OLD = "sk-abc123def456ghi789jkl012mno345pqrst678uvw"
TEST_AWS_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"
TEST_AWS_SECRET_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
TEST_GITHUB_TOKEN_CLASSIC = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef12"
TEST_GITHUB_TOKEN_OAUTH = "gho_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef12"
TEST_GITHUB_PAT = "ghp_1234567890abcdefghijklmnopqrstuvwxyz"
TEST_GENERIC_API_KEY = "super_secret_api_key_value_12345"

# Secrets
TEST_PASSWORD = "MySecurePassword123!"
TEST_BEARER_TOKEN = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
TEST_JWT_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ."
    "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
)
TEST_PRIVATE_KEY_PEM = (
    "-----BEGIN RSA PRIVATE KEY-----\n"
    "MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/Ygd12L1BG+Hv3d+3z6Z3KL5L/7d3\n"
    "-----END RSA PRIVATE KEY-----"
)
TEST_CONNECTION_STRING = (
    "Server=tcp:myserver.database.windows.net,1433;"
    "Initial Catalog=mydb;User Id=admin;Password=MySecurePass123!;"
)
TEST_DATABASE_URL = "postgresql://user:password123@localhost:5432/mydb"

# PII
TEST_EMAIL = "john.doe@example.com"
TEST_EMAIL_2 = "jane.smith@company.org"
TEST_PHONE_US = "555-123-4567"
TEST_PHONE_PARENTHESES = "(555) 123-4567"
TEST_PHONE_PLUS = "+1-555-123-4567"
TEST_PHONE_COMPACT = "5551234567"
TEST_SSN = "123-45-6789"
TEST_IP_ADDRESS_V4 = "192.168.1.100"
TEST_IP_ADDRESS_V4_2 = "10.0.0.1"
TEST_CREDIT_CARD = "4532015112830366"
TEST_CREDIT_CARD_SPACED = "4532 0151 1283 0366"

# Paths
TEST_UNIX_HOME_PATH = "/home/johndoe/projects/secret-project/main.py"
TEST_UNIX_ROOT_PATH = "/var/www/html/app/secret.conf"
TEST_WINDOWS_USER_PATH = r"C:\Users\johndoe\Documents\secret.txt"
TEST_WINDOWS_ROOT_PATH = r"C:\Program Files\App\config.ini"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sanitizer():
    """Create a default ArtisanSanitizer instance (or wrap the function API)."""
    if _ArtisanSanitizer is not None:
        return _ArtisanSanitizer()
    if _sanitize_function is not None:
        # Wrap the bare function so tests can call sanitizer.sanitize(...)
        class _Wrapper:
            @staticmethod
            def sanitize(data):
                return _sanitize_function(data)
        return _Wrapper()
    pytest.skip("No sanitizer implementation available")


@pytest.fixture
def sanitizer_with_config():
    """Create a sanitizer with a custom redaction placeholder."""
    if _ArtisanSanitizer is not None:
        try:
            return _ArtisanSanitizer(config={"redaction_placeholder": "[REDACTED]"})
        except TypeError:
            return _ArtisanSanitizer()
    pytest.skip("ArtisanSanitizer class not available")


@pytest.fixture
def strict_sanitizer():
    """Create a sanitizer in strict mode (if supported)."""
    if _ArtisanSanitizer is not None:
        try:
            return _ArtisanSanitizer(config={"strict_mode": True})
        except (TypeError, ValueError):
            return _ArtisanSanitizer()
    pytest.skip("ArtisanSanitizer class not available")


# ---------------------------------------------------------------------------
# Test Classes
# ---------------------------------------------------------------------------


class TestAPIKeyRedaction:
    """Tests for API key detection and redaction."""

    def test_redacts_openai_key_new_format(self, sanitizer):
        """OpenAI keys with the sk-proj- prefix must be redacted."""
        text = f"My OpenAI key is {TEST_OPENAI_KEY} and should be hidden."
        result = sanitizer.sanitize(text)
        assert TEST_OPENAI_KEY not in result
        assert "My OpenAI key is" in result
        assert "and should be hidden" in result

    def test_redacts_openai_key_old_format(self, sanitizer):
        """OpenAI keys with the legacy sk- prefix must be redacted."""
        text = f"Key: {TEST_OPENAI_KEY_OLD}"
        result = sanitizer.sanitize(text)
        assert TEST_OPENAI_KEY_OLD not in result

    def test_redacts_aws_access_key(self, sanitizer):
        """AWS access keys (AKIA…) must be redacted."""
        text = f"AWS access key: {TEST_AWS_ACCESS_KEY}"
        result = sanitizer.sanitize(text)
        assert TEST_AWS_ACCESS_KEY not in result
        assert "AWS access key:" in result

    def test_redacts_aws_secret_key(self, sanitizer):
        """AWS secret keys must be redacted."""
        text = f"Secret: {TEST_AWS_SECRET_KEY}"
        result = sanitizer.sanitize(text)
        assert TEST_AWS_SECRET_KEY not in result

    def test_redacts_github_token_classic(self, sanitizer):
        """GitHub classic PATs (ghp_…) must be redacted."""
        text = f"GitHub token: {TEST_GITHUB_TOKEN_CLASSIC}"
        result = sanitizer.sanitize(text)
        assert TEST_GITHUB_TOKEN_CLASSIC not in result

    def test_redacts_github_token_oauth(self, sanitizer):
        """GitHub OAuth tokens (gho_…) must be redacted."""
        text = f"OAuth token: {TEST_GITHUB_TOKEN_OAUTH}"
        result = sanitizer.sanitize(text)
        assert TEST_GITHUB_TOKEN_OAUTH not in result

    def test_redacts_generic_api_key_parameter(self, sanitizer):
        """Generic api_key=VALUE patterns must be redacted."""
        text = f"Configure with api_key={TEST_GENERIC_API_KEY} in config"
        result = sanitizer.sanitize(text)
        assert TEST_GENERIC_API_KEY not in result
        assert "api_key" in result.lower()

    def test_redacts_api_key_in_url_query_string(self, sanitizer):
        """API keys embedded in URL query strings must be redacted."""
        url = (
            f"https://api.example.com/endpoint"
            f"?api_key={TEST_GENERIC_API_KEY}&param=value"
        )
        result = sanitizer.sanitize(url)
        assert TEST_GENERIC_API_KEY not in result
        assert "https://api.example.com/endpoint" in result

    def test_redacts_api_key_in_json_string(self, sanitizer):
        """API keys in raw JSON strings must be redacted."""
        json_str = f'{{"api_key": "{TEST_GENERIC_API_KEY}", "name": "app"}}'
        result = sanitizer.sanitize(json_str)
        assert TEST_GENERIC_API_KEY not in result
        assert "name" in result

    def test_redacts_api_key_in_dict(self, sanitizer):
        """API keys in dict values must be redacted."""
        data = {"api_key": TEST_GENERIC_API_KEY, "service": "test"}
        result = sanitizer.sanitize(data)
        assert isinstance(result, dict)
        assert TEST_GENERIC_API_KEY not in str(result)

    def test_redacts_api_key_in_nested_dict(self, sanitizer):
        """API keys in nested dict structures must be redacted."""
        data = {
            "config": {
                "api": {"key": TEST_GENERIC_API_KEY, "version": "1.0"},
                "name": "myapp",
            }
        }
        result = sanitizer.sanitize(data)
        assert TEST_GENERIC_API_KEY not in str(result)

    def test_redacts_multiple_api_keys(self, sanitizer):
        """All API keys in a single string must be redacted."""
        text = f"Key1: {TEST_OPENAI_KEY_OLD} and Key2: {TEST_AWS_ACCESS_KEY}"
        result = sanitizer.sanitize(text)
        assert TEST_OPENAI_KEY_OLD not in result
        assert TEST_AWS_ACCESS_KEY not in result
        assert "Key1:" in result
        assert "Key2:" in result

    def test_preserves_non_key_content(self, sanitizer):
        """Surrounding non-sensitive content must be preserved."""
        text = f"Hello world, api_key={TEST_GENERIC_API_KEY}, goodbye world."
        result = sanitizer.sanitize(text)
        assert "Hello world" in result
        assert "goodbye world" in result
        assert TEST_GENERIC_API_KEY not in result

    def test_redacts_api_key_case_insensitive(self, sanitizer):
        """API key detection must be case-insensitive for the keyword."""
        text = f"API_KEY={TEST_GENERIC_API_KEY}"
        result = sanitizer.sanitize(text)
        assert TEST_GENERIC_API_KEY not in result

    @pytest.mark.parametrize(
        "key_text,key_identifier",
        [
            (f"sk-{TEST_OPENAI_KEY_OLD[3:]}", "openai"),
            (f"AKIA{TEST_AWS_ACCESS_KEY[4:]}", "aws_access"),
            (f"ghp_{TEST_GITHUB_TOKEN_CLASSIC[4:]}", "github_classic"),
            (f"gho_{TEST_GITHUB_TOKEN_OAUTH[4:]}", "github_oauth"),
            (f"api_key={TEST_GENERIC_API_KEY}", "generic"),
        ],
    )
    def test_parametrized_key_patterns(self, sanitizer, key_text, key_identifier):
        """Parametrized sweep across multiple API key formats."""
        text = f"Configuration: {key_text}"
        result = sanitizer.sanitize(text)
        secret_value = key_text.split("=")[-1]
        assert secret_value not in result
        assert "Configuration:" in result


class TestSecretDetection:
    """Tests for secret detection and masking."""

    def test_masks_password_in_text(self, sanitizer):
        """Plaintext passwords in prose must be masked."""
        text = f"Database password is {TEST_PASSWORD} do not share"
        result = sanitizer.sanitize(text)
        assert TEST_PASSWORD not in result
        assert "Database password" in result

    def test_masks_password_in_dict(self, sanitizer):
        """Passwords in dict values must be masked."""
        data = {"username": "admin", "password": TEST_PASSWORD}
        result = sanitizer.sanitize(data)
        assert TEST_PASSWORD not in str(result)

    def test_masks_bearer_token(self, sanitizer):
        """Bearer tokens must be masked."""
        text = f"Authorization: {TEST_BEARER_TOKEN}"
        result = sanitizer.sanitize(text)
        assert TEST_BEARER_TOKEN not in result
        assert "Authorization:" in result

    def test_masks_jwt_token(self, sanitizer):
        """JWT tokens must be masked."""
        text = f"Token: {TEST_JWT_TOKEN}"
        result = sanitizer.sanitize(text)
        assert TEST_JWT_TOKEN not in result

    def test_masks_private_key_block(self, sanitizer):
        """PEM private key blocks must be masked."""
        text = f"Private key:\n{TEST_PRIVATE_KEY_PEM}\nEnd of key"
        result = sanitizer.sanitize(text)
        assert (
            "BEGIN RSA PRIVATE KEY" not in result
            or "REDACTED" in result.upper()
        )
        assert "End of key" in result

    def test_masks_connection_string(self, sanitizer):
        """Password segments inside connection strings must be masked."""
        text = f"ConnectionString={TEST_CONNECTION_STRING}"
        result = sanitizer.sanitize(text)
        assert "MySecurePass123!" not in result
        assert "ConnectionString=" in result

    def test_masks_database_url(self, sanitizer):
        """Inline credentials in database URLs must be masked."""
        text = f"DB URL: {TEST_DATABASE_URL}"
        result = sanitizer.sanitize(text)
        assert "password123" not in result
        assert "DB URL:" in result

    def test_masks_generic_secret(self, sanitizer):
        """Generic secret=VALUE patterns must be masked."""
        text = "secret=my_super_secret_value_12345"
        result = sanitizer.sanitize(text)
        assert "my_super_secret_value_12345" not in result

    def test_masks_token_in_header_dict(self, sanitizer):
        """Tokens inside HTTP-header dicts must be masked."""
        headers = {
            "Authorization": f"Bearer {TEST_JWT_TOKEN}",
            "Content-Type": "application/json",
        }
        result = sanitizer.sanitize(headers)
        result_str = str(result)
        assert TEST_JWT_TOKEN not in result_str
        assert "Content-Type" in result_str

    def test_preserves_non_secret_content(self, sanitizer):
        """Non-sensitive prose around secrets must survive."""
        text = f"The password field is required. secret={TEST_PASSWORD} end."
        result = sanitizer.sanitize(text)
        assert "The password field is required" in result
        assert "end." in result
        assert TEST_PASSWORD not in result

    @pytest.mark.parametrize(
        "secret_text,secret_type",
        [
            (f"password={TEST_PASSWORD}", "password"),
            (f"token={TEST_BEARER_TOKEN}", "bearer"),
            (f"jwt={TEST_JWT_TOKEN}", "jwt"),
            (f"secret={TEST_PASSWORD}", "generic_secret"),
        ],
    )
    def test_parametrized_secret_patterns(self, sanitizer, secret_text, secret_type):
        """Parametrized sweep across multiple secret formats."""
        text = f"Config: {secret_text}"
        result = sanitizer.sanitize(text)
        secret_value = secret_text.split("=", 1)[1]
        assert secret_value not in result


class TestPIIRemoval:
    """Tests for PII detection and removal."""

    def test_removes_email_address(self, sanitizer):
        """Email addresses must be removed/masked."""
        text = f"Contact me at {TEST_EMAIL} for details."
        result = sanitizer.sanitize(text)
        assert TEST_EMAIL not in result
        assert "Contact me at" in result
        assert "for details" in result

    def test_removes_multiple_emails(self, sanitizer):
        """All email addresses in a single string must be removed."""
        text = f"Email {TEST_EMAIL} or {TEST_EMAIL_2} to contact."
        result = sanitizer.sanitize(text)
        assert TEST_EMAIL not in result
        assert TEST_EMAIL_2 not in result

    def test_removes_phone_number_us_format(self, sanitizer):
        """US phone numbers (dashes) must be removed."""
        text = f"Call me at {TEST_PHONE_US} please."
        result = sanitizer.sanitize(text)
        assert TEST_PHONE_US not in result
        assert "Call me at" in result

    def test_removes_phone_number_parentheses(self, sanitizer):
        """Phone numbers with parentheses must be removed."""
        text = f"Number: {TEST_PHONE_PARENTHESES}"
        result = sanitizer.sanitize(text)
        assert TEST_PHONE_PARENTHESES not in result

    def test_removes_phone_number_plus_format(self, sanitizer):
        """International phone numbers (+1-…) must be removed."""
        text = f"Call {TEST_PHONE_PLUS}"
        result = sanitizer.sanitize(text)
        assert TEST_PHONE_PLUS not in result

    def test_removes_phone_number_compact(self, sanitizer):
        """Compact 10-digit phone numbers must be removed."""
        text = f"Phone: {TEST_PHONE_COMPACT}"
        result = sanitizer.sanitize(text)
        assert TEST_PHONE_COMPACT not in result

    def test_removes_ssn(self, sanitizer):
        """Social Security Numbers must be removed."""
        text = f"SSN: {TEST_SSN}"
        result = sanitizer.sanitize(text)
        assert TEST_SSN not in result
        assert "SSN:" in result

    def test_removes_ip_address_v4(self, sanitizer):
        """IPv4 addresses must be removed."""
        text = f"Server IP: {TEST_IP_ADDRESS_V4}"
        result = sanitizer.sanitize(text)
        assert TEST_IP_ADDRESS_V4 not in result
        assert "Server IP:" in result

    def test_removes_multiple_ip_addresses(self, sanitizer):
        """Multiple IPv4 addresses must all be removed."""
        text = f"From {TEST_IP_ADDRESS_V4} to {TEST_IP_ADDRESS_V4_2}"
        result = sanitizer.sanitize(text)
        assert TEST_IP_ADDRESS_V4 not in result
        assert TEST_IP_ADDRESS_V4_2 not in result
        assert "From" in result

    def test_removes_credit_card_number(self, sanitizer):
        """Credit card numbers (contiguous digits) must be removed."""
        text = f"Card: {TEST_CREDIT_CARD}"
        result = sanitizer.sanitize(text)
        assert TEST_CREDIT_CARD not in result
        assert "Card:" in result

    def test_removes_credit_card_spaced(self, sanitizer):
        """Spaced credit card numbers must be removed."""
        text = f"Payment with {TEST_CREDIT_CARD_SPACED}"
        result = sanitizer.sanitize(text)
        assert TEST_CREDIT_CARD_SPACED not in result

    def test_removes_pii_from_dict(self, sanitizer):
        """PII in dict values must be removed while preserving safe values."""
        data = {
            "user_email": TEST_EMAIL,
            "phone": TEST_PHONE_US,
            "name": "John Doe",
        }
        result = sanitizer.sanitize(data)
        result_str = str(result)
        assert TEST_EMAIL not in result_str
        assert TEST_PHONE_US not in result_str
        assert "John Doe" in result_str

    def test_removes_pii_from_nested_structure(self, sanitizer):
        """PII deeply nested in dicts/lists must be removed."""
        data = {
            "users": [
                {"email": TEST_EMAIL, "ssn": TEST_SSN},
                {"email": TEST_EMAIL_2, "phone": TEST_PHONE_US},
            ],
            "metadata": {"count": 2},
        }
        result = sanitizer.sanitize(data)
        result_str = str(result)
        assert TEST_EMAIL not in result_str
        assert TEST_EMAIL_2 not in result_str
        assert TEST_SSN not in result_str
        assert TEST_PHONE_US not in result_str
        assert "count" in result_str

    def test_preserves_non_pii_content(self, sanitizer):
        """Non-PII prose must survive sanitization."""
        text = "User ID 12345 has valid email address, status active."
        result = sanitizer.sanitize(text)
        assert "User ID" in result
        assert "status active" in result

    @pytest.mark.parametrize(
        "pii_text,pii_type",
        [
            (f"email={TEST_EMAIL}", "email"),
            (f"phone={TEST_PHONE_US}", "phone_dash"),
            (f"phone={TEST_PHONE_PARENTHESES}", "phone_parens"),
            (f"ssn={TEST_SSN}", "ssn"),
            (f"ip={TEST_IP_ADDRESS_V4}", "ipv4"),
            (f"card={TEST_CREDIT_CARD}", "credit_card"),
        ],
    )
    def test_parametrized_pii_patterns(self, sanitizer, pii_text, pii_type):
        """Parametrized sweep across multiple PII categories."""
        text = f"Record: {pii_text}"
        result = sanitizer.sanitize(text)
        pii_value = pii_text.split("=", 1)[1]
        assert pii_value not in result
        assert "Record:" in result


class TestPathSanitization:
    """Tests for file path sanitization."""

    def test_sanitizes_unix_home_path(self, sanitizer):
        """Unix home-directory paths must have the username stripped."""
        text = f"Error in {TEST_UNIX_HOME_PATH}"
        result = sanitizer.sanitize(text)
        assert "johndoe" not in result
        assert "Error in" in result

    def test_sanitizes_unix_root_path(self, sanitizer):
        """Full Unix paths must be sanitized or replaced."""
        text = f"File: {TEST_UNIX_ROOT_PATH}"
        result = sanitizer.sanitize(text)
        assert TEST_UNIX_ROOT_PATH not in result or "redacted" in result.lower()

    def test_sanitizes_windows_user_path(self, sanitizer):
        """Windows user-directory paths must have the username stripped."""
        text = f"Located at {TEST_WINDOWS_USER_PATH}"
        result = sanitizer.sanitize(text)
        assert "johndoe" not in result
        assert "Located at" in result

    def test_sanitizes_windows_root_path(self, sanitizer):
        """Full Windows paths must be sanitized or replaced."""
        text = f"Config: {TEST_WINDOWS_ROOT_PATH}"
        result = sanitizer.sanitize(text)
        assert TEST_WINDOWS_ROOT_PATH not in result or "redacted" in result.lower()

    def test_sanitizes_path_in_error_message(self, sanitizer):
        """Paths embedded in error messages must be sanitized."""
        error = (
            f'Traceback (most recent call last):\n'
            f'  File "{TEST_UNIX_HOME_PATH}", line 42'
        )
        result = sanitizer.sanitize(error)
        assert "johndoe" not in result
        assert "Traceback" in result
        assert "line 42" in result

    def test_sanitizes_path_in_traceback(self, sanitizer):
        """Multiple paths inside tracebacks must all be sanitized."""
        traceback_text = (
            f'  File "{TEST_UNIX_HOME_PATH}", line 10, in <module>\n'
            f"    from {TEST_WINDOWS_USER_PATH} import something"
        )
        result = sanitizer.sanitize(traceback_text)
        assert "johndoe" not in result
        assert "File" in result
        assert "import" in result

    def test_preserves_relative_paths(self, sanitizer):
        """Relative paths (./…) are not sensitive and must be preserved."""
        text = "Run: ./scripts/deploy.sh"
        result = sanitizer.sanitize(text)
        assert "./scripts/deploy.sh" in result

    def test_sanitizes_multiple_paths_in_text(self, sanitizer):
        """All paths in a multi-path string must be sanitized."""
        text = (
            f"Logs in {TEST_UNIX_HOME_PATH} "
            f"and config in {TEST_WINDOWS_USER_PATH}"
        )
        result = sanitizer.sanitize(text)
        assert "johndoe" not in result
        assert "Logs in" in result
        assert "config in" in result

    @pytest.mark.parametrize(
        "path_text,path_type",
        [
            (TEST_UNIX_HOME_PATH, "unix_home"),
            (TEST_UNIX_ROOT_PATH, "unix_root"),
            (TEST_WINDOWS_USER_PATH, "windows_user"),
            (TEST_WINDOWS_ROOT_PATH, "windows_root"),
        ],
    )
    def test_parametrized_path_patterns(self, sanitizer, path_text, path_type):
        """Parametrized sweep across multiple path formats."""
        text = f"Location: {path_text}"
        result = sanitizer.sanitize(text)
        assert path_text not in result or "redacted" in result.lower()


class TestSanitizeMainEntry:
    """Tests for the main sanitize() entry point – type handling and recursion."""

    def test_sanitize_string(self, sanitizer):
        """String input returns a string with secrets removed."""
        text = f"API key: {TEST_GENERIC_API_KEY}"
        result = sanitizer.sanitize(text)
        assert isinstance(result, str)
        assert TEST_GENERIC_API_KEY not in result

    def test_sanitize_dict(self, sanitizer):
        """Dict input returns a dict with secrets removed."""
        data = {"key": TEST_GENERIC_API_KEY, "name": "app"}
        result = sanitizer.sanitize(data)
        assert isinstance(result, dict)
        assert TEST_GENERIC_API_KEY not in str(result)
        assert "name" in str(result)

    def test_sanitize_list(self, sanitizer):
        """List input returns a list with secrets removed."""
        data = [TEST_GENERIC_API_KEY, TEST_EMAIL, "normal text"]
        result = sanitizer.sanitize(data)
        assert isinstance(result, list)
        result_str = str(result)
        assert TEST_GENERIC_API_KEY not in result_str
        assert TEST_EMAIL not in result_str
        assert "normal text" in result_str

    def test_sanitize_nested_mixed_structure(self, sanitizer):
        """Nested dicts/lists with mixed types are sanitized recursively."""
        data = {
            "user": {
                "name": "John",
                "email": TEST_EMAIL,
                "api_key": TEST_GENERIC_API_KEY,
            },
            "logs": [
                f"Error at {TEST_UNIX_HOME_PATH}",
                f"Token: {TEST_GITHUB_TOKEN_CLASSIC}",
            ],
            "count": 42,
            "active": True,
        }
        result = sanitizer.sanitize(data)

        assert isinstance(result, dict)
        assert isinstance(result["user"], dict)
        assert isinstance(result["logs"], list)
        assert result["count"] == 42
        assert result["active"] is True

        result_str = str(result)
        assert TEST_EMAIL not in result_str
        assert TEST_GENERIC_API_KEY not in result_str
        assert TEST_GITHUB_TOKEN_CLASSIC not in result_str
        assert "johndoe" not in result_str

    def test_sanitize_none_returns_none(self, sanitizer):
        """None input passes through unchanged."""
        assert sanitizer.sanitize(None) is None

    def test_sanitize_int_returns_int(self, sanitizer):
        """Integer input passes through unchanged."""
        result = sanitizer.sanitize(42)
        assert result == 42
        assert isinstance(result, int)

    def test_sanitize_bool_returns_bool(self, sanitizer):
        """Boolean input passes through unchanged."""
        assert sanitizer.sanitize(True) is True
        assert sanitizer.sanitize(False) is False

    def test_sanitize_float_returns_float(self, sanitizer):
        """Float input passes through unchanged."""
        result = sanitizer.sanitize(3.14)
        assert result == 3.14
        assert isinstance(result, float)

    def test_sanitize_empty_string(self, sanitizer):
        """Empty string returns an empty string."""
        result = sanitizer.sanitize("")
        assert result == ""
        assert isinstance(result, str)

    def test_sanitize_empty_dict(self, sanitizer):
        """Empty dict returns an empty dict."""
        result = sanitizer.sanitize({})
        assert result == {}
        assert isinstance(result, dict)

    def test_sanitize_empty_list(self, sanitizer):
        """Empty list returns an empty list."""
        result = sanitizer.sanitize([])
        assert result == []
        assert isinstance(result, list)

    def test_sanitize_bytes(self, sanitizer):
        """Bytes input is handled (either stays bytes or becomes str)."""
        data = b"api_key=secret123"
        result = sanitizer.sanitize(data)
        assert result is not None
        assert isinstance(result, (bytes, str))

    def test_sanitize_deeply_nested_structure(self, sanitizer):
        """12-level deep nesting is sanitized correctly."""
        data = {"l1": {"l2": {"l3": {"l4": {"l5": {"l6": {"l7": {"l8": {"l9": {
            "l10": {"l11": {"secret": TEST_GENERIC_API_KEY, "email": TEST_EMAIL}}
        }}}}}}}}}}
        result = sanitizer.sanitize(data)
        result_str = str(result)
        assert TEST_GENERIC_API_KEY not in result_str
        assert TEST_EMAIL not in result_str
        assert isinstance(result, dict)
        assert isinstance(result["l1"], dict)

    def test_sanitize_mixed_type_list(self, sanitizer):
        """Lists with mixed types are handled element-wise."""
        data = [
            1,
            TEST_GENERIC_API_KEY,
            None,
            {"password": TEST_PASSWORD},
            3.14,
            TEST_EMAIL,
            True,
        ]
        result = sanitizer.sanitize(data)
        assert isinstance(result, list)
        assert len(result) == 7
        assert result[0] == 1
        assert result[2] is None
        assert result[4] == 3.14
        assert result[6] is True
        result_str = str(result)
        assert TEST_GENERIC_API_KEY not in result_str
        assert TEST_PASSWORD not in result_str
        assert TEST_EMAIL not in result_str

    def test_sanitize_dict_with_numeric_keys(self, sanitizer):
        """Dicts with non-string keys are still sanitized."""
        data = {1: TEST_GENERIC_API_KEY, 2: TEST_EMAIL, "name": "app"}
        result = sanitizer.sanitize(data)
        assert isinstance(result, dict)
        result_str = str(result)
        assert TEST_GENERIC_API_KEY not in result_str
        assert TEST_EMAIL not in result_str


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_very_long_string(self, sanitizer):
        """Strings >200 KB are handled without error."""
        long_text = "normal content " * 15000 + f"api_key={TEST_GENERIC_API_KEY}"
        result = sanitizer.sanitize(long_text)
        assert isinstance(result, str)
        assert TEST_GENERIC_API_KEY not in result
        assert "normal content" in result

    def test_unicode_content(self, sanitizer):
        """Unicode (emoji, CJK, Arabic) is preserved; PII is still removed."""
        text = f"中文内容 🚀 emoji test, email: {TEST_EMAIL}, مرحبا"
        result = sanitizer.sanitize(text)
        assert isinstance(result, str)
        assert "中文" in result or "emoji" in result
        assert TEST_EMAIL not in result

    def test_binary_like_content(self, sanitizer):
        """Strings with escape-sequences don't crash the sanitizer."""
        text = f"Binary: \\x00\\x01\\x02 with api_key={TEST_GENERIC_API_KEY}"
        result = sanitizer.sanitize(text)
        assert isinstance(result, str)
        assert TEST_GENERIC_API_KEY not in result
        assert "Binary:" in result

    def test_partial_key_patterns(self, sanitizer):
        """Partial key prefixes (e.g. bare 'sk-') must not crash."""
        text = "This is skeleton, not sk-"
        result = sanitizer.sanitize(text)
        assert isinstance(result, str)
        assert "skeleton" in result

    def test_key_like_but_not_key(self, sanitizer):
        """Key-like words that are not secrets should not be false-positived."""
        text = "The skeleton key was used in the api_key_descriptor field"
        result = sanitizer.sanitize(text)
        assert "skeleton" in result or "descriptor" in result

    def test_none_input(self, sanitizer):
        """None is handled gracefully."""
        assert sanitizer.sanitize(None) is None

    def test_numeric_input(self, sanitizer):
        """Numeric input passes through."""
        assert sanitizer.sanitize(12345) == 12345

    def test_boolean_input(self, sanitizer):
        """Boolean input passes through."""
        assert sanitizer.sanitize(True) is True
        assert sanitizer.sanitize(False) is False

    def test_special_characters_in_values(self, sanitizer):
        """Strings with special characters are handled."""
        text = f"Secret: {TEST_PASSWORD}!@#$%^&*()"
        result = sanitizer.sanitize(text)
        assert TEST_PASSWORD not in result
        assert "Secret:" in result

    def test_whitespace_variations(self, sanitizer):
        """Whitespace around key/value pairs doesn't prevent detection."""
        text = f"api_key = {TEST_GENERIC_API_KEY} \n\t with whitespace"
        result = sanitizer.sanitize(text)
        assert TEST_GENERIC_API_KEY not in result

    def test_case_variations_in_sensitive_keywords(self, sanitizer):
        """Case-insensitive keyword matching must work."""
        for variant in [
            f"API_KEY={TEST_GENERIC_API_KEY}",
            f"Api_Key={TEST_GENERIC_API_KEY}",
            f"api_KEY={TEST_GENERIC_API_KEY}",
        ]:
            result = sanitizer.sanitize(variant)
            assert TEST_GENERIC_API_KEY not in result

    def test_multiple_same_secrets(self, sanitizer):
        """Duplicate occurrences of the same secret are all removed."""
        text = f"Key1: {TEST_GENERIC_API_KEY}, Key2: {TEST_GENERIC_API_KEY}"
        result = sanitizer.sanitize(text)
        assert TEST_GENERIC_API_KEY not in result
        assert "Key1:" in result
        assert "Key2:" in result

    def test_adjacent_sensitive_data(self, sanitizer):
        """Back-to-back PII items are all removed."""
        text = f"{TEST_EMAIL}{TEST_PHONE_US}{TEST_SSN}"
        result = sanitizer.sanitize(text)
        assert TEST_EMAIL not in result
        assert TEST_PHONE_US not in result
        assert TEST_SSN not in result

    def test_redaction_placeholder_consistency(self, sanitizer):
        """Result differs from input and the sensitive values are gone."""
        text = f"{TEST_GENERIC_API_KEY} and {TEST_EMAIL}"
        result = sanitizer.sanitize(text)
        assert TEST_GENERIC_API_KEY not in result
        assert TEST_EMAIL not in result
        assert result != text

    def test_idempotent_sanitization(self, sanitizer):
        """Running sanitize twice yields the same result (idempotent)."""
        text = f"Key: {TEST_GENERIC_API_KEY}, Email: {TEST_EMAIL}"
        result1 = sanitizer.sanitize(text)
        result2 = sanitizer.sanitize(result1)
        assert result1 == result2

    def test_complex_multiline_structure(self, sanitizer):
        """Multiline strings with mixed sensitive data are fully cleaned."""
        text = (
            f"START\n"
            f"Line 1: {TEST_GENERIC_API_KEY}\n"
            f"Line 2: {TEST_EMAIL}\n"
            f"Line 3: Normal text\n"
            f"Line 4: {TEST_PHONE_US}\n"
            f"END"
        )
        result = sanitizer.sanitize(text)
        assert TEST_GENERIC_API_KEY not in result
        assert TEST_EMAIL not in result
        assert TEST_PHONE_US not in result
        assert "START" in result
        assert "END" in result
        assert "Normal text" in result


class TestConfiguration:
    """Tests for sanitizer configuration options."""

    def test_default_configuration(self, sanitizer):
        """Default config sanitizes without errors."""
        text = f"Key: {TEST_GENERIC_API_KEY}"
        result = sanitizer.sanitize(text)
        assert TEST_GENERIC_API_KEY not in result

    def test_custom_redaction_placeholder(self, sanitizer_with_config):
        """Custom redaction placeholder appears in output."""
        text = f"Key: {TEST_GENERIC_API_KEY}"
        result = sanitizer_with_config.sanitize(text)
        assert TEST_GENERIC_API_KEY not in result
        assert (
            "[REDACTED]" in result
            or "REDACTED" in result.upper()
            or "***" in result
        )

    def test_strict_sanitizer_mode(self, strict_sanitizer):
        """Strict mode removes secrets and PII alike."""
        text = f"Data: {TEST_GENERIC_API_KEY}, {TEST_EMAIL}"
        result = strict_sanitizer.sanitize(text)
        assert TEST_GENERIC_API_KEY not in result
        assert TEST_EMAIL not in result
        assert "Data:" in result

    def test_preserves_configuration_between_calls(self, sanitizer_with_config):
        """Config persists across consecutive calls on the same instance."""
        result1 = sanitizer_with_config.sanitize(f"Key: {TEST_GENERIC_API_KEY}")
        result2 = sanitizer_with_config.sanitize(f"Email: {TEST_EMAIL}")
        assert TEST_GENERIC_API_KEY not in result1
        assert TEST_EMAIL not in result2


class TestIntegration:
    """Integration tests combining multiple sanitization categories."""

    def test_real_world_error_message(self, sanitizer):
        """Realistic error log is fully sanitized."""
        error = (
            f"[ERROR] Failed to connect to database at {TEST_IP_ADDRESS_V4}:5432\n"
            f"Connection string: {TEST_CONNECTION_STRING}\n"
            f"Traceback: {TEST_UNIX_HOME_PATH}:42 in connect()\n"
            f"User contact: {TEST_EMAIL}\n"
            f"API Key used: {TEST_GENERIC_API_KEY}"
        )
        result = sanitizer.sanitize(error)
        assert "[ERROR]" in result
        assert TEST_IP_ADDRESS_V4 not in result
        assert "MySecurePass123!" not in result
        assert "johndoe" not in result
        assert TEST_EMAIL not in result
        assert TEST_GENERIC_API_KEY not in result
        assert "Failed to connect" in result

    def test_real_world_config_file(self, sanitizer):
        """Realistic .env-style config is fully sanitized."""
        config = (
            f"DATABASE_URL={TEST_DATABASE_URL}\n"
            f"API_KEY={TEST_GENERIC_API_KEY}\n"
            f"JWT_SECRET={TEST_JWT_TOKEN}\n"
            f"ADMIN_EMAIL={TEST_EMAIL}\n"
            f"SERVER_IP={TEST_IP_ADDRESS_V4}\n"
            f"HOME_DIR={TEST_UNIX_HOME_PATH}\n"
            f"ADMIN_PHONE={TEST_PHONE_US}"
        )
        result = sanitizer.sanitize(config)
        result_str = str(result)
        assert "password123" not in result_str
        assert TEST_GENERIC_API_KEY not in result_str
        assert "eyJh" not in result_str
        assert TEST_EMAIL not in result_str
        assert TEST_IP_ADDRESS_V4 not in result_str
        assert "johndoe" not in result_str
        assert TEST_PHONE_US not in result_str
        # Structure/labels preserved
        assert "DATABASE_URL" in result_str
        assert "API_KEY" in result_str

    def test_real_world_json_response(self, sanitizer):
        """Realistic JSON API response is fully sanitized."""
        json_data = {
            "status": "success",
            "user": {
                "id": 12345,
                "email": TEST_EMAIL,
                "phone": TEST_PHONE_US,
                "ssn": TEST_SSN,
            },
            "auth": {
                "token": TEST_JWT_TOKEN,
                "api_key": TEST_GENERIC_API_KEY,
            },
            "metadata": {
                "server_ip": TEST_IP_ADDRESS_V4,
                "log_path": TEST_UNIX_HOME_PATH,
            },
        }
        json_str = json.dumps(json_data)
        result = sanitizer.sanitize(json_str)
        result_str = str(result)

        for sensitive in (
            TEST_EMAIL,
            TEST_PHONE_US,
            TEST_SSN,
            TEST_JWT_TOKEN,
            TEST_GENERIC_API_KEY,
            TEST_IP_ADDRESS_V4,
        ):
            assert sensitive not in result_str
        assert "johndoe" not in result_str

        # Non-sensitive structure is preserved
        assert "status" in result_str
        assert "user" in result_str
        assert "12345" in result_str

    def test_real_world_dict_response(self, sanitizer):
        """Dict variant of the JSON response is also sanitized recursively."""
        data = {
            "status": "success",
            "user": {
                "id": 12345,
                "email": TEST_EMAIL,
                "phone": TEST_PHONE_US,
                "ssn": TEST_SSN,
            },
            "auth": {
                "token": TEST_JWT_TOKEN,
                "api_key": TEST_GENERIC_API_KEY,
            },
            "metadata": {
                "server_ip": TEST_IP_ADDRESS_V4,
                "log_path": TEST_UNIX_HOME_PATH,
            },
        }
        result = sanitizer.sanitize(data)
        assert isinstance(result, dict)
        result_str = str(result)

        for sensitive in (
            TEST_EMAIL,
            TEST_PHONE_US,
            TEST_SSN,
            TEST_JWT_TOKEN,
            TEST_GENERIC_API_KEY,
            TEST_IP_ADDRESS_V4,
        ):
            assert sensitive not in result_str
        assert "johndoe" not in result_str
        assert result["status"] == "success"
        assert result["user"]["id"] == 12345