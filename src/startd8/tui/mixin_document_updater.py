"""DocumentUpdaterMixin: extracted from tui_improved.py ImprovedTUI (Pass B)."""

from ._shared import *  # noqa: F401,F403
from ..paths import default_config_dir

class DocumentUpdaterMixin:
    def enhance_prompt_file_menu(self):
        """Enhance a prompt file using Claude and prompt engineering best practices"""
        self.show_header("Enhance Prompt File")
        
        self.console.print(Panel(
            "[bold]Prompt Enhancement[/bold]\n\n"
            "Reads a file containing a prompt and uses Claude to enhance it\n"
            "based on prompt engineering best practices.\n\n"
            "[bold]Strategies:[/bold]\n"
            "• [cyan]comprehensive[/cyan] - Full enhancement with all techniques\n"
            "• [cyan]clarity[/cyan] - Focus on clear, unambiguous instructions\n"
            "• [cyan]structure[/cyan] - Add professional formatting\n"
            "• [cyan]context[/cyan] - Enrich with background and examples\n"
            "• [cyan]constraints[/cyan] - Add guardrails and boundaries\n"
            "• [cyan]minimal[/cyan] - Light touch preserving style",
            border_style="cyan"
        ))
        
        # Check for Anthropic API key
        api_key = self.key_manager.get_key("ANTHROPIC_API_KEY")
        if not api_key:
            import os
            api_key = os.getenv("ANTHROPIC_API_KEY")
        
        if not api_key:
            self.console.print("\n[yellow]⚠️  Anthropic API key required for enhancement.[/yellow]")
            self.console.print("[dim]Set via 'Manage API Keys' or ANTHROPIC_API_KEY env var[/dim]\n")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Get input file path
        input_path = self._safe_path_input(
            "Enter path to prompt file:",
            style=custom_style,
            only_directories=False
        )
        
        if not input_path:
            return
        
        from pathlib import Path
        input_file = Path(input_path).expanduser()
        
        if not input_file.exists():
            self.console.print(f"\n[red]File not found: {input_file}[/red]\n")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Select strategy
        strategy = questionary.select(
            "Select enhancement strategy:",
            choices=[
                "comprehensive - Full enhancement with all techniques",
                "clarity - Focus on clear instructions",
                "structure - Add professional formatting",
                "context - Enrich with examples",
                "constraints - Add guardrails",
                "minimal - Light touch improvements"
            ],
            style=custom_style
        ).ask()
        
        if not strategy:
            return
        
        strategy_value = strategy.split(" - ")[0]
        
        # Optional additional guidance
        guidance = questionary.text(
            "Additional guidance (optional):",
            style=custom_style,
        ).ask()
        
        # Get output path
        stem = input_file.stem
        suffix = input_file.suffix
        default_output = input_file.parent / f"{stem}_enhanced{suffix}"
        
        output_path = questionary.text(
            f"Output file path:",
            default=str(default_output),
            style=custom_style
        ).ask()
        
        if not output_path:
            return
        
        # Perform enhancement
        self.console.print(f"\n[cyan]🔧 Enhancing prompt with Claude...[/cyan]")
        
        try:
            from ..prompt_enhancer import PromptEnhancer, EnhancementStrategy
            
            with self.console.status("[cyan]Processing..."):
                enhancer = PromptEnhancer(api_key=api_key)
                result = enhancer.enhance_file(
                    input_path=input_file,
                    output_path=Path(output_path),
                    strategy=EnhancementStrategy(strategy_value),
                    additional_guidance=guidance if guidance else None,
                    include_metadata=True
                )
            
            # Show results
            self.console.print()
            self.console.print(Panel(
                f"[green]✅ Enhancement complete![/green]\n\n"
                f"[bold]Output:[/bold] {result.metadata.get('output_file', output_path)}\n"
                f"[bold]Model:[/bold] {result.model}\n"
                f"[bold]Time:[/bold] {result.response_time_ms}ms\n"
                f"[bold]Tokens:[/bold] {result.token_usage.total if result.token_usage else 'N/A'}\n"
                f"[bold]Cost:[/bold] ${result.token_usage.cost_estimate:.4f}" if result.token_usage else "",
                title="Enhancement Result",
                border_style="green"
            ))
            
            # Show comparison
            from rich.table import Table
            table = Table(title="Content Comparison", show_header=True)
            table.add_column("Metric", style="cyan")
            table.add_column("Original", justify="right")
            table.add_column("Enhanced", justify="right")
            table.add_column("Change", justify="right")
            
            orig_words = result.word_count_original
            enh_words = result.word_count_enhanced
            word_change = enh_words - orig_words
            word_pct = ((enh_words / orig_words) - 1) * 100 if orig_words > 0 else 0
            
            table.add_row("Words", str(orig_words), str(enh_words), f"{word_change:+d} ({word_pct:+.1f}%)")
            table.add_row("Characters", str(len(result.original_content)), str(len(result.enhanced_content)), f"{len(result.enhanced_content) - len(result.original_content):+d}")
            
            self.console.print()
            self.console.print(table)
            
            # Show changes summary if available
            if result.changes_summary:
                self.console.print()
                self.console.print(Panel(
                    result.changes_summary,
                    title="Changes Made",
                    border_style="blue"
                ))
            
        except ImportError as e:
            self.console.print(f"\n[red]Error: {e}[/red]")
            self.console.print("[yellow]Ensure anthropic is installed: pip install anthropic[/yellow]")
        except Exception as e:
            self.console.print(f"\n[red]Enhancement failed: {e}[/red]")
        
        self.console.print()
        questionary.press_any_key_to_continue().ask()

    def document_updater_menu(self):
        """Document Updater - Consolidate documents from multiple sources"""
        self.show_header("Document Updater")
        
        self.console.print(Panel(
            "[bold cyan]Document Updater[/bold cyan]\n\n"
            "Consolidate documents from multiple AI sources by:\n"
            "  1. Reading a BASE document (e.g., Sonnet 4.5's version)\n"
            "  2. Patching in specific sections from other sources\n"
            "  3. Creating a NEW consolidated document\n\n"
            "[bold]Important:[/bold] Original files are NEVER modified.\n"
            "Only new consolidated files are created.\n\n"
            "[dim]Example: Merge Feature Design docs from Sonnet, GPT-5, and Composer[/dim]",
            border_style="cyan"
        ))
        
        action = questionary.select(
            "What would you like to do?",
            choices=[
                "🔄 Run Feature Design Consolidation (Default Workflow)",
                "📂 Smart Single-Folder Processing (Auto-Detect)",
                "📝 Custom Single Document Consolidation",
                "📁 Process Directory (Async Sequential)",
                "⚙️  Configure Source Directories",
                "← Back to Main Menu"
            ],
            style=custom_style
        ).ask()
        
        if not action or "Back" in action:
            return
        
        if "Feature Design" in action:
            self._run_feature_design_workflow()
        elif "Smart Single-Folder" in action:
            self._run_single_folder_processor()
        elif "Custom Single" in action:
            self._run_custom_consolidation()
        elif "Process Directory" in action:
            self._run_async_directory_processing()
        elif "Configure" in action:
            self._configure_document_sources()

    def _run_feature_design_workflow(self):
        """Run the default feature design consolidation workflow"""
        self.show_header("Feature Design Consolidation")
        
        # Get or create source directory configuration
        doc_config = self._load_document_updater_config()
        
        if not doc_config.get('source_dirs'):
            self.console.print("[yellow]Source directories not configured.[/yellow]\n")
            configure = questionary.confirm(
                "Configure source directories now?",
                default=True,
                style=custom_style
            ).ask()
            
            if configure:
                self._configure_document_sources()
                doc_config = self._load_document_updater_config()
            else:
                return
        
        # Show current configuration
        self.console.print(Panel(
            f"[bold]Source Directories:[/bold]\n"
            f"  Base (Sonnet 4.5): {doc_config.get('source_dirs', {}).get('sonnet_45', '[not set]')}\n"
            f"  GPT-5: {doc_config.get('source_dirs', {}).get('gpt5', '[not set]')}\n"
            f"  Composer: {doc_config.get('source_dirs', {}).get('composer', '[not set]')}\n\n"
            f"[bold]Output Directory:[/bold] {doc_config.get('output_dir', '[not set]')}\n\n"
            "[bold]Default Patches:[/bold]\n"
            "  From GPT-5: User Stories, Accessibility, Config\n"
            "  From Composer: CSS Animations, Notes, Definition of Done",
            border_style="cyan",
            title="Configuration"
        ))
        
        # Select which batches to run
        self.console.print("\n[bold]Batch Processing Order:[/bold]")
        self.console.print("  Batch 1: Feature 2 (Initials Entry)")
        self.console.print("  Batch 2: Features 3 & 4 (Trebuchet visual) - parallel")
        self.console.print("  Batch 3: Features 5 & 6 (Game progression) - parallel")
        self.console.print("  Batch 4: Features 7 & 8 (Power-ups & Messages) - parallel")
        self.console.print()
        
        batch_choice = questionary.select(
            "Which batches to run?",
            choices=[
                "🚀 Run ALL Batches (Features 2-8)",
                "📦 Run Single Batch",
                "🎯 Run Single Feature (Smart Merge)",
                "← Cancel"
            ],
            style=custom_style
        ).ask()
        
        if not batch_choice or "Cancel" in batch_choice:
            return
        
        try:
            from ..document_updater import (
                DocumentUpdaterWorkflow,
                get_default_feature_batches,
                BatchConfig
            )
        except ImportError as e:
            self.console.print(f"[red]Error importing document updater: {e}[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Initialize workflow
        source_dirs = doc_config.get('source_dirs', {})
        output_dir = doc_config.get('output_dir', '')
        
        if not output_dir:
            self.console.print("[red]Output directory not configured.[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        workflow = DocumentUpdaterWorkflow(
            base_dir=Path(source_dirs.get('sonnet_45', '.')),
            output_dir=Path(output_dir),
            source_dirs={k: Path(v) for k, v in source_dirs.items()}
        )
        
        # Determine batches to run
        batches = get_default_feature_batches()
        
        if "Single Batch" in batch_choice:
            batch_options = [f"Batch {b.batch_number}: {b.name}" for b in batches]
            batch_options.append("← Cancel")
            
            selected = questionary.select(
                "Select batch:",
                choices=batch_options,
                style=custom_style
            ).ask()
            
            if not selected or "Cancel" in selected:
                return
            
            batch_num = int(selected.split(":")[0].replace("Batch ", ""))
            batches = [b for b in batches if b.batch_number == batch_num]
        
        elif "Single Feature" in batch_choice:
            feature_num = questionary.text(
                "Feature number:",
                style=custom_style
            ).ask()
            
            try:
                fn = int(feature_num)
            except ValueError:
                self.console.print("[red]Invalid feature number[/red]")
                questionary.press_any_key_to_continue().ask()
                return
            
            # Customization Option
            customize = questionary.confirm(
                "Customize extraction rules? (Grep/Keywords)",
                default=False,
                style=custom_style
            ).ask()
            
            if customize:
                gpt5_keywords = questionary.text(
                    "GPT-5 keywords (comma-separated):",
                    default="User Stories, Accessibility, Config",
                    style=custom_style
                ).ask()
                
                composer_keywords = questionary.text(
                    "Composer keywords (comma-separated):",
                    default="Animations, Notes, Definition of Done",
                    style=custom_style
                ).ask()
                
                # Create custom config directly
                custom_patches = [
                    {
                        "source_name": "gpt5",
                        "sections": [s.strip() for s in gpt5_keywords.split(",") if s.strip()]
                    },
                    {
                        "source_name": "composer",
                        "sections": [s.strip() for s in composer_keywords.split(",") if s.strip()]
                    }
                ]
                
                self.console.print("\n[cyan]Running custom consolidation...[/cyan]")
                try:
                    config = workflow.create_feature_config(fn, patches=custom_patches)
                    
                    # Manual run
                    from ..document_updater import DocumentConsolidator
                    consolidator = DocumentConsolidator(config)
                    result = consolidator.consolidate()
                    
                    # Show results directly
                    self.console.print()
                    if result.success:
                        self.console.print(Panel(
                            f"[green]✓ Consolidation successful![/green]\n\n"
                            f"[bold]Output:[/bold] {result.output_path}\n"
                            f"[bold]Patched:[/bold] {len(result.sections_patched)}\n"
                            f"[bold]Not Found:[/bold] {len(result.sections_not_found)}",
                            title="Success",
                            border_style="green"
                        ))
                        if result.sections_not_found:
                            self.console.print("[yellow]Sections not found:[/yellow]")
                            for s in result.sections_not_found:
                                self.console.print(f"  ✗ {s}")
                    else:
                        self.console.print(f"[red]Failed: {result.error}[/red]")
                    
                    questionary.press_any_key_to_continue().ask()
                    return
                except Exception as e:
                    self.console.print(f"[red]Error running custom consolidation: {e}[/red]")
                    return

            # Standard path for single feature (using defaults)
            batches = [BatchConfig(
                batch_number=1,
                name=f"Feature {fn}",
                items=[str(fn)],
                parallel=False
            )]
        
        # Run the workflow
        self.console.print("\n[cyan]Running Document Updater...[/cyan]\n")
        
        def on_batch_start(batch):
            self.console.print(f"[bold]Starting Batch {batch.batch_number}: {batch.name}[/bold]")
        
        def on_batch_complete(batch, results):
            success_count = sum(1 for r in results.values() if r.success)
            self.console.print(f"  [green]✓ Completed: {success_count}/{len(results)} successful[/green]\n")
        
        def on_progress(batch_num, item, current, total):
            self.console.print(f"  Processing Feature {item}... ({current}/{total})")
        
        all_results = workflow.run_all_batches(
            batches,
            on_batch_start=on_batch_start,
            on_batch_complete=on_batch_complete,
            on_progress=on_progress
        )
        
        # Show summary
        self.console.print()
        self._show_consolidation_results(all_results)
        
        questionary.press_any_key_to_continue().ask()

    def _show_consolidation_results(self, all_results: Dict):
        """Show summary of consolidation results"""
        from rich.table import Table
        
        table = Table(title="Consolidation Results", show_header=True, show_lines=True)
        table.add_column("Feature", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Sections Patched", justify="right")
        table.add_column("Not Found", justify="right")
        table.add_column("Output File / Error", overflow="fold")
        
        total_success = 0
        total_failed = 0
        
        # Flatten results if nested
        flat_results = {}
        for key, val in all_results.items():
            if isinstance(val, dict):
                for k, v in val.items():
                    flat_results[f"Batch {key} - {k}"] = v
            else:
                flat_results[key] = val

        for feature_id, result in sorted(flat_results.items()):
            if result.success:
                total_success += 1
                status = "[green]✓ Success[/green]"
                output = str(result.output_path) if result.output_path else "-"
            else:
                total_failed += 1
                status = f"[red]✗ Failed[/red]"
                output = result.error if result.error else "Unknown Error"
            
            table.add_row(
                str(feature_id),
                status,
                str(len(result.sections_patched)),
                str(len(result.sections_not_found)),
                output
            )
        
        self.console.print(table)
        self.console.print()
        self.console.print(f"[bold]Total:[/bold] {total_success} successful, {total_failed} failed")

    def _run_custom_consolidation(self):
        """Run a custom single document consolidation"""
        self.show_header("Custom Document Consolidation")
        
        self.console.print(Panel(
            "[bold]Custom Consolidation[/bold]\n\n"
            "Create a consolidated document from:\n"
            "  1. A base document (copied entirely)\n"
            "  2. Sections patched from other documents\n\n"
            "[dim]Output is always a NEW file.[/dim]",
            border_style="cyan"
        ))
        
        # Get base document
        base_path = self._safe_path_input(
            "Base document path:",
            style=custom_style,
            only_directories=False
        )
        
        if not base_path:
            return
        
        base_file = Path(base_path).expanduser().resolve()
        if not base_file.exists():
            self.console.print(f"[red]File not found: {base_file}[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Show sections in base document
        try:
            from ..document_updater import MarkdownSectionExtractor
        except ImportError as e:
            self.console.print(f"[red]Error: {e}[/red]")
            return
        
        content = base_file.read_text(encoding='utf-8')
        extractor = MarkdownSectionExtractor(content, str(base_file), "base")
        sections = extractor.list_sections()
        
        self.console.print(f"\n[bold]Sections in base document:[/bold]")
        for s in sections[:15]:  # Show first 15
            self.console.print(f"  • {s}")
        if len(sections) > 15:
            self.console.print(f"  ... and {len(sections) - 15} more")
        
        # Get patch sources
        self.console.print("\n[bold]Add patch sources[/bold]")
        self.console.print("[dim]Enter documents to extract sections from. Empty to finish.[/dim]\n")
        
        patches = []
        while True:
            source_path = self._safe_path_input(
                "Patch source document (empty to finish):",
                style=custom_style,
                only_directories=False
            )
            
            if not source_path:
                break
            
            source_file = Path(source_path).expanduser().resolve()
            if not source_file.exists():
                self.console.print(f"[yellow]File not found: {source_file}[/yellow]")
                continue
            
            source_name = questionary.text(
                "Source name (for attribution):",
                default=source_file.stem,
                style=custom_style
            ).ask()
            
            # Show sections in source
            source_content = source_file.read_text(encoding='utf-8')
            source_extractor = MarkdownSectionExtractor(source_content, str(source_file), source_name)
            source_sections = source_extractor.list_sections()
            
            self.console.print(f"\n[dim]Sections in {source_name}:[/dim]")
            for s in source_sections[:10]:
                self.console.print(f"  • {s}")
            
            sections_to_patch = questionary.text(
                "Sections to patch (comma-separated):",
                style=custom_style,
            ).ask()
            
            if sections_to_patch:
                section_list = [s.strip() for s in sections_to_patch.split(",")]
                patches.append({
                    "source_name": source_name,
                    "source_path": source_file,
                    "sections": section_list
                })
                self.console.print(f"[green]✓ Added {len(section_list)} section(s) from {source_name}[/green]\n")
        
        if not patches:
            self.console.print("[yellow]No patches configured. Cancelling.[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Get output path
        default_output = base_file.parent / f"{base_file.stem}_consolidated{base_file.suffix}"
        output_path = questionary.text(
            "Output file path:",
            default=str(default_output),
            style=custom_style
        ).ask()
        
        if not output_path:
            return
        
        # Run consolidation
        from ..document_updater import ConsolidationConfig, PatchRule, DocumentConsolidator
        
        patch_rules = [
            PatchRule(
                source_name=p["source_name"],
                source_path=p["source_path"],
                sections=p["sections"]
            )
            for p in patches
        ]
        
        config = ConsolidationConfig(
            name="Custom Consolidation",
            base_source_name="base",
            base_path=base_file,
            patches=patch_rules,
            output_path=Path(output_path)
        )
        
        self.console.print("\n[cyan]Running consolidation...[/cyan]")
        
        consolidator = DocumentConsolidator(config)
        result = consolidator.consolidate()
        
        if result.success:
            self.console.print(Panel(
                f"[green]✓ Consolidation successful![/green]\n\n"
                f"[bold]Output:[/bold] {result.output_path}\n"
                f"[bold]Base sections:[/bold] {result.base_sections}\n"
                f"[bold]Final sections:[/bold] {result.final_sections}\n"
                f"[bold]Sections patched:[/bold] {len(result.sections_patched)}\n"
                f"[bold]Sections not found:[/bold] {len(result.sections_not_found)}",
                title="Success",
                border_style="green"
            ))
            
            if result.sections_not_found:
                self.console.print("\n[yellow]Sections not found:[/yellow]")
                for s in result.sections_not_found:
                    self.console.print(f"  ✗ {s}")
        else:
            self.console.print(f"[red]Consolidation failed: {result.error}[/red]")
        
        questionary.press_any_key_to_continue().ask()

    def _run_async_directory_processing(self):
        """Run async sequential processing on a directory of design documents"""
        self.show_header("Async Directory Processing")
        
        self.console.print(Panel(
            "[bold cyan]Async Sequential Directory Processing[/bold cyan]\n\n"
            "Process all design documents in a directory sequentially.\n\n"
            "[bold]How it works:[/bold]\n"
            "  1. Scans directory for design documents\n"
            "  2. Uses filename heuristics (feature, design, spec, etc.)\n"
            "  3. Checks meta documents (DESIGN_DOCUMENTS_SUMMARY.md) if present\n"
            "  4. Ignores files with 'COMPARISON' in name\n"
            "  5. Processes documents one at a time (sequential)\n"
            "  6. Creates NEW consolidated files (originals untouched)\n\n"
            "[bold yellow]Important:[/bold yellow]\n"
            "  The directory should contain ONLY design documents.\n"
            "  Other files will be ignored based on filename patterns.",
            border_style="cyan"
        ))
        
        # Get directory path
        doc_config = self._load_document_updater_config()
        default_dir = doc_config.get('last_processed_dir', '')
        
        directory_path = self._safe_path_input(
            "Directory containing design documents:",
            default=default_dir,
            style=custom_style,
            only_directories=True
        )
        
        if not directory_path:
            return
        
        directory = Path(directory_path).expanduser().resolve()
        
        if not directory.exists():
            self.console.print(f"[red]Directory not found: {directory}[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Save as last processed
        doc_config['last_processed_dir'] = str(directory)
        self._save_document_updater_config(doc_config)
        
        # Detect design documents
        try:
            from ..document_updater import DesignDocumentDetector
        except ImportError as e:
            self.console.print(f"[red]Error: {e}[/red]")
            return
        
        detector = DesignDocumentDetector(directory)
        design_docs = detector.find_design_documents()
        
        if not design_docs:
            self.console.print("\n[yellow]No design documents found in directory.[/yellow]")
            self.console.print("[dim]Looking for files with: feature, design, spec, plan, etc.[/dim]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Show detected documents
        self.console.print(f"\n[bold]Found {len(design_docs)} design document(s):[/bold]")
        for doc in design_docs:
            self.console.print(f"  📄 {doc.name}")
        
        # Check for meta documents
        meta_docs = []
        for meta_name in ["DESIGN_DOCUMENTS_SUMMARY.md", "DESIGN_DOCS_INDEX.md"]:
            meta_path = directory / meta_name
            if meta_path.exists():
                meta_docs.append(meta_name)
        
        if meta_docs:
            self.console.print(f"\n[green]✓ Found meta document(s): {', '.join(meta_docs)}[/green]")
            self.console.print("[dim]Using meta documents to identify design docs[/dim]")
        
        # Confirm processing
        confirm = questionary.confirm(
            f"\nProcess {len(design_docs)} document(s)?",
            default=True,
            style=custom_style
        ).ask()
        
        if not confirm:
            return
        
        # Get source directories
        source_dirs = doc_config.get('source_dirs', {})
        if not source_dirs:
            self.console.print("\n[yellow]Source directories not configured.[/yellow]")
            configure = questionary.confirm(
                "Configure source directories now?",
                default=True,
                style=custom_style
            ).ask()
            
            if configure:
                self._configure_document_sources()
                doc_config = self._load_document_updater_config()
                source_dirs = doc_config.get('source_dirs', {})
            else:
                return
        
        # Get output directory
        output_dir = doc_config.get('output_dir', '')
        if not output_dir:
            output_dir = self._safe_path_input(
                "Output directory for consolidated files:",
                style=custom_style,
                only_directories=True
            )
            
            if not output_dir:
                return
            
            doc_config['output_dir'] = str(Path(output_dir).expanduser().resolve())
            self._save_document_updater_config(doc_config)
        
        # Initialize async updater
        try:
            from ..document_updater import AsyncDocumentUpdater
            import asyncio
        except ImportError as e:
            self.console.print(f"[red]Error: {e}[/red]")
            return
        
        # The directory itself contains the BASE documents
        # Determine base source name (default to sonnet_45, but can be inferred)
        base_source = doc_config.get('base_source', 'sonnet_45')
        
        # If directory matches a configured source, use that
        directory_str = str(directory)
        for source_name, source_path in source_dirs.items():
            if directory_str == str(Path(source_path)):
                base_source = source_name
                break
        
        updater = AsyncDocumentUpdater(
            base_source_name=base_source,
            output_dir=Path(output_dir),
            source_dirs={k: Path(v) for k, v in source_dirs.items()}
        )
        
        # Progress tracking
        processed = []
        failed = []
        
        def on_progress(current, total, filename, result):
            if result.success:
                processed.append((filename, result))
                self.console.print(
                    f"  [green]✓[/green] [{current}/{total}] {filename} → {result.output_path.name if result.output_path else 'N/A'}"
                )
            else:
                failed.append((filename, result))
                self.console.print(
                    f"  [red]✗[/red] [{current}/{total}] {filename} - {result.error or 'Failed'}"
                )
        
        def on_complete(all_results):
            pass  # Summary shown below
        
        # Run async processing
        self.console.print("\n[cyan]Processing documents sequentially...[/cyan]\n")
        
        try:
            results = asyncio.run(
                updater.process_directory(
                    directory,
                    on_progress=on_progress,
                    on_complete=on_complete
                )
            )
        except Exception as e:
            self.console.print(f"\n[red]Processing failed: {e}[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Show summary
        self.console.print()
        self.console.print(Panel(
            f"[bold]Processing Complete[/bold]\n\n"
            f"[green]✓ Successful:[/green] {len(processed)}\n"
            f"[red]✗ Failed:[/red] {len(failed)}\n"
            f"[bold]Total:[/bold] {len(results)}\n\n"
            f"[bold]Output Directory:[/bold] {output_dir}",
            title="Summary",
            border_style="green" if not failed else "yellow"
        ))
        
        if failed:
            self.console.print("\n[yellow]Failed Documents:[/yellow]")
            for filename, result in failed:
                self.console.print(f"  ✗ {filename}: {result.error or 'Unknown error'}")
        
        questionary.press_any_key_to_continue().ask()

    def _configure_document_sources(self):
        """Configure source directories for document updater"""
        self.show_header("Configure Document Sources")
        
        doc_config = self._load_document_updater_config()
        
        self.console.print(Panel(
            "[bold]Configure Source Directories[/bold]\n\n"
            "Set the directories where each AI agent's documents are stored.\n\n"
            "[bold]Required sources:[/bold]\n"
            "  • sonnet_45 - Base documents (Sonnet 4.5)\n"
            "  • gpt5 - GPT-5 documents\n"
            "  • composer - Composer documents\n\n"
            "[bold]Output directory:[/bold]\n"
            "  Where consolidated documents will be saved (NEW files only)",
            border_style="cyan"
        ))
        
        source_dirs = doc_config.get('source_dirs', {})
        
        # Configure each source
        sources = [
            ("sonnet_45", "Sonnet 4.5 (BASE)"),
            ("gpt5", "GPT-5"),
            ("composer", "Composer")
        ]
        
        for source_id, source_name in sources:
            current = source_dirs.get(source_id, '')
            path = self._safe_path_input(
                f"{source_name} directory:",
                default=current,
                style=custom_style,
                only_directories=True
            )
            
            if path:
                source_dirs[source_id] = str(Path(path).expanduser().resolve())
        
        # Output directory
        current_output = doc_config.get('output_dir', '')
        output_dir = self._safe_path_input(
            "Output directory:",
            default=current_output,
            style=custom_style,
            only_directories=True
        )
        
        if output_dir:
            doc_config['output_dir'] = str(Path(output_dir).expanduser().resolve())
        
        doc_config['source_dirs'] = source_dirs
        self._save_document_updater_config(doc_config)
        
        self.console.print("\n[green]✓ Configuration saved![/green]")
        questionary.press_any_key_to_continue().ask()

    def _load_document_updater_config(self) -> Dict[str, Any]:
        """Load document updater configuration"""
        config_file = (self.storage_dir or default_config_dir()) / "document_updater.json"
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {'source_dirs': {}, 'output_dir': ''}

    def _save_document_updater_config(self, config: Dict[str, Any]):
        """Save document updater configuration"""
        config_file = (self.storage_dir or default_config_dir()) / "document_updater.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
