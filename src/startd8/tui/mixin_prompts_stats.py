"""PromptsStatsMixin: extracted from tui_improved.py ImprovedTUI (Pass B)."""

from ._shared import *  # noqa: F401,F403

class PromptsStatsMixin:
    def list_all_prompts(self):
        """List all prompts"""
        self.show_header("All Prompts")
        
        prompts = self.framework.list_prompts()
        
        if not prompts:
            self.console.print("[yellow]No prompts found.[/yellow]\n")
            questionary.press_any_key_to_continue().ask()
            return
        
        table = Table(title=f"Prompts ({len(prompts)} total)")
        table.add_column("ID", style="cyan")
        table.add_column("Content Preview", style="white")
        table.add_column("Tags", style="green")
        table.add_column("Responses", justify="center", style="yellow")
        
        for prompt in prompts[:20]:  # Show last 20
            responses = self.framework.list_responses(prompt_id=prompt.id)
            preview = prompt.content[:60] + "..." if len(prompt.content) > 60 else prompt.content
            tags = ", ".join(prompt.tags[:3]) if prompt.tags else "-"
            
            table.add_row(
                prompt.id[:12] + "...",
                preview,
                tags,
                str(len(responses))
            )
        
        self.console.print(table)
        questionary.press_any_key_to_continue("\nPress any key...").ask()

    def compare_prompts(self):
        """Compare responses for a prompt"""
        self.show_header("Compare Responses")
        
        # Let them select a prompt
        self.select_existing_prompt()
        
        if self.current_prompt:
            self.step3_view_results()

    def show_statistics(self):
        """Show overall statistics"""
        self.show_header("Statistics")
        
        prompts = self.framework.list_prompts()
        responses = self.framework.list_responses()
        
        total_tokens = sum(r.token_usage.total if r.token_usage else 0 for r in responses)
        total_cost = sum(r.token_usage.cost_estimate if r.token_usage else 0 for r in responses)
        
        self.console.print(Panel(
            f"[bold]Overall Statistics[/bold]\n\n"
            f"Prompts Created: {len(prompts)}\n"
            f"Responses Generated: {len(responses)}\n"
            f"Total Tokens Used: {total_tokens:,}\n"
            f"Total Cost: ${total_cost:.2f}\n\n"
            f"Average Tokens per Response: {total_tokens // len(responses) if responses else 0:,}\n"
            f"Average Cost per Response: ${total_cost / len(responses):.4f}" if responses else "$0",
            title="📊 Statistics",
            border_style="cyan"
        ))
        
        questionary.press_any_key_to_continue("\nPress any key...").ask()

    def _run_single_folder_processor(self):
        """Run smart single-folder processing"""
        self.show_header("Smart Single-Folder Processing")
        
        self.console.print(Panel(
            "[bold cyan]Smart Single-Folder Auto-Detection[/bold cyan]\n\n"
            "This workflow scans a SINGLE folder for multiple versions of design documents\n"
            "and automatically consolidates them based on their Author/Model.\n\n"
            "[bold]Why this exists (The 'Option 1' Strategy):[/bold]\n"
            "When generating design documents, different AI models excel at different tasks:\n\n"
            "  • [bold green]Sonnet (Claude):[/bold green] Best at overall structure, comprehensive system design,\n"
            "    and architectural coherence. We use this as the [bold]BASE[/bold] document.\n\n"
            "  • [bold blue]GPT-5 (OpenAI):[/bold blue] Excellent at User Stories, Accessibility requirements,\n"
            "    and Configuration details. We extract these sections to patch the base.\n\n"
            "  • [bold magenta]Composer (Cursor):[/bold magenta] Great at implementation details like Animations,\n"
            "    CSS specific notes, and 'Definition of Done'. We extract these too.\n\n"
            "[bold]How it works:[/bold]\n"
            "  1. You point to a folder containing all versions (e.g., feature_1_sonnet.md, feature_1_gpt5.md).\n"
            "  2. The system groups files by Feature ID.\n"
            "  3. It detects authors from filenames (e.g., 'sonnet', 'gpt5', 'cursor').\n"
            "  4. It automatically builds the best combined version.",
            border_style="cyan"
        ))
        
        # Get directory
        doc_config = self._load_document_updater_config()
        default_dir = doc_config.get('last_processed_dir', '')
        
        directory_path = self._safe_path_input(
            "Directory containing all design documents:",
            default=default_dir,
            style=custom_style,
            only_directories=True
        )
        
        if not directory_path:
            return
            
        # Clean up input path
        directory_path = directory_path.strip().strip("'").strip('"')
        self.console.print(f"[dim]Debug: Checking path: {repr(directory_path)}[/dim]")
        
        directory = Path(directory_path).expanduser().resolve()
        
        if not directory.exists():
            self.console.print(f"[red]Directory not found: {directory}[/red]")
            self.console.print(f"[dim]Resolved from: {directory_path}[/dim]")
            questionary.press_any_key_to_continue().ask()
            return
            
        # Save as last processed
        doc_config['last_processed_dir'] = str(directory)
        self._save_document_updater_config(doc_config)
        
        # Import processor
        try:
            from ..document_updater import SingleFolderProcessor
        except ImportError as e:
            self.console.print(f"[red]Error importing processor: {e}[/red]")
            questionary.press_any_key_to_continue().ask()
            return
            
        # Load strategy from config if available
        strategy = doc_config.get("consolidation_strategy")
        
        # Run processing
        processor = SingleFolderProcessor(directory, directory / "consolidated", strategy=strategy)
        
        self.console.print("\n[cyan]Processing...[/cyan]\n")
        
        def on_progress(feature, status, current, total, success):
            color = "green" if success else "yellow"
            icon = "✓" if success else "⚠"
            self.console.print(f"  [{color}]{icon}[/] [{current}/{total}] Feature {feature}: {status}")
            
        results = processor.process_all(on_progress=on_progress)
        
        success_count = sum(1 for r in results if r.success)
        
        self.console.print()
        self.console.print(Panel(
            f"[bold]Processing Complete[/bold]\n\n"
            f"Total Processed: {len(results)}\n"
            f"Successful: {success_count}\n\n"
            f"[bold]Output Directory:[/bold] {directory}/consolidated",
            title="Summary",
            border_style="green"
        ))
        
        questionary.press_any_key_to_continue().ask()
