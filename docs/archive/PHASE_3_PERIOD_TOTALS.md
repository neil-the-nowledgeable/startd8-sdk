# Phase 3: Running Totals for Period Queries (Issue #2)

**Status:** 🔵 IN PROGRESS  
**Start Date:** December 10, 2025  
**Estimated Effort:** 1 day  
**Dependencies:** None (can be done in parallel with Phase 4)

---

## 🎯 What Phase 3 Addresses

### Problem Statement

The `CostStore.get_total_for_period()` method is a stub that returns `0.0` for all period-based queries except "total". This breaks:

- **Budget enforcement** - Budgets checked against wrong totals on service restart
- **Analytics** - Period-based reports show zero spending
- **Monitoring** - Cannot track hourly/daily/weekly/monthly trends

**Current Behavior:**
```python
# This returns 0.0 for all periods except "total"
total = cost_store.get_total_for_period(period="daily", period_key="2025-12-10")
# Should return actual sum of costs for that day
```

### Solution Overview

Implement full `get_total_for_period()` with:
- ✅ Date/time parsing for all period types
- ✅ SQL queries to compute accurate totals
- ✅ ISO week (YYYY-Www) support
- ✅ Timezone handling
- ✅ Caching integration

---

## 📋 Implementation Steps

### Step 1: Understand Current Period Key Format

The `CostTracker._update_running_totals()` already generates correct period keys:

```python
# From tracker.py line 172-186
period_keys = {
    f"hourly:{date_str}-{hour:02d}",      # e.g., "hourly:2025-12-10-14"
    f"daily:{date_str}",                   # e.g., "daily:2025-12-10"
    f"weekly:{week_key}",                  # e.g., "weekly:2025-W49"
    f"monthly:{date_str[:7]}",             # e.g., "monthly:2025-12"
    "total"
}
```

### Step 2: Implement Period Boundary Parsing

**File:** `src/startd8/costs/store.py`

Add helper function before `get_total_for_period()`:

```python
from datetime import datetime, timedelta
import re

def _parse_period_boundaries(period: str, period_key: str) -> Tuple[datetime, datetime]:
    """
    Parse period key and return (start_time, end_time) boundaries.
    
    Args:
        period: "hourly" | "daily" | "weekly" | "monthly" | "total"
        period_key: The key from _update_running_totals()
        
    Returns:
        Tuple of (start_time, end_time) as UTC datetime objects
        
    Examples:
        "hourly", "2025-12-10-14" → (2025-12-10 14:00:00, 2025-12-10 15:00:00)
        "daily", "2025-12-10" → (2025-12-10 00:00:00, 2025-12-11 00:00:00)
        "weekly", "2025-W49" → (2025-12-08 00:00:00, 2025-12-15 00:00:00)  # Monday to Sunday
        "monthly", "2025-12" → (2025-12-01 00:00:00, 2026-01-01 00:00:00)
        "total", "total" → (1970-01-01, 2099-12-31)  # All-time
    """
    # Implementation details below
```

**Hourly Parsing:**
```python
if period == "hourly":
    # Format: "2025-12-10-14" (YYYY-MM-DD-HH)
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})-(\d{2})", period_key)
    if match:
        year, month, day, hour = map(int, match.groups())
        start = datetime(year, month, day, hour, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(hours=1)
        return start, end
```

**Daily Parsing:**
```python
if period == "daily":
    # Format: "2025-12-10" (YYYY-MM-DD)
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", period_key)
    if match:
        year, month, day = map(int, match.groups())
        start = datetime(year, month, day, 0, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        return start, end
```

**Weekly Parsing (ISO 8601):**
```python
if period == "weekly":
    # Format: "2025-W49" (YYYY-Www, where W49 = week 49)
    # ISO week: Monday = day 1, Sunday = day 7
    match = re.match(r"(\d{4})-W(\d{2})", period_key)
    if match:
        year, week = map(int, match.groups())
        # Find Monday of that ISO week
        jan_4 = datetime(year, 1, 4, tzinfo=timezone.utc)
        week_1_monday = jan_4 - timedelta(days=jan_4.weekday())
        start = week_1_monday + timedelta(weeks=week - 1)
        end = start + timedelta(days=7)
        return start, end
```

**Monthly Parsing:**
```python
if period == "monthly":
    # Format: "2025-12" (YYYY-MM)
    match = re.match(r"(\d{4})-(\d{2})", period_key)
    if match:
        year, month = map(int, match.groups())
        start = datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc)
        # First day of next month
        if month == 12:
            end = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        else:
            end = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        return start, end
```

**Total:**
```python
if period == "total":
    # All-time
    start = datetime(1970, 1, 1, tzinfo=timezone.utc)
    end = datetime(2099, 12, 31, tzinfo=timezone.utc)
    return start, end
```

### Step 3: Implement SQL Query

**File:** `src/startd8/costs/store.py`

Update `get_total_for_period()` method (line 381-399):

```python
def get_total_for_period(self, period: str, period_key: str) -> float:
    """
    Get total cost for a specific period key.
    
    Args:
        period: "hourly" | "daily" | "weekly" | "monthly" | "total"
        period_key: The key (e.g., "2025-12-10-14", "2025-W49", etc.)
        
    Returns:
        Total cost in USD for that period
    """
    # Handle "total" case (already works in current implementation)
    if period == "total":
        try:
            result = self._db.execute(
                "SELECT COALESCE(SUM(total_cost), 0.0) FROM cost_records"
            ).fetchone()
            return float(result[0]) if result else 0.0
        except Exception as e:
            logger.error(f"Error querying total cost: {e}")
            return 0.0
    
    # Parse period boundaries
    try:
        start_time, end_time = self._parse_period_boundaries(period, period_key)
    except Exception as e:
        logger.error(f"Error parsing period {period}:{period_key}: {e}")
        return 0.0
    
    # Query costs within period boundaries
    try:
        result = self._db.execute(
            """
            SELECT COALESCE(SUM(total_cost), 0.0) 
            FROM cost_records 
            WHERE created_at >= ? AND created_at < ?
            """,
            (start_time.isoformat(), end_time.isoformat())
        ).fetchone()
        return float(result[0]) if result else 0.0
    except Exception as e:
        logger.error(f"Error querying period total: {e}")
        return 0.0
```

### Step 4: Add Tests

**File:** `tests/costs/test_store.py`

Add test class for period queries:

```python
class TestPeriodQueries:
    """Test get_total_for_period() functionality"""
    
    def test_hourly_period_query(self, store):
        """Test hourly period boundary parsing"""
        # Create record at specific time
        record = CostRecord(
            agent_name="test",
            model="gpt-4",
            provider="openai",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            input_cost=0.001,
            output_cost=0.0015,
            total_cost=0.0025
        )
        record.created_at = datetime(2025, 12, 10, 14, 30, 0, tzinfo=timezone.utc)
        store.save(record)
        
        # Query same hour
        total = store.get_total_for_period("hourly", "2025-12-10-14")
        assert total == 0.0025
        
        # Query different hour should return 0
        total = store.get_total_for_period("hourly", "2025-12-10-15")
        assert total == 0.0
    
    def test_daily_period_query(self, store):
        """Test daily period boundary parsing"""
        # Create multiple records in same day
        for i in range(3):
            record = CostRecord(
                agent_name=f"test-{i}",
                model="gpt-4",
                provider="openai",
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
                input_cost=0.001,
                output_cost=0.0015,
                total_cost=0.0025
            )
            record.created_at = datetime(
                2025, 12, 10, 14 + i, 0, 0, tzinfo=timezone.utc
            )
            store.save(record)
        
        # Query day should sum all 3
        total = store.get_total_for_period("daily", "2025-12-10")
        assert total == 0.0075  # 3 * 0.0025
    
    def test_weekly_period_query(self, store):
        """Test ISO week boundary parsing"""
        # Create records in week 49 of 2025
        # Week 49: Monday Dec 8 - Sunday Dec 14, 2025
        dates = [
            datetime(2025, 12, 8, tzinfo=timezone.utc),   # Monday
            datetime(2025, 12, 10, tzinfo=timezone.utc),  # Wednesday
            datetime(2025, 12, 14, tzinfo=timezone.utc),  # Sunday
        ]
        
        for i, date in enumerate(dates):
            record = CostRecord(
                agent_name=f"test-{i}",
                model="gpt-4",
                provider="openai",
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
                input_cost=0.001,
                output_cost=0.0015,
                total_cost=0.0025
            )
            record.created_at = date
            store.save(record)
        
        # Query week 49
        total = store.get_total_for_period("weekly", "2025-W49")
        assert total == 0.0075  # 3 * 0.0025
        
        # Query week 48 (before)
        total = store.get_total_for_period("weekly", "2025-W48")
        assert total == 0.0
    
    def test_monthly_period_query(self, store):
        """Test monthly boundary parsing"""
        # Create records on Dec 1, Dec 15, Dec 31
        dates = [
            datetime(2025, 12, 1, tzinfo=timezone.utc),
            datetime(2025, 12, 15, tzinfo=timezone.utc),
            datetime(2025, 12, 31, tzinfo=timezone.utc),
        ]
        
        for i, date in enumerate(dates):
            record = CostRecord(
                agent_name=f"test-{i}",
                model="gpt-4",
                provider="openai",
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
                input_cost=0.001,
                output_cost=0.0015,
                total_cost=0.0025
            )
            record.created_at = date
            store.save(record)
        
        # Query December
        total = store.get_total_for_period("monthly", "2025-12")
        assert total == 0.0075  # 3 * 0.0025
        
        # Query November
        total = store.get_total_for_period("monthly", "2025-11")
        assert total == 0.0
    
    def test_total_period_query(self, store):
        """Test all-time total"""
        records = []
        for i in range(5):
            record = CostRecord(
                agent_name=f"test-{i}",
                model="gpt-4",
                provider="openai",
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
                input_cost=0.001,
                output_cost=0.0015,
                total_cost=0.0025
            )
            record.created_at = datetime(2025, 12, 10, tzinfo=timezone.utc)
            store.save(record)
        
        # Query total
        total = store.get_total_for_period("total", "total")
        assert total == 0.0125  # 5 * 0.0025
```

---

## ✅ Validation Checklist

Before committing Phase 3:

- [ ] All period parsing works correctly
- [ ] SQL queries return accurate totals
- [ ] ISO week parsing handles edge cases (year boundaries)
- [ ] Timezone handling is correct (UTC)
- [ ] All 6+ test cases pass
- [ ] No performance regressions
- [ ] Handles empty periods gracefully (returns 0.0)
- [ ] Handles invalid period_key gracefully
- [ ] Works with CostTracker.get_running_total() cache integration
- [ ] Code committed to git

---

## 🚀 Integration Points

### CostTracker Integration

The `CostTracker` already calls this method in `get_running_total()` (line 188-199):

```python
def get_running_total(self, period: str, period_key: str = None) -> float:
    """
    Get running total for a period.
    
    Checks in-memory cache first, falls back to store query.
    """
    # Check cache first
    if period_key in self._running_totals:
        return self._running_totals[period_key]
    
    # Fall back to store query (this will use our new implementation)
    return self.store.get_total_for_period(period, period_key)
```

Once Phase 3 is complete, this will work correctly for all periods!

---

## 📊 Effort Breakdown

| Task | Effort | Status |
|------|--------|--------|
| Period parsing | 2-3 hrs | Ready |
| SQL query implementation | 1-2 hrs | Ready |
| Test cases | 2-3 hrs | Ready |
| Integration testing | 1 hr | Ready |
| **Total** | **6-9 hrs** | **1 day** |

---

## 🎯 Success Criteria

After Phase 3:

✅ `get_total_for_period()` returns accurate totals for all periods  
✅ All 6+ test cases passing  
✅ Budget enforcement works on service restart  
✅ Period-based analytics work correctly  
✅ No performance regressions  
✅ Code committed and documented  

---

**Ready to begin Phase 3 implementation!** 🚀

Would you like me to start with Step 1-4 implementation?

