"""Tests for query_prime.decomposer — feature decomposition into work items."""

import pytest

from startd8.query_prime.decomposer import (
    decompose_feature,
    detect_database_type,
    detect_language,
    detect_operation_type,
    extract_parameters,
    extract_tables,
)
from startd8.query_prime.models import DatabaseType, OperationType


class TestDetectDatabaseType:
    def test_postgresql(self):
        assert detect_database_type("uses PostgreSQL for storage") == DatabaseType.POSTGRESQL

    def test_alloydb(self):
        assert detect_database_type("AlloyDB cart store") == DatabaseType.POSTGRESQL

    def test_npgsql(self):
        assert detect_database_type("Npgsql connection") == DatabaseType.POSTGRESQL

    def test_spanner(self):
        assert detect_database_type("Cloud Spanner database") == DatabaseType.SPANNER

    def test_redis(self):
        assert detect_database_type("Redis cache layer") == DatabaseType.REDIS

    def test_mysql(self):
        assert detect_database_type("MySQL backend") == DatabaseType.MYSQL

    def test_sqlite(self):
        assert detect_database_type("SQLite local database") == DatabaseType.SQLITE

    def test_no_match(self):
        assert detect_database_type("generic business logic") is None


class TestDetectOperationType:
    def test_select_keywords(self):
        assert detect_operation_type("get user by id") == OperationType.SELECT
        assert detect_operation_type("fetch all orders") == OperationType.SELECT
        assert detect_operation_type("query active items") == OperationType.SELECT

    def test_insert_keywords(self):
        assert detect_operation_type("add item to cart") == OperationType.INSERT
        assert detect_operation_type("create new user") == OperationType.INSERT

    def test_update_keywords(self):
        assert detect_operation_type("update user profile") == OperationType.UPDATE

    def test_delete_keywords(self):
        assert detect_operation_type("delete cart item") == OperationType.DELETE
        assert detect_operation_type("remove expired sessions") == OperationType.DELETE

    def test_health_check(self):
        assert detect_operation_type("health check endpoint") == OperationType.HEALTH_CHECK

    def test_upsert(self):
        assert detect_operation_type("upsert cart contents") == OperationType.UPSERT

    def test_default_select(self):
        assert detect_operation_type("process the data") == OperationType.SELECT


class TestDetectLanguage:
    def test_csharp(self):
        assert detect_language(["src/CartStore.cs"]) == "csharp"

    def test_python(self):
        assert detect_language(["app/store.py"]) == "python"

    def test_nodejs(self):
        assert detect_language(["src/store.js"]) == "nodejs"

    def test_go(self):
        assert detect_language(["pkg/store.go"]) == "go"

    def test_java(self):
        assert detect_language(["src/Store.java"]) == "java"

    def test_default_csharp(self):
        assert detect_language(["unknown.txt"]) == "csharp"


class TestExtractTables:
    def test_from_clause(self):
        tables = extract_tables("SELECT * FROM users WHERE id = 1")
        assert "users" in tables

    def test_insert_into(self):
        tables = extract_tables("INSERT INTO orders VALUES (...)")
        assert "orders" in tables

    def test_join(self):
        tables = extract_tables("SELECT * FROM users JOIN orders ON ...")
        assert "users" in tables
        assert "orders" in tables

    def test_no_tables(self):
        assert extract_tables("no database here") == []

    def test_deduplication(self):
        tables = extract_tables("FROM users JOIN users ON ...")
        assert len(tables) == 1


class TestExtractParameters:
    def test_id_suffix(self):
        params = extract_parameters("filter by userId and orderId")
        names = [p.name for p in params]
        assert "userId" in names
        assert "orderId" in names

    def test_name_suffix(self):
        params = extract_parameters("search by userName")
        assert any(p.name == "userName" for p in params)

    def test_no_params(self):
        assert extract_parameters("no parameters here") == []


class TestDecomposeFeature:
    def test_database_feature_produces_work_items(self):
        items = decompose_feature(
            "cart-store",
            "Implement PostgreSQL cart store: get cart items, add item, delete item",
            ["src/CartStore.cs"],
        )
        assert len(items) >= 1
        assert all(wi.database == DatabaseType.POSTGRESQL for wi in items)
        assert all(wi.target_language == "csharp" for wi in items)

    def test_non_database_feature_produces_empty(self):
        items = decompose_feature(
            "ui-component",
            "Implement the user profile card with avatar",
            ["src/ProfileCard.tsx"],
        )
        assert items == []

    def test_work_item_ids_are_unique(self):
        items = decompose_feature(
            "store",
            "PostgreSQL: select users; insert orders; delete sessions",
            ["src/Store.cs"],
        )
        ids = [wi.id for wi in items]
        assert len(ids) == len(set(ids))

    def test_metadata_database_detection(self):
        items = decompose_feature(
            "cache",
            "Implement cache layer",
            ["src/Cache.cs"],
            metadata={"notes": "Uses Redis for caching"},
        )
        assert len(items) >= 1
        assert items[0].database == DatabaseType.REDIS

    def test_multiple_operations_detected(self):
        items = decompose_feature(
            "crud",
            "MySQL CRUD: select users, insert users, update users, delete users",
            ["src/UserStore.py"],
        )
        assert len(items) >= 3  # Should detect multiple clauses
        ops = {wi.operation_type for wi in items}
        assert len(ops) >= 2  # At least 2 different operations

    def test_health_check_detected(self):
        items = decompose_feature(
            "health",
            "Implement PostgreSQL health check endpoint",
            ["src/Health.cs"],
        )
        assert len(items) >= 1
        assert any(wi.operation_type == OperationType.HEALTH_CHECK for wi in items)
