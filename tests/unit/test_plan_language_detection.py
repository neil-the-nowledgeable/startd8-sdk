"""Tests for REQ-PLI-202: Pre-PARSE language detection from plan text."""

from __future__ import annotations

import pytest

from startd8.workflows.builtin.plan_ingestion_workflow import _detect_plan_language


class TestDetectPlanLanguage:
    """Unit tests for _detect_plan_language()."""

    def test_go_detection(self) -> None:
        """Plan with Go microservices and .go files -> 'go'."""
        text = (
            "This plan implements Go microservices for the shipping service. "
            "Files: src/shippingservice/main.go, src/shippingservice/handler.go. "
            "Uses go.mod for dependency management."
        )
        assert _detect_plan_language(text) == "go"

    def test_java_detection(self) -> None:
        """Spring Boot application with build.gradle -> 'java'."""
        text = (
            "Build a Spring Boot application for order management. "
            "The project uses build.gradle for dependency management. "
            "Main class: src/main/java/com/example/OrderService.java"
        )
        assert _detect_plan_language(text) == "java"

    def test_nodejs_detection(self) -> None:
        """Express.js API with package.json -> 'nodejs'."""
        text = (
            "Create an Express.js API for the frontend service. "
            "Dependencies managed via package.json. "
            "Entry point: src/server.js"
        )
        assert _detect_plan_language(text) == "nodejs"

    def test_csharp_detection(self) -> None:
        """ASP.NET Core with .csproj -> 'csharp'."""
        text = (
            "Implement an ASP.NET Core web API for the catalog service. "
            "Project file: src/CatalogService/CatalogService.csproj. "
            "Uses Entity Framework for data access."
        )
        assert _detect_plan_language(text) == "csharp"

    def test_python_detection(self) -> None:
        """Django application with requirements.txt -> 'python'."""
        text = (
            "Build a Django application for user management. "
            "Dependencies listed in requirements.txt. "
            "Uses pytest for testing. Python 3.11 required."
        )
        assert _detect_plan_language(text) == "python"

    def test_mixed_signals_most_wins(self) -> None:
        """When one language has clearly more signals, it wins."""
        text = (
            "This Go microservices project uses Go modules (go.mod). "
            "Build src/main.go and src/handler.go. "
            "The Go service communicates with a Python utility script."
        )
        result = _detect_plan_language(text)
        assert result == "go"

    def test_no_signals_returns_none(self) -> None:
        """Generic plan text with no language signals -> None."""
        text = (
            "Create a microservice architecture with three components. "
            "Each component handles a specific domain."
        )
        assert _detect_plan_language(text) is None

    def test_file_extension_detection(self) -> None:
        """Plan text containing src/main.go -> 'go'."""
        text = (
            "Implement the service entry point in src/main.go. "
            "Add handlers in src/handlers.go and models in src/models.go."
        )
        assert _detect_plan_language(text) == "go"

    def test_framework_detection(self) -> None:
        """'Spring Boot' without file extensions -> 'java'."""
        text = (
            "Build a Spring Boot microservice with Spring Boot auto-configuration. "
            "Use JPA for persistence and Maven for builds."
        )
        assert _detect_plan_language(text) == "java"

    def test_case_insensitive_golang(self) -> None:
        """'GOLANG' (uppercase) should detect as 'go'."""
        text = (
            "This project uses GOLANG for the backend services. "
            "GOLANG goroutine-based concurrency model is ideal."
        )
        assert _detect_plan_language(text) == "go"

    def test_case_insensitive_nodejs(self) -> None:
        """'node.js' (lowercase) should detect as 'nodejs'."""
        text = (
            "Build the API server with node.js and express. "
            "Use node.js streams for file processing. "
            "Dependencies in package.json."
        )
        assert _detect_plan_language(text) == "nodejs"

    def test_empty_text_returns_none(self) -> None:
        """Empty string -> None."""
        assert _detect_plan_language("") is None

    def test_tied_signals_returns_none(self) -> None:
        """When two languages have equal signal counts -> None."""
        # Carefully craft text with exactly equal signals for two languages.
        # go.mod -> 1 go signal, requirements.txt -> 1 python signal
        text = "The repo has a go.mod and a requirements.txt."
        result = _detect_plan_language(text)
        assert result is None
