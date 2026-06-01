"""ExternalToolsMixin: extracted from tui_improved.py ImprovedTUI (Pass B)."""

from ._shared import *  # noqa: F401,F403

class ExternalToolsMixin:
    def _get_external_tracker(self):
        """Lazy-load external usage tracker"""
        from ..costs.external import ExternalUsageTracker
        from ..costs.store import CostStore

        # Use framework's cost store if available, or create new one
        if hasattr(self.framework, 'cost_tracker') and self.framework.cost_tracker:
            store = self.framework.cost_tracker.store
        else:
            store = CostStore(default_data_dir() / "costs.db")

        return ExternalUsageTracker(store)

    def _get_comparison_analytics(self):
        """Lazy-load comparison analytics"""
        from ..costs.comparison import ComparisonAnalytics
        from ..costs.store import CostStore

        if hasattr(self.framework, 'cost_tracker') and self.framework.cost_tracker:
            store = self.framework.cost_tracker.store
        else:
            store = CostStore(default_data_dir() / "costs.db")

        return ComparisonAnalytics(store)

    def log_external_usage(self):
        """Log usage from an external tool"""
        self.show_header("Log External Usage")

        self.console.print(Panel(
            "[bold]Track External Tool Usage[/bold]\n\n"
            "Record LLM usage from tools outside the SDK:\n"
            "• Claude Code (CLI)\n"
            "• Cursor IDE\n"
            "• GitHub Copilot\n"
            "• ChatGPT Web\n"
            "• And more...\n\n"
            "This helps you compare development productivity across all AI tools.",
            border_style="cyan"
        ))

        tracker = self._get_external_tracker()
        tools = tracker.list_tools()

        if not tools:
            self.console.print("[yellow]No external tools registered.[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return

        # Select tool
        tool_choices = [f"{t.display_name} ({t.id})" for t in tools]
        tool_choices.append("✚ Add Custom Tool")
        tool_choices.append("← Back")

        selected = questionary.select(
            "Select external tool:",
            choices=tool_choices,
            style=custom_style
        ).ask()

        if not selected or "Back" in selected:
            return

        if "Custom" in selected:
            self._add_custom_external_tool()
            return

        # Get tool ID from selection
        tool_id = None
        for t in tools:
            if t.display_name in selected:
                tool_id = t.id
                break

        if not tool_id:
            return

        tool = tracker.get_tool(tool_id)

        # Select entry type
        from ..costs.models import PricingType

        if tool.pricing_type == PricingType.SUBSCRIPTION:
            entry_types = [
                "⏱️  Time-based (estimate from usage time)",
                "💰 Direct cost entry",
                "← Back"
            ]
        else:
            entry_types = [
                "🔢 Token counts (input/output)",
                "💰 Direct cost entry",
                "⏱️  Time-based (estimate subscription)",
                "← Back"
            ]

        entry_type = questionary.select(
            "How would you like to record this usage?",
            choices=entry_types,
            style=custom_style
        ).ask()

        if not entry_type or "Back" in entry_type:
            return

        # Collect data based on entry type
        input_tokens = None
        output_tokens = None
        total_cost = None

        if "Token" in entry_type:
            input_tokens = questionary.text(
                "Input tokens:",
                validate=lambda x: x.isdigit() or x == "",
                style=custom_style
            ).ask()
            input_tokens = int(input_tokens) if input_tokens else 0

            output_tokens = questionary.text(
                "Output tokens:",
                validate=lambda x: x.isdigit() or x == "",
                style=custom_style
            ).ask()
            output_tokens = int(output_tokens) if output_tokens else 0

        elif "cost" in entry_type:
            cost_str = questionary.text(
                "Total cost (USD):",
                validate=lambda x: x.replace('.', '', 1).isdigit() or x == "",
                style=custom_style
            ).ask()
            total_cost = float(cost_str) if cost_str else 0.0

        elif "Time" in entry_type:
            hours = questionary.text(
                "Hours of usage:",
                validate=lambda x: x.replace('.', '', 1).isdigit() or x == "",
                style=custom_style
            ).ask()
            if hours:
                total_cost = tracker.estimate_subscription_cost(
                    tool_id, usage_hours=float(hours)
                )
                self.console.print(f"[dim]Estimated cost: ${total_cost:.4f}[/dim]")

        # Task description (optional but helpful)
        task_description = questionary.text(
            "Task description (optional):",
            style=custom_style
        ).ask()

        # Project attribution (optional)
        project = questionary.text(
            "Project (optional):",
            style=custom_style
        ).ask()

        # Tags (optional)
        tags_str = questionary.text(
            "Tags (comma-separated, optional):",
            style=custom_style
        ).ask()
        tags = [t.strip() for t in tags_str.split(",")] if tags_str else None

        # Record the usage
        try:
            record = tracker.record_external_usage(
                tool_name=tool_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_cost=total_cost,
                task_description=task_description or None,
                project=project or None,
                tags=tags,
            )

            self.console.print(Panel(
                f"[bold green]✓ Usage Recorded[/bold green]\n\n"
                f"Tool: {tool.display_name}\n"
                f"Tokens: {record.total_tokens:,}\n"
                f"Cost: ${record.total_cost:.4f}\n"
                + (f"Task: {task_description}\n" if task_description else "")
                + (f"Project: {project}" if project else ""),
                border_style="green"
            ))
        except Exception as e:
            self.console.print(f"[red]Error recording usage: {e}[/red]")

        questionary.press_any_key_to_continue().ask()

    def _add_custom_external_tool(self):
        """Add a custom external tool to the registry"""
        self.show_header("Add Custom External Tool")

        from ..costs.models import ExternalTool, PricingType

        tool_id = questionary.text(
            "Tool ID (lowercase, no spaces):",
            validate=lambda x: x.isalnum() or "-" in x,
            style=custom_style
        ).ask()

        if not tool_id:
            return

        display_name = questionary.text(
            "Display name:",
            style=custom_style
        ).ask()

        provider = questionary.text(
            "Provider (e.g., openai, anthropic, google):",
            style=custom_style
        ).ask()

        pricing_type = questionary.select(
            "Pricing model:",
            choices=[
                "per_token - Pay per token (API-style)",
                "subscription - Fixed monthly cost",
                "hybrid - Subscription + per-token overages"
            ],
            style=custom_style
        ).ask()

        pricing_type_value = PricingType(pricing_type.split(" - ")[0])

        subscription_cost = None
        if pricing_type_value in [PricingType.SUBSCRIPTION, PricingType.HYBRID]:
            cost_str = questionary.text(
                "Monthly subscription cost (USD):",
                validate=lambda x: x.replace('.', '', 1).isdigit(),
                style=custom_style
            ).ask()
            subscription_cost = float(cost_str) if cost_str else None

        # Create and save tool
        tracker = self._get_external_tracker()
        tool = ExternalTool(
            id=tool_id,
            display_name=display_name or tool_id,
            provider=provider or "custom",
            pricing_type=pricing_type_value,
            subscription_cost=subscription_cost,
        )
        tracker.register_tool(tool)

        self.console.print(f"[green]✓ Tool '{display_name}' registered![/green]")
        questionary.press_any_key_to_continue().ask()

    def compare_sdk_vs_external(self):
        """Show comparison of SDK vs external tool usage"""
        self.show_header("Compare SDK vs External Usage")

        from datetime import datetime, timedelta, timezone

        # Select time period
        period = questionary.select(
            "Select time period:",
            choices=[
                "Last 7 days",
                "Last 30 days",
                "Last 90 days",
                "Custom range",
                "← Back"
            ],
            style=custom_style
        ).ask()

        if not period or "Back" in period:
            return

        now = datetime.now(timezone.utc)
        if "7" in period:
            start = now - timedelta(days=7)
        elif "30" in period:
            start = now - timedelta(days=30)
        elif "90" in period:
            start = now - timedelta(days=90)
        else:
            # Custom range
            start_str = questionary.text(
                "Start date (YYYY-MM-DD):",
                style=custom_style
            ).ask()
            try:
                start = datetime.strptime(start_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                self.console.print("[red]Invalid date format[/red]")
                questionary.press_any_key_to_continue().ask()
                return

        analytics = self._get_comparison_analytics()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console
        ) as progress:
            progress.add_task("Analyzing usage data...", total=None)
            report = analytics.get_tool_comparison(start, now)

        # Display comparison table
        table = Table(title=f"Usage Comparison ({start.strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')})")
        table.add_column("Source", style="cyan")
        table.add_column("Calls", justify="right", style="white")
        table.add_column("Tokens", justify="right", style="white")
        table.add_column("Cost", justify="right", style="green")
        table.add_column("$/1K tokens", justify="right", style="yellow")

        # SDK row
        sdk = report.sdk_usage
        table.add_row(
            "SDK (StartD8)",
            f"{sdk.total_calls:,}",
            f"{sdk.total_tokens:,}",
            f"${sdk.total_cost:.2f}",
            f"${sdk.avg_cost_per_1k_tokens:.4f}" if sdk.total_tokens > 0 else "-"
        )

        # External tools
        for tool_name, summary in sorted(report.external_usage.items()):
            table.add_row(
                tool_name,
                f"{summary.total_calls:,}",
                f"{summary.total_tokens:,}",
                f"${summary.total_cost:.2f}",
                f"${summary.avg_cost_per_1k_tokens:.4f}" if summary.total_tokens > 0 else "-"
            )

        # Totals row
        table.add_section()
        table.add_row(
            "[bold]TOTAL[/bold]",
            f"[bold]{report.total_calls:,}[/bold]",
            f"[bold]{report.total_tokens:,}[/bold]",
            f"[bold]${report.total_cost:.2f}[/bold]",
            ""
        )

        self.console.print(table)

        # Show recommendations
        if report.recommendations:
            self.console.print("\n[bold]Recommendations:[/bold]")
            for rec in report.recommendations:
                self.console.print(f"  • {rec}")

        if report.most_cost_effective_tool:
            self.console.print(f"\n[green]Most cost-effective: {report.most_cost_effective_tool}[/green]")

        # Offer detailed report
        show_detailed = questionary.confirm(
            "\nWould you like to see the detailed report?",
            default=False,
            style=custom_style
        ).ask()

        if show_detailed:
            detailed = analytics.generate_comparison_report(start, now, format="markdown")
            from rich.markdown import Markdown
            self.console.print(Markdown(detailed))

        questionary.press_any_key_to_continue().ask()

    def manage_external_tools(self):
        """Manage external tools registry"""
        while True:
            self.show_header("Manage External Tools")

            tracker = self._get_external_tracker()
            tools = tracker.list_tools()

            # Display current tools
            table = Table(title="Registered External Tools")
            table.add_column("ID", style="cyan")
            table.add_column("Name", style="white")
            table.add_column("Provider", style="blue")
            table.add_column("Pricing", style="yellow")
            table.add_column("Subscription", justify="right", style="green")

            for tool in tools:
                sub_cost = f"${tool.subscription_cost:.0f}/mo" if tool.subscription_cost else "-"
                table.add_row(
                    tool.id,
                    tool.display_name,
                    tool.provider,
                    tool.pricing_type.value,
                    sub_cost
                )

            self.console.print(table)

            # Menu options
            choice = questionary.select(
                "\nWhat would you like to do?",
                choices=[
                    "✚ Add Custom Tool",
                    "🗑️  Remove Tool",
                    "📋 View Tool Details",
                    "← Back"
                ],
                style=custom_style
            ).ask()

            if not choice or "Back" in choice:
                break

            if "Add" in choice:
                self._add_custom_external_tool()

            elif "Remove" in choice:
                tool_choices = [f"{t.display_name} ({t.id})" for t in tools]
                tool_choices.append("← Cancel")

                to_remove = questionary.select(
                    "Select tool to remove:",
                    choices=tool_choices,
                    style=custom_style
                ).ask()

                if to_remove and "Cancel" not in to_remove:
                    for t in tools:
                        if t.display_name in to_remove:
                            if tracker.unregister_tool(t.id):
                                self.console.print(f"[green]✓ Removed {t.display_name}[/green]")
                            else:
                                self.console.print(f"[red]Failed to remove {t.display_name}[/red]")
                            break

            elif "Details" in choice:
                tool_choices = [f"{t.display_name} ({t.id})" for t in tools]
                tool_choices.append("← Cancel")

                to_view = questionary.select(
                    "Select tool to view:",
                    choices=tool_choices,
                    style=custom_style
                ).ask()

                if to_view and "Cancel" not in to_view:
                    for t in tools:
                        if t.display_name in to_view:
                            self.console.print(Panel(
                                f"[bold]{t.display_name}[/bold]\n\n"
                                f"ID: {t.id}\n"
                                f"Provider: {t.provider}\n"
                                f"Default Model: {t.default_model or 'N/A'}\n"
                                f"Pricing Type: {t.pricing_type.value}\n"
                                f"Subscription: ${t.subscription_cost:.2f}/month" if t.subscription_cost else "N/A\n"
                                f"Notes: {t.notes or 'N/A'}",
                                border_style="cyan"
                            ))
                            questionary.press_any_key_to_continue().ask()
                            break
