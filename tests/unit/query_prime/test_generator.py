"""Tests for query_prime.generator — LLM-backed generation with security gate."""

from unittest.mock import MagicMock

import pytest

from startd8.query_prime.generator import (
    _build_system_prompt,
    _build_user_prompt,
    _strip_code_fences,
    generate_query,
)
from startd8.query_prime.models import (
    DatabaseType,
    JoinSpec,
    OperationType,
    ParameterSpec,
    QueryWorkItem,
    SecurityVerdict,
    TransactionBoundary,
)


def _make_work_item(**kwargs):
    defaults = dict(
        id="test-1",
        description="Get user by ID",
        database=DatabaseType.POSTGRESQL,
        operation_type=OperationType.SELECT,
        tables=["users"],
        parameters=[ParameterSpec(name="userId")],
        target_language="csharp",
    )
    defaults.update(kwargs)
    return QueryWorkItem(**defaults)


class TestBuildSystemPrompt:
    def test_includes_security_rules(self):
        wi = _make_work_item()
        prompt = _build_system_prompt(wi)
        assert "parameterized queries" in prompt
        assert "NEVER" in prompt
        assert "string interpolation" in prompt

    def test_includes_database_safe_patterns(self):
        wi = _make_work_item(database=DatabaseType.POSTGRESQL, target_language="csharp")
        prompt = _build_system_prompt(wi)
        assert "NpgsqlParameter" in prompt or "AddWithValue" in prompt

    def test_includes_credential_warning(self):
        wi = _make_work_item(database=DatabaseType.POSTGRESQL, target_language="csharp")
        prompt = _build_system_prompt(wi)
        assert "connectionString" in prompt or "NEVER log" in prompt

    def test_includes_lifecycle_hint(self):
        wi = _make_work_item()
        prompt = _build_system_prompt(wi)
        assert "lifecycle" in prompt.lower() or "dispose" in prompt.lower()

    def test_unknown_database_still_produces_prompt(self):
        wi = _make_work_item(database=DatabaseType.REDIS, target_language="go")
        prompt = _build_system_prompt(wi)
        assert "parameterized queries" in prompt


class TestBuildUserPrompt:
    def test_includes_description(self):
        wi = _make_work_item(description="Fetch active users")
        prompt = _build_user_prompt(wi)
        assert "Fetch active users" in prompt

    def test_includes_tables(self):
        wi = _make_work_item(tables=["users", "orders"])
        prompt = _build_user_prompt(wi)
        assert "users" in prompt
        assert "orders" in prompt

    def test_includes_parameters(self):
        wi = _make_work_item(parameters=[
            ParameterSpec(name="userId", source="user_input"),
        ])
        prompt = _build_user_prompt(wi)
        assert "userId" in prompt

    def test_includes_joins(self):
        wi = _make_work_item(joins=[
            JoinSpec(left_table="users", right_table="orders",
                     join_type="LEFT", on_clause="users.id = orders.user_id"),
        ])
        prompt = _build_user_prompt(wi)
        assert "LEFT JOIN" in prompt

    def test_includes_transaction_boundary(self):
        wi = _make_work_item(
            transaction_boundary=TransactionBoundary.MULTI_STATEMENT,
        )
        prompt = _build_user_prompt(wi)
        assert "multi_statement" in prompt


class TestStripCodeFences:
    def test_strips_fences(self):
        code = "```csharp\npublic void Foo() { }\n```"
        assert _strip_code_fences(code) == "public void Foo() { }"

    def test_no_fences_unchanged(self):
        code = "public void Foo() { }"
        assert _strip_code_fences(code) == code

    def test_empty_string(self):
        assert _strip_code_fences("") == ""


class TestGenerateQuery:
    def test_safe_generation_passes(self):
        """Mock agent returns safe parameterized code."""
        wi = _make_work_item()
        agent = MagicMock()
        # Return safe parameterized code
        safe_code = (
            'await using var cmd = new NpgsqlCommand(\n'
            '    "SELECT * FROM users WHERE userId = @userId", conn);\n'
            'cmd.Parameters.AddWithValue("@userId", userId);\n'
        )
        agent.generate.return_value = MagicMock(
            text=safe_code,
            token_usage={"input_tokens": 100, "output_tokens": 50},
        )

        code, verification, cost = generate_query(wi, agent)
        assert "AddWithValue" in code
        assert verification.verdict != SecurityVerdict.FAIL
        assert cost > 0

    def test_unsafe_generation_fails_verification(self):
        """Mock agent returns unsafe interpolated code."""
        wi = _make_work_item()
        agent = MagicMock()
        # Return unsafe string interpolation
        unsafe_code = (
            'var cmd = new NpgsqlCommand(\n'
            '    $"DELETE FROM users WHERE userId = \'{userId}\'", conn);\n'
        )
        agent.generate.return_value = MagicMock(
            text=unsafe_code,
            token_usage={"input_tokens": 100, "output_tokens": 50},
        )

        code, verification, cost = generate_query(wi, agent)
        assert verification.verdict == SecurityVerdict.FAIL

    def test_strips_markdown_fences(self):
        """Code fences are stripped before verification."""
        wi = _make_work_item()
        agent = MagicMock()
        agent.generate.return_value = MagicMock(
            text="```csharp\npublic void Foo() { }\n```",
            token_usage=None,
        )

        code, _, _ = generate_query(wi, agent)
        assert "```" not in code
