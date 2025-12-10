# Cost Tracking User Guide

**Version:** 1.0  
**Last Updated:** December 10, 2025  
**Status:** Production Ready

---

## Overview

The StartD8 SDK includes comprehensive cost tracking capabilities for monitoring AI model usage and enforcing budget limits. This guide covers all features and best practices.

### Key Features
- 📊 **Cost Recording**: Track costs for every API call
- 💰 **Budget Management**: Set spending limits by project, model, or tag
- 🏷️ **Tag-Based Attribution**: Organize costs by feature, project, or purpose
- 📈 **Period Analytics**: Query costs by hour, day, week, or month
- 🔄 **Context Management**: Automatically track project and tags across call chains
- 🚨 **Budget Alerts**: Get warnings when approaching or exceeding budgets

---

## Quick Start (5 minutes)

### 1. Initialize Cost Tracking

```python
from startd8.costs import CostTracker, BudgetManager
from startd8.costs.budget import CostPeriod

# Create instances
cost_tracker = CostTracker()
budget_manager = BudgetManager(cost_tracker)

# Enable tracking (default is enabled)
cost_tracker.enable()
```

### 2. Record a Cost

```python
# Simple cost recording
cost_tracker.record_cost(
    agent_name="my-agent",
    model="gpt-4",
    provider="openai",
    input_tokens=100,
    output_tokens=50,
    input_cost=0.001,
    output_cost=0.0015
)
```

### 3. Get Total Spending

```python
# Get total spending
total = cost_tracker.store.get_total()
print(f"Total cost: ${total:.4f}")

# Get today's spending
today = cost_tracker.store.get_total_for_period("daily", "2025-12-10")
print(f"Today's cost: ${today:.4f}")
```

### 4. Set and Check Budgets

```python
# Create daily budget
budget = budget_manager.create_budget(
    name="daily-limit",
    period=CostPeriod.DAILY,
    limit_amount=100.00,
    block_on_exceed=True  # Block requests if exceeded
)

# Check budget before making an expensive call
if budget_manager.check_budget():
    # Safe to proceed
    agent.create_response(prompt)
else:
    # Budget exceeded
    print("Daily budget exceeded!")
```

---

## Using Tracking Context

### Basic Context Usage

```python
from startd8.costs import tracking_context

# Set project context
with tracking_context(project="my-project"):
    # All costs here are tagged with project="my-project"
    cost_tracker.record_cost(...)
    agent.create_response(...)
```

### Setting Tags

```python
with tracking_context(tags=["feature-a", "analytics"]):
    # All costs here are tagged with both tags
    cost_tracker.record_cost(...)
```

### Combining Project and Tags

```python
with tracking_context(project="my-app", tags=["feature-x"]):
    # All costs are tagged with both project and tags
    cost_tracker.record_cost(...)
```

### Nested Contexts

Contexts can be nested. Tags are merged, project is overridden:

```python
with tracking_context(project="app", tags=["backend"]):
    # Context: project="app", tags=["backend"]
    
    with tracking_context(tags=["database"]):
        # Context: project="app", tags=["backend", "database"]
        cost_tracker.record_cost(...)
    
    # Back to: project="app", tags=["backend"]
```

### Manual Context Management

```python
from startd8.costs import set_cost_context, get_cost_context, clear_cost_context

# Get current context
current = get_cost_context()

# Set context manually (less common)
set_cost_context({"project": "my-app", "tags": ["feature-x"]})

# Clear context
clear_cost_context()
```

---

## Setting Up Budgets

### Create a Budget

```python
from startd8.costs.budget import CostPeriod

budget = budget_manager.create_budget(
    name="daily-project-budget",
    period=CostPeriod.DAILY,          # HOURLY, DAILY, WEEKLY, MONTHLY
    limit_amount=100.00,               # Limit in USD
    warning_threshold=80.00,           # Warn at 80% of limit
    block_on_exceed=True,              # Block API calls if exceeded
    scope_project="my-project",        # Only count costs for this project
    scope_model=None,                  # Optional: limit to specific model
    scope_tags=["feature-a"],          # Optional: limit to specific tags
    is_active=True                     # Activate the budget
)
```

### Budget Types

| Period | Use Case | Example |
|--------|----------|---------|
| HOURLY | Real-time cost control | $5 per hour |
| DAILY | Daily spending caps | $100 per day |
| WEEKLY | Weekly budgets | $500 per week |
| MONTHLY | Monthly budgets | $2,000 per month |

### Scoped Budgets

```python
# Budget only for specific project
budget_manager.create_budget(
    name="project-a-daily",
    period=CostPeriod.DAILY,
    limit_amount=50.00,
    scope_project="project-a"
)

# Budget only for specific tags
budget_manager.create_budget(
    name="analytics-daily",
    period=CostPeriod.DAILY,
    limit_amount=75.00,
    scope_tags=["analytics"]
)

# Budget for specific project AND model
budget_manager.create_budget(
    name="gpt4-project-a",
    period=CostPeriod.DAILY,
    limit_amount=30.00,
    scope_project="project-a",
    scope_model="gpt-4"
)
```

### Check Budgets

```python
# Check if budget allows spending
can_spend = budget_manager.check_budget(project="my-project")
if not can_spend:
    raise Exception("Budget exceeded for project!")

# Check specific budget
specific_budget = budget_manager.get_budget("daily-limit")
if specific_budget.is_exceeded():
    print(f"Budget {specific_budget.name} exceeded!")
```

---

## Querying Costs

### Basic Queries

```python
# Get all costs
all_costs = cost_tracker.store.query()

# Filter by project
project_costs = cost_tracker.store.query(project="my-project")

# Filter by tags (any tag match)
feature_costs = cost_tracker.store.query(tags=["feature-a"])

# Filter by model
gpt4_costs = cost_tracker.store.query(model="gpt-4")

# Filter by agent name
agent_costs = cost_tracker.store.query(agent="my-agent")
```

### Date Range Queries

```python
from datetime import datetime, timezone, timedelta

# Get costs from last 24 hours
start = datetime.now(timezone.utc) - timedelta(days=1)
recent_costs = cost_tracker.store.query(start=start)

# Get costs from specific date range
start = datetime(2025, 12, 1, tzinfo=timezone.utc)
end = datetime(2025, 12, 31, tzinfo=timezone.utc)
december_costs = cost_tracker.store.query(start=start, end=end)
```

### Combined Queries

```python
# Complex query with multiple filters
costs = cost_tracker.store.query(
    project="my-project",
    tags=["feature-a"],
    model="gpt-4",
    start=datetime.now(timezone.utc) - timedelta(days=7)
)

# With limit
recent_10 = cost_tracker.store.query(
    project="my-project",
    limit=10
)
```

### Get Totals

```python
# Total of all costs
total = cost_tracker.store.get_total()

# Total for project
project_total = cost_tracker.store.get_total(project="my-project")

# Total for tags
feature_total = cost_tracker.store.get_total(tags=["feature-a"])

# Total with multiple filters
filtered_total = cost_tracker.store.get_total(
    project="my-project",
    tags=["feature-a"],
    model="gpt-4"
)
```

---

## Period-Based Analytics

### Query by Hour

```python
# Get cost for specific hour (14:00 UTC on Dec 10, 2025)
hourly = cost_tracker.store.get_total_for_period("hourly", "2025-12-10-14")
print(f"Cost at 2:00 PM: ${hourly:.4f}")
```

### Query by Day

```python
# Get cost for specific day
daily = cost_tracker.store.get_total_for_period("daily", "2025-12-10")
print(f"Cost on Dec 10: ${daily:.4f}")
```

### Query by Week (ISO 8601)

```python
# Get cost for week 50 of 2025 (Monday-Sunday)
weekly = cost_tracker.store.get_total_for_period("weekly", "2025-W50")
print(f"Cost for week 50: ${weekly:.4f}")
```

### Query by Month

```python
# Get cost for December 2025
monthly = cost_tracker.store.get_total_for_period("monthly", "2025-12")
print(f"Cost for December: ${monthly:.4f}")
```

### All-Time Total

```python
# Get all-time total
alltime = cost_tracker.store.get_total_for_period("total", "total")
print(f"Total all-time: ${alltime:.4f}")
```

---

## Events and Alerts

### Listen for Events

```python
from startd8.costs.events import EventBus, EventType

event_bus = EventBus()

# Subscribe to cost recorded events
def on_cost(event):
    print(f"Cost recorded: ${event.data['total_cost']}")

event_bus.subscribe(EventType.COST_RECORDED, on_cost)

# Subscribe to budget events
def on_budget_warning(event):
    print(f"Budget warning: {event.data['message']}")

event_bus.subscribe(EventType.BUDGET_WARNING, on_budget_warning)
```

### Event Types

| Event | Fired When |
|-------|-----------|
| `COST_RECORDED` | Cost is recorded |
| `BUDGET_WARNING` | Cost approaches budget limit (80%) |
| `BUDGET_EXCEEDED` | Budget limit exceeded |

---

## Advanced Usage

### Disabling Cost Tracking

```python
# Temporarily disable tracking
cost_tracker.disable()

# Costs recorded here are not tracked
cost_tracker.record_cost(...)

# Re-enable
cost_tracker.enable()
```

### Tag Normalization

Tags are automatically normalized:
- Duplicates are prevented
- Fast tag-based queries (O(log n) performance)
- Supports many tags per record

```python
# These produce identical results
record1 = CostRecord(..., tags=["feature-a", "feature-a"])
record2 = CostRecord(..., tags=["feature-a"])

# Both stored identically (no duplicates)
```

### Accessing Raw Cost Records

```python
# Get raw CostRecord objects
records = cost_tracker.store.query(project="my-project")

for record in records:
    print(f"Agent: {record.agent_name}")
    print(f"Model: {record.model}")
    print(f"Cost: ${record.total_cost}")
    print(f"Tokens: {record.total_tokens}")
    print(f"Tags: {record.tags}")
    print(f"Project: {record.project}")
```

---

## Best Practices

### 1. Use Tracking Context

✅ **Good:** Set context once, costs flow through
```python
with tracking_context(project="feature-x"):
    # Multiple API calls all get tagged
    response1 = agent.create_response(prompt1)
    response2 = agent.create_response(prompt2)
```

❌ **Bad:** Manually tracking each call
```python
cost_tracker.record_cost(..., project="feature-x")
cost_tracker.record_cost(..., project="feature-x")
```

### 2. Set Meaningful Project Names

✅ **Good:**
```python
"data-pipeline-v2", "customer-support-bot", "report-generation"
```

❌ **Bad:**
```python
"project1", "p2", "test"
```

### 3. Use Scoped Budgets

✅ **Good:** Different limits for different projects
```python
budget_manager.create_budget(
    name="high-cost-project",
    period=CostPeriod.DAILY,
    limit_amount=500.00,
    scope_project="data-pipeline"
)

budget_manager.create_budget(
    name="low-cost-project",
    period=CostPeriod.DAILY,
    limit_amount=50.00,
    scope_project="webhook-handler"
)
```

### 4. Monitor Budgets

✅ **Good:** Check before expensive operations
```python
if not budget_manager.check_budget(project="my-project"):
    # Use cheaper model or queue for later
    use_gpt_35_turbo()
else:
    use_gpt_4()
```

### 5. Review Costs Regularly

✅ **Good:** Daily/weekly cost reviews
```python
daily_total = cost_tracker.store.get_total_for_period("daily", "2025-12-10")
weekly_total = cost_tracker.store.get_total_for_period("weekly", "2025-W50")

print(f"Daily: ${daily_total}, Weekly: ${weekly_total}")
```

---

## Troubleshooting

### Costs Not Being Recorded

**Problem:** `cost_tracker.record_cost()` runs but costs don't appear in queries

**Solutions:**
1. Check that cost tracking is enabled: `assert cost_tracker.enabled`
2. Verify the record was saved: `records = cost_tracker.store.query()` should not be empty
3. Check for exceptions in logs

### Budgets Not Enforcing

**Problem:** `budget_manager.check_budget()` returns True even though budget should be exceeded

**Solutions:**
1. Verify budget is active: `assert budget.is_active`
2. Check scope matches: `budget.scope_project` should match your project
3. Verify period is correct: Budget should be for today, not yesterday
4. Check costs are being recorded to the scoped project

### Slow Queries

**Problem:** Queries take more than 100ms

**Solutions:**
1. Limit date range: `query(start=..., end=...)` narrows search
2. Use LIMIT: `query(limit=100)` reduces result size
3. Filter by project: `query(project=...)` reduces records scanned
4. Verify indexes exist on database

### Context Not Applied

**Problem:** Costs recorded in context don't have expected tags/project

**Solutions:**
1. Verify context is set: `get_cost_context()` should not be empty
2. Check context scope: Nested contexts override parent values
3. Explicit parameters override context: Pass `project=None` to use context

---

## Performance Considerations

### Query Performance

| Scenario | Time | Notes |
|----------|------|-------|
| Query all 1000 records | <50ms | With indexes |
| Query by tag, 1000 records | <100ms | SQL JOIN with index |
| Get total by period, 10000 records | <50ms | Direct aggregation |
| Query by date range, 100000 records | <500ms | Index range scan |

### Optimization Tips

1. **Use date ranges**: Narrow your queries
2. **Use indexes**: Indexes created automatically on project, model, tags
3. **Batch queries**: Load multiple results at once
4. **Limit results**: Use LIMIT parameter
5. **Archive old data**: Move old records to archive table periodically

---

## API Reference

For detailed API reference, see `API_REFERENCE.md`

### Key Classes

- `CostTracker`: Main class for recording and querying costs
- `BudgetManager`: Manage spending limits
- `CostStore`: SQLite-backed storage
- `EventBus`: Event emission and subscription

### Key Methods

- `cost_tracker.record_cost()`: Record a cost
- `cost_tracker.store.query()`: Query costs
- `cost_tracker.store.get_total()`: Get total cost
- `budget_manager.create_budget()`: Create a budget
- `budget_manager.check_budget()`: Check if budget allows spending

---

## Getting Help

- Check logs: Most issues logged to `startd8.costs` logger
- Review examples: See `examples/cost_tracking_*.py` for code samples
- Read code: Source in `src/startd8/costs/`
- File issues: GitHub issues for bugs and features

---

**Happy cost tracking! 💰**

