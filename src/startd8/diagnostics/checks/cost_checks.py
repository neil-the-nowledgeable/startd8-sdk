"""
Cost system health checks.

Checks cost database integrity, pricing coverage, and budget status.
"""

import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models import CheckCategory, HealthCheck, HealthStatus
from . import register_check


def _get_default_db_path() -> Path:
    """Get the default cost database path."""
    return Path.home() / ".startd8" / "costs.db"


@register_check(
    "cost_db_exists",
    CheckCategory.COSTS,
    description="Check if cost database file exists",
)
def check_cost_db_exists() -> HealthCheck:
    """Check if cost database file exists."""
    start = time.time()
    db_path = _get_default_db_path()

    if db_path.exists():
        size_bytes = db_path.stat().st_size
        size_kb = size_bytes / 1024
        status = HealthStatus.HEALTHY
        message = f"Cost database exists ({size_kb:.1f} KB)"
        details = {"path": str(db_path), "size_bytes": size_bytes}
    else:
        status = HealthStatus.WARNING
        message = "Cost database not found (will be created on first use)"
        details = {"expected_path": str(db_path)}

    return HealthCheck(
        name="cost_db_exists",
        category=CheckCategory.COSTS,
        status=status,
        message=message,
        details=details,
        duration_ms=(time.time() - start) * 1000,
    )


@register_check(
    "cost_db_integrity",
    CheckCategory.COSTS,
    description="Check cost database integrity using SQLite integrity_check",
)
def check_cost_db_integrity() -> HealthCheck:
    """Check cost database integrity using SQLite PRAGMA integrity_check."""
    start = time.time()
    db_path = _get_default_db_path()

    if not db_path.exists():
        return HealthCheck(
            name="cost_db_integrity",
            category=CheckCategory.COSTS,
            status=HealthStatus.SKIPPED,
            message="Skipped: Cost database does not exist yet",
            duration_ms=(time.time() - start) * 1000,
        )

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Run integrity check
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()

        if result and result[0] == "ok":
            # Also check table count
            cursor.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            )
            table_count = cursor.fetchone()[0]

            # Check record count
            cursor.execute(
                "SELECT COUNT(*) FROM cost_records"
            )
            record_count = cursor.fetchone()[0]

            status = HealthStatus.HEALTHY
            message = f"Database integrity OK ({record_count} records, {table_count} tables)"
            details = {
                "record_count": record_count,
                "table_count": table_count,
                "integrity": "ok",
            }
        else:
            status = HealthStatus.CRITICAL
            message = f"Database integrity check failed: {result}"
            details = {"integrity_result": result}

        conn.close()

    except sqlite3.DatabaseError as e:
        status = HealthStatus.CRITICAL
        message = f"Database corruption detected: {e}"
        details = {"error": str(e)}
    except Exception as e:
        status = HealthStatus.UNKNOWN
        message = f"Failed to check database: {e}"
        details = {"error": str(e)}

    return HealthCheck(
        name="cost_db_integrity",
        category=CheckCategory.COSTS,
        status=status,
        message=message,
        details=details,
        duration_ms=(time.time() - start) * 1000,
        fix_hint="rebuild_cost_db" if status == HealthStatus.CRITICAL else None,
    )


@register_check(
    "pricing_coverage",
    CheckCategory.COSTS,
    description="Check if all common models have pricing configured",
)
def check_pricing_coverage() -> HealthCheck:
    """Check if all common models have pricing configured."""
    start = time.time()

    try:
        from startd8.costs import PricingService

        pricing = PricingService()

        # Models we expect to have pricing for
        expected_models = [
            # Anthropic (current)
            "claude-opus-4-6",
            "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001",
            # Anthropic (legacy)
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
            "claude-sonnet-4-20250514",
            # OpenAI
            "gpt-4",
            "gpt-4-turbo",
            "gpt-4o",
            "gpt-4o-mini",
            # Gemini
            "gemini-1.5-flash",
            "gemini-1.5-pro",
        ]

        covered = []
        missing = []

        for model in expected_models:
            model_pricing = pricing.get_pricing(model)
            if model_pricing:
                covered.append(model)
            else:
                missing.append(model)

        if not missing:
            status = HealthStatus.HEALTHY
            message = f"All {len(covered)} common models have pricing"
            details = {"covered_models": len(covered)}
        elif len(missing) < len(covered):
            status = HealthStatus.WARNING
            message = f"{len(missing)} models missing pricing: {', '.join(missing[:3])}"
            details = {
                "covered_count": len(covered),
                "missing_count": len(missing),
                "missing_models": missing,
            }
        else:
            status = HealthStatus.WARNING
            message = "Many models missing pricing"
            details = {
                "covered_count": len(covered),
                "missing_count": len(missing),
            }

    except ImportError as e:
        status = HealthStatus.UNKNOWN
        message = f"Failed to import PricingService: {e}"
        details = {"error": str(e)}
    except Exception as e:
        status = HealthStatus.UNKNOWN
        message = f"Failed to check pricing: {e}"
        details = {"error": str(e)}

    return HealthCheck(
        name="pricing_coverage",
        category=CheckCategory.COSTS,
        status=status,
        message=message,
        details=details,
        duration_ms=(time.time() - start) * 1000,
        fix_hint="update_pricing_cache" if status == HealthStatus.WARNING else None,
    )


@register_check(
    "budget_status",
    CheckCategory.COSTS,
    description="Check if any budgets are near or over limit",
)
def check_budget_status(framework: Optional[Any] = None) -> HealthCheck:
    """Check if any budgets are near or over limit."""
    start = time.time()
    db_path = _get_default_db_path()

    if not db_path.exists():
        return HealthCheck(
            name="budget_status",
            category=CheckCategory.COSTS,
            status=HealthStatus.SKIPPED,
            message="Skipped: Cost database does not exist yet",
            duration_ms=(time.time() - start) * 1000,
        )

    try:
        from startd8.costs import BudgetManager
        from startd8.costs.store import CostStore

        store = CostStore(db_path)
        manager = BudgetManager(store)

        budgets = store.list_budgets()
        if not budgets:
            return HealthCheck(
                name="budget_status",
                category=CheckCategory.COSTS,
                status=HealthStatus.HEALTHY,
                message="No budgets configured",
                details={"budget_count": 0},
                duration_ms=(time.time() - start) * 1000,
            )

        over_limit: List[str] = []
        warning: List[str] = []
        ok: List[str] = []

        for budget in budgets:
            if not budget.is_active:
                continue

            status_info = manager.check_budget(budget.id)
            if status_info:
                if status_info.get("exceeded"):
                    over_limit.append(budget.name)
                elif status_info.get("warning"):
                    warning.append(budget.name)
                else:
                    ok.append(budget.name)

        if over_limit:
            status = HealthStatus.CRITICAL
            message = f"{len(over_limit)} budgets exceeded: {', '.join(over_limit)}"
        elif warning:
            status = HealthStatus.WARNING
            message = f"{len(warning)} budgets near limit: {', '.join(warning)}"
        else:
            status = HealthStatus.HEALTHY
            message = f"All {len(ok)} budgets within limits"

        return HealthCheck(
            name="budget_status",
            category=CheckCategory.COSTS,
            status=status,
            message=message,
            details={
                "over_limit": over_limit,
                "warning": warning,
                "ok": ok,
            },
            duration_ms=(time.time() - start) * 1000,
        )

    except ImportError as e:
        return HealthCheck(
            name="budget_status",
            category=CheckCategory.COSTS,
            status=HealthStatus.SKIPPED,
            message=f"Budget management not available: {e}",
            duration_ms=(time.time() - start) * 1000,
        )
    except Exception as e:
        return HealthCheck(
            name="budget_status",
            category=CheckCategory.COSTS,
            status=HealthStatus.UNKNOWN,
            message=f"Failed to check budgets: {e}",
            details={"error": str(e)},
            duration_ms=(time.time() - start) * 1000,
        )


@register_check(
    "cost_tracking_imports",
    CheckCategory.COSTS,
    description="Verify cost tracking modules can be imported",
)
def check_cost_tracking_imports() -> HealthCheck:
    """Check that all cost tracking modules can be imported."""
    start = time.time()
    import_results: Dict[str, str] = {}
    all_success = True

    modules_to_check = [
        ("CostTracker", "startd8.costs"),
        ("BudgetManager", "startd8.costs"),
        ("PricingService", "startd8.costs"),
        ("CostAnalytics", "startd8.costs"),
        ("CostStore", "startd8.costs.store"),
    ]

    for class_name, module_path in modules_to_check:
        try:
            module = __import__(module_path, fromlist=[class_name])
            getattr(module, class_name)
            import_results[class_name] = "OK"
        except ImportError as e:
            import_results[class_name] = f"ImportError: {e}"
            all_success = False
        except AttributeError as e:
            import_results[class_name] = f"AttributeError: {e}"
            all_success = False

    if all_success:
        status = HealthStatus.HEALTHY
        message = f"All {len(modules_to_check)} cost modules imported successfully"
    else:
        failed = sum(1 for v in import_results.values() if v != "OK")
        status = HealthStatus.CRITICAL
        message = f"{failed}/{len(modules_to_check)} cost module imports failed"

    return HealthCheck(
        name="cost_tracking_imports",
        category=CheckCategory.COSTS,
        status=status,
        message=message,
        details=import_results,
        duration_ms=(time.time() - start) * 1000,
    )
