"""Tests for Category S (security-sensitive) TODO classification."""

import pytest

from startd8.validators.todo_scanner import (
    TodoEntry,
    TodoInventory,
    classify_todo,
)


def _make_entry(
    raw_text: str = "// TODO: implement",
    line: int = 5,
    language: str = "csharp",
    containing_function: str = "DoWork",
) -> TodoEntry:
    return TodoEntry(
        file_path="test.cs",
        line=line,
        language=language,
        raw_text=raw_text,
        category="C",
        context_lines="",
        containing_function=containing_function,
    )


class TestCategorySClassification:
    """Security-sensitive TODO detection."""

    def test_sql_context_marks_security_sensitive(self):
        lines = [
            "public void Delete(string userId)",
            "{",
            "    // Build SQL query",
            "    var sql = \"DELETE FROM users\";",
            "    // TODO: add parameterized query",
            "    cmd.ExecuteNonQuery();",
            "}",
        ]
        entry = _make_entry(line=5)
        result = classify_todo(entry, lines)
        assert result.security_sensitive is True

    def test_database_context_marks_security_sensitive(self):
        lines = [
            "// Database connection handler",
            "public void Connect()",
            "{",
            "    var connection = new NpgsqlConnection();",
            "    // TODO: add connection pooling",
            "}",
        ]
        entry = _make_entry(line=5)
        result = classify_todo(entry, lines)
        assert result.security_sensitive is True

    def test_non_security_context_not_marked(self):
        lines = [
            "public void Process()",
            "{",
            "    var result = Calculate();",
            "    // TODO: add logging",
            "    return result;",
            "}",
        ]
        entry = _make_entry(line=4)
        result = classify_todo(entry, lines)
        assert result.security_sensitive is False

    def test_credential_context_marks_security(self):
        lines = [
            "public void Init()",
            "{",
            "    var password = GetSecret();",
            "    // TODO: rotate credentials",
            "    Connect(password);",
            "}",
        ]
        entry = _make_entry(line=4)
        result = classify_todo(entry, lines)
        assert result.security_sensitive is True


class TestTodoInventorySummary:
    """TodoInventory.compute_summary includes security_todos count."""

    def test_summary_includes_security_todos(self):
        inventory = TodoInventory(entries=[
            TodoEntry(
                file_path="a.cs", line=1, language="csharp",
                raw_text="// TODO", category="C", context_lines="",
                containing_function="F", security_sensitive=True,
            ),
            TodoEntry(
                file_path="b.cs", line=2, language="csharp",
                raw_text="// TODO", category="C", context_lines="",
                containing_function="G", security_sensitive=False,
            ),
        ])
        inventory.compute_summary()
        assert inventory.summary["security_todos"] == 1
        assert inventory.summary["total"] == 2
