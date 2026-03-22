"""Tests for cross-language element pattern surface (Layer 5)."""

import pytest
from unittest.mock import MagicMock

from startd8.micro_prime.engine import MicroPrimeEngine
from startd8.implementation_engine.drafter import _build_cross_language_element_context


class TestCrossLanguageElements:
    """Tests for MicroPrimeEngine cross-language element cache."""

    def test_register_and_query(self):
        """Register Go elements with archetype, then query for same archetype."""
        engine = MagicMock(spec=MicroPrimeEngine)
        engine._cross_language_cache = {
            "grpc_server": [
                {
                    "name": "main",
                    "language": "go",
                    "archetype": "grpc_server",
                    "code_excerpt": "grpc.NewServer()",
                    "file_path": "cmd/server/main.go",
                },
            ]
        }
        engine.get_cross_language_elements = (
            MicroPrimeEngine.get_cross_language_elements.__get__(engine)
        )

        results = engine.get_cross_language_elements(
            "grpc_server", exclude_language="java",
        )
        assert len(results) == 1
        assert results[0]["language"] == "go"

    def test_exclude_same_language(self):
        """Same language elements should not appear."""
        engine = MagicMock(spec=MicroPrimeEngine)
        engine._cross_language_cache = {
            "grpc_server": [
                {
                    "name": "main",
                    "language": "go",
                    "archetype": "grpc_server",
                    "code_excerpt": "grpc.NewServer()",
                    "file_path": "cmd/server/main.go",
                },
            ]
        }
        engine.get_cross_language_elements = (
            MicroPrimeEngine.get_cross_language_elements.__get__(engine)
        )

        results = engine.get_cross_language_elements(
            "grpc_server", exclude_language="go",
        )
        assert len(results) == 0

    def test_no_cross_run_leakage(self):
        """Cache is instance-level, cleared per run."""
        engine = MagicMock(spec=MicroPrimeEngine)
        engine._cross_language_cache = {}
        engine.get_cross_language_elements = (
            MicroPrimeEngine.get_cross_language_elements.__get__(engine)
        )

        results = engine.get_cross_language_elements("grpc_server")
        assert results == []

    def test_no_exclude_returns_all(self):
        """Without exclude_language, all entries are returned."""
        engine = MagicMock(spec=MicroPrimeEngine)
        engine._cross_language_cache = {
            "http_server": [
                {"name": "handler", "language": "go", "archetype": "http_server",
                 "code_excerpt": "http.ListenAndServe()", "file_path": "server.go"},
                {"name": "server", "language": "java", "archetype": "http_server",
                 "code_excerpt": "new HttpServer()", "file_path": "Server.java"},
            ]
        }
        engine.get_cross_language_elements = (
            MicroPrimeEngine.get_cross_language_elements.__get__(engine)
        )

        results = engine.get_cross_language_elements("http_server")
        assert len(results) == 2

    def test_multiple_languages(self):
        """Multiple languages cached, only non-excluded returned."""
        engine = MagicMock(spec=MicroPrimeEngine)
        engine._cross_language_cache = {
            "grpc_server": [
                {"name": "main", "language": "go", "archetype": "grpc_server",
                 "code_excerpt": "grpc.NewServer()", "file_path": "main.go"},
                {"name": "GrpcServer", "language": "java", "archetype": "grpc_server",
                 "code_excerpt": "Server.start()", "file_path": "GrpcServer.java"},
                {"name": "server", "language": "python", "archetype": "grpc_server",
                 "code_excerpt": "grpc.server()", "file_path": "server.py"},
            ]
        }
        engine.get_cross_language_elements = (
            MicroPrimeEngine.get_cross_language_elements.__get__(engine)
        )

        results = engine.get_cross_language_elements(
            "grpc_server", exclude_language="python",
        )
        assert len(results) == 2
        languages = {r["language"] for r in results}
        assert languages == {"go", "java"}


class TestDrafterCrossLanguageSection:
    """Tests for _build_cross_language_element_context in drafter."""

    def test_section_with_elements(self):
        """Cross-language context appears in drafter output."""
        ctx = {
            "cross_language_elements": [
                {
                    "name": "main",
                    "language": "go",
                    "code_excerpt": "grpc.NewServer()",
                },
            ]
        }
        section = _build_cross_language_element_context(ctx)
        assert "Cross-Language Element Reference" in section
        assert "grpc.NewServer()" in section
        assert "main (go)" in section

    def test_empty_context(self):
        """Empty context returns empty string."""
        assert _build_cross_language_element_context({}) == ""

    def test_none_elements(self):
        """None elements returns empty string."""
        assert _build_cross_language_element_context(
            {"cross_language_elements": None}
        ) == ""

    def test_non_list_elements(self):
        """Non-list elements returns empty string."""
        assert _build_cross_language_element_context(
            {"cross_language_elements": "not a list"}
        ) == ""

    def test_limit_to_three(self):
        """Only first 3 elements are shown."""
        elements = [
            {"name": f"elem_{i}", "language": "go", "code_excerpt": f"code_{i}"}
            for i in range(10)
        ]
        ctx = {"cross_language_elements": elements}
        section = _build_cross_language_element_context(ctx)
        assert "elem_0" in section
        assert "elem_2" in section
        assert "elem_3" not in section

    def test_code_excerpt_truncated(self):
        """Code excerpts longer than 500 chars are truncated."""
        long_code = "x" * 1000
        ctx = {
            "cross_language_elements": [
                {"name": "big_func", "language": "go", "code_excerpt": long_code},
            ]
        }
        section = _build_cross_language_element_context(ctx)
        # The code block should contain at most 500 chars of the excerpt
        assert len(long_code[:500]) == 500
        assert "x" * 501 not in section

    def test_element_without_code_skipped(self):
        """Elements without code_excerpt are skipped."""
        ctx = {
            "cross_language_elements": [
                {"name": "no_code", "language": "go", "code_excerpt": ""},
                {"name": "has_code", "language": "java", "code_excerpt": "int x = 1;"},
            ]
        }
        section = _build_cross_language_element_context(ctx)
        assert "no_code" not in section
        assert "has_code" in section
