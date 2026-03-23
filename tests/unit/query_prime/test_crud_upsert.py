"""Tests for PostgreSQL UPSERT template (REQ-QPI-003)."""

import pytest

from startd8.query_prime.models import DatabaseType, OperationType, QueryWorkItem
from startd8.query_prime.templates import generate, is_trivial


def _make_upsert_work_item() -> QueryWorkItem:
    from startd8.query_prime.models import ParameterSpec
    return QueryWorkItem(
        id="qp-test-001",
        description="Upsert cart item",
        database=DatabaseType.POSTGRESQL,
        operation_type=OperationType.UPSERT,
        tables=["cart_items"],
        parameters=[
            ParameterSpec(name="userId", param_type="string", source="input"),
            ParameterSpec(name="productId", param_type="string", source="input"),
            ParameterSpec(name="quantity", param_type="int", source="input"),
        ],
        target_language="csharp",
        target_framework="npgsql",
    )


class TestPgUpsertCsharpTemplate:
    """REQ-QPI-003: PostgreSQL UPSERT template for C#."""

    def test_template_registered(self):
        """UPSERT template exists in the registry."""
        wi = _make_upsert_work_item()
        assert is_trivial(wi) is True

    def test_generate_returns_code(self):
        wi = _make_upsert_work_item()
        code = generate(wi)
        assert code is not None
        assert len(code) > 50

    def test_contains_parameterized_queries(self):
        wi = _make_upsert_work_item()
        code = generate(wi)
        assert "AddWithValue" in code
        assert "@userId" in code
        assert "@productId" in code
        assert "@quantity" in code

    def test_no_string_interpolation(self):
        wi = _make_upsert_work_item()
        code = generate(wi)
        assert '$"' not in code
        assert "'{" not in code

    def test_contains_on_conflict(self):
        wi = _make_upsert_work_item()
        code = generate(wi)
        assert "ON CONFLICT" in code
        assert "DO UPDATE SET" in code

    def test_contains_insert_into(self):
        wi = _make_upsert_work_item()
        code = generate(wi)
        assert "INSERT INTO" in code

    def test_method_name_contains_upsert(self):
        wi = _make_upsert_work_item()
        code = generate(wi)
        assert "Upsert" in code

    def test_uses_await_using(self):
        wi = _make_upsert_work_item()
        code = generate(wi)
        assert "await using" in code
