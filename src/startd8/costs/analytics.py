"""
Cost analytics and optimization recommendations

Analyzes spending patterns and provides actionable recommendations
for cost reduction.
"""

from typing import List, Optional, Dict
from datetime import datetime, timezone, timedelta
from collections import defaultdict

from .models import CostSummary, CostOptimization, CostRecord
from .store import CostStore
from .pricing import PricingService
from ..logging_config import get_logger

logger = get_logger(__name__)


class CostAnalytics:
    """
    Analytics and optimization recommendations for cost data.
    
    Example:
        analytics = CostAnalytics(store, pricing)
        
        # Get spending trends
        trends = analytics.get_spending_trends(days=30)
        
        # Get optimization recommendations
        recommendations = analytics.get_optimizations()
        for rec in recommendations:
            print(f"{rec.title}: Save ${rec.potential_savings:.2f}/month")
    """
    
    def __init__(self, store: CostStore, pricing: PricingService):
        self.store = store
        self.pricing = pricing
    
    def get_spending_trends(
        self,
        days: int = 30,
        project: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Analyze spending trends over time.
        
        Returns:
            Dictionary with trend analysis
        """
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        
        records = self.store.query(start=start, end=end, project=project)
        
        if not records:
            return {
                "period_days": days,
                "total_cost": 0,
                "daily_average": 0,
                "trend": "stable",
                "trend_percentage": 0,
            }
        
        # Group by day
        by_day: Dict[str, float] = defaultdict(float)
        for record in records:
            day = record.timestamp.strftime('%Y-%m-%d')
            by_day[day] += record.total_cost
        
        total_cost = sum(record.total_cost for record in records)
        daily_costs = list(by_day.values())
        daily_average = total_cost / days if days > 0 else 0
        
        # Calculate trend (compare first half to second half)
        if len(daily_costs) >= 2:
            mid = len(daily_costs) // 2
            first_half_avg = sum(daily_costs[:mid]) / mid if mid > 0 else 0
            second_half_avg = sum(daily_costs[mid:]) / (len(daily_costs) - mid) if (len(daily_costs) - mid) > 0 else 0
            
            if first_half_avg > 0:
                trend_percentage = ((second_half_avg - first_half_avg) / first_half_avg) * 100
            else:
                trend_percentage = 0
            
            if trend_percentage > 10:
                trend = "increasing"
            elif trend_percentage < -10:
                trend = "decreasing"
            else:
                trend = "stable"
        else:
            trend = "stable"
            trend_percentage = 0
        
        return {
            "period_days": days,
            "total_cost": total_cost,
            "daily_average": daily_average,
            "daily_costs": dict(by_day),
            "trend": trend,
            "trend_percentage": trend_percentage,
            "projected_monthly": daily_average * 30,
        }
    
    def get_optimizations(
        self,
        days: int = 30,
        project: Optional[str] = None
    ) -> List[CostOptimization]:
        """
        Generate cost optimization recommendations.
        
        Analyzes usage patterns and suggests ways to reduce costs.
        """
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        
        records = self.store.query(start=start, end=end, project=project)
        
        if not records:
            return []
        
        recommendations = []
        
        # 1. Model downgrade opportunities
        recommendations.extend(self._analyze_model_downgrades(records))
        
        # 2. Caching opportunities (repeated similar prompts)
        recommendations.extend(self._analyze_caching_opportunities(records))
        
        # 3. Token optimization (long prompts)
        recommendations.extend(self._analyze_token_optimization(records))
        
        # 4. Batch processing opportunities
        recommendations.extend(self._analyze_batch_opportunities(records))
        
        # Sort by potential savings
        recommendations.sort(key=lambda x: x.potential_savings, reverse=True)
        
        return recommendations
    
    def _analyze_model_downgrades(self, records: List[CostRecord]) -> List[CostOptimization]:
        """Identify opportunities to use cheaper models"""
        recommendations = []
        
        # Group by model
        by_model: Dict[str, List[CostRecord]] = defaultdict(list)
        for record in records:
            by_model[record.model].append(record)
        
        # Check for expensive models that could be downgraded
        downgrade_map = {
            "claude-3-opus-20240229": "claude-3-5-sonnet-20241022",
            "gpt-4": "gpt-4o",
            "gpt-4-turbo": "gpt-4o",
            "claude-3-5-sonnet-20241022": "claude-3-5-haiku-20241022",
            "gpt-4o": "gpt-4o-mini",
        }
        
        for expensive_model, cheaper_model in downgrade_map.items():
            if expensive_model in by_model:
                model_records = by_model[expensive_model]
                current_cost = sum(r.total_cost for r in model_records)
                total_tokens = sum(r.total_tokens for r in model_records)
                
                # Estimate cost with cheaper model
                cheaper_pricing = self.pricing.get_pricing(cheaper_model)
                if cheaper_pricing:
                    # Rough estimate using average input/output ratio
                    avg_input = sum(r.input_tokens for r in model_records) / len(model_records)
                    avg_output = sum(r.output_tokens for r in model_records) / len(model_records)
                    
                    cheaper_cost = self.pricing.calculate_total_cost(
                        cheaper_model,
                        int(avg_input * len(model_records)),
                        int(avg_output * len(model_records))
                    )
                    
                    savings = current_cost - cheaper_cost
                    
                    if savings > 0.10:  # Only recommend if savings > $0.10
                        recommendations.append(CostOptimization(
                            title=f"Switch from {expensive_model} to {cheaper_model}",
                            description=(
                                f"You're using {expensive_model} for {len(model_records)} calls. "
                                f"Consider using {cheaper_model} for similar quality at lower cost."
                            ),
                            potential_savings=savings * (30 / max(1, len(set(r.timestamp.date() for r in model_records)))),  # Monthly projection
                            effort="low",
                            category="model-selection",
                            current_cost=current_cost,
                            optimized_cost=cheaper_cost,
                            affected_calls=len(model_records),
                            recommendation=f"Update agent configuration to use {cheaper_model}"
                        ))
        
        return recommendations
    
    def _analyze_caching_opportunities(self, records: List[CostRecord]) -> List[CostOptimization]:
        """Identify repeated prompts that could be cached"""
        recommendations = []
        
        # This would require access to prompt content, which we don't store in cost records
        # For now, look for rapid repeated calls to same model
        
        # Group by model and hour
        by_model_hour: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for record in records:
            hour_key = record.timestamp.strftime('%Y-%m-%d-%H')
            by_model_hour[record.model][hour_key] += 1
        
        for model, hours in by_model_hour.items():
            high_volume_hours = [h for h, count in hours.items() if count > 10]
            if high_volume_hours:
                model_records = [r for r in records if r.model == model]
                total_cost = sum(r.total_cost for r in model_records)
                
                # Estimate 20% could be cached
                potential_savings = total_cost * 0.2
                
                if potential_savings > 0.50:
                    recommendations.append(CostOptimization(
                        title=f"Implement caching for {model}",
                        description=(
                            f"High call volume detected ({len(model_records)} calls). "
                            f"Consider implementing response caching for repeated prompts."
                        ),
                        potential_savings=potential_savings,
                        effort="medium",
                        category="caching",
                        current_cost=total_cost,
                        optimized_cost=total_cost * 0.8,
                        affected_calls=len(model_records),
                        recommendation="Implement a caching layer for frequently repeated prompts"
                    ))
        
        return recommendations
    
    def _analyze_token_optimization(self, records: List[CostRecord]) -> List[CostOptimization]:
        """Identify prompts that could be shortened"""
        recommendations = []
        
        # Find calls with high input token counts
        high_input_records = [r for r in records if r.input_tokens > 4000]
        
        if high_input_records:
            total_cost = sum(r.total_cost for r in high_input_records)
            avg_input = sum(r.input_tokens for r in high_input_records) / len(high_input_records)
            
            # Estimate 30% reduction possible with prompt optimization
            potential_savings = total_cost * 0.3
            
            if potential_savings > 0.25:
                recommendations.append(CostOptimization(
                    title="Optimize long prompts",
                    description=(
                        f"Found {len(high_input_records)} calls with >4000 input tokens "
                        f"(avg: {avg_input:.0f}). Consider prompt compression techniques."
                    ),
                    potential_savings=potential_savings,
                    effort="medium",
                    category="prompt-optimization",
                    current_cost=total_cost,
                    optimized_cost=total_cost * 0.7,
                    affected_calls=len(high_input_records),
                    recommendation="Review and compress prompts, remove redundant context"
                ))
        
        return recommendations
    
    def _analyze_batch_opportunities(self, records: List[CostRecord]) -> List[CostOptimization]:
        """Identify opportunities for batch processing"""
        recommendations = []
        
        # Look for many small calls that could be batched
        small_calls = [r for r in records if r.total_tokens < 500]
        
        if len(small_calls) > 50:
            total_cost = sum(r.total_cost for r in small_calls)
            
            # Batching typically saves on API overhead
            potential_savings = total_cost * 0.15
            
            if potential_savings > 0.20:
                recommendations.append(CostOptimization(
                    title="Batch small requests",
                    description=(
                        f"Found {len(small_calls)} small requests (<500 tokens). "
                        f"Consider batching these for efficiency."
                    ),
                    potential_savings=potential_savings,
                    effort="high",
                    category="batching",
                    current_cost=total_cost,
                    optimized_cost=total_cost * 0.85,
                    affected_calls=len(small_calls),
                    recommendation="Implement request batching for small, similar tasks"
                ))
        
        return recommendations
    
    def generate_report(
        self,
        start: datetime,
        end: datetime,
        format: str = "markdown"
    ) -> str:
        """Generate a cost report"""
        summary = self.store.get_summary(start, end)
        trends = self.get_spending_trends(days=(end - start).days)
        optimizations = self.get_optimizations(days=(end - start).days)
        
        if format == "markdown":
            return self._format_markdown_report(summary, trends, optimizations, start, end)
        elif format == "json":
            import json
            return json.dumps({
                "summary": summary.model_dump(),
                "trends": trends,
                "optimizations": [o.model_dump() for o in optimizations]
            }, indent=2, default=str)
        else:
            raise ValueError(f"Unknown format: {format}")
    
    def _format_markdown_report(
        self,
        summary: CostSummary,
        trends: Dict,
        optimizations: List[CostOptimization],
        start: datetime,
        end: datetime
    ) -> str:
        """Format report as markdown"""
        lines = [
            f"# Cost Report",
            f"",
            f"**Period:** {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}",
            f"",
            f"## Summary",
            f"",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Cost | ${summary.total_cost:.2f} |",
            f"| Total Calls | {summary.total_calls:,} |",
            f"| Total Tokens | {summary.total_tokens:,} |",
            f"| Avg Cost/Call | ${summary.avg_cost_per_call:.4f} |",
            f"| Avg Tokens/Call | {summary.avg_tokens_per_call:.0f} |",
            f"",
            f"## Trends",
            f"",
            f"- **Daily Average:** ${trends['daily_average']:.2f}",
            f"- **Trend:** {trends['trend']} ({trends['trend_percentage']:+.1f}%)",
            f"- **Projected Monthly:** ${trends['projected_monthly']:.2f}",
            f"",
        ]
        
        if summary.by_model:
            lines.extend([
                f"## Cost by Model",
                f"",
                f"| Model | Cost | % |",
                f"|-------|------|---|",
            ])
            for model, cost in sorted(summary.by_model.items(), key=lambda x: x[1], reverse=True):
                pct = (cost / summary.total_cost * 100) if summary.total_cost > 0 else 0
                lines.append(f"| {model} | ${cost:.2f} | {pct:.1f}% |")
            lines.append("")
        
        if optimizations:
            lines.extend([
                f"## Optimization Recommendations",
                f"",
            ])
            for i, opt in enumerate(optimizations[:5], 1):
                lines.extend([
                    f"### {i}. {opt.title}",
                    f"",
                    f"{opt.description}",
                    f"",
                    f"- **Potential Savings:** ${opt.potential_savings:.2f}/month",
                    f"- **Effort:** {opt.effort}",
                    f"- **Action:** {opt.recommendation}",
                    f"",
                ])
        
        return "\n".join(lines)

