# Phase 4: Tag Normalization (Issue #4)

**Status:** 🔵 READY FOR IMPLEMENTATION  
**Start Date:** December 10, 2025  
**Estimated Effort:** 3 days  
**Complexity:** Medium - requires schema change + data migration  
**Dependencies:** None (can run in parallel with earlier phases)

---

## 🎯 What Phase 4 Addresses

### Problem Statement

Currently, tags are stored as JSON strings in the `cost_records.tags` column:
```json
tags: ["feature-a", "budget-project", "analytics"]
```

This creates inefficiencies:
- ❌ Tag queries require Python-side filtering (slow on large datasets)
- ❌ Cannot use `LIMIT` effectively with tag filtering
- ❌ `EXPLAIN` queries show full table scans
- ❌ Performance degrades with dataset size
- ❌ Tag normalization/deduplication not enforced

### Solution Overview

Create a normalized `cost_record_tags` junction table:

```sql
-- New table: cost_record_tags
CREATE TABLE cost_record_tags (
    cost_record_id TEXT,         -- FK to cost_records.id
    tag TEXT,                    -- The actual tag value
    PRIMARY KEY (cost_record_id, tag),
    FOREIGN KEY (cost_record_id) REFERENCES cost_records(id)
);

-- Indexes for fast lookups
CREATE INDEX idx_tag_search ON cost_record_tags(tag);
CREATE INDEX idx_cost_record ON cost_record_tags(cost_record_id);
```

Benefits:
- ✅ SQL-based tag filtering (fast index lookups)
- ✅ `LIMIT` works correctly
- ✅ Performance acceptable for large datasets (<100ms)
- ✅ Automatic tag deduplication
- ✅ Easier tag aggregations/reports

---

## 📋 Implementation Steps

### Phase 4A: Create New Schema

**File:** `src/startd8/costs/store.py`  
**Method:** `_init_schema()` (in `__init__`)

Add table creation code:

```python
def _init_schema(self):
    """Initialize database schema"""
    with self._get_connection() as conn:
        cursor = conn.cursor()
        
        # Existing tables...
        cursor.execute("""...""")
        
        # NEW: Create cost_record_tags table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cost_record_tags (
                cost_record_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                PRIMARY KEY (cost_record_id, tag),
                FOREIGN KEY (cost_record_id) REFERENCES cost_records(id) ON DELETE CASCADE
            )
        """)
        
        # Create indexes for fast lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_cost_record_tags_tag 
            ON cost_record_tags(tag)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_cost_record_tags_record 
            ON cost_record_tags(cost_record_id)
        """)
        
        conn.commit()
```

**Checklist:**
- [ ] Table created with correct schema
- [ ] Foreign key constraint added
- [ ] ON DELETE CASCADE ensures cleanup
- [ ] Indexes created for both columns
- [ ] Schema change is backward-compatible

---

### Phase 4B: Implement Data Migration

**File:** `src/startd8/costs/store.py`  
**New Method:** `migrate_tags_to_normalized_table()`

```python
def migrate_tags_to_normalized_table(self) -> int:
    """
    Migrate tags from cost_records.tags JSON to cost_record_tags table.
    
    This is an idempotent operation - safe to run multiple times.
    Already-migrated records are skipped.
    
    Returns:
        Number of tag records inserted
    """
    with self._get_connection() as conn:
        cursor = conn.cursor()
        migrated_count = 0
        
        # Get all cost records with tags
        records = cursor.execute(
            "SELECT id, tags FROM cost_records WHERE tags IS NOT NULL AND tags != '[]'"
        ).fetchall()
        
        for record in records:
            record_id = record["id"]
            tags_json = record["tags"]
            
            try:
                tags = json.loads(tags_json) if tags_json else []
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON tags for {record_id}: {tags_json}")
                continue
            
            # Insert each tag (duplicates ignored due to PRIMARY KEY)
            for tag in tags:
                try:
                    cursor.execute(
                        "INSERT OR IGNORE INTO cost_record_tags (cost_record_id, tag) VALUES (?, ?)",
                        (record_id, tag)
                    )
                    migrated_count += 1
                except Exception as e:
                    logger.error(f"Error inserting tag {tag} for {record_id}: {e}")
        
        conn.commit()
        return migrated_count
```

**Key Points:**
- ✅ Idempotent: Uses `INSERT OR IGNORE` to skip duplicates
- ✅ Safe to run multiple times
- ✅ Handles invalid JSON gracefully
- ✅ Returns count for monitoring
- ✅ Logs errors for debugging

**How to Use:**
```python
store = CostStore(Path("~/.startd8/costs.db"))
migrated = store.migrate_tags_to_normalized_table()
logger.info(f"Migrated {migrated} tag entries")
```

**Checklist:**
- [ ] Migration is idempotent
- [ ] Handles JSON parsing errors
- [ ] Returns count for verification
- [ ] Works with existing data
- [ ] Can be called at startup

---

### Phase 4C: Update save() Method

**File:** `src/startd8/costs/store.py`  
**Method:** `save()`

Update to insert tags into both columns:

```python
def save(self, record: CostRecord) -> None:
    """Save a cost record and its tags to normalized table."""
    with self._get_connection() as conn:
        cursor = conn.cursor()
        
        # Save cost record (existing code)
        cursor.execute("""
            INSERT OR REPLACE INTO cost_records (...)
            VALUES (...)
        """, (...))
        
        # NEW: Save tags to normalized table
        # First, clean up old tags for this record
        cursor.execute(
            "DELETE FROM cost_record_tags WHERE cost_record_id = ?",
            (record.id,)
        )
        
        # Then insert new tags
        for tag in record.tags:
            cursor.execute(
                "INSERT INTO cost_record_tags (cost_record_id, tag) VALUES (?, ?)",
                (record.id, tag)
            )
        
        conn.commit()
```

**Checklist:**
- [ ] Tags deleted before insert (ensures clean state)
- [ ] All tags inserted to normalized table
- [ ] Backward compatible with existing code
- [ ] Still stores JSON in cost_records.tags (for compatibility)

---

### Phase 4C: Update query() Method

**File:** `src/startd8/costs/store.py`  
**Method:** `query()`

Update tag filtering to use SQL JOINs:

```python
def query(self, start: datetime = None, end: datetime = None, 
         project: str = None, model: str = None, tags: List[str] = None) -> List[CostRecord]:
    """Query cost records with SQL-based tag filtering."""
    with self._get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Build base query
        query = "SELECT DISTINCT cr.* FROM cost_records cr"
        params = []
        where_clauses = []
        
        # Add JOIN for tag filtering if needed
        if tags:
            query += " JOIN cost_record_tags crt ON cr.id = crt.cost_record_id"
            
            # Filter by tags (using JOIN)
            placeholders = ",".join("?" * len(tags))
            where_clauses.append(f"crt.tag IN ({placeholders})")
            params.extend(tags)
        
        # Add other filters
        if start:
            where_clauses.append("cr.timestamp >= ?")
            params.append(start.isoformat())
        
        if end:
            where_clauses.append("cr.timestamp < ?")
            params.append(end.isoformat())
        
        if project:
            where_clauses.append("cr.project = ?")
            params.append(project)
        
        if model:
            where_clauses.append("cr.model = ?")
            params.append(model)
        
        # Build final query
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        
        query += " ORDER BY cr.timestamp DESC"
        
        # Execute and return
        records = []
        for row in cursor.execute(query, params).fetchall():
            records.append(CostRecord(**dict(row)))
        
        return records
```

**Checklist:**
- [ ] SQL JOIN replaces Python filtering
- [ ] Tag queries are now O(log n) instead of O(n)
- [ ] All other filters still work
- [ ] LIMIT can now be applied effectively
- [ ] `EXPLAIN` shows index usage

---

### Phase 4C: Update get_total() Method

**File:** `src/startd8/costs/store.py`  
**Method:** `get_total()`

Update to use SQL JOINs for tag filtering:

```python
def get_total(self, start: datetime = None, end: datetime = None,
             project: str = None, model: str = None, tags: List[str] = None) -> float:
    """Get total cost with SQL-based filtering."""
    with self._get_connection() as conn:
        cursor = conn.cursor()
        
        # Build base query
        query = "SELECT COALESCE(SUM(cr.total_cost), 0.0) as total FROM cost_records cr"
        params = []
        where_clauses = []
        
        # Add JOIN for tag filtering if needed
        if tags:
            query += " JOIN cost_record_tags crt ON cr.id = crt.cost_record_id"
            placeholders = ",".join("?" * len(tags))
            where_clauses.append(f"crt.tag IN ({placeholders})")
            params.extend(tags)
        
        # Add other filters (same as before)
        if start:
            where_clauses.append("cr.timestamp >= ?")
            params.append(start.isoformat())
        
        if end:
            where_clauses.append("cr.timestamp < ?")
            params.append(end.isoformat())
        
        if project:
            where_clauses.append("cr.project = ?")
            params.append(project)
        
        if model:
            where_clauses.append("cr.model = ?")
            params.append(model)
        
        # Build final query
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        
        result = cursor.execute(query, params).fetchone()
        return float(result["total"]) if result and result["total"] is not None else 0.0
```

**Checklist:**
- [ ] Uses SQL JOIN for tag filtering
- [ ] Returns accurate sums with tag filters
- [ ] Performs well on large datasets
- [ ] All other filters still work

---

## 🧪 Test Plan

### Phase 4 Test Suite

**File:** `tests/costs/test_store.py`  
**New Class:** `TestTagNormalization`

```python
class TestTagNormalization:
    """Test Phase 4: Tag Normalization"""
    
    def test_migration_creates_tags_table(self, store):
        """Verify cost_record_tags table exists after migration"""
        migrated = store.migrate_tags_to_normalized_table()
        assert migrated == 0  # Empty store
    
    def test_migration_transfers_tags(self, store):
        """Verify tags are transferred from JSON to normalized table"""
        # Create record with tags
        record = CostRecord(
            agent_name="test",
            model="gpt-4",
            provider="openai",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            input_cost=0.001,
            output_cost=0.0015,
            total_cost=0.0025,
            tags=["feature-a", "budget-project", "analytics"]
        )
        store.save(record)
        
        # Run migration
        migrated = store.migrate_tags_to_normalized_table()
        assert migrated == 3  # 3 tags inserted
    
    def test_migration_is_idempotent(self, store):
        """Verify migration can be run multiple times safely"""
        record = CostRecord(
            agent_name="test",
            model="gpt-4",
            provider="openai",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            input_cost=0.001,
            output_cost=0.0015,
            total_cost=0.0025,
            tags=["tag-1", "tag-2"]
        )
        store.save(record)
        
        # Run migration twice
        count1 = store.migrate_tags_to_normalized_table()
        count2 = store.migrate_tags_to_normalized_table()
        
        assert count1 == 2
        assert count2 == 0  # No new tags on second run
    
    def test_save_inserts_tags_to_normalized_table(self, store):
        """Verify save() inserts to cost_record_tags"""
        record = CostRecord(
            agent_name="test",
            model="gpt-4",
            provider="openai",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            input_cost=0.001,
            output_cost=0.0015,
            total_cost=0.0025,
            tags=["feature-x"]
        )
        store.save(record)
        
        # Query should find the record by tag
        results = store.query(tags=["feature-x"])
        assert len(results) == 1
        assert results[0].id == record.id
    
    def test_query_with_tag_filter_uses_sql(self, store):
        """Verify query() uses SQL JOINs for tag filtering"""
        # Create 3 records: 1 with tag-a, 1 with tag-b, 1 with both
        for i, tags in enumerate([["tag-a"], ["tag-b"], ["tag-a", "tag-b"]]):
            record = CostRecord(
                agent_name=f"test-{i}",
                model="gpt-4",
                provider="openai",
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
                input_cost=0.001,
                output_cost=0.0015,
                total_cost=0.0025,
                tags=tags
            )
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
        # Create records with different tags
        for i, tags in enumerate([["expensive"], ["cheap"], ["expensive", "cheap"]]):
            record = CostRecord(
                agent_name=f"test-{i}",
                model="gpt-4",
                provider="openai",
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
                input_cost=0.001,
                output_cost=0.0015,
                total_cost=0.0025 * (i + 1)  # Varying costs
            )
            record.tags = tags
            store.save(record)
        
        # Get total for "expensive" tag
        total = store.get_total(tags=["expensive"])
        assert total == pytest.approx(0.0025 + 0.0075)  # Records 0 and 2
    
    def test_tag_deduplication(self, store):
        """Verify duplicate tags are not stored"""
        record = CostRecord(
            agent_name="test",
            model="gpt-4",
            provider="openai",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            input_cost=0.001,
            output_cost=0.0015,
            total_cost=0.0025,
            tags=["tag-1", "tag-1", "tag-1"]  # Duplicates
        )
        store.save(record)
        
        # Query should find the record once
        results = store.query(tags=["tag-1"])
        assert len(results) == 1
    
    def test_performance_acceptable(self, store):
        """Verify tag queries complete in <100ms"""
        import time
        
        # Create 1000 records with various tags
        for i in range(1000):
            record = CostRecord(
                agent_name=f"test-{i}",
                model="gpt-4",
                provider="openai",
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
                input_cost=0.001,
                output_cost=0.0015,
                total_cost=0.0025,
                tags=[f"tag-{i % 10}"]
            )
            store.save(record)
        
        # Query with tag filter should be fast
        start = time.time()
        results = store.query(tags=["tag-0"])
        elapsed = (time.time() - start) * 1000  # Convert to ms
        
        assert elapsed < 100  # Should complete in under 100ms
        assert len(results) == 100
```

**Test Checklist:**
- [ ] Migration creates correct schema
- [ ] Migration transfers tags correctly
- [ ] Migration is idempotent
- [ ] save() inserts to normalized table
- [ ] query() uses SQL JOINs
- [ ] get_total() uses SQL JOINs
- [ ] Duplicate tags are deduplicated
- [ ] Performance acceptable (<100ms)

---

## ✅ Validation Checklist

Before marking Phase 4 complete:

- [ ] `cost_record_tags` table created with correct schema
- [ ] Indexes created on both columns
- [ ] `migrate_tags_to_normalized_table()` is idempotent
- [ ] `save()` updates both columns
- [ ] `query()` uses SQL JOINs for tag filtering
- [ ] `get_total()` uses SQL JOINs for tag filtering
- [ ] All 8+ test cases passing
- [ ] No regressions in Phase 1, 2, 3 tests
- [ ] Performance acceptable (<100ms for tag queries)
- [ ] `EXPLAIN` shows index usage (not full table scan)
- [ ] Code committed and documented
- [ ] Ready for Phase 5 (QA & Documentation)

---

## 📊 Expected Metrics After Phase 4

| Metric | Before | After |
|--------|--------|-------|
| Tag Query Speed | O(n) Python filtering | O(log n) SQL index |
| Large Dataset Query | 2-5 seconds | <100ms |
| Query Type | Full table scan | Index range scan |
| LIMIT Support | Broken | Works correctly |
| Code Complexity | Medium | Medium |
| Database Size | Normal | +~10% (junction table) |

---

## 🚀 What's Next: Phase 5

After Phase 4, proceed to Phase 5 (QA & Documentation):

1. Run full test suite (all phases)
2. Verify performance on real data
3. Check for any edge cases
4. Update documentation
5. Final review and sign-off

---

## 📝 References

- Issue #4: Tag Filtering Efficiency
- Solution: SQL-based normalized table
- Estimated Effort: 3 days
- Complexity: Medium
- Status: Ready for implementation

**Ready to begin Phase 4 implementation!** 🚀

