"""Tests for Query Prime activation gap fixes — REQ-QPA-100 through 401.

Validates:
- Go DB import pattern detection (REQ-QPA-200)
- Trend script field mapping (REQ-QPA-400)
- Security-sensitive auto-tagging (REQ-QPA-300/301)
"""

import json
import importlib.util
import sys
from pathlib import Path
from typing import Optional

import pytest

from startd8.query_prime.decomposer import detect_database_type
from startd8.query_prime.models import DatabaseType


# ---------------------------------------------------------------------------
# REQ-QPA-200: Go database import patterns
# ---------------------------------------------------------------------------

class TestGoDatabaseImportPatterns:
    """detect_database_type matches Go DB imports in source code."""

    def test_go_stdlib_database_sql(self):
        assert detect_database_type('import "database/sql"') == DatabaseType.POSTGRESQL

    def test_go_pgx_pool(self):
        assert detect_database_type('"github.com/jackc/pgx/v5/pgxpool"') == DatabaseType.POSTGRESQL

    def test_go_pgx_driver(self):
        assert detect_database_type('"github.com/jackc/pgx/v5"') == DatabaseType.POSTGRESQL

    def test_go_lib_pq(self):
        assert detect_database_type('"github.com/lib/pq"') == DatabaseType.POSTGRESQL

    def test_go_redis_client(self):
        assert detect_database_type('"github.com/go-redis/redis/v9"') == DatabaseType.REDIS

    def test_go_mysql_driver(self):
        assert detect_database_type('"github.com/go-sql-driver/mysql"') == DatabaseType.MYSQL

    def test_go_sqlite_driver(self):
        assert detect_database_type('"github.com/mattn/go-sqlite3"') == DatabaseType.SQLITE

    def test_go_no_db_imports(self):
        source = '''package main
import (
    "fmt"
    "net/http"
)
'''
        assert detect_database_type(source) is None

    def test_go_alloydb_connector(self):
        """Real-world pattern from online-boutique catalog_loader.go."""
        source = '''import (
    "cloud.google.com/go/alloydbconn"
    "github.com/jackc/pgx/v5/pgxpool"
)'''
        result = detect_database_type(source)
        assert result == DatabaseType.POSTGRESQL

    def test_existing_patterns_still_work(self):
        """Existing patterns are not broken by new additions."""
        assert detect_database_type("npgsql") == DatabaseType.POSTGRESQL
        assert detect_database_type("spanner") == DatabaseType.SPANNER
        assert detect_database_type("redis") == DatabaseType.REDIS
        assert detect_database_type("mysql") == DatabaseType.MYSQL
        assert detect_database_type("sqlite3") == DatabaseType.SQLITE


# ---------------------------------------------------------------------------
# REQ-QPA-300/301: Security-sensitive auto-tagging
# ---------------------------------------------------------------------------

class TestSecuritySensitiveAutoTag:
    """Seed derivation auto-tags features with database keywords."""

    def test_alloydb_description_detected(self):
        from startd8.seeds.derivation import _detect_database_for_enrichment
        assert _detect_database_for_enrichment("Catalog Loader (AlloyDB + Local JSON)") == "postgresql"

    def test_redis_description_detected(self):
        from startd8.seeds.derivation import _detect_database_for_enrichment
        assert _detect_database_for_enrichment("Redis Cache Layer") == "redis"

    def test_spanner_description_detected(self):
        from startd8.seeds.derivation import _detect_database_for_enrichment
        assert _detect_database_for_enrichment("Cloud Spanner integration") == "spanner"

    def test_no_database_in_description(self):
        from startd8.seeds.derivation import _detect_database_for_enrichment
        assert _detect_database_for_enrichment("Frontend Header Template") is None

    def test_security_keywords_credential(self):
        from startd8.seeds.derivation import _has_security_keywords
        assert _has_security_keywords("Manage user credentials") is True

    def test_security_keywords_api_key(self):
        from startd8.seeds.derivation import _has_security_keywords
        assert _has_security_keywords("Handle API key rotation") is True

    def test_security_keywords_connection_pool(self):
        from startd8.seeds.derivation import _has_security_keywords
        assert _has_security_keywords("Configure connection pool settings") is True

    def test_no_security_keywords(self):
        from startd8.seeds.derivation import _has_security_keywords
        assert _has_security_keywords("Frontend Header Template") is False

    def test_case_insensitive(self):
        from startd8.seeds.derivation import _detect_database_for_enrichment
        assert _detect_database_for_enrichment("ALLOYDB Catalog") == "postgresql"
        assert _detect_database_for_enrichment("PostgreSQL store") == "postgresql"


# ---------------------------------------------------------------------------
# REQ-QPA-400: Trend script field mapping
# ---------------------------------------------------------------------------

class TestTrendScriptFieldMapping:
    """_load_runs resolves metrics files from kaizen-index entries."""

    @pytest.fixture
    def trend_module(self):
        """Load the trend script as a module."""
        script_path = Path(__file__).resolve().parents[3] / "scripts" / "run_query_prime_trends.py"
        spec = importlib.util.spec_from_file_location("run_query_prime_trends", str(script_path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_load_runs_with_absolute_metrics_path(self, tmp_path, trend_module):
        """Resolves runs using absolute metrics_path field."""
        # Create a metrics file
        run_dir = tmp_path / "run-001"
        run_dir.mkdir()
        metrics = {"query_security": {"mean_score": 0.95, "pass_rate": 1.0}}
        metrics_path = run_dir / "kaizen-metrics.json"
        metrics_path.write_text(json.dumps(metrics))

        # Create index with absolute metrics_path
        index = {
            "runs": [{
                "run_id": "run-001",
                "run_dir": str(run_dir),
                "metrics_path": str(metrics_path),
            }]
        }
        (tmp_path / "kaizen-index.json").write_text(json.dumps(index))

        runs = trend_module._load_runs(tmp_path)
        assert len(runs) == 1
        assert runs[0]["mean_score"] == 0.95

    def test_load_runs_with_run_dir_fallback(self, tmp_path, trend_module):
        """Falls back to run_dir when metrics_path is absent."""
        run_dir = tmp_path / "run-002" / "plan-ingestion"
        run_dir.mkdir(parents=True)
        metrics = {"query_security": {"mean_score": 0.88, "pass_rate": 0.9}}
        (run_dir / "kaizen-metrics.json").write_text(json.dumps(metrics))

        index = {
            "runs": [{
                "run_id": "run-002",
                "run_dir": str(run_dir),
                # No metrics_path
            }]
        }
        (tmp_path / "kaizen-index.json").write_text(json.dumps(index))

        runs = trend_module._load_runs(tmp_path)
        assert len(runs) == 1

    def test_load_runs_backward_compat_relative_path(self, tmp_path, trend_module):
        """Falls back to relative_path for legacy indexes."""
        rel_dir = tmp_path / "run-003"
        rel_dir.mkdir()
        metrics = {"mean_score": 0.92, "pass_rate": 1.0}
        (rel_dir / "query-security-metrics.json").write_text(json.dumps(metrics))

        index = {
            "runs": [{
                "run_id": "run-003",
                "relative_path": "run-003",
                # No run_dir, no metrics_path
            }]
        }
        (tmp_path / "kaizen-index.json").write_text(json.dumps(index))

        runs = trend_module._load_runs(tmp_path)
        assert len(runs) == 1

    def test_load_runs_skips_missing_files(self, tmp_path, trend_module):
        """Entries with no findable metrics file are skipped."""
        index = {
            "runs": [{
                "run_id": "ghost-run",
                "run_dir": "/nonexistent/path",
                "metrics_path": "/nonexistent/kaizen-metrics.json",
            }]
        }
        (tmp_path / "kaizen-index.json").write_text(json.dumps(index))

        runs = trend_module._load_runs(tmp_path)
        assert len(runs) == 0
