"""
Document Updater - Consolidate documents from multiple AI sources

This module provides a workflow for:
1. Reading a base document
2. Extracting specific sections from other source documents
3. Creating a NEW consolidated document (never modifies originals)
4. Batch processing with dependency ordering
5. Asynchronous directory-based batch processing
"""

import re
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)

# Optional LangChain integration
try:
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_anthropic import ChatAnthropic
    HAS_LANGCHAIN = True
except ImportError:
    HAS_LANGCHAIN = False


class BatchStatus(str, Enum):
    """Status of a batch operation"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SectionExtract:
    """Extracted section from a document"""
    heading: str
    content: str
    source_file: str
    source_name: str
    line_start: int
    line_end: int


@dataclass
class PatchRule:
    """Rule for patching sections from a source"""
    source_name: str
    source_path: Path
    sections: List[str]  # Section headings to extract
    action: str = "replace_or_append"  # replace_or_append, append_only, replace_only


@dataclass
class ConsolidationConfig:
    """Configuration for document consolidation"""
    name: str
    base_source_name: str
    base_path: Path
    patches: List[PatchRule]
    output_path: Path
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BatchConfig:
    """Configuration for batch processing"""
    batch_number: int
    name: str
    items: List[str]  # Feature identifiers
    depends_on: Optional[int] = None  # Previous batch number
    parallel: bool = True


@dataclass
class ConsolidationResult:
    """Result of a consolidation operation"""
    success: bool
    output_path: Optional[Path]
    sections_patched: List[str]
    sections_not_found: List[str]
    base_sections: int
    final_sections: int
    timestamp: datetime = field(default_factory=datetime.utcnow)
    error: Optional[str] = None


class MarkdownSectionExtractor:
    """Extract sections from markdown documents by heading"""
    
    # Regex to match markdown headings (## or ###)
    HEADING_PATTERN = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
    
    def __init__(self, content: str, source_file: str = "", source_name: str = ""):
        self.content = content
        self.source_file = source_file
        self.source_name = source_name
        self.lines = content.split('\n')
        self._sections = None
    
    def _parse_sections(self) -> Dict[str, SectionExtract]:
        """Parse document into sections by heading"""
        if self._sections is not None:
            return self._sections
        
        sections = {}
        current_heading = None
        current_level = 0
        current_start = 0
        current_content_lines = []
        
        for i, line in enumerate(self.lines):
            match = self.HEADING_PATTERN.match(line)
            
            if match:
                # Save previous section
                if current_heading:
                    content = '\n'.join(current_content_lines).strip()
                    sections[current_heading] = SectionExtract(
                        heading=current_heading,
                        content=content,
                        source_file=self.source_file,
                        source_name=self.source_name,
                        line_start=current_start,
                        line_end=i - 1
                    )
                
                # Start new section
                level = len(match.group(1))
                heading = match.group(2).strip()
                current_heading = heading
                current_level = level
                current_start = i
                current_content_lines = [line]
            elif current_heading:
                current_content_lines.append(line)
        
        # Save last section
        if current_heading:
            content = '\n'.join(current_content_lines).strip()
            sections[current_heading] = SectionExtract(
                heading=current_heading,
                content=content,
                source_file=self.source_file,
                source_name=self.source_name,
                line_start=current_start,
                line_end=len(self.lines) - 1
            )
        
        self._sections = sections
        return sections
    
    def get_section(self, heading: str) -> Optional[SectionExtract]:
        """Get a specific section by heading (case-insensitive partial match)"""
        sections = self._parse_sections()
        
        # Try exact match first
        if heading in sections:
            return sections[heading]
        
        # Try case-insensitive match
        heading_lower = heading.lower()
        for key, section in sections.items():
            if key.lower() == heading_lower:
                return section
        
        # Try partial match (heading contains search term)
        for key, section in sections.items():
            if heading_lower in key.lower():
                return section
        
        return None
    
    def get_sections(self, headings: List[str]) -> Dict[str, Optional[SectionExtract]]:
        """Get multiple sections by heading"""
        return {h: self.get_section(h) for h in headings}
    
    def list_sections(self) -> List[str]:
        """List all section headings"""
        return list(self._parse_sections().keys())


class DocumentConsolidator:
    """Consolidate documents from multiple sources"""
    
    def __init__(self, config: ConsolidationConfig):
        self.config = config
        self.results: List[Tuple[str, Optional[SectionExtract]]] = []
    
    def consolidate(self) -> ConsolidationResult:
        """
        Perform document consolidation.
        
        IMPORTANT: This creates a NEW file and never modifies the original.
        """
        sections_patched = []
        sections_not_found = []
        
        try:
            logger.debug(f"Consolidating Base: {self.config.base_path}")
            # Step 1: Read base document
            if not self.config.base_path.exists():
                logger.error(f"Base file not found at {self.config.base_path}")
                return ConsolidationResult(
                    success=False,
                    output_path=None,
                    sections_patched=[],
                    sections_not_found=[],
                    base_sections=0,
                    final_sections=0,
                    error=f"Base file not found: {self.config.base_path}"
                )
            
            base_content = self.config.base_path.read_text(encoding='utf-8')
            base_extractor = MarkdownSectionExtractor(
                base_content, 
                str(self.config.base_path),
                self.config.base_source_name
            )
            base_sections_count = len(base_extractor.list_sections())
            
            # Start with base content
            consolidated_content = base_content
            
            # Step 2: Extract and patch sections from each source
            for patch in self.config.patches:
                logger.debug(f"Patching from: {patch.source_path} ({patch.source_name})")
                if not patch.source_path.exists():
                    logger.warning(f"Patch source not found: {patch.source_path}")
                    for section in patch.sections:
                        sections_not_found.append(f"{patch.source_name}:{section}")
                    continue
                
                source_content = patch.source_path.read_text(encoding='utf-8')
                source_extractor = MarkdownSectionExtractor(
                    source_content,
                    str(patch.source_path),
                    patch.source_name
                )
                
                for section_heading in patch.sections:
                    extracted = source_extractor.get_section(section_heading)
                    
                    if extracted:
                        # Apply patch
                        consolidated_content = self._apply_patch(
                            consolidated_content,
                            extracted,
                            patch.action
                        )
                        sections_patched.append(f"{patch.source_name}:{section_heading}")
                        self.results.append((section_heading, extracted))
                    else:
                        sections_not_found.append(f"{patch.source_name}:{section_heading}")
                        self.results.append((section_heading, None))
            
            # Step 3: Add consolidation metadata header
            metadata_header = self._create_metadata_header(sections_patched, sections_not_found)
            final_content = metadata_header + consolidated_content
            
            # Step 4: Write NEW file (never modify original)
            self.config.output_path.parent.mkdir(parents=True, exist_ok=True)
            self.config.output_path.write_text(final_content, encoding='utf-8')
            
            # Count final sections
            final_extractor = MarkdownSectionExtractor(final_content, "", "")
            final_sections_count = len(final_extractor.list_sections())
            
            return ConsolidationResult(
                success=True,
                output_path=self.config.output_path,
                sections_patched=sections_patched,
                sections_not_found=sections_not_found,
                base_sections=base_sections_count,
                final_sections=final_sections_count
            )
            
        except Exception as e:
            return ConsolidationResult(
                success=False,
                output_path=None,
                sections_patched=sections_patched,
                sections_not_found=sections_not_found,
                base_sections=0,
                final_sections=0,
                error=str(e)
            )
    
    def _apply_patch(
        self, 
        content: str, 
        section: SectionExtract, 
        action: str
    ) -> str:
        """Apply a section patch to the content"""
        extractor = MarkdownSectionExtractor(content, "", "")
        existing = extractor.get_section(section.heading)
        
        if existing and action in ("replace_or_append", "replace_only"):
            # Replace existing section
            lines = content.split('\n')
            before = '\n'.join(lines[:existing.line_start])
            after = '\n'.join(lines[existing.line_end + 1:])
            
            # Add source attribution
            attributed_content = self._add_attribution(section)
            return f"{before}\n{attributed_content}\n{after}"
        
        elif not existing and action in ("replace_or_append", "append_only"):
            # Append at end
            attributed_content = self._add_attribution(section)
            return f"{content}\n\n{attributed_content}"
        
        return content
    
    def _add_attribution(self, section: SectionExtract) -> str:
        """Add source attribution comment to section"""
        # Add a small comment indicating source
        attribution = f"<!-- Patched from: {section.source_name} -->"
        return f"{attribution}\n{section.content}"
    
    def _create_metadata_header(
        self, 
        patched: List[str], 
        not_found: List[str]
    ) -> str:
        """Create metadata header for consolidated document"""
        lines = [
            "<!--",
            "DOCUMENT CONSOLIDATION METADATA",
            f"Generated: {datetime.utcnow().isoformat()}",
            f"Base: {self.config.base_source_name} ({self.config.base_path.name})",
            "",
            "Sections Patched:",
        ]
        
        for p in patched:
            lines.append(f"  ✓ {p}")
        
        if not_found:
            lines.append("")
            lines.append("Sections Not Found:")
            for nf in not_found:
                lines.append(f"  ✗ {nf}")
        
        lines.extend(["-->", "", ""])
        
        return '\n'.join(lines)


class DocumentUpdaterWorkflow:
    """
    Document Updater Workflow - Orchestrates batch document consolidation.
    
    This is the main workflow class that:
    1. Manages batch processing with dependencies
    2. Coordinates multiple consolidations
    3. Tracks progress and results
    """
    
    def __init__(
        self,
        base_dir: Path,
        output_dir: Path,
        source_dirs: Dict[str, Path]
    ):
        """
        Initialize workflow.
        
        Args:
            base_dir: Base directory for source documents
            output_dir: Directory for consolidated outputs (NEW files only)
            source_dirs: Mapping of source names to directories
                         e.g., {"sonnet_45": Path(...), "gpt5": Path(...)}
        """
        self.base_dir = Path(base_dir)
        self.output_dir = Path(output_dir)
        self.source_dirs = {k: Path(v) for k, v in source_dirs.items()}
        
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.batch_results: Dict[int, Dict[str, ConsolidationResult]] = {}
    
    def create_feature_config(
        self,
        feature_number: int,
        base_source: str = "sonnet_45",
        patches: Optional[List[Dict[str, Any]]] = None
    ) -> ConsolidationConfig:
        """
        Create consolidation config for a specific feature.
        
        Default patches are configured for the Feature Design workflow:
        - GPT-5: User Stories, Accessibility, Config
        - Composer: Animations, Notes, Definition of Done
        """
        if patches is None:
            patches = [
                {
                    "source_name": "gpt5",
                    "sections": ["User Stories", "Accessibility", "Config", "Configuration"]
                },
                {
                    "source_name": "composer",
                    "sections": ["CSS Animations", "Animations", "Notes", "Definition of Done"]
                }
            ]
        
        # Build patch rules
        patch_rules = []
        for patch_def in patches:
            source_name = patch_def["source_name"]
            source_dir = self.source_dirs.get(source_name)
            
            if source_dir:
                # Try common file naming patterns
                possible_files = [
                    f"FEATURE_{feature_number}_DESIGN.md",
                    f"FEATURE{feature_number}_DESIGN.md",
                    f"feature_{feature_number}_design.md",
                    f"Feature{feature_number}.md",
                ]
                
                source_path = None
                for filename in possible_files:
                    test_path = source_dir / filename
                    if test_path.exists():
                        source_path = test_path
                        break
                
                if source_path is None:
                    source_path = source_dir / f"FEATURE_{feature_number}_DESIGN.md"
                
                patch_rules.append(PatchRule(
                    source_name=source_name,
                    source_path=source_path,
                    sections=patch_def["sections"]
                ))
        
        # Base path
        base_dir = self.source_dirs.get(base_source, self.base_dir)
        base_path = base_dir / f"FEATURE_{feature_number}_DESIGN.md"
        
        # Output path (NEW file)
        output_path = self.output_dir / f"FEATURE_{feature_number}_CONSOLIDATED.md"
        
        return ConsolidationConfig(
            name=f"Feature {feature_number} Consolidation",
            base_source_name=base_source,
            base_path=base_path,
            patches=patch_rules,
            output_path=output_path,
            metadata={"feature_number": feature_number}
        )
    
    def run_batch(
        self, 
        batch: BatchConfig,
        on_progress: Optional[callable] = None
    ) -> Dict[str, ConsolidationResult]:
        """
        Run a batch of consolidations.
        
        Args:
            batch: Batch configuration
            on_progress: Optional callback for progress updates
            
        Returns:
            Dict mapping feature IDs to results
        """
        results = {}
        
        for i, item in enumerate(batch.items):
            if on_progress:
                on_progress(batch.batch_number, item, i + 1, len(batch.items))
            
            try:
                feature_num = int(item.replace("Feature ", "").strip())
            except ValueError:
                feature_num = int(item)
            
            config = self.create_feature_config(feature_num)
            consolidator = DocumentConsolidator(config)
            result = consolidator.consolidate()
            results[item] = result
        
        self.batch_results[batch.batch_number] = results
        return results
    
    def run_all_batches(
        self,
        batches: List[BatchConfig],
        on_batch_start: Optional[callable] = None,
        on_batch_complete: Optional[callable] = None,
        on_progress: Optional[callable] = None
    ) -> Dict[int, Dict[str, ConsolidationResult]]:
        """
        Run all batches in order, respecting dependencies.
        
        Args:
            batches: List of batch configurations
            on_batch_start: Callback when batch starts
            on_batch_complete: Callback when batch completes
            on_progress: Callback for individual item progress
            
        Returns:
            Dict mapping batch numbers to their results
        """
        # Sort batches by number to ensure order
        sorted_batches = sorted(batches, key=lambda b: b.batch_number)
        
        for batch in sorted_batches:
            # Check dependencies
            if batch.depends_on is not None:
                dep_results = self.batch_results.get(batch.depends_on, {})
                if not dep_results:
                    # Dependency not completed, skip
                    continue
                
                # Check if dependency had failures
                dep_failures = [r for r in dep_results.values() if not r.success]
                if dep_failures:
                    # Could choose to skip or warn
                    pass
            
            if on_batch_start:
                on_batch_start(batch)
            
            results = self.run_batch(batch, on_progress)
            
            if on_batch_complete:
                on_batch_complete(batch, results)
        
        return self.batch_results


# =============================================================================
# Default Configuration for Feature Design Consolidation
# =============================================================================

def get_default_feature_batches() -> List[BatchConfig]:
    """Get default batch configuration for feature design consolidation"""
    return [
        BatchConfig(
            batch_number=1,
            name="Feature 2 (Initials Entry)",
            items=["2"],
            depends_on=None,  # Feature 1 should already be done
            parallel=False
        ),
        BatchConfig(
            batch_number=2,
            name="Features 3 & 4 (Trebuchet visual)",
            items=["3", "4"],
            depends_on=None,
            parallel=True
        ),
        BatchConfig(
            batch_number=3,
            name="Features 5 & 6 (Game progression)",
            items=["5", "6"],
            depends_on=None,
            parallel=True
        ),
        BatchConfig(
            batch_number=4,
            name="Features 7 & 8 (Power-ups & Messages)",
            items=["7", "8"],
            depends_on=None,
            parallel=True
        ),
    ]


def get_default_patch_rules() -> List[Dict[str, Any]]:
    """Get default patch rules for feature design consolidation"""
    return [
        {
            "source_name": "gpt5",
            "sections": [
                "User Stories",
                "Accessibility", 
                "Accessibility Requirements",
                "Config",
                "Configuration",
                "Config File Approach"
            ]
        },
        {
            "source_name": "composer",
            "sections": [
                "CSS Animations",
                "Animations",
                "Notes",
                "Definition of Done",
                "Definition of Done Checklist"
            ]
        }
    ]


# =============================================================================
# Design Document Detection
# =============================================================================

DESIGN_DOC_KEYWORDS = [
    "feature",
    "design",
    "spec",
    "specification",
    "plan",
    "architecture",
    "proposal",
    "requirement",
    "requirements"
]

EXCLUDE_KEYWORDS = [
    "comparison",
    "summary",
    "index",
    "meta",
    "consolidated",
    "combined"
]

META_DOCUMENT_NAMES = [
    "DESIGN_DOCUMENTS_SUMMARY.md",
    "DESIGN_DOCS_INDEX.md",
    "design_documents_summary.md",
    "design_docs_index.md"
]


class DesignDocumentDetector:
    """Detect design documents in a directory"""
    
    def __init__(
        self,
        directory: Path,
        keywords: Optional[List[str]] = None,
        exclude_keywords: Optional[List[str]] = None
    ):
        self.directory = Path(directory)
        self.keywords = [k.lower() for k in (keywords or DESIGN_DOC_KEYWORDS)]
        self.exclude_keywords = [k.lower() for k in (exclude_keywords or EXCLUDE_KEYWORDS)]
        self.meta_documents: Dict[str, Set[str]] = {}
        self._load_meta_documents()
    
    def _load_meta_documents(self):
        """Load meta documents to understand what are design documents"""
        for meta_name in META_DOCUMENT_NAMES:
            meta_path = self.directory / meta_name
            if meta_path.exists():
                try:
                    content = meta_path.read_text(encoding='utf-8')
                    # Extract document names from meta document
                    doc_names = self._parse_meta_document(content)
                    self.meta_documents[meta_name] = doc_names
                except Exception:
                    pass
    
    def _parse_meta_document(self, content: str) -> Set[str]:
        """
        Parse meta document to extract design document names.
        
        Looks for:
        - Markdown links: [text](filename.md)
        - File references: filename.md
        - List items with filenames
        """
        doc_names = set()
        
        # Extract markdown links
        link_pattern = re.compile(r'\[([^\]]+)\]\(([^\)]+\.md)\)', re.IGNORECASE)
        for match in link_pattern.finditer(content):
            doc_names.add(match.group(2).lower())
        
        # Extract .md filenames mentioned in text
        filename_pattern = re.compile(r'([A-Za-z0-9_\-]+\.md)', re.IGNORECASE)
        for match in filename_pattern.finditer(content):
            filename = match.group(1).lower()
            # Skip meta documents themselves
            if filename not in [m.lower() for m in META_DOCUMENT_NAMES]:
                doc_names.add(filename)
        
        return doc_names
    
    def is_design_document(self, filepath: Path) -> bool:
        """Determine if a file is a design document"""
        filename_lower = filepath.name.lower()
        
        # Always exclude if contains exclude keywords
        for exclude in self.exclude_keywords:
            if exclude in filename_lower:
                return False
        
        # Check meta documents first (authoritative)
        if self.meta_documents:
            for meta_name, doc_names in self.meta_documents.items():
                if filepath.name.lower() in doc_names:
                    return True
                # Also check without extension
                if filepath.stem.lower() in doc_names:
                    return True
        
        # Fall back to keyword matching
        for keyword in self.keywords:
            if keyword in filename_lower:
                return True
        
        return False
    
    def find_design_documents(self) -> List[Path]:
        """Find all design documents in the directory"""
        if not self.directory.exists():
            return []
        
        design_docs = []
        
        for filepath in self.directory.iterdir():
            if not filepath.is_file():
                continue
            
            if not filepath.suffix.lower() == '.md':
                continue
            
            if self.is_design_document(filepath):
                design_docs.append(filepath)
        
        # Sort by filename for consistent processing order
        return sorted(design_docs, key=lambda p: p.name.lower())


class AsyncDocumentUpdater:
    """
    Asynchronous document updater for processing directories sequentially.
    
    Processes design documents one at a time in sequence (not in parallel)
    to avoid overwhelming the system and ensure proper ordering.
    """
    
    def __init__(
        self,
        base_source_name: str,
        output_dir: Path,
        source_dirs: Dict[str, Path],
        patch_rules: Optional[List[Dict[str, Any]]] = None
    ):
        """
        Initialize async updater.
        
        Args:
            base_source_name: Name of the base source (e.g., "sonnet_45")
            output_dir: Directory for consolidated outputs
            source_dirs: Mapping of source names to directories
            patch_rules: Patch rules to apply (defaults to feature design rules)
        """
        self.base_source_name = base_source_name
        self.output_dir = Path(output_dir)
        self.source_dirs = {k: Path(v) for k, v in source_dirs.items()}
        self.patch_rules = patch_rules or get_default_patch_rules()
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.results: List[ConsolidationResult] = []
    
    async def process_document(self, doc_path: Path) -> ConsolidationResult:
        """
        Process a single design document asynchronously.
        
        This runs in sequence (not parallel) but uses async for better
        control and progress reporting.
        """
        # Determine feature number from filename if possible
        feature_num = self._extract_feature_number(doc_path)
        
        # Create consolidation config
        config = self._create_config_for_document(doc_path, feature_num)
        
        # Run consolidation (CPU-bound, but wrapped in async for control)
        loop = asyncio.get_event_loop()
        consolidator = DocumentConsolidator(config)
        result = await loop.run_in_executor(None, consolidator.consolidate)
        
        return result
    
    def _extract_feature_number(self, doc_path: Path) -> Optional[int]:
        """Try to extract feature number from filename"""
        # Look for patterns like FEATURE_2, Feature2, feature-2, etc.
        patterns = [
            r'feature[_\-\s]*(\d+)',
            r'f[_\-\s]*(\d+)',
        ]
        
        filename = doc_path.stem
        for pattern in patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    pass
        
        return None
    
    def _create_config_for_document(
        self,
        doc_path: Path,
        feature_num: Optional[int]
    ) -> ConsolidationConfig:
        """Create consolidation config for a document"""
        # The doc_path is from the base source directory
        # We need to find matching files in patch source directories
        
        # Build patch rules with actual file paths
        patch_rules = []
        
        for patch_def in self.patch_rules:
            source_name = patch_def["source_name"]
            source_dir = self.source_dirs.get(source_name)
            
            if source_dir:
                # Try to find matching file in source directory
                source_path = self._find_matching_source_file(
                    doc_path,
                    source_dir,
                    feature_num
                )
                
                if source_path:
                    patch_rules.append(PatchRule(
                        source_name=source_name,
                        source_path=source_path,
                        sections=patch_def["sections"]
                    ))
        
        # Output path (NEW file)
        output_name = f"{doc_path.stem}_consolidated{doc_path.suffix}"
        output_path = self.output_dir / output_name
        
        return ConsolidationConfig(
            name=f"Consolidation: {doc_path.name}",
            base_source_name=self.base_source_name,
            base_path=doc_path,
            patches=patch_rules,
            output_path=output_path,
            metadata={
                "original_file": str(doc_path),
                "feature_number": feature_num
            }
        )
    
    def _find_matching_source_file(
        self,
        base_file: Path,
        source_dir: Path,
        feature_num: Optional[int]
    ) -> Optional[Path]:
        """Find matching file in source directory"""
        if not source_dir.exists():
            return None
        
        base_name = base_file.name
        
        # Try exact match first
        exact_match = source_dir / base_name
        if exact_match.exists():
            return exact_match
        
        # Try with feature number
        if feature_num:
            patterns = [
                f"FEATURE_{feature_num}_DESIGN.md",
                f"FEATURE{feature_num}_DESIGN.md",
                f"feature_{feature_num}_design.md",
                f"Feature{feature_num}.md",
            ]
            
            for pattern in patterns:
                test_path = source_dir / pattern
                if test_path.exists():
                    return test_path
        
        # Try matching by stem (filename without extension)
        base_stem = base_file.stem
        for filepath in source_dir.glob("*.md"):
            if filepath.stem.lower() == base_stem.lower():
                return filepath
        
        return None
    
    async def process_directory(
        self,
        directory: Path,
        on_progress: Optional[callable] = None,
        on_complete: Optional[callable] = None
    ) -> List[ConsolidationResult]:
        """
        Process all design documents in a directory sequentially.
        
        The directory should contain design documents from the BASE source.
        Matching documents will be found in patch source directories.
        
        Args:
            directory: Directory containing base design documents
            on_progress: Callback(current, total, filename, result)
            on_complete: Callback(all_results)
            
        Returns:
            List of consolidation results
        """
        # Detect design documents
        detector = DesignDocumentDetector(directory)
        design_docs = detector.find_design_documents()
        
        if not design_docs:
            return []
        
        self.results = []
        
        total = len(design_docs)
        for i, doc_path in enumerate(design_docs, 1):
            # Process document
            result = await self.process_document(doc_path)
            self.results.append(result)
            
            # Report progress
            if on_progress:
                on_progress(i, total, doc_path.name, result)
        
        # Report completion
        if on_complete:
            on_complete(self.results)
        
        return self.results


# =============================================================================
# LangChain Integration (Optional)
# =============================================================================

class LangChainDocumentUpdater:
    """
    LangChain-powered document updater for intelligent section extraction.
    
    Uses Claude to intelligently identify and extract sections even when
    headings don't match exactly.
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = "claude-sonnet-4-20250514"):
        if not HAS_LANGCHAIN:
            raise ImportError(
                "LangChain not installed. Install with: "
                "pip install langchain langchain-anthropic"
            )
        
        import os
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("Anthropic API key required for LangChain integration")
        
        self.llm = ChatAnthropic(
            model=model,
            api_key=self.api_key,
            max_tokens=4096
        )
    
    def extract_section_intelligent(
        self,
        document_content: str,
        section_description: str
    ) -> Optional[str]:
        """
        Use LLM to intelligently extract a section from a document.
        
        Args:
            document_content: Full document text
            section_description: Description of what section to extract
            
        Returns:
            Extracted section content or None
        """
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a document section extractor. 
Extract the requested section from the provided document.
Return ONLY the section content including its heading.
If the section doesn't exist, return exactly: SECTION_NOT_FOUND"""),
            ("user", """Document:
{document}

---
Extract this section: {section}

Return the complete section with its heading, or SECTION_NOT_FOUND if it doesn't exist.""")
        ])
        
        chain = prompt | self.llm
        
        result = chain.invoke({
            "document": document_content[:50000],  # Limit size
            "section": section_description
        })
        
        content = result.content.strip()
        
        if content == "SECTION_NOT_FOUND":
            return None
        
        return content
    
    def suggest_section_mapping(
        self,
        base_sections: List[str],
        source_sections: List[str]
    ) -> Dict[str, str]:
        """
        Use LLM to suggest mapping between source sections and base sections.
        
        Returns dict mapping source sections to base sections they should replace.
        """
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a document structure analyst.
Given two lists of section headings, identify which sections from the source
should replace or supplement sections in the base document.

Return a JSON object mapping source sections to base sections.
Only include mappings where there's a clear match or relationship."""),
            ("user", """Base document sections:
{base_sections}

Source document sections:
{source_sections}

Return JSON mapping source -> base sections:""")
        ])
        
        chain = prompt | self.llm
        
        result = chain.invoke({
            "base_sections": "\n".join(f"- {s}" for s in base_sections),
            "source_sections": "\n".join(f"- {s}" for s in source_sections)
        })
        
        import json
        try:
            return json.loads(result.content)
        except json.JSONDecodeError:
            return {}


# =============================================================================
# Single Folder Auto-Detection Workflow
# =============================================================================

class DesignDocAuthor(str, Enum):
    SONNET = "sonnet_45"
    GPT5 = "gpt5"
    COMPOSER = "composer"
    UNKNOWN = "unknown"

class SingleFolderProcessor:
    """
    Process a single folder containing multiple versions of design docs.
    Recursive scanning and configurable rules.
    """
    
    def __init__(self, source_dir: Path, output_dir: Path, strategy: Optional[Dict] = None):
        self.source_dir = Path(source_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.strategy = strategy or self._default_strategy()
        
        self.groups: Dict[str, Dict[DesignDocAuthor, Path]] = {}
    
    def _default_strategy(self) -> Dict:
        return {
            "base_author": DesignDocAuthor.SONNET,
            "patches": [
                {
                    "author": DesignDocAuthor.GPT5,
                    "sections": ["User Stories", "Accessibility", "Config", "Configuration"]
                },
                {
                    "author": DesignDocAuthor.COMPOSER,
                    "sections": ["CSS Animations", "Animations", "Notes", "Definition of Done"]
                }
            ]
        }
    
    def detect_author(self, filepath: Path) -> DesignDocAuthor:
        """Detect author from filename, parent directory, OR file content"""
        # 1. Fast check: filename/dirname
        check_str = f"{filepath.parent.name.lower()}/{filepath.name.lower()}"
        
        if "sonnet" in check_str or "claude" in check_str or "anthropic" in check_str:
            return DesignDocAuthor.SONNET
        if "gpt5" in check_str or "gpt-5" in check_str or "openai" in check_str:
            return DesignDocAuthor.GPT5
        if "composer" in check_str or "cursor" in check_str:
            return DesignDocAuthor.COMPOSER
            
        # 2. Deep check: Read content
        try:
            # Read first 5000 chars to find metadata or key sections
            content = filepath.read_text(encoding='utf-8')[:5000].lower()
            
            # Explicit mentions in comments/metadata
            if "claude" in content or "anthropic" in content or "sonnet" in content:
                return DesignDocAuthor.SONNET
            if "gpt-5" in content or "openai" in content or "o1-preview" in content:
                return DesignDocAuthor.GPT5
            if "cursor" in content or "composer" in content:
                return DesignDocAuthor.COMPOSER
                
            # Structural signatures (based on unique sections)
            # GPT-5 typically has "User Stories" and "Accessibility" early on
            if "user stories" in content and "accessibility" in content:
                return DesignDocAuthor.GPT5
                
            # Composer typically has "Animations" and "Definition of Done"
            if "animations" in content and "definition of done" in content:
                return DesignDocAuthor.COMPOSER
                
            # Sonnet is typically the base structure (fallback if it looks comprehensive)
            if "architecture" in content and "system design" in content:
                return DesignDocAuthor.SONNET
                
        except Exception:
            pass
            
        return DesignDocAuthor.UNKNOWN

    def extract_feature_id(self, filename: str) -> str:
        """Extract feature ID (e.g. 'feature_1') from filename"""
        stem = Path(filename).stem.lower()
        # Match feature number, ignore leading zeros
        match = re.search(r'feature[_\-\s]*0*(\d+)', stem)
        if match:
            return f"feature_{match.group(1)}"
        return stem.split('_')[0]

    def scan_and_group(self):
        """Scan folder recursively and group files"""
        self.groups = {}
        logger.debug(f"Scanning {self.source_dir} for design documents...")
        
        # Use rglob for recursive search
        count = 0
        for filepath in self.source_dir.rglob("*.md"):
            if any(k in filepath.name.lower() for k in ["consolidated", "comparison", "summary", "index"]):
                continue
                
            feature_id = self.extract_feature_id(filepath.name)
            author = self.detect_author(filepath)
            
            logger.debug(f"Found: {filepath.name} -> Feature: {feature_id}, Author: {author}")
            
            if author == DesignDocAuthor.UNKNOWN:
                continue
                
            if feature_id not in self.groups:
                self.groups[feature_id] = {}
            
            self.groups[feature_id][author] = filepath
            count += 1
            
        logger.debug(f"Total grouped files: {count}")
        logger.debug(f"Groups: {list(self.groups.keys())}")
            
    def process_all(self, on_progress: Optional[callable] = None) -> List[ConsolidationResult]:
        """Run consolidation on all groups"""
        self.scan_and_group()
        results = []
        
        total = len(self.groups)
        current = 0
        
        sorted_groups = sorted(self.groups.items())
        
        base_author = self.strategy.get("base_author", DesignDocAuthor.SONNET)
        patches_config = self.strategy.get("patches", [])
        
        for feature_id, files in sorted_groups:
            current += 1
            
            # Determine base
            # Allow string match for author key in files
            base_path = files.get(base_author)
            if not base_path:
                # Try finding base by enum value
                for author, path in files.items():
                    if author == base_author:
                        base_path = path
                        break
            
            if not base_path:
                if on_progress:
                    on_progress(feature_id, f"Skipped (Missing {base_author} base)", current, total, False)
                continue
            
            # Build patches
            patch_rules = []
            
            for patch_cfg in patches_config:
                target_author = patch_cfg["author"]
                # Match author (enum or string)
                source_path = None
                for author, path in files.items():
                    if str(author) == str(target_author):
                        source_path = path
                        break
                
                if source_path:
                    patch_rules.append(PatchRule(
                        source_name=str(target_author),
                        source_path=source_path,
                        sections=patch_cfg["sections"]
                    ))
            
            if not patch_rules:
                if on_progress:
                    on_progress(feature_id, "Skipped (No patch sources found)", current, total, False)
                continue
                
            output_path = self.output_dir / f"{feature_id}_CONSOLIDATED.md"
            
            config = ConsolidationConfig(
                name=f"Smart Consolidation: {feature_id}",
                base_source_name=str(base_author),
                base_path=base_path,
                patches=patch_rules,
                output_path=output_path
            )
            
            consolidator = DocumentConsolidator(config)
            result = consolidator.consolidate()
            results.append(result)
            
            if on_progress:
                on_progress(feature_id, "Success", current, total, True)
                
        return results
