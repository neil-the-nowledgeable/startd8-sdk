"""Tests for C# MicroPrime routing — verifies CSHARP_MICROPRIME_ENABLED
flag, _is_non_python_file routing, and deterministic .csproj/.sln/appsettings
generation in prime_adapter.
"""

import json
from pathlib import Path

import pytest


class TestCSharpMicroPrimeRouting:
    """Verify .cs files route through MicroPrime when enabled."""

    def test_csharp_microprime_enabled_is_true(self):
        """CSHARP_MICROPRIME_ENABLED must be True."""
        from startd8.micro_prime.engine import CSHARP_MICROPRIME_ENABLED
        assert CSHARP_MICROPRIME_ENABLED is True

    def test_cs_files_route_through_microprime(self):
        """When enabled, .cs files return False from _is_non_python_file."""
        from startd8.micro_prime.engine import _is_non_python_file
        assert _is_non_python_file("src/cartservice/CartStore.cs") is False

    def test_cs_files_bypass_when_disabled(self):
        """When CSHARP_MICROPRIME_ENABLED=False, .cs files bypass MicroPrime."""
        import startd8.micro_prime.engine as engine_mod
        original = engine_mod.CSHARP_MICROPRIME_ENABLED
        try:
            engine_mod.CSHARP_MICROPRIME_ENABLED = False
            assert engine_mod._is_non_python_file("ICartStore.cs") is True
        finally:
            engine_mod.CSHARP_MICROPRIME_ENABLED = original

    def test_cs_interface_routes_through_microprime(self):
        """Simple interface files like ICartStore.cs should route through."""
        from startd8.micro_prime.engine import _is_non_python_file
        assert _is_non_python_file("src/ICartStore.cs") is False

    def test_python_still_routes_through(self):
        """Python files should not be affected by C# changes."""
        from startd8.micro_prime.engine import _is_non_python_file
        assert _is_non_python_file("main.py") is False


class TestCsprojGeneration:
    """Verify deterministic .csproj generation."""

    def test_csproj_routes_to_deterministic_generation(self):
        """_try_generate_csproj returns XML for .csproj files."""
        from startd8.micro_prime.prime_adapter import MicroPrimeCodeGenerator

        adapter = MicroPrimeCodeGenerator.__new__(MicroPrimeCodeGenerator)
        adapter._output_dir = Path("/tmp/test")

        context = {
            "dependencies": ["Grpc.AspNetCore/2.76.0", "Google.Protobuf"],
            "service_metadata": {
                "target_framework": "net8.0",
                "sdk_type": "Microsoft.NET.Sdk.Web",
            },
        }
        result = adapter._try_generate_csproj(
            "src/cartservice/cartservice.csproj",
            None,
            context,
        )
        assert result is not None
        assert "<Project" in result
        assert "Grpc.AspNetCore" in result
        assert 'Version="2.76.0"' in result
        assert "Google.Protobuf" in result
        assert "net8.0" in result

    def test_csproj_returns_none_for_non_csproj(self):
        """_try_generate_csproj returns None for non-.csproj files."""
        from startd8.micro_prime.prime_adapter import MicroPrimeCodeGenerator

        adapter = MicroPrimeCodeGenerator.__new__(MicroPrimeCodeGenerator)
        result = adapter._try_generate_csproj("main.cs", None, {})
        assert result is None

    def test_csproj_returns_none_for_py_files(self):
        from startd8.micro_prime.prime_adapter import MicroPrimeCodeGenerator

        adapter = MicroPrimeCodeGenerator.__new__(MicroPrimeCodeGenerator)
        result = adapter._try_generate_csproj("setup.py", None, {})
        assert result is None


class TestSlnGeneration:
    """Verify deterministic .sln generation."""

    def test_sln_routes_to_deterministic_generation(self):
        """_try_generate_sln returns sln content when .csproj files are in context."""
        from startd8.micro_prime.prime_adapter import MicroPrimeCodeGenerator

        adapter = MicroPrimeCodeGenerator.__new__(MicroPrimeCodeGenerator)
        adapter._output_dir = Path("/tmp/test")

        context = {
            "all_target_files": [
                "src/cartservice/cartservice.csproj",
                "src/cartservice/CartStore.cs",
            ],
        }
        result = adapter._try_generate_sln(
            "cartservice.sln",
            None,
            context,
        )
        assert result is not None
        assert "Microsoft Visual Studio Solution File" in result
        assert "cartservice" in result

    def test_sln_returns_none_for_non_sln(self):
        from startd8.micro_prime.prime_adapter import MicroPrimeCodeGenerator

        adapter = MicroPrimeCodeGenerator.__new__(MicroPrimeCodeGenerator)
        result = adapter._try_generate_sln("main.cs", None, {})
        assert result is None

    def test_sln_returns_none_without_csproj_targets(self):
        """Without .csproj in context, .sln generation should return None."""
        from startd8.micro_prime.prime_adapter import MicroPrimeCodeGenerator

        adapter = MicroPrimeCodeGenerator.__new__(MicroPrimeCodeGenerator)
        adapter._output_dir = Path("/tmp/test")

        context = {"all_target_files": ["src/main.cs"]}
        result = adapter._try_generate_sln("service.sln", None, context)
        assert result is None


class TestAppsettingsGeneration:
    """Verify deterministic appsettings.json generation."""

    def test_appsettings_generates_valid_json(self):
        """appsettings.json handler produces valid JSON config."""
        from startd8.micro_prime.prime_adapter import MicroPrimeCodeGenerator

        adapter = MicroPrimeCodeGenerator.__new__(MicroPrimeCodeGenerator)
        result = adapter._try_generate_appsettings(
            "src/cartservice/appsettings.json", {},
        )
        assert result is not None
        parsed = json.loads(result)
        assert "Logging" in parsed
        assert parsed["AllowedHosts"] == "*"
        assert parsed["Logging"]["LogLevel"]["Default"] == "Information"

    def test_appsettings_with_redis_context(self):
        """Redis detected in security_contract adds Redis config."""
        from startd8.micro_prime.prime_adapter import MicroPrimeCodeGenerator

        adapter = MicroPrimeCodeGenerator.__new__(MicroPrimeCodeGenerator)
        context = {
            "security_contract": {
                "databases": {
                    "cart-redis": {"type": "Redis"},
                },
            },
        }
        result = adapter._try_generate_appsettings(
            "appsettings.json", context,
        )
        assert result is not None
        parsed = json.loads(result)
        assert "Redis" in parsed
        assert "ConfigurationString" in parsed["Redis"]

    def test_appsettings_returns_none_for_other_files(self):
        from startd8.micro_prime.prime_adapter import MicroPrimeCodeGenerator

        adapter = MicroPrimeCodeGenerator.__new__(MicroPrimeCodeGenerator)
        assert adapter._try_generate_appsettings("config.json", {}) is None
        assert adapter._try_generate_appsettings("main.cs", {}) is None

    def test_appsettings_trailing_newline(self):
        """Generated appsettings.json should end with a newline."""
        from startd8.micro_prime.prime_adapter import MicroPrimeCodeGenerator

        adapter = MicroPrimeCodeGenerator.__new__(MicroPrimeCodeGenerator)
        result = adapter._try_generate_appsettings("appsettings.json", {})
        assert result is not None
        assert result.endswith("\n")
