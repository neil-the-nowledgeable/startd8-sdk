"""
Unit tests for CostStore Period Queries (Phase 3)
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path
import tempfile

from startd8.costs.store import CostStore
from startd8.costs.models import CostRecord


class TestPeriodQueries:
    """Test Phase 3: get_total_for_period() functionality"""
    
    @pytest.fixture
    def store(self):
        """Create a temporary cost store"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield CostStore(Path(tmpdir) / "test_costs.db")
    
    def _create_record(self, timestamp, agent_name="test"):
        """Helper to create a CostRecord with given timestamp"""
        return CostRecord(
            agent_name=agent_name,
            model="gpt-4",
            provider="openai",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            input_cost=0.001,
            output_cost=0.0015,
            total_cost=0.0025,
            timestamp=timestamp
        )
    
    def test_hourly_period_query(self, store):
        """Test hourly period boundary parsing and querying"""
        record = self._create_record(
            datetime(2025, 12, 10, 14, 30, 0, tzinfo=timezone.utc)
        )
        store.save(record)
        
        # Query same hour should return the cost
        total = store.get_total_for_period("hourly", "2025-12-10-14")
        assert total == 0.0025
        
        # Query different hour should return 0
        total = store.get_total_for_period("hourly", "2025-12-10-15")
        assert total == 0.0
    
    def test_daily_period_query(self, store):
        """Test daily period boundary parsing and querying"""
        for i in range(3):
            record = self._create_record(
                datetime(2025, 12, 10, 14 + i, 0, 0, tzinfo=timezone.utc),
                agent_name=f"test-{i}"
            )
            store.save(record)
        
        # Query day should sum all 3
        total = store.get_total_for_period("daily", "2025-12-10")
        assert total == 0.0075  # 3 * 0.0025
        
        # Different day should return 0
        total = store.get_total_for_period("daily", "2025-12-11")
        assert total == 0.0
    
    def test_weekly_period_query(self, store):
        """Test ISO week boundary parsing and querying"""
        # Week 50 of 2025: Monday Dec 8 - Sunday Dec 14, 2025
        dates = [
            datetime(2025, 12, 8, 12, 0, 0, tzinfo=timezone.utc),   # Monday
            datetime(2025, 12, 10, 12, 0, 0, tzinfo=timezone.utc),  # Wednesday
            datetime(2025, 12, 14, 12, 0, 0, tzinfo=timezone.utc),  # Sunday
        ]
        
        for i, date in enumerate(dates):
            record = self._create_record(date, agent_name=f"test-{i}")
            store.save(record)
        
        # Query week 50 should get all 3
        total = store.get_total_for_period("weekly", "2025-W50")
        assert total == 0.0075  # 3 * 0.0025
        
        # Query week 49 should get none
        total = store.get_total_for_period("weekly", "2025-W49")
        assert total == 0.0
    
    def test_monthly_period_query(self, store):
        """Test monthly boundary parsing and querying"""
        dates = [
            datetime(2025, 12, 1, 12, 0, 0, tzinfo=timezone.utc),
            datetime(2025, 12, 15, 12, 0, 0, tzinfo=timezone.utc),
            datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
        ]
        
        for i, date in enumerate(dates):
            record = self._create_record(date, agent_name=f"test-{i}")
            store.save(record)
        
        # Query December should get all 3
        total = store.get_total_for_period("monthly", "2025-12")
        assert total == 0.0075  # 3 * 0.0025
        
        # Query November should get none
        total = store.get_total_for_period("monthly", "2025-11")
        assert total == 0.0
    
    def test_total_period_query(self, store):
        """Test all-time total across all periods"""
        dates = [
            datetime(2025, 11, 1, 12, 0, 0, tzinfo=timezone.utc),
            datetime(2025, 12, 1, 12, 0, 0, tzinfo=timezone.utc),
            datetime(2025, 12, 10, 12, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        ]
        
        for i, date in enumerate(dates):
            record = self._create_record(date, agent_name=f"test-{i}")
            store.save(record)
        
        # Query total should get all 4
        total = store.get_total_for_period("total", "total")
        assert total == 0.01  # 4 * 0.0025
    
    def test_empty_period_returns_zero(self, store):
        """Test that querying empty periods returns 0.0"""
        record = self._create_record(
            datetime(2025, 12, 10, 12, 0, 0, tzinfo=timezone.utc)
        )
        store.save(record)
        
        # Query different periods should return 0
        assert store.get_total_for_period("hourly", "2025-12-10-14") == 0.0
        assert store.get_total_for_period("daily", "2025-12-11") == 0.0
        assert store.get_total_for_period("monthly", "2025-11") == 0.0
    
    def test_invalid_period_key_returns_zero(self, store):
        """Test that invalid period keys are handled gracefully"""
        # Invalid hourly key
        total = store.get_total_for_period("hourly", "invalid")
        assert total == 0.0
        
        # Invalid weekly key
        total = store.get_total_for_period("weekly", "invalid")
        assert total == 0.0


class TestTagNormalization:
    """Test Phase 4: Tag Normalization with SQL JOINs"""
    
    @pytest.fixture
    def store(self):
        """Create a temporary cost store"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield CostStore(Path(tmpdir) / "test_costs.db")
    
    def _create_record(self, agent_name="test", tags=None):
        """Helper to create a CostRecord with given tags"""
        if tags is None:
            tags = []
        return CostRecord(
            agent_name=agent_name,
            model="gpt-4",
            provider="openai",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            input_cost=0.001,
            output_cost=0.0015,
            total_cost=0.0025,
            tags=tags,
            timestamp=datetime(2025, 12, 10, 12, 0, 0, tzinfo=timezone.utc)
        )
    
    def test_migration_creates_tags_table(self, store):
        """Verify cost_record_tags table exists after migration"""
        migrated = store.migrate_tags_to_normalized_table()
        assert migrated == 0  # Empty store
    
    def test_migration_transfers_tags(self, store):
        """Verify tags are transferred from JSON to normalized table"""
        # Create record with tags
        record = self._create_record(tags=["feature-a", "budget-project", "analytics"])
        store.save(record)
        
        # Run migration
        migrated = store.migrate_tags_to_normalized_table()
        assert migrated == 3  # 3 tags inserted
    
    def test_migration_is_idempotent(self, store):
        """Verify migration can be run multiple times safely"""
        # Create record (tags saved to both JSON and normalized table by save())
        record = self._create_record(tags=["tag-1", "tag-2"])
        store.save(record)
        
        # First migration: finds tags in JSON column and inserts to normalized table
        count1 = store.migrate_tags_to_normalized_table()
        assert count1 == 2  # Two tags migrated
        
        # Second migration: INSERT OR IGNORE prevents duplicates, counts 2 (attempted but ignored)
        count2 = store.migrate_tags_to_normalized_table()
        assert count2 == 2  # Same 2 tags attempted (but ignored as duplicates)
        
        # The key is that the second run doesn't error - idempotency means no error on re-run
        # Even though it attempts to insert again, INSERT OR IGNORE prevents errors
    
    def test_save_inserts_tags_to_normalized_table(self, store):
        """Verify save() inserts to cost_record_tags"""
        record = self._create_record(tags=["feature-x"])
        store.save(record)
        
        # Query should find the record by tag
        results = store.query(tags=["feature-x"])
        assert len(results) == 1
        assert results[0].id == record.id
    
    def test_query_with_tag_filter_uses_sql(self, store):
        """Verify query() uses SQL JOINs for tag filtering"""
        # Create 3 records: 1 with tag-a, 1 with tag-b, 1 with both
        for i, tags in enumerate([["tag-a"], ["tag-b"], ["tag-a", "tag-b"]]):
            record = self._create_record(agent_name=f"test-{i}", tags=tags)
            store.save(record)
        
        # Query for tag-a should get records 0 and 2
        results = store.query(tags=["tag-a"])
        assert len(results) == 2
        
        # Query for tag-b should get records 1 and 2
        results = store.query(tags=["tag-b"])
        assert len(results) == 2
        
        # Query for both tags (OR logic) should get all 3
        results = store.query(tags=["tag-a", "tag-b"])
        assert len(results) == 3
    
    def test_get_total_with_tag_filter(self, store):
        """Verify get_total() uses SQL JOINs for tag filtering"""
        # Create records with different tags and costs
        costs = [0.0025, 0.005, 0.0075]
        for i, (tags, cost) in enumerate(zip([["expensive"], ["cheap"], ["expensive", "cheap"]], costs)):
            record = self._create_record(agent_name=f"test-{i}", tags=tags)
            record.total_cost = cost
            store.save(record)
        
        # Get total for "expensive" tag
        total = store.get_total(tags=["expensive"])
        assert total == pytest.approx(0.0025 + 0.0075)  # Records 0 and 2
    
    def test_tag_deduplication(self, store):
        """Verify duplicate tags are not stored"""
        record = self._create_record(tags=["tag-1", "tag-1", "tag-1"])  # Duplicates
        store.save(record)
        
        # Query should find the record once
        results = store.query(tags=["tag-1"])
        assert len(results) == 1
    
    def test_query_with_multiple_filters_and_tags(self, store):
        """Verify tag filtering works with other filters"""
        # Create records across different projects and times
        import time
        
        records_data = [
            ("project-a", ["tag-x"]),
            ("project-b", ["tag-y"]),
            ("project-a", ["tag-x", "tag-y"]),
        ]
        
        for i, (project, tags) in enumerate(records_data):
            record = self._create_record(agent_name=f"test-{i}", tags=tags)
            record.project = project
            store.save(record)
        
        # Query for tag-x in project-a should get records 0 and 2
        results = store.query(project="project-a", tags=["tag-x"])
        assert len(results) == 2
        
        # Query for tag-y in project-b should get record 1 only
        results = store.query(project="project-b", tags=["tag-y"])
        assert len(results) == 1
    
    def test_limit_works_with_tag_filtering(self, store):
        """Verify LIMIT works correctly with tag filtering"""
        # Create 10 records all with the same tag
        for i in range(10):
            record = self._create_record(agent_name=f"test-{i}", tags=["popular"])
            store.save(record)
        
        # Query with LIMIT should return only 5
        results = store.query(tags=["popular"], limit=5)
        assert len(results) == 5
    
    def test_performance_acceptable(self, store):
        """Verify tag queries complete quickly"""
        import time
        
        # Create 100 records with various tags
        for i in range(100):
            record = self._create_record(agent_name=f"test-{i}", tags=[f"tag-{i % 10}"])
            store.save(record)
        
        # Query with tag filter should be fast
        start = time.time()
        results = store.query(tags=["tag-0"])
        elapsed = (time.time() - start) * 1000  # Convert to ms
        
        assert len(results) == 10
        assert elapsed < 100  # Should complete in under 100ms
