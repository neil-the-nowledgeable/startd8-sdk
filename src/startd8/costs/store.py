"""
Storage backend for cost tracking data

Uses SQLite for efficient querying and persistence of:
- Cost records
- Budgets
- Event history (critical events only)
"""

import sqlite3
import json
import re
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager

from .models import CostRecord, Budget, CostSummary, CostPeriod
from ..logging_config import get_logger

logger = get_logger(__name__)


class CostStore:
    """
    SQLite-backed storage for cost tracking data.
    
    Features:
    - Efficient querying with indexes
    - Transaction support
    - Automatic schema migrations
    - Thread-safe operations
    
    Example:
        store = CostStore(Path("~/.startd8/costs.db"))
        
        # Save a cost record
        store.save(cost_record)
        
        # Query records
        records = store.query(
            start=datetime(2025, 12, 1),
            end=datetime(2025, 12, 31),
            project="my-app"
        )
        
        # Get totals
        total = store.get_total(
            start=datetime(2025, 12, 1),
            end=datetime(2025, 12, 31)
        )
    """
    
    SCHEMA_VERSION = 1
    
    def __init__(self, db_path: Path):
        """
        Initialize cost store.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._init_db()
        logger.info(f"Initialized CostStore at {self.db_path}")
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def _init_db(self):
        """Initialize database schema"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Cost records table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cost_records (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    model TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    total_tokens INTEGER NOT NULL,
                    input_cost REAL NOT NULL,
                    output_cost REAL NOT NULL,
                    total_cost REAL NOT NULL,
                    tags TEXT,  -- JSON array
                    project TEXT,
                    prompt_id TEXT,
                    response_id TEXT,
                    pipeline_id TEXT,
                    job_id TEXT,
                    correlation_id TEXT,
                    metadata TEXT  -- JSON object
                )
            """)
            
            # Indexes for efficient querying
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_cost_timestamp 
                ON cost_records(timestamp)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_cost_project 
                ON cost_records(project)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_cost_model 
                ON cost_records(model)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_cost_agent 
                ON cost_records(agent_name)
            """)
            
            # Budgets table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS budgets (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    period TEXT NOT NULL,
                    limit_amount REAL NOT NULL,
                    warning_threshold REAL NOT NULL,
                    block_on_exceed INTEGER NOT NULL,
                    scope_project TEXT,
                    scope_model TEXT,
                    scope_tags TEXT,  -- JSON array
                    is_active INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            
            # Events table (for critical events only)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    data TEXT NOT NULL,  -- JSON object
                    correlation_id TEXT
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_event_timestamp 
                ON events(timestamp)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_event_type 
                ON events(type)
            """)
            
            # Schema version table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
            """)
            
            # Insert or update schema version
            cursor.execute(
                "INSERT OR REPLACE INTO schema_version (version, applied_at) VALUES (?, ?)",
                (self.SCHEMA_VERSION, datetime.now(timezone.utc).isoformat())
            )
            
            conn.commit()
    
    def save(self, record: CostRecord) -> None:
        """
        Save a cost record.
        
        Args:
            record: CostRecord to save
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO cost_records (
                    id, timestamp, agent_name, model, provider,
                    input_tokens, output_tokens, total_tokens,
                    input_cost, output_cost, total_cost,
                    tags, project, prompt_id, response_id,
                    pipeline_id, job_id, correlation_id, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.id,
                record.timestamp.isoformat(),
                record.agent_name,
                record.model,
                record.provider,
                record.input_tokens,
                record.output_tokens,
                record.total_tokens,
                record.input_cost,
                record.output_cost,
                record.total_cost,
                json.dumps(record.tags),
                record.project,
                record.prompt_id,
                record.response_id,
                record.pipeline_id,
                record.job_id,
                record.correlation_id,
                json.dumps(record.metadata)
            ))
            conn.commit()
    
    def query(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        project: Optional[str] = None,
        model: Optional[str] = None,
        agent: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: Optional[int] = None
    ) -> List[CostRecord]:
        """
        Query cost records with filters.
        
        Args:
            start: Start time (inclusive)
            end: End time (exclusive)
            project: Filter by project
            model: Filter by model
            agent: Filter by agent name
            tags: Filter by tags (any match)
            limit: Maximum number of records to return
            
        Returns:
            List of CostRecord objects
        """
        conditions = []
        params = []
        
        if start:
            conditions.append("timestamp >= ?")
            params.append(start.isoformat())
        
        if end:
            conditions.append("timestamp < ?")
            params.append(end.isoformat())
        
        if project:
            conditions.append("project = ?")
            params.append(project)
        
        if model:
            conditions.append("model = ?")
            params.append(model)
        
        if agent:
            conditions.append("agent_name = ?")
            params.append(agent)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        query = f"""
            SELECT * FROM cost_records
            WHERE {where_clause}
            ORDER BY timestamp DESC
        """
        
        if limit:
            query += f" LIMIT {limit}"
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
        
        records = []
        for row in rows:
            record = self._row_to_cost_record(row)
            
            # Filter by tags if specified
            if tags and not any(t in record.tags for t in tags):
                continue
            
            records.append(record)
        
        return records
    
    def _row_to_cost_record(self, row: sqlite3.Row) -> CostRecord:
        """Convert database row to CostRecord"""
        return CostRecord(
            id=row["id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            agent_name=row["agent_name"],
            model=row["model"],
            provider=row["provider"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            total_tokens=row["total_tokens"],
            input_cost=row["input_cost"],
            output_cost=row["output_cost"],
            total_cost=row["total_cost"],
            tags=json.loads(row["tags"]) if row["tags"] else [],
            project=row["project"],
            prompt_id=row["prompt_id"],
            response_id=row["response_id"],
            pipeline_id=row["pipeline_id"],
            job_id=row["job_id"],
            correlation_id=row["correlation_id"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {}
        )
    
    def get_total(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        project: Optional[str] = None,
        model: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> float:
        """
        Get total cost for a time period with filters.
        
        Args:
            start: Start time (inclusive)
            end: End time (exclusive)
            project: Filter by project
            model: Filter by model
            tags: Filter by tags (any match)
            
        Returns:
            Total cost in USD
        """
        conditions = []
        params = []
        
        if start:
            conditions.append("timestamp >= ?")
            params.append(start.isoformat())
        
        if end:
            conditions.append("timestamp < ?")
            params.append(end.isoformat())
        
        if project:
            conditions.append("project = ?")
            params.append(project)
        
        if model:
            conditions.append("model = ?")
            params.append(model)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        query = f"""
            SELECT SUM(total_cost) as total
            FROM cost_records
            WHERE {where_clause}
        """
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            row = cursor.fetchone()
            total = row["total"] if row["total"] is not None else 0.0
        
        # If tags filter is specified, need to fetch records and filter
        if tags:
            records = self.query(start=start, end=end, project=project, model=model, tags=tags)
            total = sum(r.total_cost for r in records)
        
        return total
    
    def _parse_period_boundaries(self, period: str, period_key: str) -> Tuple[datetime, datetime]:
        """
        Parse period key and return (start_time, end_time) boundaries (UTC).
        
        Args:
            period: "hourly" | "daily" | "weekly" | "monthly" | "total"
            period_key: The key from _update_running_totals()
            
        Returns:
            Tuple of (start_time, end_time) as UTC datetime objects
            
        Examples:
            "hourly", "2025-12-10-14" → (2025-12-10 14:00:00 UTC, 2025-12-10 15:00:00 UTC)
            "daily", "2025-12-10" → (2025-12-10 00:00:00 UTC, 2025-12-11 00:00:00 UTC)
            "weekly", "2025-W49" → (2025-12-08 00:00:00 UTC, 2025-12-15 00:00:00 UTC)
            "monthly", "2025-12" → (2025-12-01 00:00:00 UTC, 2026-01-01 00:00:00 UTC)
            "total", "total" → (1970-01-01 UTC, 2099-12-31 UTC)
        """
        try:
            if period == "hourly":
                # Format: "2025-12-10-14" (YYYY-MM-DD-HH)
                match = re.match(r"(\d{4})-(\d{2})-(\d{2})-(\d{2})", period_key)
                if not match:
                    raise ValueError(f"Invalid hourly period_key: {period_key}")
                year, month, day, hour = map(int, match.groups())
                start = datetime(year, month, day, hour, 0, 0, tzinfo=timezone.utc)
                end = start + timedelta(hours=1)
                return start, end
            
            elif period == "daily":
                # Format: "2025-12-10" (YYYY-MM-DD)
                match = re.match(r"(\d{4})-(\d{2})-(\d{2})", period_key)
                if not match:
                    raise ValueError(f"Invalid daily period_key: {period_key}")
                year, month, day = map(int, match.groups())
                start = datetime(year, month, day, 0, 0, 0, tzinfo=timezone.utc)
                end = start + timedelta(days=1)
                return start, end
            
            elif period == "weekly":
                # Format: "2025-W49" (YYYY-Www, ISO 8601)
                # ISO week: Monday = day 0, Sunday = day 6
                match = re.match(r"(\d{4})-W(\d{2})", period_key)
                if not match:
                    raise ValueError(f"Invalid weekly period_key: {period_key}")
                year, week = map(int, match.groups())
                
                # Find Monday of that ISO week
                # Jan 4 is always in week 1, so use it as anchor
                jan_4 = datetime(year, 1, 4, tzinfo=timezone.utc)
                week_1_monday = jan_4 - timedelta(days=jan_4.weekday())
                start = week_1_monday + timedelta(weeks=week - 1)
                end = start + timedelta(days=7)
                return start, end
            
            elif period == "monthly":
                # Format: "2025-12" (YYYY-MM)
                match = re.match(r"(\d{4})-(\d{2})", period_key)
                if not match:
                    raise ValueError(f"Invalid monthly period_key: {period_key}")
                year, month = map(int, match.groups())
                start = datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc)
                
                # First day of next month
                if month == 12:
                    end = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
                else:
                    end = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=timezone.utc)
                return start, end
            
            elif period == "total":
                # All-time range
                start = datetime(1970, 1, 1, tzinfo=timezone.utc)
                end = datetime(2099, 12, 31, tzinfo=timezone.utc)
                return start, end
            
            else:
                raise ValueError(f"Unknown period type: {period}")
        
        except Exception as e:
            logger.error(f"Error parsing period {period}:{period_key}: {e}")
            raise
    
    def get_total_for_period(self, period: str, period_key: str) -> float:
        """
        Get total cost for a specific period key (Issue #2: Period Totals).
        
        Handles all period types: hourly, daily, weekly, monthly, total.
        
        Args:
            period: Period type (hourly, daily, weekly, monthly, total)
            period_key: Period identifier
                - hourly: "2025-12-10-14" (YYYY-MM-DD-HH)
                - daily: "2025-12-10" (YYYY-MM-DD)
                - weekly: "2025-W49" (YYYY-Www, ISO 8601)
                - monthly: "2025-12" (YYYY-MM)
                - total: "total"
            
        Returns:
            Total cost in USD for that period, 0.0 if period has no costs
        """
        try:
            # Parse period boundaries
            start_time, end_time = self._parse_period_boundaries(period, period_key)
            
            # Query costs within period boundaries
            with self._get_connection() as conn:
                cursor = conn.cursor()
                result = cursor.execute(
                    """
                    SELECT COALESCE(SUM(total_cost), 0.0) as total 
                    FROM cost_records 
                    WHERE timestamp >= ? AND timestamp < ?
                    """,
                    (start_time.isoformat(), end_time.isoformat())
                ).fetchone()
                
                total = result["total"] if result and result["total"] is not None else 0.0
                return float(total)
        
        except Exception as e:
            logger.error(f"Error querying period total for {period}:{period_key}: {e}")
            return 0.0
    
    def save_budget(self, budget: Budget) -> None:
        """
        Save a budget.
        
        Args:
            budget: Budget to save
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO budgets (
                    id, name, period, limit_amount, warning_threshold,
                    block_on_exceed, scope_project, scope_model, scope_tags,
                    is_active, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                budget.id,
                budget.name,
                budget.period.value,
                budget.limit_amount,
                budget.warning_threshold,
                1 if budget.block_on_exceed else 0,
                budget.scope_project,
                budget.scope_model,
                json.dumps(budget.scope_tags),
                1 if budget.is_active else 0,
                budget.created_at.isoformat()
            ))
            conn.commit()
    
    def list_budgets(self) -> List[Budget]:
        """
        List all budgets.
        
        Returns:
            List of Budget objects
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM budgets ORDER BY created_at DESC")
            rows = cursor.fetchall()
        
        budgets = []
        for row in rows:
            budget = Budget(
                id=row["id"],
                name=row["name"],
                period=CostPeriod(row["period"]),
                limit_amount=row["limit_amount"],
                warning_threshold=row["warning_threshold"],
                block_on_exceed=bool(row["block_on_exceed"]),
                scope_project=row["scope_project"],
                scope_model=row["scope_model"],
                scope_tags=json.loads(row["scope_tags"]) if row["scope_tags"] else [],
                is_active=bool(row["is_active"]),
                created_at=datetime.fromisoformat(row["created_at"])
            )
            budgets.append(budget)
        
        return budgets
    
    def delete_budget(self, budget_id: str) -> bool:
        """
        Delete a budget.
        
        Args:
            budget_id: ID of budget to delete
            
        Returns:
            True if deleted, False if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM budgets WHERE id = ?", (budget_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def save_event(self, event_data: Dict[str, Any]) -> None:
        """
        Save a critical event.
        
        Args:
            event_data: Event data dictionary
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO events (
                    id, type, source, timestamp, priority, data, correlation_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                event_data["id"],
                event_data["type"],
                event_data["source"],
                event_data["timestamp"],
                event_data["priority"],
                json.dumps(event_data["data"]),
                event_data.get("correlation_id")
            ))
            conn.commit()
    
    def get_summary(
        self,
        start: datetime,
        end: datetime,
        project: Optional[str] = None
    ) -> CostSummary:
        """
        Get cost summary for a period.
        
        Args:
            start: Period start
            end: Period end
            project: Optional project filter
            
        Returns:
            CostSummary object
        """
        records = self.query(start=start, end=end, project=project)
        
        if not records:
            return CostSummary(
                period_start=start,
                period_end=end,
                total_cost=0.0,
                total_calls=0,
                total_tokens=0
            )
        
        # Aggregate
        total_cost = sum(r.total_cost for r in records)
        total_tokens = sum(r.total_tokens for r in records)
        
        by_model: Dict[str, float] = {}
        by_agent: Dict[str, float] = {}
        by_provider: Dict[str, float] = {}
        by_project: Dict[str, float] = {}
        by_tag: Dict[str, float] = {}
        by_day: Dict[str, float] = {}
        
        for record in records:
            by_model[record.model] = by_model.get(record.model, 0) + record.total_cost
            by_agent[record.agent_name] = by_agent.get(record.agent_name, 0) + record.total_cost
            by_provider[record.provider] = by_provider.get(record.provider, 0) + record.total_cost
            
            if record.project:
                by_project[record.project] = by_project.get(record.project, 0) + record.total_cost
            
            for tag in record.tags:
                by_tag[tag] = by_tag.get(tag, 0) + record.total_cost
            
            day_key = record.timestamp.strftime('%Y-%m-%d')
            by_day[day_key] = by_day.get(day_key, 0) + record.total_cost
        
        return CostSummary(
            period_start=start,
            period_end=end,
            total_cost=total_cost,
            total_calls=len(records),
            total_tokens=total_tokens,
            by_model=by_model,
            by_agent=by_agent,
            by_provider=by_provider,
            by_project=by_project,
            by_tag=by_tag,
            by_day=by_day,
            avg_cost_per_call=total_cost / len(records) if records else 0,
            avg_tokens_per_call=total_tokens / len(records) if records else 0,
            avg_cost_per_1k_tokens=(total_cost / total_tokens * 1000) if total_tokens else 0
        )

