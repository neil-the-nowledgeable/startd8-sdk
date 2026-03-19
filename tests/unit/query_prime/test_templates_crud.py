"""Tests for CRUD templates — parameterization correctness."""

import pytest

from startd8.query_prime.models import (
    DatabaseType,
    OperationType,
    ParameterSpec,
    QueryWorkItem,
)
from startd8.query_prime.templates import generate, is_trivial


def _make_crud(
    db: DatabaseType, lang: str, op: OperationType,
    tables: list[str] | None = None,
    params: list[ParameterSpec] | None = None,
) -> QueryWorkItem:
    return QueryWorkItem(
        id=f"crud-{db.value}-{lang}-{op.value}",
        description=f"{op.value} on {db.value}",
        database=db,
        operation_type=op,
        tables=tables or ["users"],
        parameters=params or [ParameterSpec(name="id")],
        target_language=lang,
    )


class TestCrudTemplates:
    """CRUD template parameterization correctness."""

    def test_pg_select_csharp_uses_at_param(self):
        wi = _make_crud(DatabaseType.POSTGRESQL, "csharp", OperationType.SELECT)
        code = generate(wi)
        assert code is not None
        assert "@id" in code
        assert "AddWithValue" in code

    def test_pg_insert_csharp_uses_parameterized(self):
        wi = _make_crud(
            DatabaseType.POSTGRESQL, "csharp", OperationType.INSERT,
            params=[ParameterSpec(name="name"), ParameterSpec(name="email")],
        )
        code = generate(wi)
        assert code is not None
        assert "@name" in code
        assert "@email" in code

    def test_pg_delete_csharp_uses_parameterized(self):
        wi = _make_crud(DatabaseType.POSTGRESQL, "csharp", OperationType.DELETE)
        code = generate(wi)
        assert code is not None
        assert "@id" in code

    def test_pg_select_python_uses_percent_s(self):
        wi = _make_crud(DatabaseType.POSTGRESQL, "python", OperationType.SELECT)
        code = generate(wi)
        assert code is not None
        assert "%s" in code

    def test_pg_select_nodejs_uses_dollar_param(self):
        wi = _make_crud(DatabaseType.POSTGRESQL, "nodejs", OperationType.SELECT)
        code = generate(wi)
        assert code is not None
        assert "$1" in code

    def test_no_string_interpolation_in_any_template(self):
        """No template should use string interpolation for SQL."""
        for db in [DatabaseType.POSTGRESQL]:
            for lang in ["csharp", "python", "nodejs"]:
                for op in [OperationType.SELECT, OperationType.INSERT, OperationType.DELETE]:
                    wi = _make_crud(db, lang, op)
                    if is_trivial(wi):
                        code = generate(wi)
                        # Check for dangerous patterns
                        assert '$"' not in code or '@' in code, (
                            f"String interpolation in {db.value}/{lang}/{op.value}"
                        )
                        assert "f'" not in code
                        assert 'f"' not in code

    def test_nonexistent_template_returns_none(self):
        """Non-registered combo returns None."""
        wi = _make_crud(DatabaseType.REDIS, "csharp", OperationType.SELECT)
        # Redis doesn't have SELECT CRUD templates
        assert not is_trivial(wi) or generate(wi) is None
