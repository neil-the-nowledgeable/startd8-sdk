"""
Document Chunking for Large Document Processing

Provides utilities to:
1. Detect when documents are too large for single-pass LLM processing
2. Split documents into logical chunks (by sections/headers)
3. Process chunks individually and reassemble results
4. Maintain document structure and coherence across chunks

This module enables the Design Polish Pipeline to handle documents of any size
by automatically detecting large documents and processing them in chunks.
"""

import re
from typing import List, Tuple, Optional, Dict, Any, Callable
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum


class ChunkingStrategy(Enum):
    """Strategy for splitting documents into chunks."""
    SECTION = "section"  # Split by markdown headers
    PARAGRAPH = "paragraph"  # Split by paragraphs
    TOKEN_ESTIMATE = "token_estimate"  # Split by estimated token count
    HYBRID = "hybrid"  # Combine section + token limits


@dataclass
class DocumentChunk:
    """A single chunk of a document."""
    index: int
    content: str
    start_line: int
    end_line: int
    section_path: List[str]  # Hierarchy of section headers (e.g., ["Introduction", "Background"])
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def char_count(self) -> int:
        return len(self.content)
    
    @property
    def estimated_tokens(self) -> int:
        """Rough estimate: ~4 characters per token for English text."""
        return self.char_count // 4


@dataclass
class ChunkedDocument:
    """A document split into chunks for processing."""
    original_content: str
    chunks: List[DocumentChunk]
    strategy: ChunkingStrategy
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def total_chunks(self) -> int:
        return len(self.chunks)
    
    @property
    def total_chars(self) -> int:
        return len(self.original_content)
    
    @property
    def estimated_tokens(self) -> int:
        return self.total_chars // 4


@dataclass
class LargeDocumentConfig:
    """Configuration for large document detection and processing."""
    # Detection thresholds
    max_chars_single_pass: int = 50_000  # ~12,500 tokens
    max_tokens_single_pass: int = 12_000  # Conservative for most models
    
    # Chunking settings
    target_chunk_chars: int = 20_000  # ~5,000 tokens per chunk
    min_chunk_chars: int = 2_000  # Don't create tiny chunks
    max_chunk_chars: int = 40_000  # Hard limit per chunk
    
    # Processing settings
    overlap_chars: int = 500  # Overlap between chunks for context
    preserve_sections: bool = True  # Try to keep sections intact
    
    # Strategy
    strategy: ChunkingStrategy = ChunkingStrategy.HYBRID


@dataclass 
class LargeDocumentDetectionResult:
    """Result of large document detection."""
    is_large: bool
    char_count: int
    estimated_tokens: int
    recommended_chunks: int
    reason: str
    config: LargeDocumentConfig
    
    def __bool__(self):
        return self.is_large


def detect_large_document(
    content: str,
    config: Optional[LargeDocumentConfig] = None
) -> LargeDocumentDetectionResult:
    """
    Detect if a document is too large for single-pass LLM processing.
    
    Args:
        content: Document content
        config: Configuration for detection thresholds
        
    Returns:
        LargeDocumentDetectionResult with detection details
    """
    config = config or LargeDocumentConfig()
    
    char_count = len(content)
    estimated_tokens = char_count // 4
    
    is_large = False
    reason = "Document is within size limits"
    
    if char_count > config.max_chars_single_pass:
        is_large = True
        reason = f"Document exceeds character limit ({char_count:,} > {config.max_chars_single_pass:,})"
    elif estimated_tokens > config.max_tokens_single_pass:
        is_large = True
        reason = f"Document exceeds token estimate ({estimated_tokens:,} > {config.max_tokens_single_pass:,})"
    
    # Calculate recommended chunks
    if is_large:
        recommended_chunks = max(2, (char_count // config.target_chunk_chars) + 1)
    else:
        recommended_chunks = 1
    
    return LargeDocumentDetectionResult(
        is_large=is_large,
        char_count=char_count,
        estimated_tokens=estimated_tokens,
        recommended_chunks=recommended_chunks,
        reason=reason,
        config=config
    )


def split_document_by_sections(
    content: str,
    config: Optional[LargeDocumentConfig] = None
) -> ChunkedDocument:
    """
    Split a document by markdown sections (headers).
    
    Preserves document structure by splitting at header boundaries.
    Attempts to keep related sections together when possible.
    
    Args:
        content: Document content
        config: Chunking configuration
        
    Returns:
        ChunkedDocument with section-based chunks
    """
    config = config or LargeDocumentConfig()
    
    # Parse sections from document
    sections = _parse_sections(content)
    
    if not sections:
        # No sections found, treat as single chunk
        return ChunkedDocument(
            original_content=content,
            chunks=[DocumentChunk(
                index=0,
                content=content,
                start_line=1,
                end_line=content.count('\n') + 1,
                section_path=[]
            )],
            strategy=ChunkingStrategy.SECTION
        )
    
    # Group sections into chunks based on size
    chunks = _group_sections_into_chunks(sections, config)
    
    return ChunkedDocument(
        original_content=content,
        chunks=chunks,
        strategy=ChunkingStrategy.SECTION,
        metadata={"section_count": len(sections)}
    )


def split_document_hybrid(
    content: str,
    config: Optional[LargeDocumentConfig] = None
) -> ChunkedDocument:
    """
    Split document using hybrid strategy: sections with token limits.
    
    First attempts to split by sections, then further splits any
    sections that exceed the token limit.
    
    Args:
        content: Document content
        config: Chunking configuration
        
    Returns:
        ChunkedDocument with hybrid chunks
    """
    config = config or LargeDocumentConfig()
    
    # First pass: split by sections
    section_chunks = split_document_by_sections(content, config)
    
    # Second pass: split any oversized chunks
    final_chunks = []
    chunk_index = 0
    
    for chunk in section_chunks.chunks:
        if chunk.char_count > config.max_chunk_chars:
            # Split this chunk further
            sub_chunks = _split_large_chunk(chunk, config, chunk_index)
            final_chunks.extend(sub_chunks)
            chunk_index += len(sub_chunks)
        else:
            chunk.index = chunk_index
            final_chunks.append(chunk)
            chunk_index += 1
    
    return ChunkedDocument(
        original_content=content,
        chunks=final_chunks,
        strategy=ChunkingStrategy.HYBRID,
        metadata={
            "original_section_chunks": len(section_chunks.chunks),
            "final_chunks": len(final_chunks)
        }
    )


def reassemble_chunks(
    processed_chunks: List[str],
    original_document: ChunkedDocument,
    separator: str = "\n\n"
) -> str:
    """
    Reassemble processed chunks back into a complete document.
    
    Args:
        processed_chunks: List of processed chunk contents (in order)
        original_document: Original ChunkedDocument for metadata
        separator: Separator between chunks
        
    Returns:
        Reassembled document content
    """
    if len(processed_chunks) != original_document.total_chunks:
        raise ValueError(
            f"Chunk count mismatch: got {len(processed_chunks)}, "
            f"expected {original_document.total_chunks}"
        )
    
    # Simple reassembly - join with separator
    # More sophisticated reassembly could handle overlaps
    return separator.join(processed_chunks)


def create_chunk_context(
    chunk: DocumentChunk,
    chunked_doc: ChunkedDocument,
    include_toc: bool = True
) -> str:
    """
    Create context information to prepend to a chunk for processing.
    
    Helps the LLM understand the chunk's position in the overall document.
    
    Args:
        chunk: The chunk being processed
        chunked_doc: The full chunked document
        include_toc: Whether to include table of contents
        
    Returns:
        Context string to prepend
    """
    context_parts = []
    
    # Position info
    context_parts.append(
        f"[CHUNK {chunk.index + 1} OF {chunked_doc.total_chunks}]"
    )
    
    # Section path
    if chunk.section_path:
        context_parts.append(f"Section: {' > '.join(chunk.section_path)}")
    
    # TOC if requested and multiple chunks
    if include_toc and chunked_doc.total_chunks > 1:
        toc = _generate_chunk_toc(chunked_doc)
        if toc:
            context_parts.append(f"\nDocument Structure:\n{toc}")
    
    context_parts.append("\n---\n")
    
    return "\n".join(context_parts)


def get_chunk_instructions(
    chunk: DocumentChunk,
    chunked_doc: ChunkedDocument,
    task: str = "polish"
) -> str:
    """
    Generate task-specific instructions for processing a chunk.
    
    Args:
        chunk: The chunk being processed
        chunked_doc: The full chunked document
        task: Type of task (polish, review, etc.)
        
    Returns:
        Instructions string
    """
    is_first = chunk.index == 0
    is_last = chunk.index == chunked_doc.total_chunks - 1
    
    instructions = []
    
    if task == "polish":
        instructions.append(
            "Polish this section of the document while maintaining consistency "
            "with the overall document structure."
        )
        
        if is_first:
            instructions.append(
                "This is the BEGINNING of the document. Preserve the title, "
                "introduction, and any front matter."
            )
        elif is_last:
            instructions.append(
                "This is the END of the document. Ensure proper conclusion "
                "and maintain any references or appendices."
            )
        else:
            instructions.append(
                "This is a MIDDLE section. Maintain continuity with surrounding "
                "sections and preserve section headers."
            )
        
        instructions.append(
            "IMPORTANT: Output ONLY the polished content for this section. "
            "Do not add introductory text or summaries about what you did."
        )
    
    return "\n".join(instructions)


# =============================================================================
# Internal Helper Functions
# =============================================================================

@dataclass
class _Section:
    """Internal representation of a document section."""
    level: int
    title: str
    content: str
    start_line: int
    end_line: int
    path: List[str]


def _parse_sections(content: str) -> List[_Section]:
    """Parse markdown sections from document content."""
    lines = content.split('\n')
    sections = []
    current_section = None
    section_stack = []  # Track hierarchy
    
    # Regex for markdown headers
    header_pattern = re.compile(r'^(#{1,6})\s+(.+)$')
    
    for i, line in enumerate(lines):
        match = header_pattern.match(line)
        
        if match:
            # Save previous section
            if current_section:
                current_section.end_line = i
                current_section.content = '\n'.join(
                    lines[current_section.start_line - 1:i]
                )
                sections.append(current_section)
            
            # Parse new header
            level = len(match.group(1))
            title = match.group(2).strip()
            
            # Update section stack for hierarchy
            while section_stack and section_stack[-1][0] >= level:
                section_stack.pop()
            section_stack.append((level, title))
            
            path = [t for _, t in section_stack]
            
            current_section = _Section(
                level=level,
                title=title,
                content="",
                start_line=i + 1,
                end_line=0,
                path=path
            )
    
    # Don't forget the last section
    if current_section:
        current_section.end_line = len(lines)
        current_section.content = '\n'.join(
            lines[current_section.start_line - 1:]
        )
        sections.append(current_section)
    
    # Handle content before first header
    if sections and sections[0].start_line > 1:
        preamble = '\n'.join(lines[:sections[0].start_line - 1])
        if preamble.strip():
            sections.insert(0, _Section(
                level=0,
                title="[Preamble]",
                content=preamble,
                start_line=1,
                end_line=sections[0].start_line - 1,
                path=["[Preamble]"]
            ))
    
    return sections


def _group_sections_into_chunks(
    sections: List[_Section],
    config: LargeDocumentConfig
) -> List[DocumentChunk]:
    """Group sections into appropriately-sized chunks."""
    chunks = []
    current_chunk_sections = []
    current_chunk_chars = 0
    chunk_index = 0
    
    for section in sections:
        section_chars = len(section.content)
        
        # Check if adding this section would exceed limits
        would_exceed = (
            current_chunk_chars + section_chars > config.target_chunk_chars
            and current_chunk_sections  # Don't create empty chunks
        )
        
        if would_exceed:
            # Finalize current chunk
            chunk = _create_chunk_from_sections(
                current_chunk_sections, chunk_index
            )
            chunks.append(chunk)
            chunk_index += 1
            current_chunk_sections = []
            current_chunk_chars = 0
        
        # Add section to current chunk
        current_chunk_sections.append(section)
        current_chunk_chars += section_chars
    
    # Don't forget the last chunk
    if current_chunk_sections:
        chunk = _create_chunk_from_sections(
            current_chunk_sections, chunk_index
        )
        chunks.append(chunk)
    
    return chunks


def _create_chunk_from_sections(
    sections: List[_Section],
    index: int
) -> DocumentChunk:
    """Create a DocumentChunk from a list of sections."""
    content = '\n\n'.join(s.content for s in sections)
    
    # Build section path from first section
    section_path = sections[0].path if sections else []
    
    return DocumentChunk(
        index=index,
        content=content,
        start_line=sections[0].start_line if sections else 1,
        end_line=sections[-1].end_line if sections else 1,
        section_path=section_path,
        metadata={
            "section_count": len(sections),
            "section_titles": [s.title for s in sections]
        }
    )


def _split_large_chunk(
    chunk: DocumentChunk,
    config: LargeDocumentConfig,
    start_index: int
) -> List[DocumentChunk]:
    """Split an oversized chunk into smaller pieces."""
    content = chunk.content
    target_size = config.target_chunk_chars
    
    # Split by paragraphs first
    paragraphs = re.split(r'\n\n+', content)
    
    sub_chunks = []
    current_content = []
    current_size = 0
    chunk_index = start_index
    
    for para in paragraphs:
        para_size = len(para)
        
        if current_size + para_size > target_size and current_content:
            # Create sub-chunk
            sub_chunks.append(DocumentChunk(
                index=chunk_index,
                content='\n\n'.join(current_content),
                start_line=chunk.start_line,  # Approximate
                end_line=chunk.end_line,
                section_path=chunk.section_path + [f"[Part {len(sub_chunks) + 1}]"],
                metadata={"split_from": chunk.index}
            ))
            chunk_index += 1
            current_content = []
            current_size = 0
        
        current_content.append(para)
        current_size += para_size
    
    # Last sub-chunk
    if current_content:
        sub_chunks.append(DocumentChunk(
            index=chunk_index,
            content='\n\n'.join(current_content),
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            section_path=chunk.section_path + [f"[Part {len(sub_chunks) + 1}]"],
            metadata={"split_from": chunk.index}
        ))
    
    return sub_chunks


def _generate_chunk_toc(chunked_doc: ChunkedDocument) -> str:
    """Generate a simple table of contents for chunk context."""
    toc_lines = []
    
    for chunk in chunked_doc.chunks:
        if chunk.section_path:
            # Use indentation based on section depth
            title = chunk.section_path[-1]
            indent = "  " * (len(chunk.section_path) - 1)
            marker = "→" if chunk == chunked_doc.chunks[0] else "-"
            toc_lines.append(f"{indent}{marker} {title}")
    
    return '\n'.join(toc_lines[:10])  # Limit TOC size

