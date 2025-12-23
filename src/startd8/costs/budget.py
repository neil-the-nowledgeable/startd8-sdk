"""
Budget management and enforcement

Provides budget limits and enforcement for cost control.
"""

from typing import Optional, List, Dict
from datetime import datetime, timezone, timedelta
import threading

from .models import Budget, BudgetStatus, CostPeriod, CostRecord
from .store import CostStore
from ..events import EventBus, Event, EventType, EventPriority
from ..exceptions import Startd8Error
from ..logging_config import get_logger

logger = get_logger(__name__)


class BudgetExceededError(Startd8Error):
    """Raised when a budget limit is exceeded and blocking is enabled"""
    
    def __init__(self, budget: Budget, current_spend: float):
        self.budget = budget
        self.current_spend = current_spend
        super().__init__(
            f"Budget '{budget.name}' exceeded: ${current_spend:.2f} / ${budget.limit_amount:.2f}"
        )


class BudgetManager:
    """
    Manages budget limits and enforcement.
    
    Example:
        manager = BudgetManager(store)
        
        # Create a budget
        budget = manager.create_budget(
            name="Monthly Limit",
            period=CostPeriod.MONTHLY,
            limit_amount=100.0,
            warning_threshold=0.8,
            block_on_exceed=True
        )
        
        # Check before API call
        manager.check_budget()  # Raises BudgetExceededError if over limit
        
        # Get status
        status = manager.get_budget_status(budget.id)
        import logging
        logger = logging.getLogger(__name__)
        logger.info(
            f"Budget status: {status.percentage_used:.1%} used",
            extra={
                "budget_id": status.budget_id,
                "percentage_used": status.percentage_used,
                "amount_used": status.amount_used,
                "amount_limit": status.amount_limit
            }
        )
    """
    
    def __init__(self, store: CostStore):
        self.store = store
        self._budgets: Dict[str, Budget] = {}
        self._lock = threading.RLock()
        self._load_budgets()
    
    def _load_budgets(self):
        """Load budgets from store"""
        budgets = self.store.list_budgets()
        for budget in budgets:
            self._budgets[budget.id] = budget
    
    def create_budget(
        self,
        name: str,
        period: CostPeriod,
        limit_amount: float,
        warning_threshold: float = 0.8,
        block_on_exceed: bool = False,
        scope_project: Optional[str] = None,
        scope_model: Optional[str] = None,
        scope_tags: Optional[List[str]] = None
    ) -> Budget:
        """Create a new budget"""
        budget = Budget(
            name=name,
            period=period,
            limit_amount=limit_amount,
            warning_threshold=warning_threshold,
            block_on_exceed=block_on_exceed,
            scope_project=scope_project,
            scope_model=scope_model,
            scope_tags=scope_tags or []
        )
        
        with self._lock:
            self.store.save_budget(budget)
            self._budgets[budget.id] = budget
        
        # Emit event
        EventBus.emit(Event(
            type=EventType.BUDGET_CREATED,
            source="BudgetManager",
            priority=EventPriority.HIGH,
            data={
                "budget_id": budget.id,
                "budget_name": budget.name,
                "limit_amount": budget.limit_amount,
                "period": budget.period.value
            }
        ))
        
        logger.info(f"Created budget: {name} (${limit_amount:.2f}/{period.value})")
        return budget
    
    def get_budget(self, budget_id: str) -> Optional[Budget]:
        """Get budget by ID"""
        return self._budgets.get(budget_id)
    
    def list_budgets(self, active_only: bool = True) -> List[Budget]:
        """List all budgets"""
        budgets = list(self._budgets.values())
        if active_only:
            budgets = [b for b in budgets if b.is_active]
        return budgets
    
    def update_budget(self, budget: Budget) -> None:
        """Update an existing budget"""
        with self._lock:
            self.store.save_budget(budget)
            self._budgets[budget.id] = budget
        
        # Emit event
        EventBus.emit(Event(
            type=EventType.BUDGET_UPDATED,
            source="BudgetManager",
            priority=EventPriority.HIGH,
            data={
                "budget_id": budget.id,
                "budget_name": budget.name
            }
        ))
        
        logger.info(f"Updated budget: {budget.name}")
    
    def delete_budget(self, budget_id: str) -> bool:
        """Delete a budget"""
        with self._lock:
            if budget_id in self._budgets:
                budget = self._budgets[budget_id]
                self.store.delete_budget(budget_id)
                del self._budgets[budget_id]
                
                # Emit event
                EventBus.emit(Event(
                    type=EventType.BUDGET_DELETED,
                    source="BudgetManager",
                    priority=EventPriority.HIGH,
                    data={
                        "budget_id": budget_id,
                        "budget_name": budget.name
                    }
                ))
                
                logger.info(f"Deleted budget: {budget.name}")
                return True
        return False
    
    def get_budget_status(self, budget_id: str) -> Optional[BudgetStatus]:
        """Get current status of a budget"""
        budget = self.get_budget(budget_id)
        if not budget:
            return None
        
        period_start, period_end = self._get_period_bounds(budget.period)
        current_spend = self._get_spend_for_budget(budget, period_start, period_end)
        
        remaining = max(0, budget.limit_amount - current_spend)
        percentage_used = current_spend / budget.limit_amount if budget.limit_amount > 0 else 0
        
        return BudgetStatus(
            budget=budget,
            current_spend=current_spend,
            remaining=remaining,
            percentage_used=percentage_used,
            period_start=period_start,
            period_end=period_end,
            is_exceeded=current_spend >= budget.limit_amount,
            is_warning=percentage_used >= budget.warning_threshold
        )
    
    def check_budget(
        self,
        model: Optional[str] = None,
        project: Optional[str] = None,
        tags: Optional[List[str]] = None,
        estimated_cost: float = 0.0
    ) -> List[BudgetStatus]:
        """
        Check all applicable budgets before an API call.
        
        Args:
            model: Model being used
            project: Project context
            tags: Tags for the call
            estimated_cost: Estimated cost of the call (for pre-check)
            
        Returns:
            List of budget statuses that are at warning or exceeded
            
        Raises:
            BudgetExceededError: If any blocking budget is exceeded
        """
        warnings = []
        
        for budget in self.list_budgets(active_only=True):
            # Check if budget applies
            if budget.scope_model and model != budget.scope_model:
                continue
            if budget.scope_project and project != budget.scope_project:
                continue
            if budget.scope_tags and not any(t in (tags or []) for t in budget.scope_tags):
                continue
            
            status = self.get_budget_status(budget.id)
            if not status:
                continue
            
            # Check if would exceed with estimated cost
            projected_spend = status.current_spend + estimated_cost
            projected_percentage = projected_spend / budget.limit_amount if budget.limit_amount > 0 else 0
            
            if status.is_exceeded or projected_spend >= budget.limit_amount:
                if budget.block_on_exceed:
                    # Emit event before raising
                    EventBus.emit(Event(
                        type=EventType.BUDGET_EXCEEDED,
                        source="BudgetManager",
                        priority=EventPriority.CRITICAL,
                        data={
                            "budget_id": budget.id,
                            "budget_name": budget.name,
                            "current_spend": status.current_spend,
                            "limit": budget.limit_amount,
                            "blocked": True
                        }
                    ))
                    raise BudgetExceededError(budget, status.current_spend)
                else:
                    warnings.append(status)
                    EventBus.emit(Event(
                        type=EventType.BUDGET_EXCEEDED,
                        source="BudgetManager",
                        priority=EventPriority.HIGH,
                        data={
                            "budget_id": budget.id,
                            "budget_name": budget.name,
                            "current_spend": status.current_spend,
                            "limit": budget.limit_amount,
                            "blocked": False
                        }
                    ))
            elif status.is_warning or projected_percentage >= budget.warning_threshold:
                warnings.append(status)
                EventBus.emit(Event(
                    type=EventType.BUDGET_WARNING,
                    source="BudgetManager",
                    priority=EventPriority.NORMAL,
                    data={
                        "budget_id": budget.id,
                        "budget_name": budget.name,
                        "current_spend": status.current_spend,
                        "limit": budget.limit_amount,
                        "percentage": status.percentage_used
                    }
                ))
        
        return warnings
    
    def _get_period_bounds(self, period: CostPeriod) -> tuple[datetime, datetime]:
        """Get start and end of current period"""
        now = datetime.now(timezone.utc)
        
        if period == CostPeriod.HOURLY:
            start = now.replace(minute=0, second=0, microsecond=0)
            end = start + timedelta(hours=1)
        elif period == CostPeriod.DAILY:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
        elif period == CostPeriod.WEEKLY:
            start = now - timedelta(days=now.weekday())
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(weeks=1)
        elif period == CostPeriod.MONTHLY:
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            # Next month
            if now.month == 12:
                end = start.replace(year=now.year + 1, month=1)
            else:
                end = start.replace(month=now.month + 1)
        else:  # TOTAL
            start = datetime(1970, 1, 1, tzinfo=timezone.utc)
            end = datetime(2100, 1, 1, tzinfo=timezone.utc)
        
        return start, end
    
    def _get_spend_for_budget(
        self, 
        budget: Budget, 
        start: datetime, 
        end: datetime
    ) -> float:
        """Get total spend for a budget in the given period"""
        return self.store.get_total(
            start=start,
            end=end,
            project=budget.scope_project,
            model=budget.scope_model,
            tags=budget.scope_tags if budget.scope_tags else None
        )

