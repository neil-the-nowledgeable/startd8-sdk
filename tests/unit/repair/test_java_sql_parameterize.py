"""Tests for JavaSqlParameterizeStep (REQ-KZ-JV-402e Phase 3)."""

from pathlib import Path

from startd8.repair.models import RepairContext, RepairStepResult
from startd8.repair.steps.java_sql_parameterize import JavaSqlParameterizeStep


def _run(code: str, filename: str = "UserDao.java") -> RepairStepResult:
    step = JavaSqlParameterizeStep()
    return step(code, RepairContext(), Path(filename))


class TestJavaSqlParameterizeStep:
    def test_string_concat_select(self):
        code = (
            'public class UserDao {\n'
            '    void find(String userId) {\n'
            '        String sql = "SELECT * FROM users WHERE id=" + userId;\n'
            '    }\n'
            '}\n'
        )
        result = _run(code)
        assert result.modified is True
        assert "?" in result.code
        assert "setString" in result.code or "setInt" in result.code
        # The concatenation should be gone
        assert '+ userId' not in result.code

    def test_string_format_select(self):
        code = (
            'public class UserDao {\n'
            '    void find(String name, int age) {\n'
            '        String sql = String.format("SELECT * FROM users WHERE name=%s AND age=%d", name, age);\n'
            '    }\n'
            '}\n'
        )
        result = _run(code)
        assert result.modified is True
        assert "?" in result.code
        assert "%s" not in result.code
        assert "%d" not in result.code

    def test_stringbuilder_append(self):
        code = (
            'public class UserDao {\n'
            '    void delete(String userId) {\n'
            '        String sql = new StringBuilder("DELETE FROM users WHERE id=").append(userId).toString();\n'
            '    }\n'
            '}\n'
        )
        result = _run(code)
        assert result.modified is True
        assert "?" in result.code
        assert "StringBuilder" not in result.code

    def test_no_sql_keyword_skipped(self):
        code = (
            'public class Greeter {\n'
            '    void greet(String name) {\n'
            '        String msg = "Hello " + name;\n'
            '    }\n'
            '}\n'
        )
        result = _run(code)
        assert result.modified is False
        assert result.code == code

    def test_already_parameterized_skipped(self):
        code = (
            'public class UserDao {\n'
            '    void find(String userId) {\n'
            '        PreparedStatement ps = conn.prepareStatement("SELECT * FROM users WHERE id=?");\n'
            '        ps.setString(1, userId);\n'
            '    }\n'
            '}\n'
        )
        result = _run(code)
        assert result.modified is False

    def test_non_java_file_skipped(self):
        code = 'String sql = "SELECT * FROM users WHERE id=" + userId;\n'
        result = _run(code, filename="query.py")
        assert result.modified is False

    def test_insert_concat(self):
        code = (
            'public class UserDao {\n'
            '    void insert(String name, String email) {\n'
            '        String sql = "INSERT INTO users (name, email) VALUES (\'" + name + "\', \'" + email + "\')";\n'
            '    }\n'
            '}\n'
        )
        result = _run(code)
        assert result.modified is True
        assert "?" in result.code

    def test_infer_setter_int_for_id(self):
        """Variables with 'id' in the name should use setInt."""
        code = (
            'public class UserDao {\n'
            '    void find(int userId) {\n'
            '        String sql = "SELECT * FROM users WHERE id=" + userId;\n'
            '    }\n'
            '}\n'
        )
        result = _run(code)
        assert result.modified is True
        assert "setInt" in result.code

    def test_infer_setter_string_for_name(self):
        """Variables with 'name' should use setString."""
        code = (
            'public class UserDao {\n'
            '    void find(String userName) {\n'
            '        String sql = "SELECT * FROM users WHERE name=" + userName;\n'
            '    }\n'
            '}\n'
        )
        result = _run(code)
        assert result.modified is True
        assert "setString" in result.code

    def test_multiple_format_args(self):
        code = (
            'public class UserDao {\n'
            '    void find(String name, String city) {\n'
            '        String sql = String.format("SELECT * FROM users WHERE name=%s AND city=%s", name, city);\n'
            '    }\n'
            '}\n'
        )
        result = _run(code)
        assert result.modified is True
        # Should have two ? placeholders
        sql_line = [l for l in result.code.splitlines() if "?" in l]
        assert len(sql_line) >= 1
        assert result.code.count("?") >= 2
