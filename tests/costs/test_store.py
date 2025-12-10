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
        # Week 49 of 2025: Monday Dec 8 - Sunday Dec 14, 2025
        dates = [
            datetime(2025, 12, 8, 12, 0, 0, tzinfo=timezone.utc),   # Monday
            datetime(2025, 12, 10, 12, 0, 0, tzinfo=timezone.utc),  # Wednesday
            datetime(2025, 12, 14, 12, 0, 0, tzinfo=timezone.utc),  # Sunday
        ]
        
        for i, date in enumerate(dates):
            record = self._create_record(date, agent_name=f"test-{i}")
            store.save(record)
        
        # Query week 49 should get all 3
        total = store.get_total_for_period("weekly", "2025-W49")
        assert total == 0.0075  # 3 * 0.0025
        
        # Query week 48 should get none
        total = store.get_total_for_period("weekly", "2025-W48")
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
